# romp architecture figures

Romp turns a fleet of terminal Claude Code sessions into one coordinated,
observable system. This series of figures explains how. Figure 1 gives the
overall shape. Figure 2 follows a turn through the event pipeline: the model
calls that judge it and the rules that fold it into cards. Later figures zoom
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

Romp's business logic splits in two. Models judge each event once, on its way
to disk; the kernel re-derives everything the user sees from the accumulated
records, on every change, with deterministic rules. The records between them
are the only interface, and corrections close the loop: the user's verdicts
land in the same files, and the fold gives them the last word.

```mermaid
flowchart TB
  USER("the user, in the apps<br/>(figure 1)")
  CC("a Claude Code session<br/>(each session in the fleet)")

  subgraph KERNEL["The kernel: deterministic folds over the records, no model calls"]
    HUB("client hub<br/>pushes payloads,<br/>takes the user's clicks")
    CHAT("chat fold<br/>active-path walk; tool results,<br/>mail, to-dos, queue<br/>folded into widgets")
    FEED("feed fold<br/>phrases become deliverable<br/>cards, newest first")
    ASK("ask fold<br/>the request DAG becomes cards;<br/>some fifteen judged rules: newest<br/>link decides · question kinds ·<br/>auto-filing · liveness · holds …")
    TL("timeline build<br/>lanes from chopped turns,<br/>phrases, and mail")
  end

  subgraph PIPE["The summarizer pipeline: judge each event once, write it down (the session's hooks keep it alive)"]
    CHOP("the turn chopper: romp-events<br/>(deterministic) five boundary kinds,<br/>one stable id per turn")
    CALLS("three fused calls per turn (Sonnet)<br/>request: phrase + capture asks<br/>reply: tag + phrase + link + DONE<br/>message: phrase + delegation verdict")
    LIVE("live phrase<br/>(Haiku, in the hook)<br/>every prompt + reply,<br/>straight to the status bar")
    JURY("second opinions (Opus)<br/>decision briefs ·<br/>missed-handoff audits")
    PROSE("prose passes (Sonnet)<br/>card paragraphs ·<br/>session digest")
  end

  subgraph REC["Records on disk"]
    TR("transcripts<br/>~/.claude/projects/…/*.jsonl")
    SUM("summaries/<br/>one tagged phrase per<br/>turn and message")
    DAG("requests/: the request DAG<br/>asks · handoffs · links · DONE stamps ·<br/>corrections · cleared · follow-ups")
    DER("derived caches<br/>chopped turns · briefs ·<br/>paragraphs · digests")
  end

  %% top tier
  USER <-->|"one WebSocket protocol<br/>(figure 1)"| HUB
  CC -->|"every turn appended"| TR

  %% pipeline: chop, judge, write
  CHOP -.->|"watches every<br/>live transcript"| TR
  CHOP -->|"turn events,<br/>oldest first"| CALLS
  CHOP --> DER
  LIVE --> SUM
  CALLS -->|"a tagged phrase<br/>per event"| SUM
  CALLS -->|"asks · links · DONE<br/>stamps · handoffs"| DAG
  JURY -->|"demotion<br/>corrections"| DAG
  JURY --> DER
  PROSE --> DER

  %% kernel reads (dotted = reads only)
  CHAT -.->|"incremental parse"| TR
  FEED -.-> SUM
  ASK -.->|"fold by id,<br/>newest wins"| DAG
  TL -.-> DER
  HUB -->|"the user's verdicts: Clear ·<br/>correct · follow-up · report"| DAG

  %% pin tiers
  CC ~~~ CHOP

  classDef app fill:#DDF1FC,stroke:#1EA1EB,stroke-width:1.5px,color:#1a1a1a
  classDef kern fill:#E5F3D9,stroke:#54B204,stroke-width:1.5px,color:#1a1a1a
  classDef sess fill:#F0F0ED,stroke:#98998A,stroke-width:1.5px,color:#1a1a1a
  classDef rec fill:#FAE3FF,stroke:#DD42FF,stroke-width:1.5px,color:#1a1a1a
  classDef llm fill:#EFEDFD,stroke:#9088F0,stroke-width:1.5px,color:#1a1a1a
  classDef det fill:#E3F2F2,stroke:#4EA8A9,stroke-width:1.5px,color:#1a1a1a
  class USER app
  class CC sess
  class HUB,CHAT,FEED,ASK,TL kern
  class CHOP det
  class CALLS,LIVE,JURY,PROSE llm
  class TR,SUM,DAG,DER rec
  style KERNEL fill:#F1F9EB,stroke:#54B204,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style PIPE fill:#F5F3FE,stroke:#9088F0,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
  style REC fill:#FCF0FF,stroke:#DD42FF,stroke-width:2.5px,stroke-dasharray:5 5,rx:14px,ry:14px
```

The pipeline starts deterministic. The turn chopper parses each transcript
into turn events at the moments work began: a typed prompt, a dequeued
prompt, a message absorbed mid-turn, a drained message, or a mid-turn
decision. Each event carries a stable id, so every judgment downstream binds
by id instead of by time window. The summarizer daemon then judges each event
with three fused model calls: the request call phrases a typed prompt and
captures the asks it contains, the reply call tags what a turn needs from the
user with one of six relevance tags and links the work to the open asks it
served, and the message call phrases peer mail and decides whether it
delegates work. Sonnet handles this volume, a few hundred calls a day. Two
low-volume jobs run on Opus: writing a brief of what the user must decide
when a DECISION lands, and auditing a dismissed message when the recipient
soon produces work linked to nothing. A Haiku call in the hook puts a phrase
on the status bar within seconds of every prompt and reply. Every call runs
headless with zero tools, so the model can only emit a line.

The records are the contract between the two halves. The pipeline appends;
the kernel reads; nothing edits a judgment in place. `summaries/` holds one
tagged phrase per turn and message. `requests/` holds the request DAG: the
user's asks as roots, agent-to-agent handoffs as internal nodes, reply links
with DONE stamps, and the user's own verdicts appended through the feed UI.
A correction is one more record, and at fold time the newest wins, so the
user's verdict overrides the model's.

The kernel folds these files into every surface on every change and never
calls a model. The chat fold walks a transcript's active conversation path
and folds tool results, peer mail, the to-do list, and queued prompts into
widgets. The feed fold turns summaries into deliverable cards. The timeline
build assembles per-session lanes from the chopped turns, the phrases, and
the mail log. The ask fold turns the request DAG into cards in three columns
and carries most of the rules: some fifteen of them, each encoding a ruling
from daily use. The newest non-routine link decides a node's status. A
DECISION clears when the user's next typed turn arrives; an ACTION clears
only on an explicit done. A settled card files itself into Completed and
pulls itself back when work touches it; a session mid-turn on a
not-yet-attributed prompt holds its cards in place. When a card needs prose
the kernel does not write it; it spawns the pipeline's paragraph generator
and waits for the file.
