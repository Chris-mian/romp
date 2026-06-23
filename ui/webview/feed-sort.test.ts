// Feed card sort order (the user 2026-06-23): the ⛭ gear's "Oldest first" checkbox flips every column from
// the default newest-at-top to oldest-at-top. Read from the shared romp:settings, applied live (the feed
// already re-renders on the 'romp:settings' event). Source-pin over feed.ts + the kernel gear.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("feedPrefs reads oldestFirst, and the column sort flips on it (default newest-first)", () => {
  assert.match(FEED, /oldestFirst: !!s\.oldestFirst/);
  assert.match(FEED, /const oldestFirst = feedPrefs\(\)\.oldestFirst;/);
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => oldestFirst \? x\.t - y\.t : y\.t - x\.t\)/);
});

test("the ⛭ gear has an 'Oldest first' checkbox wired to the romp:settings.oldestFirst pref", () => {
  assert.match(KERNEL, /<input type=checkbox id=rs-oldest>/);
  assert.match(KERNEL, /<b>Oldest first<\/b>/);
  assert.match(KERNEL, /of=document\.getElementById\('rs-oldest'\)/);
  assert.match(KERNEL, /oldestFirst:false/);   // a load() default so the key always exists
  assert.match(KERNEL, /s\.oldestFirst=of\.checked;save\(s\);emit\(\)/);   // writes + fires the live re-sort event
  assert.match(KERNEL, /if\(of\)of\.checked=!!s\.oldestFirst;/);            // gear-open initialises the box
});
