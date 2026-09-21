# Panes as data: the pane registry

Status: PROPOSED, phased. Landing commits: TBD per phase. Tier: `feature` per phase (section 7); the one road
that would change a persisted record is named there and avoided.

A design line for an ask on the user's list (the user, 2026-09-19, paraphrased: panes should be totally
customizable, so someone can make their own pane that does whatever they want; today the set is fixed, chat,
feed, outline, the sessions band and files, and the user can only show, hide and order them; they want the
same control to ADD custom panes and show them). It follows the pane docking kit (`plans/pane-docking.md`,
phases one and two landed) and the card boards (`plans/card-boards.md`, whose registry door this copies field
for field). Line references were verified at `upstream/main` on 2026-09-19; cite by symbol first.

## 0. The premise, in code: five constants and their echoes

There is one list of panes and it is a constant: `_PANE_ORDER` in `kernel/kernel.py` (`(("chat","Chat"),
("timeline","Sessions"), ("fleet","Outline"), ("feed","Feed"), ("files","Files"))`). Five things render
from it directly, the rail's toggles (`_rail_buttons_html`), the phone's tabs (`_mtab_buttons_html`), the
WebSocket drop row, the bell's pane-label map (`PN` in `_LANDING_ERRS_JS`) and `_pane_label`. The rest of the
shell repeats the five keys by hand:

- the markup, five `<div class=pane id=<key>-pane><iframe id=f-<key> src|data-src=/<key>>` lines in
  `_landing`, the optional three served with `data-src` (the pane controller copies it to `src` once);
- the column CSS per key (`#<key>-pane{flex:var(--g-<key>,N) 1 0}`, `body:not(.po-<key>) #<key>-pane
  {display:none}`) and three gutters `gv-a`, `gv-b`, `gv-c` with hand-written neighbour picks in
  `_LANDING_JS` (`gutter(gid, leftPick, rightId)`: the outline when shown else the chat, and so on);
- the visibility defaults `po = {chat:true, fleet:false, feed:true, timeline:true, files:false}` and the
  broadcast keys `KEYS` (`_LANDING_COLLAPSE_JS`, baked into the landing string AT IMPORT from `_PANE_ORDER`);
- the grow defaults `grow = {chat:60, fleet:34, feed:40, files:40}` (`_LANDING_JS`);
- the focus map `PANE = {'f-chat':'chat-pane', ...}` and the column list `COLS` (`_LANDING_FOCUS_JS`);
- the gear's Panes rows (`gear.js`: `rs-pane-timeline`, `rs-pane-fleet`, `rs-pane-feed`, `rs-filesctl`,
  `rs-panedock`) and the settings store's `PaneSet` (`settings.ts`: exactly `timeline`, `fleet`, `feed`;
  `OPTIONAL_PANES`), the availability layer above the rail (the user 2026-09-10);
- the Files control's own setting (`showFilesControl`, read as `filesCtl()` in the shell and shipped as
  `avail.files` in the pane-set broadcast; `file-route.ts` routes a file link by `panesOn.files` and
  `panesAvail.files`);
- the routes (`/feed`, `/fleet`, `/files`, `/timeline`, each its own page builder around `_shim(app)`),
  the pusher's view audiences (a pane app named in code gets pushed views; any other app on the socket gets
  keepalives and its own ops' replies, as the Files pane and the gear do), the conserve-memory viewer set;
- the docking kit's lists: `growKey`, `defaultDock` (`pane-dock.ts`; the row order is read off the DOM, the fixed `ROW_ORDER` list retired 2026-09-21), `paneTitle`
  (`panedock-main.ts`), and the grab detector's per-app empty backgrounds (`pane-grab.ts` `EMPTY_BY_APP`).

