# Tab state badge (design note)

Status: SIGNED OFF by the user (2026-09-21), with amendments folded in below (stacking, the phone badge, the ring kept, the red fill kept). Code follows; the dot's size awaits the mockup eyeball.

A tab state badge is an optional, default-OFF alternative to the dashed outline rings on the chat tab strip: a small round dot in a state's colour at a tab's top-right corner, inside the tab's box and drawn on top, standing in for the ring while it is on. It reuses the rings' own state predicates and colours. Two things differ from the ring: the shape, and that a tab in more than one state shows a small stack of dots, one per state, where the ring shows only the winner. The tab's size does not change and nothing else on the tab moves. Both the desktop tab and the phone switcher get it. The dashed ring stays available for anyone who prefers it: the two are mutually exclusive, chosen by one switch, default OFF for now (the user's follow-up decision is that the badge becomes the default later, in a separate change).

## Why

The user asked (2026-09-21) for a switchable experiment: instead of the dashed ring around a tab, a small round badge in the state colour at the tab's top-right corner, where an exponent would sit, to see whether it reads better than the ring. Off by default, so it can be turned on to compare.

This note does not reopen the ring renames or the state tokens; those are the user's decisions, recorded in plans/needs-you.md.

## The rings today (the premise, read in code)

The strip shows a tab's state as one of three dashed outline rings, chosen by a widget registry since 2026-09-14. The CSS class names are not literal:

- `ring-needs-you` is the RED "Blocked" ring (a live prompt or an on-you API stop), `ui/webview/styles.css:593`, drawn from the tab's `--state` (`outline: 2px dashed var(--state); outline-offset: -2px`).
- `ring-waiting-on-you` is the MAGENTA "Needs you" ring (a filed needs-you card), `ui/webview/styles.css:601`, drawn from `--st-needs-bg`.
- `ring-retrying` is the AMBER "Retrying" ring, `ui/webview/styles.css:593` (it shares the red rule and reads `--state` from `.tab-retrying`).

A ring is an `outline` inset by `outline-offset: -2px`, so it paints at the tab's edge and takes no layout space. Which ring a tab wears is `tabRingId` (`ui/webview/tab-state.ts:66`): the first entry of `RING_ORDER` (`ui/webview/tab-state.ts:45`, `["ring-needs-you", "ring-waiting-on-you", "ring-retrying"]`) whose switch is on and whose predicate (`RING_TEST`, `ui/webview/tab-state.ts:46`) holds. `composeTabRing` (`ui/webview/tab-widgets.ts:154`) removes every ring class then adds only the winner's, so exactly one ring paints and it never outlives its state; `ui/webview/render.ts:6354` calls it once per tab per paint. The state tokens: `--st-awaiting-bg #c0392b` (`styles.css:196`), `--st-blocked-bg #e5484d` (`:202`), `--st-retrying-bg #e67e22` (`:222`), `--st-needs-bg #d946ef` (`:228`); the light theme sets `--st-retrying-bg #9C4A0C` (`:304`) and `--st-needs-bg #a21caf` (`:310`).

## The badge

**Shape and place.** A round dot about 8px across, `border-radius: 50%`, `position: absolute` on `.tab`, anchored `top: 2px; right: 2px` so it clears the tab's 6px top corner radius (`styles.css:529`) and sits fully inside the border box. `.tab` is already `position: relative` (`styles.css:525`), so the absolute dot joins no flex flow: the tab's width and height stay identical and the status dot, label, host prefix, context gauge, hot-key keycap, and close control all keep their positions. The dot draws on top, at a z-index above the tab fill and any inset outline, and carries `pointer-events: none` so it never intercepts a click.

**Contained, not a protruding exponent.** The dot stays within the tab's border box, not above the top border like a true superscript. The strip (`#tabbar`) clips horizontally and scrolls vertically (`styles.css:401`), so a dot spilling over the top edge could be cut; a contained dot cannot. The tab sets no `overflow` (`styles.css:523`), so the tab itself never clips the dot.

**Active, inactive, and peek tabs.** The dot sits in the same corner on every tab. An active tab differs only in its background (`--tab-active-bg`, `styles.css:714`); an inactive tab is transparent over the strip ground. The placement is identical; only the contrast floor differs (see below). A peek tab (an ephemeral tab, `render.ts:1019`) is a normal-size box whose only marks are a faint dashed outline and an italic label (`styles.css:591`), no layout change, so the dot sits there unchanged. The peek's own outline marks an ephemeral tab, not a state, and stays.

