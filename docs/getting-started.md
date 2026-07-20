# Getting started

## Before you install

Romp runs on macOS or Linux and needs three things installed:

- [Claude Code](https://docs.claude.com/en/docs/claude-code): the `claude` CLI
- Python 3.10+ and Node.js: `brew install python node` on macOS, or your
  distro's packages on Linux

## Install

```bash
git clone https://github.com/romp-on/romp.git
cd romp
./install.sh
export PATH="$PATH:$(pwd)/bin"   # add this line to your shell rc
```

The installer names anything missing, with the command to fix it. It wires
Romp into Claude Code and keeps the kernel running from login on;
[what it sets up, exactly](reference.md#what-the-installer-sets-up) is in the
Reference, along with the switches to skip pieces.

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
