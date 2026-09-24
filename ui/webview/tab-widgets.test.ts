// The tab-title widget registry (T379, the user 2026-09-12): registration order is the default composition order, the
// stored prefs decide which widgets a tab carries and with which options, the older tabCtx mode is the context bar's
// MIRROR both ways, and the strip and the settings row draw a widget through the same render. Executed on a tiny DOM
// (document.createElement stubbed), so a widget's DOM is read, never inferred from source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
const STRIP_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
import type { WidgetStatus, TabWidgetPrefs } from "./tab-widgets";

type El = { tag: string; className: string; textContent: string; title: string; attrs: Record<string, string>; children: El[]; style: Record<string, string>; parent: El | null;
            appendChild: (c: El) => El; setAttribute: (k: string, v: string) => void; remove: () => void;
            classList: { add: (...c: string[]) => void; remove: (...c: string[]) => void; contains: (c: string) => boolean; toggle: (c: string, on?: boolean) => void };
            querySelector: (sel: string) => El | null; getElementsByClassName: (cls: string) => El[] };
// The tiny DOM applyTabBadgeMode and composeTabRing read: className tokens, a live classList, appendChild/remove that keep
// a parent backref, and the two lookups applyTabBadgeMode uses (querySelector(".tab-dot") for the left dot it re-inks,
// getElementsByClassName("tab-badge") for the prior badge it clears). Nothing here is inferred from source: the node is real.
function mkEl(tag: string): El {
  const has = (c: string) => e.className.split(/\s+/).filter(Boolean).includes(c);
  const drop = (c: string) => { e.className = e.className.split(/\s+/).filter((x) => x && x !== c).join(" "); };
  const put = (c: string) => { if (!has(c)) e.className = (e.className + " " + c).trim(); };
  const e: El = { tag, className: "", textContent: "", title: "", attrs: {}, children: [], style: {}, parent: null,
    appendChild: (c) => { c.parent = e; e.children.push(c); return c; }, setAttribute: (k, v) => { e.attrs[k] = v; },
    remove: () => { if (e.parent) { e.parent.children = e.parent.children.filter((x) => x !== e); e.parent = null; } },
    classList: { add: (...cs: string[]) => cs.forEach(put), remove: (...cs: string[]) => cs.forEach(drop), contains: has, toggle: (c, on) => { (on === undefined ? !has(c) : on) ? put(c) : drop(c); } },
    querySelector: (sel) => { const cls = sel.startsWith(".") ? sel.slice(1) : sel; const walk = (n: El): El | null => { for (const ch of n.children) { if (ch.className.split(/\s+/).includes(cls)) return ch; const d = walk(ch); if (d) return d; } return null; }; return walk(e); },
    getElementsByClassName: (cls) => { const out: El[] = []; const walk = (n: El) => { for (const ch of n.children) { if (ch.className.split(/\s+/).includes(cls)) out.push(ch); walk(ch); } }; walk(e); return out; } };
  return e;
}
const store = new Map<string, string>();
(globalThis as any).document = { createElement: mkEl };
(globalThis as any).localStorage = { getItem: (k: string) => store.has(k) ? store.get(k)! : null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
(globalThis as any).navigator = { platform: "Linux x86_64" };

// eslint-disable-next-line @typescript-eslint/no-var-requires
const W = require("./tab-widgets") as typeof import("./tab-widgets");
// eslint-disable-next-line @typescript-eslint/no-var-requires
const S = require("./settings") as typeof import("./settings");

const classes = (e: El) => e.className.split(/\s+/).filter(Boolean);
const compose = (slot: "before" | "after", status: WidgetStatus, prefs: TabWidgetPrefs, sid = "11111111-2222-3333-4444-555555555555") => {
  const tab = mkEl("div"); W.composeTabWidgets(tab as unknown as HTMLElement, slot, sid, status, prefs); return tab.children;
};
const P = (p: Partial<TabWidgetPrefs> = {}): TabWidgetPrefs => ({ on: {}, order: [], opts: {}, ...p });

test("the six built-in widgets register in order: the dot before the name, the context bar and the hot key after it, then the three rings in precedence order; all on by default", () => {
  assert.deepEqual(W.tabWidgets().map((w) => [w.id, w.slot, w.defaultOn]),
    [["dot", "before", true], ["ctx", "after", true], ["hotkey", "after", true], ["ring-needs-you", "ring", true], ["ring-waiting-on-you", "ring", true], ["ring-retrying", "ring", true]]);
  assert.deepEqual(W.tabWidgets().map((w) => w.label), ["Status dot", "Context bar", "Hot key", "Blocked", "Needs you", "Retrying"]);
  assert.ok(W.tabWidgets().every((w) => w.description.length > 0 && !/\bfleet\b/i.test(w.description)));
  assert.deepEqual(W.titleWidgets().map((w) => w.id), ["dot", "ctx", "hotkey"], "the settings' Tab widgets rows: the widgets that render into the title");
  assert.deepEqual(W.ringWidgets().map((w) => [w.id, w.ring]), [["ring-needs-you", "ring-needs-you"], ["ring-waiting-on-you", "ring-waiting-on-you"], ["ring-retrying", "ring-retrying"]], "each ring's class is its id");
});

test("registration by id replaces; a contributed widget lands after the built-ins in the default order", () => {
  W.registerTabWidget({ id: "mark", label: "Demo mark", description: "a synthetic mark", defaultOn: false, slot: "after", render: () => { const e = mkEl("span"); e.className = "tab-mark"; return e as unknown as HTMLElement; } });
  assert.deepEqual(W.tabWidgets().map((w) => w.id), ["dot", "ctx", "hotkey", "ring-needs-you", "ring-waiting-on-you", "ring-retrying", "mark"]);
  W.registerTabWidget({ id: "mark", label: "Demo mark", description: "a synthetic mark, again", defaultOn: false, slot: "after", render: () => null });
  assert.equal(W.tabWidgets().length, 7, "the same id replaces, never duplicates");
  assert.equal(W.tabWidget("mark")!.description, "a synthetic mark, again");
});

test("the dot: the state rule's classes, hidden when idle by default, a quiet grey dot on the option; compacting yields nothing (its bar takes the slot)", () => {
  assert.deepEqual(compose("before", { state: "working" }, P()).map(classes), [["tab-dot"]]);
  assert.deepEqual(compose("before", { state: "awaitingBg" }, P()).map(classes), [["tab-dot", "await"]]);
  assert.deepEqual(compose("before", {}, P()).map(classes), [["tab-dot", "unknown"]]);
  assert.deepEqual(compose("before", { state: "ready" }, P()).map(classes), [["tab-dot", "none"]], "the slot is laid out in every state (T262g), hidden");
  assert.deepEqual(compose("before", { state: "ready" }, P({ opts: { dot: { idle: "grey" } } })).map(classes), [["tab-dot", "idle"]], "the option: a quiet dot when idle");
  assert.equal(compose("before", { state: "ready" }, P({ opts: { dot: { idle: "grey" } } }))[0].title, "idle");
  assert.equal(compose("before", { state: "working" }, P())[0].title, "working — a turn is running right now", "the feed's words on hover");
  assert.deepEqual(compose("before", { state: "compacting" }, P()), []);
  assert.deepEqual(compose("before", { state: "working" }, P({ on: { dot: false } })), [], "switched off: no slot at all");
  assert.deepEqual(compose("before", { state: "ready" }, P({ opts: { dot: { idle: "purple" } } })).map(classes), [["tab-dot", "none"]], "an unknown stored option falls to the default");
});

test("the context bar: from 50 percent by default, always on the option, never while compacting or closed, off when switched off", () => {
  const bar = (status: WidgetStatus, prefs = P()) => compose("after", status, prefs).filter((c) => classes(c).includes("tab-ctx"));
  assert.equal(bar({ state: "working", ctx: "62%" }).length, 1);
  assert.equal(bar({ state: "working", ctx: "40%" }).length, 0, "under half full: quiet");
  assert.equal(bar({ state: "working", ctx: "40%" }, P({ opts: { ctx: { show: "always" } } })).length, 1);
  assert.equal(bar({ state: "compacting", ctx: "62%" }).length, 0);
  assert.equal(bar({ state: "closed", ctx: "62%" }).length, 0);
  assert.equal(bar({ state: "working" }).length, 0, "no ctx reading: no bar");
  assert.equal(bar({ state: "working", ctx: "62%" }, P({ on: { ctx: false } })).length, 0);
  const g = bar({ state: "working", ctx: "62%", ctxColor: [10, 20, 30] })[0];
  assert.equal(g.children[0].className, "tab-ctx-fill");
  assert.equal(g.children[0].style.height, "62%");
  assert.equal(g.children[0].style.background, "rgb(10,20,30)", "the kernel's colormap colour rides the fill");
  assert.equal(g.title, "context 62% used");
});

test("the hot key: nothing until a hot key is assigned; the tab hot-key store shape (a set of sids, a keybinding override per sid) yields the keycap at its shortest", () => {
  const sid = "11111111-2222-3333-4444-555555555555";
  assert.deepEqual(compose("after", { state: "working" }, P()).filter((c) => classes(c).includes("tab-key")), [], "no set: no keycap");
  store.set(W.TABKEYS_KEY, JSON.stringify({ [sid]: "web" }));
  assert.deepEqual(compose("after", { state: "working" }, P()).filter((c) => classes(c).includes("tab-key")), [], "in the set but no chord bound: no keycap");
  store.set("romp:keys", JSON.stringify({ [W.HOTKEY_PREFIX + sid]: "Ctrl+Shift+1" }));
  const keys = compose("after", { state: "working" }, P()).filter((c) => classes(c).includes("tab-key"));
  assert.equal(keys.length, 1);
  assert.equal(keys[0].textContent, "⌃⇧1", "symbols, no separators (Ctrl is control everywhere)");
  assert.match(keys[0].title, /^hot key Ctrl\+Shift\+1/);
  assert.equal(keys[0].attrs["aria-label"], keys[0].title);
  assert.deepEqual(compose("after", { state: "working" }, P({ on: { hotkey: false } })).filter((c) => classes(c).includes("tab-key")), [], "switched off");
  store.delete(W.TABKEYS_KEY); store.delete("romp:keys");
});

test("the after slot composes in registration order: the bar, then the keycap; the stored order can put the keycap first", () => {
  const sid = "11111111-2222-3333-4444-555555555555";
  store.set(W.TABKEYS_KEY, JSON.stringify({ [sid]: "web" })); store.set("romp:keys", JSON.stringify({ [W.HOTKEY_PREFIX + sid]: "Ctrl+1" }));
  assert.deepEqual(compose("after", { state: "working", ctx: "70%" }, P()).map((c) => classes(c)[0]), ["tab-ctx", "tab-key"]);
  assert.deepEqual(compose("after", { state: "working", ctx: "70%" }, P({ order: ["hotkey", "ctx"] })).map((c) => classes(c)[0]), ["tab-key", "tab-ctx"]);
  assert.deepEqual(compose("after", { state: "working", ctx: "70%" }, P({ order: ["nosuch", "hotkey"] })).map((c) => classes(c)[0]), ["tab-key", "tab-ctx"], "an unknown id in the order is skipped");
  store.delete(W.TABKEYS_KEY); store.delete("romp:keys");
});

test("a contributed widget draws in its slot after the built-ins once switched on (off by default, nothing), and a widget that throws costs nothing", () => {
  W.registerTabWidget({ id: "mark", label: "Demo mark", description: "a synthetic mark", defaultOn: false, slot: "after", render: () => { const e = mkEl("span"); e.className = "tab-mark"; return e as unknown as HTMLElement; } });
  const after = compose("after", { state: "working", ctx: "70%" }, P({ on: { mark: true } })).map((c) => classes(c)[0]);
  assert.equal(after[0], "tab-ctx", "the built-ins first (registration order)");
  assert.equal(after[after.length - 1], "tab-mark", "the contributed widget last, in its slot, with no wrapper of its own");
  assert.ok(!compose("after", { state: "working", ctx: "70%" }, P()).map((c) => classes(c)[0]).includes("tab-mark"), "off by default: not drawn");
  W.registerTabWidget({ id: "boom", label: "Boom", description: "throws", defaultOn: true, slot: "before", render: () => { throw new Error("no"); } });
  assert.deepEqual(compose("before", { state: "working" }, P()).map(classes), [["tab-dot"]], "the throwing widget is skipped, the dot still drawn");
});

test("prefs normalize: junk dropped, every field present; with no stored object the context bar derives from the older tabCtx mode", () => {
  assert.deepEqual(W.tabWidgetPrefs(undefined), { on: {}, order: [], opts: {} });
  assert.deepEqual(W.tabWidgetPrefs(undefined, "never"), { on: { ctx: false }, order: [], opts: {} });
  assert.deepEqual(W.tabWidgetPrefs(undefined, "always"), { on: {}, order: [], opts: { ctx: { show: "always" } } });
  assert.deepEqual(W.tabWidgetPrefs(undefined, "over50"), { on: {}, order: [], opts: {} });
  assert.deepEqual(W.tabWidgetPrefs({ on: { dot: false, ctx: "yes" }, order: ["ctx", 3], opts: { dot: { idle: "grey", n: 1 }, ctx: "x" } }),
                   { on: { dot: false }, order: ["ctx"], opts: { dot: { idle: "grey" } } });
  assert.deepEqual(W.tabWidgetPrefs("junk", "never"), { on: { ctx: false }, order: [], opts: {} }, "a non-object store reads as absent");
});

test("the mirror: the prefs read back as the older tabCtx mode", () => {
  assert.equal(W.tabCtxOfPrefs(P()), "over50");
  assert.equal(W.tabCtxOfPrefs(P({ on: { ctx: false } })), "never");
  assert.equal(W.tabCtxOfPrefs(P({ opts: { ctx: { show: "always" } } })), "always");
  assert.equal(W.tabCtxOfPrefs(P({ on: { ctx: false }, opts: { ctx: { show: "always" } } })), "never", "off wins");
});

test("settings.ts: a store from before the widgets derives them from tabCtx; a store with them writes tabCtx back; a legacy tabCtx patch moves the widget", () => {
  store.set("romp:settings", JSON.stringify({ tabCtx: "never" }));
  let s = S.loadSettings();
  assert.deepEqual(s.tabWidgets, { on: { ctx: false }, order: [], opts: {} });
  assert.equal(s.tabCtx, "never");
  store.set("romp:settings", JSON.stringify({ tabCtx: "never", tabWidgets: { on: { ctx: true }, order: [], opts: { ctx: { show: "always" } } } }));
  s = S.loadSettings();
  assert.equal(s.tabCtx, "always", "the widgets win; tabCtx is their mirror");
  s = S.saveSettings({ tabWidgets: { on: { ctx: false }, order: [], opts: {} } });
  assert.equal(s.tabCtx, "never");
  assert.equal(JSON.parse(store.get("romp:settings")!).tabCtx, "never", "the mirror is written");
  s = S.saveSettings({ tabCtx: "always" });   // an older writer: the widget follows
  assert.deepEqual([s.tabWidgets.on.ctx, s.tabWidgets.opts.ctx.show, s.tabCtx], [true, "always", "always"]);
  assert.deepEqual(S.DEFAULT_SETTINGS.tabWidgets, { on: {}, order: [], opts: {} });
  store.delete("romp:settings");
  assert.deepEqual(S.loadSettings(), S.DEFAULT_SETTINGS);
});

test("the settings row's live rendering is the strip's own render over the demo status", () => {
  const dot = W.renderWidgetDemo(W.tabWidget("dot")!, P()) as unknown as El;
  assert.deepEqual(classes(dot), ["tab-dot"], "the demo is a working session: the gold dot");
  const bar = W.renderWidgetDemo(W.tabWidget("ctx")!, P()) as unknown as El;
  assert.deepEqual(classes(bar), ["tab-ctx"]);
  assert.equal(bar.children[0].style.height, "62%");
  const key = W.renderWidgetDemo(W.tabWidget("hotkey")!, P()) as unknown as El;
  assert.deepEqual(classes(key), ["tab-key"]);
  assert.equal(key.textContent, "⌃⇧1", "the demo keycap, with no store behind it");
});

test("source: the strip and the gear draw from this ONE module; the dot rule has its one site here", () => {
  const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "tab-widgets.ts"), "utf8");
  assert.equal((SRC.match(/tabDotClass\(status\.state\)/g) || []).length, 1, "the dot slot's one site (tab-dot-slot.test.ts's rule)");
  assert.match(SRC, /^export function tabCtxGauge\(ctxStr: string, ctxColor\?: number\[\]\): HTMLElement \{/m, "the gauge builder lives here now (the ctx widget calls it)");
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  assert.match(RENDER, /^import \{ composeTabWidgets, composeTabRing, applyTabBadgeMode, needsYouPhrase, ringSwitch, tabHotkey, miniChord, needsYouWidgetOn \} from "\.\/tab-widgets";/m, "the rings compose from here too (2026-09-14); badge mode via applyTabBadgeMode (the state badge)");
  assert.doesNotMatch(RENDER, /^function tabCtxGauge\(/m, "one builder, not two");
  assert.equal((RENDER.match(/const dotCls = tabDotClass\(st\);/g) || []).length, 0, "render.ts no longer appends the dot itself");
  const GEAR = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
  assert.match(GEAR, /var TW = require\('\.\/tab-widgets\.ts'\);/, "the gear renders the rows' live demos from the same module");
});

test("ONE .tab-key rule in the strip's sheet: this side owns it, so a merge with the tab hot keys pull request's copy cannot leave two identical blocks silently", () => {
  assert.equal((STRIP_CSS.match(/^\.tab-key \{/gm) || []).length, 1);
  assert.match(STRIP_CSS, /^\.tab-key \{ flex: 0 0 auto; font: 600 calc\(0\.82em \/ 0\.92\) ui-monospace, SFMono-Regular, Menlo, monospace; color: var\(--dim\); border: 1px solid var\(--box-border\);/m, "the agreed rule text");
});

// The DIVIDER and the order (the user's additions to T409): the session name's place in the Tab widgets list is a fixed
// row; a widget's slot is its side of it in the stored order, nothing moves until the user drags, and the rows' visual
// order (widgets, the divider, widgets) is the list a drag or an arrow key reorders and stores back whole.
// (the "mark" and "boom" widgets earlier tests registered stay in the registry; the lists below drop them)
const noMark = (ids: string[]) => ids.filter((x) => x !== "mark" && x !== "boom");
test("widgetSlot: the registered slot until the order names both the widget and the divider; then the widget's side of it", () => {
  const dot = W.tabWidget("dot")!, ctx = W.tabWidget("ctx")!, key = W.tabWidget("hotkey")!;
  assert.deepEqual([W.widgetSlot(P(), dot), W.widgetSlot(P(), ctx)], ["before", "after"], "no order: the registered slots");
  assert.deepEqual([W.widgetSlot(P({ order: ["ctx", "dot"] }), dot), W.widgetSlot(P({ order: ["ctx", "dot"] }), ctx)], ["before", "after"], "an order without the divider changes no slot");
  const moved = P({ order: ["ctx", W.NAME_DIVIDER, "dot", "hotkey"] });
  assert.deepEqual([W.widgetSlot(moved, ctx), W.widgetSlot(moved, dot), W.widgetSlot(moved, key)], ["before", "after", "after"], "dragged across: the context bar before the name, the dot after it");
  assert.equal(W.widgetSlot(P({ order: [W.NAME_DIVIDER, "ctx"] }), dot), "before", "a widget the order does not name keeps its registered slot");
  assert.deepEqual(noMark(W.orderedWidgets(moved, "before").map((w) => w.id)), ["ctx"]);
  assert.deepEqual(noMark(W.orderedWidgets(moved, "after").map((w) => w.id)), ["dot", "hotkey"]);
});

test("tabListOrder: the rows' visual order, the divider between the sides; a drag's result stored back reproduces itself", () => {
  assert.deepEqual(noMark(W.tabListOrder(P())), ["dot", W.NAME_DIVIDER, "ctx", "hotkey"], "registration order until the user drags");
  assert.deepEqual(noMark(W.tabListOrder(P({ order: ["hotkey"] }))), ["dot", W.NAME_DIVIDER, "hotkey", "ctx"], "a partial order without the divider reorders within the sides");
  const dragged = P({ order: ["ctx", W.NAME_DIVIDER, "dot", "hotkey"] });
  assert.deepEqual(noMark(W.tabListOrder(dragged)), ["ctx", W.NAME_DIVIDER, "dot", "hotkey"]);
  assert.deepEqual(W.tabListOrder(P({ order: W.tabListOrder(dragged) })), W.tabListOrder(dragged), "storing the list back is a fixed point");
});

test("the strip composes each slot from the widget's side of the divider, so a drag across it moves the widget to the other side of the name", () => {
  const moved = P({ order: ["ctx", W.NAME_DIVIDER, "dot", "hotkey"], opts: { ctx: { show: "always" } } });
  assert.deepEqual(compose("before", { state: "working", ctx: "40%" }, moved).map(classes), [["tab-ctx"]], "the context bar before the name");
  assert.deepEqual(compose("after", { state: "working", ctx: "40%" }, moved).map(classes), [["tab-dot"]], "the dot after it (no hot key is assigned to this sid, so the keycap renders nothing)");
  assert.deepEqual(compose("after", { state: "working", ctx: "40%" }, moved, W.DEMO_SID).map(classes), [["tab-dot"], ["tab-key"]], "the demo sid carries a key: the keycap follows the dot");
});

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PREFS = require("./widget-prefs") as typeof import("./widget-prefs");
test("moveId: the id out and back in at the index into the rest; unknown ids and bad indexes change nothing", () => {
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "c", 0), ["c", "a", "b"]);
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "a", 2), ["b", "c", "a"]);
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "b", 1), ["a", "b", "c"], "to its own place: unchanged");
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "a", 99), ["b", "c", "a"], "past the end: the end");
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "zz", 0), ["a", "b", "c"]);
  assert.deepEqual(PREFS.moveId(["a", "b", "c"], "a", NaN), ["a", "b", "c"]);
});

