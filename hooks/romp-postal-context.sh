#!/usr/bin/env bash
# SessionStart hook (romp): tell a romp session it can message peers, in a COMPACT
# pointer, not the full skill. The old hook emitted the entire SKILL.md body every
# session (~1.4k tokens, re-sent every turn) and duplicated the postal MCP tools'
# own instructions + descriptions. Now it emits only the essentials the session
# needs up front, and defers the full guide (shell CLI, remote-machine setup,
# coordination detail) to the romp-postal skill, loaded on demand. Non-romp /
# non-tmux sessions get nothing (gated on @romp); SDK sessions get the norms from
# the postal MCP's own instructions instead. Keep this in sync with SKILL.md.
[ "$(tmux show -v @romp 2>/dev/null)" = "1" ] || exit 0
# An ISOLATED session is told nothing about peers (the user 2026-08-27). Its sends are refused and its
# mail is held either way, so advertising the tools only teaches it to reach sideways, hit the refusal,
# and narrate that at the user — or, worse, to point the user at another session to go read. Resolved
# exactly as kernel._postal_isolated resolves it: this session's own override, else the "*" master.
ROMP_STATE_ROOT="${ROMP_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/romp}"
if python3 - "$ROMP_STATE_ROOT/session-flags.json" "$(tmux show -v @romp-session-id 2>/dev/null)" <<'PY'
import json, sys
flags_path, sid = sys.argv[1], sys.argv[2]
try:
    flags = json.loads(open(flags_path).read())
except Exception:
    sys.exit(1)                       # unreadable → not isolated, same fail-OPEN posture as the readers
own = flags.get(sid) if sid else None
if isinstance(own, dict):
    for key in ("postalServiceOff", "postalOff"):
        if key in own:
            sys.exit(0 if own[key] else 1)
master = flags.get("*")
sys.exit(0 if isinstance(master, dict) and master.get("postalServiceOff") else 1)
PY
then
    exit 0
fi
read -r -d '' CTX <<'TXT'
You're in a romp session with sibling sessions you can message: use the postal MCP tools (send_message, list_agents, set_working, check_inbox, check_sent, recall_message) or `romp mail`. Each tool's description carries its norms. Two to know up front:
- Message a peer only for something substantive (it wakes them and costs a turn), leading with DELEGATE:/COORDINATE:/QUESTION: and the whole point in the first sentence.
- BEFORE editing shared files, run list_agents and check peers' branches + working-notes to avoid collisions (overlap only collides on the same branch); publish yours with set_working.
For the full guide (shell CLI, remote-machine tunnel setup, coordination detail), invoke the romp-postal skill.
TXT
python3 - "$CTX" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": sys.argv[1]}}))
PY
