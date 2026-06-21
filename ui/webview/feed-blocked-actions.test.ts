// Surgical actions on a BLOCKED sub-goal in the feed modal (the user 2026-06-17): the user can CROSS a
// specific blocked sub off (its MARK → nodeOverride op:resolve, immediate-apply) or FOLLOW UP on just that
// sub (the footer composer re-targets at the sub's node id, so the answer files under it and unblocks only
// that branch). Both are MODAL-ONLY — wired AROUND the shared wireNodeZones, so the card checklist + ledger
// marks stay pure-nav. No jsdom for the feed renderer, so — like the other feed-*.test.ts — pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("(A) a blocked sub's MARK crosses it off — posts nodeOverride op:resolve (immediate-apply, no draft)", () => {
  // gated on a REAL blocked sub: not a dim repeat, status question, not a handoff (those resolve in another store)
  assert.match(FEED, /if \(!repeat && node\.status === "question" && node\.kind !== "handoff"\) \{/);
  assert.match(FEED, /type: "nodeOverride", sid: it\.sid, nodeId: node\.id, op: "resolve"/);
  assert.match(FEED, /mark\.classList\.add\("ftree-mark-resolve"\)/);
});

test("(A) MODAL-ONLY: the override is applied AFTER wireNodeZones, flipping ONLY the mark", () => {
  // the override re-binds mark.onclick AFTER the shared wireNodeZones call returns, so the text (goMsg) and
  // the time (goWork) keep their nav, and the card's inline checklist — which calls the SAME wireNodeZones,
  // unmodified — is untouched (no override there).
  const after = FEED.indexOf("const goWork = wireNodeZones(it, node, mark, txt, meta, !repeat);");
  const override = FEED.indexOf('type: "nodeOverride"');
  assert.ok(after > 0 && override > after, "the override comes after wireNodeZones returns");
  assert.match(FEED, /wireNodeZones\(it, s, mark, txt, null, true\);/);   // card sub-goal row, unchanged
  // the red ?-ring previews its resolved (green ✓) state on hover so a click reads as "check this off"
  assert.match(CSS, /\.ftree-mark-resolve:hover \{[^}]*border-color: var\(--check-bg\)/);
});

test("(#2) a blocked sub's '↳ follow up' re-targets the footer composer at THAT sub", () => {
  assert.match(FEED, /openSubFollowUp\?\.\(node\.id, node\.text/);
  assert.match(FEED, /el\("span", "ftree-followup"\)/);
  // opener points the composer at the sub + reveals/focuses it (the robust footer box, not a per-node draft)
  assert.match(FEED, /openSubFollowUp = \(itemId, title\) =>/);
  assert.match(FEED, /setFollowTarget\(\{ itemId, title \}\)/);
});

test("(#2) the footer composer posts askFollowUp to the picked sub, else the card/group, then reverts", () => {
  // postFollowUp prefers the picked sub's id/title, else the card (single) / first member + group title
  assert.match(FEED, /itemId: tgt \? tgt\.itemId : fbId, title: tgt \? tgt\.title : fbTitle/);
  assert.match(FEED, /postFollowUp\(txt, it\.itemId\)/);                         // single-ask modal
  assert.match(FEED, /postFollowUp\(txt, grp\.members\[0\]\.itemId, grp\.title\)/);   // group modal
  assert.match(FEED, /setFollowTarget\(null\);/);                               // revert to the card after sending
  assert.match(FEED, /followupSub = null;\s*\/\/ a fresh target/);              // and on a fresh modal open
});

test("(#2) a per-node '↻ Followed up' chip shows while THIS sub is optimistically reopened", () => {
  assert.match(FEED, /if \(!repeat && node\.followupPending\) \{/);
  assert.match(FEED, /"↻ Followed up"/);
  assert.match(FEED, /followupPending\?: boolean;/);   // consumed off AskTreeNode (emitted per-node by the kernel flatten)
  assert.match(CSS, /\.ftree-followedup \{/);
});

test("(#2) the follow-up target label names the sub and reverts to the whole card on click", () => {
  assert.match(FEED, /"↳ following up on: " \+ sub\.title/);
  assert.match(FEED, /futgtEl\.onclick = \(\) => setFollowTarget\(null\)/);
  assert.match(CSS, /\.feed-modal-follow-target \{/);
});
