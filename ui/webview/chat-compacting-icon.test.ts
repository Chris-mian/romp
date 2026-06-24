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
