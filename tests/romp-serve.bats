#!/usr/bin/env bats

# romp-serve maps the manager's spawn contract (--port / ROMP_SERVE_PORT) onto the
# Python kernel's env and execs it. The kernel binds loopback only; tailnet reach
# is `tailscale serve` proxying to loopback, so there is no persisted host opt-in
# (`romp --serve` removed 2026-07-19).

BIN="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)"
ROMP_SERVE="$BIN/romp-serve"
ROMP_SCRIPT="$BIN/romp"

setup() {
    # Running this suite INSIDE a romp session inherits the live kernel's port env, which would
    # turn every "unset" case below into an override (same trap tests/romp-service.bats documents).
    # ROMP_STATE_DIR too: a kernel exports it to its sessions, and pick_python reads it before
    # XDG_STATE_HOME, so with it inherited the venv cases below would read a LIVE venv's pyvenv.cfg.
    # The two port spellings stay unset rather than poisoned (their unset case is under test, and the
    # kernel this suite execs is a stub that never listens); the manager port is poisoned as a floor.
    unset ROMP_SERVE_PORT ROMP_KERNEL_PORT ROMP_STATE_DIR
    export ROMP_MANAGER_PORT=1
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    mkdir -p "$XDG_STATE_HOME/romp"
    # Stub kernel: print the env romp-serve hands it, then exit (no real server).
    export ROMP_KERNEL_BIN="$TEST_DIR/stub-kernel"
    cat > "$ROMP_KERNEL_BIN" << 'STUB'
#!/usr/bin/env bash
echo "PORT=${ROMP_KERNEL_PORT:-}"
echo "SERVEPORT=${ROMP_SERVE_PORT:-}"
echo "HOST=${ROMP_SERVE_HOST:-}"
echo "NOOPEN=${ROMP_KERNEL_NO_OPEN:-}"
echo "MGRPID=${ROMP_MANAGER_PID:-}"
STUB
    chmod +x "$ROMP_KERNEL_BIN"
    # romp-serve now execs the kernel VIA a picked python (`exec "$PY" "$KERNEL"`); the stub kernel is
    # bash, so hand it a "python" that just runs its argument as a shell script.
    export ROMP_PYTHON="$TEST_DIR/fake-python"
    cat > "$ROMP_PYTHON" << 'SHIM'
#!/usr/bin/env bash
exec bash "$@"
SHIM
    chmod +x "$ROMP_PYTHON"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "romp-serve: maps --port to ROMP_KERNEL_PORT, sets no-open, execs the kernel" {
    run "$ROMP_SERVE" --port 9999
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=9999"* ]]
    [[ "$output" == *"NOOPEN=1"* ]]
}

@test "romp-serve: host defaults to 127.0.0.1 with no opt-in" {
    run "$ROMP_SERVE" --port 9999
    [[ "$output" == *"HOST=127.0.0.1"* ]]
}

@test "romp-serve: a stale serve-host file can NOT rebind the kernel off loopback" {
    # The `romp --serve` opt-in is removed; a leftover state file must be ignored,
    # never silently expose the kernel on 0.0.0.0.
    printf '0.0.0.0\n' > "$XDG_STATE_HOME/romp/serve-host"
    run "$ROMP_SERVE" --port 9999
    [[ "$output" == *"HOST=127.0.0.1"* ]]
}

@test "romp-serve: explicit --host still wins (the manager's spawn seam)" {
    run "$ROMP_SERVE" --port 9999 --host 0.0.0.0
    [[ "$output" == *"HOST=0.0.0.0"* ]]
}

@test "romp-serve: ROMP_SERVE_PORT fallback + forwards ROMP_MANAGER_PID" {
    ROMP_MANAGER_PID=4242 ROMP_SERVE_PORT=29855 run "$ROMP_SERVE"
    [[ "$output" == *"PORT=29855"* ]]
    [[ "$output" == *"MGRPID=4242"* ]]
}

# ─── the two spellings of the listen port ───────────────────────────────────────────────────
# ROMP_SERVE_PORT (service-facing) and ROMP_KERNEL_PORT (process-facing) name ONE value, and
# this script is the seam where they meet. It used to read only the first and stamp it over the
# second, so renumbering a second kernel with the documented knob alone put the kernel on the
# primary's port while the CLI kept printing the configured one.

@test "romp-serve: ROMP_KERNEL_PORT alone (the documented knob) reaches the kernel" {
    ROMP_KERNEL_PORT=29856 run "$ROMP_SERVE"
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=29856"* ]]
}

@test "romp-serve: exports BOTH spellings from the one resolved port" {
    # Nothing downstream (the postal bus, the wake hook, a `romp` verb in a session) may read a
    # stale copy of the other name.
    ROMP_KERNEL_PORT=29856 run "$ROMP_SERVE"
    [[ "$output" == *"PORT=29856"* ]]
    [[ "$output" == *"SERVEPORT=29856"* ]]
    ROMP_SERVE_PORT=29857 run "$ROMP_SERVE"
    [[ "$output" == *"PORT=29857"* ]]
    [[ "$output" == *"SERVEPORT=29857"* ]]
}

@test "romp-serve: --port settles a disagreement and wins over both env spellings" {
    # The manager always passes --port; that is the kernel's own name for itself, so a stale
    # inherited env copy must never override it.
    ROMP_SERVE_PORT=29855 ROMP_KERNEL_PORT=29999 run "$ROMP_SERVE" --port 30001
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=30001"* ]]
    [[ "$output" == *"SERVEPORT=30001"* ]]
}

@test "romp-serve: conflicting spellings with no --port REFUSE to start" {
    # A silent pick here is the collision that reports success. Fail loudly instead.
    ROMP_SERVE_PORT=29855 ROMP_KERNEL_PORT=29856 run "$ROMP_SERVE"
    [ "$status" -ne 0 ]
    [[ "$output" == *"29855"* ]]
    [[ "$output" == *"29856"* ]]
    ! printf '%s\n' "$output" | grep -q '^PORT='     # the stub kernel never ran
}

@test "romp-serve: matching spellings are not a conflict" {
    ROMP_SERVE_PORT=29856 ROMP_KERNEL_PORT=29856 run "$ROMP_SERVE"
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=29856"* ]]
}

@test "romp-serve: neither set and no --port leaves both unset (the kernel's own default)" {
    run "$ROMP_SERVE"
    [ "$status" -eq 0 ]
    [ "$(printf '%s\n' "$output" | grep '^PORT=')" = "PORT=" ]
    [ "$(printf '%s\n' "$output" | grep '^SERVEPORT=')" = "SERVEPORT=" ]
}

# ── the Python floor (issue 1600) ──────────────────────────────────────────────────────────
@test "romp-serve: refuses to start the kernel on a python below 3.10, naming it and the install command" {
    # a python that answers the version probe with 3.9 (and would happily exec the stub kernel otherwise)
    cat > "$TEST_DIR/old-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *romp-pyver*) echo "romp-pyver 3.9"; exit 0 ;;
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/old-python"
    ROMP_PYTHON="$TEST_DIR/old-python" run "$ROMP_SERVE" --port 29999
    [ "$status" -eq 2 ]                                      # the floor's own code (round two: install.sh tells it from the other refusals)
    [[ "$output" == *"python 3.9"* ]]
    [[ "$output" == *"need 3.10 or newer"* ]]
    [[ "$output" == *"brew install python@3.13"* ]]
    [[ "$output" != *"PORT="* ]]                             # the stub kernel never ran
}

@test "romp-serve: --print-python prints the interpreter the kernel would run, floor applied, and starts nothing" {
    run "$ROMP_SERVE" --print-python
    [ "$status" -eq 0 ]
    [ "$output" = "$ROMP_PYTHON" ]                           # the pin, verbatim, as the pick returns it
    cat > "$TEST_DIR/old-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) echo "romp-pyver 3.8"; exit 0 ;; esac
exit 0
OLD
    chmod +x "$TEST_DIR/old-python"
    ROMP_PYTHON="$TEST_DIR/old-python" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 2 ]
    [[ "$output" == *"python 3.8"* ]]
    # the usage line names the flag
    grep -q 'romp-serve \[--port N\] \[--host H\] \[--print-python\]' "$ROMP_SERVE"
}

