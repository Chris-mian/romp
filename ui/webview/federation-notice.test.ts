// NOTICE CARDS over federation (T370, plans/notice-cards.md): a notice ask from another host rides the asks array the
// merge already carries; its sid, name AND item id take the host prefix (the id since round three of PR 1831: the reserved
// owner-less key sits in the sid slot on every host, so two hosts' cards under one key minted one id), the route strips
// the id on the way out, and a viewer's foreign clear never names the family (the kernel's _cleared_foreign skips it), so a
// dismissal is a routed gesture into the owning kernel's ledger.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { mergeHostFeeds, prefixInbound, routeOutbound } from "./federation";

const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");

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
  assert.equal(a.itemId, `notice:${SID}:figure:2`, "the MERGE touches no id: this fixture arrives already prefixed at the sid; the item id's host prefix is prefixInbound's (the test below), applied at the socket before the merge");
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
  // one helper strips a remote host's prefix the way federation adds it (round two of PR 1831), read by the rank, the chip and the header
  assert.match(FEED, /const isOwnerless = \(sid: string \| null \| undefined\): boolean => !!sid && bareId\(sid\) === NOTICE_OWNERLESS_SID;/, "the owner test, host-prefix aware");
  assert.match(FEED, /const ownerRank = \(sid: string\): number => isOwnerless\(sid\) \? 0 : 1;/, "the owner rule as a rank, not a timestamp");
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => ownerRank\(entrySid\(x\)\) - ownerRank\(entrySid\(y\)\)\);/, "applied after the time sort in every mode, stable, on the shared entrySid");
  assert.doesNotMatch(FEED, /const entryOwner = /, "no second copy of entrySid");
  assert.match(FEED, /return isOwnerless\(s\) \? -1 : rank\.has\(s\)/, "and before the session order in grouped mode");
  assert.match(FEED, /const ownerless = isOwnerless\(it\.sid\);\s*\n\s*a\._name\.style\.display = ownerless \? "none" : "";/, "no session chip on the card");
  assert.match(FEED, /if \(isOwnerless\(e\.sid\) !== \(nm\.tagName === "SPAN"\)\) \{/, "the header's name node is a span for the owner-less run");
  assert.match(FEED, /nm\.classList\.remove\("dead"\); nm\.removeAttribute\("title"\); nm\.onclick = null;/, "plain text: no title, no dead class, no click");
  assert.match(KERNEL, /"board": "feed", "category": column,/, "the board model's two fields on every notice card (agreed with the board design's author)");
});

test("a remote notice card's item id is host-prefixed on the way in, stripped on the way out, and compared bare against the viewer's cleared ids", () => {
  // round three of PR 1831: two hosts' owner-less cards under one key minted one id (the reserved word sits in the sid slot on
  // every host) and the merged board kept one element; the prefix rides the id like the sid, the route strips it, the overlay
  // compares the bare form; a goal card's id ("sid:gN") is never prefixed (T287)
  assert.match(FED, /if \(typeof out\.itemId === "string" && out\.itemId\.startsWith\("notice:"\)\) out\.itemId = prefixId\(host, out\.itemId\);/, "the inbound prefix, notice ids alone");
  assert.match(FED, /if \(typeof out\.itemId === "string" && bareId\(out\.itemId\)\.startsWith\("notice:"\)\) out\.itemId = stripHost\(host, out\.itemId\);/, "the outbound strip on the scalar route");
  assert.match(FED, /foreign\.has\(id\) \|\| \(bareId\(id\)\.startsWith\("notice:"\) && foreign\.has\(bareId\(id\)\)\)/, "the overlay compares the bare notice id");
  const a = { itemId: "notice:notes:k:1", sid: "notes", name: "Notes", column: "completed", t: 1 };
  const g = { itemId: "11111111-2222-3333-4444-555555555555:g1", sid: "11111111-2222-3333-4444-555555555555", name: "web", column: "working", t: 2 };
  const inb = prefixInbound("TESTHOST", { type: "feed", asks: [a, g], now: 1 });
  assert.equal(inb.asks[0].itemId, "TESTHOST:notice:notes:k:1", "a notice id wears the host");
  assert.equal(inb.asks[0].sid, "TESTHOST:notes");
  assert.equal(inb.asks[1].itemId, "11111111-2222-3333-4444-555555555555:g1", "a goal id stays bare");
  const r = routeOutbound({ type: "noticeAction", itemId: inb.asks[0].itemId, sid: inb.asks[0].sid, route: "/send", body: {} }, new Set(["TESTHOST"]));
  assert.deepEqual(r.map((x: any) => [x.host, x.msg.itemId, x.msg.sid]), [["TESTHOST", "notice:notes:k:1", "notes"]], "the action reaches the owning kernel with bare ids");
  const c = routeOutbound({ type: "askClear", itemId: inb.asks[0].itemId, sid: inb.asks[0].sid }, new Set(["TESTHOST"]));
  assert.deepEqual(c.map((x: any) => [x.host, x.msg.itemId]), [["TESTHOST", "notice:notes:k:1"]], "a clear too");
});
