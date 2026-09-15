# A refusal mark belongs to the cut rule it was made under: retire version-old marks at the boot sweep

**Status:** design line, 2026-09-15, the manager's word given the same night. Written against upstream/main at f17bdc95 (stage one b merged as 6cbea589, the per-session chat build timer as f17bdc95); the line references describe the repo at that commit. The code follows as a fix PR, red first on a version 6 marked fixture.

## What the measurement boot showed

The boot after stage one b's deploy boot (03:44 UTC, a browser attached) parsed 16 leaves whole, every one of them `restore:refusedStanding`: the same sixteen refusal marks the stage one census found, still standing on their sidecars. Their documents were never rewritten under the version 7 cut rule. The reason is the order of the roads: a standing mark is read BEFORE the document (`_asm_refusal_stands`, event_model.py near 5351: the sidecar's `refused` block against the leaf's current stat), and while it stands every road goes straight to the whole or cold parse with no proof and no rewrite. The version check lives in the document load (`doc.get("av") != _ASM_CKPT_V`, near 6374), which a standing mark never reaches. Those sixteen sessions are idle, so their leaves do not move, so their marks never clear, so they parse whole at every boot, for as long as they stay idle: 16 of the 16 whole parses at the measurement boot, against 40 documents restored.

## The rule

A refusal mark records that the chain proof refused a document for the TAIL's shape against ONE cut. Stage one b changed the cut rule and bumped the document version from 6 to 7, so a mark made against a version 6 document says nothing about the document the version 7 writer would produce; it is history, exactly as a mark is history when a rewrite moves the cut (that case the writer already retires: `_asm_retire_refusal_mark`, keeping the old sidecar's bytes as `<meta>.retired-<stamp>`).

So: at the boot sweep, a sidecar that carries a `refused` block AND an `av` below `_ASM_CKPT_V` has its mark retired. The sidecar's bytes are kept beside it as `.meta.retired-<stamp>` (the same shape the writer's retirement and the flags quarantine use; the sweep already removes these asides with their document since 6cbea589), and the sidecar is rewritten without the `refused` block, its `av`, `path`, `files` and `linked` unchanged, so the boot's later reads see the same inputs and no mark. Nothing is written to the document.

## The premise, checked in code

- **Where the mark is read.** `_asm_refusal_stands(leaf_path)` (near 5351) reads the sidecar `<document>.meta`, takes `refused` (a dict with `reason`, `size`, `mtime`) and answers True when `[size, mtime]` equals the leaf's current stat. Its callers send the parse to the whole or cold walk, counted `restore:refusedStanding` and `seeded:refusedStanding`, with no proof and no rewrite.
- **Where `av` is read.** The document load (near 6374) reads `av` from the inflated document and books `fallbacks.version` when it differs from `_ASM_CKPT_V`, removing the document (`removed["fallback:version"]`). The sidecar ALSO carries `av` (`_asm_sidecar`: `{"av", "path", "files", "linked"}`), written at every publish, so the sweep can read the version from the few bytes it already reads, never inflating the document.
- **The sweep's loop.** `checkpoint_sweep()` (near 1562), called once at boot from the kernel (kernel.py near 11129), walks `*.json` and `*.asm.json.gz`; for an assembly document it reads the SIDECAR's text (falling back to the document only when there is none), parses it, and keeps the document when `path` exists. The retirement is one more step inside that loop, on the parsed sidecar of a kept document: `refused` present and `av` an integer below `_ASM_CKPT_V` means rename the sidecar to `<meta>.retired-<stamp>` and write a fresh sidecar without `refused` (a tmp file then `os.replace`, as the writer does). The sidecar is already in hand, so the cost is one rename and one write per retired mark, once.
- **The counter.** `asmCheckpoint.removed` (`_asm_removed(reason)`, near 5562) counts what the sweep and the fallbacks removed, keyed by reason; the retirement bumps `removed["refusedMark:version"]` once per mark, so `romp perf --json` names how many marks a boot retired and the count is zero at every boot after the first.
- **The one-boot cost.** At the boot that retires the marks, the sixteen leaves load their version 6 documents, fail the version check (`fallbacks.version` 16, the document removed), parse whole once, and the settle's write (or the converge pass for the idle ones, since 6cbea589 both write under the version 7 rule) produces their documents; the boot after that restores them. Sixteen whole parses once, which those leaves pay at EVERY boot today, so the first boot costs nothing more and every later boot saves sixteen whole parses (at the measurement boot, 988 MB read for 16 whole parses plus 40 restores; the sixteen are most of those bytes).

## Correctness

- A mark on a CURRENT-version sidecar stands exactly as before: the sweep touches only sidecars whose `av` is below the current version. A sidecar without `av` (an older write, before the sidecar carried it) is treated as version-old too: its mark was made against a document the current load would refuse anyway.
- The retirement writes no document and moves no cut, so a restore after it takes the same road a fresh version refusal takes today (`fallbacks.version`, then the whole parse, then the settle's write): nothing new to prove.
- The retired sidecar's bytes stay beside the document (forensics) and leave with it (the sweep's `.meta.retired-*` handling since 6cbea589).
- No clock input to any verdict: the stamp in the retired name is a file name, read by nothing.

## Tests, red first on a version 6 marked fixture

A document written by the current writer, its sidecar rewritten by hand to `av` 6 with a `refused` block at the leaf's current stat (the version 6 marked shape): at the base the sweep keeps the mark, the parse goes cold under `restore:refusedStanding`, and nothing is rewritten; with the fix the sweep retires the mark (`removed["refusedMark:version"]` 1, a `.meta.retired-*` beside the document holding the old bytes, the sidecar without `refused`), the next parse books `fallbacks.version` and parses whole, the settle's write produces a version 7 document, and the parse after that restores equal to the cold parse. Controls: a current-version sidecar with a mark is untouched by the sweep (the mark stands, counted zero); a version-old sidecar WITHOUT a mark is untouched (no retirement, no aside); the sweep still removes a document whose file is gone together with its asides.

## Not taken

Retiring the mark inside `_asm_refusal_stands` at read time (checking `av` there) would move a write into every read road and every parse; the sweep runs once at boot and already holds the sidecar's bytes. Clearing every mark at a version bump regardless of the sidecar's version would also clear marks the version 7 writer made in the same process life, which stand for a real shape.
