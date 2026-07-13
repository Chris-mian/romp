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

test("model + effort reserve room independently for whichever piece is present (not 0 when model is blank)", () => {
  assert.match(SRC, /const modelPieceW = \(s\) => \(s\.model \? this\.ctxWidth\(s\.model\) \+ caretW : 0\);/);
  assert.match(SRC, /const effortPieceW = \(s\) => \(s\.effort \? this\.ctxWidth\(s\.effort\) \+ caretW : 0\);/);
  assert.match(SRC, /const maxEffortPiece = Math\.max\(0, \.\.\.vis\.map\(effortPieceW\)\);/);
});

test("the effort is left-justified to a FIXED column (the user 2026-07-03): same x for every lane", () => {
  // a fixed effort sub-column x, computed once from the widest model piece — independent of THIS lane's model
  assert.match(SRC, /const effortColX = modelColX \+ Math\.ceil\(maxModelPiece\) \+ effortGap;/);
  // both draw paths place the effort at effortColX (live picker + dead/static lane)
  assert.match(SRC, /if \(s\.effort\) drawPiece\('effort', s\.effort, effortColX\);/);
  assert.match(SRC, /if \(s\.effort\) staticPiece\(s\.effort, effortColX\);/);
});

test("the picker draws when EITHER model or effort is present, each piece guarded independently", () => {
  assert.match(SRC, /if \(s\.model \|\| s\.effort\) \{/);
  assert.match(SRC, /if \(s\.model\) drawPiece\('model', s\.model, modelColX\);/);
  assert.match(SRC, /if \(s\.model\) staticPiece\(s\.model, modelColX\);/);
});
