// THE SHARED CARD BUILDER, EXECUTED (round two of the box content PR, the verifier's low a): the feed card and the Needs you row draw the
// card's section toggles, its swirl caption and its name-row state badges through card-sections.ts, so the conditions, the precedence, the
// order and the wording live in one place and are pinned here by running that place. The module builds DOM, so a small plain-object stand-in
// (the pr-links test's idiom) provides createElement and createTextNode before the module loads; nothing here needs layout. The wiring of
// both pages into the module is pinned at the source below, the way the other webview tests pin the renderers.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { buildSectionElements, stateBadges, cardSpin, BADGE_WORDS } from "./card-sections";

// ── a DOM stand-in: elements and text nodes with the members the builder touches ────────────────────────────
class T { nodeType = 3; parentNode: E | null = null; constructor(public textContent: string) {} }
class E {
  nodeType = 1; parentNode: E | null = null; childNodes: Array<E | T> = [];
  className = ""; title = ""; type = ""; onclick: ((ev: unknown) => void) | null = null;
  style: Record<string, string> = {}; dataset: Record<string, string | undefined> = {};
  attrs = new Map<string, string>();
  constructor(public tagName: string) {}
  get classList() {
    const self = this;
    const set = () => new Set(self.className.split(/\s+/).filter(Boolean));
    const write = (s: Set<string>) => { self.className = Array.from(s).join(" "); };
    return {
      add: (...cs: string[]) => { const s = set(); cs.forEach((c) => s.add(c)); write(s); },
      remove: (...cs: string[]) => { const s = set(); cs.forEach((c) => s.delete(c)); write(s); },
      toggle: (c: string, on?: boolean) => { const s = set(); const want = on === undefined ? !s.has(c) : on; if (want) s.add(c); else s.delete(c); write(s); return want; },
      contains: (c: string) => set().has(c),
    };
  }
  get textContent(): string { return this.childNodes.map((n) => n.textContent).join(""); }
  set textContent(v: string | null) { this.childNodes = v ? [new T(v)] : []; }
  get children(): E[] { return this.childNodes.filter((n): n is E => n instanceof E); }
  private adopt(n: E | T | string): E | T { const node = typeof n === "string" ? new T(n) : n; node.parentNode = this; return node; }
  append(...ns: Array<E | T | string>) { for (const n of ns) this.childNodes.push(this.adopt(n)); }
  appendChild(n: E | T) { this.childNodes.push(this.adopt(n)); return n; }
  prepend(...ns: Array<E | T | string>) { this.childNodes.unshift(...ns.map((n) => this.adopt(n))); }
  replaceChildren(...ns: Array<E | T | string>) { this.childNodes = ns.map((n) => this.adopt(n)); }
  setAttribute(k: string, v: string) { this.attrs.set(k, v); }
  getAttribute(k: string) { return this.attrs.has(k) ? this.attrs.get(k)! : null; }
  removeAttribute(k: string) { this.attrs.delete(k); }
  querySelectorAll() { return [] as E[]; }
  querySelector() { return null; }
  addEventListener() { /* the styled tip wires hover listeners on the interrupting chip */ }
  removeEventListener() {}
}
// the module touches document only when a builder runs (its load creates the section channel, which needs none), so a static import is
// fine with the stand-in installed at module level, before any test runs (the test bundle is CommonJS: no top-level await)
(globalThis as any).document = { createElement: (tag: string) => new E(tag.toUpperCase()), createTextNode: (t: string) => new T(t),
                                  body: new E("BODY"), documentElement: new E("HTML"), addEventListener() {}, removeEventListener() {} };   // the styled tip (tip.ts) wires document listeners on first use