// A malformed stored order is rewritten clean at rest (review round one of the status line's widgets): duplicates keep
// their first place, ids the registry does not know go, the divider's id stays; the settings' save normalizes the same way
test("tabWidgetPrefs sanitizes the order: duplicates once, unknown ids gone, the divider kept", () => {
  assert.deepEqual(W.tabWidgetPrefs({ order: ["ctx", "zz", "ctx", W.NAME_DIVIDER, "dot", "dot"] }).order, ["ctx", W.NAME_DIVIDER, "dot"]);
  assert.deepEqual(W.tabWidgetPrefs({ order: [] }).order, []);
  store.clear();
  store.set("romp:settings", JSON.stringify({ compact: true, tabWidgets: { on: {}, order: ["hotkey", "hotkey", "gone"], opts: {} } }));
  const saved = S.saveSettings({ compact: false });
  assert.deepEqual(saved.tabWidgets.order, ["hotkey"], "the next save rewrites the store clean");
  assert.deepEqual(JSON.parse(store.get("romp:settings")!).tabWidgets.order, ["hotkey"]);
  store.clear();
});

// THE RING SLOT (the rings-as-widgets change, 2026-09-14): a widget of slot "ring" carries the CLASS the tab wears and a
// PREDICATE; the strip removes every registered ring class, then adds the first switched-on ring's whose predicate holds,
// so one ring paints at a time and the precedence is the registration order. Rings have no position: neither side of the
// divider, never in the stored order, never in the rows' drag list. Executed on synthetic rings registered here (the
// built-in rings register in a later step); the "mark" and "boom" widgets earlier tests registered stay in the registry.
const ring = (id: string, on: (s: WidgetStatus) => boolean, defaultOn = true) =>
  ({ id, label: id, description: "a synthetic ring", defaultOn, slot: "ring" as const, ring: "r-" + id, on: (_sid: string, s: WidgetStatus) => on(s), render: () => null });
