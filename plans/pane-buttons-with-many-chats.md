# The rail's chat button when the chat is many columns (options for the user)

Status: DECIDED 2026-09-21 (section 6): option A as recommended, as a rule for every rail button; the code
follows as a `feature` PR inside the docking kit. Tier: `docs` for this note.

The user's report (2026-09-21, paraphrased): they dragged one chat tab out of the strip into its own column,
pressed the bottom-left chat button to hide the chats, pressed it again to show them, and the panes did not
come back in the arrangement they had. They asked for more thought about the consistency of the whole
system and about what the bottom-left buttons do now that the chat is no longer one tab that opens in one
defined place; they do not have the answer and want suggestions.

A second thing they hit in the same gesture, the page stuck after the tab was dragged back into the strip, is
a bug with its own fix (PR 1978) and is not a design question: a tab drag ends when its source column
closes. This note is about the buttons and the arrangement.

## 1. The premises, in code

Verified 2026-09-21 at `upstream/main` `cf75aa32`, by symbol name; a line number is a pin, not a contract.

**The rail's five buttons toggle a KIND of pane, and the chat button toggles every chat column as one.**
`_LANDING_COLLAPSE_JS` (`kernel/kernel.py`) keeps one flag per registered pane in `romp-panes` (`po`), and
`togglePane(k)` flips it and re-applies `body.po-<k>`. The chat's flag is one flag. The shell's CSS hides the
first column and every later one by that one class: `body:not(.po-chat) #chat-pane{display:none}` and
`body:not(.po-chat) .chat-col, body:not(.po-chat) .gv-chat{display:none}` (`_LANDING_SPLIT_JS`'s style). The
buttons are generated server-side from `_pane_order()`, one `.rail-btn[data-pane=<id>]` per registered
pane; a chat column made by dragging a tab out is NOT a registered pane. It is a client-made
`<div class="pane chat-col" id="chat-pane-N">` around an iframe at `/chat?col=N`, registered with the
geometry engine only (`__rompRegisterPane`), and the kit recognises it by its id (`isChatPane` in
`ui/webview/pane-dock.ts`).

**Two stores hold two different facts.** `romp-chat-cols` (the split script, per browser) holds MEMBERSHIP:
which sessions each later column holds (`cols`, each `{n, ids}`, a bottom pane with `place:'below'`, its
`parent` and `ratio`); the first column derives its members as everything not listed. `romp-layout` (the
kit, per browser) holds PLACE: the split tree of panes with its ratios, and a `parked` list. The rail's
`romp-panes` holds the five on/off flags. Nothing today records where a hidden chat column was.

**A hide PARKS; a show re-opens at a DEFAULT dock, not where the pane was.** With the kit on, the engine
reads what the shell shows (`shown()` in `ui/webview/panedock-main.ts`: the first chat and every
`.pane.chat-col`, only while `po-chat` is on) and reconciles the tree with it (`reconcileShown` in
`pane-dock.ts`). A leaf no longer shown is parked (`closePane`: the leaf leaves the tree, its parent split
collapses, the id joins `parked`, the iframe stays mounted and hidden). A shown pane not in the tree opens at
`defaultDock`: a chat column right of the LAST chat leaf, the first chat left of everything, the outline
right of the chat side, the feed right of the outline, the rest at the right end. So the tree forgets the
column's place at the hide, and the show puts every chat column back in a default place. The lab for the
fix recorded exactly this: a column docked UNDER the feed (leaves `chat-pane, fleet-pane, feed-pane,
chat-pane-2, tl-pane`) came back RIGHT OF the first chat after the hide and show (`chat-pane, chat-pane-2,
fleet-pane, feed-pane, tl-pane`). The same holds for the feed or the outline hidden and shown: they too
return to their default docks, so the rail rearranges whenever a user has moved a pane. This is the
premise the user's expectation contradicts.

**A chat column lives while it holds a session.** `moveTab(sid, to)` is the one mutation of membership
(`'new'` opens a column, `'down'` a bottom pane, a number joins that column); an entry left empty closes
its column (`close(n)`: its sessions return to the first column, the pane and its gutter go). The palette
carries the same moves (`chat.split`, "Move this session to a new column"; `chat.closeSplit`;
`chat.moveToNextColumn` and its twin). A move into a new column brings a hidden chat group forward first
(`__rompPaneToggle('chat', true)` inside `moveTab`). At most four panes (`MAX`, `canSplit`).

**The phone shows one pane at a time**: `mobile()` refuses every split and `__rompChatSets` is null there;
the tab bar has one chat tab. Whatever the desktop rail does, the phone keeps one chat.

**The two drags are one protocol.** The strip's own drag (`render.ts` `wireTabDrag`, the reorder within a
strip) posts `{romp:"tabDrag", on, sid, name, stripH}` at its dragstart and `{on:false}` at its dragend; the
shell mounts hit areas for the gesture (the kit's `.pd-tabzone`, the split script's `.col-drop`) and a drop
on one of them runs `moveTab`. The chat session that owns the strip is adding an in-strip drag ghost; nothing
here changes the strip.

