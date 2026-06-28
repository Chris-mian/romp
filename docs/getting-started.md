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

## Configuration

### Folder click → open in your terminal/editor

The chat statusline shows the session's working directory (`📁 <folder>`). Click
it to open that folder. By default romp uses the OS opener — `open` on macOS
(Finder), `xdg-open` on Linux — since that's the only portable "open this"
command. To open it somewhere else (your terminal, an editor), set a command via
either the env var `ROMP_OPEN_FOLDER` or the first non-comment line of
`~/.config/romp/open-folder`. A `{dir}` placeholder is replaced with the clicked
path; if you omit it, the path is appended as the last argument. The command runs
on the **kernel's** machine (where the sessions run).

```bash
# ~/.config/romp/open-folder  — pick ONE line
open -a Ghostty {dir}               # macOS: a new Ghostty window in that folder
open -a iTerm {dir}                 # macOS: iTerm
ghostty --working-directory={dir}   # Linux: Ghostty
code {dir}                          # open the folder in VS Code instead
```

There is no portable OS API for "the default terminal" (macOS has no
folder→terminal handler), so this explicit command is the reliable knob.
