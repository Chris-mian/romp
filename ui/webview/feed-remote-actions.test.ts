// Feed card actions must carry the card's sid so the federation manager can route them to the OWNING
// kernel (the user 2026-07-02: clearing a remote session's card silently no-op'd on the local kernel and
// the card resurrected on every reload). Source-pin over feed.ts, like picker-host.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("every askClear send carries the card's sid (routes a remote clear to its kernel)", () => {
  const sends = FEED.match(/type: "askClear"[^}]*/g) || [];
  assert.ok(sends.length >= 6, `found ${sends.length} askClear sends — expected the 6 known sites`);
  for (const s of sends) assert.match(s, /sid: (it|m|mem|fitem)\.sid/, `askClear send missing sid: ${s}`);
});

test("expand and askFollowUp carry sid too (remote summaries + follow-ups)", () => {
  const expands = FEED.match(/type: "expand"[^}]*/g) || [];
  assert.ok(expands.length >= 2);
  for (const s of expands) assert.match(s, /sid: (it\?|fitem)\.sid/, `expand send missing sid: ${s}`);
  assert.match(FEED, /type: "askFollowUp"[^}]*sid: fbSid/);
  // both modal call sites hand postFollowUp the card's sid
  assert.match(FEED, /postFollowUp\(txt, grp\.members\[0\]\.itemId, grp\.members\[0\]\.sid, grp\.title\)/);
  assert.match(FEED, /postFollowUp\(txt, it\.itemId, it\.sid\)/);
});
