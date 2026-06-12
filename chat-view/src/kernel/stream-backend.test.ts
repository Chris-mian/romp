// StreamBackend behavior contract, exercised against the mock-claude imposter
// (mock-claude.ts — protocol shapes pinned from live probes). Isolated
// XDG_STATE_HOME; every scenario is synthetic.
//
// The headline properties under test, vs HeadlessBackend's process-per-turn:
//   - ONE process serves many turns (sequential and queued)
//   - interrupt leaves the process alive
//   - a crash settles state via the close EVENT and the next send resumes
//     (forking once), not every turn
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const TEST_STATE = fs.mkdtempSync(path.join(os.tmpdir(), "romp-stream-backend-"));
process.env.XDG_STATE_HOME = TEST_STATE;

import { test, after } from "node:test";
import * as assert from "node:assert/strict";
import { StreamBackend } from "./stream-backend";
import { writeMockClaude, mockCalls, MockScenario } from "./mock-claude";

// Safety net: a failing assertion must not skip the in-test kill() — a live
// child's pipes would pin this process open and hang the whole `node --test`
// run (exactly the suite hang of 2026-06-12). after() runs pass or fail.
const TRACKED: Array<[StreamBackend, string]> = [];
function track(b: StreamBackend, ...names: string[]): StreamBackend {
  for (const n of names) TRACKED.push([b, n]);
  return b;
}
after(() => { for (const [b, n] of TRACKED) { try { b.kill(n); } catch { /* gone */ } } });

