# romp architecture figures

Romp turns a fleet of Claude Code sessions into one coordinated,
observable system. This series of figures explains how. Figure 1 gives the
overall shape. Figure 2 follows a turn through the event pipeline: the model
roles that judge it and the rules that fold it into cards. Later figures zoom
into the subsystems: the postal service, the request DAG, the timeline, and
the two session backends.

Every figure uses the same conventions, with colors from romp's identity
palette:

- <span style="color:#1EA1EB">**blue**</span>: apps the user looks at
- <span style="color:#54B204">**green**</span>: the kernel, romp's single server process
- <span style="color:#98998A">**gray**</span>: Claude Code instances and the hooks inside them
- <span style="color:#DD42FF">**pink**</span>: records on disk
- <span style="color:#9088F0">**purple**</span>: pipeline stages that call a model
- <span style="color:#4EA8A9">**teal**</span>: deterministic pipeline stages
- **✻**: a model role; unmarked stages are deterministic code
- **model roles**: bold and colored in romp's default palette order, <span style="color:#1EA1EB">**the judge**</span> · <span style="color:#54B204">**the announcer**</span> · <span style="color:#9088F0">**the auditor**</span> · <span style="color:#4EA8A9">**the writer**</span>
- **dashed node borders**: modules that exist only with the terminal host; everything else runs with either backend
- **solid arrows**: writes and commands
- **dotted arrows**: reads only

## Figure 1: Claude Code instances, the kernel, and web apps

Everything meets at the kernel. The web apps above it speak one shared
WebSocket protocol; between the kernel and the sessions below there is no
API at all, only typed keystrokes going down and files read back up.

```mermaid
flowchart TB
  subgraph APPS["Web apps: thin clients of one kernel"]
    VSCODE("VS Code / Cursor extension<br/>(chat + feed panels)")
    BROWSER("Browser tabs<br/>(/ combined · /chat · /feed · /timeline)")
    OBSIDIAN("Obsidian leaves<br/>(iframes onto the kernel's pages)")
  end

  DASH("dashboards: terminal + Obsidian<br/>(no kernel, poll tmux directly)")

  subgraph KERNEL["The kernel: romp-serve, one Node process, 127.0.0.1:7433"]
    HUB("HTTP + WebSocket hub<br/>serves pages and bundles,<br/>routes client messages")
    MIRROR("Session mirror<br/>incremental transcript parse,<br/>feed + ask fold")
    BACKEND("SessionBackend<br/>(tmux today · headless option)")
  end

  subgraph SESSIONS["Claude Code instances: tmux sessions tagged @romp"]
    SA("claude<br/>(session A)")
    SB("claude<br/>(session B)")
    SC("claude<br/>(session …)")
    HOOKS("hooks in every session, plus the<br/>shared daemons they keep alive<br/>(status · summarizer · postal bus)")
  end

  subgraph DISK["Records on disk"]
    TR("Transcripts<br/>~/.claude/projects/…/*.jsonl")
    REC("romp records<br/>~/.local/state/romp/<br/>names · states · summaries ·<br/>requests · mail")
  end

  %% clients ⇄ kernel: one protocol
  VSCODE <-->|"WebSocket: one postMessage<br/>protocol for every client"| HUB
  BROWSER <--> HUB
  OBSIDIAN <--> HUB
  DASH -.->|"poll tmux vars<br/>once a second"| HOOKS

  %% kernel → sessions: drives them by typing (solid = writes/commands)
  BACKEND -->|"keystrokes into the terminal:<br/>prompts · interrupts · picker answers<br/>(tmux paste-buffer / send-keys)"| SB
  BACKEND --> SA
  BACKEND --> SC

  %% kernel reads (dotted = watches/polls, never writes)
  BACKEND -.->|"polls live status every 800 ms<br/>(tmux vars the hooks set:<br/>state · summary · context %)"| HOOKS
  MIRROR -.->|"watches + incrementally<br/>parses (fs.watch + poll)"| TR
  MIRROR -.-> REC

  %% sessions → disk: what Claude Code writes
  SB -->|"every turn appended"| TR
  SA --> TR
  SC --> TR
  HOOKS -->|"state log · per-turn summaries ·<br/>request DAG · mail"| REC

  %% invisible edges: pin tiers
  BROWSER ~~~ MIRROR
  DASH ~~~ BACKEND

  classDef app fill:#DDF1FC,stroke:#1EA1EB,stroke-width:1.5px,color:#1a1a1a
  classDef appAlt fill:#EDF7FD,stroke:#1EA1EB,stroke-width:1.5px,stroke-dasharray:6 4,color:#1a1a1a
  classDef kern fill:#E5F3D9,stroke:#54B204,stroke-width:1.5px,color:#1a1a1a
  classDef sess fill:#F0F0ED,stroke:#98998A,stroke-width:1.5px,color:#1a1a1a
  classDef rec fill:#FAE3FF,stroke:#DD42FF,stroke-width:1.5px,color:#1a1a1a
  class VSCODE,BROWSER,OBSIDIAN app
  class DASH appAlt
  class HUB,MIRROR,BACKEND kern
  class SA,SB,SC,HOOKS sess
  class TR,REC rec
  style APPS fill:#EDF7FD,stroke:#1EA1EB,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style KERNEL fill:#F1F9EB,stroke:#54B204,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style SESSIONS fill:#F6F7F5,stroke:#98998A,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style DISK fill:#FCF0FF,stroke:#DD42FF,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
```

