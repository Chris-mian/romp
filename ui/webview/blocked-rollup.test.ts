// Blocked rolls UP the goal tree (the user 2026-07-11): nimbus's Needs-you traced to a block buried
// two levels under a collapsed checklist row — the only visible glyph was the open to-do's ring, which
// got misread as the block source. The kernel's flatten now mirrors the judge's any_blocked (every
// non-done ancestor of an open block reads "question"; a completed subtree's block stays moot) and marks
// rolled-up ancestors qderived, so the client can show the ⏸ on a collapsed row while pointing DOWN to
// the real ask — and keep the surgical Done/Follow-up buttons OFF the ancestors. Rollup semantics are
// exercised in tests/test_kernel.py (build_feed tree); these are the wiring pins (render.ts precedent:
// no jsdom harness for feed.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const FEED = fs.readFileSync(path.join(UI, "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("kernel flatten rolls a blocked descendant up to every non-done ancestor and marks it qderived", () => {
  assert.match(KERNEL, /def _closure_blocked\(nid\):/);
  // the done/cleared short-circuit mirrors jd.any_blocked (a completed subtree's block is moot)
  assert.match(KERNEL, /if not nd or nd\.get\("cleared"\) or \(_closure_done\(nid\) and nid not in agent_open\):/);
  assert.match(KERNEL, /st = "done" if done else \("question" if _closure_blocked\(nid\) else "open"\)/);
  // rolled-up ancestors are distinguishable from the actual ask
  assert.match(KERNEL, /"qderived": st == "question" and not nd\.get\("blocked"\),/);
  // the anchor keys on the node's NEWEST trail segment — where it stands, not where born (2026-07-20)
  assert.match(KERNEL, /_node_anchor_uuids\(nd, seg_trig, seg_uuid\)/);
});

test("the card checklist ⏸ tooltip points down the tree on a rolled-up ancestor", () => {
  assert.match(FEED, /if \(s\.status === "question"\) mark\.title = s\.qderived \? "a sub-goal inside is blocked — expand to find it" : "blocked — needs you";/);
});

test("the modal keeps Done/Follow-up OFF rolled-up ancestors and labels them Blocked inside", () => {
  // action buttons only on a node open/blocked in its OWN right (Done on a rolled-up ancestor would
  // resolve the whole subtree; Follow up would file the answer off-target) — widened to open subs 2026-07-20
  assert.match(FEED, /if \(!repeat && node\.status !== "done" && !node\.cleared && !node\.qderived && node\.kind !== "handoff"\) \{/);
  assert.match(FEED, /node\.qderived \? "Blocked inside" : "Blocked"/);
  assert.match(FEED, /node\.qderived \? "a sub-goal inside is blocked — the ⏸ below is the ask" : "blocked — needs you"/);
  // nav semantics: a rolled-up ancestor is NOT "resolved" (its anchor is its mint, not a block op)
  assert.match(FEED, /const resolved = \(node\.status === "done" \|\| \(node\.status === "question" && !node\.qderived\)\) && node\.auth !== "open";/);
  assert.match(FEED, /node\.status === "question" && !node\.qderived \? "jump to where this got marked blocked"/);
});
