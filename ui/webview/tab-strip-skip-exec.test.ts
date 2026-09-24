// renderTabs EXECUTED: the unchanged-strip skip, its input list, and what still runs on the skip path — driven
// over a minimal fake DOM (no jsdom), the way models-rev.test.ts and thread-selection-scope.test.ts lift a
// render.ts function. tab-strip-skip.test.ts pins the SHAPE at the source; this file drives the BEHAVIOUR, so a
// change that keeps the pinned text but defeats the skip (a signature reset, a nonce in the signature, an input
// dropped from the per-tab array while its helper call stays) fails here. The strip's pure rules run for real:
// the plan (tab-groups.ts planStrip, over a stored tab-groups blob the test hands it) and the state → class rule
// (tab-state.ts); the group header builder is a stub that records what it was handed, since the signature — not
// the header's DOM — is what this file tests (tab-groups.test.ts executes the header).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { planStrip, parseTabGroups, headWords, revealedTabs, phoneStandIns } from "./tab-groups";
import { tabStateClass, tabRingId, RING_ORDER, tabDotClass, tabDotTitle, sectionPip, sectionPipMembers, sectionPipTitle } from "./tab-state";
import { newSkeletonState, renderKind } from "./skeleton-tabs";
import type { TagUnion } from "./session-views";

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

