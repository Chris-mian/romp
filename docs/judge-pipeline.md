# The judge pipeline

Every state on the board is a replay of appended events. Judges append, your
actions append, and nothing edits state in place, so any behavior can be
walked back to the events that produced it. This page shows who appends what,
in which order, and where each record lives. Companion detail:
[judges.md](judges.md) (per-judge prompts and triggers) and
[goal-state.md](goal-state.md) (the event model). Current as of 2026-07-09.

Reading the diagrams: blue = an LLM board judge (writes goal state), green =
an LLM caption judge (writes only text), gray = deterministic code, yellow =
data at rest, pink = you. A solid arrow always follows; a dashed arrow fires
only when its condition holds.

## The whole system

Transcripts and peer mail become segments; judges turn segments into events
on per-node logs; a deterministic rollup folds those logs into the board.
The LLM judges sit between two deterministic layers, so every judgment is
recorded and replayable.

```mermaid
flowchart LR
    TR[("transcripts")]:::data --> PARSE["parse:<br/>turns, segments"]:::det
    MAIL[("peer mail")]:::data --> PARSE
    PARSE --> PLAN["planners + placer (LLM):<br/>place every segment"]:::llm
    PARSE --> CLOSE["closer (LLM):<br/>audit each ended turn"]:::llm
    PARSE --> COUR["courier (LLM):<br/>review peer mail"]:::llm
    TODO[("agent's to-do list")]:::data --> SYNC["plan-sync:<br/>mirror to-dos"]:::det
    PLAN --> LOG[("goal stores:<br/>an event log per node")]:::data
    CLOSE --> LOG
    COUR --> LOG
    SYNC --> LOG
    YOU["you: clear, reply,<br/>resolve, move"]:::user --> LOG
    LOG --> GROUP["grouper + consolidator (LLM):<br/>nest related cards"]:::llm --> LOG
    LOG --> DIST["distiller + briefer (LLM):<br/>summaries, briefs"]:::llm --> LOG
    LOG --> ROLL["rollup:<br/>fold events to status"]:::det
    ROLL --> BOARD[("the board:<br/>3 columns")]:::data
    classDef llm fill:#dbeafe,stroke:#2563eb,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
    classDef data fill:#fefce8,stroke:#ca8a04,color:#111827
    classDef user fill:#fce7f3,stroke:#db2777,color:#111827
```

Order within one pass: planner, closer, courier, propagate (deterministic
check-off of delegated work), grouper, consolidator, distiller + briefer.
Every LLM call goes through one door that skips calls while an account usage
window is exhausted, turns an API error reply into a logged call failure
(never parser input), and logs cost per judge, one name per distinct prompt.
Every judge gives up loudly after three rejected replies on the same work
item and re-arms on its own event (judges.md, "When a judge fails"). A
separate Haiku tier (captioner, gister, archiver) writes the chat and
timeline captions; it never touches goals.

## When each judge runs

