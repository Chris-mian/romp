// Parent-death watchdog (parent-watch.ts): the kernel exits when the manager that owns it vanishes, so
// a SIGKILL'd / crashed manager can't leave an orphan kernel (the user's 2026-06-13 report). These tests
// drive a real throwaway child as the "manager": kill it and assert the liveness probe flips + the
// watcher fires exactly once. pid 0 (a manual romp-serve, no manager) must install no watchdog.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { isAlive, watchParent } from "./parent-watch";

// A live node child that just sleeps; resolves to its pid once spawned.
async function sleeper(): Promise<{ pid: number; kill: () => Promise<void> }> {
  const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60000)"]);
  await new Promise((r) => child.on("spawn", r));
  return {
    pid: child.pid as number,
    kill: () => new Promise<void>((r) => { child.on("exit", () => r()); child.kill("SIGKILL"); }),
  };
}

test("isAlive: current process is alive; pid 0 and negatives are not", () => {
  assert.equal(isAlive(process.pid), true);
  assert.equal(isAlive(0), false);
  assert.equal(isAlive(-1), false);
});

test("isAlive: a killed-and-reaped pid reads as dead", async () => {
  const c = await sleeper();
  assert.equal(isAlive(c.pid), true);
  await c.kill();
  await new Promise((r) => setTimeout(r, 120));   // let the OS reap → kill(pid,0) throws ESRCH
  assert.equal(isAlive(c.pid), false);
});

test("watchParent: no manager (pid 0) installs no watchdog", () => {
  assert.equal(watchParent(0, () => { throw new Error("must not fire"); }), null);
});

test("watchParent: fires onGone exactly once after the watched pid dies, then stops polling", async () => {
  const c = await sleeper();
  let calls = 0;
  await new Promise<void>((resolve) => {
    watchParent(c.pid, () => { calls++; resolve(); }, 25);
    void c.kill();
  });
  await new Promise((r) => setTimeout(r, 100));   // would catch a stray re-fire (it cleared its own interval)
  assert.equal(calls, 1);
});
