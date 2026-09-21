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

test("no infinite animation in the chat styles or the timeline animates `color` (compositor-only breathing)", () => {
  // every keyframe an `infinite` animation names must touch only compositor properties, except the two
  // comment busy-pulses, which tint an inline <mark> that spans line fragments (no clean overlay) and run
  // only while a reply is generating
  const allowed = new Set(["cmt-busy-pulse", "cmt-busy-pulse-code"]);
  for (const [src, label] of [[CSS, "styles.css"], [TIMELINE, "romp-timeline-view.js"]] as const) {
    const names = new Set([...src.matchAll(/animation:\s*([\w-]+)[^;}]*infinite/g)].map((m) => m[1]));
    for (const n of names) {
      if (allowed.has(n)) continue;
      const kf = src.match(new RegExp(`@keyframes ${n}\\s*\\{((?:[^{}]*\\{[^{}]*\\})*)\\s*\\}`));
      if (!kf) continue;   // keyframes defined in another file (feed.css, fleet-pane.css)
      assert.doesNotMatch(kf[1], /(^|[\s;{])color\s*:/, `${label}: @keyframes ${n} animates color`);
    }
  }
});

test("working DOTS are SOLID — no animation (oscillation was distracting)", () => {
  // chat tab dot + feed session-name dots carry no animation, and the dot keyframes are gone
  assert.doesNotMatch(CSS, /@keyframes work-dot/);
  assert.doesNotMatch(CSS, /\.tab-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /@keyframes fwork-dot/);
  assert.doesNotMatch(FEED_CSS, /\.fwork-dot \{[^}]*animation/);
  assert.doesNotMatch(FEED_CSS, /\.ftree-who-dot \{[^}]*animation/);
});
