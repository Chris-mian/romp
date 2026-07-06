#!/usr/bin/env bats

# romp-service generates the right login-agent unit per platform (launchd plist on
# macOS, systemd --user on Linux). ROMP_SERVICE_NO_LOAD asserts unit content without
# touching launchctl/systemctl; ROMP_OS_OVERRIDE exercises both platforms on one host.

setup() {
    TEST_DIR="$(mktemp -d)"
    SVC="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-service"
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    export ROMP_LAUNCHD_DIR="$TEST_DIR/LaunchAgents"
    export ROMP_SYSTEMD_DIR="$TEST_DIR/systemd"
    export ROMP_SERVICE_NO_LOAD=1                      # write the unit, don't load it
    export ROMP_MANAGER_BIN="$TEST_DIR/romp-manager"   # stable path to assert in the unit
    mkdir -p "$HOME"
    # A stand-in "node" so the macOS install's romp-node copy is hermetic + fast
    # (a byte-copy of THIS, asserted by content) rather than the real multi-MB node.
    printf '#!/bin/sh\necho fake-node "$@"\n' > "$TEST_DIR/fake-node"
    chmod +x "$TEST_DIR/fake-node"
    export ROMP_NODE_SRC="$TEST_DIR/fake-node"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "install (macOS): launchd plist runs 'romp-manager up' at login, kept alive" {
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    [ -f "$plist" ]
    grep -q "<string>$ROMP_MANAGER_BIN</string>" "$plist"
    grep -q "<string>up</string>" "$plist"
    grep -q "RunAtLoad" "$plist"
    grep -q "KeepAlive" "$plist"
}

@test "install (macOS): login agent runs the manager under the romp-node copy (FDA identity)" {
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    local launcher; launcher="$(dirname "$SVC")/romp-node-launch"
    # ProgramArguments must be: <launcher> <manager> up — the launcher FIRST, so
    # macOS keys the Full Disk Access grant to romp-node, not the shared "node".
    grep -Fq "<string>$launcher</string>" "$plist"
    grep -Fq "<string>$ROMP_MANAGER_BIN</string>" "$plist"
    grep -q "<string>up</string>" "$plist"
    local lline mline
    lline="$(grep -Fn "$launcher" "$plist" | head -1 | cut -d: -f1)"
    mline="$(grep -Fn "$ROMP_MANAGER_BIN" "$plist" | head -1 | cut -d: -f1)"
    [ "$lline" -lt "$mline" ]
    # The romp-node copy was created as a byte-for-byte copy of the source node.
    local rn="$XDG_STATE_HOME/romp/romp-node"
    [ -x "$rn" ]
    cmp -s "$ROMP_NODE_SRC" "$rn"
    # install tells the user the exact path to grant Full Disk Access to.
    [[ "$output" == *"$rn"* ]]
    [[ "$output" == *"Full Disk Access"* ]]
}

@test "install (Linux): systemd unit is unchanged — no romp-node launcher (no TCC there)" {
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    grep -q "ExecStart=$ROMP_MANAGER_BIN up" "$unit"
    ! grep -q "romp-node-launch" "$unit"
    [ ! -e "$XDG_STATE_HOME/romp/romp-node" ]
}

@test "install (Linux): systemd --user service runs 'romp-manager up', restart=always" {
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    [ -f "$unit" ]
    grep -q "ExecStart=$ROMP_MANAGER_BIN up" "$unit"
    grep -q "Restart=always" "$unit"
    grep -q "WantedBy=default.target" "$unit"
}

@test "status reflects install; uninstall removes the unit (macOS)" {
    ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [[ "$output" == *"not installed"* ]]
    ROMP_OS_OVERRIDE=Darwin "$SVC" install >/dev/null
    ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [[ "$output" == *"installed:"* ]]
    ROMP_OS_OVERRIDE=Darwin run "$SVC" uninstall
    [ "$status" -eq 0 ]
    [ ! -f "$ROMP_LAUNCHD_DIR/com.romp.manager.plist" ]
}

@test "unsupported OS fails cleanly" {
    ROMP_OS_OVERRIDE=Plan9 run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"unsupported OS"* ]]
}
