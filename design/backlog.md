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

MINIMAL (build first — browser-able):
- [ ] Merged always-on kernel: L1+L2 producer running continuously + HTTP/WS server.
  Single writer.
- [ ] `ui/` package (rename `chat-view/` → `ui/`; fold the timeline in from
  `obsidian/`; delete `romp-events --emit`).
- [ ] One view-builder (replaces `feed.ts` + `bin/romp-feed` + `chat.ts`'s parser +
  `romp-events --emit`).
- [ ] Chat pane: render the event tree directly (no second parser).
- [ ] Feed pane: inbox (`goals/` → working / blocked / completed columns) + caption
  stream.
- [ ] Timeline pane: segments-as-bars + idle gaps + caption labels.
- [ ] TOC ledger: archiver headline + turn/segment captions, clickable to jump.
- [ ] RUNNABLE by the human: a clear start command + browser URL.

INCREMENTAL (add after the three panes show real data):
- [ ] **Serve-layer security (do BEFORE serving beyond localhost)**: always-on
  Origin/Host validation on HTTP + `/ws` (kills ClawJacked, CVE-2026-25253);
  `ROMP_SERVE_TOKEN` usable without breaking local clients (auto-inject); token
  REQUIRED beyond `127.0.0.1`; token baked into launch. See `read-side.md`.
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
