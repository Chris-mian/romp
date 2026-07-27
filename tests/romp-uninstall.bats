#!/usr/bin/env bats

# romp-uninstall must leave the machine looking un-installed, so a from-scratch reinstall really is
# from scratch — and must do it WITHOUT collateral damage to the user's own Claude Code config.
# Hermetic: HOME is a temp dir; the login service and network steps are opted out.

ROMP_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

# The uninstaller is NEVER run from the real clone here. It tears down the login service and kills
# the manager, and its ROMP_DIR comes from its own $0 — so running the repo copy would take down the
# developer's live romp mid-test-suite (it did, 2026-07-27). Instead each test gets a THROWAWAY clone:
# the real script, a stubbed romp-service, and disposable build artifacts. Everything the uninstaller
# does to $HOME is still exercised for real, because HOME is a temp dir too.
fake_clone() {
    CLONE="$TEST_DIR/clone"
    mkdir -p "$CLONE/bin" "$CLONE/vscode-extension"
    cp "$ROMP_DIR/bin/romp-uninstall" "$CLONE/bin/romp-uninstall"
    chmod +x "$CLONE/bin/romp-uninstall"
    cat > "$CLONE/bin/romp-service" <<EOF
#!/usr/bin/env bash
echo "romp-service \$* (stub)" >> "$TEST_DIR/service.log"
EOF
    chmod +x "$CLONE/bin/romp-service"
}

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME"
    export ROMP_NO_SERVICE=1 ROMP_NO_EXT=1 ROMP_NO_SDK=1
    export ROMP_INSTALL_TOKEN_TRIES=1
    export ROMP_GITHOOK_DIR="$TEST_DIR/githooks"
    export ROMP_STATE_DIR="$TEST_DIR/state"
    mkdir -p "$ROMP_STATE_DIR"
    fake_clone
}

teardown() { rm -rf "$TEST_DIR"; }

hook_count() {   # how many romp hook commands are left registered across all events
    python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys, os
try:
    s = json.load(open(sys.argv[1]))
except (IOError, OSError, ValueError):
    print(0); raise SystemExit
OURS = ("tmux-status.sh", "romp-summarize.sh", "romp-postal-drain.sh", "romp-postal-ensure.sh",
        "romp-postal-revive.sh", "romp-postal-context.sh", "romp-wake.sh")
n = sum(1 for rules in (s.get("hooks") or {}).values() for r in rules for h in r.get("hooks", [])
        if h.get("command", "").rsplit("/", 1)[-1] in OURS)
print(n)
PY
}

@test "romp-uninstall: removes the hook symlinks, skills and MCP config that install.sh created" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    [ -L "$HOME/.claude/hooks/tmux-status.sh" ]
    [ -L "$HOME/.claude/romp-postal.mcp.json" ]
    [ "$(hook_count)" -gt 0 ]

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]

    [ ! -e "$HOME/.claude/hooks/tmux-status.sh" ]
    [ ! -e "$HOME/.claude/hooks/romp-summarize.sh" ]
    [ ! -e "$HOME/.claude/hooks/romp-postal-drain.sh" ]
    [ ! -e "$HOME/.claude/skills/romp" ]
    [ ! -e "$HOME/.claude/skills/romp-postal" ]
    [ ! -e "$HOME/.claude/romp-postal.mcp.json" ]
    [ "$(hook_count)" -eq 0 ]
}

@test "romp-uninstall: leaves the user's OWN hooks in settings.json untouched" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]

    # A hook of the user's own, in an event romp also writes to.
    python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["hooks"].setdefault("Stop", []).append(
    {"hooks": [{"type": "command", "command": "~/.claude/hooks/my-own-notify.sh", "timeout": 5}]})
s["permissions"] = {"allow": ["Bash(ls:*)"]}      # a non-hook setting, must also survive
json.dump(s, open(p, "w"), indent=2)
PY

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]

    run python3 -c "
import json; s = json.load(open('$HOME/.claude/settings.json'))
cmds = [h['command'] for rules in (s.get('hooks') or {}).values() for r in rules for h in r.get('hooks', [])]
assert '~/.claude/hooks/my-own-notify.sh' in cmds, cmds
assert s['permissions'] == {'allow': ['Bash(ls:*)']}, s.get('permissions')
print('preserved')
"
    [ "$status" -eq 0 ]
    [[ "$output" == *"preserved"* ]]
}

@test "romp-uninstall: keeps recorded state by default, deletes it only with --purge" {
    echo '{"synthetic": "record"}' > "$ROMP_STATE_DIR/serve-token"
    mkdir -p "$ROMP_STATE_DIR/sdkvenv/bin"

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]
    [ -f "$ROMP_STATE_DIR/serve-token" ]          # records survive a plain uninstall...
    [ ! -d "$ROMP_STATE_DIR/sdkvenv" ]            # ...but the venv is an install artifact, so it goes
    [[ "$output" == *"state dir kept"* ]]

    run "$CLONE/bin/romp-uninstall" --yes --purge
    [ "$status" -eq 0 ]
    [ ! -d "$ROMP_STATE_DIR" ]
}

@test "romp-uninstall: strips the PATH line bootstrap.sh added, and nothing else" {
    cat > "$HOME/.bashrc" <<EOF
export EDITOR=vim

# romp
export PATH="\$PATH:$CLONE/bin"
alias ll='ls -la'
EOF

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]

    ! grep -qF "$CLONE/bin" "$HOME/.bashrc"
    ! grep -q '^# romp$' "$HOME/.bashrc"
    grep -q 'EDITOR=vim' "$HOME/.bashrc"          # the user's own lines are untouched
    grep -q "alias ll=" "$HOME/.bashrc"
}

@test "romp-uninstall: removes the build artifacts a reinstall must rebuild" {
    # Stand-ins for what vscode-extension/install.sh produces, in the throwaway clone — never the
    # real one, whose dist/ is what the running kernel is serving to the browser right now.
    mkdir -p "$CLONE/vscode-extension/node_modules" "$CLONE/vscode-extension/dist"
    touch "$CLONE/vscode-extension/dist/render.js" "$CLONE/vscode-extension/romp-chat-view.vsix"

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]

    [ ! -d "$CLONE/vscode-extension/node_modules" ]
    [ ! -d "$CLONE/vscode-extension/dist" ]
    [ ! -f "$CLONE/vscode-extension/romp-chat-view.vsix" ]
}

@test "romp-uninstall: never touches a DIFFERENT clone's install (kills only its own manager)" {
    # Two clones coexist on a dev machine (worktrees are the norm here). Uninstalling one must
    # leave the other's build artifacts — and, by the same path-scoped match, its manager — alone.
    other="$TEST_DIR/other-clone"
    mkdir -p "$other/vscode-extension/dist"
    touch "$other/vscode-extension/dist/render.js"

    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]

    [ -f "$other/vscode-extension/dist/render.js" ]
    # The pkill pattern must be this clone's absolute path, not a bare 'bin/romp-manager'.
    grep -q 'pkill -f "\$ROMP_DIR/bin/romp-manager"' "$CLONE/bin/romp-uninstall"
}

@test "romp-uninstall: is idempotent — a second run on a clean machine still exits 0" {
    run "$ROMP_DIR/install.sh"
    [ "$status" -eq 0 ]
    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]
    run "$CLONE/bin/romp-uninstall" --yes
    [ "$status" -eq 0 ]
}

@test "romp uninstall: reachable as a verb and listed in help" {
    run "$ROMP_DIR/bin/romp" help
    [ "$status" -eq 0 ]
    [[ "$output" == *"romp uninstall"* ]]
}
