#!/usr/bin/env bats

# The announcer (live tmux phrase) is DEPRECATED and DEFAULT OFF (the user 2026-07-24): the SDK
# backend is the normal way to run and the kernel's index judges write the durable captions, so no
# tmux path may spend tokens unless explicitly re-enabled. The switch flipped from opt-OUT
# (~/.claude/romp-summarize-off) to opt-IN (~/.claude/romp-summarize-on): absence of the -on file IS
# off. The gate sits before any tmux call or model spawn, so default-off costs nothing at all.

setup() {
    TEST_DIR="$(mktemp -d)"
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../hooks" && pwd)/romp-summarize.sh"
    export HOME="$TEST_DIR/home"; mkdir -p "$HOME/.claude"
    unset ROMP_SUMMARIZING || true
    export TMUX="fake-socket,1,0"       # LOOK like a tmux session so only the opt-in gate can bail first
    # a tripwire tmux on PATH: if the hook gets past the gate it will call this and we fail the test
    mkdir -p "$TEST_DIR/bin"
    printf '#!/bin/sh\necho TRIPPED > "%s/tripped"\nexit 1\n' "$TEST_DIR" > "$TEST_DIR/bin/tmux"
    chmod +x "$TEST_DIR/bin/tmux"
    export PATH="$TEST_DIR/bin:$PATH"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "default (no switch file) exits before touching tmux or any model" {
    run bash -c 'printf "{\"hook_event_name\":\"Stop\"}" | "$0"' "$HOOK"
    [ "$status" -eq 0 ]
    [ ! -f "$TEST_DIR/tripped" ]
}

@test "the retired opt-OUT file does not turn it on" {
    touch "$HOME/.claude/romp-summarize-off"
    run bash -c 'printf "{\"hook_event_name\":\"Stop\"}" | "$0"' "$HOOK"
    [ "$status" -eq 0 ]
    [ ! -f "$TEST_DIR/tripped" ]
}

@test "the opt-in file arms it (reaches the tmux lookup past the gate)" {
    touch "$HOME/.claude/romp-summarize-on"
    run bash -c 'printf "{\"hook_event_name\":\"Stop\"}" | "$0"' "$HOOK"
    [ "$status" -eq 0 ]                  # the tripwire tmux fails silently (errors swallowed by design)
    [ -f "$TEST_DIR/tripped" ]           # but its invocation PROVES the gate opened
}
