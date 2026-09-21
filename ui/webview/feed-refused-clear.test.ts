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
  assert.match(h, /for \(const id of refusedIds\) for \(const c of cardTwins\(id\)\) c\.classList\.remove\("dismissing"\);/, "the collapse class off by id (round ten: stack or no stack)");
  assert.match(h, /for \(const id of refusedIds\) \{ const it = clearedItems\.get\(id\); if \(it && !asks\.some\(\(a\) => a\.itemId === id\)\) asks\.push\(it\); \}/, "and the cards back from the page's record of what it cleared");
  // a refused undo reverts the optimistic restore (the verifier's medium A): the batch leaves asks and pendingRestored, is suppressed again and goes back on the stack
  assert.match(h, /\} else if \(op === "undoClear" && refusedIds\.length\) \{/);
  assert.match(h, /for \(const id of refusedIds\) \{ pendingRestored\.delete\(id\); pendingCleared\.add\(id\); \}/);
  assert.match(h, /if \(back\.length\) clearedStack\.push\(back\);/);
  assert.match(h, /if \(Array\.isArray\(m\.owedIds\) && m\.owedIds\.length\) clearedStack\.push\(\[\]\);/, "an entry standing for the owed ids above the last clear's (the sixth executed review): the next pop matches the kernel's");
  assert.match(h, /for \(const id of refusedIds\) pendingCleared\.delete\(id\);/, "the click's suppression lets go");
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
  assert.match(KERNEL, /skipped\[LEDGER_REORDER_KEY\] = \{"fault": "", "ids": popped, "landed": bool\(landed\), "owed": \[\] if landed else list\(not_back\), "stamps": int\(stamps\)\}/, "filed by _reorder after the flag step, worded for what happened (the fourth review)");
  assert.match(KERNEL, /_reorder\(not _not_back, _not_back, len\(\{_cur2\.get\(i\) for i in _not_back\}\) or 1\)/, "the owed cards came back only if every one did; the frame names the ones that did not and how many batches they sit in");
  assert.match(KERNEL, /_send\("Undo brought back earlier cards first",[\s\S]{0,400}ok=True\)/);
  assert.match(KERNEL, /_send\("Undo went to earlier cards first",[\s\S]{0,600}ok=True, owed=value\.get\("owed"\)/, "the words for an owed store still refusing, naming the owed ids");
  assert.match(KERNEL, /Once that session's store can be read, one Undo brings them back and the next the last clear\./, "the words name the press (the sixth executed review)");
  assert.match(KERNEL, /"owed": \[\] if landed else list\(not_back\), "stamps": int\(stamps\)/, "the ids that did NOT come back, and how many batches they sit in (the seventh executed review)");
  assert.match(KERNEL, /Once their stores can be read they take more than one Undo, since they were left at different points, and the last clear comes back after them\./, "no press count when they hold more than one stamp");
  // round eight: the kernel's stack rides every account and the page takes it as its own; a batch this page makes goes under the owed entries
  assert.match(KERNEL, /frame\["batches"\], frame\["owedBatch"\], frame\["batchesTotal"\] = _lb\[0\]/, "every account carries the kernel's stack and the count before the bound");
  assert.match(FEED, /if \(storeOp && Array\.isArray\(m\.batches\) && !fromHost && !federatedPane\(\)\) \{/, "the local kernel's frame reconciles on a single-kernel pane; an old kernel's frame, and every frame on a federated pane, take the branches below (the round-nine verifier's ruling)");
  assert.match(FEED, /function federatedPane\(\): boolean \{/);
  assert.match(FEED, /if \(federatedPane\(\)\) clearedStack\.length = 0;\s*\/\/[^\n]*\n\s+const batch = clearedStack\.pop\(\);/, "and pops none: the round trip");
  assert.match(FEED, /clearedStack\.push\(\.\.\.older\);/, "the older local entries stay below the rebuilt ones under a truncated frame");
  assert.match(KERNEL, /^LEDGER_BATCHES_ON_WIRE = 20/m, "the stack on the wire is bounded (plans\/needs-you.md)");
  assert.match(KERNEL, /def _ledger_batches\(limit=LEDGER_BATCHES_ON_WIRE\):/);
  assert.match(KERNEL, /return \(\[owed\] if owed else \[\]\) \+ out\[:limit\], owed, len\(out\)/, "the newest batches within the bound, the owed ids, the count");
  assert.match(FEED, /const truncated = typeof m\.batchesTotal === "number" && m\.batchesTotal > bats\.length - \(owedB\.length \? 1 : 0\);/, "a frame that left older batches out says so (round ten)");
  assert.match(FEED, /reconcileClearedStack\(bats, owedB, truncated, refusedIds\);/);
  assert.match(FEED, /if \(truncated && !named\.has\(id\) && !cleared\.has\(id\)\) continue;/, "a suppression the truncated frame neither names nor carries stays");
  assert.match(FEED, /function pushClearedEntry\(entry: AskItem\[\]\): void \{\n  for \(const it of entry\) clearedItems\.set\(it\.itemId, it\);\n  if \(federatedPane\(\)\) return;[^\n]*\n  let i = clearedStack\.length;\n  const owedIds = new Set<string>\(\);\n  while \(i > 0 && \(clearedStack\[i - 1\] as any\)\._owed\) \{/, "every cleared card is recorded; a federated pane caches no entry; a batch this page makes goes under the owed entries, and an id they hold counts once");
  assert.match(FEED, /const rest = entry\.filter\(\(it\) => !owedIds\.has\(it\.itemId\)\);\n  if \(rest\.length\) clearedStack\.splice\(i, 0, rest\);/);
  assert.match(FEED, /function reconcileClearedStack\(batches: string\[\]\[\], owedBatch: string\[\], truncated = false, namedIds: string\[\] = \[\]\): void \{/);
  assert.equal((FEED.match(/pushClearedEntry\(/g) || []).length, 5, "the four writers (a card's Clear, a group's, a session's Clear all, the board's Clear all) and the definition");
  assert.match(KERNEL, /frame\["owedIds"\] = \[str\(i\) for i in owed\]/);
  assert.doesNotMatch(KERNEL, /The owed cards came back, but romp could not clear the note/, "the owed-write account, filed before the flag step, claims nothing about the restore");
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
