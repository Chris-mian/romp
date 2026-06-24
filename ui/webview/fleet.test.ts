// Fleet — the by-SESSION view that mirrors the chat's ledger box (the user 2026-06-23): each session, then its
// goal TREE (collapsible checkmark nodes, recency-coloured times). It rides the FEED payload (reads `ledgers`),
// renders the same .ledger-* DOM, and copies render.ts's recency-colour helpers so the colours match exactly.
// No jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");

test("fleet rides the FEED payload, reading its per-session `ledgers`", () => {
  assert.match(SRC, /m\.type !== "feed"/);                  // the proven feed channel
  assert.match(SRC, /sessions = Array\.isArray\(m\.ledgers\)/);
});

test("each session renders the real LEDGER TREE — .ledger-* nodes, marks, collapse, recency time", () => {
  assert.match(SRC, /el\("div", "ledger-tree"\)/);
  assert.match(SRC, /"ledger-tnode"/);
  assert.match(SRC, /el\("span", "ledger-tmark"\)/);
  assert.match(SRC, /n\.done \? "✓" : n\.blocked \? "⏸" : ""/);   // the ledger box's marks
  assert.match(SRC, /el\("span", "ledger-tri"/);                   // the collapse triangle
  assert.match(SRC, /el\("span", "ledger-ttext"\)/);
  assert.match(SRC, /el\("span", "ledger-ttime"\)/);
});

test("recency colour is copied VERBATIM from render.ts (identical to the ledger box)", () => {
  assert.match(SRC, /function ageColorReadable\(ageSecs: number\)/);
  assert.match(SRC, /const LO = 120, HI = 345600/);               // the same recency curve
  assert.match(SRC, /function stampSubtreeRecency/);              // the same subtree recency rollup
  assert.match(SRC, /const dt = now - nodeRecency\(n\);/);        // done text/time take the rolled-up recency…
  assert.match(SRC, /time\.style\.color = ageColorReadable\(dt\)/); // …in the shared colour
});

test("completed top goals hide by default; a 'Show completed' checkbox reveals them", () => {
  assert.match(SRC, /localStorage\.getItem\(DONE_KEY\) === "1"/);  // default OFF
  assert.match(SRC, /roots\.filter\(\(n\) => !n\.done && !n\.cleared\)/);
  assert.match(SRC, /createTextNode\("Show completed"\)/);
});

test("a node/header click opens that session (the navigation loop back to its chat)", () => {
  assert.match(SRC, /vscodeApi\?\.postMessage\(\{ type: "openSession", id: s\.sid \}\)/);
});

test("it's a MODULE (own scope) so it doesn't collide with feed.ts's globals", () => {
  assert.match(SRC, /export \{\};/);
});
