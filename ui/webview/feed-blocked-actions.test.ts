// Surgical actions on a BLOCKED sub-goal in the feed modal (the user 2026-06-29): two explicit BUTTONS sit at
// the end of a blocked node's line — "Done" crosses the sub off (nodeOverride op:resolve, immediate-apply) and
// "Follow up" re-targets the footer composer at the sub's node id (so the answer files under it and unblocks
// only that branch). The MARK stays PURE NAV here (it no longer silently crosses the sub off — that was
// confusing vs the main card). Both buttons are MODAL-ONLY — added AROUND the shared wireNodeZones, so the
// card checklist + ledger marks stay pure-nav. No jsdom for the feed renderer, so pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("(A) a non-done sub's 'Done' button crosses it off — posts nodeOverride op:resolve (immediate-apply, no draft)", () => {
  // gated on a REAL open/blocked sub (widened from blocked-only 2026-07-20): not a dim repeat, not a
  // user-dropped (cleared) row, never a rolled-up qderived ancestor (Done there would resolve the whole
  // subtree), not a handoff (those resolve in another store)
  assert.match(FEED, /if \(!repeat && node\.status !== "done" && !node\.cleared && !node\.qderived && node\.kind !== "handoff"\) \{/);
  assert.match(FEED, /type: "nodeOverride", sid: it\.sid, nodeId: node\.id, op: "resolve"/);
  // a "Done" button (not the mark) carries the resolve override now
  assert.match(FEED, /el\("button", "ftree-act-btn ftree-act-done"\)/);
  assert.match(FEED, /done\.textContent = "Done"/);
  // Every tree action button rests in the neutral gray of .ftree-act-btn and lights up in the ONE romp
  // accent hover (the user 2026-07-21, part 2): Done / Status? / Follow up / Drop all share it — full
  // uniformity, no red left on any action (only error/blocked STATUS keeps red elsewhere).
  assert.match(CSS, /\.ftree-act-done:hover,\s*\n\s*\.ftree-act-status:hover,\s*\n\s*\.ftree-act-fup:hover,\s*\n\s*\.ftree-act-drop:hover \{[^}]*color: var\(--accent\)/);
  assert.doesNotMatch(CSS, /\.ftree-act-drop:hover \{[^}]*var\(--err\)/);
  // no resting color tints on fup/status anymore — they inherit the gray base
  assert.doesNotMatch(CSS, /\.ftree-act-fup \{[^}]*color: #5aa2ff/);
  assert.doesNotMatch(CSS, /\.ftree-act-status \{[^}]*color: var\(--accent\)/);
});