@test "romp-serve: the floor reads the LAST line of the probe's output, so a chatty site customization cannot hide a 3.9" {
    cat > "$TEST_DIR/chatty-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *romp-pyver*) echo "sitecustomize: hello from a chatty site"; echo "2.7"; echo "romp-pyver 3.9"; exit 0 ;;   # a bare 2.7 in the chatter is not the version
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/chatty-python"
    ROMP_PYTHON="$TEST_DIR/chatty-python" run "$ROMP_SERVE" --port 29997
    [ "$status" -eq 2 ]
    [[ "$output" == *"python 3.9"* ]]
    [[ "$output" != *"PORT="* ]]
}

@test "romp-serve: an interpreter that blocks on its version probe is refused as unresponsive within the bound, not exec'd and not hung" {
    # round three of issue 1600: the probe is the picked interpreter's FIRST execution and was unbounded, so a blocking one
    # (a stalled network mount, a site customization reaching for the network) hung install.sh with no output
    cat > "$TEST_DIR/blocking-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *-c*) sleep 60 ;;      # blocks on any -c probe (the base's probe program has no sentinel, and must hang too)
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/blocking-python"
    # bounded from outside where timeout exists (a regression that hung would be a clean red); the probe's own bound is what is tested
    local tmo; tmo="$(command -v timeout || true)"
    ROMP_PYTHON="$TEST_DIR/blocking-python" run ${tmo:+"$tmo" 40} "$ROMP_SERVE" --print-python
    [ "$status" -eq 1 ]                                      # its own refusal, exit 1: install.sh's pass-through
    [[ "$output" == *"did not answer its version probe"* ]]
    [[ "$output" == *"blocking-python"* ]]
    [[ "$output" != *"PORT="* ]]
}

