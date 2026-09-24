// timeline-boot: the VS Code timeline surface's glue between the shared
// TimelinePanel and the extension host. Pins three contracts:
//   1. the bridge set covers every __rompTimeline* global the VIEW calls
//      (ui/romp-timeline-view.js is the authority), and matches the kernel's
//      inline _TIMELINE_BOOT twin so web and VS Code can't drift;
//   2. each bridge/dispatch translates to the exact kernel op the web boot
//      sends (same frames, either host);
//   3. the kernel reads the extracted pane CSS files live (source-pin: undoing
//      the ui/webview/*-pane.css extraction breaks this test, not the pages).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { installDomHelpers, dispatchFrame, openExternalMessage, bridgeFunctions, writeTabGroupsBlob } from "./timeline-boot";
import { setFoldsPublisher } from "./tab-groups";
import { setViewOrderPublisher } from "./view-order";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "bin", "romp-kernel"), "utf8");
const VIEW = fs.readFileSync(path.join(ROOT, "ui", "romp-timeline-view.js"), "utf8");

function posts(): { sent: any[]; post: (m: any) => void } {
  const sent: any[] = [];
  return { sent, post: (m) => sent.push(m) };
}

// ---- 1. bridge-set pins ----

test("bridges cover every __rompTimeline* global the view calls", () => {
  const wanted = new Set(VIEW.match(/__rompTimeline[A-Za-z]+/g));
  assert.ok(wanted.size >= 7, "view should call the bridge globals");
  const provided = new Set(Object.keys(bridgeFunctions(() => {})));
  for (const name of wanted) assert.ok(provided.has(name), `missing bridge ${name}`);
});

test("bridge set matches the kernel's inline _TIMELINE_BOOT twin", () => {
  const bootStart = KERNEL.indexOf("_TIMELINE_BOOT = ");
  assert.ok(bootStart > 0, "kernel _TIMELINE_BOOT block not found");
  const boot = KERNEL.slice(bootStart, KERNEL.indexOf('"""', bootStart + 60));
  const kernelSet = new Set(boot.match(/__rompTimeline[A-Za-z]+/g));
  const ourSet = new Set(Object.keys(bridgeFunctions(() => {})));
  assert.deepEqual([...kernelSet].sort(), [...ourSet].sort());
});

// ---- 2. translation behavior (mirrors the web boot's frames) ----

test("dispatchFrame routes kernel frames to the panel", () => {
  const calls: any[] = [];
  const panel = {
    update: (d: any) => calls.push(["update", d]),
    applyBars: (m: any) => calls.push(["applyBars", m.type]),
    setActiveChat: (a: any) => calls.push(["setActiveChat", a]),
    setHover: (m: any) => calls.push(["setHover", m.type]),
    refreshModels: () => calls.push(["refreshModels"]),   // the kernel's models frame: the pick memory moved
    viewsAck: (m: any) => calls.push(["viewsAck", m.type, m.writeId]),   // the kernel's answer to one of this page's views writes
    setCaps: (m: any) => calls.push(["setCaps", m.caps]),                // what the kernel can do for this page (every `ready`)
    unknownOp: (m: any) => calls.push(["unknownOp", m.op, m.writeId]),  // an op the kernel does not know: a refusal, and the cap withdrawn
  };
  assert.equal(dispatchFrame(panel, { type: "data", data: { lanes: [] } }), true);
  assert.equal(dispatchFrame(panel, { type: "bars" }), true);
  assert.equal(dispatchFrame(panel, { type: "activeChat", activeChat: "s1" }), true);
  assert.equal(dispatchFrame(panel, { type: "hover", sid: "s1" }), true);
  assert.equal(dispatchFrame(panel, { type: "models", rev: 3 }), true);
  // the shim's socket-flip frame: a kernel restart is the documented way to change the extra models the API gateway
  // declares, and a restarted kernel sends no models frame for a list that changed while it was down, so the lane
  // menu re-reads /models on the reconnect the way the chat's picker and the gear already do (review find, 2026-09-22)
  assert.equal(dispatchFrame(panel, { type: "wsup" }), true, "the reconnect frame re-reads the model list too");
  assert.equal(dispatchFrame(panel, { type: "tagEditAck", writeId: "w1", ok: true }), true, "a targeted tag edit's ack");
  assert.equal(dispatchFrame(panel, { type: "viewsAck", writeId: "w2", ok: false }), true, "a whole-blob write's ack");
  assert.equal(dispatchFrame(panel, { type: "caps", caps: ["tagEdit"] }), true, "the kernel's capabilities");
  assert.equal(dispatchFrame(panel, { type: "unknownOp", op: "tagEdit", writeId: "w3" }), true, "an op the kernel does not know");
  assert.equal(dispatchFrame(panel, { type: "ka" }), false);
  assert.equal(dispatchFrame(null, { type: "data" }), false);
  assert.deepEqual(calls.map((c) => c[0]), ["update", "applyBars", "setActiveChat", "setHover", "refreshModels", "refreshModels", "viewsAck", "viewsAck", "setCaps", "unknownOp"],
    "a models frame and a wsup frame each land on refreshModels, once");
  assert.deepEqual(calls.slice(6), [["viewsAck", "tagEditAck", "w1"], ["viewsAck", "viewsAck", "w2"], ["setCaps", ["tagEdit"]], ["unknownOp", "tagEdit", "w3"]],
    "both acks land on the one panel door; caps and unknownOp on their own");
});

