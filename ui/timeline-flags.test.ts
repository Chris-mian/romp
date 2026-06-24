// Per-session feed show/hide CHECKBOX on the timeline lane (the user 2026-06-22; a circular checkbox since
// 2026-06-23, was an eye): a small gray box+check between the session name and the model. ON the feed
// (default) = a checked ring; OFF the feed = the SAME checkbox struck through + MORE faded (de-emphasised,
// never a highlight colour). ONE click toggles hideFromFeed directly — no popup menu. The timeline view has
// no headless render harness for the lane header, so — like timeline-view.test.ts — pin the wiring at the
// source level against the shared ui/romp-timeline-view.js (the same file the web dashboard serves verbatim).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("a per-session feed-checkbox column sits BETWEEN the name and the model (live lanes only)", () => {
  assert.match(SRC, /const eyeColX = PADL \+ Math\.ceil\(maxName\) \+ COLGAP;/);
  // business inserted a postal-isolation mailColX between the feed checkbox and the model (main 56ae453),
  // so the model column now hangs off mailColX, not eyeColX directly.
  assert.match(SRC, /const mailColX = eyeColX \+ \(anyLive \? EYE_W \+ EYE_GAP : 0\);/);
  assert.match(SRC, /const modelColX = mailColX \+ \(anyLive \? EYE_W \+ EYE_GAP : 0\);/);
  assert.match(SRC, /if \(s\.live\) \{[\s\S]*?feedCheckIcon\(off, cx, cy, MODEL_FG\)/);
});

test("the checkbox is DRAWN (a gray ring + a checkmark); the OFF state adds the same strike-through slash", () => {
  // not an emoji glyph — an SVG circle ring + a polyline check, monochrome (stroke = color, no fill), so it
  // stays crisp everywhere; the eye's almond+pupil is gone.
  assert.match(SRC, /function feedCheckIcon\(off, cx, cy, color\)/);
  assert.doesNotMatch(SRC, /function eyeIcon\b/, "the old eye drawer is replaced");
  assert.match(SRC, /el\('circle', \{ cx: cx, cy: cy, r: 6, fill: 'none', stroke: color, 'stroke-width': 1\.2 \}\)/);
  assert.match(SRC, /el\('path', \{ d: 'M'[\s\S]*?fill: 'none', stroke: color[\s\S]*?'stroke-linejoin': 'round' \}\)/);
  // off → the same diagonal slash through it (the "hidden" affordance, unchanged from the eye)
  assert.match(SRC, /if \(off\) g\.appendChild\(el\('line', \{ x1: cx - 6\.5[\s\S]*?stroke: color/);
});

test("the checkbox is always GRAY; the OFF state is MORE faded (de-emphasised), never highlighted (the user 2026-06-23)", () => {
  // one colour (MODEL_FG) for both states — the off lane is faded a touch more (0.3, was 0.4), NOT spotlit
  assert.match(SRC, /const dim = off \? '0\.3' : '0\.62';/);
  assert.match(SRC, /const box = feedCheckIcon\(off, cx, cy, MODEL_FG\);/);
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
  assert.match(SRC, /mouseenter', \(e\) => \{ box\.setAttribute\('opacity', '1'\); this\.showTip\(tip, e\)/);
  assert.match(SRC, /mousemove', \(e\) => this\.moveTip\(e\)/);
  assert.match(SRC, /mouseleave', \(\) => \{ box\.setAttribute\('opacity', dim\); this\.hideTip\(\)/);
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

test("every timeline dot's white border is thin (0.75px) — romp + user dots alike (the user 2026-06-23)", () => {
  // the shared dot() helper strokes #e8eef5 at 0.75 (was 1.5) for EVERY dot — prompt dots, the romp swirl dot, etc.
  assert.match(SRC, /el\('circle', \{ cx, cy, r: DOT_R, fill: color, stroke: '#e8eef5', 'stroke-width': 0\.75 \}\)/);
  assert.doesNotMatch(SRC, /stroke: '#e8eef5', 'stroke-width': 1\.5/, "the old 1.5px dot border is gone");
});
