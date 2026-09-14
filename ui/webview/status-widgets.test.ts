// The status-line widget registry (T409, the user 2026-09-13): registration order is the default composition order,
// the stored prefs decide which widgets the line carries and with which options, the two keys the widgets replaced
// (showBranch, showSessionBadge) are their MIRRORS, written at every save and never read since the one-shot migration, and the line and the settings row draw a widget through
// the same render. Executed on a tiny DOM (document.createElement stubbed), so a widget's DOM is read, never inferred
// from source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import type { StatusRecord, StatusWidgetPrefs } from "./status-widgets";

type El = { tag: string; className: string; textContent: string; title: string; innerHTML: string; attrs: Record<string, string>; dataset: Record<string, string>;
            children: El[]; style: Record<string, string>; classList: { add: (c: string) => void; remove: (c: string) => void; contains: (c: string) => boolean; toggle: (c: string, on?: boolean) => void };
            appendChild: (c: El) => El; setAttribute: (k: string, v: string) => void; getAttribute: (k: string) => string | null; removeAttribute: (k: string) => void;
            querySelectorAll: (sel: string) => El[] };
function mkEl(tag: string): El {
  const e: El = { tag, className: "", textContent: "", title: "", innerHTML: "", attrs: {}, dataset: {}, children: [], style: {},
    classList: { add: (c) => { if (!e.classList.contains(c)) e.className = (e.className + " " + c).trim(); }, remove: (c) => { e.className = e.className.split(/\s+/).filter((x) => x && x !== c).join(" "); }, contains: (c) => e.className.split(/\s+/).includes(c),
                 toggle: (c, on) => { const has = e.classList.contains(c); if (on === undefined ? has : !on) e.className = e.className.split(/\s+/).filter((x) => x !== c).join(" "); else e.classList.add(c); } },
    appendChild: (c) => { e.children.push(c); if (c.tag === "#text") e.textContent += c.textContent; return c; },
    setAttribute: (k, v) => { e.attrs[k] = v; }, getAttribute: (k) => (k in e.attrs ? e.attrs[k] : null), removeAttribute: (k) => { delete e.attrs[k]; if (k.indexOf("data-") === 0) delete e.dataset[k.slice(5).replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase())]; },   // the DOM's dataset mirrors data-* attributes
    // descendants by a [data-x] selector (the one shape the module uses), so the inert walk is exercised on this DOM too (round three, low 4)
    querySelectorAll: (sel) => { const m = /^\[data-([a-z-]+)\]$/.exec(sel); if (!m) throw new Error("stub selector: " + sel); const key = m[1].replace(/-([a-z])/g, (_x, c: string) => c.toUpperCase());
      const out: El[] = []; const walk = (n: El) => { for (const c of n.children) { if (c.tag !== "#text" && (key in c.dataset || ("data-" + m[1]) in c.attrs)) out.push(c); if (c.children) walk(c); } }; walk(e); return out; } };
  return e;
}
const store = new Map<string, string>();
(globalThis as any).document = { createElement: mkEl, createTextNode: (t: string) => ({ tag: "#text", textContent: t }) };
(globalThis as any).localStorage = { getItem: (k: string) => store.has(k) ? store.get(k)! : null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
(globalThis as any).navigator = { platform: "Linux x86_64" };

// eslint-disable-next-line @typescript-eslint/no-var-requires
const W = require("./status-widgets") as typeof import("./status-widgets");
// eslint-disable-next-line @typescript-eslint/no-var-requires
const S = require("./settings") as typeof import("./settings");

const classes = (e: El) => e.className.split(/\s+/).filter(Boolean);
const REC: StatusRecord = { id: "11111111-2222-3333-4444-555555555555", name: "web", color: { bg: "#9cd2ff" }, cwd: "/home/user/projects/notes-api/",
                            gitBranch: "search-module", workTree: null, host: "" };
const P = (p: Partial<StatusWidgetPrefs> = {}): StatusWidgetPrefs => ({ on: {}, order: [], opts: {}, ...p });
const compose = (slot: "left" | "right", rec: StatusRecord, prefs = P()) => {
  const host = mkEl("span"); W.composeStatusWidgets(host as unknown as HTMLElement, slot, rec, prefs); return host.children;
};

test("the four built-in widgets register in order with the user's defaults: the name left and off, the folder and the branch right and on, the host right and off", () => {
  assert.deepEqual(W.statusWidgets().map((w) => [w.id, w.slot, w.defaultOn]), [["name", "left", false], ["folder", "right", true], ["branch", "right", true], ["host", "right", false]]);
  assert.deepEqual(W.statusWidgets().map((w) => w.label), ["Session name", "Folder", "Git branch", "Host"]);
  assert.ok(W.statusWidgets().every((w) => w.description.length > 0 && !/\bfleet\b/i.test(w.description)));
  assert.deepEqual(W.statusWidget("folder")!.options!.map((o) => [o.key, o.default, o.choices.map((c) => c.value)]), [["show", "name", ["name", "path"]]]);
});

test("the right slot by default: the folder by name with its glyph and the folder link, then the branch; the host renders nothing for a local session", () => {
  const out = compose("right", REC);
  assert.deepEqual(out.map(classes), [["status-dir", "folder-link"], ["status-branch"]]);
  const dir = out[0];
  assert.equal(dir.children[0].className, "status-dir-icon", "the folder glyph leads");
  assert.match(dir.children[0].innerHTML, /^<svg viewBox="0 0 16 16"/);
  assert.equal(dir.textContent, " notes-api", "the basename, the trailing slash dropped");
  assert.equal(dir.dataset.cwd, "/home/user/projects/notes-api/");
  assert.equal(dir.dataset.id, REC.id, "the session id rides along, so a remote session's click goes to its host");
  assert.equal(dir.dataset.act, "openFolder", "no http location on this DOM: the host-side opener, as in VS Code");
  assert.match(dir.title, /click to open this folder$/);
  assert.equal(out[1].textContent, "⎇ search-module");
  assert.equal(out[1].title, "git branch: search-module");
});

test("the folder's Full path option shows the whole path with its own class; no directory means no folder at all, never an empty spacer", () => {
  const full = compose("right", REC, P({ opts: { folder: { show: "path" } } }));
  assert.deepEqual(classes(full[0]), ["status-dir", "status-dir-full", "folder-link"]);
  assert.equal(full[0].textContent, " /home/user/projects/notes-api");
  assert.deepEqual(compose("right", { ...REC, cwd: "" }).map(classes), [["status-branch"]]);
  assert.deepEqual(compose("right", REC, P({ opts: { folder: { show: "bogus" } } }))[0].textContent, " notes-api", "an unknown stored option falls to the default");
});

test("the branch: the worktree's branch wins over the directory's, and no branch known means no span", () => {
  const wt = compose("right", { ...REC, workTree: { dir: "/home/user/projects/notes-api-wt", branch: "search-module-wt" } });
  assert.equal(wt[1].textContent, "⎇ search-module-wt");
  assert.match(wt[1].title, /^worktree \/home\/user\/projects\/notes-api-wt/);
  assert.deepEqual(compose("right", { ...REC, gitBranch: "" }).map(classes), [["status-dir", "folder-link"]]);
  assert.deepEqual(compose("right", REC, P({ on: { branch: false } })).map(classes), [["status-dir", "folder-link"]], "switched off");
});

test("the host renders only when switched on AND the session is remote", () => {
  assert.deepEqual(compose("right", { ...REC, host: "TESTHOST" }).map(classes), [["status-dir", "folder-link"], ["status-branch"]], "off by default");
  const on = compose("right", { ...REC, host: "TESTHOST" }, P({ on: { host: true } }));
  assert.deepEqual(on.map(classes), [["status-dir", "folder-link"], ["status-branch"], ["status-branch", "status-host"]]);
  assert.equal(on[2].textContent, "@ TESTHOST");
  assert.equal(on[2].title, "runs on TESTHOST");
  assert.deepEqual(compose("right", REC, P({ on: { host: true } })).map(classes), [["status-dir", "folder-link"], ["status-branch"]], "a local session: nothing, even when on");
});

test("the left slot: the session's name on its colour, off by default; nothing without a name", () => {
  assert.deepEqual(compose("left", REC), []);
  const on = compose("left", REC, P({ on: { name: true } }));
  assert.deepEqual(on.map(classes), [["chip", "chip-session"]]);
  assert.equal(on[0].textContent, "web");
  assert.equal(on[0].style.background, "#9cd2ff");
  assert.equal(on[0].title, "web");
  assert.deepEqual(compose("left", { ...REC, name: "" }, P({ on: { name: true } })), []);
  assert.equal(compose("left", { ...REC, color: null }, P({ on: { name: true } }))[0].style.background, undefined, "no colour yet: the theme's neutral fill (CSS), never nothing");
});

test("order: the stored order first for the ids it names, the rest in registration order; an unknown id is not drawn; a throwing widget costs nothing", () => {
  assert.deepEqual(compose("right", { ...REC, host: "TESTHOST" }, P({ order: ["host", "branch", "nope"], on: { host: true } })).map((e) => e.textContent),
                   ["@ TESTHOST", "⎇ search-module", " notes-api"]);
  assert.deepEqual(W.orderedStatusWidgets(P({ order: ["branch"] })).map((w) => w.id), ["branch", "name", "folder", "host"]);
  W.registerStatusWidget({ id: "boom", label: "Boom", description: "throws", defaultOn: true, slot: "right", demo: W.DEMO_RECORD, render: () => { throw new Error("no"); } });
  assert.deepEqual(compose("right", REC).map(classes), [["status-dir", "folder-link"], ["status-branch"]]);
  W.registerStatusWidget({ id: "boom", label: "Boom", description: "quiet now", defaultOn: false, slot: "right", demo: W.DEMO_RECORD, render: () => null });
  assert.equal(W.statusWidgets().length, 5, "the same id replaces, never duplicates");
});

test("the settings row's demo renders the widget over its demo record through the same render", () => {
  const d = W.renderStatusWidgetDemo(W.statusWidget("folder")!, P()) as unknown as El;
  assert.deepEqual(classes(d), ["status-dir"], "the demo is inert: no link dress (round two)");
  assert.equal(d.textContent, " notes-api");
  assert.equal((W.renderStatusWidgetDemo(W.statusWidget("host")!, P()) as unknown as El).textContent, "@ TESTHOST", "the demo record is a remote session, so the row shows the host");
  assert.equal((W.renderStatusWidgetDemo(W.statusWidget("name")!, P()) as unknown as El).textContent, "web");
});

test("statusWidgetPrefs: a stored object normalizes; with none the widget defaults rule, whatever the store's legacy keys say (the one-shot migration: those keys were the gear's injected default, not a choice)", () => {
  assert.deepEqual(W.statusWidgetPrefs(undefined), { on: {}, order: [], opts: {} }, "no store: nothing set, the defaults rule");
  assert.deepEqual(W.statusWidgetPrefs({ on: { folder: false, host: "yes" }, order: ["host", 3], opts: { folder: { show: "path", n: 2 } } }),
                   { on: { folder: false }, order: ["host"], opts: { folder: { show: "path" } } }, "a stored object normalizes: junk dropped");
  assert.deepEqual(W.statusWidgetPrefs("junk"), { on: {}, order: [], opts: {} }, "a non-object store is no store");
  assert.equal(W.statusWidgetPrefs.length, 1, "the resolver takes the stored object alone: no legacy argument to derive from");
});

test("legacyOfStatusPrefs: the mirror follows the switches, the widget defaults included (the branch on, the name off)", () => {
  assert.deepEqual(W.legacyOfStatusPrefs(P()), { showBranch: true, showSessionBadge: false });
  assert.deepEqual(W.legacyOfStatusPrefs(P({ on: { branch: false, name: true } })), { showBranch: false, showSessionBadge: true });
});

test("settings, the four store shapes (the one-shot migration, the user's call through the manager): no keys, a legacy false, a legacy true, a stored prefs object; the legacy keys never read, written as mirrors from the first save", () => {
  const load = (raw: Record<string, unknown>) => { store.clear(); store.set("romp:settings", JSON.stringify(raw)); return S.loadSettings(); };
  let s = load({ compact: true });
  assert.deepEqual(s.statusWidgets, { on: {}, order: [], opts: {} }, "no keys: the defaults");
  assert.equal(s.showBranch, true, "the mirror of the branch widget's default"); assert.equal(s.showSessionBadge, false);
  assert.equal(S.DEFAULT_SETTINGS.showBranch, true); assert.equal(S.DEFAULT_SETTINGS.showSessionBadge, false);
  s = load({ compact: true, showBranch: false });
  assert.deepEqual(s.statusWidgets, { on: {}, order: [], opts: {} }, "a legacy false and no statusWidgets: the gear's injected default, not a choice; the branch shows");
  assert.equal(s.showBranch, true, "the in-memory mirror follows the widget, not the stored key");
  assert.deepEqual(JSON.parse(store.get("romp:settings")!), { compact: true, showBranch: false }, "a load writes nothing: the store upgrades at the first save");
  s = load({ compact: true, showBranch: true, showSessionBadge: true });
  assert.deepEqual(s.statusWidgets, { on: {}, order: [], opts: {} }, "a legacy true reads the same: the name stays off, its default");
  assert.equal(s.showSessionBadge, false);
  s = load({ compact: true, showBranch: true, statusWidgets: { on: { branch: false, name: true }, order: ["branch"], opts: {} } });
  assert.deepEqual(s.statusWidgets, { on: { branch: false, name: true }, order: ["branch"], opts: {} }, "a stored prefs object is the user's choice and wins over any legacy key");
  assert.deepEqual([s.showBranch, s.showSessionBadge], [false, true], "the mirrors follow the prefs");
  // the first save of the prefs writes the key and both mirrors; from then on the store carries the user's choice
  load({ compact: true, showBranch: false });
  const saved = S.saveSettings({ statusWidgets: { on: { branch: false }, order: [], opts: {} } });
  assert.deepEqual([saved.showBranch, saved.showSessionBadge], [false, false]);
  const raw = JSON.parse(store.get("romp:settings")!);
  assert.deepEqual([raw.showBranch, raw.statusWidgets.on], [false, { branch: false }], "the mirror and the prefs in the store: switched off after the upgrade, it stays off");
  assert.equal(S.loadSettings().statusWidgets.on.branch, false, "and reads off on the next load");
  // an older writer patching a legacy key alone through saveSettings is an explicit act, not a stored value of unknown
  // provenance: the widget follows it (the mirror runs both ways for a patch)
  const legacy = S.saveSettings({ showBranch: true });
  assert.equal(legacy.statusWidgets.on.branch, true); assert.equal(legacy.showBranch, true);
  store.clear();
});

test("statusWidgetPrefs sanitizes the order: duplicates once, unknown ids gone; the next save rewrites the store clean", () => {
  assert.deepEqual(W.statusWidgetPrefs({ order: ["branch", "nope", "branch", "folder"] }).order, ["branch", "folder"]);
  store.clear();
  store.set("romp:settings", JSON.stringify({ compact: true, statusWidgets: { on: {}, order: ["host", "host", "zz"], opts: {} } }));
  const saved = S.saveSettings({ compact: false });
  assert.deepEqual(saved.statusWidgets.order, ["host"]);
  assert.deepEqual(JSON.parse(store.get("romp:settings")!).statusWidgets.order, ["host"]);
  store.clear();
});

test("statusListOrder: the left slot's rows, then the right slot's, each in composition order (the list a drag reorders within a slot)", () => {
  assert.deepEqual(W.statusListOrder(P()).filter((x) => x !== "boom"), ["name", "folder", "branch", "host"]);
  assert.deepEqual(W.statusListOrder(P({ order: ["host", "name"] })).filter((x) => x !== "boom"), ["name", "host", "folder", "branch"], "the stored order reorders within each slot's group");
});

test("makeInert: a demo or preview node carries no folder act, no link dress and no click clause in its title; the path stays; the walk reaches a nested folder", () => {
  const d = W.renderStatusWidgetDemo(W.statusWidget("folder")!, P()) as unknown as El;
  assert.deepEqual(classes(d), ["status-dir"], "no folder-link class on the demo");
  assert.equal(d.dataset.act, undefined); assert.equal(d.dataset.cwd, undefined); assert.equal(d.dataset.id, undefined);
  assert.match(d.title, /notes-api/, "the path still reads on hover");
  assert.doesNotMatch(d.title, /click to/, "an inert node promises no click (round three, low 3)");
  const live = compose("right", REC)[0];
  assert.equal(live.dataset.act, "openFolder", "the line's own folder keeps its act");
  assert.match(live.title, /click to open this folder/, "and its title still offers the click");
  // a composed preview: the folder sits INSIDE the line, so the walk over [data-act] must reach it
  const line = mkEl("div"); W.composeStatusWidgets(line as unknown as HTMLElement, "right", REC, P()); W.makeInert(line as unknown as HTMLElement);
  const nested = line.children.find((c) => c.className.indexOf("status-dir") === 0)!;
  assert.equal(nested.dataset.act, undefined, "the nested folder's act stripped through the walk");
  assert.deepEqual(classes(nested), ["status-dir"]);
  assert.doesNotMatch(nested.title, /click to/); assert.match(nested.title, /notes-api/);
});