**A stack, no number.** A tab in one state shows one dot; a tab in more than one shows a small stack, one dot per applicable state (see Stacking). No dot carries a count or numeral.

**No collision with the loading swirl.** While a tab loads, the swirl rides the status-dot slot at the tab's LEFT edge (`styles.css:695`, centred in the 7px dot box). The badge is at the right edge, so the two never overlap.

## Stacking, one dot per state (no precedence)

Where the ring shows only the winner, the badge shows EVERY applicable state, one dot each, stacked like a small pile of coins so the depth reads. The user chose this over a single winning badge (2026-09-21).

Geometry (chosen here; the user corrects along the way): the dots stack from the top-right corner INTO the tab, fanning down and left, so the pile stays contained in the tab's box. The most urgent sits at the corner and on top; each less-urgent dot is offset from the one above it by HALF a dot (4px for an 8px dot, so neighbours overlap by half) and drawn beneath it, with a drop shadow on each so the layering reads. Order, most urgent first (top of the pile): red (Blocked), then magenta (Needs you), then amber (Retrying). So the first dot sits at `top:2px right:2px`, a second at `top:6px right:6px`, a third at `top:10px right:10px`, each 8px, red highest in z. A three-dot stack ends by about `top:18px right:18px`, well inside a tab (about 28px tall), so it stays contained.

The applicable states are the ring predicates (`RING_TEST`, `tab-state.ts:46`) read independently, not collapsed to one by `tabRingId`; the z-order and offset sequence reuse `RING_ORDER` (`tab-state.ts:45`), so the badge stack and the ring agree on which state is most urgent.

## Colours and the contrast floors

The badge uses the three existing state tokens, the same token its matching ring reads: red `var(--state)` (`--st-awaiting-bg` or `--st-blocked-bg`), magenta `--st-needs-bg`, amber `--st-retrying-bg`, in both themes.

A filled dot sits on the tab's face, a different ground from the ring's edge line, so its colours need their own contrast and colour-vision check against the tab grounds. The check is the one the Needs-you arc built, in `ui/webview/theme-parity.test.ts`: `deltaE` (OKLab distance, times 100), `cvdWorst` (protan and deutan simulations, the worse of the two), and WCAG `contrast`. The floors that test applies: deltaE at least 15 for full-colour readers and at least 8 under the two deficiencies, WCAG 3:1 for a line or large chrome. A filled dot is large chrome, so its floor is 3:1, not the 4.5:1 text floor. The ring-hue numbers are recorded in plans/needs-you.md's colour section.

Pin the badge by adding its hue-on-ground pairs to that test's ring-hue test and PAIRS table: each state colour against both the active and the inactive tab ground, dark and light. The three hues already pass as ring lines; the pin confirms they also clear the floors as a filled dot on the tab face.

## The hard-blocked red fill

A hard-blocked tab today carries a translucent red fill (`styles.css:555`, `.tab.tab-blocked.ring-needs-you { background: rgba(229,72,77,0.30) }`) so it reads as blocked at a glance, and that fill is gated on the RED ring class. Decided (the user, 2026-09-21): keep the fill under badge mode. It is a separate at-a-glance cue the user chose (2026-06-18), not the ring itself. Keeping it means re-gating it on `.tab-blocked` (with the badge) rather than on `.ring-needs-you`, since the ring class is absent under badge mode.

## The phone tab bar: the badge on the container's corner

The phone gets the badge now (the user, 2026-09-21). Under `(pointer:coarse) and (max-width:1024px)` the chat page hides the desktop strip (`kernel/kernel.py:60872`) and swaps in its own switcher (`_CHAT_MOBILE_CSS`, `kernel/kernel.py:60865`): one full-width current-session chip (`#mcur`, `:60879`) and a dropdown of full-width rows (`.mrow`, `:60915`). Neither is a per-session tab box, so the badge sits at the CONTAINER's top-right corner instead, the chip's and each row's, contained the same way (absolute, inset from the corner, on top, `pointer-events: none`), and stacks the same way for more than one state. Both `#mcur` and `.mrow` need `position: relative` for the absolute dot to anchor.

