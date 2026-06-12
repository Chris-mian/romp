// Timeline work-bar click regression (2026-06-12): the bar's click handler
// passed a NULL anchor (a bare lane-open with preserveFocus), so clicking any
// work period visibly did nothing — while prompt-dot clicks, which carry the
// prompt-line uuid, worked. workAnchorOf is now the single anchor chain for
// WORK-intent landings (focus handler + bar click); these tests pin the chain
// and, since the SVG draw path has no DOM harness here, pin the bar/focus
// wiring at the source level so the click can't silently revert to null.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const viewPath = path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js");
const { workAnchorOf } = createRequire(__filename)(viewPath);

test("work anchor prefers the readable reply line", () => {
  assert.equal(workAnchorOf({ uuid: "p1", workUuid: "w1", replyUuid: "r1" }), "r1");
});

test("work anchor falls back to the first reply line when no readable reply", () => {
  assert.equal(workAnchorOf({ uuid: "p1", workUuid: "w1", replyUuid: null }), "w1");
});

test("interrupted period (no reply lines) anchors on the boundary line", () => {
  assert.equal(workAnchorOf({ uuid: "p1", workUuid: null, replyUuid: null }), "p1");
});

test("no event / no uuids yields null (openChat then uses anchorT / bottom)", () => {
  assert.equal(workAnchorOf(null), null);
  assert.equal(workAnchorOf({ uuid: null, workUuid: null, replyUuid: null }), null);
});

test("bar click and focus handler both route through workAnchorOf", () => {
  const src = fs.readFileSync(viewPath, "utf8");
  // the work-bar click must carry the work anchor + the period start as anchorT
  assert.match(src, /openChat\(t\.tid \|\| this\._laneTid\(s\), workAnchorOf\(t\), false, false, t\.start\)/);
  // the feed-focus landing uses the same chain, so the two can't drift apart
  assert.match(src, /workAnchorOf\(byId\)/);
});
