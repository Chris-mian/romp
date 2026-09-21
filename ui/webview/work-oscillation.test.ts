// The "working" chip/badge breathes black→teal on a 1.5s sine clock — 2× the old 3s (the user
// 2026-06-16): the chat working chip and the timeline working chip. The working DOTS, by contrast,
// stay SOLID — their oscillation was distracting (the user 2026-06-16). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const TIMELINE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("chat working chip breathes on the 1.5s clock (2× the old 3s)", () => {
  assert.match(CSS, /\.chip-pulse::after \{[^}]*animation: chip-pulse 1\.5s/);
});

test("chat working chip breathes by OPACITY, not colour — the teal is a ::after layer over the black text (2026-09-21)", () => {
  // `color` is not a compositor property: animating it re-styled and repainted the glyphs every frame for
  // as long as a session worked (the Firefox GPU-process investigation, the user 2026-09-19). The element's
  // own text stays black; ::after repeats the label in teal from data-label and fades in and out.
  assert.match(CSS, /\.chip-pulse \{[^}]*color: #1a1a1a;[^}]*\}/);
  assert.doesNotMatch(CSS, /\.chip-pulse \{[^}]*animation/);
  assert.match(CSS, /\.chip-pulse::after \{[^}]*content: attr\(data-label\) \/ "";[^}]*color: #0d9488;[^}]*opacity: 0;/);
  assert.match(CSS, /@keyframes chip-pulse \{\s*0%, 100% \{ opacity: 0; \}[^\n]*\n\s*50% +\{ opacity: 1; \}/);
  assert.doesNotMatch(CSS, /@keyframes chip-pulse \{[^}]*color:/);
  // both sites that build the chip feed the ::after its text
  const sites = RENDER.split('el("span", "chip-pulse")').length - 1;
  assert.equal(sites, 2, "two chip construction sites");
  assert.equal(RENDER.split("label.dataset.label = CHIP_LABEL.working").length - 1, 2, "each sets data-label");
});

test("timeline working chip breathes on the SAME 1.5s clock — a persistent CSS overlay (the user 2026-07-01)", () => {
  // was an in-SVG SMIL <animate> that stuttered at the redraw cadence; now a compositor-driven overlay div,
  // same 1.5s ease-in-out-sine + same black↔teal tones as the chat chip's .chip-pulse — and, since
  // 2026-09-21, the same opacity crossfade: black text, a teal ::after layer fed by data-label.
  assert.match(TIMELINE, /\.romp-tl-work-label\{[^}]*color:#1a1a1a\}/);
  assert.doesNotMatch(TIMELINE, /\.romp-tl-work-label\{[^}]*animation/);
  assert.match(TIMELINE, /\.romp-tl-work-label::after\{content:attr\(data-label\) \/ "";position:absolute;inset:0;color:#0d9488;opacity:0;/);
  assert.match(TIMELINE, /animation:romp-tl-workpulse 1\.5s cubic-bezier\(0\.37,0,0\.63,1\) infinite\}/);
  assert.match(TIMELINE, /@keyframes romp-tl-workpulse\{0%,100%\{opacity:0\}50%\{opacity:1\}\}/);
  assert.doesNotMatch(TIMELINE, /@keyframes romp-tl-workpulse\{[^}]*color/);
  assert.match(TIMELINE, /lab\.textContent = text; lab\.dataset\.label = text;/);
  assert.doesNotMatch(TIMELINE, /attributeName: 'fill'/, "no per-draw-recreated SMIL breathe");
});

// Every `infinite` animation in the chat styles and the timeline breathes on the COMPOSITOR: its keyframes
// touch only opacity, transform and filter, so the loop repaints nothing for however long it runs. The
// exceptions below are named, each with why it stays; anything else that animates a paint property
// (color, background, width…) reds this pin. A named animation whose keyframes cannot be found in the
// same file FAILS too — a parse miss must never read as a pass (the 2026-09-21 review of PR 1984 found
// the first cut skipping blocks with a trailing comment and matching only a literal `color:`).
const COMPOSITOR_PROPS = new Set(["opacity", "transform", "filter"]);
const PAINT_EXCEPTIONS: Record<string, string> = {
  // tint an inline <mark> that spans line fragments (no clean overlay); run only while a reply is generating
  "cmt-busy-pulse": "styles.css", "cmt-busy-pulse-code": "styles.css",
  // the compaction sweep's colour ramp through the colormap stops (tab strip, statusline ctx bar, timeline
  // lane); runs only while a /compact is in flight (seconds), and the ramp IS the information
  "tab-compact": "styles.css", "ctx-compress": "styles.css", "romp-tl-compact": "romp-timeline-view.js",
};
// the keyframes block for `name`: the inner `pct { decls }` rules, with comments stripped first so a
// trailing `/* … */` after the last rule cannot defeat the match; null when the file has none
function keyframeProps(src: string, name: string): string[] | null {
  const bare = src.replace(/\/\*[\s\S]*?\*\//g, "");
  const m = bare.match(new RegExp(`@keyframes\\s+${name}\\s*\\{((?:[^{}]|\\{[^{}]*\\})*)\\}`));
  if (!m) return null;
  const props: string[] = [];
  for (const rule of m[1].matchAll(/\{([^{}]*)\}/g)) {
    for (const decl of rule[1].split(";")) {
      const prop = decl.split(":")[0].trim();
      if (prop) props.push(prop);
    }
  }
  return props;
}

test("every infinite animation in the chat styles and the timeline breathes on the compositor (opacity/transform/filter only)", () => {
  const seen = new Set<string>();
  for (const [src, label] of [[CSS, "styles.css"], [TIMELINE, "romp-timeline-view.js"]] as const) {
    const names = new Set([...src.matchAll(/animation:\s*([\w-]+)[^;}]*infinite/g)].map((m) => m[1]));
    assert.ok(names.size >= 5, `${label}: the infinite-animation scan found ${names.size} names — the pattern is broken`);
    for (const n of names) {
      const props = keyframeProps(src, n);
      assert.ok(props !== null, `${label}: @keyframes ${n} not found in the file that names it`);
      assert.ok(props.length > 0, `${label}: @keyframes ${n} parsed to no properties`);
      seen.add(n);
      const paint = props.filter((p) => !COMPOSITOR_PROPS.has(p));
      if (PAINT_EXCEPTIONS[n] === label) continue;   // a named, explained exception
      assert.deepEqual(paint, [], `${label}: @keyframes ${n} animates paint properties ${JSON.stringify(paint)}`);
    }
  }
  // the two chips this file is about are among the checked, and no exception is stale
  for (const n of ["chip-pulse", "romp-tl-workpulse"]) assert.ok(seen.has(n), `${n} was not scanned`);
  for (const n of Object.keys(PAINT_EXCEPTIONS)) assert.ok(seen.has(n), `exception ${n} names no infinite animation any more — drop it`);
});

test("the compositor pin has teeth: a colour step in a checked keyframes fails it", () => {
  const doctored = CSS.replace(/@keyframes chip-pulse \{/, "@keyframes chip-pulse {\n  25% { color: red; }");
  const props = keyframeProps(doctored, "chip-pulse");
  assert.ok(props && props.includes("color"), "the doctored step is parsed");
  assert.notDeepEqual(props!.filter((p) => !COMPOSITOR_PROPS.has(p)), []);
  // and a trailing comment after the last rule does not hide the block
  const commented = "@keyframes x { 0% { opacity: 0; }   /* a */\n 50% { color: red; }   /* b */\n}";
  assert.deepEqual(keyframeProps(commented, "x"), ["opacity", "color"]);
  assert.equal(keyframeProps("nothing here", "x"), null);
});

test("working DOTS are SOLID — no animation (oscillation was distracting)", () => {
  // chat tab dot + feed session-name dots carry no animation, and the dot keyframes are gone
  assert.doesNotMatch(CSS, /@keyframes work-dot/);
  assert.doesNotMatch(CSS, /\.tab-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /@keyframes fwork-dot/);
  assert.doesNotMatch(FEED_CSS, /\.fwork-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /\.ftree-who-dot \{[^}]*animation/);
});
