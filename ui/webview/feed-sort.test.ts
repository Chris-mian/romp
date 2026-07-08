// Feed card sort order: oldest-at-top by DEFAULT (the user 2026-06-27) — the newest work sits at the BOTTOM
// of each column, and new/moved cards stack onto the bottom. A footer "Newest first" toggle (default OFF,
// the user 2026-07-07) reverses each column. The old ⛭ "Oldest first" gear checkbox stays gone. Source-pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("each column sorts oldest-at-top by default; the 'Newest first' toggle reverses it (the user 2026-07-07)", () => {
  assert.match(FEED, /const newestFirst = feedPrefs\(\)\.newestFirst;/);
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => newestFirst \? y\.t - x\.t : x\.t - y\.t\)/);
  // the footer toggle button writes romp:settings.newestFirst, default OFF
  assert.match(FEED, /ensureFeedToggle\("feed-newestfirst", "Newest first", \(\) => feedPrefs\(\)\.newestFirst, "newestFirst"/);
  assert.doesNotMatch(FEED, /oldestFirst/, "no oldestFirst pref — the natural order is oldest-first");
});

test("the 'Collapsed' toggle sets the default section state; a per-card expand overrides without leaving the mode", () => {
  // ON → new/at-default cards collapse (resolveSec default = none); toggling drops per-card overrides
  assert.match(FEED, /ensureFeedToggle\("feed-collapsed", "Collapsed", \(\) => feedPrefs\(\)\.collapsed, "collapsed"/);
  assert.match(FEED, /\(\) => \{ secChoice\.clear\(\); subChoice\.clear\(\); \}/, "toggling the mode clears BOTH the section and sub-goal per-card overrides so every card re-flows");
  assert.doesNotMatch(FEED, /anySectionOpen/, "the old Collapse/Expand-all button is gone");
});

test("the ⛭ gear no longer has an 'Oldest first' checkbox", () => {
  assert.doesNotMatch(KERNEL, /rs-oldest/);
  assert.doesNotMatch(KERNEL, /Oldest first/);
  assert.doesNotMatch(KERNEL, /oldestFirst/, "no leftover wiring in the gear JS/defaults");
});