test("dispatchFrame tolerates a panel without the optional methods", () => {
  const panel = { update: () => {} };
  assert.equal(dispatchFrame(panel, { type: "bars" }), false);
  assert.equal(dispatchFrame(panel, { type: "hover" }), false);
  assert.equal(dispatchFrame(panel, { type: "models" }), false);
  assert.equal(dispatchFrame(panel, { type: "wsup" }), false, "an older view without refreshModels is skipped on the reconnect frame too, never thrown at");
});

test("the kernel's inline boot re-reads the model list on the shim's wsup frame too, so the browser timeline sees a restart", () => {
  // The browser's timeline shim fires {type:"wsup"} as a FRAME when its socket reopens (kernel.py ws.onopen), and the
  // chat (render.ts) and the gear (gear.js) re-read /models on it: a kernel restart is the documented way to change
  // ROMP_ROUTER_MODELS, and the restarted kernel sends no models frame for a list that changed while it was down. The
  // lane menu's arm lived on the models frame alone (review find, 2026-09-22); both boots take the reconnect frame now.
  const bootStart = KERNEL.indexOf("_TIMELINE_BOOT = ");
  const boot = KERNEL.slice(bootStart, KERNEL.indexOf('"""', bootStart + 60));
  assert.match(boot, /else if\(\(m\.type==="models"\|\|m\.type==="wsup"\)&&panel\.refreshModels\)panel\.refreshModels\(\);/,
    "the inline twin arms refreshModels on models and on wsup");
  const BOOT = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "timeline-boot.ts"), "utf8");
  assert.match(BOOT, /if \(\(m\.type === "models" \|\| m\.type === "wsup"\) && panel\.refreshModels\) \{ panel\.refreshModels\(\); return true; \}/,
    "…and the VS Code boot's dispatchFrame the same pair");
});

test("openExternalMessage unwraps a vscode:// deep link into the kernel deepLink op", () => {
  const m = openExternalMessage(
    "vscode://romp.romp-chat-view/open?session=abc&anchor=u1&anchorT=17&anchorKind=prompt&compose=1");
  assert.deepEqual(m, {
    type: "deepLink", session: "abc", anchor: "u1", anchorT: 17, anchorKind: "prompt", compose: true,
  });
});

test("openExternalMessage hands other URLs (and junk) to the host as openLink", () => {
  assert.deepEqual(openExternalMessage("https://example.com/x"), { type: "openLink", href: "https://example.com/x" });
  assert.deepEqual(openExternalMessage("not a url"), { type: "openLink", href: "not a url" });
});

