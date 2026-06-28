// Feed card sort order (the user 2026-06-27): the feed is ALWAYS oldest-at-top — the newest work sits at the
// BOTTOM of each column, nearest the eye, and new/moved cards stack onto the bottom. The old ⛭ "Oldest first"
// toggle is gone; this is the permanent behavior. Source-pin over feed.ts + the kernel gear.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("every column sorts oldest-at-top, unconditionally (no toggle)", () => {
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => x\.t - y\.t\)/);
  assert.doesNotMatch(FEED, /oldestFirst/, "the oldestFirst pref is gone — it's always oldest-first");
});

test("the ⛭ gear no longer has an 'Oldest first' checkbox", () => {
  assert.doesNotMatch(KERNEL, /rs-oldest/);
  assert.doesNotMatch(KERNEL, /Oldest first/);
  assert.doesNotMatch(KERNEL, /oldestFirst/, "no leftover wiring in the gear JS/defaults");
});
