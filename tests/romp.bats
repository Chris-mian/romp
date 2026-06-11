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
    exit 0
    ;;
esac
exit 0
MOCK
    chmod +x "$MOCK_DIR/tmux"

    export PATH="$MOCK_DIR:$PATH"
    unset TMUX            # default: outside tmux → attach-session branch
    cd "$WORK_DIR"
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Helper — runs romp with merged stdout+stderr so BATS captures errors
run_romp() {
    "$ROMP_SCRIPT" "$@" 2>&1
}

# ─── Launch tests ────────────────────────────────────────────────────

@test "no args: session named after the folder, claude exec'd with empty --name" {
    run run_romp
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'tmux set -t myproject @romp 1' "$MOCK_LOG"
    # Empty --name → no auto-title pill in Claude's prompt box; the session
    # is identified by its tmux name (ghostty tab + dashboard) instead.
    grep -q 'tmux send-keys -t myproject exec claude --name "" Enter' "$MOCK_LOG"
    grep -q 'tmux attach-session -t myproject' "$MOCK_LOG"
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
    grep -q 'exec claude --name ""' "$MOCK_LOG"
}

# ─── Resume tests ────────────────────────────────────────────────────

@test "resume: romp -r launches claude --resume" {
    run run_romp -r
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'exec claude --name "" --resume Enter' "$MOCK_LOG"
}

@test "resume: -r and --resume are equivalent" {
    run run_romp -r
    [ "$status" -eq 0 ]
    grep -q 'exec claude --name "" --resume Enter' "$MOCK_LOG"

    : > "$MOCK_LOG"
    run run_romp --resume
    [ "$status" -eq 0 ]
    grep -q 'exec claude --name "" --resume Enter' "$MOCK_LOG"
}

@test "resume: 'resume' is now a normal session name, not a directive" {
    # -r/--resume replaced the bare `resume` word, so it's free to name a session.
    run run_romp resume
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s resume' "$MOCK_LOG"
    ! grep -q -- '--resume' "$MOCK_LOG"
}

@test "resume: named session plus -r" {
    run run_romp my-task -r
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s my-task' "$MOCK_LOG"
    grep -q 'tmux send-keys -t my-task exec claude --name "" --resume Enter' "$MOCK_LOG"
}

@test "resume: explicit session id (--resume <id>) resumes that conversation" {
    run run_romp --resume abc123-uuid
    [ "$status" -eq 0 ]
    grep -q 'tmux send-keys -t myproject exec claude --name "" --resume abc123-uuid Enter' "$MOCK_LOG"
}

@test "resume: name collision uniquifies instead of hijacking the session" {
    echo "myproject" > "$MOCK_TMUX_SESSIONS_FILE"

    run run_romp -r
    [ "$status" -eq 0 ]
    ! grep -qE 'tmux attach-session -t myproject$' "$MOCK_LOG"
    grep -q 'tmux new-session -d -s myproject-2' "$MOCK_LOG"
    grep -q 'tmux send-keys -t myproject-2 exec claude --name "" --resume Enter' "$MOCK_LOG"
}

# ─── Detach tests ────────────────────────────────────────────────────

@test "detach: --detach creates the session but does not attach" {
    run run_romp --detach
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'tmux send-keys -t myproject exec claude --name "" Enter' "$MOCK_LOG"
    ! grep -q 'tmux attach-session' "$MOCK_LOG"
    [[ "$output" == *"attach with: tmux attach -t myproject"* ]]
}

@test "detach: --resume + id + detach is the skill conversion path" {
    run run_romp --resume sess-xyz --detach
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s myproject' "$MOCK_LOG"
    grep -q 'tmux send-keys -t myproject exec claude --name "" --resume sess-xyz Enter' "$MOCK_LOG"
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

@test "color: all colors taken falls back to a hash pick" {
    local palette=("#1EA1EB" "#54B204" "#9088F0" "#4EA8A9" "#DD42FF" "#E87221" "#98998A" "#F85B5A" "#F9D849")
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

    run run_romp --mail send beta "hello"
    [ "$status" -eq 0 ]
    grep -q 'romp-postal called: send beta hello' "$MOCK_LOG"
}

@test "'mail' is now a normal session name, not a subcommand" {
    run run_romp mail
    [ "$status" -eq 0 ]
    grep -q 'tmux new-session -d -s mail' "$MOCK_LOG"
}
