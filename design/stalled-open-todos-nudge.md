# Stalled-with-open-to-dos → blocked + a distinct one-shot nudge

**Status:** Increment 1 (loop-safe re-arm) SHIPPED (`58bc7ad`). Increments 2–4 (this doc) NOT
started. Author: bugs session, 2026-07-01, at the user's direction.

## 1. Problem & root cause

romp's **authoritative-tier plan-sync** (see `design/` history + memory `authoritative-plan-sync-built`)
takes the agent's OWN to-do list as authoritative that work is *undone*: an open agent to-do
(`node["agentTask"]`) forces its goal to roll up **WORKING**, overriding the judge's inference. But
**Claude Code's to-do system only has pending / in-progress / completed — there is no "blocked."** So the
agent *cannot* self-mark a to-do blocked, and when it stops with to-dos still open (which it routinely
does — that's normal Claude Code behavior), romp reads the goal as WORKING **forever**.

The auto-nudge fires on "working + genuinely stopped." A permanently-working goal was therefore nudged
forever. Before the loop-safe fix, a nudge-response that stayed working RE-ARMED the next nudge (the
2026-06-25 "keep nudging till resolved" rule), so the agent responding-and-re-stalling tight-looped:
the `track` session's g9 fired every ~5s, count climbing to 82, **burning tokens**.

## 2. What's already shipped — Increment 1 (`58bc7ad`)

The auto-nudge (`_auto_nudge_tick` in `bin/romp-kernel`) now fires **at most once per GENUINE stall**:
the re-arm gate skips when `rec["lastTurnId"] == lt_id` (a folded nudge-response — same turn id) **OR**
`_turn_romp_injected(lt)` (a new romp-opened response turn). It re-arms only on a genuine
(human/sdk/peer-opened) NEW ended turn. This reverted the loop-causing `728a1e8` and killed the runaway.
Guard test: `test_auto_nudge_does_not_re_arm_on_its_own_nudge_response`.

Consequence (the gap Increments 2–4 close): a session that stops with open to-dos is now nudged **once,
then goes silent** — no blocked surfacing, no distinct nudge, no failure indicator.

**Auto-nudge is currently DISABLED** (`~/.local/state/romp/auto-nudge.json` `enabled:false`, flipped live
to stop the burn). It must stay off until the kernel is refreshed onto the loop-safe code (the live kernel
still runs the OLD looping re-arm until a `romp --refresh`).

## 3. The design (behavior the user specified + agreed refinements)

When a session is **genuinely stopped** (not actively working; a real end-of-turn idle period, per the
existing `_session_working` tail-idle + genuine-stop gate) **with open authoritative to-dos**:

1. **Treat those to-dos as BLOCKED / needs-you** — romp's inference, since the agent can't self-block.
   This pulls the card out of the working-nudge path (working-nudge only fires on `status == "working"`).
2. **Fire ONE distinct "fork" nudge** (different text from the regular `AUTO_NUDGE_TEXT`), roughly:
   *"You stopped with these still open: <…>. If you don't need anything from me, please continue with
   them. If you do, tell me which are blocked and what you need from me to finish."*
3. **The planner resolves the fork** on the response:
   - agent continues (does genuine work) → to-dos progress, back to legitimately working; **or**
   - agent declares a blocker → planner marks **≥1** open item `blocked` with `blockWhy`. (The
     "must mark ≥1" applies ONLY to the blocked branch — never force a spurious block when the agent
     just continues.)
4. **Run the DISTILLER over the block reason** (the user's explicit ask 2026-07-01): the block-distiller
   takes a more holistic view than the raw planner `blockWhy`, producing `blockSummary` for the card.
5. **One-shot, then a "nudge failed" chip.** The fork nudge (like the regular nudge) fires once per
   genuine stall. If it does NOT resolve — the agent's response leaves the goal still working-stalled
   with no genuine progress and no block marked — put a **"nudge failed"** chip on the card and STOP
   (no re-nudge). This is the escalation-instead-of-loop: one ask → if unresolved, hand to the human.

**Anti-loop invariant (already half-enforced by Increment 1):** never re-arm off the agent's own
nudge-response. A stall that persists *without genuine new work* is surfaced (blocked + chip), never
re-nudged. Only a genuine new stall (real new work → stop) can nudge again.

## 4. Implementation plan (per file)

### 4a. Judge (`bin/romp-judge`) — status + block reason + distiller
- **Relax the authoritative-open override** so a planner-set block on an open agent-task item STICKS
  (is not forced back to open/working by the agent's "still pending" to-do status). READ FIRST:
  `rollup_status` (the open_task authority), the `agentTask` field shape + its status values
  (`declared_plan`, `_sync_declared_plan`), and how `nodeComplete`/`blocked` roll up. The change:
  authoritative-open forces WORKING only while genuinely working; a stopped session's open to-do may be
  `blocked`.
- **Planner marks ≥1 blocked on the fork response.** Likely the EXISTING planner already can (it has a
  block op) if the fork nudge elicits a clear "blocked because …" — try that path first; only add a
  special planner mode if the normal pass won't reliably mark it. Capture `blockWhy` from the reason.
- **Distiller over the block reason** → `blockSummary`. READ the existing block-distiller (produces
  `blockSummary`/`briefedMt` from a blocked node). It should trigger naturally once the node is blocked
  with a `blockWhy`; verify it fires for this path.

### 4b. Kernel (`bin/romp-kernel`) — detection, fork nudge, chip
- **Detect "open authoritative to-dos":** a top goal whose subtree has a node with an OPEN `agentTask`
  status. The feed tree already exposes `auth = (nd.get("agentTask") or {}).get("status")` (in `flatten`,
  ~line 5385). Find the open status values (pending / in_progress).
- **Stalled floor in `build_feed`:** alongside the awaiting / api-error / perm floors (~5417–5468), add:
  a genuinely-stopped session (`not who_working`) with a working top goal that has open authoritative
  to-dos AND has been fork-nudged-and-unresolved → floor to needs-you/blocked with a "stalled" reason.
  (If the judge already rolls it to blocked per 4a, the floor may be unnecessary — decide after 4a.)
- **Fork nudge in `_auto_nudge_tick`:** add a branch — if the stalled goal has open authoritative to-dos,
  send the fork text (new constant `AUTO_NUDGE_STALLED_TEXT`) instead of `AUTO_NUDGE_TEXT`. Same
  once-per-genuine-stall re-arm (already in place). Fire site ~line 1178.
- **"Nudge failed" tracking:** in the nudge record (`_mark_auto_nudged` / `_auto_nudge_data`), or derived
  in `build_feed`: a goal is `nudgeFailed` when it was nudged (rec exists), the nudge-response turn
  completed, and the goal is still working-stalled (not blocked/completed, no genuine progress). Emit a
  `nudgeFailed` flag on the ask dict. Applies to BOTH the regular and fork nudge.

### 4c. UI (`ui/webview/feed.ts`) — the chip
- Render a **"nudge failed"** chip on a card whose ask carries `nudgeFailed`. Model it on the existing
  card chips (e.g. the `↻ Followed up` chip). Build via `npm --prefix chat-view run build` (dist-only —
  no kernel restart to deploy the UI, but the KERNEL changes above need a refresh).

## 5. Tests (repo rule: a test per change)
- Kernel (`tests/test_kernel.py`, class `ViewBuilder`, near the other `test_auto_nudge_*`):
  - fork nudge fires (different text) for a stopped session with open authoritative to-dos;
  - it fires ONCE (no re-arm on its own response — already guarded);
  - `nudgeFailed` flag set when the nudge-response leaves the goal still stalled;
  - the stalled goal surfaces as blocked/needs-you (floor or judge rollup).
- Judge (`tests/test_romp_events_golden.py` or `tests/test_*.py`): a stopped session with an open
  agent-task item can be marked blocked (authoritative-open no longer forces it open); the fork response
  marks ≥1 blocked with a `blockWhy`; the distiller produces `blockSummary`.
- Reuse `_drive_nudge_over` / `_stall_transcript` helpers in test_kernel.py.

## 6. Deploy & safety
- All kernel/judge changes need a **`romp --refresh`** to go live (aborts in-flight SDK turns — the
  user's call). UI is dist-only (rebuild + browser reload).
- **Do NOT re-enable auto-nudge until the loop-safe kernel is live** (refresh first). The user re-enables;
  don't do it unilaterally.

## 7. Open questions / decisions
- Does the stalled state need BOTH a judge rollup (→ blocked) AND a build_feed floor, or does one
  suffice? Resolve after reading `rollup_status`: if the judge can roll stopped+open-todos to blocked,
  the kernel floor may be redundant. But the judge only runs post-turn; the kernel floor gives immediate
  event-based surfacing. Likely: kernel floor for immediacy, judge for the persisted block + reason.
- Exact "genuine stop" gate for firing the fork nudge = the same one the regular nudge uses
  (`_session_working` False + genuine-stop gate + `_closer_settled`). Reuse verbatim.
- "nudge failed" precise trigger — pick the event-based definition (response turn completed + still
  stalled), NOT a timer.
- Session names in examples (e.g. the `track` session that hit the loop) are romp session names, not
  personal identifiers — fine to reference; keep real transcripts/prompts out (privacy rule).
