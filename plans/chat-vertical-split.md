# Split a chat pane top and bottom (drag a tab to the bottom edge)

A design line for a feature on the user's list (open since 2026-09-12, unowned): drag a tab to the BOTTOM
edge of a chat pane to split it into a top and a bottom pane, the vertical counterpart of today's
side-by-side column split (drag a tab to the right edge to open a column). This doc decides the layout model,
the drop target, the divider, focus and the strip in a stacked pane, the kernel's part (nothing new to serve),
the served lab, and the risks. It is a `feature`: it needs the user's word after this doc. No code here.

All line references re-checked at main 4f93872d. That main includes PR #1754 (the scroll-back wall fix, which
added `silentActivate`, `shownTabForRelay`, `announceActiveToRelay` and the per-pane relay re-announce): that
fix is load-bearing for this feature, see section 6. The prior draft was pinned at 2b06e774 and its `kernel.py`
references have all drifted forward by roughly 430 to 660 lines; they are corrected below.

## 1. The premise, in code: the side split today

Dragging a tab to a pane's right edge opens a new chat column. The gesture spans two documents that talk by
`postMessage`: the chat PAGE owns the tab and the native drag, the SHELL mounts the drop zones and performs
the mutation.

- **The tab is a native HTML5 draggable** (no pixel-slop threshold, the browser owns click-vs-drag). Marked
  at build: `render.ts:6767` `tab.draggable = !s.sub && !fedMissing && !isProvisionalId(id) && !settings.tabsLocked`.
  `dragstart` wires through `wireTabDrag` (`render.ts:6347`), which calls `postTabDrag` (`render.ts:6335`); the
  on:true post is `{ romp: "tabDrag", on, sid, name, stripH }` to `window.parent` (`render.ts:6341`), the
  on:false teardown a separate post (`render.ts:6338`). The strip's own `#tabs` drop path only REORDERS within
  a strip (`render.ts:20609`, committing via `reorderTo` `render.ts:5913`); it never opens a column.
- **The shell mounts the drop zones** on that message (the `_LANDING_SPLIT_JS` string, `kernel.py:58367`,
  injected into the shell at `:60135`, the tabDrag handler at `:58541`). `mountZones` (`kernel.py:58534`) lays
  a COLUMN zone over every chat pane but the source (drop moves the session there) plus, on the rightmost
  pane, an EDGE zone (drop opens a new column). The edge band is `edgeWidth(w)=max(72,min(180,0.2*w))` of the
  pane WIDTH (`kernel.py:58520`); the drop preview `ghostRect` is the RIGHT HALF of the rightmost pane, full
  row height (`kernel.py:58521`). The affordance: a column zone toggles `.over` on itself; the edge zone shows
  `#col-ghost`, a fixed rectangle at the right half labelled with the dragged session's name, or "Four columns
  at most" in the `.refused` state at the cap (`showGhost`/`cue`, `kernel.py:58522`/`:58526`; CSS
  `kernel.py:59563`).
- **The mutation is one function**, `moveTab(sid, to)` (`kernel.py:58454`, exposed `window.__rompMoveTab`,
  `:58493`). `to` is a column number or `"new"`. The `"new"` path (`:58458`): `canSplit()` (`:58443`, cap
  `MAX=4` counting the first column, on the same source line as the store key, `:58369`), `__rompSplitGrow`
  halves the rightmost column's width (`:55113`, with a close-side twin `__rompSplitShrink` `:55118`), push
  `{n, ids:[sid]}`, `save()`, then `make(n, seed, state)` (`:58426`) builds
  `<div class="pane chat-col" data-col=N style="flex:var(--g-chatN,60) 1 0">` wrapping
  `<iframe src="/chat?col=N&skeleton=1">`, inserts it before `gv-a`, wires its col-resize gutter, and calls
  the new iframe's `contentWindow.focus()` (`:58463`) so the new column takes focus.
