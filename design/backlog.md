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

UI port + parity: the existing tuned `chat-view` UI is ported as the render layer
onto the Python kernel. The curated KEEP / ADAPT / DROP checklist (what to reuse,
rewire, and leave behind against the new data model) lives in `design/ui-parity.md`.

MINIMAL (build first — browser-able): the tuned chat-view UI ported onto the kernel over WS.
- [x] Merged always-on kernel `bin/romp-kernel` (PYTHON — producer + WebSocket/HTTP server in
  one process, single writer; presence-gated producer, no model calls when no browser open).
  Hand-rolled stdlib WS reusing the chat-view `shimJs` VERBATIM — the same protocol the bundles
  + extension speak (no poll bridge). Builds the UI bundles if stale.
- [~] UI = the human's tuned chat-view render bundles, served verbatim (render.js/feed.js +
  styles/feed.css). Chat ported; feed.ts goal-tree surgery + obsidian timeline fold pending.
  `ui/` rename + `romp-events --emit` delete deferred (build-beside).
- [x] One view-builder: the kernel's Python projection emits the `{type:"session"/"feed"}` WS
  payloads the bundles consume; bundles only render. (Old reducers exist beside until cutover.)
- [x] Chat pane: atoms→ChatEvent (user / assistant / thinking / tool with output-pairing + diff /
  postal / compaction marker) over WS — the tuned transcript, tabs, rail, ledger.
- [~] Feed pane: goals→cards bucketed BLOCKED/WORKING/COMPLETED + caption stream payload built;
  feed.ts render surgery (DROP relevance/liveness/suspect per ui-parity.md, ADAPT to goal tree)
  pending.
- [ ] Timeline pane: obsidian timeline port (segments-as-bars, event-based idle gaps) pending.
- [x] TOC ledger: archiver headline + turn captions, click-to-jump (segment nesting pending).
- [x] RUNNABLE: `python3 ~/GitRepos/romp-event-model/bin/romp-kernel` → auto-opens
  http://127.0.0.1:7878 (full path: rebuild bin is off PATH; `cd chat-view && npm install` once
  if UI deps are missing).

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
