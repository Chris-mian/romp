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
    # Running this suite INSIDE a romp session inherits the live kernel's ROMP_SERVE_PORT /
    # ROMP_MANAGER_PORT, which the unit now bakes — so a default-vs-override test would be
    # reading the developer's machine instead of the code. Clear the whole instance set; the
    # tests that want them set them explicitly.
    unset ROMP_SERVE_PORT ROMP_KERNEL_PORT ROMP_POSTAL_PORT ROMP_MANAGER_PORT ROMP_STATE_DIR CLAUDE_CONFIG_DIR
    # The env-file path is baked (and, when non-default, exported) into the unit too; a developer shell
    # that carries either variable must not leak it into the default-install assertions below.
    unset ROMP_SERVICE_ENV_FILE XDG_CONFIG_HOME
    # The macOS install's verification probes the control port when the agent's manager is not running (a manager
    # already serving there, a hand-run one, is named as such). A developer's machine, and a romp session's, has a
    # live manager on the default port, so every test here answers that probe with a stand-in that says nothing
    # serves; the tests about that state set their own.
    printf '#!/bin/sh\nexit 1\n' > "$TEST_DIR/probe-nothing"
    chmod +x "$TEST_DIR/probe-nothing"
    export ROMP_MANAGER_PROBE="$TEST_DIR/probe-nothing"
}

teardown() {
    # the hang shapes record their pids: whatever a failing case left alive dies here, never in the suite's wake
    local p; for p in node sleeper; do [ -s "$TEST_DIR/$p.pid" ] && kill -KILL "$(cat "$TEST_DIR/$p.pid")" 2>/dev/null; done
    rm -rf "$TEST_DIR"
}

@test "install (macOS): launchd plist runs 'romp-manager up' at login, kept alive" {
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    [ -f "$plist" ]
    grep -q "<string>$ROMP_MANAGER_BIN</string>" "$plist"
    grep -q "<string>up</string>" "$plist"
    grep -q "RunAtLoad" "$plist"
    grep -q "KeepAlive" "$plist"
    # issue 1600: KeepAlive with launchd's default ten-second throttle respawned a manager that died at once
    # six times a minute forever; the interval bounds that loop to once a minute (a manager that ran longer
    # than it before exiting is respawned at once, since the throttle counts from the job's last start)
    grep -q "<key>ThrottleInterval</key><integer>60</integer>" "$plist"
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

@test "install (macOS): a node copy that cannot run from the state dir is removed, and the install says the manager runs on the system node" {
    # issue 1600: the copy is probed once made (an empty program, stdin closed, a bound); a node whose shared
    # library is referenced relative to its install dies from the copy, so the copy goes and the message
    # names the consequence for Full Disk Access. The launcher probes too, so this is the install's half.
    local src="$TEST_DIR/bound-node"
    cat > "$src" <<EOF
#!/bin/sh
case "\$0" in
  "$src") exit 0 ;;
  *) echo "dyld[4242]: Library not loaded: @rpath/libnode.dylib" >&2; exit 134 ;;
esac
EOF
    chmod +x "$src"
    ROMP_NODE_SRC="$src" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local rn="$XDG_STATE_HOME/romp/romp-node"
    [ ! -e "$rn" ]                                            # the unusable copy is gone
    [[ "$output" == *"cannot run from $rn"* ]]
    [[ "$output" == *"runs on the system node"* ]]
    [[ "$output" == *"ROMP_NO_NODE_COPY=1"* ]]
    [[ "$output" != *"grant it to romp's OWN node copy"* ]]   # no grant advice for a copy that is not there
}

@test "install (macOS): ROMP_NO_NODE_COPY=1 in service.env, the route the message names, makes no copy and removes a stale one" {
    # round two of issue 1600: the install never parsed service.env (it bakes the path into the unit and the plist), so
    # the line the messages name did nothing for the install's own copy. The environment is UNSET here; the file is
    # the default one under this test's HOME (the setup clears XDG_CONFIG_HOME and ROMP_SERVICE_ENV_FILE).
    ROMP_OS_OVERRIDE=Darwin "$SVC" install >/dev/null        # a copy from a normal install
    local rn="$XDG_STATE_HOME/romp/romp-node"
    [ -x "$rn" ]
    unset ROMP_NO_NODE_COPY
    mkdir -p "$HOME/.config/romp"
    printf '# knobs\nROMP_NO_NODE_COPY="1"\n' > "$HOME/.config/romp/service.env"
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ ! -e "$rn" ]
    [[ "$output" != *"grant it to romp's OWN node copy"* ]]   # no grant advice for a copy that is not there
    # …and the line read from a non-default path, the one the plist and unit are told about
    printf 'ROMP_NO_NODE_COPY=\n' > "$HOME/.config/romp/service.env"   # an empty value is OFF
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ -x "$rn" ]
    export ROMP_SERVICE_ENV_FILE="$TEST_DIR/elsewhere/service.env"
    mkdir -p "$TEST_DIR/elsewhere"; printf 'ROMP_NO_NODE_COPY=yes\n' > "$ROMP_SERVICE_ENV_FILE"
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ ! -e "$rn" ]
}

@test "install (macOS): a node copy that HANGS from the state dir is killed at the bound and removed, and no node is leaked" {
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    local src="$TEST_DIR/hang-node"
    cat > "$src" <<EOF
#!/bin/sh
case "\$0" in
  "$src") exit 0 ;;
  *) exec sleep 600 ;;
