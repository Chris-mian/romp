#!/usr/bin/env bats

# romp-serve maps the manager's spawn contract (--port / ROMP_SERVE_PORT) onto the
# Python kernel's env and execs it; `romp --serve` persists the tailnet opt-in.

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

@test "romp-serve: honors the persisted serve-host opt-in (tailnet)" {
    printf '0.0.0.0\n' > "$XDG_STATE_HOME/romp/serve-host"
    run "$ROMP_SERVE" --port 9999
    [[ "$output" == *"HOST=0.0.0.0"* ]]
}

@test "romp-serve: --host overrides the persisted opt-in" {
    printf '0.0.0.0\n' > "$XDG_STATE_HOME/romp/serve-host"
    run "$ROMP_SERVE" --port 9999 --host 127.0.0.1
    [[ "$output" == *"HOST=127.0.0.1"* ]]
}

@test "romp-serve: ROMP_SERVE_PORT fallback + forwards ROMP_MANAGER_PID" {
    ROMP_MANAGER_PID=4242 ROMP_SERVE_PORT=7433 run "$ROMP_SERVE"
    [[ "$output" == *"PORT=7433"* ]]
    [[ "$output" == *"MGRPID=4242"* ]]
}

@test "romp --serve: on writes the opt-in, status reports it, off clears it" {
    run "$ROMP_SCRIPT" --serve status
    [ "$status" -eq 0 ]
    [[ "$output" == *"127.0.0.1"* ]]

    run "$ROMP_SCRIPT" --serve on
    [ "$status" -eq 0 ]
    [ "$(cat "$XDG_STATE_HOME/romp/serve-host")" = "0.0.0.0" ]

    run "$ROMP_SCRIPT" --serve status
    [[ "$output" == *"tailnet"* ]]

    run "$ROMP_SCRIPT" --serve off
    [ "$status" -eq 0 ]
    [ ! -f "$XDG_STATE_HOME/romp/serve-host" ]
}