Every interactive UI is a thin client of one kernel. The VS Code extension
hosts the chat and feed bundles in webview panels; Obsidian shows the
kernel's pages as iframes; both spawn the kernel when none is running, then
behave exactly like browser tabs. Only the dashboards, the terminal
`romp dashboard` and its Obsidian twin, bypass the kernel: they poll the
tmux variables directly.

The kernel touches sessions only as a user would. To drive one, it types:
prompts, interrupts, and picker answers all go into the session's terminal
through tmux. To observe one, it reads: the transcript JSONL that Claude
Code appends every turn, the records that romp's hooks and daemons maintain
under `~/.local/state/romp/`, and the live status the hooks publish as tmux
variables. Nothing requires a romp-specific runtime: any `claude` in a tmux
pane with the hooks installed participates, and sessions keep working and
keep being recorded while the kernel is down.

The headless backend swaps the tmux pane for a `claude -p` child process per
turn: same kernel, same clients, no terminal. A later figure compares the
two backends.

## Figure 2: the event pipeline, from turn to card

Romp's business logic splits in two: a pipeline of model judgments writes
each event down once, on its way to disk, and the kernel re-derives
everything the user sees by re-folding the accumulated records on every
change, with deterministic rules. Most of what it derives are cards, the
tiles of the feed, each holding one thing for the user: a decision to make,
work to review, an ask in flight. The records between the two halves are
the only interface, and corrections close the loop: the user's verdicts
land in the same files and override the pipeline's judgments at fold time.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 75, "nodeSpacing": 40}}}%%
flowchart TB
  USER("the user, in the apps<br/>(figure 1)")

  subgraph KERNEL["The kernel: deterministic folds over the records, no model calls"]
    HUB("client hub<br/>pushes payloads,<br/>takes the user's clicks")
    CHAT("chat fold<br/>active-path walk; tool results,<br/>mail, to-dos, queue<br/>folded into widgets")
    FEED("feed fold<br/>phrases become deliverable<br/>cards, newest first")
    ASK("ask fold<br/>the request DAG becomes cards;<br/>some fifteen judged rules: newest<br/>link decides · question kinds ·<br/>auto-filing · liveness · holds …")
    TL("timeline build<br/>lanes from chopped turns,<br/>phrases, and mail")
  end

  subgraph PIPE["The summarizer pipeline: judge each event once, write it down"]
    CHOP("the turn chopper · deterministic<br/>chops each session record into<br/>turn events: five boundary kinds,<br/>one stable id each")
    CALLS("<font color='#1EA1EB'><b>✻ the judge</b></font> · one call per event<br/>a prompt: phrase + capture its asks<br/>a reply: tag + phrase + link + DONE<br/>mail: phrase + handoff verdict")
    LIVE("<font color='#54B204'><b>✻ the announcer</b></font> · terminal only<br/>the live phrase: one fast call<br/>per prompt and reply")
    JURY("<font color='#9088F0'><b>✻ the auditor</b></font> · rare second opinions<br/>a brief per decision ·<br/>an audit per suspected<br/>missed handoff")
    PROSE("<font color='#4EA8A9'><b>✻ the writer</b></font><br/>one call per card paragraph ·<br/>one per session digest")
  end

  subgraph REC["Records on disk: the contract between the halves"]
    SUM("summaries/<br/>one tagged phrase per<br/>turn and message")
    DAG("requests/: the request DAG<br/>asks · handoffs · links · DONE stamps ·<br/>corrections · cleared · follow-ups")
    DER("derived caches<br/>chopped turns · briefs ·<br/>paragraphs · digests")
  end

  subgraph BACK["The session backend: two interchangeable hosts, one record"]
    TMUX("a Claude Code session<br/>in a terminal<br/>(a tmux pane)")
    HEAD("a Claude Code session<br/>headless<br/>(a child process per turn)")
    TR("the session record<br/>one append-only file per session,<br/>identical from either host")
  end

  %% top tier
  USER <-->|"one WebSocket protocol<br/>(figure 1)"| HUB

  %% kernel reads (dotted = reads only)
  CHAT -.->|"the conversation,<br/>parsed incrementally"| TR
  FEED -.-> SUM
  ASK -.->|"fold by id,<br/>newest wins"| DAG
  TL -.-> DER
  HUB -->|"the user's verdicts: clear ·<br/>correct · follow-up · report"| DAG

  %% the pipeline: chop, judge, write
  CHOP -.->|"watches every<br/>live record"| TR
  CHOP -->|"turn events,<br/>oldest first"| CALLS
  CHOP --> DER
  LIVE -->|"paints the<br/>status line"| TMUX
  CALLS -->|"a tagged phrase<br/>per event"| SUM
  CALLS -->|"asks · links · DONE<br/>stamps · handoffs"| DAG
  JURY -->|"demotion<br/>corrections"| DAG
  JURY --> DER
  PROSE --> DER

  %% the backend: either host, same record
  TMUX -->|"every turn<br/>appended"| TR
  HEAD -->|"every turn<br/>appended"| TR

  %% pin tiers
  USER ~~~ CHOP
  DAG ~~~ TMUX
  DAG ~~~ HEAD

  linkStyle default stroke-width:2px

  classDef app fill:#DDF1FC,stroke:#1EA1EB,stroke-width:1.5px,color:#1a1a1a
  classDef kern fill:#E5F3D9,stroke:#54B204,stroke-width:1.5px,color:#1a1a1a
  classDef sess fill:#F0F0ED,stroke:#98998A,stroke-width:1.5px,color:#1a1a1a
  classDef rec fill:#FAE3FF,stroke:#DD42FF,stroke-width:1.5px,color:#1a1a1a
  classDef llm fill:#EFEDFD,stroke:#9088F0,stroke-width:1.5px,color:#1a1a1a
  classDef llmTerm fill:#EFEDFD,stroke:#9088F0,stroke-width:1.5px,stroke-dasharray:6 4,color:#1a1a1a
  classDef det fill:#E3F2F2,stroke:#4EA8A9,stroke-width:1.5px,color:#1a1a1a
  class USER app
  class HUB,CHAT,FEED,ASK,TL kern
  class CHOP det
  class CALLS,JURY,PROSE llm
  class LIVE llmTerm
  class SUM,DAG,DER rec
  class TMUX,HEAD sess
  class TR rec
  style KERNEL fill:#F1F9EB,stroke:#54B204,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style PIPE fill:#F5F3FE,stroke:#9088F0,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style REC fill:#FCF0FF,stroke:#DD42FF,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style BACK fill:#F6F7F5,stroke:#98998A,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
