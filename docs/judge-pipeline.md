# The judge pipeline, in diagrams

A one-page audit map of how a session transcript becomes the board: what gets
parsed, which judges run in what order, what each one is given, and every state
a goal node can be in. Companion to [judges.md](judges.md) (prose, per-judge
detail) and [goal-state.md](goal-state.md) (the diary event model). Current as
of 2026-07-08 (card-first filing, the placer, the declared postal kind).

## 1. From transcript to placed work

Everything starts as a transcript line. Parsing slices it into turns, turns
into **segments** (one per trigger — a user message, a nudge, a peer message),
and each segment becomes one or two planner **units** keyed in `placements` so
no segment is ever judged twice.

```mermaid
flowchart TD
    TR["transcript .jsonl + states .jsonl"] --> EM["event-model parse<br/>(turns, atoms)"]
    EM --> SEG["segments — one per trigger:<br/>user message / nudge / peer mail / system"]
    SEG --> SEAM["settle-seam: work that continues after<br/>a goal closed splits into its own segment<br/>(planner told: wrap-up → skip, new thread → mint)"]
    SEG --> UNITS{"planner units<br/>(dedup keys in placements)"}
    SEAM --> UNITS
    UNITS -->|"user message lands, segment still open"| PRUN["PROMPT-run  (seg#p)<br/>message + open-goals tree<br/>exactly one op: mint or sub-on-a-card"]
    UNITS -->|"segment's work ended"| WRUN["WORK-run  (seg)<br/>whole segment + open-goals tree<br/>ops: mint / sub / done / block / retitle / skip"]
    UNITS -->|"user cleared the card mid-work"| LRUN["LIVE re-plan  (seg#live)<br/>fresh mint-or-sub so the board never blanks"]
    UNITS -->|"segment is a romp nudge"| NRUN["NUDGE resolution<br/>must resolve: done or block, no filler step"]
    UNITS -->|"segment is a postal delegation"| DRUN["DELEGATION filing  (seg#d)<br/>scoped under the courier-planted goal"]
```

## 2. Where a `sub` lands — card-first filing

The planner never picks a deep node. It picks the **card** (the top-level goal
you see on the board); a second, scoped call — the placer — picks the spot
inside, and only when there is a real choice to make.

```mermaid
flowchart TD
    OP["planner op"] -->|mint| MINT["new top-level card"]
    OP -->|"sub under #n"| WALK["walk #n up to its card<br/>(the model may only name cards;<br/>a deep pick is coerced up)"]
    WALK --> KIDS{"card has open<br/>sub-goals on the menu?"}
    KIDS -->|"no (common case)"| ATCARD["attach at the card — no second call"]
    KIDS -->|yes| PLACER["PLACER call: the card's open subtree only<br/>'file at the highest level that makes sense'"]
    PLACER -->|"picks a node"| ATNODE["attach there"]
    PLACER -->|"fails / nonsense"| ATCARD
    ATCARD --> GUARD{"echo/twin guard:<br/>exact same title as the parent<br/>or an OPEN sibling?"}
    ATNODE --> GUARD
    GUARD -->|"parent echo"| LANDP["lands ON the parent<br/>(trail evidence, no new node)"]
    GUARD -->|"open twin sibling"| LANDS["reuses that sibling's node"]
    GUARD -->|no| NEWN["new node (depth-capped at 4)"]
    MINT --> DIARY["every outcome = a diary event on the node"]
    LANDP --> DIARY
    LANDS --> DIARY
    NEWN --> DIARY
```

Prompt-run and live re-plan skip the placer (latency: the board should show
the ask instantly); the work-run refines depth when the work exists.

## 3. One triage pass — the judges in order

Two tiers run in parallel. The **index tier** (Haiku) only describes; the
**triage tier** (Sonnet) owns the goal board. Every LLM call passes one door,
`_judge_run`: rate-limit gate (skips while a usage window is exhausted,
self-expiring), per-judge usage logging, give-up counters that never count
skips.

```mermaid
flowchart LR
    subgraph INDEX["index tier (Haiku) — describes, never judges"]
        CAP["captioner<br/>per-turn captions"] --> GIS["gist<br/>topic of a new ask"] --> ARC["archiver<br/>headline + abstract"]
    end
    subgraph TRIAGE["triage tier (Sonnet) — one pass, fixed order"]
        PL["planner (+ placer)<br/>place every segment"] --> CLO["closer<br/>turn-end audit: done / block / omit"]
        CLO --> COU["courier<br/>classify peer mail (declared kind = prior)"]
        COU --> PRO["propagate (no LLM)<br/>delegated goal done → sender checked off"]
        PRO --> GRP["grouper<br/>nest related tops; owns to-do-mirror nesting"]
        GRP --> CON["consolidator<br/>same, for the Completed column"]
        CON --> DIS["distiller<br/>takeaway (done) / decision brief (blocked)"]
    end
    SYNC["plan-sync (no LLM)<br/>agent's own to-do list → authoritative nodes,<br/>new items minted flat for the grouper"] -.->|"inside the planner pass, before rollup"| PL
```

