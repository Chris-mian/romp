# romp intent layer: design and views

*2026-06-09, revised 2026-06-10 after a day of live use · written by the
feed_design session · schema: `~/.local/state/romp/REQUESTS.md` · cache guide:
`~/.local/state/romp/SEARCH.md`*

## Abstract

You run ten to thirty Claude Code agents at once. Their transcripts record
everything they do, but at hundreds of megabytes they cannot be read, searched,
or remembered directly. Operating the fleet needs only three things from all
that text: a memory of what you asked for, a short list of what needs your
input, and confidence that nothing pending or finished has been lost. The romp
pipeline distills every transcript into four kinds of small durable records,
and an intent layer links each piece of work to the ask that caused it. Every
view of the fleet (the feed panel, the terminal feeds, the pipeline table, the
ledger, the timeline) is a projection of those records, computed at read time
with no model calls. The state you maintain is per-ask and small: Clear to
retire a card, and a handful of one-click adjudications (mark done, "did it",
"didn't need me") that double as training data for the reader. This document
explains the records, the request graph, the lifecycle of an ask, the teaching
loop your corrections drive, and which view answers which question.

## 1. From transcripts to records

Four kinds of records, produced by one parser and one daemon, carry everything
the views need (Fig. 1). `romp-events` parses transcripts deterministically
(no model) into turns and gives each turn a stable id of the form
`<session>:<turn-start>:<hash>`. That id is the join key everywhere: a summary
line, a detail paragraph, and a registry link about the same turn all share
it. `romp-summarize-backfill`, the only always-on process, makes one model
call per turn and writes all of the model-derived records.

```
~/.claude/projects/          transcripts: append-only, hundreds of MB, source of truth
        │
        ▼  parse (deterministic, no model)
   romp-events               turns + stable ids:  <session>:<turn-start>:<hash>
        │
        ▼  one model call per turn (romp-summarize-backfill)
 ┌──────┴────────────────────────────────────────────────┐
 │ summaries/<sid>.jsonl   one line per turn:            │
 │                         8-word phrase + routing tag   │
 │ requests/…              the request graph: asks,      │
 │                         handoffs, links  (see §2)     │
 └──────┬────────────────────────────────────────────────┘
        ▼  follow-up generators
 feed-detail/<id>.json    expandable paragraph (done/decision turns only)
 digest/<sid>.json        rolling per-session rollup
```
*Figure 1. The pipeline. Everything below the transcripts is small (a few MB),
append-only, and read directly by the views.*

Two facts about these records shape everything downstream. First, summaries
are the stable spine: once written, a line is never revised, while
`romp-events` re-derives its turn boundaries as transcripts grow and can merge
turns away. Views therefore anchor on summaries and use events only for
timing. Second, the tag on each turn (done, decision, or details) is routing
data, not content: it decides which column a card sits in and which turns get
a detail paragraph, and it never appears in any interface.

## 2. The request graph

Every piece of fleet work traces to an ask: something you typed, or approved,
in some session. The graph has three node kinds. Asks are the roots, handoffs
between agents are the branches, and links attach each reply to the requests
it served.

Roots are asks, not turns. The capture step splits each typed turn into zero
or more asks ("fix the flicker, and add some color" becomes two), folds
follow-ups into the ask they amend ("actually make it blue" rewrites the
existing root rather than spawning a new one), and materializes approvals:
when an agent proposes a plan and you answer "go ahead", the asks are drawn
from the proposal text.

A handoff between agents is itself a request node. When one session mails
work to another, that message becomes an internal request whose id is the
message id and whose parent edges name the request(s) the sender was serving.
Agents never see or mint any of these ids; the graph is assembled entirely
from what they write naturally.

Replies attach to the graph through links. For each reply, the summarizer
answers one small multiple-choice question, "which of this agent's open
requests does this serve, or none", and a link records the answer. Attribution
to your original ask therefore never requires a global judgment: a weak model
makes a reliable local match, and recorded parent edges make the rest a
mechanical walk back to the roots (Fig. 2).

```
ask · "rebuild the feed into three columns"           you → vs_chat
 ├── link    "built two-column card layout"           done
 ├── link    "stack or scroll when narrow?"           decision (needs you)
 ├── handoff "tune the recency colormap"              vs_chat → haiku_summaries
 │     └── link  "lowered tint alpha"                 done
 └── link    "three-column view shipped"              done
```
*Figure 2. One ask's subgraph. The handoff is itself a request node, and the
walk from any leaf back to the ask follows recorded edges, so no model is
involved in tracing.*

