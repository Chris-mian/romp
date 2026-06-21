// "Nudge" button (the user 2026-06-18): on the WORKING card itself (moved off the modal footer), beside
// Clear. One click sends the canned AUTO_NUDGE_TEXT status question (mirrored from bin/romp-kernel) via
// askFollowUp with nudge:true (romp-authored → gray bubble) — the SAME path Follow up uses, so the kernel
// quotes the goal as context. Source-level pin (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the card builds a Nudge button in its actions row, beside Clear", () => {
  assert.match(FEED, /const nudge = el\("button", "fdismiss ffollow fask-nudge"\); nudge\.textContent = "Nudge"/);
  // the action row is buttons only now (the state badges moved up to the name row, 2026-06-19)
  assert.match(FEED, /actions\.append\(apiRetry, nudge, clr\)/);
  assert.match(FEED, /a\._nudge = nudge;/);
});

test("Nudge sends the canned status question via the askFollowUp path (goal quoted as context)", () => {
  assert.match(FEED, /nudge\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); vscodeApi\?\.postMessage\(\{ type: "askFollowUp", itemId: it\.itemId, nudge: true, text: "Status on the goal above: what's done, what's left, and is anything blocked waiting on a decision from me\?" \}\); \};/);
});

test("Nudge shows ONLY on a real working card (it.column === 'working', not a provisional placeholder)", () => {
  assert.match(FEED, /a\._nudge\.style\.display = \(it\.column === "working" && !it\.provisional\) \? "" : "none";/);
});

test("Nudge is NO LONGER in the modal footer (it moved to the card)", () => {
  assert.doesNotMatch(FEED, /feed-modal-checkstatus/);
  assert.doesNotMatch(FEED, /wireCheckStatus/);
  assert.match(FEED, /footRow\.append\(age, fup, clr\)/);   // footer back to age · Follow up · Clear
});
