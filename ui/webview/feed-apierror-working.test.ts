// An API error is a TRANSIENT stall, not a block (the user 2026-06-29): the card STAYS in Working (not moved
// to Blocked/needs-input) and just shows the "⚠ API error" chip + Retry. Source pins (no jsdom for feed.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("askColumn keeps an apiError card in its own column (Working), only real blocks file under needs-input", () => {
  assert.match(FEED, /if \(it\.blocked && it\.blocked\.state !== "apiError"\) return "needsInput";/);
});

test("the apiError chip + Retry still show (they key on blocked.state, not the column)", () => {
  assert.match(FEED, /const isApiErr = it\.blocked\?\.state === "apiError";/);
  assert.match(FEED, /a\._apiBadge\.style\.display = isApiErr \? "" : "none";/);
  assert.match(FEED, /a\._apiRetry\.style\.display = isApiErr \? "" : "none";/);
});

test("Nudge is suppressed on an apiError card (Retry is its action)", () => {
  assert.match(FEED, /a\._nudge\.style\.display = \(it\.column === "working"[^)]*it\.blocked\?\.state !== "apiError"\)/);
});
