# The nudge walk keys on events, not on the pass

**Status:** a design line for a read before code (written 2026-09-15, romp_perf; the read is romp_manager's). The first of three lines on the kernel's steady-state cost (this walk, the spend guard's stat storm, the sessions route from the cycle's snapshot). The fix pull request follows the read, cut from main, red first, in two steps: the sub-stage marks first, then the keying.

## Why now

A devbox kernel with no client connected ran at 36 percent of a core over 32 minutes on 2026-09-15 (process CPU 677 s in 1903 s). The housekeeping thread's passes took 418 s of that wall, and its largest job was the auto-nudge walk: `jobs.autoNudge` 145 s, about eight percent of a core, on a board where almost no pass had anything to nudge. Read finer over 67 passes of a fresh boot: 26 ms of walk per pass on average (4.2 percent of wall), 8.3 ms on a quiet pass, 200 to 430 ms on the passes where something moved; 27 session looks per pass, of which the memo skipped 20.4 and 5.6 read the parse store, and 4.4 were "unbounded" looks the memo can never skip (about 2 per pass for sessions whose open work is all delegated to peers, about 2.6 for sessions whose turn is in flight). The pass takes ten stats per alive session to build the memo's key: 270 stats per pass at two passes a second, and the three event-keyed tick jobs (the awaiting lift, this walk, the interrupt block) each take the same ten, so about 810 stats per pass answer a question that is almost always "nothing moved".

## The premise, checked in code

- **The walk.** `_auto_nudge_tick` (kernel.py) is single-flight and runs `_auto_nudge_pass` every housekeeping pass: `_alive_sessions` over the cycle's liveness map; for each session the memo's key first (`_nudge_look_stat`, over `_session_files_stat`: the transcript, the states log, the goal store, its override journal and archive, the episode log, the clears log, the postal log, the kernel's downtime log and the nudge ledger); the ledger snapshot (`_auto_nudge_data`, memoized by `_ledger_read`); the wait-for graph (`_wait_for_graph`, over `_postal_wait_maps`, memoized on the postal log's stat); the cleared set (`_cleared_ids`, memoized per file state); then each session's look, `_auto_nudge_session`, behind the gate.
- **The gate.** `_nudge_look_check` skips a session's look when the ten stats are unchanged since its last completed look (this kernel's or a previous one's: the memo persists in `_TICK_SEEN`) and that look noted no clock leg that could have flipped by now. A leg noted with `None` (a release that is not one of the ten files) is never skipped. Fourteen legs note `None` by name (asker overflow, an unproved asker row, an unproved or unlanded debt ask, a new or standing deferral, paused tiers, a queued send, a store fault, all work delegated, awaiting a peer, a stamped wait, an unjudgeable check, a refused ledger write), and any verdict outside `_NUDGE_FILE_KEYED_VERDICTS` is counted `unmarked:<verdict>`: a turn in flight ("awaiting-dispatch") is one, so every session mid-turn is re-parsed every pass.
- **What a look costs.** A parse-store read (`jd.parsed_session`, a hit when the transcript stands: 5.6 per pass, cold parses 10 per boot), the goal store's shared view, the states log's idle transition, and the walk over the goal tree.
- **Where the time is marked.** `_job_stage('autoNudge', ...)` closes one `jobs.autoNudge` stage per pass with the bytes read under it; nothing finer, so the 200 to 430 ms passes name no cause on the ring.
- **What the kernel already knows without a stat.** The pusher's cycle snapshots every transcript's and states log's mtime (`_producer_sig`, `_live_scope`); the record cache holds each file's version; the ledger, the goal store saves, the clears log and the episode log are written by this process; the judge generation (`_bump_judge_gen_if_changed`) moves when a judge-written store moved; the postal log is one file, stat once per pass.

## The rule

1. **One snapshot of the ten file classes per pass, shared by the three tick jobs.** `_session_files_stat` is taken once per session per pass and served to the awaiting lift, the nudge walk and the interrupt block from the pass's snapshot: about 810 stats per pass become about 270, with no change in what any job sees (each already reads the same tuple).
2. **A session is looked at when an event marked it, or when its clock is due.** A per-session dirty set is fed by the kernel's own writers and observers: the ledger write, a goal store save or the judge generation's move, a clears or episode log append, the pusher's cycle snapshot finding a transcript or states log moved, the postal log's stat moving. A quiet pass takes no per-session stat and does no look. A floor re-stats every session once per `NUDGE_FLOOR_S` (thirty seconds) so an event the kernel missed heals within it: when unsure, look, the standing rule; the floor is the bound on the memo's trust, not a cadence for the work.
3. **The two hot legs are bounded.** A turn in flight ("awaiting-dispatch") ends with a transcript record, a keyed file, or a change in the backend's pending queue; the queue's revision (an in-process counter bumped when a queue changes) joins the key and the verdict joins `_NUDGE_FILE_KEYED_VERDICTS`. A session whose open work is all delegated, one awaiting a peer, and one under a stamped wait are released by the bus: the postal log is already the eighth file of the key, so those legs note the far horizon instead of `None`. The other eleven legs stay unbounded as named: their releases are not files or queues this process can see.
4. **Sub-stage marks first.** Before the keying lands, the pass marks `jobs.autoNudge.key` (the stats), `jobs.autoNudge.snapshot` (the ledger, the graph, the cleared set), `jobs.autoNudge.looks` and `jobs.autoNudge.parse`, through `_job_stage`'s own helper, so the 200 to 430 ms passes name what they paid and the keying's saving is read against a named baseline.

## What the user sees

Nothing about nudges changes: the same sessions are nudged at the same moments, because every input that can change a verdict still moves the key. The kernel's idle CPU falls by the walk's per-pass share, and the housekeeping thread holds the interpreter for less of every pass while a browser redials.

## The measurement

`/perf` on the devbox over thirty minutes with no client, before and after: `memos.nudgeWalk.looks` per pass (27 today; about zero on a quiet pass after), `jobs.autoNudge` per pass (8.3 ms quiet and 26 ms on average today; about 1 ms quiet after, the events' cost alone on the others), a new `memos.nudgeWalk.stats` counter per pass (270 today; one per moved file after, and the floor's 270 once per thirty seconds), the `unboundedBy` shares for `allDelegated` and `unmarked:awaiting-dispatch` (about 2 and 2.6 per pass today; zero after), and `process.cpu_s` over the window (36 percent of a core today). The outcomes control: `memos.nudgeGate.derived` and the nudge ledger's fired records over a day, the same before and after.

## Tests (red first at main)

- A quiet pass over a fixture of sessions performs zero looks and zero per-session stats once the first pass has keyed them (a counting seam around the snapshot); the floor re-stats after `NUDGE_FLOOR_S` with nothing moved and still looks at nothing.
- One transcript append yields exactly one look, for that session, at the next pass; a ledger write yields one look per session the ledger names; a clears log append yields a look for every alive session (the set is shared), as today.
- A session mid-turn is skipped while its transcript and the backend's queue revision stand and looked at when either moves; a session whose work is all delegated is skipped until the postal log moves; the same for a stamped wait and an awaited peer.
- The three tick jobs read one snapshot: the stat count per pass is the number of alive sessions times ten, not three times that.
- The four sub-stage names appear on the jobs ring with their milliseconds summing to the job's.

## Roads not taken

- **A slower cadence.** A timer where an event exists; the walk would only be late.
- **Filesystem notifications.** A platform dependency for a kernel that runs on two operating systems, where the pusher already stats every transcript once per cycle; sharing that snapshot is the same information without the dependency.
- **Moving the walk to the judges' process.** The walk injects messages into sessions; the kernel owns sends, and the judges' process is stage three's line on its own terms.
- **Dropping the memo's persistence.** The boot's first pass relies on it to skip the sessions a previous kernel had already judged; the keying builds on it.
