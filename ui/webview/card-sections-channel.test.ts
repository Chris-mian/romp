// TWO DOCUMENTS OVER A REAL CHANNEL (the 0.17.1 fix, a contributor's third note on PR 2124): two bundles of card-sections.ts, an owner
// (the feed) and a follower (the chat page), joined by Node's BroadcastChannel the way the shell's two frames are joined by the browser's.
// The defect: a row pick outlived every feed map that lacked it, because the feed applied the row's set and answered nothing, so the chat
// page re-imposed and re-posted the pick and the feed persisted it again, per payload. With the acknowledgement: after a row pick the
// Collapsed flip leaves both documents empty, and five prunes after a row pick and Clear cost the owner one view-state write, not one per
// payload. The module reads `window.BroadcastChannel`, so the stand-in window hands it Node's class; the bundle is built here from the
// source, loaded twice through a cleared require cache (one bundle, two module instances), and both channels are closed at the end so the
// process can exit (Node's channel holds the event loop).
import { test, after } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { createRequire } from "node:module";
import { BroadcastChannel } from "node:worker_threads";

class T { nodeType = 3; parentNode: E | null = null; constructor(public textContent: string) {} }
class E {
  nodeType = 1; parentNode: E | null = null; childNodes: Array<E | T> = []; className = ""; title = ""; type = ""; isConnected = false;
  style: Record<string, string> = {}; dataset: Record<string, string | undefined> = {}; attrs = new Map<string, string>();
  constructor(public tagName: string) {}
  get classList() { const self = this; const set = () => new Set(self.className.split(/\s+/).filter(Boolean)); const write = (s: Set<string>) => { self.className = Array.from(s).join(" "); };
    return { add: (...cs: string[]) => { const s = set(); cs.forEach((c) => s.add(c)); write(s); }, remove: (...cs: string[]) => { const s = set(); cs.forEach((c) => s.delete(c)); write(s); },
             toggle: (c: string, on?: boolean) => { const s = set(); const want = on === undefined ? !s.has(c) : on; if (want) s.add(c); else s.delete(c); write(s); return want; }, contains: (c: string) => set().has(c) }; }
  get textContent(): string { return this.childNodes.map((n) => n.textContent).join(""); }
  set textContent(v: string | null) { this.childNodes = v ? [new T(v)] : []; }
  append(...ns: Array<E | T | string>) { for (const n of ns) this.childNodes.push(typeof n === "string" ? new T(n) : n); }
  appendChild(n: E | T) { this.childNodes.push(n); return n; }
  prepend(...ns: Array<E | T | string>) { this.childNodes.unshift(...ns.map((n) => typeof n === "string" ? new T(n) : n)); }
  replaceChildren(...ns: Array<E | T | string>) { this.childNodes = ns.map((n) => typeof n === "string" ? new T(n) : n); }
  setAttribute(k: string, v: string) { this.attrs.set(k, v); } getAttribute(k: string) { return this.attrs.get(k) ?? null; } removeAttribute(k: string) { this.attrs.delete(k); }
  querySelectorAll() { return [] as E[]; } querySelector() { return null; } addEventListener() {} removeEventListener() {}
}
(globalThis as any).document = { createElement: (tag: string) => new E(tag.toUpperCase()), createTextNode: (t: string) => new T(t), body: new E("BODY"), documentElement: new E("HTML"), addEventListener() {}, removeEventListener() {} };
(globalThis as any).window = { BroadcastChannel };   // the browser's channel, in Node's clothes

const tick = () => new Promise<void>((r) => setTimeout(r, 30));   // a delivery hop over Node's channel

