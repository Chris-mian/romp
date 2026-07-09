# The judges — a field guide

> The picture first: [judge-pipeline.md](judge-pipeline.md) is the one-page
> diagram map (when each judge runs, card-first filing, the state machine,
> the postal flow). This page is the per-judge detail behind it.

Current as of **2026-07-08**. One judge per distinct system prompt, one name
per judge: what each one is, when it fires, what it reads and writes. The
state model (the diary, the fold, every chip) lives in
[goal-state.md](goal-state.md). Prompts are named by their constant in
`bin/romp-judge` (grep the constant; line numbers drift).

## The roster

Twelve judges, eleven prompts (the consolidator reuses the grouper's).
Usage and error logs attribute one name per prompt (2026-07-08; rows
before that date carry the family names). The timeline band keeps five
family rows and folds the fine names onto them (`_JUDGE_FAMILY`,
`bin/romp-kernel`): gister onto captioner, opener and placer onto
planner, briefer onto distiller, consolidator onto grouper.

| Judge | Tier | Prompt | Fires when |
|---|---|---|---|
| captioner | index (Haiku) | `CAPTION_SYS` | a segment or turn's work ends |
| gister | index (Haiku) | `GIST_SYS` | a user message lands |
| archiver | index (Haiku) | `ARCHIVE_SYS` | a session gains a turn |
| opener | triage (Sonnet) | `OPENER_SYS` | a message lands, work still running |
| planner | triage | `PLAN_SYS` | a segment's work ends |
| placer | triage | `PLACE_SYS` | the planner filed under a card with open sub-goals |
| grouper | triage | `GROUP_SYS` | the set of open cards changed |
| consolidator | triage | `GROUP_SYS` (shared) | the set of completed cards changed |
| closer | triage | `CLOSER_SYS` | a turn ends |
| distiller | triage | `DISTILL_SYS` | a card completed and settled |
| briefer | triage | `BLOCK_BRIEF_SYS` | a card blocked |
| courier | triage | `COURIER_SYS` | a peer message arrives |

Both tiers run continuously from the kernel producer, event-gated, so an
idle fleet costs file stats, not model calls. The index tier (`run_index`)
maintains the durable text record; the triage tier (`run_triage`, one
ordered unit: planner, closer, courier, propagate, grouper, consolidator,
distiller + briefer) maintains the live goal board. Every call goes through
one entrypoint, `_judge_run(..., judge=<name>)`: an isolated `claude -p`
subprocess with a hard timeout, rate-window gating, and per-call cost
logging.

## The index tier

**captioner.** The readable activity log: per finished segment or turn,
one short past-tense phrase (~4-7 words) that leads with the result and
never names a tool. An empty reply means "no finished work", skip. Appends
to `captions/<fsid>.jsonl`; feeds the chat, the feed cards, the timeline.

**gister.** The captioner's sibling for a request still in progress: a
present-tense topic phrase ("a dark-mode toggle for settings"), not a
result. Feeds the "Analyzing:" placeholder card and the timeline dot the
moment a message lands.

**archiver.** Per-session headline + abstract, re-run when the session
gains a turn. Reads the session's turn captions oldest-first; replies
exactly two lines, `HEADLINE:` and `ABSTRACT:`. Written to
`archive/<fsid>.json`; feeds the chat TOC and the search index.

## The planners

**opener.** Fires the moment your message lands on a still-open
segment, so the board shows the ask before the work exists. Exactly one op,
and it must place: mint a new card or file under an open one, card level
only, never done/block. A reply that never parses is logged and the ask is
hard-placed anyway; a prompted goal never stays unplaced.

**planner.** Fires when a segment's work ends; the full op list: `mint`,
`sub`, `done` (eager: an answer counts as done, but ending by asking you to
approve is a block), `block` (only the human blocks; peer/CI/build waits
stay working), `retitle`, `skip`. Its verdicts append diary events; the
same engine, mode-switched by note injections, handles four more phases:
live re-plan after you clear a card mid-work, nudge resolution (resolve the
named goal, done or block, no plain step), delegation follow-on (files the
recipient's work under the courier's plant), and tagged follow-ups (file
under the cited goal unless the reply starts a different thread). A segment
opened by an untargeted kernel notice (restart/resume) carries a
housekeeping note: pure resume/verification sweeps file nothing
(2026-07-08).

**Card-first filing** (2026-07-08). The open-goal menu renders as an
indented tree grouped under top-level cards, and a `sub` names the card,
never a nested line; the test is "can this card be called done without this
work?", judged where you actually experience the board. This replaced the
clear-time auto-split, whose promptUuid provenance was unreliable (messages
and deliverables are many-to-many). Clear is a dumb sweep again.

**placer.** The second, scoped call: only when the chosen card already has
open sub-goals, it sees just that card's subtree and picks the spot, biased
to the highest level that makes sense. Most cards have no open sub-goals,
so most placements stay one call; the prompt/live phases always stay card
level. Any failure attaches at the card and logs to `judge-errors.jsonl`.

The planners never reorganize the board; that is the grouper's job, and the
prompt says so.

## The board keepers

**grouper.** Given the open top-level cards: nest one under another, or
mint an umbrella when several serve one outcome, and "doing nothing is a
valid, common outcome". Ops move whole subtrees; it appends no diary events
(structure, never status). Called only when the open-top set actually
changed. Hard rules in `apply_group`: never touch a view-cleared card, no
cycles, depth clamp 4, same-session only. A to-do-mirror top (planted flat
by plan-sync) is explicitly the grouper's to nest. (The old
never-move-a-once-done-node rule was removed 2026-07-06; the `everDone`
flag itself was retired 2026-07-08, once-done history now lives in the
diary's done events.)

**consolidator.** The same prompt over the completed column: groups related
all-completed sibling tops under a done umbrella, gated by its own
signature, logged under its own name.

**closer.** The turn-end completion backstop; it exists because agents
rarely narrate "done". Audits only the goals the turn actually touched;
verdict done, blocked, or omit, with "when in doubt, omit". Idempotent per
turn. Its diary events carry src `closer`, so planner and closer verdicts
stay distinguishable. Both defer to the user floor: a verdict computed from
evidence at or before your last reply loses.

**distiller.** When a top card completes and settles: `BACKGROUND:` (re-
orientation for a reader who lost the thread) + `TAKEAWAY:` (the one thing
you would most want to know now that it is done), consuming the closer's
done-reason as ground truth. After a follow-up re-completes a card, the
prior summary is handed back and the work text is cut to the stretch after
your follow-up, so the takeaway is the update, never a recap. May cite a
`SOURCE: mN` line, parsed into the summary's deep link; a cite that misses
logs and chips the card instead of failing.

**briefer.** When a top card blocks (and live for the focused
picker/permission goal): a decision brief that leads with exactly what you
must decide or provide, then options and tradeoffs. Same `SOURCE:`
contract. Three call failures on one card is a loud give-up, re-armed on
recovery.

**courier.** Owns peer-message segments; the planners skip them. The sender
declared delegate/coordinate/question at send time (schema-required,
2026-07-08); the courier takes that as a strong prior and reads the body
for whether work actually changed hands. Delegating: a real goal planted in
the recipient's tree (origin-stamped) plus a "delegated to" tracking node
in the sender's. Coordinating: no card. The companion `run_propagate` is
deterministic: when the recipient completes the plant, the sender's tracker
checks off through the origin pointer.

## Not judges, but often confused with them

- **rollup_status**: pure code. Folds each node's diary into its state and
  each card's subtree into a column (see goal-state.md). Self-healing, and
  holds the authoritative tier: an open item on the agent's own to-do list
  pins the card in Working over any judge verdict.
- **plan-sync**: pure code. Mirrors the agent's own to-do list as flat top
  cards ("declared in the agent's own to-do list"); the grouper nests them.
- **auto-nudge**: a kernel trigger, not an LLM. Detects a genuinely stalled
  session and injects one nudge prompt; the planner's nudge phase does the
  judging, and a failed nudge records the block.
- **awaiting**: event-derived, never a verdict. Only real subagents make an
  idle session awaiting.

## Where responsibilities overlap

- **planner vs closer** on done/block: by design. The planner is eager per
  segment (precision), the closer is the turn-end backstop (recall); diary
  src tells them apart, and both yield to the user floor.
- **grouper vs consolidator**: same prompt, disjoint columns, separate
  names in the logs.
- **distiller vs closer**: consumer relationship; the distiller treats the
  closer's done-reason as ground truth.
- **courier vs planner**: mutually exclusive by segment author; the courier
  plants, the planner's delegation phase files under the plant.

## Ops and knobs

- Toggles: `CLOSER_ON`, `GROUPER_ON`, `DISTILLER_ON`, `CONSOLIDATE_ON`.
  Models: `STATE/judge-model` (triage), `STATE/index-model`.
- Logs: `STATE/judge-usage.jsonl` (per-call cost, one name per prompt),
  `STATE/judge-errors.jsonl` (parse / call / give-up / cite-miss /
  rate-limited).
- Debugging: run the judge's own code against the live store
  (`SourceFileLoader` on `bin/romp-judge`) rather than inferring from logs.
