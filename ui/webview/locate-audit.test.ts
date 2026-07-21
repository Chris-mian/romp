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

test("a mid-fetch anchor attempt keeps waiting instead of toasting 'couldn't locate'", () => {
  // pendingAnchor re-attempts run on EVERY push re-render (0.5-3s). fetchOlderForAnchor returns
  // false while a chunk is in flight (loadingOlder), so a mid-fetch attempt fell through to
  // "pointer-not-rendered" and a FALSE "couldn't locate" toast while the chunk that would land it
  // was still on the wire (the user 2026-07-20: the ui thread's 7-fetch burst ended not-rendered).
  const render = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
  assert.ok(render.includes("fetchOlderForAnchor(activeId, uuid) || loadingOlder.has(activeId)"),
            "an in-flight older fetch counts as pending, never a give-up");
  const guard = render.indexOf("fetchOlderForAnchor(activeId, uuid) || loadingOlder.has(activeId)");
  const body = render.slice(guard, guard + 300);
  assert.ok(body.includes("pendingOlderAnchor.set(activeId, uuid)"),
            "the arrival re-land is re-pointed at THIS uuid");
  assert.ok(body.includes('landTrail.push("pointer-fetch-older")'),
            "the trail records the wait, not a false miss");
});

test("kernel: a cold parse serves the stored summary citation instead of a link-less card", () => {
  // build_feed's anchor tiers all read parse-derived maps; right after a kernel restart ps is None
  // until _warm_fleet_bg, so every card shipped summaryAnchorUuid null and the summary click hit the
  // "no anchor was recorded" toast (the user 2026-07-20: the stalled ui card, 7 restarts that day).
  const kernel = fs.readFileSync(path.join(ROOT, "bin", "romp-kernel"), "utf8");
  assert.ok(kernel.includes("if _sa_u is None and ps is None:"),
            "the cold-parse fallback exists");
  const at = kernel.indexOf("if _sa_u is None and ps is None:");
  assert.ok(kernel.slice(at, at + 1200).includes("_sa_u = _cited"),
            "…and serves the distiller's stored citation raw");
});
