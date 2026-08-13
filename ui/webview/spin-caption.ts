// The card's SPIN line — the romp swirl + a short caption in the card body saying what is in motion —
// computed in ONE place so a test can EXECUTE the ladder instead of regexing feed.ts's source.
//
// It lives here for the same reason distiller-line.ts does: this rule was pinned by source regex, the
// regex was updated alongside a wrong change, and nothing caught it. Concretely (the user 2026-07-21):
// the "keep the decision brief visible" fix (97ff203) gated the recheck/rejudging swirl on `!briefText`,
// so a blocked card that its session keeps re-judging showed its brief and NOTHING ELSE — sitting in the
// Working column with no sign it was in motion and no sign it was still blocked underneath. The card read
// as "a working card that inexplicably has a summary". The brief and the swirl are SIBLING elements
// (feed.ts appends `secs` then `awaitSpin`), so they were never in competition: the flicker the guard was
// aimed at came from keying the LINE on `column`, and distillState already fixed that. Both show now.
//
// THE CONTRACT (spin-caption.test.ts executes every branch, in order):
//   1. AWAITING      — held in Working on dispatched/delegated work (no peer chip, no bg-task pill)
//   2. PROVISIONAL   — a dashed live-prompt placeholder the planner hasn't classified yet
//   3. RE-CHECK      — a soft-block answered with a TARGETED follow-up, pending re-judge
//   4. RE-JUDGING    — a soft-block + a PLAIN thread reply, with the reply in flight
//   5. SETTLE GAP    — the turn finished, the closer's verdict hasn't landed
//   6. DISTILLING    — a resolved card whose takeaway/brief hasn't been written yet
//   … else no spin (an ordinary working card with its turn open).
// 3 and 4 do NOT depend on whether a brief exists. That independence matters more since 2026-07-22, when
// the brief stopped showing on a card displaced to Working at all (see ./distiller-line): these two are the
// only branches that fire in that window, so the swirl is the sole thing saying the card is in motion and
// still blocked underneath. Gating either on a brief would leave it silent.

/** The card fields the ladder reads. Structural, so the test can pass plain objects. */
export interface SpinItem {
  awaiting?: { why?: string | null; tasks?: unknown[] | null } | null;
  waitingOn?: unknown;
  provisional?: boolean;
  column?: string;
  judging?: boolean;
  recheck?: boolean;
  rejudging?: boolean;
  blocked?: unknown;
  working?: { since?: number | null; toolUses?: number | null } | null;   // open-turn narration (kernel _open_turn_progress; the user 2026-08-13)
}

/** caption: the body line, or null for no spin. tip: the fuller hover explanation. awaitingBg: the
 *  AWAITING case, which additionally wears the rounded box (`.await-paused`) as its distinct read. */
export interface Spin {
  caption: string | null;
  tip: string;
  awaitingBg: boolean;
}

const NONE: Spin = { caption: null, tip: "", awaitingBg: false };

/** dCompleted/dBlocked come from distillInputs(distillState, column) — the GENUINE resolution state, not
 *  the transient column. distillPending is passed in (rather than recomputed) so the two modules keep one
 *  owner for the "is the distiller still working" rule. */
/** Compact duration for the working narration: minutes under an hour, then h+m. */
function workingFor(secs: number): string {
  const m = Math.max(0, Math.floor(secs / 60));
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
}


