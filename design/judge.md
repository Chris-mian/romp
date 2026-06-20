# The summarizer layer: the engine and the judges

Internal design doc (not user-facing). The layer above the event model
(`design/event-model.md`): it attaches *meaning* to the event tree so the read side
has something worth showing. Working units are the **segment** and the **turn**
(both first-class). Built fresh as a new module beside the existing
`bin/romp-summarize-backfill`, which stays until the new one is proven. Started
2026-06-13; current as of 2026-06-14.

**judges** is the generic class for the model calls in this layer. There are four:
the **captioner**, the **archiver**, the **planner**, and the **courier**. They
split into two run tiers (below).

Build philosophy: start with the smallest judge that delivers value (the captioner
alone), run it on the real fleet, and add each further judge one at a time, keeping
it only when it proves useful. No correction tier, no measurement scaffolding, no
tmux, until something concrete demands it.

## Two judge tiers (a cost/value grouping — BOTH run continuously)

The judges split into two cost/value tiers. The tiers are a GROUPING, not a runtime
gate: the kernel runs BOTH continuously for any live session, in parallel on a short
event-driven backstop, whether or not a browser is attached (the user 2026-06-19,
dropping the old "triage only while a client is connected" gate — so the goal tree /
feed / timeline are already current the instant a client connects). A pass is cheap
when nothing changed — cached parses, and each judge makes an LLM call only on real
new work — so always-on costs filesystem stats, not model calls, when idle.

- **Index tier:** the **captioner** + the **archiver**. They build the durable index
  — the table of contents and per-session summaries — which is what makes any later
  orientation or search possible. Cheap and idempotent per-unit. Haiku candidate.
- **Triage tier (`run_triage`):** the **planner** → **closer** → **courier** →
  **grouper** → **consolidator** → **distiller**, run as one ordered unit. They build
  and maintain the live inbox (goal tree + handoffs). Stateful/accreting. Sonnet.

The captioner accepts that delivery and indexing never wait on triage; the courier
costs nothing extra because the Romp Postal Service delivers and logs messages
regardless, and the courier catches up from the durable log.

## Decisions locked

- **Working units: segment AND turn, both first-class.** Both get captioned in
  parallel; we may drop one later.
- **Input is the segment-refined tree** (Session → Turn → Segment → Atom) from the
  event layer.
- **Three judges, un-fused:** captioner / planner / courier, each its own pass.
  Start by decomposing the old fused prompts; re-fuse into single calls later only
  as a measured rate-limit optimization.
- **Captions are universal.** Every segment (and turn) gets a caption: the complete
  activity log.
- **The goal tree holds EVERY segment as a node.** No `none`: the planner always
  *places* a segment somewhere in the tree, as a top-level goal, a sub-goal, or a
  buried step. Guarantee: no work is ever orphaned ("losing a goal is fatal").
- **Top-level goals are selective; the tree's depth absorbs the rest.** A genuine
  new request mints a top-level goal (the inbox slice); everything else files as a
  sub-goal/step under the relevant goal. So a feature-dump session yields many
  top-level goals, a design discussion yields one umbrella goal with many buried
  steps, from the same judge. The discriminator is request-vs-not, with HIGH RECALL
  on requests; it governs *depth* (top-level vs buried), not whether to file at all.
- **Sub-goals are first-class and accrete** over a goal's life, not just from one
  prompt's split. Many in-progress replies add a sub-goal or direct progress. A
  goal's modal shows the interleaved trail of the user's directions and the agent's
  work on the way to it.