/** Enough of Element for the strip's paint: children, classList, dataset, style, listeners (fired by hand). */
class FakeEl {
  tag: string; className: string; children: FakeEl[] = []; parent: FakeEl | null = null;
  dataset: Record<string, string> = {}; styleProps: Record<string, string> = {}; attrs: Record<string, string> = {};
  listeners: Record<string, Function[]> = {}; textContent = ""; title = ""; tabIndex = -1; draggable = false;
  wipes = 0;   // replaceChildren() calls: the strip's rebuild count when this is #tabs
  style: any; classList: any;
  constructor(tag: string, cls = "") {
    this.tag = tag; this.className = cls;
    const self = this;
    this.style = { display: "", color: "", padding: "", height: "", background: "", animationDelay: "", borderColor: "",
                   setProperty(k: string, v: string) { self.styleProps[k] = v; } };
    this.classList = {
      add(...c: string[]) { for (const x of c) if (!self.has(x)) self.className = (self.className + " " + x).trim(); },
      remove(...c: string[]) { for (const x of c) self.className = self.className.split(/\s+/).filter((y) => y !== x).join(" "); },
      contains(x: string) { return self.has(x); },
      toggle(x: string, on?: boolean) { if (on) this.add(x); else this.remove(x); },
    };
  }
  has(x: string): boolean { return this.className.split(/\s+/).includes(x); }
  appendChild(c: FakeEl): FakeEl { c.parent = this; this.children.push(c); return c; }
  append(...cs: FakeEl[]): void { for (const c of cs) this.appendChild(c); }
  replaceChildren(...cs: FakeEl[]): void { this.wipes++; this.children = []; this.append(...cs); }
  get firstChild(): FakeEl | null { return this.children[0] ?? null; }
  get lastElementChild(): FakeEl | null { return this.children[this.children.length - 1] ?? null; }   // the dot's hover title lands on the slot just appended
  contains(n: unknown): boolean { return n === this || this.children.some((c) => c.contains(n)); }
  setAttribute(k: string, v: string): void { this.attrs[k] = v; }
  addEventListener(t: string, f: Function): void { (this.listeners[t] ??= []).push(f); }
  fire(t: string, ev: any = {}): void { for (const f of this.listeners[t] ?? []) f(ev); }
  remove(): void { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); }
  tabs(): FakeEl[] { return this.children.filter((c) => c.has("tab") && !c.has("tab-add")); }
  heads(): FakeEl[] { return this.children.filter((c) => c.has("tab-group-head")); }
  getElementsByClassName(cls: string): FakeEl[] { const out: FakeEl[] = []; const walk = (n: FakeEl) => { for (const c of n.children) { if (c.has(cls)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel: string): FakeEl | null { const cls = sel.startsWith(".") ? sel.slice(1) : sel; const walk = (n: FakeEl): FakeEl | null => { for (const c of n.children) { if (c.has(cls)) return c; const d = walk(c); if (d) return d; } return null; }; return walk(this); }
}

// item 8: the REAL applyTabBadgeMode, bound into the paint below so its `.tab-dot` re-ink runs for real (a mutant of
// its lookup must red). tab-widgets' `el` uses document.createElement and it may read localStorage at load; the
// eval'd renderTabs uses its OWN prelude document, so these globals only serve the required module.
(globalThis as any).document ??= { createElement: (t: string) => new FakeEl(t) };
(globalThis as any).localStorage ??= { getItem: () => null, setItem: () => {}, removeItem: () => {} };
(globalThis as any).navigator ??= { platform: "Linux x86_64" };
// eslint-disable-next-line @typescript-eslint/no-var-requires
const TW = require("./tab-widgets") as typeof import("./tab-widgets");   // bundled by esbuild (a runtime createRequire would not find it on disk)

/** A recorded call of the group-header stub: what renderTabs handed makeGroupHead for one section. */
type HeadCall = { name: string | null; color: string; ids: string[]; folded: boolean; active: boolean; hidden: string[] };

type Hooks = {
  FakeEl: typeof FakeEl; applyTabBadgeMode: typeof import("./tab-widgets").applyTabBadgeMode; dotAfter: boolean; bar: FakeEl; mslot: FakeEl | null; only: string; hidden: Set<string>; down: Set<string>;
  notes: Record<string, string>; keyHint: string; lens: unknown; unions: TagUnion[]; tips: unknown[];
  aftermaths: [number, number][]; rowPaints: number; tagSyncs: number; placeholders: number;
  groupsRaw: string | null;   // the stored tab-groups blob the plan reads (localStorage's, in the page)
  phone: boolean;             // the phone layout: the plan sections as on the desktop and folds nothing there
  heads: HeadCall[];          // every group header the paint minted, in order
  planStrip: typeof planStrip; parseTabGroups: typeof parseTabGroups; headWords: typeof headWords; revealedTabs: typeof revealedTabs; phoneStandIns: typeof phoneStandIns;
  tabStateClass: typeof tabStateClass; tabRingId: typeof tabRingId; RING_ORDER: typeof RING_ORDER; tabDotClass: typeof tabDotClass; tabDotTitle: typeof tabDotTitle; sectionPip: typeof sectionPip; sectionPipMembers: typeof sectionPipMembers; sectionPipTitle: typeof sectionPipTitle;
  newSkeletonState: typeof newSkeletonState; renderKind: typeof renderKind;   // the skeleton strip (2026-09-07): empty here, so every listed id is a loaded tab or a placeholder
  skeletons: number;          // skeleton tabs minted (none expected: the set stays empty in these worlds)
  timers: Array<() => void>;  // the deferred checks renderTabs schedules (setTimeout 0), fired by the test when it chooses
  activated: string[];        // every setActive the fired checks made (T357 later lows: the hidden tab's restore)
};
type Api = {
  renderTabs: () => void; sig: () => string; folded: () => Set<string>;
  set: (patch: Record<string, unknown>) => void; pending: () => { renderPendingAfterRename: boolean; renderPendingWhilePressed: boolean };
  skeletonTabs: { ids: Set<string>; status: Map<string, any> };
};

// renderTabs + stripAftermath, transpiled (TS → JS) with esbuild at run time — required dynamically so the test
// bundle does not try to bundle esbuild itself (models-rev.test.ts's pattern).
function lift(): (hooks: Hooks) => Api {
  const a = RENDER.indexOf("function renderTabs() {"), b = RENDER.indexOf("// Right-click context menu on a tab.", a);
  assert.ok(a > 0 && b > a, "anchors not found — renderTabs or the context-menu comment moved; re-anchor");
  // the chip, the drag listeners and the context gauge live in helpers above renderTabs, shared with the
  // skeleton tab (2026-09-07): lifted for real, so the paint wears the state class and a dragstart resets the signature
  const h0 = RENDER.indexOf("function applyTabStatus("), h1 = RENDER.indexOf("// SKELETON tab (2026-09-07)", h0);
  const g0 = RENDER.indexOf("function appendTabAfterWidgets(", h1), g1 = RENDER.indexOf("// A loading PLACEHOLDER tab", g0);
  assert.ok(h0 > 0 && h1 > h0 && g0 > h1 && g1 > g0, "anchors not found — applyTabStatus / wireTabDrag / appendTabAfterWidgets or the skeleton-tab / placeholder comments moved; re-anchor");
  const js = requireCjs("esbuild").transformSync(RENDER.slice(h0, h1) + RENDER.slice(g0, g1) + RENDER.slice(a, b), { loader: "ts" }).code;
  const prelude = `
    let renameActive = false, renderPendingAfterRename = false, tabPointerHeld = false, renderPendingWhilePressed = false;
    let tabStripSig = "", activeId = null, peekId = null, allHiddenBlanked = false, draggedId = null, draggedEl = null, tabDragCommitted = false;
    let order = [], closingTabs = new Set(), tabMeta = new Map(), sessions = new Map(), views = new Map();
    let vanishedId = null, vanishedWhy = null;   // the unfocused pane's memory of what vanished and why (T357)
    let collapsedTabIds = new Set(), draggedGroup = null, provisionalId = null, provisionalTags = [];
    // stripGroupRows mirrors the default. Its break site is never reached here: FakeEl has no childElementCount,
    // so the gate's childElementCount operand is undefined whatever the setting (and the packed bit after it is
    // never read), hence no makeRowBreak stub. Give FakeEl a childElementCount and this prelude needs one.
    let settings = { tabCtx: "over50", stripGroupRows: true, theme: "classic", colormap: "aurora", tabWidgets: { on: {}, order: [], opts: {} } };
    const H = HOOKS;
    // the tab-title widgets (T379): a faithful stand-in for the registry's composition over the real tab-state rules, so the
    // dot slot and the gauge land as the strip paints them; the hot-key store is empty here
    const composeTabWidgets = (tab, slot, sid, status, prefs) => {
      const dot = () => { const cls = H.tabDotClass(status.state); if (cls) { const d = el("span", cls); const t = H.tabDotTitle(status.state); if (t) d.title = t; tab.appendChild(d); } };
      if (slot === "before") { if (!H.dotAfter) dot(); }   // H.dotAfter: compose the status dot AFTER the name, the dragged-past case (item 8)
      else if (slot === "after") { if (H.dotAfter) dot(); const st = status.state; if (status.ctx && settings.tabCtx !== "never" && st !== "compacting" && st !== "closed") { const pct = parseInt(status.ctx, 10) || 0; if (settings.tabCtx === "always" || pct >= 50) tab.appendChild(el("span", "tab-ctx")); } }
    };
    const applyTabBadgeMode = H.applyTabBadgeMode;
    const tabHotkey = () => "";
    const window = { __rompShowStrip: false }; const openSettingsOn = () => {};   // the tab-widgets gear mounts only where a gear can be reached (VS Code's strip or the shell); neither here
    const el = (tag, cls) => new H.FakeEl(tag, cls);
    const document = { activeElement: null,
      getElementById: (id) => id === "tabs" ? H.bar : id === "mtag-slot" ? H.mslot : null,
      createTextNode: (t) => { const n = new H.FakeEl("#text"); n.textContent = t; return n; } };
    const auditTabOrder = () => {}; const onlyTag = () => H.only; const matchesOnly = (name, only) => name.includes(only);
    const tabInView = (id) => id === peekId || !H.hidden.has(id);
    // the chat split's partition (2026-09-11), inert: no shell here, so the sets are null and every id is held
    let colSets = null; const readColSets = () => null; const heldHere = () => true; const noteColumnEmptiness = () => {}; const noteOrphanState = () => {}; const postChatTabs = () => {}; const isSubId = () => false; const staleActiveFallback = () => {};   // postChatTabs and isSubId: the open-tabs post at the top of renderTabs (plans/artifacts-pane.md 9.2), not the strip's
    const isProvisionalId = (id) => typeof id === "string" && id.startsWith("new-");   // the draggable flag's third clause (a create in flight is not draggable, 2026-09-11): provisional.ts's shape
    // the one visibility predicate renderTabs builds visibleIds from (T357 later lows): the view, then the #only= filter
    const stripShows = (id, only) => tabInView(id) && (!only || matchesOnly(sessions.get(id)?.name ?? tabMeta.get(id)?.name ?? "", only));
    const stripLists = (id) => !closingTabs.has(id) && (order.includes(id) || tabMeta.has(id));   // the strip's one membership rule (T357 fix)
    const setActive = (id) => { H.activated.push(id); }; const setTimeout = (f) => { H.timers.push(f); return 0; };   // the deferred checks, held for the test to fire
    const unfocusHiddenByView = () => {};
    // the section-at-a-glance view's readers on the strip, inert: the plan the view reads (lastStripItems), the
    // section the pane shows (snapView, null: no view open, so stripAftermath's follow does nothing), and the
    // view's own painter and focus probe (never reached while snapView is null)
    let lastStripItems = [], snapView = null;
    const revealedTabs = H.revealedTabs; let lastShownTabIds = null; const schedulePrebuild = () => { H.prebuilds = (H.prebuilds || 0) + 1; };   // the reveal detector renderTabs runs (PR 1671 round four): the pure half, the paint memory, a counted schedule
    const renderSnapshot = () => false; const snapshotHoldsFocus = () => false; const showActive = () => {};
    const titleWithKey = () => H.keyHint; const surfaceLens = () => H.lens; const effViews = () => null; const viewTagUnion = () => H.unions;
    const hostIsDown = (id) => H.down.has(id); const hostDownNote = (id) => H.notes[id] ?? "";
    function makePlaceholderTab(id) { const t = el("div", "tab tab-placeholder"); t.dataset.id = id; H.placeholders++; return t; }
    const skeletonTabs = H.newSkeletonState(); const renderKind = H.renderKind;
    function makeSkeletonTab(id) { const t = el("div", "tab tab-skeleton"); t.dataset.id = id; H.skeletons++; return t; }
    // the sectioned strip's pure rules, for real; the header builder a recorder
    const planStrip = H.planStrip; const headWords = H.headWords; const phoneStandIns = H.phoneStandIns;
    const readTabGroups = (u) => H.parseTabGroups(H.groupsRaw, u);
    const tabGroups = () => readTabGroups(H.unions); const writeTabGroups = () => {};
    const phoneLayout = () => H.phone;
    const tabStateClass = H.tabStateClass, tabDotClass = H.tabDotClass, tabDotTitle = H.tabDotTitle, sectionPip = H.sectionPip, sectionPipMembers = H.sectionPipMembers, sectionPipTitle = H.sectionPipTitle;   // tabDotClass: the state-dot slot every tab carries (the tab-strip fix, 2026-09-08); tabDotTitle: what the slot says on hover
    // the RINGS (widgets since 2026-09-14): a faithful stand-in for tab-widgets.ts composeTabRing over the real tab-state rule — every
    // ring class off, then the first switched-on ring whose test holds (settings.tabWidgets.on, every ring on by default) — and the
    // switch predicate the folded header's pip reads
    const ringSwitch = (prefs) => (id) => !(prefs && prefs.on && prefs.on[id] === false);
    const composeTabRing = (tab, sid, status, prefs) => { for (const id of H.RING_ORDER) tab.classList.remove(id); const r = H.tabRingId(status, ringSwitch(prefs)); if (r) tab.classList.add(r); return r; };
    const mentionRosterChanged = () => {};   // the @-mention roster hook at the top of renderTabs: not the strip's (composer-mention-pane.test.ts)
    function makeGroupHead(sec, folded, active, hidden) {
      const h = el("div", "tab-group-head" + (folded ? " collapsed" : ""));
      h.dataset.group = String(sec.name);
      H.heads.push({ name: sec.name, color: sec.color, ids: sec.ids.slice(), folded, active, hidden: hidden.slice() });
      return h;
    }
    const onTabKey = () => {}; const dragImageBlank = () => el("div"); const hideTabTip = () => {}; const syncComposerPh = () => {}; const hideFilePreview = () => {}; const snapshotDragGeometry = () => {}; const inRompShell = () => false;   // inRompShell: postTabDrag (lifted with wireTabDrag, the chat split 2026-09-11) tells no shell here; syncComposerPh: the rebuild re-syncs the composer's name overlay (T335), inert here
    const flipTabs = (f) => f(); const applyCompactSweep = () => {};
    const hostNameNodes = (name) => [document.createTextNode(name)]; const fadedColor = (h) => h;
    const tabCtxGauge = () => el("span", "tab-ctx"); const pickTone = (a, b) => b ?? a;
    const fedMissing = false;   // the page has its federation manager (render.ts fedMissing, 2026-09-10): tabs drag as before
    const showTabTip = (tab, s) => { H.tips.push(s); }; const toggleLedgerCollapsed = () => {}; const showTabMenu = () => {}; const openPicker = () => {};
    const tagMenuButton = () => el("span", "tag-btn"); const openTagMenu = () => {}; const postLens = () => {}; const vscodeApi = null;
    const GEAR_GLYPH = "\u26ed"; const openRowsMenu = () => {};   // the strip's gear (T379) and its menu (T405): built, its press outside this harness   // the tab lock (T395): the strip builds the button; its press is outside this slice
    const TAG_BTN_BORDER_CSS = "var(--card-border, rgba(255,255,255,0.10))";   // the tag button's themed border the lock borrows (T395)
    const syncTagFilter = () => { H.tagSyncs++; }; const paintTabRowLines = () => { H.rowPaints++; }; const ensureTabRowObserver = () => {};
    const focusActiveTab = () => {}; const syncNoSessionsPlaceholder = (v, t) => { H.aftermaths.push([v, t]); };
  `;
  const epilogue = `
    return { renderTabs, sig: () => tabStripSig, folded: () => collapsedTabIds, skeletonTabs,
      set: (p) => { for (const k of Object.keys(p)) {
        if (k === "activeId") activeId = p[k]; else if (k === "peekId") peekId = p[k]; else if (k === "order") order = p[k];
        else if (k === "sessions") sessions = p[k]; else if (k === "tabMeta") tabMeta = p[k]; else if (k === "settings") settings = p[k];
        else if (k === "views") views = p[k]; else if (k === "renameActive") renameActive = p[k]; else if (k === "tabPointerHeld") tabPointerHeld = p[k];
        else if (k === "provisionalId") provisionalId = p[k]; else if (k === "provisionalTags") provisionalTags = p[k];
        else if (k === "vanishedId") vanishedId = p[k]; else if (k === "vanishedWhy") vanishedWhy = p[k];
        else throw new Error("unknown knob " + k); } },
      pending: () => ({ renderPendingAfterRename, renderPendingWhilePressed }) };
  `;
  return new Function("HOOKS", prelude + js + epilogue) as (hooks: Hooks) => Api;
}

const session = (name: string, state: string, extra: Record<string, unknown> = {}) =>
  ({ name, color: { bg: "#336699", fg: "#ffffff" }, status: { state, ...extra } });
/** A tag union as viewTagUnion builds one: the plan reads name, color, members and the local id. */
const union = (name: string, color: string, members: string[]): TagUnion =>
  ({ name, color, members, ids: ["t-" + name], localId: "t-" + name, locals: [], remotes: [] });
const groups = (patch: Record<string, unknown>) => JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], ...patch });

