#!/usr/bin/env bats

# A first install on a machine that has neither a VS Code-family editor, nor tmux, nor a pip-capable
# python must still produce a WORKING romp — and must SAY what it turned off. Regression cover for a
# fresh Linux install (the user 2026-07-27) where all three were absent and each failure was swallowed
# by a `|| echo`, leaving a dashboard that served 404s for every bundle and no way to start a session.
#
# Hermetic: HOME is a temp dir, and each test puts stubs ahead of the real tools on PATH.

ROMP_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    STUB="$TEST_DIR/stub"
    mkdir -p "$HOME" "$STUB"
    export CALL_LOG="$TEST_DIR/calls.log"
    export ROMP_NO_SERVICE=1 ROMP_NO_SDK=1 ROMP_NO_EXT=1
    export ROMP_INSTALL_TOKEN_TRIES=1
    export ROMP_GITHOOK_DIR="$TEST_DIR/githooks"
}

teardown() { rm -rf "$TEST_DIR"; }

# A PATH with the stub dir first, so stubs shadow anything real. NOTE this cannot hide a
# /usr/bin/tmux: PATH ordering only shadows names the stub dir also defines. Tests that need
# tmux to look ABSENT say so with ROMP_TMUX_AVAILABLE=0 (the seam install.sh, bin/romp and
# TmuxBackend all honour) rather than hoping the host has no tmux — these very tests passed
# until tmux was installed on the dev box, then started failing for a reason unrelated to
# the code under test.
bare_path() { echo "$STUB:/usr/bin:/bin"; }

# ── the bug that blanked the dashboard ────────────────────────────────────────
# vscode-extension/install.sh used to check for an editor CLI FIRST and exit 0, so on an
# editor-less machine npm install and esbuild never ran — and the kernel serves that same
# dist/ to the browser. The build must happen before, and regardless of, the editor check.

@test "vscode-extension/install.sh: builds dist even with no editor CLI on the machine" {
    # node/npm stubs that only record what they were asked to do.
    cat > "$STUB/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$CALL_LOG"
EOF
    cat > "$STUB/node" <<'EOF'
#!/usr/bin/env bash
echo "node $*" >> "$CALL_LOG"
EOF
    chmod +x "$STUB/npm" "$STUB/node"

    # No code/cursor/codium anywhere on this PATH, and no macOS app bundles in a temp HOME.
    PATH="$(bare_path)" run "$ROMP_DIR/vscode-extension/install.sh"

    [ "$status" -eq 0 ]
    # The two steps the browser dashboard depends on both ran...
    grep -q "npm install" "$CALL_LOG"
    grep -q "node esbuild.js" "$CALL_LOG"
    # ...and it said so honestly, instead of the old "built dist/ is ready" on a path that built nothing.
    [[ "$output" == *"dist/ built"* ]]
    [[ "$output" == *"No VS Code-family editor CLI found"* ]]
}

@test "vscode-extension/install.sh: builds BEFORE it looks for an editor (ordering, not just presence)" {
    cat > "$STUB/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$CALL_LOG"
EOF
    cat > "$STUB/node" <<'EOF'
#!/usr/bin/env bash
echo "node $*" >> "$CALL_LOG"
EOF
    # An editor CLI that records when IT was consulted. If the editor gate ever moves back
    # above the build, this line lands before the npm/esbuild lines and the test fails.
    cat > "$STUB/code" <<'EOF'
#!/usr/bin/env bash
echo "code $*" >> "$CALL_LOG"
EOF
    chmod +x "$STUB/npm" "$STUB/node" "$STUB/code"

    # PACKAGE_ONLY stops before the install-into-editor loop, so the run stays hermetic.
    PATH="$(bare_path)" ROMP_EXT_PACKAGE_ONLY=1 run "$ROMP_DIR/vscode-extension/install.sh"

    npm_line="$(grep -n 'npm install' "$CALL_LOG" | head -1 | cut -d: -f1)"
    build_line="$(grep -n 'node esbuild.js' "$CALL_LOG" | head -1 | cut -d: -f1)"
    [ -n "$npm_line" ] && [ -n "$build_line" ]
    [ "$npm_line" -lt "$build_line" ]
}

# ── tmux is optional, and its absence is advisory (never fatal) ───────────────

@test "install.sh: succeeds with no tmux, and names it as a disabled optional piece" {
    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=0 run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]                       # NOT a preflight failure
    [[ "$output" == *"tmux isn't installed"* ]]
    [[ "$output" == *"romp new"* ]]           # points at the backend that still works
    [[ "$output" == *"install tmux"* ]]       # and the exact remedy
}

@test "install.sh: says nothing about tmux when tmux is present" {
    cat > "$STUB/tmux" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$STUB/tmux"
    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=1 run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [[ "$output" != *"tmux isn't installed"* ]]
}