```

Either host yields the same session record. A session runs in a terminal,
as a tmux pane the kernel types into, or headless, as a child process
spawned per turn; both append one file per session in the same format. The
chopper, the model roles, and the kernel's folds see only the record, so
they run unchanged on either host. The one exception carries a dashed
border: <span style="color:#54B204">**the announcer**</span> paints the
terminal's status line, a surface the headless host does not have.

The turn chopper, the pipeline's deterministic first stage, parses each
session record into turn events at the moments work began: a typed prompt,
a dequeued prompt, a message absorbed mid-turn, a drained message, or a
mid-turn decision. Each event carries a stable id, so every judgment
downstream binds by id instead of by time window.

Four model roles do the judging, each marked ✻ in the figure. A role is
one logical model: it has its own job, its own prompt, and a model tier
sized to the job. None runs as a resident process; every invocation is a
fresh single-shot call that sees one event, runs headless with zero tools,
and can only emit a line.

- <span style="color:#1EA1EB">**The judge**</span> rules on every event once. A typed prompt is phrased and
  mined for its asks, the requests it makes of the session. A finished
  reply gets one of six relevance tags for what the turn needs from the
  user (DECISION, ACTION, IDEA, WAIT, DONE, or DETAILS, in falling
  precedence), plus links to the open asks it served and a DONE stamp on
  each ask it completed. Peer mail gets a verdict on whether it hands work
  off to the receiving session, a handoff.
- <span style="color:#54B204">**The announcer**</span> phrases every prompt and reply into the live phrase,
  the one-line summary on the session's status line, within seconds; the
  latency budget is why it runs on a small fast model.
- <span style="color:#9088F0">**The auditor**</span>, the strongest model, gives second opinions where the
  stakes are high: a brief of what the user must decide when
  <span style="color:#1EA1EB">**the judge**</span> tags a DECISION, and an
  audit for a missed handoff when a dismissed message is followed by work
  linked to nothing.
- <span style="color:#4EA8A9">**The writer**</span> produces the longer prose: the paragraph a card expands
  into, and the session digest, a rolling summary of the session's purpose
  and recent work.

The sessions keep the pipeline alive through their hooks, so events keep
being judged while the kernel is down.

The records are the contract between the two halves. The pipeline appends
and the kernel reads; nothing edits a judgment in place. `summaries/` holds
one tagged phrase per turn and message. `requests/` holds the request DAG:
the user's asks as roots, handoffs as internal nodes, reply links with
their DONE stamps, and the user's own verdicts appended through the feed
UI. A correction is one more record; at fold time the newest wins.

A small example shows how the fold reads these records.
<span style="color:#1EA1EB">**The judge**</span> wrote the purple records;
the user wrote the blue one. Both asks came from a single typed prompt;
the handoff is the peer message that delegated the docs work.

```mermaid
flowchart TB
  subgraph EX["requests/: the DAG for one prompt, a few turns in"]
    ASK1("ask<br/>add rate limiting to the API")
    ASK2("ask<br/>get the API docs updated")
    L1("link · stamped DONE<br/>session api's reply:<br/>rate limiter merged")
    F("follow-up · from the user<br/>also add per-user limits")
    H("handoff<br/>session api hands the docs<br/>work to session docs")
    L2("link · tagged ACTION<br/>session docs' reply:<br/>draft ready for review")
  end

  ASK1 --> L1
  ASK1 --> F
  ASK2 --> H
  H --> L2

  linkStyle default stroke-width:2px

  classDef judge fill:#EFEDFD,stroke:#9088F0,stroke-width:1.5px,color:#1a1a1a
  classDef user fill:#DDF1FC,stroke:#1EA1EB,stroke-width:1.5px,color:#1a1a1a
  class ASK1,ASK2,L1,H,L2 judge
  class F user
  style EX fill:#FCF0FF,stroke:#DD42FF,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
