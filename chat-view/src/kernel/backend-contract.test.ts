// SessionBackend contract tests.
//
// Shape contract: every backend implements the full interface (checked for
// both). Behavior contract: exercised against HeadlessBackend with a mocked
// `claude` binary and an isolated XDG_STATE_HOME — spawn/send/interrupt/
// rename/kill, the states/<sid>.jsonl record, and lastSid tracking from the
// turn's result JSON. (TmuxBackend's mechanics are pinned by the bats suites —
// tests/romp.bats and tests/tmux-status-hook.bats — which mock tmux itself.)
//
// NOTE: state-dir modules resolve XDG_STATE_HOME at import time, so it is set
// BEFORE the imports via a top-level side effect.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const TEST_STATE = fs.mkdtempSync(path.join(os.tmpdir(), "romp-backend-test-"));
process.env.XDG_STATE_HOME = TEST_STATE;

// Mock `claude`: records its argv, emits a result JSON with a fresh session_id.
const MOCK_BIN = path.join(TEST_STATE, "bin");
fs.mkdirSync(MOCK_BIN, { recursive: true });
const CLAUDE_LOG = path.join(TEST_STATE, "claude-calls.log");
fs.writeFileSync(path.join(MOCK_BIN, "claude"), `#!/usr/bin/env bash
echo "claude $*" >> ${JSON.stringify(CLAUDE_LOG)}
sleep 0.2
echo '{"type":"result","session_id":"forked-fsid-123","result":"ok"}'
`);
fs.chmodSync(path.join(MOCK_BIN, "claude"), 0o755);
process.env.ROMP_CLAUDE_BIN = path.join(MOCK_BIN, "claude");

import { test } from "node:test";
import * as assert from "node:assert/strict";
import type { SessionBackend } from "./backend";
import { TmuxBackend } from "./tmux-backend";
import { HeadlessBackend } from "./headless-backend";

const ROMP = path.join(TEST_STATE, "romp");

function shapeCheck(b: SessionBackend, name: string) {
  test(`${name}: implements the full SessionBackend interface`, () => {
    for (const m of ["liveSessions", "send", "interrupt", "spawn", "resume", "rename", "kill", "markIdle"] as const) {
      assert.equal(typeof (b as any)[m], "function", `${name}.${m} missing`);
    }
    assert.ok("tui" in b, `${name}.tui missing`);
  });
}

shapeCheck(new TmuxBackend(), "TmuxBackend");
shapeCheck(new HeadlessBackend(), "HeadlessBackend");

test("TmuxBackend exposes TUI ops; HeadlessBackend has none", () => {
  const t = new TmuxBackend();
  assert.ok(t.tui && typeof t.tui.capturePane === "function");
  assert.equal(new HeadlessBackend().tui, null);
});

test("headless: spawn registers the session, identity record, waiting state", async () => {
  const b = new HeadlessBackend();
  assert.equal(await b.spawn("hl-alpha", TEST_STATE), true);
  const live = b.liveSessions();
  assert.ok(live.has("hl-alpha"));
  assert.equal(live.get("hl-alpha")!.state, "waiting");
  // identity record: names/<sid> = name\tdir…
  const reg = JSON.parse(fs.readFileSync(path.join(ROMP, "headless", "hl-alpha.json"), "utf8"));
  const namesRec = fs.readFileSync(path.join(ROMP, "names", reg.sid), "utf8");
  assert.equal(namesRec.split("\t")[0], "hl-alpha");
  // durable state record
  const states = fs.readFileSync(path.join(ROMP, "states", reg.sid + ".jsonl"), "utf8").trim();
  assert.match(states, /"state":"waiting"/);
  // double-spawn under the same name refuses
  assert.equal(await b.spawn("hl-alpha", TEST_STATE), false);
});

