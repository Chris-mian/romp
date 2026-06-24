// Fleet — the by-SESSION open-work view (the user 2026-06-23). It reuses the feed WS payload (m.asks),
// groups goals by session, and hides completed work behind a "Show completed" checkbox (default OFF). The
// view has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");

test("fleet consumes the feed payload's `asks`, grouped by session", () => {
  assert.match(SRC, /m\.type !== "feed"/);                 // same stream the feed uses
  assert.match(SRC, /goals = Array\.isArray\(m\.asks\)/);  // the goal cards are the source
  assert.match(SRC, /function bySession\(\)/);             // grouped by sid, not by status column
  assert.match(SRC, /groups\.set\(g\.sid/);
});

test("completed work is hidden by default, behind a 'Show completed' checkbox", () => {
  // default OFF: localStorage must be exactly "1" to show completed (a missing key → off)
  assert.match(SRC, /localStorage\.getItem\(DONE_KEY\) === "1"/);
  assert.match(SRC, /const isOpen = \(g: Goal\) => g\.column !== "completed"/);
  // render filters out completed unless showDone(), and drops a session with nothing left to show
  assert.match(SRC, /\.filter\(\(g\) => sd \|\| isOpen\(g\)\)/);
  assert.match(SRC, /createTextNode\("Show completed"\)/);
  assert.match(SRC, /setShowDone\(cb\.checked\); render\(\)/);
});

test("a session row opens that session (the navigation loop back to its chat)", () => {
  assert.match(SRC, /vscodeApi\?\.postMessage\(\{ type: "openSession", id: s\.sid \}\)/);
});

test("status dots distinguish working / needs-you / awaiting / done", () => {
  assert.match(SRC, /classList\.add\("done"\)/);
  assert.match(SRC, /classList\.add\("block"\)/);
  assert.match(SRC, /classList\.add\("work"\)/);
});

test("it's a MODULE (own scope) so it doesn't collide with feed.ts's globals", () => {
  assert.match(SRC, /export \{\};/);
});
