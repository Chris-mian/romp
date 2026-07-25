# cli/ — terminal tools

Python implementations of the terminal-facing romp commands. Run them via
their `bin/` symlinks (`romp -f`, `romp -j`, `romp --version`, `romp --update`)
— see `bin/README.md` for the command surface.

| File | Command | What it is |
|---|---|---|
| `feed.py` | `romp -f` | Terminal mirror of the feed. Deliberately does NOT import the kernel/judge: it re-reads the same raw stores from scratch as an independent cross-check. |
| `judge_monitor.py` | `romp -j` | Terminal health view of the judges. |
| `version.py` | `romp --version` | Version report across the moving parts (working tree vs running kernel vs built bundles). |
| `update.py` | `romp --update [host]` | Pushes this machine's committed romp to attached remote kernels over ssh and restarts them. |
| `idle_dots.py` | (hook-fired) | tmux backend only: heals stranded `working` state by inspecting tmux panes. Fired from `hooks/tmux-status.sh`. |
