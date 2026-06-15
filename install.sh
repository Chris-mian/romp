#!/usr/bin/env bash
# Install romp onto this machine:
#   - symlink the Claude Code hooks into ~/.claude/hooks/
#   - symlink the MCP config (Romp Postal Service) into ~/.claude/
#   - symlink the /romp skill into ~/.claude/skills/
#   - build + install the romp-chat-view VS Code extension
#
# bin/ is NOT symlinked anywhere — add it to PATH in your shell rc:
#   export PATH="$PATH:<this repo>/bin"
set -euo pipefail
ROMP_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/.claude/hooks" "$HOME/.claude/skills"

for h in romp-summarize.sh romp-postal-drain.sh romp-postal-ensure.sh \
         romp-postal-revive.sh romp-manager-ensure.sh tmux-status.sh; do
    ln -sf "$ROMP_DIR/hooks/$h" "$HOME/.claude/hooks/$h"
done
echo "  Symlinked romp hooks into ~/.claude/hooks/"

# Register the hooks in ~/.claude/settings.json so Claude Code actually fires
# them. Idempotent merge: adds only missing romp entries, never touches any
# other hooks you have registered.
python3 - <<'PYEOF'
import json, os

SETTINGS = os.path.expanduser("~/.claude/settings.json")
WANT = {  # event -> [(hook script, timeout secs, async)]
    "SessionStart":     [("tmux-status.sh", 5, False),
                         ("romp-postal-ensure.sh", 5, True),
                         ("romp-manager-ensure.sh", 5, True),
                         ("romp-postal-revive.sh", 8, False)],
    "UserPromptSubmit": [("tmux-status.sh", 5, False),
                         ("romp-summarize.sh", 10, True)],
    "PostToolUse":      [("tmux-status.sh", 5, False)],
    "Stop":             [("tmux-status.sh", 5, False),
                         ("romp-summarize.sh", 10, True),
                         ("romp-postal-drain.sh", 10, False)],
    "Notification":     [("tmux-status.sh", 5, False)],
    "PreCompact":       [("tmux-status.sh", 5, False)],
    "PostCompact":      [("tmux-status.sh", 5, False)],
}

try:
    with open(SETTINGS) as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
hooks = settings.setdefault("hooks", {})

added = []
for event, entries in WANT.items():
    groups = hooks.setdefault(event, [])
    registered = {h.get("command") for g in groups for h in g.get("hooks", [])}
    target = next((g for g in groups if not g.get("matcher")), None)
    if target is None:
        target = {"hooks": []}
        groups.append(target)
    for name, timeout, is_async in entries:
        cmd = "~/.claude/hooks/" + name
        if cmd in registered:
            continue
        target.setdefault("hooks", []).append(
            {"type": "command", "command": cmd, "timeout": timeout, "async": is_async})
        added.append(event + ":" + name)

if added:
    with open(SETTINGS, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("  Registered in ~/.claude/settings.json: " + ", ".join(added))
else:
    print("  Hooks already registered in ~/.claude/settings.json")
PYEOF

ln -sf "$ROMP_DIR/claude/romp-postal.mcp.json" "$HOME/.claude/romp-postal.mcp.json"
echo "  Symlinked romp-postal.mcp.json (Romp Postal Service MCP config)"

ln -sf "$ROMP_DIR/claude/skills/romp" "$HOME/.claude/skills/romp"
echo "  Symlinked /romp skill"

if [[ -x "$ROMP_DIR/chat-view/install.sh" ]]; then
    echo "  Installing romp-chat-view extension..."
    "$ROMP_DIR/chat-view/install.sh" || echo "  (romp-chat-view install skipped/failed)"
fi

case ":$PATH:" in
    *":$ROMP_DIR/bin:"*) ;;
    *) echo "  NOTE: add to your shell rc:  export PATH=\"\$PATH:$ROMP_DIR/bin\"" ;;
esac
