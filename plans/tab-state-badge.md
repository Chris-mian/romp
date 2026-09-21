# Tab state badge (design note)

Status: CONFIRMED by the user (2026-09-21). The earlier stacked model is replaced by the model below: only Needs you is a top-right dot, retrying moves to the left status dot under badge mode, Blocked is unchanged. Code follows.

The badge is a top-right MAGENTA dot for Needs you, and nothing else. On seeing the stack mockups the user separated the three ring states by kind (2026-09-21): retrying is not an attention state, it is an alternative to working, so it belongs on the LEFT status dot (amber), not a top-right badge; Blocked is a hard run-state stop that outranks working or anything else and keeps its red dashed ring and red fill as today; only Needs you, which can ride any run state, gets the top-right dot. So there is no stack and no precedence among badges: at most one dot (Needs you) sits at the top right. The setting changes two shapes, the Needs-you cue (ring to top-right dot) and the retrying cue (ring to left amber dot); working, idle and Blocked are untouched. Default OFF; the dashed ring stays available.

## Why

The user asked (2026-09-21) for a switchable experiment: show a session's state as a small dot rather than the dashed outline ring, to see whether it reads better. The first model put a dot per state at the top right, stacked. After the mockups the user refined it: only Needs you is a top-right dot; retrying is a run state and moves to the left dot; Blocked keeps the ring. This note is that refined model.

This note does not reopen the ring renames or the state tokens; those are the user's decisions, recorded in plans/needs-you.md.

## The states today (the premise, read in code)

Two places show a tab's state today: the dashed outline RING and the left STATUS DOT.

The RING is one of three, chosen by a widget registry since 2026-09-14; the class names are not literal:
- `ring-needs-you` is the RED "Blocked" ring (a live prompt or an on-you API stop), `ui/webview/styles.css:593`, drawn from `--state`.
- `ring-waiting-on-you` is the MAGENTA "Needs you" ring (a filed needs-you card), `ui/webview/styles.css:601`, from `--st-needs-bg`.
- `ring-retrying` is the AMBER "Retrying" ring, `ui/webview/styles.css:593` (shares the red rule, reads `--state` from `.tab-retrying`).
A ring is an `outline` inset by `outline-offset: -2px`, so it takes no layout space. `tabRingId` (`tab-state.ts:66`) picks the first of `RING_ORDER` (`tab-state.ts:45`) whose switch is on and predicate (`RING_TEST`, `tab-state.ts:46`) holds; `composeTabRing` (`tab-widgets.ts:154`) puts on exactly that one; `render.ts:6354` calls it per tab per paint. Tokens: `--st-needs-bg #d946ef` (`styles.css:228`, light `#a21caf` `:310`), `--st-retrying-bg #e67e22` (`:222`, light `#9C4A0C` `:304`), `--st-blocked-bg #e5484d` (`:202`), `--st-awaiting-bg #c0392b` (`:196`).

The left STATUS DOT is `.tab-dot`, classed by `tabDotClass` (`tab-state.ts:133`): working is `.tab-dot` (gold `--st-working-bg`, `styles.css:603`), awaitingBg is `.tab-dot await` (green `--st-awaitbg-bg`, `:604`), opening is `.tab-dot opening` (`:615`), an unknown state is `.tab-dot unknown` (a grey ring, `:611`), and EVERYTHING ELSE, including retrying and blocked, is `.tab-dot none` (hidden, `:607`). So today the left dot shows working and awaiting only; retrying shows as the amber ring and blocked as the red ring plus fill, neither colouring the dot. The dot is composed as the "before" widget (`render.ts:6368`). The mobile switcher's leading dot maps the same: `#mcur .wd` and `.mrow .workdot` are gold (`--st-working-bg`), `.await` green (`--st-awaitbg-bg`); needs-you shows there as `#mcur.ask`'s dashed magenta border (`kernel/kernel.py:60893`) and `.mrow.ask`'s magenta left bar (`:60929`).

## The Needs-you dot

The badge is one magenta dot at the tab's top-right corner, shown only when the tab is in the Needs-you state (`RING_TEST["ring-waiting-on-you"]`: `status.needsYou === true` and the tab is not closed).

**Shape and place.** A round dot 8px across (the user approved this from the mockup, 2026-09-21), `border-radius: 50%`, `position: absolute` on `.tab`, `top: 2px; right: 2px` so it clears the tab's 6px top corner radius (`styles.css:529`) and sits fully inside the border box. `.tab` is already `position: relative` (`styles.css:525`), so the dot joins no flex flow: the tab's size does not change and the status dot, label, host prefix, context gauge, hot-key keycap and close all keep their places. It draws on top (z above the fill and any inset outline) with `pointer-events: none`.

