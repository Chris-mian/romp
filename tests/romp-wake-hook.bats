#!/usr/bin/env bats

# romp-wake.sh is the event-driven judge trigger: on the Stop / UserPromptSubmit
# hook events it pokes the kernel's POST /tick so the producer runs a pass NOW
# instead of on the 20s backstop. It must (a) hit /tick on the configured port,
# and (b) NEVER fail the turn — even with no kernel/curl reachable.

setup() {
    TEST_DIR="$(mktemp -d)"
    MOCK="$TEST_DIR/mock"; mkdir -p "$MOCK"
    export CURL_LOG="$TEST_DIR/curl.log"
    # Mock curl: log args (the hook detaches it into a subshell, so the test polls
    # for the log below). Exported CURL_LOG so the detached mock can still find it.
    cat > "$MOCK/curl" <<'MOCK'
#!/usr/bin/env bash
echo "curl $*" >> "$CURL_LOG"
MOCK
    chmod +x "$MOCK/curl"
    export PATH="$MOCK:$PATH"
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../hooks" && pwd)/romp-wake.sh"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "romp-wake pokes POST /tick on the configured kernel port" {
    ROMP_SERVE_PORT=7777 run bash -c 'echo "{}" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
    # curl is detached (( curl & )), so poll briefly for the log to land
    for _ in $(seq 1 40); do [ -s "$CURL_LOG" ] && break; sleep 0.05; done
    grep -q -- '-X POST' "$CURL_LOG"
    grep -q 'http://127.0.0.1:7777/tick' "$CURL_LOG"
}

@test "romp-wake defaults to port 7433 when ROMP_SERVE_PORT is unset" {
    run bash -c 'echo "{}" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
    for _ in $(seq 1 40); do [ -s "$CURL_LOG" ] && break; sleep 0.05; done
    grep -q 'http://127.0.0.1:7433/tick' "$CURL_LOG"
}

@test "romp-wake never fails the turn when the kernel is unreachable" {
    rm "$MOCK/curl"                       # use the real curl against a dead port
    ROMP_SERVE_PORT=1 run bash -c 'printf "" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
}
