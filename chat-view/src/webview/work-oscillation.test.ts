// The "working" chip/badge breathes black→teal on a 1.5s sine clock — 2× the old 3s (the user
// 2026-06-16): the chat working chip and the timeline working chip. The working DOTS, by contrast,
// stay SOLID — their oscillation was distracting (the user 2026-06-16). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");
const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
const TIMELINE = fs.readFileSync(path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js"), "utf8");

test("chat working chip breathes on the 1.5s clock (2× the old 3s)", () => {
  assert.match(CSS, /\.chip-pulse \{[^}]*animation: chip-pulse 1\.5s/);
});

test("timeline working chip SMIL breathe is 1.5s too", () => {
  assert.match(TIMELINE, /attributeName: 'fill'[^)]*dur: '1\.5s'/);
});

test("working DOTS are SOLID — no animation (oscillation was distracting)", () => {
  // chat tab dot + feed session-name dots carry no animation, and the dot keyframes are gone
  assert.doesNotMatch(CSS, /@keyframes work-dot/);
  assert.doesNotMatch(CSS, /\.tab-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /@keyframes fwork-dot/);
  assert.doesNotMatch(FEED_CSS, /\.fwork-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /\.ftree-who-dot \{[^}]*animation/);
});