esac
EOF
    chmod +x "$src"
    local bare="$TEST_DIR/bare"; mkdir -p "$bare"
    local t
    for t in bash sh cmp cp chmod mv mkdir rm sleep ps setsid id date cut head tr printf sed cat grep dirname readlink; do p="$(command -v "$t" 2>/dev/null || true)"; [ -n "$p" ] && ln -s "$p" "$bare/$t"; done
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "needs coreutils timeout to bound the run"
    PATH="$bare" ROMP_NODE_SRC="$src" ROMP_OS_OVERRIDE=Darwin run "$tmo" 60 setsid -w bash -c 'printf "%s\n" "$$" > "$1"; exec "$2" install' _ "$TEST_DIR/pgid" "$SVC"
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/romp-node" ]
    [[ "$output" == *"cannot run from"* ]]
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    run bash -c 'ps -eo pgid=,args= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [[ "$output" != *"sleep 600"* ]]
    [ -z "$output" ]
}

# These cases need setsid and coreutils timeout for their outer bound, so on a mac, the platform that takes the watchdog
# path, they SKIP: the watchdog code is the same on both platforms and is exercised here through the bare PATH, but a mac
# run of the suite proves nothing about it (the tidy of the fresh-install set names this; a mac-shaped bound is future work).
# The hang shapes on both probe paths, the install's twin of the launcher's matrix (round four of issue 1600): exec (the
# copy is the hung process), fork (a version manager's shim runs node instead of exec'ing it: the hung process is a child
# of the pid the wrapper holds, which leaked on the watchdog path) and deaf (TERM ignored: only KILL ends it, and a timeout
# without -k held the install for good). The stand-in runs from its source path and hangs from the copy's; the bound is
# two seconds here (ROMP_NODE_PROBE_BOUND); the hung pids go to files, so the leak check names them.
_hang_src() {   # $1 shape: exec | fork | deaf
    local body
    case "$1" in
      exec) body='exec sleep 60' ;;
      fork) body='sleep 60 & echo $! > "'"$TEST_DIR"'/sleeper.pid"; wait' ;;
      deaf) body='trap "" TERM; exec sleep 60' ;;
    esac
    cat > "$TEST_DIR/hang-node" <<EOF
#!/bin/sh
case "\$0" in
  "$TEST_DIR/hang-node") exit 0 ;;
  *) echo \$\$ > "$TEST_DIR/node.pid"; $body ;;
esac
EOF
    chmod +x "$TEST_DIR/hang-node"
}
_dead() {   # $1 pid: gone, or a zombie awaiting its reap
    local st; st="$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' ')"
    [ -z "$st" ] || [ "${st#Z}" != "$st" ]
}
_run_install_hang() {   # $1 shape, $2 path: bare (the watchdog) | timeout; the install in its own session under a 20 s outer bound
    command -v setsid >/dev/null 2>&1 || skip "needs setsid to scope the process-group check (Linux)"
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "needs coreutils timeout to bound the run"
    _hang_src "$1"
    local bare="$TEST_DIR/bare"; rm -rf "$bare"; mkdir -p "$bare"
    local t p
    for t in bash sh cmp cp chmod mv mkdir rm sleep ps pgrep setsid id date cut head tr printf sed cat grep dirname readlink; do p="$(command -v "$t" 2>/dev/null || true)"; [ -n "$p" ] && ln -s "$p" "$bare/$t"; done
    if [ "$2" = timeout ]; then ln -s "$tmo" "$bare/timeout"; fi
    rm -f "$TEST_DIR/node.pid" "$TEST_DIR/sleeper.pid" "$TEST_DIR/pgid"
    PATH="$bare" ROMP_NODE_PROBE_BOUND=2 ROMP_NODE_SRC="$TEST_DIR/hang-node" ROMP_OS_OVERRIDE=Darwin run "$tmo" 20 setsid -w bash -c 'printf "%s\n" "$$" > "$1"; exec "$2" install' _ "$TEST_DIR/pgid" "$SVC"
}
_install_hang_asserts() {   # the copy is removed with the reason said, and nothing of the probe survives: not the node, not its child, nothing in the session
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/romp-node" ]
    [[ "$output" == *"cannot run from"* ]]
    [ -s "$TEST_DIR/node.pid" ]
    _dead "$(cat "$TEST_DIR/node.pid")"
    [ ! -s "$TEST_DIR/sleeper.pid" ] || _dead "$(cat "$TEST_DIR/sleeper.pid")"
    local pgid; pgid="$(cat "$TEST_DIR/pgid")"
    run bash -c 'ps -eo pgid=,args= | awk -v g="$1" "\$1==g"' _ "$pgid"
    [ -z "$output" ]
}
@test "install (macOS), the watchdog path: a shim that FORKS the hung node leaks nothing: the tree under the wrapper's pid is killed" { _run_install_hang fork bare; _install_hang_asserts; }
@test "install (macOS), the watchdog path: a node that IGNORES TERM is killed a second later and the copy removed" { _run_install_hang deaf bare; _install_hang_asserts; }
@test "install (macOS), the timeout path: a hung copy is killed at the bound (control: so it was before this round)" { _run_install_hang exec timeout; _install_hang_asserts; }
@test "install (macOS), the timeout path: a shim that FORKS the hung node leaks nothing (control: timeout signals the whole group)" { _run_install_hang fork timeout; _install_hang_asserts; }
@test "install (macOS), the timeout path: a node that IGNORES TERM is killed by -k a second after the bound instead of holding the install for good" { _run_install_hang deaf timeout; _install_hang_asserts; }

@test "install (macOS): ROMP_NODE_PROBE_BOUND=0 is clamped to one second, so a good copy is kept instead of failed at once" {
    ROMP_NODE_PROBE_BOUND=0 ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ -x "$XDG_STATE_HOME/romp/romp-node" ]
    [[ "$output" != *"cannot run from"* ]]
}