/** Two landed sessions and one placeholder, the first active; every knob at a quiet default (no tags: the
 *  flat strip). */
function world(): { H: Hooks; api: Api; sessions: Map<string, any>; tabMeta: Map<string, any>; settings: any } {
  const H: Hooks = { FakeEl, applyTabBadgeMode: TW.applyTabBadgeMode, dotAfter: false, bar: new FakeEl("div"), mslot: null, only: "", hidden: new Set(), down: new Set(), notes: {},
                     keyHint: "Open a session (K)", lens: { all: true }, unions: [], tips: [], aftermaths: [], rowPaints: 0, tagSyncs: 0, placeholders: 0,
                     groupsRaw: null, phone: false, heads: [],
                     planStrip, parseTabGroups, headWords, revealedTabs, phoneStandIns, tabStateClass, tabRingId, RING_ORDER, tabDotClass, tabDotTitle, sectionPip, sectionPipMembers, sectionPipTitle,
                     newSkeletonState, renderKind, skeletons: 0, timers: [], activated: [] };
  const api = lift()(H);
  const sessions = new Map<string, any>([["a", session("web", "ready")], ["b", session("api", "working")]]);
  const tabMeta = new Map<string, any>([["p", { name: "tests", color: { bg: "#112233", fg: "#ffffff" } }]]);
  const settings = { tabCtx: "over50", stripGroupRows: true, theme: "classic", colormap: "aurora", tabWidgets: { on: {}, order: [], opts: {} } };
  api.set({ order: ["a", "b", "p"], sessions, tabMeta, settings, activeId: "a" });
  return { H, api, sessions, tabMeta, settings };
}