const RINGS_HERE = ["rr", "ry", "ra"];
const noRings = (ids: string[]) => noMark(ids).filter((x) => !RINGS_HERE.includes(x));
const hereRings = () => W.ringWidgets().filter((w) => RINGS_HERE.includes(w.id));
// the registry's own rings (registered at import) switched off, so the synthetic rings alone decide in these tests
const BUILTIN_OFF: Record<string, boolean> = Object.fromEntries(W.ringWidgets().map((w) => [w.id, false]));
const PR = (p: Partial<TabWidgetPrefs> = {}): TabWidgetPrefs => P({ ...p, on: { ...BUILTIN_OFF, ...(p.on || {}) } });
const tabOf = (cls: string) => { const t = mkEl("div"); t.className = cls; (t as any).classList = {
  add: (c: string) => { if (!classes(t).includes(c)) t.className = (t.className + " " + c).trim(); },
  remove: (c: string) => { t.className = classes(t).filter((x) => x !== c).join(" "); } }; return t; };

test("ring: a ring widget registers with its class and predicate; ringWidgets lists rings alone in registration order; titleWidgets never lists one", () => {
  W.registerTabWidget(ring("rr", (s) => s.state === "needsInput"));
  W.registerTabWidget(ring("ry", (s) => s.needsYou === true && s.state !== "closed"));
  W.registerTabWidget(ring("ra", (s) => s.state === "retrying"));
  assert.deepEqual(hereRings().map((w) => [w.id, w.ring]), [["rr", "r-rr"], ["ry", "r-ry"], ["ra", "r-ra"]]);
  assert.ok(W.titleWidgets().every((w) => w.slot !== "ring"), "the title's widgets exclude the rings");
  assert.deepEqual(noMark(W.titleWidgets().map((w) => w.id)), ["dot", "ctx", "hotkey"]);
  assert.ok(RINGS_HERE.every((id) => W.tabWidgets().some((w) => w.id === id)), "…while tabWidgets lists every registration");
});

