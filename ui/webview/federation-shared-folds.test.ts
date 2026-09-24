// TWO VIEWERS OF ONE KERNEL FOLD TOGETHER (the user 2026-09-23, who wanted to collapse tag groups on the phone too, with
// the collapsed state synced to the desktop like the tab order).
//
// Executed against the real FederationManager and the real tab-groups store, twice over: a browser here is its own
// `window` and its own localStorage, and everything on this path is synchronous, so swapping the globals IS having two
// of them (federation-shared-order.test.ts's harness, the same shape). The fake kernel in the middle does what kernel.py
// does with the viewer's store: keeps the fold object it is handed without reading it, says whether it has one at all
// (`folds: null` when not), and pushes ONE viewOrder frame, the arrangement's and the folds' together, to every client
// when either CHANGES. What is pinned is the protocol between the two, not a mock of it.
//
// SYNTHETIC only: the notes-api demo world (web, api, tests), placeholder uuids.
import { test } from "node:test";
import assert from "node:assert/strict";
import { FederationManager } from "./federation";
import { planStrip, readTabGroups, setSectionCollapsed, writeTabGroups, TABGROUPS_EVENT, TABGROUPS_KEY, TABGROUPS_SHARED_KEY } from "./tab-groups";
import { viewTagUnion } from "./session-views";

const WEB = "11111111-2222-4333-8444-000000000001";
const API = "11111111-2222-4333-8444-000000000002";
const TESTS = "11111111-2222-4333-8444-000000000003";
const VIEWS = { active: "all", tags: [{ id: "g1", name: "api", color: "#1EA1EB", members: [API, TESTS] }, { id: "g2", name: "web", color: "#4EC9B0", members: [WEB] }] };
const UNIONS = viewTagUnion(VIEWS);

/** The kernel's viewer store and its push, as kernel.py implements them (_write_view_folds, _view_order_frame). */
function fakeKernel(opts: { folds?: boolean } = {}) {
  const keepsFolds = opts.folds !== false;   // a kernel from before 2026-09-23 sends no folds half at all
  const k = {
    folds: null as Record<string, unknown> | null,
    viewers: [] as Viewer[],
    posts: [] as unknown[],
    frame(): any {
      const fr: any = { type: "viewOrder", order: [], stored: false };
      if (keepsFolds) fr.folds = k.folds === null ? null : JSON.parse(JSON.stringify(k.folds));
      return fr;
    },
    post(folds: Record<string, unknown>) {
      k.posts.push(folds);
      if (!keepsFolds) return;                                      // an older kernel answers unknownOp; nothing is kept
      if (k.folds !== null && JSON.stringify(k.folds) === JSON.stringify(folds)) return;   // unchanged: no push
      k.folds = JSON.parse(JSON.stringify(folds));
      for (const v of k.viewers) if (v.connected) v.deliver(k.frame());   // a dropped socket hears nothing
    },
    connect(v: Viewer) { v.connected = true; v.deliver(k.frame()); },
    /** the page's socket drops: the kernel no longer reaches it, and what it sends waits in the shim's queue
     *  (the page shim queues every send while its socket is down and flushes the queue when a new one opens) */
    drop(v: Viewer) { v.connected = false; },
    /** a new socket opens: the shim flushes what the page queued while down, the reconnect's `wsup` frame reaches the
     *  page, then (before the kernel's viewOrder frame) whatever the connect push's earlier frames make the page write
     *  (`beforeFrame`: the views frame's rename follow, say), then the viewOrder frame */
    reconnect(v: Viewer, beforeFrame?: () => void) {
      v.connected = true;
      for (const f of v.queued.splice(0)) k.post(f);
      v.deliver({ type: "wsup" });
      if (beforeFrame) beforeFrame();
      v.deliver(k.frame());
    },
  };
  return k;
}
type Kernel = ReturnType<typeof fakeKernel>;

