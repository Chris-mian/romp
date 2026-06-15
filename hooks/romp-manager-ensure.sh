#!/usr/bin/env bash
# romp-manager-ensure.sh — SessionStart hook: make sure the romp kernel supervisor
# (romp-manager) is running, for romp sessions. No-op for non-romp sessions. Registered
# async so it never delays session start. This is what makes the dashboard "just there"
# without ever running `romp on`: starting any romp session auto-starts the supervisor
# (idempotent singleton), which owns + serves the kernel; front ends just attach.

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
manager="$(cd "$(dirname "$src")/../bin" 2>/dev/null && pwd)/romp-manager"
[[ -x "$manager" ]] || exit 0

"$manager" ensure >/dev/null 2>&1
exit 0
