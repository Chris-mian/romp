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
  // from the auto-nudge, plans/stalled-open-todos-nudge.md) is a different thing and allowed to exist.
  assert.doesNotMatch(FEED, /"fask-nudge"/);
  assert.doesNotMatch(FEED, /nudge\.onclick/);
  assert.doesNotMatch(FEED, /a\._nudge[^A-Za-z]/);
  // the action row is buttons only (the state badges moved up to the name row, 2026-06-19); no Nudge now
  assert.match(FEED, /actions\.append\(apiRetry, revive\)/);
});

test("the modal footer is age · Follow up · Move to Working · Check status · Clear", () => {
  // "Check status" (the user 2026-07-20) is NOT the old manual Nudge coming back: the Nudge was a
  // contentless poke at a stalled session (auto-nudge replaced it, above); Check status is a per-item
  // sweep — one message asking where every open/blocked sub-goal stands, whose replies file back per item.
  assert.match(FEED, /footRow\.append\(age, fup, mv, cs, clr\)/);   // mv = Move to Working (the user 2026-07-06); cs = Check status
  assert.match(FEED, /el\("button", "fdismiss feed-modal-status"\)/);
  assert.match(FEED, /cs\.textContent = "Check status"/);
});

test("the card-level 'Status?' sweep: one askFollowUp naming every open item; acked + re-armed event-based (the user 2026-07-20)", () => {
  // the sweep body enumerates the card's open/blocked subs (root + handoffs + cleared excluded), capped with an honest "+N more"
  assert.match(FEED, /function statusSweepText\(it: AskItem\)/);
  assert.match(FEED, /n\.status !== "done" && !n\.cleared && n\.kind !== "handoff" && n\.id !== it\.itemId/);
  assert.match(FEED, /\+" more on this card\)"|more on this card/);
  // card button: reads the CURRENT card data at click time (re-render-safe, the warnChip pattern), acks
  // by disable+relabel BEFORE the kernel round-trip, and only shows when there is something to sweep
  assert.match(FEED, /const cur = \(card as any\)\._askData as AskItem \| undefined;/);
  assert.match(FEED, /statBtn\.disabled = true; statBtn\.textContent = "Asked";/);
  // BLOCKED cards only (the user 2026-07-20): a Working card's agent is visibly moving — no status poke
  // from the card face; the modal's "Check status" stays available one click deeper for any card.
  assert.match(FEED, /stb\.style\.display = \(!it\.provisional && it\.live && it\.column === "needs_input"\s*\n\s*&& statusSweepText\(it\)\.n > 0\) \? "" : "none";/);
  // re-arm is EVENT-based: the judge's re-file clearing the followup/recheck state, never a timer
  assert.match(FEED, /if \(stb\.disabled && !it\.followupPending && !it\.recheck && !it\.rejudging\)/);
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
