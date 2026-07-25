# postal/ — the Romp Postal Service

Inter-session mail: how peer sessions message each other (delegate, coordinate,
question) without waking the human. `postal_service.py` is both the MCP server
each session gets (`claude/romp-postal.mcp.json`) and the shell CLI
(`romp mail`); the `bin/romp-postal-service` symlink points here.

The bus is a port-keyed singleton that self-restarts when its source changes.
Delivery is turn-boundary–safe: mail lands via the Stop hook
(`hooks/romp-postal-drain.sh`) so it never interleaves with a working turn.
User-facing guide: `docs/guide/postal-service.md`; agent-facing usage lives in
the `romp-postal` skill (`claude/skills/romp-postal/`).
