# Architecture

romp is one always-on **kernel** (a single Python process, single writer) that
reads each session's Claude Code transcript, builds an event tree, runs the
**judges** that write the durable records, and serves the four panes (chat,
feed, fleet, and timeline) over HTTP + WebSocket.

```text
transcripts (~/.claude/projects/)
        │  read in place, never copied
        ▼
   event model  ──►  judges (captioner, archiver, planner, … — see Judges)
        │                     │
        │                     ▼
        │              durable records (captions · archive · goal tree)
        ▼                     │
   kernel  ◄───────────────────┘
        │  HTTP + WebSocket on 127.0.0.1:7433
        ▼
   panes: chat · feed · fleet · timeline   (browser, VS Code/Cursor, or Obsidian)
```

## Deep dives

The judge layer is documented on this site:

- [Judges](judges.md) — the full roster: who each judge is and when it runs.
- [The judge pipeline](judge-pipeline.md) — the one-page diagram map.
- [How a card gets its state](goal-state.md) — the state model, chip by chip.

So are the architecture/schema deep dives:

- [The event model](event-model.md) — the bottom-layer event tree built from each transcript.
- [The read side](read-side.md) — the kernel and the panes.
- [The SDK session backend](sdk-backend.md) — the Agent SDK (non-tmux) session backend.

Design docs for work that has since shipped (kept as history, with the why):
the repository's `plans/` directory — e.g. `segment-regrowth.md` (the
settle-time segment seam) and `stalled-open-todos-nudge.md` (the
stalled-with-open-to-dos nudge).
