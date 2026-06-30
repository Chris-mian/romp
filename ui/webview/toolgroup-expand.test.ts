// Expanding a compact tool-group reveals the GROUPED TOOLS only — never the thinking that sat between them.
// Compact mode's whole promise is "hide thinking"; the expansion used to render the contiguous start..end span,
// which leaked thinking back in when opened (the user 2026-06-29). Source pin, mirroring the other render.ts tests.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("an expanded tool-group iterates it.indices (the tools), not the contiguous span", () => {
  // the expansion walks the grouped tool indices directly — thinking is never in it.indices (compactDisplay skipped it)
  assert.match(RENDER, /it\.indices\.forEach\(\(i, j\) => \{/);
  assert.match(RENDER, /if \(j === it\.indices\.length - 1\) child\.classList\.add\("tg-last"\)/);
  // the old contiguous-span walk that surfaced the in-between thinking is gone
  assert.doesNotMatch(RENDER, /const start = it\.indices\[0\], end = it\.indices\[it\.indices\.length - 1\];/);
  assert.doesNotMatch(RENDER, /for \(let i = start; i <= end; i\+\+\)/);
});
