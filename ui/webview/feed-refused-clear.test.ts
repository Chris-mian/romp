// A clear the clears log refused leaves the board as it was (the second review of PR 1967, 2026-09-21).
//
// The bug: `clr.onclick` adds the card's id to pendingCleared, released only when a payload OMITS the card; after
// `_clear_all` returns the ledger's fault every payload still lists it and the refusal frame named no request, so the
// card stayed hidden under a dialog saying every card is as it was. The kernel's frame now names the request (`op`, the
// batch's `itemIds`) and the feed's `err` handler releases those ids and repaints. Source-level pins (no jsdom for the
// feed renderer), mirroring feed-move-ack.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("client: the err handler releases the ids a refused clear names and repaints, before the latch re-arms", () => {
  const i = FEED.indexOf('} else if (m.type === "err" && typeof m.text === "string" && m.text) {');
  assert.ok(i >= 0);
  const h = FEED.slice(i, FEED.indexOf('} else if (m.type === "pickerOptions"', i));
  assert.match(h, /const refusedIds = Array\.isArray\(m\.itemIds\) \? m\.itemIds\.map\(String\) : \(op === "askClear" && itemId \? \[itemId\] : \[\]\);/);
  assert.match(h, /if \(\(op === "askClear" \|\| op === "askClearMany" \|\| op === "nodeOverride"\) && refusedIds\.length\) \{/, "the three clear requests");
  assert.match(h, /for \(const id of refusedIds\) pendingCleared\.delete\(id\);/, "the click's suppression lets go");
  assert.match(h, /clearedStack\.splice\(i, 1\);/, "and the optimistic Undo entry for a clear that never happened goes");
  assert.ok(h.indexOf("render();") > h.indexOf("pendingCleared.delete(id)"), "then the board repaints from the payload that still lists the card");
  assert.ok(h.indexOf("refusedIds") < h.indexOf('if (op === "apiRetry" && sid)'), "ahead of the latch re-arms the frame already drove");
});

test("kernel: the clears-log refusal names the request the way _refuse_drive's frame does", () => {
  assert.match(KERNEL, /"type": "err", "sid": "", "title": title, "text": text, "op": op or "",\s+"itemId": _ids\[0\] if _ids else "", "itemIds": _ids\}/);
  assert.ok(KERNEL.includes('_gesture_store_refusal(client, "undo", _undo_clear(), op=str(msg.get("type") or ""))'), "an undo names its op (the request's type) and no ids");
});
