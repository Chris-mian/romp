// ensureThenAttach (kernel-attach.ts): a front end attaches to a manager-owned kernel; if none is on
// its port it asks the manager to ensure one, waits, then attaches. It must NEVER conclude success
// without /healthz passing, and must distinguish "no manager running" from "manager acked but the
// kernel never came up" so the UI can show the right fix. Tests inject deps so they run instantly.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { ensureThenAttach, parseHealthz, warnAfter, AttachDeps } from "./kernel-attach";

const noDelay = () => Promise.resolve();

// A scripted healthz that returns the i-th value per call, sticking on the last.
function healthSeq(seq: boolean[]) {
  let i = 0;
  return () => Promise.resolve(seq[Math.min(i++, seq.length - 1)]);
}

test("attaches immediately when a kernel already serves the port (never asks the manager)", async () => {
  let asked = 0;
  const res = await ensureThenAttach({
    healthz: () => Promise.resolve(true),
    ensureViaManager: () => { asked++; return Promise.resolve(true); },
    delay: noDelay,
  });
  assert.deepEqual(res, { ok: true });
  assert.equal(asked, 0, "should not contact the manager when a kernel is already up");
});

test("no kernel + no manager → reason no-manager (does not poll)", async () => {
  let polls = 0;
  const deps: AttachDeps = {
    healthz: () => { polls++; return Promise.resolve(false); },
    ensureViaManager: () => Promise.resolve(false),
    delay: noDelay,
    pollTries: 10,
  };
  const res = await ensureThenAttach(deps);
  assert.deepEqual(res, { ok: false, reason: "no-manager" });
  assert.equal(polls, 1, "only the initial probe; no post-ensure polling when the manager is absent");
});

test("manager ensures and the kernel comes up on a later poll → ok", async () => {
  // down on the initial probe + first poll, then up
  const res = await ensureThenAttach({
    healthz: healthSeq([false, false, true]),
    ensureViaManager: () => Promise.resolve(true),
    delay: noDelay,
    pollTries: 5,
  });
  assert.deepEqual(res, { ok: true });
});

test("manager acked but the kernel never serves → reason kernel-didnt-start (bounded by pollTries)", async () => {
  let polls = 0;
  const res = await ensureThenAttach({
    healthz: () => { polls++; return Promise.resolve(false); },
    ensureViaManager: () => Promise.resolve(true),
    delay: noDelay,
    pollTries: 4,
  });
  assert.deepEqual(res, { ok: false, reason: "kernel-didnt-start" });
  assert.equal(polls, 5, "1 initial probe + 4 post-ensure polls, then give up");
});

test("default poll budget covers a kernel RESTART, not just a clean spawn (>= 10s)", async () => {
  // A `romp refresh` respawn + cold boot can exceed the old ~5s budget; attaching mid-restart
  // then toasted "couldn't bring up a kernel" while it came up seconds later (2026-07-13).
  let waited = 0;
  const res = await ensureThenAttach({
    healthz: () => Promise.resolve(false),
    ensureViaManager: () => Promise.resolve(true),
    delay: (ms) => { waited += ms; return Promise.resolve(); },
  });
  assert.deepEqual(res, { ok: false, reason: "kernel-didnt-start" });
  assert.ok(waited >= 10000, `default budget must be >= 10s of polling, got ${waited}ms`);
});

test("warnAfter: one failed round is a transient (quiet); a persistent failure warns", () => {
  assert.equal(warnAfter(0), false);
  assert.equal(warnAfter(1), false, "a single failure (e.g. attaching mid-restart) must not interrupt");
  assert.equal(warnAfter(2), true);
  assert.equal(warnAfter(5), true);
});

test("parseHealthz accepts BOTH kernel generations: plain 'ok' and {ok:true} JSON", () => {
  // The Python kernel's plain-text form read as unhealthy under the old JSON-only
  // parse — VS Code could never attach to a healthy kernel (2026-07-13).
  assert.deepEqual(parseHealthz(200, "ok"), { ok: true });
  assert.deepEqual(parseHealthz(200, " ok\n"), { ok: true });
  assert.deepEqual(parseHealthz(200, '{"ok": true, "version": "1.2"}'), { ok: true, version: "1.2" });
  assert.equal(parseHealthz(200, '{"ok": false}').ok, false);
});

test("parseHealthz rejects non-200s and junk bodies", () => {
  assert.equal(parseHealthz(403, "ok").ok, false, "a forbidden 'ok' body is not health");
  assert.equal(parseHealthz(undefined, "ok").ok, false);
  assert.equal(parseHealthz(200, "<html>proxy error</html>").ok, false);
  assert.equal(parseHealthz(200, "").ok, false);
});