## 2. What "show" would have to remember

The user expects the arrangement before the hide. Today two things are lost at the hide: the parked leaf's
PLACE (which split it sat in, at which index, with which ratio) and, once its parent split collapses, the
SHAPE of the tree around it. Restoring the arrangement means remembering the tree, not the leaf: a snapshot
of the whole tree at the hide, restored at the show when the same set of panes comes back; when the set has
changed meanwhile (a pane toggled while the chats were hidden, a column that emptied and closed while
hidden), the panes present are placed from the snapshot and the missing ones dropped, the rest at their
default docks. The layout store's `v: 1` shape takes an optional field (a remembered tree beside `parked`)
that an older bundle ignores, so no migration.

Sharpened by the code (2026-09-21, the feature PR): the memory is not restored whole and then patched; a returning
pane is INSERTED beside the nearest remembered neighbour the tree still shows, on the side it had, with the share it
had (a sibling when that neighbour's parent is the remembered split itself, else the two wrapped in a split of the
remembered direction, so a group the memory kept apart comes back as a group). When nothing moved since the hide the
insertions rebuild the remembered tree exactly, shares included; when something did, it stands: a move puts the
pane beside its neighbour where the neighbour is now, a resize keeps its ratios (the memory compares shapes, never
ratios). The memory is taken at every park (rebuilt from the shown tree with the earlier parked panes re-inserted, so they
keep their places, as the next paragraph says), is reduced to the panes the layout still knows (a column closed while
hidden leaves no record), and is dropped once nothing is parked. The band keeps its own road (the root's bottom, fixed); a tab drop's hint
wins over the memory for its column; the phone is untouched, since the kit stays off there.

Sharpened once more by the review of the feature PR (2026-09-21): the memory is REBUILT at every park from the shown
tree, with the earlier parked panes re-inserted by the show's own rule, so a pane turned on or a column opened while
another was hidden is known to it and a resize made meanwhile keeps its ratios. The band is the neighbour of last
resort: with every row pane hidden, a shown pane comes back above the band (a column over it, never a row beside it),
and the memory-less road does the same. A stranger pane (one the memory never knew, turned on while a pane was
hidden) in the neighbour's split does not stop the returning pane joining that split as a sibling with its remembered
share, so the room comes from the whole row and not from the neighbour alone; only a split the memory knew as a
separate group (a chat over its feed inside a row) wraps, so that group comes back as a group.

The band is the neighbour of last resort only when it is ALL the tree shows (the second review of the feature PR,
2026-09-21): with a stranger pane shown above the band, a returning pane whose remembered neighbours are all hidden takes
its default dock beside the stranger instead of a full-width row of its own between the stranger and the band. The cost,
accepted: at any park made while only strangers and the band are shown (a stranger turned off, a second stranger toggled,
the band turned off) the HIDDEN panes' remembered places are dropped, since none of them has a shown neighbour to be
re-inserted beside; the memory itself stands, rebuilt from the strangers' tree, which keeps only their places (the store
keeps writing it, and a parked stranger keeps its place). The hidden panes then come back at their default docks around the
first one shown, so the shape may match the seed's but
the shares are the default dock's (the seed, every pane hidden, a stranger on and off, the three back: 493, 246.5 and 246.5 px
against the seed's 441.5, 250.2 and 294.3 px at 1000 px), and a non-flat arrangement (the feed under the chat) comes back a flat row.
With the band OFF the same holds without the band: a pane whose remembered neighbours are all hidden has no place to be
re-inserted at a stranger's park, waits in the parked list without a place, and returns at its default dock, which the
rule intends (keeping the old memory would cost the stranger its place).

