// Feed cards are outlined with a 2px border in their corresponding session's identity colour (the user
// 2026-07-15) — up from a faint 1px recency tint. The colour is CSS-driven from per-card --card-r/g/b
// channels (a PLAIN rgba, not color-mix which a reused card node can silently reject) so the highlight can
// BOLD the SAME colour (0.5α rest → 0.8α pinned → full when focused/hovered) instead of a white ring. Both the
// single-session AskItem card and the multi-session AskGroup card set their channels from the session colour,
// with the recency tint as a colourless fallback. Source-level pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card border is 2px", () => {
  assert.match(CSS, /\.fitem \{[\s\S]*?border: 2px solid transparent;/);
});

test("hexToRgb splits a session hex into [r,g,b] channels (no color-mix — it was being rejected)", () => {
  assert.match(FEED, /function hexToRgb\(hex: string\): \[number, number, number\] \| null \{/);
  assert.match(FEED, /return \[\(n >> 16\) & 255, \(n >> 8\) & 255, n & 255\];/);
  assert.doesNotMatch(FEED, /border[Cc]olor[^\n]*color-mix/);
});

test("setCardChannels writes --card-r/g/b and clears the inline border-color (CSS owns it)", () => {
  assert.match(FEED, /card\.style\.setProperty\("--card-r", String\(rgb\[0\]\)\)/);
  assert.match(FEED, /card\.style\.setProperty\("--card-g", String\(rgb\[1\]\)\)/);
  assert.match(FEED, /card\.style\.setProperty\("--card-b", String\(rgb\[2\]\)\)/);
  assert.match(FEED, /card\.style\.borderColor = "";/);
});

test("a real AskItem card sets its channels from the session colour, recency tint as fallback", () => {
  assert.match(FEED, /setCardChannels\(card, \(it\.color && hexToRgb\(it\.color\.bg\)\) \|\| \[r, g, b\]\);/);
});

test("an AskGroup (multi-session) card sets its channels from the group session colour, recency tint as fallback", () => {
  assert.match(FEED, /setCardChannels\(card, \(g\.color && hexToRgb\(g\.color\.bg\)\) \|\| \[r, gg, b\]\);/);
});

test("the border colour is CSS-driven from the channels: 0.5α at rest", () => {
  assert.match(CSS, /\.fitem\.ask, \.fitem\.fgroup \{ border-color: rgba\(var\(--card-r, 255\), var\(--card-g, 255\), var\(--card-b, 255\), 0\.5\); \}/);
});

test("the highlight BOLDS the same colour (no white ring): pinned 0.8α, focused full opacity", () => {
  assert.match(CSS, /\.fitem\.ask\.pinned  \{ border-color: rgba\(var\(--card-r, 255\), var\(--card-g, 255\), var\(--card-b, 255\), 0\.8\); \}/);
  assert.match(CSS, /\.fitem\.ask\.focused \{ border-color: rgb\(var\(--card-r, 255\), var\(--card-g, 255\), var\(--card-b, 255\)\); \}/);
  // the old white box-shadow rings are gone
  assert.doesNotMatch(CSS, /\.fitem\.ask\.focused \{ box-shadow: 0 0 0 2px #fff/);
  assert.doesNotMatch(CSS, /\.fitem\.ask\.pinned \{ box-shadow: 0 0 0 1\.5px rgba\(255, 255, 255/);
});
