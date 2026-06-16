#!/usr/bin/env bats

# Resolve path to the romp script under test
ROMP_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
    WORK_DIR="$TEST_DIR/myproject"
    MOCK_DIR="$TEST_DIR/mock"
    export MOCK_LOG="$TEST_DIR/mock.log"

    mkdir -p "$WORK_DIR" "$MOCK_DIR"

    # Fixtures the tmux mock reads:
    #   sessions file: one per line, "name" or "name|rompflag" (flag defaults to 1)
    #   identity file: "name=colour" lines (for @identity-bg lookups)
    export MOCK_TMUX_SESSIONS_FILE="$TEST_DIR/mock_sessions.txt"
    export MOCK_TMUX_IDENTITY_FILE="$TEST_DIR/mock_identity.txt"
    touch "$MOCK_TMUX_SESSIONS_FILE" "$MOCK_TMUX_IDENTITY_FILE"

    cat > "$MOCK_DIR/tmux" << 'MOCK'
#!/usr/bin/env bash
echo "tmux $*" >> "$MOCK_LOG"
case "$1" in
  has-session)
    # $3 is "=<name>"; a session exists iff its name is in the file
    target="${3#=}"
    cut -d'|' -f1 "$MOCK_TMUX_SESSIONS_FILE" 2>/dev/null | grep -qx "$target" && exit 0
    exit 1
    ;;
  display-message)
    echo "${MOCK_TMUX_CURRENT:-mysession}"
    exit 0
    ;;
  list-sessions)
    # Reformat each session line per the requested -F format ($3).
    # @romp defaults to 1; a "name|0" line is a non-romp session.
    fmt="$3"
    while IFS='|' read -r s c; do
      [[ -z "$s" ]] && continue
      c="${c:-1}"
      out="$fmt"
      out="${out//'#{@romp}'/$c}"
      out="${out//'#{session_name}'/$s}"
      out="${out//'#S'/$s}"
      echo "$out"
    done < "$MOCK_TMUX_SESSIONS_FILE" 2>/dev/null
    exit 0
    ;;
  show)
    if [[ "$2" == "-t" && "$4" == "-v" && "$5" == "@identity-bg" ]]; then
      result=$(grep "^${3}=" "$MOCK_TMUX_IDENTITY_FILE" 2>/dev/null | head -1 | cut -d= -f2)
      [[ -n "$result" ]] && { echo "$result"; exit 0; }
      exit 1
    fi
    # global status-format[0] — the default main-row composition the
    # provisioning pins onto each session (sentinel for assertions)
    if [[ "$2" == "-gv" && "$3" == "status-format[0]" ]]; then
      echo "GLOBAL_ROW0"; exit 0
    fi
    exit 0
    ;;
esac
exit 0
MOCK
    chmod +x "$MOCK_DIR/tmux"

    export PATH="$MOCK_DIR:$PATH"
    unset TMUX            # default: outside tmux → attach-session branch
    # Hermetic HOME: bin/romp probes $HOME/.claude/romp-postal.mcp.json (would
    # nondeterministically append --mcp-config on a dev machine) and writes the
    # names map under XDG_STATE_HOME (was polluting the REAL state dir).
    export HOME="$TEST_DIR/home"
    export XDG_STATE_HOME="$HOME/.local/state"
    mkdir -p "$HOME"
    cd "$WORK_DIR"
}

teardown() {
    # Tests that launch a background romp-manager record its pid in MGR_PID so we
    # always reap it (and its child kernels), even if an assertion aborted the test.
    [[ -n "${MGR_PID:-}" ]] && kill "$MGR_PID" 2>/dev/null
    rm -rf "$TEST_DIR"
}

# Helper — runs romp with merged stdout+stderr so BATS captures errors
run_romp() {
    "$ROMP_SCRIPT" "$@" 2>&1
}

# ─── Launch tests ────────────────────────────────────────────────────

@test "no args: session named after the folder, claude exec'd with --name + --session-id" {
    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'tmux set -t myproject @romp 1' "$MOCK_LOG"
    # The pill carries the session name, and a self-assigned --session-id lets
    # romp record name<->id up front (names map → resume picker).
    grep -qE 'tmux send-keys -t myproject exec claude --name "myproject" --session-id [0-9a-f-]{36} Enter' "$MOCK_LOG"
    grep -q 'tmux attach-session -t myproject' "$MOCK_LOG"
}

