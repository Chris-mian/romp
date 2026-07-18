# Getting started

## Requirements

- macOS or Linux
- [Claude Code](https://docs.claude.com/en/docs/claude-code): the `claude` CLI
- Python 3.10+ (the kernel picks the newest `python3.x` it can find; a
  [uv](https://docs.astral.sh/uv/)-managed one in `~/.local/bin` counts)
- Node.js (the kernel manager runs on it)
- [tmux](https://github.com/tmux/tmux), only if you want terminal sessions
  (the [tmux backend](reference.md#session-backends))

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

## Your first session

1. Open `http://127.0.0.1:7433/` in any browser.
2. Type a name into the session picker and choose **New session**.
3. Give the agent some work in the chat.
4. Open the **feed**. Within a few turns a task card appears, tracking what
   the agent is doing and what needs you.

That card is Romp at work: [Task management](guide/tasks.md) explains
what it tracks, and [The fleet at a glance](guide/the-fleet.md) tours the
views around it.
