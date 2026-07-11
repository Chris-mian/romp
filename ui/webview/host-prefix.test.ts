// A federated session's "host:" name prefix renders as quiet metadata — gray, never bold, italic, a
// step smaller — instead of wearing the session's identity color at full weight (the user 2026-07-11:
// "it's just the host name, not part of the name"). The marker is DESIGNED, not a guess: federation.js
// prefixes both the sid and the display name with "host:", and a local sid (a bare uuid) never
// contains a colon. hostPrefix() is executed here; the per-surface wiring is pinned at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { hostPrefix } from "./host-prefix";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const read = (f: string) => fs.readFileSync(path.join(UI, f), "utf8");

test("hostPrefix splits exactly the federation-prefixed names, nothing else", () => {
  // remote: sid and name share the "host:" prefix → split
  assert.deepEqual(hostPrefix("myhost:nimbus", "myhost:1111-2222"), { host: "myhost:", rest: "nimbus" });
  // local: bare-uuid sid → never split, even if the NAME contains a colon (a name is free text)
  assert.equal(hostPrefix("notes: cleanup", "11111111-2222-3333-4444-555555555555"), null);
  // sid prefixed but the name doesn't carry the same prefix → not a federation-prefixed name
  assert.equal(hostPrefix("nimbus", "myhost:1111-2222"), null);
  // degenerate: empty name-part or missing inputs stay whole
  assert.equal(hostPrefix("myhost:", "myhost:1111"), null);
  assert.equal(hostPrefix("x", null), null);
  assert.equal(hostPrefix(null, "myhost:1111"), null);
});

test("every surface renders the prefix through the shared treatment", () => {
  const RENDER = read("render.ts"), FEED = read("feed.ts"), FLEET = read("fleet.ts");
  // chat tabs (live + placeholder) and the session picker
  assert.match(RENDER, /label\.replaceChildren\(\.\.\.hostNameNodes\(s\.name, id\)\)/);
  assert.match(RENDER, /if \(meta\?\.name\) label\.replaceChildren\(\.\.\.hostNameNodes\(meta\.name, id\)\);/);
  assert.match(RENDER, /name\.replaceChildren\(\.\.\.hostNameNodes\(it\.name, it\.id\)\)/);
  // feed cards (single + group) and the modal headers
  assert.match(FEED, /a\._name\.replaceChildren\(\.\.\.hostNameNodes\(it\.name, it\.sid\)\)/);
  assert.match(FEED, /a\._name\.replaceChildren\(\.\.\.hostNameNodes\(g\.name, g\.sid\)\)/);
  assert.match(FEED, /agent\.replaceChildren\(\.\.\.hostNameNodes\(grp\.name, grp\.sid\)\)/);
  assert.match(FEED, /agent\.replaceChildren\(\.\.\.hostNameNodes\(it\.name, it\.sid\)\)/);
  // fleet: the prefix stays OUT of the search highlight (metadata never highlights)
  assert.match(FLEET, /function nameInto\(elm: HTMLElement, name: string, sid: string, q: string\)/);
  assert.match(FLEET, /nameInto\(tnm, s\.name, s\.sid, curSearch\)/);
  assert.match(FLEET, /nameInto\(nm, s\.name, s\.sid, curSearch\)/);
  // one class, both sheets (the feed page loads only feed.css — the .romp-acted precedent)
  const CSS = read("styles.css"), FCSS = read("feed.css");
  for (const sheet of [CSS, FCSS]) {
    assert.match(sheet, /\.host-prefix \{ color: var\(--dim\); font-weight: 400; font-style: italic; font-size: 0\.88em; \}/);
  }
  // the timeline lane label (one plain-JS file, SVG tspans) applies the same rule off the sid marker
  const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");
  assert.match(TL, /const hci = String\(s\.id \|\| ''\)\.indexOf\(':'\)/);
  assert.match(TL, /'font-style': 'italic', 'font-size': 10\.5/);
});
