# Split a chat pane top and bottom (drag a tab to the bottom edge)

A design line for a feature on the user's list (open since 2026-09-12, unowned): drag a tab to the BOTTOM
edge of a chat pane to split it into a top and a bottom pane, the vertical counterpart of today's
side-by-side column split (drag a tab to the right edge to open a column). This doc decides the layout model,
the drop target, the divider, the kernel's part (nothing new), the served lab, and the risks. It is a
`feature`: it needs the user's word after this doc. No code here.

All line references re-checked at main 2b06e774.

## 1. The premise, in code: the side split today

Dragging a tab to a pane's right edge opens a new chat column. The gesture spans two documents that talk by
`postMessage`: the chat PAGE owns the tab and the native drag, the SHELL mounts the drop zones and performs
the mutation.

- **The tab is a native HTML5 draggable** (no pixel-slop threshold, the browser owns click-vs-drag). Marked
  at build: `render.ts:6767` `tab.draggable = !s.sub && !fedMissing && !isProvisionalId(id) && !settings.tabsLocked`.
  `dragstart` posts to the shell: `render.ts:6347` `wireTabDrag`, which calls `postTabDrag(true, id)`
  (`render.ts:6328`), sending `{romp:"tabDrag", on, sid, name, stripH}` to `window.parent`. The strip's own
  `#tabs` drop path only REORDERS within a strip (`render.ts:20532`); it never opens a column.
- **The shell mounts the drop zones** on that message (`kernel.py:57907`, the `_LANDING_SPLIT_JS` string).
  `mountZones` (`kernel.py:57901`) lays a COLUMN zone over every chat pane but the source (drop moves the
  session there) plus, on the rightmost pane, an EDGE zone (drop opens a new column). The edge band is
  `edgeWidth(w)=max(72,min(180,0.2*w))` of the pane WIDTH (`kernel.py:57887`); the drop preview
  `ghostRect` is the RIGHT HALF of the rightmost pane, full row height (`kernel.py:57888`). The affordance:
  a column zone toggles `.over` on itself (an accent wash + inset ring); the edge zone shows `#col-ghost`, a
  fixed rectangle at the right half labelled with the dragged session's name (`cue`/`showGhost`,
  `kernel.py:57889`; CSS `kernel.py:58928`).
- **The mutation is one function**, `moveTab(sid, to)` (`kernel.py:57821`, exposed `window.__rompMoveTab`,
  `:57860`). `to` is a column number or `"new"`. The `"new"` path: `canSplit()` (`:57810`, cap `MAX=4`
  counting the first column, `:57736`), `__rompSplitGrow` halves the rightmost column's width (`:54480`),
  push `{n, ids:[sid]}`, `save()`, then `make(n, sid, state)` (`:57793`) builds
  `<div class="pane chat-col" data-col=N style="flex:var(--g-chatN,60) 1 0">` wrapping
  `<iframe src="/chat?col=N&skeleton=1">`, inserts it before `gv-a`, and wires its gutter.
- **The column's dial terms** (the served `/chat` shim, `kernel.py:53635`): `/ws?app=chat&delta=1&iid=<uuid>`
  `&col=<N>&skeleton=1` (plus `active`/`reconnect` as any pane). `col=N` sets the page's per-column state
  key (`SK`, `kernel.py:53781`) and is LOG-ONLY on the kernel (`col = (q.get("col")...)`, `kernel.py:63375`,
  recorded on the client, printed in the drop-client row, never changing what is served). `skeleton=1` is
  the term that changes served content: the strip with a skeleton list, one full frame for the `active` tab,
  a light status per other tab (the diet, `kernel.py:63373` and `_resolve_reconnect`).
- **View state is browser localStorage, per browser, no kernel store.** Three keys:
  `romp-chat-cols` (`{v:2, cols:[{n, ids}]}` in row order: which columns exist and which sessions each holds,
  `kernel.py:57741`, restored at boot by `make()` per column, `:57948`); `romp-vscode-state-chat:N` (a
  column's own active tab / drafts / scroll, `kernel.py:57737`); `romp-pane-grow` (pane widths as flex-grow
  numbers, a later column registers `chatN`, `kernel.py:54452`). The kernel's `timeline-views.json` stores
  tag filters, NOT layout.
- **The layout axis is a single horizontal flex row**: `.row{display:flex}` (`kernel.py:58349`), each pane
  `flex:var(--g-chatN,60) 1 0` (`:58874`), 7px `.gv` gutters between (`:58887`). Desktop only (`mobile()`
  disables the split and `__rompChatSets` returns null).

