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
- [~] Planner (goal-tree placement + per-node completion + soft-block + settled
  rollup). Built; needs completion tuning (agreed at the checkpoint, queued):
  - [ ] Flatten: file steps as SIBLINGS under the goal / a real sub-goal, not chained
    to the latest leaf.
  - [ ] Mark DONE readily, including completing the TOP goal when a segment discharges
    the whole ask.
  - [ ] Settled lock: focus-hold + "a newer top goal minted" as the move-on signal;
    reject complete-on-turn-end (reintroduces flicker).
  - [ ] Un-block: clear a node's block when later work under the goal progresses
    (newest-wins).
- [ ] Courier (handoffs: propagating / FYI + sender goal; plants a goal in the
  recipient's tree). Needs global cross-session time-order.
- [ ] Writers: expand-paragraph feed-card detail (TBD, remake). Session digest is
  subsumed by the archiver (done).

Engine:
- [~] Per-session passes via `--once`. The always-on daemon is part of the kernel (L3).

## Layer 3 — read side (`design/read-side.md`)

MINIMAL (build first — browser-able):
- [x] Merged always-on kernel `bin/romp-kernel` (PYTHON — producer + server co-located in
  one process, single writer; presence-gated producer thread, no model calls when no
  browser open). HTTP + polling; WS push deferred (the JSON payload shapes are the contract).
- [~] `ui/` package: built fresh `ui/index.html` (thin render client) served by the kernel.
  Deferred (build-beside, old stays): rename/retire `chat-view/`, fold `obsidian/` timeline,
  delete `romp-events --emit`.
- [x] One view-builder: the kernel's Python projection (`view_feed`/`view_chat`/`view_timeline`)
  IS the single view-builder; `ui/` only renders payloads. (Old `feed.ts`/`bin/romp-feed`/
  `chat.ts` parser/`romp-events --emit` still exist beside until cutover.)
- [x] Chat pane: event tree rendered directly from the parser (no second parser).
- [x] Feed pane: inbox (`goals/` → working/blocked/completed columns) + caption stream.
- [x] Timeline pane: segments-as-bars + idle gaps + caption-on-hover.
- [x] TOC ledger: archiver headline + turn/segment captions, clickable to jump.
- [x] RUNNABLE: `python3 ~/GitRepos/romp-event-model/bin/romp-kernel` → auto-opens
  http://127.0.0.1:7878 (the rebuild bin is off the human's PATH, so run it by full path).

INCREMENTAL (add after the three panes show real data):
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
