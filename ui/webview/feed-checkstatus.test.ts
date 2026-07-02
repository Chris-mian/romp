// The manual "Nudge" button was REMOVED (the user 2026-06-30): once Auto Nudge is robust you never
// hand-nudge a session, so the button (and the whole concept of manually nudging) is gone. What remains
// here is the surrounding footer/Follow-up structure it used to share. Source-level pin (no jsdom for the
// feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the manual Nudge button is gone (Auto Nudge replaces it)", () => {
  // exact-string pins: the passive "nudge failed" CHIP (fask-nudgefailed / a._nudgeFailed — a status cue
  // from the auto-nudge, design/stalled-open-todos-nudge.md) is a different thing and allowed to exist.
  assert.doesNotMatch(FEED, /"fask-nudge"/);
  assert.doesNotMatch(FEED, /nudge\.onclick/);
  assert.doesNotMatch(FEED, /a\._nudge[^A-Za-z]/);
  // the action row is buttons only (the state badges moved up to the name row, 2026-06-19); no Nudge now
  assert.match(FEED, /actions\.append\(apiRetry, revive, clr\)/);
});

test("the modal footer is age · Follow up · Clear (no check-status control)", () => {
  assert.doesNotMatch(FEED, /feed-modal-checkstatus/);
  assert.doesNotMatch(FEED, /wireCheckStatus/);
  assert.match(FEED, /footRow\.append\(age, fup, clr\)/);
});

test("the card's own 'Follow up' button is removed — click-to-cite covers it (the user 2026-07-01)", () => {
  // no card button, no toggle, no stored ref, and the one-click open-modal-into-composer plumbing is gone
  assert.doesNotMatch(FEED, /fask-fup/, "the card Follow up button (fask-fup) is gone");
  assert.doesNotMatch(FEED, /a\._cardFup/, "no stored card-Follow-up ref");
  assert.doesNotMatch(FEED, /openFollowUpOnRender/, "the card-only pop-into-composer flag is removed as dead code");
  // but the MODAL keeps its own Follow up (and its composer wiring)
  assert.match(FEED, /const fup = el\("button", "fdismiss ffollow feed-modal-follow"\)/, "the modal Follow up button stays");
  assert.match(FEED, /wireFollowUp\(fupEl, fuboxEl, fuinEl, fusendEl/, "the modal's own Follow up composer is still wired");
});
