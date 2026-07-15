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

test("the card border is 1.5px (bolder than the old 1px, dialled back ~25% from 2px for subtlety)", () => {
  assert.match(CSS, /\.fitem \{[\s\S]*?border: 1\.5px solid transparent;/);
});

test("a real AskItem card is bordered in its session colour, recency tint as fallback", () => {
  assert.match(FEED, /card\.style\.borderColor = it\.color\?\.bg \?\? `rgba\(\$\{r\}, \$\{g\}, \$\{b\}/);
});

test("an AskGroup (multi-session) card is bordered in its group session colour, recency tint as fallback", () => {
  assert.match(FEED, /card\.style\.borderColor = g\.color\?\.bg \?\? `rgba\(\$\{r\}, \$\{gg\}, \$\{b\}/);
});
