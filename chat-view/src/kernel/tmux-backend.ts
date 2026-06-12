// The tmux SessionBackend: romp's original substrate. Sessions are tmux
// sessions tagged @romp; state lives in tmux user options set by the Claude
// Code hooks; input is send-keys/paste-buffer; live picker screens are
// capture-pane. Ported from chat-view/src/extension.ts (the VS Code host).
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { execSync, execFileSync, execFile } from "child_process";
import type { SessionBackend, SessionState, TuiOps } from "./backend";

const ROMP_STATE = () => path.join(
  process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
  "romp",
);
const ROMP_NAMES = () => path.join(ROMP_STATE(), "names");

// Find the actual tmux server socket file (default server). Passing it with
// `-S` bypasses any inherited $TMUX / TMUX_TMPDIR entirely.
function tmuxSocket(): string | null {
  const uid = typeof process.getuid === "function" ? process.getuid() : 0;
  for (const dir of ["/tmp", process.env.TMUX_TMPDIR, process.env.TMPDIR, os.tmpdir()]) {
    if (!dir) continue;
    const s = path.join(dir, `tmux-${uid}`, "default");
    try { if (fs.existsSync(s)) return s; } catch { /* ignore */ }
  }
  return null;
}

function tmuxEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PATH: `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${process.env.PATH || ""}`,
  };
  // The host process may have inherited a $TMUX client socket pointing at the
  // wrong server (empty result). Clear it so we use the TMUX_TMPDIR socket.
  delete env.TMUX;
  const uid = typeof process.getuid === "function" ? process.getuid() : 0;
  for (const dir of ["/tmp", process.env.TMUX_TMPDIR, process.env.TMPDIR, os.tmpdir()]) {
    if (!dir) continue;
    try {
      if (fs.existsSync(path.join(dir, `tmux-${uid}`, "default"))) { env.TMUX_TMPDIR = dir; break; }
    } catch { /* ignore */ }
  }
  return env;
}

function tmuxArgs(extra: string[]): string[] {
  const sock = tmuxSocket();
  return sock ? ["-S", sock, ...extra] : extra;
}

function T(args: string[]): string {
  return execFileSync("tmux", tmuxArgs(args), { env: tmuxEnv(), timeout: 4000, encoding: "utf8" });
}

const TMUX_FMT = "'#{session_name}|#{@romp}|#{@claude-state}|#{@claude-effort}|#{@claude-model}|#{@claude-context}|#{@claude-state-since}|#{@claude-summary}'";

function runShell(cmd: string): string {
  try {
    return execSync(cmd, { env: tmuxEnv(), encoding: "utf8", timeout: 2500, stdio: ["ignore", "pipe", "pipe"] });
  } catch (e: any) {
    return String(e?.stdout || "");
  }
}

function parseTmux(out: string): Map<string, SessionState> {
  const map = new Map<string, SessionState>();
  for (const line of out.split("\n")) {
    const p = line.split("|");
    if (p.length < 2 || p[1].trim() !== "1") continue;
    // @claude-summary may itself contain '|', so it's the last field — rejoin the tail.
    map.set(p[0].trim(), { state: (p[2] || "").trim(), effort: (p[3] || "").trim(), model: (p[4] || "").trim(), ctx: (p[5] || "").trim(), since: (p[6] || "").trim(), summary: p.slice(7).join("|").trim() });
  }
  return map;
}

// The real login-shell PATH (cached): the romp launcher lives on the
// interactive shell's PATH but not on tmuxEnv()'s minimal one.
let loginPath: string | null = null;
function loginShellPath(): string {
  if (loginPath !== null) return loginPath;
  const shell = process.env.SHELL || "/bin/zsh";
  try {
    loginPath = (execFileSync(shell, ["-lic", 'printf %s "$PATH"'], { timeout: 4000, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }) || "").trim();
  } catch { loginPath = ""; }
  return loginPath;
}
function launchEnv(): NodeJS.ProcessEnv {
  const env = tmuxEnv();
  const login = loginShellPath();
  if (login) env.PATH = login + ":" + (env.PATH || "");
  return env;
}

function rompBin(): string {
  // ROMP_BIN lets a packaged install point anywhere; fall back to PATH.
  if (process.env.ROMP_BIN) return process.env.ROMP_BIN;
  return "romp";
}

