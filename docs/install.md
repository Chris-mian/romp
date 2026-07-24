# Install

Romp installs from source with one script. Three things need to be in place
first.

- **[Claude Code](https://docs.claude.com/en/docs/claude-code), signed in.**
  Install it and run `claude` once to log in. Romp runs on your existing Claude
  Code login and adds no account of its own.
- **Python 3.10 or newer.**
- **Node.js.**

On macOS, install Python and Node with [Homebrew](https://brew.sh):

```bash
brew install python node
```

On Ubuntu or Debian:

```bash
sudo apt install python3 nodejs npm
```

## Install

```bash
git clone --depth 1 https://github.com/romp-on/romp.git
cd romp
./install.sh
export PATH="$PATH:$(pwd)/bin"   # add this line to your shell rc
```

`--depth 1` clones only the latest commit, which is a few MB rather than the
whole history; Romp behaves identically. Omit it if you want the full history.

The installer registers Romp with Claude Code (the hooks, the postal service,
the `romp` skills, and the VS Code / Cursor extension) and keeps the kernel
running from login on.
[What it installs, in detail](reference.md#what-the-installer-sets-up).

## First run

The installer starts Romp and keeps it running, so the dashboard is already
live. Run:

```bash
romp launch
```

It opens the dashboard in your browser and prints the link as well: the link
carries the one-time access token. After that first open a cookie remembers you
and plain `http://127.0.0.1:29855/` works. Type a name into the picker and start
a session.

On a remote or headless box `romp launch` won't try to open a browser — it
prints the link plus the two ways to reach it from your laptop (attach the host
from your dashboard, or forward the port over ssh).

<video src="../assets/guide/first-session.mp4" autoplay loop muted playsinline width="100%"></video>

The installer also adds the VS Code / Cursor extension. Reload your editor
window and open Romp from the sidebar.

From here, the [Guide](guide.md) tours the four views and everything Romp does
with your sessions.
