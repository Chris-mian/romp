# romp knowledge cache — search guide

The distilled, durable record of what every romp agent (Claude Code session) has
done. To answer "what was related to X?", an LLM reads the hierarchy below.
Everything joins on a stable **event id** `<sessionId>:<turnStartEpoch>:<sha1>`.

## Layout
- `names/<sid>` — session identity, tab-separated: `name <TAB> dir <TAB> bgColor <TAB> fgColor`.
  Maps a session id to its human name + working directory.
- `summaries/<sid>.jsonl` — one JSON line per turn (requests and replies). A reply line:
  ```json
  {"id":"<sid>:<t>:<hash>","t":<written>,"kind":"reply","text":"<=8-word phrase","relevance":"DONE|DECISION|DETAILS"}
  ```
  Per-turn ground truth: what each turn accomplished + its relevance tag. This is the
  stable spine — written once, never revised (unlike the romp-events event list, which
  re-derives and folds).
- `digest/<sid>.json` — a rolling per-SESSION rollup: `{summary, bullets:[{text,t}]}`.
  The session-level "what is this agent about" entrypoint.
- `feed-detail/<id>.json` — a fuller JLD paragraph, DONE/DECISION turns only:
  `{"id","t","paragraph","next_steps?","relevance"}`.

## How to search "what was related to X?"
1. Scan `digest/*.json` (coarse, session-level) to find which sessions touched X.
2. For those sessions, read `summaries/<sid>.jsonl` (fine, per-turn) for the specific deliverables.
3. Pull `feed-detail/<id>.json` for the full context on a specific DONE/DECISION turn.
Join by `id`; resolve a session id to its name/dir via `names/<sid>`.
