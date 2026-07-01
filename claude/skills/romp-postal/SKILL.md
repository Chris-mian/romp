---
name: romp-postal
description: How to message peer romp sessions (the Romp Postal Service). Use when you have the postal MCP tools (send_message / check_inbox / list_agents / set_working / check_sent / recall_message) or are inside a romp session and need to coordinate with, hand off to, or reply to sibling sessions. romp sessions get a short pointer to this at SessionStart; a plain Claude Code session has no peers and can ignore it.
allowed-tools: Bash
---

# Romp Postal Service (messaging peer sessions)

Only applies inside a romp session (a tmux session tagged `@romp`, or an SDK-backed romp session). A plain Claude Code session has no peers, so ignore this.

## Tools

Message sibling sessions with the postal MCP tools (each tool's own description carries the specifics): `send_message(to, body)`, `check_inbox()`, `list_agents()`, `set_working(text)`, `check_sent()`, `recall_message(to, id?)`. Inbox is also delivered automatically at each turn's end, so you rarely call `check_inbox` yourself.

Addressing is live-only: you can message only currently-live sessions (see `list_agents`). Dead names error, with no parked mail or reviving.

From the shell (also how the human drives it): `romp --mail send <name> "<text>"`, `romp --mail inbox|agents|sent`, `romp --mail working "<note>"`, `romp --mail recall <name> [id]`.

## On a remote machine

If you SSH'd into another machine and are running romp there, run `romp --mail remote` to connect it to the laptop's bus. It configures the remote side and prints the one tunnel command to run from the laptop (an `ssh -R` reverse forward, or a `~C` escape on the open connection), then auto-detects when it connects. Messaging before this setup nudges you to run it.

## Norms

**Keep it tight.** Message a peer only for something substantive: a question you need answered, information they need, or a result worth sharing. A message wakes the recipient and costs it a turn, so never send just to acknowledge, and stop once the exchange is done.

**Write so the recipient can act from your first line** (they share none of your context):
- Lead with `DELEGATE:` (you own this now, reply only to clarify), `COORDINATE:` (aligning or heads-up, reply optional), or `QUESTION:` (reply required).
- First sentence is the whole point: the ask or conclusion, not how you got there. Context after, only what they need to act.
- Name things exactly: files by path, sessions by name, the same term each time. Mark verified vs. suspected, and whose ask it is.
- End with the reply you need, or that none is. One point per message; when brevity and clarity conflict, clarity wins.

**Coordinate by reading state, not by waking peers.** Before editing a shared repo, run `list_agents` to see peers' branches and working-notes (overlap is a real collision only on the same branch), and publish yours with `set_working`. Declare what you own in your first line ("I own A/B, stay off them"). Resolve ownership by reading that state, never by messaging "do you still own this?": an idle peer's note may be stale, a peer with no note holds nothing, and romp auto-clears a note once a session's work is done. Use `check_sent` to see whether a message was read instead of asking. Never wake an idle session just to coordinate, which is the false interrupt romp exists to avoid.

When the human says "coordinate with X about Y," message X and act on the replies.
