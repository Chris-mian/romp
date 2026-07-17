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

test("the hover acknowledgement is ATOMIC on BOTH handles — dot and strip share instantLocalBand", () => {
  // the user 2026-07-17: hovering a dot lit the dot at once but the related lines lagged by the 120ms
  // intent debounce + a round-trip. The local band now draws SYNCHRONOUSLY in both mouseenter handlers,
  // BEFORE the debounced cross-surface message; the kernel's full-segment band still replaces it on
  // fan-back. mouseleave clears it through the shared helper too.
  const fn = SRC.slice(SRC.indexOf("function wireTurnHover"), SRC.indexOf("function applyGlow"));
  const enters = fn.match(/addEventListener\("mouseenter", \(\) => \{\s*\n\s*(?:\/\/[^\n]*\n\s*)*instantLocalBand\(turn\);/g) || [];
  assert.equal(enters.length, 2, "dot AND rail strip mouseenter both open with the instant local band");
  const leaves = fn.match(/addEventListener\("mouseleave", \(\) => \{\s*\n\s*clearLocalBand\(\);/g) || [];
  assert.equal(leaves.length, 2, "both mouseleave handlers clear through the shared helper");
  // the instant band precedes the debounce timer in source order within each enter handler
  assert.ok(fn.indexOf("instantLocalBand(turn);") < fn.indexOf("timer = setTimeout"), "local ack before the debounce");
});

test("one hover language: thicken/expand IN OWN COLOR — no white rings anywhere on the rail", () => {
  // the user 2026-07-17 (superseding the white-ring capsule): a hovered/lit dot EXPANDS with its own
  // background color; the band is the rail itself THICKENED in the rail color. No white box-shadows.
  assert.match(CSS, /\.dot\.dot-nav:hover \{ transform: scale\(1\.45\); z-index: 3; \}/);
  assert.match(CSS, /\.dot\.rail-ring \{ transform: scale\(1\.45\); z-index: 3; \}/);
  assert.match(CSS, /\.turn\.ext-glow \.dot \{ transform: scale\(1\.45\); z-index: 3; \}/);
  assert.match(CSS, /\.rail-band \{[^}]*background: var\(--active-accent, var\(--rail\)\)/);
  assert.doesNotMatch(CSS, /\.dot\.dot-nav:hover \{[^}]*box-shadow/);
  assert.doesNotMatch(CSS, /\.dot\.rail-ring \{[^}]*box-shadow/);
  assert.doesNotMatch(CSS, /\.rail-band \{[^}]*box-shadow/);
});

test("every band edge lands ON A DOT — and ONLY between dots (no lineless glow)", () => {
  // the user 2026-07-02 ×3 + 2026-07-03: box-boundary edges read as arbitrary cuts, and the box-bottom
  // fallback painted glow over the LINELESS stub after the last event. The band now exists solely
  // between dots: no bounding dot → clamp to the run's own dots; none at all → no band.
  assert.match(SRC, /function railDotAbove\(turn: HTMLElement, hostR: DOMRect\)/);
  assert.match(SRC, /function railDotBelow\(turn: HTMLElement, hostR: DOMRect\)/);
  const fn = SRC.slice(SRC.indexOf("function paintRailBand"), SRC.indexOf("function paintGlowRuler"));
  assert.match(fn, /const top = railDotAbove\(first, hostR\) \?\? railDotBelow\(first, hostR\);/);
  assert.match(fn, /const bottom = railDotBelow\(last, hostR\) \?\? railDotAbove\(last, hostR\);/);
  assert.match(fn, /if \(top == null \|\| bottom == null\) continue;/, "no dots → no band, never a box edge");
  assert.match(SRC, /paintRailBand\(\);\s*\/\/ one continuous measured band/, "painted with every glow application");
  assert.match(CSS, /\.rail-band \{ position: absolute; width: 4px;/, "the thickened-rail band (4px vs the rail's 2px)");
  assert.match(CSS, /\.rail-band \{[^}]*pointer-events: none/, "the band never intercepts the strip's hover");
  assert.doesNotMatch(CSS, /\.turn\.ext-glow::before|\.turn\.rail-glow::before/, "no per-turn slice glows remain");
});

test("band runs still break at each dot, and the dot GROWS to take over the joint", () => {
  // geometry kept from the capsule era (the user 2026-07-03: nothing may cross through a dot): runs stop
  // RAIL_DOT_CLEAR short of every dot in range; the dot, scaled 1.45, covers the clearance gap so the
  // thick line reads continuous into the grown disc.
  assert.match(SRC, /const RAIL_DOT_CLEAR = 7;/);
  assert.match(SRC, /function railDotsBetween\(host: HTMLElement, hostR: DOMRect, top: number, bottom: number\)/);
  assert.match(SRC, /const stops = \[top, \.\.\.dots\.map\(\(d\) => d\.y\), bottom\];/);
  assert.match(SRC, /d\.el\.classList\.add\("rail-ring"\);/, "every dot along the band grows via .rail-ring");
});

test("the hover strip exists only where the line does (the last turn's 16px stub)", () => {
  // "no .turn after me", never :last-child — appended .rail-band siblings broke that match mid-hover,
  // snapping a full-height line over the final text (the user 2026-07-03)
  assert.match(CSS, /\.turn:not\(:has\(~ \.turn\)\) \.rail-hit \{ bottom: auto; height: 16px; \}/);
  assert.match(CSS, /\.turn:not\(:has\(~ \.turn\)\)::before \{ bottom: auto; height: 16px; \}/);
  assert.doesNotMatch(CSS, /\.turn:last-child::before/, "the fragile :last-child stub is gone");
  // local hover past the last dot draws nothing — there is no complete inter-dot span there
  const wire = SRC.slice(SRC.indexOf("function wireTurnHover"), SRC.indexOf("function applyGlow"));
  assert.match(wire, /if \(top != null && bottom != null\) drawRailBand\(host, hostR, turn, top, bottom, true\);/);
});

test("the strip hugs the line and never steals the dot's hover", () => {
  assert.match(CSS, /\.rail-hit \{ position: absolute; left: 7px; top: 0; bottom: 0; width: 9px; cursor: pointer; z-index: 0; \}/);
  assert.match(CSS, /\.dot\.dot-nav \{ cursor: pointer; z-index: 1; \}/, "the dot stacks above the strip");
});
