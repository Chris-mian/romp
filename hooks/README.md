# hooks/ — Claude Code hooks

Shell hooks that romp registers with Claude Code (see `install.sh`). They are
the event-driven glue between a running session and the rest of romp — each
fires on a Claude Code lifecycle event; none of them poll.

| Hook | Event | What it does |
|---|---|---|
| `romp-wake.sh` | turn end / new work | Wakes the judges when an event creates new work for them (event-based over time heuristics, by design). |
| `romp-postal-drain.sh` | Stop | Delivers queued peer mail at turn end, so mail never interleaves with a working turn. |

Disable the postal hooks with `~/.claude/romp-postal-off`. Shell tests:
`tests/*.bats` (`romp-wake-hook.bats`, …) — keep them GNU/BSD-portable, CI runs
on Linux. (The terminal-era hooks — status scraping, the announcer phrase, the
postal ensure/context/revive legs — retired with the tmux backend, 2026-08-16;
`install.sh` scrubs their old symlinks and settings rows on upgrade.)