What the user can do with this: show or hide a pane (the rail, `romp-panes`), decide a pane's membership in
this browser (the gear's Panes rows, `romp:settings.panes`), size it (the gutters, `romp-pane-grow`) and,
with the docking kit on, arrange the panes (`romp-layout`). Nothing adds a pane. A new pane is a code change
in every place above; the artifacts pane the feed owner is building (`plans/artifacts-pane.md`) touches each of
them once, the Files pane's pattern, which is exactly the cost this design removes.

The precedent for "as data" is the board registry (`plans/card-boards.md` sections 1 and 3, landed): one
schema for code and data (`_board_check`, run on the code constants at import and on every define), one
write door (`define_board`, an atomic write of `STATE/boards/<id>.json`, reserved ids refused), three
callers (in process, `POST /board` behind `_authorize`, `romp board define|list|show|remove`), a memoized
reader on the directory's stat (`_boards()`), and code winning an id collision the door prevents.

## 1. The model: a pane is a record

**Decision: a pane is a definition in ONE schema; the shipped panes (six since the Artifacts pane, 2026-09-19) are code constants in that schema
(an id the shell's derived element names already take, `tl`, `a` to `d`, `ghost`, `col`, or one beginning `chat-`, is refused at
the door since 2026-09-21; a pane file already written under such an id is skipped at the next listing with one stderr line
naming the file and the rule, the fail-loud convention, and its page is gone from the dashboards until it is re-defined under
another id)
and every other pane is a JSON document in the same schema under the state root.** The renderer of the
shell (the rail, the tabs, the markup, the CSS, the broadcast, the gear) is a function of the list.

```
Pane {
  id: string           // [a-z][a-z0-9_-]{0,31}; the shipped keys (chat, timeline, fleet, feed, files) and
                       //   "settings" are reserved (a define of one is refused)
  title: string        // <= 24 chars (a rail button, a phone tab, the palette's word); default: the id with
                       //   its first letter upper-cased. Never a resting title bar (the docking plan, section 3)
  source: Source       // where the page comes from (below)
  on: boolean          // whether the pane is shown by default in a browser that has made no choice for it yet
                       //   (the rail's romp-panes default); default false
  experimental: boolean   // default false. Listed under the gear's Panes with the word "experimental" and OFF
                       //   in that browser until the row is checked (the availability layer); no phone tab
  protocol: "romp" | "none"   // default "romp" for a route or a state-root page (the shim is served, the
                       //   pane-set broadcast is heard, the page may post to the shell); "none" for an external
                       //   URL (a plain iframe the shell only places)
}
Source = "/<route>"            // a kernel route the kernel already serves (a code pane's page, the feed owner's /artifacts)
       | "pane:<id>"           // a static page under the state root: STATE/panes/<id>/index.html, served at /pane/<id>/
       | "https://..." | "http://..."   // an external page; protocol is forced to "none"
```

A definition is a JSON object of exactly these members (an unknown member is a refusal naming it). One
function checks it, `_pane_check(defn) -> (defn, error)`, run on the code constants at import (a drifted
constant fails the suite) and on every define; every refusal is prose naming the member and the rule. The
code panes are `_CODE_PANES`, the five records with `source` their routes and `on` today's `po` defaults
(`chat` on, `timeline` on, `feed` on, `fleet` off, `files` off), so `_PANE_ORDER` becomes a derived tuple
(`tuple((p["id"], p["title"]) for p in _pane_order())`) and nothing that reads it moves.

Two things the record does NOT carry, on purpose: a **size** (the grows and the tree are the browser's,
`romp-pane-grow` and `romp-layout`; a pane arrives at a fair grow as a re-shown pane does today,
`__rompGrowFair`, or at its default dock under the kit) and a **rank** (the rail order is the code panes in
`_PANE_ORDER`'s order, then the data panes by id; the user arranges with the kit's drag, which is the one
ordering surface the plan has, section 9 of the docking plan). A `band` member (a full-width bottom band
like Sessions, a fixed-px kid in the tree) is a later phase (section 7), not a first-release member.

## 2. The store and its doors (the board door, field for field)

`define_pane(defn) -> (defn, error)` in `kernel/kernel.py` beside `define_board`: `_pane_check`, a
reserved id refused, `STATE/panes/<id>.json` written whole (the atomic replace the kernel uses for the
boards). Three callers, the board door's exactly:

- in process (a code pane never calls it; a producer inside the kernel may);
- `POST /pane` behind `_authorize`, the body the definition itself (`_read_post_body`,
  `_json_object_body`), the answers `/board`'s; `GET /panes` answers the current list, code and data, each
  with `source` and a `builtin: true` mark on the code five (the command's `list`, and a page asking what
  exists); `DELETE`-shaped removal rides `POST /pane/remove` with `{id}` as `/board`'s remove does;
- `romp pane define <id> (--from <path> | --json <text>) | list | show <id> | remove <id>` in `bin/romp`,
  on `romp board`'s mechanics (the token through `_romp_token_cfg`, one `romp pane: ...` line, `refused`
  naming the error with exit 1, usage errors exit 2).

