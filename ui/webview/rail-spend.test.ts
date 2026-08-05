// Under API-KEY auth the rail shows SPEND WINDOWS that mirror the subscription bars' grammar — the
// same rows, labels, and twin tracks, for 5h / 7d / month-to-date — so flipping between the two auth
// modes reads instantly (the user 2026-08-04/05). A row FILLS only when spend-budgets.json names that
// window's budget: the fill is spend-over-budget, and without a cap there is no honest fraction — the
// row carries plain dollars in the readout slot and no used-track. Spend accumulates per ResultMessage
// (total_cost_usd + usage tokens) into spend.json's day AND hour buckets (the rolling windows read the
// hours). BOTH rail copies carry the builder — VS Code's strip.ts and the web landing's usage JS in
// kernel.py — and must stay in step. No jsdom harness → source pins (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");
const STRIPCSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.css"), "utf8");
const BACKEND = fs.readFileSync(path.join(ROOT, "kernel", "sdk_backend.py"), "utf8");

test("the kernel serves spend WINDOWS on the auth-flip marker, zero-filled when fresh", () => {
  assert.ok(KERNEL.includes('if o.get("apiKey"):'), "gated on the #208 auth-flip marker");
  assert.ok(KERNEL.includes('"spend": _spend_windows()'));
  assert.ok(KERNEL.includes("def _spend_windows():"));
  assert.ok(KERNEL.includes("def _spend_budgets():"), "budgets give a window its fill denominator");
  // rolling 5h/7d read the HOUR buckets; month-to-date reads the day ledger
  assert.match(KERNEL, /"fiveHour": _rolling\(5\), "sevenDay": _rolling\(7 \* 24\)/);
  assert.ok(KERNEL.includes('k.startswith(month)'));
  // a window-less file WITHOUT the marker stays None — nothing known, draw nothing
  assert.match(KERNEL, /if o\.get\("apiKey"\):[\s\S]{0,800}?return None/);
  // the accumulator: every result's cost + tokens, folded into BOTH bucket sets
  assert.ok(BACKEND.includes('self.backend._record_spend(getattr(msg, "total_cost_usd", None),'));
  assert.ok(BACKEND.includes("_fold(days, day, 90)"));
  assert.ok(BACKEND.includes("_fold(hours, hour, 192)"), "8 days of hour buckets feed the rolling windows");
});

test("VS Code strip: ONE row builder for both auth modes — spend rows ride the same loop as the bars", () => {
  assert.match(STRIP, /export function spendWindows\(usage: any, nowS: number\): UsageWindow\[\]/);
  assert.match(STRIP, /usageWindows\(usage, nowS\)\.concat\(spendWindows\(usage, nowS\)\)/);
  // no budget → no used-track and a dollars readout; never a made-up fraction
  assert.match(STRIP, /const pct = budget != null \? Math\.max\(0, Math\.min\(100, Math\.round\(\(seg\.usd \/ budget\) \* 100\)\)\) : null;/);
  assert.match(STRIP, /if \(w\.pct != null\) bars\.appendChild\(mkTrack\(w\.pct, usageColor\(w\.pct\)\)\);/);
  assert.match(STRIP, /pct\.textContent = w\.readout \?\? `\$\{w\.pct\}%`;/);
  // rolling windows draw no elapsed track; month-to-date does (it has a real boundary)
  assert.match(STRIP, /if \(key === "month" && budget != null\)/);
  // labels mirror the subscription table's two-tier form
  assert.match(STRIP, /\["fiveHour", "5 hours", "5h"\]/);
  assert.match(STRIP, /\["month", "Month", "mo"\]/);
  // dollars AND tokens stay visible in the readout (the user 2026-08-05); the split stays on hover
  assert.match(STRIP, /\+ " · " \+ fmtTok\(seg\.tok \|\| 0\) \+ " tok"/);
  assert.ok(KERNEL.includes("+' \\u00b7 '+fmtTok(seg.tok||0)+' tok'"), "web readout carries tokens too");
  // the old one-off chip is gone, and with it any minted style
  assert.doesNotMatch(STRIP, /spendChip/);
  assert.doesNotMatch(STRIPCSS, /\.ru-spend/);
});

test("the web landing copy carries the SAME builder — the two rails stay in step", () => {
  assert.ok(KERNEL.includes("function spendWinsHTML(u)"));
  assert.ok(KERNEL.includes("var SPEND_WINS=[['fiveHour','5 hours'],['sevenDay','7 days'],['month','Month']];"));
  assert.ok(KERNEL.includes("function hasSpend(u){return !!(u&&u.apiKey&&u.spend&&u.spend.fiveHour);}"));
  // same row markup as winsHTML: ru-w → ru-name → ru-bars (tracks) → ru-pct readout
  assert.ok(KERNEL.includes("+'<div class=ru-name>'+w[1]+'</div>'"));
  assert.ok(KERNEL.includes("(pct!=null?'<div class=ru-track><i class=ru-fill style=\"width:'+pct+'%;background:'+spendColor(pct)+'\"></i></div>':'')"));
  // both the single- and multi-account paths fall to the window rows
  assert.ok(KERNEL.includes("el.innerHTML=hasBars(live[0].usage)?winsHTML(live[0].usage,det):spendWinsHTML(live[0].usage);return;}"));
  assert.ok(KERNEL.includes("(hasBars(r.usage)?winsHTML(r.usage,det):spendWinsHTML(r.usage))"));
});
