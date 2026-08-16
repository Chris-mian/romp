#!/usr/bin/env bats

# A first install on a machine that has neither a VS Code-family editor nor a pip-capable
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
    # Keep vscode-extension/install.sh's app-bundle probe inside the sandbox: on a
    # dev mac, /Applications really contains editors, and finding one would send
    # the "no editor" tests down the package-and-install path.
    export ROMP_EDITOR_APPS="$TEST_DIR/no-apps"

    # An ALLOWLIST bin instead of the machine's /usr/bin — "absent" must mean
    # the same thing on every machine, and with a real /usr/bin it doesn't: CI's
    # apt/Debian put node there, and a mac keeps it in
    # /opt/homebrew. So a PATH of "$STUB:/usr/bin:/bin" is bare on one box and
    # fully equipped on the next (exactly how these tests passed on the box that
    # wrote them and failed on the runner). Symlink only the tools the scripts
    # under test legitimately need; everything else is absent, everywhere.
    BAREBIN="$TEST_DIR/barebin"; mkdir -p "$BAREBIN"
    local t p
    for t in bash sh env dirname basename realpath readlink mktemp mkdir ln cp mv rm \
             cat echo printf grep sed awk tr sort head tail cut wc date chmod touch \
             sleep find xargs uname hostname python3 git curl; do
        p="$(command -v "$t" 2>/dev/null || true)"
        [ -n "$p" ] && ln -s "$p" "$BAREBIN/$t"
    done
}

teardown() { rm -rf "$TEST_DIR"; }

# Stubs first, then the allowlist — nothing from the host machine leaks in (CI's
# Debian's node lives in /usr/bin, so a PATH keeping /usr/bin is never
# bare).
# assumption explicitly via ROMP_TMUX_AVAILABLE (the seam install.sh, bin/romp
# and TmuxBackend all honour), so the assertion doesn't ride on PATH mechanics.
bare_path() { echo "$STUB:$BAREBIN"; }

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
    # The PACKAGE_ONLY path reaches `npx @vscode/vsce package`; a real npx would
    # hit the network (or, on the allowlist PATH, not exist at all).
    cat > "$STUB/npx" <<'EOF'
#!/usr/bin/env bash
echo "npx $*" >> "$CALL_LOG"
EOF
    chmod +x "$STUB/npm" "$STUB/node" "$STUB/code" "$STUB/npx"

    # PACKAGE_ONLY stops before the install-into-editor loop, so the run stays hermetic.
    PATH="$(bare_path)" ROMP_EXT_PACKAGE_ONLY=1 run "$ROMP_DIR/vscode-extension/install.sh"

    npm_line="$(grep -n 'npm install' "$CALL_LOG" | head -1 | cut -d: -f1)"
    build_line="$(grep -n 'node esbuild.js' "$CALL_LOG" | head -1 | cut -d: -f1)"
    [ -n "$npm_line" ] && [ -n "$build_line" ]
    [ "$npm_line" -lt "$build_line" ]
}





# ── uuidgen is not universal ─────────────────────────────────────────────────
# Debian/Ubuntu ship it in uuid-runtime, which a minimal install omits. It used to fail to an
# EMPTY --session-id rather than to an error, so the session broke with nothing naming the cause.


# ── a python that cannot bootstrap pip (Debian without python3-venv) ─────────

@test "romp-sdk-setup: names the venv package when ensurepip is missing, instead of dying at pip" {
    # A python that satisfies the >= 3.10 gate but has no ensurepip — exactly Debian/Ubuntu's
    # split-out python3-venv. Fully self-contained: it answers romp-sdk-setup's probes itself
    # rather than delegating to the host python3, whose version differs per machine (a mac's
    # /usr/bin/python3 is the 3.9 xcode shim, which dies at the version gate and never reaches
    # the ensurepip branch this test is about).
    cat > "$STUB/python3.12" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"version_info >= (3, 10)"*) exit 0 ;;
  *'print("%d.%d"'*)           echo "3.12"; exit 0 ;;
  *"import ensurepip"*)        exit 1 ;;