@test "provisioning pins status-format[0] alongside the session-scoped peers row" {
    # tmux gotcha (2026-06-12): a session-scoped status-format[1] shadows the
    # whole inherited array — without [0] pinned to the global composition the
    # main status row (status-left + windows + status-right) renders EMPTY.
    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t myproject status-format\[0\] GLOBAL_ROW0' "$MOCK_LOG"
    grep -q 'tmux set -t myproject status-format\[1\]' "$MOCK_LOG"
}

@test "named session: romp my-task → my-task" {
    run run_romp my-task
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s my-task' "$MOCK_LOG"
    grep -q 'tmux attach-session -t my-task' "$MOCK_LOG"
}

@test "session name sanitization: dots and colons replaced with dashes" {
    run run_romp "my.task:v2"
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s my-task-v2' "$MOCK_LOG"
    grep -q 'exec claude --name "my-task-v2"' "$MOCK_LOG"
}

@test "session name sanitization: shell metacharacters folded to dashes (no command injection)" {
    # A name/dir carrying $(), ;, or quotes must NOT survive into the launch
    # command that gets typed into the pane's shell — every unsafe char becomes
    # '-'. Regression for the command-injection-via-session-name hole.
    run run_romp 'pwn$(touch INJECTED);x"y'
    [ "$status" -eq 0 ]
    local line
    line="$(grep -F 'send-keys' "$MOCK_LOG" | grep -F 'exec claude')"
    [ -n "$line" ]
    # no shell metacharacters survive in the exec line
    ! grep -qE '[$();]' <<<"$line"
    # exactly the two quotes that wrap --name "<name>", no injected extras
    [ "$(grep -o '"' <<<"$line" | wc -l | tr -d ' ')" -eq 2 ]
}

@test "interrupt/escape key bindings route the session name through tmux #{q:} quoting" {
    run run_romp myproject
    [ "$status" -eq 0 ]
    grep -F 'bind -n C-c' "$MOCK_LOG"    | grep -qF 'romp-interrupt-reset #{q:session_name}'
    grep -F 'bind -n Escape' "$MOCK_LOG" | grep -qF 'romp-interrupt-reset #{q:session_name}'
    # the unquoted (injectable) form must be gone
    ! grep -qF 'romp-interrupt-reset #{session_name}' "$MOCK_LOG"
}

@test "resume: a session id with shell metacharacters is refused before any launch" {
    # resume_id is typed into `claude --resume <id>`; a non-alphanumeric id must
    # be rejected before a session is created.
    run run_romp myproject --resume 'abc;touch INJECTED' --detach
    [ "$status" -ne 0 ]
    [[ "$output" == *"invalid session id"* ]]
    [ "$(grep -c 'tmux new-session' "$MOCK_LOG")" -eq 0 ]
}

@test "state dir is created private (0700)" {
    run run_romp myproject
    [ "$status" -eq 0 ]
    local perms
    perms="$(stat -f '%Lp' "$XDG_STATE_HOME/romp" 2>/dev/null || stat -c '%a' "$XDG_STATE_HOME/romp")"
    [ "$perms" = "700" ]
}

# ─── Resume tests ────────────────────────────────────────────────────

@test "resume: bare -r with no resumable sessions is a no-op" {
    # bare -r opens the by-name picker; with an empty names map there is
    # nothing to offer — no session may be created as a side effect. The names
    # dir exists-but-empty (steady state on any machine that ran romp before);
    # a MISSING dir is the silent first-run path, exercised below.
    # NOTE bats/macOS gotcha: a false [[ ]] mid-test is SWALLOWED (only the
    # last command's status fails a test) — assert with simple commands
    # (grep, [ ]) so failures actually fire.
    mkdir -p "$XDG_STATE_HOME/romp/names"
    run run_romp -r
    [ "$status" -eq 0 ]
    grep -q "no resumable sessions" <<<"$output"
    [ "$(grep -c 'tmux new-session' "$MOCK_LOG")" -eq 0 ]
}

@test "resume: -r and --resume are equivalent" {
    mkdir -p "$XDG_STATE_HOME/romp/names"
    run run_romp -r
    [ "$status" -eq 0 ]
    grep -q "no resumable sessions" <<<"$output"

    run run_romp --resume
    [ "$status" -eq 0 ]
    grep -q "no resumable sessions" <<<"$output"
}

@test "resume: first run ever (no names dir) exits silently, creating nothing" {
    touch "$MOCK_LOG"    # this path may make no tmux calls at all
    run run_romp -r
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [ "$(grep -c 'tmux new-session' "$MOCK_LOG")" -eq 0 ]
}

@test "resume: 'resume' is now a normal session name, not a directive" {
    # -r/--resume replaced the bare `resume` word, so it's free to name a session.
    run run_romp resume
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s resume' "$MOCK_LOG"
    ! grep -q -- '--resume' "$MOCK_LOG"
}

@test "resume: named session plus -r still goes through the picker" {
    mkdir -p "$XDG_STATE_HOME/romp/names"
    run run_romp my-task -r
    [ "$status" -eq 0 ]
    grep -q "no resumable sessions" <<<"$output"
    [ "$(grep -c 'tmux new-session' "$MOCK_LOG")" -eq 0 ]
}

@test "resume: explicit session id (--resume <id>) resumes that conversation" {
    run run_romp --resume abc123-uuid
    [ "$status" -eq 0 ]
    grep -q 'tmux send-keys -t myproject exec claude --resume abc123-uuid --name "myproject" Enter' "$MOCK_LOG"
}

@test "resume: name collision uniquifies instead of hijacking the session" {
    echo "myproject" > "$MOCK_TMUX_SESSIONS_FILE"

    run run_romp --resume abc123-uuid
    [ "$status" -eq 0 ]
    ! grep -qE 'tmux attach-session -t myproject$' "$MOCK_LOG"
    grep -q 'tmux new-session -d -s myproject-2' "$MOCK_LOG"
    grep -q 'tmux send-keys -t myproject-2 exec claude --resume abc123-uuid --name "myproject-2" Enter' "$MOCK_LOG"
}

# ─── Detach tests ────────────────────────────────────────────────────

@test "detach: --detach creates the session but does not attach" {
    run run_romp --detach
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -qE 'tmux send-keys -t myproject exec claude --name "myproject" --session-id [0-9a-f-]{36} Enter' "$MOCK_LOG"
    ! grep -q 'tmux attach-session' "$MOCK_LOG"
    [[ "$output" == *"attach with: tmux attach -t myproject"* ]]
}

@test "detach: --resume + id + detach is the skill conversion path" {
    run run_romp --resume sess-xyz --detach
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'tmux send-keys -t myproject exec claude --resume sess-xyz --name "myproject" Enter' "$MOCK_LOG"
    ! grep -q 'tmux attach-session' "$MOCK_LOG"
    [[ "$output" == *"(detached)"* ]]
}

# ─── Misc ────────────────────────────────────────────────────────────

@test "unknown option shows error" {
    run run_romp -x
    [ "$status" -eq 1 ]
    [[ "$output" == *"Unknown option: -x"* ]]
}

@test "existing session reattaches instead of creating new" {
    echo "myproject" > "$MOCK_TMUX_SESSIONS_FILE"

    run run_romp
    [ "$status" -eq 0 ]
    ! grep -q 'tmux new-session' "$MOCK_LOG"
    grep -q 'tmux attach-session -t myproject' "$MOCK_LOG"
}

# ─── Identity-color tests ────────────────────────────────────────────

@test "color: first session gets the first palette color + a status dot" {
    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t myproject @identity-bg #1EA1EB' "$MOCK_LOG"
    # The tab dot is seeded blue (ready) at launch; the status hook drives
    # it thereafter.
    grep -q 'tmux set -t myproject @romp-emoji 🔵' "$MOCK_LOG"
}

@test "color: second session gets a different color from the first" {
    echo "other" > "$MOCK_TMUX_SESSIONS_FILE"
    echo "other=#1EA1EB" > "$MOCK_TMUX_IDENTITY_FILE"

    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t myproject @identity-bg #54B204' "$MOCK_LOG"
}

@test "color: third session gets teal (colorblind-tuned order: blue, green, teal)" {
    # The 3rd slot is teal #4EA8A9, the more colorblind-friendly of teal/purple against
    # the blue+green pair (the user 2026-06-12) — pin both earlier colors as taken.
    printf '%s\n' "s1" "s2" > "$MOCK_TMUX_SESSIONS_FILE"
    printf '%s\n' "s1=#1EA1EB" "s2=#54B204" > "$MOCK_TMUX_IDENTITY_FILE"

    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t myproject @identity-bg #4EA8A9' "$MOCK_LOG"
}

@test "color: all colors taken falls back to a hash pick" {
    local palette=("#1EA1EB" "#54B204" "#4EA8A9" "#DD42FF" "#E87221" "#98998A" "#F85B5A" "#F9D849" "#9088F0")
    > "$MOCK_TMUX_SESSIONS_FILE"
    > "$MOCK_TMUX_IDENTITY_FILE"
    for i in "${!palette[@]}"; do
        echo "sess${i}" >> "$MOCK_TMUX_SESSIONS_FILE"
        echo "sess${i}=${palette[$i]}" >> "$MOCK_TMUX_IDENTITY_FILE"
    done

    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux set -t myproject @identity-bg #' "$MOCK_LOG"
}

# ─── No attach/rename subcommands (use tmux a / tmux rename) ─────────

@test "'a' and 'attach' are now normal session names, not subcommands" {
    # `romp a`/`attach` were removed — use plain `tmux a`. So these words just
    # name a session now.
    run run_romp a
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s a' "$MOCK_LOG"

    : > "$MOCK_LOG"
    run run_romp attach
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s attach' "$MOCK_LOG"
}

@test "'rename' is now a normal session name, not a subcommand" {
    run run_romp rename
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s rename' "$MOCK_LOG"
}

# ─── Dashboard (-d) ──────────────────────────────────────────────────

@test "-d dispatches to romp-dashboard" {
    cat > "$MOCK_DIR/romp-dashboard" << 'MOCK'
#!/usr/bin/env bash
echo "romp-dashboard called" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-dashboard"
    # bin/romp prepends its own dir to PATH, so the real (never-exiting)
    # dashboard shadows the mock — use the test seam instead
    export ROMP_DASHBOARD_BIN="$MOCK_DIR/romp-dashboard"

    run run_romp -d
    [ "$status" -eq 0 ]
    grep -q 'romp-dashboard called' "$MOCK_LOG"
}

@test "dashboard is a normal session name, not a subcommand" {
    # `-d` is the dashboard, so the word "dashboard" is free to name a session.
    run run_romp dashboard
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s dashboard' "$MOCK_LOG"
}

# ─── `romp on` — the kernel manager ──────────────────────────────────

@test "manager verbs (on/refresh/status) dispatch to romp-manager with the right sub-command" {
    cat > "$MOCK_DIR/romp-manager" << 'MOCK'
#!/usr/bin/env bash
echo "romp-manager called: $*" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-manager"
    export ROMP_MANAGER_BIN="$MOCK_DIR/romp-manager"

    run run_romp on            # `romp on` is PURELY start-the-manager
    [ "$status" -eq 0 ]
    grep -q 'romp-manager called: up' "$MOCK_LOG"

    : > "$MOCK_LOG"
    run run_romp refresh       # restart ALL kernels
    [ "$status" -eq 0 ]
    grep -q 'romp-manager called: restart-all' "$MOCK_LOG"

    : > "$MOCK_LOG"
    run run_romp status
    [ "$status" -eq 0 ]
    grep -q 'romp-manager called: status' "$MOCK_LOG"
}

@test "romp on no longer forwards a restart sub-verb (romp refresh replaces it)" {
    cat > "$MOCK_DIR/romp-manager" << 'MOCK'
#!/usr/bin/env bash
echo "romp-manager called: $*" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-manager"
    export ROMP_MANAGER_BIN="$MOCK_DIR/romp-manager"
    run run_romp on restart main
    [ "$status" -eq 0 ]
    grep -q 'romp-manager called: up' "$MOCK_LOG"   # starts the manager; trailing words are NOT forwarded
    ! grep -q 'restart' "$MOCK_LOG"
}

@test "refresh/status are reserved manager verbs, NOT session names" {
    cat > "$MOCK_DIR/romp-manager" << 'MOCK'
#!/usr/bin/env bash
echo "romp-manager called: $*" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-manager"
    export ROMP_MANAGER_BIN="$MOCK_DIR/romp-manager"
    for verb in refresh status; do
        : > "$MOCK_LOG"
        run run_romp "$verb"
        [ "$status" -eq 0 ]
        grep -q 'romp-manager called' "$MOCK_LOG"
        ! grep -q "tmux new-session -d -s ${verb}" "$MOCK_LOG"
    done
}

@test "'down' is a normal session name again (no romp down verb — Ctrl+C the foreground romp on)" {
    run run_romp down
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s down' "$MOCK_LOG"
}

@test "on is the manager command, NOT a session name" {
    cat > "$MOCK_DIR/romp-manager" << 'MOCK'
#!/usr/bin/env bash
echo "romp-manager called" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-manager"
    export ROMP_MANAGER_BIN="$MOCK_DIR/romp-manager"
    run run_romp on
    [ "$status" -eq 0 ]
    grep -q 'romp-manager called' "$MOCK_LOG"
    # must NOT create a tmux session named "on"
    ! grep -q 'tmux new-session -d -s on' "$MOCK_LOG"
}

@test "romp-manager: control verbs error cleanly when no manager is running" {
    command -v node >/dev/null 2>&1 || skip "node not available"
    local mgr; mgr="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-manager"
    # port nothing is listening on → the control client must fail fast with a clear message
    run env ROMP_MANAGER_PORT=7531 node "$mgr" status
    [ "$status" -eq 1 ]
    [[ "$output" == *"not running"* ]]
}

@test "romp-manager: /ensure spawns an additional kernel on demand, idempotently" {
    command -v node >/dev/null 2>&1 || skip "node not available"
    command -v curl >/dev/null 2>&1 || skip "curl not available"
    local mgr; mgr="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-manager"

    # Fake kernel launcher: ignore --port and just stay alive, so the manager keeps it "running"
    # without any real port binding (the test asserts on the manager's bookkeeping, not a live kernel).
    local fake="$TEST_DIR/fake-serve"
    printf '#!/usr/bin/env bash\nexec sleep 30\n' > "$fake"
    chmod +x "$fake"

    local cport=7541 mport=7542 kport=7543
    # Launch the manager in the background; it auto-spawns 'main' on mport via the fake launcher.
    ROMP_MANAGER_PORT=$cport ROMP_SERVE_PORT=$mport ROMP_SERVE_BIN="$fake" \
        node "$mgr" up >/dev/null 2>&1 &
    MGR_PID=$!   # teardown reaps this

    # Wait for the control endpoint to come up (≤ ~3s)
    local i
    for i in $(seq 1 30); do
        curl -fsS "http://127.0.0.1:$cport/status" >/dev/null 2>&1 && break
        sleep 0.1
    done

    # Ensure a second kernel on kport → freshly spawned
    run curl -fsS -X POST "http://127.0.0.1:$cport/ensure?port=$kport"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"spawned":true'* ]]
    [[ "$output" == *"\"port\":$kport"* ]]
    [[ "$output" == *"\"id\":\"k$kport\""* ]]

    # Ensuring the same port again is idempotent — no second spawn
    run curl -fsS -X POST "http://127.0.0.1:$cport/ensure?port=$kport"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"spawned":false'* ]]

    # /status now lists both the default 'main' kernel and the on-demand one
    run curl -fsS "http://127.0.0.1:$cport/status"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"id":"main"'* ]]
    [[ "$output" == *"\"id\":\"k$kport\""* ]]

    # Graceful shutdown (teardown also reaps via MGR_PID as a backstop)
    curl -fsS -X POST "http://127.0.0.1:$cport/stop" >/dev/null 2>&1 || true
}

@test "romp-manager: /restart-all kicks every kernel in the registry (romp refresh)" {
    command -v node >/dev/null 2>&1 || skip "node not available"
    command -v curl >/dev/null 2>&1 || skip "curl not available"
    local mgr; mgr="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp-manager"
    local fake="$TEST_DIR/fake-serve"
    printf '#!/usr/bin/env bash\nexec sleep 30\n' > "$fake"
    chmod +x "$fake"

    local cport=7551 mport=7552 kport=7553
    ROMP_MANAGER_PORT=$cport ROMP_SERVE_PORT=$mport ROMP_SERVE_BIN="$fake" \
        node "$mgr" up >/dev/null 2>&1 &
    MGR_PID=$!
    local i
    for i in $(seq 1 30); do curl -fsS "http://127.0.0.1:$cport/status" >/dev/null 2>&1 && break; sleep 0.1; done
    curl -fsS -X POST "http://127.0.0.1:$cport/ensure?port=$kport" >/dev/null   # a 2nd kernel in the registry

    run curl -fsS -X POST "http://127.0.0.1:$cport/restart-all"
    [ "$status" -eq 0 ]
    # the response lists EVERY kernel it kicked — the default 'main' AND the on-demand one (not just main)
    [[ "$output" == *'"restarted"'* ]]
    [[ "$output" == *'main'* ]]
    [[ "$output" == *"k$kport"* ]]

    curl -fsS -X POST "http://127.0.0.1:$cport/stop" >/dev/null 2>&1 || true
}

# ─── Help (-h / --help) ──────────────────────────────────────────────

@test "-h prints usage and starts no session" {
    run run_romp -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"romp -d"* ]]
    ! grep -q 'tmux new-session' "$MOCK_LOG"
}

