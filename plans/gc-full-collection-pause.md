# The full garbage collection still pauses the kernel for seconds; the roads to shorten it

**Status:** design line, 2026-09-21; Road B is filed as PR #1987. Issue #1735 (a contributor's report of 2026-09-15) reported a 9.2 second full collection on the pusher thread at `eb18195e`. Since then main gained the `/perf` gc and heap blocks, per-split gc deltas, the line-by-line record reader, the weak atom LRU, the judging band memo and three cached-build changes, none of which touched the collector itself. This note measures the collector on the running kernel today and lays out the candidate roads with the measurement each needs before it is chosen. Nothing here is built; the point is the user's read on which road before code, as the issue's own caution about `gc.freeze` asks.

## What the running kernel shows now (read-only from `/perf`, one boot)

Measured on the live devbox kernel, boot `1858128`, at about 2.9 hours of warm uptime, read-only from its `/perf` gc, heap, pusher, process and recordCache blocks (no live setting changed):

- Generation-two (full) collections have run about seventy times an hour, each pausing the interpreter one and a half to two and a half seconds. The longest was 2.6 seconds and the most recent full collection was also multi-second, so this is warm steady state, not a cold-boot artifact. A full collection stops every thread, the pusher included, for its whole duration.
- The pusher's warm cycle ring (its last few hundred cycles) still holds a worst cycle above ten seconds; its ninetieth percentile cycle is about 1.3 seconds and its median under a tenth of a second. The tail is the full collections landing on a cycle.
- The tracked heap the collector walks is dominated by decoded transcript data: the resident size is about 4 GiB (down from the 6.2 GiB the issue measured), the record cache holds about 0.7 GiB across 150 entries with no evictions (down from 1.16 GiB across 430), and the materialized atom and judging structures account for hundreds of thousands of tracked container objects. A full collection's cost scales with the number of tracked containers, and these trees of dictionaries are most of them. The collector's own probe in the issue (`_PyDict_MaybeUntrack` during full collections) points at the same population.

So the merged work moved the resident size and the cache down, but the full-collection pause is unchanged: seconds, in warm operation, on the thread the browser waits on. The issue does not close on these numbers.

## The mechanism, stated plainly

A generation-two collection visits every tracked container object in the interpreter to find reference cycles. The request-serving interpreter holds the decoded records, the materialized atoms, the parsed sessions and the judging rows, all trees of dictionaries and lists, all tracked. The pause is the time to walk them. Two levers shorten it: walk fewer objects (hold fewer tracked containers, or take the long-lived ones out of the walk), or walk less often (let more garbage accumulate between collections). Moving the collection to another thread does not help: the interpreter lock means every thread still stops. The issue says this directly.

## The candidate roads, and the measurement each needs first

Each road below is a hypothesis about the lever; none is chosen here. The rule the issue sets and the manager repeats: measure the road's effect on the collector before choosing it, and distinguish cold-start cost from warm operation.

### Road A: raise the generation-two threshold

`gc.set_threshold` (or `gc.set_threshold(0)` to stop automatic full collections and drive them on an event) trades frequency for accumulation: fewer full collections an hour, each no cheaper per object, and a larger resident size between them. The lever is walk-less-often, not walk-fewer.

Measure first, off the live kernel (a lab kernel or an offline replay, since no live setting is changed): full collections an hour and the longest pause at the current threshold versus a raised one, the resident size between collections at each, and whether the total interpreter-seconds an hour spent collecting falls or merely clumps. A road that halves the frequency but leaves a 2.5 second pause has not fixed the interrupt the issue is about; a road that also drops the per-collection time only does so if the between-collection heap is not proportionally larger.

### Road B: freeze the decoded records after load

`gc.freeze` moves the currently tracked objects into a permanent generation the collector never walks again, so a full collection after a freeze walks only what was allocated since. The decoded records are long-lived and mostly acyclic, so freezing them after load would take the bulk of the walk out of it. The lever is walk-fewer, and it is the one that targets this heap directly.

The issue's caution is the gate here, and it is real: the public `gc.freeze` freezes the ENTIRE tracked heap, not just the acyclic decoded data, and an empty `gc.garbage` while a cyclic object is still owned does not establish that the object is reclaimed after its owner drops it. So the measurement is a lifecycle validation, not a pause number alone:

- Reclamation after eviction, clear and replacement, including cyclic runtime objects: a session evicted from the cache, a goal store cleared, a login replaced, each followed by an unfreeze-and-collect, must free what it should, proven with a weakref oracle over objects shaped like the real cyclic ones (the attachment chains and stop-hook rings the checkpoint walk already fights).
- No compensating growth: the frozen generation must not accumulate every boot's decoded data without an unfreeze on eviction, or the resident size grows without bound. Freezing on load and unfreezing on eviction is the shape to measure, and whether that unfreeze-collect is itself a pause.
- The pause: full-collection time with the decoded records frozen versus not, warm, and the cold-start cost of the freeze itself.

If freezing the whole heap cannot be made safe under eviction, the fallback the issue names is freezing only the acyclic decoded data, which the public API does not offer and would need a narrower mechanism; that is a larger change and is noted, not proposed.

### Road C: the process split's seams (plans/process-split.md)

The standing design line already aims at this heap from the other side: move the decoding, and later the judges, out of the request-serving interpreter, so the records the full collection walks are not in the process the browser waits on. Stage two (a decode worker that writes the documents the kernel restores from) removes the cold-parse decoded trees from the request interpreter; stage three (the judges in their own process) removes the judging structures. Both stages are owned elsewhere (see plans/process-split.md). Both shrink the tracked heap the collector walks, which is exactly Road B's lever reached by architecture instead of a freeze.