@test "install (macOS): the hatch reads 0, false, no and off as off, and the file's last assignment wins" {
    mkdir -p "$HOME/.config/romp"
    local rn="$XDG_STATE_HOME/romp/romp-node"
    unset ROMP_NO_NODE_COPY
    for v in 0 false No off OFF; do
        rm -f "$rn"
        printf 'ROMP_NO_NODE_COPY=%s\n' "$v" > "$HOME/.config/romp/service.env"
        ROMP_OS_OVERRIDE=Darwin run "$SVC" install
        [ "$status" -eq 0 ]
        [ -x "$rn" ]
    done
    for v in disabled none; do                                 # any other non-empty value is on: the docs say so
        rm -f "$rn"
        printf 'ROMP_NO_NODE_COPY=%s\n' "$v" > "$HOME/.config/romp/service.env"
        ROMP_OS_OVERRIDE=Darwin run "$SVC" install
        [ "$status" -eq 0 ]
        [ ! -e "$rn" ]
    done
    printf 'ROMP_NO_NODE_COPY=1\nROMP_NO_NODE_COPY=\n' > "$HOME/.config/romp/service.env"   # set, then cleared below: the copy is made
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ -x "$rn" ]
    printf 'ROMP_NO_NODE_COPY=\nROMP_NO_NODE_COPY=1\n' > "$HOME/.config/romp/service.env"   # cleared, then set: skipped and removed
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ ! -e "$rn" ]
    printf 'ROMP_NO_NODE_COPY=0\n' > "$HOME/.config/romp/service.env"                            # the file's last word wins over the environment: it says off here
    ROMP_NO_NODE_COPY=0 ROMP_OS_OVERRIDE=Darwin run "$SVC" install                              # 0 in the environment is off too
    [ "$status" -eq 0 ]
    [ -x "$rn" ]
}

@test "install (macOS): ROMP_NO_NODE_COPY=1 in the environment makes no copy either (the second route)" {
    ROMP_NO_NODE_COPY=1 ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/romp-node" ]
}

@test "install (macOS): a node copy that dies by SIGNAL from the state dir leaves no job-status line in the output" {
    local src="$TEST_DIR/abort-node"
    cat > "$src" <<EOF
#!/bin/sh
case "\$0" in
  "$src") exit 0 ;;
  *) kill -ABRT \$\$ ;;
esac
EOF
    chmod +x "$src"
    ROMP_NODE_SRC="$src" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/romp-node" ]
    [[ "$output" == *"cannot run from"* ]]
    [[ "$output" != *"Aborted"* ]]
    [[ "$output" != *"core dumped"* ]]
}

@test "install (Linux): systemd unit is unchanged — no romp-node launcher (no TCC there)" {
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    grep -q "ExecStart=$ROMP_MANAGER_BIN up" "$unit"
    # `run` + status, NOT a bare `! grep`: `!` is exempt from set -e, so mid-test it asserts nothing.
    run grep -q "romp-node-launch" "$unit"
    [ "$status" -ne 0 ]
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

# The install's bootstrap races the preceding bootout (launchd rejects with
# "Input/output error" while the old job drains). ROMP_LAUNCHCTL stubs launchctl
# to exercise that path: install must RETRY until launchd accepts, and fail
# loudly — never silently — if it never does (a swallowed failure leaves no
# agent loaded and a dead kernel with nothing saying why).

@test "install (macOS): bootstrap retries through the bootout drain race" {
    unset ROMP_SERVICE_NO_LOAD
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
[ "\$1" = bootout ] && exit 0
# once loaded, print names the live process (the post-install check reads the pid line, not print's exit)
[ "\$1" = print ] && [ "\$(grep -c bootstrap "$calls")" -ge 3 ] && { echo "	pid = 4242"; exit 0; }
[ "\$(grep -c bootstrap "$calls")" -ge 3 ] && exit 0
echo "Bootstrap failed: 5: Input/output error" >&2
exit 5
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    grep -q bootout "$calls"
    [ "$(grep -c bootstrap "$calls")" -eq 3 ]
    [[ "$output" == *"Installed launchd agent"* ]]
}

@test "install (macOS): no bootstrap while the old job is still draining" {
    # bootout only STARTS the teardown; a manager draining live SDK sessions outlives any
    # blind retry window (2026-07-20, twice: every bootstrap rejected mid-drain -> no agent
    # loaded, dead dashboard). Install must WAIT for the job to actually leave launchd
    # (print stops answering) and only then bootstrap.
    unset ROMP_SERVICE_NO_LOAD
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
if [ "\$1" = print ]; then
    # After bootstrap the NEW job answers print with its live pid (the post-install running check reads it).
    grep -q bootstrap "$calls" && { echo "	pid = 4242"; exit 0; }
    [ "\$(grep -c print "$calls")" -ge 4 ] && exit 5   # the old job finally drains away
    exit 0                                             # still tearing down (loaded, no process named)
fi
exit 0
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    [ "$(grep -c print "$calls")" -ge 4 ]              # waited through the drain
    [ "$(grep -c bootstrap "$calls")" -eq 1 ]          # then loaded cleanly, first try
    # the drain-wait prints stop BEFORE the bootstrap; only the running-check prints follow it
    grep -B1000 bootstrap "$calls" | grep -q print     # waited, then bootstrapped
}

@test "install (macOS): a bootstrap that never lands fails LOUDLY, not silently" {
    unset ROMP_SERVICE_NO_LOAD
    local stub="$TEST_DIR/launchctl-stub"
    cat > "$stub" <<'EOF'
#!/bin/sh
[ "$1" = bootout ] && exit 0
echo "Bootstrap failed: 5: Input/output error" >&2
exit 5
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"FAILED to load the login agent"* ]]
    [[ "$output" == *"Input/output error"* ]]
    [[ "$output" == *"Retry by hand"* ]]
}

