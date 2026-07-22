#!/usr/bin/env bats

# `romp launch` — the first-run entry point (2026-07-22): print the tokened dashboard URL AND try to
# open a browser on it (Jupyter's flow). The PRINT is the contract — it must always happen, even when
# no browser can be opened — because it is the user's guaranteed way in. On a remote/headless box it
# must NOT pretend to open anything, and must say how to reach the dashboard from a laptop instead.
# `romp --url` stays the print-only variant for scripting.

ROMP_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    export XDG_STATE_HOME="$TEST_DIR/state"
    mkdir -p "$XDG_STATE_HOME/romp"
    printf 'TESTTOKEN123\n' > "$XDG_STATE_HOME/romp/serve-token"
    export ROMP_KERNEL_PORT=7433
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

@test "romp launch prints the tokened URL" {
    run "$ROMP_SCRIPT" launch
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:7433/?token=TESTTOKEN123"* ]]
}

@test "romp launch opens a browser on a local machine" {
    run "$ROMP_SCRIPT" launch
    [ "$status" -eq 0 ]
    [ -s "$OPEN_LOG" ]
    grep -q "token=TESTTOKEN123" "$OPEN_LOG"
}

@test "romp launch on a remote/ssh box prints the URL but opens nothing" {
    SSH_CONNECTION="10.0.0.1 1 10.0.0.2 22" run "$ROMP_SCRIPT" launch
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:7433/?token=TESTTOKEN123"* ]]   # the link is ALWAYS printed
    [[ "$output" == *"remote/headless"* ]]
    [[ "$output" == *"ssh -N -L"* ]]                                    # tells you how to reach it
    [ ! -s "$OPEN_LOG" ] || false                                       # never opened a browser
}

@test "romp launch still prints the URL when no opener exists" {
    rm "$MOCK/open"
    PATH="$MOCK:/usr/bin:/bin" run "$ROMP_SCRIPT" launch
    [ "$status" -eq 0 ]
    [[ "$output" == *"http://127.0.0.1:7433/?token=TESTTOKEN123"* ]]
}

@test "romp launch fails loudly when no token has been minted yet" {
    rm "$XDG_STATE_HOME/romp/serve-token"
    run "$ROMP_SCRIPT" launch
    [ "$status" -ne 0 ]
    [[ "$output" == *"no serve token"* ]]
}

@test "romp --url stays print-only (no browser, bare URL for scripts)" {
    run "$ROMP_SCRIPT" --url
    [ "$status" -eq 0 ]
    [ "$output" = "http://127.0.0.1:7433/?token=TESTTOKEN123" ]         # exactly the URL, nothing else
    [ ! -s "$OPEN_LOG" ] || false
}