/** The same world sectioned: `a` and `b` home in the tag `backend`, the placeholder `p` untagged, and the
 *  UNTAGGED placeholder active — so the backend section may fold (the active tab's section never does). */
function sectionedWorld() {
  const w = world();
  w.H.unions = [union("backend", "#aa0000", ["a", "b"])];
  w.api.set({ activeId: "p" });
  return w;
}

/** Drive one change: it repaints the strip exactly once, and an unchanged render after it does not. */
function repaintsOnce(H: Hooks, api: Api, what: string, change: () => void): void {
  change();
  const before = H.bar.wipes;
  api.renderTabs();
  assert.equal(H.bar.wipes, before + 1, what + " changed: the strip repaints");
  api.renderTabs();
  assert.equal(H.bar.wipes, before + 1, what + " unchanged since: no repaint");
}

test("an unchanged strip is not rebuilt, and the aftermath runs on both paths", () => {
  const { H, api } = world();
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  assert.equal(H.rowPaints, 1);
  assert.deepEqual(H.aftermaths, [[3, 3]]);
  const nodes = [...H.bar.children];
  assert.equal(H.bar.tabs().length, 3, "two sessions and a placeholder");
  assert.equal(H.heads.length, 0, "no tags: the flat strip, no header");
  api.renderTabs();
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "the second and third render found nothing changed: no wipe");
  assert.equal(H.rowPaints, 1, "no layout read either");
  assert.equal(H.placeholders, 1, "no node minted");
  assert.deepEqual(H.bar.children, nodes, "the same DOM nodes");
  assert.equal(H.aftermaths.length, 3, "the no-sessions placeholder reconciles on the skip path too");
});