**The prior art that matters most:** the shell's outer `.col` is ALREADY a vertical flexbox with a
top/bottom split. `.col{display:flex;flex-direction:column}` (`kernel.py:58345`) stacks the pane `.row` over a
`row-resize` gutter `#gh` (`kernel.py:59281`) over a full-width timeline band `#tl-pane`
(`{flex:0 0 var(--tl,200px)}`, `:58896`). So a horizontal divider between a top and a bottom region is not
new machinery; what is new is applying it to split ONE chat pane into two chat panes.

## 2. The layout model

**Decision: one level. A flat list of columns (horizontal), each column OPTIONALLY split into a top and a
bottom chat pane. Not a full nested grid.** A bottom split does NOT hold a column split inside it; the grid is
at most two rows deep and only within a single column. Rationale: the persisted shape is already a flat
`cols` list in row order (`romp-chat-cols`), and the manager's framing holds in code, a bottom pane is a
column with a different placement, so the minimal extension is a per-column optional bottom entry rather than
an arbitrary rows-and-columns tree. Arbitrary nesting would rewrite the partition (`chat-columns.ts`
`ownerOf`/`columnHolds`), the `sets()` shell logic, and the persistence for a layout the four-pane cap makes
shallow anyway.

**Persistence.** Extend `romp-chat-cols` (a `v:3`) so a column entry may carry an optional bottom sub-pane:
`{n, ids, below?: {n, ids, ratio}}`, where `below.n` is the bottom pane's own column number (for its
`/chat?col=N` dial and its `romp-vscode-state-chat:N` blob), `below.ids` its sessions, and `ratio` the
top/bottom height split. The total pane count (top and bottom panes across all columns) stays under the
existing cap. `sets()` (`kernel.py:57755`) and `chat-columns.ts` gain the bottom panes as ordinary
column-numbered members; a session belongs to exactly one pane. Restore recreates each column's top pane and,
if present, its bottom pane, exactly as `make()` recreates columns today (`kernel.py:57948`).

**The divider.** A per-column horizontal (`row-resize`) gutter between the top and bottom panes, ratio-traded
and PERSISTED. The precedents, precisely:
- The `.gv` column gutter (`gutter()`, `kernel.py:54502`) is the ratio/persistence pattern to mirror onto the
  vertical axis: a ghost line on `mousemove`, both neighbours' sizes written ONCE on `mouseup` (a grow write
  re-lays out every iframe), `body.drag iframe{pointer-events:none}` to keep the mouse, a min clamp
  `min(120, sum*0.25)`.
- The `#gh` band gutter (`kernel.py:54440`) is the `row-resize` MECHANISM already on the vertical axis (it
  resizes `--tl`), with a 48px floor and a 70vh cap.
- The T410 focused-section gutter (`feed.ts:4466` `wireFocusGutter`) is the ratio-with-keyboard precedent
  (pointer capture, a weight ratio with a `MIN_W` floor, persisted via `persistViewState`), but it is
  WIDTH-only by design.
- The composer-resize and tab-strip-resize grips (`render.ts:19246`, `:13940`) are the closest in spirit: a
  horizontal grip that trades top-vs-bottom real estate INSIDE a chat pane, `setPointerCapture`,
  write-on-release, double-click to reset, 7px grip.
The gap this doc names: every EXISTING horizontal divider resizes a FIXED-height region (`--tl` band,
composer, tab strip), never a ratio between two flex panes; the only ratio-trading gutters are horizontal
(`col-resize`). So the top/bottom chat divider is a new combination, the `#gh` row-resize mechanism carrying
the `.gv` ratio/ghost/write-on-release/persist pattern. Its min clamp must leave each pane enough for a
one-row tab strip plus the composer's floor (`COMPOSER_MIN_H=38`, `render.ts:18845`).

## 3. The drop target

