#!/usr/bin/env bats

# `romp-manager ensure` is the no-`romp on` auto-start: the SessionStart hook
# (romp-manager-ensure.sh) calls it so romp usage brings up the supervisor.
# It must be idempotent (no second manager) and non-blocking (spawns detached).

setup() {
    TEST_DIR="$(mktemp -d)"
    MGR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-manager"
    # Fake kernel launcher: stay alive without binding a real port (we assert on the
    # manager's control endpoint, not a live kernel).
    FAKE="$TEST_DIR/fake-serve"
    printf '#!/usr/bin/env bash\nexec sleep 30\n' > "$FAKE"
    chmod +x "$FAKE"
    CPORT=7561 MPORT=7562
}

teardown() {
    # Graceful stop, then reap the detached manager (it is orphaned, not our child).
    curl -fsS -X POST "http://127.0.0.1:${CPORT:-0}/stop" >/dev/null 2>&1 || true
    [[ -n "${MGR_PID:-}" ]] && kill "$MGR_PID" 2>/dev/null || true
    rm -rf "$TEST_DIR"
}

@test "ensure: idempotent, non-blocking auto-start of the supervisor" {
    command -v node >/dev/null 2>&1 || skip "node not available"
    command -v curl >/dev/null 2>&1 || skip "curl not available"

    # Nothing running yet → status fails.
    run env ROMP_MANAGER_PORT=$CPORT node "$MGR" status
    [ "$status" -eq 1 ]

    # ensure returns 0 immediately (non-blocking) and spawns a DETACHED manager.
    run env ROMP_MANAGER_PORT=$CPORT ROMP_SERVE_PORT=$MPORT ROMP_SERVE_BIN="$FAKE" node "$MGR" ensure
    [ "$status" -eq 0 ]

    # The detached manager comes up on the control port.
    local i
    for i in $(seq 1 40); do
        curl -fsS "http://127.0.0.1:$CPORT/status" >/dev/null 2>&1 && break
        sleep 0.1
    done
    run curl -fsS "http://127.0.0.1:$CPORT/status"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"id":"main"'* ]]
    MGR_PID="$(printf '%s' "$output" | grep -oE '"pid":[ ]*[0-9]+' | head -1 | grep -oE '[0-9]+')"

    # A second ensure is a harmless no-op; the manager stays up (no double-start).
    run env ROMP_MANAGER_PORT=$CPORT ROMP_SERVE_PORT=$MPORT ROMP_SERVE_BIN="$FAKE" node "$MGR" ensure
    [ "$status" -eq 0 ]
    run curl -fsS "http://127.0.0.1:$CPORT/status"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"id":"main"'* ]]
}

@test "manager bootstraps a tmux server (launchd-rooted) with exit-empty off" {
    command -v node >/dev/null 2>&1 || skip "node not available"

    # Fake tmux on PATH that records its args — so we assert WHAT the manager asks of tmux at startup,
    # without touching the real tmux server. (The fix: a launchd-rooted server so new sessions don't
    # inherit a terminal's TCC identity → the "VS Code wants to access" prompt.)
    BIN="$TEST_DIR/bin"; mkdir -p "$BIN"
    CALLS="$TEST_DIR/tmux-calls"
    printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "%s"\nexit 0\n' "$CALLS" > "$BIN/tmux"
    chmod +x "$BIN/tmux"

    # Run `up` directly on a UNIQUE port (so it doesn't no-op against the other test's manager); the
    # manager calls startTmuxServer() at startup, before it ever binds the control port.
    env PATH="$BIN:$PATH" ROMP_MANAGER_PORT=7571 ROMP_SERVE_PORT=7572 ROMP_SERVE_BIN="$FAKE" node "$MGR" up >/dev/null 2>&1 &
    MGR_PID=$!
    local i
    for i in $(seq 1 50); do [ -f "$CALLS" ] && break; sleep 0.1; done
    kill "$MGR_PID" 2>/dev/null || true

    # startManager() → startTmuxServer() ran our fake tmux with start-server + exit-empty off.
    [ -f "$CALLS" ]
    grep -q "start-server" "$CALLS"
    grep -q "exit-empty off" "$CALLS"
}

@test "a leaked \$TMUX never reaches the manager or its kernels" {
    command -v node >/dev/null 2>&1 || skip "node not available"

    # The 2026-07-20 anchor-clobber chain: a manual `romp-manager up` from inside tmux leaked
    # $TMUX to kernels + SDK sessions, whose tmux-status hooks then hijacked the ATTACHED
    # session's @romp-session-id (live session flapping "dead" -> bogus revive). The manager
    # must scrub TMUX/TMUX_PANE from its own env before any kernel spawns.
    local envdump="$TEST_DIR/kernel-env"
    printf '#!/usr/bin/env bash\nenv > "%s"\nexec sleep 30\n' "$envdump" > "$FAKE"
    chmod +x "$FAKE"
    env TMUX="/tmp/tmux-000/default,99999,7" TMUX_PANE="%7" \
        ROMP_MANAGER_PORT=7581 ROMP_SERVE_PORT=7582 ROMP_SERVE_BIN="$FAKE" \
        node "$MGR" up >/dev/null 2>&1 &
    MGR_PID=$!
    local i
    for i in $(seq 1 50); do [ -s "$envdump" ] && break; sleep 0.1; done
    curl -fsS -X POST "http://127.0.0.1:7581/stop" >/dev/null 2>&1 || true
    [ -s "$envdump" ]
    ! grep -q '^TMUX=' "$envdump"
    ! grep -q '^TMUX_PANE=' "$envdump"
    grep -q '^ROMP_SERVE_BIN=' "$envdump"   # the dump is real: other env DID flow through
}
