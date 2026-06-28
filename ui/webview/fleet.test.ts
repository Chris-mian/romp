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
  assert.match(SRC, /el\("span", "ledger-tmark lz-nav"\)/);
  assert.match(SRC, /n\.done \? "✓" : n\.blocked \? "⏸" : ""/);   // the ledger box's marks
  assert.match(SRC, /el\("span", "ledger-tri"/);                   // the collapse triangle
  assert.match(SRC, /el\("span", "ledger-ttext lz-nav"\)/);
  assert.match(SRC, /el\("span", "ledger-ttime"\)/);
});

test("ledger parity (the user 2026-06-24): pointer-cursor zones + grouped hover highlight (no ⊕ summary expander)", () => {
  // .lz-nav → the pointer cursor (styles.css) on the checkbox / text / time, so each reads as clickable
  assert.match(SRC, /"ledger-tmark lz-nav"/);
  assert.match(SRC, /"ledger-ttext lz-nav"/);
  assert.match(SRC, /if \(time\.textContent\) \{ time\.classList\.add\("lz-nav"\)/);
  // grouped hover (.lz-hl toggled together) — the ledger box's linkHover, ported verbatim
  assert.match(SRC, /function linkHover\(group: HTMLElement\[\]\)/);
  assert.match(SRC, /g\.classList\.add\("lz-hl"\)/);
  assert.match(SRC, /linkHover\(\[mark, txt\]\)/);                  // open node: checkbox + text are one block
  assert.match(SRC, /linkHover\(time\.textContent \? \[mark, time\] : \[mark\]\)/);   // resolved: checkbox + time
  // the ⊕/⊖ distiller-summary expander + its panel + delegate were removed 2026-06-27 (just the goals now)
  assert.doesNotMatch(SRC, /ledger-tsum/);
  assert.doesNotMatch(SRC, /sumToggle/);
  assert.doesNotMatch(SRC, /sumOpen/);
  assert.doesNotMatch(SRC, /sum: \(el\) => \{/);
});

test("a session-level collapse caret folds the whole session's tree WITHOUT opening it (the user 2026-06-24)", () => {
  // the caret is in the .fl-head but carries its OWN data-act="sessfold" (innermost), so a click on it folds
  // while a click on the name (data-act="open") still jumps into the session.
  assert.match(SRC, /const sessFolded = new Set<string>\(\)/);
  assert.match(SRC, /caret\.dataset\.act = "sessfold"; caret\.dataset\.sid = s\.sid;/);
  assert.match(SRC, /head\.appendChild\(caret\)/);
  // folded → render the head only, skip the tree
  assert.match(SRC, /if \(!sfolded\) \{ for \(const r of visibleRoots\) renderNode\(r, 0\); sec\.appendChild\(treeBox\); \}/);
  // the delegate toggles per-session fold, separate from the row "open" action
  assert.match(SRC, /sessfold: \(el\) => \{/);
  assert.match(SRC, /if \(sessFolded\.has\(sid\)\) sessFolded\.delete\(sid\); else sessFolded\.add\(sid\);/);
});

test("recency colour is copied VERBATIM from render.ts (identical to the ledger box)", () => {
  assert.match(SRC, /function ageColorReadable\(ageSecs: number\)/);
  assert.match(SRC, /const LO = 120, HI = 345600/);               // the same recency curve
  assert.match(SRC, /function stampSubtreeRecency/);              // the same subtree recency rollup
  assert.match(SRC, /const dt = now - nodeRecency\(n\);/);        // done text/time take the rolled-up recency…
  assert.match(SRC, /time\.style\.color = ageColorReadable\(dt\)/); // …in the shared colour
});

test("completed top goals hide by default; a 'Show completed' chip sits bottom-right (the user 2026-06-24)", () => {
  assert.match(SRC, /localStorage\.getItem\(DONE_KEY\) === "1"/);  // default OFF
  // the top-row selection (open-only vs +done +archived) is the pure, BEHAVIORALLY-tested ./fleet-roots
  // (fleet-roots.test.ts) — here we just pin that fleet.ts routes through it (the user 2026-06-27)
  assert.match(SRC, /import \{ fleetVisibleRoots \} from "\.\/fleet-roots"/);
  assert.match(SRC, /const visibleRoots = fleetVisibleRoots\(roots, archivedTops, sd\)/);
  assert.match(SRC, /createTextNode\("Show completed"\)/);
  // it shares ONE floating bottom-right row with the recency slider now (the user 2026-06-27); #fleet-foot is hidden
  assert.match(SRC, /function mountControls\(\)/);
  assert.match(SRC, /position:fixed;bottom:8px;right:10px/);
  assert.match(SRC, /foot\.style\.display = "none"/);
});

test("Fleet restores the ledger box's per-node mark TOOLTIP (the user 2026-06-24)", () => {
  // the checkbox explains WHY it reads the way it does — explicit / inferred (roll-up vs roll-down) / dismissed
  // / blocked / open — plus the full goal text on the row's text zone (it can clip in the narrow Fleet pane).
  assert.match(SRC, /const markReason = \(\): string =>/);
  assert.match(SRC, /"done — inferred: every sub-step is complete"/);
  assert.match(SRC, /"done — inferred: a parent goal was checked off"/);
  assert.match(SRC, /"completed, then dismissed \(cleared\)"/);
  assert.match(SRC, /mark\.title = markReason\(\);/);
  assert.match(SRC, /txt\.title = n\.text;/);
});

test("a node/header click opens that session AND flips back to chat (the user 2026-06-24)", () => {
  // openSession() posts openSession to the kernel AND asks the shell to leave the Fleet view (the tab bar —
  // which holds the Fleet toggle — is hidden while Fleet is shown, so picking a session must return there).
  assert.match(SRC, /function openSession\(sid: string\) \{ vscodeApi\?\.postMessage\(\{ type: "openSession", id: sid \}\); backToChat\(\); \}/);
  // click-safe (the user 2026-06-24): the open action is DELEGATED to the stable #fleet-list (render() rebuilds
  // its children every push, so a per-node onclick gets dropped mid-click) — see click-safe.test.ts. The
  // header + each row declare data-act="open" + data-sid; the delegate routes them to openSession.
  assert.match(SRC, /open: \(el\) => \{ const sid = el\.dataset\.sid; if \(sid\) openSession\(sid\); \}/);
  assert.match(SRC, /head\.dataset\.act = "open"; head\.dataset\.sid = s\.sid;/);
  assert.match(SRC, /row\.dataset\.act = "open"; row\.dataset\.sid = s\.sid;/);
  // leaving Fleet is now the shell strip's "Chat" toggle; openSession still returns via {romp:"toggleFleet", to:"chat"}
  assert.match(SRC, /window\.parent\.postMessage\(\{ romp: "toggleFleet", to: "chat" \}/);
});

test("fleet nodes DEEP-LINK to the same place the feed modal does (the user 2026-06-27)", () => {
  // the node carries the kernel's per-node anchor uuids (already sent in build_session's tree)
  assert.match(SRC, /promptAnchorUuid\?: string \| null; anchorUuid\?: string \| null;/);
  // zones declare data-act mirroring the modal: TEXT → the asking message; a RESOLVED mark/time → the work
  assert.match(SRC, /txt\.dataset\.act = "goprompt"/);
  assert.match(SRC, /mark\.dataset\.act = resolved \? "gowork" : "goprompt"/);
  assert.match(SRC, /time\.dataset\.act = "gowork"/);
  // delegated (click-safe) through fleetNavTo, which posts the SAME showOnTimeline message shape as feed.ts
  assert.match(SRC, /goprompt: \(el\) => fleetNavTo\(el, "prompt"\)/);
  assert.match(SRC, /gowork: \(el\) => fleetNavTo\(el, "work"\)/);
  assert.match(SRC, /vscodeApi\?\.postMessage\(\{ type: "showOnTimeline", itemId: nid, sid, t, anchor: kind, anchorUuid \}\)/);
  // work jump uses the resolved node's mt (where it resolved), prompt jump uses its start t — like wireNodeZones
  assert.match(SRC, /const t = kind === "work" \? \(\(resolved && n\.mt\) \? n\.mt : n\.t\) : n\.t;/);
});

test("it's a MODULE (own scope) so it doesn't collide with feed.ts's globals", () => {
  assert.match(SRC, /export \{\};/);
});