interface Viewer {
  name: string;
  connected: boolean;
  queued: Record<string, unknown>[];   // sends made while the socket was down (the shim's queue)
  store: Map<string, string>;
  fm: any;
  repaints: number;
  as<T>(fn: () => T): T;
  deliver(frame: any): void;
  shared(): any;
}

function makeViewer(name: string, k: Kernel, seed: Record<string, unknown> = {}, sharedStore?: Map<string, string>): Viewer {
  const g: any = globalThis;
  const store = sharedStore ?? new Map<string, string>();   // two panes of one browser share one store
  for (const [key, val] of Object.entries(seed)) store.set(key, JSON.stringify(val));
  const win: any = new EventTarget();
  win.__rompApp = "chat";
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, val: string) => { store.set(key, val); },
    removeItem: (key: string) => { store.delete(key); },
  };
  const v: Viewer = {
    name, store, fm: null, repaints: 0, connected: false, queued: [],
    as<T>(fn: () => T): T {
      const saved: Record<string, [boolean, unknown]> = {};
      for (const key of ["window", "document", "localStorage", "setInterval", "fetch"]) saved[key] = [key in g, g[key]];
      g.window = win;
      g.document = Object.assign(new EventTarget(), { visibilityState: "visible" });
      g.localStorage = localStorage;
      g.setInterval = () => 0;
      g.fetch = () => new Promise(() => {});
      try { return fn(); } finally {
        for (const key of Object.keys(saved)) { const [had, val] = saved[key]; if (had) g[key] = val; else delete g[key]; }
      }
    },
    deliver(frame: any) { v.as(() => v.fm.inbound("", frame)); },
    shared() { const raw = store.get(TABGROUPS_SHARED_KEY); return raw === undefined ? undefined : JSON.parse(raw); },
  };
  // render.ts repaints the strip on this event (window.addEventListener(TABGROUPS_EVENT, () => renderTabs())): counted here
  win.addEventListener(TABGROUPS_EVENT, () => { v.repaints++; });
  v.as(() => {
    const fm: any = new FederationManager();
    fm.start();
    fm.outbound = (m: any) => { if (m && m.type === "setViewFolds") { if (v.connected) k.post(m.folds); else v.queued.push(m.folds); } };
    v.fm = fm;
  });
  k.viewers.push(v);
  return v;
}

/** The strip each viewer would paint now: the plan over its own store, the phone's layout for the phone. */
const shape = (v: Viewer, phone: boolean, active: string | null = WEB) => v.as(() =>
  planStrip([WEB, API, TESTS], UNIONS, readTabGroups(UNIONS), active, phone).items.map((i) => ("head" in i ? `#${i.head.name}${i.folded ? "(folded)" : ""}` : i.id)));
/** A fold as the strip's header click (and the phone picker's heading, through it) writes it. */
const fold = (v: Viewer, group: string, folded: boolean) => v.as(() => writeTabGroups(setSectionCollapsed(readTabGroups(UNIONS), group, folded)));

// ── the headline ─────────────────────────────────────────────────────────────────────────────────────
test("a group folded on the desktop folds on the phone, live, and opened on the phone opens on the desktop", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  assert.deepEqual(shape(phone, true), ["#api", API, TESTS, "#web", WEB], "both open to start");
  const before = phone.repaints;
  fold(desktop, "api", true);
  assert.deepEqual(k.folds, { collapsed: ["api"], expanded: [], pinned: [] }, "the kernel keeps the fold");
  assert.deepEqual(phone.shared().collapsed, ["api"], "the phone has it, off the kernel's push");
  assert.ok(phone.repaints > before, "…and was told to repaint: no reload, nothing polling");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web", WEB], "the phone's picker lists api's heading alone");
  assert.deepEqual(shape(desktop, false), ["#api(folded)", "#web", WEB]);
  // the phone opens it again: the desktop follows
  fold(phone, "api", false);
  assert.deepEqual(k.folds, { collapsed: [], expanded: [], pinned: [] });
  assert.deepEqual(shape(desktop, false), ["#api", API, TESTS, "#web", WEB], "opened on the phone, open on the desktop");
});

