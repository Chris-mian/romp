---
name: romp-postal
description: How to message peer romp sessions — the Romp Postal Service. Use when you have the postal MCP tools (send_message / check_inbox / list_agents / set_working / check_sent / recall_message / find_sessions / revive_session) or are inside a romp session (a tmux session tagged @romp) and need to coordinate with, hand off to, or reply to sibling sessions. romp sessions auto-load this via the SessionStart hook; a plain Claude Code session has no peers and can ignore it.
allowed-tools: Bash
---

# Romp Postal Service (messaging other romp sessions)

**Only applies inside a romp session** (a tmux session tagged `@romp`; `tmux show -v @romp 2>/dev/null` prints `1`). A plain Claude Code session has no peers — ignore this skill.

In a romp session you can message sibling sessions. Prefer the MCP tools when you have them:
- `send_message(to, body)` — message another session by its name.
- `check_inbox()` — read messages sent to you (they're also delivered automatically at the end of each turn, so you rarely need this).
- `list_agents()` — list the sessions you can reach (yours is marked), each with its git branch and what it's working on.
- `set_working(text)` — publish what you're working on (files/surface) so peers see it in `list_agents`; pass empty text to clear when done.
- `check_sent()` — see whether your sent messages were read/acted on yet, or are still pending (pending ones show an `id` you can recall).
- `recall_message(to, id?)` — unsend a message the recipient hasn't read yet (still queued, or parked for a dead session) — e.g. when the ask went moot. Pass `to` to recall your unread message(s) to them, or add `id` (from `check_sent`) to cancel just one. Only your own, still-unread messages.
- `find_sessions(query)` — search PAST and present sessions by their saved Haiku summaries (what each asked + did), name, and dir, to find one with relevant expertise/context. Returns alive ● / dead ○ sessions with dir, last-active, UUID, and matching snippets. Omit the query for the most recent. Read-only.
- `revive_session(session, message?)` — bring a DEAD session back (resumes its full conversation in its own dir, rejoins `list_agents`); it returns IDLE until messaged. Pass `message` to tell it why it was woken (delivered as it loads). Spawning a process, so the human is asked to approve.

The same thing from the shell, and for the human: `romp --mail send <name> "<text>"`, `romp --mail inbox`, `romp --mail agents`, `romp --mail working "<note>"`, `romp --mail sent`, `romp --mail recall <name> [id]`, `romp --mail find "<query>"`, `romp --mail revive <name> "<msg>"`.

**On a remote machine** (you SSH'd in and are running romp there): run `romp --mail remote` to connect this machine to the laptop's bus. It configures the remote side automatically and prints the one tunnel command to run from the laptop (an `ssh -R` reverse forward, or a `~C` escape on the open connection), then auto-detects when it connects. If you try to message before setting this up, the tool nudges you to run it.

When the user tells you to coordinate with another session ("talk to X about Y"), message it and act on the replies you receive.

**Handing off to a session that's been killed.** If a peer has exited but you need to relieve it of a responsibility (it might be revived later and shouldn't keep thinking the job is still its), just `send_message` to its name anyway. If a session by that name really existed, the message is **parked**: it waits on disk and is delivered the instant that session is ever revived (even days later), and is silently ignored if it never returns. The send response tells you whether it was delivered (live) or parked (dead) — once parked, you know the responsibility is yours. (A name no session ever had still errors, so typos fail loudly.) On the flip side: if you're a revived session, mail that was parked while you were gone is the first thing surfaced in your context on resume, flagged `⏸ parked` — treat it as possibly stale and reconcile before assuming your old task still stands.

**Keep exchanges tight.** Message a peer only when you have something substantive: a question you need answered, information they need, or a result worth sharing. Don't reply just to acknowledge or to be polite, and stop once the exchange has served its purpose — two agents trading acknowledgments loop pointlessly. Remember a message wakes the recipient and costs it a whole turn, so make it count.

**Write self-contained messages.** A peer shares none of your context — only the bytes you send — and should be able to act from your first line:
- **Lead with intent.** Start the body with one of `DELEGATE:` (you own this now — reply only if you need clarification or to discuss it further), `COORDINATE:` (aligning/confirming/heads-up — reply optional, no work transferred), or `QUESTION:` (reply required, no work transferred).
- **First sentence = the whole point.** State the conclusion or ask itself, not the story of how you got there. Context comes after, and only as much as the recipient needs to act.
- **Name things exactly** — files by path, sessions by name, the same term every time; never "the thing," a synonym, or a codename you invented mid-task.
- **Match wording to evidence.** "Verified X (repro'd)" and "suspect Y (untested)" are different claims — make established vs. guessed legible from the words alone. When relaying, say whose ask or decision it is (the human's, yours, a peer's).
- **End with the response you need**, or that none is. This is what prevents pointless back-and-forth.
- **Cut words, not information.** One point per message; routine coordination is 1–3 lines, a delegation can be long. When brevity and clarity conflict, clarity wins.

**Coordinate before parallel edits.** When delegating to or working alongside a peer, declare what you own ("I own files A/B — stay off them") in the first line. Before editing in a shared repo, run `list_agents` to see what others have published (their working-on note + branch — file overlap is only a real collision on the *same* branch), and publish your own with `set_working`. Use `check_sent` to see if a message was read instead of asking "did you get it?". Confirm substantive coordination (a delegation plan, an ownership boundary) — but never just to acknowledge.
