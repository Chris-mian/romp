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

teardown() {
    # the hang shapes record their pids: whatever a failing case left alive dies here, never in the suite's wake
    local p; for p in node sleeper; do [ -s "$TEST_DIR/$p.pid" ] && kill -KILL "$(cat "$TEST_DIR/$p.pid")" 2>/dev/null; done
    rm -rf "$TEST_DIR"
}

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

@test "the watchdog path: the kill of the sleep is waited on, so a sleep that takes a moment to die never outlives the launcher" {
    # CI 2026-09-14 (a tree that did not touch the launcher): the check above saw one leftover sleep pid once, a race the
    # watchdog's trap left open by exiting right after its kill. The sleep here is a stand-in that lingers a second after
    # its TERM (killing the real sleep it wraps), so at the base the launcher exits with the stand-in still alive, every
    # time; with the trap waiting for it, the session is empty when the launcher has exec'd the manager.
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    local bare="$TEST_DIR/bare-linger"; mkdir -p "$bare"
    local t
    for t in sh cmp cp chmod mv mkdir rm ps pgrep setsid; do ln -s "$(command -v "$t")" "$bare/$t"; done
    local real; real="$(command -v sleep)"
    cat > "$bare/sleep" <<EOF
#!/bin/sh
trap 'kill "\$p" 2>/dev/null; "$real" 1; exit 143' TERM
"$real" "\$@" & p=\$!
wait "\$p"
EOF
    chmod +x "$bare/sleep"
    ln -s "$BIN/node" "$bare/node"
    PATH="$bare" run setsid -w sh -c 'printf "%s\n" "$$" > "$1"; exec "$2" "$3" up' _ "$TEST_DIR/pgid" "$LAUNCH" "$MANAGER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    [ -n "$pgid" ]
    run bash -c 'ps -eo pgid=,args= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [ -z "$output" ]
}

@test "the watchdog path: a copy that HANGS is killed at the bound, the manager comes up on the system node, and no node is leaked" {
    # round three of issue 1600: the watchdog could only signal the probe's wrapper subshell, and a wrapper that ran the node
    # in its foreground survived the kill while the hung node did not die; one hung node leaked per launch (the launcher's
    # only platform, a stock mac, has no timeout). The wrapper now runs the node in its background and kills it on TERM.
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    # the stand-in hangs when run FROM THE COPY's path alone: the launcher execs the system node through the bare
    # PATH's symlink, so a stand-in keyed on its original path would hang as the manager too and hold the capture
    cat > "$BIN/node" <<EOF
#!/bin/sh
case "\$0" in
  "$RN") exec sleep 600 ;;                          # the copy hangs
  *) echo "NODE_V1 ran: \$*" ;;
esac
EOF
    chmod +x "$BIN/node"
    local bare="$TEST_DIR/bare"; mkdir -p "$bare"
    local t
    for t in sh cmp cp chmod mv mkdir rm sleep ps setsid; do ln -s "$(command -v "$t")" "$bare/$t"; done
    ln -s "$BIN/node" "$bare/node"
    # bounded from outside by an absolute-path timeout (the bare PATH must stay without one, or the launcher takes the
    # timeout path instead of the watchdog's): a leak that hung the launcher would be a clean failure, not a stuck suite
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "needs coreutils timeout to bound the run"
    PATH="$bare" run "$tmo" 60 setsid -w sh -c 'printf "%s\n" "$$" > "$1"; exec "$2" "$3" up' _ "$TEST_DIR/pgid" "$LAUNCH" "$MANAGER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]          # the fallback happened, at the bound
    [[ "$output" == *"cannot run here"* ]]
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    run bash -c 'ps -eo pgid=,args= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [[ "$output" != *"sleep 600"* ]]                          # the hung node is gone with the launcher
    [ -z "$output" ]
}

# These cases need setsid and coreutils timeout for their outer bound, so on a mac, the platform that takes the watchdog
# path, they SKIP: the watchdog code is the same on both platforms and is exercised here through the bare PATH, but a mac
# run of the suite proves nothing about it (the tidy of the fresh-install set names this; a mac-shaped bound is future work).
# The hang shapes on both probe paths (round four of issue 1600). exec: the copy IS the hung process. fork: a version
# manager's shim that RUNS node instead of exec'ing it, so the hung process is a child of the pid the wrapper holds, and
# killing that pid alone leaked the child on the watchdog path. deaf: a node that ignores TERM, which only KILL ends; a
# timeout without -k, or a wrapper without the escalation, waited on it for good. Every shape is keyed on the COPY's path
# alone, so the system node the launcher falls back to runs the manager stand-in. The bound is two seconds here
# (ROMP_NODE_PROBE_BOUND); the hung pids go to files, so the leak check names them whatever else runs on the machine.
_hang_node() {   # $1 shape: exec | fork | deaf; writes the node stand-in
    local body
    case "$1" in
      exec) body='exec sleep 60' ;;
      fork) body='sleep 60 & echo $! > "'"$TEST_DIR"'/sleeper.pid"; wait' ;;
      deaf) body='trap "" TERM; exec sleep 60' ;;
    esac
    cat > "$BIN/node" <<EOF