const env = {
  durNodes: (since: number | null | undefined) => (since ? [" · ", Object.assign(new E("SPAN"), { className: "dur" }) as unknown as HTMLElement] : []),
  openSession: (_sid: string) => { opened.push(_sid); },
  clockHM: (t: number) => "hm" + t,
  openWarns: (it: unknown, title: string) => { warnsOpened.push(title); },
  workDot: (peer: HTMLElement, name: string) => { (peer as unknown as E).dataset.dot = name; },
};
let opened: string[] = [], warnsOpened: string[] = [];
const badges = (it: Parameters<typeof stateBadges>[0], caption: string | null = null) => stateBadges(it, env as any, caption) as unknown as E[];
const classes = (els: E[]) => els.map((e) => e.className);

test("buildSectionElements: the card's toggles in the card's order, the bodies they drive, the checklist and the swirl box", () => {
  const se = buildSectionElements() as unknown as Record<string, any>;
  assert.deepEqual((se.toggles as E[]).map((b) => [b.tagName, b.className, b.textContent]),
    [["BUTTON", "fask-secbtn", "Background"], ["BUTTON", "fask-secbtn", "Summary"], ["BUTTON", "fask-secbtn fask-stallbtn", "Stalled"], ["BUTTON", "fask-secbtn", "Sub-goals"], ["BUTTON", "fask-secbtn fask-taskbtn", ""]],
    "Background · Summary · Stalled · Sub-goals · Awaiting task, one element each, built for both pages");
  assert.deepEqual([se.subBtn.style.display, se.stallBtn.style.display, se.taskBtn.style.display], ["none", "none", "none"], "the three conditional toggles start hidden; applySections shows them");
  assert.deepEqual((se.secs as E).children.map((c) => c.className), ["fask-bg-body", "fask-distill", "fask-stall-body"], "the bodies only, in the toggles' order; the toggles ride the caller's row");
  assert.equal((se.checklist as E).className, "fask-checklist");
  assert.deepEqual((se.awaitSpin as E).children.map((c) => [c.className, c.getAttribute("aria-hidden")]), [["fask-awaiting-swirl", "true"], ["fask-awaiting-why", null]], "the swirl glyph (decoration) and its why");
  assert.equal((se.awaitSpin as E).style.display, "none", "no caption yet");
  assert.deepEqual((se.taskBtn as E).children.map((c) => c.className), ["fask-awaiting-swirl", "fask-taskbtn-lbl"], "the Awaiting task pill: the mini swirl and its label");
});

test("stateBadges: nothing for a plain item; each state its badge with the card's words", () => {
  assert.deepEqual(badges({}), []);
  assert.deepEqual(badges({ recheck: true }).map((b) => [b.className, b.textContent, b.title]), [["fask-followedup", BADGE_WORDS.rejudging.text, BADGE_WORDS.rejudging.title]]);
  assert.equal(BADGE_WORDS.rejudging.text, "↩ re-judging");
  assert.deepEqual(badges({ doneConfirming: true }).map((b) => [b.className, b.textContent]), [["fask-doneconfirming", "done, confirming"]]);
  assert.deepEqual(badges({ nudgeFailed: true }).map((b) => [b.className, b.textContent, b.title]), [["fask-nudgefailed", "follow-up failed", BADGE_WORDS.nudgeFailed.title]]);
  assert.deepEqual(badges({ interrupting: true }).map((b) => [b.className, b.textContent]), [["fask-interrupting", "interrupting…"]]);
  assert.deepEqual(badges({ interrupted: true }).map((b) => [b.className, b.textContent, b.title]), [["fask-interrupted", "interrupted", BADGE_WORDS.interrupted.title]]);
});

test("stateBadges: the card's precedence: the swirl's Analyzing caption replaces the re-judging chip; a plain reply (rejudging) never wears it; follow-up failed outranks both interrupt words; the interrupt words never show together", () => {
  assert.deepEqual(badges({ recheck: true }, "Analyzing…"), [], "the swirl already says it (the user 2026-06-29: don't show both)");
  assert.deepEqual(badges({ rejudging: true }), [], "rejudging: the swirl is the ONLY cue (the medium of round two: the row wore the chip where the card withheld it)");
  assert.deepEqual(classes(badges({ nudgeFailed: true, interrupting: true, interrupted: true })), ["fask-nudgefailed"]);
  assert.deepEqual(classes(badges({ interrupting: true, interrupted: true })), ["fask-interrupting"], "in flight outranks settled");
  assert.deepEqual(classes(badges({ interrupted: true, nudgeFailed: false })), ["fask-interrupted"]);
});