export function spinFor(it: SpinItem, distillPending: boolean, dCompleted: boolean, nowS?: number): Spin {
  const aw = it.awaiting;
  // a bg-TASK wait no longer boxes its why here (the user 2026-07-13): the compact "Waiting on task" pill
  // on the toggles row carries it (with the task list one click away, like Sub-goals) — see applySections
  const awTasks = ((aw && aw.tasks) || []).filter(Boolean);
  if (aw && !it.waitingOn && !awTasks.length) {
    // AWAITING — the session is held, waiting on background work it dispatched (agents). It keeps its own
    // read: a boxed "Awaiting background agents" label. The romp swirl SPINS here too (the user 2026-07-04:
    // a spin reads as "in flight, not stalled", which is exactly the awaiting state — the box already
    // distinguishes it from the actively-working cases, so the glyph needn't also freeze). A subagent/overlay
    // why keeps the classic boxed label; the caption wraps to two lines if long.
    const why = aw.why || "";
    return {
      caption: /^waiting on/i.test(why) ? why.charAt(0).toUpperCase() + why.slice(1)
                                        : "Awaiting background agents",
      tip: why ? why + ". Not on you; paused until the background work lands."
               : "Paused, waiting on background work it dispatched (not on you). Clears when the result lands.",
      awaitingBg: true,
    };
  }
  if (it.provisional && it.column === "working" && !aw) {
    // the chip tells the truth about the phase (the user 2026-07-12): an OPEN turn is just Working — the
    // judge has nothing to classify yet; once the turn settles (kernel `judging`) the planner's pass is
    // due/in flight and only THEN does the chip say Analyzing…. An AWAITING placeholder (a bg-task wait with
    // no goal to floor, the user 2026-07-13) is provisional too but NOT working: !aw defers it to the boxed
    // why (branch above) or, when tasks exist, to the "Waiting on task" pill — never a false "Working…".
    return {
      caption: it.judging ? "Analyzing…" : "Working…",
      tip: it.judging
        ? "This stretch of work finished; the judge is sorting it into a goal."
        : "A new prompt, still running. Sorted into a goal once this stretch of work finishes.",
      awaitingBg: false,
    };
  }
  if (it.recheck) {
    // RE-CHECK — a soft-block you answered with a TARGETED follow-up, moved to Working and de-urgented
    // (dashed) until the judge re-judges. It rides ALONGSIDE the decision brief, which stays on screen
    // the whole time (the user 2026-07-21): the brief says what it is blocked on, the swirl says the
    // judge is looking at it again. Suppressing one for the other left the card unreadable.
    return {
      caption: "Analyzing…",
      tip: "You followed up. Reopened to Working; the judge will resolve it or re-block it.",
      awaitingBg: false,
    };
  }
  if (it.rejudging) {
    // RE-JUDGING — a soft-block + a PLAIN thread reply, with a turn now in flight. The kernel moves this
    // card to Working the instant you hit send (kernel build_feed: "The 'Re-judging…' swirl rides along in
    // Working"), so the swirl is the ONLY thing telling you the card is still blocked underneath and that
    // the block is being re-evaluated — the `↩ re-judging` chip covers `recheck` only.
    return {
      caption: "Analyzing…",
      tip: "You replied on this thread. Moved to Working while the reply runs; it comes back if the judge re-confirms the block.",
      awaitingBg: false,
    };
  }
  if (it.judging && it.column === "working") {
    // SETTLE GAP (the user 2026-07-13) — the session FINISHED its turn but the closer's verdict hasn't
    // landed, so the card would sit inertly in Working ("the session is done, why is its card still
    // working?"). The swirl says what's actually happening; it hands off to the column move (and then
    // Distilling…) when the verdict files the work. The tip also carries the story the retired
    // judging-stall chip used to tell (the user 2026-07-31): auto-nudges hold off while the review
    // runs, and that hold is romp working the card, not a stall — so it lives here, one hover deep,
    // instead of as a yellow chip pulling the eye to a state nobody needs to act on.
    return {
      caption: "Analyzing…",
      tip: "This stretch of work finished; the judge is deciding whether it completed or blocked this goal. "
         + "Nudges hold off while the review runs — romp is working this card, not stuck on it.",
      awaitingBg: false,
    };
  }
  if (distillPending) {
    // DISTILLING (the user 2026-06-29) — a resolved card whose distiller hasn't produced its line yet:
    // a completed goal awaiting its takeaway (summary), or a blocked goal awaiting its decision brief
    // (blockSummary). The same swirl spins in the distiller-line spot until the line lands, so a card that
    // "is in motion" (the distiller LLM is running) reads as busy rather than blank. Excludes a live
    // permission/picker block (on YOU) — see distillPending in ./distiller-line.
    return {
      caption: "Distilling…",
      tip: dCompleted ? "Writing the key takeaway…" : "Writing the decision brief…",
      awaitingBg: false,
    };
  }
  if (it.working && it.column === "working") {
    // WORKING NARRATION (the user 2026-08-13) — the ordinary working card with its turn open used to
    // be the ONE mute case ("no spin"). Now it says what is actually happening: the open turn's tool
    // count and how long it has been running, both live — a frozen count under a climbing timer is
    // how a silent regression becomes visible at a glance. Every richer story above (awaiting,
    // provisional, re-check, re-judging, the settle gap, distilling) still wins; this is the floor.
    const n = it.working.toolUses || 0;
    const dur = nowS && it.working.since ? ` · ${workingFor(nowS - it.working.since)}` : "";
    return {
      caption: `Working — ${n} tool ${n === 1 ? "use" : "uses"}${dur}`,
      tip: "The open turn's live progress: tool calls made so far, and how long this stretch has been "
         + "running. If the count freezes while the timer climbs, something is worth a look.",
      awaitingBg: false,
    };
  }
  return NONE;
}
