// StreamBackend — headless romp sessions on ONE long-lived `claude` process
// per session (stream-json in/out), instead of HeadlessBackend's
// process-per-turn. Same engine, same transcripts, same registry/identity/
// states model (shared via headless-backend.ts exports) — what changes is the
// control channel and its costs:
//
//   per-turn spawn/boot/MCP reconnect  → paid once per session
//   per-turn --resume transcript fork  → ONE session id for the whole life
//                                        (fork only when resuming a dead one)
//   SIGINT-kills-the-turn              → control_request interrupt; the
//                                        process survives and takes next turn
//   state inferred from child exit     → state keyed on protocol events:
//                                        user msg written → working,
//                                        result event → waiting (exact,
//                                        event-based — no time heuristics)
//
// Protocol shapes are pinned by mock-claude.test.ts (probed live 2026-06-12):
// stdin takes {"type":"user",…} turns and {"type":"control_request",
// {"subtype":"interrupt"}}; stdout streams system:init (per turn, carries
// session_id + model), assistant/user messages, and a result event per turn
// (subtype success | error_during_execution). stdin EOF ends the process.
//
// Sends during an in-flight turn QUEUE (written to stdin; the CLI plays them
// sequentially) — matching what a tmux session does with mid-turn typed
// messages, where HeadlessBackend had to refuse them.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { randomUUID } from "crypto";
import type { SessionBackend, SessionState } from "./backend";
import {
  Reg, claudeBin, readReg, writeReg, listRegs,
  lastState, appendState, recordIdentity,
} from "./headless-backend";

// One live child + its protocol state. Exists only while the process runs;
// between processes (never started / crashed / killed) a session is just its
// registry + states files, exactly like HeadlessBackend.
interface Proc {
  child: ChildProcess;
  inflight: number;      // user turns written minus results seen
  sinceT: number;        // epoch s of the current working stretch
  model: string;         // from the latest system:init
  buf: string;
  reqSeq: number;        // control_request id counter
  endedByUs: boolean;    // kill() in progress — suppress crash recovery
}

export class StreamBackend implements SessionBackend {
  readonly tui = null;
  private procs = new Map<string, Proc>();

  liveSessions(): Map<string, SessionState> {
    const map = new Map<string, SessionState>();
    for (const r of listRegs()) {
      if (!r.alive) continue;
      const p = this.procs.get(r.name);
      const st = p && p.inflight > 0
        ? { state: "working", t: p.sinceT }
        : lastState(r.sid);
      map.set(r.name, {
        state: st.state || "waiting",
        effort: "",
        model: p?.model || "",
        ctx: "",
        since: st.t ? String(st.t) : "",
        summary: "",
      });
    }
    return map;
  }

  // Deliver a turn. Starts the session's process on first send; a send while
  // a turn is in flight queues behind it (the CLI consumes stdin sequentially).
  send(name: string, text: string): boolean {
    const r = readReg(name);
    if (!r || !r.alive) return false;
    let p = this.procs.get(name);
    if (!p) {
      const started = this.start(name, r);
      if (!started) return false;
      p = started;
    }
    try {
      p.child.stdin!.write(JSON.stringify({
        type: "user",
        message: { role: "user", content: [{ type: "text", text }] },
      }) + "\n");
    } catch { return false; }
    if (p.inflight === 0) p.sinceT = Math.floor(Date.now() / 1000);
    p.inflight++;
    appendState(r.sid, "working");
    return true;
  }

  // Interrupt the in-flight turn via the control protocol. The process
  // survives; the turn's result event (error_during_execution) settles state.
  interrupt(name: string): boolean {
    const p = this.procs.get(name);
    if (!p || p.inflight === 0) return false;
    try {
      p.child.stdin!.write(JSON.stringify({
        type: "control_request",
        request_id: "romp-" + ++p.reqSeq,
        request: { subtype: "interrupt" },
      }) + "\n");
      return true;
    } catch { return false; }
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
    try { fs.unlinkSync(path.join(registryDir(), oldName + ".json")); } catch { /* ignore */ }
    r.name = newName;
    writeReg(r);
    recordIdentity(r.sid, newName, r.dir);
    const p = this.procs.get(oldName);
    if (p) { this.procs.delete(oldName); this.procs.set(newName, p); }
    return true;
  }

