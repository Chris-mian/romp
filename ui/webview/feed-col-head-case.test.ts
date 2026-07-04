// The feed's three column-header chips ("Working" / "Blocked" / "Completed") read as sentence case,
// matching the chat + timeline status chips (the user 2026-07-03). The labels were always cased in
// feed.ts; the ALL-CAPS look came from a text-transform:uppercase on .feed-col-head — dropped here.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the column labels are sentence-case in feed.ts", () => {
  assert.match(FEED, /\["asks", "Working", "working"\], \["needsInput", "Blocked", "blocked"\], \["completed", "Completed", "completed"\]/);
});

test(".feed-col-head no longer forces uppercase", () => {
  const m = CSS.match(/\.feed-col-head \{[\s\S]*?\}/);
  assert.ok(m, ".feed-col-head rule exists");
  assert.doesNotMatch(m![0], /text-transform:\s*uppercase/);
});
