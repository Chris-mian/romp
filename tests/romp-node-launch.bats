#!/usr/bin/env bats

# romp-node-launch execs romp-manager under a romp-OWNED copy of node ("romp-node")
# so macOS Full Disk Access is scoped to romp alone, not the shared "node" every
# script inherits (see the script's header for the TCC rationale). These exercise
# the copy/refresh behavior and the exec target with fake node + manager stand-ins.

setup() {
    TEST_DIR="$(mktemp -d)"
    LAUNCH="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-node-launch"
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    BIN="$TEST_DIR/bin"
    mkdir -p "$HOME" "$BIN"
    # Fake manager: just a marker file. It is never run directly — the fake node
    # (below) is what "runs" it, and it echoes the argv it was handed so the test
    # can see the manager path + args the launcher exec'd the copy with.
    MANAGER="$TEST_DIR/romp-manager"
    printf 'placeholder manager\n' > "$MANAGER"
    # Fake `node` (v1) first on PATH, so the launcher copies THIS, not the real
    # system node. Echoes a version marker + its args.
    printf '#!/bin/sh\necho "NODE_V1 ran: $*"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    export PATH="$BIN:$PATH"
    RN="$XDG_STATE_HOME/romp/romp-node"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "creates a romp-node copy of the system node and execs the manager under it" {
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    # The copy exists and is a byte-for-byte copy of the system node.
    [ -x "$RN" ]
    cmp -s "$BIN/node" "$RN"
    # It was the COPY (romp-node) that ran the manager, with our args.
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
}

@test "refreshes the copy when the system node changes (a node upgrade)" {
    "$LAUNCH" "$MANAGER" up >/dev/null
    cmp -s "$BIN/node" "$RN"
    # Simulate a node upgrade: different bytes at the same PATH entry.
    printf '#!/bin/sh\necho "NODE_V2 ran: $*"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    cmp -s "$BIN/node" "$RN"                       # copy now matches the NEW node
    [[ "$output" == *"NODE_V2 ran: $MANAGER up"* ]]
}

@test "a failed refresh never blocks startup — falls back to the existing copy" {
    if [ "$(id -u)" -eq 0 ]; then skip "unwritable-dir check needs a non-root user"; fi
    "$LAUNCH" "$MANAGER" up >/dev/null              # seed the copy (v1)
    [ -x "$RN" ]
    chmod 555 "$XDG_STATE_HOME/romp"               # block the refresh write
    printf '#!/bin/sh\necho "NODE_V2 ran: $*"\n' > "$BIN/node"   # node changed → refresh WOULD fire
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    chmod 755 "$XDG_STATE_HOME/romp"               # restore for teardown
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]] # ran via the kept v1 copy, not aborted
}