test("bridges post the same kernel ops as the web boot", () => {
  const { sent, post } = posts();
  const b = bridgeFunctions(post);
  b.__rompTimelineCompact("sess");
  b.__rompTimelineSendCommand("sess", "/model");
  b.__rompTimelineSetFlag("id1", "eye", 1);
  b.__rompTimelineDismiss("id2");
  b.__rompTimelineHover("s1", ["g1"], 5, 9);
  b.__rompTimelineHover();
  b.__rompTimelineSetViews({ active: "all", tags: [] }, "w7");
  b.__rompTimelineTagEdit("w8", { op: "rename", tid: "g7", newName: "notes-api" });
  assert.deepEqual(sent, [
    { type: "compact", name: "sess" },
    { type: "sendCommand", name: "sess", cmd: "/model" },
    { type: "setSessionFlag", id: "id1", flag: "eye", value: true },
    { type: "dismissLane", id: "id2" },
    { type: "timelineHover", sid: "s1", segIds: ["g1"], t0: 5, t1: 9 },
    { type: "timelineHover", off: true },
    // the views writes carry the id the kernel's ack names; a targeted edit's op rides NESTED under
    // `edit`, so no field of it (a tag name) sits where the federation router reads session addresses
    { type: "setTimelineViews", views: { active: "all", tags: [] }, writeId: "w7", edited: [] },
    { type: "tagEdit", writeId: "w8", edit: { op: "rename", tid: "g7", newName: "notes-api" } },
  ]);
});

