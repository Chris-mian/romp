# Needs you: one category, one colour, a hard-stop mark, and a box at the bottom of the chat (2026-09-20)

**The ask (the user, 2026-09-20; paraphrased throughout, never quoted).** The feed's middle column, titled Blocked
today, becomes **Needs you** and holds everything the user can give feedback on: what a session cannot proceed
without, what it asked the user to clarify, and what it offered to do next. That is one category on purpose, since
an item moves between those states; a session fully stopped (a permission or approval prompt, or an API error only the
user can clear) is a **hard stop**, a mark on top of the category, never a
second column. The two dashed tab rings are renamed and one is recoloured: the red ring (today's Needs you row in the
settings' Tab widgets: a stopped session) becomes **Blocked**; the yellow ring (today's Waiting on you row: a card of
the session's in the column) becomes **Needs you** and turns **magenta**, because yellow already means working. One
colour for the Needs you category, used the same way across the software: the column's chip and header, the tab ring,
the card's accent, and the outline of the box at the bottom of the chat; red is reserved for the hard stop alone (the
Blocked ring, and a red mark on a card whose session is hard-stopped, a subset of the column). A box at the bottom of
the chat transcript lists the session's Needs you cards, one line per card with a way to act, outlined in the
category's colour, behind a settings row that is on by default. Completed must be safe to clear unread: nothing left
undone, offered as a next step or asked about may land there.

This note is phase one. Phase two is the renames, the chip on every surface and the colour; phase three is the box; the
judges' change that makes Completed safe to clear is the judges' owner's note, `plans/judge-prompt-experiments.md`, linked
below. The user signed the design off on 2026-09-20 with three amendments, paraphrased and folded in below: the box wears
the awaiting box's dress in the category's colour and holds the session's Needs you items that are not hard blocks; the
Blocked chip becomes the Needs you chip on every surface that shows it, the sessions pane's lanes and chips, the outline's
rows, the feed's column chip and header, the chat's status chip, the tag overview, the settings' demos and the guide; the
rest stands as written.

## The premises, checked in the code

Every claim the design leans on, read at `upstream/main` 55d8e8f0.

- **The category.** The feed's three categories are a code table in two places kept equal by a test: `_CODE_BOARDS["feed"]`
  in `kernel/kernel.py` (`{"id": "needs_input", "title": "Blocked", "chip": "blocked"}`, `needsYou: "needs_input"`,
  `notify: ["needs_input", "completed"]`) and `FEED_BOARD` in `ui/webview/board-def.ts` (the same triple;
  `feed-col-head-case.test.ts` and `board-def.test.ts` hold the header triples to it, `tests/test_card_boards.py` holds
  the kernel table to the pane's). The pane's column header chip is `.fcol-chip-blocked { background: #c0392b }`
  (`ui/webview/feed.css`), the modal's blocked node label the same red as a white-on-red chip (`.st-question .ftree-meta`),
  and the checkbox notation's blocked mark a red pause inside a red ring (`.fcheck.question .fcheck-mark`, `--err`: `#c0392b` in feed.css's dark root, `#B02A1C` in its light root,
  which `feed.css` defines as `#c0392b` because that sheet has its own root). The category id `needs_input` is a wire
  value (every kernel and pane, federation included) and does not change; only the title, the chip class's colour and
  the copy do.
