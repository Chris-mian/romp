// The feed card's modal tree node splits into the SAME three click/hover zones as the ledger (the user
// 2026-06-17): the TEXT jumps to the MESSAGE that minted the goal (anchor "prompt" → the user turn, by its
// start time); the MARK + the META time jump to where it got CHECKED OFF / blocked (anchor "work" → the
// assistant turn, by id via anchorUuid). Hovering the mark or the time lights BOTH (shared target); the
// text lights on its own. No jsdom for the feed renderer, so pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the modal shows the DISTILLER's per-node line (summary/blockSummary) but NO why/generating (restored 2026-06-29)", () => {
  // a done node's takeaway / a blocked node's decision brief, via the SAME executable rule as the card
  // (./distiller-line, behaviorally tested in distiller-line.test.ts); shown only when produced.
  assert.match(FEED, /el\("div", "ftree-summary"\)/);
  assert.match(FEED, /const nodeDistill = distillText\(node\.status === "done", node\.status === "question",\s*node\.summary, node\.blockSummary\)/);
  assert.match(FEED, /if \(nodeDistill\) \{/);
  // the planner's per-node why-rationale lines + the "(generating…)" placeholder stay GONE (the user 2026-06-27/29)
  assert.doesNotMatch(FEED, /ftree-why/);
  assert.doesNotMatch(FEED, /"\(generating…\)"/);
});

test("modal node: text → the minting MESSAGE (anchor 'prompt', resolves by promptAnchorUuid)", () => {
  // the prompt jump now carries the node's promptAnchorUuid (the user's minting turn) → resolves BY ID, not
  // the old anchorUuid:null + time-landing (kernel 92e23ff + bugs' contract).
  // goMsg is multi-statement now (it falls back to goWork when a node has no minting message — see the
  // fallback test in feed-nav-hover); the prompt emit it still carries is pinned by the next two asserts.
  assert.match(FEED, /const goMsg = \(ev: Event\) => \{/);
  assert.match(FEED, /t: node\.t, anchor: "prompt", anchorUuid: node\.promptAnchorUuid \?\? null/);
  assert.match(FEED, /txt\.classList\.add\("lz-nav"\); txt\.title = "jump to the message that asked for this"; txt\.onclick = goMsg/);
});

test("modal node: mark + time → where it got CHECKED OFF (anchor 'work' @ resolveT, by anchorUuid)", () => {
  assert.match(FEED, /const resolveT = \(resolved && node\.mt\) \? node\.mt : node\.t/);
  assert.match(FEED, /const goWork = \(ev: Event\) => \{[^}]*t: resolveT, anchor: "work", anchorUuid: node\.anchorUuid \?\? null \}/);
  assert.match(FEED, /mark\.classList\.add\("lz-nav"\);[^\n]*mark\.onclick = goWork/);
  assert.match(FEED, /meta\.classList\.add\("lz-nav"\);[^\n]*meta\.onclick = goWork/);
  // the old whole-line jump is gone
  assert.doesNotMatch(FEED, /line\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); vscodeApi\?\.postMessage\(\{ type: "showOnTimeline"/);
});

test("RESOLVED node (shared wireNodeZones): mark + time LINKED on hover; text lights alone; styled per zone", () => {
  // the zone logic is factored into wireNodeZones, shared by the modal AND the card sub-goal checklist
  assert.match(FEED, /function wireNodeZones\(it: AskItem, node: AskTreeNode, mark: HTMLElement, txt: HTMLElement, meta: HTMLElement \| null, wire: boolean\)/);
  assert.match(FEED, /if \(resolved\) \{/);                                   // the 3-way split is gated on resolved
  assert.match(FEED, /linkHover\(\[txt\]\);/);
  assert.match(FEED, /linkHover\(meta \? \[mark, meta\] : \[mark\]\);/);       // mark + time pair (time only when present)
  assert.match(CSS, /\.ftree-node \.lz-nav \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.ftree-mark\.lz-hl \{[^}]*box-shadow/);                 // mark = halo ring
  assert.match(CSS, /\.ftree-text\.lz-hl[^{]*\{[^}]*background/);             // text = rounded fill
});

test("card sub-goals click EXACTLY like the modal — same wireNodeZones, separate links (the user 2026-06-17)", () => {
  // the modal tree node and the card's inline sub-goal checklist BOTH call wireNodeZones, so they navigate
  // identically; the card has no time cell so it passes null for meta.
  assert.match(FEED, /const goWork = wireNodeZones\(it, node, mark, txt, meta, !repeat\);/);   // modal
  assert.match(FEED, /wireNodeZones\(it, s, mark, txt, null, true\);/);                        // card sub-goal row
  assert.match(CSS, /\.fcheck \.lz-nav \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fcheck-mark\.lz-hl \{[^}]*box-shadow/);                                 // checkbox = halo
  assert.match(CSS, /\.fcheck-text\.lz-hl \{[^}]*background/);                                  // text = fill
});

test("modal UNRESOLVED node: checkbox + text light together, checkbox STAYS a circle (the user 2026-06-17)", () => {
  // not yet checked off / blocked → the mark points at the SAME message as the text and they light together,
  // but each keeps its own shape: the checkbox is its CIRCULAR halo, never a square (no .lz-merge fill).
  // auth rider (plan-sync authoritative tier): an agent's OWN to-do item has no minting user message,
  // so its mark jumps to the latest work instead — a plain judge node keeps the goMsg wiring.
  assert.match(FEED, /mark\.title = node\.auth \? "jump to the latest work on this to-do item" : "jump to the message that asked for this"/);
  assert.match(FEED, /mark\.onclick = node\.auth \? goWork : goMsg/);
  assert.match(FEED, /linkHover\(\[mark, txt\]\)/);
  assert.match(CSS, /\.ftree-mark\.lz-hl \{[^}]*box-shadow/);   // checkbox highlight = circular halo
  assert.doesNotMatch(CSS, /lz-merge/);                          // no square/bridged merge fill
});

test("an OPEN node no longer shows a creation 'why' line (removed 2026-06-27 — just the goal text)", () => {
  assert.doesNotMatch(FEED, /node\.status === "open" && node\.why/);
  assert.doesNotMatch(FEED, /ftree-why/);
  assert.doesNotMatch(CSS, /\.ftree-why/);
});

test("modal BLOCKED node: white-on-red 'BLOCKED' chip + red '?' in a red ring; tooltip says 'marked blocked' (the user 2026-06-17)", () => {
  assert.match(FEED, /meta\.textContent = node\.status === "question" \? "BLOCKED"/);
  assert.doesNotMatch(FEED, /"needs you" :/);                                  // the old amber label is gone
  // the BLOCKED label is a white-on-red chip (same red as the feed's Blocked column header)
  assert.match(CSS, /\.st-question \.ftree-meta \{[^}]*background: #c0392b;[^}]*color: #ffffff/);
  // the ? mark is a RED ring, 13px (same as the done ✓ disc), with the ? visible in red — always rendered
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*width: 13px/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*border: 1\.5px solid var\(--err\)/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*color: var\(--err\)/);
  // the mark/time tooltip on a blocked node says "marked blocked", not "checked off"
  assert.match(FEED, /node\.status === "question" \? "jump to where this got marked blocked"/);
});
