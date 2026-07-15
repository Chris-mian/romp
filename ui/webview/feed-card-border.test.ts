// Feed cards are outlined with a 2px border in their corresponding session's identity colour (the user
// 2026-07-15) — up from a faint 1px recency tint. Both the single-session AskItem card and the multi-session
// AskGroup card colour their border by the session (with the recency tint as a colourless fallback so the
// border can never void to transparent). Source-level pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card border is 2px (bolder than the old 1px; softened via a 0.5-alpha colour)", () => {
  assert.match(CSS, /\.fitem \{[\s\S]*?border: 2px solid transparent;/);
});

// PLAIN rgba, NOT color-mix — a reused card node silently rejects an invalid inline border-color and keeps
// the old solid colour, so the alpha never appeared (the user 2026-07-15). hexToRgba builds the rgba directly.
test("hexToRgba turns a session hex into a plain rgba() at the given alpha", () => {
  assert.match(FEED, /function hexToRgba\(hex: string, alpha: number\): string \| null \{/);
  assert.match(FEED, /return `rgba\(\$\{\(n >> 16\) & 255\}, \$\{\(n >> 8\) & 255\}, \$\{n & 255\}, \$\{alpha\}\)`;/);
  assert.doesNotMatch(FEED, /borderColor = [^\n]*color-mix/);   // no border uses color-mix — it was being rejected
});

test("a real AskItem card is bordered in its session colour at 0.5 alpha (plain rgba), recency tint as fallback", () => {
  assert.match(FEED, /card\.style\.borderColor = \(it\.color && \(hexToRgba\(it\.color\.bg, 0\.5\) \?\? it\.color\.bg\)\) \|\| `rgba\(\$\{r\}, \$\{g\}, \$\{b\}/);
});

test("an AskGroup (multi-session) card is bordered in its group session colour at 0.5 alpha, recency tint as fallback", () => {
  assert.match(FEED, /card\.style\.borderColor = \(g\.color && \(hexToRgba\(g\.color\.bg, 0\.5\) \?\? g\.color\.bg\)\) \|\| `rgba\(\$\{r\}, \$\{gg\}, \$\{b\}/);
});
