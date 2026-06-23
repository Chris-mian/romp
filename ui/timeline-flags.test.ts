// Per-session feed show/hide EYE on the timeline lane (the user 2026-06-22, replacing the old gear + flag
// menu): a small gray eye between the session name and the model. ON the feed (default) = a plain eye; OFF
// the feed = the SAME eye struck through + DIMMER (de-emphasised, never a highlight colour). ONE click
// toggles hideFromFeed directly — no popup menu. The timeline view has no headless render harness for the
// lane header, so — like timeline-view.test.ts — pin the wiring at the source level against the shared
// ui/romp-timeline-view.js (the same file the web dashboard serves verbatim).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("a per-session EYE column sits BETWEEN the name and the model (live lanes only)", () => {
  assert.match(SRC, /const eyeColX = PADL \+ Math\.ceil\(maxName\) \+ COLGAP;/);
  assert.match(SRC, /const modelColX = eyeColX \+ \(anyLive \? EYE_W \+ EYE_GAP : 0\);/);
  assert.match(SRC, /if \(s\.live\) \{[\s\S]*?eyeIcon\(off, cx, cy, MODEL_FG\)/);
});

test("the eye is DRAWN (almond outline + pupil); the OFF state adds a strike-through slash", () => {
  // not an emoji glyph — an SVG path almond + a pupil circle, so it stays crisp + monochrome
  assert.match(SRC, /function eyeIcon\(off, cx, cy, color\)/);
  assert.match(SRC, /el\('path', \{ d: 'M' \+ \(cx - 6\)[\s\S]*?fill: 'none', stroke: color/);
  assert.match(SRC, /el\('circle', \{ cx: cx, cy: cy, r: 1\.5, fill: color \}\)/);
  // off → a diagonal slash line through the eye (the "hidden" affordance the user asked for)
  assert.match(SRC, /if \(off\) g\.appendChild\(el\('line', \{ x1: cx - 6\.5[\s\S]*?stroke: color/);
});

test("the eye is always GRAY; the OFF state is DIMMER (de-emphasised), never highlighted (the user 2026-06-22)", () => {
  // one colour (MODEL_FG) for both states — the off lane is dimmed, NOT painted a spotlight amber
  assert.match(SRC, /const dim = off \? '0\.4' : '0\.62';/);
  assert.match(SRC, /const eye = eyeIcon\(off, cx, cy, MODEL_FG\);/);
  assert.doesNotMatch(SRC, /FEED_OFF_FG/, "no amber highlight colour for the off state");
  assert.doesNotMatch(SRC, /GEAR_ON_FG/, "the old amber gear-active colour is gone");
});

test("the eye has a generous transparent hit RECT, and ONE click toggles hideFromFeed directly (no menu)", () => {
  assert.match(SRC, /const hit = el\('rect', \{[^}]*fill: 'transparent', 'pointer-events': 'all'/);
  // direct toggle on click: optimistic local flip + persist via _setSessionFlag — no _openFlagMenu
  assert.match(SRC, /hit\.addEventListener\('click', \(e\) => \{[\s\S]*?s\.hideFromFeed = next;[\s\S]*?this\._setSessionFlag\(s, 'hideFromFeed', next\)/);
  assert.doesNotMatch(SRC, /_openFlagMenu/, "the popup flag menu is removed");
  assert.doesNotMatch(SRC, /const SESSION_FLAGS = \[/, "the flag list is removed (single flag, direct toggle)");
});

test("the tooltip uses the shared showTip/hideTip (a native SVG <title> never shows — a redraw kills it)", () => {
  // the bug the user hit: no tooltip appeared. showTip freezes live-follow so the tip survives the timeline's
  // frequent redraws; a native <title> needs ~1s of stable hover that a redraw interrupts.
  assert.match(SRC, /mouseenter', \(e\) => \{ eye\.setAttribute\('opacity', '1'\); this\.showTip\(tip, e\)/);
  assert.match(SRC, /mousemove', \(e\) => this\.moveTip\(e\)/);
  assert.match(SRC, /mouseleave', \(\) => \{ eye\.setAttribute\('opacity', dim\); this\.hideTip\(\)/);
  assert.match(SRC, /Off the feed — click to put it back on/);
  assert.match(SRC, /On the feed — click to take it off/);
});

test("setSessionFlag still posts via the web host hook, with a Node-fs fallback for Obsidian", () => {
  assert.match(SRC, /_setSessionFlag\(s, flag, value\)/);
  assert.match(SRC, /window\.__rompTimelineSetFlag === 'function'/);
  assert.match(SRC, /window\.__rompTimelineSetFlag\(s\.id, flag, value\)/);
  assert.match(SRC, /session-flags\.json/, "Obsidian/headless writes the same file the kernel reads");
});

test("the eye toggle is OPTIMISTIC + STICKY: held across pushes until the kernel confirms (no flicker-back) (the user 2026-06-22)", () => {
  // the bug: click → eye flips → a routine push with the OLD flag reverts it for ~1s before the kernel's
  // rebuild lands. Fix: record the clicked value in _pendingFlags and re-apply it on every update() until the
  // incoming data matches it (then drop). So the click sticks instantly and never bounces.
  assert.match(SRC, /this\._pendingFlags = \{\};/);
  assert.match(SRC, /\(this\._pendingFlags\[s\.id\] = this\._pendingFlags\[s\.id\] \|\| \{\}\)\.hideFromFeed = next;/);
  // update() reconciles right after adopting the new data, BEFORE the early-returns/draw
  assert.match(SRC, /this\.data = data;\s*\n\s*this\._reconcilePendingFlags\(\);/);
  assert.match(SRC, /_reconcilePendingFlags\(\) \{[\s\S]*?if \(s\[flag\] === p\[flag\]\) delete p\[flag\];[\s\S]*?else s\[flag\] = p\[flag\];/);
});
