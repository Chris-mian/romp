# The romp web kernel and the SessionBackend seam

*2026-06-11 · companion to `docs/design.md` (the intent layer). That document
covers the records and views; this one covers where the system RUNS: the
standalone web kernel (`romp-serve`), the backend abstraction that makes
tmux+Claude-Code one pluggable substrate among several, and what was made
portable so a packaged romp works without the author's dotfiles.*

## 1. The layering

romp was already a file-based system: transcripts in `~/.claude/projects/` are
the source of truth, the small records under `~/.local/state/romp/` are the
derived state, and every view is a read-time projection of those files. What
was NOT separable before this refactor was the host: the chat/feed UI could
only run inside VS Code, because the extension host was the one process that
read the files, drove tmux, and fed the webviews over a private postMessage
pipe.

The refactor names each layer and gives it a home:

```
┌─ views ─────────────────────────────────────────────────────────────┐
│ browser tab (romp-serve)  ·  VS Code panel (extension)  ·  terminal │
│ feeds (romp -f/-l/-p)  ·  Obsidian timeline                         │
└──────────────────────────────▲──────────────────────────────────────┘
                  the UI protocol (postMessage message types)
┌──────────────────────────────┴──────────────────────────────────────┐
│ KERNEL — chat-view/src/kernel/, served by bin/romp-serve            │
│   server.ts   HTTP + WebSocket bridge, message routing              │
│   chat.ts     session mirroring, status chips, live-ask driving     │
│   feed.ts     the feed/ask fold (port of the Python read side)      │
│   state.ts    record-file readers/writers                           │
├──────────────────── SessionBackend (backend.ts) ────────────────────┤
│ tmux-backend.ts            │ headless-backend.ts                    │
│ tmux sessions tagged @romp │ `claude -p` turns, registry files      │
│ send-keys / capture-pane   │ no TUI; tui = null                     │
└─────────────────────────────────────────────────────────────────────┘
┌─ records ───────────────────────────────────────────────────────────┐
│ ~/.claude/projects (transcripts) · ~/.local/state/romp (the rest)   │
└─────────────────────────────────────────────────────────────────────┘
```

Two prior observations made this cheap. First, the webview bundles
(`src/webview/render.ts`, `feed.ts` — ~3,400 lines) were already pure
browser code whose only host contact is `acquireVsCodeApi().postMessage`; a
~40-line shim that backs postMessage with a WebSocket runs them unchanged in
any browser. Second, the record files were already the interop layer, so the
kernel needed no new storage — it reads and writes exactly the files the
extension did.

## 2. romp-serve

`bin/romp-serve [--port N] [--host H] [--backend tmux|headless]` builds (if
stale) and runs `chat-view/dist/kernel.js`:

- `GET /` — the chat page: the same `render.js` bundle VS Code loads, plus
  the shim and a Dark+ default block for the `--vscode-*` CSS variables VS
  Code would otherwise inject.
- `GET /feed` — the feed page (`feed.js`), same treatment.
- `WS /ws?app=chat|feed` — the postMessage bridge. Message types and
  semantics are IDENTICAL to `extension.ts` in both directions (`update`,
  `status`, `askLive`, `ledger`, … down; `sendMessage`, `answerAsk`,
  `askClear`, … up). The protocol is the contract; anything that speaks it is
  a romp UI host.
- `GET /healthz` — `{ok, sessions, clients}`.

Defaults are deliberately safe: binds `127.0.0.1` with no auth required. For
anything wider set `ROMP_SERVE_TOKEN` (or `--token`): every route then
requires the token — open `/?token=…` once and a cookie carries it for the
static assets and the WebSocket. Combine with an SSH tunnel or tailscale for
remote use. Webview UI state (the extension's `workspaceState`)
lives in `~/.local/state/romp/web-kernel.json`; per-page bits (ledger
collapsed) use localStorage via the shim's getState/setState.

Where the extension used a native VS Code surface, the kernel substitutes the
safe default rather than a dialog: closing a tab never offers to end the
session; a dead session opens read-only instead of prompting to revive; a
rail-dot click that matches several feed cards opens the first;
`openFile` shells out to `cursor -g` / `code -g` (override:
`ROMP_SERVE_OPEN_CMD="cmd {file}:{line}"`). The resume-picker QuickPick
(`answerPicker`) is not yet supported in the web UI.

The extension is untouched and fully functional; it and the kernel can run at
the same time (they read the same files and both drive tmux idempotently).
The intended end-state is for the extension host to shrink to a thin client
of the same kernel, deleting the ~2,000 duplicated lines — deferred until the
kernel has seen real daily use.

## 3. The SessionBackend seam

`src/kernel/backend.ts` defines the substrate contract. The semantic surface
(what the rest of romp is allowed to need):

```ts
liveSessions(): Map<name, {state, effort, model, ctx, since, summary}>
send(name, text) · interrupt(name) · markIdle(name, notAfter)
spawn(name, cwd) · resume(name, id, cwd?) · rename(old, new) · kill(name)
tui: { capturePane, sendKeys, sendLiteral } | null      // TUI-only extras
```

Design rules learned porting the tmux host:

- **The seam is semantic, not mechanical.** Most tmux hacks (send-keys,
  capture-pane picker scraping, the `@claude-state` vars) exist to synthesize
  semantics that a non-TUI backend gets natively. The interface names the
  semantics; each backend supplies its own mechanics.
- **TUI capabilities are optional, feature-checked via `tui`.** A backend
  without them simply has no live picker mirroring — pending asks then only
  surface via the transcript/feed, never wrongly auto-answered.
- **An empty `liveSessions()` map means "probe unreliable", not "all dead".**
  Callers must not mass-close anything on it (inherited from the extension's
  hard-won tmux behavior).
- **Durable state is files; substrate vars are display.** The hooks now write
  `states/<sid>.jsonl` on BOTH paths and tmux vars only when in tmux (§5), so
  a backend never needs to fake another backend's display layer.

### The tmux backend

A direct port of the extension's mechanics: `@romp`-tagged sessions, state
from the hook-maintained tmux user options, paste-buffer + Enter for send,
Esc + guarded `markIdle` for interrupt (Claude Code fires no hook on Esc),
`romp --detach` / `romp <name> --resume <id> --detach` for spawn/resume.

### The headless backend

Sessions on headless Claude Code (`claude -p`, the engine the Agent SDK
drives) — no tmux anywhere. Because headless Claude writes the same
transcript format to `~/.claude/projects/`, the ENTIRE pipeline (romp-events,
summarizer, feed, timeline) works on these sessions unchanged. Mechanics:

- A session is a registry file `~/.local/state/romp/headless/<name>.json` =
  `{name, sid, lastSid, dir, alive}` plus the standard `names/<sid>` identity
  record.
- `spawn` mints the anchor sid (same trick as `bin/romp`'s self-assigned
  `--session-id`); the FIRST turn claims it with `--session-id`, so the
  identity record matches the transcript filename.
- `send` runs one turn: `claude -p <text> --output-format json --name <name>
  [--resume <lastSid>]`, with `ROMP_SESSION_ID`/`ROMP_SESSION_NAME` exported
  for the hooks' headless path. A resume forks a new transcript uuid (exactly
  like interactive resume); the result JSON's `session_id` becomes the next
  resume target, and `--name` keeps the customTitle stable so romp-events'
  fork-join finds every transcript. One turn at a time per session.