A turn is your message, the work it causes, and the stop at the end. A
segment is one input and its work; a turn can hold several (your message,
then a peer's message, each with its own work). The two tiers are separate
systems, so each gets its own figure.

**The caption tier** (green) writes the words you read — chat, timeline,
search — and never touches a card. Every arrow is unconditional.

```mermaid
flowchart LR
    M["message<br/>lands"]:::user --> W["work runs<br/>(the segment)"]:::det --> E["segment<br/>ends"]:::det --> X["turn<br/>ends"]:::det
    M --> GI["gister:<br/>topic phrase: the Analyzing<br/>card + the timeline dot"]:::idx
    E --> CA["captioner:<br/>one line, what<br/>got done"]:::idx
    CA -->|"the turn's captions,<br/>oldest first"| AR["archiver:<br/>session headline<br/>+ abstract"]:::idx
    linkStyle default stroke-width:2.5px
    classDef idx fill:#d1fae5,stroke:#059669,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
    classDef user fill:#fce7f3,stroke:#db2777,color:#111827
```

**The board tier** (blue) files and rules. A solid arrow always follows; a
dashed arrow fires only when the gray gate on its path holds — the gates
are deterministic checks, not model calls, and they are why nothing here
follows the clock.

```mermaid
flowchart LR
    M["message<br/>lands"]:::user --> W["work runs<br/>(the segment)"]:::det --> E["segment<br/>ends"]:::det --> X["turn<br/>ends"]:::det
    E ~~~ MAIL[("peer mail")]:::data --> CO["courier:<br/>real handoff? goal in the recipient's<br/>tree + tracker in the sender's"]:::llm
    M -.->|"work still running,<br/>not a follow-up"| PP["opener:<br/>put the ask on the board right now<br/>(<code>mint</code> or <code>sub</code> only)"]:::llm
    E --> PL["planner:<br/>file what the work did<br/>(<code>mint</code>, <code>sub</code>, <code>done</code>, <code>block</code>, <code>retitle</code>, <code>skip</code>)"]:::llm
    PL -.->|"its card has<br/>open sub-goals"| PC["placer:<br/>pick the level<br/>inside that card"]:::llm
    X --> CL["closer:<br/>end-of-turn audit of the goals the<br/>turn touched (<code>done</code>, <code>block</code>, or omit)"]:::llm
    X ~~~ SYNC["plan-sync:<br/>mirror the agent's<br/>own to-do list"]:::det
    CO ~~~ YOU["you:<br/>clear, resolve,<br/>move, reply"]:::user
    PP & PL & CL & CO & SYNC & YOU --> OG{"the set of open<br/>cards changed?"}:::det
    OG -.-> GR["grouper:<br/>nest related<br/>open cards"]:::llm
    PL & CL & YOU --> CG{"the set of completed<br/>cards changed?"}:::det
    CG -.-> CN["consolidator:<br/>the same,<br/>done column"]:::llm
    PL & CL & YOU --> DG{"a card completed<br/>and settled?"}:::det
    DG -.-> DI["distiller:<br/>background<br/>+ takeaway"]:::llm
    PL & CL --> BG{"a card<br/>blocked?"}:::det
    BG -.-> BR["briefer:<br/>the decision<br/>brief"]:::llm
    subgraph LEGEND["legend"]
        direction LR
        LS1["·"]:::det -->|"always follows"| LS2["·"]:::det
        LD1["·"]:::det -.->|"only if the<br/>gate holds"| LD2["·"]:::det
    end
    linkStyle default stroke-width:2.5px
    linkStyle 11 stroke:#2563eb
    linkStyle 7,12,18,22,26 stroke:#7c3aed
    linkStyle 13,19,23,27 stroke:#0d9488
    linkStyle 14 stroke:#b45309
    linkStyle 15 stroke:#64748b
    linkStyle 16,20,24 stroke:#db2777
    classDef llm fill:#dbeafe,stroke:#2563eb,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
    classDef data fill:#fefce8,stroke:#ca8a04,color:#111827
    classDef user fill:#fce7f3,stroke:#db2777,color:#111827
```

Edge colors carry no meaning beyond tracing which node an arrow leaves:
purple = planner, teal = closer, pink = you, blue = opener, amber =
courier, slate = plan-sync. The planner and closer are not alternatives:
every segment's work is filed by the planner, including the turn's last,
and the closer then runs once more at turn end to audit the goals the whole
turn touched (within a pass, always planner first, then closer).

The diamond gates are the event gating: the grouper keys on the set of open
cards (top-level ids) and the consolidator on the set of completed cards,
so they run after any source that changes those sets — the filing judges,
the courier's planted goals, the plan-sync mirrors, or your own
clear/resolve/undo — and stay silent when a pass changes nothing. The
distiller and briefer key on a single card's state (completed-and-settled,
blocked) regardless of which judge put it there. The placer is the
planner's second, scoped call only: the opener and the live re-plan always
hard-place at card level.

The board judges, with what each one reads and the ops it may emit:

| Judge | Fires when | Reads | May do |
|---|---|---|---|
| opener | your message lands, work still running | the message + the open-card tree | exactly one op: `mint`, or `sub` under an open card |
| planner | a segment's work ends | the work + the tree | `mint`, `sub`, `done`, `block`, `retitle`, `skip` |
| placer | the planner filed under a card that has open sub-goals | that card's subtree only | pick the level inside the card |
| closer | the turn ends | the goals this turn touched | `done`, `block`, omit (when in doubt, omit) |
| courier | a peer message arrives | the message + both sessions' trees | plant a goal + tracking node, or nothing |
| grouper | the set of open cards changed | open top cards | nest a card, mint an umbrella, nothing |
| consolidator | the set of completed cards changed | completed top cards | the same ops, done column |
| distiller | a card completed and settled | the card's whole work (or the delta since a reopen) | background + takeaway |
| briefer | a card blocked | the blocking stretch | the decision brief |

Two special inputs change how the planner reads a segment: a segment opened
by a goal-tagged nudge must resolve that goal (done or block, no plain
step), and a segment opened by an untargeted kernel notice (restart/resume)
carries a housekeeping note, so a post-restart verification sweep files
nothing instead of minting its own card.

## Placement is one question: which card

For each segment the planner answers: which open card could not be called
done without this work? No card qualifies, mint a new one. Everything after
that answer is mechanical, including where inside the card the work lands.