@test "romp-serve: an interpreter that ignores TERM is killed a second after the bound (-k) and refused; no watchdog, no clock" {
    # round four of issue 1600: timeout carried no -k, so a TERM-ignoring interpreter hung past the bound. Round five dropped
    # the watchdog that stood in for timeout where there is none (its TERM trap ran under set -e and let a blocking
    # interpreter through): where coreutils timeout is absent the probe is unbounded, as the picker's own runs are.
    cat > "$TEST_DIR/deaf-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *-c*) trap '' TERM; exec sleep 60 ;;      # becomes its sleep: the KILL after the ignored TERM leaves no stray child
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/deaf-python"
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "the bound needs coreutils timeout"
    local t0=$SECONDS
    ROMP_PYTHON="$TEST_DIR/deaf-python" run "$tmo" 40 "$ROMP_SERVE" --print-python
    [ "$status" -eq 1 ]
    [[ "$output" == *"did not answer its version probe"* ]]
    [ $((SECONDS - t0)) -lt 15 ]                             # the bound plus the kill, not the outer bound
    [[ "$output" != *"Killed"* ]]                             # the KILLed timeout leaves no job-status line in the log
}

_dead() {   # $1 pid: gone, or a zombie awaiting its reap
    local st; st="$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' ')"
    [ -z "$st" ] || [ "${st#Z}" != "$st" ]
}

@test "romp-serve: a child the blocked interpreter left behind dies at the bound with it (the group is signalled)" {
    # round five of issue 1600: --foreground handed the signals to the interpreter alone, so a child it had started (a
    # site customization's helper, a sleep here) outlived the bound, one per probe; plain timeout signals the group
    cat > "$TEST_DIR/forking-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *-c*) sleep 60 & echo $! > "$ROMP_TEST_PIDFILE"; wait ;;   # blocks, with a child of its own
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/forking-python"
    local tmo; tmo="$(command -v timeout || true)"
    [ -n "$tmo" ] || skip "the bound needs coreutils timeout"
    ROMP_TEST_PIDFILE="$TEST_DIR/child.pid" ROMP_PYTHON="$TEST_DIR/forking-python" run "$tmo" 40 "$ROMP_SERVE" --print-python
    [ "$status" -eq 1 ]
    [[ "$output" == *"did not answer its version probe"* ]]
    [ -s "$TEST_DIR/child.pid" ]
    local child; child="$(cat "$TEST_DIR/child.pid")"
    if ! _dead "$child"; then kill -KILL "$child" 2>/dev/null; return 1; fi   # the child outlived the bound (killed here so the suite's wake is clean)
}

@test "romp-serve: a TMPDIR that is not there, or a PATH without mktemp, refuses no good interpreter: the file falls to /tmp, or the read to a pipe" {
    # round five of issue 1600 (round three started it): mktemp ran unguarded under set -e, so a stale TMPDIR (a launchd
    # agent's /var/folders path across a reboot) refused a good interpreter with mktemp's own message, and a PATH
    # without mktemp was exit 127
    cat > "$TEST_DIR/good-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) echo "romp-pyver 3.12"; exit 0 ;; esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/good-python"
    TMPDIR="$TEST_DIR/no-such-tmp" ROMP_PYTHON="$TEST_DIR/good-python" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/good-python" ]
    local bare="$TEST_DIR/bare"; mkdir -p "$bare"
    local t; for t in bash sh cat rm date dirname readlink; do ln -s "$(command -v "$t")" "$bare/$t"; done   # no mktemp, no timeout
    PATH="$bare" ROMP_PYTHON="$TEST_DIR/good-python" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/good-python" ]
    # and the floor still holds through the pipe read
    cat > "$TEST_DIR/old-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) echo "romp-pyver 3.9"; exit 0 ;; esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/old-python"
    PATH="$bare" ROMP_PYTHON="$TEST_DIR/old-python" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 2 ]
}

@test "romp-serve: a TERM mid-probe leaves no probe file behind" {
    # round five of issue 1600: the probe file was removed after the read alone, so a romp-serve stopped during the probe
    # (a manager restart mid-launch) left one romp-pyver.* per stop in TMPDIR
    cat > "$TEST_DIR/blocking-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *-c*) sleep 60 ;; esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/blocking-python"
    local tmp="$TEST_DIR/tmp"; mkdir -p "$tmp"
    local tmo; tmo="$(command -v timeout || true)"
    TMPDIR="$tmp" ROMP_PYTHON="$TEST_DIR/blocking-python" ${tmo:+"$tmo" 40} "$ROMP_SERVE" --print-python >/dev/null 2>&1 &
    local pid=$!
    sleep 1
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" || true                       # the trap runs once the foreground probe returns, at the bound at the latest
    [ -z "$(ls "$tmp"/romp-pyver.* 2>/dev/null)" ]
}

@test "romp-serve: a helper the interpreter leaves holding its stdout cannot hold the version read; the probe returns at once" {
    # round four, medium 2: the substitution read until every writer closed the pipe, so a prompt interpreter whose site
    # customization spawned a helper made the read last the helper's life (8 s here); the version is read from a file
    cat > "$TEST_DIR/helper-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in
  *-c*) ( sleep 8 ) & echo "romp-pyver 3.12"; exit 0 ;;   # a child keeps the stdout pipe; the interpreter exits at once (any -c probe: the base's too)
esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/helper-python"
    local t0=$SECONDS
    ROMP_PYTHON="$TEST_DIR/helper-python" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/helper-python" ]
    [ $((SECONDS - t0)) -lt 5 ]                              # not the helper's 8 seconds
}

