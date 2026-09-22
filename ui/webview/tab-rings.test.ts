// THE RINGS AS WIDGETS (2026-09-14; the ask ring itself from the review of 2026-09-13): a session with a card that
// needs you should grab attention in the tab strip without a click, the way a live prompt rings the tab red, and
// it should do so whether the session went idle after asking or is still working in the background. The red ring is
// the LIVE state's (a permission or picker prompt, or an API stop only you can clear); the magenta ring is the FEED's
// verdict: a card of the session's under needs-you; the amber ring is an API retry on its own. The kernel puts the
// feed's verdict on the session STATUS (build_session's needsYou, the same set the ledger's needsInput and the
// section-at-a-glance rows read); the three rings are WIDGETS of the tab-widget registry (tab-widgets.ts, slot "ring",
// a switch each in the settings), composed onto every tab — a loaded one and a skeleton alike — one class at a time,
// red over magenta over amber (tab-state.ts RING_TEST is the pure twin, executed in tab-state.test.ts and pinned equal to
// the composition in tab-widgets.test.ts); render.ts reads the magenta's input in the strip's signature so a card
// entering or leaving the column always repaints. No jsdom harness executes render.ts, so the wiring and the sheets are
// pinned at the source (the tab-strip-skip idiom); the paint itself runs in tab-strip-skip-exec.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const GEAR_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.css"), "utf8");
const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
// the tab strip's own detail moved to the reference (CLAUDE.md "The documentation front pages")
const REF = fs.readFileSync(path.resolve(process.cwd(), "..", "docs", "reference.md"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const OUTLINE_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet-pane.css"), "utf8");
const RINGS = ["ring-needs-you", "ring-waiting-on-you", "ring-retrying"];

test("the tab wears its ring through the registry's composition, right after the state class, in the one chip helper both tab kinds share", () => {
  const chip = RENDER.slice(RENDER.indexOf("function applyTabStatus("), RENDER.indexOf("function wireTabDrag("));
  assert.match(chip, /const stateCls = tabStateClass\(s\.status\);\s*\n\s*if \(stateCls\) tab\.classList\.add\(stateCls\);/, "the state class first, untouched");
  assert.match(chip, /if \(stateCls\) tab\.classList\.add\(stateCls\);\s*\n(?:\s*\/\/[^\n]*\n)*\s*composeTabRing\(tab, s\.id \|\| "", s\.status, settings\.tabWidgets\);/, "then the ring: the registry's composition over the same status and the widget switches");
  assert.equal(RENDER.split("composeTabRing(").length - 1, 1, "one paint site: applyTabStatus (the skeleton tab and the loaded tab both call it)");
  for (const c of [...RINGS, "tab-ask"]) assert.equal(RENDER.split('"' + c + '"').length - 1, 0, "no hand-rolled ring class in render.ts (" + c + "): the classes live in the registry");
  assert.doesNotMatch(RENDER, /tabAskClass/, "the branch's one-off ask class is gone: the magenta ring is a widget like the others");
  assert.match(RENDER, /^import \{ tabStateClass, sectionPip, sectionPipMembers, sectionPipTitle \} from "\.\/tab-state";/m);
  assert.match(RENDER, /^import \{ composeTabWidgets, composeTabRing, applyTabBadgeMode, needsYouPhrase, ringSwitch, tabHotkey, miniChord \} from "\.\/tab-widgets";/m);   // miniChord joined the import with the per-tab hot keys (merged 2026-09-14)
  // the folded header's pip and its tooltip read the same switches, so a fold never shows a colour no unfolded tab would
  const head = RENDER.slice(RENDER.indexOf("function makeGroupHead("), RENDER.indexOf("function applyTabStatus("));
  assert.match(head, /const kind = sectionPip\(hidden\.map\(\(id\) => sessions\.get\(id\)\?\.status\), ringSwitch\(settings\.tabWidgets\)\);/);
  assert.match(head, /sectionPipMembers\(kind, hidden\.map\(\(id\) => sessions\.get\(id\)\), ringSwitch\(settings\.tabWidgets\)\)/);
});

test("the strip's signature reads the magenta ring's input for a loaded tab AND a skeleton, so a card entering or leaving needs-you repaints (the switches ride settings.tabWidgets, already in it)", () => {
  const fn = RENDER.slice(RENDER.indexOf("function renderTabs() {"), RENDER.indexOf("function stripAftermath("));
  const sig = fn.slice(fn.indexOf("const stripSig = JSON.stringify(["), fn.indexOf("const mslotEl = "));
  assert.match(sig, /st\.state, tabStateClass\(st\), st\.needsYou === true, settings\.tabStateBadge \? st\.needsYouCount : null, !!st\.faded,/, "the loaded tab's row (needsYou and, in badge mode only, its count: the badge's number keys the sig only when it is drawn)");
  assert.match(sig, /kst\?\.state, kst && tabStateClass\(kst\), kst\?\.needsYou === true, kst\?\.needsYou === true \? kst\?\.needsYouCount : null, !!kst\?\.faded,/, "the skeleton's row: the count keys the sig whenever the status needs you, both modes, since the cold title carries it (PR 2033 review)");
  assert.ok(sig.includes("settings.tabWidgets"), "a switch flipped in the settings repaints the strip");
});

test("the status carries needsYou: the kernel's build_session puts the feed's per-session verdict on the STATUS, beside the on-you API flags", () => {
  // on the status, not only the ledger: a skeleton tab gets status frames alone, and the tab rule reads one object
  assert.match(KERNEL, /"apiRefusal": bool\(aerr and aerr\.get\("refusal"\)\),\n(?:\s*#[^\n]*\n)+\s*"needsYou": needs_you,/,
    "needsYou rides the live status dict");
  assert.match(KERNEL, /"needsInput": needs_you\}/, "…and the ledger still carries the verdict for the section rows");
  // ONE read per build for both (the review of 2026-09-13): two reads could straddle a concurrent pusher's swap of the
  // set, and a row would say "needs you" beside a tab with no ring in the same frame
  assert.match(KERNEL, /\n    needs_you = _feed_needs_input_of\(sid\)\n/, "the verdict is read once into a local…");
  assert.equal(KERNEL.split("needs_you = _feed_needs_input_of(sid)").length - 1, 1, "…exactly once");
  // …and the feed build that MOVES the set wakes the pusher, so the ring trails the card by one build, not a backstop tick
  assert.match(KERNEL, /if _needs_now != _feed_needs_input\[0\]:\n(?:\s*#[^\n]*\n)+\s*_pusher_wake\.set\(\)\n\s*_feed_needs_input\[0\] = _needs_now/, "a changed set wakes; an unchanged one does not");
  assert.match(RENDER, /interface Status \{[^\n]*apiRefusal\?: boolean; needsYou\?: boolean \| null; needsYouCount\?: number \| null; retrySuppressed\?: boolean;/, "the client's Status names needsYou (tri-state) and its count");
});

test("THE SHEET: the dashed outlines key on the RING classes the strip composes (two-class selectors, after the peek ring), never on the state class; no :not chain, no raw hex; the blocked fill rides the red ring", () => {
  assert.match(CSS, /\n\.tab\.ring-needs-you, \.tab\.ring-retrying \{ outline: 2px dashed var\(--state\); outline-offset: -2px; \}/, "the red and the amber read the state's --state");
  assert.match(CSS, /\n\.tab\.ring-waiting-on-you \{ outline: 2px dashed var\(--st-needs-bg\); outline-offset: -2px; \}/, "the Needs you ring reads its own token (plans/needs-you.md)");
  // the state classes still set --state (the colour the red and amber rings read), and nothing else paints an outline off them
  assert.match(CSS, /\.tab\.tab-awaiting \{ --state: var\(--st-awaiting-bg\); \}/);
  assert.match(CSS, /\.tab\.tab-retrying \{ --state: var\(--st-retrying-bg\); \}/);
  assert.match(CSS, /\.tab\.tab-blocked \{ --state: var\(--st-blocked-bg\); \}/);
  for (const line of CSS.split("\n")) if (/^\.tab\b[^{]*\{[^}]*outline: 2px dashed/.test(line)) assert.match(line, /^\.tab\.ring-/, "every 2px dashed outline rule on a tab keys on a ring class: " + line);
  assert.doesNotMatch(CSS, /\.tab-awaiting[^\n{]*\{[^}]*outline:/, "no outline off the awaiting state");
  assert.doesNotMatch(CSS, /\.tab-retrying[^\n{]*\{[^}]*outline:/, "no outline off the retrying state");
  assert.equal(CSS.split(".tab.tab-ask").length - 1, 0, "the branch's :not-chained ask rule is gone");
  assert.equal(GEAR_CSS.split("tab-ask").length - 1, 0);
  // the CASCADE: the peek ring (structure, not status) is declared before the ring rules so a real ring wins at equal specificity
  const peekAt = CSS.indexOf(".tab.tab-peek { outline:"), ringAt = CSS.indexOf(".tab.ring-needs-you, .tab.ring-retrying { outline:"), magentaAt = CSS.indexOf(".tab.ring-waiting-on-you { outline:");
  assert.ok(peekAt > 0 && peekAt < ringAt && ringAt < magentaAt, "peek, then the rings");
  // the ring rules are two class-level parts each: one class at a time on the tab, so no rule needs to out-specify another
  const classParts = (s: string) => (s.match(/\.[a-z-]+/g) || []).length;
  for (const sel of [".tab.ring-needs-you", ".tab.ring-retrying", ".tab.ring-waiting-on-you"]) assert.equal(classParts(sel), 2);
  // never a raw hex on a ring rule: the token carries the colour in both themes (theme-parity.test.ts pins the pairs)
  const ringRules = CSS.split("\n").filter((l) => /^\.tab\.ring-/.test(l));
  assert.equal(ringRules.length, 2);
  assert.doesNotMatch(ringRules.join("\n"), /#[0-9a-fA-F]{3,8}\b|rgba?\(/, "the rings read tokens");
  assert.doesNotMatch(ringRules.join("\n"), /padding|margin|border(?!-radius)|width|height|display/, "no box property: an outline is painted outside layout, so a ring never moves the strip (T262g)");
  // the blocked tab's red FILL rides the red ring: switched off, a stopped session is a plain tab
  assert.match(CSS, /\.tab\.tab-blocked\.ring-needs-you \{ background: rgba\(229, 72, 77, 0\.30\); \}/);
  assert.match(CSS, /\.tab\.tab-blocked\.ring-needs-you:hover \{ background: rgba\(229, 72, 77, 0\.38\); \}/);
  assert.match(CSS, /\.tab\.tab-blocked\.ring-needs-you\.active \{\s*\n\s*background: linear-gradient/);
  assert.doesNotMatch(CSS, /\.tab\.tab-blocked \{[^}]*background/, "no fill off the state alone");
  // the tokens, in both themes; the folded header's pip wears the same magenta (tab-groups.test.ts pins the pip's other colours)
  assert.match(CSS, /--st-needs-bg: #d946ef; --st-needs-fg: #2a0a2a;/, "the dark Needs you magenta, apart from both reds, the amber and the gold (theme-parity pins the pairs)");
  assert.match(CSS, /\.tab-group-pip\.ask \{ background: var\(--st-needs-bg\); \}/);
});

test("THE GEAR'S SHEET: the ring rows' demos wear the same classes through gear.css fallbacks (its hosts load feed.css and gear.css, not styles.css), and feed.css carries the Needs you tokens in both themes", () => {
  assert.match(GEAR_CSS, /#rsettings \.rs-widget-demo \.tab\.ring-needs-you, #rsettings \.rs-preview \.tab\.ring-needs-you \{ outline: 2px dashed var\(--st-awaiting-bg, #c0392b\); outline-offset: -2px; \}/);
  assert.match(GEAR_CSS, /#rsettings \.rs-widget-demo \.tab\.ring-waiting-on-you, #rsettings \.rs-preview \.tab\.ring-waiting-on-you \{ outline: 2px dashed var\(--st-needs-bg, #d946ef\); outline-offset: -2px; \}/);
  assert.match(GEAR_CSS, /#rsettings \.rs-widget-demo \.tab\.ring-retrying, #rsettings \.rs-preview \.tab\.ring-retrying \{ outline: 2px dashed var\(--st-retrying-bg, #e67e22\); outline-offset: -2px; \}/);
  assert.match(GEAR_CSS, /#rsettings \.rs-widget-demo \.tab \{[^}]*border-radius: 6px;/, "the demo tab has the strip's radius, so the ring follows it");
  const block = (css: string, opener: string) => css.slice(css.indexOf(opener), css.indexOf("\n}", css.indexOf(opener)));
  assert.match(block(FEED_CSS, ":root {"), /--st-needs-bg: #d946ef; --st-needs-fg: #2a0a2a;/, "feed.css :root mirrors the dark pair");
  assert.match(block(FEED_CSS, "body.theme-light {"), /--st-needs-bg: #[0-9a-f]{6}; --st-needs-fg: #ffffff;/, "…and the light block re-inks it (theme-parity pins the value's contrast)");
  const styLight = block(CSS, "body.theme-light {").match(/--st-needs-bg: (#[0-9a-f]{6});/)![1], feedLight = block(FEED_CSS, "body.theme-light {").match(/--st-needs-bg: (#[0-9a-f]{6});/)![1];
  assert.equal(feedLight, styLight, "the two sheets agree on the light value");
});

test("the reference says what the Needs you ring means, when it shows (idle, waiting or still working), what outranks it, and that the notification is the same event", () => {
  const prose = (t: string) => new RegExp(t.replace(/[.()*]/g, "\\$&").split(" ").join("\\s+"));   // the reference wraps its lines; the bold markers are literal
  assert.match(REF, prose("A tab wears a dashed red ring, **Blocked**, while its session is stopped: on a permission or picker prompt, or on an API error only you can clear."));
  assert.match(REF, prose("the tab wears a dashed magenta ring instead, **Needs you**, whether the session is idle, waiting on background work or still working, so the sessions that need you stand out in the strip without a click"));
  assert.match(REF, prose("A red ring outranks the magenta one; the amber ring of a session retrying an API error on its own gives way to it."));
  assert.match(REF, prose("With notifications on, the card entering Needs you is also what notifies you"));
  assert.match(REF, prose("the session picker marks the same sessions with a magenta bar at the row's left edge"), "the phone's picker carries the mark too");
  // the rings as widgets (2026-09-14): the three rows, their switches, the one-at-a-time rule and what a switched-off ring leaves
  assert.match(REF, prose("each with its own switch, listed in that order because a tab wears one ring at a time and the first that applies wins: red over magenta over amber."));
  assert.match(REF, /\*\*Tab widgets\*\*\s+\(\*\*Blocked\*\*, \*\*Needs\s+you\*\*, \*\*Retrying\*\*\)/, "the rows by their labels, in precedence order");
  assert.match(REF, prose("A ring switched off leaves the tab with its dot; the small dot on a folded group's header and the phone's picker follow the same switches."));
  assert.match(REF, prose("the three rings around a tab are listed below those rows without a place in the order, since a ring has no side of the name"), "the strip paragraph's Tab widgets sentence");
  assert.match(REF, prose("One colour, the Needs you colour, marks the category everywhere"), "the one-colour sentence");
});

test("the phone's session picker scrapes the Needs you ring's class off the desktop strip and paints it on the row and the current-session chip, so it follows the ring's switch for free", () => {
  assert.match(KERNEL, /ask:t\.classList\.contains\('ring-waiting-on-you'\),/, "scraped beside working/awaitbg (the picker reads the real strip, not a copy; a switched-off ring puts no class on the tab)");
  assert.equal(KERNEL.split("'tab-ask'").length - 1, 0, "the branch's class is gone from the picker");
  assert.match(KERNEL, /row\.classList\.toggle\('ask',!!s\.ask\);/, "the row");
  assert.match(KERNEL, /cur\.classList\.toggle\('ask',!!\(act&&act\.ask\)\);/, "the current chip");
  assert.match(KERNEL, /"\.mrow\.ask\{border-left:3px solid var\(--st-needs-bg,#d946ef\);padding-left:9px\}"/, "a magenta bar at the row's left edge, in the one Needs you token");
  assert.match(KERNEL, /"#mcur\.ask\{border-color:var\(--st-needs-bg,#d946ef\);border-style:dashed\}"/, "the chip's border takes the dashed magenta ring");
  assert.ok(KERNEL.indexOf('"#mcur.colored{') < KERNEL.indexOf('"#mcur.ask{'), "after #mcur.colored, so the ring wins the border over the identity colour at equal specificity");
});

test("the outline pane's Needs you mark wears the category's colour: the tree row's ⏸ and the hover card's sub-list mark, never the error red (PR 1935 round two)", () => {
  assert.match(CSS, /\.ledger-tnode\.blocked \.ledger-tmark \{ border-color: var\(--st-needs-bg\); color: var\(--st-needs-bg\); \}/);
  assert.doesNotMatch(CSS, /\.ledger-tnode\.blocked \.ledger-tmark \{[^}]*--err/, "the error red is the hard stop's");
  assert.match(OUTLINE_CSS, /\.fl-hover-sub\.blocked \.m\{color:var\(--st-needs-bg,#d946ef\)\}/);
});
