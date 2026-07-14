// The romp strip — the VS Code stand-in for the web shell's bottom rail
// (usage bar-pairs + the settings gear below the chat composer / feed foot).
// Pure helpers tested directly; the host opt-in + feed-over-chat wiring is
// source-pinned (chat-view/src/host-chrome.test.ts covers the builders).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { usageColor, fmtReset, usageWindows, STRIP_PANES } from "./strip";

test("usageColor mirrors the rail's green/amber/red ramp", () => {
  assert.equal(usageColor(0), "#54B204");
  assert.equal(usageColor(69), "#54B204");
  assert.equal(usageColor(70), "#e0b020");
  assert.equal(usageColor(89), "#e0b020");
  assert.equal(usageColor(90), "#c0392b");
});

test("fmtReset renders d/h/m compactly and 'soon' at rollover", () => {
  assert.equal(fmtReset(10_000, 10_100), "soon");
  assert.equal(fmtReset(10_000 + 5 * 60, 10_000), "5m");
  assert.equal(fmtReset(10_000 + 2 * 3600 + 5 * 60, 10_000), "2h 5m");
  assert.equal(fmtReset(10_000 + 86400 + 3600, 10_000), "1d 1h 0m");
});

test("usageWindows keeps only reported windows, clamps, and computes pace", () => {
  const nowS = 100_000;
  const ws = usageWindows({
    fiveHour: { pct: 91, resetsAt: nowS + 3600 },        // 1h left of 5h → 80% elapsed
    fable: { pct: 120, resetsAt: nowS + 7 * 86400 },     // over-reported → clamped, 0% elapsed
  }, nowS);
  assert.deepEqual(ws.map((w) => w.key), ["fiveHour", "fable"]);
  assert.deepEqual(ws.map((w) => w.short), ["5h", "F5"], "each window carries its compressed tag");
  assert.equal(ws[0].pct, 91);
  assert.equal(ws[0].elapsedPct, 80);
  assert.match(ws[0].title, /5 hours — used 91% · 80% through the window · resets in 1h 0m/);
  assert.equal(ws[1].pct, 100);
  assert.equal(ws[1].elapsedPct, 0);
});

test("a window that reset since the last report reads 0, not stale", () => {
  const ws = usageWindows({ fiveHour: { pct: 91, resetsAt: 50 } }, 100);
  assert.equal(ws[0].pct, 0);
});

test("no usage → no windows (the strip stays quiet, never fakes bars)", () => {
  assert.deepEqual(usageWindows(null, 100), []);
  assert.deepEqual(usageWindows({}, 100), []);
});

test("the strip carries the rail's controls: refresh, network popover, pane quick-opens", () => {
  const src = fs.readFileSync(path.join(path.resolve(process.cwd(), ".."), "ui", "webview", "strip.ts"), "utf8");
  assert.ok(src.includes('"/restart"') || src.includes("/restart`"), "the refresh button restarts the kernel");
  for (const ep of ["/ssh-hosts", "/tunnels", "/tunnels/detach", "/tunnels/update", "/tunnels/start"])
    assert.ok(src.includes(ep), `the network popover must drive ${ep} (the rail twin)`);
  assert.ok(src.includes('{ type: "openPane", pane: p.key }'), "quick-opens post openPane to the host");
});

test("the strip quick-opens cover chat/outline/feed only (timeline is a native panel)", () => {
  assert.deepEqual(STRIP_PANES.map((p) => p.key), ["chat", "fleet", "feed"]);
  assert.deepEqual(STRIP_PANES.map((p) => p.label), ["Chat", "Outline", "Feed"]);
});

// A narrow pane must NEVER grow a horizontal scrollbar under the strip (the
// user 2026-07-13): the strip is a size container whose @container ladder
// compresses the usage windows tier by tier, and flex-wrap folds whatever
// still doesn't fit onto another row.
test("the strip compresses through concise tiers and wraps instead of overflowing", () => {
  const ROOT = path.resolve(process.cwd(), "..");
  const css = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.css"), "utf8");
  const stripRule = css.match(/#romp-strip \{[^}]*\}/)![0];
  assert.ok(stripRule.includes("container: romp-strip / inline-size"), "the strip is a named size container (zoom-safe, unlike media queries)");
  assert.ok(stripRule.includes("flex-wrap: wrap"), "the wrap backstop: leftover buttons take another row");
  const tiers = [...css.matchAll(/@container romp-strip \(max-width: (\d+)px\)/g)].map((m) => Number(m[1]));
  assert.equal(tiers.length, 3, "three compress tiers below the full layout");
  assert.deepEqual([...tiers].sort((a, b) => b - a), tiers, "tiers narrow monotonically");
  // ladder order: first the label compresses to its tag, then the % readout goes, then the label entirely
  const after = (w: number) => css.slice(css.indexOf(`(max-width: ${w}px)`));
  assert.ok(after(tiers[0]).includes(".ru-name-full { display: none; }"), "tier 1 swaps the expanded label for the tag");
  assert.ok(after(tiers[1]).includes(".ru-pct { display: none; }"), "tier 2 drops the % readout");
  assert.ok(after(tiers[2]).includes(".ru-name { display: none; }"), "tier 3 drops labels — bars only");
  const src = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");
  assert.ok(src.includes('"ru-name-full"') && src.includes('"ru-name-short"'), "both label variants render; CSS picks one");
  assert.ok(src.includes('"strip-acts"'), "the actions travel as one right-pinned cluster");
  assert.ok(!src.includes("strip-spacer"), "no spacer item — margin-left:auto keeps the pin across wrapped rows");
});

test("the feed's control bar wraps on a narrow pane instead of overflowing", () => {
  const ROOT = path.resolve(process.cwd(), "..");
  const css = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.css"), "utf8");
  const foot = css.match(/#feed-foot \{[^}]*\}/)![0];
  assert.ok(foot.includes("flex-wrap: wrap"), "#feed-foot must fold its buttons onto another row");
});

test("the chat hosts its OWN gear modal (opens over the pane it was clicked in)", () => {
  const ROOT = path.resolve(process.cwd(), "..");
  const render = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
  assert.ok(render.includes('require("./gear.js")'), "chat bundle must load the gear module");
  assert.ok(!render.includes("openRompSettings"), "no cross-pane settings hop remains");
});

test("both bundles init the strip; the web pages never opt in", () => {
  const ROOT = path.resolve(process.cwd(), "..");
  const read = (f: string) => fs.readFileSync(path.join(ROOT, "ui", "webview", f), "utf8");
  assert.ok(read("render.ts").includes("initStrip("), "chat bundle must init the strip");
  assert.ok(read("feed.ts").includes("initStrip("), "feed bundle must init the strip");
  const kernel = fs.readFileSync(path.join(ROOT, "bin", "romp-kernel"), "utf8");
  assert.ok(!kernel.includes("__rompShowStrip"), "the web shell keeps its own rail — no strip opt-in kernel-side");
});