test("ring: composeTabRing paints ONE class, the first switched-on ring whose predicate holds; every ring class comes off first", () => {
  const status: WidgetStatus = { state: "needsInput", needsYou: true };
  const tab = tabOf("tab r-ra stale-other");
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", status, PR()), "r-rr", "the first ring wins with everything on");
  assert.deepEqual(classes(tab), ["tab", "stale-other", "r-rr"], "the stale ring class is gone, an unrelated class stays, one ring on");
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", status, PR({ on: { rr: false } })), "r-ry", "the red switch off: the next ring whose predicate holds");
  assert.deepEqual(classes(tab), ["tab", "stale-other", "r-ry"]);
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", status, PR({ on: { rr: false, ry: false } })), null, "…and with that off too, nothing (the amber's predicate is false here)");
  assert.deepEqual(classes(tab), ["tab", "stale-other"]);
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "retrying", needsYou: true }, PR()), "r-ry", "magenta over amber: registration order is the precedence");
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "retrying" }, PR()), "r-ra");
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "closed", needsYou: true }, PR()), null, "a closed tab with a stale card wears nothing");
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "working", needsYou: false }, PR()), null);
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "working", needsYou: null }, PR()), null);
  assert.equal(W.tabRing("s", { state: "retrying" }, PR({ on: { ra: false } })), null, "tabRing: the switched-off ring is not the winner");
  assert.equal(W.tabRing("s", { state: "retrying" }, PR())!.id, "ra");
  W.registerTabWidget({ ...ring("rboom", () => { throw new Error("no"); }), ring: "r-boom" });
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "retrying" }, PR()), "r-ra", "a throwing predicate reads false, the next ring still paints");
  W.registerTabWidget(ring("rboom", () => false, false));   // quiet again for the tests below
});

