// The live edge must never run BACKWARD (the user 2026-07-03: the timeline "jumps forward as if it's
// more recent and then it jumps back"). Two mechanisms guarantee it:
//   1. isFreshNowSample clamps a RE-EMITTED payload (federation re-serves the stored local `now` on a
//      remote push; _cached_timeline re-serves its build-time `now`) so the bars/positions never regress.
//   2. reanchorEdge keeps the DISPLAYED edge monotonic: it catches up forward when the free-run falls
//      behind a sample, but HOLDS (never snaps back) when a sample lands behind the free-run edge — which
//      is what bursty/jittery/latency-varying delivery produces. The old shouldReanchorEdge rebased to the
//      sample on any >0.5s ABSOLUTE drift, snapping the axis both directions.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC_PATH = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const SRC = fs.readFileSync(SRC_PATH, "utf8");
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { isFreshNowSample, reanchorEdge, interpNow } = require(SRC_PATH) as {
  isFreshNowSample: (newestSeen: number | null, incoming: number | undefined) => boolean;
  reanchorEdge: (baseSec: number | null, baseMs: number | null, nowMs: number, dataNow: number,
                 wasLive: boolean) => { baseSec: number; baseMs: number };
  interpNow: (baseSec: number, baseMs: number, nowMs: number, live: boolean, maxAheadSec: number) => number;
};

test("isFreshNowSample: only a strictly newer now is a fresh clock sample", () => {
  assert.equal(isFreshNowSample(null, 1000), true, "first sample is fresh");
  assert.equal(isFreshNowSample(1000, 1002), true, "a newer now is fresh");
  assert.equal(isFreshNowSample(1000, 1000), false, "an equal now is a re-emission");
  assert.equal(isFreshNowSample(1000, 997), false, "an older now is a re-emission (federation/cache)");
  assert.equal(isFreshNowSample(1000, undefined), false, "a missing now is never fresh");
});

// Replay a sample stream through reanchorEdge + interpNow exactly as update()+_tickLive do, tracking the
// DISPLAYED edge. Crucially it records the value the eye sees JUST BEFORE each poll (the free-run peak off
// the OLD base at the poll's clock) AND just after the re-anchor — because the visible backward snap is the
// free-run climbing, then a poll yanking it back. The guarantee: the whole sequence is non-decreasing.
function replay(samples: Array<[number, number]>) {
  let baseSec: number | null = null, baseMs: number | null = null, wasLive = false;
  const displayed: number[] = [];
  for (const [dataNow, nowMs] of samples) {
    if (baseSec != null && baseMs != null && wasLive) {
      displayed.push(interpNow(baseSec, baseMs, nowMs, true, 30));   // the free-run edge the instant before the poll
    }
    const a = reanchorEdge(baseSec, baseMs, nowMs, dataNow, wasLive);
    baseSec = a.baseSec; baseMs = a.baseMs; wasLive = true;
    displayed.push(interpNow(baseSec, baseMs, nowMs, true, 30));     // and the instant after the re-anchor
  }
  return displayed;
}

test("reanchorEdge: a sample landing BEHIND the free-run edge holds it — never snaps backward", () => {
  // anchor at 1000@0, glide 2s → edge is at 1002; then a jittery sample arrives 0.6s BEHIND it.
  let a = reanchorEdge(null, null, 0, 1000, false);          // first anchor
  assert.deepEqual(a, { baseSec: 1000, baseMs: 0 });
  const displayed = interpNow(a.baseSec, a.baseMs, 2000, true, 30);
  assert.equal(displayed, 1002, "the edge glided to 1002");
  const b = reanchorEdge(a.baseSec, a.baseMs, 2000, 1001.4, true);   // sample 0.6s behind the free-run
  const after = interpNow(b.baseSec, b.baseMs, 2000, true, 30);
  assert.ok(after >= 1002, `held at ${after}, must not drop below 1002 (the backward jump)`);
});

test("reanchorEdge: catches up FORWARD only when genuinely behind (a backgrounded tab / real lag)", () => {
  // anchor 1000@0; only 1s of local glide (edge≈1001) but the real clock jumped to 1010 (tab was asleep).
  const a = reanchorEdge(1000, 0, 1000, 1010, true);
  assert.equal(a.baseSec, 1010, "a sample well ahead of the free-run pulls the edge forward to catch up");
});

test("the forward-then-back oscillation cannot happen: the whole stream is monotonic", () => {
  // a deliberately nasty stream: steady glide, then a BURST (two samples ~together), a sample that lands
  // behind the overshot free-run (the old backward snap), a re-emitted stale now, and a real forward gap.
  const stream: Array<[number, number]> = [
    [1000, 0], [1002, 2000], [1004, 4000],       // steady 1x
    [1004.9, 4100], [1005, 4150],                // BURST: two samples land ~together, ahead of the glide
    [1005.2, 6000],                              // a sample that lands BEHIND the 6s free-run edge (~1007)
    [1005.2, 7000],                              // a STALE re-emission (same now) a second later
    [1020, 8000],                                // a real forward gap (backgrounded ~13s)
  ];
  const displayed = replay(stream);
  for (let i = 1; i < displayed.length; i++) {
    assert.ok(displayed[i] >= displayed[i - 1] - 1e-9,
      `edge went BACKWARD at step ${i}: ${displayed[i - 1]} -> ${displayed[i]}`);
  }
  assert.ok(displayed[displayed.length - 1] >= 1020, "the real forward gap is still honored (catch-up)");
});

// Source pins (house style for the SVG renderer — no jsdom): the monotonic re-anchor is actually wired in.
test("update() clamps a regressed data.now and drives the edge through the monotonic reanchorEdge", () => {
  assert.match(SRC, /if \(isFreshNowSample\(this\._newestNow, data\.now\)\) this\._newestNow = data\.now;/);
  assert.match(SRC, /else if \(this\._newestNow != null\) data\.now = this\._newestNow;/);
  assert.match(SRC, /const _a = reanchorEdge\(this\._nowBaseSec, this\._nowBaseMs, _tMs, data\.now, this\._wasLive\);/);
  assert.doesNotMatch(SRC, /&& shouldReanchorEdge\(this\._nowBaseSec/,
                      "the old absolute-drift re-anchor is gone from update()");
});

test("applyBars never regresses data.now on a cached/merged bars payload", () => {
  assert.match(SRC, /if \(isFreshNowSample\(this\._newestNow, m\.now\)\) this\._newestNow = m\.now;/);
  assert.match(SRC, /this\.data\.now = \(this\._newestNow != null\) \? this\._newestNow : m\.now;/);
});

test("reanchorEdge + isFreshNowSample are exported for unit tests", () => {
  assert.match(SRC, /module\.exports = \{[^}]*reanchorEdge[^}]*\};/);
  assert.match(SRC, /module\.exports = \{[^}]*isFreshNowSample[^}]*\};/);
});
