// The Artifacts pane's pure parts (plans/artifacts-pane.md): the grid's rule, the cycle's order, the rule words, the row
// click's route, the age words; and source pins on the pieces outside the kernel (the retired setting dropped, the gear's generic row, the
// bundle entries). The kernel's walk, listing, op, route and shell hooks are pinned in tests/test_artifacts_list.py; the
// behaviour rides tests/test_artifacts_pane_served.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { gridItems, cycleEntries, viaWord, rowRoute, ago, type ArtifactItem, nextSelection, normalizeTabs, shownRow } from "./artifacts-model";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const item = (p: string, over: Partial<ArtifactItem> = {}): ArtifactItem =>
  ({ path: p, name: p.slice(p.lastIndexOf("/") + 1), t: 100, via: "write", exists: true, size: 10, mtime: 100, kind: "other", refused: "", ...over });

test("the grid shows the existing, allowed images and nothing else; the cycle is the grid's order with the session's sid", () => {
  const items = [
    item("/srv/notes-api/figures/accuracy.png", { kind: "image", t: 400 }),
    item("/srv/notes-api/report.md", { kind: "markdown", t: 300 }),
    item("/srv/notes-api/figures/gone.png", { kind: "image", exists: false, t: 200 }),
    item("/srv/notes-api/.env.png", { kind: "image", refused: "a secrets-shaped name", t: 150 }),
    item("/srv/notes-api/figures/loss.png", { kind: "image", t: 100 }),
  ];
  assert.deepEqual(gridItems(items).map((i) => i.name), ["accuracy.png", "loss.png"], "a missing or refused image has no thumbnail; a document is a row, not a tile");
  assert.deepEqual(cycleEntries(items, "S1"), [{ path: "/srv/notes-api/figures/accuracy.png", sid: "S1" }, { path: "/srv/notes-api/figures/loss.png", sid: "S1" }], "newest first, the listing's order");
});

test("the rule words and the age words", () => {
  assert.deepEqual(["write", "edit", "multiedit", "notebook", "rendered", "drop", "other"].map(viaWord), ["written", "edited", "edited", "notebook", "shown", "dropped", "other"]);
  assert.equal(ago(5), "just now"); assert.equal(ago(125), "2 min ago"); assert.equal(ago(3600), "1 hour ago"); assert.equal(ago(7300), "2 hours ago"); assert.equal(ago(86400 * 3), "3 days ago");
});

test("a row click walks the chat's ladder: an open Files pane takes it, else the file opens here", () => {
  assert.equal(rowRoute(true, { files: true }, { files: true }), "pane");
  assert.equal(rowRoute(true, { files: false }, { files: true }), "here", "the pane closed: here");
  assert.equal(rowRoute(true, { files: true }, { files: false }), "here", "no Files control: nothing to bring forward");
  assert.equal(rowRoute(false, { files: true }, { files: true }), "here", "standalone /artifacts has no shell");
});