@test "unsupported OS fails cleanly" {
    ROMP_OS_OVERRIDE=Plan9 run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"unsupported OS"* ]]
}

@test "install appends an attribution line to the restart audit" {
    # Four unload-without-reload outages in one day were untraceable: the loud failure went to the
    # CALLER's stderr and nothing recorded WHO ran the install. Every install now journals itself.
    export XDG_STATE_HOME="$TEST_DIR/state"
    export CLAUDE_CODE_SESSION_ID="11111111-2222-3333-4444-555555555555"
    mkdir -p "$TEST_DIR/state/romp/names"
    printf 'testsess\t/tmp\n' > "$TEST_DIR/state/romp/names/11111111-2222-3333-4444-555555555555"
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 run "$SVC" install
    [ "$status" -eq 0 ]
    local aud="$TEST_DIR/state/romp/restart-audit.jsonl"
    [ -f "$aud" ]
    grep -q '"action": "service-install"' "$aud"
    grep -q '"name": "testsess"' "$aud"
}

@test "install (macOS): a bootstrap that is accepted but never runs fails loudly" {
    # bootstrap ACCEPTED != job RUNNING: launchd can take the definition and still fail the spawn.
    # Exit 0 must require the service to actually report itself.
    unset ROMP_SERVICE_NO_LOAD
    export XDG_STATE_HOME="$TEST_DIR/state"
    local stub="$TEST_DIR/launchctl-stub"
    cat > "$stub" <<'EOF2'
#!/bin/sh
[ "$1" = bootout ] && exit 0
[ "$1" = bootstrap ] && exit 0    # accepted...
exit 5                            # ...but print never finds it running
EOF2
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"NOT running"* ]]
}

# ── loaded is not running (issue 1600) ─────────────────────────────────────────────────────
# launchctl print succeeds for any LOADED job, a crash-looping one included: the manager's copied node
# aborted at exec, KeepAlive respawned it every throttle interval, `status` said running and install.sh
# trusted that. The job's record names its process (a `pid = N` line) only while one runs, and keeps the
# previous run's exit code; both are read now.
_dying_record() {   # the record of a loaded job that keeps dying: no pid, last exit 134
    printf 'gui/501/com.romp.manager = {\n\tactive count = 0\n\tstate = not running\n\tlast exit code = 134\n\truns = 17\n}\n'
}
_crashloop_loaded_stub() {   # for status: a launchctl whose job is loaded from the start and keeps dying
    cat > "$1" <<'EOF'
#!/bin/sh
[ "$1" = bootout ] && exit 0
[ "$1" = bootstrap ] && exit 0
if [ "$1" = print ]; then
    printf 'gui/501/com.romp.manager = {\n\tactive count = 0\n\tstate = not running\n\tlast exit code = 134\n\truns = 17\n}\n'
    exit 0
fi
exit 0
EOF
    chmod +x "$1"
}
_crashloop_stub() {   # for install: print fails until bootstrap (the drain wait ends at once); the FIRST post-bootstrap print
    # names a pid, the aborting manager alive for its first split second, and every later print says not running, exit 134.
    # Round two of issue 1600: the base declared success on that first pid; the install must re-read a second later and
    # see the SAME pid before it says installed.
    local stub="$1" calls="$2"
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
[ "\$1" = bootout ] && exit 0
[ "\$1" = bootstrap ] && exit 0
if [ "\$1" = print ]; then
    grep -q bootstrap "$calls" || exit 5                                  # not loaded until bootstrapped
    if [ "\$(sed -n '/bootstrap/,\$p' "$calls" | grep -c print)" -eq 1 ]; then      # the first print AFTER the bootstrap: alive
        printf 'gui/501/com.romp.manager = {\n\tactive count = 1\n\tstate = running\n\tpid = 4242\n\tlast exit code = (never exited)\n}\n'
        exit 0
    fi
    printf 'gui/501/com.romp.manager = {\n\tactive count = 0\n\tstate = not running\n\tlast exit code = 134\n\truns = 2\n}\n'
    exit 0
fi
exit 0
EOF
    chmod +x "$stub"
}
_running_stub() {   # a launchctl whose job runs: print names the pid, the same one every time
    cat > "$1" <<'EOF'
#!/bin/sh
[ "$1" = print ] && { printf 'gui/501/com.romp.manager = {\n\tactive count = 1\n\tstate = running\n\tpid = 4242\n\tlast exit code = (never exited)\n}\n'; exit 0; }
exit 0
EOF
    chmod +x "$1"
}

@test "status (macOS): a loaded job that keeps dying is NOT running, and the last exit code is named" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null   # the plist alone
    local stub="$TEST_DIR/launchctl-stub"; _crashloop_loaded_stub "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [ "$status" -eq 0 ]
    [[ "$output" == *"installed:"* ]]
    [[ "$output" == *"loaded but not running"* ]]
    [[ "$output" == *"last exit code: 134"* ]]
    # never the bare line install.sh keys its skip-the-reinstall shortcut on
    run grep -qx running <<< "$output"
    [ "$status" -ne 0 ]
}

@test "status (macOS): a job whose record names a live pid is running (a CONTROL: green at the base too, where print's exit alone said running)" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/launchctl-stub"; _running_stub "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [ "$status" -eq 0 ]
    run grep -qx running <<< "$output"
    [ "$status" -eq 0 ]
}

