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

test("modal node shows the planner's rationale INLINE under it, not just as a tooltip (the user 2026-06-17)", () => {
  // done → why-done, blocked → why-blocked, else creation why; a dim italic .ftree-why line under the node
  assert.match(FEED, /const whyText = node\.status === "done" \? node\.doneWhy : node\.status === "question" \? node\.blockWhy : node\.why/);
  assert.match(FEED, /el\("div", "ftree-why"\)/);
  assert.match(FEED, /\(node\.status === "done" \? "✓ " : node\.status === "question" \? "⏸ " : ""\) \+ whyText/);
  assert.match(CSS, /\.ftree-why \{/);
});

test("modal BLOCKED node: red 'BLOCKED' label + red '?' in a red ring the size of the ✓ disc (the user 2026-06-17)", () => {
  assert.match(FEED, /meta\.textContent = node\.status === "question" \? "BLOCKED"/);
  assert.doesNotMatch(FEED, /"needs you" :/);                                  // the old amber label is gone
  // the ? mark is a RED ring, 13px (same as the done ✓ disc), with the ? visible in red
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*width: 13px/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*border: 1\.5px solid var\(--err\)/);
  assert.match(CSS, /\.st-question \.ftree-mark \{[^}]*color: var\(--err\)/);
  assert.match(CSS, /\.st-question \.ftree-meta \{[^}]*color: var\(--err\)/);
});
