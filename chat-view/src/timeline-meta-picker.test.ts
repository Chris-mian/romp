// A freshly-launched SDK lane has no model for the few seconds until it connects, but its effort is always
// known (the registry). The model+effort picker used to hide BOTH when the model was blank, so a new SDK
// session showed neither (the user 2026-06-26, re-routed from bugs). Effort must show immediately. Source
// pins (no jsdom for the SVG renderer): they fail if the picker reverts to gating everything on the model.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("modelLabel returns the effort alone when the model is not known yet", () => {
  assert.match(SRC, /if \(!s\.model\) return s\.effort \|\| '';/);
});

test("metaWidth reserves room for whichever of model/effort is present (not 0 when model is blank)", () => {
  assert.match(SRC, /const metaWidth = \(s\) => \{ let w = 0; if \(s\.model\) w \+= this\.ctxWidth\(s\.model\) \+ caretW; if \(s\.effort\) w \+= \(w \? META_GAP : 0\)/);
});

test("the picker draws when EITHER model or effort is present, each piece guarded independently", () => {
  assert.match(SRC, /if \(s\.model \|\| s\.effort\) \{/);
  assert.match(SRC, /if \(s\.model\) drawPiece\('model', s\.model\);/);
  assert.match(SRC, /if \(s\.effort\) \{ if \(s\.model\) px \+= META_GAP; drawPiece\('effort', s\.effort\); \}/);
});
