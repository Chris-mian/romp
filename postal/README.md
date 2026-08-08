# postal/ — the Romp Postal Service

Inter-session mail: how peer sessions message each other (delegate, coordinate,
question) without waking the human. `postal_service.py` is both the MCP server
each session gets (`claude/romp-postal.mcp.json`) and the shell CLI
(`romp mail`); the `bin/romp-postal-service` symlink points here.

The bus is a port-keyed singleton that self-restarts when its source changes.
Delivery is push-first with a turn-boundary backstop: the kernel wakes the
recipient (`POST /deliver`) — an SDK enqueue, or for tmux sessions on Claude
Code ≥ 2.1.224 one JSON line down the session's own inbox socket (instant,
draft-safe; only for launches tagged `@romp-inbound-accept`, whose inbound gate
provably can't hold-and-drop), else draft-preserving pane injection — and the
Stop hook (`hooks/romp-postal-drain.sh`) drains whatever a wake couldn't land,
so mail never interleaves with a working turn. The mechanics live in
`docs/read-side.md` ("How mail reaches a session").
User-facing guide: `docs/guide/postal-service.md`; agent-facing usage lives in
the `romp-postal` skill (`claude/skills/romp-postal/`).
