#!/usr/bin/env bash
# SessionStart hook (romp): in a romp session, auto-load the Romp Postal Service
# norms (the romp-postal skill) as session context — so peer-messaging guidance
# is present WITHOUT living in the always-on global CLAUDE.md (it only applies to
# romp sessions). Non-romp / non-tmux sessions get nothing: gated on the @romp
# tmux flag. The skill SKILL.md is the single source of truth; this emits its
# body (frontmatter stripped) as SessionStart additionalContext.
[ "$(tmux show -v @romp 2>/dev/null)" = "1" ] || exit 0
exec python3 - "$HOME/.claude/skills/romp-postal/SKILL.md" <<'PY'
import json, re, sys
try:
    txt = open(sys.argv[1], encoding="utf-8").read()
except OSError:
    sys.exit(0)
body = re.sub(r"\A---\n.*?\n---\n", "", txt, count=1, flags=re.S).strip()
if body:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": body}}))
PY
