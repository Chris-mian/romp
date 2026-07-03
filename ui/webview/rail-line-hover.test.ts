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
  assert.match(fn, /turn\.classList\.add\("rail-glow"\);/, "the line lights up immediately on hover");
  assert.match(fn, /turn\.classList\.remove\("rail-glow"\);/);
});

test("the line's glow is the dots' expanding white ring, on the ::before segment", () => {
  assert.match(CSS, /\.turn\.rail-glow::before \{ box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\); opacity: 1; \}/);
  // same ring the dot hover uses — one visual language
  assert.match(CSS, /\.dot\.dot-nav:hover \{ box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\); \}/);
});

test("the cross-highlight lights the WHOLE segment's line as one contiguous band", () => {
  // the kernel's glowTurns fan-back marks every turn of the hovered segment (.ext-glow); each marked
  // turn's rail slice must glow too, or the band reads chopped (the user 2026-07-02)
  assert.match(CSS, /\.turn\.ext-glow::before \{ box-shadow: 0 0 0 2px rgba\(255, 255, 255, 0\.85\); opacity: 1; \}/);
});

test("the strip hugs the line and never steals the dot's hover", () => {
  assert.match(CSS, /\.rail-hit \{ position: absolute; left: 7px; top: 0; bottom: 0; width: 9px; cursor: pointer; z-index: 0; \}/);
  assert.match(CSS, /\.dot\.dot-nav \{ cursor: pointer; z-index: 1; \}/, "the dot stacks above the strip");
});
