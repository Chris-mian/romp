// A permission-mode selector sits to the LEFT of the model name in the statusline, a badge+dropdown
// like the model/effort pickers (the user 2026-06-16). There's no /mode slash command, so the host
// sets it by shift+tab cycling; the webview just posts setMode like setModel/setEffort. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");

test("MetaKind includes mode; the status carries it; there's a MODE_CHOICES menu", () => {
  assert.match(RENDER, /type MetaKind = "mode" \| "model" \| "effort"/);
  assert.match(RENDER, /mode\?: string;/);                       // Status.mode
  assert.match(RENDER, /const MODE_CHOICES/);
});

test("the mode button renders FIRST (left of model) and the picker posts setMode", () => {
  assert.match(RENDER, /if \(st\.mode\) meta\.appendChild\(metaButton\("mode", prettyMode\(st\.mode\)\)\);\s*\n\s*if \(st\.model\)/);
  assert.match(RENDER, /"setMode"/);
  assert.match(RENDER, /const META_CHOICES: Record<MetaKind/);   // model/effort + mode share the menu path
});