test("a pushed fold that changes nothing is not announced: every viewer sees its own publish come back", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  fold(desktop, "api", true);
  const d = desktop.repaints, p = phone.repaints, posts = k.posts.length;
  k.connect(phone);                                                // a reconnect re-serves the same folds
  assert.equal(phone.repaints, p, "the same folds again: no repaint");
  fold(phone, "api", true);                                        // folding what is already folded
  assert.equal(k.posts.length, posts, "nothing changed, nothing published");
  desktop.as(() => writeTabGroups({ ...readTabGroups(UNIONS), on: false }));   // this browser's own switch
  assert.equal(k.posts.length, posts, "the group switch is this browser's: it publishes nothing");
  assert.equal(desktop.repaints, d + 1, "…and repaints its own strip");
  assert.equal(phone.shared().collapsed.length, 1);
});

test("the pins ride with the folds: a member set to show through its fold on the desktop shows through on the phone", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  desktop.as(() => writeTabGroups({ ...setSectionCollapsed(readTabGroups(UNIONS), "api", true), pinned: [{ sid: TESTS, name: "api", id: "g1" }] }));
  assert.deepEqual(shape(phone, true), ["#api(folded)", TESTS, "#web", WEB], "the pinned member keeps its row under the folded heading");
});

// ── the migration ─────────────────────────────────────────────────────────────────────────────────
test("a browser carrying folds of its own into a kernel with none publishes them, and the others take them", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k, { [TABGROUPS_KEY]: { on: true, collapsed: ["web"], expanded: [], pinned: [] } });   // folded before the move
  const phone = makeViewer("phone", k);
  k.connect(phone);
  assert.equal(k.posts.length, 0, "a phone with no folds of its own publishes nothing");
  k.connect(desktop);
  assert.deepEqual(k.folds, { collapsed: ["web"], expanded: [], pinned: [] }, "the upgrading browser's folds survive the move");
  assert.deepEqual(shape(phone, true), ["#api", API, TESTS, "#web(folded)"], "and the phone converges on them");
  assert.deepEqual(JSON.parse(desktop.store.get(TABGROUPS_KEY)!).collapsed, ["web"], "the pre-move key is left where it was");
});

test("a kernel that already keeps folds wins over a browser's own, and the browser's key is left in place", () => {
  const k = fakeKernel();
  k.folds = { collapsed: ["api"], expanded: [], pinned: [] };       // another device folded first
  const phone = makeViewer("phone", k, { [TABGROUPS_KEY]: { on: true, collapsed: ["web"], expanded: [], pinned: [] } });
  // before the kernel's word lands, the first paint is the fold this browser is used to
  assert.deepEqual(shape(phone, true), ["#api", API, TESTS, "#web(folded)"], "the first paint: this browser's pre-move folds");
  k.connect(phone);
  assert.equal(k.posts.length, 0, "nothing published over the kernel's");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web", WEB], "the kernel's folds win");
  assert.deepEqual(JSON.parse(phone.store.get(TABGROUPS_KEY)!).collapsed, ["web"], "…without destroying the local key: reverting hands it back");
  // an EMPTIED kernel state (every group opened) is somebody's answer, not a missing one: never refilled from an old key
  const k2 = fakeKernel();
  k2.folds = { collapsed: [], expanded: [], pinned: [] };
  const laptop = makeViewer("laptop", k2, { [TABGROUPS_KEY]: { on: true, collapsed: ["web"], expanded: [], pinned: [] } });
  k2.connect(laptop);
  assert.deepEqual([k2.posts.length, shape(laptop, false)], [0, ["#api", API, TESTS, "#web", WEB]]);
});