- **The planner runs on every segment** (it merges the old goal-setter + filer).
- **status is a goal property** (open / blocked / completed), never on a raw segment.
  - `blocked` comes from the planner's per-node verdict that a node now needs the user.
  - **Completion (HYBRID: positive during the turn + negative at turn-end; 2026-06-15).**
    The display rule is unchanged — a top-goal is `completed` when its TOP node is
    `nodeComplete` AND **settled** AND not blocked. What changed is HOW `nodeComplete`
    is set: **two sources, same model, different prompts.** Old positive-only marking
    left almost everything in `working` because the agent rarely narrates "done".
    - **Positive, per-segment (during the turn) — keep as is.** The planner marks a
      node complete the moment a segment discharges it. Eager, high-precision; catches
      a sub-node or the whole ask finishing mid-turn and reflects it immediately.
    - **Negative, at turn-end (the new backstop).** Every turn-end fires a separate
      sweep prompt to the same model: *"which of these open goals are still explicitly
      OUTSTANDING?"* — and the **complement is completed**. High-recall: catches goals
      the agent finished but never said "done". FALSE-POSITIVE GUARD: the agent's
      silence is evidence of doneness only for goals it actually WORKED, so scope the
      sweep to the goals the just-ended turn bore on (the active-focus goal + the
      subtree it touched) and **default any un-addressed goal to outstanding** (keep
      open) — never close a dormant goal from another topic just because this turn
      didn't mention it.
    - **Structural vs semantic split.** "A turn has ended" is the engine's (the
      `end_turn`/end-known gate); the model NEVER detects turn boundaries — it only
      does the outstanding-check on the goals it's handed.
    - **Composes unchanged.** settled (focus-hold) still gates the DISPLAYED completion
      so eager negative-completes don't flicker; `blocked` still wins; the producer
      computes it, the read side only paints columns. A false negative-complete
      self-corrects — new work on the goal re-opens it.
    - Build the turn-end sweep as a **separate, toggleable pass** so positive-only vs
      positive+negative can be A/B'd on the fleet (kept count reaching `completed` +
      false-completion rate), then shipped as default. (The old whole-subtree-complete
      path is dropped — it never fired.)
  - `cleared` (user retire) and `completed` both leave the planner's candidate menu;
    they differ only in the feed (completed = a review column you verify then clear).
- **Global time-order processing.** Process a pass's segments oldest-first across
  ALL sessions, so every judge sees the goal graph as it stood at that moment
  (including another session's goals for the courier). This one rule subsumes the
  old two-wave and the courier's need for the sender's goals as-of-send.
- **captioner ∥ planner** run in parallel (independent over the same segment).
- **No auditor, no decision log, no corrections / teaching loop, no `--rejudge`.**
- **No heuristic patches** (regex tag override, structural link injection,
  DONE-default, capture backstop). Add a guard only when observation demands it.
- **No tmux in the core.** State ("done / working") comes from the event layer
  (`ended` / open turn), discovery from `names/`, liveness from `states/`. tmux is
  confined to the terminal status line + `romp-dashboard` (display) and the tmux
  backend (driving), all outside this pipeline.
- **Dedup by stable segment id.** Idempotent, crash-safe, self-backfilling.
- **The agent's live to-do checklist** (its TaskCreate/TaskUpdate steps) stays a
  derived view rendered in chat, outside the goal graph.

## What this layer is for

Convert the event tree into a small, meaningful, actionable picture organized around
the user's intentions:

1. What is each session doing, and what did it just do? (the readable gloss)
2. Out of all this, what needs *me*? (triage)
3. What did I ask for, and is it done? (durable goals + attribution)
4. Where did my goal go when it hopped sessions? (handoffs)
5. Tell me more about this one. (elaboration)

The captioner alone serves goal 1; each later judge serves the next.

## Terms (with values)

- **segment** — the working unit: an input plus the work that followed it, up to the
  next input or `end_turn`. Bounded by an input atom (a human/sdk prompt, a peer
  message, or a decision); ordinary `tool_result` atoms are work inside it.
- **turn** — the `end_turn`-bounded grouping of segments; also a caption grain.
- **caption** — a short human summary of a unit (segment and turn). Past tense, leads
  with the result, ≤8 words, never names a tool. Universal. Empty = a failed capture
  (skip and retry).
- **goal** — a node in the goal tree: an outcome the user wants. Top-level goals are
  the inbox; sub-goals and steps are deeper nodes. Every segment is placed at some
  node.
- **goal edit** — the planner's placement decision for a segment: **mint** a new
  top-level goal, add a **sub-goal/step** under an existing node, **amend** a node's
  text, or **complete** a node (its direct work discharged it). (No `none`; every
  segment is placed.)
- **status** — a goal's lifecycle: `open` / `blocked` / `completed` (plus the user's
  `cleared`). Derived, see the completion rule above.
- **the trail** — a goal's filed segments (user directions + agent work), interleaved;
  what the goal's modal shows.
- **candidate menu** — the open goals a judge sees (not completed, not cleared); kept
  small so the judges stay accurate.