- **What files a card there.** The kernel's category expression in `_feed_session_entry` floors a card on a live
  permission or picker prompt (`_NEEDS_INPUT_STATES = ("permission", "picker")`, the card's `blocked.state`), on an API
  stop only the user can clear (the status flags `apiTooLong`, `apiSpendLimit`, `apiModelLimit`, `apiAuthErr`,
  `apiRefusal`, the same five `tabStateClass` reads for the red tab), on a judge's question verdict (a node with status
  `question`, the blocker's brief), on the idle hold of a blocking request, and on a held peer message (a notice card
  with `needsYou`), and on the judges' credential being refused (`_jauth_map`: the session's focus top floors with
  `blocked.state` `judgeAuth` and the `.fask-jauth` badge; the session itself runs, romp's analysis of it is down,
  and only the user can fix the key or the login). The hard stop is therefore already a distinguishable subset: the
  card carries `blocked.state` in the two prompt states, or its session's status carries one of the five API flags; a
  judge's question carries neither, and the credential refusal is a Needs you item without the mark by this note's
  own definition (the session is not stopped): its badge takes the category's token, and phase three's box row for
  it carries the credential fix as its action and no Clear, since a Clear would hide the fault while the refusals
  continue.
- **The rings.** `ui/webview/tab-state.ts` names three ring ids in precedence order: `ring-needs-you` (the RED ring;
  its test is `tabStateClass(s) === "tab-awaiting" || "tab-blocked"`, a live prompt or an on-you API stop),
  `ring-waiting-on-you` (the YELLOW ring; its test is `status.needsYou === true` and the tab not closed, the kernel's
  per-session read of the column in `build_session`), and `ring-retrying` (amber). The strip composes one ring, the
  first switched on whose test holds (`composeTabRing`); the folded group header's pip follows the same rule
  (`sectionPip`: `blocked` for the red ring, `ask` for the yellow). The sheet keys on the ring classes:
  `.tab.ring-needs-you, .tab.ring-retrying { outline: 2px dashed var(--state) }` where `--state` is the state class's
  colour (`--st-awaiting-bg #c0392b` for a live prompt, `--st-blocked-bg #e5484d` for an API stop), and
  `.tab.ring-waiting-on-you { outline: 2px dashed var(--st-ask-bg) }`, the ask yellow (`#f5d33f` dark, `#504100`
  light); the red ring adds a translucent red fill on an API-stopped tab. The settings rows are `RING_ROWS` in
  `ui/webview/tab-widgets.ts` (labels **Needs you**, **Waiting on you**, **Retrying**, with a description and a demo
  each), rendered by the gear from `ringWidgets()` under Tab widgets; the gear's demo tab wears the same classes
  through `gear.css`. So the ring today named Needs you is the hard stop, and the one named Waiting on you is the
  category: the user's renames put each name on the thing it means.
- **The ask yellow's other surfaces.** The same token paints the folded group header's pip (`.tab-group-pip.ask`), the
  phone picker's current-session chip border and row bar (`#mcur.ask`, `.mrow.ask` in the mobile page's inline
  sheet, `kernel/kernel.py`), and the settings' ring demo. `theme-parity.test.ts` pins the ring hue as a line on the
  page at 3:1 in both themes and its text pair, and the light palette's comment records the pairwise distances of every
  ring and dot hue under a red-green deficiency.
- **The chat's chip.** `ui/webview/status-chip.ts` is the one vocabulary for a session's state in a pill: the state
  `needsInput` (a live permission or picker prompt) reads **Blocked**, and the tag overview's rows say **Blocked** for
  a feed-filed card too (T322b, "the feed's column word"); **API error** is the on-you API stop. The guide's session
  paragraph says the chip follows the feed.
- **The bottom of the chat.** Two boxes sit between the transcript and the composer already: `#notices`, the approval
  box (`renderNotices`, plans/notice-cards.md "The chat pane's approval box"): the active session's standing needs-you
  NOTICE cards that carry actions, one row each, reconciled in place and keyed by item id, its clicks on one delegate,
  its rows a per-session slice `status.notices` on the session frame; and `#bg-tasks`, the background box
  (`renderBgTasks`). Both ride the transcript's bottom-box rule (a resize observer keeps an at-bottom reader at the
  bottom; `render.ts` names the three boxes `notices`, `bg-tasks`, `footer`). Neither has a settings switch today.
