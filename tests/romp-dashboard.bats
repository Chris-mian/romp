#!/usr/bin/env bats

# Resolve path to the dashboard script
DASHBOARD_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-dashboard"

setup() {
    TEST_DIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Helper — extract a function from the script without triggering tput/interactive code
extract_fn() {
    sed -n "/^${2}()/,/^}/p" "$1"
}

# ─── format_duration tests ────────────────────────────────────────────

@test "format_duration: 0 seconds" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" format_duration)"
    result=$(format_duration 0)
    [ "$result" = "0s" ]
}

@test "format_duration: 45 seconds" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" format_duration)"
    result=$(format_duration 45)
    [ "$result" = "45s" ]
}

@test "format_duration: 65 seconds → 1m" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" format_duration)"
    result=$(format_duration 65)
    [ "$result" = "1m" ]
}

@test "format_duration: 3700 seconds → 1h" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" format_duration)"
    result=$(format_duration 3700)
    [ "$result" = "1h" ]
}

@test "format_duration: 90000 seconds → 1d" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" format_duration)"
    result=$(format_duration 90000)
    [ "$result" = "1d" ]
}

# ─── shorten_dir tests ────────────────────────────────────────────────

@test "shorten_dir: home directory replaced with ~" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" shorten_dir)"
    result=$(shorten_dir "$HOME/foo")
    [ "$result" = "~/foo" ]
}

@test "shorten_dir: non-home path unchanged" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" shorten_dir)"
    result=$(shorten_dir "/other/path")
    [ "$result" = "/other/path" ]
}

# ─── identity_fg_escape tests ────────────────────────────────────────

@test "identity_fg_escape: hex → 24-bit foreground escape" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" identity_fg_escape)"
    result=$(identity_fg_escape '#D900FF')
    [[ "$result" == *'38;2;217;0;255'* ]]
}

@test "identity_fg_escape: colourN → 256-color foreground escape" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" identity_fg_escape)"
    result=$(identity_fg_escape colour33)
    [[ "$result" == *'38;5;33'* ]]
}

@test "identity_fg_escape: unparseable color → empty" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" identity_fg_escape)"
    result=$(identity_fg_escape 'nope')
    [ -z "$result" ]
}

# ─── clip tests ──────────────────────────────────────────────────────

@test "clip: short string is unchanged" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" clip)"
    result=$(clip "hello" 10)
    [ "$result" = "hello" ]
}

@test "clip: long string is truncated with an ellipsis" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" clip)"
    result=$(clip "hello world" 5)
    [ "$result" = "hell…" ]
}

@test "clip: zero/negative max yields empty" {
    eval "$(extract_fn "$DASHBOARD_SCRIPT" clip)"
    result=$(clip "hello" 0)
    [ -z "$result" ]
}