```mermaid
flowchart TD
    M["a segment's work"]:::det --> Q{"which card needs it?"}:::llm
    Q -->|none| MINT["mint a new card"]:::det
    Q -->|"card #n"| K{"open sub-goals<br/>inside #n?"}:::det
    K -->|no| CARD["file at the card"]:::det
    K -->|yes| P["placer (LLM):<br/>highest level that fits"]:::llm
    P --> CARD2["file inside the card"]:::det
    CARD --> G{"exact same title as<br/>parent or open sibling?"}:::det
    CARD2 --> G
    G -->|yes| REUSE["land on that node,<br/>mint nothing"]:::det
    G -->|no| NEW["new node"]:::det
    classDef llm fill:#dbeafe,stroke:#2563eb,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
```

Timing details that matter when auditing: a user message is placed twice.
The opener files it the moment it lands (card level only, so the board
updates instantly); the planner's work run refines at turn end and may add,
complete, block, or retitle. A placer or opener failure files at the card,
never nowhere, and logs to judge-errors.jsonl. The same-title guard is exact
string equality, and a completed sibling never matches, so repeated steps
still get their own nodes.

## A node's state is a replay of its log

Nothing stores "blocked" or "done" as a fact. Each node carries an
append-only log of events, each stamped with its source (planner, closer,
courier, nudge, interrupt, romp, user, agent) and reason; the visible state
is a fold over that log. A direct state write raises at the write site. The
grouper and consolidator never appear as sources: they move whole subtrees,
they never judge.

```mermaid
stateDiagram-v2
    [*] --> Open : mint
    Open --> Done : done
    Open --> Blocked : block
    Blocked --> Open : unblock, or your reply
    Done --> Open : reopen
    Done --> Settled : settle
    Settled --> Open : follow-up
    Open --> Cleared : clear
    Done --> Cleared : clear
    Blocked --> Cleared : clear
    Cleared --> Open : undo
```

Three derived flags answer the questions the chart cannot:

| Flag | Meaning | Cleared by |
|---|---|---|
| held | you asserted "not done" and no judge has answered | any later non-user event on the node |
| followupPending | your reply is being re-judged (the card's swirl) | the planner's next verdict, or a pivot |
| stale-verdict guard | a done/block computed from evidence at or before your last reply is refused | newer evidence |

## Three columns, one precedence

The rollup folds a card's subtree into a column, in this order:

1. Any open descendant blocked, or the card itself: **Needs you**.
2. Subtree done and settled, and the card is not held: **Completed**.
3. Otherwise: **Working**.

Two overrides sit above the judges: an open item on the agent's own to-do
list holds its card in Working regardless of verdicts, and your actions
(clear, resolve, move) outrank both. Completion sticks via a settle event,
so a finished card does not flicker back to Working when late work trickles
in; only a real follow-up reopens it.

## Peer mail: the sender declares, the courier verifies

A sender must declare each message delegate, coordinate, or question in the
send call itself; the courier takes the declaration as a strong prior and
reads the body for the receiving-side truth. Only a real handoff makes
cards: one in each tree, linked, and the link checks itself off.

```mermaid
flowchart TD
    S["send_message(to, body, kind)<br/>kind: delegate, coordinate, or question"]:::det --> C{"courier: did work<br/>actually change hands?"}:::llm
    C -->|yes| P["goal planted in the recipient's tree<br/>+ tracking node in the sender's"]:::det
    C -->|no| N["no card: the exchange<br/>stays in chat"]:::det
    P --> D["recipient completes the goal;<br/>the sender's tracker checks off<br/>by itself (deterministic)"]:::det
    classDef llm fill:#dbeafe,stroke:#2563eb,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
```

## Walk any surprise back to its cause

| Question | Read this |
|---|---|
| why is this card in this state? | the node's `log` in `goals/<sid>.json`: every event has source, kind, reason, time |
| why was this work filed here? | `placements` in the store, plus the node's `why` and `trail` |
| why did this mint at top level? | the node's `why`: "declared in the agent's own to-do list" means the plan-sync mirror, and nesting it is the grouper's job; anything else is the planner |
| did a judge fail or get skipped? | `judge-errors.jsonl`: every row carries judge, session, kind (parse, call, give-up, cite-miss, rate-limited, task-store, history-unreadable), and the evidence (reply tail, API message, re-arm event); rows before 2026-07-08 use the family names |
| what did a judge call cost, and when? | `judge-usage.jsonl`, per judge and session |
| what happened to a peer message? | `timeline/messages.jsonl` by message id, plus the delivered markers in the transcript |
