# romp feed — three-column rebuild, v2 (spec for vs_chat)

REVISION (2026-06-09, supersedes v1): the user reviewed the first three-column cut
and corrected the design. ONE view, THREE columns, NO navigation buttons, and
the columns merge asks with standalone completions. Underlying model:
`~/.local/state/romp/REQUESTS.md`.

## The view — one screen, three columns, nothing else

| 1 · ASKS | 2 · NEEDS INPUT | 3 · COMPLETED |
|---|---|---|
| Open asks in flight: asked, not finished, nothing pending from the user. Purpose: external memory — "I already asked this; it exists." | Things waiting on the user. The obvious column. | Things that finished. Could be a whole ask, or something granular/unexpected the user never explicitly asked for. |

**Column routing (derived, read-time):**
- An **ask card** lives in exactly one column by its newest link:
  newest link DECISION → NEEDS INPUT · newest link DONE → COMPLETED ·
  otherwise (no links, or DETAILS) → ASKS.
- A **standalone deliverable card** (granular/unexpected work): a user-origin
  reply that is NOT linked to any ask — DECISION-tagged → NEEDS INPUT,
  DONE-tagged → COMPLETED. Linked replies never get their own card (they live
  inside their ask's subgraph). Agent-internal and routine (details) turns
  never appear at all.
- Cards MOVE between columns as links arrive. Nothing accumulates as stale rows.

**An ask card accumulates its subgraph.** Conceptually: stuff keeps happening
on the timeline that belongs to this ask; the registry's links/parents edges
ARE that subgraph, and the card collects it dynamically — the tally on the
card, the linked-work list on expand. (Same data a future timeline tree-view
will draw; the card is the list rendering of it.)

**Chrome that is GONE — remove, don't hide:**
- The asks/deliverables view toggle (one view now).
- The dismissed toggle button.
- done/decision/details chips, the internal chip, every per-card tag badge.
  The relevance tag now has ZERO user-facing presence anywhere. It remains on
  disk as internal plumbing only — it is literally what routes the columns
  above and gates paragraph generation. Never render the words.
- Header becomes just: title + "N need input" (the actionable count) + live
  count. Nothing clickable.

**Clear** is the only per-card act (every card, all three columns; most useful
on COMPLETED). It appends `{id,t}` to `requests/cleared.jsonl` via the existing
`askClear` message — works for BOTH card kinds (ask ids and reply ids share the
file; the host filters both). No auto-clear.

**Responsive**: stack the three columns (same headers) when narrow; never let
words break mid-word.

## Card anatomy (unchanged from v1)

```
│ ASK or DELIVERABLE TEXT (bold, wraps)            17m ago │  row 1
│ session_name · 2 done · 1 needs you      [+]  [Clear]    │  row 2
│ ╰─ expand: linked work, newest first                     │
```
- Ask card title = the user's ask text. Standalone card title = the deliverable
  phrase. Never a summarizer description of a turn as an ask headline.
- Expand on an ask = the linked-work subgraph. Expand on a standalone
  deliverable = the existing ask/response detail (paragraph when present).
- Whole-card click → showOnTimeline (ask: turnId/created; standalone: itemId).
  Name click → openSession. Buttons stopPropagation. Keyed incremental
  reconcile (no hover flicker).
- Recency tint on card background as today.

## Data (host side — feed_design owns; ALREADY WIRED for v2)

Every feed push carries:
- `asks: AskItem[]` — `{itemId, sid, name, color, text, t, created, live,
  done, needsYou, linked[{did,relevance,t,reply_id}], turnId, trgb}`.
  Column = newest link: `linked[0]?.relevance` (DECISION→input, DONE→completed,
  else ASKS).
- `items: FeedItem[]` — now each carries `inAsk: boolean` (this reply is linked
  to some ask). Standalone cards = `origin==="user" && !inAsk &&
  (relevance==="DONE"||relevance==="DECISION")`. Cleared reply-ids are already
  filtered out host-side.
- Clear: `postMessage({type:"askClear", itemId})` for either card kind.

Need payload changes? Ask feed_design — don't fork the fold.

## Process

Installs always-clear; shared tree. You own feed.ts/feed.css; feed_design owns
the extension.ts feed block. Shout via postal when shipped.
