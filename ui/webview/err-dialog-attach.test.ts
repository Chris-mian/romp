// The feed's error dialog shows its words. showErrDialog built its box (title, detail, Copy, Dismiss) and appended
// only the empty overlay to the body, so an err frame reaching a feed pane painted a bare dim sheet with no words
// and no button, dismissable only by clicking the sheet (found by the verifier of PR 1967, 2026-09-21). The End
// hand-back now aims the not-delivered frame at a feed pane when no chat pane is connected (PR 1994), a new road
// to that dialog, so the attach rides along here. No jsdom for this renderer: pinned at source, the module's
// convention (undelivered-err.test.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("feed: showErrDialog attaches its box to the overlay before the overlay goes on the body", () => {
  const m = FEED.match(/function showErrDialog\(title: string, text: string, copy: string\) \{([\s\S]*?)\n\}\n/);
  assert.ok(m, "showErrDialog is defined with its three-string signature");
  const body = m![1];
  assert.match(body, /overlay\.appendChild\(box\);[^\n]*\n\s*document\.body\.appendChild\(overlay\);/,
    "the box goes INTO the overlay, then the overlay onto the body; a detached box paints a bare dim sheet");
});
