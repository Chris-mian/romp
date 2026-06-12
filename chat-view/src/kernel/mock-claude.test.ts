// Pins the mock-claude imposter to the real CLI's stream-json protocol
// (shapes probed live 2026-06-12 — see mock-claude.ts header). These tests are
// the executable spec StreamBackend is built against: if the mock drifts from
// what the probes established, fix the mock, not the backend.
//
// All scenario content is synthetic (privacy rule).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { writeMockClaude, writeScenario, mockCalls, MockScenario } from "./mock-claude";

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "romp-mock-claude-"));

const SCENARIO: MockScenario = {
  sessionId: "00000000-0000-4000-8000-000000000001",
  turns: [
    {
      steps: [
        { kind: "tool", name: "Bash", input: { command: "echo synthetic-one" }, result: "synthetic-one" },
        { kind: "text", text: "synthetic narration" },
      ],
      resultText: "FIRST",
    },
    { resultText: "SECOND" },
  ],
};

// Tiny driver: spawn the imposter in stream input mode, collect parsed events,
// resolve waiters as events land (event-based — no sleeps).
class Driver {
  proc: ChildProcess;
  events: any[] = [];
  private waiters: Array<{ pred: (e: any) => boolean; resolve: (e: any) => void }> = [];
  private buf = "";
  exit: Promise<number | null>;

  constructor(bin: string, extraArgs: string[] = []) {
    this.proc = spawn(bin, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", ...extraArgs], { cwd: TMP });
    this.proc.stdout!.on("data", (d) => {
      this.buf += String(d);
      let i;
      while ((i = this.buf.indexOf("\n")) >= 0) {
        const line = this.buf.slice(0, i); this.buf = this.buf.slice(i + 1);
        if (!line.trim()) continue;
        let o; try { o = JSON.parse(line); } catch { continue; }
        this.events.push(o);
        this.waiters = this.waiters.filter((w) => (w.pred(o) ? (w.resolve(o), false) : true));
      }
    });
    this.exit = new Promise((r) => this.proc.on("close", (code) => r(code)));
  }
  send(text: string) {
    this.proc.stdin!.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text }] } }) + "\n");
  }
  interrupt(requestId: string) {
    this.proc.stdin!.write(JSON.stringify({ type: "control_request", request_id: requestId, request: { subtype: "interrupt" } }) + "\n");
  }
  next(pred: (e: any) => boolean): Promise<any> {
    const hit = this.events.find(pred);
    if (hit) return Promise.resolve(hit);
    return new Promise((resolve) => this.waiters.push({ pred, resolve }));
  }
  end() { this.proc.stdin!.end(); }
}

test("stream mode: two turns, one process, one session_id, init per turn", async () => {
  const dir = path.join(TMP, "basic");
  const bin = writeMockClaude(dir, SCENARIO);
  const d = new Driver(bin);
  d.send("synthetic ask one");
  const r1 = await d.next((e) => e.type === "result");
  assert.equal(r1.subtype, "success");
  assert.equal(r1.result, "FIRST");
  d.send("synthetic ask two");
  const r2 = await d.next((e) => e.type === "result" && e.result === "SECOND");
  assert.equal(r2.is_error, false);
  d.end();
  assert.equal(await d.exit, 0);

  const sids = new Set(d.events.filter((e) => e.session_id).map((e) => e.session_id));
  assert.deepEqual([...sids], [SCENARIO.sessionId], "one session_id across turns");
  const inits = d.events.filter((e) => e.type === "system" && e.subtype === "init");
  assert.equal(inits.length, 2, "init re-emitted per turn");
  assert.equal(inits[0].model, "mock-model-1");

  // tool steps come through as a tool_use/tool_result pair with matching ids
  const tu = d.events.find((e) => e.type === "assistant" && e.message.content[0]?.type === "tool_use");
  const tr = d.events.find((e) => e.type === "user" && e.message.content[0]?.type === "tool_result");
  assert.ok(tu && tr);
  assert.equal(tu.message.content[0].name, "Bash");
  assert.equal(tr.message.content[0].tool_use_id, tu.message.content[0].id);
  assert.equal(tr.message.content[0].is_error, false);
});

