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
         romp-postal-revive.sh tmux-status.sh; do
    ln -sf "$ROMP_DIR/hooks/$h" "$HOME/.claude/hooks/$h"
done
echo "  Symlinked romp hooks into ~/.claude/hooks/"

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
