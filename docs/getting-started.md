# Getting started

## Requirements

- macOS or Linux
- [Claude Code](https://docs.claude.com/en/docs/claude-code): the `claude` CLI
- Python 3.10+ and Node.js. macOS: `brew install python node`. Linux: your
  distro's packages ([uv](https://docs.astral.sh/uv/) also works for Python:
  `uv python install 3.13`). The kernel is a Python process; its supervisor
  runs on Node.
- [tmux](https://github.com/tmux/tmux), only if you want terminal sessions
  (the [tmux backend](reference.md#session-backends))

`install.sh` checks for these up front and names anything missing, with the
command to fix it.

## Install

```bash
git clone https://github.com/romp-on/romp.git
cd romp
./install.sh
export PATH="$PATH:$(pwd)/bin"   # add this line to your shell rc
```

`install.sh` is idempotent. It registers the Claude Code hooks, the postal
MCP config, and the `romp` skills; builds the editor extension; and installs a
login service that keeps the kernel up (`ROMP_NO_SERVICE=1` opts out).

It installs nothing into your Python. The kernel and CLI are standard library
only; the one dependency of the [SDK backend](reference.md#session-backends)
(`claude-agent-sdk`) lives in a dedicated venv under
`~/.local/state/romp/`, built against the newest Python 3.10+ on the machine
and rebuilt automatically when that Python changes.

## Your first session

![Opening the dashboard, naming a session, and creating it](assets/guide/first-session.gif){ width="100%" }

1. Open `http://127.0.0.1:7433/` in any browser.
2. Type a name into the session picker and choose **New session**.
3. Give the agent some work in the chat.
4. Open the **feed**. Within a few turns a task card appears, tracking what
   the agent is doing and what needs you.

That card is Romp at work: [Task management](guide/tasks.md) explains
what it tracks, and [The fleet at a glance](guide/the-fleet.md) tours the
views around it.