**Contained.** The dot stays within the border box, never above the top edge, so `#tabbar`'s horizontal clip (`styles.css:401`) cannot cut it; the tab sets no `overflow` (`styles.css:523`), so it does not clip the dot. Active, inactive and peek tabs place it identically (a peek is a normal-size tab, `styles.css:591`); only the contrast floor differs by ground (below). The dot is at the right; the loading swirl rides the left dot slot (`styles.css:695`), so the two never meet.

**One top-right dot, no stack; it carries the count.** Needs you is the only top-right dot, so there is never more than one at the top right. It carries how many things need you in the session (see the count below): preferred as a black number in the dot, with a capped series of dots as the fallback.

## The count in the Needs-you dot

The Needs-you dot carries the count of things that need you in the session (the user, 2026-09-21). Two styles are drawn for the user to pick from the mockups; the choice is FIXED for all tabs, since the dot's pixel size is the same on every tab, so it is one decision, not a per-tab switch:

- PREFERRED: a black number in the dot. The dot grows to about 12 to 14px to fit the digits (the mockup sets the exact size), still contained at the top-right and still moving nothing; black digits at a legible size on the magenta. A count of one shows "1", not a bare dot. One and two digits fit; past 99 the dot shows "99+".
- FALLBACK, if a legible number does not fit at a contained dot size: a series of dots, one per Needs-you item, in the horizontal top-aligned row (each half a dot to the left of the one before it, the most recent at the corner), capped at FOUR. Five or more items still show exactly four dots, with no plus and no overflow marker; the fourth dot stands for "four or more".

Source, in code, so the readings never disagree: the count is `needsYouCount`, an ADDITIVE wire field beside the `needsYou` boolean, computed where the boolean is (the kernel's per-session read in build_session, over the session's needs-input rows, the same set the box lists and the feed's Needs-you column holds). An older page without the field shows a bare dot from the boolean; a newer page shows the count. The contrast pin adds black-on-magenta in both themes for the numbered style.

## Retrying moves to the left status dot

Under badge mode, retrying stops being the amber ring and becomes an amber LEFT dot: `tabDotClass` gains a retrying case returning `.tab-dot retrying`, and a `.tab-dot.retrying { background: var(--st-retrying-bg) }` rule joins the dot colours at `styles.css:604`. This sits retrying beside working and awaiting as a run-state colour on the one dot, which is what the user judged it to be. Working still outranks nothing it did not before; the dot shows the tab's single run state (`tabStateClass`), so working, awaitingBg and retrying never collide on it.

Decided (the user, 2026-09-21): the retrying RING stays in RING mode, byte-identical to today; the left-dot retrying appears only under BADGE mode. Ring mode is unchanged, so a ring-mode-unchanged pin guards that turning the badge off leaves the retrying amber ring and no retrying dot.

## Blocked is unchanged

Blocked keeps its red dashed ring (`ring-needs-you` on a `tab-blocked` tab) and its translucent red fill (`styles.css:555`) in BOTH modes. It is a hard run-state stop that outranks the other run states, so it is not a top-right dot and not a left-dot colour: the whole-tab red ring and fill are the loudest cue and stay. No re-gating is needed (the ring class stays on a blocked tab), which reverses the earlier note's plan to re-gate the fill.

## Colours and the contrast floors

Two colours move: the Needs-you magenta (`--st-needs-bg`) as the top-right dot, and the retrying amber (`--st-retrying-bg`) as the left dot, both in both themes, reusing the existing tokens.

Each is a filled dot on a ground it did not sit on before (the Needs-you dot on the tab face; the retrying dot in the left slot over the tab face), so pin both with the Needs-you arc's validator in `ui/webview/theme-parity.test.ts`: `deltaE` (OKLab x100), `cvdWorst` (protan and deutan, the worse), WCAG `contrast`. Floors: deltaE at least 15 for full-colour readers, at least 8 under the two deficiencies; WCAG 3:1 (a filled dot is large chrome, not text). Add the magenta-on-tab-ground and amber-on-tab-ground pairs (active and inactive, dark and light) to the ring-hue test and PAIRS table; the numbers for the ring hues are in plans/needs-you.md.

## The phone switcher

The same split holds on the phone. Under badge mode: Needs you becomes a magenta dot at the top-right corner of the current-session chip (`#mcur`) and of each row (`.mrow`), contained the same way (absolute, inset, on top, `pointer-events: none`; both need `position: relative`), replacing `#mcur.ask`'s dashed border (`kernel/kernel.py:60893`) and `.mrow.ask`'s magenta left bar (`:60929`). Retrying becomes an amber leading dot (`#mcur .wd` / `.mrow .workdot` gain a retrying colour beside `.await`). Blocked is unchanged. The leading gold/green working/await dot stays. The phone CSS and JS live in the kernel's mobile strings, so this is drawn there, not in the webview tab renderer. The phone's Needs-you dot carries the count in the same style chosen for the desktop.

## The setting

A per-browser boolean `tabStateBadge`, default false, a checkbox in the gear's Tab strip section beside the tab lock (`ui/webview/gear.js:233`), following the tab lock's pattern on `RompSettings` (`settings.ts:34`), `DEFAULT_SETTINGS` (`:80`) and the literal-true read in `loadSettings` (`:91`). Per browser, fanned out by settingsSync (`gear.js` save `:444` and `:452`, host repost `extension.ts:385`, receive `settings.ts:166`). The gear's preview (`gear.js` demoTab `:973`, paintWidgets `:1039`; `gear.css:329`) shows the Needs-you dot and the retrying left dot when the switch is on, the ring when off. Flipping repaints in place, no reload (the settings event re-renders the strip). The switch changes only the Needs-you and retrying shapes; the dashed ring stays available (badge off is today's behaviour), and Blocked is the same either way. Default OFF; the user's follow-up decision is that the badge becomes the default later, in a separate change.

