# The Sessions pane's provisional row

**Status:** a design line for a read before code (2026-09-14). The pane side is romp_cards's; the gate side is romp_perf's (the cold-tab gate, PR 1659), who reads this line too.

## Why now

The cold-tab gate (`kernel.py`, `_push`'s build loop, "THE COLD-TAB GATE") builds no chat tab that no connected page is looking at and that every connected chat page holds as a skeleton; the page's click or its idle prefetch releases the skeleton and that push builds the tab. The gate stands down whenever a Sessions pane is connected: its condition carries `not want_fleet and not _any_sessions_pane`, because the pane's rows come from `feed["ledgers"]`, one entry per `build_session` result (`chat_sessions`), attached in `_push` right after the chat loop. The user's dashboard keeps the pane connected, so the gate's deploy boot skipped nothing: `builds.chat.coldSkipped` 0, 349 chat tabs built in the first 151 s, every connect push 60 to 74 s. The gate's saving on the user's own board waits on a row the pane can show for a cold tab without a build.

## What a row is today

A ledgers row (`_push`, the `feed["ledgers"]` comprehension) carries `sid`, `name`, `color`, `status`, the mail-off fields (`postalServiceOff`, `mailOffWhy`, from `_mail_off_fields`) and `ledger`, the build's ledger with `archivedTops` added. The build's ledger (`build_session`, the `ledger = {...}` dict) holds `summary`, `tree` (the first 80 nodes of the goal tree walk), `current`, `recent`, `workingNote`, `needsInput`.

The pane (`ui/webview/fleet.ts`, `FleetSession` and `render`) reads: `sid` (keys and actions), `name`, `color`, `mailOffWhy`; of the status only `state` (the pip: working, awaitingBg, unknown when the status is absent; blocked, retrying, compacting and closed have their own treatments and no pip); of the ledger `tree` (the goal rows, the folds, the marks, the hover card, the jumps), `current` (its `t` stamps the subtree's recency) and `archivedTops` (Show completed). It does not read `summary`, `recent`, `workingNote`, `needsInput`, nor any other status field.

## Which fields come only from the build, and what the provisional row shows

| Field | Today's source | The provisional row |
| --- | --- | --- |
| `name`, `color` | the live map's row (`m["name"]`, `m.get("color")`), the session's own record, the strip's | the same values; no build |
| `status` | the built status dict | `_light_status(sid, path, tm, now)`: the live row's word with blocked, awaiting and compacting from their cheap reads; `state`, `sinceEpoch`, `faded`, `needsYou`, `ctx`, `ctxOver`, the context colour and tone, the model and effort colours and tones, the awaiting fields, the API flags, the retry ladder, backend, model, effort, mode; `provisional: True`. The pane reads `state`, so the pip rule is unchanged. `None` when the live map has no row for the session: the gate builds then, as today, and the row is the built one |
| mail-off fields | `_mail_off_fields(sid)` | the same call; a postal record read, no build |
| `ledger.tree` | the tree walk (`_twalk`) over the goal store's nodes (`jd.load_goals_shared_or_fault`, `_apply_rewind_hold`), each node stamped with its deep-link anchors from the parsed transcript (`_node_anchor_uuids` over the trail segments: `promptAnchorUuid`, `anchorUuid`) | the same walk over the store alone: text, depth, marks, blocked, cleared, children, the agent-open flag; the two anchors `None`. The rows render as today; the jump actions (`goprompt`, `gowork`) are withheld on a provisional row, since there is no transcript position to land on until the tab is built. The walk moves into a helper the build and the provisional assembly share, with the anchor pass a parameter |
| `ledger.current` | `{"t": last_turn["t"]}` when the parsed transcript's last turn is open | the live row's `since` as `t` when the row says working (the backend's turn start, the same instant the parse would find), else `None`; the recency stamp follows it |
| `ledger.recent` | the store's live roots and `_archive_roots(sid)` | the same |
| `ledger.summary` | `jd.load_archive(sid)["headline"]` | the same |
| `ledger.workingNote` | `Sessions.working_note(sid)` | the same |
| `ledger.needsInput` | `_feed_needs_input_of(sid)` | the same |
| `archivedTops` | `_fleet_archived_tops(sid)`, a cached store read | the same |
| `provisional` (new) | absent | `True` on the row, beside the status's own flag |

Blank with a reason, then: the two anchors per tree node (no transcript position) and `current` for a session whose row is not working (no open turn to name). Everything else the pane reads is a value.

## How the pane learns a row went from provisional to built

The ledgers ride the feed frame whole, every cycle; the pane replaces its `sessions` from `m.ledgers` on each frame and renders. When a chat page's click or prefetch releases the skeleton, that push builds the tab, and the next cycle's `feed["ledgers"]` carries the built row in the same position, `provisional` absent: the ledger frame is the signal. The per-client dedup of the feed frame (`_send_client`, the frame's signature) sends it because a row changed. The status frame is the chat's channel, per tab, on the `("status", sid)` slot; the pane never rides it, and needs no slot of its own: one list, replaced wholesale, is the slot.

The pane marks a provisional row lightly, the way it marks the feed's provisional cards for a create in flight (`asks` rows with `provisional: true`): the same name and colour, the state's pip as today, the tree's rows drawn, the jump actions withheld with a title saying the session has not been opened since the restart. No loader: a provisional row is data, not a wait.

## The gate's condition

Today: no Sessions pane connected (`_any_sessions_pane`) and no pane in the push's audience (`want_fleet`). Proposed: the pane declares the capability at its dial, a query flag on the shared connect URL beside `app`, `delta`, `iid`, `wid`, `active` and the chat's `skeleton` (the kernel's landing script builds that query; the handshake reads `skeleton=1` into the client record), read into the client record as `provRows`. The condition becomes: no connected Sessions pane that lacks `provRows`. `want_fleet` alone no longer forces a build: for a skipped tab, `_push` appends a provisional row, assembled as above, to the ledgers in build order. An older pane (no flag) disables the gate as today; a mixed set, one old pane among new ones, disables it too. The gate's own rule is otherwise untouched: the watched tabs build, a warm tab is served from its cache, a session without a live row builds.

## The measurement

The next deploy boot's `/perf` (`romp perf`): `builds.chat.coldSkipped` and the view counter `chatSkipCold` above zero with the pane connected (0 today); `connect_push.byApp` for the chat and the pane, `ms_last` and `ms_max`, against today's 60 to 74 s; the first cycle's chat builds against today's 349 in 151 s, expected to fall to the watched tabs, one per chat column. A served lab states the same before the deploy: a dashboard with the pane connected over N cold sessions shows N rows at the first frame, each provisional, while the chat builds only its active tab (`coldSkipped` N minus 1); a click on a second tab builds it and its row loses the mark on the next frame; an older pane (no flag) makes the same boot build every tab.

## Order of work, one feature pull request

1. Kernel: the tree walk factored into a helper the build and the provisional assembly share (the anchor pass a parameter); `_provisional_ledger(sid, tm)` from the store reads above; the row assembly in `_push` for skipped tabs; the `provRows` flag at the handshake; the gate's condition. Kernel unit tests: a pane client with the flag over cold tabs skips them and ships provisional rows with the light status and the store ledger; a pane client without it builds every tab as today; a built tab's row replaces the provisional one on the next frame.
2. Pane: `FleetSession.provisional`, the light mark, the withheld jumps and their title; `fleet.ts` unit tests over both row kinds.
3. The lab above, and the deploy measurement read by romp_perf after the next boot.

## Open points for the read

- The tree's anchors: withheld (this line) or a store-only stand-in, the node's `mt` as a time to jump near? Withheld is honest; a near-jump can mislead.
- `current` from the live row's `since`: the same instant the parse would find for a live turn, or a blank with a reason? This line takes the value.
- The dial: a query flag like the chat's `skeleton=1` (this line), or a capabilities frame? The kernel's `caps` list is the kernel's own capabilities to the client; the client's declarations ride the query today, so the flag follows precedent.
