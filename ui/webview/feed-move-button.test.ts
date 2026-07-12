// The feed modal's "Move to Working" button (the user 2026-07-06): a follow-up WITHOUT a message — the
// card is not done / not waiting on the user. Shown only on a needs-input or completed SINGLE-ASK card;
// posts cardMove, flips the card optimistically as a PLAIN move (no "Followed up" chip styling), and the
// kernel-side user_move stamps the followupAt evidence floor. No jsdom for the feed renderer, so pin at
// the source (feed.ts + bin/romp-kernel + bin/romp-judge).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");
const JUDGE = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-judge"), "utf8");

test("the modal has a Move to Working button, shown only for a needs-input/completed single ask", () => {
  assert.match(FEED, /mv\.id = "feed-modal-move"/);
  assert.match(FEED, /mv\.textContent = "Move to Working"/);
  // gated on the card being OUT of Working; wired in the single-ask (it) branch only
  assert.match(FEED, /if \(mvEl && \(it\.column === "needs_input" \|\| it\.column === "completed"\)\) \{/);
  // default-hidden + reset on every render, so the group/standalone modals never show it
  assert.match(FEED, /mvEl\.style\.display = "none"; mvEl\.disabled = false; mvEl\.textContent = "Move to Working";/);
});

test("clicking posts cardMove and acknowledges BEFORE the kernel round-trip", () => {
  assert.match(FEED, /type: "cardMove", itemId: it\.itemId, sid: it\.sid, to: "working"/);
  // acknowledge-first (the buttons rule): disable + relabel precedes the post in the handler
  const handler = FEED.slice(FEED.indexOf('mvEl.onclick = () => {'));
  const ack = handler.indexOf('mvEl.disabled = true; mvEl.textContent = "Moving…";');
  const post = handler.indexOf('type: "cardMove"');
  assert.ok(ack >= 0 && post > ack, "disable+relabel comes before the cardMove post");
});

test("the optimistic flip is a PLAIN move — no follow-up chip styling, its own revert toast", () => {
  assert.match(FEED, /optimisticFollowMove\(it\.itemId, true\);/);
  // plain ids skip the recheck + followupPending prediction styling
  assert.match(FEED, /if \(!pendingMovePlain\.has\(a\.itemId\)\) \{ a\.recheck = true; a\.followupPending = true; \}/);
  // the revert toast names a move, not a follow-up
  assert.match(FEED, /That move didn’t stick/);
  // reconcile clears the plain marker with the prediction
  assert.match(FEED, /pendingFollowMove\.delete\(id\); pendingMovePlain\.delete\(id\);/);
});

test("kernel: cardMove routes to jd.user_move with 'working' as the only legal target", () => {
  assert.match(KERNEL, /elif t == "cardMove":/);
  assert.match(KERNEL, /if iid and \(msg\.get\("to"\) or "working"\) == "working":/);
  assert.match(KERNEL, /jd\.user_move\(sid, iid, now=int\(time\.time\(\)\)\)/);
  assert.match(KERNEL, /_mark_views_dirty\(\)/);
});

test("judge: user_move reuses the follow-up machinery — reopen + followupAt floor + stub, NO followupPending", () => {
  assert.match(JUDGE, /def user_move\(fsid, gid, now=None\):/);
  assert.match(JUDGE, /_reopen\(store, gid, by="user-move", now=now\)/);
  // the same stamp drives the Working sort floor and BOTH staleness floors (block + done),
  // routed through the fused gate+recorder since P3.1 (record_verdict, 2026-07-06)
  assert.match(JUDGE, /def _done_is_stale\(nd, ev_t\):/);
  assert.match(JUDGE, /record_verdict\(store, nodes\[t\], "planner", "done", seg_t/);   // planner done guard
  assert.match(JUDGE, /if not record_verdict\(store, nd, "closer", "done", t/);        // closer done guard
  // user_move itself never sets the followupPending chip
  const um = JUDGE.slice(JUDGE.indexOf("def user_move("), JUDGE.indexOf("def user_move(") + 3200);
  assert.ok(!um.includes('followupPending"] = True'), "user_move must not set the follow-up chip flag");
});

test("judge: the grouper's never-move-an-everDone-node guard is gone (removed to try, the user 2026-07-06)", () => {
  assert.ok(!JUDGE.includes("and not allow_done"), "the everDone relink guard was removed");
  // (tops → menu 2026-07-11: the grouper's index space now numbers steps too, for the merge op)
  assert.match(JUDGE, /def apply_group\(store, menu, ops, t\):/);   // allow_done parameter dropped too
});
