#!/usr/bin/env bats

# Resolve path to the hook script under test
HOOK_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../hooks" && pwd)/tmux-status.sh"

setup() {
    TEST_DIR="$(mktemp -d)"
    MOCK_DIR="$TEST_DIR/mock"
    export MOCK_LOG="$TEST_DIR/mock.log"

    mkdir -p "$MOCK_DIR"

    # ── Mock tmux ──────────────────────────────────────────────────────
    cat > "$MOCK_DIR/tmux" << 'MOCK'
#!/usr/bin/env bash
echo "tmux $*" >> "$MOCK_LOG"
# display-message -p '#S' → return session name from env
if [[ "$1" == "display-message" && "$2" == "-p" && "$3" == "#S" ]]; then
    echo "${MOCK_SESSION_NAME:-test}"
fi
# show -t NAME -v @romp → the romp marker (empty = not a romp session)
if [[ "$1" == "show" && "$5" == "@romp" ]]; then
    echo "${MOCK_IS_ROMP-1}"
fi
# show -t NAME -v @claude-state → the PREVIOUS state (for the sticky-compaction guard)
if [[ "$1" == "show" && "$5" == "@claude-state" ]]; then
    echo "${MOCK_PREV_STATE-}"
fi
# show -t NAME -v @romp-session-id → durable session id (default EMPTY so existing tests write no
# states file; a test opts in by exporting MOCK_SESSION_ID + XDG_STATE_HOME)
if [[ "$1" == "show" && "$5" == "@romp-session-id" ]]; then
    echo "${MOCK_SESSION_ID-}"
fi
exit 0
MOCK
    chmod +x "$MOCK_DIR/tmux"

    # ── Mock romp-idle-dots ────────────────────────────────────────────
    # The hook ensures the idle-dot watcher when a session goes idle; mock it so
    # the test captures the call without spawning the real (forking) daemon.
    cat > "$MOCK_DIR/romp-idle-dots" << 'MOCK'
#!/usr/bin/env bash
echo "romp-idle-dots $*" >> "$MOCK_LOG"
exit 0
MOCK
    chmod +x "$MOCK_DIR/romp-idle-dots"

    export PATH="$MOCK_DIR:$PATH"
    export TMUX="fake"
    export MOCK_SESSION_NAME="test"
    export MOCK_IS_ROMP=1
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Helper — runs the hook with JSON on stdin
run_hook() {
    echo "$1" | "$HOOK_SCRIPT" 2>&1
}

# ─── Event mapping tests ──────────────────────────────────────────────

@test "SessionStart sets state to waiting" {
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state waiting' "$MOCK_LOG"
}

@test "UserPromptSubmit sets state to working" {
    run run_hook '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state working' "$MOCK_LOG"
}

@test "PostToolUse sets state to working" {
    run run_hook '{"hook_event_name":"PostToolUse","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state working' "$MOCK_LOG"
}

@test "Stop sets state to waiting" {
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state waiting' "$MOCK_LOG"
}

@test "PreCompact sets state to compacting" {
    run run_hook '{"hook_event_name":"PreCompact","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state compacting' "$MOCK_LOG"
}

@test "compacting is STICKY: a Stop mid-compaction keeps compacting (no split)" {
    export MOCK_PREV_STATE=compacting
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state compacting' "$MOCK_LOG"
    ! grep -q '@claude-state waiting' "$MOCK_LOG"
}

@test "compacting is STICKY against a working event too" {
    export MOCK_PREV_STATE=compacting
    run run_hook '{"hook_event_name":"PostToolUse","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state compacting' "$MOCK_LOG"
}

@test "PostCompact ENDS compacting (the only exit)" {
    export MOCK_PREV_STATE=compacting
    run run_hook '{"hook_event_name":"PostCompact","cwd":"/tmp/project"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state waiting' "$MOCK_LOG"
}

# ─── Notification mapping tests ───────────────────────────────────────

@test "Notification permission_prompt sets state to permission" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state permission' "$MOCK_LOG"
}

