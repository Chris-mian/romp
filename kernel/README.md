# kernel/ — the always-on core

The Python backend: one process (`kernel.py`) that reads every session's Claude
Code transcript, builds the event tree, runs the judges, drives the session
backends, and serves the four panes over HTTP + WebSocket on `127.0.0.1:29855`.
Spawned by `bin/romp-serve` (the `bin/romp-kernel` symlink points here); see
`docs/architecture.md` for the data-flow picture.

Layered bottom-up:

| File | Layer | What it is |
|---|---|---|
| `event_model.py` | 1 | Transcript JSONL → event tree (atoms / segments / turns). The schema is pinned in `docs/event-model.md`. |
| `judge.py` | 2 | The judge engine + every judge prompt (captioner, archiver, planner, …). Writes the durable records (captions, archive, goal tree). `docs/judges.md`. |
| `kernel.py` | 3 | The read side: selects and displays what the layers below computed — HTTP + WebSocket server, pane payload builders, session lifecycle, nudges. `docs/read-side.md`. |

Session control (how romp drives Claude Code) sits behind one seam:

| File | What it is |
|---|---|
| `session_backend.py` | The `SessionBackend` ABC — the single interface both backends implement (guarded by `tests/test_session_api.py`). |
| `sdk_backend.py` | The Agent SDK backend (current default): an exact, event-based control channel. `docs/sdk-backend.md`. The tmux backend lives inside `kernel.py` (`TmuxBackend`). |
| `askparse.py` | tmux backend only: recovers the AskUserQuestion picker from a captured pane (SDK sessions get it natively). |

Shared lookup tables: `colormap.py` (recency tints, single source shared with
the web bundles) and `palette.py` (session-identity colors).

Everything here is loaded by file path (`SourceFileLoader`), not installed as a
package — the repo runs straight from a git clone. Python tests live in
`tests/test_*.py`.