## Red-first tests to plan

All served labs run under `ROMP_SERVED_TESTS_REQUIRE=1`.

1. The Needs-you dot, contained, nothing moved (served lab). Seed a needs-you session. Measure the tab's width and the label's left edge with the badge off. Flip `tabStateBadge` on. Assert the dot is present, its rect inside the tab's rect at the top-right, the tab's width and the label unchanged, and no dashed ring. Red at the base: no dot.
2. Retrying on the left dot (served lab). A retrying session under badge mode shows the amber left dot (`.tab-dot.retrying`) and NO amber ring; under ring mode it shows the amber ring, byte-identical to today (the user decided ring mode is unchanged). A ring-mode-unchanged pin guards that turning the badge off restores the amber ring and shows no retrying dot. Red at the base: no retrying dot class.
3. Blocked unchanged (served lab). A blocked session shows the red ring and red fill in both modes, and no top-right dot. Red at the base: only if the code wrongly moved it.
4. Contrast and colour-vision (theme-parity). Add the magenta-on-ground and amber-on-ground pairs to `theme-parity.test.ts` at the floors above, both themes, active and inactive. Red at the base: the pairs are not in the table.
5. Gear preview. The preview shows the Needs-you dot and the retrying left dot when on, the ring when off. Red at the base: no badge branch.
6. Phone (served lab, phone layout). Under badge mode the Needs-you magenta dot sits at the chip and row corner (the dashed border and left bar gone), retrying is the amber leading dot, Blocked is unchanged, the working/await dot stays. Red at the base: no phone dot.
7. The count in the dot (served lab, once the style is picked). Numbered: the black count in the dot per state at 1, 2 and 12. Or the capped series: one dot per item at 1, 2, 4 and 6 items (four at most, the fourth for four-or-more). The count moves when the session's Needs-you rows change. Red at the base: no count.
8. The needsYouCount wire field. Additive beside needsYou, computed in build_session over the session's needs-input rows, and pinned in the wire census; the dot, the box header and the feed's Needs-you column read the one field, so a divergence is a red. Red at the base: the field is absent, or diverges from the box's row count.

## Decided by the user (2026-09-21)

- Only Needs you is a top-right dot; no stack, no precedence.
- Retrying moves to the left status dot (amber), as a run state.
- Blocked is unchanged: red ring plus fill, in both modes, outranking the other run states.
- 8px dot at 2px inset, the horizontal top-aligned placement and the phone placement, approved from the mockups.
- The dashed ring stays available; the setting flips only the Needs-you and retrying shapes; the badge becomes the default later, in a separate change (default OFF now).
- The Needs-you dot carries a count (`needsYouCount`, an additive wire field). The style, a black number in the dot or a capped series of dots, is being picked from the mockups; the series caps at four dots for four or more, with no plus and no marker.

The retrying ring stays in ring mode (byte-identical to today); the left-dot retrying appears only under badge mode (the user confirmed, 2026-09-21).
