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
  // the spend view arms on the legacy apiKey marker OR a login-less machine with recorded spend
  // (per-session auth writes no marker any more — the user 2026-08-08)
  assert.ok(KERNEL.includes('if o.get("apiKey") or (not _claude_account() and (jd.STATE / "spend.json").exists()):'));
  assert.ok(KERNEL.includes('"spend": _spend_windows()'));
  assert.ok(KERNEL.includes("def _spend_windows():"));
  assert.ok(KERNEL.includes("def _spend_budgets():"), "budgets give a window its fill denominator");
  // rolling 5h/7d read the HOUR buckets; month-to-date reads the day ledger
  assert.match(KERNEL, /"fiveHour": _rolling\(5\), "sevenDay": _rolling\(7 \* 24\)/);
  assert.ok(KERNEL.includes('k.startswith(month)'));
  // a window-less file on a logged-in machine stays None — nothing known, draw nothing
  assert.match(KERNEL, /if o\.get\("apiKey"\) or [\s\S]{0,900}?return None/);
  // the subscription payload carries the spend windows BESIDE the bars — the hover's token graph
  // needs them for every account, not just spend-only ones (the user 2026-08-08)
  assert.match(KERNEL, /"fiveHour": five, "sevenDay": seven, "fable": fable,[\s\S]{0,600}?"spend": _spend_windows\(\),/);
  // the accumulator: total_cost_usd AND the usage token counts are CUMULATIVE per CLI process — fold
  // per-turn DELTAS for both, and a shrunken counter (an unwatched reset) folds whole, never negative
  // (the user 2026-08-08, dollars in the morning and tokens by the evening)
  assert.ok(BACKEND.includes("delta = total - self._last_cost_total if total >= self._last_cost_total else total"));
  assert.ok(BACKEND.includes("turn_u[k] = v - last if v >= last else v"));
  assert.ok(BACKEND.includes("self.backend._record_spend(delta, turn_u)"));
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
  assert.ok(KERNEL.includes("function spendWinsHTML(u,det)"));
  assert.ok(KERNEL.includes("var SPEND_WINS=[['fiveHour','5 hours'],['sevenDay','7 days'],['month','Month']];"));
  assert.ok(KERNEL.includes("function hasSpend(u){return !!(u&&u.apiKey&&u.spend&&u.spend.fiveHour);}"));
  // same row markup as winsHTML: ru-w → ru-name → ru-bars (tracks) → ru-pct readout
  assert.ok(KERNEL.includes("+'<div class=ru-name>'+w[1]+'</div>'"));
  assert.ok(KERNEL.includes("(pct!=null?'<div class=ru-track><i class=ru-fill style=\"width:'+pct+'%;background:'+spendColor(pct)+'\"></i></div>':'')"));
  // both the single- and multi-account paths fall to the window rows, and BOTH fill the hover detail
  // (spendDet) so a bars account still gets the token graph
  assert.ok(KERNEL.includes("if(hasBars(live[0].usage)){el.innerHTML=winsHTML(live[0].usage,det);spendDet(live[0].usage,det);}"));
  assert.ok(KERNEL.includes("else el.innerHTML=spendWinsHTML(live[0].usage,det);"));
  assert.ok(KERNEL.includes("if(hasBars(r.usage)){inner=winsHTML(r.usage,det);spendDet(r.usage,det);}"));
  assert.ok(KERNEL.includes("else inner=spendWinsHTML(r.usage,det);"));
});

test("the rich tip is the ONE hover surface: no native titles, every account renders, cursor-anchored", () => {
  // NO native title attributes anywhere on the rail (the user 2026-08-08, who got the browser's flat
  // yellow box on top of the rich hover): the usage JS may mention titles only in comments
  const usageJS = KERNEL.split("_LANDING_USAGE_JS = \"\"\"")[1].split('"""')[0];
  for (const line of usageJS.split("\n")) {
    const code = line.split("//")[0];
    assert.ok(!/\btitle\s*=/.test(code) && !code.includes(".title="), `native title in usage JS: ${line.trim()}`);
  }
  // a SPEND-ONLY account used to return '' from setHTML, so a mixed hover showed only the
  // subscription login (the user 2026-08-08) — now it renders its own section
  assert.ok(usageJS.includes("if(!keys.length&&!sp)return '';"));
  assert.ok(usageJS.includes("var spendOnly=!keys.length;"));
  // the token graph: the three spend windows' volume on ONE shared auto-scale, in the tip's track idiom
  assert.ok(usageJS.includes("function spendDet(u,det)"));
  assert.ok(usageJS.includes("var mx=1;ks.forEach(function(k){if(sp[k].tok>mx)mx=sp[k].tok;});"));
  // dollars ride the value column only where they are REAL billing (spend-only accounts)
  assert.ok(usageJS.includes("+fmtTok(v.tok)+(spendOnly?' \\u00b7 $'"));
  // the tip anchors ABOVE the rail, centered on the CURSOR — never pinned to the container edge
  assert.ok(usageJS.includes("var x=(ev&&typeof ev.clientX==='number')?ev.clientX:(r.left+r.width/2);"));
  assert.ok(usageJS.includes("x-tip.offsetWidth/2"));
  assert.ok(usageJS.includes("r.top-tip.offsetHeight-8"));
  // the click hint the native title used to carry lives in the tip's footer now
  assert.ok(usageJS.includes("'<div class=ru-tip-age>click to refresh</div>'"));
});

test("every tip string carries data — the narration is gone and stays gone", () => {
  // The de-inking pass (the user 2026-08-08, who found the tip overly verbose): the host name alone
  // heads a section, the token rows label themselves, config hints live in the docs, and the reader
  // is already hovering the bars when the refresh hint shows.
  const usageJS = KERNEL.split("_LANDING_USAGE_JS = \"\"\"")[1].split('"""')[0];
  const code = usageJS.split("\n").map((l) => l.split("//")[0]).join("\n");
  assert.ok(!code.includes("its own allowance"), "the host heading is the host name, bare");
  assert.ok(!code.includes("one scale"), "the token rows are their own labels");
  assert.ok(!code.includes("no budget set"), "no config instructions in a glance surface");
  assert.ok(!code.includes("current usage unknown"), "the ? row already says unknown");
  assert.ok(!code.includes("click the bars"), "the short hint replaced it");
  assert.ok(code.includes("window reset '+esc(v.ago)+'; no reading since"), "the rolled note keeps only its facts");
});
