// The feed card's modal tree node splits into the SAME three click/hover zones as the ledger (the user
// 2026-06-17): the TEXT jumps to the MESSAGE that minted the goal (anchor "prompt" → the user turn, by its
// start time); the MARK + the META time jump to where it got CHECKED OFF / blocked (anchor "work" → the
// assistant turn, by id via anchorUuid). Hovering the mark or the time lights BOTH (shared target); the
// text lights on its own. No jsdom for the feed renderer, so pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.ts"), "utf8");   // the card's sections, tree and badges moved to card-sections.ts, one builder with the Needs you row (plans/needs-you.md)
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.css"), "utf8");   // the card's sections moved to a sheet both pages import (plans/needs-you.md)

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
  // 2026-07-20: the minting-message jump is DONE-only — a non-done node's text answers "where does this
  // stand" (goWork, its newest event) instead; a stale sub's title landed on a bare 'retry' mint before.
  assert.match(FEED, /const goMsg = \(ev: Event\) => \{/);
  assert.match(FEED, /t: node\.t, anchor: "prompt", anchorUuid: node\.promptAnchorUuid \?\? null/);
  assert.match(FEED, /if \(node\.status === "done"\) \{[\s\S]*?txt\.title = "jump to the message that asked for this"; txt\.onclick = goMsg;/);
});

test("modal NON-DONE node: text → the LATEST WORK (goWork), never the mint prompt (the user 2026-07-20)", () => {
  // open + blocked nodes: every zone answers "where does this stand" — text included — and lights as one
  assert.match(FEED, /txt\.title = workTitle; txt\.onclick = goWork;/);
  assert.match(FEED, /linkHover\(meta \? \[mark, txt, meta\] : \[mark, txt\]\);/);
});

test("modal node: mark + time → where it got CHECKED OFF (anchor 'work' @ resolveT, by anchorUuid)", () => {
  assert.match(FEED, /const resolveT = \(resolved && node\.mt\) \? node\.mt : \(node\.last \|\| node\.t\)/);
  // the work anchor falls to the PROMPT anchor rather than dispatching null (the user 2026-07-20: the
  // kernel's cache-only parse goes cold on every transcript write, and a null dispatch can only toast)
  assert.match(FEED, /const goWork = \(ev: Event\) => \{[^}]*t: resolveT, anchor: "work", anchorUuid: node\.anchorUuid \?\? node\.promptAnchorUuid \?\? null \}/);
  assert.match(FEED, /mark\.classList\.add\("lz-nav"\);[^\n]*mark\.onclick = goWork/);
  assert.match(FEED, /meta\.classList\.add\("lz-nav"\);[^\n]*meta\.onclick = goWork/);
  // the old whole-line jump is gone
  assert.doesNotMatch(FEED, /line\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); vscodeApi\?\.postMessage\(\{ type: "showOnTimeline"/);
});

test("DONE node (shared wireNodeZones): mark + time LINKED on hover; text lights alone; styled per zone", () => {
  // the zone logic is factored into wireNodeZones, shared by the modal AND the card sub-goal checklist
  assert.match(FEED, /function wireNodeZones\(it: AskItem, node: AskTreeNode, mark: HTMLElement, txt: HTMLElement, meta: HTMLElement \| null, wire: boolean\)/);
  assert.match(FEED, /if \(node\.status === "done"\) \{/);                    // the 3-way split is DONE-gated now
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
  assert.match(FEED, /env\.wireNode\(it, s, mark, txt, !repeat\);/);                     // card sub-goal row
  assert.match(FEED, /wireNode: \(it, node, mark, txt, wire\) => \{ wireNodeZones\(it as AskItem, node, mark, txt, null, wire\); \},/, "the feed hands the shared builder its own click zones (card-sections.ts calls the environment; the chat page hands a no-op)");
  assert.match(CSS, /\.fcheck \.lz-nav \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fcheck-mark\.lz-hl \{[^}]*box-shadow/);                                 // checkbox = halo
  assert.match(CSS, /\.fcheck-text\.lz-hl \{[^}]*background/);                                  // text = fill
});

test("modal NON-DONE node: checkbox + text light together, checkbox STAYS a circle (the user 2026-06-17)", () => {
  // open/blocked → the mark, text (and time) all point at the node's latest work and light together
  // (2026-07-20 — the old auth-only goWork rider generalized to every non-done node), but each keeps its
  // own shape: the checkbox is its CIRCULAR halo, never a square (no .lz-merge fill).
  assert.match(FEED, /mark\.classList\.add\("lz-nav"\); mark\.title = workTitle; mark\.onclick = goWork;/);
  assert.match(FEED, /linkHover\(meta \? \[mark, txt, meta\] : \[mark, txt\]\)/);
  assert.match(CSS, /\.ftree-mark\.lz-hl \{[^}]*box-shadow/);   // checkbox highlight = circular halo
  assert.doesNotMatch(CSS, /lz-merge/);                          // no square/bridged merge fill
});

test("an OPEN node no longer shows a creation 'why' line (removed 2026-06-27 — just the goal text)", () => {
  assert.doesNotMatch(FEED, /node\.status === "open" && node\.why/);
  assert.doesNotMatch(FEED, /ftree-why/);
  assert.doesNotMatch(CSS, /\.ftree-why/);
});

test("modal NEEDS YOU node: a 'Needs you' chip and a '?' in a ring, both in the category's colour; tooltip says 'filed under Needs you' (the user 2026-06-17; the colour the category's since 2026-09-20)", () => {
  // rolled-up ancestors (qderived) say "Needs you inside"; the actual ask says "Needs you" (the user 2026-07-11; the word the category's since 2026-09-20)
  assert.match(FEED, /meta\.textContent = node\.status === "question" \? \(node\.qderived \? "Needs you inside" : "Needs you"\)/);
  assert.doesNotMatch(FEED, /"needs you" :/);                                  // the old amber label is gone
  // the label is a chip in the Needs you colour (the same token as the feed's Needs you column header; plans/needs-you.md)
  assert.match(CSS, /\.st-question \.ftree-meta \{[^}]*background: var\(--st-needs-bg\);[^}]*color: var\(--st-needs-fg\)/);
  // the ? mark is a ring in the same colour, 13px (same as the done ✓ disc), with the ? visible; red is the hard stop's alone
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*width: 13px/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*border: 1\.5px solid var\(--st-needs-bg\)/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*color: var\(--st-needs-bg\)/);
  assert.doesNotMatch(CSS, /\.st-question \.ftree-mark \{[^}]*var\(--err\)/, "no red on a question mark");
  // the mark/time tooltip on a node that needs you in its OWN right says "filed under Needs you", not "checked off"
  assert.match(FEED, /node\.status === "question" && !node\.qderived \? "jump to where this was filed under Needs you"/);
});
