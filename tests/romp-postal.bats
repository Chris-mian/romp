#!/usr/bin/env bats

# Exercises the romp-postal program end to end: a real bus (own port per test),
# CLI client ops, the loop guard, the stdio MCP server, and autostop. tmux is
# mocked so no real sessions are needed.

POSTAL="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-postal"

setup() {
    TEST_DIR="$(mktemp -d)"
    export XDG_STATE_HOME="$TEST_DIR/state"
    export ROMP_POSTAL_PORT=$((47200 + ${BATS_TEST_NUMBER:-0}))
    export ROMP_POSTAL_POLL=1
    export ROMP_POSTAL_IDLE_GRACE=2
    export ROMP_POSTAL_HEARTBEAT_TTL=2
    export HOME="$TEST_DIR/home"; mkdir -p "$HOME"   # sandbox the client-only marker
    unset SSH_CONNECTION SSH_TTY                      # default: not a remote machine

    # mock tmux over a "name|uuid" fixture (all @romp=1)
    MOCK="$TEST_DIR/mock"; mkdir -p "$MOCK"
    export SESS="$TEST_DIR/sessions.txt"
    printf 'alpha|uuid-a\nbeta|uuid-b\n' > "$SESS"
    export MOCK_CURRENT=alpha
    cat > "$MOCK/tmux" <<MOCK
#!/usr/bin/env bash
case "\$1" in
  display-message) echo "\${MOCK_CURRENT}" ;;
  show) [ "\$5" = "@romp-session-id" ] && grep "^\$3|" "$SESS" | head -1 | cut -d'|' -f2 ;;
  list-sessions) while IFS='|' read -r n u; do [ -n "\$n" ] && echo "1|\$n|\$u"; done < "$SESS" ;;
esac
exit 0
MOCK
    chmod +x "$MOCK/tmux"
    export PATH="$MOCK:$PATH"

    "$POSTAL" serve >/dev/null 2>&1 &
    BUS_PID=$!
    for _ in $(seq 1 50); do curl -s "127.0.0.1:$ROMP_POSTAL_PORT/ping" >/dev/null 2>&1 && break; sleep 0.1; done
}

teardown() {
    kill "$BUS_PID" 2>/dev/null
    rm -rf "$TEST_DIR"
}

mb() { echo "$XDG_STATE_HOME/romp/postal/mail/$1"; }
cnt() { ls -1 "$1" 2>/dev/null | wc -l | tr -d ' '; }
# toggle POSTAL ISOLATION on for a session uuid (writes the kernel's session-flags.json that the bus reads)
iso() { mkdir -p "$XDG_STATE_HOME/romp"; printf '{"%s":{"postalOff":true}}' "$1" > "$XDG_STATE_HOME/romp/session-flags.json"; }

@test "agents lists live sessions and marks you" {
    run "$POSTAL" agents
    [ "$status" -eq 0 ]
    [[ "$output" == *"alpha (you)"* ]]
    [[ "$output" == *"beta"* ]]
}

@test "send delivers into the recipient's maildir" {
    run "$POSTAL" send beta "hello there"
    [ "$status" -eq 0 ]
    [[ "$output" == *"delivered to 'beta'"* ]]
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]
    grep -q "hello there" "$(mb uuid-b)/new/"*
    grep -q "From: alpha" "$(mb uuid-b)/new/"*
}

@test "send to an unknown session errors" {
    run "$POSTAL" send ghost "x"
    [ "$status" -ne 0 ]
    [[ "$output" == *"no live romp session named 'ghost'"* ]]
}

@test "an isolated session (mailbox off) is invisible in agents" {
    iso uuid-b                                   # beta toggles postal isolation on
    run "$POSTAL" agents
    [ "$status" -eq 0 ]
    [[ "$output" == *"alpha"* ]]
    [[ "$output" != *"beta"* ]]                  # isolated → hidden from peers
}