test("stateBadges: the warning chip, a focusable button, its label by the warns' family, its hover the attempt history or the last message, its click the page's detail", () => {
  warnsOpened = [];
  const one = badges({ text: "wire the fixtures", warns: [{ kind: "brief-failed", t: 1, msg: "the brief could not be written", detail: "" }] });
  assert.deepEqual(one.map((b) => [b.tagName, b.className, b.textContent]), [["BUTTON", "fask-warnchip", "distill failed"]], "every warn the distiller's own → 'distill failed'");
  assert.equal(one[0].title, "the brief could not be written\n— click for what happened and why");
  one[0].onclick!({ stopPropagation() {} }); assert.deepEqual(warnsOpened, ["wire the fixtures"], "the click hands the page the item's title");
  const two = badges({ warns: [{ kind: "brief-failed", t: 1, msg: "a", detail: "" }, { kind: "cite-miss", t: 2, msg: "the cite missed", detail: "" }] });
  assert.equal(two[0].textContent, "warning ×2", "a mixed family counts as warnings");
  const logged = badges({ warns: [{ kind: "summary-failed", t: 1, msg: "m", detail: "" }], failLog: [{ t: 5, line: "", model: "opus", note: "529" }] });
  assert.equal(logged[0].title, "hm5 tried opus — 529\n— click for what happened and why", "the attempt history when one exists (the user 2026-08-18)");
});

test("stateBadges: the peer wait, the origin, the handoff and the tracked delegation, with their clicks", () => {
  opened = [];
  const w = badges({ waitingOn: { name: "api", kind: "delegate", since: 10 } });
  assert.deepEqual(w.map((b) => [b.className, b.textContent]), [["fask-waiton", "Handed off to api · "]], "a delegate wait; the live duration rides its own element");
  assert.deepEqual(classes(badges({ waitingOn: { name: "api", inCycle: true } })), ["fask-waiton fask-waiton-cycle"]);
  assert.equal(badges({ waitingOn: { name: "api", inCycle: true } })[0].textContent, "Deadlock api");
  assert.equal(badges({ waitingOn: { name: "api" } })[0].textContent, "Awaiting api");
  const o = badges({ origin: { peer: "api", peerSid: "s-api", live: false } });
  assert.deepEqual(o.map((b) => [b.tagName, b.className, b.textContent]), [["A", "fask-origin fask-origin-absorbed", "↪ from api"]], "absorbed: the same badge, dimmed, never removed");
  o[0].onclick!({ stopPropagation() {} }); assert.deepEqual(opened, ["s-api"], "the click opens the sender");
  assert.equal(badges({ origin: { peer: "api", peerSid: "s-api", live: true } })[0].className, "fask-origin");
  assert.equal(badges({ handoffTo: { peer: "tests", peerSid: "s-t" } })[0].textContent, "↪ delegated to tests");
  const d = badges({ delegTracked: [{ sid: "s1", name: "web" }, { sid: "s2", name: "api" }] });
  assert.equal(d[0].textContent, "↪ delegated to web, api");
  assert.deepEqual(d[0].children.filter((c) => c.className === "fask-origin-peer").map((c) => c.dataset.dot), ["web", "api"], "the page's live dot before each recipient (the feed's workDot)");
});

test("stateBadges: the card's order when every badge shows", () => {
  const all = badges({ recheck: true, doneConfirming: true, nudgeFailed: true, interrupting: true, interrupted: true,
                       warns: [{ kind: "x", t: 1, msg: "m", detail: "" }], waitingOn: { name: "api" },
                       origin: { peer: "api", peerSid: "s" }, handoffTo: { peer: "tests", peerSid: "t" }, delegTracked: [{ sid: "u", name: "docs" }] });
  assert.deepEqual(classes(all), ["fask-origin", "fask-followedup", "fask-doneconfirming", "fask-nudgefailed", "fask-warnchip", "fask-waiton", "fask-origin", "fask-origin"],
    "origin, re-judging, done confirming, follow-up failed (the interrupt words yield to it), the warning chip, the peer wait, the handoff, the tracked delegation");
});