#!/bin/sh
case "\$0" in
  "$RN") echo \$\$ > "$TEST_DIR/node.pid"; $body ;;
  *) echo "NODE_V1 ran: \$*" ;;
esac
EOF
    chmod +x "$BIN/node"
}
_dead() {   # $1 pid: gone, or a zombie awaiting its reap
    local st; st="$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' ')"
    [ -z "$st" ] || [ "${st#Z}" != "$st" ]
}
_run_hang() {   # $1 shape, $2 path: bare (the watchdog) | timeout; the launcher in its own session under a 20 s outer bound
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "needs coreutils timeout to bound the run"
    _hang_node "$1"
    local bare="$TEST_DIR/bare"; rm -rf "$bare"; mkdir -p "$bare"
    local t
    for t in sh cmp cp chmod mv mkdir rm sleep ps pgrep setsid; do ln -s "$(command -v "$t")" "$bare/$t"; done
    if [ "$2" = timeout ]; then ln -s "$tmo" "$bare/timeout"; fi
    ln -s "$BIN/node" "$bare/node"
    rm -f "$TEST_DIR/node.pid" "$TEST_DIR/sleeper.pid" "$TEST_DIR/pgid"
    PATH="$bare" ROMP_NODE_PROBE_BOUND=2 run "$tmo" 20 setsid -w sh -c 'printf "%s\n" "$$" > "$1"; exec "$2" "$3" up' _ "$TEST_DIR/pgid" "$LAUNCH" "$MANAGER"
}
_hang_asserts() {   # the fallback happened at the bound, and nothing of the probe survives: not the node, not its child, nothing in the session
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    [[ "$output" == *"cannot run here"* ]]
    [ -s "$TEST_DIR/node.pid" ]
    _dead "$(cat "$TEST_DIR/node.pid")"
    [ ! -s "$TEST_DIR/sleeper.pid" ] || _dead "$(cat "$TEST_DIR/sleeper.pid")"
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    run bash -c 'ps -eo pgid=,args= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [ -z "$output" ]
}
@test "the watchdog path: a shim that FORKS the hung node (a version manager's) leaks nothing: the tree under the wrapper's pid is killed" { _run_hang fork bare; _hang_asserts; }
@test "the watchdog path: a node that IGNORES TERM is killed a second later, and the manager comes up on the system node" { _run_hang deaf bare; _hang_asserts; }
@test "the timeout path: a hung copy is killed at the bound (control: so it was before this round)" { _run_hang exec timeout; _hang_asserts; }
@test "the timeout path: a shim that FORKS the hung node leaks nothing (control: timeout signals the whole group)" { _run_hang fork timeout; _hang_asserts; }
@test "the timeout path: a node that IGNORES TERM is killed by -k a second after the bound instead of holding the launch for good" { _run_hang deaf timeout; _hang_asserts; }