@test "romp new -t: without tmux, fails naming the remedy and the SDK alternative" {
    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=0 run "$ROMP_DIR/bin/romp" new -t notes-api
    [ "$status" -eq 1 ]
    [[ "$output" == *"tmux isn't installed"* ]]
    [[ "$output" == *"install tmux"* ]]
    # It must offer the path that still works, with the session name carried through.
    [[ "$output" == *"romp new notes-api"* ]]
    # And never leak the raw shell error the launcher would otherwise produce.
    [[ "$output" != *"command not found"* ]]
}

# ── uuidgen is not universal ─────────────────────────────────────────────────
# Debian/Ubuntu ship it in uuid-runtime, which a minimal install omits. It used to fail to an
# EMPTY --session-id rather than to an error, so the session broke with nothing naming the cause.

@test "romp new -t: generates a session id without uuidgen installed" {
    cat > "$STUB/tmux" <<'EOF'
#!/usr/bin/env bash
echo "tmux $*" >> "$CALL_LOG"
case "$1" in
  has-session) exit 1 ;;
  show|show-hooks|list-keys|list-sessions) exit 0 ;;
esac
exit 0
EOF
    cat > "$STUB/claude" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$STUB/tmux" "$STUB/claude"
    # No uuidgen on this PATH — python3 (a hard romp dependency) must cover for it.
    [ ! -x "$STUB/uuidgen" ]

    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=1 run "$ROMP_DIR/bin/romp" new -t notes-api --detach

    # A real lowercase v4 uuid reached the launch line, not an empty string.
    grep -qE 'session-id [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$CALL_LOG"
    ! grep -qE 'session-id *$' "$CALL_LOG"
}

# ── a python that cannot bootstrap pip (Debian without python3-venv) ─────────

@test "romp-sdk-setup: names the venv package when ensurepip is missing, instead of dying at pip" {
    # A python that satisfies the >= 3.10 gate but has no ensurepip — exactly Debian/Ubuntu's
    # split-out python3-venv. Real python3 for everything except `import ensurepip`.
    cat > "$STUB/python3.12" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do
  case "$a" in
    "import ensurepip") exit 1 ;;
  esac
done
exec /usr/bin/python3 "$@"
EOF
    chmod +x "$STUB/python3.12"

    export ROMP_STATE_DIR="$TEST_DIR/state"
    PATH="$(bare_path)" ROMP_PYTHON="$STUB/python3.12" run "$ROMP_DIR/bin/romp-sdk-setup"

    [ "$status" -eq 1 ]
    [[ "$output" == *"ensurepip"* ]]
    [[ "$output" == *"venv"* ]]               # names the package to install
    # Says romp still works without it — this backend being down is not a dead install.
    [[ "$output" == *"romp still runs without this"* ]]
    # And it must NOT have left a pip-less husk behind for the next run to trip over.
    [ ! -x "$TEST_DIR/state/sdkvenv/bin/python" ]
}

@test "romp-sdk-setup: rebuilds a venv that has python but no pip" {
    # Simulate the husk a pre-fix run left behind: bin/python present, bin/pip absent.
    # Gating on python alone (the old check) would skip creation and die at the pip line.
    export ROMP_STATE_DIR="$TEST_DIR/state"
    mkdir -p "$TEST_DIR/state/sdkvenv/bin"
    ln -s "$(command -v python3)" "$TEST_DIR/state/sdkvenv/bin/python"

    # Stub `python3 -m venv` so the test never builds a real venv or hits the network:
    # record that a rebuild was attempted, which is the behaviour under test.
    # ensurepip is answered explicitly rather than delegated — the host running these tests
    # may itself be a Debian box without it, and this test is about the pip-less-husk rebuild,
    # not the ensurepip gate (which test 6 covers).
    # The stub stands in for the whole venv: it records the rebuild, then lays down a bin/pip and
    # bin/python so the rest of romp-sdk-setup runs to a clean exit instead of dying at the pip line
    # (which would leave the test asserting on a crash rather than on the rebuild).
    cat > "$STUB/python3.12" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
  echo "venv-rebuild $3" >> "$CALL_LOG"
  mkdir -p "$3/bin"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$3/bin/pip"
  printf '#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n' > "$3/bin/python"
  chmod +x "$3/bin/pip" "$3/bin/python"
  exit 0
fi
for a in "$@"; do
  [ "$a" = "import ensurepip" ] && exit 0
done
exec /usr/bin/python3 "$@"
EOF
    chmod +x "$STUB/python3.12"

    PATH="$(bare_path)" ROMP_PYTHON="$STUB/python3.12" run "$ROMP_DIR/bin/romp-sdk-setup"

    [ "$status" -eq 0 ]
    grep -q "venv-rebuild" "$CALL_LOG"
}
