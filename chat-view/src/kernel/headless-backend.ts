// HeadlessBackend — romp sessions WITHOUT tmux, hosted on headless Claude Code
// (`claude -p`, the same engine the Agent SDK drives). Each send() runs one
// turn as a child process; between turns a session is just its files. Because
// headless Claude writes the SAME transcript format to ~/.claude/projects, the
// whole romp pipeline (romp-events, summarizer, feed, timeline) works on these
// sessions unchanged.
//
// What replaces each tmux mechanism:
//   session container   → a registry file (ROMP_STATE/headless/<name>.json)
//   @romp tag           → presence in that registry
//   @claude-state vars  → states/<sid>.jsonl, written here on turn start/end
//                         (the hooks' headless path writes the same file and
//                         dedupes by last-state, so both can be active)
//   send-keys           → spawning the next `claude -p --resume` turn
//   capture-pane        → none: tui = null (no live picker mirroring; asks
//                         surface through the transcript instead)
//
// A resumed turn forks a NEW transcript uuid (same as interactive resume);
// `--name` keeps the customTitle stable so romp-events' fork-join finds every
// transcript of the session. The registry tracks the latest fsid via the
// `session_id` field of --output-format json.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { randomUUID } from "crypto";
import type { SessionBackend, SessionState } from "./backend";

// Resolved at CALL time, not module load: tests (and long-lived kernels) may
// point XDG_STATE_HOME elsewhere after this module is imported — ESM hoists
// imports above any caller's env assignment, so a module-load constant would
// silently bind to the real state dir.
function rompState(): string {
  return path.join(
    process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
    "romp",
  );
}
const REGISTRY = () => path.join(rompState(), "headless");
const NAMES = () => path.join(rompState(), "names");
const STATES = () => path.join(rompState(), "states");

// The registry + identity + durable-state model is SHARED with StreamBackend
// (stream-backend.ts): both engines host "headless" sessions — same registry
// dir, same names/<sid> records, same states/<sid>.jsonl — so a session
// started under one engine can be picked up by the other (resume via lastSid).
export interface Reg {
  name: string;
  sid: string;       // anchor session id (names/<sid> identity record key)
  lastSid: string;   // newest transcript uuid (resume target)
  dir: string;
  alive: boolean;
}

export function claudeBin(): string {
  return process.env.ROMP_CLAUDE_BIN || "claude";
}

export function readReg(name: string): Reg | null {
  try {
    const o = JSON.parse(fs.readFileSync(path.join(REGISTRY(), name + ".json"), "utf8"));
    return o && o.sid ? o as Reg : null;
  } catch { return null; }
}

export function writeReg(r: Reg) {
  try {
    fs.mkdirSync(REGISTRY(), { recursive: true });
    const f = path.join(REGISTRY(), r.name + ".json");
    fs.writeFileSync(f + ".tmp", JSON.stringify(r));
    fs.renameSync(f + ".tmp", f);
  } catch { /* ignore */ }
}

export function listRegs(): Reg[] {
  try {
    return fs.readdirSync(REGISTRY())
      .filter((f) => f.endsWith(".json"))
      .map((f) => { try { return JSON.parse(fs.readFileSync(path.join(REGISTRY(), f), "utf8")) as Reg; } catch { return null; } })
      .filter((r): r is Reg => !!r && !!r.sid);
  } catch { return []; }
}

export function lastState(sid: string): { state: string; t: number } {
  try {
    const lines = fs.readFileSync(path.join(STATES(), sid + ".jsonl"), "utf8").trim().split("\n");
    const o = JSON.parse(lines[lines.length - 1]);
    return { state: String(o.state || ""), t: Number(o.t) || 0 };
  } catch { return { state: "", t: 0 }; }
}

export function appendState(sid: string, state: string) {
  if (lastState(sid).state === state) return;   // same dedupe rule as the hook
  try {
    fs.mkdirSync(STATES(), { recursive: true });
    fs.appendFileSync(path.join(STATES(), sid + ".jsonl"),
      JSON.stringify({ t: Math.floor(Date.now() / 1000), state }) + "\n");
  } catch { /* ignore */ }
}

// The romp identity palette — same hexes (and fg pairings) bin/romp assigns,
// so headless and tmux sessions draw from one visual identity system.
const PALETTE: Array<[string, string]> = [
  ["#1EA1EB", "white"], ["#54B204", "black"], ["#9088F0", "black"],
  ["#4EA8A9", "white"], ["#DD42FF", "white"], ["#E87221", "black"],
  ["#98998A", "black"], ["#F85B5A", "white"], ["#F9D849", "black"],
];