esac
exit 0
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
case "$*" in
  *"version_info >= (3, 10)"*) exit 0 ;;
  *'print("%d.%d"'*)           echo "3.12"; exit 0 ;;
  *"import ensurepip"*)        exit 0 ;;
esac
exit 0
EOF
    chmod +x "$STUB/python3.12"

    PATH="$(bare_path)" ROMP_PYTHON="$STUB/python3.12" run "$ROMP_DIR/bin/romp-sdk-setup"

    [ "$status" -eq 0 ]
    grep -q "venv-rebuild" "$CALL_LOG"
}

# ── installs ship a PRODUCTION bundle ────────────────────────────────────────
# Without --production the dashboard shipped a development build: render.js, the chat pane's
# code, was 578 KB of unminified JS the browser parsed before anything appeared (a slow chat
# load on a fresh install). Minified it is 297 KB and no sourcemaps are emitted at all.

@test "vscode-extension/install.sh: builds minified for an install, not a dev bundle" {
    cat > "$STUB/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$CALL_LOG"
EOF
    cat > "$STUB/node" <<'EOF'
#!/usr/bin/env bash
echo "node $*" >> "$CALL_LOG"
EOF
    chmod +x "$STUB/npm" "$STUB/node"

    PATH="$(bare_path)" run "$ROMP_DIR/vscode-extension/install.sh"
    [ "$status" -eq 0 ]
    grep -q 'node esbuild.js --production' "$CALL_LOG"
}

@test "vscode-extension/install.sh: ROMP_EXT_DEV_BUILD keeps the readable bundle for a UI dev loop" {
    cat > "$STUB/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$CALL_LOG"
EOF
    cat > "$STUB/node" <<'EOF'
#!/usr/bin/env bash
echo "node $*" >> "$CALL_LOG"
EOF
    chmod +x "$STUB/npm" "$STUB/node"

    PATH="$(bare_path)" ROMP_EXT_DEV_BUILD=1 run "$ROMP_DIR/vscode-extension/install.sh"
    [ "$status" -eq 0 ]
    grep -qE 'node esbuild.js *$' "$CALL_LOG"
    ! grep -q -- '--production' "$CALL_LOG"
}

# ── the finish line points at the command, not just a URL ────────────────────

@test "install.sh: ends by telling you to type romp, keeping the link as the fallback" {
    # Force the "romp is running" branch: that block needs a minted token to print.
    export ROMP_STATE_DIR="$TEST_DIR/state"
    mkdir -p "$ROMP_STATE_DIR"
    echo "TESTTOKEN123" > "$ROMP_STATE_DIR/serve-token"

    # node is absent from the allowlist bin by design; preflight needs one.
    printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB/node"; chmod +x "$STUB/node"

    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=1 run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Open a new terminal and type:  romp"* ]]
    # The URL must survive as the fallback — this terminal's PATH is stale, and a headless
    # box has no browser for `romp` to open.
    [[ "$output" == *"token=TESTTOKEN123"* ]]
}

# ── romp installs its own critical dependency, rather than assigning homework ──
# The SDK backend is what plain `romp new` runs on, so a box without it has a romp that starts,
# looks healthy and cannot run a single session. romp-sdk-setup used to stop at Debian's missing
# ensurepip and tell the user to sudo — which an installer cannot do for them, and which is exactly
# where a fresh python3.14 install stalled (the user 2026-07-28). It now builds the venv without pip
# and bootstraps pip itself; the sudo message is the LAST resort, not the first answer.

