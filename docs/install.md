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

Open a new terminal afterwards, so `~/romp/bin` is on your `PATH` and the `romp`
command works. To update later, run the same command again.

This clones Romp to `~/romp` and installs the newest release.
[What it installs, in detail](architecture.md#what-the-installer-sets-up).

### Manual and custom installs

Install this way to keep Romp somewhere other than `~/romp`, or to run the
latest commit rather than the newest release:

```bash
git clone https://github.com/romp-on/romp.git ~/romp
cd ~/romp
git checkout "$(git tag -l 'v*' --sort=-v:refname | head -n1)"   # newest release
# or:   git checkout main                                        # the latest commit
./install.sh
```

Then add `bin/` to your `PATH` in your shell rc; `install.sh` prints the exact
line for your clone.

```bash
export PATH="$PATH:$HOME/romp/bin"
```

## First run

The installer ends by printing your dashboard link, with an access token in it.
Open that link and Romp is running. There is nothing to start by hand.

It is already up because the installer also adds a login service, which holds
the kernel's supervisor open from the moment you sign in to the machine. The
supervisor runs the kernel, and the kernel mints the token the link carries. So
the back end starts before you open anything, and it comes back on its own after
a reboot.

The first visit trades that token for a year-long cookie, so
`http://127.0.0.1:29855/` works on its own from then on. To print the link again
for a new browser or after clearing cookies:

```bash
romp url
```

Running `romp` on its own does the same and opens a browser with it, which is
the everyday way in.

### In VS Code or Cursor

The installer adds the extension automatically. Reload your editor window and
open Romp from the sidebar.

### Start a session

<video src="../assets/guide/first-session.mp4" controls loop muted playsinline preload="none" data-romp-autoplay width="100%"></video>

### If the dashboard does not answer

Four things account for nearly every case:

- **You updated the code.** Restart the kernels so they pick it up: `romp
  refresh`.
- **The back end is not running.** `romp status` says whether it is, and
  `bin/romp-service install` puts the login service back if it went missing.
- **You installed with `ROMP_NO_SERVICE=1`.** Then there is no login service by
  design; `romp up` holds the back end open in a terminal for as long as you
  leave it running.
- **The machine has no browser**, being a server you reach over ssh. Print the
  link with `romp url` and forward the port (`ssh -L 29855:127.0.0.1:29855
  <host>`), or attach the machine to a kernel you already use and drive it from
  there; see [Linking kernels on other
  machines](guide.md#linking-kernels-on-other-machines).
