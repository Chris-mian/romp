// ensureThenAttach (kernel-attach.ts): a front end attaches to a manager-owned kernel; if none is on
// its port it asks the manager to ensure one, waits, then attaches. It must NEVER conclude success
// without /healthz passing, and must distinguish "no manager running" from "manager acked but the
// kernel never came up" so the UI can show the right fix. Tests inject deps so they run instantly.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { ensureThenAttach, AttachDeps } from "./kernel-attach";

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