// First palette color not used by another ALIVE headless session; name-hash
// fallback when all are taken (mirrors bin/romp's rule).
function pickColor(name: string): [string, string] {
  const used = new Set<string>();
  for (const r of listRegs()) {
    if (!r.alive) continue;
    try {
      const bg = fs.readFileSync(path.join(NAMES(), r.sid), "utf8").split("\t")[2]?.trim();
      if (bg) used.add(bg);
    } catch { /* ignore */ }
  }
  for (const c of PALETTE) if (!used.has(c[0])) return c;
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function recordIdentity(sid: string, name: string, dir: string, color?: [string, string]) {
  // names/<sid> = name\tdir\tbg\tfg — same record bin/romp's _romp_record
  // writes. Keep an existing color when present (a resume/rename must not
  // re-roll identity); assign from the palette otherwise.
  let bg = "", fg = "";
  try {
    const prev = fs.readFileSync(path.join(NAMES(), sid), "utf8").split("\t");
    bg = prev[2]?.trim() || ""; fg = prev[3]?.trim() || "";
  } catch { /* new record */ }
  if (!bg) [bg, fg] = color ?? pickColor(name);
  try {
    fs.mkdirSync(NAMES(), { recursive: true });
    fs.writeFileSync(path.join(NAMES(), sid), `${name}\t${dir}\t${bg}\t${fg}\n`);
  } catch { /* ignore */ }
}

export class HeadlessBackend implements SessionBackend {
  readonly tui = null;
  // In-flight turn child per session name (this kernel is the only spawner).
  private running = new Map<string, ChildProcess>();

  liveSessions(): Map<string, SessionState> {
    const map = new Map<string, SessionState>();
    for (const r of listRegs()) {
      if (!r.alive) continue;
      const st = this.running.has(r.name) ? { state: "working", t: Math.floor(Date.now() / 1000) } : lastState(r.sid);
      map.set(r.name, {
        state: st.state || "waiting",
        effort: "", model: "", ctx: "",
        since: st.t ? String(st.t) : "",
        summary: "",
      });
    }
    return map;
  }

  // One turn: claude -p, resuming the newest transcript, keeping the session
  // name (customTitle) stable. Updates lastSid from the result JSON.
  send(name: string, text: string): boolean {
    const r = readReg(name);
    if (!r || !r.alive) return false;
    if (this.running.has(name)) return false;   // one turn at a time
    const args = ["-p", text, "--output-format", "json", "--name", name];
    // First turn: claim the anchor sid (names/<sid> must match the transcript
    // filename — same trick as bin/romp's self-assigned --session-id). Later
    // turns resume the newest fork.
    if (r.lastSid) args.push("--resume", r.lastSid);
    else args.push("--session-id", r.sid);
    const env = {
      ...process.env,
      ROMP_SESSION_ID: r.sid,        // the hooks' headless path keys on this
      ROMP_SESSION_NAME: name,
    };
    let child: ChildProcess;
    try {
      child = spawn(claudeBin(), args, { cwd: r.dir || os.homedir(), env, stdio: ["ignore", "pipe", "pipe"] });
    } catch { return false; }
    this.running.set(name, child);
    appendState(r.sid, "working");
    let out = "";
    child.stdout?.on("data", (d) => { out += String(d); });
    // Turn-end handlers key on the child + the stable anchor sid, NOT the
    // captured name or reg object: a mid-turn rename() moves the running-map
    // entry and rewrites the registry under the new name, so deleting the old
    // key would leak the entry (stuck "working") and writeReg(r) would
    // resurrect the old-name registry file with a stale lastSid.
    const sid = r.sid;
    const done = () => {
      for (const [n, c] of this.running) if (c === child) this.running.delete(n);
      appendState(sid, "waiting");
    };
    child.on("error", done);
    child.on("close", () => {
      done();
      try {
        const res = JSON.parse(out);
        const fsid = String(res.session_id || "");
        const cur = listRegs().find((x) => x.sid === sid);
        if (fsid && cur) { cur.lastSid = fsid; writeReg(cur); }
      } catch { /* non-JSON output (error turn) — keep the old resume target */ }
    });
    return true;
  }

  interrupt(name: string): boolean {
    const child = this.running.get(name);
    if (!child) return false;
    try { child.kill("SIGINT"); return true; } catch { return false; }
  }

  spawn(name: string, cwd: string): Promise<boolean> {
    if (readReg(name)?.alive) return Promise.resolve(false);
    const sid = randomUUID();
    const dir = fs.existsSync(cwd) ? fs.realpathSync(cwd) : cwd;
    recordIdentity(sid, name, dir);
    writeReg({ name, sid, lastSid: "", dir, alive: true });
    appendState(sid, "waiting");
    return Promise.resolve(true);
  }

  resume(name: string, id: string, cwd?: string): boolean {
    const prev = readReg(name);
    const dir = cwd || prev?.dir || os.homedir();
    recordIdentity(id, name, dir);
    writeReg({ name, sid: id, lastSid: id, dir, alive: true });
    appendState(id, "waiting");
    return true;
  }

  rename(oldName: string, newName: string): boolean {
    const r = readReg(oldName);
    if (!r || readReg(newName)) return false;
    try { fs.unlinkSync(path.join(REGISTRY(), oldName + ".json")); } catch { /* ignore */ }
    r.name = newName;
    writeReg(r);
    recordIdentity(r.sid, newName, r.dir);
    const child = this.running.get(oldName);
    if (child) { this.running.delete(oldName); this.running.set(newName, child); }
    return true;
  }

  kill(name: string): boolean {
    const r = readReg(name);
    if (!r) return false;
    this.interrupt(name);
    r.alive = false;
    writeReg(r);
    return true;
  }

  markIdle(name: string, _notAfter: number): void {
    const r = readReg(name);
    if (r) appendState(r.sid, "waiting");
  }
}

export { REGISTRY as headlessRegistryDir };
