<p align="center">
  <img src="assets/romp-wordmark.png" alt="romp" width="440">
</p>

AI coding agents can work in parallel and unattended for hours, but once you
run more than a few, managing them consumes the attention you meant to spend
directing them. This requires you to keep track of which agent is working on
which task, scroll through transcripts for the relevant background a decision
needs, check in on the agents to see which ones are stuck or need you, and
coordinate work between multiple agents by copy and paste.

Romp gives you the tools to direct the fleet:

- **The whole fleet at a glance.** One dashboard shows every agent: who is
  working, who is stuck, who has been waiting on you, and for how long.
- **Tasks, not transcripts.** Romp infers what tasks the agents are working on
  and organizes the work by task rather than by session: several tasks can
  interleave in one session, and one task can span several. Each task shows who
  has it, what got handed off, what is done, what needs you, plus a short
  summary and the background you need to decide, so picking a thread back up
  after a week costs a glance.
- **Coordination across agents and machines.** The Romp Postal Service is mail
  between agents: they delegate, hand off, and ask each other questions
  directly, and romp tracks every exchange. It runs over SSH, so one fleet can
  span machines.
- **Transcripts built for humans.** Timestamps, live status, and collapsible
  detail; read at any level, from a one-line summary down to the raw exchange.
- **No thread is lost.** Every session is indexed and searchable, and a closed
  session revives with its history intact.
- **On your machine, from any screen.** Romp is a kernel you run on your own
  machine serving a web dashboard, with no hosted service in the middle. Open
  the dashboard in a browser tab, in the editor, or over SSH from any device.

## The three views

The feed splits the work into task cards, the timeline lays the sessions out
over time and shows where they interact, and the chat is the conversation you
already know, laid out for scanning.

## Components

- **`bin/romp`** — launch/resume/attach managed sessions, with identity colors;
  terminal views (`-d` dashboard, `-f` feed). Sessions run on one of two
  backends: the Agent SDK (default; the kernel drives the Claude Agent SDK) or
  tmux (terminal sessions tagged `@romp`). A `bin/README.md` maps every bin
  command.
- **Romp Postal Service** (`bin/romp-postal-service`) — inter-session mail: send,
  inbox, working-notes, parked mail for dead sessions, session search, revive.
  Exposed to Claude sessions as an MCP server (`romp-postal-service mcp`) and on the
  shell as `romp --mail …`.
- **Kernel** (`bin/romp-kernel`) — THE always-on core: one Python process,
  single writer. It parses each session's transcript into an event tree
  (`bin/romp-event-model`), runs the **judges** (`bin/romp-judge` — an index
  tier always on, the planners and board keepers while a client is watching;
  the roster lives in `docs/judges.md`) that
  write the durable records, and serves the chat / feed / timeline UI over
  HTTP + WebSocket. Its lifecycle is owned by **`bin/romp-manager`** (start with
  `romp --on`; `bin/romp-service` auto-starts it at login). Open
  `http://127.0.0.1:7433/` in any browser — no VS Code required.
  Design: `design/read-side.md`.
- **UI** — the three panes (chat, feed, timeline). The chat + feed render
  bundles are built from `ui/webview/` and served by the kernel; the
  timeline is `ui/romp-timeline-view.js`, served verbatim at `/timeline`.
- **chat-view/** — the VS Code/Cursor extension: a thin WebSocket client of the
  same kernel. The editor panel and a browser tab share one kernel — same tabs,
  per-client focus.
- **hooks/** — Claude Code hooks: tmux status-line state, the live one-line
  activity phrase (`hooks/romp-summarize.sh`), Romp Postal Service inbox
  drain/ensure/revive.
- **claude/** — the `/romp` skill and the MCP server config.

## Install

```bash
./install.sh                 # hooks, skill, MCP config symlinks + chat-view extension
export PATH="$PATH:$(pwd)/bin"   # add to your shell rc
```

`install.sh` also registers the hooks in your `~/.claude/settings.json`
(idempotently — it only adds missing romp entries and never touches other
hooks; see `hooks/` headers for what fires on which event) and installs the
login service so the kernel manager is always up.

State lives under `${XDG_STATE_HOME:-~/.local/state}/romp/`.

## What romp records, where it lives, what it costs

Everything stays on your machine. romp itself only ever talks to `127.0.0.1`
(the local kernel and Romp Postal Service); the only external traffic is the `claude`
CLI you already use.

- **The judges.** The kernel runs small `claude -p` calls (zero tools, MCP
  disabled — they structurally cannot act) to caption each segment/turn and to
  index each session, and (while a browser/extension is connected) to place work
  in the goal tree. The tmux status line additionally runs one live one-line
  phrase per turn (`hooks/romp-summarize.sh`). This spends a little of your own
  Claude quota — that is the cost of the live captions and inbox.
- **What gets stored:** the judges' records — per-segment/turn **captions**, a
  per-session **archive** (headline + abstract), and the **goal tree** (the
  inbox) — plus timeline events and inter-session mail, all under
  `${XDG_STATE_HOME:-~/.local/state}/romp/`. Transcripts themselves are read in
  place from where Claude Code already writes them (`~/.claude/projects/`) and
  are never copied elsewhere.
- **Nothing is uploaded, and nothing is written inside this repo.** A test
  (`tests/test_no_personal_identifiers.py`) enforces that no tracked file
  contains your hostname or home path, so recorded data can't leak into
  commits.

Kill switches — `touch` to disable, `rm` to re-enable, effective immediately:
`~/.claude/romp-summarize-off` (the live tmux activity phrase),
`~/.claude/romp-postal-off` (postal service).

## Tests

```bash
bats tests/*.bats
python3 -m pytest tests/
```

## Docs

The published site sources live in `docs/`: `getting-started.md`,
`guide/postal-service.md`, `architecture.md`, and the judge layer —
`judges.md` (the roster), `judge-pipeline.md` (the diagram map), and
`goal-state.md` (the card state model). Architecture + schemas live in
`design/`: `event-model.md` (the bottom-layer event tree), `read-side.md`
(the kernel + the three panes), `sdk-backend.md` (the Agent SDK backend),
`segment-regrowth.md`, and `stalled-open-todos-nudge.md`.
