#!/usr/bin/env bats

# Claude Code version floor (2.1.224): agent mail delivers through the CLI's per-session
# inbox socket from that version on; an older CLI still works but falls back to pane
# injection. bin/romp says so once at the user-facing entrypoints (bare `romp`, launches)
# and caches the `claude --version` answer keyed on the binary's mtime, so the ~1s node
# startup is paid once per installed binary, not on every romp command.

ROMP_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    export XDG_STATE_HOME="$TEST_DIR/state"
    mkdir -p "$XDG_STATE_HOME/romp"
    printf 'TESTTOKEN123\n' > "$XDG_STATE_HOME/romp/serve-token"
    export ROMP_KERNEL_PORT=29855
    MOCK="$TEST_DIR/mock"; mkdir -p "$MOCK"
    export PATH="$MOCK:$PATH"
    export ROMP_OPENER=            # never open a real browser
    export CLAUDE_CALLS="$TEST_DIR/claude-calls.log"
    unset SSH_CONNECTION SSH_TTY
    export DISPLAY=":0"
}

teardown() { rm -rf "$TEST_DIR"; }

_stub_claude() {   # $1 = the version the stub reports
    cat > "$MOCK/claude" <<STUB
#!/usr/bin/env bash
echo "called \$*" >> "$CLAUDE_CALLS"
echo "$1 (Claude Code)"
STUB
    chmod +x "$MOCK/claude"
}

@test "old claude: bare romp prints the upgrade nudge and still prints the URL" {
    _stub_claude "2.1.220"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"2.1.220"* ]]
    [[ "$output" == *"claude update"* ]]
    [[ "$output" == *"http://127.0.0.1:29855/?token=TESTTOKEN123"* ]]   # the URL contract holds
}

@test "new claude: no nudge" {
    _stub_claude "2.1.226"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" != *"claude update"* ]]
}

@test "equal to the floor counts as meeting it" {
    _stub_claude "2.1.224"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" != *"claude update"* ]]
}

@test "unparsable claude --version: silent, and nothing cached" {
    cat > "$MOCK/claude" <<'STUB'
#!/usr/bin/env bash
echo "flimflam"
STUB
    chmod +x "$MOCK/claude"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" != *"claude update"* ]]
    [ ! -f "$XDG_STATE_HOME/romp/claude-version" ]   # a transient failure must not stick
}

@test "the version answer is cached on the binary's mtime (one spawn, not two)" {
    _stub_claude "2.1.220"
    run "$ROMP_SCRIPT"; [ "$status" -eq 0 ]
    run "$ROMP_SCRIPT"; [ "$status" -eq 0 ]
    [ "$(grep -c 'called --version' "$CLAUDE_CALLS")" -eq 1 ]
    [[ "$output" == *"claude update"* ]]             # the nudge still fires, from the cache
}

@test "a replaced (updated) binary re-reads its version" {
    _stub_claude "2.1.220"
    run "$ROMP_SCRIPT"
    [[ "$output" == *"claude update"* ]]
    sleep 1                                          # whole-second mtimes on some filesystems
    _stub_claude "2.1.226"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" != *"claude update"* ]]
}

@test "old claude: nudge still fires when no serve token exists yet (fresh install)" {
    # A fresh install whose service hasn't minted a token is exactly the run that
    # should hear about an old Claude Code — the nudge precedes the token bail.
    rm -f "$XDG_STATE_HOME/romp/serve-token"
    _stub_claude "2.1.220"
    run "$ROMP_SCRIPT"
    [ "$status" -eq 1 ]                       # still the loud no-token bail
    [[ "$output" == *"claude update"* ]]      # but the floor line came first
    [[ "$output" == *"no serve token"* ]]
}
