# Invisible restarts and a kernel split into processes along its cheap seams

**Status:** design line, 2026-09-14. The user ruled the same afternoon (paraphrased): restarts should be invisible, the previous board staying on screen with only the watched tab rebuilt; and the kernel should be split into processes along the seams the review found, in stages, quantified along the way, done completely to the degree it improves performance. Written against upstream/main at 5f836e8e; the line references describe the repo at that commit. Each stage is its own pull request with its own measurement; nothing here is built yet.

## What the review measured (2026-09-14, four reviewers, reports outside the repo)

The kernel is one Python interpreter on effectively one core. Over a 617 second window its threads wanted about 1,430 seconds of interpreter time (the refresh thread 526, the judges 422, the housekeeping 394, the request thread 88). Every slow thing waits on the interpreter lock, not on disk: a saved transcript document restores in 0.2 seconds alone but was charged 1.5 seconds each at boot behind a decoding thread; the 55 seconds of chat builds on the 3:58 PM restart read 238 MB, under a second of decoding by itself; JSON decoding is 83 to 90 percent of a cold parse. More threads in parallel therefore make things slower, which the first cut of the cards-first shortcut showed the same day (131 seconds to a full board with six panes rebuilding the same cold work at once). The levers are doing less work, keying work on events, single-flight de-duplication (landed), and moving decoding out of the process the browser waits on.

The bad seam is passing parsed transcripts between processes: a parse is a tree of dictionaries (the record cache holds 1.2 GB of them) and pickling it costs about what decoding the JSON did; subinterpreters share the same transfer problem. The good seams hand over compact bytes the kernel already knows how to consume.

## Stage zero: invisible restarts (the browser and the reload core)

Today a restart reloads the page: the shell's `checkBoot` reads `/version` on its socket's reopen, and a boot id other than the one baked into the page requests a reload (`noteVersion`, the reload core in kernel.py). The reloaded page dials as one that holds nothing, so the kernel builds every tab whole for its connect push and again for the first refresh, and the user sees the romp logo with no panes for as long as that takes.

The change, in the reload core and the shim (kernel.py strings; romp_perf), with the client half of the diet (romp_chat, pull request 1661) standing:

- A restart with an unchanged build never reloads. The trigger `noteVersion` requests a reload only when the build changed: `dist_ver` above the page's `LOADEDV` (already `noteDv`) or the kernel's code sha differing from the page's. A boot id alone marks the board reconnecting (the `armStale` machinery) and lets the shim redial as it does today (`reconnect=1`), which the kernel resolves to the skeleton diet: the watched tab whole, every other tab a skeleton with its status. The board never leaves the screen.
- A changed build reloads once, and only once the redialed socket's `freshPending` has cleared (the first fresh frame arrived), so the reload lands on a kernel whose builds are warm and the splash lasts a bundle load. The reload core's `fire()` and its record are untouched; romp_chat widens the chat pane's diet condition from "the record says restart" to "a record is present", so the reloaded page dials the diet too.
- The fresh open after a boot (no record, no redial) stays served whole; the manager is putting its design to the user separately (the diet as a property of the first dial that carries an active hint on a cold kernel).

Measurement: the connect push timer (`pusher.connectPush`) and the browser-side time to the first pane, at the next browser-attached boot; the goal is no blank page at all on an unchanged build and a bundle-load-long one on a deploy.

## Stage one: a saved document for every transcript (romp_metrics)

The checkpoint writer refuses a document for 34 of the 76 transcripts over 10 MB (43 percent of their bytes) because its parent walk gives up on a cycle in the resolved graph (`skip("cycle")`, event_model.py near 5840); the refusal is retried at every settle. Those undocumented sessions are the boot's whole parses (about 28 per boot; about 9 once they have documents). A visited set, as `active_path` uses, ends the walk on a repeated uuid without refusing the document. Owner romp_metrics, design line first; this stage is the prerequisite of every later one, since the document is the form the processes hand each other.

Two measures beside the counts (romp_metrics, 2026-09-14): correctness, a document written over a looping graph must restore to the same world the live parse shows, so the writer's walk stops at the first revisit exactly as `active_path` does and the restore-equality test (the cold parse as the oracle) runs over looping fixtures shaped like the review's rings (an attachment chain; a stop-hook summary, assistant, user, compact-boundary ring); and the refusal class, since `cycle` is not structural today and is retried at every settle and converge pass, paying the writer's prelude each time: after the visited set any cycle that still refuses becomes structural, and the perf block shows the retries gone (`asmCheckpoint.skipped.cycle` at zero across a boot).

