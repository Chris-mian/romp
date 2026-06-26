// The timeline ships a LANES skeleton first, then the heavy BARS ({type:"bars"} → applyBars). Until the
// bars land the plot area (right of the lane labels) is empty, so draw() paints the romp swirl loader there
// (the user 2026-06-26). The old full-pane _pane_spin("host") was dropped from the kernel because it hid the
// instant #host got its first child (the wrap, before any bars) — the view now owns the bars-area loader,
// gated on _barsLoaded. Source-level pins (no jsdom for the SVG renderer): they fail if the gate regresses.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the bars-loaded gate starts false and flips true the moment applyBars runs", () => {
  assert.match(SRC, /this\._barsLoaded = false;/);
  // applyBars sets it true (even for an empty bars payload) so the loader can never stick
  assert.match(SRC, /this\._barsLoaded = true;\s+\/\/ the bars payload has landed/);
});

test("a full one-shot data object through update() also marks the bars loaded (test harness / older clients)", () => {
  assert.match(SRC, /if \(data\.turns && Object\.keys\(data\.turns\)\.length\) this\._barsLoaded = true;/);
});

test("draw() paints the swirl loader in the plot centre while !_barsLoaded", () => {
  assert.match(SRC, /if \(!this\._barsLoaded\) this\._drawBarsLoader\(svg, M\.left \+ plotW \/ 2, \(M\.top \+ axisY\) \/ 2\);/);
});

test("_drawBarsLoader is the reverse-spinning romp swirl-as-o (matches the shared loader)", () => {
  assert.match(SRC, /_drawBarsLoader\(svg, cx, cy\)/);
  assert.match(SRC, /'\/media\/romp-swirl-o\.svg'/);
  // reverse spin (-360), 7s — same as _LOADER_CSS .rl-o
  assert.match(SRC, /to: '-360 ' \+ cx \+ ' ' \+ cy, dur: '7s', repeatCount: 'indefinite'/);
});
