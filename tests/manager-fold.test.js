// A restart in flight is an event, not a window (2026-09-15): the kernel's own converge and a peer's push asked
// restart-all three seconds apart, and the second SIGTERM killed a kernel two seconds old. inflightGate is the pure
// decision on the record's phase: from the SIGTERM until the successor is spawned a second request is FOLDED into the
// restart in flight (the successor loads the disk as it stands); from the spawn until the successor answers its port
// one TRAILING restart is kept and sent when it does; otherwise the request restarts. The wiring is executed with a
// stand-in child and a stand-in kernel port. Run: node --test tests/manager-fold.test.js
'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

const ROOTS = [];
const tmpRoot = (prefix) => { const d = fs.mkdtempSync(path.join(os.tmpdir(), prefix)); ROOTS.push(d); return d; };
process.on('exit', () => { for (const d of ROOTS) fs.rmSync(d, { recursive: true, force: true }); });
const STATE = tmpRoot('romp-mgr-fold-');
process.env.ROMP_STATE_DIR = STATE;
process.env.ROMP_READY_PROBE_MS = '20';
const MGR = path.join(__dirname, '..', 'bin', 'romp-manager');
const mgr = require(MGR);
const { restartKernel, kernels } = mgr;
const inflightGate = mgr.inflightGate;   // absent at the base: the assertions below then fail on their own terms

const AUDIT = path.join(STATE, 'restart-audit.jsonl');
const rows = () => (fs.existsSync(AUDIT) ? fs.readFileSync(AUDIT, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []);
const resetAudit = () => { try { fs.unlinkSync(AUDIT); } catch (e) { /* none yet */ } };

// A stand-in child: records the signals it is sent, never exits on its own.
function standIn(pid) {
  return { pid, signals: [], exitCode: null, signalCode: null, kill(sig) { this.signals.push(sig); } };
}
function seed(id, child, over) {
  kernels.clear();
  kernels.set(id, Object.assign({ spec: { id, port: 1, stateDir: STATE }, child, restarts: 0, quickCrashes: 0,
                                  startedAt: Date.now(), stopping: false, requested: null, inflight: null, trail: null }, over || {}));
  return kernels.get(id);
}

test('the pure gate: no flight restarts, a signaled flight folds, a spawned successor trails', () => {
  assert.ok(inflightGate, 'inflightGate is exported');
  assert.equal(inflightGate(null), 'restart');
  assert.equal(inflightGate(undefined), 'restart');
  assert.equal(inflightGate('signaled'), 'fold');
  assert.equal(inflightGate('spawned'), 'trail');
});

test('two restart requests during one restart kill once: the second is folded and noted', () => {
  resetAudit();
  const child = standIn(4242);
  const rec = seed('main', child);
  const first = restartKernel('main', 'restart-all');
  assert.ok(first, 'the first request restarts');
  assert.deepEqual(child.signals, ['SIGTERM'], 'one SIGTERM');
  assert.equal(rec.inflight, 'signaled', 'the record says a restart is in flight');
  const second = restartKernel('main', 'restart-all');
  assert.equal(second, 'folded', 'the second request rides the restart in flight');
  assert.deepEqual(child.signals, ['SIGTERM'], 'still one SIGTERM: the base sent two');
  const r = rows();
  assert.deepEqual(r.map((x) => x.action), ['manager-sigterm', 'restart-folded'], 'the ledger: one sigterm, one fold');
  assert.equal(r[1].into, 4242, 'the fold names the pid it rode');
  assert.equal(r[1].trigger, 'restart-all');
});

test('a request while the successor is up but not yet answering is kept as one trailing restart, never a second kill', () => {
  resetAudit();
  const child = standIn(5151);
  const rec = seed('main', child, { inflight: 'spawned' });
  assert.equal(restartKernel('main', 'p2p-update'), 'trailing');
  assert.deepEqual(child.signals, [], 'nothing signaled: the new kernel is still booting');
  assert.equal(rec.trail, 'p2p-update', 'one trailing restart kept');
  assert.equal(restartKernel('main', 'restart-all'), 'trailing');
  assert.equal(rec.trail, 'p2p-update', 'a second request folds into the one trailing restart');
  assert.deepEqual(rows().map((x) => x.action), ['restart-trailing', 'restart-folded']);
});

test('the successor answering its port ends the flight and sends the trailing restart once', async () => {
  resetAudit();
  const answers = [];
  const srv = http.createServer((req, res) => { answers.push(req.url); res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ busy: 0 })); });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const port = srv.address().port;
  try {
    const child = standIn(6161);
    const rec = seed('main', child, { inflight: 'spawned', trail: 'p2p-update' });
    rec.spec.port = port;
    mgr.awaitReady('main', child);
    await new Promise((r) => setTimeout(r, 300));
    assert.ok(answers.length >= 1, 'the port was probed');
    assert.deepEqual(child.signals, ['SIGTERM'], 'the trailing restart went out once the kernel answered');
    assert.equal(rec.trail, null, 'and the trail is consumed');
    assert.equal(rec.inflight, 'signaled', 'a new flight is in progress for the trailing restart');
    assert.deepEqual(rows().map((x) => x.action), ['manager-sigterm'], 'the trailing restart is an ordinary sigterm row');
  } finally {
    await new Promise((r) => srv.close(r));
  }
});

test('a successor that never answers keeps the flight open and sends nothing on its own', async () => {
  resetAudit();
  const child = standIn(7171);
  const rec = seed('main', child, { inflight: 'spawned' });
  rec.spec.port = 1;   // nothing listens: the probe fails and retries
  mgr.awaitReady('main', child);
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(rec.inflight, 'spawned', 'no answer, no end of flight');
  assert.deepEqual(child.signals, [], 'and no signal');
  child.exitCode = 1;   // the child leaves before answering: the probe stands down (its exit handler respawns)
  await new Promise((r) => setTimeout(r, 120));
  kernels.clear();
});
