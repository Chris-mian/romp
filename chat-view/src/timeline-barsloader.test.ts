// The timeline ships a LANES skeleton first, then the heavy BARS ({type:"bars"} → applyBars). Until all the
// data is in, the timeline shows ONLY the romp wordmark loader (R + spinning swirl-o + m + p + dots) — NO
// lanes, NO gridlines (the user 2026-06-26: partial data + empty gridlines read as "broken"). draw() returns
// early with the loader while !_barsLoaded. Source-level pins (no jsdom for the SVG renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the bars-loaded gate starts false and flips true the moment applyBars runs", () => {
  assert.match(SRC, /this\._barsLoaded = false;/);
  assert.match(SRC, /this\._barsLoaded = true;\s+\/\/ the bars payload has landed/);
});

test("a full one-shot data object through update() also marks the bars loaded (test harness / older clients)", () => {
  assert.match(SRC, /if \(data\.turns && Object\.keys\(data\.turns\)\.length\) this\._barsLoaded = true;/);
});

test("draw() shows ONLY the loader and returns early until bars are ready (no lanes, no gridlines)", () => {
  // ready = the flag is set OR the data already carries turns (a full one-shot / a direct draw())
  assert.match(SRC, /const barsReady = this\._barsLoaded \|\| !!\(data\.turns && Object\.keys\(data\.turns\)\.length\);/);
  assert.match(SRC, /if \(!barsReady\) \{ this\._showLoader\(true\); return; \}/);
  assert.match(SRC, /this\._showLoader\(false\);/);
});

test("_showLoader toggles a wordmark overlay against the SVG", () => {
  assert.match(SRC, /_showLoader\(show\)/);
  assert.match(SRC, /this\.svg\.style\.display = show \? 'none' : '';/);
});

test("the loader is the full ROMP wordmark — R, m, p letters + the reverse-spinning swirl-o + dots", () => {
  assert.match(SRC, /_buildLoader\(\)/);
  assert.match(SRC, /mk\('R', '#1EA1EB'\)/);
  assert.match(SRC, /mk\('m', '#54B204'\)/);
  assert.match(SRC, /mk\('p', '#4EA8A9'\)/);
  assert.match(SRC, /o\.src = '\/media\/romp-swirl-o\.svg'/);
  assert.match(SRC, /@keyframes tl-rl-spin\{to\{transform:rotate\(-360deg\)\}\}/);
  assert.match(SRC, /rl-dots/);
});
