# The Outline pane's provisional row

**Status:** a design line for a read before code (written 2026-09-14, revised 2026-09-15 after the manager's and romp_perf's reads). The pane side is romp_cards's; the gate side is romp_perf's (the cold-tab gate, PR 1659).

**The pane, named exactly.** The pane that rides `feed["ledgers"]` is the OUTLINE pane: client app id `fleet`, module `ui/webview/fleet.ts`, the rail's label "Outline" (`_PANE_ORDER` in `kernel.py`). The Sessions pane is the timeline (app `timeline`), which never reads ledgers. Every mention below of "the pane" is the Outline pane; a flag wired into the Sessions pane would leave the gate inert exactly as today.

## Why now

The cold-tab gate (`kernel.py`, `_push`'s build loop, "THE COLD-TAB GATE") builds no chat tab that no connected page is looking at and that every connected chat page holds as a skeleton; the page's click or its idle prefetch releases the skeleton and that push builds the tab. The gate stands down whenever an Outline pane is connected: its condition carries `not want_fleet and not _any_sessions_pane` (the variable's name notwithstanding, it is the Outline's app id it tests), because the pane's rows come from `feed["ledgers"]`, one entry per `build_session` result (`chat_sessions`), attached in `_push` right after the chat loop. The user's dashboard keeps the Outline connected, so the gate's deploy boot skipped nothing: `builds.chat.coldSkipped` 0, 349 chat tabs built in the first 151 s, every connect push 60 to 74 s. The gate's saving on the user's own board waits on a row the Outline can show for a cold tab without a build.

## What a row is today

A ledgers row (`_push`, the `feed["ledgers"]` comprehension) carries `sid`, `name`, `color`, `status`, the mail-off fields (`postalServiceOff`, `mailOffWhy`, from `_mail_off_fields`) and `ledger`, the build's ledger with `archivedTops` added. The build's ledger (`build_session`, the `ledger = {...}` dict) holds `summary`, `tree` (the goal tree walk, capped at 80 nodes), `current`, `recent`, `workingNote`, `needsInput`; a session with `hideFromFeed` (the mute) has its `tree`, `current` and `recent` zeroed after the walk.

The Outline (`fleet.ts`, `FleetSession` and `render`) reads: `sid` (keys and actions), `name`, `color`, `postalServiceOff` and `mailOffWhy` (the quiet mail-off mark and its title); of the status only `state` (the pip: working, awaitingBg, unknown when the status is absent; blocked, retrying, compacting and closed have their own treatments and no pip); of the ledger `tree` (the goal rows, the folds, the marks, the hover card, the jumps), `current` (its `t` stamps the subtree's recency) and `archivedTops` (Show completed). It does not read `summary`, `recent`, `workingNote`, `needsInput`, nor any other status field.

## Which fields come only from the build, and what the provisional row shows

The provisional row carries what the Outline reads and nothing more: `sid`, `name`, `color`, `status`, `postalServiceOff`, `mailOffWhy`, `ledger` with `tree`, `current` and `archivedTops`, and `provisional: true`. The four ledger fields the pane never reads (`summary`, `recent`, `workingNote`, `needsInput`) are not assembled for a provisional row; each is a store or record read per session per cycle that would buy nothing on the wire, and the built row brings them back.

| Field | Today's source | The provisional row |
| --- | --- | --- |
| `name`, `color` | the live map's row (`m["name"]`, `m.get("color")`), the session's own record, the strip's | the same values; no build |
| `status` | the built status dict | `_light_status(sid, path, tm, now)`: the live row's word with blocked, awaiting and compacting from their cheap reads; `state`, `sinceEpoch`, `faded`, `needsYou`, `ctx`, `ctxOver`, the context colour and tone, the model and effort colours and tones, the awaiting fields, the API flags, the retry ladder, backend, model, effort, mode; `provisional: True`. The Outline reads `state`, so the pip rule is unchanged. This column applies to a tab with a live row only: `None` (no row in the live map) means the gate builds the tab as today, and its row is the built one |
| `postalServiceOff`, `mailOffWhy` | `_mail_off_fields(sid)` | the same call; a postal record read, no build |
| `ledger.tree` | the tree walk (`_twalk`) over the goal store's nodes (`jd.load_goals_shared_or_fault`, `_apply_rewind_hold`), each node stamped with its deep-link anchors from the parsed transcript (`_node_anchor_uuids` over the trail segments: `promptAnchorUuid`, `anchorUuid`); then the mute's zeroing and the cap of 80 | the same walk over the store alone through a shared helper: text, depth, marks, blocked, cleared, children, the agent-open flag; the two anchors `None`; the mute's zeroing and the cap applied inside the helper, so a muted session shows no goals and a provisional row never holds more rows than its built twin |
| `ledger.current` | `{"t": last_turn["t"]}` when the parsed transcript's last turn is open | `None`, with a reason: the live row's `since` is stamped at the queue pop, not at the transcript's turn start, and in the backgrounded-subagent branch the row says working while the turn is closed, so a value taken from the row would flip on the first build. The recency stamp of the subtree waits for the built row |
| `archivedTops` | `_fleet_archived_tops(sid)`, a cached store read | the same |
| `provisional` (new) | absent | `true` on the row, beside the status's own flag |

Blank with a reason, then: the two anchors per tree node and `current`. Everything else the Outline reads is a value.

## The anchors, withheld

The node's position exists in the store; what a cold tab lacks is the LANDING: the chat page holds no loaded history for it, and the kernel's focus road documents no fallback by time. So a provisional row's jump actions (`goprompt`, `gowork`) are withheld, and the withheld action's title says what the click cannot do ("nothing to land on until this tab is built"), not that the session was never opened. A near-jump on the node's time would mislead.

## The memo, parse-free

The build's ledger memo (`_ledger_memo`) keys on the parse object's identity and the store object's identity (`_lent[1] is parsed and _lent[2] is gstore`), so a provisional row can never hit it. The shared helper takes its own memo: per session, keyed on the goal store file's stat key and the archive's (the `_stat_key` idiom the build uses for `cleared.jsonl`), holding the store-only tree, capped and mute-applied. With the Outline connected the skipped set is every cold tab (349 at the last boot), and without this memo the pusher would walk 349 stores every cycle where today the build pays the walk once per built tab and caches it. On the gate's side, `_light_status`'s compact-boundary tail read runs per skipped tab per push and re-reads a growing suffix; romp_perf memoizes it per path, since and size and lands that memo on main before this pull request, which then carries it.

## How the Outline learns a row went from provisional to built

The ledgers ride the feed frame whole, every cycle; the pane replaces its `sessions` from `m.ledgers` on each frame and renders. When a chat page's click or prefetch releases the skeleton, that push builds the tab, and the next cycle's `feed["ledgers"]` carries the built row in the same position, `provisional` absent: the ledger frame is the signal. The feed frame's per-client signature moves on a one-row change, so the frame goes. The status frame is the chat's channel, per tab, on the `("status", sid)` slot; the Outline never rides it and needs no slot of its own.

The Outline marks a provisional row lightly, the way it marks the feed's provisional cards for a create in flight (`asks` rows with `provisional: true`): the same name and colour, the state's pip as today, the tree's rows drawn, the jump actions withheld with the title above. No loader: a provisional row is data, not a wait.

## The gate's condition and the two clients that hold an Outline

Two gate sites, one changes (romp_perf's read): the periodic push's clause in `_push` is the one the capability replaces; the handshake push's copy in `_push_session_now` gates on the chat clients' skeleton sets alone and never read the pane, so it stands. The ledgers attach in `_push` (`chat_sessions or want_fleet`) must include the provisional rows for the skipped tabs, in build order, or an Outline alone on the wire gets an empty list.

The capability is a query flag on the client's dial, `provrows=1`, beside `app`, `delta`, `iid`, `wid`, `active` and the chat's `skeleton`, read at the handshake into the client record as `provRows`, gated on its own app as the skeleton flag is (`skeleton` is read only when `app == "chat"`; `provrows` only when `app == "fleet"`). Two clients dial an Outline:

- the served dashboard's Outline frame, through the shared connect URL the kernel's landing script builds (`/ws?app=fleet&delta=1&iid=...`), which gains the term;
- the VS Code extension's Outline panel, whose host builds its own connect URL in `vscode-extension/src/extension.ts` (`/ws?app=${this.app}&wid=...&token=...`) with no query terms. It gains the same term for `app === "fleet"`, and its panel renders the provisional row through the same `fleet.ts` bundle. Without the term that panel would be a permanently unflagged Outline that disables the gate for the whole kernel while open.

The condition becomes: no connected Outline that lacks `provRows`. `want_fleet` alone no longer forces a build: for a skipped tab, `_push` appends a provisional row, assembled as above, to the ledgers in build order. An older Outline (a bundle from before the flag) disables the gate as today; a mixed set, one old pane among new ones, disables it too. The gate's own rule is otherwise untouched: the watched tabs build, a warm tab is served from its cache, a session without a live row builds.

## The measurement

The next deploy boot's `/perf` (`romp perf`): `builds.chat.coldSkipped` and the view counter `chatSkipCold` above zero with the Outline connected (0 today); `pusher.connectPush.byApp` for the chat and the Outline, `ms_last` and `ms_max`, against today's 60 to 74 s; the first cycle's chat builds against today's 349 in 151 s, expected to fall to the watched tabs, one per chat column. Both counters are cumulative across cycles, so the lab's numbers below are the first push's.

The lab to extend is `tests/test_cold_boot_diet_browser.py` (twenty-seven synthetic sessions, the served dashboard, the restart dial): with the Outline frame connected, the first refresh shows twenty-seven rows in the pane, each provisional, while the chat builds only its active tab (`coldSkipped` twenty-six on the first push); a click on a second tab builds it and its row loses the mark on the next frame; a muted session's provisional row shows no goals; an Outline dialing without the flag makes the same boot build every tab. The extension's panel is pinned at the source (the connect URL carries the term for the Outline app).

## Order of work, one feature pull request

1. Kernel: the tree walk factored into a helper the build and the provisional assembly share (the anchor pass a parameter; the mute's zeroing and the cap inside it), with the parse-free memo; `_provisional_ledger(sid)`; the row assembly in `_push` for skipped tabs; the `provrows` flag at the handshake, app-gated; the gate's condition. The source pins in `tests/test_kernel_fleet_ledgers.py` on the ledgers comprehension (`feed["ledgers"] = [{"sid": m["id"]`) survive, or are re-pinned deliberately with the reason in the pull request body. Kernel unit tests: an Outline client with the flag over cold tabs skips them and ships provisional rows with the light status and the store ledger; an Outline client without it builds every tab as today; a built tab's row replaces the provisional one on the next frame; a muted session's provisional tree is empty; the memo hits across cycles and misses on a store write.
2. Pane: `FleetSession.provisional`, the light mark, the withheld jumps and their title; the extension's connect URL term; `fleet.ts` unit tests over both row kinds.
3. The lab above, and the deploy measurement read by romp_perf after the next boot.

## The open points, closed

- The anchors: withheld, for the landing reason above.
- `current`: blank with the reason above.
- The dial: the query flag, app-gated, following the skeleton flag's precedent.
