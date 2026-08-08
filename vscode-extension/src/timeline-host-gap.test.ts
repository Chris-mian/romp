// The half-row gap at host boundaries is GONE (the user 2026-08-08): remote hosts' lanes no longer
// interleave with local ones in a single shared order, so the boundary said nothing — lanes list out
// uniformly and the quiet "host:" name prefix alone marks a remote session. This pins the uniform
// geometry everywhere a lane y was computed with the old offsets (draw, drag-invert, focus pulse,
// judge band), so the gap cannot creep back into one path and skew the others.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("timeline lanes are uniform — no host-boundary offsets in any geometry path", () => {
  assert.doesNotMatch(TL, /laneOff/, "the offset machinery is fully removed, not just zeroed");
  assert.ok(TL.includes("const laneY = (i) => M.top + i * LANE_GAP + LANE_GAP * 0.5;"), "draw");
  assert.ok(TL.includes("const ly = this._geom.top + i * LANE_GAP + LANE_GAP / 2;"), "drag invert");
  assert.ok(TL.includes("const y = g.top + i * LANE_GAP + LANE_GAP * 0.5;"), "focus pulse");
  assert.ok(TL.includes("const jb0 = M.top + vis.length * LANE_GAP + JB_TOPGAP;"), "judge band top");
});