const ROMP = path.join(TEST_STATE, "romp");
const reg = (name: string) => JSON.parse(fs.readFileSync(path.join(ROMP, "headless", name + ".json"), "utf8"));
const statesOf = (sid: string) =>
  fs.readFileSync(path.join(ROMP, "states", sid + ".jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l).state);

// Bounded poll for an expected condition (test-side wait; the backend itself
// is event-driven). 20ms ticks, 5s cap.
async function until(what: string, fn: () => boolean): Promise<void> {
  for (let i = 0; i < 250; i++) {
    if (fn()) return;
    await new Promise((r) => setTimeout(r, 20));
  }
  assert.fail("timed out waiting for: " + what);
}

function useMock(label: string, scenario: MockScenario): string {
  const dir = path.join(TEST_STATE, "mock-" + label);
  writeMockClaude(dir, scenario);
  process.env.ROMP_CLAUDE_BIN = path.join(dir, "claude");
  return dir;
}

test("spawn registers identity + waiting state (parity with headless)", async () => {
  useMock("spawn", { sessionId: "00000000-0000-4000-8000-0000000000a1", turns: [{}] });
  const b = new StreamBackend();
  assert.equal(await b.spawn("st-alpha", TEST_STATE), true);
  assert.equal(b.liveSessions().get("st-alpha")!.state, "waiting");
  const r = reg("st-alpha");
  assert.equal(fs.readFileSync(path.join(ROMP, "names", r.sid), "utf8").split("\t")[0], "st-alpha");
  assert.deepEqual(statesOf(r.sid), ["waiting"]);
  assert.equal(await b.spawn("st-alpha", TEST_STATE), false, "double-spawn refuses");
});

test("one process serves sequential AND queued turns; argv claims the anchor sid", async () => {
  const gate = path.join(TEST_STATE, "gate-multiturn");
  const dir = useMock("multi", {
    sessionId: "unused-the-backend-passes--session-id",
    turns: [
      { steps: [{ kind: "gate", file: gate }], resultText: "T1" },
      { resultText: "T2" },
      { resultText: "T3" },
    ],
  });
  const b = track(new StreamBackend(), "st-multi");
  await b.spawn("st-multi", TEST_STATE);
  const anchor = reg("st-multi").sid;

  assert.equal(b.send("st-multi", "synthetic turn 1"), true);
  await until("working", () => b.liveSessions().get("st-multi")!.state === "working");
  // mid-turn send QUEUES instead of refusing (tmux parity — the data-model fix
  // over HeadlessBackend, which returns false here)
  assert.equal(b.send("st-multi", "synthetic turn 2"), true, "mid-turn send queues");
  fs.writeFileSync(gate, "go");
  await until("both turns done", () => b.liveSessions().get("st-multi")!.state === "waiting");

  assert.equal(b.send("st-multi", "synthetic turn 3"), true);
  await until("turn 3 done", () => b.liveSessions().get("st-multi")!.state === "waiting" && reg("st-multi").lastSid === anchor);

  const calls = mockCalls(dir);
  assert.equal(calls.length, 1, "three turns, ONE claude invocation");
  assert.match(calls[0], new RegExp("--session-id " + anchor));
  assert.match(calls[0], /--name st-multi/);
  assert.match(calls[0], /--input-format stream-json/);
  // single working stretch across the queued turns, then waiting
  assert.deepEqual(statesOf(anchor), ["waiting", "working", "waiting", "working", "waiting"]);
  b.kill("st-multi");   // end the child or its open pipes keep the test process alive
});

test("interrupt aborts the turn via control protocol; the process survives", async () => {
  const gate = path.join(TEST_STATE, "gate-interrupt");
  const dir = useMock("intr", {
    sessionId: "unused",
    turns: [
      { steps: [{ kind: "text", text: "going" }, { kind: "gate", file: gate }], resultText: "NEVER" },
      { resultText: "AFTER-INTERRUPT" },
    ],
  });
  const b = track(new StreamBackend(), "st-intr");
  await b.spawn("st-intr", TEST_STATE);
  assert.equal(b.interrupt("st-intr"), false, "nothing to interrupt while idle");
  b.send("st-intr", "synthetic long task");
  await until("working", () => b.liveSessions().get("st-intr")!.state === "working");
  assert.equal(b.interrupt("st-intr"), true);
  await until("settled after interrupt", () => b.liveSessions().get("st-intr")!.state === "waiting");
  // same process takes the next turn
  b.send("st-intr", "synthetic follow-up");
  await until("follow-up done", () => b.liveSessions().get("st-intr")!.state === "waiting");
  assert.equal(mockCalls(dir).length, 1, "interrupt did NOT cost a respawn");
  b.kill("st-intr");
});

test("crash mid-turn settles via the close event; next send resumes with a fork", async () => {
  const dir = useMock("crash", {
    sessionId: "unused",
    turns: [
      { steps: [{ kind: "text", text: "about to die" }, { kind: "crash" }] },
      { resultText: "BACK" },
    ],
  });
  const b = track(new StreamBackend(), "st-crash");
  await b.spawn("st-crash", TEST_STATE);
  const anchor = reg("st-crash").sid;
  b.send("st-crash", "synthetic doomed turn");
  await until("crash settled to waiting", () => b.liveSessions().get("st-crash")!.state === "waiting");

  // next send respawns, resuming the last known transcript
  b.send("st-crash", "synthetic recovery turn");
  await until("recovery done", () => b.liveSessions().get("st-crash")!.state === "waiting" && mockCalls(dir).length === 2);
  const calls = mockCalls(dir);
  assert.match(calls[1], new RegExp("--resume " + anchor), "recovery resumes the anchor transcript");
  assert.equal(reg("st-crash").lastSid, "fork-" + anchor, "forked uuid tracked as next resume target");
  assert.equal(reg("st-crash").sid, anchor, "anchor identity unchanged");
  b.kill("st-crash");
});

test("kill ends the session; resume revives it under the same identity", async () => {
  useMock("kill", { sessionId: "unused", turns: [{ resultText: "X" }] });
  const b = track(new StreamBackend(), "st-kill");
  await b.spawn("st-kill", TEST_STATE);
  const anchor = reg("st-kill").sid;
  b.send("st-kill", "synthetic turn");
  await until("turn done", () => b.liveSessions().get("st-kill")!.state === "waiting");
  assert.equal(b.kill("st-kill"), true);
  assert.ok(!b.liveSessions().has("st-kill"));
  assert.ok(fs.existsSync(path.join(ROMP, "names", anchor)), "identity survives kill");
  assert.equal(b.send("st-kill", "x"), false, "dead session refuses sends");
  assert.equal(b.resume("st-kill", anchor, TEST_STATE), true);
  assert.ok(b.liveSessions().has("st-kill"));
});

test("rename moves registry, identity, and the live process", async () => {
  const gate = path.join(TEST_STATE, "gate-rename");
  const dir = useMock("rename", {
    sessionId: "unused",
    turns: [{ steps: [{ kind: "gate", file: gate }], resultText: "R1" }, { resultText: "R2" }],
  });
  const b = track(new StreamBackend(), "st-old", "st-new");
  await b.spawn("st-old", TEST_STATE);
  b.send("st-old", "synthetic turn");
  await until("working", () => b.liveSessions().get("st-old")!.state === "working");
  assert.equal(b.rename("st-old", "st-new"), true);
  assert.ok(!b.liveSessions().has("st-old"));
  assert.equal(b.liveSessions().get("st-new")!.state, "working");
  fs.writeFileSync(gate, "go");
  await until("turn done under new name", () => b.liveSessions().get("st-new")!.state === "waiting");
  // the live process moved with the rename: next send reuses it
  b.send("st-new", "synthetic turn 2");
  await until("turn 2 done", () => b.liveSessions().get("st-new")!.state === "waiting");
  assert.equal(mockCalls(dir).length, 1, "rename kept the process");
  b.kill("st-new");
});
