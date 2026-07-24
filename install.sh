#!/usr/bin/env bash
# Install romp onto this machine:
#   - symlink the Claude Code hooks into ~/.claude/hooks/
#   - symlink the MCP config (Romp Postal Service) into ~/.claude/
#   - symlink the romp + romp-postal skills into ~/.claude/skills/
#   - build + install the romp-chat-view VS Code extension
#
# bin/ is NOT symlinked anywhere — add it to PATH in your shell rc:
#   export PATH="$PATH:<this repo>/bin"
set -euo pipefail
ROMP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Preflight — name anything missing up front, with the exact remedy, instead
# of failing later at runtime. We deliberately do NOT auto-install system
# packages (surprising, and the right package manager varies); we check and
# tell. ROMP_SKIP_PREFLIGHT=1 bypasses; ROMP_NODE overrides the node binary.
if [[ -z "${ROMP_SKIP_PREFLIGHT:-}" ]]; then
    preflight_missing=0
    if ! command -v "${ROMP_NODE:-node}" >/dev/null 2>&1; then
        echo "install.sh: Node.js not found — the kernel manager runs on it." >&2
        echo "  macOS:  brew install node    Linux: your distro's nodejs package" >&2
        preflight_missing=1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        echo "install.sh: python3 not found — the kernel is a Python process." >&2
        echo "  macOS:  brew install python@3.13    or:  uv python install 3.13" >&2
        preflight_missing=1
    fi
    [[ "$preflight_missing" -eq 0 ]] || exit 1
fi

mkdir -p "$HOME/.claude/hooks" "$HOME/.claude/skills"

for h in romp-summarize.sh romp-postal-drain.sh romp-postal-ensure.sh \
         romp-postal-revive.sh romp-postal-context.sh romp-wake.sh tmux-status.sh; do
    ln -sf "$ROMP_DIR/hooks/$h" "$HOME/.claude/hooks/$h"
done
echo "  Symlinked romp hooks into ~/.claude/hooks/"