const tui: TuiOps = {
  capturePane(name: string): string {
    try {
      return execFileSync("tmux", tmuxArgs(["capture-pane", "-p", "-t", name]), { env: tmuxEnv(), timeout: 3000, encoding: "utf8" });
    } catch { return ""; }
  },
  sendKeys(name: string, keys: string[]): void {
    if (!keys.length) return;
    try {
      try { if (T(["display-message", "-p", "-t", name, "#{pane_in_mode}"]).trim() === "1") T(["send-keys", "-t", name, "-X", "cancel"]); } catch { /* not in copy-mode */ }
      T(["send-keys", "-t", name, ...keys]);
    } catch { /* pane gone */ }
  },
  sendLiteral(name: string, text: string): void {
    try {
      try { if (T(["display-message", "-p", "-t", name, "#{pane_in_mode}"]).trim() === "1") T(["send-keys", "-t", name, "-X", "cancel"]); } catch { /* not in copy-mode */ }
      T(["send-keys", "-t", name, "-l", text]);
    } catch { /* pane gone */ }
  },
};

export class TmuxBackend implements SessionBackend {
  readonly tui = tui;

  liveSessions(): Map<string, SessionState> {
    const sock = tmuxSocket();
    const direct = (sock ? `tmux -S ${JSON.stringify(sock)}` : "tmux") + ` list-sessions -F ${TMUX_FMT}`;
    let map = parseTmux(runShell(direct));
    if (map.size === 0) {
      // Fallback through a login+interactive shell, which reproduces the
      // terminal env where tmux can reach the server.
      const viaLogin = parseTmux(runShell(`zsh -ilc ${JSON.stringify(`tmux list-sessions -F ${TMUX_FMT}`)}`));
      if (viaLogin.size > 0) map = viaLogin;
    }
    return map;
  }

  send(name: string, text: string): boolean {
    const BUF = "romp-chat-view";
    try {
      // exit copy-mode if the pane is scrolled, so the paste + Enter actually land
      try { if (T(["display-message", "-p", "-t", name, "#{pane_in_mode}"]).trim() === "1") T(["send-keys", "-t", name, "-X", "cancel"]); } catch { /* not in copy-mode */ }
      T(["set-buffer", "-b", BUF, text]);
      T(["paste-buffer", "-b", BUF, "-d", "-p", "-t", name]); // -p bracketed paste, -d delete buffer after
      // brief gap so the bracketed paste is fully received before Enter submits it
      setTimeout(() => { try { T(["send-keys", "-t", name, "Enter"]); } catch { /* ignore */ } }, 250);
      return true;
    } catch { return false; }
  }

  interrupt(name: string): boolean {
    // Esc INTERRUPTS the current response in Claude Code; Ctrl+C is the EXIT key.
    try { T(["send-keys", "-t", name, "Escape"]); return true; }
    catch { return false; }
  }

  spawn(name: string, cwd: string): Promise<boolean> {
    return new Promise((resolve) => {
      execFile(rompBin(), ["--detach", name], { cwd, env: launchEnv(), timeout: 20000 }, (err) => resolve(!err));
    });
  }

  resume(name: string, id: string, cwd?: string): boolean {
    try {
      execSync(`${JSON.stringify(rompBin())} ${JSON.stringify(name)} --resume ${JSON.stringify(id)} --detach`, {
        env: launchEnv(), cwd: cwd || undefined, timeout: 12000, stdio: ["ignore", "ignore", "ignore"],
      });
      return true;
    } catch { return false; }
  }

  rename(oldName: string, newName: string): boolean {
    try { T(["rename-session", "-t", "=" + oldName, newName]); return true; }
    catch { return false; }
  }

  kill(name: string): boolean {
    // Exact target (=name) so we never kill a prefix-matched neighbor.
    try { T(["kill-session", "-t", "=" + name]); return true; }
    catch { return false; }
  }

  // Mirror the Stop branch of tmux-status.sh (state + since + emoji + the
  // transition the timeline reads). Guarded: only clears working/compacting and
  // never clobbers a NEWER hook event.
  markIdle(name: string, notAfter: number): void {
    try {
      const prev = T(["show", "-t", name, "-v", "@claude-state"]).trim();
      if (prev !== "working" && prev !== "compacting") return;
      const since = parseInt(T(["show", "-t", name, "-v", "@claude-state-since"]).trim(), 10);
      if (since && since > notAfter) return;   // a newer event fired → leave it alone
      const now = Math.floor(Date.now() / 1000);
      T(["set", "-t", name, "@claude-state", "waiting"]);
      T(["set", "-t", name, "@claude-state-since", String(now)]);
      T(["set", "-t", name, "@romp-emoji", "🔵"]);
      const sid = T(["show", "-t", name, "-v", "@romp-session-id"]).trim();
      if (sid) {
        const dir = path.join(ROMP_STATE(), "states");
        try { fs.mkdirSync(dir, { recursive: true }); fs.appendFileSync(path.join(dir, `${sid}.jsonl`), JSON.stringify({ t: now, state: "waiting" }) + "\n"); } catch { /* ignore */ }
      }
    } catch { /* pane gone */ }
  }
}

export { ROMP_STATE, ROMP_NAMES };
