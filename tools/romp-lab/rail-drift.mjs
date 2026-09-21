#!/usr/bin/env node
// Permanent lab assertion (T129, the user 2026-08-27, screen recording: the transcript rail's
// side marks moved RELATIVE TO EACH OTHER while scrolling — geometrically impossible for a linear
// map): under PURE SCROLLING, every scroll-marks notch must hold its pairwise spacing — nothing
// moves relative to anything else. The fix made contentOffsetFrame a fully VIRTUAL frame (one
// cached-height prefix over all units), so a mark's rail position is independent of scrollTop and
// the render window; it changes only when information arrives (a height first measured, events
// appended). This script proves the invariant over the BUILT bundle:
//   pass 1 (down+up) PRIMES the height cache — remaps here are event-keyed learning, allowed;
//   pass 2 (down+up) is the assertion regime — zero drift, to sub-pixel rounding.
// Metric: per animation frame, normalize all mark tops to [0,1] over their span (a global rescale
// is legitimate — the native thumb does the same); drift = max over marks of the range of its
// normalized position across frames. Fails loud above TOLERANCE_PX.
//
// Usage: node rail-drift.mjs [--dist <dir>]   (defaults to ../../vscode-extension/dist)
// Hermetic: synthetic transcript (placeholder UUIDs, notes-api world), file:// page, no kernel.
import { createRequire } from "node:module";
import { mkdtempSync, writeFileSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const distArg = process.argv.indexOf("--dist");
const dist = resolve(distArg > 0 ? process.argv[distArg + 1] : join(here, "..", "..", "vscode-extension", "dist"));
const require2 = createRequire(join(dist, "..", "package.json"));
const { chromium } = require2("playwright");

const TOLERANCE_PX = 1.5;   // sub-pixel style rounding only; real drift measured 5.7px before the fix

const dir = mkdtempSync(join(tmpdir(), "rail-drift-"));
copyFileSync(join(dist, "render.js"), join(dir, "render.js"));
copyFileSync(join(dist, "styles.css"), join(dir, "styles.css"));
writeFileSync(join(dir, "page.html"), `<!DOCTYPE html>
<html><head><meta charset="utf-8"><link href="styles.css" rel="stylesheet"></head><body>
  <div id="winframe"></div>
  <div id="tabbar"><span id="tabs"></span></div>
  <div id="tabbar-resize"></div>
  <div id="ledger" style="display:none"></div>
  <div id="content"><div id="live-ask" style="display:none"></div></div>
  <div id="footer"><div id="composer-resize"></div><div id="statusline" class="statusline"></div>
  <div id="composer"><div id="composer-files" style="display:none"></div><div id="composer-staged" style="display:none"></div><div id="composer-chips" style="display:none"></div><textarea id="composer-input" rows="1"></textarea><button id="composer-attach"></button><button id="composer-send">➤</button></div></div>
<script>window.acquireVsCodeApi = function () { return { postMessage: function () {}, getState: function () { return {}; }, setState: function () {} }; };</script>
<script src="render.js"></script>
</body></html>`);

const frame = (o) => `window.dispatchEvent(new MessageEvent("message", { data: ${JSON.stringify(o)} }))`;
const S = "aaaaaaaa-1111-2222-3333-444444440001";
const events = [];
let u = 0;
const uid = () => "u-" + (++u);
for (let i = 0; i < 120; i++) {   // long MIXED transcript: virtualization + folds + height variety
  events.push({ kind: "user", md: "question " + i + " about the api behavior?", uuid: uid(), human: true });
  events.push({ kind: "assistant", md: i % 3 === 0
    ? ("A long answer. " + "The quick brown fox jumps over the lazy dog and explains the tradeoff in detail. ".repeat(6 + (i % 5)))
    : "Short answer " + i + ".", uuid: uid() });
  if (i % 2 === 0) for (let k = 0; k < 3; k++)
    events.push({ kind: "tool", name: "Bash", input: { command: "echo step-" + i + "-" + k }, output: "ok " + "line\n".repeat(1 + (k * 3)), uuid: uid() });
  if (i % 4 === 1) events.push({ kind: "assistant", md: "```python\n" + "x = compute(" + i + ")\nprint(x)\n".repeat(4) + "```", uuid: uid() });
}

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 700, height: 600 }, deviceScaleFactor: 1 });
p.on("pageerror", (e) => { console.error("PAGEERROR", e.message); process.exitCode = 1; });
await p.goto("file://" + join(dir, "page.html"));
await p.evaluate(frame({ type: "session", id: S, name: "web", cwd: "/home/demo/notes-api",
  status: { state: "idle", sinceEpoch: null, faded: false }, events }));
await p.evaluate(frame({ type: "tabOrder", order: [S], tabs: [{ id: S, name: "web", color: { bg: "#4dabf7", fg: "#111" } }] }));
await p.waitForSelector(".turn", { timeout: 8000 });
await p.waitForTimeout(500);
const samples = await p.evaluate(async () => {
  const content = document.getElementById("content");
  const marks = () => Array.from(document.querySelectorAll(".scroll-marks .scroll-mark")).map((m) => parseFloat(m.style.top));
  const raf = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const max = content.scrollHeight - content.clientHeight;
  const out = [];
  for (let dir2 = 0; dir2 < 4; dir2++) {           // two full round trips; the second is the assertion regime
    for (let k = 0; k <= 60; k++) {
      content.scrollTop = dir2 % 2 === 0 ? (max * k) / 60 : max - (max * k) / 60;
      content.dispatchEvent(new Event("scroll"));
      await raf(); await raf();
      out.push(marks());
    }
  }
  return out;
});
const railH = await p.evaluate(() => document.querySelector(".scroll-marks")?.getBoundingClientRect().height || 0);
await b.close();

const n = Math.min(...samples.map((s2) => s2.length));
if (!(n > 10)) { console.error("rail-drift: too few marks rendered (" + n + ")"); process.exit(1); }
const norm = samples.filter((s2) => s2.length === n).map((s2) => {
  const lo = Math.min(...s2), hi = Math.max(...s2);
  return s2.map((y) => (hi > lo ? (y - lo) / (hi - lo) : 0));
});
const driftOver = (frames) => {
  let worst = 0;
  for (let i = 0; i < n; i++) {
    const vals = frames.map((f) => f[i]);
    const d = Math.max(...vals) - Math.min(...vals);
    if (d > worst) worst = d;
  }
  return worst * railH;
};
const learnedPx = driftOver(norm.slice(Math.floor(norm.length / 2)));
const allPx = driftOver(norm);
console.log(JSON.stringify({ marks: n, frames: samples.length, railH: Math.round(railH),
  learnedRegimeDriftPx: +learnedPx.toFixed(2), allFramesDriftPx: +allPx.toFixed(2), tolerancePx: TOLERANCE_PX }));
if (learnedPx > TOLERANCE_PX) {
  console.error(`rail-drift FAIL: marks moved ${learnedPx.toFixed(2)}px relative to each other under pure scrolling (tolerance ${TOLERANCE_PX}px)`);
  process.exit(1);
}
console.log("rail-drift OK: pairwise positions invariant under pure scrolling");