@test "romp-serve: an interpreter that itself exits 124 or 137 from the probe is refused as unresponsive: from the bounded branch the code IS the bound, no clock" {
    # round five of issue 1600 dropped round four's clock (a SECONDS-grained guess that misread a 124 at about 4 s)
    command -v timeout >/dev/null 2>&1 || skip "the bounded branch needs coreutils timeout"
    local code
    for code in 124 137; do
        cat > "$TEST_DIR/oddexit-python" << OLD
#!/usr/bin/env bash
case "\$*" in *romp-pyver*) exit $code ;; esac
exec bash "\$@"
OLD
        chmod +x "$TEST_DIR/oddexit-python"
        ROMP_PYTHON="$TEST_DIR/oddexit-python" run "$ROMP_SERVE" --port 29994
        [ "$status" -eq 1 ]
        [[ "$output" == *"did not answer its version probe"* ]]
        [[ "$output" == *"of its own accord reads the same"* ]]
        [[ "$output" != *"PORT=29994"* ]]
    done
}

@test "romp-serve: a line printed AFTER the version, or a CRLF line ending, cannot hide a 3.9" {
    # round three, low 1: the last-line read let a 3.9 through when an atexit hook printed after it or the output was CRLF
    cat > "$TEST_DIR/atexit-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) echo "romp-pyver 3.9"; echo "atexit: goodbye from a chatty hook"; exit 0 ;; esac
exec bash "$@"
OLD
    cat > "$TEST_DIR/crlf-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) printf 'romp-pyver 3.9\r\n'; exit 0 ;; esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/atexit-python" "$TEST_DIR/crlf-python"
    ROMP_PYTHON="$TEST_DIR/atexit-python" run "$ROMP_SERVE" --port 29996
    [ "$status" -eq 2 ]
    [[ "$output" == *"python 3.9"* ]]
    [[ "$output" != *"PORT="* ]]
    ROMP_PYTHON="$TEST_DIR/crlf-python" run "$ROMP_SERVE" --port 29995
    [ "$status" -eq 2 ]
    [[ "$output" == *"python 3.9"* ]]
    [[ "$output" != *"PORT="* ]]
    # round four, low 2: chatter that is a bare 2.7 before a good 3.12 does not refuse the 3.12 (the sentinel is what is read)
    cat > "$TEST_DIR/mixed-python" << 'OLD'
#!/usr/bin/env bash
case "$*" in *romp-pyver*) echo "2.7"; echo "romp-pyver 3.12"; exit 0 ;; esac
exec bash "$@"
OLD
    chmod +x "$TEST_DIR/mixed-python"
    ROMP_PYTHON="$TEST_DIR/mixed-python" run "$ROMP_SERVE" --port 29993
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=29993"* ]]
}

@test "romp-serve: the other refusals keep exit 1, so install.sh can tell them from the floor" {
    ROMP_SERVE_PORT=29855 ROMP_KERNEL_PORT=29856 run "$ROMP_SERVE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"disagree"* ]]
    ROMP_KERNEL_BIN="$TEST_DIR/no-such-kernel" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 1 ]
    [[ "$output" == *"kernel not found"* ]]
    ROMP_PYTHON="$TEST_DIR/no-such/python3.12" run "$ROMP_SERVE" --print-python
    [ "$status" -eq 1 ]
    [[ "$output" == *"not an executable interpreter"* ]]
}

@test "romp-serve: an interpreter that reports no version is left to the exec as before (the suites' shell stand-in)" {
    run "$ROMP_SERVE" --port 29998
    [ "$status" -eq 0 ]
    [[ "$output" == *"PORT=29998"* ]]
}

@test "romp --serve: removed — rejected as unknown, writes no state" {
    run "$ROMP_SCRIPT" --serve on
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown option"* ]]
    [ ! -f "$XDG_STATE_HOME/romp/serve-host" ]
}

# ─── pick_python: the ROMP_PYTHON override, and the newest-first fallback for a machine with no venv ─
# Unit tests over the extracted function. It runs only candidates the tests lay down as fakes, so a
# bare fake PATH is enough; that PATH has no `timeout`, which is the no-coreutils path, and one test
# below adds the real one back. The e2e wiring (exec "$PY" "$KERNEL") is covered by every test above
# via the ROMP_PYTHON shim in setup().

extract_pick() { sed -n '/^pick_python()/,/^}/p' "$1"; }

@test "pick_python: ROMP_PYTHON override wins verbatim" {
    # The pin is checked to be an executable interpreter before it is echoed (the cases further down),
    # so the fixture is an executable stub rather than a path that does not exist.
    mkdir -p "$TEST_DIR/custom"
    printf '#!/bin/sh\n' > "$TEST_DIR/custom/python"; chmod +x "$TEST_DIR/custom/python"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON="$TEST_DIR/custom/python" run pick_python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/custom/python" ]
}

@test "pick_python: newest python3.1x on PATH beats plain python3" {
    fakebin="$TEST_DIR/fakebin"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3.12"; chmod +x "$fakebin/python3.12"
    printf '#!/bin/sh\n' > "$fakebin/python3";    chmod +x "$fakebin/python3"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= PATH="$fakebin" run pick_python
    [ "$output" = "$fakebin/python3.12" ]
}

@test "pick_python: probes ~/.local/bin explicitly (non-login ssh shells lack it on PATH)" {
    mkdir -p "$HOME/.local/bin"
    printf '#!/bin/sh\n' > "$HOME/.local/bin/python3.11"; chmod +x "$HOME/.local/bin/python3.11"
    fakebin="$TEST_DIR/fakebin2"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3"; chmod +x "$fakebin/python3"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= PATH="$fakebin" run pick_python
    [ "$output" = "$HOME/.local/bin/python3.11" ]
}