test("a lane drag posts the WHOLE arrangement to the local kernel, never a per-kernel writeOrder", () => {
  // Two rulings, and only one of them moved. The ORDER is still computed here, over every attached host
  // at once: a `writeOrder` op would hand each kernel a fragment of its own sids, which is exactly why
  // hosts could never interleave before 2026-07-31. What the kernel gets since 2026-09-23 is the finished
  // list, host prefixes and all, as opaque data to KEEP — so a drag here reaches the viewer's phone and
  // their other desktop instead of stopping at this webview (the user 2026-09-23).
  // …and only once this webview has HEARD the kernel's arrangement (review find on #2062, 2026-09-23): before
  // that the drag is kept pending and merged over the kernel's when its viewOrder frame arrives.
  // A webview that reloaded (its host's reconnect does that) holds the arrangement it cached and no publisher.
  const g: any = globalThis;
  const hadLS = "localStorage" in g, prevLS = g.localStorage;
  const store = new Map<string, string>([["romp:vieworder:shared", JSON.stringify(["TESTHOST:b", "a"])]]);
  g.localStorage = { getItem: (k: string) => (store.has(k) ? store.get(k)! : null), setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
  setViewOrderPublisher(null);
  try {
    const { sent, post } = posts();
    const bridges = bridgeFunctions(post);
    bridges.__rompTimelineWriteOrder(["a", "TESTHOST:b"]);
    assert.deepEqual(sent, [], "not heard yet: nothing published");
    // meanwhile another device added a session to the end; the frame carries that
    dispatchFrame({}, { type: "viewOrder", order: ["TESTHOST:b", "a", "c"], stored: true });
    assert.deepEqual(sent, [{ type: "setViewOrder", order: ["a", "TESTHOST:b", "c"] }],
      "the pending drag lands over the kernel's list, and the other device's session stays");
    bridges.__rompTimelineWriteOrder(["TESTHOST:b", "a", "c"]);
    assert.deepEqual(sent.at(-1), { type: "setViewOrder", order: ["TESTHOST:b", "a", "c"] }, "heard: a drag is published as it happens");
    assert.ok(!sent.some((m: any) => m.type === "writeOrder" || m.type === "reorderTabs"),
      "a kernel is never asked to order sids it does not know about");
  } finally {
    setViewOrderPublisher(null);
    if (hadLS) g.localStorage = prevLS; else delete g.localStorage;
  }
});

test("the VS Code timeline hears the kernel's FOLDS and, from then on, publishes a fold through its host pipe (2026-09-23)", () => {
  // the Sessions pane honours the tag groups' folds; in VS Code it has no federation manager, so the viewOrder frame's folds half
  // reaches dispatchFrame, and the view's own fold write (romp-timeline-view.js writeTabGroupsBlob → window.__rompWriteTabGroups,
  // which timeline-main.ts sets to writeTabGroupsBlob) publishes through `post` once the kernel's folds were heard
  const g: any = globalThis;
  const store = new Map<string, string>();
  const saved = [g.localStorage, g.window];
  g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
  g.window = new EventTarget();
  try {
    const { sent, post } = posts();
    bridgeFunctions(post);
    assert.equal(dispatchFrame({}, { type: "viewOrder", order: [], stored: false, folds: { collapsed: ["api"], expanded: [], pinned: [] } }), true, "the frame is the timeline's to take");
    assert.deepEqual(JSON.parse(store.get("romp:tabgroups:shared")!).collapsed, ["api"], "the kernel's folds adopted into this webview's store");
    assert.deepEqual(sent, [], "adopting publishes nothing");
    writeTabGroupsBlob({ on: true, collapsed: ["api", "web"], expanded: [], pinned: [], timeline: true });
    assert.deepEqual(sent, [{ type: "setViewFolds", folds: { collapsed: ["api", "web"], expanded: [], pinned: [] } }], "heard: the view's fold goes to the kernel");
    assert.equal(dispatchFrame({}, { type: "viewOrder", order: [], stored: true }), true, "a frame with no folds half (an older kernel): taken, nothing adopted");
  } finally {
    [g.localStorage, g.window] = saved;
    setFoldsPublisher(null);
    setViewOrderPublisher(null);   // the frame's arrangement half installed this webview's order publisher too
  }
});

test("installDomHelpers supplies the 3 Obsidian helpers", () => {
  (globalThis as any).document = {
    createElement: (tag: string) => ({
      tag, className: "", textContent: "", children: [] as any[],
      appendChild(c: any) { this.children.push(c); return c; },
    }),
  };
  try {
    const proto: any = {
      appendChild(c: any) { (this.children ??= []).push(c); return c; },
    };
    installDomHelpers(proto);
    const host: any = Object.create(proto);
    const d = proto.createDiv.call(host, { cls: "x", text: "hi" });
    assert.equal(d.tag, "div");
    assert.equal(d.className, "x");
    assert.equal(d.textContent, "hi");
    assert.equal(host.children.length, 1);
    assert.equal(proto.createSpan.call(host).tag, "span");
    // idempotent: a second install must not clobber existing helpers
    const before = proto.createEl;
    installDomHelpers(proto);
    assert.equal(proto.createEl, before);
  } finally {
    delete (globalThis as any).document;
  }
});

// ---- 3. shared pane CSS: files exist and the kernel reads them live ----

test("kernel reads the extracted pane CSS files (no inline twins left)", () => {
  assert.ok(fs.existsSync(path.join(ROOT, "ui", "webview", "timeline-pane.css")));
  assert.ok(fs.existsSync(path.join(ROOT, "ui", "webview", "fleet-pane.css")));
  assert.ok(KERNEL.includes('"timeline-pane.css"'), "kernel must read ui/webview/timeline-pane.css");
  assert.ok(KERNEL.includes('"fleet-pane.css"'), "kernel must read ui/webview/fleet-pane.css");
  assert.ok(!KERNEL.includes("_FLEET_CSS"), "inline _FLEET_CSS twin must stay deleted");
  assert.ok(!KERNEL.includes("TIMELINE_CSS ="), "inline TIMELINE_CSS twin must stay deleted");
});

test("the view prefers the host usage hook over the iframe-parent forward", () => {
  // In VS Code the webview's parent is the workbench wrapper — a parent
  // postMessage vanishes, so __rompForwardUsage (installed by timeline-main)
  // must win, keeping the toolbar copy hidden and feeding the status bar.
  const hook = VIEW.indexOf("__rompForwardUsage");
  const parentFwd = VIEW.indexOf("window.parent.postMessage({ romp: 'usage'");
  assert.ok(hook > 0, "view must honor __rompForwardUsage");
  assert.ok(parentFwd > 0, "web-shell forward must remain");
  assert.ok(hook < parentFwd, "the host hook must be checked before the parent forward");
});

// ---- 4. chat rail CLICK → pan + pulse the timeline (the user 2026-07-23) ----
// The click deliberately does NOT go through focusEvent, which also calls openChat: the click came from
// the chat, so that would scroll the pane the user is already reading back to where they clicked.

test("dispatchFrame routes revealEvent to the panel, passing (sid, t, id)", () => {
  const calls: any[] = [];
  const panel = { revealEvent: (sid: string, t: number, id: string) => calls.push([sid, t, id]) };
  assert.equal(dispatchFrame(panel, { type: "revealEvent", sid: "s1", t: 1700, id: "g7" }), true);
  assert.deepEqual(calls, [["s1", 1700, "g7"]]);
});

test("dispatchFrame ignores revealEvent on a panel too old to have it, rather than throwing", () => {
  assert.equal(dispatchFrame({}, { type: "revealEvent", sid: "s1", t: 1 }), false);
});

test("the kernel's inline boot dispatches revealEvent too, so the browser is not left behind", () => {
  // Two copies of this dispatch exist: timeline-boot.ts (VS Code webview) and the kernel's inline
  // _TIMELINE_BOOT (browser). A handler added to one and not the other is a silently half-shipped feature.
  const bootStart = KERNEL.indexOf("_TIMELINE_BOOT = ");
  const boot = KERNEL.slice(bootStart, KERNEL.indexOf('"""', bootStart + 60));
  assert.match(boot, /m\.type==="revealEvent"&&panel\.revealEvent\)panel\.revealEvent\(m\.sid,m\.t,m\.id\)/);
});