@test "sending TO an isolated session is refused, not parked" {
    iso uuid-b
    run "$POSTAL" send beta "secret"
    [ "$status" -ne 0 ]
    [[ "$output" == *"isolation"* ]]
    [[ "$output" == *"RECIPIENT"* ]]             # the error names whose mailbox is off: the RECIPIENT's
    [[ "$output" == *"YOUR mailbox is fine"* ]]  # ...and reassures the sender it's not them
    [ "$(cnt "$(mb uuid-b)/new")" = "0" ]        # nothing delivered or parked
}

@test "an isolated session cannot send" {
    iso uuid-a                                   # alpha (the current session) is isolated
    run "$POSTAL" send beta "hi"
    [ "$status" -ne 0 ]
    [[ "$output" == *"isolation"* ]]
    [[ "$output" == *"YOUR OWN mailbox is OFF"* ]]   # makes clear it's the SENDER's own mailbox,
    [[ "$output" == *"relay"* ]]                     # ...so a relaying agent tells the user the right thing
    [ "$(cnt "$(mb uuid-b)/new")" = "0" ]
}

@test "an isolated session holds its inbox until it reconnects" {
    run "$POSTAL" send beta "for beta"           # delivered while beta is on the postal service
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]
    iso uuid-b                                    # beta now isolates
    export MOCK_CURRENT=beta
    run "$POSTAL" inbox
    [ "$status" -eq 0 ]
    [[ "$output" != *"for beta"* ]]              # held — not delivered while isolated
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]        # still waiting in new/
}

@test "send to a dead-but-known session parks a handoff" {
    # gamma has a persistent names/ record but is NOT a live session
    mkdir -p "$XDG_STATE_HOME/romp/names"
    printf 'gamma\t/tmp\t#aa3344\twhite\n' > "$XDG_STATE_HOME/romp/names/uuid-g"
    run "$POSTAL" send gamma "DELEGATE: I'm taking over; you're relieved."
    [ "$status" -eq 0 ]
    [[ "$output" == *"parked as a handoff"* ]]
    [ "$(cnt "$(mb uuid-g)/new")" = "1" ]
    grep -q "X-Park: 1" "$(mb uuid-g)/new/"*
    grep -q "taking over" "$(mb uuid-g)/new/"*
}

@test "tool descriptions use only the DELEGATE/COORDINATE/QUESTION vocabulary (no stale ASK:/FYI:/HANDOFF:)" {
    # f537fd1 unified the lead-word vocabulary, but missed the revive_session examples; this guards
    # against any old caps-colon lead word creeping back into the MCP tool descriptions / norms.
    run grep -nE "\b(ASK|FYI|HANDOFF):" "$POSTAL"
    [ "$status" -ne 0 ]   # grep finds nothing → non-zero → pass
}

