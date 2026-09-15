// The partition's pure rules, EXECUTED (the chat split, the user 2026-09-11): which column a page is from its
// own search string, and whether a column holds a session under the shell's sets. render.ts's tabInView is the
// one caller; tab-strip-skip.test.ts pins that call at the source. And the emptiness verdict a later column reaches from
// one strip (columnEmptiness), whose host rule keeps a column from folding on a member whose host has not reported yet
// (the user 2026-09-14; render.ts noteColumnEmptiness is the caller, chat-split-exec.test.ts runs that caller). Synthetic ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { colFromSearch, columnHolds, columnEmptiness, ownerOf, type ColSets } from "./chat-columns";

const WEB = "11111111-2222-3333-4444-555555555501";
const API = "11111111-2222-3333-4444-555555555502";
const TESTS = "11111111-2222-3333-4444-555555555503";
const REMOTE = "TESTHOST:11111111-2222-3333-4444-555555555504";   // a remote host's session rides its host prefix, as `order` carries it

test("colFromSearch: the shim's rule — the first column is the empty string, ?col=1 folds to it, a later column is its number", () => {
  assert.equal(colFromSearch(""), "", "no search: the first column (a standalone page, the VS Code webview)");
  assert.equal(colFromSearch("?col=1"), "", "?col=1 IS the first column: its state blob keeps the unsuffixed key");
  assert.equal(colFromSearch("?col=2"), "2");
  assert.equal(colFromSearch("?col=3&skeleton=1"), "3", "the skeleton flag rides beside it");
  assert.equal(colFromSearch("?skeleton=1"), "", "no col: the first column");
  assert.equal(colFromSearch("garbage"), "", "an unparseable search is the first column, never a throw");
});

test("columnHolds with null sets: no partition, everything is held, whatever the column", () => {
  for (const col of ["", "2", "9"]) for (const id of [WEB, API, REMOTE]) assert.equal(columnHolds(null, col, id), true, col + " holds " + id);
});

test("columnHolds: a later column holds the ids its entry lists, and only those", () => {
  const sets: ColSets = { "2": [API], "3": [TESTS, REMOTE] };
  assert.equal(columnHolds(sets, "2", API), true);
  assert.equal(columnHolds(sets, "2", TESTS), false, "listed by another column");
  assert.equal(columnHolds(sets, "2", WEB), false, "listed by no column: the first column's");
  assert.equal(columnHolds(sets, "3", TESTS), true);
  assert.equal(columnHolds(sets, "3", REMOTE), true, "a host-prefixed id is matched as a whole string");
  assert.equal(columnHolds(sets, "4", API), false, "a column with no entry holds nothing (a stale page whose entry closed)");
});

test("columnHolds: the first column derives — every id no entry lists, and none an entry does", () => {
  const sets: ColSets = { "2": [API], "3": [TESTS] };
  assert.equal(columnHolds(sets, "", WEB), true, "unlisted: the first column's");
  assert.equal(columnHolds(sets, "", REMOTE), true, "a remote host's session that arrived with no gesture lands in the first column");
  assert.equal(columnHolds(sets, "", API), false);
  assert.equal(columnHolds(sets, "", TESTS), false);
  assert.equal(columnHolds({}, "", WEB), true, "no later columns: the first column holds everything");
  assert.equal(columnHolds({}, "2", WEB), false);
});

test("a doubly listed id belongs to ONE column, the first key holding it, never to both", () => {
  // the shell's writes never produce a double and its sets() resolves one by row order; a store another
  // dashboard wrote before this shell reconciled it can still carry one, and two columns must not both show it
  const sets: ColSets = { "2": [API], "3": [API, TESTS] };
  assert.equal(ownerOf(sets, API), "2");
  assert.equal(columnHolds(sets, "2", API), true);
  assert.equal(columnHolds(sets, "3", API), false);
  assert.equal(columnHolds(sets, "", API), false, "…and the first column does not derive it either");
  assert.equal([2, 3, ""].filter((c) => columnHolds(sets, String(c), API)).length, 1, "exactly one holder");
});

test("ownerOf: the empty string for an id no entry lists, and a junk entry is skipped, never a throw", () => {
  assert.equal(ownerOf({ "2": [API] }, WEB), "");
  assert.equal(ownerOf({ "2": null as unknown as string[], "3": [WEB] }, WEB), "3", "a corrupt entry is passed over");
});