```

At fold time the newest record on each path decides. The first ask
reopens, because the user's follow-up is newer than its DONE link. The
second ask waits on the user, because its newest link is an ACTION: the
draft needs review.

The kernel folds these files into every surface on every change and never
calls a model. The chat fold walks a session record's active conversation
path and folds tool results, peer mail, the to-do list, and queued prompts
into widgets. The feed fold turns summaries into cards, newest first. The
timeline build assembles per-session lanes from the chopped turns, the
phrases, and the mail log. The ask fold turns the request DAG into cards
in three columns.

Most of the rules live in the ask fold: some fifteen, each encoding a
ruling from daily use. The newest link above DETAILS decides a node's
status.
A DECISION clears when the user's next typed turn arrives; an ACTION clears
only on an explicit done. A settled card files itself into Completed and
pulls itself back when work touches it; a session mid-turn on a
not-yet-attributed prompt holds its cards in place. When a card needs
prose the kernel does not write it; it spawns
<span style="color:#4EA8A9">**the writer**</span> and waits for the file.

## Following one prompt through the pipeline

The pipeline reads most clearly when you follow one prompt from keystroke to
card. Take a prompt typed into a session named `api`: "add rate limiting to
the API, and get the docs updated." The sections below carry that prompt
through each stage and then note where other inputs take a different path.
The request DAG it builds is the one drawn above.

### The turn chopper

The turn chopper converts the raw session record into the events everything
downstream judges. When the prompt lands, the session appends it to the
record, and the chopper marks one event: a typed boundary at the instant the
turn began, carrying a stable id built from the session, the timestamp, and a
hash of the text. The work that follows, up to the next boundary, is that
event's work period.

A typed prompt is one of five boundary kinds, and the other four cover the
ways work starts without you typing at that moment. A prompt typed while the
session is busy waits in the queue and becomes a queued boundary when the
session picks it up. A message that arrives mid-turn and folds into the
running work becomes an absorbed boundary; one delivered as the turn ends
becomes a drain. Answering a picker or approving a plan mid-turn steers the
session like a fresh prompt, so it becomes a decision boundary. Each kind
gets its own event and its own id, and that id is the join key: every later
judgment binds to the event by id, never by matching clocks.

### The model roles

The typed event goes first to
<span style="color:#1EA1EB">**the judge**</span>, which reads the prompt and
records what it asks for. Here it finds two requests the prompt makes of the
session, rate limiting and a docs update, and writes them to `requests/` as
two asks, the roots of the graph. While that runs,
<span style="color:#54B204">**the announcer**</span> puts a live phrase on the
session's status line within seconds, so you see "adding rate limiting"
without opening anything.

The judge runs again each time the work produces something. When session
`api` finishes the limiter and replies, the judge's reply call tags the turn,
links the reply to the rate-limiting ask, and stamps that ask DONE. When
`api` hands the docs work to a session named `docs` by sending it a message,
the judge's message call rules the message a handoff and records it as a node
under the docs ask.

The reply tag is the judge's main lever, and its six values set what a card
asks of you. DECISION and ACTION both need you, a decision to make or work to
review; DONE closes an ask; WAIT marks a turn paused on an external event
rather than on you; IDEA records a suggestion; DETAILS is routine and never
decides a card's status. The tags fall in that precedence, so the most
demanding one a turn earns is the one that shows.

Two roles enter only when the stakes rise.
<span style="color:#9088F0">**The auditor**</span>, the strongest model,
writes a brief of what you must decide when a reply is tagged DECISION, and
audits a handoff that looks dropped when a session is sent a message,
dismisses it, and then produces work linked to nothing.
<span style="color:#4EA8A9">**The writer**</span> produces the longer prose on
demand: the paragraph a card expands into, and the rolling digest of what a
session is for.

### The request DAG

After a few turns the example's records form the DAG drawn above, and three
node kinds make it up. The two asks are the roots, the requests you typed.
The handoff is an internal node, the docs ask delegated from `api` to `docs`.
The links are the leaves, each a reply bound to the ask it served, carrying
its tag and, where the work finished, a DONE stamp.

Your own verdicts append to the same graph as more records. A follow-up, a
correction, or a clear is one record on a path, and at fold time the newest
record on a path wins. Typing "also add per-user limits" lands as a follow-up
under the rate-limiting ask, newer than the DONE stamp beneath it.

### The feed fold and the ask fold

The feed fold and the ask fold are the two read-time passes that turn these
records into cards. The feed fold is the simpler one: it orders the tagged
phrases newest first and renders each as a card. The ask fold is where the
rules live: it folds the request DAG into three columns, Working, Blocked,
and Completed.

The example's two asks land in different columns, and a later record moves
one of them. The rate-limiting ask, its newest link a DONE, files into
Completed; the docs ask, its newest link an ACTION, sits in Blocked awaiting
your review. When the follow-up arrives it reopens the rate-limiting ask,
now newer than the DONE, and pulls the card back to Working.

The fold carries some fifteen such rules, each one kept from daily use. A
liveness check asks whether anything is still moving on an ask: whether the
owning session is working it, a handoff holds it, or nothing will move
without you. An ask that nothing will move files itself out of Working on its
own, unless it is paused on an external event like a build or a peer's reply,
in which case it stays put because it is not waiting on you.
