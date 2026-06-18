// "Check status" button (the user 2026-06-18): in the single-ask / group modal footer, beside Follow up,
// shown only for a WORKING card. One click sends a canned "What is the status of the above goal?" down the
// SAME path as Follow up (postFollowUp → askFollowUp), so the kernel quotes the goal as context. Plain
// source-level pin (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("the modal footer builds a 'Check status' button between Follow up and Clear", () => {
  assert.match(FEED, /el\("button", "fdismiss ffollow feed-modal-checkstatus"\)/);
  assert.match(FEED, /chk\.textContent = "Check status"/);
  assert.match(FEED, /footRow\.append\(age, fup, chk, clr\)/);   // next to Follow up
});

test("Check status reuses the follow-up path with the canned status question", () => {
  assert.match(FEED, /postFollowUp\("What is the status of the above goal\?", fbId, fbTitle\)/);
});

test("Check status shows ONLY for a working card (it.column === 'asks') / a working group", () => {
  // gated on the RAW kernel column value "working" (NOT "asks" — that mismatch silently hid the button)
  assert.match(FEED, /wireCheckStatus\(it\.column === "working", it\.itemId\)/);
  assert.match(FEED, /wireCheckStatus\(grp\.members\.some\(\(m\) => m\.column === "working"\), grp\.members\[0\]\.itemId, grp\.title\)/);
  // hidden + unwired by default each render, so a non-working modal never shows a stale button
  assert.match(FEED, /if \(chkEl\) \{ chkEl\.style\.display = "none"; chkEl\.onclick = null; \}/);
});
