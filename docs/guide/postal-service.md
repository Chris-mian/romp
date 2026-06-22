# The postal service

Inside a romp session you can message sibling sessions — the **Romp Postal
Service**. A peer shares none of your context, only the bytes you send, so write
messages the recipient can act on from the first line.

## From a Claude session (MCP tools)

| Tool | What it does |
|---|---|
| `send_message(to, body)` | Message another session by its name. |
| `check_inbox()` | Read messages sent to you (also delivered at the end of each turn). |
| `list_agents()` | List the sessions you can reach, each with its branch and what it's working on. |
| `set_working(text)` | Publish what you're working on so peers see it. |
| `check_sent()` | See whether your sent messages were read yet. |
| `recall_message(to, id?)` | Unsend a message the recipient hasn't read yet. |
| `find_sessions(query)` | Search past and present sessions by their saved summaries. |
| `revive_session(session, message?)` | Bring a dead session back, resuming its full conversation. |

## From the shell

The same surface is on the command line, for you and for scripts:

```bash
romp --mail send <name> "<text>"
romp --mail inbox
romp --mail agents
romp --mail working "<note>"
romp --mail find "<query>"
romp --mail revive <name> "<msg>"
```

## Parked handoffs

!!! info "Messages to a dead session are not lost"
    Message a session that has exited and the message is **parked**: it waits on
    disk and is delivered the instant that session is ever revived — even days
    later — and is silently ignored if it never returns. The send response tells
    you whether the message was delivered (live) or parked (dead).

## Coordinating parallel edits

Before editing a shared repo, run `list_agents` to see what peers have published
(their working-note + branch — file overlap is only a real collision on the
*same* branch), and publish your own with `set_working`. When handing off, declare
ownership in your first line:

> DELEGATE: I own `bin/romp-kernel` — stay off it. …