test("ring: rings have no position — widgetSlot says ring whatever the order, the before and after lists and tabListOrder never carry one, and a stored order naming one is sanitized", () => {
  const rr = W.tabWidget("rr")!;
  assert.equal(W.widgetSlot(P(), rr), "ring");
  assert.equal(W.widgetSlot(P({ order: ["rr", W.NAME_DIVIDER, "dot"] }), rr), "ring", "even a stored order that puts it before the divider");
  const stored = P({ order: ["rr", "ctx", W.NAME_DIVIDER, "ry", "dot", "ra"] });
  assert.ok(!W.orderedWidgets(stored, "before").some((w) => w.slot === "ring") && !W.orderedWidgets(stored, "after").some((w) => w.slot === "ring"));
  assert.deepEqual(noRings(W.tabListOrder(stored)), ["ctx", W.NAME_DIVIDER, "dot", "hotkey"]);
  assert.ok(!W.tabListOrder(stored).some((id) => RINGS_HERE.includes(id)), "the drag list never names a ring");
  assert.deepEqual(W.orderedWidgets(stored, "ring").map((w) => w.id).filter((id) => RINGS_HERE.includes(id)), RINGS_HERE, "the ring list is the registration order, not the stored one");
  assert.deepEqual(W.tabWidgetPrefs({ order: ["rr", "ctx", W.NAME_DIVIDER, "ry", "dot"] }).order, ["ctx", W.NAME_DIVIDER, "dot"], "a stored order never keeps a ring id");
  assert.deepEqual(compose("before", { state: "needsInput" }, P()).map(classes), [["tab-dot", "none"]], "composing a title slot appends no ring node");
});

test("ring: ringDemoClass lights on the ring's own demo status and is null when switched off; ringSwitch reads the switches by id", () => {
  W.registerTabWidget({ ...ring("ry", (s) => s.needsYou === true && s.state !== "closed"), demo: { state: "working", needsYou: true } });
  assert.equal(W.ringDemoClass(W.tabWidget("ry")!, PR()), "r-ry");
  assert.equal(W.ringDemoClass(W.tabWidget("ry")!, PR({ on: { ry: false } })), null, "switched off: a plain demo tab");
  assert.equal(W.ringDemoClass(W.tabWidget("rr")!, PR()), null, "the default demo status (a working session) lights no prompt ring");
  assert.equal(W.ringDemoClass(W.tabWidget("dot")!, PR()), null, "not a ring: null");
  const sw = W.ringSwitch(P({ on: { ry: false } }));
  assert.deepEqual([sw("rr"), sw("ry"), sw("ra"), sw("nosuch")], [true, false, true, true], "an unknown id reads on, so a pure caller's own order decides");
  for (const id of [...RINGS_HERE, "rboom"]) W.registerTabWidget({ ...ring(id, () => false, false), slot: "after" });   // out of the ring list for any later test
  assert.deepEqual(hereRings(), []);
});

// THE BUILT-IN RINGS (2026-09-14): registered after the hot key in PRECEDENCE order (tab-state.ts RING_ORDER: red over
// magenta over amber), each rendering nothing and naming its class; over every synthetic status times every switch set,
// the registry's composition (composeTabRing) equals the pure twin the folded header's pip reads (tabRingId under
// ringSwitch), so the strip and the pip cannot drift. Runs after the synthetic rings above left the ring list.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const TS = require("./tab-state") as typeof import("./tab-state");
test("the built-in rings: registration order IS RING_ORDER; a ring renders no node; each demo lights its own ring; over every status times every switch set the composition equals tabRingId", () => {
  assert.deepEqual(W.ringWidgets().map((w) => w.id), TS.RING_ORDER, "the precedence pinned in tab-state.ts is the registration order");
  for (const w of W.ringWidgets()) {
    assert.equal(W.renderWidgetDemo(w, P()), null, w.id + " renders no node");
    assert.equal(W.ringDemoClass(w, P()), w.ring, w.id + "'s demo status lights its own ring");
    assert.equal(W.ringDemoClass(w, P({ on: { [w.id]: false } })), null, w.id + " switched off: a plain demo tab");
    assert.equal(w.options, undefined, "no options");
  }
  assert.deepEqual(W.ringWidgets().map((w) => w.demo), [{ state: "awaiting" }, { state: "working", needsYou: true, needsYouCount: 2 }, { state: "retrying" }]);   // the Needs-you demo carries a count (2) so the gear preview draws the numbered dot and the :not(:empty) rules live (PR 2065 review)
  // the popover descriptions read by STATE, not SHAPE (PR 2065 review): the same rows drive both the badge and the ring,
  // so "a dashed ring" was wrong in badge mode. No shape word ("ring", "dashed") survives in a description.
  for (const w of W.ringWidgets()) {
    assert.doesNotMatch(w.description || "", /\bdashed\b|\brings?\b/i, w.id + " describes the STATE, not the shape: " + JSON.stringify(w.description));
  }
  const statuses: WidgetStatus[] = [
    { state: "ready" }, { state: "ready", needsYou: true }, { state: "idle", needsYou: true }, { state: "working" }, { state: "working", needsYou: true },
    { state: "awaitingBg", needsYou: true }, { state: "compacting", needsYou: true }, { state: "needsInput" }, { state: "needsInput", needsYou: true },
    { state: "awaiting", needsYou: true }, { state: "blocked" }, { state: "blocked", needsYou: true }, { state: "blocked", apiTooLong: true },
    { state: "blocked", apiSpendLimit: true, needsYou: true }, { state: "blocked", apiModelLimit: true }, { state: "blocked", apiAuthErr: true, needsYou: true },
    { state: "blocked", apiRefusal: true, needsYou: true }, { state: "retrying" }, { state: "retrying", needsYou: true }, { state: "closed" }, { state: "closed", needsYou: true },
    { state: "ready", needsYou: false }, { state: "ready", needsYou: null }, { state: "opening" }, {},
  ];
  let painted = 0;
  for (let mask = 0; mask < 8; mask++) {
    const on = { "ring-needs-you": !!(mask & 1), "ring-waiting-on-you": !!(mask & 2), "ring-retrying": !!(mask & 4) };
    const prefs = P({ on });
    for (const st of statuses) {
      const tab = tabOf("tab ring-needs-you ring-retrying");   // stale ring classes on the element, as after a state change
      const got = W.composeTabRing(tab as unknown as HTMLElement, "s", st, prefs);
      const want = TS.tabRingId(st, W.ringSwitch(prefs));
      assert.equal(got, want, JSON.stringify(st) + " with " + JSON.stringify(on));
      assert.deepEqual(classes(tab).filter((c) => c.startsWith("ring-")), got ? [got] : [], "one ring class at most, the stale ones gone");
      if (got) painted++;
    }
  }
  assert.ok(painted > 40, "the grid exercised rings, not only nothings: " + painted);
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "needsInput", needsYou: true }, P()), "ring-needs-you", "red over magenta");
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "retrying", needsYou: true }, P()), "ring-waiting-on-you", "magenta over amber");
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "needsInput", needsYou: true }, P({ on: { "ring-needs-you": false } })), "ring-waiting-on-you", "the red switched off hands the tab to the magenta");
});

