// The chat rail LINE is a nav handle like its dots (the user 2026-07-02): hovering exactly on a turn's
// rail segment lights it with the same expanding white ring the dots use (.dot-nav:hover) and drives the
// same timeline/feed cross-highlight (same dotHover payload, same 120ms intent debounce). The line is the
// turn's ::before pseudo — no pointer events — so render.ts overlays a slim .rail-hit strip; the dot's
// enlarged hit pad stacks above it, so the dot wins where they overlap. Source pins (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("every nav-able turn grows a rail hit strip, wired like the dot", () => {
  const fn = SRC.slice(SRC.indexOf("function wireTurnHover"), SRC.indexOf("function applyGlow"));
  assert.match(fn, /const rail = el\("div", "rail-hit"\);/);
  assert.match(fn, /turn\.appendChild\(rail\);/, "created inside wireTurnHover — only turns with nav data get one");
  // the SAME dotHover payload + the same 120ms intent debounce as the dot hover
  assert.match(fn, /railTimer = setTimeout\(\(\) => \{ railTimer = undefined; if \(activeId\) vscodeApi\?\.postMessage\(\{ type: "dotHover", sid: activeId, uuid, t, tlId \}\); \}, 120\);/);
  // instant feedback is a dot-anchored band too — never the old per-turn slice that flashed an
  // arbitrary chopped bit before the segment band landed (the user 2026-07-02 ×3)
  assert.match(fn, /const top = railDotAbove\(turn, hostR\)/);
  assert.match(fn, /drawRailBand\(host, hostR, turn, top, bottom, true\);/);
  assert.doesNotMatch(fn, /rail-glow/, "the box-bounded slice glow is gone");
});

test("the band's glow is the dots' expanding white ring — one visual language", () => {
  assert.match(CSS, /\.dot\.dot-nav:hover \{ box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\); \}/);
  assert.match(CSS, /\.rail-band \{[^}]*box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\)/);
});

test("every band edge lands ON A DOT — the rail's only meaningful y-coordinates", () => {
  // the user 2026-07-02 ×3: box-boundary edges and uuid-gap slices read as arbitrary cuts. railDotAbove/
  // railDotBelow WALK to the nearest dot (up from the band's first turn, down past its last); turn-box
  // edges remain only as the transcript-end fallback where no bounding dot exists.
  assert.match(SRC, /function railDotAbove\(turn: HTMLElement, hostR: DOMRect\)/);
  assert.match(SRC, /function railDotBelow\(turn: HTMLElement, hostR: DOMRect\)/);
  const fn = SRC.slice(SRC.indexOf("function paintRailBand"), SRC.indexOf("function paintGlowRuler"));
  assert.match(fn, /const top = railDotAbove\(first, hostR\) \?\? \(first\.getBoundingClientRect\(\)\.top - hostR\.top\);/);
  assert.match(fn, /const bottom = railDotBelow\(last, hostR\) \?\? \(last\.getBoundingClientRect\(\)\.bottom - hostR\.top\);/);
  assert.match(SRC, /paintRailBand\(\);\s*\/\/ one continuous measured band/, "painted with every glow application");
  assert.match(CSS, /\.rail-band \{ position: absolute; width: 2px;[^}]*box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\)/);
  assert.match(CSS, /\.rail-band \{[^}]*pointer-events: none/, "the band never intercepts the strip's hover");
  assert.doesNotMatch(CSS, /\.turn\.ext-glow::before|\.turn\.rail-glow::before/, "no per-turn slice glows remain");
});

test("the strip hugs the line and never steals the dot's hover", () => {
  assert.match(CSS, /\.rail-hit \{ position: absolute; left: 7px; top: 0; bottom: 0; width: 9px; cursor: pointer; z-index: 0; \}/);
  assert.match(CSS, /\.dot\.dot-nav \{ cursor: pointer; z-index: 1; \}/, "the dot stacks above the strip");
});
