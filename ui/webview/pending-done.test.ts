// The modal's "Done" on a sub-goal acknowledges INSTANTLY (the user 2026-07-23, for whom it felt very
// slow). It used to post and paint nothing, so the tick waited on a goal-store write, a rollup and a
// full feed rebuild — while Drop and Check status beside it already acknowledged on click.
//
// Two properties matter beyond "it paints early", and both are pinned here:
//   1. the optimistic state is STICKY, not a one-shot DOM edit. The feed re-renders on every kernel
//      push, and a push already in flight when the click happened still carries the OLD tree, so a
//      one-shot paint would flip the tick straight back off.
//   2. it can be WRONG, and then it must say so. A cross-off that quietly un-crossed itself a second
//      later would be worse than the slow version it replaced.
// Source pins (no jsdom for the feed renderer), as with the other feed-* tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("Done records the node and repaints before the kernel is heard from", () => {
  const i = FEED.indexOf('done.onclick = (ev) => {');
  const fn = FEED.slice(i, FEED.indexOf("};", i));
  assert.match(fn, /pendingDone\.add\(node\.id\);/, "remembered, so re-renders keep the tick");
  assert.match(fn, /postMessage\(\{ type: "nodeOverride", sid: it\.sid, nodeId: node\.id, op: "resolve" \}\)/);
  assert.match(fn, /renderModal\(\);/, "repainted on the click, not on the round trip");
  // the add must precede the repaint, or the repaint reads the old set and paints nothing
  assert.ok(fn.indexOf("pendingDone.add") < fn.indexOf("renderModal()"), "record, then repaint");
});

test("the optimistic node is rewritten to done, so every part of the line agrees", () => {
  // mark, status class, the Blocked label and the action buttons all derive from node.status; patching
  // them one by one is how an optimistic line drifts from how a genuinely-done node draws.
  assert.match(FEED, /if \(!repeat && pendingDone\.has\(node\.id\) && node\.status !== "done"\) node = \{ \.\.\.node, status: "done" \};/);
});

test("an optimistic tick is retired by the authoritative tree, not by a timer", () => {
  const i = FEED.indexOf("function reconcilePendingDone");
  const fn = FEED.slice(i, FEED.indexOf("\n}", i));
  assert.match(fn, /if \(st === "done" \|\| st === undefined\) pendingDone\.delete\(id\);/,
    "done → the kernel caught up; absent → the node is gone and holding the flag would leak it");
  assert.doesNotMatch(fn, /setTimeout/, "event-based, never a grace period (CLAUDE.md)");
  // and it actually runs on every payload
  assert.match(FEED, /reconcilePendingDone\(incomingAsks\);/);
});

test("a refused Done reverts the tick and says why, out loud", () => {
  const i = FEED.indexOf('m.type === "nodeOverrideResult"');
  const fn = FEED.slice(i, FEED.indexOf("} else if", i));
  assert.match(fn, /if \(!m\.ok\) \{/, "agreement is silent; only disagreement acts");
  assert.match(fn, /pendingDone\.delete\(m\.nodeId\);/, "the tick comes back off");
  assert.match(fn, /renderModal\(\);/);
  assert.match(fn, /feedToast\("couldn't mark that sub-goal done: "/, "and the reason is shown");
  assert.match(fn, /String\(m\.error \|\| ""\) \|\| "the kernel refused it"/, "never an empty explanation");
});

test("Done now acknowledges like the buttons beside it", () => {
  // Drop and Check status were already instant; Done being the only laggard is what made it feel broken.
  const drop = FEED.slice(FEED.indexOf("drop.onclick = (ev) => {"), FEED.indexOf("// \"Check status\""));
  assert.match(drop, /line\.classList\.add\("st-cleared"\)/, "Drop still acknowledges on click");
  const stat = FEED.slice(FEED.indexOf("stat.onclick = (ev) => {"), FEED.indexOf("acts.append(done, drop, stat)"));
  assert.match(stat, /stat\.textContent = "Asked";/, "Check status still acknowledges on click");
});
