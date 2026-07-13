// A "couldn't locate" jump must be diagnosable from EVIDENCE: the chat posts a
// locateDiag trail for every anchor landing (hit or miss), and the kernel
// appends it to locate-audit.jsonl (the user 2026-07-13: a feed summary click
// landed on the web but honest-failed in VS Code — without the persisted trail
// the difference is guesswork).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

test("the chat posts a landing trail and the kernel persists it", () => {
  const render = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
  assert.ok(render.includes('type: "locateDiag"'), "render.ts must post the landing diagnostics");
  const kernel = fs.readFileSync(path.join(ROOT, "bin", "romp-kernel"), "utf8");
  assert.ok(kernel.includes('"locateDiag"'), "the kernel must handle the frame");
  assert.ok(kernel.includes("locate-audit.jsonl"), "…and append it to the audit file");
});

test("the chat bundle's kernel fetches are host-aware (kernelUrl)", () => {
  const render = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
  // A bare same-origin fetch silently fails in the VS Code webview — the empty
  // model picker (the user 2026-07-13). Every kernel GET goes through kernelUrl.
  assert.ok(!/fetch\("\//.test(render), "no bare same-origin fetches in render.ts");
  for (const ep of ["/palette", "/models", "/commands", "/followup-preview"])
    assert.ok(render.includes(`kernelUrl("${ep}`), `${ep} must route through kernelUrl`);
});
