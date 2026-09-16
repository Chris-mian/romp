# Sessions pane: a context menu on a session's row (Rename, Delete)

The user (2026-09-16): right-click a session name in the Sessions panel's list to Rename or Delete it. Today only the
chat's tab strip has a session context menu; the Sessions pane (its script under ui/webview, a file still carrying the
pane's former name) has none, and its rows only open the session on click.

## The two items and their roads

One road per verb, the tab strip's, never a second one.

- **Rename.** The row's name becomes an inline input in place (the strip's `startTabRename` shape: the current name
  selected, Enter commits, Escape cancels, a blur commits like Enter). The commit posts the tab menu's exact wire
  message, `{type: "renameSession", id, name}`, through the pane's own host api. The kernel's arm validates the name
  (letters, digits, `. _ -`), refuses a thread's name, claims it against the live set, and pushes the new name to every
  surface: the strip's tab, the feed's cards, this row. Nothing is renamed locally ahead of the kernel: the row shows
  the input until the push lands (the strip does the same), so a refusal (the kernel's `warn` frame) leaves the old
  name standing. No undo beyond renaming again; the name is a label, mail, goals and history follow the session.
- **Delete.** The tab menu has no Delete item; the strip's delete road is its close button, and the pane takes that
  road exactly. The Sessions pane lists running sessions, so Delete means **end the session**: it asks first, with the
  strip's confirm (title `End "name"?`, the detail naming the open goals on its board and the standing sentence
  that the history stays on disk and the session can be revived from the picker or the timeline, buttons
  `End session` (danger) and `Cancel`), and on `End session` posts the strip's two messages in the strip's order,
  `{type: "endSession", id}` then `{type: "closeTab", id}`. The row leaves on the kernel's next push (the kill is the
  event; the pusher wakes on it), never locally ahead of it: the pane has no tab to drop and a row that vanished
  before the kill would be a lie if the kill failed. A running session is therefore stopped first through the
  confirm, not refused. Undo: none on this road; the confirm says how the session comes back (revive). A
  provisional row (a tab not yet built) is a running session too and takes the same road. Cancel changes nothing.

## The menu

- **Skin.** One menu vocabulary through the theme tokens (ui/CLAUDE.md): the menu is a `.ctx-menu` card with
  `.ctx-item` rows, each a `.ctx-item-label` and an optional `.ctx-item-sub` line, the Delete row wearing the danger
  colour the confirm button wears; `--menu-bg`, `--menu-fg`, `--menu-border`, `--menu-hover`, `--radius-menu`,
  `--shadow-menu`, 12px romp sans, sub-lines at 0.82em and 0.6 opacity. The pane's stylesheet gains the `.ctx-menu`
  rules by the tokens (the feed mirrored them the same way); no hex value outside a `var()` fallback.
- **Builder.** A small shared module, `ui/webview/ctx-menu.ts`: `openContextMenu(x, y, items, opts)` builds the card
  and its rows from `{label, sub?, danger?, pick()}` items, places it inside the viewport, dismisses on an outside
  press, Escape, scroll or blur, and gives the rows keyboard reach (arrows move, Enter or Space picks, Home and End).
  The Sessions pane uses it now. The tab menu, the feed's card menu and the file browser's row menu each build the
  same rows by hand today; moving them onto the builder is a later tidy, not this change (their pins hold their text).
- **Keyboard reach.** The row's head is focusable (`tabindex=0`); the ContextMenu key and Shift+F10 open the menu
  anchored to the row, Enter opens the session as a click does. The menu's own keys come from the builder.
- **Where it opens.** A right-click on the row's head (the name, the status dot, the mail mark): the goal rows below it
  keep their own click, and a right-click on them does nothing new.

## The lab (served, red first per road)

The dashboard page over a hermetic kernel with synthetic sessions (the notes-api world: web, api, tests, given as
registered SDK records with closed transcripts, so nothing is ever spawned), the chat pane and the Sessions pane up:

1. right-click api's row: the menu shows two rows, Rename and Delete, on the token card (computed background equals
   the theme's `--menu-bg` in both themes);
2. Rename: the inline input replaces the name, a new name typed and Enter posts `renameSession` once with that name,
   and the name propagates: the row reads the new name and the chat strip's tab for api reads it too, on the kernel's
   push; Escape on a second attempt leaves the name as it was and posts nothing; a refused name (a thread's) keeps the
   old name and the kernel's warning arrives;
3. Delete on a running session: the confirm opens with the strip's title, its detail names the session's open goal
   (a synthetic ledger with one open top), Cancel posts nothing and the row stays; `End session` posts `endSession`
   then `closeTab` for that id, the row leaves the pane and the tab leaves the strip;
4. keyboard: focus the row, Shift+F10 opens the menu, ArrowDown and Enter pick Delete, Escape closes the confirm.

Executed under ROMP_SERVED_TESTS_REQUIRE=1 with chromium, pinned Python 3.13, capped; source pins for the builder's
dismissal and key rules in a node test.

## Out of scope

Moving the existing menus onto the builder; a Delete item in the tab menu (its close button is the road); colours,
tags, hot keys, billing and folder moves from the Sessions pane (the tab menu has them; the ask names Rename and
Delete).