- **The new column starts with an active tab, not on the wall.** `make()` seeds the dragged session as the
  column's persisted `activeId` (`seed`/`seedFor`, `kernel.py:58402`/`:58406`), which the page restores through
  the arrival path (`restoreIfShown`, `render.ts:17293`). So a drag-created pane reveals its seeded tab at
  once; `silentActivate` (section 6) is the FALLBACK for when that tab is unlisted or held elsewhere, or when
  focus later leaves the pane.
- **The column's dial terms** (the served `/chat` shim, `_shim` `kernel.py:54039`, mints one `iid` per page at
  `:54092`): `/ws?app=chat&delta=1&iid=<uuid>&col=<N>&skeleton=1` (plus `active`/`reconnect` as any pane),
  composed at `kernel.py:54268`. `col=N` sets the page's per-column state key `SK` (`kernel.py:54414`) and is
  LOG-ONLY on the kernel: parsed "for the logs" (`:64040`), stashed `client["col"]=col` (`:64108`), printed
  only in the drop-client log row (`:46141`), never branching what is served. `skeleton=1` is the term that
  changes served content, gated to `app=="chat"` (`:64038`): the strip with a skeleton list, one full frame
  for the `active` tab, a light status per other tab (the diet, `_resolve_reconnect` `:46474`).
- **View state is browser localStorage, per browser, no kernel store.** Three keys: `romp-chat-cols`
  (`{v:2, cols:[{n, ids}]}` in row order: which columns exist and which sessions each holds; key and `MAX` at
  `kernel.py:58369`, written by `save()` `:58374`, read and migrated by `read()` `:58568`, restored at boot by
  `make()` per column `:58583`); `romp-vscode-state-chat:N` (a column's own active tab, drafts, scroll; `BK`
  `kernel.py:58370`); `romp-pane-grow` (pane widths as flex-grow numbers, a later column registers `chatN`;
  `GK` `kernel.py:55085`). The kernel's `timeline-views.json` stores tag filters, NOT layout
  (`kernel.py:4698`).
- **The layout axis is a single horizontal flex row**: `.row{display:flex;flex:1 1 auto;min-height:0}`
  (`kernel.py:58982`), each pane `flex:var(--g-chatN,60) 1 0` (`:59507`), 7px `.gv` gutters between (`:59520`).
  Desktop only (`mobile()` disables the split and `__rompChatSets` returns null; the mobile `.row{display:block}`
  override at `:59595`).

**The prior art that matters most:** the shell's outer `.col` is ALREADY a vertical flexbox with a top/bottom
split. `.col{display:flex;flex-direction:column;height:100%}` (`kernel.py:58978`) stacks the pane `.row` over a
`row-resize` gutter `#gh` (element `:59914`, `.gh` CSS `:59536`) over a full-width timeline band. So a
horizontal divider between a top and a bottom region is not new machinery; what is new is applying it to split
ONE chat pane into two chat panes, NESTED inside a single column.

## 2. The layout model

**Decision: one level. A flat list of columns (horizontal), each column OPTIONALLY split into a top and a
bottom chat pane. Not a full nested grid.** A bottom split does NOT hold a column split inside it; the grid is
at most two rows deep and only within a single column. Rationale: the persisted shape is already a flat `cols`
list in row order (`romp-chat-cols`), and, in code, a bottom pane is a column with a different placement, so
the minimal extension is a per-column optional bottom entry rather than an arbitrary rows-and-columns tree.
Arbitrary nesting would rewrite the partition and the persistence for a layout the four-pane cap makes shallow
anyway.

