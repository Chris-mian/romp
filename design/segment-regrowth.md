# Segment regrowth: post-close pivot work is invisible to the planner

Status: PROPOSED (the user 2026-07-02). Nothing here is built; the cite-miss warn chip
(judge `_node_warn`, the yellow card chip) shipped separately and only makes the *symptom*
visible — this doc is about the cause.

## The incident shape (synthetic)

A session gets one prompt: "fix A, B, and C." It works 30 minutes, finishes all three,
merges, pushes, cleans up its worktree — genuinely done, and the closer rightly marks the
goal complete. Then, without any new user message, the agent pivots in the SAME turn to a
different thread it remembered from before a compaction (or from a peer message, a to-do
backlog, momentum rules) and works another 20 minutes.

What the user sees on the feed: a card in Completed, and the session's status dot WORKING.
It reads exactly like "the judge marked this complete while it's still working" — a false
done-mark — even though the done-mark was right. The pivot work has NO card at all, and never
gets one: when the next user prompt eventually arrives, the planner's prompt-run plans THAT
segment, and the 20 minutes of pivot work end up either attributed to the next prompt's goal
or lost entirely.

## How the system is designed today

- The event model slices a session into TURNS (user prompt → idle), and turns into
  SEGMENTS. A turn triggered by one prompt is ONE segment; the segment id embeds the
  trigger's timestamp + text hash (`fsid:t:texthash`), so the id is STABLE while the
  segment grows — an open turn's segment at minute 3 and at minute 50 have the same id.
  (Injected retries and command wrappers do not open new segments.)
- The planner is IDEMPOTENT PER SEGMENT: `apply_plan` records `placements[seg_id]` (and
  `seg_id#p` for the prompt-run), and a placed segment is never re-planned. This is a load-
  bearing design choice — it is what makes judge passes cheap and re-entrant, and it is why
  a re-run never double-mints goals.
- The closer may close mid-turn (it reads the live segment and the agent's own completion
  declaration — "suites green, merging"). That is correct and desirable: waiting for turn-end
  would hold every finished card hostage to whatever the agent does next.