Measurement: `asmCheckpoint.parse` at the first refresh with a browser (`full` against `restore`), `checkpoints.readBytes`, and the count of documents on disk that restore cleanly.

## Stage two: a decode worker process that writes documents (romp_perf with romp_metrics)

The transfer form is the document the kernel already restores from: all 44 sessions together are 26 MB compressed, the largest 4.4 MB, one restores in 0.2 seconds. A worker process parses a cold transcript and writes its document; the kernel restores. JSON decoding, 85 to 90 percent of the cold parse, leaves the interpreter the browser waits on.

- **Shape.** A script beside `bin/romp-event-model` (which already parses one transcript from the command line) takes a list of leaves and, for each, parses whole and writes the document exactly as the settle's writer does (`parse_session` then `asm_checkpoint_write`, in its own interpreter with its own caches), printing one line per finished leaf (the leaf, the outcome, the document's key) that the kernel reads on a thread. One worker at a time, spawned under its own `systemd-run --user --scope` with a low CPU weight, never a fork of the kernel (a 4 GB multi-threaded process must not fork).
- **When.** At boot, for every alive leaf whose document is missing or refused, in priority order: the tabs the connected pages are looking at first, then the rest smallest first (the most sessions per second). At exit, the old kernel spawns the same worker for its undocumented leaves and lets it outlive the process, so the next kernel finds documents where the old one found none: the old kernel hands the new one a warm cache in the one form that survives.
- **Single-flight across the two processes.** The kernel keeps the set of leaves handed to the worker. A consumer about to parse a leaf in that set waits, bounded, for the worker's line and then restores; a leaf the worker has not started is claimed by the consumer, parsed in-process as today, and skipped by the worker (the kernel tells it through its stdin). The active tab is therefore never held behind the worker's queue: it is either first in the queue or built in-process at once.
- **Failure is loud and falls back.** A worker that exits early, writes nothing for a leaf, or writes a document the kernel's restore refuses (the identity and coverage checks it already runs) is counted under `/perf` (a `docWorker` block: spawned, leaves handed, written, refused, fallbacks, seconds) and said once on stderr; the consumer parses in-process as before this stage. No new state on disk beyond the documents themselves; their per-writer temporary names already carry the process id.
- **Memory.** The worker's record cache is its own and dies with it; the kernel's stays bounded as today.

Measurement: the first refresh with a browser (chat, cards and timeline stages), `connectPush` by app, `jobsFirstPassS`, and the interpreter-seconds per thread from the boot's stack samples, against the 12:46 PM restart of 2026-09-14 (70 seconds to a full board, 66 of them chat builds).

## Stage three: the judges in their own process (romp_metrics with romp_perf)

The judges used 422 of the 1,430 interpreter-seconds. They already talk to the kernel through files (the goal stores, the verdict rows, the diary) and run their model calls as subprocesses; their in-process share is parsing and store reading. A judge process restores sessions from the same documents (after stage one) and writes the same stores; the kernel needs a wake signal (a pipe, or the postal bus) where it now shares a memo, and the shared parse store (`jd.parsed_session`, one parse for the kernel and the judges) becomes two restores from one document, cheap once documents exist. Design line first: the pass frame, the goal-store snapshot the feed serves during a pass, and the billing ledger's re-bill on host re-attach all assume one process today.

Measurement: the interpreter-seconds of the pusher and the request thread during a judge pass, the pusher's cycle time percentiles, and the judges' own pass time.

## Stage four, if the numbers still say so: frame builders as processes

What the browser receives is already bytes (a 1.8 MB cards frame, 9.5 MB of timeline bars). Builder processes could produce the wire bytes and the kernel relay them, but only once documents are the shared cheap form (stage one) and each builder would hold its own memory. Decided after stages two and three are measured, not before.

## Beside the stages: the free-threaded build, gated

The free-threaded Python build removes the interpreter lock at a 10 to 40 percent single-thread cost. A gated measurement (the hermetic served boot test under both interpreters on the devbox, then one boot) decides whether it is worth carrying; it is not a substitute for the stages, since the transfer costs and the duplicated work are the same under both.

## Rules every stage keeps

- Lazy by default: nothing is parsed or built until something looks at it; the worker prepares documents, it does not build frames.
- Loud failure, no silent degrade: every fallback is counted under `/perf` and said once on stderr.
- Event-keyed, never a timer: the worker's lines, the socket's fresh frame and the build change are the events; bounds exist only as backstops and are named as such.
- One shared pool, sized to the machine: any new cache is a fraction of memory, never a small literal.
- Measured on the next browser-attached boot, with several panes redialing, before the next stage starts.
