# Simplifying the judge layer — the comprehensive plan

2026-07-06 (v2, supersedes the same-day v1 sketch; approved direction: "store the history,
derive the conclusions"). Companion docs: `docs/judges.md` (what the judges are),
`design/feed-card-drag.md` (the user-action machinery that motivated this).

## The thesis

The goal store keeps only CONCLUSIONS (mutable flags) about a history it throws away, so it
needs guards before every write and heals after — machinery that exists only to compensate for
the missing history, re-implemented per write site, exercised daily (reopens ~daily; two of its
bugs cost an afternoon on 2026-07-06). The plan: store the history per node (an append-only
VERDICT LOG), derive the conclusions with one fold, and delete the compensation machinery as it
becomes redundant. The judges' prompts, cadence, and the read side do not change.

Non-goals, permanently out of scope here: prompt re-fusing (decomposed prompts beat the old
fused ones — settled), index-tier redesign beyond the Phase-0 bug, any change to columns /
sorting / feed semantics.

## Current-state inventory (what exists and why)

### The flag zoo — and each flag's disposition

Every flag is a hand-maintained cache of one question about lost history. Live counts from the
2026-07-06 fleet scan (291 live nodes / 4094 archived) in parentheses.

| Flag | Caches the question | Disposition |
|---|---|---|
| `nodeComplete` (131) | done verdict with no reopen since? | KEPT as materialized cache of the fold |
| `blocked` (29) | block verdict with no answer since? | KEPT as materialized cache of the fold |
| `cleared` (9) | user crossed it off? | KEPT (kernel-owned; also a `clear` event for audit) |
| `everDone` (104) | ever done, at any point? | ELIMINATED → derived ("any done in log") |
| `settledDone` (46) | completion displayed once (anti-flicker)? | KEPT in v1 (settle stays code); revisit in P3.4 |
| `settledAt` (12) | when it entered Completed (sort) | KEPT (display stamp, not a verdict) |
| `negComplete`/`negBlock` (35/22) | which judge said it? | ELIMINATED → the event's `source` field |
| `followupAt` (2) | user's last action time | ELIMINATED → the latest user event's `ev_t` |
| `followupPending` (1) | user reply in flight, unjudged? | ELIMINATED → derived ("latest = user reopen, no judge verdict after") |
| `rolledUp` (8) | child closed by parent, not on merits? | ELIMINATED → parent-done SHADOWS open children in the fold; reopen unshadows |
| `deltaSince` (1) | where the prior episode ended | ELIMINATED → derived (previous done→reopen pair's `ev_t`) |
| `doneWhy`/`blockWhy` | rationale text | MOVED into the event (`why`); read side keeps seeing them via the cache |
| `agentTask` (1) | agent's own to-do mirror | KEPT — a live overlay input to the fold, not an event (it self-heals from the agent's store) |
| `provisional` (stubs) | optimistic open placeholder | ELIMINATED in P3.4 — a user `reopen` event holds the top open in the fold, no stub node needed |
| `warns`, `summary`, `blockSummary`, `background`, `summaryAnchor`, `retitle` | distiller/display artifacts | KEPT — content, not state |
| `umbrella`, `origin`, `promptUuid`, `quote`, `trail`, `t`, `mt` | structure/anchors | KEPT — tree shape and provenance, not verdicts |

### The referee machinery — and each piece's disposition

| Mechanism | Job today | Disposition |
|---|---|---|
| `_block_is_stale` (2 sites) | void replayed block vs user action | ELIMINATED — ordering is inherent in the fold |
| `_done_is_stale` (2 sites) | void replayed done vs user action | ELIMINATED — same; the `<`-vs-`<=` boundary becomes ONE tie rule in the fold |
| view-clear checks (5 sites) | user's cross-off seals everything | COMBINED into `may_apply` (P1), then the fold's top authority rank (P3) |
| `agentTask` authority (in rollup) | agent's open to-do forces working | COMBINED into the fold's rank order |
| moot-block heal | drop stale block on completed subtree | ELIMINATED — can't occur under the fold |
| followupPending-deadlock heal | drop stranded optimistic chip | ELIMINATED — the derived value can't strand |
| roll-down heal + `_reopen`'s un-resolve | close children under a done parent, reversibly | ELIMINATED — shadowing (see below) |
| sticky completion (`settledDone`) | anti-flicker | KEPT in v1 |
| `_reopen` | the multi-flag reopen dance | SHRINKS to "append a reopen event" + the P3.4 leftovers |
| `_nudge_diag`, `by=` tags | reopen forensics | ELIMINATED — the log IS the audit trail |
| optimistic vs official reopen split | kernel acts now, judge confirms | ELIMINATED as a distinction — both are just events from different sources |

### Also eliminated/combined while we're in there (small, independent)

- Dead config: the removed fairness caps (`PLAN_FAIRNESS = None` etc., romp-judge:101-140) —
  delete the constants and the `[:None]` slices.
- `apply_group`'s legacy `everDone` backfill remnants and grouper-guard comments already stale
  after the 2026-07-06 rule removal.
- The judge's `_seg_key` and the kernel's twin copy: extract to one shared helper both load
  (they must never drift; today they are literal copies).
- Distiller's two prompts share their BACKGROUND/TAKEAWAY/SOURCE scaffolding as one template
  with a done/blocked insert (cosmetic; only if touching the distiller anyway).

## The verdict log design (Phase 3's target state)

Per node, append-only:

    {"ev_t": <evidence unix-s>, "src": "planner"|"closer"|"courier"|"user"|"agent",
     "kind": "done"|"reopen"|"block"|"unblock"|"clear", "why": "...",
     "at": <wall-clock appended>, "seg": <segment id, when judge-derived>}

`ev_t` is EVIDENCE time (the segment/turn/user-action moment); `at` is arrival time, kept for
forensics only. The fold, per node:

1. Order events by (authority rank: user > agent > judge), then `ev_t`, then `at` as the tie
   break — the old per-guard `<`/`<=` asymmetry becomes this ONE explicitly-tested tie rule.
2. The latest-winning verdict determines the node's own state (open / done / blocked).
3. Parent shadowing: a top's `done` shadows its OPEN descendants for rollup purposes (they
   count complete without ever being written); a later `reopen` on the top unshadows exactly
   them. Replaces the roll-down/rolledUp write-remember-unwrite cycle.
