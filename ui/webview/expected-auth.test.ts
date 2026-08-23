// TELEMETRY-UNAVAILABLE surfaces on an all-keyed box (the user 2026-08-15): under API-key auth the
// usage windows are structurally absent — both usage.json writers skip keyed sessions — so the rail
// must not read as broken. The kernel's keyed no-window payload carries telemetryUnavailable (the
// manager env holds a key, or the box declares ROMP_EXPECTED_AUTH=key — the apiKeyHelper machine,
// where no key ever rides service.env); the hover renders the spend it advertises even when no host
// has window bars, plus ONE quiet line saying why the bars are absent. No jsdom harness → source
// pins (the repo convention; rail-spend.test.ts is the pattern).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const usageJS = KERNEL.split('_LANDING_USAGE_JS = """')[1].split('"""')[0];

test("the hover renders the spend section even when NO host has window bars", () => {
  // the old tipHTML returned '' when every setHTML block was empty — BEFORE appending the spend
  // section, so an all-keyed box's API cell had an empty hover exactly when spend was all there
  // was to show. blocks are optional now; the spend section always appends.
  assert.ok(usageJS.includes("var h=blocks.length?"), "empty blocks no longer short-circuit");
  assert.ok(usageJS.includes("h+=fleetSpendHTML(sets);"));
  assert.ok(!usageJS.includes("if(!blocks.length)return '';"), "the early return is gone");
  assert.ok(!usageJS.includes("return h+fleetSpendHTML(sets);"),
    "the return-time append (unreachable on empty blocks) is gone with it");
});

test("the keyed no-window payload says WHY, and the hover carries one quiet line", () => {
  // the kernel marks the spend-only payload when the reason is key auth — a manager-env key, or
  // the ROMP_EXPECTED_AUTH=key declaration (the apiKeyHelper box has no key in the manager env)
  assert.ok(KERNEL.includes('out["telemetryUnavailable"] = True'));
  assert.match(KERNEL, /if \(_auth_key_present\(\)\s*\n\s*or \(os\.environ\.get\("ROMP_EXPECTED_AUTH"\) or ""\)\.strip\(\)\.lower\(\) == "key"\):/);
  // the rail captures the flag per host and renders ONE dim line (the acct line's dress — the
  // hover's existing quiet-note affordance), never a bar-shaped guess
  assert.ok(usageJS.includes("if(r.usage.telemetryUnavailable)det._telemUnavail=true;"));
  assert.ok(usageJS.includes(
    "<div class=ru-tip-acct>rate-limit telemetry unavailable under API-key auth</div>"));
  assert.ok(usageJS.includes("sets.some(function(e){return e.det._telemUnavail;})"),
    "any keyed host's payload is enough — the line renders once, not per host");
});
