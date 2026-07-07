# How a card gets its state — the diary, the fold, the ladder, the chips

Current as of **2026-07-07**, after the verdict-log flip (P3.3) and the dead-path audit. Companion
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
   `{ev_t, src, kind, why, seg, at}` — src ∈ planner/closer/courier/grouper/nudge/user/agent,
   kind ∈ done/block/reopen/unblock/clear. `record_verdict()` is the ONLY door: it gates
   (may_apply) and appends in one call. The old flags (`nodeComplete`/`blocked`/`cleared`) still
   exist but are a **materialized cache**: every rollup recomputes them from the diary's fold —
   a flag written without a diary event does not survive the next pass.
5. **The read side** (kernel `build_feed` → the browser): maps states to columns, adds live
   floors and chips, renders verbatim with short-lived optimistic predictions.

## The fold (how a diary becomes a state)

Sort events by evidence time (`ev_t`; arrival `at` breaks ties) and replay:
- a `done` lands; a `block` lands; a `reopen`/`unblock` opens; a `clear` clears (a later
  user reopen — undo — un-clears).
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
5. Every verdict goes through `record_verdict` (gate + diary in one call); it migrates a
   pre-flip node BEFORE appending (ordering bug 2026-07-07). A reopen must carry `unblock`
   events for blocked descendants/ancestors or materialization re-blocks them.
6. Reopens un-resolve only auto-rolled (`rolledUp`) children; genuinely-done leaves keep their
   state. Re-completions re-summarize only the NEW stretch (deltaSince).
7. Identity: identical prompts in different turns are different work (twins); same-second
   identical bursts plan once; any seg-id-derivation change ships a placements migration
   (`placementsV`).
8. The auto-nudge fires once per genuine stall, never re-arms off romp's own turns, is
   suppressed while "interrupted", and its failure becomes a block (see stalled).
9. Diaries are capped (LOG_CAP 64, oldest dropped, `logTrunc` marks it). Backfilled (synth)
   events are tagged and never fake timeline judging marks.

## Known targets to improve next (in rough priority)

1. **Make the stored flags non-load-bearing** (committed next step): sweep every reader onto a
   memoized fold accessor, then hand out read-only node views so a rogue write RAISES at the
   offending line instead of being silently corrected. The audit's reader census is the input.
2. **Retire the remaining derived-state stragglers** into the fold: `followupPending` (needs a
   "message-in-flight" marker distinct from a plain move), the provisional stub (a reopen event
   should hold the top open without a fake node), `settledDone/settledAt` (a `settle` event
   would make even display timing replayable).
3. **Close the migration window**: once every store's nodes carry `logBorn`, delete
   `_backfill_log`, the legacy `everDone` reads, and `logBorn` itself (sweep-then-delete).
4. **P4 — one resolver?** The eager-done sampler (`eager-done-samples.jsonl`, focusHeld rate)
   decides whether the closer absorbs the planner's done/block (~40% fewer triage calls) or
   both stay. Review with a few weeks of data.
5. **Rate-limit-aware judging**: an account-limit window burns retries fleet-wide (the archiver
   postmortem); one global gate — skip judge passes while `usage.json` says limited — would
   quiet every judge at once, event-based.
6. **Audit the other payload contracts**: this round only swept the FEED; the chat (render.ts)
   and timeline payloads deserve the same three-way audit — the feed found two dead subsystems,
   the priors are similar.
7. **Unify `_seg_key`** (judge + kernel carry literal copies that must never drift).
8. Dated cleanups: order-audit instrumentation (~Aug 2026), the eager-done sampler after P4's
   call.
