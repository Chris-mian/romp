// The feed card's modal tree node splits into the SAME three click/hover zones as the ledger (the user
// 2026-06-17): the TEXT jumps to the MESSAGE that minted the goal (anchor "prompt" → the user turn, by its
// start time); the MARK + the META time jump to where it got CHECKED OFF / blocked (anchor "work" → the
// assistant turn, by id via anchorUuid). Hovering the mark or the time lights BOTH (shared target); the
// text lights on its own. No jsdom for the feed renderer, so pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("modal node: text → the minting MESSAGE (anchor 'prompt' @ node.t)", () => {
  assert.match(FEED, /const goMsg = \(ev: Event\) => \{[^}]*anchor: "prompt", anchorUuid: null \}/);
  assert.match(FEED, /t: node\.t, anchor: "prompt"/);
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

test("modal node: mark + time are LINKED on hover; text lights alone; styled per zone", () => {
  assert.match(FEED, /linkHover\(\[txt\]\);/);
  assert.match(FEED, /linkHover\(\[mark, meta\]\);/);
  assert.match(CSS, /\.ftree-node \.lz-nav \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.ftree-mark\.lz-hl \{[^}]*box-shadow/);                 // mark = halo ring
  assert.match(CSS, /\.ftree-text\.lz-hl[^{]*\{[^}]*background/);             // text = rounded fill
});

test("modal node shows the planner's rationale INLINE, clickable to where it was authored (the user 2026-06-17)", () => {
  // done → why-done, blocked → why-blocked, else creation why; a dim italic .ftree-why line under the node
  assert.match(FEED, /const whyText = node\.status === "done" \? node\.doneWhy : node\.status === "question" \? node\.blockWhy : node\.why/);
  assert.match(FEED, /el\("div", "ftree-why lz-nav"\)/);
  assert.match(FEED, /\(node\.status === "done" \? "✓ " : node\.status === "question" \? "⏸ " : ""\) \+ whyText/);
  // clickable → goWork (where the planner authored the why = the node's resolution/minting segment)
  assert.match(FEED, /w\.onclick = goWork/);
  assert.match(CSS, /\.ftree-why \{/);
  assert.match(CSS, /\.ftree-why\.lz-nav \{[^}]*cursor: pointer/);
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
