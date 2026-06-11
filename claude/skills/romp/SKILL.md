---
name: romp
description: Move the current Claude Code conversation into a romp-managed tmux session ("convert this terminal to romp"). Use when the user runs /romp, or asks to put/resume/convert the current session into romp/tmux so it shows on the romp dashboard and persists. Idempotent — does nothing if already running inside a romp session.
allowed-tools: Bash
---

# romp — convert this session into a romp window

Goal: make sure THIS conversation is running inside a `romp`-managed tmux
session (tagged with the `@romp` flag, colored, on the romp dashboard). This is
for the common case where the user started `claude` in a plain terminal and
now wants it in romp without losing the conversation.

Background (so you explain it right): Claude Code has no live multi-window
sync. Resuming continues the *same* session id from its on-disk transcript,
so the new window picks up the full conversation — but the two processes then
diverge and share one transcript file. So "convert" means: start the romp
continuation, then the user exits the original window.

## Steps

1. **Idempotency check.** Run:

   ```bash
   if [[ -n "${TMUX:-}" ]] && [[ -n "$(tmux show -v @romp 2>/dev/null)" ]]; then
       echo "already in romp: $(tmux display-message -p '#S')"
   else
       echo "not in romp"
   fi
   ```

   romp sessions are identified by the `@romp` tmux flag (not a name
   prefix). If it prints `already in romp: <name>`, STOP — tell the user
   they're already running in that romp session, nothing to do.

2. **Resume into a detached romp session** (only if not already in romp):

   ```bash
   if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
       romp --resume "$CLAUDE_CODE_SESSION_ID" --detach
   else
       romp --resume --detach   # fall back to the picker if the id isn't set
   fi
   ```

   `--detach` makes romp create the session without trying to attach (you
   can't host an interactive attach), and print the session name plus the
   `tmux attach -t <name>` command.

3. **Hand off.** Relay to the user:
   - The exact `tmux attach -t <name>` command romp printed.
   - That they must **exit this original terminal session after attaching** —
     both processes share the same conversation transcript, so running them
     at once will clobber it.
   - If step 2 hit the picker fallback (no session id), tell them to choose
     this conversation from the list in the new window.

Do not try to kill the current session yourself — the user controls that.
