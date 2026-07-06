# Manual drag-to-recategorize + user-licensed regrouping

Design investigation, 2026-07-06; first increment BUILT same day (see "What
shipped" at the end — the user's decisions there supersede two proposals in the
body: no `userMovedAt` field, and the everDone guard was removed outright
rather than licensed). The ask: drag a feed card to
another column ("this blocked card shouldn't be blocked — put it in Working";
"pull this completed card back to Working"), have it auto-sort into place, and
have the system smoothly re-incorporate the user's verdict instead of fighting
it. Companion ask: two cards both in Working should be groupable even if one
was previously done/blocked — an erroneous split, dragged back together, should
let the grouper re-merge them.

## The governing insight: columns are derived, so a drag edits flags, not columns

A card's column is never stored directly — `rollup_status` (bin/romp-judge)
derives it from node flags (`blocked`, `nodeComplete`, `followupPending`,
`cleared`, settled). A drag that only changed a displayed column would snap
back on the next rollup. So the drag op must edit the same underlying flags
the judges edit — and the system already has exactly one flow that does this
on the user's behalf: the follow-up path (`optimistic_followup` → `_reopen`,
with the `followupAt` stamp and the `_block_is_stale` replay guard). **A drag
is a follow-up without a message.** The design is a generalization of that
proven path, not a new mechanism.

## Semantics: the drag is a floor, not a pin

The user's drag means "as of now, this card is Working." It voids judge
verdicts based on evidence from BEFORE the drag; it does not freeze the card.
New evidence after the drag flows normally — if the agent later genuinely
finishes, the card completes again; if it genuinely ends a turn asking the
user, it re-blocks. This is the same contract `followupAt` already implements
for blocks (`_block_is_stale`: a replayed verdict with `ev_t <= followupAt` is
void), and it is what avoids the weird edge cases: there is no permanent
user-pin fighting the judges, just a timestamp that outranks stale evidence.
(Precedent for user-outranks-judge already exists at the top of the ladder:
view-clear.)

## The op

One kernel message from the feed UI, mirroring `askFollowUp`:

    {type: "cardMove", sid, itemId, to: "working"}   // MVP: only "working"

Kernel handler calls a new judge-side `user_move(store, gid, to, now)`:

- **blocked → working** ("not actually blocked"): walk the node + subtree
  clearing `blocked`/`blockWhy` (mirroring `_reopen`'s ancestor walk), stamp
  `userMovedAt = now`. Do NOT set `followupPending` — there is no message in
  flight, so the "Re-judging…" chip and its rollup branch must not engage.
- **completed → working** ("reopen"): literally `_reopen(store, gid,
  by="user-drag")` + `userMovedAt = now`. `_reopen` already does everything
  wanted: stamps `everDone`, clears `nodeComplete`/`settledDone`, moves
  `settledAt` → `deltaSince` (so the distiller delta-scopes the next summary),
  un-resolves `rolledUp` children.
- Then `rollup_status`, `save_goals`, `_mark_views_dirty()` — same tail as the
  follow-up handler.

`userMovedAt` is a new node stamp, kept separate from `followupAt` because
`followupPending` carries UI semantics (re-judge chip) a silent drag must not
trigger. Every place that currently reads `followupAt` as a floor reads
`max(followupAt, userMovedAt)` instead:

1. **Sort**: `build_feed`'s working `disp_t` floor — the dragged card lands at
   the bottom of Working (newest end), auto-sorted, no special case.
2. **Block replay guard**: `_block_is_stale` — a stale block verdict cannot
   re-block the card.
3. **NEW — done replay guard** (the one genuinely new mechanism): a symmetric
   `_done_is_stale` check in `apply_plan`/`apply_close`'s done paths, so the
   planner/closer cannot re-complete a user-reopened card from evidence that
   predates the drag. Without this, completed→working snaps back on the next
   pass — this guard is the heart of the feature.

Nothing else needs teaching: settled/seam stamping, the distiller's
delta-divider, and the consolidator's umbrella-revert on reopen all already
key off the `_reopen` effects.

### Edge cases (resolved by the floor semantics)

- **Card under an umbrella**: drags operate on TOP-level cards (status is
  per-top). Dragging an umbrella moves the whole subtree — consistent with
  how status and grouping already work.
- **Nothing happens after a reopen-drag**: the card sits in Working as an
  orphaned working top — which is precisely what auto-nudge watches for. The
  emergent behavior is right: drag done→working on a stalled session and the
  nudge machinery asks the agent to pick it back up. No new code.
- **Open `agentTask` items**: the authoritative tier only forces *working*, so
  it never conflicts with a →working drag. (A future working→completed drag
  would need a policy call; out of scope.)
- **View-cleared cards**: invisible, undraggable; `_reopen` already refuses
  them. No interaction.
- **Later drags/follow-ups**: stamps are monotone (`max`), so repeated user
  actions compose.

### Deliberately out of scope (MVP)

- working → blocked (no use case: "blocked" means needs-the-user).
- working → completed (user marks done): plausible later — set
  `nodeComplete` + `everDone` + `settledDone`, `doneWhy: "marked done by the
  user"` — but Clear already covers most of the want.
- Dragging sub-goals between trees.

## UI

- **Gesture**: reuse the chat tab strip's drag pattern (`render.ts`
  draggable / module `draggedId` / midpoint hit-testing / `.drop-*` cues).
  Drop targets are the three column containers. Optimistic move generalizes
  `optimisticFollowMove`/`applyFollowMovePrediction` (predict `column` +
  `t=now`, reconcile on the next kernel payload).
