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

type El = { tag: string; className: string; textContent: string; title: string; attrs: Record<string, string>; children: El[]; style: Record<string, string>;
            appendChild: (c: El) => El; setAttribute: (k: string, v: string) => void };
function mkEl(tag: string): El {
  const e: El = { tag, className: "", textContent: "", title: "", attrs: {}, children: [], style: {},
    appendChild: (c) => { e.children.push(c); return c; }, setAttribute: (k, v) => { e.attrs[k] = v; } };
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
  assert.match(RENDER, /^import \{ composeTabWidgets, composeTabRing, ringSwitch, tabHotkey, miniChord \} from "\.\/tab-widgets";/m, "the rings compose from here too (2026-09-14)");
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
  assert.equal(W.composeTabRing(tab as unknown as HTMLElement, "s", { state: "retrying", needsYou: true }, PR()), "r-ry", "yellow over amber: registration order is the precedence");
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
// yellow over amber), each rendering nothing and naming its class; over every synthetic status times every switch set,
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
  assert.deepEqual(W.ringWidgets().map((w) => w.demo), [{ state: "awaiting" }, { state: "working", needsYou: true }, { state: "retrying" }]);
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
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "needsInput", needsYou: true }, P()), "ring-needs-you", "red over yellow");
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "retrying", needsYou: true }, P()), "ring-waiting-on-you", "yellow over amber");
  assert.equal(W.composeTabRing(tabOf("tab") as unknown as HTMLElement, "s", { state: "needsInput", needsYou: true }, P({ on: { "ring-needs-you": false } })), "ring-waiting-on-you", "the red switched off hands the tab to the yellow");
});
