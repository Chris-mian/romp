# Getting started

## Requirements

- macOS or Linux
- [tmux](https://github.com/tmux/tmux)
- Python 3.11+ (the `bin/` tools are pure standard library — no third-party deps)
- [Claude Code](https://docs.claude.com/en/docs/claude-code) — the `claude` CLI
- Node.js — only if you want the VS Code / Cursor extension

## Install

```bash
git clone https://github.com/OWNER/romp.git   # ← your repo
cd romp
./install.sh
export PATH="$PATH:$(pwd)/bin"   # add this line to your shell rc
```

`install.sh` is idempotent. It:

- symlinks the Claude Code hooks into `~/.claude/hooks/` and registers them in
  `~/.claude/settings.json` (only adding missing romp entries — it never touches
  your other hooks);
- symlinks the postal-service MCP config and the `romp` / `romp-postal` skills;
- builds and installs the VS Code / Cursor extension;
- installs a login service so the kernel manager is always up (opt out with
  `ROMP_NO_SERVICE=1`).

!!! tip "First run"
    Open `http://127.0.0.1:7433/` in any browser — no VS Code required. From
    there you can watch the fleet and even start sessions.

## Where things live

State is written under `${XDG_STATE_HOME:-~/.local/state}/romp/`. Transcripts are
read in place from where Claude Code already writes them
(`~/.claude/projects/`) and are never copied elsewhere.

!!! warning "Kill switches"
    `touch` to disable, `rm` to re-enable — effective immediately:

    - `~/.claude/romp-summarize-off` — the live tmux activity phrase
    - `~/.claude/romp-postal-off` — the postal service