@test "status (macOS): the record's readers survive a print of thousands of lines and capture the exit value whole" {
    # round two, lows 1 and 2: `sed | head -1` under set -e plus pipefail died of SIGPIPE once sed's output passed the pipe
    # buffer (exit 141, no status line), and the value stopped at its first space, so "(signal: 6)" read as "(signal:"
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/launchctl-stub"
    cat > "$stub" <<'EOF'
#!/bin/sh
if [ "$1" = print ]; then
    printf 'gui/501/com.romp.manager = {\n\tstate = not running\n'
    i=0; while [ "$i" -lt 3000 ]; do printf '\tlast exit code = (signal: 6)\n'; i=$((i+1)); done   # loop-ok: a fixed-count stub
    printf '}\n'; exit 0
fi
exit 0
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [ "$status" -eq 0 ]
    [[ "$output" == *"last exit code: (signal: 6)"* ]]
    # …and a record of thousands of pid lines reads as running, not as a broken pipe
    cat > "$stub" <<'EOF'
#!/bin/sh
if [ "$1" = print ]; then
    printf 'gui/501/com.romp.manager = {\n\tstate = running\n'
    i=0; while [ "$i" -lt 3000 ]; do printf '\tpid = 4242\n'; i=$((i+1)); done   # loop-ok: a fixed-count stub
    printf '}\n'; exit 0
fi
exit 0
EOF
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" status
    [ "$status" -eq 0 ]
    run grep -qx running <<< "$output"
    [ "$status" -eq 0 ]
}

@test "install (macOS): a job that loads, lives for a moment and then keeps dying fails loudly, naming the last exit code" {
    # round two, medium 1: the first post-bootstrap read saw the aborting manager alive; a second later the pid is gone.
    # The stub's print fails until the bootstrap, so the drain wait before it ends at once (low 3).
    unset ROMP_SERVICE_NO_LOAD
    export XDG_STATE_HOME="$TEST_DIR/state"
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    _crashloop_stub "$stub" "$calls"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"NOT running"* ]]
    [[ "$output" == *"last exit code: 134"* ]]
    [[ "$output" != *"Installed launchd agent"* ]]
    [ "$(grep -c print "$calls")" -ge 3 ]                     # the drain wait's print, the first live read, the re-read
}

# ── a manager already serving outside the service ─────────────────────────────────────────
# bin/romp-manager refuses to start a second manager on a held control port (exit 1 at once), the throttle keeps the
# respawn out of the verification window, and the install ended saying the dashboard would be dead while the hand-run
# manager was serving it. The verification probes the control port and names that state with its own code.
_dying_loaded_stub() {   # for install: print fails until bootstrap, then a loaded job with no pid and last exit $3 (1 by default)
    local stub="$1" calls="$2" code="${3:-1}"
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
[ "\$1" = bootout ] && exit 0
[ "\$1" = bootstrap ] && exit 0
if [ "\$1" = print ]; then
    grep -q bootstrap "$calls" || exit 5
    printf 'gui/501/com.romp.manager = {\n\tactive count = 0\n\tstate = not running\n\tlast exit code = $code\n\truns = 2\n}\n'
    exit 0
fi
exit 0
EOF
    chmod +x "$stub"
}

@test "install (macOS): a manager already serving on the control port is named when the agent's code is the manager's refusal (1), with the log pointer" {
    unset ROMP_SERVICE_NO_LOAD
    export XDG_STATE_HOME="$TEST_DIR/state"
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    _dying_loaded_stub "$stub" "$calls" 1
    printf '#!/bin/sh\necho "probed :$1" >> "%s"\nexit 0\n' "$TEST_DIR/probe-calls" > "$TEST_DIR/probe-up"; chmod +x "$TEST_DIR/probe-up"
    ROMP_MANAGER_PORT=7499 ROMP_MANAGER_PROBE="$TEST_DIR/probe-up" ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 3 ]
    [[ "$output" == *"ALREADY serving on :7499"* ]]
    [[ "$output" == *"code 1"* ]]
    [[ "$output" == *"most likely outside the login service"* ]]     # the probe cannot tell whose manager answers
    [[ "$output" == *"check $XDG_STATE_HOME/romp/manager.log"* ]]     # the log pointer stays in every branch (round two)
    [[ "$output" != *"dashboard"* ]]                                   # the control port proves a manager, not the dashboard
    grep -q "probed :7499" "$TEST_DIR/probe-calls"                     # the port the manager would use, not a default
    # …and with nothing answering the port, the plain NOT running verdict and exit 1 as before
    printf '#!/bin/sh\nexit 1\n' > "$TEST_DIR/probe-down"; chmod +x "$TEST_DIR/probe-down"
    rm -f "$calls"
    ROMP_MANAGER_PROBE="$TEST_DIR/probe-down" ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"NOT running"* ]]
    [[ "$output" != *"ALREADY serving"* ]]
}

@test "install (macOS): an agent that died of its own cause (134) beside a manager answering is reported as both facts, not as the held port" {
    # round two of the install-wording fix: the branch was gated on the probe alone, so issue 1600's own shape (the node copy
    # aborting at exec) read as a held port once the user had worked around it with a hand-run romp up
    unset ROMP_SERVICE_NO_LOAD
    export XDG_STATE_HOME="$TEST_DIR/state"
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    _dying_loaded_stub "$stub" "$calls" 134
    printf '#!/bin/sh\nexit 0\n' > "$TEST_DIR/probe-up"; chmod +x "$TEST_DIR/probe-up"
    ROMP_MANAGER_PORT=7499 ROMP_MANAGER_PROBE="$TEST_DIR/probe-up" ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 1 ]
    [[ "$output" == *"NOT running (last exit code: 134)"* ]]
    [[ "$output" == *"check $XDG_STATE_HOME/romp/manager.log"* ]]
    [[ "$output" == *"A manager is also serving on :7499"* ]]
    [[ "$output" == *"not why it died"* ]]
    [[ "$output" != *"ALREADY serving"* ]]
}

