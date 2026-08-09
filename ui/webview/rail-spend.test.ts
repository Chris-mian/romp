// API-KEY SPEND on the rail (redesigned 2026-08-08, with per-session auth): spend is NUMBERS, never
// bars — the old hover graph scaled each window's bar to the largest window, a shape that told the
// reader nothing, and the budget-fill tracks on the web rail died with it. A host's payload can now
// carry a login's WINDOWS and its key's SPEND at once (`spend` beside the bars, keyed-only sums), so
// presence of the spend windows — not the legacy apiKey flag — is what turns the dollars on. The
// collapsed web rail shows one API cell (key tail + 5h/month dollars); the hover breaks spend down
// per window per host. Spend accumulates per ResultMessage (total_cost_usd + usage tokens) into
// spend.json's day AND hour buckets, each bucket carrying a `key` sub-count for key-billed turns.
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

test("the kernel serves spend windows for BOTH payload shapes, keyed-only beside bars", () => {
  // the spend-only view arms on the legacy apiKey marker OR a login-less machine with recorded spend,
  // and keeps TOTAL sums (everything there bills the key; legacy files predate the split)
  assert.ok(KERNEL.includes('if o.get("apiKey") or (not _claude_account() and (jd.STATE / "spend.json").exists()):'));
  assert.ok(KERNEL.includes('"spend": _spend_windows(), "apiTail": _auth_key_tail(),'));
  // the bars payload attaches the KEYED split only — a login turn's computed cost there would be
  // dollars nobody is billed — and only when key turns actually exist (the user 2026-08-08)
  assert.ok(KERNEL.includes("def _spend_windows(keyed_only=False):"));
  assert.ok(KERNEL.includes("ksp = _spend_windows(keyed_only=True)"));
  assert.match(KERNEL, /if any\(\(ksp\.get\(k\) or \{\}\)\.get\("turns"\) for k in \("fiveHour", "sevenDay", "month"\)\):/);
  assert.ok(KERNEL.includes('out["apiTail"] = _auth_key_tail()'));
  // rolling 5h/7d read the HOUR buckets; month-to-date reads the day ledger
  assert.match(KERNEL, /"fiveHour": _rolling\(5\), "sevenDay": _rolling\(7 \* 24\)/);
  assert.ok(KERNEL.includes("k.startswith(month)"));
  // the accumulator: cumulative-per-process DELTAS, and each bucket splits out the key's own turns
  assert.ok(BACKEND.includes("delta = total - self._last_cost_total if total >= self._last_cost_total else total"));
  assert.ok(BACKEND.includes("turn_u[k] = v - last if v >= last else v"));
  assert.ok(BACKEND.includes("self.backend._record_spend(delta, turn_u, keyed=self.api_key_auth)"));
  assert.ok(BACKEND.includes("if keyed or ke:   # carry an existing key split forward even on a login turn"));
  assert.ok(BACKEND.includes("_fold(days, day, 90)"));
  assert.ok(BACKEND.includes("_fold(hours, hour, 192)"), "8 days of hour buckets feed the rolling windows");
});

test("VS Code strip: spend rows key on the windows' PRESENCE, one row builder for both kinds", () => {
  assert.match(STRIP, /export function spendWindows\(usage: any, nowS: number\): UsageWindow\[\]/);
  // presence, not the apiKey flag: a mixed host's payload carries bars AND spend at once
  assert.ok(STRIP.includes("const sp = usage && usage.spend;"));
  assert.doesNotMatch(STRIP, /usage\.apiKey && usage\.spend/);
  assert.match(STRIP, /usageWindows\(usage, nowS\)\.concat\(spendWindows\(usage, nowS\)\)/);
  // labels mirror the subscription table's two-tier form; dollars AND tokens stay visible
  assert.match(STRIP, /\["fiveHour", "5 hours", "5h"\]/);
  assert.match(STRIP, /\["month", "Month", "mo"\]/);
  assert.match(STRIP, /\+ " · " \+ fmtTok\(seg\.tok \|\| 0\) \+ " tok"/);
  // the old one-off chip is gone, and with it any minted style
  assert.doesNotMatch(STRIP, /spendChip/);
  assert.doesNotMatch(STRIPCSS, /\.ru-spend/);
});

