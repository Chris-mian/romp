# The judges — a field guide

Current as of **2026-07-06**. This is the working reference for what each judge
actually is today: its prompts, triggers, inputs/outputs, and where the roles
overlap. The original design rationale lives in `design/judge.md` (written
2026-06-13/14, when only four judges existed); this doc describes what shipped.
All line references are `bin/romp-judge` unless prefixed `kernel:`.

## The short version

Seven human-facing roles, ten distinct system prompts. Several of the names you
hear ("the planner", "the grouper") are actually more than one thing:

| Role | Prompts | Passes / phases |
|---|---|---|
| **captioner** | 2 — `CAPTION_SYS` (past-tense done-gloss), `GIST_SYS` (present-tense topic gist) | one pass, two unit kinds |
| **archiver** | 1 — `ARCHIVE_SYS` | per session, on new turn |
| **planner** | 2 — `PLAN_PROMPT_SYS` (place the ask), `PLAN_SYS` (record the work) | ~5 dispatch phases: prompt / work / live / nudge / delegation / tagged-followup |
| **grouper** | 1 — `GROUP_SYS` | 2 passes: working-column grouper + completed-column **consolidator** |
| **closer** | 1 — `CLOSER_SYS` | turn-end backstop |
| **distiller** | 2 — `DISTILL_SYS` (done takeaway), `BLOCK_BRIEF_SYS` (decision brief) | one pass, two sides |
| **courier** | 1 — `COURIER_SYS` | postal segments (+ deterministic `run_propagate`, no LLM) |

Two cost tiers, both run continuously by the kernel producer on every pass
(kernel:8864-8873), event-gated so an idle fleet costs file stats, not model
calls:

- **Index tier** (Haiku, `run_index`): captioner + archiver — the durable index.
- **Triage tier** (Sonnet, `run_triage`, one ordered unit, 3988-4008):
  planner → closer → courier → propagate → grouper → consolidator → distiller —
  the live goal board.

Every LLM call goes through one entrypoint, `_judge_run(model, sys, user, ...,
judge=<role>)` (358): a single isolated `claude -p` subprocess with a hard
timeout. The `judge=` label is what usage/error logs attribute to — note the
gist prompt logs as `captioner` and the block-brief logs as `distiller`, so the
logs show 7 roles even though there are 10 prompts.

## The judges, one by one

### captioner (index tier, Haiku)

The readable activity log. Two prompts under one label:

- **`CAPTION_SYS`** (174) — per finished segment/turn unit: one short phrase,
  ~4-7 words, past tense, leads with the result, never names a tool. Empty
  reply = "no finished work", skip. Output appends to `captions/<fsid>.jsonl`.
- **`GIST_SYS`** (433) — for an **in-progress** request (the feed's
  "Analyzing:…" placeholder, provisional cards, timeline dots): a present-tense
  *topic* phrase ("a dark-mode toggle for settings"), not a result.

### archiver (index tier, Haiku)

Per-session headline + abstract. Triggered when a session gains a turn (the
turn-caption count is the event, 761). Reads the session's turn captions
oldest-first; replies exactly two lines, `HEADLINE:` (TOC label) and
`ABSTRACT:` (2-3 sentences). Written to `archive/<fsid>.json`; feeds the chat
TOC header and the on-disk search index.

### planner (triage tier, Sonnet)

Places every segment on the per-session goal tree (max depth 4). Deliberately
**two runs per segment** — early placement was chosen over single-pass
simplicity (2026-06-21):

- **Prompt-run, `PLAN_PROMPT_SYS`** (919): fires the moment the user's message
  lands on a still-open segment. Exactly ONE op, and it must place — `mint` a
  new top goal or `sub` under an open one; never done/block (no work yet).
- **Work-run, `PLAN_SYS`** (842): fires when the segment's work ends. Emits a
  JSON op list: `mint` (selective), `sub` (default — file under the matching
  open goal), `done` (eager; "an answer counts as done", but ending by asking
  the user to approve is a block, not done), `block` (**only the human
  blocks** — waiting on a peer/CI/build/agents stays working), `retitle`,
  `skip` (only when there is neither message nor work).

The work-run engine is reused, mode-switched by `<note>` injections
(1670-1724), for the other phases: **live** re-plan after a user Clear ("place
it NOW"), **nudge** resolution ("RESOLVE goal #1: done or block, no plain
step"), **delegation** follow-on work (files the recipient's work under a
courier-planted goal), and **tagged follow-up** (file under the cited goal
unless the reply clearly starts a different thread).

The planner explicitly does NOT reorganize the board — that's the grouper's
job, and the prompt says so (907).

### grouper (triage tier, Sonnet) — and its twin the consolidator

`GROUP_SYS` (2816): given the session's open top-level goals, nest one top
under another or mint an umbrella when several tops serve one outcome — and
"doing nothing is a valid, common outcome". Ops move whole subtrees. Runs as
its own pass and inline after each planner placement, but the model is only
called when the open-top id set actually changed (`groupedSig` event gate).