test("cardSpin: a targeted follow-up (recheck) and a plain reply (rejudging) both say Analyzing…, so neither wears the chip beside the swirl", () => {
  const clock = { nowSec: () => 1000 };
  assert.equal(cardSpin({ recheck: true, blockSummary: "the brief" }, false, true, clock).caption, "Analyzing…");
  assert.equal(cardSpin({ rejudging: true, blockSummary: "the brief" }, false, true, clock).caption, "Analyzing…");
  assert.equal(cardSpin({ blockSummary: "the brief", blocked: {} }, false, true, clock).caption, null, "a blocked card with its brief: no spin");
  assert.deepEqual(badges({ recheck: true }, cardSpin({ recheck: true, blockSummary: "b" }, false, true, clock).caption), [], "the rule, end to end");
});

// ── the wiring: both pages draw through the module ─────────────────────────────────────────────────────────
const W = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const FEED = W("feed.ts"), RENDER = W("render.ts"), MOD = W("card-sections.ts");
test("the feed card and the Needs you row build the toggles, draw the swirl, the landings and the badges through the shared module, and never keep a copy", () => {
  assert.match(FEED, /const se = buildSectionElements\(\);\s*\n\s*const \{ bgBtn, bgBody, takeBtn, distill, subBtn, stallBtn, stallBody, taskBtn, taskLbl, secs, checklist, awaitSpin, awaitWhy \} = se;/, "the card's elements");
  assert.match(FEED, /row3\.append\(\.\.\.se\.toggles, actions\);/, "in the builder's order");
  assert.match(RENDER, /const se = buildSectionElements\(\);/, "the row's elements"); assert.match(RENDER, /secsRow\.append\(\.\.\.se\.toggles\);/);
  assert.match(FEED, /const spin = cardSpin\(it, dCompleted, dBlocked, sectionEnv\);[^\n]*\n\s*applySpin\(a, it, spin, sectionEnv\);\s*\n\s*const spinCaption = spin\.caption;/, "the card's swirl");
  assert.match(RENDER, /const spin = cardSpin\(it, dCompleted, dBlocked, noticeSectionEnv\); applySpin\(rowAny, it, spin, noticeSectionEnv\);/, "the row's swirl");
  assert.match(FEED, /a\._badges\.replaceChildren\(\.\.\.stateBadges\(it, sectionEnv, spinCaption\)\);/, "the card's badges, with the caption");
  assert.match(RENDER, /badgesEl\.replaceChildren\(\.\.\.stateBadges\(it, noticeSectionEnv, spin\.caption\)\);/, "the row's badges, with the caption");
  assert.match(FEED, /applyDistillLanding\(a, it, distillShown, dCompleted, dBlocked, sectionEnv\);/, "the card's line");
  assert.match(RENDER, /applyDistillLanding\(rowAny, it, shown, dCompleted, dBlocked, noticeSectionEnv\);/, "the row's line");
  for (const gone of [/fupBadge/, /nfBadge/, /intingBadge/, /warnChip/, /waitOnBadge/, /dcBadge/, /a\._followedup/, /a\._warnChip/, /a\._waitOn/, /a\._origin\b/, /spinFor\(/, /function relAge\(/])
    assert.doesNotMatch(FEED, gone, "no second copy in the feed: " + gone.source);
  assert.match(FEED, /row2\.append\(idwrap, retryBadge, apiBadge, apiRetry, apiLogin, capLine, capBtn, jauthBadge, blkBadge, badges\);/, "the name row's one badge slot");
  assert.match(MOD, /export function stateBadges\(it: BadgeItem, env: Pick<SectionEnv, "durNodes" \| "openSession" \| "clockHM" \| "openWarns" \| "workDot">, spinCaption: string \| null = null\): HTMLElement\[\] \{/);
});

test("every write to the section choice goes through the module's setters, which cross the shell's two documents; the feed owns the state and the chat page follows", () => {
  assert.doesNotMatch(FEED, /secChoice\.(set|clear|delete)\(/, "the feed's three writers (hydrate, prune, the Collapsed clear) go through replaceSectionChoices (the medium of round two: they never crossed the channel)");
  assert.match(FEED, /replaceSectionChoices\(Object\.entries\(st\.sec\) as \[string, SecChoice\]\[\], \{ quiet: true \}\);/, "hydration");
  assert.match(FEED, /replaceSectionChoices\(Object\.entries\(kept\.sec\) as \[string, SecChoice\]\[\], \{ quiet: true \}\);/, "the prune to the live set (quiet: the render applies every card next; a map that did not move is no change at all)");
  assert.match(MOD, /let same = next\.size === secChoice\.size;\s*\n\s*if \(same\) for \(const \[k, v\] of next\) if \(secChoice\.get\(k\) !== v\) \{ same = false; break; \}\s*\n\s*if \(same\) return;/, "the whole-map setter is a no-op when nothing moved: the prune runs on every render");
  assert.match(FEED, /lastCollapsedPref = p\.collapsed; replaceSectionChoices\(\[\], \{ quiet: true \}\); \}/, "the Collapsed flip");
  assert.match(FEED, /configureSectionSync\(\{ role: "owner", onChange: \(\) => persistViewState\(\) \}\);/, "the owner persists every change, a follower's pick included");
  assert.match(RENDER, /configureSectionSync\(\{ role: "follower" \}\);/, "the chat page says hello and takes the map");
  assert.match(MOD, /setSectionChoice\(id, choice === want \? "none" : want\);/, "a press writes through the setter");
  assert.match(MOD, /if \(d\.kind === "hello"\) \{ if \(syncRole === "owner"\) postSync\(\{ kind: "map", entries: Array\.from\(secChoice\.entries\(\)\) \}\); return; \}/, "the owner answers a hello with its map");
  assert.match(MOD, /if \(syncRole === "owner"\) postSync\(\{ kind: "map", entries: Array\.from\(secChoice\.entries\(\)\) \}\);\s*\n\s*else postSync\(\{ kind: "hello" \}\);/, "and posts it when it loads, for a follower already up");
  assert.match(MOD, /const sectionChannel: BroadcastChannel \| null = typeof window !== "undefined" && typeof \(window as \{ BroadcastChannel\?: unknown \}\)\.BroadcastChannel === "function" \? new window\.BroadcastChannel\("romp-card-sections"\) : null;/, "the WINDOW's channel only: Node's own kept the test process alive once a message was posted at load");
});

test("the row's landings are the chat page's own: the line and a paragraph scroll to the turn, a sub-goal row's text jumps to its work anchor, no anchor says so in the landing toast", () => {
  assert.match(RENDER, /landing: \(_it, target\) => \{ scrollToAnchor\(target\.anchorUuid\); \},/);
  assert.match(RENDER, /const u = node\.anchorUuid; txt\.classList\.add\("nav"\); txt\.title = "jump to where this was worked on";\s*\n\s*txt\.onclick = \(ev: Event\) => \{ ev\.stopPropagation\(\); scrollToAnchor\(u\); \};/);
  assert.match(RENDER, /landToast\("couldn't locate this in the transcript — no anchor was recorded for this card"\);/);
  assert.match(RENDER, /refreshAges\(document\.querySelectorAll<HTMLElement>\("#notices \[data-age-t\]"\), noticeNowSec\(\), relAge, \(\) => ""\);/, "the row's stamped ages repainted by the page's own pass");
  assert.match(MOD, /else age\.textContent = env\.relAge\(0\);/, "a part with no event time: the static '<1m ago' (the medium of round two: the row printed an epoch-sized age)");
});
