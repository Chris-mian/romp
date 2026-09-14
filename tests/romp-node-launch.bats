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
    # The launcher honors both; a developer shell exporting them would point every
    # case here at a real service.env or state dir.
    unset ROMP_SERVICE_ENV_FILE ROMP_STATE_DIR
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

# ── the copy that cannot run (issue 1600) ──────────────────────────────────────────────────
# A node whose shared libnode is referenced relative to its own install (Homebrew's build, a version
# manager's shim) copies fine and then dies at exec from the copy; the launcher trusted "executable" and
# exec'd it, and the login agent's KeepAlive respawned that abort forever. The copy is probed first.
_path_bound_node() {   # $1 the path the fake node must be run FROM; anywhere else it dies like dyld would
    cat > "$1" <<EOF
#!/bin/sh
case "\$0" in
  "$1") echo "NODE_V1 ran: \$*" ;;
  *) echo "dyld[4242]: Library not loaded: @rpath/libnode.dylib" >&2; exit 134 ;;
esac
EOF
    chmod +x "$1"
}

@test "a copy that cannot run from its new path never takes the manager down: the system node runs it, and the log says why" {
    _path_bound_node "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]          # the manager came up, on the system node
    [[ "$output" == *"cannot run here"* ]]                    # said once on stderr (the manager log)
    [[ "$output" == *"ROMP_NO_NODE_COPY=1"* ]]                # with the way to stop the copy attempts
    [[ "$output" != *"Library not loaded"* ]]                 # the probe's own noise is dropped
}

@test "ROMP_NO_NODE_COPY=1 in service.env, the route the message names, skips the copy: the manager runs on the system node" {
    # round two of issue 1600: the launcher read the variable before it parsed service.env, so the one route a
    # launchd-started launcher has did nothing; the file is parsed first now. The environment is UNSET here.
    export ROMP_SERVICE_ENV_FILE="$TEST_DIR/service.env"
    printf 'ROMP_NO_NODE_COPY=1\n' > "$ROMP_SERVICE_ENV_FILE"
    unset ROMP_NO_NODE_COPY
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    [ ! -e "$RN" ]                                            # no copy was made
    [[ "$output" != *"cannot run here"* ]]                    # and nothing to say about one
    # …and a quoted value, the shape the kernel's reader and systemd accept, reads the same
    printf 'ROMP_NO_NODE_COPY="1"\n' > "$ROMP_SERVICE_ENV_FILE"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [ ! -e "$RN" ]
}

@test "ROMP_NO_NODE_COPY=1 in the environment skips the copy too (the second route)" {
    ROMP_NO_NODE_COPY=1 run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    [ ! -e "$RN" ]
}

@test "a copy that dies by SIGNAL from its new path (the real dyld abort) leaves no job-status line in the log" {
    # dyld kills the process with SIGABRT, and coreutils timeout re-raises a child's signal on itself; a subshell
    # whose last command dies by a signal dies by it too, and the launcher's shell then printed "Aborted (core
    # dumped)" on its stderr, the manager log. The probe's subshell ends in an explicit exit, so the death is a
    # code, and only the launcher's own message remains.
    cat > "$BIN/node" <<EOF
#!/bin/sh
case "\$0" in
  "$BIN/node") echo "NODE_V1 ran: \$*" ;;
  *) kill -ABRT \$\$ ;;
esac
EOF
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    [[ "$output" == *"cannot run here"* ]]
    [[ "$output" != *"Aborted"* ]]
    [[ "$output" != *"core dumped"* ]]
}

@test "the watchdog path (no timeout on PATH) leaves no ten-second sleep behind after a fast probe" {
    # a stock mac has no coreutils timeout, so the launcher's watchdog subshell is the normal path there; killed
    # after a fast probe, it used to leave its sleep 10 orphaned, one per launch. The launcher runs in its own
    # session (setsid), so the orphan, if any, would still be in that process group after the launcher exits.
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    local bare="$TEST_DIR/bare"; mkdir -p "$bare"
    local t
    for t in sh cmp cp chmod mv mkdir rm sleep ps setsid; do ln -s "$(command -v "$t")" "$bare/$t"; done
    ln -s "$BIN/node" "$bare/node"
    PATH="$bare" run setsid -w sh -c 'printf "%s\n" "$$" > "$1"; exec "$2" "$3" up' _ "$TEST_DIR/pgid" "$LAUNCH" "$MANAGER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    [ -n "$pgid" ]
    # nothing of the launcher's session survives it: no sleep, no watchdog subshell
    run bash -c 'ps -eo pgid=,comm= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [ -z "$output" ]
}