test("every input the strip paints repaints it, once, when it changes", () => {
  const { H, api, sessions, tabMeta, settings } = world();
  api.renderTabs();
  const a = sessions.get("a");
  const changes: [string, () => void][] = [
    ["a session's state", () => { a.status.state = "working"; }],
    ["a state's tab class with the state unchanged (blocked: transient → on-you)", () => { a.status = { state: "blocked" }; api.renderTabs(); a.status = { state: "blocked", apiRefusal: true }; }],
    ["a session's name", () => { a.name = "web2"; }],
    ["a session's color", () => { a.color = { bg: "#993366", fg: "#ffffff" }; }],
    ["faded", () => { a.status.faded = true; }],
    ["context percent", () => { a.status.ctx = "72"; }],
    ["context color", () => { a.status.ctxColor = [200, 100, 0]; }],
    ["context tone", () => { a.status.ctxTone = [20, 20, 220]; }],
    ["the viewer flag", () => { a.sub = true; }],
    ["the host-down mark", () => { H.down.add("a"); }],
    ["the host-down note while the mark stands", () => { H.notes.a = "web-host is disconnected, last reached 10:00"; }],
    ["the active tab", () => { api.set({ activeId: "b" }); }],
    ["the peek tab", () => { api.set({ peekId: "b" }); }],
    ["the order", () => { api.set({ order: ["b", "a", "p"] }); }],
    ["a tab hidden by the views filter", () => { H.hidden.add("p"); }],
    ["the context-gauge setting", () => { settings.tabCtx = "always"; }],
    ["the one-group-per-row setting", () => { settings.stripGroupRows = false; }],
    ["the theme", () => { settings.theme = "yatharth"; }],
    ["the colormap", () => { settings.colormap = "hawaii"; }],
    ["the + tab's key hint", () => { H.keyHint = "Open a session (J)"; }],
    ["the tag lens", () => { H.lens = { all: false, tags: ["t1"] }; }],
    ["the tag unions (a tag holding no visible tab: the filter chips read it)", () => { H.unions = [union("u", "#000000", ["zz"])]; }],
    ["a placeholder's name", () => { H.hidden.delete("p"); api.renderTabs(); tabMeta.get("p").name = "tests2"; }],
    ["a placeholder's color", () => { tabMeta.get("p").color = { bg: "#445566", fg: "#000000" }; }],
    ["a placeholder's session landing", () => { sessions.set("p", session("tests2", "opening")); }],
  ];
  for (const [what, change] of changes) repaintsOnce(H, api, what, change);
});

test("the sectioned strip: every input a group header paints repaints it, once, when it changes", () => {
  const { H, api, sessions } = sectionedWorld();
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  assert.deepEqual(H.heads.map((h) => [h.name, h.folded, h.active, h.hidden]), [["backend", false, false, []], [null, false, true, []]],
    "a backend header, open, then the untagged separator (which holds the active placeholder)");
  const headNodes = H.bar.heads();
  assert.equal(headNodes.length, 2);
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "equal plan, equal tabs: skipped");
  assert.deepEqual(H.bar.heads(), headNodes, "the header nodes were kept");
  const changes: [string, () => void][] = [
    ["a section folds", () => { H.groupsRaw = groups({ collapsed: ["backend"] }); }],
    ["a hidden member's state (the folded header's pip)", () => { sessions.get("a").status.state = "blocked"; }],
    ["a hidden member's name (the pip's tooltip)", () => { sessions.get("a").name = "web-renamed"; }],
    ["a member pinned to show under its folded header", () => { H.groupsRaw = groups({ collapsed: ["backend"], pinned: [{ sid: "b", name: "backend", id: "t-backend" }] }); }],
    ["the section unfolds", () => { H.groupsRaw = groups({}); }],
    ["the tag's color (the header's chip)", () => { H.unions = [union("backend", "#00aa00", ["a", "b"])]; }],
    ["a tab's home tag (membership)", () => { H.unions = [union("backend", "#00aa00", ["a"])]; }],
    ["the group order", () => { H.unions = [union("frontend", "#0000aa", ["b"]), union("backend", "#00aa00", ["a"])]; api.renderTabs(); H.unions = [union("backend", "#00aa00", ["a"]), union("frontend", "#0000aa", ["b"])]; }],
    ["the active tab's section (unfoldable while it holds it)", () => { H.groupsRaw = groups({ collapsed: ["backend"] }); api.renderTabs(); api.set({ activeId: "a" }); }],
    ["a provisional tab's tags (it sections under its future home)", () => { api.set({ provisionalId: "p", provisionalTags: ["frontend"] }); }],
    ["sectioning switched off", () => { H.groupsRaw = groups({ on: false }); }],
    // the phone folds like the desktop since 2026-09-23; what it paints beyond the plan is the folded-away ACTIVE tab's node,
    // which its picker's current-session chip mirrors (tab-groups.ts phoneStandIns)
    ["the phone layout with the active tab folded away (its stand-in node for the picker's chip)", () => { H.groupsRaw = groups({ collapsed: ["backend"] }); api.set({ activeId: "a" }); api.renderTabs(); H.phone = true; }],
  ];
  for (const [what, change] of changes) repaintsOnce(H, api, what, change);
});