Under badge mode the phone's ring-equivalents give way to the badges, so the either/or holds here too: the dashed chip border (`#mcur.ask`, `:60893`) and the magenta left bar on a row (`.mrow.ask`, `:60929`) are suppressed. The leading colour dot (`#mcur .wd`, `.mrow .workdot`) stays, because it is a working/await indicator, not a ring. The phone's CSS and JS live in the kernel's mobile strings, so the badge is drawn there (a small absolute element the mobile JS appends to `#mcur` and each `.mrow`, coloured from the same state tokens), not in the webview's tab renderer.

## The setting

**Name and home.** A per-browser boolean `tabStateBadge`, default false, a checkbox in the gear's Tab strip section beside the tab lock (`ui/webview/gear.js:233`). It follows the tab lock's pattern: declared on `RompSettings` (`ui/webview/settings.ts:34`), defaulted `false` in `DEFAULT_SETTINGS` (`settings.ts:80`), and read default-OFF with the literal-true idiom in `loadSettings` (`settings.ts:91`).

**Per-browser fan-out.** Like every gear setting, it is per browser and fanned out by settingsSync: `gear.js` `save` (`:444`) writes localStorage and posts `settingsSync` (`:452`); the host reposts to every other pane (`vscode-extension/src/extension.ts:385`); the receiving pane writes its own store and raises the settings event (`settings.ts:166`).

**Preview.** The gear's settings preview renders a sample tab (`gear.js` demoTab `:973`, paintWidgets `:1039`). With the switch on it shows the badge in each of the three state colours, the way the ring preview shows the rings today (`ui/webview/gear.css:329`). Add a preview rule beside the ring mirror.

**On the flip.** Tabs repaint in place, no reload. The settings event re-renders the strip, and `composeTabRing` re-composes each tab: badge on removes the ring class and shows the dot, badge off restores the ring. The ring widget switches already flip this way without a reload.

**Ring and badge are one either/or, both kept.** The dashed ring stays available for anyone who prefers it; the switch chooses between them for all states at once: badge on suppresses the dashed ring per tab (and the phone's ring-equivalents), badge off is today's behaviour. They are never both shown. Default OFF now; the user's follow-up decision is that the badge becomes the default later, in a separate change.

## Red-first tests to plan

All served labs run under `ROMP_SERVED_TESTS_REQUIRE=1`.

1. The badge, per state, contained, nothing moved (served lab). Seed a session in each of the three states (blocked, needs-you, retrying). Measure the tab's width and the label's left edge with the badge off (ring mode). Flip `tabStateBadge` on. Assert, per state: the badge element is present; its bounding rect is inside the tab's rect at the top-right; the tab's width and the label's left edge are unchanged from ring mode; no dashed outline paints (the ring class is absent). Red at the base: no badge element exists.
2. Contrast and colour-vision (theme-parity). Add the badge hue-on-ground pairs to `theme-parity.test.ts`: each state colour against the active and the inactive tab ground, dark and light, at the deltaE and WCAG floors above. Red at the base: the pairs are not in the table.
3. Stacking (no precedence). A tab in more than one state shows one dot PER applicable state, each dot's rect offset from its neighbour by half a dot and every dot inside the tab's rect, the most urgent at the corner and drawn on top (red over magenta over amber). Assert the count of dots equals the count of applicable states and the offsets. Red at the base: no badge, or a single winner.
4. Gear preview. With the switch on, the preview sample tab shows the badge in each state colour; with it off, the ring. A DOM test on the preview builder. Red at the base: the preview has no badge branch.
5. Phone (served lab, phone layout under the mobile media rule). Under badge mode the phone shows the badge at the container's top-right corner (the chip `#mcur` and a row `.mrow`), its rect inside the container's rect, stacked the same way for more than one state; the dashed chip border and the magenta left bar are gone (the either/or), and the leading colour dot stays. Red at the base: no badge on the phone.

## Decided by the user (2026-09-21)

The sign-off settled the questions this note had raised:

- The dashed ring STAYS available; badge and ring are mutually exclusive; the badge becomes the DEFAULT later, in a separate change (default OFF now).
- The hard-blocked translucent red fill STAYS under badge mode, re-gated off the ring class.
- No precedence: every applicable state gets its own dot, stacked (see Stacking).
- The phone GETS a badge now, at the container's corner (see the phone section).
- Size: an 8px dot at a 2px inset to start.

One thing still travels to the user as a mockup, not a question: the dot's exact diameter and inset. The mockup renders the 8px-at-2px proposal in both themes, the three single states on active and inactive tabs, a two-dot and a three-dot stack, and the phone chip and a row; the user adjusts from it. It goes to the shared drops before the code PR.
