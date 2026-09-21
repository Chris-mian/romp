# The Artifacts pane (2026-09-19)

An optional pane, off by default, experimental: a session picker at its top and, under it, every file that was put
into that session's thread, as a file list, and for images a grid of BIG thumbnails, so that when a session produces a
run of plots the user can open the pane and cycle through them large. Nothing is injected into any session and no
instruction changes: this is an on-top read of what already happened, by deterministic rules only (no judge, no model
call). The user asked for it on 2026-09-19; the manager dispatched the design first.

This document records the decisions the code follows. Every premise below was checked in the code it names.

## 1. What "put into the thread" means: three rules, each with its source record

A file belongs to a session's artifacts when one of these rules names it. Each rule reads ONE record the kernel already
parses; nothing new is written anywhere.

1. **Written by the session.** An assistant turn's `tool_use` block whose `name` is one of the edit tools and whose
   `input` carries `file_path` (Write, Edit, MultiEdit) or `notebook_path` (NotebookEdit). The record is the transcript's
   assistant message content, the same read `_session_meta_step` makes for `lastEditPath` (`kernel/kernel.py`, the
   `_EDIT_TOOLS` set); the pane reads the same blocks over the whole thread instead of keeping the newest. A path is taken
   as the tool received it (absolute as Claude Code writes them); a relative one resolves against the session's cwd the
   way a click does (`_resolve_open_path`).
   *A road not taken:* Bash is NOT parsed. A `Bash` tool's `command` can create files a hundred ways (redirects, `tee`,
   `cp`, a script that writes), and guessing which words of a shell line are output paths is a heuristic that would be
   quietly wrong (CLAUDE.md: never a lossy reconstruction where the record is not authoritative). A plot a session makes
   through a script shows up under rule 2 when the session names it in its prose, which is what a session that wants the
   user to see a figure does.
2. **Rendered by the chat from the session's prose.** A bare path in assistant text that the chat renders as a figure or
   links as a file: the path-token walk of `ui/webview/path-links.ts` (`linkifyPathTokens`, the same matcher every surface
   imports) over the assistant turn's text, narrowed to what the kernel stat'd when the event carries a `pathLinks`
   verdict, and, for images, the figure rule of `render.ts` (a token whose `previewKind` is `img` renders full-size at
   its mention through the file route). The kernel side of this pane applies the same token rule to the assistant text
   of the parsed turns (`kernel.py`'s `_PREVIEW_IMG_RE`, built from `_IMG_MIME`, for image paths; the path-links grammar
   for other files), so a figure the chat showed is an artifact and one it did not is not. A `file://` URI names an
   absolute path and counts the same way.
3. **Dropped into the chat by the user.** A file dropped or pasted on the composer is saved by the kernel under the state
   directory's `drops/` (`_save_dropped_file`: `<millis>-<safe name>`) and its saved path enters the user's message: as
   an image block's source path or as a bare path in the text, both of which the user-turn image scan (`_user_images`)
   already reads. The pane reads the same user turn: a path under `STATE/drops/` in a user turn is an artifact the user
   put in, attributed to the turn that carries it.

Every rule yields `(path, t, via)`: the path, the time of the turn that mentioned it, and which rule (`write`, `edit`,
`multiedit`, `notebook`, `rendered`, `drop`). A secrets-shaped name or a path outside the session's folder and the user's
home is listed but marked `refused` with the file route's own reason (`_slice_allowed`), never fetched: the pane shows
what the thread named, and the route decides what it will serve, as it does for the chat. A path under the Claude
configuration directory (`CLAUDE_CONFIG_DIR`, else `~/.claude/`) is marked `refused` by the pane's own rule ("under the
Claude configuration directory"): a thread names its own transcripts, task stores and settings, and they are not its
files. The shared route does not refuse them (home is a confinement root) and is not widened here: its confinement is
the chat's contract for every path link, and changing it is the user's call, not this pane's (round two, 2026-09-19).

## 2. The list

- **Newest first, one entry per path.** Entries are de-duplicated by resolved path; the LATEST mention wins (its time,
  its rule), so a file written three times is one row dated by the last write, and a plot the session wrote and then
  named in its prose is one row whose rule is the later mention.