4. Tree rollup (bottom-up completeness, any-blocked, the settled gate, ladder precedence) is
   UNCHANGED code operating on fold outputs instead of raw flags.

Kept OUTSIDE the log, deliberately: settledness (a function of session focus at read time,
plus the settledAt/settledDone display stamps), the agentTask overlay (a live mirror of the
agent's own store — it self-corrects, so freezing it into events would be wrong), and
view-clear's authoritative copy (cleared.jsonl, kernel-owned). The fold consumes all three as
inputs alongside the log.

## Experiments — test the assumptions against the store BEFORE building on them

Each phase has a gate experiment. E1-E3 and E7 are cheap read-only scripts over
`$XDG_STATE_HOME/romp` (the pattern used for the 2026-07-06 fleet scan); E2/E4/E6 are
instrumentation riding existing logs.

- **E1 (gates P1) — write-site census.** Static inventory of every site that writes each
  verdict flag and every guard call. Assumption tested: the may_apply seam covers ALL writers
  (miss one and the seam is a lie). Output: a checklist table in the P1 change.
- **E2 (gates P3 scope) — heal-fire telemetry.** A JSONL counter line per heal firing (which
  heal, which store); run the fleet ~1 week. Assumption tested: "the heals exist for
  flag-mutation races and dissolve under the fold" — if any heal fires for a reason the fold
  does NOT subsume, we learn it BEFORE deleting the heal, not after.
- **E3 (gates P3 design) — offline reconstruction dry run.** For every ARCHIVED store (4094
  nodes with known-final states): reconstruct a synthetic verdict log from the provenance that
  DID survive (nodeComplete/negComplete/everDone/mt/deltaSince), fold it, compare to the
  stored rollup verdicts. Assumption tested: the fold's rank + tie rules reproduce reality on
  historical data. Divergences are design feedback at zero live risk.
- **E4 (gates the P3 flip) — live shadow fold.** During dual-write, compute fold-status beside
  rollup_status on every producer pass; log every divergence with the node's log + flags. Flip
  only after N quiet days. The main safety gate.
- **E5 (gates P0a) — archiver failure autopsy.** Capture raw model output on the next parse
  failures in the 8 looping sessions (68% fail rate, 1195 calls/48h). Assumption tested:
  format drift fixable by parser leniency, vs. something pathological in those sessions'
  caption history (then the give-up cap alone is the fix).
- **E6 (gates P4; may never run) — planner-eagerness display benefit.** In the closer's
  existing `samples` hook, log for each planner-set done whether that goal was the session's
  active focus at verdict time (if yes, the settled gate delayed display to turn-end anyway —
  the closer would have delivered identical UX). Assumption tested: "eager dones reach the
  user earlier often enough to justify a second resolver" (the planner lands 71% of dones
  first, but firstness ≠ visible earliness). Only a clear "almost never" green-lights P4.