# Install the git pre-push identifier hook. Symlinked into the SHARED git hooks
# dir (git rev-parse --git-common-dir), so it fires from every worktree; the hook
# self-locates the tree being pushed. ROMP_GITHOOK_DIR overrides the target (the
# test harness points it at a temp dir so it never touches a real .git). Skipped
# with ROMP_NO_GITHOOK, or when this isn't a git checkout (e.g. a tarball).
if [[ -z "${ROMP_NO_GITHOOK:-}" && -f "$ROMP_DIR/.githooks/pre-push" ]]; then
    githook_dir="${ROMP_GITHOOK_DIR:-}"
    if [[ -z "$githook_dir" ]]; then
        common="$(git -C "$ROMP_DIR" rev-parse --git-common-dir 2>/dev/null || true)"
        if [[ -n "$common" ]]; then
            case "$common" in /*) ;; *) common="$ROMP_DIR/$common" ;; esac
            githook_dir="$common/hooks"
        fi
    fi
    if [[ -n "$githook_dir" ]]; then
        mkdir -p "$githook_dir"
        ln -sf "$ROMP_DIR/.githooks/pre-push" "$githook_dir/pre-push"
        echo "  Installed the git pre-push identifier hook"
    fi
fi

# Register the hooks in ~/.claude/settings.json so Claude Code actually fires
# them. Idempotent merge: adds only missing romp entries, never touches any
# other hooks you have registered.
python3 - <<'PYEOF'
import json, os

SETTINGS = os.path.expanduser("~/.claude/settings.json")
WANT = {  # event -> [(hook script, timeout secs, async)]
    "SessionStart":     [("tmux-status.sh", 5, False),
                         ("romp-postal-ensure.sh", 5, True),
                         ("romp-postal-revive.sh", 8, False),
                         ("romp-postal-context.sh", 5, False)],  # romp sessions: load the romp-postal skill
    "UserPromptSubmit": [("tmux-status.sh", 5, False),
                         ("romp-summarize.sh", 10, True),
                         ("romp-wake.sh", 5, True)],     # poke the kernel → judges run NOW, not on the 20s tick
    "PostToolUse":      [("tmux-status.sh", 5, False)],
    "Stop":             [("tmux-status.sh", 5, False),
                         ("romp-summarize.sh", 10, True),
                         ("romp-postal-drain.sh", 10, False),
                         ("romp-wake.sh", 5, True)],     # turn ended → wake the producer immediately

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

ln -sf "$ROMP_DIR/claude/romp-session-prompt.md" "$HOME/.claude/romp-session-prompt.md"
echo "  Symlinked romp-session-prompt.md (working-style append-system-prompt)"

# -n: the skill links point at DIRECTORIES — on a re-run, plain -sf would follow the existing
# dir-symlink and drop a NEW link INSIDE the repo (claude/skills/romp/romp → an absolute personal
# path, which the no-personal-identifiers test rightly rejects). -n replaces the link itself.
ln -sfn "$ROMP_DIR/claude/skills/romp" "$HOME/.claude/skills/romp"
ln -sfn "$ROMP_DIR/claude/skills/romp-postal" "$HOME/.claude/skills/romp-postal"
echo "  Symlinked romp + romp-postal skills"

# The Agent SDK venv — romp's non-tmux backend. Best-effort: a host without python >= 3.10 still
# works fully for tmux sessions (romp-sdk-setup says what to install). Opt out with ROMP_NO_SDK=1.
if [[ -z "${ROMP_NO_SDK:-}" && -x "$ROMP_DIR/bin/romp-sdk-setup" ]]; then
    "$ROMP_DIR/bin/romp-sdk-setup" || echo "  (SDK backend not provisioned — tmux sessions unaffected)"
fi

if [[ -z "${ROMP_NO_EXT:-}" && -x "$ROMP_DIR/vscode-extension/install.sh" ]]; then
    echo "  Installing romp-chat-view extension..."
    "$ROMP_DIR/vscode-extension/install.sh" || echo "  (romp-chat-view install skipped/failed)"
fi

# Auto-start: install the login service so the kernel supervisor (romp-manager) is
# always up — you never run `romp --on`; open the browser and you can even start
# sessions FROM it. launchd on macOS, systemd --user on Linux. Opt out with
# ROMP_NO_SERVICE=1; remove later with `romp-service uninstall`.
if [[ -z "${ROMP_NO_SERVICE:-}" ]]; then
    # ROMP_SERVICE_BIN overrides the binary (tests stub it); defaults to the repo copy.
    _svc="${ROMP_SERVICE_BIN:-$ROMP_DIR/bin/romp-service}"
    if [[ -x "$_svc" ]]; then
        # Don't tear down a HEALTHY manager just to ship a webview dist/VSIX change. `romp-service
        # install` boots the running romp-manager OUT (SIGTERM, drains every kernel) then re-bootstraps;
        # a bootstrap that loses the drain-race exits 1 and leaves the dashboard dead on :29855. A routine
        # webview deploy needs NO manager restart (the kernel serves the rebuilt dist live), so skip the
        # whole bootout when the manager already reports `running`. Only (re)install when it is NOT
        # running — and then FAIL LOUDLY on a non-zero exit rather than `|| echo`-swallowing it, so a
        # webview deploy can never silently leave the manager unloaded (the user's rescue_me, 2026-07-21).
        if "$_svc" status 2>/dev/null | grep -qx running; then
            echo "  romp-manager already running — leaving it up (a webview deploy needs no restart)"
        else
            echo "  Installing the romp login service (romp-manager)..."
            if ! "$_svc" install; then
                echo "install.sh: romp-service install FAILED — romp-manager is NOT running; the dashboard will be dead on :29855." >&2
                echo "  Retry by hand:  $_svc install" >&2
                exit 1
            fi
        fi
    fi
fi

case ":$PATH:" in
    *":$ROMP_DIR/bin:"*) ;;
    *) echo "  NOTE: add to your shell rc:  export PATH=\"\$PATH:$ROMP_DIR/bin\"" ;;
esac

# ROMPHOME — where a bare `romp` launches when you'd otherwise be in $HOME.
# $HOME is a bad cwd: its direct children include the macOS TCC-protected
# Downloads/Desktop/Documents, so Claude indexing them triggers a stream of
# spurious file-access prompts. romp defaults ROMPHOME to this install dir
# ($ROMP_DIR) automatically; export it in your shell rc to point elsewhere.
echo "  romp launches in ROMPHOME (default: $ROMP_DIR), never \$HOME."
echo "  Override:  export ROMPHOME=\"/path/you/prefer\""