test("a fold made before the kernel's folds reach the page lands OVER them: the gesture stands, and so does what another device folded", () => {
  // the connect push serves the strip (a header a person can click, and the views frame a rename follow runs on) before
  // the folds: a whole-state publish from then would put this browser's older copy over what another device folded since,
  // and adopting the kernel's on arrival would undo the click. The change waits as a delta and is merged over the kernel's
  const k = fakeKernel();
  k.folds = { collapsed: ["api"], expanded: [], pinned: [] };          // another device folded api
  const phone = makeViewer("phone", k);
  fold(phone, "web", true);                                            // clicked before the kernel's word arrived
  assert.equal(k.posts.length, 0, "not heard yet: nothing published");
  k.connect(phone);
  assert.deepEqual(k.folds, { collapsed: ["api", "web"], expanded: [], pinned: [] }, "both: the other device's fold and this click");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web(folded)"]);
  fold(phone, "web", false);
  assert.deepEqual(k.folds, { collapsed: ["api"], expanded: [], pinned: [] }, "heard: from now on a fold here is published whole, at once");
});

test("a browser with folds from before the move that clicks before hearing: the kernel's folds win, the click lands on them", () => {
  const k = fakeKernel();
  k.folds = { collapsed: [], expanded: [], pinned: [] };               // the kernel's: every group open (somebody's answer)
  const desktop = makeViewer("desktop", k, { [TABGROUPS_KEY]: { on: true, collapsed: ["web"], expanded: [], pinned: [] } });
  fold(desktop, "api", true);                                          // over the pre-move folds the page painted first
  k.connect(desktop);
  assert.deepEqual(k.folds, { collapsed: ["api"], expanded: [], pinned: [] }, "web stays open (the kernel's), api folds (the click)");
  assert.deepEqual(JSON.parse(desktop.store.get(TABGROUPS_KEY)!).collapsed, ["web"], "the pre-move key still untouched");
});

test("two panes of ONE browser: a click in the pane that has not heard lands, whichever pane hears the kernel first", () => {
  // the sibling-pane race a real browser showed (tests/test_cold_boot_diet_browser.py): the unheard pane's click wrote the
  // browser's copy, and a later adoption of the kernel's older folds put the section back. The delta is origin-wide, so
  // the first pane of the browser to hear lands it
  for (const firstToHear of ["clicked", "other"] as const) {
    const k = fakeKernel();
    k.folds = { collapsed: ["api"], expanded: [], pinned: [] };
    const shared = new Map<string, string>();
    const clicked = makeViewer("clicked pane", k, {}, shared), other = makeViewer("other pane", k, {}, shared);
    shared.set(TABGROUPS_SHARED_KEY, JSON.stringify(k.folds));         // the browser's copy from its last visit: api folded
    fold(clicked, "api", false);                                       // opened before either pane heard
    if (firstToHear === "clicked") { k.connect(clicked); k.connect(other); } else { k.connect(other); k.connect(clicked); }
    assert.deepEqual(k.folds, { collapsed: [], expanded: [], pinned: [] }, firstToHear + " pane heard first: the click landed");
    assert.deepEqual(shape(other, false), ["#api", API, TESTS, "#web", WEB], firstToHear + ": and every pane shows it");
  }
});

test("a kernel that keeps no folds (one from before 2026-09-23) sends no folds half: the folds stay this browser's, nothing is published", () => {
  const k = fakeKernel({ folds: false });
  const phone = makeViewer("phone", k, { [TABGROUPS_KEY]: { on: true, collapsed: ["web"], expanded: [], pinned: [] } });
  k.connect(phone);
  fold(phone, "api", true);
  assert.equal(k.posts.length, 0, "no publisher was ever installed");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web(folded)"], "the folds still work, per browser, as before");
});

test("a REMOTE kernel's folds are ignored: they belong to whoever sits in front of that machine", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k);
  k.connect(desktop);
  desktop.as(() => desktop.fm.inbound("TESTHOST", { type: "viewOrder", order: [], stored: true, folds: { collapsed: ["api", "web"], expanded: [], pinned: [] } }));
  assert.deepEqual(shape(desktop, false), ["#api", API, TESTS, "#web", WEB], "untouched");
});