@test "ROMP_NO_NODE_COPY: 0, false, no and off are off, the last assignment in service.env wins, and an export-prefixed line is skipped, not fatal" {
    export ROMP_SERVICE_ENV_FILE="$TEST_DIR/service.env"
    unset ROMP_NO_NODE_COPY
    # off values keep the copy
    for v in 0 false FALSE no off OFF; do
        rm -f "$RN"
        printf 'ROMP_NO_NODE_COPY=%s\n' "$v" > "$ROMP_SERVICE_ENV_FILE"
        run "$LAUNCH" "$MANAGER" up
        [ "$status" -eq 0 ]
        [ -x "$RN" ]
    done
    # any other non-empty value is on, disabled and none included: the docs say so
    for v in disabled none; do
        rm -f "$RN"
        printf 'ROMP_NO_NODE_COPY=%s\n' "$v" > "$ROMP_SERVICE_ENV_FILE"
        run "$LAUNCH" "$MANAGER" up
        [ "$status" -eq 0 ]
        [ ! -e "$RN" ]
    done
    # set then cleared below: the last assignment wins (a copy is made)
    rm -f "$RN"
    printf 'ROMP_NO_NODE_COPY=1\nROMP_NO_NODE_COPY=\n' > "$ROMP_SERVICE_ENV_FILE"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [ -x "$RN" ]
    # cleared then set below: on
    rm -f "$RN"
    printf 'ROMP_NO_NODE_COPY=\nROMP_NO_NODE_COPY=yes\n' > "$ROMP_SERVICE_ENV_FILE"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [ ! -e "$RN" ]
    # an export-prefixed line: skipped as malformed (under dash it took the launcher down), the good line still exported
    printf 'export ROMP_TEST_BAD=1\nROMP_TEST_GOOD=fine\n' > "$ROMP_SERVICE_ENV_FILE"
    printf '#!/bin/sh\necho "GOOD=[$ROMP_TEST_GOOD] BAD=[${ROMP_TEST_BAD-unset}] ran: $*"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    run "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"GOOD=[fine] BAD=[unset] ran: $MANAGER up"* ]]
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

@test "service.env: a name that is readonly in the shell (UID, PPID: the .env idiom) is skipped, not fatal, under sh in POSIX mode" {
    # round four of issue 1600: under macOS's /bin/sh (bash in POSIX mode) an assignment error in the special builtin
    # export exits the shell in spite of the or-true, before any exec and with nothing in the manager log, and KeepAlive
    # respawned that silent exit every ThrottleInterval. bash --posix is that shell's shape here; dash, where the names
    # are plain, is the control.
    export ROMP_SERVICE_ENV_FILE="$TEST_DIR/service.env"
    printf 'ROMP_TEST_BEFORE=one\nUID=1000\nPPID=1\nROMP_TEST_AFTER=two\n' > "$ROMP_SERVICE_ENV_FILE"
    printf '#!/bin/sh\necho "BEFORE=[$ROMP_TEST_BEFORE] AFTER=[$ROMP_TEST_AFTER] ran: $*"\n' > "$BIN/node"
    chmod +x "$BIN/node"
    run bash --posix "$LAUNCH" "$MANAGER" up
    [ "$status" -eq 0 ]
    [[ "$output" == *"BEFORE=[one] AFTER=[two] ran: $MANAGER up"* ]]
    if command -v dash >/dev/null 2>&1; then
        run dash "$LAUNCH" "$MANAGER" up
        [ "$status" -eq 0 ]
        [[ "$output" == *"BEFORE=[one] AFTER=[two] ran: $MANAGER up"* ]]
    fi
}

@test "ROMP_NODE_PROBE_BOUND=0 is clamped to one second: a good copy runs the manager on the watchdog path, and a hung copy on the timeout path falls back at once" {
    # the tidy of the fresh-install set: 0 was accepted, and timeout -k 1 0 means NO bound while the watchdog's sleep 0 failed a
    # good copy at once
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the run (Linux)"
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "needs coreutils timeout to bound the run"
    # the copy takes half a second to answer: the setup's instant stand-in beat the base's sleep-0 kill, this one does not
    cat > "$BIN/node" <<EOF
#!/bin/sh
case "\$0" in
  "$RN") sleep 0.5; echo "NODE_V1 ran: \$*" ;;
  *) echo "NODE_V1 ran: \$*" ;;
esac
EOF
    chmod +x "$BIN/node"
    local bare="$TEST_DIR/bare"; rm -rf "$bare"; mkdir -p "$bare"
    local t; for t in sh cmp cp chmod mv mkdir rm sleep ps pgrep setsid; do ln -s "$(command -v "$t")" "$bare/$t"; done
    ln -s "$BIN/node" "$bare/node"
    PATH="$bare" ROMP_NODE_PROBE_BOUND=0 run "$tmo" 20 setsid -w sh -c 'exec "$1" "$2" up' _ "$LAUNCH" "$MANAGER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NODE_V1 ran: $MANAGER up"* ]]
    [[ "$output" != *"cannot run here"* ]]                    # the good copy was not failed by an instant kill
    _hang_node exec
    ln -s "$tmo" "$bare/timeout"
    rm -f "$TEST_DIR/node.pid"
    PATH="$bare" ROMP_NODE_PROBE_BOUND=0 run "$tmo" 20 setsid -w sh -c 'exec "$1" "$2" up' _ "$LAUNCH" "$MANAGER"
    [ "$status" -eq 0 ]                                        # not the outer bound: the clamp made timeout's bound one second
    [[ "$output" == *"cannot run here"* ]]
    _dead "$(cat "$TEST_DIR/node.pid")"
}