- **A missing file is shown as such, never hidden.** The kernel stats every path at request time (a regular file or
  not, its size, its mtime); a path that no longer exists (deleted since, or written on another machine) stays in the
  list with a "missing" mark and no thumbnail. Hiding it would silently drop a fact the thread states.
- Each entry: `{path, name, t, via, exists, size, mtime, kind, refused}`; `kind` is the file route's view kind
  (`image`, `pdf`, `markdown`, `code`, or `other`), the pane's grid rule below reads it. A drop's `name` is the name the
  user dropped (the saved file's millisecond prefix stripped), and a drop is the user's own file: allowed wherever the
  state directory lives, the secrets rule and the kind rule still applying.
- The list is capped at the newest 500 entries (a session that writes thousands of files is a build, not a thread of
  artifacts); the cap is stated on the page when it binds, like the notice store's live-keys cap.

## 3. The page

A single page served at `/artifacts`, built like the Files pane's (`_files_page`): the theme stylesheet, its own small
stylesheet, the pane shim (`_shim("artifacts", v, no_stale=True)`: this page receives no pushed view), `federation.js`
for host routing, and one bundle `ui/webview/artifacts.ts`.

- **The picker and the lock** at the top (pass two, section 9, superseding the first landing's native `<select>` over the
  picker's list): a button wearing the selected session the way the tab strip wears a tab (the host prefix in the quiet
  `.host-prefix` dress, the name bold in its identity colour, `hostNameNodes` of `ui/webview/host-prefix.ts`), which opens
  a `ctx-menu.ts` card listing exactly the sessions OPEN in the chat panes of this dashboard (every column's tabs, local
  and remote, the shell's `chatTabs` broadcast), one row per session in the same dress; beside it the lock (the Sessions
  pane's padlock glyph). Unlocked, the pane shows whatever came last, a pick from the list or the most recently selected
  chat tab (the shell's `activeChat` relay); locked, it stays on the picked session; only the lock button changes the
  lock. The lock and the picked session are remembered per browser
  (`localStorage`, keys `romp:artifacts:sid` and `romp:artifacts:lock`). A page with no shell (opened alone) has no tabs to
  list and falls back to the picker's list (`requestSessions`), the first landing's behaviour.
- **The list and the grid.** Under the picker, the images of the selection (`kind === "image"`, existing, not
  refused) render as a grid of large thumbnails (a minimum of 220 px a side, three across at the pane's default width,
  `object-fit: contain`, newest first), each loaded through the file route with the session's sid, lazily
  (`loading="lazy"`). Below the grid, every entry as a file list row: the name in the link dress, the folder dimmed, the
  rule as a small word, the time as the chat's relative age, a missing file struck through with "missing" beside it, a
  refused one with the route's reason as its title. A row click on a file opens it in the Files pane when that pane is on
  screen, else in this document's viewer, the chat's own ladder (`ui/webview/file-route.ts fileLinkRoute`).
- **The large view.** A thumbnail click opens the image large IN PLACE (over the pane, the chat's lightbox dress), with
  left and right (the keyboard's arrows too) cycling through the grid's images in list order, the file's name and rule
  under it, Escape closing. One control sends the image to the Files pane's viewer: the shell's `viewFile` relay
  (`window.parent.postMessage({romp:'viewFile', path, sid, pane:'pane'})`, the same message a chat file link posts), which
  brings the Files pane forward and opens the file there; where no Files control exists (`avail.files` false in the
  pane-set broadcast) the control is hidden.
- **Thumbnails and the large view read the existing token-authed file route** (`/file?path=&sid=`, `fileUrl` in
  `ui/webview/preview.ts`, host-routed for a remote session), never a new file server. No pin: the pane shows the file
  as it stands now, and says "missing" when it does not.

## 4. The kernel's side: lazy, request and response, through the parse cache

- One WebSocket op, `listArtifacts {sid, reqId}`, answered on the asking socket with
  `artifactsListing {reqId, sid, items, capped, error}` by the kernel that owns the session (federation routes by the
  sid, as `listDir` is routed for the Files pane). No listing is pushed: an off pane costs nothing; a pane that is on and
  shows a session costs one request per selection and one per growth of that session's transcript. Growth reaches the
  pane as a SIGNAL, not a view (pass two, section 9.4): the pane names the one session it shows (`watchArtifacts {sid}`,
  one per socket, replacing the previous) and the owning kernel sends `artifactsChanged {sid, version}` from the pusher
  cycle when that session's transcript version (its file's mtime and size, the same first component the chat build's
  signature reads) moved since the last signal to that socket; the pane then re-asks. The first landing's Refresh
  control is gone; the page still re-asks when the shell's pane broadcast turns it on screen with a stale listing.
- The kernel reads the session's parse through the existing store: `_parse_cached(path)` first (the cached parse under
  the live key, never a parse); when that misses (a cold kernel, a session no chat has opened), `jd.parsed_session(sid,
  [path], now)` once, into the same shared cache every other reader uses, so the next request and the chat's own build
  find it warm. The transcript path is the session's row (`_session_row`, the resolution the chat's own build uses; the
  picker itself enumerates nothing, it lists the chat columns' open tabs), forks included as the chat includes them.
- The walk is one pass over `turns[].atoms[]`: assistant blocks for rules 1 and 2, user blocks and text for rule 3; then
  the de-duplication, the stat, the route's verdict, the sort and the cap. Since pass two the walk is INCREMENTAL per
  session (section 9.4): an in-memory memo per sid keeps the mentions map and the identity of the last turn walked
  (its position, its fork-stable turn id, its atom count and its last atom's uuid), and a request after growth walks from that
  turn on (the last walked turn may have grown; a rewind inside it walks the session whole), hydrating only
  those, merging into the map (the latest mention still wins); a parse whose turns no longer carry that prefix (a full
  re-assembly rather than a fold) is walked whole again. The stat and the route's verdict run over every entry on every
  answer (a file can appear or vanish between growths), which is at most the cap.
- Nothing is written: no store, no index, no ledger. The walk memo lives in the kernel's memory, dies with it, and is
  rebuilt from the parse on the next request. The pane's "state" is the browser's remembered selection and lock.

## 5. The shell hooks: a new app key, hidden by default, one place each

> **Since panes-as-data phase three (PR 1922)** the pane is a code record in the kernel's `_CODE_PANES` (`id`
> `artifacts`, experimental, off by default) rendered by the GENERIC pane build, and the gear's generic Panes row is
> its control: `showArtifactsControl` and the hand-written hooks this section names (the `_PANE_ORDER` entry, the
> `po-artifacts` line, the `gv-d` gutter, the `f-artifacts` iframe, the frame lists) are the FIRST landing's, kept
> here as history. The iframe still takes its `src` only when the pane comes on screen (PR 1911 round two, M2), now
> by the generic build's gate (`plans/panes-as-data.md`, section 7 item 3). Section 7 below, where it names the
> registry as coming, is likewise overtaken.

The pane is an app key `artifacts` in the shell's pane set (`kernel.py _PANE_ORDER`, entry `("artifacts", "Artifacts")`),
so today's toggle control shows and hides it with no new mechanism:

- **The rail's toggle and the phone's tab** come from `_PANE_ORDER` (`_rail_buttons_html`, `_mtab_buttons_html`); the
  landing's `LBL` map gains its word, the `po-artifacts` body class is toggled in `apply()` beside the other five, the
  landing's CSS gains its column (`#artifacts-pane{flex:var(--g-artifacts,40) 1 0}`, hidden without `po-artifacts`, a
  gutter beside it), and the row gains its iframe `f-artifacts`, served with `data-src=/artifacts` like the optional
  panes (never loaded until shown).
- **Hidden by default like the Files pane's flag.** A fresh setting `showArtifactsControl` beside `showFilesControl`
  (`ui/webview/settings.ts`: only the literal `true` shows; the gear's Panes section gains the row), read by the landing
  the way `filesCtl()` is: off, the rail button and the tab are hidden, an open pane closes on the same apply, and
  `togglePane('artifacts')` refuses. The kernel's own `/version` says nothing about it; the flag is per browser.
- **The shipped naming pattern, exactly** (the timeline owner's word, 2026-09-19, for the registry that folds a pane in by
  key and the docking engine that keys panes by element id): the pane element `artifacts-pane`, the iframe `f-artifacts`
  with `data-src`, the body class `po-artifacts`, the grow variable `--g-artifacts`, the `_PANE_ORDER` entry with its
  `LBL` word; the pane-set broadcast carries the key from `_PANE_ORDER` for free. The docking engine
  (`ui/webview/pane-dock.ts`, on only under the gear's docking switch) lists the four dashboard panes by name today, so
  this pane shows, hides and orders through the shipped flex path and becomes a leaf of the docking tree only when the
  registry PR reads the pane set from `_PANE_ORDER`; that is the registry's change, not this one's. Under the docking
  switch today the pane element is not in the tree, so it renders at 0 by 0 while its toggle reads on (no throw, no
  broken layout; the registry's phase two lifts it).
- **Self-contained by protocol.** The page and the shell exchange only the pane protocol: inbound `{romp:'panes', on,
  avail}` (the shell's broadcast, so the pane knows whether the Files pane is on screen and whether its control
  exists) and outbound `{romp:'viewFile', ...}` (the existing relay). Its kernel traffic rides its own shim socket
  (`listArtifacts`, `requestSessions`). The timeline owner's coming panes-as-data registry (a pane defined like a board)
  will fold this pane in by its key and route; nothing here reaches into another pane's document.
- The viewer set that keeps the kernel's memory awake (`kernel.py`, the tuple of the five pane app keys beside the
  `viewer =` read in the conserve-memory check) gains `artifacts`, so a dashboard with only this pane open counts as a
  viewer.

## 6. Tests

Pass two's tests are listed in section 9.6; the first landing's are these.

- Kernel: `tests/test_artifacts_list.py`: the walk over a synthetic parsed session (two writes of one path keep the newest;
  a MultiEdit and a NotebookEdit path; a rendered image path in assistant prose; a Bash `command` naming a path yields
  nothing; a drop path in a user turn; a `file://` URI; a relative path resolved against the cwd), the stat and the
  missing mark, the refused mark for a secrets-shaped name and for a path outside the folder and home, the sort and the
  cap, the op's request and response shape and its sid routing, the pane key in `_PANE_ORDER`, the route serving the page.
- Pane: `ui/webview/artifacts.test.ts` on the pane's pure parts (the grid's kind rule, the cycle's order and wrap, the
  route ladder for a row click), and source pins on the shell hooks (the `po-artifacts` class, the iframe, the CSS, the
  setting).
- Served lab: `tests/test_artifacts_pane_served.py`: a hermetic kernel over one synthetic session in the notes-api world
  with a transcript carrying two written files (one since deleted), one rendered image path and one drop; the control
  turned on through the setting; the pane toggled on; the picker naming the session; the list's four rows newest
  first with the missing mark; the grid's thumbnails loaded through the file route; a click opening the large view and
  the arrows cycling; the `viewFile` relay posted to the shell; the pane toggled off; and, with the control off, no rail
  button and no request made (the off state costs nothing).

## 7. What stays out

- Any write: no export, no rename, no delete from the pane.
- Bash output paths (section 1), files a subagent wrote in its own transcript (a later rule, if asked), and files named
  in tool RESULTS (a `Read` of a file is not putting it into the thread).
- A pushed LISTING or a per-session index on disk (the growth signal of section 9.4 is a few bytes and the walk memo is
  memory only); a pin of the file's bytes (the chat's mention pins stay the chat's).
- Polling of any kind: the pane learns of growth from the kernel's signal (a compare the pusher's event-woken cycle makes, with
  the 0.5 s backstop that cycle already keeps; no timer of the pane's own), of tab changes from the shell's broadcast.
- The panes-as-data registry itself (the timeline owner's design); this pane is written to fit it.

## 8. Privacy

Synthetic fixtures only (`TESTHOST`, the notes-api world, invented paths and placeholder uuids); the lab's files are
minted under its own temp root; no real transcript or path is copied anywhere.

## 9. Pass two (2026-09-20): remote sessions, the open-tabs scope, the picker's dress, growth, the lock

The user tried the pane and asked for five things (paraphrased by the manager, 2026-09-20). Every premise below was
checked in the code it names, and each anchor below names the symbol (the line numbers of main at 10f33abb were dropped when the
pass landed; a symbol survives an edit, a line does not). The
invariants of sections 1, 2 and 7 hold:
deterministic rules, nothing injected, lazy, nothing written, the refused marks.

### 9.1 Remote sessions: the transport already works, only the selector never offered one

- The listing op is routed by federation to the kernel that owns the sid, client-side: `SCALAR_ID = ["id", "sid"]`
  (`SCALAR_ID`, `ui/webview/federation.ts`), `hostOf(msg.sid)` picks the host and the prefix is stripped before the send
  (`sendRemote`'s prefix strip, `federation.ts`), the remote host's own socket carries it (`sendTo`, `federation.ts`, spliced by the hub at
  `GET /remote/<host>/ws`, the hub's relay route in `kernel.py`), and the answer's `sid` comes back host-prefixed (`prefixInbound`,
  `federation.ts`), so the pane's "is this answer for my selection" check holds for a remote sid. Thumbnails and the
  large view already go through `fileUrl` (`ui/webview/preview.ts`), which rewrites the base to
  `/remote/<host>/file` with the bare sid, answered by `_remote_file` (`kernel.py`) over the tunnel.
- The one gap: the selector asked `requestSessions` with no `host` (`requestSessions`, `artifacts.ts`), which federation routes to the
  LOCAL kernel only (`routeOutbound`, `federation.ts`), and the local `_session_list` has no remote arm (`kernel.py`), so a
  remote session could never be picked. The chat's own picker asks per host (`requestSessions` per host, `render.ts`).
- The fix falls out of 9.2: the picker lists the OPEN tabs of the chat panes, and the chat strip already merges every
  attached host's tabs with their `host:` ids and prefixed names, so a remote session is listed, routed and served with
  no per-host request. `_artifacts_list` on the owning kernel is unchanged: it receives the bare sid it owns.
- The two-kernel lab (section 9.6) proves it end to end: a hub and a checked-in TESTHOST kernel (the remote file-preview
  lab's shape, `tests/test_file_preview_remote_served.py`), a session whose transcript and files live on the remote
  disk only, the hub's chat showing its tab, the pane listing it and loading its thumbnails through the hub's relay.

### 9.2 Scope: the sessions open in the chat panes, not the picker's thirty days

- Nothing in the shell carries the set of open tabs today (the map found none: column membership lives in
  `localStorage` `romp-chat-cols`, the split script in `kernel.py`, and the shell scrapes a column's DOM for its active tab,
  the same script); the chat posts one signal about its tabs, `{romp:'activeTab', id, nonce, gesture}` on every
  switch (`notifyActive`, `render.ts`), which the shell forwarded to the feed alone (`_LANDING_FOCUS_JS`, `kernel.py`).
- **The chat column posts its tab set.** `renderTabs` (`render.ts`) posts `{romp:'chatTabs', tabs}` to the shell,
  `tabs` the strip's MEMBERSHIP in strip order (`stripLists`: the kernel's order plus a just-arrived tab, less a closing
  one; never the display-narrowed subset, so the demo filter and a folded section do not scope another pane) narrowed
  to the tabs THIS column holds (`heldHere`, the chat split's partition, which the strip applies as a display rule; the
  follow lab caught the whole membership going out, the other column's sessions included), a subagent viewer and a
  provisional tab left out, as `{id, name, color}` (the id host-prefixed for a remote tab, the name as the strip shows
  it, the identity colour as `{bg, fg}` or null), only when the set, its order, a name or a colour changed (a signature
  compare, the way `activeTab` is deduped). The union over the columns is what the user sees open.
- **The shell unions and broadcasts.** The landing keeps one map, column id to its last posted set, unions the sets in
  column order and posts `{romp:'chatTabs', tabs}` to every pane iframe whose `data-protocol` is `romp` (the same
  `tell` that carries the pane-set broadcast, `_LANDING_COLLAPSE_JS`), on every change and on each pane iframe's load (the
  boot-order race the pane-set broadcast already covers, the load re-tell in `_LANDING_COLLAPSE_JS`). A column that closes drops its set. The
  broadcast joins the pane protocol's inbound set (`plans/panes-as-data.md`, section on the protocol), which the
  timeline owner has read.
- The pane's list is that union, verbatim: a session the picker knows but no chat pane shows is not offered; a stored
  selection that is no longer open stays selected (its listing stays readable) but is shown as "not open" in the button
  and offered nowhere in the list; the next tab switch replaces it when unlocked.
- Coordinated with the chat owner (2026-09-20): the message shape and the dedup are theirs to confirm; the change
  rides this branch.

### 9.3 The picker's dress: the strip's session row, the menu vocabulary

- One shared renderer for a session's label already exists and is what the strip uses: `hostNameNodes(name, id)`
  (`ui/webview/host-prefix.ts`, exported, side-effect free, imported by `files.ts` and `file-view.ts`); the strip paints
  the name bold in the identity colour through `--chip-bg` and `.colored` (the strip's label in `renderTabs`, `render.ts`; `.tab.colored .tab-label`, `styles.css`) and the
  host prefix quiet, italic, `0.86em`, weight 400 (`.host-prefix`, `styles.css`). The @-mention pop is the precedent for a session
  list in the menu dress: a `.ctx-menu` card, `.ctx-item` rows, the name through `hostNameNodes`, the highlighted row
  wearing `--menu-hover` so coloured names stay readable (the mention pop in `render.ts`, its rows' rule in `styles.css`).
- **A shared label helper.** `sessionLabelNodes(name, id, color)` joins `host-prefix.ts` beside `hostNameNodes`: the
  quiet prefix plus a `.session-name` span carrying the name, bold in the identity colour (a `--chip-bg` custom property
  and the `.colored` class, the strip's own tokens). The picker's button and rows use it; the strip, the mention pop and
  the Outline's private `nameInto` (`fleet.ts`) may adopt it later (the cards owner's call, asked 2026-09-20).
- **The card** is built with `ctx-menu.ts` (`menuCard`, `showMenuCard`, `ctx-menu.ts`): the menu tokens, placement
  under the button, dismissal, keyboard (arrows, Home, End, Enter, Escape) and focus return all shared, no hex outside a
  `var()` fallback (`ui/CLAUDE.md`, the menu rule). The current session's row wears the `--check-bg` mark. The page
  already loads `styles.css` (`_artifacts_page`, `kernel.py`), so the dress needs no new stylesheet beyond the button's own rule.
- The button reads as the strip's tab would, its name lifted to the T390 lightness floor (`--peer-ink-l`, the oklch line of
  `.session-name.colored`) so a dark identity colour stays legible on both themes where the strip's tab has its own fade
  rules: the dress above, a chevron, and the lock beside it; the identity dot of the
  first landing is gone (the colour is on the name now).

### 9.4 Growth: a signal from the kernel, an incremental walk, no polling

- Today growth reaches nothing but the chat: the pusher wakes on the backend's push (`_push_soon`, `kernel.py`), `_push_all` builds
  per app audience (`kernel.py`) and no audience names `artifacts`; the page's shim is `no_stale` (no pushed view,
  `_shim("artifacts", v, no_stale=True)` in `_artifacts_page`); the pane's only growth road was the Refresh button (`artifacts.ts`, gone since).
- **The watch.** The pane sends `watchArtifacts {sid}` when its shown session changes (and `{sid, unwatch: true}` for the
  previous session, on its own kernel, when it shows
  none); federation routes it by the sid to the owning kernel like `listArtifacts`. The kernel records the one watched
  bare sid on the client (`client["artifacts"]`). In the pusher cycle (`_pusher_cycle_jobs`, the stage `artifactsSignal`, `kernel.py`), for each live
  `artifacts` client with a watched sid, the kernel reads that session's transcript version, the `(mtime, size)` of its
  file (the first component of `_chat_build_sig`, through `_session_row`), one stat per cycle per WATCHED SESSION (a dict
  from sid to version, built once per cycle), and when it differs from the last version sent to a watching client (the
  compare and the stamp under that client's lock), sends ONE `artifactsChanged {sid,
  version}` frame (the version compare is the dedup; the watch op stamps the version at watch time, so the listing the
  pane asks for beside the watch is not answered by a signal for the same bytes). Nothing else is pushed; an unwatched
  session costs nothing;
  a pane off screen keeps its watch but re-asks only when shown again (it marks the listing stale on the signal). The
  request-and-response design stands: the listing is still asked for, and the signal is the event that says when.
- **Why a signal and not the listing itself.** The listing can be hundreds of entries with a stat each; the pane may be
  off screen or on another session by the time it lands; the signal is a few bytes and lets the pane decide. The
  request path also stays the one road for the first paint and for a selection, so there is one listing builder.
- **The watch survives the socket.** A socket (re)open mints a fresh client on the kernel, and its watch with it; the
  pane re-arms on every (re)open (the shim's `romp:wsup` for the local kernel, federation's `romp:hostRelayUp` for a
  host's relay), never on the shown session changing, and re-asks the listing, since a growth during the outage was
  never signalled (round two, the medium; with no Refresh control left, this is the recovery).
- **The incremental walk** (section 4, amended): `_ARTIFACTS_MEMO[sid] = {idx, tid, n, uuidN, mentions, cands, t}`, in
  memory, guarded by `_ARTIFACTS_MEMO_LOCK` (the op runs on the socket thread). `cands` holds rule 2's unadmitted prose
  candidates by absolute path, re-judged on every answer (`_artifacts_admit`), so a file named before it existed lists once
  it does; the map is bounded per session (`_ARTIFACTS_CANDS_CAP`, 64, the newest mentions kept), so a long session naming
  many never-created paths pays at most that many stats per answer, and a candidate past the cap is not re-judged. On a request
  the kernel reads the parse as today; if the memo's turn id is still the id of the turn at the memo's index (turn ids
  are fork-stable, `_turn_id` in `event_model.py`; a serve or a fold leaves every previously emitted atom in place,
  the fold and serve paths of `event_model.py`), it walks `turns[index:]`, the last walked turn INCLUDED (a turn keeps its id while it gains
  atoms, so a file written later in the same turn lives in a turn already walked: the verifier's probe of round two, one
  turn with two Writes listing the first alone), hydrating only those turns (`em.hydrate` takes the subset), and merges
  their mentions into the map (the latest mention wins; a re-walked mention is the same mention); otherwise it walks
  everything and replaces the memo. The items step (stat, verdict, sort, cap) runs over the merged map every time. A session no longer
  listed keeps a memo until the kernel restarts or the memo count passes a small cap (the least recently listed goes).
- The design rule this follows: an exact event (the transcript's version moved) over a time heuristic, read on the
  pusher's event-woken cycle; the pane never polls and the kernel re-walks only the last walked turn and what came after it.

- **Refusals** (asked for by the reviews of pass two). Nothing degrades silently; every road that cannot list says so:
  - A sid this kernel has no transcript for (`_artifacts_list` through `_session_row`) answers the error string "no session
    with that id has a transcript here"; a transcript that cannot be read answers "the session's transcript could not be
    read (…)" with the cause. The pane shows the string in place of the list (`.art-err`), the count blank.
  - Per row, `_artifacts_items` applies the file route's own confinement (`_slice_allowed`): a secrets-shaped name, a path
    outside the session's folder and the home, and any path under the Claude configuration directory (a thread's own
    transcripts and task stores are not its artifacts) mark the row `refused` with the reason; a refused row is listed
    dimmed with the reason in its title, has no thumbnail, and a click on it does nothing. A kind the preview does not show
    is an ordinary row (`other`), listed plain; a click says the viewer cannot show it (the note beside the count).
  - A session whose host is in federation's down set (the kernel's tunnel health) gets `hostDownNote` in place of the wait,
    repainted on the down set's own event (`romp-hosts`); its return re-asks (`rearm`).
  - A pane frame for a host federation holds no conn for yet is dropped there (`sendRemote`, no-conn); the pane defers its
    first ask to the relay's open instead of asking into the drop, and federation holds `watchArtifacts` and
    `listArtifacts` for the open once a conn exists (BOOKKEEPING).
  - A listing answer for an earlier selection (its `reqId` or `sid` not the current one) is dropped, never rendered.

### 9.5 The lock and the follow

- **Unlocked, the pane follows the most recently selected chat tab.** The seam exists for the feed (T410, T416): the chat
  posts `{romp:'activeTab', id, nonce, gesture}` to the shell on every switch (`notifyActive`, `render.ts`) and on its kernel
  socket, the shell forwards it to the feed as `{romp:'activeChat', ...}` (`_LANDING_FOCUS_JS`, `kernel.py`), the kernel records one
  active sid per window (`_ACTIVE_CHAT_BY_WID`; with two columns the later report stands,
  `_relay_active_chat`) and mirrors it to the window's feed clients and on a feed's `ready` (`_send_active_chat`,
  `kernel.py`). Pass two widens both roads to the Artifacts pane: the shell relays `activeChat` to every pane
  iframe with `data-protocol` `romp` (the feed included, as today), and the kernel sends its `activeChat` frame to the
  window's `artifacts` clients too (the relay's fan-out and the `ready` arm, the pane posting `ready` as the Files pane
  does), so a reloaded pane knows the focused session before any switch. The id arrives host-prefixed for a remote tab (federation's fan-out, `prefixInbound`),
  which is the id the listing needs.
- **Locked, the pane stays on the picked session; only the lock button changes the lock** (the manager's correction
  of 2026-09-20, paraphrasing the user, who wanted an unlocked pane to mirror whichever came last, a pick or a chat tab
  switch, and a locked pane to stay on its pick). So a pick never flips the lock: unlocked, a pick
  shows that session until the next tab switch replaces it (the follow continues); locked, a pick replaces the locked
  session and the lock stays on. The lock button beside the picker wears the Sessions pane's padlock (the glyph
  `_drawLockToggle` draws, `ui/romp-timeline-view.js`: the body and the two shackle paths, seated when locked and
  swung out when unlocked), accent when locked and faint when unlocked, with the same two-state tip; unlocking keeps the
  shown session until the next tab switch (no jump: nothing new was selected). The lock and the shown sid persist per
  browser (`romp:artifacts:lock`, `romp:artifacts:sid`); a fresh browser starts unlocked and following.
- The pure state machine is in `artifacts-model.ts` (`nextSelection(state, event)` over the events `activeChat`, `pick`,
  `toggleLock`, `tabsChanged`), unit-tested; the DOM reads it.

### 9.6 Tests added by pass two

- Kernel: `tests/test_artifacts_list.py`: the watch op recorded per client and the `artifactsChanged` signal sent once per
  version move from the pusher cycle (a second cycle with no growth sends nothing; a growth sends one); the incremental
  walk (a memo whose turn id, atom count and last atom still stand walks from that turn on, hydrates only those, and merges with the latest
  mention winning; a prefix that changed walks whole); the active-chat frame reaching an `artifacts` client on its
  `ready` and on the chat's switch.
- Refusals: `tests/test_artifacts_list.py` Listing (a refused name and path, the Claude directory, kind other; the unknown sid's
  error string); `tests/test_artifacts_remote_served.py` (the down host's note, the deferred first ask's frame order).
- Pane: `ui/webview/artifacts.test.ts`: the selection machine (follow, a pick never changes the lock, toggle, unlock keeps the
  shown session, a closed tab); the listing signature; the echo watermark (relays A, B, C, then B's echo dropped);
  the picker's row model over a `chatTabs` union (order kept, duplicates across columns collapsed, a stored selection
  not open marked); pins on the shared label helper and the ctx-menu card.
- Served labs: the two-kernel lab for remote sessions (9.1); the scope lab (two chat columns holding two sessions, a
  third session the picker knows but no column shows: the list names exactly the two, in column order); the dress lab
  (computed styles: the card's background is the menu token's value, the row's host prefix italic and small, the name
  weight 600 in the session's identity colour); the growth lab (a new Write appended to the shown session's transcript
  lists its file with no click, and no Refresh button exists); the lock lab (unlocked, a chat tab switch moves the pane,
  and a pick is replaced by the next tab switch; locked, a tab switch leaves it and a pick holds; the lock survives a
  reload).
- Red first per test at the base, on behaviour (the op unanswered, the row absent, the style unchanged, the button
  present, the pane not following).
