// Model-name + effort text tint (the user 2026-07-02): the chat statusline meta buttons and the timeline lane
// model/effort text are colored on the global colormap by the kernel-computed modelColor / effortColor. No DOM
// harness for either draw path, so pin the wiring at the source (the way the other render/timeline tests do).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const MODULE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "status-controls.ts"), "utf8");   // the status line's controls moved here from render.ts (T415 part two)
const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("Status carries the server-computed modelColor / effortColor", () => {
  assert.match(RENDER, /interface Status \{[^}]*modelColor\?: number\[\]; effortColor\?: number\[\]/);
});

test("the statusline meta buttons tint model/effort labels from those colors", () => {
  // metaColor picks modelColor for the model button, effortColor for the effort, "" (default) otherwise
  assert.match(MODULE, /export function metaColor\(kind: MetaKind, st: MetaStatus\): string \{[\s\S]*?kind === "model" \? pickTone\(st\.modelColor, st\.modelTone\)/);   // dual palette (PR #763): classic color vs yatharth tone, picked by theme
  // applied to the label in the refresh loop (runs on create AND the 1s ticker); a switching model shows
  // dots instead, so the tint is skipped only then (the user 2026-07-03)
  assert.match(MODULE, /label\.style\.color = showDots \? "" : metaColor\(kind, st\);/);
});

test("the timeline lane tints the model/effort pieces by rank, keeping hover + restoring the tint", () => {
  assert.match(TL, /const tint0 = kind === 'model' \? pickTone\(s\.modelColor, s\.modelTone\) : pickTone\(s\.effortColor, s\.effortTone\);/);
  assert.match(TL, /const base = \(tint && tint\.length === 3\) \? \('rgb\(' \+ tint\[0\]/);
  // the drawn word starts at the tint, and mouseleave restores to `base` (the tint), not the flat gray
  assert.match(TL, /el\('text', \{ x: sx,[^}]*fill: base/);
  assert.match(TL, /mouseleave', \(\) => \{ if \(dots\) return; wt\.setAttribute\('fill', base\)/);
});

test("the model/effort picker ROWS wear their own rank color, and the popover badge fallback re-encodes (the user 2026-08-31)", () => {
  // every /models-fed row is tinted (a picker whose rows are all default-gray codes nothing)…
  assert.match(RENDER, /if \(kind === "model" \|\| kind === "effort"\) \{\s*\n\s*const rowTint = nonClassicChoiceTone\(c as \{ color\?: number\[\] \| null; tone\?: number\[\] \| null \}\);/);
  assert.match(RENDER, /if \(rowTint\) item\.style\.color = `rgb\(\$\{rowTint\.join\(","\)\}\)`;/);
  // …through nonClassicChoiceTone, which re-encodes for light (a TEXT tint, not a fill)
  assert.match(RENDER, /function nonClassicChoiceTone\([\s\S]{0,300}?readableRgb\(picked\)/);
  // and the comment-popover badge's session-status FALLBACK re-encodes too, like its /models branch
  assert.match(RENDER, /const tint = \(nonClassicChoiceTone\(choice\) as number\[\] \| undefined\) \|\| \(tint0 && tint0\.length === 3 \? readableRgb\(tint0\) : tint0\);/);
});