// ── a dropped connection: the page stops speaking for the folds until the next one hears the kernel's ─────────────
test("a page whose connection drops while another device folds adopts the kernel's folds on reconnect and publishes nothing stale", () => {
  // the order half's per-connection gate (#2062, view-order.ts hearSharedOrder), applied to the folds: the publisher is the
  // current connection's, granted by its viewOrder frame and withdrawn by the reconnect. Kept across the drop, the page put
  // its pre-drop copy over the kernel's with the first write its reconnect made before that frame (here the connect push's
  // views frame, whose rename follow writes the memory): the fold another device made meanwhile was lost on every device
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  fold(desktop, "api", true);
  k.drop(phone);                                                       // the phone goes offline…
  fold(desktop, "web", true);                                          // …while the desktop folds web
  assert.deepEqual(phone.shared().collapsed, ["api"], "premise: the phone never heard of web's fold");
  const before = k.posts.length;
  k.reconnect(phone, () => phone.as(() => writeTabGroups({ ...readTabGroups(UNIONS), followed: { g2: "web" } })));
  const fromPhone = k.posts.slice(before);
  assert.ok(fromPhone.every((f: any) => f.collapsed.includes("web")), "nothing the phone published drops the desktop's fold: " + JSON.stringify(fromPhone));
  assert.deepEqual(k.folds, { collapsed: ["api", "web"], expanded: [], pinned: [], followed: { g2: "web" } },
    "the kernel's folds stand, the phone's own change (the follow) landed over them");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web(folded)"], "the phone adopted the desktop's fold");
  assert.deepEqual(shape(desktop, false), ["#api(folded)", "#web(folded)"]);
  // and a reconnect with no change of its own publishes nothing at all
  k.drop(phone); fold(desktop, "web", false);
  const quiet = k.posts.length;
  k.reconnect(phone);
  assert.equal(k.posts.length, quiet, "adopted, not answered");
  assert.deepEqual(shape(phone, true), ["#api(folded)", "#web", WEB]);
});

test("a fold made while offline is kept and merged over the kernel's folds when the next connection hears them", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  fold(desktop, "api", true);
  k.drop(phone);
  phone.as(() => (globalThis as any).window.dispatchEvent(new Event("romp:wsdown")));   // the shim's own drop event
  fold(desktop, "web", true);                                          // the desktop folds web meanwhile
  fold(phone, "api", false);                                           // the phone, offline, opens api
  assert.deepEqual(phone.queued, [], "nothing queued to publish blind: the drop withdrew the publisher");
  assert.deepEqual(shape(phone, true), ["#api", API, TESTS, "#web", WEB], "the phone shows its own gesture meanwhile");
  k.reconnect(phone);
  assert.deepEqual(k.folds, { collapsed: ["web"], expanded: [], pinned: [] }, "api opened (the phone's), web folded (the desktop's)");
  assert.deepEqual(shape(desktop, false), ["#api", API, TESTS, "#web(folded)"], "and the desktop follows");
  fold(phone, "tests", true);
  assert.deepEqual(k.folds.collapsed, ["web", "tests"], "heard again: a fold here is published at once");
});

// ── the active session on the phone ───────────────────────────────────────────────────────────────
test("the phone folds the active session's group like the desktop does: the heading stands in for it, and it is marked", () => {
  const k = fakeKernel();
  const desktop = makeViewer("desktop", k), phone = makeViewer("phone", k);
  for (const v of [desktop, phone]) k.connect(v);
  fold(desktop, "api", true);
  const [dplan, pplan] = [false, true].map((ph) => (ph ? phone : desktop).as(() => planStrip([WEB, API, TESTS], UNIONS, readTabGroups(UNIONS), API, ph)));
  const head = (p: typeof dplan) => p.items.find((i) => "head" in i && i.head.name === "api") as any;
  assert.deepEqual([head(pplan).folded, head(pplan).active, head(pplan).hidden], [true, true, [API, TESTS]], "the phone: folded, its heading the active session's stand-in");
  assert.deepEqual([head(dplan).folded, head(dplan).active], [true, true], "…exactly as the desktop's header");
  assert.ok(pplan.folded.has(API), "the active session is folded away on both");
});
