# The summarizer layer: the engine and the judges

Internal design doc (not user-facing). The layer above the event model
(`design/event-model.md`): it attaches *meaning* to the event tree so the read side
has something worth showing. Working units are the **segment** and the **turn**
(both first-class). Built fresh as a new module beside the existing
`bin/romp-summarize-backfill`, which stays until the new one is proven. Started
2026-06-13; current as of 2026-06-14.

**judges** is the generic class for the model calls in this layer. There are three:
the **captioner**, the **planner**, and the **courier**.

Build philosophy: start with the smallest judge that delivers value (the captioner
alone), run it on the real fleet, and add each further judge one at a time, keeping
it only when it proves useful. No correction tier, no measurement scaffolding, no
tmux, until something concrete demands it.

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
  - **Completion is two-layer:** the planner marks a node complete when its *direct*
    work discharges it (explicit, per node, the only completion the judges emit);
    the higher feed layer derives a goal's completion by **rollup** (all sub-nodes
    complete) **gated by the kept "settled" heuristic** (nothing live still working
    it). The settled gate is what keeps accreting sub-goals from completing a goal
    prematurely. No separate "the whole goal is done" judge-mark.
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

- **captioner** (live) — per segment, and a per-turn variant.
  - In: one segment (trigger + work atoms); the turn variant gets the whole turn.
  - Out: a caption.
  - Prompt sketch: "Here is one segment of a coding session, what the user said and
    what the assistant did. In ≤8 words, past tense, say what the assistant
    accomplished. Lead with the result; never name a tool."
- **planner** (next) — every segment; places it in the goal tree.
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
- **courier** (later) — peer-message segments.
  - In: the peer message + the **sender's** open goals (numbered).
  - Out: **propagating** (carries sender-goal #N forward) or **FYI**; plants a goal in
    the recipient's tree that the planner then works under.
  - Prompt sketch: "One session messaged another. Handing off work or just FYI? Which
    of the sender's goals does it carry forward?"

Writers (not judges; deferred): the expand-paragraph and the session digest.

## The records it writes

- **captions** — one per segment/turn, keyed by id. This is the new `summaries/`.
  Peer-message captions live here too, keyed by the message/segment id.
- **the goal tree** — nodes (goals/sub-goals/steps), edges (parent/child), per-node
  completion marks; folded with the kept settled-heuristic for goal-level status.
- No `decision-log`, no `corrections`, no `message-summaries` sidecar.

## The increments (build order)

Each step: build it, run it on the fleet, look at the output, keep it only if it
earns its place.

1. **captioner** — a caption per segment and per turn. Goal 1.
2. **planner** — place every segment in the goal tree (mint / sub-goal / amend /
   complete), with the inbox = top-level goals and per-node completion. Goals 2 + 3.
   The candidate menus and global time-order processing arrive here.
3. **courier** — handoffs (propagating / FYI + sender goal). Goal 4.
4. **writers** — expand paragraph, session digest. Goal 5.

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
- **the "settled" heuristic's exact definition** (kept from the old higher layer): the
  liveness condition that gates goal-level completion. Tune when the planner is in.
- **un-block lag on answers:** a blocked goal un-blocks a beat after you answer (when
  the follow-on work files under it). Fine; the planner can attribute the
  answer-segment itself if the lag ever bothers us.
- **re-fusing the judges** into single calls later, once we know which are load-bearing.
- **whether the courier folds into the planner** later.
- **session → files** (deferred, higher layer): resumed sessions don't link forks via
  `parentUuid`; lean an explicit `rompUuid → fork files` registry. Needed before
  resumed history stitches; not for the captioner.
