#!/usr/bin/env bats

# ./install.sh — "install romp normally, then everything (incl. federating this host from another
# dashboard) just works". Hermetic: HOME points at a temp dir; the login service, VS Code extension
# and SDK-venv steps are opted out (ROMP_NO_SERVICE / ROMP_NO_EXT / ROMP_NO_SDK) — they touch the
# real machine or the network. What's covered: hook symlinks, the idempotent settings.json merge,
# and the MCP/skills symlinks.

ROMP_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME"
    export ROMP_NO_SERVICE=1 ROMP_NO_EXT=1 ROMP_NO_SDK=1
    # Redirect the git pre-push hook symlink into a temp dir so install.sh never
    # writes into the REAL repo's .git/hooks while these tests run.
    export ROMP_GITHOOK_DIR="$TEST_DIR/githooks"
}

teardown() { rm -rf "$TEST_DIR"; }

count_cmd() {   # occurrences of a hook script in one event's rules
    python3 - "$HOME/.claude/settings.json" "$1" "$2" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
n = sum(1 for r in s.get("hooks", {}).get(sys.argv[2], []) for h in r.get("hooks", [])
        if h.get("command", "").endswith(sys.argv[3]))
print(n)
PY
}

@test "install.sh: wires hooks, settings.json, and the MCP config on a fresh machine" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [ -L "$HOME/.claude/hooks/tmux-status.sh" ]
    [[ "$(readlink "$HOME/.claude/hooks/tmux-status.sh")" == *"/hooks/tmux-status.sh" ]]
    [ "$(count_cmd Stop tmux-status.sh)" = "1" ]
    [ "$(count_cmd Stop romp-summarize.sh)" = "1" ]
    [ "$(count_cmd Stop romp-postal-drain.sh)" = "1" ]
    [ "$(count_cmd SessionStart romp-postal-ensure.sh)" = "1" ]
    [ "$(count_cmd PostToolUse tmux-status.sh)" = "1" ]
    [ -L "$HOME/.claude/romp-postal.mcp.json" ]
}

@test "install.sh: idempotent — a second run adds no duplicate hook entries" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already registered"* ]]
    [ "$(count_cmd Stop tmux-status.sh)" = "1" ]
    [ "$(count_cmd UserPromptSubmit romp-summarize.sh)" = "1" ]
    # regression: a re-run used to FOLLOW the existing skill dir-symlink and drop a new link INSIDE
    # the repo (claude/skills/romp/romp → an absolute personal path). ln -sfn replaces the link.
    [ ! -e "$ROMP_DIR/claude/skills/romp/romp" ]
    [ ! -e "$ROMP_DIR/claude/skills/romp-postal/romp-postal" ]
    [ -L "$HOME/.claude/skills/romp" ]
}

@test "install.sh: preflight fails clearly when node is missing" {
    ROMP_NODE=romp-test-no-such-node run "$ROMP_DIR/install.sh"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Node.js not found"* ]]
    [[ "$output" == *"brew install node"* ]]
    # nothing was installed: the preflight runs before any mutation
    [ ! -e "$HOME/.claude/hooks/tmux-status.sh" ]
}

@test "install.sh: ROMP_SKIP_PREFLIGHT bypasses the checks" {
    ROMP_NODE=romp-test-no-such-node ROMP_SKIP_PREFLIGHT=1 run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [ -L "$HOME/.claude/hooks/tmux-status.sh" ]
}

# The login-service step (the user's rescue_me, 2026-07-21): a webview deploy must never bootout a
# HEALTHY romp-manager, and must FAIL LOUDLY (not `|| echo`-swallow) if an install it DID attempt fails —
# the swallowed failure is what left the dashboard dead on :7433. ROMP_SERVICE_BIN stubs romp-service.
_svc_stub() {   # write a fake romp-service to $1; behavior toggled by ROMP_SVC_RUNNING / ROMP_SVC_FAIL
    cat > "$1" <<'SH'
#!/usr/bin/env bash
echo "$1" >> "$ROMP_SVC_LOG"
case "$1" in
  status) echo "installed: /tmp/plist"; [[ -n "${ROMP_SVC_RUNNING:-}" ]] && echo "running" ;;
  install) [[ -n "${ROMP_SVC_FAIL:-}" ]] && { echo "romp-service: bootstrap lost the drain-race" >&2; exit 1; } ;;
esac
exit 0
SH
    chmod +x "$1"
}

