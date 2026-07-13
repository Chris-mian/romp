# The postal service

Inside a romp session you can message sibling sessions — the **Romp Postal
Service**. A peer shares none of your context, only the bytes you send, so write
messages the recipient can act on from the first line.

## From a Claude session (MCP tools)

| Tool | What it does |
|---|---|
| `send_message(to, body, kind)` | Message another session by its name. `kind` is required — `delegate` (they own the work now), `coordinate` (aligning/heads-up), or `question` (you need an answer). The declaration travels with the message and the courier judge treats it as a strong prior, overriding only when the body clearly does something else. |
| `check_inbox()` | Read messages sent to you (also delivered at the end of each turn). |
| `list_agents()` | List the sessions you can reach, each with its branch and what it's working on. |
| `set_working(text)` | Publish what you're working on so peers see it. |
| `check_sent()` | See whether your sent messages were read yet. |
| `recall_message(to, id?)` | Unsend a message the recipient hasn't read yet. |

## From the shell

The same surface is on the command line, for you and for scripts:

```bash
romp --mail send [--kind delegate|coordinate|question] <name> "<text>"
romp --mail inbox
romp --mail agents
romp --mail working "<note>"
```

## Addressing is live-only

!!! info "You can only message live sessions"
    Addressing resolves against the currently-live fleet (see `list_agents`). A
    name that isn't a live session errors — there is no parking mail for, or
    reviving, dead sessions.

## Coordinating parallel edits

Before editing a shared repo, run `list_agents` to see what peers have published
(their working-note + branch — file overlap is only a real collision on the
*same* branch), and publish your own with `set_working`. When handing off, declare
ownership in your first line:

> DELEGATE: I own `kernel/kernel.py` — stay off it. …