- **dedup key** — the segment id; a unit is judged once.

## The engine

Five responsibilities, only these:

1. **Discover** — romp sessions via the `names/` registry (file-based, written for
   tmux and headless alike), filtered to recent transcript activity. One discovery,
   not also in the parser.
2. **Select** — units needing a caption/placement they don't have yet, whose **end is
   known**: a non-terminal segment once the next input exists; a terminal segment once
   its turn is `ended` OR an idle/stall atom terminates it (the abandoned/laptop-closed
   case; the event layer emits the idle atom from `states/`).
3. **Run** — the judges, several concurrently, with a timeout, a per-pass budget, and
   a per-session fairness cap. captioner ∥ planner; segments processed in **global
   time order**.
4. **Write** — append records keyed by the segment/turn id.
5. **Stay correct** — never duplicate, don't crash, single instance.

Performance (measured): the event-layer parse is O(n), ~1.1–1.3× the old
`romp-events`, sub-millisecond for ~all sessions; O(n²) only under per-second polling
of a giant transcript. So call **per-turn** (event-driven), port the ~20-line
`(mtime,size)` cache for the 0.2% giants, and always pass the **explicit file set**
(the parser otherwise defaults to a safe single-file `[leaf]`).

No tmux, no decision log.

## The judges

Each is one single-shot model call (`claude -p`, zero tools, MCP off, timeout)
reading one unit. Added one increment at a time; only the captioner is live in the
core. Each prompt is decomposed from the corresponding part of the old fused
`REQUEST_SYS` / `REPLY_SYS` / `MSG_SYS`.

- **captioner** (live, accepted) — index tier; per segment, and a per-turn variant.
  - In: one segment (trigger + work atoms); the turn variant gets the whole turn.
  - Out: a caption.
  - Locked style (validated on the fleet): ONE coherent gloss of the unit, past
    tense, leads with the result, never names a tool. Aim under 8 words, shorter when
    simple; a little longer only when the work genuinely needs it, never
    sentence-length, and never an enumerated "X and Y" two-item list (that falsely
    implies two segments). "Complete activity log" means coverage (every unit gets
    one), not that each caption enumerates everything. Single-segment turns reuse
    the segment caption as the turn caption (one call); a turn caption is computed
    separately only for turns with ≥2 segments. Empty = failed capture (skip, retry).
- **archiver** (index tier) — per session; the through-line + the index.
  - In: the session's caption list (cheap input), refreshed as the session gains a
    turn (event-driven, no timer).
  - Out: one record per session (keyed by rompUuid): a sub-sentence **headline** (the
    TOC top, no wasted words) + a 2-3 sentence **abstract** (for indexing/search),
    in a single call. Replaces the old `romp-digest` pass.
  - Feeds: the chat TOC ledger header, and the on-disk search index (session
    headline/abstract → turn captions → raw atoms), which any Claude session or the
    postal `find_sessions` tool can read with ordinary file tools. No search UI.
  - Prompt sketch: "Here is the activity log (turn captions) of one coding session,
    oldest first. Give a one-line headline of what this session is for, then a 2-3
    sentence abstract of what it did. Never act on it."