@test "pick_python: falls back to plain python3 when no 3.1x exists anywhere" {
    fakebin="$TEST_DIR/fakebin3"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3"; chmod +x "$fakebin/python3"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= PATH="$fakebin" run pick_python
    [ "$output" = "$fakebin/python3" ]
}

# ─── pick_python: the SDK venv names the interpreter; the newest install is only the fallback ────
# A stray `uv python install 3.14` put a python3.14 into ~/.local/bin, and the next kernel respawn
# ran on it while the venv's compiled extensions were still 3.12's: every SDK session died at
# import with a message blaming a missing install (2026-09-06). The venv's pyvenv.cfg records the
# interpreter it was built with, so a machine with a venv runs THAT; newest-first is for machines
# without one.

write_venv_cfg() {   # $1 = state root, then the pyvenv.cfg lines
    local root="$1"; shift
    mkdir -p "$root/sdkvenv"
    printf '%s\n' "$@" > "$root/sdkvenv/pyvenv.cfg"
}

@test "pick_python: a venv's recorded interpreter (executable key) beats a newer python on PATH" {
    fakebin="$TEST_DIR/fakebin-venv"; mkdir -p "$fakebin" "$TEST_DIR/venvpy"
    printf '#!/bin/sh\n' > "$fakebin/python3.14"; chmod +x "$fakebin/python3.14"
    printf '#!/bin/sh\n' > "$TEST_DIR/venvpy/python3.12"; chmod +x "$TEST_DIR/venvpy/python3.12"
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/venvpy" "version = 3.12.3" \
        "executable = $TEST_DIR/venvpy/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= PATH="$fakebin" run pick_python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/venvpy/python3.12" ]
}

@test "pick_python: an older venv with only home + version still names its interpreter" {
    # python < 3.11 wrote no `executable =` line; home + version reach the same binary.
    fakebin="$TEST_DIR/fakebin-venv2"; mkdir -p "$fakebin" "$TEST_DIR/venvpy2"
    printf '#!/bin/sh\n' > "$fakebin/python3.14"; chmod +x "$fakebin/python3.14"
    printf '#!/bin/sh\n' > "$TEST_DIR/venvpy2/python3.10"; chmod +x "$TEST_DIR/venvpy2/python3.10"
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/venvpy2" "include-system-site-packages = false" \
        "version = 3.10.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= PATH="$fakebin" run pick_python
    [ "$status" -eq 0 ]
    [ "$output" = "$TEST_DIR/venvpy2/python3.10" ]
}

@test "pick_python: ROMP_STATE_DIR is where the venv is looked for" {
    fakebin="$TEST_DIR/fakebin-venv3"; mkdir -p "$fakebin" "$TEST_DIR/venvpy3"
    printf '#!/bin/sh\n' > "$fakebin/python3.14"; chmod +x "$fakebin/python3.14"
    printf '#!/bin/sh\n' > "$TEST_DIR/venvpy3/python3.12"; chmod +x "$TEST_DIR/venvpy3/python3.12"
    write_venv_cfg "$TEST_DIR/altstate" "home = $TEST_DIR/venvpy3" "version = 3.12.3" \
        "executable = $TEST_DIR/venvpy3/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON= ROMP_STATE_DIR="$TEST_DIR/altstate" PATH="$fakebin" run pick_python
    [ "$output" = "$TEST_DIR/venvpy3/python3.12" ]
}

@test "pick_python: a venv whose interpreter is gone falls back to newest-first and SAYS so" {
    fakebin="$TEST_DIR/fakebin-gone"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3.13"; chmod +x "$fakebin/python3.13"
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/no-such-dir" "version = 3.12.3" \
        "executable = $TEST_DIR/no-such-dir/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    # stderr to a file rather than `run --separate-stderr`: that flag needs mktemp, and PATH is bare here.
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.13" ]
    [[ "$err" == *"$TEST_DIR/no-such-dir/python3.12"* ]]    # names the interpreter it could not run
    [[ "$err" == *"romp-sdk-setup"* ]]                       # and the way to make the venv match again
}

@test "pick_python: a venv with a broken interpreter (present, will not run) also falls back" {
    fakebin="$TEST_DIR/fakebin-broken"; mkdir -p "$fakebin" "$TEST_DIR/brokenpy"
    printf '#!/bin/sh\n' > "$fakebin/python3.13"; chmod +x "$fakebin/python3.13"
    printf '#!/bin/sh\nexit 127\n' > "$TEST_DIR/brokenpy/python3.12"; chmod +x "$TEST_DIR/brokenpy/python3.12"
    write_venv_cfg "$XDG_STATE_HOME/romp" "executable = $TEST_DIR/brokenpy/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.13" ]
    [[ "$err" == *"$TEST_DIR/brokenpy/python3.12"* ]]
}

