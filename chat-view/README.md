# romp Chat View

A read-only, nicely-rendered, **live** view of Claude Code (romp) sessions inside
VS Code / Cursor — styled to look like the official Claude Code panel, but for
*any* session (including ones running in a terminal / romp), which the official
panel can't drive.

It renders the session transcript JSONL straight off disk and tails it live, so
the panel updates as the terminal session advances. You drive chat elsewhere
(e.g. romp postal mail); this is purely the nice viewer.

## How it works

- A Claude Code session is one append-only JSONL file at
  `~/.claude/projects/<munged-cwd>/<session-id>.jsonl`.
- `src/transcript.ts` (extension host) parses it: walks the **active path**
  (`last-prompt.leafUuid` → root, so rewound/orphaned branches are skipped),
  folds each `tool_result` into its `tool_use`, and emits a flat event list.
- `src/webview/render.ts` + `styles.css` (webview) render those events. Base
  colors/fonts come from VS Code theme variables; the accents (green rail dot,
  warm code tones) match the shipped Claude Code CSS.
- The extension host `fs.watch`es the file and re-sends on every append.

Thinking text is only stored in plaintext for small models; the big reasoning
models store a signature-only block, so those render as a `Thinking…` placeholder.

## Develop

```sh
npm install
npm run build      # or: npm run watch
```

Then open this folder in VS Code/Cursor and press **F5** (Run romp Chat View).
In the dev host, run the command **“romp Chat: Open Session Viewer”** and pick a
session.

## Roadmap

- Shared core extracted so an Obsidian view + the `romp -g` browser page reuse it.
- Syntax highlighting + math (KaTeX) — trivial in the Obsidian host (built in).
- Byte-offset tailing instead of full re-read for large transcripts.
