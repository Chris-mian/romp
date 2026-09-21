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
  assert.match(h, /if \(\(op === "askClear" \|\| op === "askClearMany" \|\| op === "nodeOverride" \|\| op === "clearAll"\) && refusedIds\.length\) \{/, "the four clear requests");
  // the card returns in either window (the third review): the collapse class off, the cached item re-pushed, as Undo does
  assert.match(h, /for \(const c of cardTwins\(it\.itemId\)\) c\.classList\.remove\("dismissing"\);/);
  assert.match(h, /if \(!asks\.some\(\(a\) => a\.itemId === it\.itemId\)\) asks\.push\(it\);/);
  // a refused undo reverts the optimistic restore (the verifier's medium A): the batch leaves asks and pendingRestored, is suppressed again and goes back on the stack
  assert.match(h, /\} else if \(op === "undoClear" && refusedIds\.length\) \{/);
  assert.match(h, /for \(const id of refusedIds\) \{ pendingRestored\.delete\(id\); pendingCleared\.add\(id\); \}/);
  assert.match(h, /if \(back\.length\) clearedStack\.push\(back\);/);
  assert.match(h, /for \(const id of refusedIds\) pendingCleared\.delete\(id\);/, "the click's suppression lets go");
  assert.match(h, /for \(const it of clearedStack\.splice\(i, 1\)\[0\]\) \{/, "and the optimistic Undo entry for a clear that never happened goes, its items back on the board");
  assert.ok(h.indexOf("render();") > h.indexOf("pendingCleared.delete(id)"), "then the board repaints from the payload that still lists the card");
  assert.ok(h.indexOf("refusedIds") < h.indexOf('if (op === "apiRetry" && sid)'), "ahead of the latch re-arms the frame already drove");
  assert.match(h, /\} else if \(!op && sid\) rearmLatches\(\{ kind: "session", sid \}\);/, "an old kernel's reply naming a session and no request re-arms the session's latches; a store gesture's account (op rides) re-arms nothing (the fourth review of PR 1967, the manager's ruling: a latch is released only by the reply to the request that made it)");
  assert.doesNotMatch(FEED, /STORE_GESTURE_OPS/, "no request set widens the session re-arm");
  assert.match(h, /if \(m\.ok !== true\) window\.parent\?\.postMessage\(\{ romp: "notify", kind: "undelivered",/, "an information frame (the landed reorder) is a dialog and no bell entry (the round-four verifier)");
});

test("kernel: the clears-log refusal names the request the way _refuse_drive's frame does", () => {
  assert.match(KERNEL, /frame = \{"type": "err", "sid": sid_, "title": title, "text": text, "op": op or "",\s+"itemId": acct_ids\[0\] if acct_ids else "", "itemIds": list\(acct_ids\)\}/, "one frame shape for every account, each with its own ids");
  assert.match(KERNEL, /if ok:\s+frame\["ok"\] = True/, "and `ok` on an information frame alone (the round-four verifier)");
  assert.ok(KERNEL.includes('_gesture_store_refusal(client, "undo", _undo_clear(batch_out=_ub), ids=_ub, op=str(msg.get("type") or ""))'), "an undo names its op (the request's type) and the batch it reached for (the verifier's medium A)");
  // the double-fault window's other side (round four): the re-journal-first refusal fills the batch too, so the feed's revert has ids
  assert.match(KERNEL, /named = popped \+ \[i for i in owed_ids if i not in popped\][^\n]*\n\s+if batch_out is not None:\s+batch_out\.extend\(named\)\s+skipped\[LEDGER_REJOURNAL_AGAIN_KEY\] = \{"fault": _store_fault_copy\(e\), "ids": named\}\s+return skipped/);
  // the landed reorder tells the feed the popped batch was not restored this press (the third review's medium): an err frame, op undoClear, the popped ids
  assert.match(KERNEL, /skipped\[LEDGER_REORDER_KEY\] = \{"fault": "", "ids": popped, "landed": bool\(landed\)\}/, "filed by _reorder after the flag step, worded for what happened (the fourth review)");
  assert.match(KERNEL, /_reorder\(set\(owed_ids\) <= \(set\(restored \+ notices\) - set\(_rj\)\)\)/, "the owed cards came back only if every undo row landed and its flag step ran");
  assert.match(KERNEL, /_send\("Undo brought back earlier cards first",[\s\S]{0,400}ok=True\)/);
  assert.match(KERNEL, /_send\("Undo went to earlier cards first",[\s\S]{0,400}ok=True\)/, "the words for an owed store still refusing");
  // the owed note (lows 3 and 4 of the fourth review, the round-four verifier's medium): one lock across the section, the rewrite with what is still owed, none after an unreadable note
  assert.match(KERNEL, /_OWED_LOCK = threading\.RLock\(\)/);
  assert.match(KERNEL, /    with _OWED_LOCK:\n[\s\S]{0,900}_rerr = _owed_load\(\)/, "the read under the lock _undo_clear holds across the section");
  assert.match(KERNEL, /if not _rerr:\n[\s\S]{0,700}_werr = _owed_rewrite\(list\(_rejournal_owed\)\)/, "the rewrite with the ids still owed, skipped after an unreadable note");
  assert.doesNotMatch(KERNEL, /_owed_rewrite\(\[\]\)/, "never a literal empty list");
  assert.match(KERNEL, /popped = \[i for i in popped if i not in owed_ids\]/, "a re-journaled id in the newest batch is restored this press, not named as parked");
  // each account names only its own ids (the third review's high): a skipped session's frame carries its own out of the batch
  assert.match(KERNEL, /_ids = \[i for i in _batch if \(i\.startswith\("notice:%s:" % sid\) if notices else \(not i\.startswith\("notice:"\) and i\.rsplit\(":", 1\)\[0\] == sid\)\)\]/, "a skipped session's own ids out of the batch");
  // the dialogs attach their box (the verifier's medium B, pre-existing on main): the behaviour rides the feed lab; this pins both functions carry the append
  assert.equal((FEED.match(/overlay\.appendChild\(box\);/g) || []).length, 3, "the quarantine dialog's, and now showErrDialog's and showPickerDialog's");
});