// the bundle of the module under test, built ONCE per file at run time into one temporary directory, removed when the file's tests are done (the
// manager's read of the fix PR: a directory per test was never removed, three left per run); esbuild is loaded through a runtime require
// (createRequire), which the test bundler does not follow (its own API refuses to be bundled)
const req = createRequire(__filename);
let bundleDir: string | null = null, bundlePath: string | null = null;
function bundleOnce(): string {
  if (bundlePath) return bundlePath;
  const esbuild = req("esbuild");
  const src = path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.ts");
  bundleDir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-card-sections-"));
  bundlePath = path.join(bundleDir, "card-sections.js");
  esbuild.buildSync({ entryPoints: [src], bundle: true, format: "cjs", platform: "node", outfile: bundlePath, logLevel: "silent" });
  return bundlePath;
}
after(() => { if (bundleDir) fs.rmSync(bundleDir, { recursive: true, force: true }); bundleDir = bundlePath = null; });
function loadFresh(out: string): any { delete req.cache[req.resolve(out)]; return req(out); }
function twoDocuments(): { owner: any; follower: any; writes: { n: number } } {
  const out = bundleOnce();
  const owner = loadFresh(out); const follower = loadFresh(out);
  const writes = { n: 0 };
  owner.configureSectionSync({ role: "owner", onChange: () => { writes.n++; } });
  follower.configureSectionSync({ role: "follower" });
  return { owner, follower, writes };
}

test("a row pick then the Collapsed flip: both documents end empty (the pick was acknowledged, so the map that lacks it governs)", async () => {
  const { owner, follower, writes } = twoDocuments();
  try {
    await tick();                                                   // the hello and the load-time map
    follower.setSectionChoice("i1", "bg");                          // the row picks
    await tick();
    assert.equal(owner.secChoice.get("i1"), "bg", "the owner applied and persisted the row's pick");
    const afterPick = writes.n;
    owner.replaceSectionChoices([]);                                // the Collapsed clear
    await tick(); await tick();
    assert.deepEqual([owner.secChoice.size, follower.secChoice.size], [0, 0], "both documents empty after the flip (before: the follower re-imposed the pick and the owner persisted it again)");
    assert.equal(writes.n, afterPick + 1, "the flip is one write; nothing came back");
  } finally { owner.closeSectionSync(); follower.closeSectionSync(); }
});

test("a row pick then Clear: five prunes cost the owner one write, not one per payload", async () => {
  const { owner, follower, writes } = twoDocuments();
  try {
    await tick();
    owner.replaceSectionChoices([["i0", "stall"]]);                 // another item's standing pick, so the map is never the same as an empty one
    await tick();
    follower.setSectionChoice("i2", "bg");                          // the row picks
    await tick();
    const afterPick = writes.n;
    for (let i = 0; i < 5; i++) { owner.replaceSectionChoices([["i0", "stall"]], { quiet: true }); await tick(); }   // the prune, once the item left the live set, per payload
    assert.deepEqual([owner.secChoice.get("i2"), follower.secChoice.get("i2")], [undefined, undefined], "the dropped item is gone on both documents");
    assert.equal(writes.n, afterPick + 1, "one write for the five prunes (before: one per prune plus one per re-imposed pick)");
  } finally { owner.closeSectionSync(); follower.closeSectionSync(); }
});

test("a pick made before any owner is up still stands when the owner comes up and posts its map", async () => {
  const out = bundleOnce();
  const load = () => loadFresh(out);
  const follower = load(); follower.configureSectionSync({ role: "follower" });
  follower.setSectionChoice("i3", "subgoals");                       // nobody hears it
  await tick();
  const owner = load(); owner.replaceSectionChoices([["i9", "bg"]], { quiet: true }); owner.configureSectionSync({ role: "owner" });   // the feed hydrates (no post: not yet the owner) and, configured, posts its map
  try {
    await tick(); await tick(); await tick();   // the map, the follower's re-post, the acknowledgement
    assert.deepEqual([follower.secChoice.get("i3"), follower.secChoice.get("i9")], ["subgoals", "bg"], "the follower took the map and kept its own pick");
    assert.equal(owner.secChoice.get("i3"), "subgoals", "and the owner has the pick, re-posted and acknowledged");
    owner.replaceSectionChoices([]);
    await tick(); await tick();
    assert.deepEqual([owner.secChoice.size, follower.secChoice.size], [0, 0], "and, acknowledged, it yields to a later map that lacks it");
  } finally { owner.closeSectionSync(); follower.closeSectionSync(); }
});
