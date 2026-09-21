# A peer is behind by what it runs, not by the commit it booted from

**Status:** a design line for a read before code (written 2026-09-14, romp_perf; the read is romp_manager's, no hosts owner live). The fix pull request follows the read, cut from main, red first.

## Why now

The laptop kernel restarted about every five minutes on the evening of 2026-09-14, once per merge to main, docs-only and tests-only merges included. Each restart dropped every pane's socket for one to two seconds and redialed them (before invisible restarts landed the same evening, each one also reloaded the whole dashboard). Read from the laptop kernel's own audit and client rows: each restart is an `http-restart` landing about thirteen seconds after the laptop's own `main-converge-skip` row said "no kernel-code change". This is most of the random connection drops the user reported, and every one of them cut whatever turns were in flight there.

## The premise, checked in code

- `_remote_out_of_date(r)` (kernel.py, near `_behind_info`) reads a peer as out of date when the sha its kernel BOOTED from (`kernel_sha`, from the hub's poll of the peer's `/version`) is not the hub's HEAD. `_behind_info` then counts the commits between them for the hosts row: any commit, a docs edit as much as a kernel change.
- `_maybe_auto_push(r)` runs on every supervisor pass and, for a checked-in peer that is out of date, calls `_auto_ask_peer(host)`, which calls `_ask_peer_to_pull(host)`: `POST /tunnels/pull` to the peer (the peer fast-forwards its checkout over its own ssh; `_pull_remote` deliberately restarts nothing and says "restart romp to run it"), then `POST /restart {"fleet": false}` to the peer, unconditionally, "so it runs what it just pulled": a pull alone leaves the peer's `/version` on the old sha, so the drift would re-offer forever.
- The peer already knows whether the pull changed what its process runs. Its own converge (`_kernel_code_changed(running, target)`, T216, the user 2026-08-23) classes the diff by file: UI and dist inputs, tests, docs, plans, cli, postal and AST-equal kernel python converge in place with the kernel left up (`_in_place_converge`: rebuild dist, audit `main-converge-skip`); only kernel-class python restarts. On the evening in question the peer took that road every time, and the hub's unconditional restart followed it.
- `/version` carries `code_ident` since invisible restarts (2026-09-14): a short hash over the bytes of kernel/*.py the process runs.
- `_dist_ver()` is the newest mtime across the served bundles, recomputed per page render, so a UI-only pull needs no restart for the dashboard to pick the new bundle up: the page reloads once for the newer bundle, after the chat pane has caught up (the reload core's rule).
- Two readers of the drift verdict: the hosts row (`/tunnels` payload: `outOfDate`, `behindBy`, `aheadBy`, `kernelSha`; ui/webview/strip.ts draws "behind N commits" and the Update offer) and the automatic sync's ledger (`_set_auto_push` phases: asking, waiting, failed; `waiting` clears when the peer comes back "reporting our sha", and `_sync_notice` says "it is restarting").

## The rule

1. **The hub asks a restart only when the pull changed kernel code.** The peer's `/tunnels/pull` answer carries `kernel_code_changed`, the peer's own `_kernel_code_changed(running, pulled)` over the fast-forward it just did (the peer is the authority: its tree, its classification, its AST check). `_ask_peer_to_pull` reads it: true, ask the restart as today; false, no restart, and the detail says the peer converged in place. When the field is absent (a peer older than this line) the hub computes the same verdict over the two commits it holds (the peer's booted sha and its own HEAD, both in the hub's repository); when that cannot be read, the restart is asked, the safe converge, as every converge rule in this file falls.
2. **Drift is measured on the checkout, restart pending on the code.** `/version` gains `checkout_sha` (the checkout's HEAD, read fresh) beside `kernel_sha` (the booted commit) and `restart_pending` (the peer's own `_kernel_code_changed(booted, checkout)`: its checkout holds kernel code its process does not run). The hub's poll stores both on the row. `_remote_out_of_date` reads the CHECKOUT sha against the hub's HEAD: a push or a pull would change what is on the peer's disk. A peer whose checkout matches is not behind, whatever it booted from. When `checkout_sha` is absent the booted sha stands in, as today.
3. **The hosts row says which.** A peer behind on its checkout reads "behind N commits" as today. A peer whose checkout matches but whose `restart_pending` is true reads "up to date, running older code" with the restart offered (the Update action becomes a restart ask for that row); a peer with neither reads "up to date". The automatic sync's `waiting` phase ends when the peer's checkout matches the hub's HEAD, the event a pull produces, not when its booted sha does; the notice says "it pulled" or "it pulled and is restarting" by the pull answer's verdict.
4. **Nothing else moves.** The peer's in-place converge, the bundle rebuild, the dashboard's one reload for a newer bundle, the rail's Restart button (which asks every row by design) and the push direction's own restart step (`_update_remote`, the hub's ssh onto a remote it drives) keep their behaviour; the push direction gets the same `kernel_code_changed` test in a later line if the numbers ask for it.

## What the user sees after this

A docs or tests merge: nothing on any machine but the hub's own in-place converge. A UI merge: the laptop kernel rebuilds its bundle in place and the dashboard reloads once, after the chat pane has caught up, no socket drop. A kernel merge: the restart as today, invisible when the code the page runs is unchanged, one reload otherwise.

## The measurement

The laptop kernel's `restart-cuts.jsonl` and `restart-audit.jsonl` (read through local_misc, read only): after the fix, an evening of merges shows an `http-restart` row only after a merge that changed kernel code, never after a `main-converge-skip`; the count of laptop kernel restarts per merge falls from one to the share of merges that touch kernel/*.py (about a third on 2026-09-14). The hosts row for the laptop reads "up to date" within a poll of each docs or tests merge.

## Tests (red first at main)

- A hub over a peer whose pull answer says `kernel_code_changed: false` posts no `/restart`; over one that says true, posts it; over one whose answer lacks the field, computes the verdict from the two commits and posts only when kernel code changed (three hermetic peers with recorded answers, the hub's calls recorded).
- `/version` carries `checkout_sha` and `restart_pending`; `restart_pending` is false when the booted and checkout commits are one, true over a tree whose kernel/*.py moved on disk, false over a tree whose only moved files are tests and docs.
- `_remote_out_of_date` reads the checkout sha when the row holds one and the booted sha otherwise; the `/tunnels` payload and the hosts row carry the three states, and the automatic sync's `waiting` clears on the checkout matching.

## Roads not taken

- **Compare `code_ident` hub against peer.** Two machines at one commit run the same bytes, so it tempts; but the hub's own running code can lag its checkout (it converges in place too), and the test then says "different" for two machines that are both up to date. The peer's own booted-against-checkout verdict is the honest one, and only the peer can read its tree.
- **Let the hub skip the restart on its own classification and leave the row alone.** Cheaper, but the row would keep saying "behind N commits" for a peer that is up to date and merely running older non-code, and `_maybe_auto_push` would ask again on every pass: the loop this line exists to end.
- **Never ask a restart.** A peer would run old kernel code after a kernel merge until someone restarted it by hand; the restart is right when the code changed.
- **Batch or delay the restarts.** A quiet window already exists for restarts that cut turns; a timer would only spread the same drops out. The event that justifies a restart is a kernel-code change, and this line keys on it.

## The running-code identity (2026-09-15)

`restart_pending` no longer compares commits. The laptop's readout that day showed two hub-asked pulls that changed kernel code (13:11Z and 14:12Z) drawing no restart, against two others that restarted within eleven seconds, and the kernel running 1 h 52 min behind its own checkout. The running commit (`_kernel_sha`) is resolved lazily: a first read that fails at a busy boot (that kernel booted inside a 39 s sleep wake) is taken again later, and by then the checkout had been pulled, so the read named the pulled head as the running one and the verdict compared the checkout with itself.

The verdict now reads the code: the identity of the kernel/*.py this process loaded, taken at import before any pull can move the files (`_code_ident`, the hash `/version` already carries for the reload core), against the identity of the kernel/*.py on disk now (`_checkout_code_ident`, keyed on the files' stats so a poll costs a stat per file). Byte for byte: a comment-only edit reads pending too, since the converge's AST tolerance belongs to the self-converge, which judges commits, and here the fact reported is a byte the process does not run. No git on either side, so a git flake cannot latch a wrong answer and the memo, retry bound and prefix keys of the commit comparison are gone with it. A forced identity (`ROMP_CODE_IDENT`, a lab's stand-in) claims nothing. The running commit stays what `/version` and the hosts row display.
