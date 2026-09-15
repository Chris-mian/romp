// Permission-mode glyphs (the user 2026-08-28): every mode wears a small line icon BESIDE its
// text — the statusline badge and the picker rows carry it; an icon alone is a riddle, so the
// label never drops. House icon style: 16-unit viewBox, stroke currentColor 1.4, round joins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const MODULE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "status-controls.ts"), "utf8");   // the status line's controls moved here from render.ts (T415 part two)
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("every offerable mode + the renderable-only dontAsk has a glyph; the set speaks one vocabulary", () => {
  const iconsAt = MODULE.indexOf("const MODE_ICONS");
  const block = MODULE.slice(iconsAt, MODULE.indexOf("};", iconsAt));
  for (const k of ["default", "acceptedits", "auto", "plan", "bypasspermissions", "dontask"]) {
    assert.ok(block.includes(`${k}:`), k + " has a glyph");
  }
  // the gate vocabulary: Normal is the shield; Bypass is the SAME shield path plus the slash
  const shield = block.match(/default: '<path d="([^"]+)"\/>'/)![1];
  assert.ok(block.includes(`bypasspermissions: '<path d="${shield}"/>`), "bypass = the shield, slashed");
  assert.match(MODULE, /viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1\.4" stroke-linecap="round" stroke-linejoin="round"/,
    "the house line-icon dress (the tag-glyph convention)");
});

test("the badge mounts the glyph beside the label and the sync loop keeps it live", () => {
  assert.match(MODULE, /if \(kind === "mode"\) \{ {3}\/\/ the permission glyph, always beside its text/);
  assert.match(MODULE, /const ico = b\.querySelector\("\.mode-ico"\) as HTMLElement \| null;\n\s*if \(ico\) ico\.innerHTML = modeIconSvg\(st\.mode\);/);
});

test("the picker rows carry the glyph (mode menu only) and labels normalize to the same icon", () => {
  assert.match(RENDER, /const rowIco = kind === "mode" \? el\("span", "meta-ico mode-ico"\) : null;/);
  // modeIconSvg accepts wire values AND prettyMode labels ("Accept edits" → acceptedits)
  assert.match(MODULE, /const raw = \(mode \|\| "default"\)\.toLowerCase\(\)\.replace\(/);
  assert.match(CSS, /\.meta-ico \{ display: inline-flex; align-items: center; margin-right: 4px;/);
});