// ── the state badge (plans/tab-state-badge.md): applyTabBadgeMode, run only in badge mode, swaps the Needs-you ring for a
//    numbered magenta top-right dot, moves retrying to the left status dot (amber), leaves Blocked's red ring alone, and is
//    a no-op when neither the Needs-you nor the retrying predicate holds. The count and the dot are read from the DOM the
//    function builds, never inferred from source. Ring-mode byte-identity (badge off → the ring, no dot) is render.ts's
//    gate, pinned by the served lab; here the function's own behaviour over the status matrix is the subject.
const badgeTab = (stale = "") => {   // a strip tab as render hands it to applyTabBadgeMode: the ring composeTabRing painted, and the "before" .tab-dot slot already inside
  const t = mkEl("div"); t.className = ("tab " + stale).trim();
  const dot = mkEl("span"); dot.className = "tab-dot none"; t.appendChild(dot);
  return t;
};
const leftDot = (t: El) => t.children.find((c) => classes(c).includes("tab-dot"))!;
const badgeOf = (t: El) => t.children.find((c) => classes(c).includes("tab-badge")) || null;

test("state badge: the Needs-you dot is a black numbered magenta dot, per state at 1, 3 and 12, singular at 1, '99+' past 99, a bare dot when the count is absent", () => {
  for (const [n, text, title] of [[1, "1", "1 thing needs you"], [3, "3", "3 things need you"], [12, "12", "12 things need you"], [99, "99", "99 things need you"], [100, "99+", "100 things need you"]] as const) {
    const t = badgeTab("ring-waiting-on-you");   // the magenta ring the render painted; badge mode replaces it with the dot
    const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "working", needsYou: true, needsYouCount: n }, P()) as unknown as El | null;
    assert.ok(dot, n + ": a Needs-you dot is drawn");
    assert.deepEqual(classes(dot!), ["tab-badge", "badge-needs"], n + ": the dot's classes");
    assert.equal(dot!.textContent, text, n + ": the black number");
    assert.equal(dot!.attrs["role"], "img", n + ": the dot is an image to a screen reader (not a bare digit)");
    assert.equal(dot!.attrs["aria-label"], title, n + ": the count phrase is the aria-label (the native title is inert under pointer-events:none)");
    assert.equal(badgeOf(t)!.textContent, text, n + ": the one dot lives on the tab");
    assert.deepEqual(classes(t).filter((c) => c.startsWith("ring-")), [], n + ": the run-state ring gave way to the dot");
    assert.deepEqual(classes(leftDot(t)), ["tab-dot", "none"], n + ": the left status dot is untouched (Needs you rides the run state, it is not one)");
  }
  for (const st of [{ state: "working", needsYou: true }, { state: "working", needsYou: true, needsYouCount: 0 }, { state: "working", needsYou: true, needsYouCount: null }] as WidgetStatus[]) {
    const t = badgeTab(); const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", st, P()) as unknown as El | null;
    assert.ok(dot, JSON.stringify(st) + ": still a dot");
    assert.equal(dot!.textContent, "", JSON.stringify(st) + ": no number, a bare dot (an older kernel, or nothing pending)");
    assert.equal(dot!.attrs["aria-label"], "needs you", JSON.stringify(st) + ": the plain aria-label");
  }
});

test("state badge: retrying moves to the left status dot (amber), no top-right dot; Needs you rides retrying, so both show at once", () => {
  const t = badgeTab("ring-retrying");
  const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "retrying" }, P());
  assert.equal(dot, null, "retrying alone: no Needs-you dot");
  assert.equal(badgeOf(t), null, "…and none on the tab");
  assert.deepEqual(classes(leftDot(t)), ["tab-dot", "retrying"], "the left dot goes amber");
  assert.equal(leftDot(t).title, "retrying an API error on its own", "…with its hover");
  assert.deepEqual(classes(t).filter((c) => c.startsWith("ring-")), [], "the amber ring gave way");
  const t2 = badgeTab("ring-retrying ring-waiting-on-you");
  const dot2 = W.applyTabBadgeMode(t2 as unknown as HTMLElement, "s", { state: "retrying", needsYou: true, needsYouCount: 2 }, P()) as unknown as El | null;
  assert.ok(dot2, "both: the Needs-you dot is drawn");
  assert.equal(dot2!.textContent, "2", "…with its count");
  assert.deepEqual(classes(leftDot(t2)), ["tab-dot", "retrying"], "and the left dot is still amber");
  assert.deepEqual(classes(t2).filter((c) => c.startsWith("ring-")), [], "both run-state rings gave way");
});

test("state badge: the close glyph outranks the count pill (z 4 > z 3) so a wide '99+' never blocks the x (low, the manager 2026-09-22)", () => {
  assert.match(STRIP_CSS, /\.tab-badge \{[^}]*z-index: 3;/, "the badge sits at z-index 3");
  assert.match(STRIP_CSS, /\.tab:hover \.tab-close, \.tab\.active \.tab-close \{ position: relative; z-index: 4; \}/, "the close glyph rises above the badge on hover and active, so its click target stays clickable over the pill");
});

test("state badge: a dense-chrome tab shrinks the count pill and tucks it into the corner, its INTENDED smaller footprint pinned by rule text (low, the second contributor PR 2017)", () => {
  // no served-lab pixel ink measure (RULED, the lean lane stands, the PR 2023 post-merge review): the smaller, corner-tucked
  // dense pill is the INTENDED effect, pinned by the rule's text so a re-cut cannot silently drop it; whether that
  // reduces the hover-lifted close's overpaint is not asserted as a measured fact here. dense-chrome-layout.test.ts
  // covers the dense tab box the pill sits in.
  assert.match(STRIP_CSS, /body\.dense-chrome \.tab-badge \{ top: 1px; right: 1px; \}/, "the dense badge sits tucked into the very corner (1px inset, restored 2026-09-24 for PR 2023's measured reason: the hover-lifted close glyph overpaints less of the digits)");
  assert.match(STRIP_CSS, /body\.dense-chrome \.tab-badge:not\(:empty\) \{ min-width: 12px; height: 12px; border-radius: 6px; \}/, "the dense pill is a smaller box (not a smaller digit: the dense block carries no sub-10px font-size), tucked into the corner");
});

