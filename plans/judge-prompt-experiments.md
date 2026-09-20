# Judge prompt experiments: measuring a prompt change before it moves cards

**Status:** a design note for a read before code (written 2026-09-20, romp_perf; the read is romp_manager's). The harness follows the read as its own pull request, cut from main, red first; no paid pass runs before the manager's go-ahead on the budget below. The category this serves is the one plans/needs-you.md (the cards owner) is redesigning; this note links it and does not restate it.

## Why now

The user's decision (2026-09-20, paraphrased): Completed must be safe to clear without reading. Nothing a session left undone, offered as a next step, or asked the user about may land under Completed; all of that belongs in the category becoming Needs you. The judges' prompts decide these placements, so the change is a prompt change. Prompt changes move cards, every card move claims something changed, and the cards-move rule (CLAUDE.md) forbids moves on inference flaps; so the user wants a quantitative experiment on their own history before any prompt tweak lands: how many offers, open questions and undone items reach Completed under the current prompt and under each candidate, how many genuinely finished threads a candidate would pull into Needs you (a false interrupt is a broken flow state), how many cards flap between builds, and what each pass costs.

## The premise, checked in code

- **Where the prompts live.** `kernel/judge.py`: `PLAN_SYS` (the planner, one segment against the open-goals menu; ops `done`, `block`, `awaiting` and the tree edits), `CLOSER_SYS` (the closer, a turn-end auditor over the open goals the turn worked on; per goal `done`, `blocked` or kept open), `UNBLOCK_SYS` (the unblocker, whether a blocked goal's question was since answered or made moot). The model calls are `plan_llm(segment_text, menu_text, model=, effort=)`, the closer's call inside `_close_turn`, and `unblock_llm(blocks_text, since_text, completed_text)`. The prompts are module constants read at call time, so a harness can swap a candidate in by assigning the module attribute for the run, with no code path of its own.
- **What the current prompt already says, and where it points the other way.** `CLOSER_SYS` rules that a turn closing with a question that awaits the user's go-ahead is not done, and files the goal owning that decision as blocked. It also rules the opposite for one shape: a goal whose only loose end is an explicitly optional offer is done, not blocked. Under the user's decision that shape is exactly what must leave Completed, so the first candidate prompt is the closer's with that clause inverted; the planner's `done` op and the unblocker's moot rule carry the same question for offers ("an offer or approval whose work was then done anyway" is moot) and are the second and third surfaces.
- **How a verdict becomes a column.** Every verdict goes through `record_verdict(store, node, src, kind, ...)`: an append to the node's verdict log and the flags; `rollup_status` derives each node's status (`completed`, `blocked`, `working`, `awaiting`); the feed (`kernel/kernel.py`, build_feed's card loop) files a top under `needs_input` when the status is `blocked` (or an API block, a permission prompt, a stall), under `completed` when the status is `completed`, else under `working`. So "reaches Completed" is measurable from the store alone, without a browser: a top whose rolled-up status reads `completed` after the pass.
- **What the user's past card actions left behind.** The override journal `STATE/overrides/<fsid>.jsonl` (`append_override`, `append_clear`) carries the user's gestures as append-only events: on this machine today, 640 `clear` rows by the user (the cross-off), 465 `followup` rows (the user re-opened a card with more to do), 22 `resolve`, 23 `unclear` and 10 `restore` (a cleared card brought back); the verdict logs add 11 user `done` and 10 user `clear` events; the 337 `block` rows are the kernel's (the interrupt and nudge roads), not the user's. A `followup` on a card the judges had completed is the strongest recorded signal of a false Completed; a `clear` with no later `followup`, `unclear` or `restore` on the same card is the recorded signal of an accepted one. Neither is a clean label of "offer" against "finished", so the labelling section below uses them as the first tier and a labeller pass as the second.
- **What exists to run the judges outside the kernel.** `romp-judge --plan` and `--close` run one tier over the sessions `discover` finds under the state root; `_rebind_state(path)` repoints the goal, caption, episode and archive directories to another root; `ROMP_CLAUDE_BIN` names the model binary the calls use; `_ab_close_session` already sweeps every turn of one session through the closer on a deep copy of its store, oldest first, and reports the completed tops before and after without saving anything; `_ab_classify` already runs the planner's blocked-or-working verdict under arms of model and effort and diffs against the live status without mutating it. Every model call lands a row in `judge-usage.jsonl` with its judge, model, milliseconds and cost, which is the spend ledger the harness reads back.
- **What a pass costs today** (the last seven days on this machine, from `judge-usage.jsonl`): closer 3169 calls at a mean of 0.11 dollars and 13 seconds each; planner 2169 at 0.08 dollars and 12 seconds; unblocker 684 at 0.05 dollars and 6 seconds. The corpus: 85 registered sessions, 115 goal stores holding 883 top-level cards and 1211 nodes, 68 override journals.

## The corpus

Built once by a script under the harness, from the live state root read only, into `~/.cache/romp-perf/judge-corpus/<date>/`, never into the repository and never into a mail or a body. An **ending** is one finished turn of one session: the transcript up to that turn's result, the goal store as the judges held it before that turn (the store's verdict log and the override journal replayed up to the turn's evidence time, the same replay `load_goals` does), and the card placements the live judges filed for it. Endings are selected in four classes by a heuristic pre-pass over the turn's last assistant text and its to-do state, then confirmed by the labelling below:

1. **Offers**: the turn ends by offering a next step it did not take ("I can also", "if you want, I could", "shall I").
2. **Open questions**: the turn ends by asking the user something it needs answered.
3. **Undone items**: the turn's own to-do list or the transcript shows work it named and left (an unchecked item, a "not done" line, a test it did not run).
4. **Finished threads** (the control): the turn delivers what was asked and states so, with no offer, no question and no undone item.

Target size: 300 endings, roughly 75 per class, drawn across sessions and weeks so no one session dominates; a pilot of 60 (15 per class) runs first. The heuristics are the selection, not the truth: every selected ending gets a label.

## Labelling: the ground truth

Two tiers, each recorded per ending with its source.

1. **The user's own later actions**, where the journal has them: a `followup`, `unclear` or `restore` on a card the judges completed at that ending labels it "not finished"; a user `clear` with none of those within seven days, on a card completed at that ending, labels it "finished"; a user `resolve` labels "finished". About a third of the corpus will carry one of these.
2. **A labeller pass** with a strong model for the rest, reading the ending's last turn and the card's title, answering one of the four classes with a one-line reason, run twice with the order of the classes shuffled so the label is the agreement of the two; its agreement with tier one is measured on every ending that has both, and the harness reports that agreement before any prompt result is read (below 90 percent the labeller is redesigned, not trusted).

## The harness

A script under `scripts/` (or a `--experiment` road in the judge module, whichever the read prefers) that, per arm:

1. Copies the corpus into a fresh scratch state root under `~/.cache/romp-perf/judge-runs/<run>/<arm>/` and rebinds the judge module onto it (`_rebind_state`), so no run reads or writes the live root; the kernel is never started; `ROMP_CLAUDE_BIN` stays the real binary for paid passes and the tests' fake for the harness tests.
2. Swaps the arm's prompt into the module attribute (`CLOSER_SYS`, `PLAN_SYS`, `UNBLOCK_SYS`: the current text for the baseline arm, a candidate file for each other arm).
3. For each ending, runs the planner over the turn's segments and the closer over the turn (as `_ab_close_session` sweeps, on the ending's store copy), then the unblocker over the goals the pass blocked; records each top's rolled-up status and its column by the feed's rule.
4. Runs the same ending a second time from the same store copy to count flaps (a placement that differs between two builds of the same evidence).
5. Sums the arm's cost from the `judge-usage.jsonl` rows the run appended under its own root.

Rules the harness keeps: every run through `capped`; paid passes only inside a quiet window the manager holds and only after the manager's go-ahead on the run's budget; concurrency at the gear's setting; a run that exceeds its budget by a fifth stops and reports.

**Budget.** At today's means, one arm over 300 endings costs about 34 dollars of closer calls, 25 of planner calls and 5 of unblocker calls: about 64 dollars per arm-pass, 128 with the flap re-run. Three arms (the current prompt and two candidates) come to about 380 dollars for the full corpus, plus about 30 dollars for the labeller pass. The pilot of 60 endings costs about 13 dollars per arm-pass, 80 for three arms with re-runs and the labeller. The first paid pass is the pilot; the manager's word gates it and again the full run.

## The measures, per arm

Reported as a cleanplots figure (the skill's rules: horizontal bars from zero, one panel per measure, the arms as bars, the exact numbers annotated) with the same numbers in a table in the results file, and only counts and dollars, never a title or a line of text from the corpus.

1. **Leaks into Completed**: endings in classes 1 to 3 whose card reads `completed` after the pass. Must go to zero.
2. **False interrupts**: endings in class 4 whose card reads `needs_input` after the pass. Must not rise above the current prompt's count.
3. **Flaps**: cards whose column differs between the two builds of the same ending.
4. **Cost per pass** in dollars, and the mean call time, from the ledger.

A candidate lands only when 1 is zero on the full corpus, 2 is at or below the baseline, and 3 is at or below the baseline; the result is a row in this note and the prompt change files as its own fix pull request with the figure attached.

## Roads not taken

- **A synthetic corpus.** Invented endings would measure the prompt against the author's idea of an offer, not the user's history; the tests use synthetic fixtures, the experiment uses the real endings, under `~/.cache` only.
- **An A/B on the live kernel.** The judges' passes would move the user's real cards under two prompts at once; the harness runs on copies and the kernel never sees them.
- **A prompt tweak first, measurement after.** The tweak is what moves cards; the measurement is the gate.
- **The labeller alone as the truth.** One model grading another shares its blind spots; the user's recorded actions come first and the labeller's agreement with them is reported before its labels count.
- **Reusing `_ab_close` as it stands.** It sweeps the live root and prints titles to the terminal; the harness takes its sweep and drops both.

## Tests for the harness (red first at main)

- The corpus builder, over a synthetic state root, writes only under the scratch root it was given, selects the four classes from scripted endings, and refuses a destination inside the repository.
- The arm runner, with the tests' fake `claude` scripted to answer fixed verdicts, produces the exact leak, false-interrupt and flap counts the script implies, on a copy, with the live root untouched (a hermetic `XDG_STATE_HOME`; the state root's `session-hosts` file off).
- The prompt swap: the baseline arm's calls carry the module's current prompt text, a candidate arm's carry the candidate file's, and the module attribute is restored after the run.
- The ledger read sums only the run's own rows and stops the run past its budget.
- The report writes the figure and the table from a fixture of counts with no corpus text in either.
