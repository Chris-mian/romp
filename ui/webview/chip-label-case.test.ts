// Status chips read as sentence case, not ALL CAPS (the user 2026-07-03): "Working", "Ready",
// "Blocked", "Compacting", … — first letter capitalized, the rest lowercase (acronyms like "API"
// stay). Pins the statusline CHIP_LABEL map + its fallback in render.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const R = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("CHIP_LABEL uses sentence case, never ALL-CAPS status words", () => {
  const m = R.match(/const CHIP_LABEL[\s\S]*?\};/);
  assert.ok(m, "CHIP_LABEL exists");
  const map = m![0];
  assert.match(map, /working: "Working"/);
  assert.match(map, /ready: "Ready"/);
  assert.match(map, /awaiting: "Blocked"/);
  assert.match(map, /compacting: "Compacting"/);
  assert.match(map, /idle: "Idle"/);
  assert.match(map, /closed: "Closed"/);
  // no bare ALL-CAPS status word survives (the acronym "API" is allowed)
  assert.doesNotMatch(map, /"WORKING"|"READY"|"BLOCKED"|"COMPACTING"|"IDLE"|"CLOSED"/);
});

test("the unknown-state fallback is sentence case too (not toUpperCase)", () => {
  assert.match(R, /s\.status\.state\[0\]\.toUpperCase\(\) \+ s\.status\.state\.slice\(1\)\.toLowerCase\(\)/);
});