@test "service.env: KEY=VALUE lines reach the manager; comments and junk skipped" {
    # Parity with the systemd unit's EnvironmentFile=- : the launcher parses
    # (never sources) ~/.config/romp/service.env before exec'ing the manager.
    export XDG_CONFIG_HOME="$HOME/.config"
    mkdir -p "$XDG_CONFIG_HOME/romp"
    {
        echo '# comment'
        echo 'ROMP_TEST_SECRET=hunter2'
        echo ''
        echo 'not a valid line'
    } > "$XDG_CONFIG_HOME/romp/service.env"
    # Fake node prints the env var the launcher should have exported.
    printf '#!/bin/sh\necho "SECRET=[$ROMP_TEST_SECRET] ran: $*"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"SECRET=[hunter2] ran: $MANAGER up"* ]]
}

@test "service.env: one layer of matching quotes comes off the value and whitespace around it is dropped; edge cases follow the kernel's reader" {
    # Every reader of this file strips one layer of matching quotes and discards
    # whitespace around the value (a trailing space after the closing quote, a CRLF
    # line ending): systemd's EnvironmentFile=, the kernel's own reader
    # (kernel/keysource.py _assignments) and this launcher. Without that a quoted
    # value means one thing on Linux and another on macOS. The edge cases follow
    # the kernel's reader, not systemd, which parses a value like a shell (pieces
    # concatenate, an unbalanced quote runs on to the next line): an unbalanced
    # quote is left as written; quotes inside a value are part of the value; an
    # empty quoted value is empty; exactly one layer comes off, so a nested pair
    # keeps its inner quotes; the pair must match, so "abc' is left as written; a
    # value holding the other quote character keeps it.
    export XDG_CONFIG_HOME="$HOME/.config"
    mkdir -p "$XDG_CONFIG_HOME/romp"
    {
        echo 'ROMP_TEST_DQ="two words"'
        echo "ROMP_TEST_SQ='x y'"
        echo 'ROMP_TEST_ONE="abc'
        echo 'ROMP_TEST_EMPTY=""'
        echo 'ROMP_TEST_INNER=a"b"c'
        echo "ROMP_TEST_NESTED=\"'q'\""
        echo 'ROMP_TEST_TWO=""a""'
        echo "ROMP_TEST_MIX=\"abc'"
        echo "ROMP_TEST_APOS=\"it's\""
        printf 'ROMP_TEST_TSP="a b" \n'          # trailing space after the closing quote
        printf 'ROMP_TEST_CRLF="c d"\r\n'        # a CRLF line ending on a quoted value
        printf 'ROMP_TEST_BARECR=plain\r\n'      # and on an unquoted one
    } > "$XDG_CONFIG_HOME/romp/service.env"
    printf '#!/bin/sh\necho "DQ=[$ROMP_TEST_DQ] SQ=[$ROMP_TEST_SQ] ONE=[$ROMP_TEST_ONE] EMPTY=[${ROMP_TEST_EMPTY-unset}] INNER=[$ROMP_TEST_INNER] NESTED=[$ROMP_TEST_NESTED] TWO=[$ROMP_TEST_TWO] MIX=[$ROMP_TEST_MIX] APOS=[$ROMP_TEST_APOS] TSP=[$ROMP_TEST_TSP] CRLF=[$ROMP_TEST_CRLF] BARECR=[$ROMP_TEST_BARECR]"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    want="DQ=[two words] SQ=[x y] ONE=[\"abc] EMPTY=[] INNER=[a\"b\"c] NESTED=['q'] TWO=[\"a\"] MIX=[\"abc'] APOS=[it's] TSP=[a b] CRLF=[c d] BARECR=[plain]"
    [[ "$output" == *"$want"* ]]
}