@test "pick_python: no venv means newest-first, silently (a fresh machine before romp-sdk-setup)" {
    fakebin="$TEST_DIR/fakebin-fresh"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3.13"; chmod +x "$fakebin/python3.13"
    printf '#!/bin/sh\n' > "$fakebin/python3.12"; chmod +x "$fakebin/python3.12"
    [ ! -e "$XDG_STATE_HOME/romp/sdkvenv" ]
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.13" ]
    [ ! -s "$TEST_DIR/stderr" ]
}

@test "pick_python: ROMP_PYTHON wins over the venv's recorded interpreter too" {
    mkdir -p "$TEST_DIR/venvpy4" "$TEST_DIR/custom"
    printf '#!/bin/sh\n' > "$TEST_DIR/venvpy4/python3.12"; chmod +x "$TEST_DIR/venvpy4/python3.12"
    printf '#!/bin/sh\n' > "$TEST_DIR/custom/python";       chmod +x "$TEST_DIR/custom/python"
    write_venv_cfg "$XDG_STATE_HOME/romp" "executable = $TEST_DIR/venvpy4/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON="$TEST_DIR/custom/python" run pick_python
    [ "$output" = "$TEST_DIR/custom/python" ]
}

@test "pick_python: romp-serve, romp-sdk-setup and romp-codex-setup carry the SAME picker (each venv must match the kernel)" {
    # The kernel imports both venvs' site-packages in-process, so both setup scripts must pick the
    # interpreter romp-serve will run, by the same rules, byte for byte. romp-codex-setup carried an
    # older copy (no venv-follow, no pin check) before this pin covered it.
    [ "$(extract_pick "$ROMP_SERVE" | wc -l)" -gt 20 ]     # armed: an empty extraction would diff clean
    diff <(extract_pick "$ROMP_SERVE") <(extract_pick "$BIN/romp-sdk-setup")
    diff <(extract_pick "$ROMP_SERVE") <(extract_pick "$BIN/romp-codex-setup")
}

# ─── pick_python: the pin is checked, and the candidates are checked ──────────────────────────────
# A fake interpreter that claims one X.Y and one build (the default, or `t` for free-threaded): exits 0
# for the check naming both, 1 for any other version check, 0 for `-c pass`. The check's text carries
# the wanted build as `bool('t')` or `bool('')`, so a stub named python3.14 can claim the t build (uv's
# layout) and a stub named python3.14t is never taken for a default-build venv. The bare
# `printf '#!/bin/sh\n'` fakes above answer every check with 0.
fake_python() {   # $1 path, $2 the X.Y it claims, $3 its build: empty for the default, t for free-threaded
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<STUB
#!/bin/sh
case "\$*" in *"(${2%%.*}, ${2#*.})"*"bool('${3:-}')"*) exit 0 ;; *version_info*) exit 1 ;; esac
exit 0
STUB
    chmod +x "$1"
}

@test "pick_python: ROMP_PYTHON naming a missing path is refused with the pin named, not bash's own error" {
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON="$TEST_DIR/no-such/python3.12" run pick_python
    [ "$status" -eq 1 ]
    [[ "$output" == *"ROMP_PYTHON=$TEST_DIR/no-such/python3.12"* ]]
    [[ "$output" == *"not an executable interpreter"* ]]
    [[ "$output" == *"service.env"* ]]                        # where a pin usually lives
}

@test "pick_python: ROMP_PYTHON naming a file that is not executable is refused the same way" {
    mkdir -p "$TEST_DIR/pin"; printf '#!/bin/sh\n' > "$TEST_DIR/pin/python3.12"     # no chmod +x
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON="$TEST_DIR/pin/python3.12" run pick_python
    [ "$status" -eq 1 ]
    [[ "$output" == *"not an executable interpreter"* ]]
    ROMP_PYTHON="$TEST_DIR/pin" run pick_python                # a directory is not one either
    [ "$status" -eq 1 ]
}

@test "pick_python: ROMP_PYTHON as a bare command name resolves on PATH and is echoed as given" {
    fakebin="$TEST_DIR/fakebin-pin"; mkdir -p "$fakebin"
    printf '#!/bin/sh\n' > "$fakebin/python3.12"; chmod +x "$fakebin/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON=python3.12 PATH="$fakebin" run pick_python
    [ "$status" -eq 0 ]
    [ "$output" = "python3.12" ]
    ROMP_PYTHON=python3.99 PATH="$fakebin" run pick_python
    [ "$status" -eq 1 ]
    [[ "$output" == *"ROMP_PYTHON=python3.99"* ]]
}

@test "romp-serve: a bad ROMP_PYTHON stops the launch with one romp line, and the kernel never starts" {
    # End to end. Before the check romp-serve died at its exec with bash's "No such file or directory"
    # (exit 127, no mention of the pin), and the manager respawned it every few seconds.
    ROMP_PYTHON="$TEST_DIR/no-such/python3.12" run "$ROMP_SERVE" --port 9999
    [ "$status" -eq 1 ]
    [[ "$output" == *"ROMP_PYTHON=$TEST_DIR/no-such/python3.12"* ]]
    [[ "$output" != *"No such file or directory"* ]]
    [[ "$output" != *"PORT="* ]]                              # the stub kernel never ran
}