@test "install.sh: skips the service bootout when romp-manager is already running" {
    unset ROMP_NO_SERVICE
    _svc_stub "$TEST_DIR/romp-service"
    export ROMP_SVC_LOG="$TEST_DIR/svc.log" ROMP_SVC_RUNNING=1
    ROMP_SERVICE_BIN="$TEST_DIR/romp-service" run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already running"* ]]
    # it asked status but NEVER ran install — the healthy manager was left up
    grep -qx status "$TEST_DIR/svc.log"
    ! grep -qx install "$TEST_DIR/svc.log"
}

@test "install.sh: installs the service when romp-manager is NOT running" {
    unset ROMP_NO_SERVICE
    _svc_stub "$TEST_DIR/romp-service"
    export ROMP_SVC_LOG="$TEST_DIR/svc.log"   # ROMP_SVC_RUNNING unset -> not running
    ROMP_SERVICE_BIN="$TEST_DIR/romp-service" run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    grep -qx install "$TEST_DIR/svc.log"
}

@test "install.sh: a FAILED service install fails the whole run loudly (never swallowed)" {
    unset ROMP_NO_SERVICE
    _svc_stub "$TEST_DIR/romp-service"
    export ROMP_SVC_LOG="$TEST_DIR/svc.log" ROMP_SVC_FAIL=1   # not running + install exits 1
    ROMP_SERVICE_BIN="$TEST_DIR/romp-service" run "$ROMP_DIR/install.sh"
    [ "$status" -ne 0 ]
    [[ "$output" == *"romp-service install FAILED"* ]]
    [[ "$output" == *"dashboard will be dead"* ]]
    grep -qx install "$TEST_DIR/svc.log"
}

@test "install.sh: merges into an existing settings.json without clobbering the user's own config" {
    mkdir -p "$HOME/.claude"
    cat > "$HOME/.claude/settings.json" <<'JSON'
{
  "model": "opus",
  "hooks": {
    "Stop": [ { "hooks": [ { "type": "command", "command": "my-own-hook.sh" } ] } ]
  }
}
JSON
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
assert s["model"] == "opus", "unrelated settings preserved"
stop = [h["command"] for r in s["hooks"]["Stop"] for h in r["hooks"]]
assert "my-own-hook.sh" in stop, stop
assert any(c.endswith("tmux-status.sh") for c in stop), stop
PY
}

# ── vscode-extension/install.sh: the build version is stamped, never committed ──
# The editor caches extension code BY VERSION, so each install must carry a strictly
# newer one; that number used to be written back into package.json and committed,
# which produced a version-churn commit per install and a package.json version that
# read like a romp release version without being one. The stamp now lives only in the
# packaged .vsix. These pin that: package.json comes back byte-identical, and the
# stamp it briefly held is strictly greater than the committed baseline.

ext_setup() {   # a throwaway copy so nothing here can touch the real extension dir
    EXT="$TEST_DIR/ext"
    mkdir -p "$EXT"
    cp "$ROMP_DIR/vscode-extension/install.sh" "$EXT/install.sh"
    printf '{\n  "name": "romp-chat-view",\n  "version": "0.4.0"\n}\n' > "$EXT/package.json"
    echo 'require("fs").writeFileSync("dist.marker","built")' > "$EXT/esbuild.js"
    # stub the toolchain the script shells out to; real node does the stamping
    mkdir -p "$TEST_DIR/stub"
    printf '#!/bin/sh\nexit 0\n' > "$TEST_DIR/stub/npm"
    printf '#!/bin/sh\ntouch romp-chat-view.vsix\nexit 0\n' > "$TEST_DIR/stub/npx"
    chmod +x "$TEST_DIR/stub/npm" "$TEST_DIR/stub/npx"
    export PATH="$TEST_DIR/stub:$PATH"
}

@test "vscode-extension/install.sh: restores package.json, leaving the committed version untouched" {
    ext_setup
    before="$(cat "$EXT/package.json")"
    ROMP_EXT_PACKAGE_ONLY=1 run "$EXT/install.sh"
    [ "$status" -eq 0 ]
    [ "$(cat "$EXT/package.json")" = "$before" ]   # byte-identical
    [ ! -f "$EXT/package.json.orig" ]              # no scratch file left behind
    [[ "$output" == *"build version -> 0.4."* ]]
    [[ "$output" == *"not committed"* ]]
}

