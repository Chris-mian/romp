// Model-name + effort text tint (the user 2026-07-02): the chat statusline meta buttons and the timeline lane
// model/effort text are colored on the global colormap by the kernel-computed modelColor / effortColor. No DOM
// harness for either draw path, so pin the wiring at the source (the way the other render/timeline tests do).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("Status carries the server-computed modelColor / effortColor", () => {
  assert.match(RENDER, /interface Status \{[^}]*modelColor\?: number\[\]; effortColor\?: number\[\]/);
});

test("the statusline meta buttons tint model/effort labels from those colors", () => {
  // metaColor picks modelColor for the model button, effortColor for the effort, "" (default) otherwise
  assert.match(RENDER, /function metaColor\(kind: MetaKind, st: Status\): string \{[\s\S]*?kind === "model" \? st\.modelColor : kind === "effort" \? st\.effortColor/);
  // applied to the label in the refresh loop (runs on create AND the 1s ticker)
  assert.match(RENDER, /label\.style\.color = metaColor\(kind, st\)/);
});

test("the timeline lane tints the model/effort pieces by rank, keeping hover + restoring the tint", () => {
  assert.match(TL, /const tint = kind === 'model' \? s\.modelColor : s\.effortColor;/);
  assert.match(TL, /const base = \(tint && tint\.length === 3\) \? \('rgb\(' \+ tint\[0\]/);
  // the drawn word starts at the tint, and mouseleave restores to `base` (the tint), not the flat gray
  assert.match(TL, /el\('text', \{ x: px,[^}]*fill: base/);
  assert.match(TL, /mouseleave', \(\) => \{ wt\.setAttribute\('fill', base\)/);
});
