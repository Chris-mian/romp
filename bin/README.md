# bin/ — the command surface

`bin/` is the stable **entry-point surface**: every runnable romp command lives
here (put it on `$PATH`: `export PATH="$PATH:<repo>/bin"`). The Python
*implementations* live in the logical source folders — `kernel/`, `postal/`,
`cli/` — and the corresponding bin entries are **symlinks** to them, so external
consumers (launchd/systemd, hooks, the MCP config, remote kernels)
keep stable paths while the code stays navigable by component. `ls -l bin` is
the live map of that indirection.

Only the shell/Node launch glue is a real file here — it *is* the command, with
no separate implementation to point at.

## Real files (launch chain + shell commands)

`romp-service` (login agent) → `romp-node-launch` → `romp-manager` →
`romp-serve` → `kernel/kernel.py`.

| File | Lang | What it is |
|---|---|---|
| `romp` | Bash | The dispatcher: create sessions over the kernel API (`romp new`), revive past ones (`romp resume`), message/interrupt/end them, plus `status`/`refresh`/`update`/`version`. |
| `romp-service` | Bash | Installs/removes the launchd (macOS) / systemd-user (Linux) login agent. Run by `install.sh`. |
| `romp-node-launch` | POSIX sh | Runs the manager under a romp-owned copy of node (`romp-node`) so macOS TCC permissions can be granted to romp alone. |
| `romp-manager` | Node | The kernel **supervisor**: spawns kernels via `romp-serve`, respawns on crash, `up/ensure/restart-all/status/down`. Reached via `romp up` / `romp refresh` / `romp status`. |
| `romp-serve` | Bash | The manager→kernel seam: maps the manager's spawn contract onto the kernel's env, picks the python, then `exec`s the kernel (PID preserved for the supervisor; the kernel self-builds stale UI bundles). |
| `romp-sdk-setup` | Bash | Provisions the Agent SDK venv for the SDK backend. Run by `install.sh`. |

## Symlinks → `kernel/` (the always-on core)

| Command | Source | What it is |
|---|---|---|
| `romp-kernel` | `kernel/kernel.py` | **The** kernel: parses transcripts into the event tree, runs the judges, serves chat/feed/fleet/timeline over HTTP+WebSocket on `127.0.0.1:29855`. Spawned by `romp-serve`. |
| `romp-event-model` | `kernel/event_model.py` | Layer 1: transcript → event tree (atoms/segments/turns). Loaded by the kernel and the judges. |
| `romp-judge` | `kernel/judge.py` | Layer 2: the judge engine + all judge prompts (captioner, archiver, planner, …). `docs/judges.md`. |
| `romp_sdk_backend.py` | `kernel/sdk_backend.py` | The **SDK session backend** (current default): drives sessions via the Claude Agent SDK. |
| `romp_session_backend.py` | `kernel/session_backend.py` | The `SessionBackend` contract the SDK backend implements (plus the NullBackend of documented refusals). |
| `romp_colormap.py` | `kernel/colormap.py` | The recency colormaps, single source of truth shared with the web bundles. |
| `romp_palette.py` | `kernel/palette.py` | The session-identity color palettes. |

## Symlinks → `postal/`

| Command | Source | What it is |
|---|---|---|
| `romp-postal-service` | `postal/postal_service.py` | Inter-session mail: MCP server + CLI (`romp mail`). `romp-postal` is a symlink alias. |

## Symlinks → `cli/` (terminal tools)

| Command | Source | What it is |
|---|---|---|
| `romp-update` | `cli/update.py` | Pushes this machine's committed romp to attached remote kernels and restarts them (`romp update [host]`). |
| `romp-version` | `cli/version.py` | Version report across the moving parts (`romp version`). |

