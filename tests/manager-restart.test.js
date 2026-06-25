// romp-manager's restart-storm guard (the user 2026-06-24): the kernel was SIGTERM'd + respawned 300+ times
// because every /restart restarted 1:1. restartGate coalesces near-simultaneous requests into one trailing
// restart and, once the rate looks like a storm, holds to one restart per cooldown. Pure decision function,
// time injected — unit-tested here. Run: node --test tests/manager-restart.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { restartGate } = require(path.join(__dirname, '..', 'bin', 'romp-manager'));

const OPTS = { coalesceMs: 3000, stormWindowMs: 60000, stormMax: 8, stormCooldownMs: 30000 };
const burst = (n, start = 1000, gap = 100) => Array.from({ length: n }, (_, i) => start + i * gap);

test('first restart goes through immediately', () => {
  assert.equal(restartGate({ last: null, history: [] }, 1000, OPTS).action, 'restart');
});

test('a rapid second request coalesces into a single trailing restart', () => {
  const g = restartGate({ last: 1000, history: [1000] }, 1500, OPTS);   // 500ms later
  assert.equal(g.action, 'coalesce');
  assert.ok(g.scheduleIn > 0 && g.scheduleIn <= OPTS.coalesceMs);
});

test('a request after the coalesce window restarts', () => {
  assert.equal(restartGate({ last: 1000, history: [1000] }, 4001, OPTS).action, 'restart');
});

test('a storm (>= stormMax in window) widens the gap to the cooldown — caps a tight loop', () => {
  const history = burst(8);                                            // 8 restarts in 700ms
  const g = restartGate({ last: history[7], history }, history[7] + 4000, OPTS); // 4s > coalesce, < cooldown
  assert.equal(g.inStorm, true);
  assert.equal(g.action, 'coalesce');
});

test('after the cooldown elapses a restart goes through even mid-storm (latest code still loads)', () => {
  const history = burst(8);
  assert.equal(restartGate({ last: history[7], history }, history[7] + 31000, OPTS).action, 'restart');
});

test('old restarts age out of the window — no false storm', () => {
  const history = burst(8);
  const g = restartGate({ last: history[7], history }, history[7] + 70000, OPTS);
  assert.equal(g.inStorm, false);
  assert.equal(g.action, 'restart');
});