@test "install (macOS): the probe asks the port service.env gives the agent's manager (last assignment, quotes off), not the environment's default" {
    unset ROMP_SERVICE_NO_LOAD ROMP_MANAGER_PORT
    export XDG_STATE_HOME="$TEST_DIR/state"
    mkdir -p "$HOME/.config/romp"
    printf 'ROMP_MANAGER_PORT=7601\nROMP_MANAGER_PORT="7602"\n' > "$HOME/.config/romp/service.env"
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    _dying_loaded_stub "$stub" "$calls" 1
    printf '#!/bin/sh\necho "probed :$1" >> "%s"\nexit 0\n' "$TEST_DIR/probe-calls" > "$TEST_DIR/probe-up"; chmod +x "$TEST_DIR/probe-up"
    ROMP_MANAGER_PROBE="$TEST_DIR/probe-up" ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 3 ]
    [[ "$output" == *"ALREADY serving on :7602"* ]]
    grep -q "probed :7602" "$TEST_DIR/probe-calls"
    ! grep -q "probed :7432" "$TEST_DIR/probe-calls"
}

@test "both units bake ROMP_SUPERVISED=1 — the manager's stale-self refresh needs a respawning supervisor" {
    # The manager may EXIT on a refresh when its own binary changed (the fresh supervisor respawn IS
    # the refresh) — but only when something WILL respawn it. KeepAlive/Restart=always is that
    # something; this env var is how the manager knows it's running under one (2026-07-24).
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    grep -q "<key>ROMP_SUPERVISED</key><string>1</string>" "$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    grep -q "^Environment=ROMP_SUPERVISED=1$" "$ROMP_SYSTEMD_DIR/romp-manager.service"
}

# ── the instance env: which romp does this service supervise? ──────────────────────────────
# A second OS user on one machine (a kernel handed to another person) shares the PORT space,
# so their manager/kernel/bus must be renumbered. The installing shell had the overrides; the
# unit did not, so the supervised manager came up on the defaults, its control port collided
# with the primary user's, and the service died at login while every foreground `romp` command
# still reported the configured port.

@test "install bakes the renumbered ports into the unit (Linux) and the plist (macOS)" {
    export ROMP_SERVE_PORT=29856 ROMP_POSTAL_PORT=25303 ROMP_MANAGER_PORT=7433
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    grep -q "^Environment=ROMP_SERVE_PORT=29856$"   "$unit"
    grep -q "^Environment=ROMP_POSTAL_PORT=25303$"  "$unit"
    grep -q "^Environment=ROMP_MANAGER_PORT=7433$"  "$unit"
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    grep -q "<key>ROMP_SERVE_PORT</key><string>29856</string>"  "$plist"
    grep -q "<key>ROMP_POSTAL_PORT</key><string>25303</string>" "$plist"
    grep -q "<key>ROMP_MANAGER_PORT</key><string>7433</string>" "$plist"
}

@test "install bakes ROMP_KERNEL_PORT — the spelling the docs tell people to set" {
    # docs/reference.md names ROMP_KERNEL_PORT and not ROMP_SERVE_PORT, so someone renumbering a
    # second instance by the book sets only this one. It used to reach no unit at all: the
    # supervised manager came up on the default and the new kernel bound the primary's port.
    export ROMP_KERNEL_PORT=29856
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    grep -q "^Environment=ROMP_KERNEL_PORT=29856$" "$ROMP_SYSTEMD_DIR/romp-manager.service"
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    grep -q "<key>ROMP_KERNEL_PORT</key><string>29856</string>" "$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
}

@test "install bakes the rest of the profile: state root, Claude config dir" {
    # The same set romp-manager's specEnv hands an aux kernel — a profile that is only half
    # carried is the silent-divergence bug, not a smaller version of it.
    export ROMP_STATE_DIR="$TEST_DIR/alt-state" CLAUDE_CONFIG_DIR="$TEST_DIR/alt-claude"
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    grep -q "^Environment=ROMP_STATE_DIR=$TEST_DIR/alt-state$"      "$unit"
    grep -q "^Environment=CLAUDE_CONFIG_DIR=$TEST_DIR/alt-claude$"  "$unit"
}

@test "a default install writes NO instance env — unchanged for everyone not doing this" {
    # setup() cleared the set, so this is the single-user machine's install.
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    run grep -q "ROMP_SERVE_PORT\|ROMP_KERNEL_PORT\|ROMP_POSTAL_PORT\|ROMP_MANAGER_PORT\|ROMP_STATE_DIR\|CLAUDE_CONFIG_DIR" "$unit"
    [ "$status" -ne 0 ]
    # ...and the file is still well-formed around the seam: the always-present
    # (optional, dash-prefixed) EnvironmentFile line, a blank line, then [Install].
    grep -q "^Environment=ROMP_SUPERVISED=1$" "$unit"
    grep -q "^EnvironmentFile=-" "$unit"
    grep -q "^\[Install\]$" "$unit"
    [ -z "$(sed -n '/^EnvironmentFile=-/{n;p;}' "$unit")" ]
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    run grep -q "ROMP_SERVE_PORT\|ROMP_STATE_DIR\|CLAUDE_CONFIG_DIR" "$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    [ "$status" -ne 0 ]        # (a bare `! cmd` that is not the test's last statement can never fail it)
}

