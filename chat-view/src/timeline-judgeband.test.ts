// The judging band draws one row per summarizer judge; each bar is a RUN SPAN [sent, recv] filled with the
// SESSION's colour. When several sessions are judged by the SAME judge at OVERLAPPING times, the bars used
// to draw on top of each other (only the top one hoverable). Now they pack into SUB-LANES within the row and
// shrink vertically so each is visible and independently hoverable (the user 2026-06-23). Source-level pins
// (no jsdom for the SVG timeline renderer) — they fail the moment the band reverts to one shared Y per row.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("overlapping same-judge blocks are greedily partitioned into sub-lanes by pixel extent", () => {
  // each block takes the first sub-lane whose previous bar already ended (start px >= that lane's last end px)
  assert.match(SRC, /const laneEnds = \[\];/);
  assert.match(SRC, /laneEnds\.findIndex\(\(endX\) => bx1 >= endX\)/);
  assert.match(SRC, /b\._lane = lane;/);
});

test("the busiest instant sets the row's stack depth; depth 1 (no overlap) keeps the full bar height", () => {
  assert.match(SRC, /const depth = Math\.max\(1, laneEnds\.length\);/);
  assert.match(SRC, /const slotTop = y - JROW \/ 2, laneH = JROW \/ depth;/);
  // bars shrink to fit the sub-lane but never below 2px, and stay 9px (JBAR_H) when depth === 1
  assert.match(SRC, /const barH = Math\.max\(2, Math\.min\(JBAR_H, laneH - 1\)\);/);
});

test("each stacked bar draws at its own sub-lane centre, not a single shared row Y", () => {
  assert.match(SRC, /const by = slotTop \+ laneH \* \(b\._lane \+ 0\.5\);/);
  assert.match(SRC, /y: by - barH \/ 2, width: x2 - x1, height: barH/);
});

test("each bar's hit target is its own sub-lane (height laneH) so every stacked bar is independently hoverable", () => {
  assert.match(SRC, /el\('rect', \{ x: x1 - 2, y: by - laneH \/ 2, width: \(x2 - x1\) \+ 4, height: laneH/);
});