@test "vscode-extension/install.sh: the stamped version is strictly newer than the committed baseline" {
    ext_setup
    ROMP_EXT_PACKAGE_ONLY=1 run "$EXT/install.sh"
    [ "$status" -eq 0 ]
    stamped="$(echo "$output" | sed -n 's/.*build version -> \([0-9.]*\).*/\1/p')"
    [ -n "$stamped" ]
    python3 - "$stamped" <<'PY'
import sys
base = (0, 4, 0)                       # the committed baseline in this fixture
got = tuple(int(x) for x in sys.argv[1].split("."))
assert got[:2] == base[:2], f"major.minor must not move (a lower one reads as a DOWNGRADE): {got}"
assert got > base, f"stamp must be strictly newer than the baseline: {got} !> {base}"
PY
}

@test "vscode-extension/install.sh: restores package.json even when packaging FAILS" {
    ext_setup
    printf '#!/bin/sh\nexit 3\n' > "$TEST_DIR/stub/npx"   # vsce package blows up mid-run
    chmod +x "$TEST_DIR/stub/npx"
    before="$(cat "$EXT/package.json")"
    ROMP_EXT_PACKAGE_ONLY=1 run "$EXT/install.sh"
    [ "$status" -ne 0 ]                            # the failure still surfaces
    [ "$(cat "$EXT/package.json")" = "$before" ]   # ...and the trap still restored
    [ ! -f "$EXT/package.json.orig" ]
}

# ── git pre-push identifier hook ──────────────────────────────────────
# The repo may go public and history is permanent, so a personal identifier must
# never leave the machine. install.sh symlinks .githooks/pre-push into the shared
# git hooks dir; the hook runs tests/test_no_personal_identifiers.py and blocks a
# push that would leak one. (ROMP_GITHOOK_DIR redirects the target in setup().)

@test "install.sh: symlinks the pre-push hook into the git hooks dir" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [ -L "$ROMP_GITHOOK_DIR/pre-push" ]
    [[ "$(readlink "$ROMP_GITHOOK_DIR/pre-push")" == *"/.githooks/pre-push" ]]
}

@test "install.sh: ROMP_NO_GITHOOK skips the pre-push hook" {
    ROMP_NO_GITHOOK=1 run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [ ! -e "$ROMP_GITHOOK_DIR/pre-push" ]
}

# Behaviour of the hook itself, exercised through a real `git push` to a bare
# remote, with a SYNTHETIC denylist (never a real identifier) via XDG_CONFIG_HOME.
setup_hook_repo() {
    export XDG_CONFIG_HOME="$TEST_DIR/cfg"
    mkdir -p "$XDG_CONFIG_HOME/romp"
    printf 'ZZBANNEDZZ\n' > "$XDG_CONFIG_HOME/romp/private-strings.txt"
    git init -q "$TEST_DIR/remote.git" --bare
    WORK="$TEST_DIR/work"
    git init -q "$WORK"
    git -C "$WORK" config user.email t@e.invalid
    git -C "$WORK" config user.name t
    mkdir -p "$WORK/tests"
    cp "$ROMP_DIR/tests/test_no_personal_identifiers.py" "$WORK/tests/"
    cp "$ROMP_DIR/.githooks/pre-push" "$WORK/.git/hooks/pre-push"
    git -C "$WORK" remote add origin "$TEST_DIR/remote.git"
}

@test "pre-push hook: allows a push when the tree is clean" {
    setup_hook_repo
    echo "clean" > "$WORK/ok.txt"
    git -C "$WORK" add -A && git -C "$WORK" commit -qm clean
    run git -C "$WORK" push origin HEAD:main
    [ "$status" -eq 0 ]
}

@test "pre-push hook: blocks a push that would leak an identifier" {
    setup_hook_repo
    printf 'leak ZZBANNEDZZ here\n' > "$WORK/leak.txt"
    git -C "$WORK" add -A && git -C "$WORK" commit -qm leak
    run git -C "$WORK" push origin HEAD:main
    [ "$status" -ne 0 ]
    [[ "$output" == *"BLOCKED"* ]]
}

@test "pre-push hook: --no-verify bypasses the block" {
    setup_hook_repo
    printf 'leak ZZBANNEDZZ here\n' > "$WORK/leak.txt"
    git -C "$WORK" add -A && git -C "$WORK" commit -qm leak
    run git -C "$WORK" push --no-verify origin HEAD:main
    [ "$status" -eq 0 ]
}
