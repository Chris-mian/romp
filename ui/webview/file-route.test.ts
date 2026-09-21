// The file link's ladder, executed (pure): where a file clicked in the chat opens. Three inputs since T404 (the user
// 2026-09-13): whether a shell frames this chat, whether the Files pane is OPEN, and whether the Files control exists at all.
// The setting that once let a click bring a CLOSED pane forward is gone: the behaviour follows the open pane. The one
// preference lost is a closed pane brought forward on every click, named in the pull request so the user can ask for it back.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { fileLinkRoute, browseRoute } from "./file-route";

test("fileLinkRoute: no shell (standalone /chat), everything opens in place", () => {
  for (const open of [true, false]) for (const avail of [true, false]) assert.equal(fileLinkRoute(false, open, avail), "here", `filesOpen=${open} avail=${avail}`);
});

test("fileLinkRoute: Files pane OPEN, the click goes there", () => {
  assert.equal(fileLinkRoute(true, true), "pane");
  assert.equal(fileLinkRoute(true, true, true), "pane");
});

test("fileLinkRoute: Files pane CLOSED, the file opens over the pane you clicked: no setting brings a closed pane forward (T404)", () => {
  assert.equal(fileLinkRoute(true, false), "here");
  assert.equal(fileLinkRoute(true, false, true), "here", "the control shown changes nothing while the pane is closed");
  assert.equal(fileLinkRoute(true, false, false), "here");
});

test("fileLinkRoute: the Files control hidden, an open pane cannot be (the shell closes it): over the pane clicked", () => {
  assert.equal(fileLinkRoute(true, true, false), "here", "no control, no pane to open there");
  assert.equal(browseRoute(true, true, false, false), "here", "a folder walks the same ladder");
  assert.equal(browseRoute(false, true, false, false), "editor", "VS Code keeps the editor's opener");
});

test("fileLinkRoute takes no setting: three parameters, the third defaulting to a shown control", () => {
  assert.equal(fileLinkRoute.length, 2, "framed and filesOpen are required; filesAvail defaults");
  assert.equal(fileLinkRoute(true, true), fileLinkRoute(true, true, true));
});

test("fileLinkRoute names only the two targets this chat can open", () => {
  const seen = new Set<string>();
  for (const framed of [true, false]) for (const open of [true, false]) for (const avail of [true, false]) seen.add(fileLinkRoute(framed, open, avail));
  assert.deepEqual([...seen].sort(), ["here", "pane"]);
});