@test "parked handoff survives the orphan sweep; a normal orphan does not" {
    mkdir -p "$XDG_STATE_HOME/romp/names"
    printf 'gamma\t/tmp\t#aa3344\twhite\n' > "$XDG_STATE_HOME/romp/names/uuid-g"
    "$POSTAL" send gamma "parked: take over"                 # -> X-Park handoff
    local box; box="$(mb uuid-g)/new"; mkdir -p "$box"
    printf 'From: alpha\nFrom-Id: uuid-a\nDate: t\n\nnormal stale\n' > "$box/normal.msg"
    [ "$(cnt "$box")" = "2" ]
    ROMP_POSTAL_ORPHAN_GRACE=0 run "$POSTAL" sweep
    [ "$status" -eq 0 ]
    [ ! -e "$box/normal.msg" ]                               # non-parked orphan bounced + removed
    [ "$(cnt "$box")" = "1" ]                                # parked handoff still waiting
    grep -q "X-Park: 1" "$box"/*                             # ...and it's the parked one
}

@test "recall unsends an unread message you sent; sent shows it recalled" {
    "$POSTAL" send beta "stale ask please ignore"           # as alpha (uuid-a)
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]
    run "$POSTAL" recall beta
    [ "$status" -eq 0 ]
    [[ "$output" == *"recalled 1 message"* ]]
    [ "$(cnt "$(mb uuid-b)/new")" = "0" ]                    # gone from the recipient's box
    run "$POSTAL" sent
    [[ "$output" == *"recalled"* ]]                          # receipt reflects it
}

@test "recall removes only your OWN queued messages" {
    "$POSTAL" send beta "from alpha — recall me"            # From-Id: uuid-a
    printf 'From: zeta\nFrom-Id: uuid-zeta\nDate: t\n\nfrom someone else\n' > "$(mb uuid-b)/new/other.msg"
    [ "$(cnt "$(mb uuid-b)/new")" = "2" ]
    run "$POSTAL" recall beta                                # as alpha
    [ "$status" -eq 0 ]
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]                    # only alpha's removed
    grep -q "from someone else" "$(mb uuid-b)/new/"*        # the other sender's survives
}

@test "pending-mail marker tracks unread mail (present when queued, gone when drained)" {
    pend="$XDG_STATE_HOME/romp/postal/mail-pending/uuid-b"
    [ ! -e "$pend" ]
    "$POSTAL" send beta "ping"
    [ -e "$pend" ]                                  # delivery raises the marker
    MOCK_CURRENT=beta "$POSTAL" inbox >/dev/null    # consuming read empties new/
    [ ! -e "$pend" ]                                # ...and clears the marker
}

@test "pending-mail marker is set for a DEAD parked recipient and survives" {
    mkdir -p "$XDG_STATE_HOME/romp/names"
    printf 'gamma\t/tmp\t#aa3344\twhite\n' > "$XDG_STATE_HOME/romp/names/uuid-g"
    "$POSTAL" send gamma "parked handoff"           # gamma is dead -> parks
    [ -e "$XDG_STATE_HOME/romp/postal/mail-pending/uuid-g" ]   # visible even though dead
}

@test "retry reconciles a stale pending marker (new/ already empty)" {
    mkdir -p "$XDG_STATE_HOME/romp/postal/mail-pending"
    touch "$XDG_STATE_HOME/romp/postal/mail-pending/uuid-ghost"   # marker but no new/ mail
    run "$POSTAL" retry
    [ "$status" -eq 0 ]
    [ ! -e "$XDG_STATE_HOME/romp/postal/mail-pending/uuid-ghost" ]   # reconciled away
}

@test "find searches past sessions by their archived summary + captions" {
    mkdir -p "$XDG_STATE_HOME/romp/names" "$XDG_STATE_HOME/romp/archive" "$XDG_STATE_HOME/romp/captions"
    printf 'oldzot\t/tmp/proj\t#179EE8\twhite\n' > "$XDG_STATE_HOME/romp/names/uuid-z"
    printf '{"headline":"Zotero sync work","abstract":"Worked on the zotero metadata sync."}\n' \
        > "$XDG_STATE_HOME/romp/archive/uuid-z.json"
    printf '{"id":"uuid-z:1","grain":"turn","t":1780000000,"caption":"Fixed the zotero metadata sync"}\n' \
        > "$XDG_STATE_HOME/romp/captions/uuid-z.jsonl"
    run "$POSTAL" find zotero
    [ "$status" -eq 0 ]
    [[ "$output" == *"oldzot"* ]]
    [[ "$output" == *"zotero metadata"* ]]
    [[ "$output" == *"dead"* ]]                              # uuid-z is not among the live mock sessions
}

@test "revive resumes a dead session via the romp launcher" {
    mkdir -p "$XDG_STATE_HOME/romp/names"
    printf 'oldzot\t%s\t#179EE8\twhite\n' "$TEST_DIR" > "$XDG_STATE_HOME/romp/names/uuid-z"
    local log="$TEST_DIR/romp-call.log"
    cat > "$MOCK/romp" <<EOF
#!/usr/bin/env bash
echo "ARGS=[\$*] CWD=\$PWD" > "$log"
echo "[romp] started (detached)."
EOF
    chmod +x "$MOCK/romp"
    ROMP_BIN="$MOCK/romp" run "$POSTAL" revive oldzot
    [ "$status" -eq 0 ]
    [[ "$output" == *"reviving 'oldzot'"* ]]
    grep -q "ARGS=\[oldzot --resume uuid-z --detach\]" "$log"
}

@test "revive of an unknown session name errors" {
    ROMP_BIN=/bin/false run "$POSTAL" revive nope-never-existed
    [ "$status" -ne 0 ]
    [[ "$output" == *"no live or past romp session"* ]]
}

@test "inbox consumes; peek does not" {
    "$POSTAL" send beta "keep then read"
    MOCK_CURRENT=beta run "$POSTAL" peek
    [[ "$output" == *"keep then read"* ]]
    [ "$(cnt "$(mb uuid-b)/new")" = "1" ]
    MOCK_CURRENT=beta run "$POSTAL" inbox
    [[ "$output" == *"keep then read"* ]]
    [ "$(cnt "$(mb uuid-b)/new")" = "0" ]
}

@test "loop guard: 8 rapid drains cap at 6, rest pause and are retained" {
    local box; box="$(mb uuid-loop)/new"; mkdir -p "$box"
    local deliv=0 paused=0 n
    for n in $(seq 1 8); do
        printf 'From: g\nDate: t\n\nrapid #%s\n' "$n" > "$box/$(date +%s).$$_${n}.h"
        if [ -n "$("$POSTAL" drain --id uuid-loop)" ]; then deliv=$((deliv+1)); else paused=$((paused+1)); fi
    done
    [ "$deliv" = "6" ]
    [ "$paused" = "2" ]
    [ "$(cnt "$box")" = "2" ]
}

@test "MCP: initialize, tools/list, and tool calls work" {
    req='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_agents","arguments":{}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"send_message","arguments":{"to":"beta","body":"via tool"}}}'
    out="$(printf '%s\n' "$req" | MOCK_CURRENT=alpha "$POSTAL" mcp 2>/dev/null)"
    [[ "$out" == *'"protocolVersion": "2025-06-18"'* ]]
    [[ "$out" == *"send_message"* ]]
    [[ "$out" == *"check_inbox"* ]]
    [[ "$out" == *"list_agents"* ]]
    [[ "$out" == *"inputSchema"* ]]
    [[ "$out" == *"alpha (you)"* ]]
    [[ "$out" == *"Delivered to 'beta'"* ]]
    [ "$(cnt "$(mb uuid-b)/new")" -ge 1 ]
}

@test "bus self-stops when no romp clients remain" {
    : > "$SESS"   # drop all sessions; heartbeats age out (TTL=2)
    local stopped=0 _
    for _ in $(seq 1 30); do
        curl -s "127.0.0.1:$ROMP_POSTAL_PORT/ping" >/dev/null 2>&1 || { stopped=1; break; }
        sleep 0.5
    done
    [ "$stopped" = "1" ]
}

@test "remote: on the host (no SSH) refuses and creates no marker" {
    run "$POSTAL" remote
    [ "$status" -eq 0 ]
    [[ "$output" == *"looks like your Romp Postal Service host"* ]]
    [[ "$output" == *"RemoteForward"* ]]
    [ ! -e "$HOME/.config/romp-postal/client-only" ]
}

@test "remote --force with the bus reachable configures the client and connects" {
    rm -f "$XDG_STATE_HOME/romp/postal/server.pid"   # model a tunnel: reachable port, no local bus
    export SSH_CONNECTION="1 2 3 4"
    run "$POSTAL" remote --force
    [ "$status" -eq 0 ]
    [ -e "$HOME/.config/romp-postal/client-only" ]
    [[ "$output" == *"Already connected"* ]]
    [[ "$output" == *"alpha"* ]]
}

@test "remote: nudge fires for an unconfigured remote, gone once configured" {
    export SSH_CONNECTION="1 2 3 4"
    run "$POSTAL" agents
    [[ "$output" == *"romp --mail remote"* ]]
    mkdir -p "$HOME/.config/romp-postal"; touch "$HOME/.config/romp-postal/client-only"
    run "$POSTAL" agents
    [[ "$output" != *"romp --mail remote"* ]]
}