One reply often serves several requests at once, because mail from other
sessions arrives mid-turn and a single turn closes threads across unrelated
workstreams. A link that names several requests therefore carries a short
phrase *per request*, scoped to what the turn did for that one; the
whole-turn phrase is only a fallback. Without this, the summary of a
multi-thread turn bleeds into every card it touches.

A wrong local match is tolerated by design. A mislinked or unlinked reply
costs only display placement, and a decision log records every match with its
candidates, so link reliability is measurable rather than assumed. The one
failure the design refuses is losing a root: your ask persists until you clear
it, so anything that goes missing can be hunted down starting from the ask.

## 3. The lifecycle of an ask

An ask is judged by where its paths *end*. Each node in the ask's subgraph
takes its status from the newest link directly on it; the card's column then
folds those statuses upward: a node whose every downstream path ends done is
done itself, even if nothing was ever filed directly on it, and an open
question anywhere bubbles to the top (Fig. 2b). Restating work or answering a
question along the way is transparent; only the ends of paths matter. This
replaced the original newest-link-anywhere rule after one day of real use,
where delegated chains could never finish because no one stamps "done" on
every intermediate restatement.

```
ask  "rebuild the feed"                ●          ●  done   — every path below
 ├── link  "layout built"              ●                      ends done
 ├── handoff → haiku_summaries         ●  (transparent: its
 │     └── link "tint lowered"         ●   own path ends done)
 └── handoff → vs_chat                 ○  ← drop point: this path just stops,
                                            so vs_chat owes you its ending
```
*Figure 2b. The leaf-path fold. The card completes when every path ends in `●`;
a path that ends in `○` names the session that owes you a completion or a
question; a `?` anywhere routes the whole card to AWAITING.*

| Where the paths stand | Column | Reading |
|---|---|---|
| some path still open | ASKS | in flight; your external memory that you asked |
| a question, action, or idea is live | AWAITING | someone needs you: answer, do, or react |
| every path ends done | COMPLETED | at rest; verify it, then Clear |

AWAITING (the awaiting-chip red) holds three kinds of items, distinguished by
what crosses them off: a *decision* is crossed off by your next typed answer
in that session; an *action* ("reload the editor window") survives typing and
clears only when you click "did it", because you may well have typed without
acting; an *idea* is a suggestion your next typed turn implicitly dismisses.
Anything that lands in AWAITING wrongly carries a "didn't need me" link, and
clicking it both removes the item and teaches the reader (§5).

Completion is recoverable in both directions. A completed card carries a
"Follow up" box: the text is delivered to the owning session under the card's
title, and the card returns to ASKS with the same title, completing again when
the new work ends. The follow-up turn is filed as a child of the original
ask, so one card accumulates the whole history of a request and its
afterthoughts. In the other direction, the system never declares an ask
complete on its own authority: "looks finished" is derived from the records,
while "is finished" is yours alone to assert, by clearing.

Clearing appends one line to `cleared.jsonl` and removes the card from every
surface. Clearing early degrades gracefully: a question or a follow-up that
arrives after your Clear resurrects the card, because something waiting on
you must never be invisible.

## 4. The views

Each view answers one operational question (Table 1); choose by the question,
not the surface.

| View | Where | The question it answers |
|---|---|---|
| three-column feed | VS Code "romp feed" panel | what is open, what needs me, what finished? |
| asks inbox | `romp -f --asks` | the same, in a terminal |
| deliverables feed | `romp -f` | what got done across the fleet, newest first? |
| pipeline table | `romp -p` | is the machinery itself keeping up? |
| ledger | `romp -l` | what is each session doing right now? |
| timeline | vault-code / vscode-trackchanges | when did things happen, and who messaged whom? |

*Table 1. The views. All of them are read-time projections of the same records.*

The feed panel is the primary surface and holds exactly three columns
(Fig. 3). An ask card carries your phrasing as its title, the owning session,
evidence tallies, and two controls (expand and Clear). Work linked to an ask
renders inside that card, as the tally and the expandable linked-work list,
never as its own card. User-prompted work that finished without belonging to
any ask appears as a standalone card in the right two columns: that is the
granular or unexpected work. Agent-internal turns and routine progress never
surface at all; routine turns only freshen their ask's recency.

