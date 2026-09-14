# A saved document for every transcript: the writer's spine walk ends at the first revisit

**Status:** design line, 2026-09-14, landing with its fix (stage one of the process split: `plans/process-split.md`). Written against upstream/main at 487cafe2.

## What is wrong

The assembly checkpoint writer builds the document's pre-cut spine by walking the leaf's parent chain root-ward. Its walk was bounded by the record count and refused the WHOLE document (`skip("cycle")`) when the bound was exceeded, the reading being that a walk longer than the record count is a cycle. The cycles are real: a reused uuid resolves, last-wins, into a ring 3 to 50 records long, 50 or more hops above the leaf (chains of attachment records; a stop-hook summary, assistant, user, compaction-boundary ring). The review of 2026-09-14 counted 34 of the 76 transcripts over 10 MB refused this way (1.97 GB, 43 percent of their bytes); the kernel journal of the same day shows the refusal on six live transcripts, four of them 133 to 161 MB, 12 to 16 refusals each in six hours, so every chat build of those sessions was a whole cold parse, and `"cycle"` not being a structural skip meant the refusal was retried at every settle and converge pass, each retry paying the writer's prelude.

## The rule

The parse already answers the question the writer asked. `active_path` walks the same resolved graph with a visited set and ends at the first revisit; the chat shows that spine, and `chain_verdicts` files the ring's records as `broken` (kept). The writer now walks the same way: repeated uuids last-wins (the graph's own resolution), a self-linked record a root (the graph's own resolution), the walk ending at the first revisit, and the chain up to there the document's spine. The document's world equals the live parse's world, which the restore-equality oracle (restore, hydrated, against the cold parse) proves over ring-shaped fixtures. No document is refused for a cycle; the reason is gone from the writer, and with it the per-settle retry.

One refinement the ring forced in the writer's tip guard. The restore's tail proof (T402 round five) refuses a document whose pre-cut tip has a pre-cut child, because a tail record chaining onto that child instead of the tip would move the spine while still reaching the tip through the child. In a ring the tip has such a child by construction: the ring's own member (a1 above, whose parent is the reused u1). That child is ON the spine already, so a tail chaining onto it reaches the tip through the same spine nodes with the same verdicts and decides no fork; the guard now counts only children of the tip that are OFF the spine. The worry itself is still refused: a tail re-rooted onto the ring's child leaves the tail into the pre-cut interior, the reachability proof refuses the standing document, and the cold parse (whose spine then bypasses the boundary, so no document by design) rules; pinned beside the ring's round trip.

Unchanged: the restore's tail proof (T402 rounds one to eight). A tail record that self-links, reuses a pre-cut uuid or closes a cycle still refuses the standing document at restore, because there the parser itself re-roots and the pre-cut verdicts the document carries may be stale; those shapes are pinned as controls beside the new tests.

## Measurement

At the next deploy boot with a browser attached: `asmCheckpoint.parse` (`full` against `restore`), `checkpoints.readBytes`, `asmCheckpoint.skipped` carrying no `cycle` key, and the count of documents on disk that restore cleanly; the review's estimate is about 28 whole parses a boot falling to about 9. And the biggest live transcript's chat build time from `/perf` before and after.
