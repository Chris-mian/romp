# Install

## Requirements

- **[Claude Code](https://docs.claude.com/en/docs/claude-code), signed in.**
  Install it and run `claude` once in a terminal to log in.
- **Python 3.10 or newer, and Node.js.**

    ```bash
    brew install python node               # macOS (Homebrew)
    sudo apt install python3 nodejs npm    # Ubuntu / Debian
    ```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/romp-on/romp/main/bootstrap.sh | bash
```

This clones Romp to `~/romp`, checks out the newest release, runs the
installer, and adds `bin/` to your shell rc. Open a new terminal afterwards so
the `romp` command is on your `PATH`. To update later, run it again; it moves
you to the newest release.

### Installing by hand

If you would rather read the script first, or already have a clone:

```bash
git clone https://github.com/romp-on/romp.git ~/romp
cd ~/romp
git checkout "$(git tag -l 'v*' --sort=-v:refname | head -n1)"   # newest release
./install.sh
```

Then add `bin/` to your `PATH` in your shell rc; `install.sh` prints the exact
line for your clone.

```bash
export PATH="$PATH:$HOME/romp/bin"
```

[What it installs, in detail](architecture.md#what-the-installer-sets-up).

## First run

The installer starts Romp and keeps it running, so the dashboard is already
live. Open it in a browser or in your editor.

### In a browser

```bash
romp launch
```

This opens the dashboard and prints the same link. The link carries an access
token, which the kernel requires on every request. The first open trades the
token for a cookie, so plain `http://127.0.0.1:7433/` works from then on.

On a remote machine, `romp launch` prints the link rather than opening a
browser, along with the two ways to reach it from your laptop: attach the host
from your dashboard, or forward the port over ssh.

### In VS Code or Cursor

The installer adds the extension. Reload your editor window and open Romp from
the sidebar.

### Start a session

<video src="../assets/guide/first-session.mp4" controls autoplay loop muted playsinline width="100%"></video>