@test "Notification idle_prompt sets state to idle" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"idle_prompt","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t test @claude-state idle' "$MOCK_LOG"
}

@test "Notification with unknown type exits 0 and no tmux set calls" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"something_else","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q 'tmux set -t' "$MOCK_LOG"
}

# ─── Status-emoji tests (ghostty tab dot) ────────────────────────────

@test "working state sets the yellow tab dot" {
    run run_hook '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '@romp-emoji 🟡' "$MOCK_LOG"
}

@test "waiting state sets the blue tab dot" {
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '@romp-emoji 🔵' "$MOCK_LOG"
}

@test "permission state sets the red tab dot" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '@romp-emoji 🔴' "$MOCK_LOG"
}

@test "compacting sets the monochrome compress glyph, NOT a coloured dot (the user 2026-06-22)" {
    # compacting is a transient PROCESS, so it reads as ⇲ (a monochrome compress glyph) instead of
    # another colour dot — distinct from 🟡/🔴/🔵 at a glance.
    run run_hook '{"hook_event_name":"PreCompact","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '@romp-emoji ⇲' "$MOCK_LOG"
    ! grep -q '@romp-emoji 🟠' "$MOCK_LOG"
}

@test "idle state sets the blue tab dot" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"idle_prompt","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '@romp-emoji 🔵' "$MOCK_LOG"
}

# ─── Idle-dot watcher tests (fades the tab dot to ⚪ after 1h idle) ───

@test "Stop ensures the idle-dot watcher (session just went idle)" {
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'romp-idle-dots --ensure' "$MOCK_LOG"
}

@test "idle_prompt ensures the idle-dot watcher" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"idle_prompt","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'romp-idle-dots --ensure' "$MOCK_LOG"
}

@test "working does NOT ensure the watcher (high-frequency path stays cheap)" {
    run run_hook '{"hook_event_name":"PostToolUse","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q 'romp-idle-dots' "$MOCK_LOG"
}

# ─── Unknown event test ──────────────────────────────────────────────

@test "unknown event exits 0 with no tmux set calls" {
    run run_hook '{"hook_event_name":"SomeNewEvent","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q 'tmux set -t' "$MOCK_LOG"
}

# ─── Non-claude session test ─────────────────────────────────────────

@test "non-romp session (no @romp flag) exits early" {
    export MOCK_IS_ROMP=""
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q 'tmux set -t' "$MOCK_LOG"
}

# ─── No TMUX env test ────────────────────────────────────────────────

@test "no TMUX env exits early" {
    unset TMUX
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q 'tmux set -t' "$MOCK_LOG"
}

# ─── cwd extraction test ─────────────────────────────────────────────

@test "cwd is stored as @claude-dir" {
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/home/user/myproject"}'
    [ "$status" -eq 0 ]
    grep -q 'set -t test @claude-dir /home/user/myproject' "$MOCK_LOG"
}

@test "state-since timestamp is set" {
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'set -t test @claude-state-since' "$MOCK_LOG"
}

# ─── permission_mode extraction (feed block detection) ───────────────

@test "permission_mode is published as @claude-permission-mode (auto mode)" {
    run run_hook '{"hook_event_name":"Notification","notification_type":"permission_prompt","permission_mode":"acceptEdits","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'set -t test @claude-permission-mode acceptEdits' "$MOCK_LOG"
}

@test "permission_mode is published on ordinary events too (default mode)" {
    run run_hook '{"hook_event_name":"UserPromptSubmit","permission_mode":"default","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q 'set -t test @claude-permission-mode default' "$MOCK_LOG"
}

@test "absent permission_mode never writes the var (no clobber)" {
    run run_hook '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    ! grep -q '@claude-permission-mode' "$MOCK_LOG"
}

# ─── headless (no-tmux) backend tests ─────────────────────────────────
# A session launched by a non-tmux backend exports ROMP_SESSION_ID; the hook
# must write the durable states/<sid>.jsonl record and touch tmux not at all.

