// Renaming a REMOTE session's tab (the user 2026-08-02). A federated session displays as "host:name",
// where "host:" is metadata this viewer prepends (see host-prefix.ts) — the kernel that owns the session
// knows it by the bare name. The editor used to open on the whole display string, so the host went into
// the field, came back out on the other side of the rename, and the write was refused: a colon is not a
// legal session name. The host is fixed chrome now and only the name is editable.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { hostPrefix } from "./host-prefix";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const rename = RENDER.slice(RENDER.indexOf("function startTabRename"),
                            RENDER.indexOf("// Keyboard nav on a focused tab"));

test("the editor opens on the session name alone, with the host beside it", () => {
  assert.match(rename, /const p = hostPrefix\(s\.name, id\);/);
  assert.match(rename, /const base = p \? p\.rest : s\.name;/);
  assert.match(rename, /input\.value = base;/, "the field holds the part that is theirs to change");
  assert.match(rename, /el\("span", "host-prefix"\)/, "…and the host reads exactly as the label renders it");
  assert.match(rename, /input\.before\(fixed\)/, "sitting before the field, not inside it");
});

test("the host is never part of what is submitted", () => {
  assert.match(rename, /name: v \}\)/);
  assert.doesNotMatch(rename, /name: s\.name/);
  assert.match(rename, /v !== base/, "unchanged is measured against the name, not the display string");
});

test("the fixed prefix is torn down with the editor", () => {
  assert.match(rename, /fixed\?\.remove\(\)/, "else it outlives the rename and doubles the host on the tab");
});

test("a local session's rename is untouched", () => {
  // hostPrefix returns null off a bare (local) sid, so base === s.name and no fixed span is built —
  // the local path is exactly what it was.
  assert.equal(hostPrefix("api", "11111111-2222-3333-4444-555555555555"), null);
});

test("a remote name splits into the host and the name the far kernel knows", () => {
  const p = hostPrefix("TESTHOST:api", "TESTHOST:11111111-2222-3333-4444-555555555555");
  assert.deepEqual(p, { host: "TESTHOST:", rest: "api" });
});

test("a local name that merely contains a colon is not split", () => {
  // the sid is the marker, never the name: a bare uuid means every character of the name is the name
  assert.equal(hostPrefix("odd:name", "11111111-2222-3333-4444-555555555555"), null);
});