@test "pick_python: a home/python3 that is no longer the recorded X.Y is NOT taken silently" {
    # Stdlib venvs on Debian/Ubuntu record `home = /usr/bin` and a version, no executable. A distro
    # upgrade removes python3.12 and repoints /usr/bin/python3 at 3.14: that path is present and runs,
    # and taking it put the kernel on the wrong minor with no line saying so.
    fakebin="$TEST_DIR/fakebin-upg"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$TEST_DIR/upg/python3" 3.14                  # home/python3, another minor now
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/upg" "version = 3.12.3"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]                        # newest-first, since no 3.12 is left anywhere
    [[ "$err" == *"$TEST_DIR/upg/python3.12"* ]]              # names what the venv was built with
    [[ "$err" == *"romp-sdk-setup"* ]]                        # and that the venv must be rebuilt for the pick
}

@test "pick_python: a home/python3 that IS the recorded X.Y is taken, silently (the check rejects only a mismatch)" {
    fakebin="$TEST_DIR/fakebin-same"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$TEST_DIR/same/python3" 3.12
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/same" "version = 3.12.3"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$TEST_DIR/same/python3" ]
    [ ! -s "$TEST_DIR/stderr" ]
}

@test "pick_python: a uv-built venv (home plus version_info, no executable) still names its interpreter" {
    # uv writes `home =` and `version_info =` (X.Y for one of its managed interpreters, X.Y.Z for a system
    # python) and no `executable =` line (the stdlib's venv writes `version =`), so the X.Y that gates every
    # home candidate comes from the version_info key alone; the reader takes the X.Y prefix of either shape,
    # and this cfg carries the longer one. The `version_info` fake_python matches is in the probe's Python
    # source, a different thing: every other cfg in this file writes `version =` or no version line, so the
    # key was read by nothing here.
    fakebin="$TEST_DIR/fakebin-uv"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$TEST_DIR/uvhome/python3.12" 3.12
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/uvhome" "implementation = CPython" \
        "uv = 0.8.0" "version_info = 3.12.3" "include-system-site-packages = false"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$TEST_DIR/uvhome/python3.12" ]                # the venv's interpreter, not the newest on PATH
    [ ! -s "$TEST_DIR/stderr" ]                               # and nothing about a gone interpreter
}

@test "pick_python: the recorded binary itself is checked against the recorded X.Y" {
    fakebin="$TEST_DIR/fakebin-exe"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$TEST_DIR/exe/python3" 3.14                  # `executable` kept its path, changed its minor
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.12.3" "executable = $TEST_DIR/exe/python3"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
    [ -s "$TEST_DIR/stderr" ]
}

@test "pick_python: when the recorded interpreter is gone, another python of the SAME minor beats newest-first" {
    # `executable` is a realpath into a patch-versioned install root, which a patch upgrade removes
    # while python3.12 on PATH still runs. The venv's site-packages are valid for it, so nothing needs
    # rebuilding, and the kernel must not move to 3.14 for want of looking.
    fakebin="$TEST_DIR/fakebin-minor"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$fakebin/python3.12" 3.12
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.12.4" "executable = $TEST_DIR/gone/3.12.4/bin/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.12" ]
    [[ "$err" == *"$TEST_DIR/gone/3.12.4/bin/python3.12"* ]]  # what it could not run
    [[ "$err" == *"using $fakebin/python3.12"* ]]             # and what it used instead
    [[ "$err" != *"romp-sdk-setup"* ]]                        # no rebuild is needed
}

@test "pick_python: the same-minor fallback also looks in ~/.local/bin" {
    fakebin="$TEST_DIR/fakebin-minor2"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$HOME/.local/bin/python3.12" 3.12
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.12.4" "executable = $TEST_DIR/gone/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$HOME/.local/bin/python3.12" ]
}

@test "pick_python: a python3.12 on PATH that is not actually 3.12 is skipped by the same-minor fallback" {
    fakebin="$TEST_DIR/fakebin-liar"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$fakebin/python3.12" 3.14                    # a shim named for one minor, running another
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.12.4" "executable = $TEST_DIR/gone/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
    [[ "$err" == *"romp-sdk-setup"* ]]
}

@test "pick_python: a cfg with a home but no version line yields no home candidate (a bare python is python2 on many machines)" {
    fakebin="$TEST_DIR/fakebin-py2"; mkdir -p "$fakebin" "$TEST_DIR/py2home"
    fake_python "$fakebin/python3.14" 3.14
    printf '#!/bin/sh\n' > "$TEST_DIR/py2home/python"; chmod +x "$TEST_DIR/py2home/python"   # runs, answers 0
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/py2home" "include-system-site-packages = false"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
    [ -s "$TEST_DIR/stderr" ]                                 # and it is not silent about the venv
}

@test "pick_python: a recorded interpreter that hangs counts as not runnable (bounded by timeout where coreutils has it)" {
    command -v timeout >/dev/null 2>&1 || skip "no coreutils timeout on this machine"
    fakebin="$TEST_DIR/fakebin-hang"; mkdir -p "$fakebin" "$TEST_DIR/tbin" "$TEST_DIR/hang"
    ln -s "$(command -v timeout)" "$TEST_DIR/tbin/timeout"    # the one real tool the picker may use
    fake_python "$fakebin/python3.14" 3.14
    # The stub sleeps longer than the picker's bound and then exits 0: unbounded, it would be taken as
    # the venv's interpreter, so the pick landing on python3.14 IS the proof the bound was applied.
    printf '#!/bin/sh\nexec /bin/sleep 12\n' > "$TEST_DIR/hang/python3.12"; chmod +x "$TEST_DIR/hang/python3.12"
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.12.4" "executable = $TEST_DIR/hang/python3.12"
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin:$TEST_DIR/tbin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
    [[ "$err" == *"$TEST_DIR/hang/python3.12"* ]]
}

