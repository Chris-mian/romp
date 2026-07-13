<p align="center">
  <img src="assets/romp-wordmark.png" alt="romp" width="440">
</p>

AI agents like Claude Code can work autonomously for long stretches, so
running several in parallel multiplies what you can accomplish. But it also
means more to manage: keeping track of which agent is doing what,
scrolling through transcripts to find the background a
decision needs, checking in to see which agents are stuck, and coordinating
handoffs of work and information between them.

Romp provides the tools to make this management seamless, so you can stay
focused on what you're trying to accomplish instead of how the work is
happening. It organizes your interaction with the agents by human-facing
tasks and goals:

- **See the whole fleet at a glance.** One place shows every agent: who is
  working, who is stuck, and who is waiting on you.
- **Pick up any thread in a glance.** Each task carries a plain-language
  summary and the background a decision needs, so you never dig through
  transcripts to get your bearings.
- **The fleet keeps moving on its own.** An agent that stalls with work left
  gets nudged back to it, so progress does not wait on you noticing.
- **Agents coordinate with each other.** They hand off work and ask each other
  questions directly, across machines, while you stay in the loop.
- **Never lose your place.** A closed session revives with its full history,
  and everything is searchable, so stepping away is always safe.

Romp adds all of this on top of the agents you already run, whatever they are
and whatever tools they use, without changing how you work.

## Self-hosted, reachable from anywhere

You run Romp yourself, on your laptop or a server, with no hosted service in
between. Connect several machines over SSH and they federate into one fleet
whose agents message across the boundary. Open the dashboard in a browser or
as a VS Code / Cursor extension, and reach it from your phone over Tailscale
to check in or keep a conversation going. The only traffic that leaves your
machine is the `claude` CLI you already use.

## See it in action

Romp presents the fleet through four views: the feed (work as task cards), the
fleet (every session with its open tasks), the timeline (sessions over time and
where they interact), and the chat you already know.

<!-- TODO: screenshots / short GIFs go here. Planned captures:
     - The fleet at a glance: the dashboard with several agents, each showing status (working / stuck / needs you).
     - A task card opening to its summary and background ("Tasks, not transcripts").
     - A stalled agent getting nudged back to its open work.
     - Two agents exchanging postal mail (a delegate / handoff / question).
     - The timeline laying sessions out over time and showing where they interact.
     - Reviving a closed session with its history intact.
     - Reaching the dashboard from a phone over Tailscale.
     - The VS Code / Cursor extension panel beside a browser tab (same fleet, two surfaces).
-->


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
  write the durable records, and serves the chat / feed / fleet / timeline UI
  over HTTP + WebSocket. Its lifecycle is owned by **`bin/romp-manager`** (start with
  `romp --on`; `bin/romp-service` auto-starts it at login). Open
  `http://127.0.0.1:7433/` in any browser — no VS Code required.
  Design: `design/read-side.md`.
- **UI** — the four panes (chat, feed, fleet, timeline). The chat + feed +
  fleet render bundles are built from `ui/webview/` and served by the kernel;
  the timeline is `ui/romp-timeline-view.js`, served verbatim at `/timeline`.
- **chat-view/** — the VS Code/Cursor extension: a thin WebSocket client of the
  same kernel. The editor panel and a browser tab share one kernel — same tabs,
  per-client focus.
- **hooks/** — Claude Code hooks: tmux status-line state, the live one-line
  activity phrase (`hooks/romp-summarize.sh`), Romp Postal Service inbox
  drain/ensure/revive.
- **claude/** — the `/romp` skill and the MCP server config.

## Install

```bash
git clone https://github.com/romp-on/romp.git
cd romp
./install.sh                 # hooks, skill, MCP config symlinks + chat-view extension
export PATH="$PATH:$(pwd)/bin"   # add to your shell rc
```

`install.sh` also registers the hooks in your `~/.claude/settings.json`
(idempotently — it only adds missing Romp entries and never touches other
hooks; see `hooks/` headers for what fires on which event) and installs the
login service so the kernel manager is always up.

State lives under `${XDG_STATE_HOME:-~/.local/state}/romp/`.

## What Romp records, where it lives, what it costs

Everything stays on your machine. Romp itself only ever talks to `127.0.0.1`
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

The published site sources live in `docs/`: `getting-started.md`, a `guide/`
with a page per capability (`the-fleet.md`, `tasks.md`, `nudges.md`,
`postal-service.md`, `sessions.md`, `remote-access.md`), `architecture.md`,
and the judge layer — `judges.md` (the roster), `judge-pipeline.md` (the
diagram map), and `goal-state.md` (the card state model). Architecture +
schemas live in `design/`: `event-model.md` (the bottom-layer event tree),
`read-side.md` (the kernel + the panes), `sdk-backend.md` (the Agent SDK
backend), `segment-regrowth.md`, and `stalled-open-todos-nudge.md`.