- The feed has a placeholder for the OPPOSITE gap (`_provisional_card`: a session working a
  brand-new ask the planner hasn't classified yet). Its drop-gate is the PLACEMENT event —
  `_seg_placed(placements, held_seg)` → no placeholder. That gate is exactly why it cannot
  cover a pivot: the pivot happens inside a segment that was placed half an hour ago, so
  the placeholder is suppressed by design, and nothing ever *plans* the pivot slice either.

The combination: one prompt = one segment = one planning decision, made early. Everything
the agent does inside that segment afterward — including a pivot to unrelated work after its
goal closed — is structurally invisible to the planner. This is an EVENT-model blind spot,
not a judge-prompt problem: no prompt change can fix "the text was never shown to a judge."

## Where it goes wrong (the precise event)

The unhandled event is:

> a top goal SETTLES (closer done / settledDone stamped) while its newest trail segment is
> still OPEN and the session keeps producing work in it.

Everything after the settle point inside that segment is unplanned text. Note the symmetry
with the distiller: the distiller reads the same trail, so a summary distilled at settle
time also never sees post-settle text (fine — the goal was done), and the kernel's fallback
anchor scans the same atoms (also fine once the citation is reliable). The PLANNER is the
only judge with an obligation to the post-settle tail, and it is the one that never returns.

## Proposed fix: a settle-time segment split (virtual boundary)

Introduce a derived boundary in the event model: when a top goal settles, record the settle
point (`closedTurns` already carries the close; add the atom uuid/timestamp of the last atom
the closer saw — call it the SEAM). If the segment then grows past the seam by any assistant
work (not just trailing tool results), `em.segments` emits the tail as a NEW segment:
`fsid:t2:texthash2` where t2/texthash2 come from the first post-seam atom. The planner sees
an unplaced segment and does what it always does — plans it: usually minting a fresh top
("pivoted to: …"), occasionally re-opening the old goal if the work is actually a
continuation (its existing judgment, unchanged).

### Trigger semantics (the user 2026-07-02)

The seam fires when the goal that OWNS the open segment settles — not when "any" goal
finishes (an unrelated card's completion would split a segment whose work is still properly
owned → noise seams) and not when "all" goals finish (other cards sitting open elsewhere
would mask the incident case entirely). Ownership is already recorded: `placements[seg_id]`
names the node the segment was filed under; its top ancestor is the owner. The orphaning
event is exactly that top's settle while its segment is still open and growing. It composes:
if the planned tail's new top later settles mid-turn too, that ownership expiry is a fresh
seam — each seam mints a new segment id, so placement idempotency never bends.

The seam keys on the CLOSER's settle event ONLY — never on the user's Clear. Clear is the
one human-asserted fact ("stop showing me this"); if clearing a still-working card split its
segment and re-minted a card for the continuing work, romp would override the dismissal
moments after it was made. A cleared-but-working goal behaves exactly as today: the work
continues invisibly under the cleared card, and if it later genuinely needs the user, the
existing resurrection path (`reopened`) brings it back.

Why this shape:

- It is EXACT and event-based (repo design rule): the boundary is "the closer's settle
  event," not a timer, a size threshold, or a similarity heuristic.
- Placement idempotency is untouched — we never re-plan a placed segment; we mint a new one.
  All the drift-safety machinery (`_seg_key` timestamp-invariance) applies as-is.
- The closer keeps its freedom to close mid-turn; closing early no longer costs visibility.
- The feed's provisional placeholder nearly covers the gap for free: the unplaced tail is
  exactly what `_provisional_card` was built for ("working a segment the planner hasn't
  classified"), so the user sees "Working…" next to the Completed card even before the
  planner's next pass. One allowance needed: the tail segment has no human trigger, so the
  `_seg_human` gate must admit a seam-born segment (it exists only because real post-settle
  work exists, so the "only a real ask warrants a placeholder" rationale still holds).

Cost / risk:

- `em.segments` gains a dependency on the goal store (the seam) — today segmentation is
  pure transcript. Mitigation: pass seams IN as an argument (the judge and kernel both
  already load the store before segmenting), keeping the event model itself store-free;
  callers that pass nothing get today's behavior.
- A settle followed by 30 seconds of wrap-up chatter would mint a noise segment. Gate the
  split on the tail containing REAL work (any tool-use atom or a substantive prose atom),
  which is an event condition, not a time window.

## Alternatives considered

1. **Re-plan a grown segment (drop idempotency for open segments).** Let the planner
   re-visit `placements[seg_id]` while the segment's turn is open, diffing for new text.
   Rejected: it breaks the one invariant that keeps passes cheap and re-entrant, needs
   dedup of every op kind (not just placement), and re-judges the same early text every
   pass for the whole life of a long turn.
2. **Closer refuses to close while the turn is open.** Rejected: it trades a visibility gap
   for a truth gap — finished work would sit "working" for arbitrarily long (the incident's
   goal was genuinely done 20 minutes before the turn ended), and it contradicts the design
   memory that completion should key on the completion event, not turn shape.
3. **Working-state floor instead of planning: keep the top's status WORKING while its
   session works in its trail segment.** Cheapest to build, but it lies in the other
   direction — the pivot work is NOT that goal's work, and the card would read "still
   working on A/B/C" forever while the agent does D. It also still never gives D a card.
4. **To-do-list authority (plan-sync) as the catch-all.** When the agent maintains a to-do
   list, the authoritative tier already mints/holds goals per item, and a pivot with a
   fresh to-do would surface. Real but partial: sessions that pivot WITHOUT declaring a
   to-do item (the incident case) stay invisible; keep plan-sync as a complement, not the
   fix.

Recommendation: the settle-time seam (proposed fix), with alternative 4 kept as-is. If the
seam proves noisy in practice, tighten the real-work gate before reaching for heuristics.

## Test sketch

- event-model: a fixture turn whose goal settles mid-turn, with post-seam tool-use → two
  segments; without post-seam work → one segment (no noise mint).
- judge: run_plan over the regrown fixture → the tail is planned exactly once (a new top or
  a reopen), placements gain the new seg id, the settled top keeps settledDone.
- kernel: build_feed on "completed top + unplaced regrown tail" → provisional Working card
  alongside the Completed card.