**A bottom-edge zone mirroring the right-edge zone.** In `mountZones` (`kernel.py:57901`), beside the
right-edge zone, mount a bottom-edge zone on a pane whose HEIGHT axis is the mirror of the width edge:
`edgeWidth` applied to the pane HEIGHT (a band `max(72,min(180,0.2*h))` at the pane's bottom), a `ghostRect`
that is the pane's BOTTOM HALF (full width, bottom half height) rather than the right half, and a drop that
calls `moveTab(sid, "down")`, a new `to` value that splits the current column rather than adding one. The
affordance mirrors the edge ghost: `#col-ghost` (or a sibling) positioned over the bottom half, labelled with
the session name, `.refused` at the pane cap. The zone is desktop-only and suppressed when the source is a
lone-session pane, as the right edge is (`!alone`, `kernel.py:57902`).

**Keyboard parity.** Add `chat.splitDown` (the analog of `chat.split`, `Mod+\`, `commands.ts:32`;
`palette-main.ts:186`) that calls a `moveTab(activeId, "down")`, plus move-up/down-a-pane analogs of
`chat.moveToNextColumn` (`palette-main.ts:208`). Focus already has the axis: `moveFocus(dir)`
(`kernel.py:54572`, Alt/Option+Arrow) moves between panes and TODAY no-ops "up from a column" while Alt-Down
enters the timeline band, so a top/bottom chat split slots into the existing up/down focus axis rather than
inventing one.

## 4. The kernel side: nothing new

A bottom pane is a chat column with a different PLACEMENT, so it dials exactly as a column does:
`/chat?col=N&skeleton=1` with its own `iid` (the shim mints one per page, `kernel.py:53635`). `col=N` stays
page-and-log only (`kernel.py:63375`); `skeleton=1` drives the same diet (`kernel.py:63373`,
`_resolve_reconnect`), so a bottom pane, a VIEW of the one session its `?active=` hint names, gets the strip +
skeleton list + one full + statuses exactly as a side column does. The placement (top or bottom, the height
ratio) is pure shell CSS and localStorage; the kernel never learns it. **The kernel must learn nothing.** The
only kernel-visible change is one more `col=N` client per split, already within the shape the relay-scoped
diet and the wsopen row handle.

## 5. The served lab it would need

A single-kernel served lab (the `test_cold_boot_diet_browser.py` / `test_chat_split_served.py` family: a
hermetic kernel, the served shell driven by Playwright) that:
1. Drags a tab to the BOTTOM edge of a chat pane and asserts the split appears: a second chat iframe stacked
   under the first, a `row-resize` gutter between them.
2. Asserts the bottom pane DIALS `/chat?col=N&skeleton=1` with its own `iid` (hook `window.WebSocket` to
   capture the dial URLs, as the cold-boot lab does; assert the second chat dial carries `skeleton=1` and a
   distinct `iid`).
3. Reloads the shell and asserts the split PERSISTS: `romp-chat-cols` restores the top and bottom panes and
   their sessions, and the height ratio is restored.
4. Asserts the diet on the bottom pane: its `/perf builds.chat` shows the skeleton diet (a status per
   non-active tab), the same observable the column diet uses.

**Red first at main:** at main there is no bottom-edge zone, so a drag to the bottom edge produces no
vertical split and no second chat dial; the lab's split/dial/persist assertions fail. Green once the feature
lands.

## 6. Risks

- **Tab-strip real estate at small heights.** The tab strip wraps then scrolls (`#tabbar` `max-height:
  var(--tabbar-cap,150px); overflow-y:auto`, `styles.css:386`); there is no collapse-to-icons mode. In a
  short bottom pane the strip scrolls, which is acceptable but tight; the divider's min clamp must reserve at
  least one strip row plus the composer floor so neither pane becomes unusable.
- **The composer in a bottom pane.** One composer per `/chat` page (`_chat_body`, `kernel.py:54399`), bottom
  anchored in `#footer`. It already self-limits to 60% of the IFRAME's `innerHeight`
  (`composerMaxH`, `render.ts:18846`) with a min-height floor (`styles.css:1459`) and a wrapping statusline
  (`styles.css:1178`), so a short bottom pane self-caps rather than eating the transcript. The divider min
  clamp is the backstop.
- **The reload holds with two panes.** Each pane is an independent `/chat?col=N` page that reloads and
  redials on its own; the shell recreates both from `romp-chat-cols` on the shell reload (`kernel.py:57948`),
  and each pane's reload-core diet applies per pane (the federated-dial work landed the relay diet; a local
  pane keeps the fail-safe whole push, see `plans/federated-pane-dial-terms.md` section 7). Two panes mean
  two redials on a shell reload; the lab pins that both land and both diet.
- **Tier.** This is a `feature` (a new capability inside the existing model, no kernel contract change). It
  needs the user's word after this doc before any code.
