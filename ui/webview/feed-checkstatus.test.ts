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
  assert.doesNotMatch(FEED, /fask-nudge/);
  assert.doesNotMatch(FEED, /nudge\.onclick/);
  assert.doesNotMatch(FEED, /a\._nudge/);
  // the action row is buttons only (the state badges moved up to the name row, 2026-06-19); no Nudge now
  assert.match(FEED, /actions\.append\(apiRetry, revive, cardFup, clr\)/);
});

test("the modal footer is age · Follow up · Clear (no check-status control)", () => {
  assert.doesNotMatch(FEED, /feed-modal-checkstatus/);
  assert.doesNotMatch(FEED, /wireCheckStatus/);
  assert.match(FEED, /footRow\.append\(age, fup, clr\)/);
});

test("a card 'Follow up' button on blocked/completed cards jumps straight into the modal composer (the user 2026-06-22)", () => {
  assert.match(FEED, /const cardFup = el\("button", "fdismiss ffollow fask-fup"\); cardFup\.textContent = "Follow up"/);
  assert.match(FEED, /actions\.append\(apiRetry, revive, cardFup, clr\)/);
  // shown ONLY on blocked (needs_input) or completed cards
  assert.match(FEED, /a\._cardFup\.style\.display = \(\(it\.column === "needs_input" \|\| it\.column === "completed"\) && !it\.provisional\) \? "" : "none"/);
  // click → open THIS goal's modal AND request the composer pop open on the next render
  assert.match(FEED, /cardFup\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); fullscreenAskId = it\.itemId; openFollowUpOnRender = true; renderModal\(\); \}/);
  assert.match(FEED, /if \(openFollowUpOnRender\) \{\s*openFollowUpOnRender = false;\s*if \(fupEl && fupEl\.style\.display !== "none" && fuboxEl && fuinEl\) \{\s*fuboxEl\.style\.display = ""; growFollowUp\(fuinEl\); fuinEl\.focus\(\);/);
  assert.match(FEED, /wireFollowUp\(fupEl, fuboxEl, fuinEl, fusendEl/, "the modal's own Follow up composer is still wired");
});