- **E7 (informs the P3.3 cache contract) — read-side flag census.** Which flags do
  build_feed/build_session actually read? The materialized cache exports exactly that set and
  nothing else. (Known so far: nodeComplete, blocked, cleared, followupPending, settledAt,
  followupAt, provisional, umbrella, warns, the summaries, origin.)

## Phasing — what ships at each step

Status 2026-07-06 night: P0a, P1, P2, E2, **P3.1 and P3.2** are SHIPPED. P0b closed by
diagnosis (the brief's call-fail bursts were account rate-limit windows — its give-up already
copes). E5: the archiver "parse" storm was the same outage mislabeled (call vs parse now logged
distinctly). E3 ran offline over 4118 archived nodes: the fold reproduced stored verdicts 99.6%,
with all 17 divergences in exactly the cases where reconstruction LOSES ordering (overwritten
mt, the block boundary) — which the live log records precisely; fold design validated.

P3.1 shipped as a FUSED seam (deviation from the sketch, deliberate): `record_verdict()` = gate
AND recorder in one call — a writer cannot pass the gate yet skip the history. All verdict
writers route through it (planner done/block, closer done/block, every _reopen flavor incl.
optimistic/user-move/delegation/nudge/followup, the agent-mirror done, propagate's link-back,
the umbrella housekeeping clear, and the kernel's user clear/undo). Events: {ev_t, src, kind,
why, seg, at}, per-node, LOG_CAP 64. P3.2: `_fold_node_state` (evidence-time ordering, arrival
tie-break, the user floor as ONE rule) + `_shadow_fold_check` in every rollup pass comparing
fold vs flags for logBorn tops (nodes minted post-dual-write, whose whole history is in the
log) → fold-divergence.jsonl is the E4 gate. The E6 eager-done sampler is armed.

**P3.3 SHIPPED same night (the user: "let's just go to the new one").** The shadow wait was
replaced by a stronger construction: every node self-migrates on first rollup touch
(_backfill_log synthesizes the minimal log whose fold equals its current flags, tagged synth),
then _materialize_from_log rewrites the flags from the fold every pass — the LOG IS THE
AUTHORITY; an out-of-band flag write is overwritten by history on the next pass. Proven against
the live fleet before deploy: all 136 stores' status maps byte-identical under the flip. The
shadow comparator was deleted (obsolete: fold and cache are definitionally in step now). The
flip surfaced and fixed two latent gaps: subtree/ancestor unblocks were EVENTLESS (user_move and
_reopen now record `unblock` events, added to the fold), and _reopen's default event time now
derives from the store's latest moment, never the wall clock. Tree-level machinery (roll-down,
settled/sticky, followupPending) remains as cache maintenance over fold states — that was
always its KEEP disposition.

