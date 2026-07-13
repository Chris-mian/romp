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
import { installDomHelpers, dispatchFrame, openExternalMessage, bridgeFunctions } from "./timeline-boot";

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
  };
  assert.equal(dispatchFrame(panel, { type: "data", data: { lanes: [] } }), true);
  assert.equal(dispatchFrame(panel, { type: "bars" }), true);
  assert.equal(dispatchFrame(panel, { type: "activeChat", activeChat: "s1" }), true);
  assert.equal(dispatchFrame(panel, { type: "hover", sid: "s1" }), true);
  assert.equal(dispatchFrame(panel, { type: "ka" }), false);
  assert.equal(dispatchFrame(null, { type: "data" }), false);
  assert.deepEqual(calls.map((c) => c[0]), ["update", "applyBars", "setActiveChat", "setHover"]);
});

test("dispatchFrame tolerates a panel without the optional methods", () => {
  const panel = { update: () => {} };
  assert.equal(dispatchFrame(panel, { type: "bars" }), false);
  assert.equal(dispatchFrame(panel, { type: "hover" }), false);
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
  b.__rompTimelineWriteOrder(["a", "b"]);
  b.__rompTimelineCompact("sess");
  b.__rompTimelineSendCommand("sess", "/model");
  b.__rompTimelineSetFlag("id1", "eye", 1);
  b.__rompTimelineDismiss("id2");
  b.__rompTimelineHover("s1", ["g1"], 5, 9);
  b.__rompTimelineHover();
  assert.deepEqual(sent, [
    { type: "writeOrder", order: ["a", "b"] },
    { type: "compact", name: "sess" },
    { type: "sendCommand", name: "sess", cmd: "/model" },
    { type: "setSessionFlag", id: "id1", flag: "eye", value: true },
    { type: "dismissLane", id: "id2" },
    { type: "timelineHover", sid: "s1", segIds: ["g1"], t0: 5, t1: 9 },
    { type: "timelineHover", off: true },
  ]);
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
