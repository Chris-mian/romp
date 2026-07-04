// The live edge must never run BACKWARD on a re-emitted payload (the user 2026-07-03: with a remote
// host attached, the timeline "jumps forward and then keeps going backwards" in real time). Federation
// re-emits the STORED local payload whenever a remote host pushes — its `now` is up to a push interval
// old — and _cached_timeline re-serves the `now` baked at build time. A single kernel's clock never
// runs backward within a page lifetime, so a non-increasing data.now is a RE-EMISSION, not a clock
// sample: isFreshNowSample gates the edge re-anchor and the applyBars adoption on it.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC_PATH = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const SRC = fs.readFileSync(SRC_PATH, "utf8");
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { isFreshNowSample, shouldReanchorEdge, interpNow } = require(SRC_PATH);

test("isFreshNowSample: only a strictly newer now is a fresh clock sample", () => {
  assert.equal(isFreshNowSample(null, 1000), true, "first sample is fresh");
  assert.equal(isFreshNowSample(1000, 1002), true, "a newer now is fresh");
  assert.equal(isFreshNowSample(1000, 1000), false, "an equal now is a re-emission");
  assert.equal(isFreshNowSample(1000, 997), false, "an older now is a re-emission (federation/cache)");
  assert.equal(isFreshNowSample(1000, undefined), false, "a missing now is never fresh");
});

test("the oscillation scenario: a stale re-emission would re-anchor backward — the fresh gate stops it", () => {
  // Local push at t=1000 anchors the edge; it glides 2s; a remote push re-emits the stored local
  // payload still carrying now=1000. Without the gate, shouldReanchorEdge sees 2s of "drift" and snaps
  // the edge back to 1000 — then the next local push (1003) snaps it forward again: the seesaw.
  const baseSec = 1000, baseMs = 0, nowMs = 2000;              // 2s of glide since the anchor
  const displayed = interpNow(baseSec, baseMs, nowMs, true, 30);
  assert.equal(displayed, 1002, "the edge has glided to 1002");
  const staleReemission = 1000;                                 // the re-emitted payload's old now
  assert.equal(shouldReanchorEdge(baseSec, baseMs, nowMs, staleReemission, true, true), true,
               "un-gated, the stale now LOOKS like drift and would snap the edge backward");
  assert.equal(isFreshNowSample(1000, staleReemission), false,
               "the fresh-sample gate names it a re-emission — no re-anchor, the edge keeps gliding");
  assert.equal(isFreshNowSample(1000, 1003), true, "the next genuine local push still re-anchors");
});

// Source pins (house style for the SVG renderer — no jsdom): the gate is actually wired in.
test("update() clamps a regressed data.now and gates the backward re-anchor on freshness", () => {
  assert.match(SRC, /const _freshNow = isFreshNowSample\(this\._newestNow, data\.now\);/);
  assert.match(SRC, /if \(_freshNow\) this\._newestNow = data\.now;\s*\n\s*else if \(this\._newestNow != null\) data\.now = this\._newestNow;/);
  assert.match(SRC, /\(_freshNow \|\| this\._nowBaseSec == null \|\| !\(_live && this\._wasLive\)\)\s*\n\s*&& shouldReanchorEdge\(/,
               "continuously-live re-anchor requires a fresh sample; first anchor and held/re-entry still adopt");
});

test("applyBars never regresses data.now on a cached/merged bars payload", () => {
  assert.match(SRC, /if \(isFreshNowSample\(this\._newestNow, m\.now\)\) this\._newestNow = m\.now;/);
  assert.match(SRC, /this\.data\.now = \(this\._newestNow != null\) \? this\._newestNow : m\.now;/);
  assert.doesNotMatch(SRC, /if \(typeof m\.now === 'number'\) this\.data\.now = m\.now;/,
                      "the old verbatim adoption is gone");
});

test("isFreshNowSample is exported for unit tests", () => {
  assert.match(SRC, /module\.exports = \{[^}]*isFreshNowSample[^}]*\};/);
});