test("the phone paints the folded-away ACTIVE tab as one hidden node after its stand-in header, and only there (2026-09-23)", () => {
  // the picker's current-session chip mirrors the strip's active tab; a fold that took it off the strip would leave the
  // chip naming whichever session came first. The node is the full tab (the one builder), marked away: never displayed,
  // out of the keyboard's reach, not draggable. The desktop paints no such node (its header is the stand-in)
  const { H, api } = sectionedWorld();
  H.groupsRaw = groups({ collapsed: ["backend"] });
  api.set({ activeId: "a" });
  api.renderTabs();
  assert.deepEqual(H.bar.tabs().map((t) => t.dataset.id), ["p"], "the desktop: only the untagged placeholder is a tab node");
  H.phone = true;
  api.renderTabs();
  const tabs = H.bar.tabs();
  assert.deepEqual(tabs.map((t) => [t.dataset.id, t.classList.contains("tab-away"), t.classList.contains("active")]), [["a", true, true], ["p", false, false]],
    "the phone: the active tab's node, away and active, then the placeholder");
  const away = tabs[0];
  assert.deepEqual([away.attrs["aria-hidden"], away.tabIndex, away.draggable], ["true", -1, false], "hidden from assistive tech and the keyboard, and never dragged");
  const kids = H.bar.children, at = kids.indexOf(away);
  assert.ok(at > 0 && kids[at - 1].classList.contains("tab-group-head") && kids[at - 1].dataset.group === "backend", "right after the header that stands in for it");
  assert.deepEqual([...api.folded()].sort(), ["a", "b"], "the plan's folded set is unchanged: the node is paint, not a tab back on the strip");
  // the active tab shown again (its section opened): no node
  H.groupsRaw = groups({});
  api.renderTabs();
  assert.ok(!H.bar.tabs().some((t) => t.classList.contains("tab-away")), "open: the tab itself is on the strip, no stand-in node");
});

test("the folded set the plan yields is published on the skip path too (keyboard cycling reads it)", () => {
  const { H, api } = sectionedWorld();
  H.groupsRaw = groups({ collapsed: ["backend"] });
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  assert.deepEqual([...api.folded()].sort(), ["a", "b"], "both members hidden under the folded header");
  assert.deepEqual(H.heads.map((h) => [h.name, h.folded, h.hidden]), [["backend", true, ["a", "b"]], [null, false, []]]);
  assert.equal(H.bar.tabs().length, 1, "only the untagged placeholder is a tab node");
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "skipped");
  assert.deepEqual([...api.folded()].sort(), ["a", "b"], "the set stands across the skip");
});

test("the paint wears the shared state → class rule (tab-state.ts), and the signature reads the same rule", () => {
  const { H, api, sessions } = world();
  sessions.get("a").status = { state: "blocked", apiSpendLimit: true };
  api.renderTabs();
  const tab = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(tab.has("tab-blocked") && !tab.has("tab-retrying"), "an on-you block: alarm-red");
  assert.equal(tabStateClass(sessions.get("a").status), "tab-blocked");
  // the same state under a different class (the transient API error) is a different signature
  sessions.get("a").status = { state: "blocked" };
  api.renderTabs();
  assert.equal(H.bar.wipes, 2);
  const tab2 = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(tab2.has("tab-retrying") && !tab2.has("tab-blocked"), "a transient API error auto-retries: amber");
});

test("the RINGS ride beside the state class as one class at a time: a working tab wears the magenta with its dot; the magenta's flip alone repaints once, and a switch off takes the ring away (2026-09-13, widgets since 2026-09-14)", () => {
  const { H, api, sessions, settings } = world();
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  // the feed files a card of the WORKING session under needs-you: the tab keeps its working class and gains the ring
  sessions.get("b").status = { state: "working", needsYou: true };
  api.renderTabs();
  assert.equal(H.bar.wipes, 2, "the verdict alone is a repaint: the signature reads needsYou");
  const b = H.bar.tabs().find((t) => t.dataset.id === "b")!;
  assert.ok(b.has("tab-working") && b.has("ring-waiting-on-you"), "gold dot AND magenta ring: the ring does not replace the state");
  api.renderTabs();
  assert.equal(H.bar.wipes, 2, "unchanged: no rebuild");
  // the magenta ring switched off in the settings: one repaint (settings.tabWidgets is in the signature), the class gone, the state kept
  api.set({ settings: { ...settings, tabWidgets: { on: { "ring-waiting-on-you": false }, order: [], opts: {} } } });
  api.renderTabs();
  assert.equal(H.bar.wipes, 3, "the switch alone is a repaint");
  const bOff = H.bar.tabs().find((t) => t.dataset.id === "b")!;
  assert.ok(bOff.has("tab-working") && !bOff.has("ring-waiting-on-you"), "switched off: the dot stays, the ring goes");
  api.set({ settings });
  api.renderTabs();
  assert.equal(H.bar.wipes, 4);
  assert.ok(H.bar.tabs().find((t) => t.dataset.id === "b")!.has("ring-waiting-on-you"), "…and back on");
  // the card leaves the column (answered, cleared): the ring goes, the working class stays
  sessions.get("b").status = { state: "working", needsYou: false };
  api.renderTabs();
  assert.equal(H.bar.wipes, 5);
  const b2 = H.bar.tabs().find((t) => t.dataset.id === "b")!;
  assert.ok(b2.has("tab-working") && !b2.has("ring-waiting-on-you"));
  // an idle session that asked: the ring alone (the common case the state rule never sees)
  sessions.get("a").status = { state: "ready", needsYou: true };
  api.renderTabs();
  const a = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(a.has("ring-waiting-on-you") && !a.has("tab-working") && !a.has("tab-awaiting"));
  // a live prompt on the same session: the red ring alone — never two rings
  sessions.get("a").status = { state: "needsInput", needsYou: true };
  api.renderTabs();
  const a2 = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(a2.has("tab-awaiting") && a2.has("ring-needs-you") && !a2.has("ring-waiting-on-you"), "red outranks magenta: one ring class");
  // the red ring switched off: the same tab wears the magenta (a card of its DOES need you), the state class untouched
  api.set({ settings: { ...settings, tabWidgets: { on: { "ring-needs-you": false }, order: [], opts: {} } } });
  api.renderTabs();
  const a3 = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(a3.has("tab-awaiting") && a3.has("ring-waiting-on-you") && !a3.has("ring-needs-you"), "the next ring whose test holds");
  // …and with no card, a plain awaiting tab: the state's hover title and dot slot, no ring
  sessions.get("a").status = { state: "needsInput" };
  api.renderTabs();
  const a4 = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(a4.has("tab-awaiting") && !a4.className.includes("ring-"), "no ring at all");
  api.set({ settings });
  // an API retry: the amber ring; a card on it: the magenta outranks the amber
  sessions.get("a").status = { state: "retrying" };
  api.renderTabs();
  assert.ok(H.bar.tabs().find((t) => t.dataset.id === "a")!.has("ring-retrying"));
  sessions.get("a").status = { state: "retrying", needsYou: true };
  api.renderTabs();
  const a5 = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.ok(a5.has("tab-retrying") && a5.has("ring-waiting-on-you") && !a5.has("ring-retrying"), "magenta over amber");
});

