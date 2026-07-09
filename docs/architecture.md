# Architecture

romp is one always-on **kernel** (a single Python process, single writer) that
reads each session's Claude Code transcript, builds an event tree, runs the
**judges** that write the durable records, and serves the three panes — chat,
feed, and timeline — over HTTP + WebSocket.

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
   panes: chat · feed · timeline   (browser, VS Code/Cursor, or Obsidian)
```

## Deep dives

The judge layer is documented on this site:

- [Judges](judges.md) — the full roster: who each judge is and when it runs.
- [The judge pipeline](judge-pipeline.md) — the one-page diagram map.
- [How a card gets its state](goal-state.md) — the state model, chip by chip.

The remaining design documents live in the repository's `design/` directory:

- **`event-model.md`** — the bottom-layer event tree built from each transcript.
- **`read-side.md`** — the kernel and the three panes.
- **`sdk-backend.md`** — the Agent SDK (non-tmux) session backend.
- **`segment-regrowth.md`** — the settle-time segment seam.
- **`stalled-open-todos-nudge.md`** — the stalled-with-open-to-dos nudge.
