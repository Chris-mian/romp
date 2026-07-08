# How a card gets its state — the diary, the fold, the ladder, the chips

Current as of **2026-07-07 (evening)**, after the verdict-log flip (P3.3), the dead-path audit,
the straggler fold-in (settle/chip/stubs), the migration-window close, and the write seam. Companion
to `docs/judges.md` (who the judges are); the design history lives in
`design/judge-simplification-plan.md`. This is the working reference for the STATE MODEL: what
moves a card, every chip it can wear, and the edge-case rules — the "constitution."

## The five layers

1. **Raw logs** (romp only reads): the Claude Code transcript per session, the states log
   (working/waiting/idle), the postal log.
2. **The event model** (pure parse, recomputed, never stored): atoms → segments (one input + its
   work) → turns. Authors detected from markers (human / romp-injection / peer / system).
3. **The judges** (small LLM calls) annotate: the index tier writes captions/archives (text only);
   the triage tier maintains the ONE piece of moving state — the goal store.
4. **The goal store**: a tree of goal nodes per session. Since 2026-07-06 each node's verdict
   state lives in its **DIARY** (`log`): an append-only list of events
   `{ev_t, src, kind, why, seg, at}` — src ∈ planner/closer/courier/grouper/nudge/interrupt/
   romp/user/agent, kind ∈ done/block/reopen/unblock/clear/settle/dismiss. Event markers:
   `msg` (a user message rides this reopen — the chip), `undo` (an undo-clear restore, asserts
   nothing about doneness), `synth` (reconstructed by migration, never witnessed).
   `record_verdict()` is the ONLY door: it gates (may_apply), appends, and MATERIALIZES the
   node's cache in one call — callers write no flags at all. Every derived key — `nodeComplete`/
   `blocked`/`cleared`, `doneWhy`/`blockWhy`, `followupAt`, `followupPending`, `settledAt`/
   `settledDone`, `deltaSince` — is a cache the fold rewrites. **The write seam** (2026-07-07):
   every node is a `GuardedNode`; assigning any diary-owned key outside the diary/cache layer
   RAISES at the write site. Bypassing the diary is structurally impossible, not just corrected.
5. **The read side** (kernel `build_feed` → the browser): maps states to columns, adds live
   floors and chips, renders verbatim with short-lived optimistic predictions.

## The fold (how a diary becomes a state)

Sort events by evidence time (`ev_t`; arrival `at` breaks ties) and replay:
- a `done` lands; a `block` lands; a `reopen`/`unblock` opens; a `clear` clears.
- **Snapshots (provisional flips restore what they displaced):** a `clear` snapshots the state
  it covers, and an `undo`-reopen restores it — a cleared COMPLETED card comes back completed,
  never "open". A `msg`-reopen (romp's optimistic flip when you reply to a card) snapshots too,
  and a planner `dismiss` (the pivot verdict: "that reply started its own thread") restores it —
  a pivoted completed card returns to Completed with its ORIGINAL settledAt.
- **`settle` is an event** (when the card entered the Completed column); `settledAt`/
  `settledDone`/`deltaSince` derive from it: the newest un-reopened settle is the column-entry
  stamp; the settle a reopen ended becomes the delta boundary for the re-distilled takeaway.
- **held / pending:** an unanswered USER reopen HOLDS the node open (no bottom-up re-completion
  can overrule "I said this isn't done") — this replaced the provisional stub node; if the
  reopen carried a message (`msg`) the card also wears the "Followed up" chip. ANY later
  judge/agent/romp event answers both — the moment the reply is actually processed.
- **The user floor**: a user event's time floors judge evidence — a judge `done` needs
  `ev_t >= floor` (equality LANDS: the resolving reply shares the stamp), a judge `block` needs
  `ev_t > floor` (equality VOIDS: that block was computed from the very ask the user answered).
  User/agent events are never floored (ordering alone decides).
- Replay-safe by construction: a stale verdict arriving late sorts into its historical place and
  loses. Shuffling a diary never changes its fold (property-tested).

## The tree, then the column

- Card blocked if ANY open descendant is blocked; parent done if ruled done or all children done;
  a parent's done shadows still-open sub-steps (display-resolved, reversibly — `rolledUp`).
- **Agent override**: an open item on the agent's OWN to-do list pins the card in Working over
  any judge done; releases the instant it's checked off.
- **Column ladder**: Cleared > Blocked > reply-in-flight (Working) > Completed-AND-settled >
  Working. **Settled** = the ruled-done goal is no longer the session's focus (or the session
  closed); **sticky** = once shown Completed, a mere re-touch (a status question, a mention)
  can't flap it back — only a real reopen does.
- Sorting inside columns is stamp-driven: newest at the bottom; a moved/reopened card lands at
  the bottom because its stamp is "now".

## What moves a card (the complete event list)

Judge rulings at segment/turn end · your reply (any column — reopens instantly, optimistically)
· Move to Working (button or drag; a reply-without-a-message) · Clear / Undo clear · the agent
checking off its to-dos · a peer completing delegated work (courier link-back) · a failed
auto-nudge (records a block — see stalled) · the settle moment · live floors (below).

## Every chip / badge / visual state

**Column-forcing floors (live events, beat the stored state):**
- **⏸ picker / approval** — the session is stopped RIGHT NOW on a question/permission prompt →
  Needs-you (a placeholder card is synthesized if no goal exists yet).
- **⚠ API error** — transient: stays in Working with a Retry; a "prompt too long" error IS on
  you → Needs-you.
- **Parked handoff** — a message sent to a dead session → a Needs-you card (revive to deliver,
  or dismiss).