test("the dot slot explains its state on hover: a visible dot carries the feed's phrase for that state, the hidden slot says nothing", () => {
  // the phrases are the feed's (feed.ts DOT_TIP), read from its source so the two surfaces cannot drift apart
  const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
  const at = FEED.indexOf("const DOT_TIP");
  const tip: Record<string, string> = Object.fromEntries([...FEED.slice(at, FEED.indexOf("};", at)).matchAll(/^\s*(work|await|unknown): "([^"]+)",/gm)].map((m) => [m[1], m[2]]));
  assert.deepEqual(Object.keys(tip).sort(), ["await", "unknown", "work"]);
  const sep = /^working(\s\S\s)/.exec(tip.work)![1];   // the feed's separator: the opening phrase (no feed twin) keeps the feed's shape
  const { H, api, sessions } = world();
  api.renderTabs();
  // the dot is found BY CLASS: the label, the context gauge and the close button follow it, so once the paint is
  // done it is not the tab's last child (it is at the moment applyTabStatus writes the title)
  const dot = (id: string): FakeEl => {
    const d = H.bar.tabs().find((t) => t.dataset.id === id)!.children.filter((c) => c.has("tab-dot"));
    assert.equal(d.length, 1, id + ": one dot slot");
    return d[0];
  };
  assert.ok(!dot("b").has("none"), "working: a visible dot");
  assert.equal(dot("b").title, tip.work, "the working dot speaks the feed's working phrase");
  assert.ok(dot("a").has("none"), "ready: the hidden slot");
  assert.equal(dot("a").title, "", "the hidden slot says nothing");
  const a = sessions.get("a");
  a.status = { state: "awaitingBg" }; api.renderTabs();
  assert.ok(dot("a").has("await")); assert.equal(dot("a").title, tip.await, "awaiting background work: the feed's awaiting phrase");
  a.status = {}; api.renderTabs();
  assert.ok(dot("a").has("unknown")); assert.equal(dot("a").title, tip.unknown, "no state: the feed's unknown phrase");
  a.status = { state: "opening" }; api.renderTabs();
  assert.ok(dot("a").has("opening")); assert.equal(dot("a").title, "opening" + sep + "this session is still starting up", "opening: the strip's own phrase (the feed draws no opening pip)");
  a.status = { state: "compacting" }; api.renderTabs();
  const tabA = H.bar.tabs().find((t) => t.dataset.id === "a")!;
  assert.equal(tabA.children.filter((c) => c.has("tab-dot")).length, 0, "compacting: no dot");
  assert.ok(tabA.children.find((c) => c.has("tab-compacting-bar"))!.title.startsWith("compacting"), "the bar carries its own title");
});

test("a render held by the pressed-tab or rename guard is not lost to the skip", () => {
  const { H, api, sessions } = world();
  api.renderTabs();
  sessions.get("a").name = "renamed";
  api.set({ tabPointerHeld: true });
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "held: no rebuild mid-click");
  assert.equal(api.pending().renderPendingWhilePressed, true);
  api.set({ tabPointerHeld: false });
  api.renderTabs();
  assert.equal(H.bar.wipes, 2, "released: the change that arrived while held is painted");
  sessions.get("b").name = "renamed too";
  api.set({ renameActive: true });
  api.renderTabs();
  assert.equal(H.bar.wipes, 2);
  assert.equal(api.pending().renderPendingAfterRename, true);
  api.set({ renameActive: false });
  api.renderTabs();
  assert.equal(H.bar.wipes, 3);
});

test("a tab drag resets the signature: the next render rebuilds even with nothing else changed", () => {
  const { H, api } = world();
  api.renderTabs();
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  H.bar.tabs().find((t) => t.dataset.id === "a")!.fire("dragstart", { dataTransfer: null });
  api.renderTabs();
  assert.equal(H.bar.wipes, 2, "the drag live-reordered the DOM outside renderTabs");
});

test("the hover tooltip reads the session fresh: a tab node outlives a frame that replaced the session object", () => {
  const { H, api, sessions } = world();
  api.renderTabs();
  const fresh = session("web", "ready");   // same painted fields, new object (a kernel frame's upsert)
  sessions.set("a", fresh);
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "equal signature: the node was kept");
  H.bar.tabs().find((t) => t.dataset.id === "a")!.fire("mouseenter");
  assert.equal(H.tips.length, 1);
  assert.equal(H.tips[0], fresh, "the tooltip got the session that is current, not the one the node was built from");
});

test("the mobile tag slot mounts once, and an empty slot is a reason to rebuild", () => {
  const { H, api } = world();
  H.mslot = new FakeEl("div");
  api.renderTabs();
  assert.equal(H.mslot.children.length, 2, "button + chips mounted");
  assert.equal(H.bar.wipes, 1);
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "mounted slot, equal strip: skipped");
  assert.equal(H.mslot.children.length, 2, "not mounted twice");
  H.mslot.children = [];
  api.renderTabs();
  assert.equal(H.bar.wipes, 2, "an empty slot forces the rebuild that mounts it");
  assert.equal(H.mslot.children.length, 2);
});

