#!/usr/bin/env bash
# romp-postal-ensure.sh — SessionStart hook: make sure the Romp Postal Service
# bus is running, for romp sessions. No-op for non-romp sessions. Registered
# async so it never delays session start; the bus is a singleton (started once,
# shared by every romp session, and self-stops when the last one closes).

set -uo pipefail

[[ -n "${ROMP_SUMMARIZING:-}" ]] && exit 0
[[ -z "${TMUX:-}" ]] && exit 0

sess="$(tmux display-message -p '#S' 2>/dev/null || true)"
[[ -n "$sess" ]] || exit 0
[[ -n "$(tmux show -t "$sess" -v @romp 2>/dev/null || true)" ]] || exit 0

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

"$postal" ensure >/dev/null 2>&1
exit 0
