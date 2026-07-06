// Per-thread auto-retry suppression on interrupt (the user 2026-07-06): the global "Stop all auto-retries"
// only stops romp's own 10s loop and is account-wide + flap-prone. Interrupting a stuck thread is the real
// per-thread off-switch — the interrupt aborts the CLI's in-flight retry, and status.retrySuppressed keeps
// romp from re-firing "retry" into it until a successful turn re-arms it. The chat renderer has no jsdom
// harness, so pin the wiring at source. (Kernel side: tests/test_session_retry_suppress.py.)
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const R = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("Status carries the per-session retrySuppressed flag", () => {
  assert.match(R, /retrySuppressed\?: boolean/);
});

test("the stop/interrupt button is now reachable on a retrying / blocked thread (so you can interrupt it)", () => {
  // it renders for working/compacting AND the stuck states — that's where it doubles as the per-thread off-switch
  assert.match(R, /state === "retrying" \|\| s\.status\.state === "blocked"\) sl\.appendChild\(stopButton\(s\.status\.state\)\)/);
  // the button adapts its label/title for the stuck states
  assert.match(R, /const stuck = state === "retrying" \|\| state === "blocked"/);
  assert.match(R, /Stop retrying — interrupt this thread/);
  // and it fires the SAME interrupt op (the kernel arms suppression off it)
  assert.match(R, /vscodeApi\.postMessage\(\{ type: "interrupt", id: activeId \}\)/);
});

test("the auto-retry tick SKIPS a thread the user interrupted (retrySuppressed), like a recovered one", () => {
  assert.match(R, /s\.status\.state === "blocked" && !s\.status\.retrySuppressed/);
});

test("a suppressed thread's card says WHY it isn't retrying (distinct from the global pause)", () => {
  // initial render on the card
  assert.match(R, /else if \(suppressed\) countdown\.textContent = "auto-retry stopped for this session — send a message to resume"/);
  // and the live countdown tick keeps that message instead of a fake "retrying in Ns"
  assert.match(R, /if \(active\?\.status\.retrySuppressed\) \{\s*\n\s*cd\.textContent = "auto-retry stopped for this session/);
});
