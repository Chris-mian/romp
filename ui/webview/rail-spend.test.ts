// Under API-KEY auth the rail shows SPEND where the subscription bars sat (the user 2026-08-04): the
// account has no 5h/weekly windows (get_usage only times out there — see the #208 auth-flip fix), so
// the kernel serves {apiKey, spend:{usd,turns,date}} built from spend.json, which accumulates each
// ResultMessage's total_cost_usd by local date. BOTH rail copies render it — VS Code's strip.ts and
// the web landing's usage JS in kernel.py — and must stay in step (the two-copies lesson, again).
// No jsdom harness → source pins (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");
const STRIPCSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.css"), "utf8");
const BACKEND = fs.readFileSync(path.join(ROOT, "kernel", "sdk_backend.py"), "utf8");

test("the kernel serves spend on the auth-flip marker, never a confident zero", () => {
  // the payload rides the SAME _usage() path the bars used — no new wire/handler
  assert.ok(KERNEL.includes('if o.get("apiKey"):'), "gated on the #208 auth-flip marker");
  assert.ok(KERNEL.includes('"spend": _spend_today()'));
  assert.ok(KERNEL.includes("def _spend_today():"));
  // a window-less file WITHOUT the marker stays None — nothing known, draw nothing
  assert.match(KERNEL, /if o\.get\("apiKey"\):[\s\S]{0,400}?return None/);
  // the accumulator: every result's cost, by local date, pruned
  assert.ok(BACKEND.includes('self.backend._record_spend(getattr(msg, "total_cost_usd", None))'));
  assert.ok(BACKEND.includes("def _record_spend(self, cost) -> None:"));
});

test("VS Code strip renders the spend chip where the bars sat", () => {
  assert.match(STRIP, /function spendChip\(usage: any\): HTMLElement \| null/);
  assert.match(STRIP, /const sp = usage && usage\.apiKey && usage\.spend;/);
  assert.match(STRIP, /box\.textContent = "API \$" \+ sp\.usd\.toFixed\(2\) \+ " today";/);
  assert.match(STRIP, /if \(spend\) usageWrap\.appendChild\(spend\);/);
  assert.match(STRIPCSS, /\.ru-spend \{/);
});

test("the web landing copy carries the SAME branch — the two rails stay in step", () => {
  assert.ok(KERNEL.includes("function hasSpend(u){return !!(u&&u.apiKey&&u.spend&&typeof u.spend.usd==='number');}"));
  assert.ok(KERNEL.includes("function spendHTML(u)"));
  // spend rows count as live rows, and both the single- and multi-account paths fall to the chip
  assert.ok(KERNEL.includes("return hasBars(r.usage)||hasSpend(r.usage);"));
  assert.ok(KERNEL.includes("el.innerHTML=hasBars(live[0].usage)?winsHTML(live[0].usage,det):spendHTML(live[0].usage);return;"));
  assert.ok(KERNEL.includes("(hasBars(r.usage)?winsHTML(r.usage,det):spendHTML(r.usage))"));
  assert.ok(KERNEL.includes('".ru-spend{'), "the landing CSS styles the chip");
});
