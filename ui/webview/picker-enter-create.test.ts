// The + picker's Enter belongs to CREATE once a name is typed (the user 2026-07-28): typing a name and
// pressing Enter must open a NEW session with exactly that name — never reopen an existing session that
// happens to match. Reopening a match takes an explicit ArrowDown (or hover/click) onto its row; ArrowUp
// from the top row steps back out to the armed New-session button. Source pins against render.ts (no
// jsdom harness for the picker), like the other picker suites.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("with a typed name in create mode, NO row auto-activates — matches are ArrowDown away", () => {
  assert.match(SRC, /setActiveRow\(creating && q\.trim\(\) \? null : pickerRows\(\)\[0\] \?\? null\);/);
});

test("the New-session button arms whenever a name is typed and no row is explicitly active", () => {
  assert.match(SRC, /function syncNewButton\(\)/);
  assert.match(SRC, /btn\.classList\.toggle\("active", creating && !!q && !rowActive\);/);
  // the arm no longer requires ZERO matches (the old rule that made Enter reopen a fuzzy match)
  assert.doesNotMatch(SRC, /pickerRows\(\)\.length === 0\);/);
  // setActiveRow keeps the two Enter targets mutually exclusive on every path (arrow, hover, filter)
  assert.match(SRC, /syncNewButton\(\);\s*\/\/ an active row and an armed New-session button are mutually exclusive/);
});

test("Enter precedence: explicit active row, then the armed create button, then (empty box) the first row", () => {
  assert.match(SRC, /if \(active\) \{ active\.click\(\); return; \}\s*\n\s*const btn = document\.getElementById\("picker-new-btn"\);\s*\n\s*if \(btn\?\.classList\.contains\("active"\)\) \{ btn\.click\(\); return; \}\s*\n\s*const first = pickerRows\(\)\[0\];\s*\n\s*if \(first\) first\.click\(\);/);
});

test("ArrowUp from the top row steps back OUT of the match list to the armed create button", () => {
  assert.match(SRC, /if \(cur === 0 && delta < 0\) \{[\s\S]*?if \(creating && q\) \{ setActiveRow\(null\); return; \}/);
});
