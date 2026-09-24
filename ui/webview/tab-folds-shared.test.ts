// THE FOLDS ARE EVERY DEVICE'S (the user 2026-09-23, who wanted to collapse tag groups on the phone too, with the collapsed
// state synced to the desktop like the tab order): the tab-groups store in two halves. This browser's switches (whether the
// strip groups by tag, and the Sessions pane's own switch) stay in romp:tabgroups; the FOLDS (which groups are folded,
// which default-folded ones were opened, which members show through a fold, and the rename memory those pins rest on) are
// the kernel's, cached here under romp:tabgroups:shared and published when they change. Executed against the real module
// over a fake localStorage; the protocol with the kernel is federation-shared-folds.test.ts's. Synthetic ids only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { adoptSharedFolds, foldsOf, foldsToPublish, hearSharedFolds, mergeFolds, parseTabGroups, phoneStandIns, planStrip, readTabGroups,
         setFoldsPublisher, setSectionCollapsed, writeTabGroups, TABGROUPS_EVENT, TABGROUPS_KEY, TABGROUPS_PENDING_KEY, TABGROUPS_SHARED_KEY,
         type TabFolds, type TabGroupsState } from "./tab-groups";
import { viewTagUnion } from "./session-views";
import { routeOutbound } from "./federation";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");

function withStore<T>(seed: Record<string, unknown>, fn: (store: Map<string, string>, events: string[]) => T): T {
  const g: any = globalThis;
  const store = new Map<string, string>();
  for (const [k, v] of Object.entries(seed)) store.set(k, typeof v === "string" ? v : JSON.stringify(v));
  const events: string[] = [];
  const win: any = new EventTarget();
  win.addEventListener(TABGROUPS_EVENT, () => events.push(TABGROUPS_EVENT));
  const saved = [g.localStorage, g.window];
  g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
  g.window = win;
  try { return fn(store, events); } finally { [g.localStorage, g.window] = saved; setFoldsPublisher(null); }
}
const json = (store: Map<string, string>, k: string) => JSON.parse(store.get(k)!);

test("a write splits the store: this browser's switches to romp:tabgroups, the folds to the kernel's cached copy", () => {
  withStore({}, (store) => {
    writeTabGroups({ on: false, collapsed: ["api"], expanded: ["archived"], pinned: [{ sid: "web", name: "api", id: "g1" }], followed: { g1: "api" }, timeline: true });
    assert.deepEqual(json(store, TABGROUPS_KEY), { on: false, timeline: true }, "the switches alone");
    assert.deepEqual(json(store, TABGROUPS_SHARED_KEY), { collapsed: ["api"], expanded: ["archived"], pinned: [{ sid: "web", name: "api", id: "g1" }], followed: { g1: "api" } },
      "the folds, in the canonical shape the wire carries");
    assert.deepEqual(readTabGroups(), { on: false, collapsed: ["api"], expanded: ["archived"], pinned: [{ sid: "web", name: "api", id: "g1" }], followed: { g1: "api" }, timeline: true },
      "read back whole");
  });
});

test("the pre-move fold fields are READ as the first paint and never written again: reverting hands them back", () => {
  const PRE = { on: true, collapsed: ["web"], expanded: [], pinned: [], timeline: true };
  withStore({ [TABGROUPS_KEY]: PRE }, (store) => {
    assert.deepEqual(readTabGroups().collapsed, ["web"], "no kernel copy yet: the folds this browser is used to");
    writeTabGroups(setSectionCollapsed(readTabGroups(), "web", false));
    assert.deepEqual(readTabGroups().collapsed, [], "the write lands in the kernel's copy, which reads first from now on");
    assert.deepEqual(json(store, TABGROUPS_KEY), PRE, "the old key's folds are exactly as they were");
    writeTabGroups({ ...readTabGroups(), on: false });
    assert.deepEqual(json(store, TABGROUPS_KEY), { ...PRE, on: false }, "only its switch moves");
  });
});

test("a fold is PUBLISHED when the folds change, and only then; before the kernel's are heard it waits as a delta, landed over them", () => {
  withStore({}, (store) => {
    const sent: TabFolds[] = [];
    writeTabGroups(setSectionCollapsed(readTabGroups(), "api", true));
    assert.equal(sent.length, 0, "no publisher yet: a page never publishes its whole state before it has heard the kernel's");
    assert.deepEqual(json(store, TABGROUPS_PENDING_KEY), { collapsed: [], expanded: [], pinned: [] }, "the change's base is kept, origin-wide");
    writeTabGroups(setSectionCollapsed(readTabGroups(), "api", false));
    writeTabGroups(setSectionCollapsed(readTabGroups(), "api", true));
    assert.deepEqual(json(store, TABGROUPS_PENDING_KEY), { collapsed: [], expanded: [], pinned: [] }, "the FIRST unheard change's base stands for the ones after it");
    // the kernel's word: another device had folded web meanwhile. The change here (api folded) lands over it
    hearSharedFolds({ collapsed: ["web"], expanded: [], pinned: [] }, (f) => sent.push(f), setFoldsPublisher);
    assert.deepEqual(sent, [{ collapsed: ["web", "api"], expanded: [], pinned: [] }], "published: the kernel's folds with this browser's change over them");
    assert.equal(store.has(TABGROUPS_PENDING_KEY), false, "the delta is spent");
    assert.deepEqual(readTabGroups().collapsed, ["web", "api"]);
    writeTabGroups(setSectionCollapsed(readTabGroups(), "tests", true));
    assert.deepEqual(sent.at(-1), { collapsed: ["web", "api", "tests"], expanded: [], pinned: [] }, "heard: a change goes up whole, at once");
    writeTabGroups(setSectionCollapsed(readTabGroups(), "tests", true));
    writeTabGroups({ ...readTabGroups(), on: false });
    assert.equal(sent.length, 2, "an unchanged rewrite and a switch flip publish nothing");
  });
});

