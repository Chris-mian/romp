# Simplifying the judge layer — a measured plan

2026-07-06. Companion to `docs/judges.md` (what the judges are today). The user's ask: is the
system's complication masking a simpler model underneath — and if so, what's the concrete path
that doesn't break existing behavior?

## Diagnosis

The seven judges themselves are fine: each is one small prompt with one job, and the history is
clear that DECOMPOSED prompts beat the old fused ones. The complexity lives in the **state model
underneath them**: a goal node carries ~16 mutable flags and stamps, mutated by five kinds of
writers (planner, closer, courier, kernel optimistic ops, user ops), reconciled by a precedence
ladder plus six healing passes plus two staleness floors — and every new feature adds a flag or a
floor. The 2026-07-06 "Move to Working" work was diagnostic: it required a second staleness floor
byte-similar to the first (`_done_is_stale` / `_block_is_stale`), which is the classic smell of a
missing abstraction. The same day's replay storm (4cdbe44 → 199118f) showed the other soft spot:
placement identity is parse-derived and unversioned, so any seg-id-derivation change silently
invalidates recorded state.

## Measurements (2026-07-06, live fleet; scripts run read-only against `$XDG_STATE_HOME/romp`)

**Verdict provenance** — who actually resolves goals:
- Archived history (4094 nodes): planner-positive dones **1946 (71%)** vs closer-backstop **793
  (29%)**. Live top-level cards: 18 planner vs 13 closer.
- Both resolvers are load-bearing. The closer is not a rarely-fired safety net; the planner is
  not redundant eagerness.

**Flag usage** (135 live stores, 291 nodes): nodeComplete 131, everDone 104, settledDone 46,
negComplete 35, blocked 29, negBlock 22, origin 22, settledAt 12, umbrella 11, cleared 9,
rolledUp 8, followupAt 2, followupPending 1, agentTask 1, warns 1, deltaSince 1.
The long tail is telling: most special-case flags are ALMOST NEVER live at once, yet each one is
permanent code — a write site, a rollup branch, a healing rule, and a test surface.

**Reopens are a hot path, not an edge case**: 391 lifetime `reopen-done` events (optimistic 183,
follow-up 55, delegation 35, nudge 1, untagged 117). The reopen/staleness machinery runs daily;
investment there pays.

**Call volume, 48h**: captioner 2250 + archiver 1759 (Haiku; 71% of all calls) — planner 738,
closer 543, distiller 231, grouper 145, courier 11 (Sonnet). Mean latency: planner 6.4s,
distiller 7.6s, courier 4.9s, closer 4.2s, grouper 3.7s.

**Failure rates, 48h** (judge-errors.jsonl):
- **Archiver: 1195 parse failures out of 1759 calls (68%)**, concentrated in 8 sessions,
  retrying every pass — the archiver has NO give-up cap (the distiller does: DISTILL_FAIL_CAP).
  This is the single largest waste in the pipeline right now.
- Block-brief writer: 80 call failures + 25 give-ups + 41 cite-misses.
- Planner parse 5% (38/738), closer parse 4% (22/543) — healthy.

## The plan

### Phase 0 — quick wins the measurements exposed (small, independent, do first)
- **0a. Archiver give-up + leniency.** Cap repeated parse failures per session (mirror
  DISTILL_FAIL_CAP's escape hatch) and make `_parse_archive` tolerant of the actual Haiku drift
  (inspect the 8 failing sessions' outputs first — fix the cause, cap as the backstop). Kills
  ~1200 wasted calls/48h.
- **0b. Brief-writer failures.** Diagnose the 80 call-fails (timeout? size?); same give-up
  hygiene.

### Phase 1 — one arbitration seam (no behavior change)
The authority policy — **user > agent's own to-do list > judges; within a rank, newer evidence
beats older** — is real but scattered: two staleness floors at four call sites, view-clear seals
in five places, the agentTask override inside rollup, optimistic-vs-official reopen rules.
Introduce ONE gate:

    may_apply(store, node, source, verdict, evidence_t) -> bool

Every writer (apply_plan, apply_close, courier, user_move, optimistic_followup, propagate) asks
it before setting a flag. The ladder gets stated once, tested once. New writers inherit it
instead of remembering N floors (the failure mode "Move to Working" nearly shipped with). Pure
refactor: existing tests must pass unchanged.

### Phase 2 — placement identity hardening (the replay-storm lesson)
Placements are keyed by parse-derived seg ids with no version. Add `placementsV` to the store and
a deploy-time rule: any change to seg-id derivation (t or text hash) ships with a
seal-or-migrate sweep (like the caption cache's v4→v5 bump), plus the twin-burst regression
suite (tests/test_judge_retry_burst.py) as the gatekeeper. Institutionalizes 199118f.

### Phase 3 — the simpler model underneath: a per-node verdict log
The event-based model the flags are approximating. Each node accrues append-only verdict events:

    {source: planner|closer|courier|user|agent, kind: done|reopen|block|unblock|clear,
     ev_t, why}

and status = a pure fold over the log ordered by (authority rank, evidence time). Migration is
incremental and safe:
1. **Dual-write** (flags stay authoritative; every flag write also appends its verdict event).
2. **Shadow fold**: compute status from the log alongside `rollup_status`; log every divergence
   on the live fleet until quiet.
3. **Flip**: rollup becomes the fold; flags remain as a materialized cache for the read side.
4. **Retire heals one at a time** — moot-block heal, followupPending-deadlock heal, roll-down
   orphan heal each become properties of the fold rather than repair passes.

What dissolves: both staleness floors (an old-evidence verdict simply loses the fold — replay
becomes naturally idempotent, which also shrinks the Phase-2 blast radius), most derived flags
(everDone/settledDone/followupPending are questions you ask the log), and the debugging
side-channels (negComplete, `by=` diag tags, nudge-diag.jsonl) — the log IS the audit trail.
Given reopens run ~daily (391 events), this machinery is exercised enough to justify the build.

### Phase 4 — resolver consolidation, ONLY if the A/B says so
The tempting cut — demote the planner to placement-only and let the closer own done/block — is
NOT supported by default: the planner lands 71% of dones first. The honest question is whether
that eagerness ever reaches the USER earlier (the settled gate usually delays display to
turn-end anyway; the exception is non-focus tops completing mid-turn). The closer's existing
`samples` A/B hook can measure exactly that: log, for each planner-done, whether display would
have waited for turn-end anyway. If eagerness almost never shows, consolidating saves ~40% of
triage Sonnet calls (738+543 → ~740) and deletes the negComplete/negBlock provenance split; if
it shows, keep both — they're cheap enough.

### Non-goals
- **No prompt re-fusing** (decomposed-from-fused is settled history; quality dropped fused).
- **No index-tier redesign** beyond 0a — cheap, working, and 71% of volume is fine to leave.
- **Grouper/consolidator** — already one prompt, two candidate sets; nothing to merge.

## Sequencing

0a/0b now (hours each). Phase 1 next (a day, pure refactor, big safety payoff). Phase 2 rides
the next judge change that touches parsing (the rule + version field are an hour; the sweep
script exists from the 199118f cleanup). Phase 3 is the real project (days, but each step is
shippable and reversible; the shadow-fold stage produces divergence data before any behavior
changes). Phase 4 waits for its measurement.
