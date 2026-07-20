# Reference

This page lists every command and knob. Everything here runs on the machine
that hosts the kernel.

## The `romp` command

| Command | What it does |
|---|---|
| `romp <name>` | Start or re-attach the terminal (tmux-backend) session `<name>` |
| `romp -d` / `-f` / `-j` | Terminal views: dashboard, feed mirror, judge monitor |
| `romp --on` / `--status` | Start the kernel manager / report its status |
| `romp --refresh` | Restart the kernels (fleet-wide; running sessions reconnect) |
| `romp --mail …` | The postal service from the shell (below) |
| `romp update [host]` | Push this machine's committed romp to an attached remote kernel and restart it |
| `romp --version` | Version report across the moving parts |

## Mail from the shell

```bash
romp --mail send [--kind delegate|coordinate|question] <name> "<text>"
romp --mail inbox                 # read your messages
romp --mail agents                # who is live, their branch and working-note
romp --mail working "<note>"      # publish what this session is working on
```

## Mail inside a session (MCP tools)

| Tool | What it does |
|---|---|
| `send_message(to, body, kind)` | Message a live session by name; `kind` declares delegate / coordinate / question |
| `check_inbox()` | Read messages sent to you (also delivered at the end of each turn) |
| `list_agents()` | The live fleet, each with its branch and working-note |
| `set_working(text)` | Publish what you hold so peers steer clear |
| `check_sent()` | Whether your sent messages were read yet |
| `recall_message(to, id?)` | Unsend a message the recipient hasn't read |

## Session backends

Sessions run on one of two backends, chosen per session:

- **Agent SDK (the default).** The kernel drives the session through the
  Claude Agent SDK. Sessions started from the dashboard use this; it is the
  most robust path, with native pickers, queued sends, and model switching.
- **tmux.** A regular Claude Code terminal session running inside tmux. Romp
  reads the same transcript, and delivers messages and nudges by injecting
  text into the terminal. Injection is inherently less robust than the SDK,
  but it lets Romp ride along with the terminal Claude Code you already use:
  run `romp <name>` and the session shows up on the dashboard like any other.

## What the installer sets up

`install.sh` registers the Claude Code hooks, the postal MCP config, and the
`romp` skills; builds the editor extension; and installs a login service that
keeps the kernel up. It is idempotent: re-running adds only what is missing,
and it never touches hooks you registered yourself.

It installs nothing into your Python. The kernel and CLI are standard library
only; the one dependency of the [SDK backend](#session-backends)
(`claude-agent-sdk`) lives in a dedicated venv under `~/.local/state/romp/`,
built against the newest Python 3.10+ on the machine and rebuilt
automatically when that Python changes.

## Configuration

### Folder click, in your terminal or editor

The chat statusline shows the session's working directory; clicking it opens
that folder. The default is the OS opener (`open` / `xdg-open`). To open it
elsewhere, set a command via the env var `ROMP_OPEN_FOLDER` or the first
non-comment line of `~/.config/romp/open-folder`; `{dir}` is replaced with
the clicked path (omitted, the path is appended). The command runs on the
kernel's machine.

```bash
# ~/.config/romp/open-folder: pick one line
open -a Ghostty {dir}               # macOS: a new Ghostty window there
ghostty --working-directory={dir}   # Linux: Ghostty
code {dir}                          # VS Code instead
```

### Install-time switches

- `ROMP_NO_SERVICE=1 ./install.sh` skips the login service.
- `ROMP_NO_EXT=1 ./install.sh` skips the VS Code / Cursor extension.
- `ROMP_NO_SDK=1 ./install.sh` skips the SDK backend's venv (tmux sessions
  still work).

## Where things live

State is written under `${XDG_STATE_HOME:-~/.local/state}/romp/`. Transcripts
are read in place from where Claude Code writes them (`~/.claude/projects/`)
and never copied.

## Kill switches

`touch` to disable, `rm` to re-enable, effective immediately:

- `~/.claude/romp-summarize-off`: the live tmux activity phrase
- `~/.claude/romp-postal-off`: the postal service
