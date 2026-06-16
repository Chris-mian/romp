# romp

A multi-agent session manager for Claude Code on tmux. romp turns a fleet of
terminal Claude sessions into a coordinated, observable system: named, colored,
persistent sessions; inter-session mail; automatic per-turn captions; a live
activity feed, goal inbox, and timeline.

## Components

- **`bin/romp`** — launch/resume/attach managed sessions (tmux sessions tagged
  `@romp`), with identity colors; terminal views (`-d` dashboard, `-f` feed).
- **Romp Postal Service** (`bin/romp-postal`) — inter-session mail: send,
  inbox, working-notes, parked mail for dead sessions, session search, revive.
  Exposed to Claude sessions as an MCP server (`romp-postal mcp`) and on the
  shell as `romp --mail …`.
- **Kernel** (`bin/romp-kernel`) — THE always-on core: one Python process,
  single writer. It parses each session's transcript into an event tree
  (`bin/romp-event-model`), runs the **judges** (`bin/romp-judge` — a captioner
  + archiver always on, a planner + courier while a client is watching) that
  write the durable records, and serves the chat / feed / timeline UI over
  HTTP + WebSocket. Its lifecycle is owned by **`bin/romp-manager`** (start with
  `romp on`; `bin/romp-service` auto-starts it at login). Open
  `http://127.0.0.1:7433/` in any browser — no VS Code required.
  Design: `design/read-side.md`.
- **UI** — the three panes (chat, feed, timeline). The chat + feed render
  bundles are built from `chat-view/src/webview/` and served by the kernel; the
  timeline is `obsidian/romp-timeline-view.js`, served verbatim at `/timeline`.
- **chat-view/** — the VS Code/Cursor extension: a thin WebSocket client of the
  same kernel. The editor panel and a browser tab share one kernel — same tabs,
  per-client focus.
- **obsidian/** — the timeline view module, also consumable by an Obsidian
  plugin via a thin wrapper.
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

Architecture + schemas live in `design/`: `event-model.md` (the bottom-layer
event tree), `judge.md` (the captioner / archiver / planner / courier),
`read-side.md` (the kernel + the three panes), `ui-parity.md` (the UI port), and
`backlog.md` (spec-vs-built). `docs/simplification-inventory.md` maps the
codebase.
