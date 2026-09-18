// NOTICE CARDS over federation (T370, plans/notice-cards.md): a notice ask from another host rides the asks array the
// merge already carries; its sid and name take the host prefix like every card's, its item id stays as the owner minted it
// (notice:<sid>:<key>:<rev>, a namespaced family), and a viewer's foreign clear never names the family (the kernel's
// _cleared_foreign skips it), so a dismissal is a routed gesture into the owning kernel's ledger.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { mergeHostFeeds } from "./federation";

const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

const SID = "11111111-2222-3333-4444-555555555555";
const notice = (sid: string, rev: number) => ({
  itemId: `notice:${sid}:figure:${rev}`, sid, name: "web", color: { bg: "#1EA1EB", fg: "#ffffff" }, text: "A new figure", t: 1757000000,
  live: false, trgb: [1, 2, 3], turnId: `notice:${sid}:figure:${rev}`, column: "completed", tree: [],
  notice: { producer: "figure", key: "figure", rev, body: "the body", attachment: null, actions: [{ label: "Send again", route: "/send", body: { text: "x" } }], expiresAt: null, dismissOnAction: false },
});

test("a remote host's notice card merges with its prefixed sid and name kept and its item id untouched; a foreign clear naming a goal leaves it", () => {
  // inbound frames are host-prefixed field by field at receive time (sid, name); the merge concatenates them
  const A = "HOSTA:" + SID;
  const remote = { type: "feed", asks: [{ ...notice(SID, 2), sid: A, name: "HOSTA:web" }], sessions: [{ sid: A, name: "HOSTA:web" }], working: [], awaiting: [], ledgers: [] };
  const local = { type: "feed", asks: [], sessions: [], working: [], awaiting: [], ledgers: [], clearedForeign: [SID + ":g1"] };
  const merged: any = mergeHostFeeds({ "": local, HOSTA: remote }, ["", "HOSTA"]);
  const a = merged.asks.find((x: any) => x.notice);
  assert.ok(a, "the notice ask rides the merged asks");
  assert.equal(a.sid, A, "the sid wears the host prefix (gestures route by it)");
  assert.equal(a.name, "HOSTA:web", "the name too (the chip shows the host)");
  assert.equal(a.itemId, `notice:${SID}:figure:2`, "the item id is the owner's, never prefixed");
  assert.deepEqual(a.notice, remote.asks[0].notice, "the flavour object passes through untouched");
  assert.equal(merged.asks.length, 1, "a foreign clear of a goal id touches no notice");
});

test("the dismissal of a notice card is a routed gesture: the feed posts askClear with the card's sid", () => {
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "askClear", itemId: it\.itemId, sid: it\.sid \}\);/);
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "noticeAction", itemId: it\.itemId, sid: it\.sid, route: act\.route, body: act\.body \}\);/, "an action carries the sid too");
});

test("the owner-less notice cards' owner key is one literal in the kernel and the pane, and the pane ranks it first by the feed board's rule", () => {
  // plans/notice-cards.md, "Owner-less cards and the terse command" (the user 2026-09-18): the reserved home is a word, so no
  // uuid sid can collide; the pane's sort rule reads the same key; the run's name is the kernel's
  assert.match(KERNEL, /^NOTICE_OWNERLESS_SID = "notes"/m, "the kernel's reserved key");
  assert.match(FEED, /const NOTICE_OWNERLESS_SID = "notes";/, "the pane's literal equals it");
  assert.match(KERNEL, /^NOTICE_OWNERLESS_NAME = "Notes"/m, "the run's name");
  assert.match(FEED, /const ownerRank = \(sid: string\): number => sid === NOTICE_OWNERLESS_SID \? 0 : 1;/, "the owner rule as a rank, not a timestamp");
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => ownerRank\(entryOwner\(x\)\) - ownerRank\(entryOwner\(y\)\)\);/, "applied after the time sort in every mode, stable");
  assert.match(FEED, /s === NOTICE_OWNERLESS_SID \? -1 : rank\.has\(s\)/, "and before the session order in grouped mode");
  assert.match(FEED, /const ownerless = it\.sid === NOTICE_OWNERLESS_SID;\s*\n\s*a\._name\.style\.display = ownerless \? "none" : "";/, "no session chip on the card");
  assert.match(KERNEL, /"board": "feed", "category": column,/, "the board model's two fields on every notice card (agreed with the board design's author)");
});