@test "the rendered unit and plist stay well-formed with the instance env present" {
    export ROMP_SERVE_PORT=29856 ROMP_MANAGER_PORT=7433
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    # every Environment= line sits in [Service], i.e. before [Install]
    local envlast instline
    envlast="$(grep -n '^Environment=' "$unit" | tail -1 | cut -d: -f1)"
    instline="$(grep -n '^\[Install\]$' "$unit" | cut -d: -f1)"
    [ "$envlast" -lt "$instline" ]
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    # the pairs land INSIDE EnvironmentVariables, and the plist still parses
    if command -v plutil >/dev/null 2>&1; then plutil -lint "$plist" >/dev/null; fi
    local dictline portline closeline
    dictline="$(grep -n '<key>EnvironmentVariables</key>' "$plist" | cut -d: -f1)"
    portline="$(grep -n '<key>ROMP_SERVE_PORT</key>' "$plist" | cut -d: -f1)"
    closeline="$(grep -n '<key>RunAtLoad</key>' "$plist" | cut -d: -f1)"
    [ "$dictline" -lt "$portline" ]
    [ "$portline" -lt "$closeline" ]
}

@test "install (Linux): unit loads optional extra service env (service.env)" {
    # EnvironmentFile=- (leading dash): missing file is a no-op, so a default
    # install behaves exactly as before anyone creates service.env.
    XDG_CONFIG_HOME="$HOME/.config" ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    grep -Fq "EnvironmentFile=-$HOME/.config/romp/service.env" "$ROMP_SYSTEMD_DIR/romp-manager.service"
}

@test "install carries a non-default env-file path into the unit (quoted) and the plist (escaped); a default install does not" {
    # kernel/credentials.py resolves the env file from the SERVICE's environment, which never sees the
    # installing shell's ROMP_SERVICE_ENV_FILE, so a non-default path baked into EnvironmentFile= alone
    # was read by systemd and not by the kernel's own read of the same file (its boot check today). The
    # resolved path rides the unit and the plist whenever it is not the default.
    # every character class systemd or XML would mangle: a space (word-split), a double quote and a
    # backslash (quoting), a percent sign (specifier expansion), an ampersand (XML)
    local odd='alt "q" \b %z & dir'
    export ROMP_SERVICE_ENV_FILE="$TEST_DIR/$odd/service.env"
    mkdir -p "$TEST_DIR/$odd"
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    local unit="$ROMP_SYSTEMD_DIR/romp-manager.service"
    local exp_env='Environment="ROMP_SERVICE_ENV_FILE='"$TEST_DIR"'/alt \"q\" \\b %%z & dir/service.env"'   # quoted, escaped, % doubled
    grep -Fq "$exp_env" "$unit"
    local exp_file='EnvironmentFile=-'"$TEST_DIR"'/alt "q" \b %%z & dir/service.env'                         # % doubled here too
    grep -Fq "$exp_file" "$unit"
    [ -z "$(sed -n '/^EnvironmentFile=-/{n;p;}' "$unit")" ]                                     # the seam is unchanged
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    local plist="$ROMP_LAUNCHD_DIR/com.romp.manager.plist"
    local exp_plist='<key>ROMP_SERVICE_ENV_FILE</key><string>'"$TEST_DIR"'/alt &quot;q&quot; \b %z &amp; dir/service.env</string>'
    grep -Fq "$exp_plist" "$plist"
    command -v python3 >/dev/null 2>&1 && python3 -c "import plistlib,sys; plistlib.load(open(sys.argv[1],'rb'))" "$plist"
    unset ROMP_SERVICE_ENV_FILE
    ROMP_OS_OVERRIDE=Linux run "$SVC" install
    [ "$status" -eq 0 ]
    run grep -q "ROMP_SERVICE_ENV_FILE" "$unit"
    [ "$status" -ne 0 ]        # (a bare `! cmd` that is not the test's last statement can never fail it)
    ROMP_OS_OVERRIDE=Darwin run "$SVC" install
    [ "$status" -eq 0 ]
    run grep -q "ROMP_SERVICE_ENV_FILE" "$plist"
    [ "$status" -ne 0 ]
}

# ─── stop / start: the supervisor halves of `romp down` / `romp up` ──────────────────────────
# A stop has to go THROUGH the supervisor: the manager exiting on its own is a crash to
# Restart=always / KeepAlive and it respawns within seconds. ROMP_SYSTEMCTL stubs systemctl the
# way ROMP_LAUNCHCTL stubs launchctl; both record their argv so the tests assert the exact call.

_systemctl_stub() {
    # $1 = what `is-active` answers (active|inactive|failed); every call's argv lands in systemctl-calls
    local stub="$TEST_DIR/systemctl-stub" calls="$TEST_DIR/systemctl-calls"
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$*" >> "$calls"
case "\$2" in
  is-active) echo "$1"; [ "$1" = active ] ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$stub"
    printf '%s' "$stub"
}

@test "stop (Linux): stops the unit through systemctl and says it stays stopped" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub; stub="$(_systemctl_stub active)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" stop
    [ "$status" -eq 0 ]
    grep -qx -- '--user stop romp-manager.service' "$TEST_DIR/systemctl-calls"
    [[ "$output" == *"stays stopped until"* ]]
    # never a disable: the unit stays enabled so the next boot (linger) brings it back
    run grep -q 'disable' "$TEST_DIR/systemctl-calls"
    [ "$status" -ne 0 ]
}

@test "start (Linux): starts the unit through systemctl" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub; stub="$(_systemctl_stub inactive)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" start
    [ "$status" -eq 0 ]
    grep -qx -- '--user start romp-manager.service' "$TEST_DIR/systemctl-calls"
    [[ "$output" == *"Started the login service"* ]]
}

