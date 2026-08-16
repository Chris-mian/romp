#!/usr/bin/env bats

# Resolve path to the script under test
RESET_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-interrupt-reset"

setup() {
    TEST_DIR="$(mktemp -d)"
    MOCK_DIR="$TEST_DIR/mock"
    export MOCK_LOG="$TEST_DIR/mock.log"
    export MOCK_PANE_FILE="$TEST_DIR/pane.txt"
    mkdir -p "$MOCK_DIR"

    # ── Mock tmux ──────────────────────────────────────────────────────
    #   show -t NAME -v @romp         → $MOCK_ROMP  (default 1)
    #   show -t NAME -v @claude-state → $MOCK_STATE (default working)
    #   capture-pane -t NAME -p       → contents of $MOCK_PANE_FILE
    #   set ...                       → logged
    cat > "$MOCK_DIR/tmux" << 'MOCK'
#!/usr/bin/env bash
echo "tmux $*" >> "$MOCK_LOG"
case "$1" in
  show)
    case "$5" in
      @romp)         echo "${MOCK_ROMP-1}" ;;
      @claude-state) echo "${MOCK_STATE-working}" ;;
    esac ;;
  capture-pane) cat "$MOCK_PANE_FILE" 2>/dev/null ;;
esac
exit 0
MOCK
    chmod +x "$MOCK_DIR/tmux"

    export PATH="$MOCK_DIR:$PATH"
    export ROMP_INTERRUPT_DELAY=0   # don't actually sleep in tests
    export MOCK_ROMP=1
    export MOCK_STATE=working
}

teardown() {
    rm -rf "$TEST_DIR"
}

run_reset() { "$RESET_SCRIPT" "${1:-test}" 2>&1; }

# ─── Reset-on-landed-interrupt ────────────────────────────────────────

@test "working + idle pane (no indicator) → resets to waiting + blue dot" {
    printf '%s\n' 'Interrupted · What should Claude do instead?' '❯ ' '  ctx:3%   /tmp/x' > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    grep -q 'set -t test @claude-state waiting' "$MOCK_LOG"
    grep -q '@romp-emoji 🔵' "$MOCK_LOG"
}

@test "landed interrupt bumps @claude-state-since (counts as activity)" {
    # An interrupt is user interaction → it must reset the idle clock the dashboard,
    # timeline, and idle-dot watcher judge staleness by; otherwise interrupting a
    # long task would immediately read as stale.
    printf '%s\n' 'Interrupted · What should Claude do instead?' '❯ ' > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    grep -qE 'set -t test @claude-state-since [0-9]+' "$MOCK_LOG"
}

# ─── Leave genuinely-working sessions alone ───────────────────────────

@test "working + live timer on pane → does NOT reset" {
    printf '%s\n' '· Proofing… (3s · ↓ 41 tokens · thinking with xhigh effort)' '❯ ' > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    ! grep -q '@claude-state waiting' "$MOCK_LOG"
}

@test "working + 'esc to interrupt' on pane → does NOT reset" {
    printf '%s\n' '✶ Generating… (12s · ↑ 200 tokens · esc to interrupt)' > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    ! grep -q '@claude-state waiting' "$MOCK_LOG"
}

# ─── Guards ───────────────────────────────────────────────────────────

@test "non-romp session → no-op (never touches state)" {
    export MOCK_ROMP=""
    : > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    ! grep -q 'set -t test @claude-state' "$MOCK_LOG"
}

@test "already idle (state != working) → no-op" {
    export MOCK_STATE=waiting
    : > "$MOCK_PANE_FILE"
    run run_reset
    [ "$status" -eq 0 ]
    ! grep -q 'set -t test @claude-state' "$MOCK_LOG"
}

@test "missing session arg → errors out" {
    run "$RESET_SCRIPT"
    [ "$status" -ne 0 ]
}
