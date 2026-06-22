# Architecture

romp is one always-on **kernel** (a single Python process, single writer) that
reads each session's Claude Code transcript, builds an event tree, runs the
**judges** that write the durable records, and serves the three panes — chat,
feed, and timeline — over HTTP + WebSocket.

```text
transcripts (~/.claude/projects/)
        │  read in place, never copied
        ▼
   event model  ──►  judges (captioner · archiver · planner · courier)
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

The design documents live in the repository's `design/` directory:

- **`event-model.md`** — the bottom-layer event tree built from each transcript.
- **`judge.md`** — the captioner, archiver, planner, and courier.
- **`read-side.md`** — the kernel and the three panes.
- **`ui-parity.md`** — the UI port.
- **`backlog.md`** — spec-vs-built.

!!! note "Publishing the design docs"
    These are currently developer-facing notes kept in the repo. To publish them
    on this site, move (or symlink) them under `docs/` and add them to `nav` in
    `mkdocs.yml`.
