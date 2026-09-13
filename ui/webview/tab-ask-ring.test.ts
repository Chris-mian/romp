// THE ASK RING (the user 2026-09-13): a session with something waiting on you should grab attention in the tab
// strip without a click — the way a live prompt rings the tab red — and it should do so whether the session went
// idle after asking or is still working in the background. The red ring is the LIVE state's (a permission or
// picker prompt); the yellow ring is the FEED's verdict: a card of the session's under needs-you. The kernel puts
// that verdict on the session STATUS (build_session's needsYou, the same set the ledger's needsInput and the
// section-at-a-glance rows read), tab-state.ts turns it into a second class beside the state class (tabAskClass,
// executed in tab-state.test.ts), and render.ts wears it on every tab — a loaded one and a skeleton alike — and
// reads it in the strip's signature so a card entering or leaving the column always repaints. No jsdom harness
// executes render.ts, so the wiring and the cascade are pinned at the source (the tab-strip-skip idiom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const GUIDE = fs.readFileSync(path.resolve(process.cwd(), "..", "docs", "guide.md"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("the tab wears the ask class BESIDE the state class, from tab-state.ts's rule, in the one chip helper both tab kinds share", () => {
  const chip = RENDER.slice(RENDER.indexOf("function applyTabStatus("), RENDER.indexOf("function wireTabDrag("));
  assert.match(chip, /const stateCls = tabStateClass\(s\.status\);\s*\n\s*if \(stateCls\) tab\.classList\.add\(stateCls\);/, "the state class first, untouched");
  assert.match(chip, /const askCls = tabAskClass\(s\.status\);\s*\n\s*if \(askCls\) tab\.classList\.add\(askCls\);/, "then the ask ring, the shared rule's second class");
  assert.ok(chip.indexOf("const stateCls = tabStateClass(s.status);") < chip.indexOf("const askCls = tabAskClass(s.status);"), "state, then ask");
  assert.equal(RENDER.split("tabAskClass(s.status)").length - 1, 1, "one paint site: applyTabStatus (the skeleton tab and the loaded tab both call it)");
  assert.equal(RENDER.split('"tab-ask"').length - 1, 0, "no hand-rolled ask class anywhere in render.ts: the rule lives in tab-state.ts");
  assert.match(RENDER, /^import \{ tabStateClass, tabAskClass, sectionPip, sectionPipMembers, sectionPipTitle \} from "\.\/tab-state";/m);
});