**The partition needs NO page-side change; the work is shell-side.** `chat-columns.ts` (`ownerOf` `:26`,
`columnHolds` `:37`, `ColSets` `:11`) is a pure function over a flat `{columnNumber: ids}` map, and the page
filters by its own `?col=N` (`COL` `render.ts:1028`, `colSets` `:1040`, `heldHere` `:1047`, `tabInView`
`:1048`). A bottom pane that dials `/chat?col=below.n` and is listed under `below.n` in that flat map is
admitted by the same code with no edit, and each pane boots its own `FederationManager` (one relay per host)
exactly as a side column does. What must learn about a bottom pane is the SHELL's own routing half in
`_LANDING_SPLIT_JS`, a SEPARATE `ownerOf` at `kernel.py:58387` (distinct from the page's): `sets()` (`:58388`)
must emit `below.n` as an ordinary top-level key with the bottom pane's ids and extend its `seen` dedup to span
top and bottom so each id lands in exactly one pane; `target()` (`:58396`), `moveTab()` (`:58454`) and
`unlist()` (`:58447`) must route bottom entries. (The doc's earlier "extend `chat-columns.ts`
`ownerOf`/`columnHolds`" pointed at the wrong file: that pure function is unchanged; the shell's routing
`ownerOf` is the one that grows.)

**Persistence: add an OPTIONAL `below` under the existing v:2; do NOT bump to v:3.** A column entry may carry
`{n, ids, below?: {n, ids, ratio}}`, where `below.n` is the bottom pane's own column number (for its
`/chat?col=N` dial and its `romp-vscode-state-chat:N` blob), `below.ids` its sessions, and `ratio` the
top/bottom height split. Keeping the version at 2 matters for the multi-tab transition window: `read()`
(`kernel.py:58573`) matches only `raw.v===2`, so a v:3 store written by a new tab and read by a still-running
OLD bundle would fall through to empty `cols`, and the storage reconcile (`:58580`) would then CLOSE every
column in that stale tab, the same drop as the v1-to-v2 bump. An OPTIONAL `below` under v:2 degrades
gracefully instead: an old reader's `add(c.n, c.ids)` (`:58573`) silently ignores the unknown `below` and keeps
the top panes. The per-column blob is keyed PURELY by column number
(`SK = 'romp-vscode-state-'+app+(COL?':'+COL:'')`, `kernel.py:54414`; `persistActive` `render.ts:1149`,
`wantActive` `:1133`, `activeId` `:1102` all read and write it through the shim's getState/setState), so a
bottom pane with its own `below.n` gets `romp-vscode-state-chat:below.n` automatically, with no new blob key.

**The cap arithmetic and the number allocator both change.** `canSplit()` (`kernel.py:58443`,
`cols.length+1<MAX`) and `nextNumber()` (`:58389`) scan only top-level `cols` entries. A bottom pane adds a
pane WITHOUT a top-level entry, so `canSplit` must count top-plus-bottom panes against `MAX=4` (total panes),
and `nextNumber` must avoid colliding with any `below.n`.

**`make()` needs a nested-pane variant; it cannot be reused as-is.** `make()` (`kernel.py:58426`) inserts a
pane into the SINGLE horizontal `.row` (`row.insertBefore(..., gva)`) and wires a col-resize gutter plus
horizontal `chatN` grow. A bottom pane must instead be NESTED inside its parent column's div as a vertical flex
child, with a `row-resize` gutter and a separate height-ratio store. Only the KERNEL serve path is genuinely
unchanged (section 5); the DOM and layout half is new code. `seedFor` (`:58406`) must read
`romp-vscode-state-chat:below.n`, and the boot restore loop (`:58583`) recreates each column's top pane and,
if present, its bottom pane.

**The divider.** A per-column horizontal (`row-resize`) gutter between the top and bottom panes, ratio-traded
and PERSISTED (the `ratio` field above). The precedents, precisely:
- The `.gv` column gutter (`gutter()`, `kernel.py:55135`, exposed `window.__rompGutter` `:55151`, wired per
  column in `make()` at `:58439`) is the ratio and persistence pattern to mirror onto the vertical axis: a
  ghost line on `mousemove`, both neighbours' sizes written ONCE on `mouseup`,
  `body.drag iframe{pointer-events:none}` to keep the mouse, a min clamp. Its comment already notes it wires
  the split's chat-to-chat gutters through one code path.
- The `#gh` band gutter (element `kernel.py:59914`, `.gh` CSS `:59536` `cursor:row-resize`, the
  `body.dragh{cursor:row-resize}` state `:59543`, JS around `:55073`) is the `row-resize` MECHANISM already on
  the vertical axis (it resizes the timeline band's height).
- The composer-resize and tab-strip-resize grips (`render.ts:19327` and `:13995`) are the closest in spirit: a
  horizontal grip that trades top-versus-bottom real estate INSIDE a chat page, with pointer capture,
  write-on-release, and a double-click reset.
The gap this doc names: every EXISTING horizontal divider resizes a FIXED-size region (the timeline band, the
composer, the tab strip), never a ratio between two flex panes; the only ratio-trading gutters are horizontal
(`col-resize`). So the top/bottom chat divider is a new combination: the `#gh` row-resize mechanism carrying
the `.gv` ratio/ghost/write-on-release/persist pattern. Its min clamp must leave EACH pane enough for a one-row
tab strip plus the composer's floor (`COMPOSER_MIN_H=38`, `render.ts:18922`; the composer self-caps at 60% of
the iframe via `composerMaxH`, `:18923`).

## 3. The drop target, focus on creation, and keyboard

**A bottom-edge zone mirroring the right-edge zone.** In `mountZones` (`kernel.py:58534`), beside the
right-edge zone, mount a bottom-edge zone whose HEIGHT axis is the mirror of the width edge: `edgeWidth`
applied to the pane HEIGHT (a band `max(72,min(180,0.2*h))` at the pane's bottom), a `ghostRect` that is the
pane's BOTTOM HALF (full width, bottom half height) rather than the right half, and a drop that calls
`moveTab(sid, "down")`, a new `to` value that splits the current column rather than adding one. The affordance
mirrors the edge ghost: `#col-ghost` (or a sibling) over the bottom half, labelled with the session name,
`.refused` at the pane cap. Desktop-only, suppressed when the source is a lone-session pane, as the right edge
is.

**`moveTab(sid, "down")` must seed and focus, like the "new" path.** It must seed the bottom pane's blob with
the dragged sid (so the bottom pane's shim dials `active=sid` and reveals it immediately) AND call the new
bottom iframe's `contentWindow.focus()` (mirroring `kernel.py:58463`). Without both, the bottom pane starts
no-active behind the diet and depends on the `silentActivate` fallback from its first frame (section 6). This
is the difference between filling AT creation and relying on the recovery path.

**Keyboard parity.** Add `chat.splitDown` (the analog of `chat.split`, `Mod+\`, `commands.ts:32`, registered
`palette-main.ts:186`) that calls `moveTab(activeId, "down")`, plus move-up/down-a-pane analogs of
`chat.moveToNextColumn` (`palette-main.ts:208`).

**The vertical focus-nav graph is real new code, not a free slot.** `moveFocus(dir)` (`kernel.py:55205`,
Alt/Option+Arrow) is column-indexed only (`visCols()`/`indexOf`): Down from a column enters the timeline band,
Up from a column no-ops (`:55213`). It has NO notion of two panes stacked in one column. The design must extend
the vertical axis so that, in a split column, Alt-Down from the TOP pane moves to the BOTTOM pane (not straight
to the timeline), Alt-Up from the BOTTOM pane returns to the top, and Alt-Down from the BOTTOM pane then enters
the timeline. The shell's `setFocus`/`paneOf` (`kernel.py:55178`) already track a numbered chat frame, so
ownership and the focus ring need no change; only the up/down GRAPH does. So section 3's earlier claim that the
split "slots into the existing up/down focus axis rather than inventing one" is only half true: the frame is
known, but the graph is flat and must grow.
**Open question to resolve in the feature:** when the timeline's Alt-Up (`kernel.py:55207`) returns to a split
column, which pane does it land on? `lastCol` (`kernel.py:55172`) tracks a column id, not a within-column pane,
so the return target for a split column is undefined today. The design should track the last-focused pane per
split column (extend `lastChat`) and return there.

## 4. Focus arbitration and the strip in a stacked pane

**Focus arbitration is unchanged; exactly one column owns each session.** The shell's
`target(sid)=frameOfCol(ownerOf(sid))` (`kernel.py:58396`, exposed as `window.__rompChatTarget` `:58501`) is
the authority; each page's `focusIsOurs(sid)` (`render.ts:8284`) asks it and acts only if the owning frame is
itself, else `forwardToOwner` (`render.ts:8299`) hands the message to the owner (focus, confirm-revive and
focus-echo all route through this gate, `render.ts:18426`/`:18674`/`:20133`). The shell's own focus RING is
separate and event-based: `setFocus` (`kernel.py:55178`) tracks the focused pane on child pointerdown, focusin
or window-focus, exactly one `.pane-focused`. Because a bottom pane is an ordinary numbered column,
`ownerOf`/`target`/`focusIsOurs` resolve it with no new arbitration: a split adds a numbered frame the existing
authority already handles.

**The strip does not collapse to icons; it wraps then scrolls.** `#tabs` wraps onto rows (`flex-wrap:wrap`,
`styles.css:402`) and `#tabbar` SCROLLS once the rows exceed `max-height:var(--tabbar-cap,150px)` with
`overflow-y:auto` (`styles.css:389`); the user's only height control is the `#tabbar-resize` grip
(`styles.css:425`, wired `render.ts:13995`). In a short bottom pane the strip wraps then scrolls inside its
cap. (This is orthogonal to `collapsedTabIds` `render.ts:1055`, which is the user's per-tag-section fold, not a
height response.)

**A folded active tab is a designed state, inherited unchanged.** When the active tab's tag section is folded,
its section header is the stand-in (`makeGroupHead` `render.ts:6114`, `standIn` `:6165`): `focusActiveTab`
lands on the header (`render.ts:7863`), the arrows step from it, and `showActive` renders the section SNAPSHOT
(`renderSnapshot` `render.ts:12930`, `snapView` `:12827`) rather than a transcript. `silentActivate`
deliberately leaves any fold alone (no `unfoldSectionOf`, the #1754 low-d decision), so a bottom pane that
silently adopts a folded tab shows that header-plus-snapshot, which is correct and consistent with a side
column.

**What the design must specify for a stacked pane:**
1. The divider min clamp reserves, for EACH pane, at least one strip row plus the composer floor
   (`COMPOSER_MIN_H=38` `render.ts:18922`; composer min-height `styles.css:1464`; `composerMaxH` caps at 60%
   `render.ts:18923`), so a short bottom pane never hides its whole strip or composer.
2. There is NO auto-scroll-active in `#tabbar`, so a short scrolling strip can leave the active tab (or its
   folded stand-in header) off-screen. The feature should add scroll-active-into-view on activation for a short
   pane; if it does not, the doc must say the active affordance can be off-screen and that is accepted.
3. A freshly-split bottom pane inherits the silent no-unfold behaviour: if its adopted tab is under a folded
   section it shows the section snapshot, not the transcript, until the user opens the section. The feature
   should confirm this is the intended first view (the alternative, unfolding the adopted tab on a fresh split,
   departs from `silentActivate`'s silence and is not recommended).

## 5. The kernel side: nothing new to serve

A bottom pane is a chat column with a different PLACEMENT, so it dials exactly as a column does:
`/chat?col=N&skeleton=1` with its own `iid`. To the kernel it is byte-for-byte a side-column client: `col=N`
stays page-and-log only (`kernel.py:64040`, `:46141`); `skeleton=1` drives the same diet (`_resolve_reconnect`
`:46474`, which reads `active`/`skeletonOnReady`/`_skeleton_for` and never reads `col`). The placement (top or
bottom, the height ratio) is pure shell CSS and localStorage; the kernel never learns it. The only
kernel-visible change is one more `col=N` client per split, already within the shape the relay-scoped diet and
the wsopen row handle.

**One #1754 behaviour each pane inherits (not new kernel state, worth naming):** every `/chat` page
re-announces its own shown tab to the relay on `romp:hostRelayUp` / `romp:wsup` (`shownTabForRelay` +
`announceActiveToRelay`, `render.ts:16155`/`:16179`), and `silentActivate` (`render.ts:12684`) gives a
shown-but-no-active pane an active without a focus hop. A bottom pane is another `col=N` page that runs this
path independently: one more `activeTab` op on its own socket. This is the mechanism section 6 leans on, and it
changes no kernel contract.

## 6. The served lab: a long session in EVERY pane (the wall lesson)

**The central correctness link, stated plainly: the vertical split inherits the side split's total dependence
on #1754.** A chat column is a shell column (`colSets !== null`), and a shell column does NOT adopt the first
arriving frame (`render.ts:8376`): it must activate a tab to reveal a transcript body. So EVERY pane that is
not the currently focused column relies on the #1754 recovery to fill: the T357 restore (`restoreIfShown`,
`render.ts:17293`) when the persisted active still names a held-and-shown tab, and `staleActiveFallback` to
`silentActivate` (`render.ts:8375` to `:12684`) when it does not. The bottom pane is the focused column at the
split instant (section 3 seeds and focuses it), but it becomes non-focused the moment focus moves: a click on
the top pane, an Alt-arrow, or ANY shell reload (which restores the ring to one pane, `kernel.py:58583`). The
SOURCE (top) pane is non-focused the instant the drop lands if it still holds sessions, the exact pane that
historically read "no session shown" and motivated the split-column `staleActiveFallback` branch
(`render.ts:6632`, the 2026-09-12 report). From that point each non-focused pane fills ENTIRELY through the
#1754 path; without `silentActivate` it would sit on the scroll-back wall.

**Two faces, do not conflate them:**
- A LOCAL session in a bottom pane: the kernel's no-active diet does NOT apply (it is scoped to
  `kind=='relay'`, `kernel.py:46529`); a no-active local dial gets the fail-safe WHOLE push. So the local wall
  is purely PAGE-side (no body revealed because `colSets !== null`), and `silentActivate`'s `showActive` is the
  fix.
- A REMOTE (federated) session in a bottom pane: the pane rides a relay socket, the no-active diet DOES
  skeleton its shown tab, and `silentActivate`'s `showActive` to `notifyActive`, plus the
  `romp:hostRelayUp`/`romp:wsup` re-announce, is what carries the shown tab past the diet.
Both faces are #1754; the lab exercises both. See `plans/federated-pane-dial-terms.md` section 7 (the deferred
widening of the diet from relay-only to LOCAL pages): if that lands, the local and relay faces become
identical, so the lab must assert fill-to-turn-0 regardless of whether the kernel dieted or pushed whole.

**The lab, grounded in the existing harness:**
- **Boot** from `tests/test_chat_split_served.py` `setUpClass` (single kernel, real pointer drag, reload
  restore): build the dist, seed XDG state, write `session-hosts` `off`, `Popen bin/romp-kernel`, poll
  `/healthz`. Seed at least two sessions in the SAME column so a tab can be dragged out, and make each a LONG
  session with a head gap: the local cut-floor seed precedent is `tests/test_local_split_cutfloor_served.py`
  (the asm-checkpoint seed helper). For the remote face, add the two-kernel shape
  (`tests/test_federated_twocol_wall_served.py`, added by #1754).
- **Drive the drag to the BOTTOM edge:** a real pointer drag (`page.mouse.down`, a move past the threshold so
  the page posts `{romp:"tabDrag"}` and the shell mounts zones, then a move to the bottom-band coordinates so
  the bottom `#col-ghost` gains `.on`), then `page.mouse.up` to drop, calling `moveTab(sid,"down")`.
- **Assert the bottom pane is STACKED under, not beside:** the new frame has the SAME left as the top pane and
  a GREATER top, inside one column (contrast the horizontal split's greater LEFT, equal top), and the
  between-panes gutter's computed cursor is `row-resize`, never `col-resize`.
- **Assert the bottom dial:** hook `window.WebSocket` for FULL dial URLs (the cold-boot `wrapDials` pattern in
  `tests/test_cold_boot_diet_browser.py`), read the bottom frame's dials, and assert its `/ws` URL carries
  `&skeleton=1` and an `iid=` distinct from the top pane's. (Do not use the twocol lab's dial projection: it
  drops `iid`.)
- **Assert fill in EVERY pane (the headline the wall lesson demands):** for BOTH the top and the bottom frame,
  scroll `#content` to the top and assert `window.__rompRegions(sid)` contains a run region with `lo===0`
  (filled to turn 0) plus a head gap, NOT a skeleton and not empty. Assert this for the NON-FOCUSED pane
  specifically (drive focus to the other pane, or reload the shell so the ring lands on one pane), and for the
  SOURCE pane. A test that only checks the just-focused new pane would pass even with `silentActivate` removed,
  so the non-focused fill-to-turn-0 check is the assertion that actually pins the wall lesson.
- **Assert the diet per bottom pane on ITS OWN socket** (`routeWebSocket`, counting `type=="session"` fulls
  versus `type=="status"`), or the bottom frame's `#tabs .tab-skeleton` count, NOT the kernel-wide
  `/perf builds.chat` (a slow runner mixes every pane's frames into that window).
- **Assert persistence:** reload the shell and assert `romp-chat-cols` (v:2 with the optional
  `below:{n,ids,ratio}`) restores the top and bottom panes, their sessions, and the height ratio; assert each
  recreated pane redials (two redials per shell reload) and each fills to turn 0. The reload is exactly where
  the non-focused pane's #1754 dependence bites.

**Red first at main:** there is no bottom-edge zone, no `moveTab("down")`, no nested vertical chat gutter, and
no bottom-pane frame convention, so the drag produces no split and the split/dial/fill/persist assertions fail.
Every drive selector (the bottom zone class, the bottom ghost, the bottom frame id) is a name the feature
introduces, so the lab is written after the feature lands, its selectors pinned to the feature's chosen names.
Run it on the devbox with `ROMP_SERVED_TESTS_REQUIRE=1 ROMP_SERVED_TESTS_ENGINES=chromium uv run --python 3.13
--with pytest pytest tests/test_<newlab>.py` under `capped`; CI picks it up via the `tests/test_*_served.py`
glob.

## 7. Risks and open questions

- **The wall dependence is the top risk.** The feature is correct only because #1754 fills a non-focused shell
  pane; the lab's non-focused fill-to-turn-0 assertion is the guard, and it must run for both the local and the
  remote face. If `federated-pane-dial-terms.md` section 7 later widens the diet to local pages, a local
  non-focused bottom pane would also take the kernel skeleton, so the assertion must not depend on which path
  served the frame.
- **`make()` and the cap are more work than "nothing new" suggests.** Only the kernel serve path is unchanged;
  the DOM nesting, the row-resize gutter with a persisted ratio, the cap counting panes not columns, and the
  number allocator avoiding `below.n` collisions are all new shell code.
- **The persistence transition window.** Adding `below` as OPTIONAL under v:2 (not a v:3 bump) is deliberate:
  an old bundle in another tab keeps the top panes instead of dropping the whole store. The new `below` pane
  still needs its CustomEvent dispatched (`palette-main.ts:377` listener) for cross-tab liveness.
- **Tab-strip real estate and the active affordance at small heights.** The strip wraps then scrolls with no
  collapse-to-icons mode, and there is no auto-scroll-active, so a short bottom pane can scroll the active tab
  or its folded stand-in header off-screen. The divider min clamp is the backstop; scroll-active-into-view on a
  short pane is the recommended addition.
- **The composer in a bottom pane.** One composer per `/chat` page, bottom-anchored; it self-limits to 60% of
  the iframe (`composerMaxH`, `render.ts:18923`) with a min-height floor, so a short bottom pane self-caps
  rather than eating the transcript. The divider min clamp is the backstop.
- **The vertical focus graph and the timeline return target** (section 3) are undefined today and must be
  designed: Alt-Up from the timeline into a split column needs a per-column last-focused-pane memory.
- **Tier.** This is a `feature` (a new capability inside the existing model, no kernel contract change). It
  needs the user's word after this doc before any code.
