// Each chat tab wears a slim VERTICAL context gauge beside the session name (the user 2026-08-08):
// the statusline battery's fill % + global-colormap colour, rotated upright, no % text — so "this
// session is filling up" reads at a glance across the whole strip. Space for it comes from tightening
// the strip (inter-tab gap 0, smaller in-tab gap/padding), with the ✕ pushed to the tab's right edge
// by DOM order (dot · name · gauge · ✕). WHEN it shows is a gear → Chat picker (the user 2026-08-08
// v2, replacing the on/off toggle): only once ≥50% full (the DEFAULT — a gauge on every quiet tab is
// clutter), always, or never. Source-pin (no jsdom for the tab-bar draw path, like the sibling
// tab-*.test.ts); the mode normalization is pure and unit-tested directly.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { tabCtxMode, DEFAULT_SETTINGS } from "./settings";

const WEBVIEW = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(WEBVIEW, "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(WEBVIEW, "styles.css"), "utf8");
const SETTINGS = fs.readFileSync(path.join(WEBVIEW, "settings.ts"), "utf8");
const GEAR = fs.readFileSync(path.join(WEBVIEW, "gear.js"), "utf8");

const TW = fs.readFileSync(path.join(WEBVIEW, "tab-widgets.ts"), "utf8");   // the gauge is the CONTEXT BAR widget since T379 (the user 2026-09-12)

test("the context-bar widget renders the gauge after the label, gated on its option + a reported ctx%", () => {
  assert.match(TW, /if \(!status\.ctx \|\| st === "compacting" \|\| st === "closed"\) return null;/);
  // the 50% threshold: over50 (the default) shows the gauge only once it has news; the option "always" lifts it
  assert.match(TW, /if \(opts\.show !== "always" && pct < 50\) return null;/);
  assert.match(TW, /return tabCtxGauge\(status\.ctx, pickTone\(status\.ctxColor, status\.ctxTone\)\);/);   // dual palette (PR #763): the caller picks by theme
  // DOM order: label first, then the after-the-name widgets (the gauge), then the ✕ — so the ✕ sits at the tab's right edge
  const label = RENDER.indexOf("tab.appendChild(label);");
  const gauge = RENDER.indexOf("appendTabAfterWidgets(tab, s);");
  const close = RENDER.indexOf('const close = el("span", "tab-close");');
  assert.ok(label >= 0 && label < gauge && gauge < close, "expected label < gauge < close in renderTabs");
});

test("the gauge mirrors setCtxBar: clamped %, server ctxColor, the same traffic-light fallback", () => {
  assert.match(TW, /export function tabCtxGauge\(ctxStr: string, ctxColor\?: number\[\]\)/);
  assert.match(TW, /Math\.max\(0, Math\.min\(100, parseInt\(ctxStr, 10\) \|\| 0\)\)[\s\S]{0,400}fill\.style\.height = pct \+ "%"/);
  // colormap colour when the kernel ships one; setCtxBar's exact fallback ramp when it doesn't
  assert.match(TW, /tabCtxGauge[\s\S]{0,700}ctxColor && ctxColor\.length === 3\) \? `rgb\(\$\{ctxColor\.join\(","\)\}\)`\s*\n\s*: ctxFallbackColor\(pct\)/);   // theme-aware fallback; the FILL wears the tone as-is (readableRgb is for text — 2026-08-31)
});

test("the gauge is a slim VERTICAL bar and the strip tightened to make room for it", () => {
  // vertical: markedly taller than wide, fill anchored to the bottom
  const g = CSS.match(/\.tab-ctx \{[^}]*width: (\d+)px; height: (\d+)px/);
  assert.ok(g, ".tab-ctx must declare width+height");
  assert.ok(+g![1] < +g![2], `gauge must be vertical (w ${g![1]} < h ${g![2]})`);
  assert.match(CSS, /\.tab-ctx-fill \{ position: absolute; left: 0; right: 0; bottom: 0/);
  // the strip's spacing trade (the user 2026-08-08): inter-tab gap 0; in-tab gap/padding shrunk.
  // (The Yatharth theme reopens a 3px seam under its scope — tab-theme.test.ts pins that.)
  assert.match(CSS, /#tabs \{ display: flex; flex: 1 1 auto; flex-wrap: wrap; align-items: stretch; gap: 0; position: relative; \}/);
  assert.match(CSS, /\.tab \{[\s\S]{0,400}gap: 4px;[^\n]*\n\s*padding: 6px 7px;/);
});

test("the mode defaults to over50 and normalizes the boolean-era store", () => {
  assert.equal(DEFAULT_SETTINGS.tabCtx, "over50");
  assert.equal(tabCtxMode("always"), "always");
  assert.equal(tabCtxMode("never"), "never");
  assert.equal(tabCtxMode("over50"), "over50");
  assert.equal(tabCtxMode(false), "never", "boolean-era false was an explicit hide");
  assert.equal(tabCtxMode(true), "over50", "boolean-era true was the shipped default nobody chose");
  assert.equal(tabCtxMode(undefined), "over50", "a fresh store gets the default");
  // loadSettings applies it, so render/gear consumers always see a mode
  assert.match(SETTINGS, /s\.tabCtx = tabCtxMode\(s\.tabCtx\);/);
});

test("gear → Tabs: the Context bar widget's WHEN option (From 50% full / Always; off is the switch), persisted as tabWidgets and mirrored to settings.tabCtx", () => {
  // T379 (the user 2026-09-12): the picker is the Context bar row's option in the Chat tab's Tab widgets section, one of the widget rows gear.js
  // builds from tab-widgets.ts; the older tabCtx key is written back from the prefs so every older reader keeps its meaning
  assert.match(TW, /id: "ctx", label: "Context bar", defaultOn: true, slot: "after",/);
  assert.match(TW, /options: \[\{ key: "show", label: "Show", default: "over50",\s*\n\s*choices: \[\{ value: "over50", label: "From 50% full" \}, \{ value: "always", label: "Always" \}\] \}\],/);
  assert.doesNotMatch(GEAR, /id=rs-tabctx\b/, "the old Chat-section row is gone");
  assert.match(GEAR, /var drop = housePick\(wrap, 'wopt-' \+ w\.id \+ '-' \+ o\.key, widgetOptRowHTML,/, "the option is the panel's house picker");
  assert.match(GEAR, /s\.tabWidgets = prefs; s\.tabCtx = TW\.tabCtxOfPrefs\(prefs\); save\(s\);/, "the prefs and the mirror");
  assert.match(GEAR, /function tabCtxMode\(v\) \{ return \(v === 'always' \|\| v === 'never'\) \? v : \(v === false \? 'never' : 'over50'\); \}/, "the normalizer stays for the mirror's readers");
});

test("a gear change repaints the tab strip live, not on the next kernel push", () => {
  assert.match(RENDER, /onExternalSettingsChange\(\(s\) => \{ settings = s; applyChatScheme\(s\); renderTabs\(\); rerenderAll\(\); refillOpenCommentPop\(\); \}\)/);
});
