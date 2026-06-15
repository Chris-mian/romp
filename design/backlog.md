# Rebuild backlog: spec vs implemented

A running tab of what the design docs specify against what is actually built, so we
add features incrementally instead of trying to land everything at once. Keep it
current as we build. Status: `[x]` done, `[~]` partial / needs tuning, `[ ]` not
started.

## Layer 1 — event model (`design/event-model.md`)

- [x] Event parser `bin/romp-event-model` (Session → Turn → Atom, author, triggers,
  idle atoms, compaction stitch). 38 tests.
- [ ] rompUuid birth-stamp + `rompUuid → fork-files` registry (launcher writes at
  birth/resume). Powers new-model discovery AND session→files stitching.
- [ ] Headless-with-parity substrate (Agent SDK vs stream-json client) — deferred.

## Layer 2 — judges (`design/judge.md`)

Index tier (always on):
- [x] Captioner (segment + turn captions). Accepted on the fleet.
- [x] Archiver (per-session headline + abstract from captions). Accepted.

Triage tier (on-demand):
- [x] Planner (goal-tree placement + per-node completion + soft-block + settled
  rollup). Built + completion tuning landed (db5d3d5 + rollup top-done rule):
  - [x] Flatten: file steps as SIBLINGS under the goal / a real sub-goal, not chained
    to the latest leaf. (`MAX_DEPTH=2` re-parent + shallow-tree prompt; depth 18→3.)
  - [x] Mark DONE readily, including completing the TOP goal when a segment discharges
    the whole ask. (Prompt: "DON'T BE SHY… DONE the TOP-LEVEL goal".)
  - [x] Settled lock: focus-hold + "a newer top goal minted" as the move-on signal;
    reject complete-on-turn-end (reintroduces flicker). (`settled = nid != focus or
    session_closed`; closed = last turn idle-terminated, NOT turn-end. Completion =
    top node nodeComplete AND settled — confirmed by simplify; whole-subtree dropped,
    0/27 ever reached it. completed 0→10 on the fleet.)
  - [x] Un-block: clear a node's block when later work under the goal progresses
    (newest-wins). (Clears `blocked` on the top-ancestor subtree on later non-block work.)
  - [x] HYBRID completion (positive per-segment + negative turn-end sweep) — SHIPPED
    (1f7ac8d build, default flipped on after A/B). At every end-known turn the sweep
    asks which OPEN top-goals THAT TURN TOUCHED are still OUTSTANDING and completes the
    complement; scoped to the turn's placed-segment top-ancestors (false-positive guard),
    idempotent per turn id, `settled`+`blocked` compose unchanged. Separate toggleable
    pass (`run_sweep`, `NEG_SWEEP` env default-on, `ROMP_NEG_SWEEP=0` to revert);
    `romp-judge --ab-sweep` measures positive-only vs +sweep without mutating state.
    Fleet A/B: 25→30 completed top-goals (+5, a FLOOR — settled defers active-focus
    swept-completes), zero false-positives, calibration confirmed. Premise-shift noted:
    positive-only already ~52%, so the sweep is the precision backstop, not the driver.
    Watch: sweep quality rides on planner placement (a mis-filed segment can sweep the
    wrong goal) — fix is better placement, helps both paths (per simplify).
- [~] Courier (handoffs) — judge side BUILT (1c8dc06): classifies each peer
  (postal) segment propagating/FYI; PROPAGATING plants a top-level goal in the
  RECIPIENT's tree with `origin:{peer,goalId,msgId}`; FYI no goal-edit. The planner
  SKIPS peer segments (`_seg_peer` is the shared discriminator) — no double-place.
  Global oldest-first across sessions; idempotent by msgId. Triage tier (run_courier,
  browser-gated). Dry-verified: 42 peer / 85 planner segs, zero leakage.
  - [ ] Read-side origin wiring: ↪ from <sender> on the feed card (ask.origin /
    AskTreeNode kind:"handoff") + bind the timeline connector to the planted goal.
  - [ ] Sender goals as-of-SEND (MVP reads as-of-now). Live handoffs: as-of-now ≈
    as-of-send (tiny gap). Matters for BACKFILL — when the courier processes OLD
    messages, the sender's tree has since evolved, so as-of-now can pick a goalId
    that didn't exist at send / miss a since-closed one → mis-attribution. Land
    before relying on backfilled handoff attribution (per simplify).
  - [ ] Ack taxonomy: a result returning on a delegated goal → completes that node.
- [ ] Writers: expand-paragraph feed-card detail (TBD, remake). Session digest is
  subsumed by the archiver (done).

Engine:
- [~] Per-session passes via `--once`. The always-on daemon is part of the kernel (L3).

## Layer 3 — read side (`design/read-side.md`)

UI port + parity: the existing tuned `chat-view` UI is ported as the render layer
onto the Python kernel. The curated KEEP / ADAPT / DROP checklist (what to reuse,
rewire, and leave behind against the new data model) lives in `design/ui-parity.md`.

MINIMAL (build first — browser-able): the tuned chat-view UI ported onto the kernel over WS.
- [x] Merged always-on kernel `bin/romp-kernel` (PYTHON — producer + WebSocket/HTTP server in
  one process, single writer; presence-gated producer, no model calls when no browser open).
  Hand-rolled stdlib WS reusing the chat-view `shimJs` VERBATIM — the same protocol the bundles
  + extension speak (no poll bridge). Builds the UI bundles if stale.
- [~] UI = the human's tuned chat-view render bundles, served verbatim (render.js/feed.js +
  styles/feed.css) + the shared obsidian TimelinePanel injected at `/timeline`. Chat, feed, and
  timeline panes all render real data. feed.ts dead-path tidy + `ui/` rename + `romp-events --emit`
  delete deferred (build-beside).