A define REPLACES the definition. A remove is never refused for state the kernel cannot see (which
browsers show the pane is per-browser); a browser holding the pane on drops it on its next load, exactly
as an optional pane turned off in the gear leaves `KEYS` today. The store is read by `_panes()`, memoized
on the directory's stat (one stat per landing build), merged with `_CODE_PANES` (code wins an id
collision the door prevents), and `_pane_order()` is that merge in rail order.

**A define takes effect on the next dashboard load, and the open dashboards are OFFERED a reload.** The
landing is built per request from `_pane_order()` (section 3); nothing re-renders a live shell's pane
row, because the inline pane scripts read the markup once at load and every served-page pin holds that
markup. A define or remove bumps a pane-set revision `_panes_rev`, which rides every keepalive beside the
dist build token `dv`; the shim (`_shim`) treats a changed pane revision as it treats a changed `dv`: the
reload core OFFERS a reload through the shell's banner ("the pane set changed"), with Reload and Not now
(the user 2026-09-16's offer, never a self-reload). One mechanism, two reasons, the same bar.

## 3. The shell reads the list (the OFF path, today's flex row)

Every reader of the five keys becomes a reader of `_pane_order()`; with no data pane defined the code panes'
RENDERING is unchanged (the rail, the phone tabs, the pane row, the column and gutter rules, the gutter calls and
the body class, slice for slice against a stored rendering of the base; the page as a whole gains the guards and
the attribute reads, deliberately), which the source pins require (the inline `<script>` count of 21 in
`tests/test_kernel_mobile.py`, the exact substrings in `tests/test_kernel_pane_rail.py` and the split pins
in `ui/webview/chat-split.test.ts`) and a pin in this design's tests asserts outright.

- **The rail, the tabs, the drop row, the labels**: `_rail_buttons_html`, `_mtab_buttons_html`, the WS drop
  row and `_pane_label` already render from the one list; they render from `_pane_order()`. A data pane's
  rail button and tab appear after Files; an experimental pane gets no phone tab (section 1).
- **The baked constants leave import time.** `PN` (the bell's label map), `KEYS` (the broadcast keys),
  `PANE` and `COLS` (the focus map) are built into module-level strings at import from `_PANE_ORDER`. They
  read one JSON the landing emits as an attribute, `<body data-panes='[...]'>` (the list of `{id, title,
  protocol, experimental, on}` for the DATA panes), and the inline scripts parse it (`JSON.parse(document.
  body.dataset.panes)`) and EXTEND their baked five with it. The attribute carries every pane after the hand-written
  five (since phase three the Artifacts record rides it too, marked `builtin`), so with no data pane the hand-written
  panes' rendering is unchanged (phase one's first pin, re-cut deliberately at phase three);
  an attribute, not a script, so the inline count pin stays at 21 and no inline JS is added (the docking
  plan's section 10 rule). The three module-level strings keep their shape and their pinned substrings
  literal (the executed harnesses read them as constants); each gains a line that reads the attribute.
- **The markup and the CSS are generated from the list.** For each pane not among the code five, `_landing`
  emits `<div class=pane id=<id>-pane><iframe id=f-<id> data-src=<served source>></iframe></div>` after
  the Files pane (always `data-src`: a data pane loads when shown, the optional panes' rule; a URL source's
  iframe also carries `sandbox="allow-scripts allow-forms allow-popups"` and a `src` without `?v=`), and the
  stylesheet gains `#<id>-pane{flex:var(--g-<id>,40) 1 0}` and `body:not(.po-<id>) #<id>-pane
  {display:none}`. The code five keep their hand-written lines byte for byte.
- **One gutter rule for every pair.** Today three gutters carry three hand-written neighbour picks. The
  generic rule: a gutter sits before every column pane but the first, and its left neighbour is the
  rightmost SHOWN column pane before it in `_pane_order()`'s column order (the chat's side columns
  included, through `__rompLastChatPane`). The three shipped picks are that rule's answers for the fixed
  order, which the executed harnesses in `tests/test_pane_gutters.py` and `tests/test_pane_gutter_drag.py`
  hold: they must pass unchanged against the rewritten `gutter()`. A data pane's gutter is `gv-<id>`.
- **Visibility and grows**: `po`'s defaults come from each record's `on`; the broadcast `{romp:'panes',
  on, avail}` names every pane in the list; `grow` defaults a data pane to 40 (the Files pane's number),
  and a shown data pane takes a fair grow through the road a re-shown pane takes today.
- **Availability, the gear and the settings store**: the gear's Panes section renders a row per pane from
  the same `data-panes` attribute on the settings page (emitted there too; the code rows keep their ids
  and copy), a data pane's row wearing its title and, when experimental, the word "experimental";
  `settings.ts`'s `PaneSet` widens to `Record<string, boolean>` with `paneSet(v)` keeping every present key
  (only an explicit false hides one, as today) and `OPTIONAL_PANES` becoming the code three plus whatever
  the store holds; the shell's `reconcile` reads `romp:settings.panes[<id>]` for a data pane as it does
  for the optional three (absent means on for a normal pane, off for an experimental one). The Files
  control's `showFilesControl` stays what it is.
- **The palette**: the pane commands (`pane.<label>`) come from the list on the shell page.
- **The routes and the page**: a `source` that is a kernel route is served as today (the artifacts page's
  builder is the feed owner's). A `pane:<id>` source is a STATIC page under the state root: `GET /pane/<id>/`
  serves `STATE/panes/<id>/index.html` and `GET /pane/<id>/<path>` its files, with the `/dist/` route's
  traversal guard (`base.resolve() in fp.parents`) and its content types; two generated files ride beside
  it, `GET /pane/<id>/shim.js` (`_shim(id)`, so the page speaks the protocol by one `<script src>`) and
  `GET /pane/<id>/theme.css` (`THEME_CSS`, so it wears the dashboard's tokens). A URL source is a plain
  iframe with `protocol: "none"`: the shell places it and toggles it; it hears and posts nothing, and section 5
  says how the shell enforces that (the sandbox attribute, no token in any form, every handler checking the
  message's source frame and origin, the broadcast and the kit's injection skipping it).
- **The socket**: a `pane:<id>` page that includes `shim.js` dials `/ws?app=<id>`; the kernel accepts any
  app name today (`_new_ws_client(app)`), pushes no view to one outside the build audiences, and answers
  the ops it has (`openSession`, `viewFile`, `browseDir`, the gear's setters, ...) on that socket. A pane
  that wants a kernel op of its own needs the op in code, a release: the record cannot add one, and the
  design says so rather than promising a scripting surface (section 6).

## 4. The docking kit reads the list

The kit's own fixed lists become functions of the same attribute. `pane-dock.ts`: the row is read off the DOM
in document order (`reconcileShown` opens new panes in that order; the fixed `ROW_ORDER` list is gone since the
registry fix PR, 2026-09-21); `growKey(id)` is the pane's id for a data pane (the code five keep
their store keys); `defaultDock` docks a data pane at the right end; `reconcileShown`'s shown set is read
from the list's element ids. `panedock-main.ts`: `paneTitle` is the record's title; the frames it wires and
marks are every `.pane` in `.col`, already generic. The grab detector (`pane-grab.ts`): a protocol pane
declares its own empty background with `data-pane-empty` on its containers, a page-side attribute the
detector honours for ANY app before the per-app lists (the feed's, the band's, the outline's and the files
pane's lists stay as the code panes' declarations); a `protocol: "none"` pane has only the ring. The tree
(`pane-tree.ts`) keys leaves by id and needs nothing.

## 5. The pane protocol: the whole contract between the shell and a page

What a protocol pane page may rely on, and nothing else (a specific pane's other traffic is that pane's):

- **From the shim** (`shim.js`): `window.__rompApp` (its id), `window.__rompLocalSend(msg)` (a kernel op
  on its socket), every non-keepalive frame handed to the window as a message, the build-drift and
  pane-set reload offer, the `?v=` build token.
- **Inbound from the shell** (`window` messages): `{romp:"panes", on, avail}` (which panes are on screen
  and which exist), `{romp:"paneFocus", dir, from}` (a focus arrived by the shell's Alt+Arrow),
  `{romp:"chatTabs", tabs}` (the open tabs of the chat panes, the union of every chat column's strip in
  column order, `{id, name, color}` each, on every change and on the pane's load) and `{romp:"activeChat",
  id, nonce, gesture}` (the chat's most recently selected tab, relayed on every switch), both since the
  Artifacts pane's second pass (`plans/artifacts-pane.md` sections 9.2 and 9.5), and, with the docking kit
  on, the body class `pane-docking` and the injected grab detector (the docking plan, section 3).
- **Outbound to the shell** (`window.parent.postMessage`): `{romp:"notify", kind, text}` (a line in the
  shell's bell), `{romp:"viewFile", ...}` (the file relay to the Files pane, as the artifacts pane uses),
  `{romp:"ready"}`, `{romp:"paneGrab"}` and `{romp:"paneGrabEnd"}` (the detector's, section 4).

Everything else the shipped panes post or hear (`tabDrag`, `adopt`, `closing`, `activeTab`, `usage`,
`toggleFleet`, `hostsPending`) is a specific pane's business and is not part of the contract. A page that
loads `federation.js` may, but the manager pends only its four pane channels; a custom pane is not one.

**A `protocol: "none"` pane hears and posts nothing, and the shell ENFORCES it.** Intent is not enough: a
cross-origin page inside an iframe can still `postMessage` to its parent. So:

- every pane-protocol handler in the shell (`notify`, `viewFile`, `ready`, `paneGrab`, `paneGrabEnd`, the
  grab detector's channel, the focus relay's `paneFocus` answers, the pane-set broadcast's replies) accepts a
  message only when `e.source` is the `contentWindow` of a frame whose record has `protocol: "romp"` AND
  `e.origin` is the dashboard's own origin; a message from any other source is dropped without a reply. The
  check is one function, `_paneSourceOk(e)`, read by every handler, so a new handler cannot forget it;
- a URL-source iframe is rendered with `sandbox="allow-scripts allow-forms allow-popups"`, never
  `allow-same-origin` on our origin, so its page is a foreign origin whatever it loads;
- it never receives the token in any form: no `?v=` on its `src`, no `shim.js`, no `theme.css` (both carry
  the served build's token road), no message carrying a token;
- it is excluded from the pane-set broadcast's recipients (`tell()` skips it) and from the docking kit's grab
  injection (`markDoc` skips a frame whose record is not `protocol: "romp"`; a cross-origin document cannot
  be marked or read anyway, and the skip says so in the code rather than relying on the exception);
- it keeps the ring as its one grab surface (section 4) and toggles, docks and resizes like any pane.

The pin: `tests/test_pane_registry_served.py`'s URL-pane leg loads a URL-source pane whose page posts a forged
`{romp:"viewFile"}` and a forged `{romp:"paneGrab"}` to the parent (the lab's own page on a second local
origin): the Files pane opens nothing, the kit arms no press, the shell's bell shows no line, and the frame
carries the sandbox attribute and a `src` without `?v=`; `tests/test_pane_registry.py` pins `_paneSourceOk`'s
table (a protocol frame's window on our origin passes; a none frame's window, a foreign origin, the shell's
own window and a nested frame all fail: the check rules on the message's IMMEDIATE source, an iframe of the
shell document, so a frame nested inside a pane is not a pane and its page relays what it means to say). Every
shell listener, inline and bundled (the palette's `openKeys` and `hotkeyConfigure`, the docking kit's grab and
tab-drag messages), reads the one check FAIL-CLOSED: a page without the check acts on nothing; the same test
takes the census over the built landing, the bundles' sources and the built bundles.

## 6. Roads not taken

- **A per-browser pane list** (a `romp-panes.json` beside `romp-panes`, no kernel registry): a pane would
  not follow the user across browsers or machines, and a page under the state root needs the kernel to
  serve it anyway; the boards are kernel-side for the same reason.
- **The settings store as the registry** (`romp:settings.panes` gaining definitions): it is per-browser
  availability, not a definition; the two layers stay two, as the docking plan's section 0 has them.
- **A client-side shell** (a bundle building the rail and the markup from `GET /panes` at load): the
  inline pane scripts read the markup at load and every served-page pin holds it; a client render would
  re-lay every boot and break the pins for the code panes for no gain. The server builds per request and
  the open dashboards are offered a reload (section 2).
- **Plugins as kernel code** (Python loaded from the state root to add ops): a release per op stays; code
  from the state root is a surface the token model does not cover. A custom pane is a page, and its kernel
  traffic is the ops that exist.
- **A rank or a size on the record**: the kit's drag and the tree are the arrangement surface; a second
  ordering store would drift from it (the docking plan's one-store rule).
- **A band member in the first release**: the band is the tree's one fixed-px kid and the flex `.col`'s one
  bottom slot; a second band changes the seed and the column's CSS. Later (section 7).
- **Registering panes through the VS Code extension**: its panels are its own surface; the dashboard's
  shell is kernel-served, and the registry is the kernel's.

## 7. Phasing as pull requests

1. **The registry, its doors and the shell reading it.** `_pane_check`, `_CODE_PANES`, `define_pane`,
   `_panes()`, `_pane_order()`, `POST /pane`, `GET /panes`, the remove, `romp pane define|list|show|remove`,
   the `data-panes` attribute and the three baked constants reading it, the generated markup and CSS for a
   data pane, the one gutter rule, the gear's rows, the widened `PaneSet`, the palette, the `/pane/<id>/`
   static root with `shim.js` and `theme.css`, the pane-set revision and the reload offer. Tier: `feature`
   (additive: the code panes' rendering unchanged with an empty registry, pinned slice by slice; the old stores untouched).
2. **The docking kit reads the list** (section 4) and the grab detector's `data-pane-empty`. Tier: `feature`.
3. **The artifacts pane folds in** (DONE, joint with the feed owner): the feed owner's `artifacts` is a `_CODE_PANES`
   record (`{id: "artifacts", title: "Artifacts", source: "/artifacts", on: false, experimental: true}`), its
   hand-written hooks (the `_PANE_ORDER` entry, the label word, the `po-artifacts` class line, the column CSS, the
   `f-artifacts` iframe, every hand list) deleted for what the generic build emits (the generic build renders
   every pane after the hand-written five, `_HAND_PANES`), its `showArtifactsControl` mapped onto `experimental`
   (the gear's generic Panes row is the control; the bespoke key deleted, no migration), and a generic pane's iframe
   takes its `src` only when the pane comes ON SCREEN, never when merely enabled (the Artifacts page's first load
   walks the remembered session). Its page, its listing op and its bundle are untouched. Tier: `feature`, joint.
4. **Bands and the phone**: a `band` member (a second fixed-px kid; the flex `.col`'s bottom slot
   generalised) and experimental panes on the phone. Tier: `feature`; if the `romp-panes` store's SHAPE ever
   changed for this (today a flat `{key: bool}`), that is a persisted-contract change and a `major-feature`
   discussion; the plan avoids it by keeping keys flat. Recorded for it (the 1922 read, 2026-09-21): with the
   Files control on, the phone's tab bar is 403 px wide at a 390 px viewport, clipping the settings action,
   unreachable at 375 px or with a data pane's tab beside it; the options are a scrolling tab strip beside a
   fixed action cluster, or a content budget for the bar (shrink-with-ellipsis mangles the labels). Until then,
   on a phone a generic pane loads by its TAB alone (the registry fix PR, 2026-09-21): the tab bar's tap, or the
   pane controller's apply for the current tab; never by the desktop flag, and a pane with no tab (an
   experimental record) falls to the chat.

## 8. Tests named

- `tests/test_pane_registry.py`: `_pane_check` refuses every bad member and every reserved id with prose
  naming the member; `_CODE_PANES` pass the check at import; `define_pane` writes `STATE/panes/<id>.json`
  atomically and replaces; `_panes()` re-reads on the directory's stat and not otherwise; `_pane_order()`
  is the code five then the data panes by id; `GET /panes` marks the five builtin; `POST /pane` behind
  `_authorize` and the remove; `_landing()` with an empty registry rendering the code panes unchanged (the pin that
  keeps every existing landing pin honest), and with one data pane: the rail button after Files, the phone
  tab, the `data-src` iframe, the two CSS rules, the `data-panes` attribute, the inline `<script>` count still
  21; the pane-set revision bumps on define and remove and rides the keepalive.
- `tests/romp-pane.bats`: the command's usage exits, `refused` lines, `list`, `show`, `remove`, on `romp
  board`'s harness.
- `tests/test_pane_gutters.py` and `tests/test_pane_gutter_drag.py`: unchanged and green against the one
  gutter rule (their fixtures are the three hand-written picks' cases).
- `ui/webview/settings.test.ts`: `paneSet` keeps a data pane's key and hides only an explicit false;
  `ui/webview/pane-dock.test.ts`: row order, grow key, default dock from a list holding a data pane;
  `ui/webview/pane-grab.test.ts`: `data-pane-empty` honoured for an unknown app.
- `tests/test_pane_registry_served.py` (real pointer events where a gesture is measured): a pane defined
  before boot as a state-root page including `shim.js` shows in the rail and the gear, toggles on with its
  iframe loaded from `/pane/<id>/`, hears the pane-set broadcast (the page echoes it into a data attribute
  the lab reads), is named by the palette; a URL-source pane is a plain iframe with no shim; with the
  docking kit on the data pane is a tree leaf with a ring and can be dropped into a half-zone; a define at
  runtime bumps the revision and the shell shows the reload offer; the gutters pair as today for the code
  five (the harness's pairs) and the data pane's gutter pairs with the rightmost shown pane before it.

## 9. Risks and open questions

- **Byte identity for the code panes** is the whole safety of phase one: the generated lines are emitted
  only for data panes, and the landing test compares today's output to the new builder's with an empty
  registry. Any drift is a red, not a judgement call.
- **The gutter rewrite** touches `_LANDING_JS`, held by two executed harnesses; the generic rule must
  reproduce their pairs exactly, including the Files gutter's three-way pick.
- **Trust**: a `pane:<id>` page runs same-origin with the kernel's token in its shim, so a user-authored
  pane is trusted as the user's own code under their own state root; an external URL pane is sandboxed,
  cross-origin, gets no token and no protocol, and every shell handler checks the message's source frame
  and origin before acting (section 5). The design says which is which; it adds no third kind.
- **A define while dashboards are open** changes nothing on screen until the offered reload is taken; the
  phone's tabs likewise. Coherent with the build-drift offer; a live re-layout of the shell's pane row is
  the client-side road not taken.
- **The artifacts pane's key and hooks** are coordinated (with the feed owner, 2026-09-19): `artifacts`,
  `/artifacts`, the label Artifacts, the Files pane's hook pattern, so phase three's fold is a deletion of
  their hooks, not a rewrite of their page.