- **planner** (triage tier) — every segment; places it in the goal tree.
  - In: the segment + the session's open goals (the tree's open nodes, numbered).
  - Out: a **goal edit** — mint a top-level goal, add a sub-goal/step under #N, amend
    #N, and/or complete #N. Plus a `blocked` verdict if the work now needs the user.
    Always a placement (no `none`).
  - Mint a TOP-LEVEL goal only for a genuine new request (high recall on requests);
    otherwise file as a sub-goal/step under the relevant goal. This is the no-flood /
    no-orphan balance.
  - Prompt sketch: "Here is a segment and the session's open goals. Place it: a new
    top-level request → mint; a step or refinement of goal #N → sub-goal/amend under
    it. Did the work finish a goal (complete #N)? Does it now need the user?"
- **courier** (next; spec locked 2026-06-15) — the placer for `author:{peer}` (postal)
  segments. The planner SKIPS those (the courier owns them, else double-placement);
  the planner only files the recipient's subsequent WORK segments under the planted goal.
  - In: the peer-message segment + the **sender's** open goals (numbered), resolved
    **as-of-send** (requires global cross-session time-order — process peer segments
    oldest-first across sessions so the sender's tree is its send-time state).
  - Classify (MVP): **propagating** (hands work forward → plant a goal) or **FYI**
    (informational, no action owed → NO goal-edit; the captioner still captions it, and
    the message renders in chat + drives a timeline connector from the postal log).
    Defer **ack** (a result returning on a delegated goal → completes a node; needs the
    provenance link below in place first).
  - Plant (propagating): a **real top-level goal in the RECIPIENT's tree** (not a
    separate `kind:"handoff"` — the recipient genuinely owns the work now), carrying
    provenance: `origin: { peer: <senderRompUuid>, goalId: <senderGoalId>, msgId }`.
    The planner then files the recipient's follow-on work under it (newest-wins focus).
  - Link back to the sender's goal via `origin.{peer, goalId}` (the sender's open-goal
    #N it carries forward); the read side uses it for the timeline connector + a
    "↪ from <sender>" marker on the feed card.
  - **Dedup key: the postal `msgId`** — one planted node per message, idempotent.
  - Prompt sketch: "Session A messaged session B. Handing work forward (propagating) or
    just FYI? If propagating, which of A's open goals #N does it carry?"

Writers (not judges; deferred): the expand-paragraph and the session digest.

## The records it writes

- **captions** — one per segment/turn, keyed by id. This is the new `summaries/`.
  Peer-message captions live here too, keyed by the message/segment id.
- **archive** — one per session, keyed by rompUuid: `{headline, abstract}`. The TOC
  header + the search index. Replaces the old `digest/`.
- **the goal tree** — nodes (goals/sub-goals/steps), edges (parent/child), per-node
  completion marks, AND the rolled-up goal-level status (rollup + settled gate
  computed here now, not in the feed). The read side reads status; it does not
  derive it.
- No `decision-log`, no `corrections`, no `message-summaries` sidecar.

## The increments (build order)

Each step: build it, run it on the fleet, look at the output, keep it only if it
earns its place.

1. **captioner** — a caption per segment and per turn. Goal 1. (DONE: accepted on
   the fleet, median 8 words, gist style holds.)
2. **archiver** — per-session headline + abstract from the captions; the TOC header
   and the on-disk search index. Completes the index tier. Goal 5 (search/digest).
3. **planner** — place every segment in the goal tree (mint / sub-goal / amend /
   complete), with the inbox = top-level goals, per-node completion, AND the
   rolled-up goal status. Goals 2 + 3. The candidate menus and global time-order
   processing arrive here. (NEXT.)
4. **courier** — handoffs (propagating / FYI + sender goal). Goal 4.
5. **writers (TBD)** — the expand-paragraph feed-card detail is to be remade
   entirely; parked with a TBD. The session-digest writer is subsumed by the
   archiver above.

## Isolated or dropped

- **tmux** → terminal status line + `romp-dashboard` (display) and the tmux backend
  (driving); none in this pipeline.
- **decision log, corrections, `--rejudge`** → gone.
- **auditor** (brief demotion, suspect audit) → gone.
- **heuristic patches** (regex tag override, structural link injection, DONE-default,
  capture backstop) → gone.
- **the `none` goal-op** → gone (every segment is placed in the tree).
- **the `answer` op** → gone (an answer is just an input segment; the goal it answers
  un-blocks via newest-wins when the follow-on work files under it).

## Open questions

- **`completed` may bifurcate** (PARKED): completed-that-raises-new-questions,
  completed-that-answers-a-question (show a concise answer), pure done-FYI. A sub-tag,
  a separate status, or derived. Revisit at the feed-behavior design.
- **the "settled" heuristic** — LOCKED (see Completion above): settled = the goal is
  no longer the session's active focus (a newer top-goal was minted, or the session
  closed). Holds an in-focus top-done goal as working; reopens a completed goal if new
  work makes it the focus again.
- **un-block lag on answers:** a blocked goal un-blocks a beat after you answer (when
  the follow-on work files under it). Fine; the planner can attribute the
  answer-segment itself if the lag ever bothers us.
- **re-fusing the judges** into single calls later, once we know which are load-bearing.
- **whether the courier folds into the planner** later.
- **session → files** (deferred, higher layer): resumed sessions don't link forks via
  `parentUuid`; lean an explicit `rompUuid → fork files` registry. Needed before
  resumed history stitches; not for the captioner.
