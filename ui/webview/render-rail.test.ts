// Chat rail rendering (the user 2026-06-13/14). Two changes, both about the left rail:
//   1. Tool outcome lives ONLY on the left dot now — green ✓ disc on success, red ✗ disc on
//      error. The duplicate right-side in-head ✓/✗ (`.tool-status`) was removed.
//   2. A day boundary shows its date on a full-width divider above the day's first turn, NOT in
//      the rail — the gutter is 47px and "Yesterday" measures 52.6px, so it used to be clipped.
// The chat renderer has no jsdom harness, so — like the feed-*.test.ts files — pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the redundant right-side tool-status ✓/✗ is gone; the dot carries the outcome", () => {
  assert.doesNotMatch(RENDER, /tool-status/, "no in-head status glyph is created");
  assert.doesNotMatch(CSS, /\.tool-status\b/, "the dead .tool-status rules are removed");
  // error dot = a red disc with a white ✗, mirroring the green ✓ disc
  assert.match(CSS, /\.dot\.err::before \{[^}]*content: "✗"/);
  assert.match(CSS, /\.dot\.green::before \{[^}]*content: "✓"/);
});

test("the date rides a day divider, not the 47px rail gutter it used to be clipped by", () => {
  // the old stacked-in-the-gutter markup is GONE — that is what clipped "Yesterday"
  assert.doesNotMatch(RENDER, /tm-date|tm-time/, "no date/time spans stacked inside the marker");
  assert.doesNotMatch(CSS, /\.tm-date\b|\.tm-time\b/, "the stacked-marker rules are removed");
  // the divider carries it instead, with room to spare
  assert.match(RENDER, /el\("div", "day-divider"\)/);
  assert.match(RENDER, /el\("span", "day-divider-label"\)/);
  assert.match(CSS, /\.day-divider \{/);
  // the label must never be told to fit a fixed width — that is the bug class being closed
  assert.doesNotMatch(CSS, /\.day-divider-label \{[^}]*\bwidth:/);
  assert.match(CSS, /\.day-divider-label \{[^}]*white-space: nowrap/);
});

test("the rail marker shows only the time on a day boundary", () => {
  // `day ? hm : text` — never the combined "Yesterday · 21:24", which overran the gutter
  assert.match(RENDER, /m\.textContent = day \? hm : text/);
});
