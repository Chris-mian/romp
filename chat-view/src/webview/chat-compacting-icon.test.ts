// A compacting session shows a 🗜 compression icon before its name in the chat tab — that state gets
// no tab outline, so the icon is the cue (the user 2026-06-16). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("compacting tab gets a 🗜 icon before the name", () => {
  assert.match(RENDER, /if \(st === "compacting"\) \{/);
  assert.match(RENDER, /el\("span", "tab-compacting-icon"\); ci\.textContent = "🗜"/);
  assert.match(CSS, /\.tab-compacting-icon \{/);
});