Measure first, from the stages' own measurements already specified in `plans/process-split.md`: the interpreter-seconds per thread and the pusher cycle percentiles before and after each stage, plus the generation-two collection count and longest pause on the request interpreter before and after. If stage two alone drops the full-collection pause below a second warm, the collector needs nothing of its own. This road is the slowest to build and the one with standing owners; the gc-specific measurement is the new ask, to be read beside those stages rather than duplicating them.

## The decision

The user chose the road on 2026-09-21 (paraphrased): try whatever we judge most effective for the kernel's speed, the road ours to pick. The pick:

- **Road B first, freezing the decoded records after load, under the lifecycle validation this issue demands.** It is the most direct at this heap and the fastest to try, and it carries the issue's own safety gate.
- **Road A, the generation-two threshold, as the cheap companion measured in the same run.** A frequency trade that only helps if it also drops the per-collection time; measuring it beside the freeze costs one more arm.
- **Road C, the split, stays the long road already planned** (see plans/process-split.md); its gc-specific numbers are read as those stages land.

No collector change ships before the measurement is in and the user has heard the numbers. The measurement never touches the live kernel's settings: it runs a hermetic kernel over a synthetic warmed workload of realistic size (recorded shapes with synthetic content, never real transcripts), capped, with the `/perf` gc block as the instrument, one boot per arm (base, freeze, threshold, both), cold and warm distinguished. Beside it, the lifecycle validation the issue names, as tests that fail before the fix: a frozen decoded record still reclaimed after its owner drops it and the freeze lifts (a weakref probe), correct eviction, clear and replacement of sessions and caches under the freeze, no whole-transcript reread churn, and the gc hook still counting. The fix ships only once the measurement shows the pause moving; if the freeze does not move it, that is reported with the numbers and the road turns to the split.

## The evidence (2026-09-21)

Measured with a hermetic use of the kernel's own event model: a synthetic corpus of 80 sessions (506 MiB, invented content, placeholder uuids, hostname TESTHOST, never a real transcript, in a scratch root, not the repository, not the live state) parsed through `parse_session`, one fresh process per arm, capped, the collector itself the instrument (`time.perf_counter` around `gc.collect` and `gc.get_stats`, the same per-generation timing the gc hook records). The parse builds 5.6 million tracked objects at 3.1 GiB resident, and a base full collection of 2.85 seconds, matched to the live kernel's 2.6 seconds at about 4 GiB.

Warm full-collection pause per arm:

| arm | cold full collection | warm full collection | resident |
| --- | --- | --- | --- |
| base | 2857 ms | 2833 ms | 3.16 GiB |
| threshold (generation two raised to 100000) | 2857 ms | 2801 ms | 3.16 GiB |
| freeze after load | 2789 ms | 0.1 ms | 3.12 GiB |
| both | 2845 ms | 0.1 ms | 3.16 GiB |

The threshold leaves the per-collection pause unchanged: raising it changes how often a full collection fires, not what one costs, and each one still pauses about 2.8 seconds, so it cannot fix the interrupt alone. The freeze moves all 5.6 million loaded objects out of the collector's walk, so a warm full collection walks only what was allocated since and costs 0.1 ms, independent of the frozen heap's size. `gc.freeze()` itself cost 0.0 ms (a generation-list pointer move); the only cost at load is the full collection the boot already pays, so the freeze adds no cold-start cost. Resident size is unchanged, because a freeze excludes objects from the cycle walk rather than freeing them. Cold, the load's own first full collection, is about 2.8 seconds for every arm, since the freeze happens after it.

The lifecycle semantics, confirmed with a weakref probe on weakref-able cyclic and acyclic objects: an acyclic object frozen and then dropped by its owner is reclaimed at once by reference counting, freeze or no freeze; a cyclic object frozen while owned and then dropped survives a full collection (frozen objects are not walked) and is reclaimed only after an unfreeze and a collection. This is the reason for the reclamation mechanism below.

## The design: reclamation under the freeze

A whole-heap freeze keeps frozen objects out of every collection, so a cyclic structure that becomes garbage AFTER the freeze (an evicted session's decoded tree, a cleared cache entry, a replaced document) is never reclaimed until an unfreeze and a full collection lift it back into the collector's reach; acyclic garbage still dies by reference counting and needs no unfreeze. The record cache is acyclic today, but the materialized-atom structures beside it are not guaranteed to be, so the freeze cannot assume its released objects are all acyclic.

The mechanism is an unfreeze, a full collection and a re-freeze, keyed on the EVENTS that release frozen objects: an eviction from the record cache, a clear of a session's cards or caches, or a replacement of a loaded document. It runs at the pusher's idle boundary right after such an event, never on a timer (the repository's rule is to key on the event, not approximate it with a period). The re-freeze's own pause is a full collection and is bounded by the live heap; it is therefore paid when no browser is waiting (the idle boundary), and it is measured like the others.

A boot's freeze covers everything loaded before the first serve: the freeze-after-load runs once the initial parse of the alive sessions has settled. Sessions parsed later (a lazy warm parse on a client connect, a resumed fork) are not yet frozen; they join the frozen set at the next re-freeze the release events trigger, so the frozen population tracks the loaded population without a timer.

Visibility: the gc hook keeps counting and timing every collection that does run (the young generations, and any full collection during a re-freeze), and the `/perf` gc block already reports the frozen count from `gc.get_freeze_count()`, so the freeze state is visible beside the collections it removes.

Rollout: default on, with an environment switch to turn the freeze off for a measurement, documented in the reference's state and environment section (not a front page).
