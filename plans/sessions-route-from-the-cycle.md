# GET /sessions is served from the cycle's snapshot

**Status:** a design line for a read before code (written 2026-09-15, romp_perf; the read is romp_manager's; the postal bus, the route's steadiest reader, is its owner's to check). The third of the three lines on the kernel's steady-state cost (the nudge walk on events, #1733 and #1736; the spend guard, #1741). The fix pull request follows the read, cut from main, red first.

## Why now

On the nudge line's before window (one devbox boot, 43 minutes to snapshot C) `GET /sessions` was answered 1095 times, about 25 a minute, at 125 ms each: 137 s of handler wall in 2595 s up, the largest of the HTTP routes by an order of magnitude (`GET /version` 273 calls at 40 ms, `GET /views` 68 at 2 ms). The steady-state attribution of the same morning put it at 38.5 s over its window. Every one of those requests rebuilds the same list from the same reads, and nothing in the list changes between most of them.

## The premise, checked in code

- **The route builds per request.** `GET /sessions` (kernel.py, the handler) calls `_session_rows()` and serializes it; `?threads=1` appends `_thread_rows()` for the postal bus.
- **What one build reads.** `_session_rows` reads the working-notes store (`_working_notes`), takes ONE `_sessions(time.time())` sweep for the sid-to-path map (discover's fingerprint re-stats every names entry and each discovered transcript; outside a pusher or jobs cycle there is no `_live_scope.sessions` memo, so the request pays the sweep whole), and `Sessions.live()` (every backend's registry read, the same read `_live_map` takes once per cycle). Per row: `_identity_of`, `_name_of`, `_cwd_of`, `jd._sdk_last_sid` and `_compacting_now(sid, tm=meta, path=path)` (the cached parse only; the two hoists in its docstring are the 2026-08-31 fix that took the route from 3.3 s p90 to today's 125 ms).
- **Who asks.** The postal bus (`_kernel_sessions` in postal/postal_service.py: the roster behind list_agents and the send's liveness check), the laptop hub polling this kernel through its tunnel (`_poll_remote_sessions`, one GET per pass of its tunnel supervisor for the wake-router's ids and the names), and an editor plugin's picker on demand. About 25 a minute today with one peer attached and the bus up.
- **The same inputs are already snapshotted.** The pusher's cycle takes `_live_map()` and `_names_snapshot()` once per cycle (`_live_scope`); the jobs pass takes its own; the working notes are a kernel-side store written by `set_working`; the compacting bit is a function of the live row and the cached parse.

## The rule

1. **One listing per change, not per request.** The pusher's cycle builds the `/sessions` rows once, from its own liveness and names snapshots, and keeps them with a key: the liveness snapshot's (sid, state, since, backend) tuples, the names snapshot's stamp, the working-notes store's stat, and each row's compacting bit. A request serves the kept JSON; a request arriving before the first cycle builds once, as today, and keeps the result under the same key.
2. **The key is exact.** Every field a row carries is a function of the key's inputs: id, name and colors from the names snapshot, state and backend from the live row, dir from the registry, lastSid from the SDK registry (part of the liveness read), working from the notes store, compacting from the live row and the cached parse. A field whose input is not in the key cannot be added without adding the input.
3. **Threads ride the same key.** `_thread_rows` is built beside the listing when the bus asks with `?threads=1`, keyed on the SDK backend's thread table revision, and kept the same way.
4. **The pollers change nothing.** The bus and the hub keep their cadence and their shape; the route answers from memory. A push-side hint (the kernel telling the bus the roster moved) is a later line if the bus's owner wants one.

## What the user sees

The picker, the bus's roster and the hub's names are what they were, a cycle old at most (the cycle is the pusher's half-second backstop or sooner on a wake), which is the age the hub's poll already gives them. The kernel's handler thread stops paying a discover sweep and a registry read per request, so a request from the bus during a busy cycle no longer competes with the build for the interpreter.

## The measurement

`/perf` on the devbox over thirty minutes with no client, before and after: `http."GET /sessions"` count and ms (1095 and 137 s over 43 minutes today: about 125 ms a call; after, about the JSON's serialization, single-digit ms), `sessions` under memos (built, served, the key's misses by input), `process.cpu_s`. The claim to hold: the route's mean falls by two orders of magnitude and the bus's roster and the hub's names still move within a cycle of a session's start, rename or death.

## Tests (red first at main)

- Two requests with nothing moved build once (a counting seam on `_session_rows`) and serve equal bodies.
- A session starting, a rename, a state change, a working note and a compacting edge each miss the key and rebuild once; the served row carries the change.
- A request before the first cycle builds and is served from the kept listing by the next.
- `?threads=1` is kept apart from the plain listing and misses on the thread table's revision.
- The route's shape is unchanged: the pins the postal bus and the by-fsid route hold today stand.

## Roads not taken

- **A time-to-live on the listing.** A clock where the inputs are known; a 2 s cache would serve a dead session to the bus for up to 2 s and still rebuild on a quiet board.
- **Making the pollers slower.** Their cadence is theirs; the route should be cheap at any cadence.
- **A push to the bus instead of its poll.** The larger change, for the bus's owner; this line makes the poll free first.