test("the three-way merge: the kernel's folds with this browser's changes since the base, per section, pin and memory entry", () => {
  const base: TabFolds = { collapsed: ["api", "old"], expanded: [], pinned: [{ sid: "web", name: "api", id: "g1" }], followed: { g1: "api" } };
  const local: TabFolds = { collapsed: ["old", "tests"], expanded: ["archived"], pinned: [{ sid: "web", name: "ops", id: "g1" }], followed: { g1: "ops" } };
  const served: TabFolds = { collapsed: ["api", "old", "docs"], expanded: [], pinned: [{ sid: "web", name: "api", id: "g1" }, { sid: "api", name: "web" }], followed: { g1: "api", g2: "web" } };
  assert.deepEqual(mergeFolds(base, local, served), {
    collapsed: ["old", "docs", "tests"],   // api opened here: opened; docs folded there: stands; tests folded here: folded
    expanded: ["archived"],                // archived opened here
    pinned: [{ sid: "api", name: "web" }, { sid: "web", name: "ops", id: "g1" }],   // the pin carried here moves; the other device's pin stands
    followed: { g1: "ops", g2: "web" },    // the memory entry changed here takes this browser's; the other's stands
  });
  assert.deepEqual(mergeFolds(base, base, served), foldsOf({ on: true, ...served }), "no change here: the kernel's, exactly");
  assert.deepEqual(mergeFolds(base, local, mergeFolds(base, local, served)), mergeFolds(base, local, served), "a change the kernel already carries applies as a no-op");
});

test("the migration decision: the kernel's folds win; with none there, this browser's go up unless it has none", () => {
  const mine: TabGroupsState = { on: true, collapsed: ["web"], expanded: [], pinned: [] };
  assert.equal(foldsToPublish({ collapsed: [], expanded: [], pinned: [] }, mine), null, "the kernel keeps folds (even emptied ones): they win");
  assert.deepEqual(foldsToPublish(null, mine), foldsOf(mine), "the kernel keeps none: publish this browser's, so they survive the move");
  assert.equal(foldsToPublish(null, parseTabGroups(null)), null, "nothing folded, opened, pinned or remembered here: nothing to publish");
  assert.deepEqual(foldsToPublish(null, { ...parseTabGroups(null), expanded: ["archived"] }), { collapsed: [], expanded: ["archived"], pinned: [] }, "an opened default-folded group is a fold state too");
  assert.equal(foldsToPublish(undefined, mine), null, "no folds half at all (an older kernel): never published");
});

test("an adoption caches and announces only a CHANGE, and a malformed half is ignored", () => {
  withStore({}, (store, events) => {
    assert.equal(adoptSharedFolds({ collapsed: ["api"], expanded: [], pinned: [] }), true);
    assert.deepEqual([json(store, TABGROUPS_SHARED_KEY).collapsed, events.length], [["api"], 1], "cached, and the strip told to repaint");
    assert.equal(adoptSharedFolds({ collapsed: ["api"], expanded: [], pinned: [] }), false, "its own publish coming back");
    assert.equal(events.length, 1, "…announces nothing");
    for (const junk of [null, undefined, ["api"], "api", 7]) assert.equal(adoptSharedFolds(junk), false, "junk: " + JSON.stringify(junk));
    assert.equal(adoptSharedFolds({ collapsed: ["api", 3, null], pinned: "no", expanded: [] }), false, "parsed through the one parser: junk entries drop, and what is left is what was held");
  });
});

// ── the phone ─────────────────────────────────────────────────────────────────────────────────────
const VIEWS = { active: "all", tags: [{ id: "g1", name: "api", color: "#1EA1EB", members: ["api", "tests"] }, { id: "g2", name: "web", color: "#4EC9B0", members: ["web"] }] };
const U = viewTagUnion(VIEWS);