@test "stop / start with no unit installed exit 3 and touch nothing: the caller falls back" {
    unset ROMP_SERVICE_NO_LOAD
    local stub; stub="$(_systemctl_stub inactive)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" stop
    [ "$status" -eq 3 ]
    [[ "$output" == *"no login service is installed"* ]]
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" start
    [ "$status" -eq 3 ]
    [ ! -e "$TEST_DIR/systemctl-calls" ]
    # macOS: the same contract against the plist
    ROMP_OS_OVERRIDE=Darwin run "$SVC" stop
    [ "$status" -eq 3 ]
    [[ "$output" == *"no login agent is installed"* ]]
}

@test "stop (Linux): a failing systemctl stop is loud and exit 1" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/systemctl-stub"
    printf '#!/bin/sh\ncase "$2" in is-active) echo active; exit 0 ;; esac\necho "Failed to stop" >&2\nexit 1\n' > "$stub"
    chmod +x "$stub"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" stop
    [ "$status" -eq 1 ]
    [[ "$output" == *"stop romp-manager.service failed"* ]]
}

@test "stop (macOS): boots the job out and waits for it to leave launchd" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    # loaded until the bootout lands; `print` fails once bootout has been called
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
case "\$1" in
  print) grep -q bootout "$calls" && exit 1; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" stop
    [ "$status" -eq 0 ]
    grep -q bootout "$calls"
    [[ "$output" == *"Stopped the login agent"* ]]
}

@test "start (macOS): a booted-out job is bootstrapped again; a loaded one is kickstarted" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    # not loaded: print fails, so bootstrap
    cat > "$stub" <<EOF
#!/bin/sh
echo "\$1" >> "$calls"
[ "\$1" = print ] && exit 1
exit 0
EOF
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" start
    [ "$status" -eq 0 ]
    grep -q bootstrap "$calls"
    run grep -q kickstart "$calls"
    [ "$status" -ne 0 ]
    # loaded: print succeeds, so kickstart, no bootstrap
    : > "$calls"
    printf '#!/bin/sh\necho "$1" >> "%s"\nexit 0\n' "$calls" > "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" start
    [ "$status" -eq 0 ]
    grep -q kickstart "$calls"
    run grep -q bootstrap "$calls"
    [ "$status" -ne 0 ]
}

@test "status names a deliberate stop: the romp down marker's time, and how to start again" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub; stub="$(_systemctl_stub inactive)"
    mkdir -p "$XDG_STATE_HOME/romp"
    printf '{"t": %s, "cmd": "romp down"}\n' "$(date +%s)" > "$XDG_STATE_HOME/romp/down-by-romp"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" status
    [ "$status" -eq 0 ]
    [[ "$output" == *"stopped by romp down at "* ]]
    [[ "$output" == *"(romp up to start)"* ]]
    run grep -qx running <<< "$output"
    [ "$status" -ne 0 ]
    # a running service outranks a stale marker: no "stopped" line while it answers active
    stub="$(_systemctl_stub active)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" status
    [[ "$output" == *"running"* ]]
    run grep -q 'stopped by romp down' <<< "$output"
    [ "$status" -ne 0 ]
    # no marker, not running: nothing about a deliberate stop
    rm "$XDG_STATE_HOME/romp/down-by-romp"
    stub="$(_systemctl_stub inactive)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" status
    run grep -q 'romp down' <<< "$output"
    [ "$status" -ne 0 ]
}

@test "status renders an old marker with its date, not a bare clock time" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub; stub="$(_systemctl_stub inactive)"
    mkdir -p "$XDG_STATE_HOME/romp"
    printf '{"t": %s, "cmd": "romp down"}\n' "$(( $(date +%s) - 3 * 86400 ))" > "$XDG_STATE_HOME/romp/down-by-romp"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" status
    [[ "$output" =~ stopped\ by\ romp\ down\ at\ [0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2} ]]
}

@test "stop (Linux): an installed unit that is not running is exit 4, says so, and is not stopped again" {
    # `systemctl --user stop` on an inactive unit exits 0, which would read as a stop while a manager
    # started outside the service kept running; the caller stops that one itself on a 4
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Linux ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub; stub="$(_systemctl_stub inactive)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" stop
    [ "$status" -eq 4 ]
    [[ "$output" == *"installed but not running"* ]]
    run grep -q -- '--user stop' "$TEST_DIR/systemctl-calls"
    [ "$status" -ne 0 ]
    run grep -q 'Stopped the login service' <<< "$output"
    [ "$status" -ne 0 ]
    # a failed unit is not running either
    stub="$(_systemctl_stub failed)"
    ROMP_SYSTEMCTL="$stub" ROMP_OS_OVERRIDE=Linux run "$SVC" stop
    [ "$status" -eq 4 ]
}

@test "stop (macOS): an installed agent that is not loaded is exit 4, says so, and no bootout" {
    unset ROMP_SERVICE_NO_LOAD
    ROMP_OS_OVERRIDE=Darwin ROMP_SERVICE_NO_LOAD=1 "$SVC" install >/dev/null
    local stub="$TEST_DIR/launchctl-stub" calls="$TEST_DIR/launchctl-calls"
    printf '#!/bin/sh\necho "$1" >> "%s"\n[ "$1" = print ] && exit 1\nexit 0\n' "$calls" > "$stub"
    chmod +x "$stub"
    ROMP_LAUNCHCTL="$stub" ROMP_OS_OVERRIDE=Darwin run "$SVC" stop
    [ "$status" -eq 4 ]
    [[ "$output" == *"installed but not running"* ]]
    run grep -q bootout "$calls"
    [ "$status" -ne 0 ]
    run grep -q 'Stopped the login agent' <<< "$output"
    [ "$status" -ne 0 ]
}