- [x] One view-builder: the kernel's Python projection emits the `{type:"session"/"feed"}` WS
  payloads the bundles consume; bundles only render. (Old reducers exist beside until cutover.)
- [x] Chat pane: atoms→ChatEvent (user / assistant / thinking / tool with output-pairing + diff /
  postal / compaction marker) over WS — the tuned transcript, tabs, rail, ledger.
- [x] Feed pane: RENDERS on real goals. Goals map onto the AskItem/AskTreeNode shape feed.js
  already consumes (goal tree = card tree, status → Working/Blocked/Completed column), with the
  DROP concepts (relevance/liveness/suspects/openQuestions) left empty so the render's
  conditional paths hide them — ZERO edits to the tuned feed code. Literal dead-path code removal
  + segment-nested modal trail = follow-up tidy. `/` now serves the combined chat+feed view.
- [x] Timeline pane: the shared obsidian TimelinePanel served at `/timeline` + as the 3rd pane of
  the combined shell, driven by `build_timeline` over WS (segments-as-bars from the event model,
  caption tooltips, awaiting/compacting stripes from `states/`, usage bars). The view is injected
  verbatim (no fork — same code VS Code/Obsidian use). Later increments: message connectors
  (courier), model/effort pickers + context battery (tmux-only), cross-pane focus/hover.
- [x] TOC ledger: archiver headline + turn captions, click-to-jump (segment nesting pending).
- [x] RUNNABLE: `python3 ~/GitRepos/romp-event-model/bin/romp-kernel` → auto-opens
  http://127.0.0.1:7878 (full path: rebuild bin is off PATH; `cd chat-view && npm install` once
  if UI deps are missing).

INCREMENTAL (add after the three panes show real data):
- [x] **Serve-layer security (do BEFORE serving beyond localhost)**: always-on
  Origin/Host validation on HTTP + `/ws` (kills ClawJacked, CVE-2026-25253);
  `ROMP_SERVE_TOKEN` usable without breaking local clients (auto-inject); token
  REQUIRED beyond `127.0.0.1`; token baked into launch. See `read-side.md`.
  (Done — de58481: Origin/Host gate before routing, SameSite=Strict cookie
  auto-inject, `/healthz` exempt, `ROMP_SERVE_HOST=0.0.0.0` + tokened banner.)
- [x] Browser-presence gating of the triage tier (planner + courier gate on a
  connected WS client `_clients`); INDEX tier (captioner + archiver) is always-on
  for any active tmux session. (The freeze bug was a 90s-since-HTTP timer a
  long-lived WS never refreshed — gate on the real events instead.)
- [~] Liveness: working / blocked / completed — lane badges + chat chip from tmux
  @claude-state (working/waiting=READY/permission=BLOCKED/compacting); chat chip's
  WORKING uses the event-model open-turn (stable) not the laggy @claude-state. Hard
  live-prompt floor merge: TODO.
- [x] Live-state read: lane/chip state, model/effort/context% from tmux; awaiting/
  compacting stripes + usage from `states/`/`usage.json` (file-based).
- [ ] rompUuid birth-stamp discovery (new-model only; 48h window = parse bound only).
- [x] Clear-all + undo (cleared.jsonl, append-only; clear-all = one batch, one undo
  restores the batch; per-card Clear + the footer UndoClear button).

Read-side parity hardening (2026-06-15, the user's live review):
- [x] Hard liveness filter: feed/timeline/chat show only tmux-alive sessions
  (dead-session tabs/lanes/cards gone); living sessions shown fully.
- [x] Shared tab↔timeline order (session-order.json drag-sync, tabOrder push).
- [x] Recency colormap on feed cards (age → hawaii ramp), stream cards visible.
- [x] Timeline message connectors from the postal log (both-ends-alive).
- [x] Resizable panes (thin sashes); timeline auto-fits its lanes (drag can't exceed).
- [x] Work-timer ms fix; chat richness (postal sender color, reminders fold, tool
  desc, bigger IO); tab × hides the tab (reversible, not a kill).
- [ ] Remaining chat richness: image thumbnails (path: refs), postal parked badge + mid.
- [ ] Re-judging progress surface.
- [ ] Timeline connectors (needs the courier) + focus/hover overlays.
- [ ] Tags: `dir → tag` map + per-session override; views via URL hash + gear default
  + timeline-bottom selector.
- [ ] Comms scope: directory groups, group-wide, alive-gated edges + config allowlist
  + approval prompt.
- [x] `romp --on` superseded: `romp on` → `romp-manager up`; the kernel is supervised
  by romp-manager, auto-started at login by `bin/romp-service` (launchd/systemd) which
  `install.sh` installs. romp-serve repointed to the Python kernel on the manager's
  port 7433. Port is env-configurable (`ROMP_SERVE_PORT`/`ROMP_KERNEL_PORT`); a
  per-machine port config FILE is an optional nicety, not built.
- [ ] VS Code extension: keep working as a thin WS client (protocol stable).
- [ ] Remote kernels + postal federation (read-federation deferred).
- [ ] Hard data isolation via a separate `ROMP_STATE` root (manual).

## Clean break (`design/read-side.md`)

- [x] New stores only (`captions/` `archive/` `goals/`); no reads of old
  `summaries/` `requests/` `decision-log` `corrections/` `digest/`. Honored by the
  index tier; enforce in kernel discovery.

## Open questions (revisit)

- [ ] Live permission-prompt CONTENT may live only in tmux, not the transcript (chip
  state is safe from `states/`).
- [ ] Settled gate exact definition — being locked at the planner checkpoint.
- [ ] Read-federation across machines.
- [ ] Where the comms-approval prompt surfaces + how the alive-gated edge is stored.
