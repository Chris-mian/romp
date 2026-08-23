# claude/ — what romp ships into Claude Code

The Claude-side configuration romp installs for its sessions (symlinked into
place by `install.sh`):

- **`romp-session-prompt.md`** — the extra system-prompt content every
  romp-managed session gets: plain done/not-done reporting the judges can read,
  plus the housekeeping note that pre-explains romp's artifacts (`[romp]`
  notices, `<!-- romp-* -->` comments) as bookkeeping to ignore.
- **`romp-postal.mcp.json`** — registers the postal MCP server
  (`postal/postal_service.py`, via the `romp-postal-service` command on PATH).
- **`skills/romp-postal/`** — the full postal-service guide, loaded on demand
  (sessions get only a compact pointer at start — see
  `hooks/romp-postal-context.sh`).
- **`skills/manager/`** — the manager workflow: one session dispatching work to
  a group of worker sessions (roster = a session group, uniform worker color,
  dispatch/track/verify/report norms). Loaded on demand.

Skills live in this repo (not `~/.claude/skills/` directly) so a skill and the
tool it documents change in the same commit; the installer creates the
symlinks.