Hard rules in `apply_group` (2976): never move an `everDone` node (a
once-completed card keeps its standalone identity), never touch a view-cleared
card, no cycles, depth clamp 4, same-session only.

The **consolidator** (3103) is the same prompt/parser run over the COMPLETED
column: groups related all-completed sibling tops under a done umbrella
(`allow_done=True` lifts the everDone guard there), gated by its own
`consolidatedSig`. So "the grouper" = one prompt, two passes over disjoint
column domains.

### closer (triage tier, Sonnet)

The turn-end completion backstop — exists because agents rarely narrate
"done". `CLOSER_SYS` (3218): a turn-end auditor over the goals this turn
actually touched; for each, verdict **done** (outcome fully delivered),
**blocked** (needs the user's decision — peer/CI/build waits are NOT blocked),
or **omit** ("when in doubt, omit"). Idempotent per turn id. Its verdicts set
the same node flags as the planner's done/block, tagged `negComplete`/
`negBlock` for provenance.

### distiller (triage tier, Sonnet)

The card-face writer, two prompts, independently event-gated per top goal:

- **`DISTILL_SYS`** (3649) — when a top goal completes: `BACKGROUND:` +
  `TAKEAWAY:` ("the one thing the user would most want to know now that it's
  done"), delta-scoped past `FOLLOWUP_DIVIDER` after a reopen so a follow-up's
  summary covers the recent stretch. Writes `node.summary`.
- **`BLOCK_BRIEF_SYS`** (3701) — when a top goal blocks (and live for the
  focused picker/permission goal): a decision brief — "lead with exactly what
  they must decide or provide", options and tradeoffs. Writes
  `node.blockSummary`.

Both may cite a `SOURCE: mN` line, parsed off into `summaryAnchor`. The done
side consumes the closer's `doneWhy` as ground truth.

### courier (triage tier, Sonnet)

Owns postal (peer-message) segments — the planner skips those entirely
(`_seg_peer` discriminator). `COURIER_SYS` (4017): classify one A→B message as
**delegating** (B now owns a concrete task → plant a real top-level goal in
B's tree, with `origin:{peer, goalId, msgId}` provenance, plus a
"↪ delegated to <peer>" tracking node in A's tree) or **coordinating** (no
goal; placement recorded as `fyi`). Idempotent by postal msgId. The companion
`run_propagate` (4161) is deterministic, no LLM: when B completes the planted
goal, the sender's tracking node is marked done through the origin pointer.

## Not judges, but often confused with them

- **`rollup_status`** (1427) — pure code, no LLM. The single authority that
  turns node flags into each top card's column. Precedence: `cleared` >
  `blocked` > `followupPending` (optimistic) > `completed`(+settled) >
  `working`. Self-healing on every pass: drops moot blocks on completed
  subtrees, clears stale optimistic chips, rolls completion down to orphaned
  open sub-steps (`rolledUp`, reversibly), and holds the **authoritative
  tier** — a node whose subtree has an open `agentTask` (the agent's own
  to-do list) can never be complete, whatever any judge said.
- **auto-nudge** (kernel:1352) — kernel-side trigger, not an LLM. Detects a
  genuinely stalled session with an orphaned working top and injects a nudge
  prompt; the *planner's nudge phase* then does the judging.
- **awaiting** — event-derived, never a judge verdict: the session chip comes
  from live state (`_NEEDS_INPUT_STATES`), the per-goal ⏳ badge from the
  `states/<sid>.jsonl` awaiting overlay the SDK backend writes.

## Where responsibilities overlap

- **planner done/block vs closer done/block** — the real overlap, by design:
  planner is eager per-segment (high precision), closer is the turn-end
  backstop (high recall). Same flags, provenance-tagged. Both defer to
  `_block_is_stale` so a user follow-up outranks a replayed stale verdict.
- **planner nudge-phase vs closer** — both resolve; the nudge phase force-
  resolves one named goal, the closer sweeps the turn.
- **grouper vs consolidator** — same prompt, disjoint columns.
- **distiller vs closer** — consumer relationship: the distiller treats the
  closer's `doneWhy` as ground truth.
- **courier vs planner** — mutually exclusive by segment author; the courier
  plants, the planner's delegation phase then files work under the plant.

## Ops and knobs

- Toggles: `CLOSER_ON`, `GROUPER_ON`, `DISTILLER_ON`, `CONSOLIDATE_ON`
  (147-169). Models: `STATE/judge-model` (triage) / `STATE/index-model`.
- Logs: `STATE/judge-usage.jsonl` (per-call usage by `judge=` label),
  `STATE/judge-errors.jsonl`.
- Debugging: run the judge's own code against the live store
  (`SourceFileLoader` on `bin/romp-judge`) rather than inferring from logs.