test("headless: send runs a turn, tracks working→waiting, updates resume target", async () => {
  const b = new HeadlessBackend();
  await b.spawn("hl-send", TEST_STATE);
  assert.equal(b.send("hl-send", "do the thing"), true);
  // mid-turn: working, and a second send is refused (one turn at a time)
  assert.equal(b.liveSessions().get("hl-send")!.state, "working");
  assert.equal(b.send("hl-send", "another"), false);
  await new Promise((r) => setTimeout(r, 700));   // mock turn takes ~200ms
  assert.equal(b.liveSessions().get("hl-send")!.state, "waiting");
  // lastSid picked up from the result JSON → next turn resumes the fork
  const reg = JSON.parse(fs.readFileSync(path.join(ROMP, "headless", "hl-send.json"), "utf8"));
  assert.equal(reg.lastSid, "forked-fsid-123");
  assert.equal(b.send("hl-send", "follow-up"), true);
  await new Promise((r) => setTimeout(r, 700));
  const calls = fs.readFileSync(CLAUDE_LOG, "utf8").trim().split("\n").filter((l) => l.includes("hl-send"));
  // first turn claims the anchor sid; the follow-up resumes the fork
  assert.match(calls[0], new RegExp(`--session-id ${reg.sid}`));
  const last = calls[calls.length - 1];
  assert.match(last, /--resume forked-fsid-123/);
  assert.match(last, /--name hl-send/);
  // durable record went working→waiting→working→waiting
  const states = fs.readFileSync(path.join(ROMP, "states", reg.sid + ".jsonl"), "utf8").trim().split("\n");
  assert.deepEqual(states.map((l) => JSON.parse(l).state), ["waiting", "working", "waiting", "working", "waiting"]);
});

test("headless: interrupt kills the in-flight turn", async () => {
  const b = new HeadlessBackend();
  await b.spawn("hl-int", TEST_STATE);
  assert.equal(b.interrupt("hl-int"), false, "nothing to interrupt while idle");
  b.send("hl-int", "long task");
  assert.equal(b.interrupt("hl-int"), true);
  await new Promise((r) => setTimeout(r, 300));
  assert.equal(b.liveSessions().get("hl-int")!.state, "waiting");
});

test("headless: rename MID-TURN — completion lands under the new name", async () => {
  // Regression: the turn-end handlers used to capture the old name and reg
  // object, so a rename during a turn leaked the running-map entry (stuck
  // "working") and wrote lastSid back under the resurrected old-name file.
  const b = new HeadlessBackend();
  await b.spawn("hl-mid-old", TEST_STATE);
  const sid = JSON.parse(fs.readFileSync(path.join(ROMP, "headless", "hl-mid-old.json"), "utf8")).sid;
  assert.equal(b.send("hl-mid-old", "synthetic turn"), true);
  assert.equal(b.rename("hl-mid-old", "hl-mid-new"), true);   // turn still in flight
  await new Promise((r) => setTimeout(r, 700));               // mock turn takes ~200ms
  assert.equal(b.liveSessions().get("hl-mid-new")!.state, "waiting", "not stuck working");
  assert.equal(b.send("hl-mid-new", "synthetic follow-up"), true, "no leaked running entry");
  await new Promise((r) => setTimeout(r, 700));
  const r2 = JSON.parse(fs.readFileSync(path.join(ROMP, "headless", "hl-mid-new.json"), "utf8"));
  assert.equal(r2.sid, sid);
  assert.equal(r2.lastSid, "forked-fsid-123", "lastSid landed under the NEW name");
  assert.ok(!fs.existsSync(path.join(ROMP, "headless", "hl-mid-old.json")), "old-name registry not resurrected");
});

test("headless: rename moves the registry + identity; kill marks dead", async () => {
  const b = new HeadlessBackend();
  await b.spawn("hl-old", TEST_STATE);
  assert.equal(b.rename("hl-old", "hl-new"), true);
  const live = b.liveSessions();
  assert.ok(!live.has("hl-old"));
  assert.ok(live.has("hl-new"));
  const reg = JSON.parse(fs.readFileSync(path.join(ROMP, "headless", "hl-new.json"), "utf8"));
  assert.equal(fs.readFileSync(path.join(ROMP, "names", reg.sid), "utf8").split("\t")[0], "hl-new");
  // rename onto an existing name refuses
  await b.spawn("hl-other", TEST_STATE);
  assert.equal(b.rename("hl-new", "hl-other"), false);
  // kill: gone from liveSessions, transcript/identity stay on disk
  assert.equal(b.kill("hl-new"), true);
  assert.ok(!b.liveSessions().has("hl-new"));
  assert.ok(fs.existsSync(path.join(ROMP, "names", reg.sid)));
  // resume brings it back under the same name
  assert.equal(b.resume("hl-new", reg.sid, TEST_STATE), true);
  assert.ok(b.liveSessions().has("hl-new"));
});
