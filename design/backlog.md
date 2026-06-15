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
- [ ] Courier (handoffs: propagating / FYI + sender goal; plants a goal in the
  recipient's tree). Needs global cross-session time-order.
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
- [ ] Browser-presence gating of the triage tier; run-when-disconnected setting.
- [ ] Liveness: working / blocked / completed; hard-block floor from live state
  (merge: hard OR soft, hard wins).
- [ ] Live-state read (`states/` + open turns) for the chip + timeline stripes.
- [ ] rompUuid birth-stamp discovery (new-model only; 48h window = parse bound only).
- [ ] Clear-all + undo.
- [ ] Re-judging progress surface.
- [ ] Timeline connectors (needs the courier) + focus/hover overlays.
- [ ] Tags: `dir → tag` map + per-session override; views via URL hash + gear default
  + timeline-bottom selector.
- [ ] Comms scope: directory groups, group-wide, alive-gated edges + config allowlist
  + approval prompt.
- [ ] Remove `romp --on`; per-machine port config.
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