- working/waiting transitions are appended to `states/<sid>.jsonl` by the
  backend itself (deduped by last-state, so the hook path coexisting is
  harmless). `interrupt` SIGINTs the in-flight turn.

## 4. Tests — what pins what

| Suite | Pins |
|---|---|
| `tests/test_romp_events_golden.py` + `tests/fixtures/events-golden/` | the romp-events extractor contract: boundary kinds, stable ids, peer gating, banner stripping, idle-gap clipping, active-path anchors. A golden diff IS a contract change — review it and bump `CACHE_VERSION`. Regen: `--regen`. |
| `chat-view` `npm test` → `src/*.test.ts` | the pure modules every host shares: transcript parser (incremental == one-shot, rewinds, compaction stitch, queue/todo folds), askparse (all three picker screens), postal-spec (join markers, timeline index, all-or-nothing hydration). |
| `src/kernel/backend-contract.test.ts` | the SessionBackend shape for both backends + headless behavior end-to-end against a mocked `claude` binary and isolated `XDG_STATE_HOME`. |
| `tests/tmux-status-hook.bats` (incl. headless cases) | the hook's event→state map, and that the headless path writes the durable record while touching tmux not at all. |
| `tests/test_romp_{read,pipeline}_side.py` (pre-existing) | the fold semantics the kernel's `feed.ts` ports. The TS port re-derives from the same record files; if the two ever disagree, the Python suite is the spec. |

Known gap: `feed.ts` (the TS fold) has no direct twin-test against the Python
fold; it is a line-faithful port of `extension.ts`, which has been the live
implementation for the feed panel. A shared-fixture parity test
(records dir in → ask columns out, run through both) is the natural next
hardening step.

## 5. Portability (no dotfiles required)

Previously the author's `dotfiles/tmux/tmux.conf` carried glue romp silently
required. `bin/romp` now self-provisions all of it on a stock tmux:

- **Server glue, installed once per launch and only when absent** (a user's
  own config always wins): the `after-rename-session` →`romp _renamed` hook,
  `session-closed`/`client-session-changed` → postal prune/mail-clear, and
  the pass-through `C-c`/`Escape` root bindings → `romp-interrupt-reset`.
  All paths resolve from the romp checkout itself, never `~/GitRepos/...`.
- **Session-scoped display decorations** (`tmux set -t <session>` — non-romp
  sessions untouched): titles with the `@romp-emoji` dot, the status line
  with the live summary, and the `status-format[1]` postal-peers row.

The hooks gained a headless membership path: a session with no tmux but
`ROMP_SESSION_ID` in its env writes the durable records (`states/`,
summarizer ensure) and skips every display write. Plain non-romp Claude
sessions still exit instantly on both paths.

The terminal/ghostty display surface is thus exactly one DisplayAdapter among
several, fed by the same records; absent tmux, nothing else degrades.

## 6. Done since first draft / still deferred

Done: token auth (`ROMP_SERVE_TOKEN`/`--token` — pages take `?token=` once
and set a cookie for static+WS), identity colors for headless sessions (same
palette + first-unused rule as bin/romp), and the TS↔Python fold parity tests
(`src/kernel/fold-parity.test.ts` — answered crossoff, ACTION survival,
leaf-path completion, clear/resurrect, follow-up reopen, child-ask nesting,
amend).

Still deferred:

- Extension host → thin client of the kernel (delete the duplicated host).
  Until then the kernel and the extension are two independent hosts over the
  same records; they run fine simultaneously (verified live), but host-logic
  changes must land in both.
- `answerPicker` (resume-picker QuickPick) in the web UI.
- End-session confirmation in the web UI (close-tab is always tab-only today).