test("(A) one accent hover across every action button — Clear/Move/Follow up hover accent, not red/blue (the user 2026-07-21)", () => {
  // .fdismiss (Clear, Move to Working, Clear all, UndoClear) hovers the ONE accent highlight; the old
  // red-fill and the Follow-up dark-blue override are gone. Only error/blocked STATUS keeps red.
  assert.match(CSS, /\.fdismiss:hover \{[^}]*color: var\(--accent\)/);
  assert.doesNotMatch(CSS, /\.fdismiss:hover \{[^}]*var\(--err/);
  assert.doesNotMatch(CSS, /\.fdismiss\.ffollow:hover \{/);        // no separate dark-blue Follow-up hover
  assert.doesNotMatch(CSS, /\.fq-send:hover \{[^}]*rel-decision/); // inline send hover unified to accent too
  // the error/status reds survive on purpose (retry ties to an API error; the blocked chip is a status color)
  assert.match(CSS, /\.fdismiss\.fretry:hover[^{]*\{[^}]*#e5484d/);
});

test("(A) Done/Drop/Status? are SUB-TASK-ONLY — the top-level goal (tree root) gets only 'Follow up' (the user 2026-06-30; Clear + the card-level sweep cover the root)", () => {
  // the root is identified as it.tree[0]; the per-item buttons are gated behind !isRoot
  assert.match(FEED, /const isRoot = node\.id === it\.tree\?\.\[0\]\?\.id;/);
  assert.match(FEED, /if \(!isRoot\) \{[\s\S]*?ftree-act-done[\s\S]*?acts\.append\(done, drop, stat\);\s*\n\s*\}/);
  // Follow up is appended unconditionally (every non-done node, the root included)
  assert.match(FEED, /acts\.append\(fu\);/);
});

test("(A) 'Drop' is the item-level clear — nodeOverride op:clear, acknowledged in place (the user 2026-07-20)", () => {
  assert.match(FEED, /el\("button", "ftree-act-btn ftree-act-drop"\)/);
  assert.match(FEED, /type: "nodeOverride", sid: it\.sid, nodeId: node\.id, op: "clear"/);
  // instant ack: the line flips to the cleared look before the kernel round-trip
  assert.match(FEED, /line\.classList\.add\("st-cleared"\);/);
  // a cleared row renders checked-off + faded + struck, in the modal tree AND the inline checklist
  assert.match(CSS, /\.ftree-node\.st-cleared \{[^}]*opacity/);
  assert.match(CSS, /\.fcheck\.cleared \{[^}]*opacity/);
  assert.match(FEED, /if \(n\.cleared\) return "cleared";/);
});

test("(A) the per-sub-goal 'Check status' is a ONE-CLICK targeted ask — askFollowUp with the canned per-item question (the user 2026-07-20; renamed from 'Status?' 2026-07-21)", () => {
  assert.match(FEED, /el\("button", "ftree-act-btn ftree-act-status"\)/);
  // reads "Check status" now — one verb for the same act as the modal footer sweep, not the old "Status?"
  assert.match(FEED, /stat\.textContent = "Check status"/);
  assert.doesNotMatch(FEED, /stat\.textContent = "Status\?"/);
  assert.match(FEED, /function statusAskOne\(title: string\): string/);
  // The canned ask still elicits the four reply shapes the judge's planner files (done / in progress /
  // blocked-on-me / obsolete) but no longer NAMES that taxonomy at the session (the user 2026-07-24): the
  // recipient has never heard of romp, so four labeled reply slots read as a form to fill in rather than a
  // question. A person asking "what shipped, what's next, or what do you need from me" gets the same four
  // answers back. Same rule as the clear-wrap message.
  assert.match(FEED, /what shipped, what's next, or exactly what you/);
  assert.doesNotMatch(FEED, /Status check on this card/, "'card' is romp's word, not one the session knows");
  assert.match(FEED, /text: statusAskOne\(node\.text \|\| "this sub-goal"\), sid: it\.sid/);
  // instant ack: disable + relabel before the round-trip (the ↻ chip takes over on the next push)
  assert.match(FEED, /stat\.disabled = true; stat\.textContent = "Asked";/);
});

test("(A) MODAL-ONLY: the buttons are added AROUND wireNodeZones; the MARK stays pure nav", () => {
  // the Done/Follow up buttons are appended to the line AFTER the shared wireNodeZones call returns, so the
  // mark (goMsg/goWork), the text and the time keep their nav, and the card's inline checklist — which calls
  // the SAME wireNodeZones, unmodified — is untouched. The mark is NO LONGER flipped to an override here.
  const after = FEED.indexOf("const goWork = wireNodeZones(it, node, mark, txt, meta, !repeat);");
  const acts = FEED.indexOf('el("span", "ftree-node-acts")');
  assert.ok(after > 0 && acts > after, "the action buttons are built after wireNodeZones returns");
  assert.match(FEED, /wireNodeZones\(it, s, mark, txt, null, !repeat\);/);   // card sub-goal row (wire=false for a dim repeat)
  // the mark is never re-bound to an override (no .ftree-mark-resolve anywhere)
  assert.doesNotMatch(FEED, /ftree-mark-resolve/);
  assert.doesNotMatch(CSS, /ftree-mark-resolve/);
});

test("(#2) a blocked sub's 'Follow up' button re-targets the footer composer at THAT sub", () => {
  assert.match(FEED, /openSubFollowUp\?\.\(node\.id, node\.text/);
  assert.match(FEED, /el\("button", "ftree-act-btn ftree-act-fup"\)/);
  assert.match(FEED, /fu\.textContent = "Follow up"/);
  // opener points the composer at the sub + reveals/focuses it (the robust footer box, not a per-node draft)
  assert.match(FEED, /openSubFollowUp = \(itemId, title\) =>/);
  assert.match(FEED, /setFollowTarget\(\{ itemId, title \}\)/);
});

test("(#2) the footer composer posts askFollowUp to the picked sub, else the card/group, then reverts", () => {
  // postFollowUp prefers the picked sub's id/title, else the card (single) / first member + group title;
  // the card's sid rides along so a REMOTE card's follow-up routes to its owning kernel (federation).
  assert.match(FEED, /itemId: tgt \? tgt\.itemId : fbId, title: tgt \? tgt\.title : fbTitle/);
  assert.match(FEED, /postFollowUp\(txt, it\.itemId, it\.sid\)/);                // single-ask modal
  assert.match(FEED, /postFollowUp\(txt, grp\.members\[0\]\.itemId, grp\.members\[0\]\.sid, grp\.title\)/);   // group modal
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
