# How a card gets its state

The state model, the "constitution": what moves a card, every chip it can
wear, and the edge-case rules. Current as of **2026-07-09**. Companions:
[judge-pipeline.md](judge-pipeline.md) (the diagram map) and
[judges.md](judges.md) (who the judges are); design history in
`design/judge-simplification-plan.md` (git history — the plan shipped and the
doc was removed).

## The five layers

1. **Raw logs** (romp only reads): the Claude Code transcript per session,
   the states log (working/waiting/idle), the postal log.
2. **The event model** (pure parse, recomputed, never stored): atoms become
   segments (one input + its work), segments become turns. Authors come
   from markers: human, romp injection, peer, system.
3. **The judges** (small LLM calls) annotate: the index tier writes
   captions and archives (text only); the triage tier maintains the one
   piece of moving state, the goal store.
4. **The goal store**: a tree of goal nodes per session. Each node's state
   lives in its **diary** (`log`), an append-only list of events
   `{ev_t, src, kind, why, seg, at}`. src is planner / closer / courier /
   nudge / interrupt / romp / user / agent (the grouper never judges);
   kind is done / block / reopen / unblock / clear / settle / dismiss.
   Markers: `msg` (a user message rides this reopen), `undo` (an
   undo-clear restore), `synth` (reconstructed by migration, never
   witnessed). `record_verdict()` is the only door: it gates, appends, and
   materializes the node's cached flags in one call. Every derived key
   (`nodeComplete`, `blocked`, `cleared`, `doneWhy`, `blockWhy`,
   `followupAt`, `followupPending`, `settledAt`, `settledDone`,
   `deltaSince`) is a cache the fold rewrites. The **write seam**: every
   node is a `GuardedNode`, and assigning a diary-owned key outside the
   diary/cache layer raises at the write site.
5. **The read side** (kernel `build_feed` to the browser): maps states to
   columns, adds live floors and chips, renders verbatim with short-lived
   optimistic predictions.

## The fold: how a diary becomes a state

Sort events by evidence time (`ev_t`; arrival `at` breaks ties) and replay:

- A `done` lands; a `block` lands; a `reopen`/`unblock` opens; a `clear`
  clears.
- **Snapshots**: provisional flips restore what they displaced. A `clear`
  snapshots the state it covers, and an undo-reopen restores it, so a
  cleared completed card comes back completed, never "open". A msg-reopen
  (the optimistic flip when you reply to a card) snapshots too, and a
  planner `dismiss` (the pivot verdict: that reply started its own thread)
  restores the original state and settle stamp.
- **Settle is an event** (the moment the card entered the Completed
  column). `settledAt`, `settledDone`, and `deltaSince` derive from it:
  the newest un-reopened settle is the column-entry stamp, and the settle
  a reopen ended becomes the delta boundary for the re-distilled takeaway.
- **Held**: an unanswered user reopen holds the node open; no bottom-up
  re-completion can overrule "I said this isn't done". If the reopen
  carried a message, the card also wears the "Followed up" chip. Any later
  judge/agent/romp event answers both.
- **The user floor**: a user event's time floors judge evidence. A judge
  `done` needs `ev_t >= floor` (equality lands: the resolving reply shares
  the stamp); a judge `block` needs `ev_t > floor` (equality voids: that
  block was computed from the very ask you answered).
- Replay-safe by construction: a stale verdict arriving late sorts into
  its historical place and loses. Shuffling a diary never changes its fold
  (property-tested).

## The tree, then the column

- A card is blocked if any open descendant is blocked. A parent is done if
  ruled done or all children are done; a parent's done shadows still-open
  sub-steps (display-resolved, reversibly: `rolledUp`).
- **Agent override**: an open item on the agent's own to-do list pins the
  card in Working over any judge done; releases the instant it's checked
  off.
- **Column ladder**: Cleared > Blocked > reply-in-flight (Working) >
  Completed-and-settled > Working. **Settled** means the ruled-done goal
  is no longer the session's focus (or the session closed). **Sticky**
  means once shown Completed, a mere re-touch cannot flap it back; only a
  real reopen does.
- Sorting inside columns is stamp-driven: newest at the bottom; a moved or
  reopened card lands at the bottom because its stamp is "now".

## What moves a card

Judge rulings at segment/turn end · your reply (any column; reopens
instantly, optimistically) · Move to Working (a reply without a message) ·
Clear / Undo clear · Resolve · the agent checking off its to-dos · a peer
completing delegated work (courier link-back) · a failed auto-nudge
(records a block) · the settle moment · the live floors below.

## Every chip, badge, and visual state

Column-forcing floors (live events, beat the stored state):

- **picker / approval**: the session is stopped right now on a question or
  permission prompt. Needs-you; a placeholder card is synthesized if no
  goal exists yet.
- **API error**: transient errors stay in Working with a Retry; a "prompt
  too long" error is on you, so Needs-you.