  kill(name: string): boolean {
    const r = readReg(name);
    if (!r) return false;
    const p = this.procs.get(name);
    if (p) {
      p.endedByUs = true;
      this.interrupt(name);
      try { p.child.stdin!.end(); } catch { /* ignore */ }
      // 'close' is the real teardown event; SIGTERM is hung-child recovery
      // only (an external process can die without ever emitting an event).
      const t = setTimeout(() => { try { p.child.kill("SIGTERM"); } catch { /* ignore */ } }, 3000);
      t.unref();
      p.child.once("close", () => clearTimeout(t));
      this.procs.delete(name);
    }
    r.alive = false;
    writeReg(r);
    return true;
  }

  markIdle(name: string, _notAfter: number): void {
    const r = readReg(name);
    if (r) appendState(r.sid, "waiting");
  }

  // ---- process lifecycle ----

  private start(name: string, r: Reg): Proc | null {
    const args = [
      "-p",
      "--input-format", "stream-json",
      "--output-format", "stream-json",
      "--verbose",
      "--name", name,
    ];
    // First process claims the anchor sid (names/<sid> matches the transcript
    // file). A later process — after a crash or a revive — resumes the newest
    // transcript, which forks a new uuid we pick up from its init event.
    if (r.lastSid) args.push("--resume", r.lastSid);
    else args.push("--session-id", r.sid);
    const env = {
      ...process.env,
      ROMP_SESSION_ID: r.sid,        // the hooks' headless path keys on this
      ROMP_SESSION_NAME: name,
    };
    let child: ChildProcess;
    try {
      child = spawn(claudeBin(), args, {
        cwd: r.dir || os.homedir(),
        env,
        stdio: ["pipe", "pipe", "ignore"],
      });
    } catch { return null; }
    const p: Proc = { child, inflight: 0, sinceT: 0, model: "", buf: "", reqSeq: 0, endedByUs: false };
    // Handlers key on the ANCHOR SID, not the name: a session can be renamed
    // while a turn is in flight, and events that resolve the registry by a
    // captured name would miss and leave the state stuck on "working".
    const sid = r.sid;
    child.stdout!.on("data", (d) => this.onData(sid, p, String(d)));
    child.on("error", () => this.onGone(sid, p));
    child.on("close", () => this.onGone(sid, p));
    this.procs.set(name, p);
    return p;
  }

  private onData(sid: string, p: Proc, chunk: string) {
    p.buf += chunk;
    let i;
    while ((i = p.buf.indexOf("\n")) >= 0) {
      const line = p.buf.slice(0, i);
      p.buf = p.buf.slice(i + 1);
      if (!line.trim().startsWith("{")) continue;
      let o: any;
      try { o = JSON.parse(line); } catch { continue; }
      const r = regBySid(sid);
      if (o.type === "system" && o.subtype === "init") {
        if (o.model) p.model = String(o.model);
        // a resumed process announces its forked uuid here — track it as the
        // next resume target (the anchor sid, and states keyed on it, stay)
        const fsid = String(o.session_id || "");
        if (r && fsid && fsid !== r.lastSid && fsid !== r.sid) { r.lastSid = fsid; writeReg(r); }
        else if (r && fsid === r.sid && !r.lastSid) { r.lastSid = fsid; writeReg(r); }
      } else if (o.type === "result") {
        p.inflight = Math.max(0, p.inflight - 1);
        if (p.inflight === 0 && r) appendState(r.sid, "waiting");
        const fsid = String(o.session_id || "");
        if (r && fsid && fsid !== r.lastSid) { r.lastSid = fsid; writeReg(r); }
      }
    }
  }

  // Process ended — by kill(), by stdin EOF, or by a crash. Drop the proc so
  // the NEXT send restarts via --resume lastSid; settle state from the event
  // (no timers: this IS the exit event). Map cleanup is by proc identity —
  // the entry's key may have changed under a rename.
  private onGone(sid: string, p: Proc) {
    let found = false;
    for (const [n, q] of this.procs) {
      if (q === p) { this.procs.delete(n); found = true; }
    }
    if (!found) return;   // already replaced/removed (e.g. kill())
    const r = regBySid(sid);
    if (r && r.alive && !p.endedByUs) appendState(r.sid, "waiting");
  }
}

// Resolve a registry entry by its stable anchor sid (names change; sids don't).
function regBySid(sid: string): Reg | null {
  return listRegs().find((r) => r.sid === sid) ?? null;
}

function registryDir(): string {
  return path.join(
    process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
    "romp", "headless",
  );
}