```
┌─ ASKS ─────────────────┐┌─ AWAITING ─────────────┐┌─ COMPLETED ────────────┐
│ open, in flight        ││ waiting on you         ││ finished; verify+Clear │
│                        ││                        ││                        │
│ port the nag plugin    ││ stack or scroll        ││ feed rebuilt           │
│  exercise_time         ││ when narrow?           ││  vs_chat · 3 done      │
│  waiting on vs_chat 2h ││  [reply…] didn't       ││  [Follow up] [Clear]   │
│  [Clear]               ││  need me               ││                        │
└────────────────────────┘└────────────────────────┘└────────────────────────┘
```
*Figure 3. The feed panel: one card per open ask, plus standalone completions.
Card background is tinted by recency. One typed prompt that splits into
several asks renders as one group card whose members check off individually.*

Opening a card shows the request graph itself, drawn as an indented tree:
your ask at the root, handoffs nested under what they serve, each node's
replies as its rows, every line marked `●` done (green), `?` needs you, or `○`
still open. The tree reads as a linear history, oldest at the top at every
level, and a completed card is simply a tree of all `●`. There is no such thing
as a progress report that is not a completed thing, so every report row is a
green dot; hovering any line highlights the union of everything beneath it on
the timeline.

Clicks follow one contract. A card title always jumps the chat to *your
prompt*: the landing uses the card's own recorded session and moment, never a
relayed pointer, and is restricted to your turns, so the worst case is a
nearby prompt of yours rather than an agent's reply (a degraded landing says
so in a small notice and logs itself for diagnosis). Hovering or
single-clicking a card only highlights its path on the timeline; double-click
pans the timeline to it; rows inside the tree jump to the work they name.

The pipeline table (`romp -p`) watches the machinery rather than the content.
A healthy row shows only age, session, duration, and the turn's phrase. Status
text appears only when a stage is behind (an hourglass plus the lagging
stage's name, `summary` or `detail`), colored by
how long it has waited, and dim trailing notes record registry traffic
(`+1 ask`, `→1 req`).

## 5. The teaching loop

Your one-click adjudications are the reader's training data, and the loop runs
daily. Each click ("mark done" on a stale card, "did it" on an action,
"didn't need me" on a false AWAITING item) appends a correction: a record
naming the node, the verdict the reader should have reached, and the reply it
should have reached it on. At read time a correction acts exactly like a link,
so the card moves immediately; on the write side the same row becomes a
labeled example and a permanent regression fixture, and a re-judge pass
re-runs the reader over still-open cards whenever its prompts change. The
efficient workflow is deliberately coarse: batch-click whatever you can see is
done, then have the prompts reworked; flag only the structurally weird cards.

The loop's risk posture makes this cheap. A card wrongly marked completed is
safe, because everything in COMPLETED gets verified by you before Clear; the
only fatal error is losing an ask. Two write-side rules guard the asymmetry: a
reply may only stamp done on requests it explicitly finished, and a completed
ask is never re-titled (a late amendment becomes a child instead).

## 6. Design rules

Seven rules keep the records trustworthy and the views cheap:

- **single writer**: each file has one writer; the daemon writes all
  model-derived records, the UI writes only the human-asserted files
  (`cleared.jsonl`, `corrections.jsonl`, `followups.jsonl`);
- **read-time derivation**: every view is a file join; rendering makes no
  model calls;
- **human-only resolution**: done links are evidence, Clear is the only
  retirement, and your corrections outrank the reader;
- **misattribution over lost roots**: a wrong link is acceptable, a vanished
  ask is not;
- **oblivious agents**: no agent ever sees, mints, or carries a registry id;
- **degrade precision, never kind**: a click that means "my prompt" may land
  on a nearby prompt, never on an agent's output; failures announce
  themselves rather than impersonating success;
- **quiet when healthy**: interfaces spend ink only on deviation; states that
  must change while no event fires (an interrupted session stuck "working",
  an idle dot that should fade) are healed by one timer-side watcher rather
  than per-surface guards.

## 7. Where things live

`~/.local/state/romp/` holds all records: `summaries/`, `requests/` (the graph
plus your `cleared`, `corrections`, and `followups` files), `feed-detail/`,
`digest/`, `names/` (session identity), and `locate-diag.jsonl` (how every
deep-link landing resolved, for diagnosing a click that landed somewhere
weird). `REQUESTS.md`, in the same directory, defines the registry schema;
`SEARCH.md` explains how an agent should search the cache. The knowledge
subset mirrors to a Proton-backed git remote every 15 minutes. Transcripts
stay in `~/.claude/projects/`, untouched.
