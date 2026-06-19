// Per-session settings gear on the timeline lane (the user 2026-06-19): a ⚙ between the session name and
// the model that opens a flag menu — currently "hide from feed" (the session's prompts stop minting feed
// cards but it stays on the timeline). The timeline view has no headless render harness for the lane
// header, so — like timeline-view.test.ts — pin the wiring at the source level against the shared
// obsidian/romp-timeline-view.js (the same file the web dashboard serves verbatim).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js"), "utf8");

test("a per-session gear column sits BETWEEN the name and the model (live lanes only)", () => {
  // a reserved gear column, after the name, before the model — width added only when a live lane exists
  assert.match(SRC, /const gearColX = PADL \+ Math\.ceil\(maxName\) \+ COLGAP;/);
  assert.match(SRC, /const modelColX = gearColX \+ \(anyLive \? GEAR_W \+ GEAR_GAP : 0\);/);
  // the gear glyph is drawn only on live lanes
  assert.match(SRC, /if \(s\.live\) \{[\s\S]*?GEAR_GLYPH/);
});

test("the gear has a generous transparent hit RECT (not the painted glyph) so it's easy to click", () => {
  // the bug: a bare <text> glyph only catches clicks on its painted strokes (the user 2026-06-19) —
  // so the glyph is pointer-events:none and a transparent rect with pointer-events:all is the hit target
  assert.match(SRC, /GEAR_GLYPH; svg\.appendChild\(g\)/);
  assert.match(SRC, /'pointer-events': 'none'[\s\S]*?GEAR_GLYPH/, "the glyph itself takes no pointer events");
  assert.match(SRC, /const hit = el\('rect', \{[^}]*fill: 'transparent', 'pointer-events': 'all'/);
  assert.match(SRC, /hit\.addEventListener\('click', \(e\) => \{ e\.stopPropagation\(\); this\._openFlagMenu\(s, hit\)/);
});

test("the gear brightens when a flag is active so a muted lane stands out", () => {
  assert.match(SRC, /const fon = !!s\.hideFromFeed;/);
  assert.match(SRC, /fill: fon \? GEAR_ON_FG : MODEL_FG/);
  assert.match(SRC, /const GEAR_ON_FG = /);
});

test("the flag menu lists the session flags with a ✓ + hint, toggling optimistically", () => {
  assert.match(SRC, /_openFlagMenu\(s, anchorEl\)/);
  assert.match(SRC, /const SESSION_FLAGS = \[/);
  assert.match(SRC, /key: 'hideFromFeed'/);
  assert.match(SRC, /for \(const f of SESSION_FLAGS\)/);
  assert.match(SRC, /s\[f\.key\] = next;/, "optimistic local update before the round-trip");
  assert.match(SRC, /this\._setSessionFlag\(s, f\.key, next\)/);
});

test("setSessionFlag posts via the web host hook, with a Node-fs fallback for Obsidian", () => {
  assert.match(SRC, /_setSessionFlag\(s, flag, value\)/);
  assert.match(SRC, /window\.__rompTimelineSetFlag === 'function'/);
  assert.match(SRC, /window\.__rompTimelineSetFlag\(s\.id, flag, value\)/);
  assert.match(SRC, /session-flags\.json/, "Obsidian/headless writes the same file the kernel reads");
});

test("the flag menu reuses the shared _metaMenu (outside-click / Esc close) under a 'flags' kind", () => {
  assert.match(SRC, /this\._metaMenu\._kind === 'flags'/);
  assert.match(SRC, /menu\._kind = 'flags'; menu\._sid = s\.id;/);
});