**P3.4 DONE EARLY (the user 2026-07-07: "just do the cleanup now").** Retired: everDone and
negComplete/negBlock writes (the diary's src IS the provenance; the timeline's judging band now
reads verdict events directly — precise sources planner/closer/courier/grouper/nudge in every
event), the _nudge_diag/heal-fire side-logs (the diary is the audit trail), the dead
PLAN_FAIRNESS cap. _backfill_log still READS legacy everDone flags to reconstruct dormant
stores' history. Kept: the eager-done sampler (it gates P4, the one open decision) and the
tree-level cache maintenance (roll-down / settled / sticky / followupPending — display logic,
not old-system remnants). Rider fixes the same day: a FAILED AUTO-NUDGE now records a block
verdict (src "nudge") so the card moves to Needs-you through the normal ladder instead of
idling in Working with a chip (the user's rule), and the dead "reopened" chip was deleted
(unreachable since cleared-is-sealed, 2026-06-22).

**P3.4 CLOSED OUT 2026-07-07 evening (the user: stragglers + retirement + the write seam, all
same day).** Everything the table above marked ELIMINATED is now eliminated: followupPending/
followupAt/settledAt/settledDone/deltaSince/doneWhy/blockWhy all derive from the fold (`settle`
became an event; a `msg`-marked reopen drives the chip; an unanswered user reopen HOLDS the top
open — the provisional stub node is deleted); the migration window is closed (boot sweep
`migrate_all_stores`, logBorn retired — an empty `"log": []` at mint is the era marker; a
flagged no-diary node freezes loudly instead of deriving-and-wiping); and the ratchet got teeth:
every node is a `GuardedNode`, so a diary-owned key written outside record_verdict/the rollup
cache layer RAISES at the write site. record_verdict now materializes the node itself — callers
keep no flag mirrors. New event kinds from the close-out: `dismiss` (the pivot verdict restores
what the optimistic msg-reopen displaced) and `undo`-marked reopens (an undo-clear restores the
pre-clear state by snapshot). The seam immediately caught one real bug: the modal's user Resolve
had been a silent no-op since the flip (flags with no event, reverted by its own rollup).
Validated the same way as the flip: live-fleet copy, 139 stores, top-status byte-identical;
sweep idempotent (second pass rewrites 0).

- **P0 (hours):** 0a archiver give-up cap + parse fix per E5 (kills ~1200 wasted calls/48h);
  0b brief-writer failure triage (80 call-fails + 25 give-ups/48h).
- **P1 (a day):** E1 census → `may_apply(store, node, src, kind, ev_t)` encoding the whole
  ladder (user > agent > judges; newer evidence wins; view-clear seals) → every writer calls
  it → delete the scattered guard calls. Zero behavior change; existing suites pass untouched;
  new tests state the ladder once.
- **P2 (an hour + a standing rule):** `placementsV` schema version + the deploy rule: any
  seg-id-derivation change ships a seal-or-migrate sweep (the 199118f replay-storm lesson),
  gated by the twin-burst regression suite.
- **P3.1 (a day):** event append inside may_apply (dual-write; flags stay authoritative) + E2
  telemetry + the E3 offline report.
- **P3.2 (days, mostly waiting):** shadow fold + E4 divergence telemetry on the live fleet.
- **P3.3 (the flip):** the fold becomes authoritative; flags become the materialized cache
  (E7 contract); both staleness guards deleted; heals deleted one per change as E2 confirms
  each is silent.
- **P3.4 (follow-ups):** provisional stubs → reopen-event semantics; settledDone into the fold
  if the anti-flicker property provably holds; `_nudge_diag`/`by=` forensics removed; the
  dead-config sweep; the shared `_seg_key` helper.
- **P4 (only if E6 says so):** the planner sheds its done/block ops; the closer owns
  resolution and absorbs the nudge phase. Saves ~40% of triage Sonnet calls (planner 738 +
  closer 543 per 48h today). Parked until then — both resolvers are load-bearing on today's
  numbers.

## Ratchets — how it stays simple afterward

- A new "what happened before?" question is answered by a fold derivation, never a new flag
  (a flag addition to the store is a review red flag).
- A new writer goes through may_apply/the log; a lint test greps for direct verdict-flag
  writes outside the materialized-cache layer and fails on any.
- A seg-id-derivation change without a placements migration fails the P2 deploy rule.

## Success criteria

- **Bug-class removal:** replay/out-of-order writes cannot change board state (property test:
  shuffling a log never changes its fold).
- **Code removal:** both staleness guards, ≥3 heals, ≥6 flags, and the reopen forensics gone —
  a net-negative diff in bin/romp-judge by P3.4.
- **Behavior:** the E4 divergence log quiet; the full existing suites pass unchanged at every
  phase boundary.
- **Ops:** archiver error rate 68% → <2%; judge-errors.jsonl quiet enough that a new entry
  means something.
