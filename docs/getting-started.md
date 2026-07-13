# Getting started

## Requirements

- macOS or Linux
- [Claude Code](https://docs.claude.com/en/docs/claude-code) — the `claude` CLI
- Python 3.10+ for the Agent SDK backend (the default) — the kernel picks the
  newest `python3.x` it can find (a [uv](https://docs.astral.sh/uv/)-managed one
  in `~/.local/bin` counts), so an older system `python3` alongside is fine. The
  `bin/` tools are pure standard library — no third-party deps beyond the
  SDK venv `install.sh` builds.
- [tmux](https://github.com/tmux/tmux) — only for terminal sessions (the tmux
  backend); sessions started from the dashboard don't need it
- Node.js — only if you want the VS Code / Cursor extension

## Install

```bash
git clone https://github.com/romp-on/romp.git
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

## First run

1. Open `http://127.0.0.1:7433/` in any browser — no VS Code required. The
   login service keeps the kernel up.
2. Start a session: type a name in the dashboard's session picker and choose
   **New session**, or run `romp <name>` in a terminal for a tmux session.
3. Give the agent work in the chat, then open the **feed**: a task card
   appears, tracking what the agent is doing, what is done, and what needs
   you.
4. Add more sessions. The **fleet** view lists each one with its open tasks,
   and the **timeline** lays them out over time and shows where they
   interact.

## Remote hosts (federation)

One dashboard can show sessions from **other machines**, grouped by host —
`gpu1:mysession` tabs and timeline lanes next to your local ones, with
cross-machine messaging between sessions. Setup is the same install, then one
click:

1. On the remote machine: clone romp and run `./install.sh`
   (`ROMP_NO_EXT=1` skips the editor extension on a headless box). Make sure
   you can `ssh <host>` to it non-interactively (an entry in `~/.ssh/config`).
2. In your dashboard: open the network icon (top bar) and attach the host.

That's it. The attach fetches the remote kernel's token over ssh, opens the
tunnels (dashboard→kernel and remote-sessions→your postal bus), and **starts
the remote kernel if it isn't running** — a host that has never run romp
lights up on the first attach. If romp isn't installed there at all, the
popover says so and names the command to run.

The kernel is found on the remote's `PATH` or in conventional clone spots
(`~/GitRepos/romp`, `~/romp`, `~/code/romp`, `~/src/romp`).

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
