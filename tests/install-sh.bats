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
