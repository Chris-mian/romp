# romp feed — three-column rebuild, v2 (spec for vs_chat)

REVISION (2026-06-09, supersedes v1): the user reviewed the first three-column cut
and corrected the design. ONE view, THREE columns, NO navigation buttons, and
the columns merge asks with standalone completions. Underlying model:
`~/.local/state/romp/REQUESTS.md`.

REVISION (2026-06-11, the user's card-taxonomy rulings — supersedes the names and
two card types below):
- Columns renamed: ASKS → **WORKING**, NEEDS INPUT → **BLOCKED** (blocked = the
  user is the blocker; waiting on an external event is NOT blocked — it stays in
  WORKING). COMPLETED unchanged.
- **Every card is an ask.** Every typed prompt mints one-or-more asks, amends an
  open one, or answers a pending question (closed classification, enforced
  write-side with a deterministic backstop — see REQUESTS.md). A card is never
  retired except by the user's Clear.
- **Blocked sessions are not their own cards**: a live permission/picker block
  files the ask card the session is blocked ON under BLOCKED (host joins the
  blocked turn to its card via mint/amend turn ids + linked events; ⏸ badge on
  the card opens the session). The old synthetic blocked-session card survives
  ONLY as an **error flag**: it renders when no card claims the blocked turn —
  which the every-prompt-mints rule forbids — wearing a ⚠ "unattributed" badge
  whose modal explains the registry miss and what a correction needs. It is not
  a supported steady-state card type; its presence = a capture/link bug to file
  (benign exception: the claiming card was cleared moments earlier).
- **Standalone deliverable cards** are expected to wither: with capture unable
  to silently mint nothing, user-prompted work always has an ask to live under.
  The code path remains as a safety net while that's verified, then dies.
- **Exception loop (2026-06-11)**: the legend's "?" opens a help overlay laying
  out the user's three buckets — routine (no marker), teaching clicks (colored
  rings; ordinary actions double as training data), and ⚠ exceptions (amber;
  each is a bug worth reporting). Every card modal carries a "⚠ Report an
  exception" box (category dropdown + free text) that appends to
  `requests/reports.jsonl` with a snapshot of the card's computed state —
  labeled failure examples for prompt rework. A deterministic missed-handoff
  sweep (req-decision REQ=no followed by the recipient's orphan work within
  45 min) attaches ⚠ "handoff?" suspects to the sender's most plausible card,
  with the evidence shown above the report box.
- **Ring simplification (2026-06-11 evening)**: rings exist ONLY in COMPLETED.
  Every Completed card is judged-done (stamped by the reply model or a
  correction), auto-filed (settled detector), or both. Both = the expected
  state = NO ring (quiet when healthy). Green = auto-filed only (verify, then
  Clear confirms / Follow up denies — each click is a labeled example). Blue =
  judged only (not settled yet; glance first). The old gold "still moving" ring
  was the complement of blue and is gone; the old dashed-orange stalled ring is
  now an amber ⚠ stalled badge (exception bucket, report-capable). The brief
  generator is the AUDITOR: it runs only on needs-user items (~30/day vs ~470
  per-turn calls), uses BRIEF_MODEL (Opus), and its NEEDED=no demotes.
- **AUTO-FILING is ON** (validated by the user's green-ring sweep, 2026-06-11,
  zero false positives): a settled card (no turn claimed on it, no open
  handoffs, no open follow-up) never sits in WORKING — it files to COMPLETED
  with its green ring kept (`autoFiled`), marking the verify-before-Clear set.
  New work touching the card pulls it back automatically. WORKING now means
  literally that: a turn is running on it, a handoff is pending, or a handoff
  stalled (dashed ring — needs a re-kick). Known accepted leak until the WAIT
  tag exists: work waiting on an external event auto-files as completed.

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
