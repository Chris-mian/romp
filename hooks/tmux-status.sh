#!/usr/bin/env bash
set -euo pipefail

# Two membership paths (the same hook serves both session backends):
#   tmux     — the session lives in a tmux session tagged @romp; durable state
#              goes to states/<sid>.jsonl AND the tmux display vars
#              (@claude-state, @romp-emoji, …) that the status line / dashboard
#              / ghostty dot render.
#   headless — the launcher exported ROMP_SESSION_ID (no tmux); only the
#              durable states/<sid>.jsonl record is written. Every tmux-var
#              write below is display-only and skipped.
DISPLAY_TMUX=0
session_name=""
if [[ -n "${TMUX:-}" ]]; then
    session_name=$(tmux display-message -p '#S')
    # Only act on romp sessions — identified by the @romp flag, not the name.
    is_romp=$(tmux show -t "$session_name" -v @romp 2>/dev/null || true)
    [[ -n "$is_romp" ]] || exit 0
    DISPLAY_TMUX=1
elif [[ -n "${ROMP_SESSION_ID:-}" ]]; then
    session_name="${ROMP_SESSION_NAME:-$ROMP_SESSION_ID}"
else
    exit 0
fi

# Parse hook JSON with pure bash regex — no jq, no process spawns
input=$(cat)
[[ "$input" =~ \"hook_event_name\":\"([^\"]+)\" ]] && EVENT="${BASH_REMATCH[1]}" || EVENT=""
[[ "$input" =~ \"notification_type\":\"([^\"]+)\" ]] && NOTIF_TYPE="${BASH_REMATCH[1]}" || NOTIF_TYPE=""
[[ "$input" =~ \"cwd\":\"([^\"]+)\" ]] && WORK_DIR="${BASH_REMATCH[1]}" || WORK_DIR=""
[[ "$input" =~ \"source\":\"([^\"]+)\" ]] && SOURCE="${BASH_REMATCH[1]}" || SOURCE=""
# Current permission mode (default|plan|acceptEdits|auto|dontAsk|bypassPermissions).
# Not every event carries it — leave empty when absent so we never clobber a good
# value with "". Consumers use it to tell a GENUINE permission block from auto
# mode's transient permission notifications (which the classifier allows moments
# later) — an event-based replacement for the feed's old time-threshold debounce.
[[ "$input" =~ \"permission_mode\":\"([^\"]+)\" ]] && PERM_MODE="${BASH_REMATCH[1]}" || PERM_MODE=""

case "$EVENT" in
    SessionStart)          state="waiting" ;;
    UserPromptSubmit)      state="working" ;;
    PostToolUse)           state="working" ;;
    Stop)                  state="waiting" ;;
    PreCompact)            state="compacting" ;;   # context compaction STARTED (manual /compact or auto)
    PostCompact)           state="waiting" ;;      # compaction done → idle for next prompt (any real event re-corrects)
    Notification)
        case "$NOTIF_TYPE" in
            permission_prompt) state="permission" ;;
            idle_prompt)       state="idle" ;;
            *) exit 0 ;;
        esac ;;
    *) exit 0 ;;
esac

# Status emoji for the ghostty tab dot (tmux.conf set-titles-string reads
# @romp-emoji). Mirrors the dashboard's state→color: 🔵 ready (waiting/
# idle), 🟡 working, 🔴 awaiting (permission). Updated here on every event
# so the dot tracks Claude's live status. (A fourth dot, ⚪ inactive, is set
# NOT here but by scripts/romp-idle-dots once a ready session sits idle > 1h —
# the tab analog of the dashboard/timeline fade; the next event resets it here.)
# Compacting is the ODD ONE OUT on purpose: a monochrome compress glyph (⇲, NOT
# a coloured dot) so a transient context-compaction reads as a PROCESS, not as
# another live-status colour (the user 2026-06-22).
case "$state" in
    working)      emoji="🟡" ;;
    permission)   emoji="🔴" ;;
    compacting)   emoji="⇲" ;;    # ⇲ context compacting (monochrome — not a status colour)
    *)            emoji="🔵" ;;   # waiting / idle
esac

now=$(date +%s)

# Append a state-transition log (only on an actual change) so the timeline can
# reconstruct HISTORICAL state intervals — e.g. how long a session sat AWAITING
# your input — not just the current @claude-state-since. One small JSONL per
# session; this is the DURABLE record (written on both backends — the tmux vars
# below are display only).
if [[ "$DISPLAY_TMUX" == 1 ]]; then
    sid=$(tmux show -t "$session_name" -v @romp-session-id 2>/dev/null || true)
    prev=$(tmux show -t "$session_name" -v @claude-state 2>/dev/null || true)
else
    sid="$ROMP_SESSION_ID"
    # No tmux var to diff against — read the last recorded state instead.
    prev=$(tail -1 "${XDG_STATE_HOME:-$HOME/.local/state}/romp/states/$sid.jsonl" 2>/dev/null \
        | sed -n 's/.*"state":"\([^"]*\)".*/\1/p' || true)
fi
# Compaction is STICKY: once PreCompact set state=compacting, ONLY PostCompact ends it. A postal
# message (or any other hook) firing mid-compaction must NOT clobber @claude-state back to
# working/waiting — that split the timeline's compacting span and stopped the live % partway (the
# user). With this guard prev==state==compacting, so no spurious transition is logged and the span
# stays continuous. A missed PostCompact can't strand it: romp-idle-dots heals a stuck 'compacting'.
if [[ "$prev" == "compacting" && "$EVENT" != "PostCompact" ]]; then
    state="compacting"; emoji="⇲"