test("state badge: with the Status dot widget off there is no slot, so retrying KEEPS its amber ring rather than vanishing; the re-ink toggles the slot's class, never overwriting it", () => {
  // no ".tab-dot" child (the dot widget is switched off): the amber ring has nowhere to move, so it stays
  const noSlot = mkEl("div"); noSlot.className = "tab ring-retrying";
  const r = W.applyTabBadgeMode(noSlot as unknown as HTMLElement, "s", { state: "retrying" }, P());
  assert.equal(r, null, "no Needs-you dot");
  assert.deepEqual(classes(noSlot).filter((c) => c.startsWith("ring-")), ["ring-retrying"], "the amber ring is kept: badge mode does not drop it for nothing when there is no dot slot");
  assert.equal(badgeOf(noSlot), null, "and no dot");
  // the re-ink toggles the slot's class rather than overwriting className: an option class the dot carries survives
  const t = mkEl("div"); t.className = "tab ring-retrying";
  const slot = mkEl("span"); slot.className = "tab-dot none extra-opt"; t.appendChild(slot);
  W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "retrying" }, P());
  assert.deepEqual(classes(leftDot(t)), ["tab-dot", "extra-opt", "retrying"], "the slot keeps its other classes: none removed, retrying added, extra-opt untouched");
  assert.deepEqual(classes(t).filter((c) => c.startsWith("ring-")), [], "with a slot, the ring moved to the dot");
});

test("state badge: the amber left dot beats the 'grey dot when idle' option for both retrying and flagless Blocked, composed through the REAL dot widget (none AND idle come off before retrying)", () => {
  // both retrying and a flagless Blocked read as tab-retrying, and tabDotClass gives them `tab-dot none`, which the dot
  // widget's grey option renders as `tab-dot idle`; the idle rule follows the retrying rule at equal specificity, so a
  // leftover `idle` would dim the amber. applyTabBadgeMode must drop BOTH before adding retrying (the second contributor, PR 2017).
  for (const st of [{ state: "retrying" }, { state: "blocked" }] as WidgetStatus[]) {
    const t = mkEl("div"); t.className = "tab ring-retrying";
    W.composeTabWidgets(t as unknown as HTMLElement, "before", "s", st, P({ opts: { dot: { idle: "grey" } } }));   // the real dot widget, grey option → the slot starts as `tab-dot idle`
    // RING mode is byte-identical under the grey-idle option: applyTabBadgeMode never runs, so the slot stays the quiet
    // grey idle dot titled "idle" (not the amber, not "retrying"), exactly as any other hidden-slot state under the option.
    assert.deepEqual(classes(leftDot(t)), ["tab-dot", "idle"], JSON.stringify(st) + ": under the grey option a none-state slot renders idle");
    assert.equal(leftDot(t).title, "idle", JSON.stringify(st) + ": ring mode leaves the grey idle dot's title, no amber");
    W.applyTabBadgeMode(t as unknown as HTMLElement, "s", st, P({ opts: { dot: { idle: "grey" } } }));
    assert.deepEqual(classes(leftDot(t)), ["tab-dot", "retrying"], JSON.stringify(st) + ": none and idle both come off, so the amber is not painted at idle's dim opacity");
    // BADGE mode: retrying is titled IFF visibly dotted: here it is both (the amber dot carries its hover title).
    assert.equal(leftDot(t).title, "retrying an API error on its own", JSON.stringify(st) + ": the amber dot is titled (titled iff visibly dotted, badge mode)");
  }
});

test("state badge: the badge call runs AFTER both sides' widgets compose (in appendTabAfterWidgets), so a dot dragged past the name is found (the second contributor, PR 2017)", () => {
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  const after = RENDER.slice(RENDER.indexOf("function appendTabAfterWidgets"), RENDER.indexOf("\nfunction ", RENDER.indexOf("function appendTabAfterWidgets") + 1));
  assert.match(after, /composeTabWidgets\(tab, "after"[\s\S]*if \(settings\.tabStateBadge\) applyTabBadgeMode\(tab,/, "appendTabAfterWidgets calls the badge AFTER composing the after-side widgets, so the slot exists wherever the dot sits");
  const applyStatus = RENDER.slice(RENDER.indexOf("function applyTabStatus"), RENDER.indexOf("function appendTabAfterWidgets"));
  assert.doesNotMatch(applyStatus, /applyTabBadgeMode/, "applyTabStatus no longer calls the badge: an after-side dot's slot is not composed there yet");
});

test("state badge: Blocked is untouched, its red ring and the left dot stay, no top-right dot; a blocked-and-needs-you tab keeps the red ring AND wears the dot", () => {
  for (const st of [{ state: "awaiting" }, { state: "blocked", apiTooLong: true }, { state: "blocked", apiAuthErr: true }] as WidgetStatus[]) {
    const t = badgeTab("ring-needs-you");   // the red ring composeTabRing painted
    const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", st, P());
    assert.equal(dot, null, JSON.stringify(st) + ": no top-right dot for Blocked");
    assert.equal(badgeOf(t), null, JSON.stringify(st) + ": none on the tab");
    assert.deepEqual(classes(t).filter((c) => c.startsWith("ring-")), ["ring-needs-you"], JSON.stringify(st) + ": the red ring stays (Blocked keeps its ring in both modes)");
    assert.deepEqual(classes(leftDot(t)), ["tab-dot", "none"], JSON.stringify(st) + ": the left dot is untouched");
  }
  const t = badgeTab("ring-needs-you");
  const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "awaiting", needsYou: true, needsYouCount: 4 }, P()) as unknown as El | null;
  assert.ok(dot, "the Needs-you dot rides the red ring");
  assert.equal(dot!.textContent, "4", "…carrying its count");
  assert.deepEqual(classes(t).filter((c) => c.startsWith("ring-")), ["ring-needs-you"], "the red ring is kept, never removed");
});

test("state badge: a no-op when nothing needs you and the tab is not retrying; idempotent (one dot on a reused tab, its count refreshed)", () => {
  for (const st of [{ state: "working" }, { state: "idle" }, { state: "ready", needsYou: false }, { state: "closed", needsYou: true }] as WidgetStatus[]) {
    const t = badgeTab(); const dot = W.applyTabBadgeMode(t as unknown as HTMLElement, "s", st, P());
    assert.equal(dot, null, JSON.stringify(st) + ": no dot");
    assert.equal(badgeOf(t), null, JSON.stringify(st) + ": nothing added");
    assert.deepEqual(classes(leftDot(t)), ["tab-dot", "none"], JSON.stringify(st) + ": the left dot is untouched");
  }
  const t = badgeTab();
  W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "working", needsYou: true, needsYouCount: 3 }, P());
  W.applyTabBadgeMode(t as unknown as HTMLElement, "s", { state: "working", needsYou: true, needsYouCount: 7 }, P());
  const badges = t.children.filter((c) => classes(c).includes("tab-badge"));
  assert.equal(badges.length, 1, "one dot after two paints");
  assert.equal(badges[0].textContent, "7", "the count refreshed on the reused tab");
});