test("the pieces outside the kernel: the retired setting dropped at load, the gear's generic Panes row as the control, the bundle entries", () => {
  const SETTINGS = fs.readFileSync(path.join(UI, "settings.ts"), "utf8");
  const KERNEL = fs.readFileSync(path.join(UI, "..", "..", "kernel", "kernel.py"), "utf8");
  const BUILD = fs.readFileSync(path.resolve(process.cwd(), "esbuild.js"), "utf8");
  const GEAR = fs.readFileSync(path.join(UI, "gear.js"), "utf8");
  // the pane is an EXPERIMENTAL record in the kernel's _CODE_PANES (plans/panes-as-data.md, phase three): the gear's generic Panes row
  // (gear.js renderRegistryRows, off by default for an experimental pane) is its control; the bespoke showArtifactsControl key is gone
  assert.match(KERNEL, /\{"id": "artifacts", "title": "Artifacts", "source": "\/artifacts", "on": False, "experimental": True\}/, "the record: off by default, asked for in the gear");
  assert.doesNotMatch(SETTINGS, /showArtifactsControl: boolean|showArtifactsControl: false|s\.showArtifactsControl =/, "no bespoke setting key: no field, no default, no normalization (only the retired key's drop at load, pinned below)");
  assert.doesNotMatch(GEAR, /rs-artctl/, "no bespoke gear row");
  assert.match(GEAR, /delete o\.showArtifactsControl;/, "the gear's load() drops the retired key (save() writes the whole object, so a kept key was re-persisted forever)");
  assert.match(GEAR, /var BUILTIN_HINTS = \{ artifacts: 'A session\\'s written, shown and dropped files as a list and a grid of large thumbnails\.' \};/, "the shipped record's row says what the pane shows (its first landing's words)");
  assert.match(GEAR, /\(p\.builtin \? \(\(BUILTIN_HINTS\[p\.id\] \|\| ''\) && BUILTIN_HINTS\[p\.id\] \+ ' '\) : 'A pane defined at the kernel \(romp pane\)\. '\)/, "a data pane's row says it is defined at the kernel");
  assert.match(GEAR, /'Off' \+ \(p\.experimental \? ' \(the default for an experimental pane\)' : ''\)/, "the experimental default is said only where it applies");
  assert.match(SETTINGS, /delete \(s as Record<string, unknown>\)\.showArtifactsControl;/, "the retired key is dropped at load, like the repo's other retired keys");
  assert.match(BUILD, /"\.\.\/ui\/webview\/artifacts\.ts",/); assert.match(BUILD, /"\.\.\/ui\/webview\/artifacts-pane\.css",/);
  const ART = fs.readFileSync(path.join(UI, "artifacts.ts"), "utf8");
  assert.match(ART, /ask\(\{ type: "listArtifacts", sid: sel\.sid, reqId: lastReq \}\);/, "one request, by id");
  assert.match(ART, /if \(m\.reqId !== lastReq \|\| m\.sid !== sel\.sid\) return;/, "a slow answer for an earlier selection is dropped, never rendered");
  assert.match(ART, /window\.parent\.postMessage\(\{ romp: "viewFile", path: p, sid: sel\.sid, pane: "pane", frag: null \}, "\*"\);/, "the shell's existing relay sends a picture to the Files pane");
  assert.match(ART, /img\.src = fileUrl\(it\.path, sel\.sid\);/, "thumbnails through the token-authed file route with the session's sid");
  assert.doesNotMatch(ART, /new WebSocket|fetch\(/, "no file server of its own, no fetch: the route and the socket the shim gives it");
  // round two (2026-09-19): the cap says the newest of more, once; a kind the viewer does not show is listed plain and a click says so
  assert.match(ART, /count\.textContent = listing\.capped \? "the newest " \+ listing\.max \+ " files of more" : listing\.items\.length \+ \(listing\.items\.length === 1 \? " file" : " files"\);/);
  assert.match(ART, /if \(it\.kind === "other"\) \{ note\("The viewer cannot show " \+ it\.name \+ ": not a kind it renders\."\); return; \}/);
});

// ── pass two (plans/artifacts-pane.md section 9) ─────────────────────────────────────────────────────────────────────
test("the selection machine: unlocked follows whatever came last, locked stays, only the lock button changes the lock", () => {
  let s = { sid: null as string | null, locked: false };
  s = nextSelection(s, { type: "activeChat", id: "A" }); assert.deepEqual(s, { sid: "A", locked: false }, "unlocked: the chat's tab");
  s = nextSelection(s, { type: "pick", id: "B" }); assert.deepEqual(s, { sid: "B", locked: false }, "a pick shows the session and does NOT lock (the manager's correction, 2026-09-20)");
  s = nextSelection(s, { type: "activeChat", id: "C" }); assert.deepEqual(s, { sid: "C", locked: false }, "unlocked: the next tab switch replaces the pick");
  s = nextSelection(s, { type: "activeChat", id: null }); assert.deepEqual(s, { sid: "C", locked: false }, "no tab shown selects nothing new");
  s = nextSelection(s, { type: "toggleLock" }); assert.deepEqual(s, { sid: "C", locked: true }, "the lock button locks, on the shown session");
  s = nextSelection(s, { type: "activeChat", id: "D" }); assert.deepEqual(s, { sid: "C", locked: true }, "locked: a tab switch leaves it");
  s = nextSelection(s, { type: "pick", id: "E" }); assert.deepEqual(s, { sid: "E", locked: true }, "locked: a pick replaces the locked session and the lock stays on");
  s = nextSelection(s, { type: "tabsChanged", tabs: [] }); assert.deepEqual(s, { sid: "E", locked: true }, "a closed tab keeps the selection (the button says not open)");
  s = nextSelection(s, { type: "toggleLock" }); assert.deepEqual(s, { sid: "E", locked: false }, "unlocking keeps the shown session until the next switch (nothing new was selected)");
});

test("the picker's rows are the shell's union made safe; the shown session's row, or a stub marked not open", () => {
  const rows = normalizeTabs([{ id: "S1", name: "web", color: { bg: "#1EA1EB", fg: "#fff" } }, { id: "TESTHOST:S2", name: "TESTHOST:api", color: null }, { id: "S1", name: "dup" }, { name: "no id" }, null]);
  assert.deepEqual(rows, [{ id: "S1", name: "web", color: { bg: "#1EA1EB", fg: "#fff" } }, { id: "TESTHOST:S2", name: "TESTHOST:api", color: null }], "one row per id, the first wins, a row without an id dropped, the order kept");
  assert.deepEqual(shownRow(rows, "TESTHOST:S2"), { row: rows[1], open: true });
  assert.deepEqual(shownRow(rows, "11111111-2222-3333-4444-000000000931"), { row: { id: "11111111-2222-3333-4444-000000000931", name: "11111111", color: null }, open: false }, "a selection no tab shows and never did: a stub, not open");
  const known = new Map([["11111111-2222-3333-4444-000000000931", { id: "11111111-2222-3333-4444-000000000931", name: "tests", color: { bg: "#E5484D", fg: "#fff" } }]]);
  assert.deepEqual(shownRow(rows, "11111111-2222-3333-4444-000000000931", known), { row: known.get("11111111-2222-3333-4444-000000000931")!, open: false }, "a tab that closed keeps its last known name and colour, marked not open (round two, low d)");
  assert.deepEqual(shownRow(rows, "TESTHOST:11111111-2222-3333-4444-000000000931").row!.name, "TESTHOST:11111111", "a remote stub keeps its host prefix");
  assert.deepEqual(shownRow(rows, null), { row: null, open: false });
});

test("the page: the picker in the strip's label and the menu card, the lock, the watch, the shell's signals, no Refresh, no native select", () => {
  const ART = fs.readFileSync(path.join(UI, "artifacts.ts"), "utf8");
  assert.match(ART, /import \{ sessionLabelNodes, hostOf \} from "\.\/host-prefix";/, "the strip's label, shared (and the host of a sid, for the re-arm)");
  assert.match(ART, /import \{ menuCard, showMenuCard, closeContextMenu \} from "\.\/ctx-menu";/, "the card is the menu builder's");
  assert.match(ART, /pick\.append\(\.\.\.sessionLabelNodes\(shown\.row\.name, shown\.row\.id, shown\.row\.color\)\);/, "the button wears the label");
  assert.match(ART, /b\.append\(\.\.\.sessionLabelNodes\(t\.name, t\.id, t\.color\)\); row\.appendChild\(b\);/, "each row wears the label");
  assert.match(ART, /const card = menuCard\(\{ className: "art-picker", id: "art-picker" \}\);/);
  assert.match(ART, /apply\(\{ type: "pick", id \}\)/, "a row click is a pick through the machine");
  assert.match(ART, /"art-lock": \(\) => apply\(\{ type: "toggleLock" \}\),/, "the lock button toggles through the machine");
  assert.match(ART, /if \(m\.romp === "chatTabs"\) \{ tabs = normalizeTabs\(m\.tabs\); for \(const t of tabs\) known\.set\(t\.id, t\); apply\(\{ type: "tabsChanged", tabs \}\); return; \}/, "the shell's union, every tab's name remembered");
  assert.match(ART, /if \(m\.romp === "activeChat" \|\| m\.type === "activeChat"\) \{ apply\(\{ type: "activeChat", id: typeof m\.id === "string" && m\.id \? m\.id : null \}\); return; \}/, "the shell's relay and the kernel's frame");
  assert.match(ART, /ask\(\{ type: "watchArtifacts", sid: watched, unwatch: true \}\);/, "the previous watch dropped on its own kernel");
  assert.match(ART, /if \(sid\) ask\(\{ type: "watchArtifacts", sid \}\);/, "the shown session watched");
  assert.match(ART, /if \(m\.type === "artifactsChanged"\) \{[^\n]*\n\s*if \(m\.sid !== sel\.sid\) return;[^\n]*\n\s*if \(onScreen\(\)\) requestListing\(\); else stale = true;/, "growth: re-ask on screen, stale off screen");
  assert.match(ART, /if \(!framed\) requestSessions\(\);/, "the picker's list only for a page with no shell");
  assert.match(ART, /vscodeApi\?\.postMessage\(\{ type: "ready" \}\);/, "the handshake every pane sends: the kernel's active chat comes on it (9.5)");
  assert.match(ART, /window\.addEventListener\("romp:wsup", \(\) => rearm\(""\)\);/, "the watch re-armed on the local socket's (re)open (round two, medium)");
  assert.match(ART, /window\.addEventListener\("romp:hostRelayUp", \(ev\) => rearm\(String\(\(ev as CustomEvent\)\.detail\?\.host \|\| ""\)\)\);/, "…and on a host's relay socket reopening");
  assert.match(ART, /ask\(\{ type: "watchArtifacts", sid: sel\.sid \}\); watched = sel\.sid;\s*\n\s*if \(onScreen\(\)\) requestListing\(\); else stale = true;/, "the re-arm never depends on the sid changing, and re-asks the listing");
  assert.match(ART, /if \(hadFocus\) document\.getElementById\(hadFocus\)\?\.focus\(\);/, "a repaint keeps the focus on the bar's button (round two, low c)");
  assert.match(ART, /const shown = shownRow\(tabs, sel\.sid, known\);/, "the last known name for a closed tab (low d)");
  assert.doesNotMatch(ART, /art-refresh|"Refresh"|createElement\("select"\)|art-dot/, "no Refresh button, no native select, no identity dot");
  assert.match(ART, /localStorage\.setItem\(LOCK_KEY, on \? "1" : "0"\)/, "the lock persists per browser");
  const HP = fs.readFileSync(path.join(UI, "host-prefix.ts"), "utf8");
  assert.match(HP, /export function sessionLabelNodes\(name: string, sid: string \| null \| undefined, color: \{ bg: string; fg: string \} \| null \| undefined\): Node\[\]/, "the shared label helper beside hostNameNodes");
  assert.match(HP, /span\.className = "session-name" \+ \(bg \? " colored" : ""\);/);
  const CSS = fs.readFileSync(path.join(UI, "styles.css"), "utf8");
  assert.match(CSS, /\.session-name\.colored \{ color: var\(--chip-bg\); color: oklch\(from var\(--chip-bg\) var\(--peer-ink-l, l\) c h\); \}/, "the strip's ink through the T390 lightness floor");
  const RENDER = fs.readFileSync(path.join(UI, "render.ts"), "utf8");
  assert.match(RENDER, /noteOrphanState\(\);[^\n]*\n\s*postChatTabs\(ids\.filter\(\(id\) => heldHere\(id\) && !isSubId\(id\) && !isProvisionalId\(id\)\)\);/, "the column posts its OWN membership (the partition, not the display-narrowed subset) from renderTabs");
  assert.match(RENDER, /window\.parent\.postMessage\(\{ romp: "chatTabs", tabs \}, "\*"\);/);
  assert.match(RENDER, /if \(sig === chatTabsSig\) return;/, "posted only when the set changed");
});