- **Parked handoff**: a message sent to a dead session becomes a Needs-you
  card (revive to deliver, or dismiss).

Chips on cards:

- **interrupted** (yellow): you stopped the session mid-turn and haven't
  spoken since; auto-nudge holds off until your next message. Yields to
  stalled.
- **stalled**: the one auto-nudge didn't resolve the goal; it is never
  re-asked, and the failure records a block (src `nudge`) so the card sits
  in Needs-you with this chip as the explanation. Yields once a real judge
  verdict takes over. Tooltip carries the nudge history.
- **re-judging** (dotted): you answered a soft-blocked card with a
  targeted reply; it de-urgents into Working pending the re-judge.
- **Re-judging swirl**: a plain thread reply is in flight on a blocked
  card; returns on its own if the judge holds the block.
- **awaiting**: waiting on dispatched/background/delegated work. A Working
  flavor, never Needs-you; only humans block.
- **waiting on peer**: an unanswered question out to a live peer.
- **from peer**: courier provenance; this goal was delegated in.
- **warning** (yellow, clickable): a judge stamped an anomaly (e.g. a
  cite-miss); click for detail.
- **working dot** before a session name: that session is working right
  now.
- **provisional ghost** (dim, dashed, "Analyzing:"): a live prompt the
  planner hasn't classified yet; replaced by the real card.
- **Followed up** (modal tree, per sub-node): that sub was optimistically
  reopened by a per-sub follow-up.
- **Group cards**: sibling goals minted by one typed turn fold into one
  card (worst member's column); umbrellas nest related tops
  (grouper/consolidator; reorganization only, never status).

Optimistic predictions are client-side and kernel-reconciled: a
follow-up/move flips the card instantly; if the kernel doesn't confirm
within a beat it reverts with a toast, never silently.

## Edge-case rules

1. Authority: user > agent > judges; newer evidence wins within a rank.
   The `>=` / `>` floor asymmetry above is deliberate and tested.
2. Only a human blocks. Peers, CI, builds, and agents mean Working.
3. Done resolves eagerly, blocking is conservative ("when in doubt,
   omit"); the error costs are asymmetric: a wrong done costs a glance, a
   wrong block costs an interrupt. Omit is not a dodge: a stalled omit
   escalates (nudge, forced resolution, block) in bounded steps.
4. Cleared is sealed forever; a follow-up to a cleared card becomes a
   fresh goal.
5. Every verdict goes through `record_verdict`. A reopen carries `unblock`
   events for blocked descendants and ancestors; every unblock is an
   event.
6. Reopens un-resolve only auto-rolled (`rolledUp`) children;
   genuinely-done leaves keep their state. Re-completions re-summarize
   only the new stretch (`deltaSince`).
7. Identity: identical prompts in different turns are different work
   (twins); same-second identical bursts plan once; any seg-id-derivation
   change ships a placements migration (`placementsV`, at v2 since
   2026-07-09, when an unbumped hash change replayed cleared cards;
   `tests/test_placements_canary.py` now pins the derivation).
8. The auto-nudge fires once per genuine stall, never re-arms off romp's
   own turns, is suppressed while interrupted, and its failure becomes a
   block.
9. Diaries are capped (`LOG_CAP` 64, oldest dropped, `logTrunc` marks it).
   Migrated (`synth`) events never fake timeline judging marks.
10. The migration window is closed: `migrate_all_stores` sweeps every
    live + archived store at kernel boot (idempotent). A node born in the
    diary era carries `"log": []` from birth; a verdict-flagged node with
    no diary is frozen, never derived-and-wiped, and surfaces loudly in
    judge-errors.jsonl. Retired flags (`everDone`, `logBorn`) are popped
    by the sweep.

## Open items

1. **P4, one resolver?** The eager-done sampler (`eager-done-samples.jsonl`,
   focusHeld rate) decides whether the closer absorbs the planner's
   done/block (~40% fewer triage calls) or both stay. Review with a few
   weeks of data (snoozed to ~2026-07-14).
2. **Re-run the failure-rate numbers (decide ~July 16+).** The 2026-07-09
   failure contract made judge-errors.jsonl trustworthy for the first time:
   one name per prompt in both logs, call vs parse attributed correctly
   (error envelopes can no longer masquerade as parse failures), and every
   row carries its evidence. Rows before 07-09 conflate all of that, so
   per-judge failure rates computed over them mislead. After a week of
   normal use: tally rows per judge and kind against judge-usage.jsonl call
   counts (ask any session). Expect well under 1% genuine parse rejects per
   judge; a judge sitting meaningfully above that now has inspectable
   evidence (reply tails, `romp --debug on` captures) — fix its prompt or
   parser. Give-up rows should be near zero; any cluster means a cap is
   too tight or a prompt drifted.
3. Dated cleanups: order-audit instrumentation (~Aug 2026), the eager-done
   sampler after P4's call, the boot sweep once judge-errors.jsonl shows no
   unmigrated-node lines for a few weeks.
