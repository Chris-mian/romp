// A just-opened session said "Working" over an epoch-sized clock while its transcript didn't exist yet
// (the user 2026-08-05, who wanted "opening" with animated dots until it's ready). The fix is layered:
// the KERNEL reports state "opening" for a spawned session whose transcript isn't on disk (the first
// record is the deciding event — discover() then takes over), and the CLIENT shows the same line for a
// tab whose session payload hasn't arrived at all (which previously left the PREVIOUS tab's statusline
// standing). Same in-progress line treatment as compacting, dots in the accent per the loader rule.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");

test("the kernel reports OPENING while the transcript doesn't exist — never a working chip on a broken clock", () => {
  assert.ok(KERNEL.includes('if chip in ("working", "ready") and not path_override and not os.path.exists(sess["path"]):'));
  assert.ok(KERNEL.includes('chip = "opening"'));
});

test("the statusline shows Opening + dots for BOTH the pre-payload tab and the kernel's opening state", () => {
  assert.match(RENDER, /function openingLine\(\): HTMLElement/);
  // pre-payload: a placeholder tab used to leave the PREVIOUS tab's statusline standing
  assert.match(RENDER, /if \(activeId && !s\) \{[\s\S]{0,700}?sl\.replaceChildren\(openingLine\(\)\);\s*\n\s*return;/);
  // kernel-reported opening rides the same line
  assert.match(RENDER, /s\.status\.state === "opening"/);
  assert.match(RENDER, /"opening"/);
  assert.ok(RENDER.includes('opening: "Opening…",'), "the chip vocabulary knows the state");
  // three staggered accent dots — the loader idiom's smallest form, no new fonts
  assert.match(CSS, /\.opening-line-dots span \{ width: 4px; height: 4px; border-radius: 50%; background: var\(--accent\);/);
  assert.match(CSS, /@keyframes opening-line-pulse/);
  assert.match(CSS, /\.opening-line \{ color: var\(--accent\); \}/);
});

test("the MCP panel names a stale kernel instead of a raw parse error (the user 2026-08-05)", () => {
  assert.match(RENDER, /this romp kernel predates the MCP panel — restart romp to update it/);
  assert.match(RENDER, /\(\(e && e\.message\) \|\| e\)/);
});