test("the strip's signature reads the ask class for a loaded tab AND a skeleton, so a card entering or leaving needs-you repaints", () => {
  const fn = RENDER.slice(RENDER.indexOf("function renderTabs() {"), RENDER.indexOf("function stripAftermath("));
  const sig = fn.slice(fn.indexOf("const stripSig = JSON.stringify(["), fn.indexOf("const mslotEl = "));
  assert.match(sig, /st\.state, tabStateClass\(st\), tabAskClass\(st\), !!st\.faded,/, "the loaded tab's row");
  assert.match(sig, /kst\?\.state, kst && tabStateClass\(kst\), kst && tabAskClass\(kst\), !!kst\?\.faded,/, "the skeleton's row, from the stored status frame");
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
  assert.match(RENDER, /interface Status \{[^\n]*apiRefusal\?: boolean; needsYou\?: boolean \| null; retrySuppressed\?: boolean;/, "the client's Status names it, tri-state like the ledger's");
});

test("CASCADE: the ask ring's :not chain excludes the two red rings AND out-specifies the state outlines, so it wins `outline` over the amber retry wherever it sits", () => {
  // the state rule is two classes (.tab.tab-retrying); the ask rule is two classes plus two :not(class) — four
  // class-level parts — so it takes the tie on specificity, not on source order (the review of 2026-09-13: an
  // order pin here would fail a behaviour-preserving reorganisation of the sheet). The peek ring's own order pin
  // (peek-tab.test.ts) is untouched: the peek is two classes too and must lose to a real state.
  const stateRule = CSS.match(/\.tab\.tab-awaiting, \.tab\.tab-blocked, \.tab\.tab-retrying \{ outline: 2px dashed var\(--state\); outline-offset: -2px; \}/);
  const askRule = CSS.match(/\n(\.tab\.tab-ask[^{\n]*)\{ outline: 2px dashed var\(--st-ask-bg\); outline-offset: -2px; \}/);
  assert.ok(stateRule && askRule, "both rules present");
  const sel = askRule![1].trim();
  assert.equal(sel, ".tab.tab-ask:not(.tab-awaiting):not(.tab-blocked)");
  assert.ok(/:not\(\.tab-awaiting\)/.test(sel) && /:not\(\.tab-blocked\)/.test(sel), "never over a red ring");
  const classParts = (s: string) => (s.match(/\.[a-z-]+/g) || []).length;   // each .class inside :not() counts toward specificity too
  assert.ok(classParts(sel) > classParts(".tab.tab-retrying"), "out-specifies the amber ring's rule: " + classParts(sel) + " vs " + classParts(".tab.tab-retrying"));
  assert.equal(CSS.split(".tab.tab-ask").length - 1, 1, "one ask rule: no second selector could re-tie the outline");
  // the same dashed geometry as the red ring: one ring vocabulary, the colour carries the meaning
  // the token, in both themes (theme-parity.test.ts pins the contrast pairs); never a raw hex on the rule
  assert.match(CSS, /--st-ask-bg: #f5d33f; --st-ask-fg: #332600;/, "the dark ask yellow — a lemon apart from Working's gold and the retrying amber");
  assert.match(CSS, /--st-ask-bg: #7a6400; --st-ask-fg: #ffffff;/, "the light palette's");
  assert.doesNotMatch(CSS.match(/\.tab\.tab-ask[^\n]*/g)!.join("\n"), /#[0-9a-fA-F]{3,8}\b|rgba?\(/, "the ring reads the token");
  // the folded header's pip wears the same token (tab-groups.test.ts pins the pip's other colours)
  assert.match(CSS, /\.tab-group-pip\.ask \{ background: var\(--st-ask-bg\); \}/);
});

test("the working dot keeps its slot: the ring is an outline, so a tab's width and the strip's row count do not move with an ask (T262g)", () => {
  const rule = CSS.match(/\.tab\.tab-ask:not\(\.tab-awaiting\):not\(\.tab-blocked\) \{([^}]*)\}/)![1];
  assert.doesNotMatch(rule, /padding|margin|border(?!-radius)|width|height|display/, "no box property: an outline is painted outside layout");
});

test("the guide says what the yellow ring means, when it shows (idle, waiting or still working), what outranks it, and that the notification is the same event", () => {
  const prose = (t: string) => new RegExp(t.replace(/[.()]/g, "\\$&").split(" ").join("\\s+"));   // the guide wraps its lines
  assert.match(GUIDE, prose("A tab wears a dashed red ring while its session is stopped on a permission or picker prompt."));
  assert.match(GUIDE, prose("the tab wears a dashed yellow ring instead, whether the session is idle, waiting on background work or still working, so the sessions that need you stand out in the strip without a click"));
  assert.match(GUIDE, prose("A red ring outranks the yellow one; the amber ring of a session retrying an API error on its own gives way to it."));
  assert.match(GUIDE, prose("With notifications on, the card entering Blocked is also what notifies you"));
  assert.match(GUIDE, prose("the session picker marks the same sessions with a yellow bar at the row's left edge"), "the phone's picker carries the mark too");
});

test("the phone's session picker scrapes the ask class off the desktop strip and paints it on the row and the current-session chip", () => {
  assert.match(KERNEL, /ask:t\.classList\.contains\('tab-ask'\),/, "scraped beside working/awaitbg (the picker reads the real strip, not a copy)");
  assert.match(KERNEL, /row\.classList\.toggle\('ask',!!s\.ask\);/, "the row");
  assert.match(KERNEL, /cur\.classList\.toggle\('ask',!!\(act&&act\.ask\)\);/, "the current chip");
  assert.match(KERNEL, /"\.mrow\.ask\{border-left:3px solid var\(--st-ask-bg,#f5d33f\);padding-left:9px\}"/, "a yellow bar at the row's left edge, in the one ask token");
  assert.match(KERNEL, /"#mcur\.ask\{border-color:var\(--st-ask-bg,#f5d33f\);border-style:dashed\}"/, "the chip's border takes the dashed yellow ring");
  assert.ok(KERNEL.indexOf('"#mcur.colored{') < KERNEL.indexOf('"#mcur.ask{'), "after #mcur.colored, so the ring wins the border over the identity colour at equal specificity");
});
