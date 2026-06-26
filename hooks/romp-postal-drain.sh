#!/usr/bin/env bash
# romp-postal-drain.sh — Stop hook: deliver Romp Postal Service mail at turn end.
#
# When a romp session finishes a turn, mail that arrived from peer sessions is
# fed back into the conversation, so the session "deals with" messages at the
# next turn boundary WITHOUT anything being typed into the prompt box — incoming
# mail can never clobber a draft. The loop guard (cap on rapid auto-deliveries)
# lives in the bus; this hook just wraps the drained text in a Stop-hook block.
#
# Must be async:false (an async hook can't return a decision). The
# ROMP_SUMMARIZING guard keeps the summarizer's nested `claude` calls out.
#
# Disable any time:  touch ~/.claude/romp-postal-off   (rm to re-enable)

set -uo pipefail

[[ -n "${ROMP_SUMMARIZING:-}" ]] && exit 0
[[ -f "$HOME/.claude/romp-postal-off" ]] && exit 0

input="$(cat)"
[[ "$input" =~ \"session_id\":\"([^\"]+)\" ]] || exit 0
sid="${BASH_REMATCH[1]}"

# Locate romp-postal-service via this hook's REAL (symlink-followed) path: the hook
# lives at dotfiles/claude/hooks/ and romp-postal-service at dotfiles/scripts/.
src="${BASH_SOURCE[0]}"
while [[ -L "$src" ]]; do
    tgt="$(readlink "$src")"
    case "$tgt" in
        /*) src="$tgt" ;;
        *)  src="$(cd "$(dirname "$src")" && pwd)/$tgt" ;;
    esac
done
postal="$(cd "$(dirname "$src")/../bin" 2>/dev/null && pwd)/romp-postal-service"
[[ -x "$postal" ]] || exit 0

# Loop-guarded, consuming drain (also autostarts the bus if needed).
msgs="$("$postal" drain --id "$sid" 2>/dev/null || true)"
[[ -n "${msgs//[[:space:]]/}" ]] || exit 0

# JSON-escape in pure bash (no Homebrew/python dependency in the hook path).
esc="$(printf '%s' "$msgs" | { s="$(cat)"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/\\n}"; s="${s//$'\t'/\\t}"; s="${s//$'\r'/}"
    printf '%s' "$s"; })"
printf '{"decision":"block","reason":"%s"}\n' "$esc"
exit 0