test("the all-hidden blank lands on the skip path when the active view appears between two equal strips", () => {
  const { H, api } = world();
  H.hidden.add("a"); H.hidden.add("b"); H.hidden.add("p");
  const views = new Map<string, any>();
  api.set({ views });
  api.renderTabs();
  assert.equal(H.bar.wipes, 1);
  assert.deepEqual(H.aftermaths.at(-1), [0, 3], "no visible tab, three sessions");
  const av = { el: new FakeEl("div") };
  views.set("a", av);   // the lazily built active view
  api.renderTabs();
  assert.equal(H.bar.wipes, 1, "equal strip: skipped");
  assert.equal(av.el.style.display, "none", "the transcript is blanked from the aftermath, not the rebuild");
  H.hidden.delete("a");
  api.renderTabs();
  assert.equal(H.bar.wipes, 2);
  assert.equal(av.el.style.display, "", "restored once anything is visible");
});

test("executed: the hidden tab's restore fires only for a tab still on the strip (T357 later lows, the review's low)", () => {
  // the pane unfocused with web hidden by the filter (vanishedWhy "hidden"); the filter lifts and renderTabs schedules
  // the restore. BEFORE it fires, web is torn down while not active: dismissSession writes vanished* for the active tab
  // alone, so the reason still reads "hidden" while web has left `order`. The timer must not hand focus to a tab nobody
  // can see: the fire-time check reads the strip's membership, not only the predicate
  const { H, api, sessions } = world();
  api.set({ activeId: null, vanishedId: "a", vanishedWhy: "hidden" });
  api.renderTabs();
  assert.equal(H.timers.length, 1, "the restore is scheduled once");
  api.set({ order: ["b", "p"] }); sessions.delete("a");
  H.timers[0]();
  assert.deepEqual(H.activated, [], "…and does not fire for a tab that left the strip meanwhile");
  // the same schedule with the tab still listed restores it
  const w2 = world();
  w2.api.set({ activeId: null, vanishedId: "a", vanishedWhy: "hidden" });
  w2.api.renderTabs();
  assert.equal(w2.H.timers.length, 1);
  w2.H.timers[0]();
  assert.deepEqual(w2.H.activated, ["a"], "the tab still on the strip takes focus back");
});

test("executed: the restore's fire-time membership is the paint's own rule: a tab listed only as a placeholder paints, so it restores (T357 fix)", () => {
  // the schedule reads visibleIds (order AND the tabMeta placeholders); the fire-time check read `order` alone, so a
  // tab present only as a placeholder painted while its restore declined (the review's low). One rule at both ends.
  const { H, api, tabMeta } = world();
  tabMeta.set("a", { name: "web", color: { bg: "#112233", fg: "#ffffff" } });
  api.set({ order: ["b", "p"], activeId: null, vanishedId: "a", vanishedWhy: "hidden" });
  api.renderTabs();
  assert.equal(H.timers.length, 1, "the placeholder-only tab is visible, so the restore is scheduled");
  H.timers[0]();
  assert.deepEqual(H.activated, ["a"], "…and fires: it paints, so it restores");
});

test("badge mode executed: the real applyTabBadgeMode re-inks an AFTER-side status dot to retrying, ring off (item 8)", () => {
  const { H, api, sessions, settings } = world();
  H.dotAfter = true;                                   // the status dot composed AFTER the name (dragged past it): the case the before-side stub never drove
  settings.tabStateBadge = true;                       // badge mode: appendTabAfterWidgets runs applyTabBadgeMode after both sides
  sessions.set("a", session("web", "retrying"));       // a soft-blocked, auto-retrying session
  api.set({ sessions, settings });
  api.renderTabs();
  const tabA = H.bar.tabs().find((t) => t.dataset.id === "a");
  assert.ok(tabA, "the retrying tab painted");
  const dot = tabA!.querySelector(".tab-dot");
  assert.ok(dot, "the status-dot slot exists, composed after the name");
  assert.deepEqual(dot!.className.split(/\s+/).filter(Boolean).sort(), ["retrying", "tab-dot"],
    "the real applyTabBadgeMode found the after-side slot and inked it amber; a lookup stopping at the label would miss it and leave tab-dot none");
  assert.equal(tabA!.has("ring-retrying"), false, "and took the retrying ring off the tab");
});

test("badge OFF, executed: a cold tab's needsYouCount change repaints it, so its title (the count in both modes) never goes stale (item 1)", () => {
  const { H, api, sessions, tabMeta, settings } = world();
  settings.tabStateBadge = false;                    // ring mode (a chosen-off browser; the badge is the default since 2026-09-23)
  tabMeta.set("sk", { name: "dev", color: { bg: "#334455", fg: "#ffffff" } });
  api.skeletonTabs.ids.add("sk");                    // a cold tab: listed, not a full session, its kernel status frame held
  api.skeletonTabs.status.set("sk", { state: "working", needsYou: true, needsYouCount: 3 });
  api.set({ order: ["a", "b", "p", "sk"], tabMeta, settings });
  api.renderTabs();                                  // baseline: the cold tab painted with count 3
  // a cold tab's title carries the count in BOTH modes (makeSkeletonTab), so a count move must repaint it even with the
  // badge OFF; at the base the skeleton sig keyed the count only in badge mode, so a count move left the cold title stale.
  repaintsOnce(H, api, "a cold tab's needsYouCount with the badge off", () => { api.skeletonTabs.status.set("sk", { state: "working", needsYou: true, needsYouCount: 5 }); });
});