- **Re-render safety**: the feed re-renders on every kernel push; a re-render
  mid-drag destroys the dragged node. Defer renders while a drag is in
  flight and flush on drop/dragend — the timeline's `_pointerHeld` pattern,
  event-based, exactly as the click-safety rule requires.
- **Touch**: HTML5 drag-and-drop does not exist on phones, where the feed is
  heavily used. Ship the same op behind an explicit card action too ("Move to
  Working" in the card's menu / the blocked card's action row) — the op layer
  is shared, the drag is the desktop gesture. The action-button form is also
  the cheaper first increment for testing the store semantics.

## Part 2: regrouping cards the user pushed back together

Today an erroneously-split pair can't be re-merged once either card has ever
completed, because of one rule: `apply_group` never moves an `everDone` node
("a once-done card keeps its standalone identity"). That guard is right for
the completed column but wrong for a card the USER deliberately pulled back
into Working — and note the drag itself sets `everDone` (via `_reopen`), so
without a change, drag-then-regroup can never work.

- **Trigger is already free**: the grouper's `groupedSig` gate is the open-top
  id set; a reopen changes that set, so the grouper re-runs on the next pass
  with no new wiring. "Drag it back to working and the grouper takes another
  look" falls out of the existing event gate.
- **License, don't abolish, the guard**: a user-initiated reopen
  (`_reopen(by="user-drag")`, and plausibly `by="optimistic"` follow-ups too)
  sets `regroupOk = True` on the top, which lifts the `everDone` guard for
  that node only; cleared again when the node next completes. Automatic
  reopens keep the conservative behavior. If fleet experience shows the guard
  is too tight generally, widen to "any currently-open top is groupable" as a
  follow-up — but start with the user-licensed version, since the guard's
  original purpose (protecting settled identities) still holds for cards the
  user never touched.

### Manual nesting (drop a card ON another card)

The same drag can offer a second drop-target type: dropping card A onto card B
(both in Working) nests A under B directly — the user does the merge without
waiting for the grouper's opinion.

    {type: "cardNest", sid, childId, parentId}

Judge-side this reuses `apply_group`'s relink guts with the user license
(everDone guard lifted, cycle guard and depth clamp kept). It is stable
against the judges: the grouper only ever groups, it never un-nests, so a
user nesting is permanent until the user clears or the tree completes. UI:
column background = recategorize, card body = nest; distinct hover cues.

## Build order

1. `user_move` + `userMovedAt` + `_done_is_stale` in bin/romp-judge; `cardMove`
   handler in bin/romp-kernel. Tests: reopen-drag not re-completed by a stale
   closer verdict; unblock-drag not re-blocked by a stale planner verdict;
   sort lands at Working-bottom (extend feed-sort/followup-move tests).
2. Card action buttons invoking the op (works on touch; proves semantics).
3. `regroupOk` license + grouper guard change. Test: everDone top with
   `regroupOk` gets grouped; without it, untouched.
4. Desktop drag gesture (column targets) with render-deferral during drag.
5. `cardNest` (drop-on-card) last — separate op, separate tests.

## What shipped (2026-07-06, the user's decisions)

Steps 1-3 above, built with three decisions that amend the body:

- **No new `userMovedAt` field — `followupAt` is THE user-action stamp.** The
  chip concern that motivated a separate field was misplaced: the "Followed
  up"/re-check styling keys on the `followupPending` FLAG, which `user_move`
  never sets. One stamp now drives the Working sort floor, `_block_is_stale`,
  and the new `_done_is_stale`, for follow-ups and moves alike.
- **The everDone grouper guard is REMOVED outright** ("let's try removing that
  rule and see how it works"), not gated behind a `regroupOk` license. The
  `allow_done` parameter went with it; the consolidator is unchanged in
  behavior (its candidates are all-completed by construction). `everDone`
  itself remains as stamped provenance, so reverting the experiment is one
  guard line.
- **Moving TO blocked/completed is ruled out**, not just deferred: blocked
  means needs-the-user (nobody demands of themselves), and Clear covers
  retiring a card.
- **Both the modal BUTTON and the desktop DRAG shipped** (button first, drag
  same day): "Move to Working" in the card modal footer (single-ask cards in
  needs-input/completed) is the touch path; the drag gesture is the desktop
  path over the same `cardMove` op. Drag affordances: the source card dims +
  dashes, the Working column outlines in accent while a drag is in flight, and
  a LANDING SLOT animates open at the column's BOTTOM — the honest landing
  spot, since the column auto-sorts by recency and the followupAt stamp lands
  the moved card last (the slot never follows the pointer pretending free
  placement exists). render() defers while a drag is in flight and flushes on
  dragend/drop (the timeline _pointerHeld pattern) — cards are reused DOM
  nodes, but a mid-drag reconcile would still cancel the browser drag.
  Step 5 (`cardNest`, drop-on-card manual nesting) stays future work.
- The completed→working path plants the "Reopened by the user" provisional
  stub only when the subtree would re-complete bottom-up, and never stacks a
  second stub. An untouched reopened card parks in Working as an orphaned
  working top — auto-nudge's existing territory.

Tests: `tests/test_judge_user_move.py` (judge semantics + staleness floors +
grouper), `ui/webview/feed-move-button.test.ts` (modal button + plain
optimistic move + kernel/judge source pins).