fi
if [[ -n "$sid" && "$prev" != "$state" ]]; then
    sdir="${XDG_STATE_HOME:-$HOME/.local/state}/romp/states"
    mkdir -p "$sdir"
    printf '{"t":%s,"state":"%s"}\n' "$now" "$state" >> "$sdir/$sid.jsonl"
fi

# Everything below is DISPLAY: tmux vars, the ghostty dot watcher, the /color
# push. A headless session has none of these surfaces.
[[ "$DISPLAY_TMUX" == 1 ]] || exit 0

# AWAITING overlay (tmux backend, the user 2026-06-22): at turn-end, mirror what the SDK backend's Stop
# hook does for its own sessions (bin/romp_sdk_backend.py append_awaiting) — read the Stop payload's
# `background_tasks` (run_in_background work still outstanding) and write the SAME {"awaiting":bool,"why":…}
# overlay to states/<sid>.jsonl, which the kernel's _session_awaiting reads (idle-only) for the ⏳ awaiting
# badge + the auto-nudge exemption. Tmux-only (the SDK backend writes its own, so no double-write).
# Transition-only — emit a row only when true↔false actually changes — so the log stays lean. A FOREGROUND
# subagent keeps the turn open (state=working), so it never reaches this idle-time overlay; only a genuinely
# backgrounded task survives the Stop.
if [[ "$EVENT" == "Stop" && -n "$sid" ]]; then
    if [[ "$input" =~ \"background_tasks\":[[:space:]]*\[[[:space:]]*[^][:space:]] ]]; then
        awaiting="true"
    else
        awaiting="false"
    fi
    sdir="${XDG_STATE_HOME:-$HOME/.local/state}/romp/states"
    prev_aw=$(grep -oE '"awaiting":(true|false)' "$sdir/$sid.jsonl" 2>/dev/null | tail -1 | sed 's/.*://' || true)
    if [[ "$awaiting" != "$prev_aw" && ( "$awaiting" == "true" || "$prev_aw" == "true" ) ]]; then
        mkdir -p "$sdir"
        if [[ "$awaiting" == "true" ]]; then
            printf '{"t":%s,"awaiting":true,"why":"background work still running"}\n' "$now" >> "$sdir/$sid.jsonl"
        else
            printf '{"t":%s,"awaiting":false}\n' "$now" >> "$sdir/$sid.jsonl"
        fi
    fi
fi

# Keep the timer-side watcher alive (scripts/romp-idle-dots): Claude fires NO
# event while a session sits quiet, so nothing else would ever fade its ghostty
# tab dot to ⚪ — and NO hook at all on an Esc-interrupt, so nothing else would
# ever clear a stranded @claude-state=working (the watcher heals both). Ensured
# on waiting/idle AND on UserPromptSubmit (once per typed prompt — a turn can
# only get stuck after a prompt starts it) — never the high-frequency
# PostToolUse path. The watcher self-exits once no romp session remains.
if [[ "$state" == "waiting" || "$state" == "idle" || "$EVENT" == "UserPromptSubmit" ]]; then
    command -v romp-idle-dots >/dev/null 2>&1 && romp-idle-dots --ensure >/dev/null 2>&1 || true
fi

# Store session state for dashboard + tab dot — single tmux invocation
if [[ -n "$WORK_DIR" ]]; then
    tmux set -t "$session_name" @claude-state "$state" \;\
         set -t "$session_name" @claude-state-since "$now" \;\
         set -t "$session_name" @romp-emoji "$emoji" \;\
         set -t "$session_name" @claude-dir "$WORK_DIR"
else
    tmux set -t "$session_name" @claude-state "$state" \;\
         set -t "$session_name" @claude-state-since "$now" \;\
         set -t "$session_name" @romp-emoji "$emoji"
fi

# Publish the permission mode for the feed's block detection (see PERM_MODE
# above). Only when this event actually carried it — an unconditional set would
# write "" on the events that omit the field and erase the last known mode.
if [[ -n "$PERM_MODE" ]]; then
    tmux set -t "$session_name" @claude-permission-mode "$PERM_MODE"
fi

# Clear the transient "←/→ peer:" top-line message prefix when a NORMAL prompt
# starts — but KEEP it when the prompt is an injected peer-message banner (which
# carries a long "####…" rule), so the label rides along with that message's turn.
# (Set by scripts/romp-postal-service _set_msg_prefix; rendered by status-right.)
if [[ "$EVENT" == "UserPromptSubmit" && "$input" != *"####################"* ]]; then
    tmux set -t "$session_name" @romp-msg-dir "" \;\
         set -t "$session_name" @romp-msg-peer "" \;\
         set -t "$session_name" @romp-msg-id-cur "" || true
fi

# On a FRESH session start, push Claude's /color so the pill (approximately)
# matches the romp identity color. Only source=startup: on resume Claude is still
# loading the transcript and the keystrokes get dropped, and the resumed session
# restores its own color anyway. The name is handled separately (--name at launch
# / resume, and /rename on the after-rename hook). No-op for non-romp sessions.
if [[ "$EVENT" == "SessionStart" && "$SOURCE" == "startup" ]]; then
    # Resolve romp via PATH, falling back to the repo this hook lives in
    # (readlink -f follows the ~/.claude/hooks symlink back to romp/hooks/).
    ROMP_BIN="$(command -v romp || true)"
    if [[ -z "$ROMP_BIN" ]]; then
        SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
        ROMP_BIN="$(dirname "$SELF")/../bin/romp"
    fi
    "$ROMP_BIN" _color "$session_name" 2>/dev/null || true
fi
