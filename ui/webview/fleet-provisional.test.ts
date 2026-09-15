// THE OUTLINE'S PROVISIONAL ROW (plans/outline-pane-provisional-row.md, 2026-09-15): a ledgers row the kernel ships for a tab the
// cold-tab gate skipped (`provisional: true`, its ledger from the goal store alone) renders like any session's, with a light mark
// and its jump actions withheld: the store holds each node's position but a cold tab has no landing (no loaded history, and the
// focus road has no time fallback), so the mark, the text and the time carry no data-act and say what the click cannot do; the
// row's own "open" stays. The pane declares the capability on its dial (the kernel's shim adds the term for the Outline app; the
// extension's host adds it to its own connect URL). No jsdom harness here: pinned at the source, as fleet.test.ts pins the pane.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the row type carries the flag, and a provisional session's section wears the light mark with a title that says why", () => {
  assert.match(SRC, /interface FleetSession \{(?:[^}]|\{[^}]*\})*provisional\?: boolean;/, "the kernel's flag on the row");
  assert.match(SRC, /if \(s\.provisional\) \{ sec\.classList\.add\("fl-prov-sess"\);/, "the section's mark");
  assert.match(SRC, /head\.title = s\.provisional \? "Open this session: its transcript has not been loaded since the restart, so its goals are read from the store and their jumps wait for the tab" : "Open this session";/, "the head says so, and still opens");
  assert.match(CSS, /\n\.fl-prov-sess \.fl-name \{ border-bottom: 1px dashed rgba\(255, 255, 255, 0\.25\); \}/, "the light mark: the provisional cards' dashed underline on the name");
});

test("a provisional session's nodes carry no jump actions: the mark, the text and the time say what the click cannot do, and the row's open stays", () => {
  assert.match(SRC, /const prov = !!ctx\.s\.provisional;\s*\n/, "the node render reads the session's flag");
  assert.match(SRC, /const mark = el\("span", "ledger-tmark" \+ \(prov \? "" : " lz-nav"\)\);/, "no pointer cursor on a withheld mark");
  assert.match(SRC, /if \(!prov\) \{ mark\.dataset\.sid = s\.sid; mark\.dataset\.nid = n\.id; mark\.dataset\.act = resolved \? "gowork" : "goprompt"; \}/, "the mark's jump withheld");
  assert.match(SRC, /const txt = el\("span", "ledger-ttext" \+ \(prov \? "" : " lz-nav"\)\);/);
  assert.match(SRC, /if \(!prov\) \{ txt\.dataset\.sid = s\.sid; txt\.dataset\.nid = n\.id; txt\.dataset\.act = "goprompt"; \}/, "the text's jump withheld");
  assert.match(SRC, /if \(time\.textContent && !prov\) \{ time\.classList\.add\("lz-nav"\)/, "the time's jump withheld");
  assert.match(SRC, /const WITHHELD = "nothing to land on until this tab is built: open the session first";/, "one sentence for what the click cannot do");
  // the hover card is a row's ONE tooltip (fleet.test.ts, the user 2026-07-13: no native titles on the mark or the text, which
  // would pop on top of it), so the withheld line rides the card as a second state line, never a title
  assert.match(SRC, /card\.append\(state\);\n[^\n]*\n  if \(s\.provisional\) \{ const held = el\("div", "fl-hover-state"\); held\.textContent = WITHHELD; card\.append\(held\); \}\n  card\.append\(title\);/, "the withheld line in the hover card");
  assert.doesNotMatch(SRC, /mark\.title = /); assert.doesNotMatch(SRC, /txt\.title = /);
  assert.match(SRC, /row\.dataset\.act = "open"; row\.dataset\.sid = s\.sid;   \/\/ click-safe: action lives on the #fleet-list delegate/, "the row still opens the session");
});