test("the view exposes revealEvent, and it never drives the chat", () => {
  const i = VIEW.indexOf("revealEvent(sid, t, id) {");
  assert.ok(i > 0, "the shared view must define revealEvent");
  const body = VIEW.slice(i, VIEW.indexOf("\n  }", i));
  assert.match(body, /this\._panToTime\(tt\)/, "it pans to the moment");
  assert.match(body, /this\._pulseFocus\(/, "...and pulses the glyph there");
  assert.doesNotMatch(body, /openChat/, "but never calls back into the chat the click came from");
});

test("dispatchFrame routes tagEditFailed to the panel — the LOUD half of remote-tag edits (federation v1)", () => {
  const got: any[] = [];
  const panel = { tagEditFailed: (m: any) => got.push(m) };
  assert.equal(dispatchFrame(panel, { type: "tagEditFailed", host: "TESTHOST-A", name: "team", error: "not reachable" }), true);
  assert.equal(got[0].error, "not reachable");
  assert.equal(dispatchFrame({}, { type: "tagEditFailed" }), false, "an older panel is skipped, never thrown at");
  // …and the kernel's inline boot + the editTag outbound hook stay mirrored (the pinned pair)
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  // (the listener body ends there; the boot registers it wrapped through the page's performance collector when one
  // is published on window.__rompPerf, the way every pane bundle wraps its own — perf-telemetry.ts)
  assert.match(KERNEL, /else if\(m\.type==="tagEditFailed"&&panel\.tagEditFailed\)panel\.tagEditFailed\(m\);\nelse if\(m\.type==="openViewsDialog"&&panel\._openViewsDialog\)panel\._openViewsDialog\(null\);\};\nvar frameListener=\(window\.__rompPerf&&window\.__rompPerf\.wrapFrameHandler\)\?window\.__rompPerf\.wrapFrameHandler\(onFrame\):onFrame;\nwindow\.addEventListener\("message",frameListener\);/);
  assert.match(KERNEL, /window\.__rompTimelineEditTag=function\(edit\)\{post\(\{type:"editTag",edit:edit\}\);\};/);
  const BOOT = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "timeline-boot.ts"), "utf8");
  assert.match(BOOT, /__rompTimelineEditTag: \(edit: unknown\) => post\(\{ type: "editTag", edit \}\),/);
});

