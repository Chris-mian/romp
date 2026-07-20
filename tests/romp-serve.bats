#!/usr/bin/env bats

# romp-serve maps the manager's spawn contract (--port / ROMP_SERVE_PORT) onto the
# Python kernel's env and execs it. The kernel binds loopback only; tailnet reach
# is `tailscale serve` proxying to loopback, so there is no persisted host opt-in
# (`romp --serve` removed 2026-07-19).

BIN="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)"
ROMP_SERVE="$BIN/romp-serve"
ROMP_SCRIPT="$BIN/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    mkdir -p "$XDG_STATE_HOME/romp"
    # Stub kernel: print the env romp-serve hands it, then exit (no real server).
    export ROMP_KERNEL_BIN="$TEST_DIR/stub-kernel"
    cat > "$ROMP_KERNEL_BIN" << 'STUB'
#!/usr/bin/env bash
echo "PORT=${ROMP_KERNEL_PORT:-}"
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
    ROMP_MANAGER_PID=4242 ROMP_SERVE_PORT=7433 run "$ROMP_SERVE"
    [[ "$output" == *"PORT=7433"* ]]
    [[ "$output" == *"MGRPID=4242"* ]]
}

@test "romp --serve: removed — rejected as unknown, writes no state" {
    run "$ROMP_SCRIPT" --serve on
    [ "$status" -ne 0 ]
    [[ "$output" == *"Unknown option"* ]]
    [ ! -f "$XDG_STATE_HOME/romp/serve-host" ]
}

# ─── pick_python: the kernel runs on the best python available (Agent SDK needs >= 3.10) ────────
# Unit tests over the extracted function (it uses only `command -v` + $HOME probing, so a bare
# fake PATH is enough). The e2e wiring (exec "$PY" "$KERNEL") is covered by every test above via
# the ROMP_PYTHON shim in setup().

extract_pick() { sed -n '/^pick_python()/,/^}/p' "$1"; }

@test "pick_python: ROMP_PYTHON override wins verbatim" {
    eval "$(extract_pick "$ROMP_SERVE")"
    ROMP_PYTHON=/opt/custom/python run pick_python
    [ "$output" = "/opt/custom/python" ]
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

@test "pick_python: romp-serve and romp-sdk-setup carry the SAME picker (venv must match the kernel)" {
    diff <(sed -n '/^pick_python()/,/^}/p' "$ROMP_SERVE") \
         <(sed -n '/^pick_python()/,/^}/p' "$BIN/romp-sdk-setup")
}
