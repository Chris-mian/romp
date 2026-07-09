# bin/ — what each file is

Two naming conventions, on purpose:

- **No extension** = an executable command meant for `$PATH` (`export
  PATH="$PATH:<repo>/bin"`). The language is whatever the shebang says —
  convention for commands is to hide the implementation language from the
  caller (you type `romp`, not `romp.sh`, and the implementation can change
  language without renaming).
- **`.py` extension** = an importable Python module, not a command. These are
  loaded by other bin files (via `SourceFileLoader`), never run directly.

The extensionless Python files double as modules: the kernel loads
`romp-event-model`, `romp-judge`, and `romp-askparse` by path with
`SourceFileLoader`, so they stay single-source while also being runnable.

## The core (always on)

| File | Lang | What it is |
|---|---|---|
| `romp-kernel` | Python | **The** kernel: parses transcripts into the event tree, runs the judges, serves chat/feed/timeline over HTTP+WebSocket on `127.0.0.1:7433`. Spawned by `romp-serve`. |
| `romp-event-model` | Python | Layer 1: transcript → event tree (atoms/segments/turns). Loaded by the kernel and the judges. `design/event-model.md`. |
| `romp-judge` | Python | Layer 2: the judge engine + all judge prompts (captioner, archiver, planner, …). Loaded by the kernel. `docs/judges.md`. |
| `romp-postal-service` | Python | Inter-session mail: MCP server + CLI (`romp --mail`). `romp-postal` is a symlink alias. |
| `romp_sdk_backend.py` | Python module | The **SDK session backend** (current default): drives sessions via the Claude Agent SDK. Loaded on demand by the kernel. |
| `romp_session_backend.py` | Python module | The `SessionBackend` ABC — the one seam both backends (SDK, tmux) implement. |
| `romp_colormap.py` | Python module | The recency colormaps, single source of truth shared with the web bundles. |

## The launch chain (login service → kernel)

`romp-service` (login agent) → `romp-node-launch` → `romp-manager` →
`romp-serve` → `romp-kernel`.

| File | Lang | What it is |
|---|---|---|
| `romp-service` | Bash | Installs/removes the launchd (macOS) / systemd-user (Linux) login agent. Run by `install.sh`. |
| `romp-node-launch` | POSIX sh | Runs the manager under a romp-owned copy of node (`romp-node`) so macOS TCC permissions can be granted to romp alone. |
| `romp-manager` | Node | The kernel **supervisor**: spawns kernels via `romp-serve`, respawns on crash, `up/ensure/restart-all/status/down`. Reached via `romp --on/--refresh/--status`. |
| `romp-serve` | Bash | The manager→kernel seam: rebuilds stale UI bundles, then `exec`s the kernel (PID preserved for the supervisor). |

## User-facing commands

| File | Lang | What it is |
|---|---|---|
| `romp` | Bash | The launcher/dispatcher: start/resume/attach sessions, `-d`/`-f`/`-j` terminal views, `--on/--refresh/--status`, `--mail`, `update`, `--version`. Also provisions the tmux server glue when using the tmux backend. |
| `romp-feed` | Python | Terminal mirror of the feed (`romp -f`). Backend-agnostic. |
| `romp-judge-monitor` | Python | Terminal health view of the judges (`romp -j`). |
| `romp-update` | Python | Pushes this machine's committed romp to attached remote kernels and restarts them (`romp update [host]`). |
| `romp-version` | Python | Version report across the moving parts (`romp --version`). |
| `romp-sdk-setup` | Bash | Provisions the Agent SDK venv for the SDK backend. Run by `install.sh`. |

## tmux backend only

Still wired, only meaningful for tmux sessions. If the tmux backend is ever
dropped, these (and the tmux glue in `romp` + dotfiles `tmux.conf`) go with it.

| File | Lang | What it is |
|---|---|---|
| `romp-dashboard` | Bash | Terminal dashboard over `tmux list-sessions` (`romp -d`). The web kernel is the modern equivalent. |
| `romp-askparse` | Python | Parses the AskUserQuestion picker out of a captured tmux pane (the TUI never writes an unanswered picker to the transcript). Loaded by the kernel; SDK sessions get the picker natively. |
| `romp-idle-dots` | Python | Heals stranded `working` state / fades idle tab dots by inspecting tmux panes. Fired from `hooks/tmux-status.sh`. |
| `romp-interrupt-reset` | Bash | tmux Ctrl-C/Esc bind: resets a stuck `working` state (Claude fires no interrupt hook). |
| `romp-mail-clear` | Bash | Clears the postal badge in the tmux status bar on session switch. |