// ── the emptiness verdict (render.ts noteColumnEmptiness; the host rule, the user 2026-09-14) ──
const S = (...xs: string[]) => new Set(xs);
const LOCAL_SEEN = S("");                       // the local kernel's own strip has landed, no remote host's yet
const REMOTE2 = "TESTHOST:11111111-2222-3333-4444-555555555505";
const FAR = "OTHERHOST:11111111-2222-3333-4444-555555555506";

test("columnEmptiness over bare ids: today's rule unchanged — listed or live-and-not-crossed is held, otherwise empty once the local strip has landed", () => {
  assert.equal(columnEmptiness([API, TESTS], [WEB, API, TESTS], S(), S(), LOCAL_SEEN), "held", "a member listed");
  assert.equal(columnEmptiness([API, TESTS], [WEB, TESTS], S(), S(), LOCAL_SEEN), "held", "one member still listed");
  assert.equal(columnEmptiness([API, TESTS], [WEB], S(), S(), LOCAL_SEEN), "empty", "none listed, none live");
  assert.equal(columnEmptiness([API], [WEB], S(API), S(), LOCAL_SEEN), "held", "omitted but live-affirmed: a transient read failure (T258)");
  assert.equal(columnEmptiness([API], [WEB], S(API), S(API), LOCAL_SEEN), "empty", "…unless this page's own cross removed it");
  assert.equal(columnEmptiness([], [WEB], S(), S(), LOCAL_SEEN), "held", "nothing to judge: a column with no entry never empties");
  assert.equal(columnEmptiness([API], [], S(), S(), LOCAL_SEEN), "empty", "an empty strip with the local host reported: gone");
});

test("columnEmptiness under a host prefix: a member is absent only once ITS host has reported; before that the verdict is unknown, never empty", () => {
  // the user's drop (2026-09-14): the new column's first strip is the local kernel's, the member rides a remote host's prefix
  assert.equal(columnEmptiness([REMOTE], [WEB, API], S(), S(), LOCAL_SEEN), "unknown", "its host has not reported: not knowable, not gone");
  assert.equal(columnEmptiness([REMOTE], [], S(), S(), LOCAL_SEEN), "unknown", "…even over an empty strip");
  assert.equal(columnEmptiness([REMOTE], [WEB, API], S(), S(), S()), "unknown", "no host at all reported yet");
  assert.equal(columnEmptiness([REMOTE], [WEB, REMOTE], S(), S(), S("", "TESTHOST")), "held", "its host reported and lists it");
  assert.equal(columnEmptiness([REMOTE], [WEB, REMOTE], S(), S(), LOCAL_SEEN), "held", "a listed member is present whatever the hosts set says");
  assert.equal(columnEmptiness([REMOTE], [WEB], S(REMOTE), S(), S("", "TESTHOST")), "held", "omitted but live-affirmed by its host");
  assert.equal(columnEmptiness([REMOTE], [WEB], S(), S(), S("", "TESTHOST")), "empty", "its host reported and does not list it: gone");
  assert.equal(columnEmptiness([REMOTE], [WEB], S(), S(), S("TESTHOST")), "empty", "the member's own host is what counts, not the local one");
  // the remote-host page (the earlier probe): the only strip so far is another host's, the member is local
  assert.equal(columnEmptiness([API], [REMOTE, REMOTE2], S(), S(), S("TESTHOST")), "unknown", "the local kernel has not reported on this socket");
  assert.equal(columnEmptiness([API], [REMOTE, REMOTE2], S(), S(), S("TESTHOST", "")), "empty");
  // mixed members: empty only when EVERY member's host has reported and none is present
  assert.equal(columnEmptiness([API, FAR], [WEB], S(), S(), LOCAL_SEEN), "unknown", "the local member is gone, the far host silent");
  assert.equal(columnEmptiness([API, FAR], [WEB], S(), S(), S("", "OTHERHOST")), "empty");
  assert.equal(columnEmptiness([API, FAR], [WEB, FAR], S(), S(), LOCAL_SEEN), "held", "a present member holds the column whatever the other's host");
  assert.equal(columnEmptiness([REMOTE, FAR], [WEB], S(), S(), S("", "TESTHOST")), "unknown", "one remote host reported, the other not");
});
