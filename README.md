# romp

A multi-agent session manager for Claude Code on tmux. romp turns a fleet of
terminal Claude sessions into a coordinated, observable system: named, colored,
persistent sessions; inter-session mail; automatic per-turn summaries; a live
activity feed and timeline.

## Components

- **`bin/romp`** — launch/resume/attach managed sessions (tmux sessions tagged
  `@romp`), with identity colors and a dashboard (`bin/romp-dashboard`).
- **Romp Postal Service** (`bin/romp-postal`) — inter-session mail: send,
  inbox, working-notes, parked mail for dead sessions, session search, revive.
  Exposed to Claude sessions as an MCP server (`romp-postal mcp`) and on the
  shell as `romp --mail …`.
- **Summarizer** (`bin/romp-summarize-backfill`, `hooks/romp-summarize.sh`) —
  per-turn summaries of every session's transcript, tagged by relevance,
  feeding the surfaces below.
- **Feed & requests** (`bin/romp-feed`, `bin/romp-feed-detail`,
  `bin/romp-pipeline`, `bin/romp-ledger`) — what each session delivered,
  folded into per-request cards (spec: `docs/specs/REQUESTS.md`).
- **Timeline** (`bin/romp-events`, `bin/romp-timeline-serve`,
  `obsidian/romp-timeline-*.js`) — event-level history of all sessions.
- **Kernel** (`bin/romp-serve`, `chat-view/src/kernel/`) — THE UI host: chat
  tabs, the feed, request cards, live status, served over HTTP + WebSocket.
  Run `romp-serve` and open `http://127.0.0.1:7433/` (chat) and `/feed` in
  any browser — no VS Code required. Sessions are driven through a pluggable
  backend — tmux (default) or `--backend headless` (`claude -p`, no tmux at
  all). Design: `docs/web-kernel-design.md`.
- **chat-view/** — the VS Code/Cursor extension: a thin client of the same
  kernel (it spawn-or-attaches one automatically). The editor panel and a
  browser tab share one kernel — same tabs, per-client focus.
- **obsidian/** — view modules (timeline, dashboard) consumable by an
  Obsidian plugin via a thin wrapper.
- **hooks/** — Claude Code hooks: tmux status-line state, per-turn summarize,
  Romp Postal Service inbox drain/ensure/revive.
- **claude/** — the `/romp` skill and the MCP server config.

## Install

```bash
./install.sh                 # hooks, skill, MCP config symlinks + chat-view extension
export PATH="$PATH:$(pwd)/bin"   # add to your shell rc
```

`install.sh` also registers the hooks in your `~/.claude/settings.json`
(idempotently — it only adds missing romp entries and never touches other
hooks; see `hooks/` headers for what fires on which event).

State lives under `${XDG_STATE_HOME:-~/.local/state}/romp/`.

## What romp records, where it lives, what it costs

Everything stays on your machine. romp itself only ever talks to `127.0.0.1`
(the local kernel and postal bus); the only external traffic is the `claude`
CLI you already use.

- **Per-turn summaries.** On each prompt and each finished turn,
  `hooks/romp-summarize.sh` runs a nested `claude` call (zero tools, MCP
  disabled — it structurally cannot act) over a slice of that session's
  transcript and stores a short phrase for the dashboard/feed/timeline. This
  spends a little of your own Claude quota on every turn of every romp
  session — that is the cost of the live summaries.
- **What gets stored:** summaries, timeline events, request cards, and
  inter-session mail, all under `${XDG_STATE_HOME:-~/.local/state}/romp/`.
  Transcripts themselves are read in place from where Claude Code already
  writes them (`~/.claude/projects/`) and are never copied elsewhere.
- **Nothing is uploaded, and nothing is written inside this repo.** A test
  (`tests/test_no_personal_identifiers.py`) enforces that no tracked file
  contains your hostname or home path, so recorded data can't leak into
  commits.

Kill switches — `touch` to disable, `rm` to re-enable, effective immediately:
`~/.claude/romp-summarize-off` (summaries), `~/.claude/romp-digest-off`
(digests), `~/.claude/romp-postal-off` (postal service).

## Tests

```bash
bats tests/*.bats
python3 -m pytest tests/
```

## Docs

`docs/design.md` (architecture), `docs/paper.md` (writeup),
`docs/request-tree-design.md` and `docs/specs/` (frozen cross-tool contracts).