test("needsYouPhrase: the ONE Needs-you phrase for the badge aria-label and a cold tab's title", () => {
  assert.equal(W.needsYouPhrase(3), "3 things need you");
  assert.equal(W.needsYouPhrase(1), "1 thing needs you", "the singular");
  assert.equal(W.needsYouPhrase(0), "needs you", "no count (an older kernel with the needsYou bit): the bare phrase");
  assert.equal(W.needsYouPhrase(150), "150 things need you", "never capped, so the phone leg and the tooltip agree with the desktop label above 99");
});

// plan test 5, EXECUTED (PR 2065 review item 4): the source pin in settings-previews.test.ts proves the gear's ring-demo
// calls the badge branch, but cannot see the ORDER it depends on: the ring class is added BEFORE applyTabBadgeMode, so
// the badge pass runs last and the ring it dropped is not re-added. Swapping those two lines leaves the source pin green.
// Here the demo function is sliced from gear.js and EXECUTED over the real tab-widgets module and the tiny DOM above, so
// the swap reds: applyTabBadgeMode would drop the Needs-you ring, then the ringDemoClass line would put it back.
test("plan test 5 executed: the gear ring demo drops the Needs-you ring for the badge dot, and the swap of the ring-class and badge-call lines reds it", () => {
  const gear = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
  const ringSection = gear.slice(gear.indexOf("var ringSection = widgetSection({"), gear.indexOf("function statusPrefs(s)"));
  const m = ringSection.match(/demo: function \(w, prefs\) \{([\s\S]*?)\n\s*\},/);
  assert.ok(m, "the ring-section demo function is where the pin expects it");
  const body = m![1];
  // the swap the review names: the ringDemoClass line must come BEFORE the applyTabBadgeMode line in the CODE (strip the
  // comment first, which mentions applyTabBadgeMode in prose)
  const code = body.replace(/^[ \t]*\/\/.*$/gm, "");
  assert.ok(code.indexOf("ringDemoClass") < code.indexOf("applyTabBadgeMode"), "the ring class is added before the badge pass, so the badge pass runs last");
  store.set("romp:settings", JSON.stringify({ tabStateBadge: true }));
  const demo = new Function("w", "prefs", "TW", "load", "demoTab", "demoLabel", body + "\n") as
    (w: any, prefs: any, TW: any, load: any, demoTab: () => El, demoLabel: () => El) => El;
  const run = (src: string) => {
    const fn = new Function("w", "prefs", "TW", "load", "demoTab", "demoLabel", src + "\n") as typeof demo;
    return fn(W.tabWidget("ring-waiting-on-you"), P(), W, S.loadSettings, () => mkEl("span"), () => mkEl("span"));
  };
  const tab = run(body);
  assert.ok(!classes(tab).includes("ring-waiting-on-you"), "badge on: the Needs-you ring class is gone (dropped for the top-right dot)");
  assert.ok(tab.children.some((c) => classes(c).includes("tab-badge")), "…and the top-right badge dot is on the demo");
  // the swap: run applyTabBadgeMode BEFORE the ring class is added, so the ring is put back and the class returns (the bug)
  const swapped = body.replace(/(\s*)(var cls = TW\.ringDemoClass\(w, prefs\); if \(cls\) tab\.classList\.add\(cls\);)(\s*)(if \(badge\) TW\.applyTabBadgeMode\(tab, sid, st, prefs\);)/, "$1$4$3$2");
  assert.notEqual(swapped, body, "the swap rewrite matched the two lines");
  const swappedTab = run(swapped);
  assert.ok(classes(swappedTab).includes("ring-waiting-on-you"), "the swap re-adds the ring class after the badge pass: the demo wrongly keeps the ring (this is what the pin catches)");
});

// PR 2080 review LOW 7: the DRAGGED order (a stored order with the status dot AFTER the name) is the case the demo's
// both-sides composition exists for. Run the sliced demo against the STRIP's own composition (compose before, the name,
// compose after, the ring class, applyTabBadgeMode) for that order, every ring row: they must AGREE. On the base (the
// demo composing only the before slot) the dragged dot is missing from the demo, so applyTabBadgeMode cannot re-ink it
// and the demo keeps the ring while the strip shows the dot: the two disagree.
test("plan test 5 (dragged order): the gear demo matches the strip's composition with the dot after the name, all three ring rows", () => {
  const gear = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
  const ringSection = gear.slice(gear.indexOf("var ringSection = widgetSection({"), gear.indexOf("function statusPrefs(s)"));
  const body = ringSection.match(/demo: function \(w, prefs\) \{([\s\S]*?)\n\s*\},/)![1];
  store.set("romp:settings", JSON.stringify({ tabStateBadge: true }));
  const demoFn = new Function("w", "prefs", "TW", "load", "demoTab", "demoLabel", body + "\n") as
    (w: any, prefs: any, TW: any, load: any, demoTab: () => El, demoLabel: () => El) => El;
  const dragged = P({ order: [W.NAME_DIVIDER, "dot", "ctx", "hotkey"] });   // every widget AFTER the name (the dot dragged past it)
  const strip = (w: any) => {   // the strip's own composition, as render.ts assembles it
    const tab = mkEl("span"); const st = w.demo || W.DEMO_STATUS, sid = w.demoSid || W.DEMO_SID;
    W.composeTabWidgets(tab as unknown as HTMLElement, "before", sid, st, dragged);
    tab.appendChild(mkEl("span"));
    W.composeTabWidgets(tab as unknown as HTMLElement, "after", sid, st, dragged);
    const cls = W.ringDemoClass(w, dragged); if (cls) tab.classList.add(cls);
    W.applyTabBadgeMode(tab as unknown as HTMLElement, sid, st, dragged);
    return tab;
  };
  const sig = (t: El) => classes(t).filter((c) => c.startsWith("ring-")).sort().join(",") + " :: "
    + t.children.map((c) => classes(c).sort().join(".")).join(" | ");
  for (const id of ["ring-needs-you", "ring-waiting-on-you", "ring-retrying"]) {
    const w = W.tabWidget(id)!;
    const demoTab = demoFn(w, dragged, W, S.loadSettings, () => mkEl("span"), () => mkEl("span"));
    assert.equal(sig(demoTab), sig(strip(w)), id + ": the demo's composition matches the strip's for the dragged order");
  }
});