# ─── pick_python: the build is part of the match ──────────────────────────────────────────────────
# venv names a free-threaded venv's lib directory python3.14t and the kernel keys its match on that tag,
# so a default-build 3.14 is not "another python 3.14" for such a venv: handed one, the kernel boots and
# refuses the venv as a mismatch, and every SDK session shows the mismatch card. The picker read the
# minor alone, from the cfg's version line; the build is in the lib directory's name.
write_venv_lib() { mkdir -p "$1/sdkvenv/lib/python$2/site-packages"; }   # $1 state root, $2 the lib tag

@test "pick_python: a free-threaded venv whose interpreter is gone is NOT handed the default build of the same minor" {
    # The t package removed, the default build still on PATH: the same-minor fallback took it and said the
    # venv still matched. Now it falls through to newest-first with the rebuild line, as for any lost venv.
    fakebin="$TEST_DIR/fakebin-ft1"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$fakebin/python3.13" 3.13
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/gone" "version = 3.14.0" \
        "executable = $TEST_DIR/gone/python3.14t"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14t
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]                        # newest-first, the only rule left
    [[ "$err" == *"python 3.14t"* ]]                          # names the build the venv was built for
    [[ "$err" == *"romp-sdk-setup"* ]]                        # and that the venv must be rebuilt for the pick
    [[ "$err" != *"still matches"* ]]
}

@test "pick_python: a free-threaded venv whose interpreter is gone takes python3.14t on PATH, and says so" {
    fakebin="$TEST_DIR/fakebin-ft2"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14
    fake_python "$fakebin/python3.14t" 3.14 t
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.14.0" "executable = $TEST_DIR/gone/python3.14t"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14t
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14t" ]
    [[ "$err" == *"using $fakebin/python3.14t"* ]]
    [[ "$err" == *"same minor and the same build"* ]]
    [[ "$err" != *"romp-sdk-setup"* ]]                        # no rebuild is needed
}

@test "pick_python: the build is read from the interpreter's abi flags, never from its file name" {
    # uv's free-threaded install has python3.14 as a link to python3.14t: the default name, the t build.
    fakebin="$TEST_DIR/fakebin-ft3"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14" 3.14 t
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.14.0" "executable = $TEST_DIR/gone/python3.14t"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14t
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
    [[ "$err" == *"using $fakebin/python3.14"* ]]
    [[ "$err" != *"romp-sdk-setup"* ]]
    # and the reverse: a default-build venv is not handed the t build that sits under the default name
    rm -rf "$XDG_STATE_HOME/romp/sdkvenv"
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.14.0" "executable = $TEST_DIR/gone/python3.14"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]                        # newest-first: the only python there is
    [[ "$err" == *"romp-sdk-setup"* ]]                        # with the rebuild line
    [[ "$err" != *"still matches"* ]]
}

@test "pick_python: a home holding both builds yields the venv's build, silently; holding only the other, nothing" {
    # A distro with python3.14 and python3.14t both under home, the recorded executable gone: the cfg
    # candidate home/python3.14 ran, reported (3, 14) and was taken for a 3.14t venv with no line at all.
    fakebin="$TEST_DIR/fakebin-ft4"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.13" 3.13
    fake_python "$TEST_DIR/usr/python3.14" 3.14
    fake_python "$TEST_DIR/usr/python3.14t" 3.14 t
    write_venv_cfg "$XDG_STATE_HOME/romp" "home = $TEST_DIR/usr" "version = 3.14.0" \
        "executable = $TEST_DIR/usr/3.14.0/bin/python3.14t"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14t
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$TEST_DIR/usr/python3.14t" ]
    [ ! -s "$TEST_DIR/stderr" ]
    rm -f "$TEST_DIR/usr/python3.14t"                         # the t package removed; home/python3.14 stays
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.13" ]                        # not home/python3.14: newest-first on PATH
    [[ "$err" == *"romp-sdk-setup"* ]]
}

@test "pick_python: a default-build venv keeps the same-minor fallback it had, and never tries python3.14t by name" {
    fakebin="$TEST_DIR/fakebin-ft5"; mkdir -p "$fakebin"
    fake_python "$fakebin/python3.14t" 3.14 t                 # the only 3.14 on PATH is the t build
    fake_python "$fakebin/python3.13" 3.13
    write_venv_cfg "$XDG_STATE_HOME/romp" "version = 3.14.0" "executable = $TEST_DIR/gone/python3.14"
    write_venv_lib "$XDG_STATE_HOME/romp" 3.14
    eval "$(extract_pick "$ROMP_SERVE")"
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    err="$(cat "$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.13" ]                        # newest-first never looks for python3.14t
    [[ "$err" == *"no other python 3.14 was found"* ]]
    fake_python "$fakebin/python3.14" 3.14                    # the default build back on PATH: taken
    out="$(ROMP_PYTHON= PATH="$fakebin" pick_python 2>"$TEST_DIR/stderr")"
    [ "$out" = "$fakebin/python3.14" ]
}
