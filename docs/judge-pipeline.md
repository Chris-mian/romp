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
then a peer's message, each with its own work). Every judge is a node below.
The entry judges hang off the turn's three fixed moments (and peer mail);
the board-change judges on the right follow whichever judge or action
changed the card set, never the clock. Solid = always follows; dashed =
only when the condition on the edge or node holds.

```mermaid
flowchart LR
    M["message<br/>lands"]:::user --> W["work runs<br/>(the segment)"]:::det --> E["segment<br/>ends"]:::det --> X["turn<br/>ends"]:::det
    E ~~~ MAIL[("peer mail")]:::data --> CO["courier:<br/>real handoff? goal in the recipient's<br/>tree + tracker in the sender's"]:::llm
    M --> GI["gister:<br/>topic phrase: placeholder card,<br/>timeline dot, chat gloss"]:::idx
    E --> CA["captioner:<br/>one line, what<br/>got done"]:::idx
    CA --> AR["archiver:<br/>headline + abstract from<br/>the turn captions"]:::idx
    M -.->|"work still running,<br/>not a follow-up"| PP["opener:<br/>put the ask on the board<br/>right now (mint or sub only)"]:::llm
    E --> PL["planner:<br/>file what the work did<br/>(mint, sub, done, block, retitle, skip)"]:::llm
    PL -.->|"its card has<br/>open sub-goals"| PC["placer:<br/>pick the level<br/>inside that card"]:::llm
    X --> CL["closer:<br/>done/blocked audit of the<br/>goals the turn touched"]:::llm
    X ~~~ SYNC["plan-sync:<br/>mirror the agent's<br/>own to-do list"]:::det
    CL ~~~ YOU["you:<br/>clear, resolve,<br/>move, reply"]:::user
    PP & PL & CL & CO & SYNC & YOU -.-> GR["grouper:<br/>nest related open cards<br/>(the open-top set changed)"]:::llm
    PL & CL & YOU -.-> CN["consolidator:<br/>the same for the completed<br/>column (its set changed)"]:::llm
    PL & CL & YOU -.-> DI["distiller:<br/>background + takeaway (a card<br/>completed and settled)"]:::llm
    PL & CL -.-> BR["briefer:<br/>decision brief<br/>(a card blocked)"]:::llm
    subgraph LEGEND["legend"]
        direction LR
        LB["board judge:<br/>writes goal state"]:::llm
        LG["caption judge:<br/>writes text only"]:::idx
        LS1["·"]:::det -->|"always follows"| LS2["·"]:::det
        LD1["·"]:::det -.->|"only when its<br/>condition holds"| LD2["·"]:::det
    end
    classDef llm fill:#dbeafe,stroke:#2563eb,color:#111827
    classDef idx fill:#d1fae5,stroke:#059669,color:#111827
    classDef det fill:#e5e7eb,stroke:#6b7280,color:#111827
    classDef data fill:#fefce8,stroke:#ca8a04,color:#111827
    classDef user fill:#fce7f3,stroke:#db2777,color:#111827
```

The dashed fan-in on the right is the event gating: the grouper keys on the
open-top id set and the consolidator on the completed-top set, so they run
after any source that changes those sets — the filing judges, the courier's
planted goals, the plan-sync mirrors, or your own clear/resolve/undo — and
stay silent when a pass changes nothing. The distiller and briefer key on a
single card's state (completed-and-settled, blocked) regardless of which
judge put it there. The placer is the planner's second, scoped call only:
the opener and the live re-plan always hard-place at card level.

The board judges, with what each one reads and the ops it may emit:

| Judge | Fires when | Reads | May do |
|---|---|---|---|
| opener | your message lands, work still running | the message + the open-card tree | exactly one op: mint or file under a card |
| planner | a segment's work ends | the work + the tree | mint, sub, done, block, retitle, skip |
| placer | the planner filed under a card that has open sub-goals | that card's subtree only | pick the level inside the card |
| closer | the turn ends | the goals this turn touched | done, blocked, omit (when in doubt, omit) |
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
| did a judge fail or get skipped? | `judge-errors.jsonl`: every row carries judge, session, kind (parse, call, give-up, cite-miss, rate-limited, task-store), and the evidence (reply tail, API message, re-arm event); rows before 2026-07-08 use the family names |
| what did a judge call cost, and when? | `judge-usage.jsonl`, per judge and session |
| what happened to a peer message? | `timeline/messages.jsonl` by message id, plus the delivered markers in the transcript |
