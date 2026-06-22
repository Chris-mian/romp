// A compacting session shows a ⇲ compress glyph before its name in the chat tab — that state gets
// no tab outline, so the glyph is the cue (the user 2026-06-16). It's MONOCHROME (⇲, U+21F2), not the
// old colour 🗜 clamp emoji, so it reads as a transient process not a status colour, and matches the
// ghostty tab dot's compacting glyph (the user 2026-06-22). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("compacting tab gets a monochrome ⇲ glyph before the name (NOT the colour 🗜 emoji)", () => {
  assert.match(RENDER, /if \(st === "compacting"\) \{/);
  assert.match(RENDER, /el\("span", "tab-compacting-icon"\); ci\.textContent = "⇲"/);
  assert.doesNotMatch(RENDER, /ci\.textContent = "🗜"/, "the old colour clamp emoji is gone");
  assert.match(CSS, /\.tab-compacting-icon \{/);
});
