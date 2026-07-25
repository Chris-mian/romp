#!/usr/bin/env bats

# Bare `romp` — the front door (2026-07-25: the shortest command does the most common thing):
# print the tokened dashboard URL AND try to open a browser on it (Jupyter's flow). The PRINT
# is the contract — it must always happen, even when no browser can be opened — because it is
# the user's guaranteed way in. On a remote/headless box it must NOT pretend to open anything,
# and must say how to reach the dashboard from a laptop instead. `romp url` stays the
# print-only variant for scripting (`--url` is its silent agent-facing alias), and the old
# `-l`/`--launch` spellings fail loudly naming bare `romp`.

ROMP_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    export XDG_STATE_HOME="$TEST_DIR/state"
    mkdir -p "$XDG_STATE_HOME/romp"
    printf 'TESTTOKEN123\n' > "$XDG_STATE_HOME/romp/serve-token"
    export ROMP_KERNEL_PORT=29855
    # a fake opener on PATH that records that it was called, instead of opening a real browser
    MOCK="$TEST_DIR/mock"; mkdir -p "$MOCK"
    export OPEN_LOG="$TEST_DIR/open.log"
    cat > "$MOCK/open" <<'MOCK'
#!/usr/bin/env bash
echo "$*" >> "$OPEN_LOG"
MOCK
    chmod +x "$MOCK/open"
    export PATH="$MOCK:$PATH"
    # default to a LOCAL machine (no ssh env, and a DISPLAY so Linux CI isn't treated as headless)
    unset SSH_CONNECTION SSH_TTY
    export DISPLAY=":0"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "bare romp prints the tokened URL" {
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:29855/?token=TESTTOKEN123"* ]]
}

@test "bare romp opens a browser on a local machine" {
    run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [ -s "$OPEN_LOG" ]
    grep -q "token=TESTTOKEN123" "$OPEN_LOG"
}

@test "bare romp on a remote/ssh box prints the URL but opens nothing" {
    SSH_CONNECTION="10.0.0.1 1 10.0.0.2 22" run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:29855/?token=TESTTOKEN123"* ]]   # the link is ALWAYS printed
    [[ "$output" == *"remote/headless"* ]]
    [[ "$output" == *"ssh -N -L"* ]]                                    # tells you how to reach it
    [ ! -s "$OPEN_LOG" ] || false                                       # never opened a browser
}

@test "bare romp still prints the URL when no opener exists" {
    # ROMP_OPENER= (set, empty) means "no opener", which PATH alone CANNOT express:
    # macOS ships /usr/bin/open, so the previous `rm $MOCK/open` + PATH=...:/usr/bin
    # form fell through to the REAL opener and launched an actual browser on every
    # macOS run. Linux has no `open`, which is why only macOS was affected.
    rm "$MOCK/open"
    ROMP_OPENER= run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:29855/?token=TESTTOKEN123"* ]]
    [[ "$output" == *"couldn't open a browser automatically"* ]]
}

@test "bare romp opens nothing when no opener exists, even where a real one is on PATH" {
    # The regression guard for the above: assert the real opener was never reached.
    # $MOCK/open stays in place and must NOT be called.
    ROMP_OPENER= run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [ ! -s "$OPEN_LOG" ] || false
}

@test "bare romp honours a custom ROMP_OPENER" {
    cat > "$MOCK/mybrowser" <<'MOCK'
#!/bin/sh
echo "$@" >> "$OPEN_LOG"
MOCK
    chmod +x "$MOCK/mybrowser"
    ROMP_OPENER=mybrowser run "$ROMP_SCRIPT"
    [ "$status" -eq 0 ]
    [[ "$(cat "$OPEN_LOG")" == *"token=TESTTOKEN123"* ]]
}

@test "bare romp fails loudly when no token has been minted yet" {
    rm "$XDG_STATE_HOME/romp/serve-token"
    run "$ROMP_SCRIPT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"no serve token"* ]]
}

@test "romp url stays print-only (no browser, bare URL for scripts)" {
    run "$ROMP_SCRIPT" url
    [ "$status" -eq 0 ]
    [ "$output" = "http://127.0.0.1:29855/?token=TESTTOKEN123" ]         # exactly the URL, nothing else
    [ ! -s "$OPEN_LOG" ] || false
}

@test "--url is a silent alias of romp url (agent-facing text names it)" {
    run "$ROMP_SCRIPT" --url
    [ "$status" -eq 0 ]
    [ "$output" = "http://127.0.0.1:29855/?token=TESTTOKEN123" ]
}

@test "the retired -l and --launch spellings fail naming bare romp" {
    for old in -l --launch; do
        run "$ROMP_SCRIPT" "$old"
        [ "$status" -eq 2 ]
        [[ "$output" == *"retired"* ]]
        [[ "$output" == *"the dashboard is now just: romp"* ]]
        [ ! -s "$OPEN_LOG" ] || false
    done
}
