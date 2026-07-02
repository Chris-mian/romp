// A compacting session shows a tiny animated compaction BAR before its name in the chat tab — that state
// gets no tab outline, so the bar is the cue. It's a teal fill whose right edge slides left and loops (the
// same compression motion as the statusline ctx-scan bar, miniaturised), so it reads as a transient PROCESS
// not a status colour. Replaces the static ⇲ glyph (and, before that, the colour 🗜 clamp emoji) the user
// disliked (2026-06-24). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("compacting tab gets an animated compaction bar before the name (NOT the static ⇲ glyph or 🗜 emoji)", () => {
  assert.match(RENDER, /if \(st === "compacting"\) \{/);
  assert.match(RENDER, /el\("span", "tab-compacting-bar"\)/);
  assert.match(RENDER, /el\("span", "tab-compacting-fill"\)/);
  assert.doesNotMatch(RENDER, /ci\.textContent = "⇲"/, "the old static compress glyph is gone");
  assert.doesNotMatch(RENDER, /ci\.textContent = "🗜"/, "the old colour clamp emoji is gone");
  assert.match(CSS, /\.tab-compacting-bar \{/);
  // the fill loops the compression animation — motion is what conveys "compacting"
  assert.match(CSS, /animation: tab-compact /);
  assert.match(CSS, /@keyframes tab-compact \{/);
});

test("the tab compaction sweep is armed with applyCompactSweep (phase-sync + colormap gradient)", () => {
  // the fill is armed before being appended, so it survives renderTabs()' replaceChildren() rebuilds
  assert.match(RENDER, /const cfill = el\("span", "tab-compacting-fill"\);\s*\n\s*applyCompactSweep\(cfill\);/);
  // the statusline battery scan is armed too (its ctx-compress runs 3.2s, so the duration is passed)
  assert.match(RENDER, /applyCompactSweep\(scan, 3200\)/);
});

test("applyCompactSweep phase-syncs across re-renders via a negative wall-clock animation-delay (no restart)", () => {
  // renderTabs()/updateStatusline() recreate the element every push; a plain CSS animation would reset to
  // frame 0 each time (the hiccup). A negative delay of -(now mod duration) makes the phase a pure function
  // of the wall clock, so a freshly-built element resumes exactly where the destroyed one was.
  assert.match(RENDER, /function applyCompactSweep\(fillEl: HTMLElement, durationMs = 1600\)/);
  assert.match(RENDER, /fillEl\.style\.animationDelay = `-\$\{Date\.now\(\) % durationMs\}ms`/);
});

test("the compaction sweep mirrors the context colormap: ramp() sampled into --cmp0…--cmp4 vars", () => {
  // widest width = the map's full/100% colour (--cmp4 = ramp(1.0)); narrowing toward its 0% colour
  // (--cmp0 = ramp(0.12)) — the SAME map the battery fill uses.
  assert.match(RENDER, /fillEl\.style\.setProperty\("--cmp0", rgb\(0\.12\)\)/);
  assert.match(RENDER, /fillEl\.style\.setProperty\("--cmp4", rgb\(1\.0\)\)/);
  // the keyframes step through the vars (fallback to the flat compacting teal when unset)
  assert.match(CSS, /@keyframes tab-compact \{[\s\S]*?background: var\(--cmp4, var\(--st-compacting-bg\)\)[\s\S]*?background: var\(--cmp0, var\(--st-compacting-bg\)\)/);
  assert.match(CSS, /@keyframes ctx-compress \{[\s\S]*?var\(--cmp4, var\(--st-compacting-bg\)\)[\s\S]*?var\(--cmp0, var\(--st-compacting-bg\)\)/);
});