# A python that passes the >= 3.10 gate, has no ensurepip, and can fake `-m venv --without-pip`
# well enough to exercise the bootstrap. Self-contained for the same reason as the test above: the
# host's own python3 differs per machine.
_pipless_python() {
    cat > "$STUB/python3.12" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *"version_info >= (3, 10)"*) exit 0 ;;
  *'print("%d.%d"'*)           echo "3.12"; exit 0 ;;
  *"import ensurepip"*)        exit 1 ;;
  *"-m venv --without-pip"*)
      v="\${@: -1}"
      mkdir -p "\$v/bin"
      # the venv's python: running get-pip.py is what mints bin/pip
      printf '#!/usr/bin/env bash\ncase "\$*" in *get-pip.py*) printf "#!/usr/bin/env bash\\nexit 0\\n" > "\$(dirname "\$0")/pip"; chmod +x "\$(dirname "\$0")/pip";; esac\nexit 0\n' > "\$v/bin/python"
      chmod +x "\$v/bin/python"
      exit 0 ;;
esac
exit 0
EOF
    chmod +x "$STUB/python3.12"
}

@test "romp-sdk-setup: bootstraps pip itself when ensurepip is missing — no sudo, no homework" {
    _pipless_python
    export ROMP_STATE_DIR="$TEST_DIR/state"
    # file:// keeps the fetch hermetic — curl handles it, and no test may reach the network.
    printf '# a stand-in for PyPA get-pip.py\n' > "$TEST_DIR/get-pip.py"

    PATH="$(bare_path)" ROMP_PYTHON="$STUB/python3.12" \
      ROMP_GET_PIP_URL="file://$TEST_DIR/get-pip.py" run "$ROMP_DIR/bin/romp-sdk-setup"

    [ "$status" -eq 0 ]
    [[ "$output" == *"bootstrapping pip"* ]]
    # the whole point: it must NOT send the user to sudo when it can do the job itself
    [[ "$output" != *"sudo apt install"* ]]
    [ -x "$TEST_DIR/state/sdkvenv/bin/pip" ]
    # the downloaded bootstrap script is not left lying in the venv
    [ ! -f "$TEST_DIR/state/sdkvenv/get-pip.py" ]
}

@test "romp-sdk-setup: ROMP_NO_GET_PIP opts out, and then it names the package" {
    _pipless_python
    export ROMP_STATE_DIR="$TEST_DIR/state"

    PATH="$(bare_path)" ROMP_PYTHON="$STUB/python3.12" ROMP_NO_GET_PIP=1 \
      run "$ROMP_DIR/bin/romp-sdk-setup"

    [ "$status" -eq 1 ]
    [[ "$output" == *"sudo apt install"* ]]           # the fallback is still there for anyone who wants it
    [[ "$output" == *"romp still runs without this"* ]]
    [ ! -x "$TEST_DIR/state/sdkvenv/bin/python" ]     # and never a husk for the next run to trip over
}

@test "install.sh: a missing SDK backend is a BANNER, not an optional-pieces footnote" {
    export ROMP_STATE_DIR="$TEST_DIR/state"
    mkdir -p "$ROMP_STATE_DIR"
    echo "TESTTOKEN123" > "$ROMP_STATE_DIR/serve-token"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB/node"; chmod +x "$STUB/node"
    # Let the real sdk step RUN (ROMP_NO_SDK cleared — that flag is what sets ROMP_SDK_MISSING) but
    # make it fail at the VERSION gate, so this stays hermetic: no venv built, no network reached.
    cat > "$STUB/oldpython" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"version_info >= (3, 10)"*) exit 1 ;;
  *'print("%d.%d"'*)           echo "3.9"; exit 0 ;;
esac
exit 0
EOF
    chmod +x "$STUB/oldpython"

    PATH="$(bare_path)" ROMP_TMUX_AVAILABLE=1 ROMP_NO_SDK= ROMP_PYTHON="$STUB/oldpython" \
      run "$ROMP_DIR/install.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"CANNOT START SESSIONS"* ]]
    # it must NOT be filed under the things you can happily live without
    [[ "$output" != *"Some optional pieces aren't set up:"*"Agent SDK"* ]]
}
