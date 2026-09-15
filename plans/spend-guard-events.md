# The spend guard stats a tree only while its session can spend

**Status:** a design line for a read before code (written 2026-09-15, romp_perf; the read is romp_manager's). The second of the three lines on the kernel's steady-state cost (the nudge walk on events landed as #1733 and its code head is #1736; the sessions route from the cycle's snapshot follows). The fix pull request follows the read, cut from main, red first.

## Why now

The steady-state attribution of 2026-09-15 (an idle devbox kernel at 36 percent of a core) put the spend guard second among the housekeeping jobs after the nudge walk. Read again on the before window of the nudge line (one boot, 32 minutes, 2691 passes at the jobs thread's half-second cadence): `jobs.spendGuard` 56 ms of a 177 ms pass, and over that boot's 3461 passes 222 seconds in all; `memos.spendTree` counted 1506 directory stats and 365 file stats per pass. Nothing in those stats changes on a quiet pass: the sessions' agent trees move only while a session runs, and most of the live sessions are idle at any moment.

## The premise, checked in code

- **The guard runs every pass over every alive session.** `_spend_guard_tick` (kernel.py, on the jobs thread through `_job_stage('spendGuard', ...)`, never the boot's first pass) reads `_spend_rate_usd_per_hour(path, now)` for each row of `_alive_sessions`, latches a session over the ceiling in `_SPEND_GUARD` and fires once, and clears it once the rate falls under `SPEND_GUARD_REARM` of the ceiling.
- **The rate is a window over files.** `_spend_window_usd` sums `_spend_file_rows` over `_spend_window_files(leaf, since)`: the leaf transcript and every agent transcript under `<sid>/subagents/` (Task agents at the top, Workflow agents under `workflows/`) that changed at or after the window's floor.
- **The tree memo stats every directory every pass.** `_spend_window_files` keeps each tree's directories and files with their mtimes (`_SPEND_TREE_CACHE`, persisted). On every call it stats every directory of the tree (a new file moves its parent's mtime), the hot files (mtime at or after the floor less `SPEND_GUARD_MEMO_SLACK_S`) every call, and the cold files once per `SPEND_GUARD_TREE_RESCAN_S` (30 s). The 1506 directory stats a pass are this loop over every live session's tree; the 365 file stats are the hot files plus the cold sweep's share.
- **The rows are already memoized.** `_spend_file_rows` serves a file's rows from `_SPEND_ROWS_CACHE` while the record cache entry's (mtime, size, base) stands; a pass over an unchanged file costs one entry read (`entryStats` 0.25 a pass) and no scan.
- **What the kernel knows without a stat.** The session's live row (`live_map[sid]["state"]`: working or not, its `since`) is in the pass's own snapshot; the backend holds the session's live subagent and background-task sets in memory (the sources `_session_awaiting` reads first, 0 and 0.5: SubagentStart/Stop and the task lifecycle stream); the nudge line's standing snapshot (#1736) already observes the live rows and, with a client connected, the pusher's producer signature.
- **The decay needs no file.** A latched session clears when its rate falls under the re-arm share: the rows in the window are known (the memo), and the window slides with the clock, so the rate of a session whose files stand is a function of the rows' timestamps and `now`.

## The rule

1. **A tree is statted while its session can spend.** A session can spend while its live row says working, or while its backend reports a live subagent or background task for it (a background agent writes its transcript under the tree while the parent's row stands idle). For every other alive session the guard serves the tree's standing file list and the rows' memo: no directory stat, no file stat.
2. **The edges re-stat.** A row that moves to or from working, a change in the session's live sets, and the pusher's signature seeing a transcript under the tree move (a client connected) mark the session for a fresh stat on the next pass, through the standing snapshot's marks (`_files_stat_mark`, #1736), so the agent files a turn wrote after the row went idle are read once more at the edge.
3. **The rate of an idle session is computed from the memo.** `_spend_window_usd` over a session the guard does not stat reads the rows it holds against the sliding window; the latch clears on the pass where that rate falls under the re-arm share, as today, with no stat. A crossing cannot happen without a write, and a write happens only while the session can spend.
4. **A floor bounds the trust.** An idle session's tree is statted once per `SPEND_GUARD_TREE_RESCAN_S` (30 s, the bound the cold sweep already uses) so a writer the observers miss (a transcript moved by hand, a backend that reports no sets) is seen within it. The cold sweep and the hot-file rule stay as they are for a session being statted.
5. **The counters name the saving.** `memos.spendTree` gains `served` (sessions served from the standing list without a stat) beside `dirStats` and `fileStats`; the read is their per-pass rate before and after.

## What the user sees

Nothing about the guard changes: a session crossing the ceiling is stopped and told on the same pass as today, since it is being statted while it runs; a latched session clears on the same pass, since the clearing is the clock's. The housekeeping pass drops by the guard's share on a quiet board.

## The measurement

`/perf` on the devbox over thirty minutes with no client, before and after: `memos.spendTree.dirStats` and `fileStats` per pass (1506 and 365 today; about the working sessions' trees after, a few tens on a quiet board), `served` per pass, `jobs.spendGuard` ms per pass (56 today, read under a suite's contention; a quiet window is owed), `process.cpu_s`. The claim to hold: the stats fall to the working sessions' share, and the guard's firings and clearings in the ledger are the same events at the same passes.

## Tests (red first at main)

- A pass over idle sessions (rows waiting, no live sets) stats no directory and no file once their trees are known; `served` counts them.
- A session whose row says working is statted every pass; a session with a live background task and an idle row is statted every pass; a row moving from working to waiting is statted once more on the pass after the edge.
- A latched session whose files stand clears on the pass where the window slides past its rows, with no stat.
- The floor re-stats an idle session's tree once per bound and serves it again after.
- A crossing during a working turn fires on the same pass as before the change (the fixture that pins the guard today, run with the rule).

## Roads not taken

- **A slower guard cadence.** A timer where an event exists; a crossing would only be caught late.
- **Keying the tree on the leaf transcript's mtime alone.** A background agent writes under the tree without touching the leaf; the live sets are the event for that.
- **Filesystem notifications.** The platform dependency the nudge line declined; the backends already know when a session runs.
- **Dropping the cold sweep.** It is the floor here too; with idle sessions no longer statted every pass it costs a stat per file per thirty seconds per working session only.