@test "headless: ROMP_SESSION_ID writes the durable state record, no tmux" {
    unset TMUX
    export ROMP_SESSION_ID="headless-sid-1"
    export XDG_STATE_HOME="$TEST_DIR/state"
    run run_hook '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    grep -q '"state":"working"' "$TEST_DIR/state/romp/states/headless-sid-1.jsonl"
    ! grep -q 'tmux set -t' "$MOCK_LOG"
}

@test "headless: repeated same-state events append only one record" {
    unset TMUX
    export ROMP_SESSION_ID="headless-sid-2"
    export XDG_STATE_HOME="$TEST_DIR/state"
    run_hook '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}'
    run_hook '{"hook_event_name":"PostToolUse","cwd":"/tmp"}'
    [ "$(wc -l < "$TEST_DIR/state/romp/states/headless-sid-2.jsonl")" -eq 1 ]
    run_hook '{"hook_event_name":"Stop","cwd":"/tmp"}'
    [ "$(wc -l < "$TEST_DIR/state/romp/states/headless-sid-2.jsonl")" -eq 2 ]
}

@test "headless: no ROMP_SESSION_ID still exits silently" {
    unset TMUX
    unset ROMP_SESSION_ID
    export XDG_STATE_HOME="$TEST_DIR/state"
    run run_hook '{"hook_event_name":"SessionStart","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    [ ! -d "$TEST_DIR/state/romp/states" ]
}

# ─── awaiting overlay from the Stop hook's background_tasks (tmux backend) ─────
# At turn-end the hook reads the Stop payload's `background_tasks` (run_in_background work still
# outstanding) and writes the same {"awaiting":bool,"why":…} overlay the SDK backend writes, which the
# kernel's _session_awaiting reads for the ⏳ badge. Tmux-only, transition-only.

@test "Stop with background_tasks writes an awaiting:true overlay" {
    export MOCK_SESSION_ID="tmux-aw-1"
    export XDG_STATE_HOME="$TEST_DIR/state"
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[{"id":"t1"}]}'
    [ "$status" -eq 0 ]
    grep -q '"awaiting":true' "$TEST_DIR/state/romp/states/tmux-aw-1.jsonl"
}

@test "Stop with EMPTY background_tasks writes no awaiting record (nothing to clear)" {
    export MOCK_SESSION_ID="tmux-aw-2"
    export XDG_STATE_HOME="$TEST_DIR/state"
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[]}'
    [ "$status" -eq 0 ]
    ! grep -q '"awaiting"' "$TEST_DIR/state/romp/states/tmux-aw-2.jsonl"
}

@test "awaiting clears (false) only after it was true — transition-only, no dupes" {
    export MOCK_SESSION_ID="tmux-aw-3"
    export XDG_STATE_HOME="$TEST_DIR/state"
    f="$TEST_DIR/state/romp/states/tmux-aw-3.jsonl"
    run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[{"id":"t1"}]}'   # → true
    run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[{"id":"t1"}]}'   # still running → NO dup
    [ "$(grep -c '"awaiting":true' "$f")" -eq 1 ]
    run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[]}'              # finished → clear
    grep -q '"awaiting":false' "$f"
    [ "$(grep -c '"awaiting"' "$f")" -eq 2 ]                                              # exactly true then false
}

@test "headless (SDK) sessions get NO tmux-side awaiting overlay (the SDK backend writes its own)" {
    unset TMUX
    export ROMP_SESSION_ID="headless-aw-1"
    export XDG_STATE_HOME="$TEST_DIR/state"
    run run_hook '{"hook_event_name":"Stop","cwd":"/tmp","background_tasks":[{"id":"t1"}]}'
    [ "$status" -eq 0 ]
    ! grep -q '"awaiting"' "$TEST_DIR/state/romp/states/headless-aw-1.jsonl"
}
