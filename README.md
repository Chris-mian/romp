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

Hook registration (which hooks fire on which Claude Code events) lives in your
own `~/.claude/settings.json`; see `hooks/` headers for the expected events.

State lives under `${XDG_STATE_HOME:-~/.local/state}/romp/`.

## Tests

```bash
bats tests/*.bats
python3 -m pytest tests/
```

## Docs

`docs/design.md` (architecture), `docs/paper.md` (writeup),
`docs/request-tree-design.md` and `docs/specs/` (frozen cross-tool contracts).