- **The colour red, three tokens.** `--st-awaiting-bg #c0392b` (a live prompt: the tab state, the column chip, the
  modal's chip, `--err`), `--st-blocked-bg #e5484d` (an API stop: the tab state, the API-error badge on a card, the
  group pip's `blocked`), and the alarm fill on a blocked tab. Magenta existed once more, as `--st-5xx-bg` (`#c026d3`
  dark, `#A21CAF` light) and the two literal inks of `.ah-c-r5xx` (`#e879f9` dark, `#86198F` light): the 5xx marks of
  the API-health cell's hover tip and detail (and the legend, on every hover), which sit on the LANDING page beside
  every session's state (`/perf` and `/api-health` answer JSON). Phase two moved the 5xx hue to a purple apart from the Needs you magenta and routed the inks through a token
  (below).
- **Notifications.** The bell and the phone push fire on a card ENTERING `needs_input` or `completed`
  (`_feed_notifications`, `notify: ["needs_input", "completed"]`); their copy names the card, not the column.
- **The docs.** `docs/guide.md` says Blocked seven times (the ring paragraph, the chip paragraph, the sessions
  overview, two chip glyphs); `docs/reference.md` twice (the restart notice card, an internal row name that stays).

## The design

### One category, Needs you, with a hard-stop mark on top

The middle column is **Needs you**. Its members are the cards the user can act on: a session stopped on a prompt or
an approval, a session stopped on an API error only they can clear, a question a session asked (the judge's
`question` verdict with its decision brief), a blocking request under the idle hold, a held peer message awaiting
approval, and the offers a session made of what to do next (the judges' change; see Completed below). The category
id stays `needs_input`; the title, the chip class's colour and every user-facing word change.

The **hard stop** is a mark ON a card in that column, never a place: a card whose session is fully stopped (its
`blocked.state` a prompt state, or its session's status carrying one of the five on-you API flags; a `judgeAuth`
state is not a stop and wears no mark) wears a red mark
where today's ⏸ live-block badge and ⚠ API-error badge sit (the same two elements: they are the hard stop already,
and they keep their red). A card in the column without the mark is something the user can answer at their pace while
the session goes on. The judge's question mark in the tree (the red pause in a ring, the white-on-red node label) is
NOT a hard stop and turns to the category's colour.

Why one category and not two (the road not taken): a Stopped column beside Needs you would split one decision across
two places and move a card twice as a session stops, asks and resumes; the user's steer was explicit that an item moves
between the states, and the card-move rule (cards move on new information, never on inference) prefers a mark that
appears and disappears on the card over a card that changes column.

### The rings: Blocked and Needs you

`ring-needs-you` (red, the hard stop) is renamed **Blocked**; `ring-waiting-on-you` (yellow, the column) is renamed
**Needs you** and recoloured to the category's magenta. The precedence stays red over magenta over amber, the tests
stay what they are (`tabStateClass` red states; `status.needsYou`), and the class ids in the code stay as they are
(they are wire-adjacent: `settings.tabWidgets.on` stores them by id, so a rename of the id would drop every user's
switch state; the labels and descriptions in `RING_ROWS`, the guide and the demo change). The folded header's pip
follows: `blocked` stays red, `ask` turns magenta. The phone picker's current-session chip border and row bar take
the magenta with the same token.

Keeping yellow (the road not taken): the ask yellow was chosen to sit apart from the working gold and the retrying
amber, and it does; but the user reads yellow as working, and a colour the user has to learn against their own
reading is the wrong colour. Keeping red for the column (the other road not taken): red on the column and red on the
hard-stop ring said the same thing about two different states, and most of the column's members would have worn a
magenta ring under a red header; the user asked for the inconsistency resolved in favour of one colour per meaning.

### The colour rule

One token, `--st-needs-bg` with its text pair `--st-needs-fg`, in `styles.css` and mirrored in `feed.css` (that sheet
has its own root; every state token is mirrored there today); the mobile page's inline sheet reads it with the dark value as its fallback (`var(--st-needs-bg,#d946ef)`), the pair itself arriving through styles.css:

- dark `#d946ef` on `#1e1e1e`: 4.8:1 as a line on the page, 5.2:1 for a dark text pair (`#2a0a2a`), 3.5:1 for white;
- light `#a21caf` on `#F1EAE2`: 5.3:1 on the page, 6.3:1 for white text.

Both clear the ring and pair floors `theme-parity.test.ts` holds (3:1), and the dark hue sits apart from the working
gold, the retrying amber and both reds under a red-green deficiency (the test's pairwise pins extend to it). The 5xx
marks of the API-health cell's tip and detail on the landing page (`--st-5xx-bg`, the `.ah-seg-serverErrors` fill;
`--st-5xx-ink`, the `.ah-c-r5xx` text) are a purple apart from the Needs you magenta in both themes: measured, OKLab
distance x100, dark fill `#7e22ce` 19.3 and ink `#c4b5fd` 22.8 from `#d946ef`, light fill and ink `#4c1d95` 18.0 from
`#a21caf` (the light 5xx value had been byte-identical to the token, the dark fill 7.5 away); theme-parity.test.ts pins
the token against the fill and the ink per theme at the categorical floor of 15.

Where the token paints, and only there:

- the feed's column header chip (`.fcol-chip-blocked` becomes the `needs` chip class; the chip class in the board
  schema, `"blocked"`, is a wire value on data boards' definitions and stays, so the class keeps its name and takes
  the new colour, and the schema's chip name is documented as the Needs you dress);
- the card's accent in that column: the judge's question mark and node label in the card's tree and the modal
  (`.st-question`, `.fcheck.question`), today red;
- the tab ring `ring-waiting-on-you` and the group pip `ask`;
- the phone picker's chip border and row bar;
- the outline of the Needs you box below (phase three);
- the settings' ring demo.
- the sessions pane's lane chip for a session in the column (`ui/romp-timeline-view.js`, `BADGE.needs`, drawn on the
  canvas in the same pair);
- the status chip's Needs you state, `.chip-needsInput` and its legacy twin `.chip-awaiting`, wherever the shared chip is
  painted: the bar under the transcript, the tag overview rows and the comment popover's statusline;

Red stays on: the Blocked ring and its translucent fill, the hard-stop marks on a card (the ⏸ live-block badge, the
⚠ API-error badge), the chat chip's **API error**, the unread passage's dashed box (a different meaning, the same
family, left alone by this note). Two card badges LEFT the red family in phase two, since neither is a hard stop: the
⚠ retrying badge (`.fask-retrying`) wears the retrying amber its ring, chip and lane badge already wear, and the
⚠ credential badge (`.fask-jauth`) is filled in the Needs you pair, filled against outlined kept.

### The status chip: Needs you on every surface

