#!/usr/bin/env bats

# `romp --debug [on|off|status]` persists judge debug mode (STATE/debug-mode.json).
# When on, judge-failure rows carry the failing call's input + reply and the feed
# joins them onto each card's modal (the user 2026-07-09). The kernel + judge read
# the file live (mtime-cached), so the toggle needs no restart.

BIN="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)"
ROMP_SCRIPT="$BIN/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    mkdir -p "$XDG_STATE_HOME/romp"
}

teardown() {
    rm -rf "$TEST_DIR"
}

@test "romp --debug: on writes the flag, status reports it, off clears it" {
    run "$ROMP_SCRIPT" --debug status
    [ "$status" -eq 0 ]
    [[ "$output" == *"off"* ]]

    run "$ROMP_SCRIPT" --debug on
    [ "$status" -eq 0 ]
    grep -q 'true' "$XDG_STATE_HOME/romp/debug-mode.json"

    run "$ROMP_SCRIPT" --debug status
    [[ "$output" == *"debug mode: on"* ]]

    run "$ROMP_SCRIPT" --debug off
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/debug-mode.json" ]

    run "$ROMP_SCRIPT" --debug status
    [[ "$output" == *"debug mode: off"* ]]
}

@test "romp --debug: an unknown subcommand exits 2 with usage" {
    run "$ROMP_SCRIPT" --debug bogus
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp --debug"* ]]
}
