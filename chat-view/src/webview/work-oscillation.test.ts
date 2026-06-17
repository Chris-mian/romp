// The "working" UI breathes yellow→teal on ONE shared 1.5s sine clock — 2× the old 3s (the user
// 2026-06-16): the chat working chip, the chat tab dots, the feed session-name dots, and the timeline
// working chip. Same period everywhere → they pulse to teal together. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");
const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
const TIMELINE = fs.readFileSync(path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js"), "utf8");

test("chat working chip breathes on the 1.5s clock", () => {
  assert.match(CSS, /\.chip-pulse \{[^}]*animation: chip-pulse 1\.5s/);
});

test("chat tab dots oscillate yellow→teal on the 1.5s clock; subagent dot stays static", () => {
  assert.match(CSS, /@keyframes work-dot/);
  assert.match(CSS, /\.tab-dot \{[^}]*animation: work-dot 1\.5s/);
  assert.match(CSS, /\.tab\.tab-subagent \.tab-dot \{[^}]*animation: none/);
});

test("feed session-name dots oscillate yellow→teal on the 1.5s clock", () => {
  assert.match(FEED_CSS, /@keyframes fwork-dot/);
  assert.match(FEED_CSS, /\.fwork-dot \{[^}]*animation: fwork-dot 1\.5s/);
  assert.match(FEED_CSS, /\.ftree-who-dot \{[^}]*animation: fwork-dot 1\.5s/);
});

test("timeline working chip SMIL breathe is 1.5s too", () => {
  assert.match(TIMELINE, /attributeName: 'fill'[^)]*dur: '1\.5s'/);
});