## 4. A goal node's life — the diary state machine

Since 2026-07-07 a node has no writable status flags: every change is an
appended **diary event** `{src, kind, why, t}` and the visible state is a pure
fold of that log (a stray direct write raises at the write site). Sources:
planner / closer / courier / grouper / nudge / interrupt / romp / user / agent.

```mermaid
stateDiagram-v2
    [*] --> Open : mint (planner / courier / plan-sync)
    Open --> Done : done (planner, closer, agent cross-off, user)
    Open --> Blocked : block (planner, closer, interrupt, failed nudge)
    Blocked --> Open : unblock (new real work on the branch)
    Blocked --> Open : reopen-msg (user replied, chip armed)
    Done --> Open : reopen (follow-up, nudge, delegation, user move)
    Done --> Settled : settle (romp, completion goes sticky)
    Settled --> Open : reopen (a genuine follow-up unseals)
    Open --> Cleared : clear (user cross-off, archived, undoable)
    Done --> Cleared : clear
    Blocked --> Cleared : clear
    Cleared --> Open : reopen-undo (restores what the clear displaced)
```

Fold-derived extras a plain state chart can't show, all answered by later
events, never by timers:

- **held** — the user asserted "not done" (a reopen no judge has answered):
  the card cannot roll up completed until a non-user event answers it.
- **followupPending** — a `msg` reopen in flight: the card wears the
  "Re-judging…" swirl; the planner's next verdict (or a pivot's `dismiss`,
  which restores the displaced state by snapshot) resolves it.
- **stale-verdict guards** — a done/block computed from evidence at or before
  your last follow-up is refused (your reply outranks a replayed judgment).

## 5. Card status on the board — the rollup

```mermaid
flowchart TD
    R{"rollup, per top card"} -->|"any open descendant blocked,<br/>or the top itself"| NY["Needs you"]
    R -->|"subtree done + settled,<br/>not held, no open agent to-do"| CP["Completed"]
    R -->|otherwise| WK["Working"]
    WK -->|"idle but real subagents in flight"| AW["awaiting swirl"]
    WK -->|"user follow-up in flight"| RJ["Re-judging… chip"]
    NY -->|"agent's own to-do list still holds<br/>an open item under this card"| WK
```

The agent's own to-do list is **authoritative**: an open to-do holds its card
Working over any judge inference; your actions (clear, resolve, move) outrank
both.

## 6. Peer mail — declared kind, courier reviewed

```mermaid
sequenceDiagram
    participant A as sender session
    participant BUS as postal bus
    participant B as recipient session
    participant C as courier judge
    A->>BUS: send_message(to, body, kind) — kind required:<br/>delegate | coordinate | question
    BUS->>B: deliver — body + msg-id + msg-kind markers
    Note over B: delivery becomes a peer segment<br/>(the planner skips it — the courier owns it)
    C->>C: classify — declared kind is a strong prior,<br/>the body can overrule it
    alt delegating
        C->>B: plant goal G in the recipient's tree
        C->>A: "delegated to …" tracking node in the sender's tree
        Note over B: recipient's later work files under G<br/>(the delegation planner unit)
        B-->>A: propagate — G completes, the sender's<br/>tracking node checks off (no LLM)
    else coordinating / question
        C->>C: no card — the exchange stays in chat
    end
```

## Where to look when auditing

| Question | Authoritative place |
|---|---|
| why is this card in this state? | the node's diary (`log` in `goals/<sid>.json`) — every event has src, kind, why, time |
| why was this segment filed there? | `placements` in the store (seg / seg#p / seg#live / seg#d keys) + the node's `why` and `trail` |
| did a judge fail or get skipped? | `judge-errors.jsonl` (parse fails, give-ups, rate-gate lines, unmigrated nodes) |
| what did a judge call cost / when did it run? | `judge-usage.jsonl`, attributed per judge and session |
| what happened to a peer message? | `timeline/messages.jsonl` (sent/exec events by msg-id) + the delivered markers in the transcript |
| why did a card mint at top level? | node `why`: "declared in the agent's own to-do list" = plan-sync mirror (grouper's job to nest); otherwise the planner |