test("the web rail's API cell is numbers with the key's own tail — no spend bars anywhere", () => {
  const usageJS = KERNEL.split('_LANDING_USAGE_JS = """')[1].split('"""')[0];
  // one compact cell: 'API …wxyz' (several distinct keys fall back to bare 'API'), 5h + month dollars
  assert.ok(usageJS.includes("function apiCellHTML(live)"));
  assert.ok(usageJS.includes("'API'+(tl.length===1?' \\u2026'+esc(tl[0]):'')"));
  assert.ok(usageJS.includes("fmtUsd(sum.fiveHour)+' 5h \\u00b7 '+fmtUsd(sum.month)+' mo</div>'"));
  // the graph and the budget fills are gone: no spend track, no spend color ramp, no shared scale
  assert.ok(!usageJS.includes("spendColor"), "the budget-fill ramp died with the spend bars");
  assert.ok(!usageJS.includes("spendWinsHTML"), "spend never renders as window rows with tracks");
  assert.ok(!usageJS.includes("var mx=1;"), "the token auto-scale graph is gone");
  // presence-keyed, like the strip
  assert.ok(usageJS.includes("function hasSpend(u){return !!(u&&u.spend&&u.spend.fiveHour);}"));
});

test("the rich tip is the ONE hover surface: no native titles, per-host sections, numbers-only spend", () => {
  // NO native title attributes anywhere on the rail (the user 2026-08-08, who got the browser's flat
  // yellow box on top of the rich hover): the usage JS may mention titles only in comments
  const usageJS = KERNEL.split('_LANDING_USAGE_JS = """')[1].split('"""')[0];
  for (const line of usageJS.split("\n")) {
    const code = line.split("//")[0];
    assert.ok(!/\btitle\s*=/.test(code) && !code.includes(".title="), `native title in usage JS: ${line.trim()}`);
  }
  // a host section can carry BOTH its login's windows and its key's spend (per-session auth) — the
  // spendOnly gate that hid a bars host's dollars is gone
  assert.ok(usageJS.includes("if(!keys.length&&!sp)return '';"));
  assert.ok(!usageJS.includes("spendOnly"), "spend renders for ANY host that has it");
  assert.ok(usageJS.includes("if(sp){var ks=['fiveHour','sevenDay','month'].filter(function(k){return sp[k];});"));
  // numbers only: dollars · tokens · turns per window, labelled by the key's tail
  assert.ok(usageJS.includes("function spendDet(u,det)"));
  assert.ok(usageJS.includes("API'+(d._tail?' \\u2026'+esc(d._tail):'')+' spend</span>"));
  assert.ok(usageJS.includes("fmtUsd(v.usd)+' \\u00b7 '+fmtTok(v.tok)+' tok \\u00b7 '+(v.turns||0)+' turns</span>"));
  // the tip anchors ABOVE the rail, centered on the CURSOR — never pinned to the container edge
  assert.ok(usageJS.includes("var x=(ev&&typeof ev.clientX==='number')?ev.clientX:(r.left+r.width/2);"));
  assert.ok(usageJS.includes("x-tip.offsetWidth/2"));
  assert.ok(usageJS.includes("r.top-tip.offsetHeight-8"));
  // the click hint the native title used to carry lives in the tip's footer now
  assert.ok(usageJS.includes("'<div class=ru-tip-age>click to refresh</div>'"));
});

test("every tip string carries data — the narration is gone and stays gone", () => {
  // The de-inking pass (the user 2026-08-08, who found the tip overly verbose): the host name alone
  // heads a section, the spend rows label themselves, config hints live in the docs, and the reader
  // is already hovering the bars when the refresh hint shows.
  const usageJS = KERNEL.split('_LANDING_USAGE_JS = """')[1].split('"""')[0];
  const code = usageJS.split("\n").map((l) => l.split("//")[0]).join("\n");
  assert.ok(!code.includes("its own allowance"), "the host heading is the host name, bare");
  assert.ok(!code.includes("one scale"), "the spend rows are their own labels");
  assert.ok(!code.includes("no budget set"), "no config instructions in a glance surface");
  assert.ok(!code.includes("current usage unknown"), "the ? row already says unknown");
  assert.ok(!code.includes("click the bars"), "the short hint replaced it");
  assert.ok(code.includes("window reset '+esc(v.ago)+'; no reading since"), "the rolled note keeps only its facts");
});