The chip that reads **Blocked** today becomes the **Needs you** chip, and the rename feeds out to every surface that shows
it (the user's second amendment): the chat's status chip under the transcript, the tag overview's rows, the sessions pane's
lanes and their chips, the outline pane's rows, the feed's column chip and header, the settings' demos and the guide. One
vocabulary (`status-chip.ts`, `CHIP_LABEL`) says the word once for the `needsInput` state and its legacy `awaiting`
spelling; the chip wears the category's colour (`.chip-needsInput` on the Needs you token), since the chip names the
category, and the hard stop is the ring and the card's red marks, never the chip's word. **API error** stays, red. Phase two
sweeps every surface for the word and the chip class, in the code and in the inline copies the kernel serves (the phone
page, the sessions pane), and the lab reads the word on each.

### The Needs you box at the bottom of the chat (phase three)

The box wears the awaiting box's dress in the category's colour (the user's first amendment): the same appearance as the
background-tasks box `#bg-tasks` today, a thin line around the edge, the same shape and the same placement between the
transcript and the composer, the line in the Needs you token instead of the await-green; and its rows are the shape the
closed requests pull request drew (#994, "Requests from sessions: what a session needs from you, held until you or it says otherwise": one line per request at the bottom of the transcript, Reply and Dismiss), one line per item with a way to act. It holds the session's Needs you items that are NOT
hard blocks: the permission and approval prompts the chat already shows inline stay out, and the box lists the judge's
questions (the card's title, its decision brief as the line), the offers a session made, the blocking requests under the
idle hold, and the held peer messages with their actions. The approval box (`#notices`, plans/notice-cards.md) already is a
row-per-notice box above `#bg-tasks` with a per-session slice on the session frame; phase three widens its slice to every
Needs you card of the session's that is not a hard block, with the kind on each row (a notice with its stored actions; a
goal card with **Reply**, which targets the composer at the card as Follow up does, **Continue** where the card offers it,
and **Clear**), keeps its in-place reconcile and its one delegate, and dresses the box as the awaiting box in the token,
titled **Needs you** with the count. It shows when the session has such an item and hides otherwise; an item leaves with the
frame that drops it (the answer, the judge's re-file, the clear). A settings row under Chat, **Needs you box**, on by default,
hides it; with the box off the tab ring and the feed still say it.

### Completed is safe to clear unread

Nothing left undone, offered as a next step, or asked about may land in Completed: those are Needs you's. That is the
judges' change, whose design, measurement and landing gate are the judges' owner's note,
`plans/judge-prompt-experiments.md`: the closer's optional-offer clause inverted as the first candidate, the planner's
done op and the unblocker's moot rule as the second and third surfaces. This note's part is the contract the column
relies on: a card in Completed asks nothing of the user, so a Clear all over Completed loses nothing.

## Phases

1. **This note** (docs).
2. **The renames, the chip on every surface and the colour**, one PR (feature): `RING_ROWS` labels and descriptions;
   the token in the three sheets; the column title in both tables; the chip class's colour; the tree and modal question
   marks; the group pip; the phone picker's two rules; the chip's word in `status-chip.ts` and its colour, and every
   surface that shows the chip swept for the word and the class (the sessions pane's lanes and chips, the outline's rows,
   the settings' demos, the kernel's inline copies); the guide's ring, chip and overview paragraphs and the two chip glyphs;
   the reference's restart card line; the settings' demo. A served lab reads the COMPUTED colours on every surface in both
   themes (the column chip and header, a card's question mark, the modal's node label, the tab ring and the group pip, the
   phone picker's chip border and row bar, the settings' demo tab) and the WORDS on every surface that shows the chip (the
   two ring rows, the column header, the chat chip, the overview row, the sessions pane's lane chip, the outline's row).
   Every pin on the old title and the old ring names moves in the same commit.
3. **The box** (feature): the widened slice, the rows by kind, the awaiting dress in the token, the switch, and a chat
   lab: a card entering the column shows a row; Reply, Continue and Clear each remove it; a hard block shows no row; the
   switch hides the box and leaves the ring.

## Tests

- `theme-parity.test.ts`: the new token pair and the ring line in both themes; the pairwise distances extended.
- `tab-state.test.ts`, `tab-rings.test.ts`, `tab-widgets.test.ts`: the labels and the colour class; the precedence
  and the tests unchanged.
- `board-def.test.ts`, `feed-col-head-case.test.ts`, `tests/test_card_boards.py`: the header triple's new title,
  the two tables equal.
- `status-chip.test.ts`, `chip-label-case.test.ts`, `tab-snapshot.test.ts`: the chip's two words.
- The served labs: the colour lab above; `test_tab_widgets_browser.py`, `test_feed_focus_served.py`,
  `test_held_mail_chat_served.py`, `test_kernel_mobile.py` re-pointed to the words and the token.
- Phase three: a chat lab for the box (a row per item that is not a hard block; Reply, Continue and Clear each
  remove theirs; the switch hides the box and leaves the ring).

## Privacy

Synthetic fixtures only (the notes-api demo world, placeholder ids, `TESTHOST`); no session names or people in the
text or the tests.