test("interrupt mid-turn: control_response ack, aborted result, process survives", async () => {
  const dir = path.join(TMP, "intr");
  const gate = path.join(dir, "release-the-turn");
  const bin = writeMockClaude(dir, {
    sessionId: "00000000-0000-4000-8000-000000000002",
    turns: [
      { steps: [{ kind: "text", text: "started" }, { kind: "gate", file: gate }], resultText: "NEVER" },
      { resultText: "ALIVE" },
    ],
  });
  const d = new Driver(bin);
  d.send("synthetic long task");
  await d.next((e) => e.type === "assistant"); // turn is provably in flight
  d.interrupt("rq-1");
  const ack = await d.next((e) => e.type === "control_response");
  assert.equal(ack.response.subtype, "success");
  assert.equal(ack.response.request_id, "rq-1");
  const r1 = await d.next((e) => e.type === "result");
  assert.equal(r1.subtype, "error_during_execution");
  assert.equal(r1.is_error, true);
  assert.equal(r1.terminal_reason, "aborted_streaming");
  // same process takes the next turn (this is the no-respawn property)
  d.send("synthetic follow-up");
  const r2 = await d.next((e) => e.type === "result" && e.result === "ALIVE");
  assert.equal(r2.subtype, "success");
  d.end();
  assert.equal(await d.exit, 0, "clean final turn → exit 0");
});

test("session identity: --session-id wins; --resume forks a new id; argv logged", async () => {
  const dir = path.join(TMP, "ident");
  const bin = writeMockClaude(dir, { sessionId: "00000000-0000-4000-8000-00000000000a", turns: [{ resultText: "ok" }] });

  const d1 = new Driver(bin, ["--session-id", "11111111-0000-4000-8000-000000000001"]);
  d1.send("x");
  const r1 = await d1.next((e) => e.type === "result");
  assert.equal(r1.session_id, "11111111-0000-4000-8000-000000000001");
  d1.end(); await d1.exit;

  const d2 = new Driver(bin, ["--resume", "11111111-0000-4000-8000-000000000001", "--name", "synthetic-name"]);
  d2.send("y");
  const r2 = await d2.next((e) => e.type === "result");
  assert.equal(r2.session_id, "fork-11111111-0000-4000-8000-000000000001", "resume forks a NEW session id");
  d2.end(); await d2.exit;

  const calls = mockCalls(dir);
  assert.equal(calls.length, 2);
  assert.match(calls[1], /--resume 11111111-0000-4000-8000-000000000001/);
  assert.match(calls[1], /--name synthetic-name/);
});

test("single-shot -p --output-format json keeps the old headless contract", async () => {
  const dir = path.join(TMP, "oneshot");
  const bin = writeMockClaude(dir, { sessionId: "00000000-0000-4000-8000-00000000000b", turns: [{ resultText: "oneshot-ok" }] });
  const out: string = await new Promise((resolve, reject) => {
    const p = spawn(bin, ["-p", "synthetic prompt", "--output-format", "json"], { cwd: TMP });
    let s = "";
    p.stdout.on("data", (d) => (s += String(d)));
    p.on("close", (code) => (code === 0 ? resolve(s) : reject(new Error("exit " + code))));
  });
  const res = JSON.parse(out.trim());
  assert.equal(res.type, "result");
  assert.equal(res.result, "oneshot-ok");
  assert.equal(res.session_id, "00000000-0000-4000-8000-00000000000b");
});

test("scenario rewrite mid-process takes effect on the next turn", async () => {
  const dir = path.join(TMP, "rewrite");
  const bin = writeMockClaude(dir, { sessionId: "00000000-0000-4000-8000-00000000000c", turns: [{ resultText: "BEFORE" }] });
  const d = new Driver(bin);
  d.send("a");
  await d.next((e) => e.type === "result" && e.result === "BEFORE");
  writeScenario(dir, { sessionId: "00000000-0000-4000-8000-00000000000c", turns: [{ resultText: "AFTER" }] });
  d.send("b");
  const r = await d.next((e) => e.type === "result" && e.result === "AFTER");
  assert.equal(r.subtype, "success");
  d.end();
  await d.exit;
});