## 3. The options

**A. One chat button toggles every chat column as one group; hide remembers the tree, show restores it.**
The user's expectation, and the smallest change to what the buttons mean: the rail hides and shows a kind
of pane, it never rearranges. The mechanism of section 2, in the pure module (`reconcileShown` and a
remembered tree in the layout), with the same rule for every button: the feed hidden and shown comes back
where it was too. Costs: a pure-module change with node tests; one served lab (hide and show under a moved
column, a column closed while hidden, a pane toggled while hidden); no new chrome, no store migration; the
phone unchanged. Re-join under A: a dragged-out tab returning to the strip empties its column, the column
closes, the kit prunes its park (`present` in `reconcileShown`) and the fix's `endDragFrom` ends the drag;
a remembered tree that names the closed column drops it at the restore.

**B. A column made by dragging a tab out is a pane of its own, with its own presence in the rail.** A
button per chat column, made client-side (the rail is generated from registered panes; a column is not
one), each toggling its own column; the chat button becomes the first column's alone. Costs: buttons that
appear and vanish with columns (their number is reused after a close, `nextNumber`), a label problem (a
column has no name of its own; its members change), the phone's tab bar with no counterpart, per-column
flags in `romp-panes` or a new store, a per-column hidden class the split script's CSS does not have, and
more resting chrome, against the kit's line of no resting chrome (`plans/pane-docking.md` section 3). It
also splits the meaning of the one button the user already knows. Re-join under B: the column's button
must go with the column and its flag be pruned, one more thing to get wrong.

**C. One chat button carrying a small count, with a menu to toggle columns one by one.** The button reads
"chat" with a count of the later columns; a click toggles the group as today; a secondary gesture (the
shared menu builder, `ui/webview/ctx-menu.ts`, the Sessions pane's row menu precedent) lists the columns
by their members' names with a checkbox each. Costs: A's mechanism is needed anyway (a column hidden alone
must come back where it was); per-column hidden flags and a per-column hidden class, on both the kit's
`shown()` and the split script's CSS; the menu; the phone unchanged. Worth it only if hiding ONE column
while keeping another is a real want, which the user has not said; the count alone (no menu) is cheap and
can be added to A later without the rest.

## 4. Recommendation

**A**, generalised to every rail button: a hide remembers the tree and a show restores it when the same
panes return, else places what is present from the memory and the rest at their default docks. It answers
the user's expectation directly, keeps the buttons' meaning (one button per kind; the chat kind is every
chat column), adds no chrome, and makes the system consistent, since today the feed and the outline are
rearranged by the rail in the same way and nobody has asked for that either. The count on the chat button
(C without the menu) is an optional addition once A ships, if seeing how many chat columns are hidden turns
out to matter.

Under every option the re-join rule stands: a dragged-out tab returning to a strip joins it, the emptied
column closes, every record of that column (its park, its remembered place, any flag or button) goes with
it, and the drag that carried the tab ends with the column (PR 1978).

## 5. For the user to decide

1. A as recommended, or A with the count on the chat button, or C in full.
2. Whether the remembered tree is a rule for every rail button (the recommendation) or for the chat button
   alone.
3. Nothing changes on the phone under any option; say so if that is wrong.

## 6. Decision

The user decided (2026-09-21, about 2:20 PM PT, relayed by the manager): **option A as recommended.** One chat
button for the whole chat group; a hide remembers the arrangement and a show restores it, as a rule for EVERY
rail button, so the feed and the outline stop rearranging too. Nothing changes on the phone. No count on the
button and no per-column menu now; the count stays an optional later addition.

What follows from it, for the code (a `feature` PR, unarmed, red-first): the remembered tree sits beside
`parked` in the layout store's `v: 1` shape (an optional field an older bundle ignores) and is restored at a
show when the same set of panes returns; when the set changed meanwhile (a column closed while hidden, a pane
toggled while hidden), the panes present are placed from the memory and the rest at their default docks. The
re-join rule stands: a dragged-out tab returning to a strip empties its column, the column closes, and every
record of it goes, the remembered place included. Section 2 is the design line; sharpened there if the code
needs it.