test("the phone paints the folded-away ACTIVE tab once, right after the heading that stands in for it, and nothing when it shows", () => {
  const folded = setSectionCollapsed(parseTabGroups(null), "api", true);
  const p = planStrip(["web", "api", "tests"], U, folded, "api", true);
  const paint = phoneStandIns(p.items, "api", p.folded);
  assert.deepEqual(paint.map((i) => ("head" in i ? "#" + i.head.name : ("away" in i ? "away:" : "") + i.id)), ["#api", "away:api", "#web", "web"],
    "the picker reads the away node for its current-session chip, and lists api's heading alone");
  assert.equal(phoneStandIns(p.items, "web", p.folded), p.items, "an active tab on the strip: the plan's items themselves");
  assert.equal(phoneStandIns(p.items, null, p.folded), p.items, "no active tab: nothing");
  const pinned = { ...folded, pinned: [{ sid: "api", name: "api", id: "g1" }] };
  const pp = planStrip(["web", "api", "tests"], U, pinned, "api", true);
  assert.equal(phoneStandIns(pp.items, "api", pp.folded), pp.items, "pinned through the fold: the tab itself shows, no stand-in node");
});

// ── the wiring: every kind of page hears the folds through the one implementation, and a fold goes to the LOCAL kernel ──
test("a fold goes to the LOCAL kernel whole, and every page hears the folds through hearSharedFolds", () => {
  // the folds name tags and host-prefixed pins as this viewer sees them: never split by host the way an order[] is
  assert.deepEqual(routeOutbound({ type: "setViewFolds", folds: { collapsed: ["api"], expanded: [], pinned: [{ sid: "TESTHOST:web", name: "api" }] } }, new Set(["TESTHOST"])),
    [{ host: "", msg: { type: "setViewFolds", folds: { collapsed: ["api"], expanded: [], pinned: [{ sid: "TESTHOST:web", name: "api" }] } } }]);
  // a page with a manager: the frame's folds half, only from the local kernel, and the window slot installed there
  assert.match(FED, /if \("folds" in m\) \{\s*\n\s*hearSharedFolds\(m\.folds, \(f\) => this\.outbound\(\{ type: "setViewFolds", folds: f \}\), \(fn\) => \{ w\.__rompPublishViewFolds = fn; \}\);/);
  assert.match(FED, /if \(m && m\.type === "viewOrder"\) \{\s*\n\s*if \(host !== LOCAL\) return;\s*\n\s*const w = window as any;/, "…`w` the frame's window, shared with the arrangement half");
  assert.ok(FED.indexOf('if (m && m.type === "viewOrder") {') < FED.indexOf('if ("folds" in m) {') && /if \(m && m\.type === "viewOrder"\) \{\s*\n\s*if \(host !== LOCAL\) return;/.test(FED),
    "a remote kernel's folds are never adopted: they belong to whoever sits in front of that machine");
  assert.doesNotMatch(FED.slice(FED.indexOf("  start(): void {"), FED.indexOf("this.poll();", FED.indexOf("  start(): void {"))), /__rompPublishViewFolds =|__rompPublishViewOrder =/,
    "start() installs no publisher of either half: a page speaks for the folds and the order only once it has heard them");
  assert.match(FED, /w\.__rompWriteTabGroups = \(blob: unknown\) => writeTabGroups\(parseTabGroups\(JSON\.stringify\(blob \?\? \{\}\)\)\);/, "the raw timeline view's one write");
  // a VS Code chat webview: its own frame branch, publishing through its host pipe
  assert.match(RENDER, /if \("folds" in m\) hearSharedFolds\(m\.folds, \(f\) => vscodeApi\?\.postMessage\(\{ type: "setViewFolds", folds: f \}\), setFoldsPublisher\);/);
});

test("the folds' publisher is the CURRENT connection's: a drop withdraws it with the arrangement's, on every kind of page", () => {
  // the order half's per-connection gate (#2062): the viewOrder frame grants both publishers and a drop withdraws both, so a
  // page reconnecting after an outage cannot publish a stale fold copy before it hears the kernel's current one (executed
  // end to end in federation-shared-folds.test.ts: the reconnect and the offline fold)
  const unhear = FED.slice(FED.indexOf("private unhearViewOrder(): void {"), FED.indexOf("private lastFeedCounts"));
  assert.match(unhear, /delete \(window as any\)\.__rompPublishViewOrder;/);
  assert.match(unhear, /delete \(window as any\)\.__rompPublishViewFolds;/, "the socket's drop (romp:wsdown) and a new connection (wsup) withdraw the folds' too");
  assert.match(FED, /w\.addEventListener\("romp:wsdown", \(\) => this\.unhearViewOrder\(\)\);/);
  assert.match(FED, /if \(m && m\.type === "wsup" && host === LOCAL\) this\.unhearViewOrder\(\);/);
  // the VS Code chat webview's pipe going down withdraws both of its publishers
  assert.match(RENDER, /if \(m\.type === "pipeState" && !m\.up && paneArranges\(window as any\)\) \{ setViewOrderPublisher\(null\); setFoldsPublisher\(null\); \}/);
});
