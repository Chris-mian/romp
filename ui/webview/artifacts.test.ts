// The Artifacts pane's pure parts (plans/artifacts-pane.md): the grid's rule, the cycle's order, the rule words, the row
// click's route, the age words; and source pins on the pieces outside the kernel (the setting, the gear's row, the
// bundle entries). The kernel's walk, listing, op, route and shell hooks are pinned in tests/test_artifacts_list.py; the
// behaviour rides tests/test_artifacts_pane_served.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { gridItems, cycleEntries, viaWord, rowRoute, ago, type ArtifactItem } from "./artifacts-model";

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

test("the pieces outside the kernel: the fresh setting read like the Files control's, the gear's Panes row, the bundle entries", () => {
  const SETTINGS = fs.readFileSync(path.join(UI, "settings.ts"), "utf8");
  const KERNEL = fs.readFileSync(path.join(UI, "..", "..", "kernel", "kernel.py"), "utf8");
  const BUILD = fs.readFileSync(path.resolve(process.cwd(), "esbuild.js"), "utf8");
  const GEAR = fs.readFileSync(path.join(UI, "gear.js"), "utf8");
  // the pane is an EXPERIMENTAL record in the kernel's _CODE_PANES (plans/panes-as-data.md, phase three): the gear's generic Panes row
  // (gear.js renderRegistryRows, off by default for an experimental pane) is its control; the bespoke showArtifactsControl key is gone
  assert.match(KERNEL, /\{"id": "artifacts", "title": "Artifacts", "source": "\/artifacts", "on": False, "experimental": True\}/, "the record: off by default, asked for in the gear");
  assert.doesNotMatch(SETTINGS, /showArtifactsControl: boolean|showArtifactsControl: false|s\.showArtifactsControl =/, "no bespoke setting key: no field, no default, no normalization (only the retired key's drop at load, pinned below)");
  assert.doesNotMatch(GEAR, /rs-artctl|showArtifactsControl/, "no bespoke gear row");
  assert.match(GEAR, /var BUILTIN_HINTS = \{ artifacts: 'A session\\'s written, shown and dropped files as a list and a grid of large thumbnails\.' \};/, "the shipped record's row says what the pane shows (its first landing's words)");
  assert.match(GEAR, /\(p\.builtin \? \(\(BUILTIN_HINTS\[p\.id\] \|\| ''\) && BUILTIN_HINTS\[p\.id\] \+ ' '\) : 'A pane defined at the kernel \(romp pane\)\. '\)/, "a data pane's row says it is defined at the kernel");
  assert.match(GEAR, /'Off' \+ \(p\.experimental \? ' \(the default for an experimental pane\)' : ''\)/, "the experimental default is said only where it applies");
  assert.match(SETTINGS, /delete \(s as Record<string, unknown>\)\.showArtifactsControl;/, "the retired key is dropped at load, like the repo's other retired keys");
  assert.match(BUILD, /"\.\.\/ui\/webview\/artifacts\.ts",/); assert.match(BUILD, /"\.\.\/ui\/webview\/artifacts-pane\.css",/);
  const ART = fs.readFileSync(path.join(UI, "artifacts.ts"), "utf8");
  assert.match(ART, /ask\(\{ type: "listArtifacts", sid: selected, reqId: lastReq \}\);/, "one request, by id");
  assert.match(ART, /if \(m\.reqId !== lastReq \|\| m\.sid !== selected\) return;/, "a slow answer for an earlier selection is dropped, never rendered");
  assert.match(ART, /window\.parent\.postMessage\(\{ romp: "viewFile", path: p, sid: selected, pane: "pane", frag: null \}, "\*"\);/, "the shell's existing relay sends a picture to the Files pane");
  assert.match(ART, /img\.src = fileUrl\(it\.path, selected\);/, "thumbnails through the token-authed file route with the session's sid");
  assert.doesNotMatch(ART, /new WebSocket|fetch\(/, "no file server of its own, no fetch: the route and the socket the shim gives it");
  // round two (2026-09-19): the cap says the newest of more, once; a kind the viewer does not show is listed plain and a click says so
  assert.match(ART, /count\.textContent = listing\.capped \? "the newest " \+ listing\.max \+ " files of more" : listing\.items\.length \+ \(listing\.items\.length === 1 \? " file" : " files"\);/);
  assert.match(ART, /if \(it\.kind === "other"\) \{ note\("The viewer cannot show " \+ it\.name \+ ": not a kind it renders\."\); return; \}/);
});
