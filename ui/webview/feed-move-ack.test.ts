// A predicted card move ends on the kernel's ANSWER, never on a stopwatch (the user 2026-07-21).
//
// The bug: replying to a card flipped it to Working, then ~4s later a toast claimed "That follow-up didn't
// move the card to Working — the session may not have picked it up" and the card fell back to Completed,
// while the session was already several tool calls into working that very reply. Two causes, both fixed
// here. (1) The feed serves a goal-store snapshot frozen for the length of a judge pass, and the reply's
// reopen went to the LIVE store — so a reply landing mid-pass was invisible for the whole pass, routinely
// 30-80 seconds, and no window the client could wait was ever going to be long enough. (2) The client was
// timing the kernel out at all, for something the kernel knows exactly: whether the reopen applied.
//
// So the kernel punches user writes through the snapshot (test_kernel.py) and ANSWERS the prediction with
// cardMoveAck: ok=false is the one real failure worth interrupting for, and buildId names which payload is
// the answer to this gesture. Source-level pins (no jsdom for the feed renderer), mirroring feed-move-button.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("kernel: every predicted move is answered, right after the prediction it answers", () => {
  assert.match(KERNEL, /def _ack_card_move\(ids, ok\):/);
  assert.match(KERNEL, /"type": "cardMoveAck", "ids": ids, "ok": bool\(ok\),/);
  assert.match(KERNEL, /"buildId": _feed_build_id\[0\]/);
  // the follow-up route: reopen, mark the write so it beats the pass snapshot, then answer
  const fu = KERNEL.slice(KERNEL.indexOf('elif t == "askFollowUp":'), KERNEL.indexOf('elif t == "cardMove":'));
  assert.match(fu, /ok = bool\(jd\.optimistic_followup\(/);
  assert.ok(fu.indexOf('_predict_working("followup"') < fu.indexOf("_ack_card_move([iid], ok)"),
    "the ack FOLLOWS its prediction, so a client can never see the answer before the question");
  assert.match(fu, /_note_user_goal_write\(sid\)/);
});

test("kernel: a user write is marked so it punches through a mid-flight judge pass", () => {
  assert.match(KERNEL, /def _note_user_goal_write\(sid\):/);
  // _feed_goals replays the override journal onto the frozen snapshot — the judge's OWN idempotent code,
  // so the user's reopen shows without admitting the judges' half-applied mid-pass writes alongside it
  assert.match(KERNEL, /jd\._replay_overrides\(sid, store\)/);
  assert.match(KERNEL, /jd\.rollup_status\(store, False\)/);
  // gated on the snapshot's READ time, stamped before the reads so a racing write counts as after them
  assert.match(KERNEL, /at = time\.time\(\)\s+# stamped BEFORE the reads/);
  // …and re-punched whenever the MARK moves, so a second gesture in one long pass lands too (test_kernel.py)
  assert.match(KERNEL, /if mark >= _goals_snap_at\[0\] and _goals_snap_done\.get\(sid\) != mark:/);
  // every user gesture that writes a goal store marks it: reply, Move to Working, crossing a node off,
  // and (2026-07-23) restoring a dismissed card — the un-clear that used to wait out the whole pass
  assert.equal((KERNEL.match(/^\s+_note_user_goal_write\(sid\)/gm) || []).length, 4);
});

test("kernel: the feed payload carries the build id, claimed BEFORE the read it describes", () => {
  assert.match(KERNEL, /def _next_feed_build_id\(\):/);
  const cached = KERNEL.slice(KERNEL.indexOf("def _cached_feed("), KERNEL.indexOf("def _cached_timeline("));
  const claim = cached.indexOf("bid = _next_feed_build_id()");
  const build = cached.indexOf("feed = build_feed(now, tmux)");
  assert.ok(claim >= 0 && build > claim,
    "claimed before the build: one already in flight when a click lands gets the LOWER id it deserves");
  assert.match(cached, /feed\["buildId"\] = bid/);
});

test("client: ok=false is the only thing that interrupts the user, and it says what actually happened", () => {
  assert.match(FEED, /function ackFollowMove\(itemId: string, ok: boolean, buildId: number\)/);
  assert.match(FEED, /m\.type === "cardMoveAck" && Array\.isArray\(m\.ids\)/);
  // a follow-up's MESSAGE still went out even when the card is gone — say so rather than implying it vanished
  assert.match(FEED, /Your reply was sent, but that card isn’t on the board any more to move to Working\./);
  // …and the old accusation that the session ignored the reply is gone for good
  assert.doesNotMatch(FEED, /the session may not have picked it up/);
  assert.doesNotMatch(FEED, /didn’t move the card to Working/);
});

test("client: an ACKED prediction yields only to a payload built AFTER the gesture", () => {
  // the exact race the old timer papered over: a build already in flight when the click landed cannot know
  // about the reopen, and taking it as the answer is the bounce back to Completed this replaced
  assert.match(FEED, /const acked = pendingMoveAck\.get\(id\);/);
  assert.match(FEED, /if \(acked !== undefined && buildId > acked\) clearFollowMove\(id\);/);
  assert.match(FEED, /function reconcileFollowMove\(incoming: AskItem\[\], buildId: number\)/);
});

test("client: an ack silences the toast but never lets a prediction wedge", () => {
  // ok=true re-arms the window SILENTLY: the kernel has spoken, so nothing after that is worth a toast, but
  // a prediction must not outlive the answer either if a payload goes missing
  const ack = FEED.slice(FEED.indexOf("function ackFollowMove("), FEED.indexOf("// On a fresh authoritative payload"));
  assert.match(ack, /pendingMoveAck\.set\(itemId, buildId\);/);
  assert.match(ack, /clearFollowMove\(itemId\); render\(\);\s*\/\/ silent wedge guard/);
  assert.ok(!/feedToast/.test(ack.slice(ack.indexOf("pendingMoveAck.set"))),
    "no toast on any path after the kernel confirmed the move");
  // a fresh gesture waits on its OWN answer, never inheriting the last one's
  assert.match(FEED, /pendingMoveAck\.delete\(itemId\);\s+\/\/ a fresh gesture waits on its OWN answer/);
});