**Chips on cards:**
- **"interrupted"** (yellow) — you stopped the session mid-turn and haven't spoken since;
  auto-nudge holds off until your next message. Yields to "stalled".
- **"stalled"** — the one auto-nudge didn't resolve the goal; per the anti-loop rule it is never
  re-asked, and (2026-07-07) the failure records a block verdict (src `nudge`) so the card sits
  in Needs-you with this chip as the explanation. The chip yields once a REAL judge verdict
  takes the story over (diary-keyed). Tooltip carries the nudge history (count + times).
- **"↩ re-judging"** (recheck) — you answered a soft-blocked card with a TARGETED reply → it
  de-urgents (dotted, out of the needs-you tally) into Working pending the re-judge.
- **"Re-judging…" swirl** (rejudging) — a PLAIN thread reply is in flight on a blocked card →
  Working while the reply's echo/turn is open; returns on its own if the judge holds the block.
- **⏳ awaiting** — waiting on dispatched/background/delegated work; a Working flavor, never
  Needs-you (only humans block).
- **"waiting on <peer>"** — an unanswered QUESTION out to a live peer.
- **"↪ from <peer>"** — courier provenance: this goal was delegated in by a peer's message.
- **warning** (yellow, clickable) — a judge stamped an anomaly (e.g. a distiller cite-miss);
  click for detail.
- **working dot** before a session name — that session is working right now.
- **provisional ghost** (dim, dashed, "Analyzing: …") — a live prompt the planner hasn't
  classified yet; replaced by the real card.
- **"↻ Followed up"** (modal tree, per sub-node) — that sub was optimistically reopened by a
  per-sub follow-up.
- **Group cards** — N sibling goals minted by one typed turn fold into one card (worst member's
  column); umbrellas nest related tops (grouper/consolidator; reorganization only, never status).

**Optimistic predictions (client-side, kernel reconciles):** a follow-up/move flips the card
instantly; if the kernel doesn't confirm within a beat it reverts WITH a toast (never silent).
Clear/undo are likewise optimistic with caches.

## Edge-case rules (the constitution's fine print)

1. Authority: user > agent > judges; newer evidence wins within a rank; the `<`/`>=` boundary
   asymmetry above is deliberate and tested.
2. Only a human blocks. Peers/CI/builds/agents = Working (⏳/waiting-on chips).
3. Done resolves eagerly, blocking is conservative ("when in doubt, omit") — error costs are
   asymmetric: a wrong done costs a glance; a wrong block costs an interrupt. Omit ≠ dodge:
   a stalled omit escalates (nudge → forced resolution → block) in bounded steps.
4. Cleared is sealed forever; a follow-up to a cleared card becomes a FRESH goal.
5. Every verdict goes through `record_verdict` (gate + diary + materialize in one call). A
   reopen carries `unblock` events for blocked descendants/ancestors — every unblock is an
   event (user_move, _mark_node_done's discharge, the moot-block heal, the interrupt lift).
6. Reopens un-resolve only auto-rolled (`rolledUp`) children; genuinely-done leaves keep their
   state. Re-completions re-summarize only the NEW stretch (deltaSince).
7. Identity: identical prompts in different turns are different work (twins); same-second
   identical bursts plan once; any seg-id-derivation change ships a placements migration
   (`placementsV`).
8. The auto-nudge fires once per genuine stall, never re-arms off romp's own turns, is
   suppressed while "interrupted", and its failure becomes a block (see stalled).
9. Diaries are capped (LOG_CAP 64, oldest dropped, `logTrunc` marks it). Migrated (synth)
   events are tagged and never fake timeline judging marks.
10. The migration window is CLOSED (2026-07-07): `migrate_all_stores` sweeps every live +
   archived store at kernel boot (idempotent; adopts legacy flags as synth events, deletes
   stub nodes, strips `logBorn`). A node born in the diary era carries `"log": []` from birth —
   the diary key IS the era marker. A verdict-flagged node with NO diary is frozen, never
   derived-and-wiped, and surfaces loudly in judge-errors.jsonl.

## Known targets to improve next (in rough priority)

DONE 2026-07-07 (same-day follow-through): the write seam (GuardedNode — a rogue write raises
at the offending line), the straggler fold-in (settle events, the derived chip, stub-node
retirement, evented subtree unblocks), and the migration-window close (boot sweep; `logBorn`,
`_backfill_log`-in-hot-paths, and the everDone hot reads deleted). Riders found by the seam:
the modal's user Resolve was a silent no-op since the flip; a pivot now records `dismiss`; an
undo-clear restores the pre-clear state by snapshot.

DONE 2026-07-07 (late evening): rate-limit-aware judging (the `_judge_run` gate skips every
judge LLM call while a usage window is exhausted — self-expiring via resets_at, skips never
count as failures), the chat + timeline payload audits (bullets/current-subfields/auth/recent
flags/apiError.category/askAnswer.multiSelect off the chat contract; backend/compactPct/
pendingMail/stale lanes, nudge/mids/reply bars, parked/toGoal/fromOrig connectors, the whole
nudges array + tokens off the timeline contract; the in-chat ledger's dead reader functions and
19 orphaned CSS rules removed), and `_seg_key` unified (the kernel delegates to the judge's).

1. **P4 — one resolver?** The eager-done sampler (`eager-done-samples.jsonl`, focusHeld rate)
   decides whether the closer absorbs the planner's done/block (~40% fewer triage calls) or
   both stay. Review with a few weeks of data (snoozed to ~2026-07-14).
2. Dated cleanups: order-audit instrumentation (~Aug 2026), the eager-done sampler after P4's
   call, the boot sweep itself once judge-errors.jsonl shows no unmigrated-node lines for a
   few weeks.