@test "--help prints usage" {
    run run_romp --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "help is a normal session name, not a subcommand" {
    run run_romp help
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s help' "$MOCK_LOG"
}

@test "--mail dispatches to romp-postal with its args" {
    cat > "$MOCK_DIR/romp-postal" << 'MOCK'
#!/usr/bin/env bash
echo "romp-postal called: $*" >> "$MOCK_LOG"
MOCK
    chmod +x "$MOCK_DIR/romp-postal"
    # same PATH-prepend shadowing as the dashboard test — without the seam this
    # exec'd the REAL romp-postal (a live mail send) instead of the mock
    export ROMP_POSTAL_BIN="$MOCK_DIR/romp-postal"

    run run_romp --mail send beta "hello"
    [ "$status" -eq 0 ]
    grep -q 'romp-postal called: send beta hello' "$MOCK_LOG"
}

@test "'mail' is now a normal session name, not a subcommand" {
    run run_romp mail
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s mail' "$MOCK_LOG"
}

@test "resume picker summary: archive headline, then caption fallback" {
    # _romp_last_summary now reads the judges' index (archive headline, else the
    # latest caption), not the retired summaries/ store. Extract just the function.
    local adir="$TEST_DIR/archive" cdir="$TEST_DIR/captions" sid="uuid-z"
    local fn="$TEST_DIR/_lastsum.sh"
    mkdir -p "$adir" "$cdir"
    sed -n '/^_romp_last_summary()/,/^}/p' "$ROMP_SCRIPT" > "$fn"
    printf '{"headline":"Fixing the feed flicker","abstract":"x"}\n' > "$adir/$sid.json"
    run env ROMP_ARCHIVE_DIR="$adir" ROMP_CAPTIONS_DIR="$cdir" \
        bash -c 'source "$1"; _romp_last_summary "$2"' _ "$fn" "$sid"
    [ "$status" -eq 0 ]
    [[ "$output" == $'reply\tFixing the feed flicker' ]]
    # no archive yet -> fall back to the most recent caption
    rm "$adir/$sid.json"
    printf '{"grain":"turn","t":1,"caption":"An older step"}\n{"grain":"turn","t":2,"caption":"Latest thing done"}\n' > "$cdir/$sid.jsonl"
    run env ROMP_ARCHIVE_DIR="$adir" ROMP_CAPTIONS_DIR="$cdir" \
        bash -c 'source "$1"; _romp_last_summary "$2"' _ "$fn" "$sid"
    [ "$status" -eq 0 ]
    [[ "$output" == $'reply\tLatest thing done' ]]
}

@test "help -h reflects which commands are PRESENT (presence-checked, no drift)" {
    # Run a copy of romp with only SOME backing romp-* binaries reachable: present commands show, absent
    # ones are hidden, built-ins always show — so the help can't drift from what's installed (the user 2026-06-16).
    local td; td="$TEST_DIR/help"; mkdir -p "$td"
    cp "$ROMP_SCRIPT" "$td/romp"
    local b; for b in romp-manager romp-version; do printf '#!/bin/sh\nexit 0\n' > "$td/$b"; chmod +x "$td/$b"; done
    run env PATH="$td:/usr/bin:/bin:/opt/homebrew/bin" bash "$td/romp" -h
    [ "$status" -eq 0 ]
    # built-ins (no backing binary) always shown — incl. `serve`, which the old static help omitted
    [[ "$output" == *"romp serve"* ]]
    [[ "$output" == *"romp --detach"* ]]
    # present backing → shown
    [[ "$output" == *"romp on"* ]]
    [[ "$output" == *"romp --version"* ]]
    # absent backing → hidden
    [[ "$output" != *"romp -d"* ]]
    [[ "$output" != *"romp -f"* ]]
    [[ "$output" != *"romp --mail"* ]]
}
