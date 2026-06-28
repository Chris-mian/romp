// Feed cards FLY to their new column when status changes (the user 2026-06-27), instead of teleporting. Cards
// are reused nodes reconcileCol MOVES between columns, so FLIP works: record rect+column before the move, then
// invert+play after. The flying card rides the BACK layer (z-index:-1 in the #feed-cols stacking context) so it
// never passes over other cards. Source pins (no jsdom for feed.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("render() captures rects BEFORE the reconcile and flies changed cards AFTER", () => {
  // capture must precede the column reconciles…
  assert.match(FEED, /const flipFirst = captureCardRects\(cols\);[\s\S]*?reconcileCol\(cols\.asks/);
  // …and the fly runs after the DOM (and scroll) settle
  assert.match(FEED, /list\.scrollTop = prevScroll;\s*\n\s*\/\/ FLIP step 2[\s\S]*?flyColumnChanges\(flipFirst, cols\);/);
});

test("captureCardRects records each card's rect + column", () => {
  assert.match(FEED, /function captureCardRects\(/);
  assert.match(FEED, /m\.set\(c\.dataset\.key, \{ rect: c\.getBoundingClientRect\(\), col: colEl\.id \}\)/);
});

test("flyColumnChanges only flies a card whose COLUMN changed (not new cards / non-movers)", () => {
  assert.match(FEED, /function flyColumnChanges\(/);
  assert.match(FEED, /if \(!prev \|\| prev\.col === colEl\.id\) continue;/);   // new card OR same column → skip
  assert.match(FEED, /if \(!dx && !dy\) continue;/);                          // no real move → skip
});

test("FLIP: invert to the old spot instantly, then release with a transition (two rAFs)", () => {
  assert.match(FEED, /c\.style\.transition = "none";\s*\n\s*c\.style\.transform = `translate\(\$\{dx\}px, \$\{dy\}px\)`;/);
  assert.match(FEED, /requestAnimationFrame\(\(\) => requestAnimationFrame\(\(\) => \{[\s\S]*?c\.style\.transform = "translate\(0, 0\)";/);
  // cleans up on transitionend so the card returns to normal flow + stacking
  assert.match(FEED, /ev\.propertyName !== "transform"/);
  assert.match(FEED, /c\.classList\.remove\("fitem-flying"\)/);
});

test("respects prefers-reduced-motion", () => {
  assert.match(FEED, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)\.matches\) return;/);
});

test("the flying card sits in the BACK layer, and #feed-cols is the stacking context that makes that work", () => {
  assert.match(CSS, /\.feed-cols \{[^}]*position: relative; z-index: 0;/);
  assert.match(CSS, /\.fitem-flying \{ position: relative; z-index: -1; pointer-events: none; will-change: transform; \}/);
});
