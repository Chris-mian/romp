// Chat rail rendering (the user 2026-06-13/14). Two changes, both about the left rail:
//   1. Tool outcome lives ONLY on the left dot now — green ✓ disc on success, red ✗ disc on
//      error. The duplicate right-side in-head ✓/✗ (`.tool-status`) was removed.
//   2. A day boundary's marker stacks the date on its OWN line above the time, so a combined
//      "Yesterday · 21:24" no longer overruns the narrow gutter into the dot.
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

test("a day marker stacks the date above the time so it can't overrun the gutter", () => {
  assert.match(RENDER, /el\("span", "tm-date"\)/);
  assert.match(RENDER, /el\("span", "tm-time"\)/);
  // the date line floats on its own row above (absolute, bottom:100%)
  assert.match(CSS, /\.time-marker\.day \.tm-date \{[^}]*position: absolute[^}]*bottom: 100%/);
});
