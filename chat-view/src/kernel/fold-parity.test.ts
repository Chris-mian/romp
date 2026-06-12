// Fold parity tests: the kernel's TS ask-fold (feed.ts) checked against the
// semantics spec'd in REQUESTS.md and pinned for the Python read side by
// tests/test_romp_read_side.py. Same record-file fixtures, same expected
// columns — if the two folds ever disagree, the Python suite is the spec.
//
// Cases mirror the Python suite's core invariants: DONE completes; an
// unanswered DECISION routes to needs_input; the user's next typed turn
// crosses a DECISION off (answered crossoff); ACTION survives typing; the
// leaf-path fold completes a delegated chain through restatements; an open
// leaf names its drop point; Clear hides; a post-clear question resurrects;
// a follow-up reopens a completed card.
import { test, beforeEach } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { computeFeedItems, computeAskItems, FeedItem } from "./feed";

const SID = "aaaaaaaa-1111-2222-3333-444444444444";
const PEER = "bbbbbbbb-1111-2222-3333-444444444444";
const T0 = 1781040000;                      // past REQUESTS_FLOOR

let STATE = "";
beforeEach(() => {
  STATE = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fold-test-"));
  process.env.XDG_STATE_HOME = STATE;       // state.ts resolves at call time
  const romp = path.join(STATE, "romp");
  fs.mkdirSync(path.join(romp, "names"), { recursive: true });
  fs.mkdirSync(path.join(romp, "requests"), { recursive: true });
  fs.mkdirSync(path.join(romp, "summaries"), { recursive: true });
  fs.writeFileSync(path.join(romp, "names", SID), "main_sess\t/tmp\t#1EA1EB\twhite\n");
  fs.writeFileSync(path.join(romp, "names", PEER), "peer_sess\t/tmp\t#54B204\tblack\n");
});

function writeRows(file: string, rows: any[]) {
  fs.writeFileSync(path.join(STATE, "romp", "requests", file),
    rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : ""));
}
function writeSummaries(sid: string, rows: any[]) {
  fs.writeFileSync(path.join(STATE, "romp", "summaries", `${sid}.jsonl`),
    rows.map((r) => JSON.stringify(r)).join("\n") + "\n");
}
function ask(id: string, t: number, text = "do the thing", sid = SID) {
  return { kind: "ask", id, t, text, sid, turn_id: `${sid}:${t}:abcd1234` };
}
function link(rid: string, requestIds: string[], relevance: string, t: number, sid = SID, extra: any = {}) {
  return { kind: "link", reply_id: rid, request_ids: requestIds, relevance, t, sid, ...extra };
}
// run the fold the way refreshFeed does: feed items first (builds
// lastReqBySid for the answered crossoff), then the ask fold
function fold() {
  const all = computeFeedItems(null);
  const didById = new Map<string, FeedItem>(all.map((i) => [i.itemId, i] as const));
  return computeAskItems(null, didById);
}
const colOf = (asks: ReturnType<typeof fold>, id: string) =>
  asks.find((a) => a.itemId === id)?.column;

test("DONE on the root completes; nothing filed leaves it in asks", () => {
  writeRows("nodes.jsonl", [ask("a1", T0), ask("a2", T0 + 10)]);
  writeRows("links.jsonl", [link("r1", ["a1"], "DONE", T0 + 100)]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "completed");
  assert.equal(colOf(asks, "a2"), "asks");
});

test("unanswered DECISION → needs_input; the user's next typed turn crosses it off", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("links.jsonl", [link("r1", ["a1"], "DECISION", T0 + 100)]);
  assert.equal(colOf(fold(), "a1"), "needs_input");
  // a later `request` line in the SAME session = the user typed → answered.
  // (id middle field carries the typed turn's process-start time.)
  writeSummaries(SID, [
    { kind: "request", id: `${SID}:${T0 + 200}:beef0001`, t: T0 + 200, text: "typed answer" },
  ]);
  assert.equal(colOf(fold(), "a1"), "asks", "answered DECISION reverts to in-flight");
});

test("ACTION survives the user typing; only a DONE correction closes it", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("links.jsonl", [link("r1", ["a1"], "ACTION", T0 + 100)]);
  writeSummaries(SID, [
    { kind: "request", id: `${SID}:${T0 + 200}:beef0002`, t: T0 + 200, text: "typed something else" },
  ]);
  assert.equal(colOf(fold(), "a1"), "needs_input", "typing does not cross an ACTION off");
  // "did it" = a DONE correction on the node (newest-wins)
  writeRows("corrections.jsonl", [{
    t: T0 + 300, by_sid: "feed-panel", kind: "link", decision_ref: "r1",
    should_have: { request_ids: ["a1"], relevance: "DONE" }, note: "did it",
  }]);
  assert.equal(colOf(fold(), "a1"), "completed");
});

test("leaf-path fold: delegated chain completes through an unstamped intermediate", () => {
  // ask a1 → handoff h1 (peer); only the LEAF (h1) ever gets a DONE.
  writeRows("nodes.jsonl", [
    ask("a1", T0),
    { kind: "internal", id: "h1", t: T0 + 50, text: "tune the colormap", sid: SID, to_sid: PEER },
    { kind: "parents", id: "h1", parent_ids: ["a1"] },
  ]);
  writeRows("links.jsonl", [link("r2", ["h1"], "DONE", T0 + 150, PEER)]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "completed", "every path ends done → done, no stamp on the root needed");
  const a = asks.find((x) => x.itemId === "a1")!;
  assert.equal(a.tree.find((n) => n.id === "h1")?.who, "peer_sess");
});

test("an open leaf names its drop point (the session that owes an ending)", () => {
  writeRows("nodes.jsonl", [
    ask("a1", T0),
    { kind: "internal", id: "h1", t: T0 + 50, text: "port the plugin", sid: SID, to_sid: PEER },
    { kind: "parents", id: "h1", parent_ids: ["a1"] },
  ]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "asks");
  const a = asks.find((x) => x.itemId === "a1")!;
  assert.equal(a.openPaths.length, 1);
  assert.equal(a.openPaths[0].name, "peer_sess", "the handoff recipient owes the ending");
});

test("clear hides; a post-clear question resurrects (reopened)", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("cleared.jsonl", [{ id: "a1", t: T0 + 100 }]);
  assert.equal(fold().find((a) => a.itemId === "a1"), undefined, "cleared card is gone");
  // a question ARRIVING after the clear must never be invisible
  writeRows("links.jsonl", [link("r1", ["a1"], "DECISION", T0 + 200)]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "needs_input");
  assert.equal(asks.find((a) => a.itemId === "a1")!.reopened, true);
  // …while a question the user saw BEFORE clearing stays dismissed
  writeRows("cleared.jsonl", [{ id: "a1", t: T0 + 100 }, { id: "a1", t: T0 + 300 }]);
  assert.equal(fold().find((a) => a.itemId === "a1"), undefined);
});

test("a follow-up reopens a completed card until the bookkeeper catches up", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("links.jsonl", [link("r1", ["a1"], "DONE", T0 + 100)]);
  assert.equal(colOf(fold(), "a1"), "completed");
  writeRows("followups.jsonl", [{ id: "a1", sid: SID, t: T0 + 200, text: "also make it blue" }]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "asks", "open follow-up holds the card in ASKS");
  // the bookkeeper mints the follow-up turn as a child → ordinary fold owns it again
  writeRows("nodes.jsonl", [
    ask("a1", T0),
    { kind: "internal", id: "fu1", t: T0 + 250, text: "also make it blue", sid: SID },
    { kind: "parents", id: "fu1", parent_ids: ["a1"] },
  ]);
  writeRows("links.jsonl", [link("r1", ["a1"], "DONE", T0 + 100), link("r2", ["fu1"], "DONE", T0 + 300)]);
  assert.equal(colOf(fold(), "a1"), "completed", "follow-up's DONE completes the card again");
});

test("a child ask renders inside its root, never as its own card", () => {
  writeRows("nodes.jsonl", [
    ask("a1", T0),
    ask("a2", T0 + 50, "follow-up filed as child"),
    { kind: "parents", id: "a2", parent_ids: ["a1"] },
  ]);
  const asks = fold();
  assert.equal(asks.find((a) => a.itemId === "a2"), undefined, "child ask has no top-level card");
  assert.ok(asks.find((a) => a.itemId === "a1")!.tree.some((n) => n.id === "a2"));
});

test("amend rewrites the ask text in place", () => {
  writeRows("nodes.jsonl", [
    ask("a1", T0, "make it green"),
    { kind: "amend", id: "a1", t: T0 + 60, text: "actually make it blue" },
  ]);
  assert.equal(fold().find((a) => a.itemId === "a1")!.text, "actually make it blue");
});

// ---- the 2026-06-11 fold layers: latching, answers, liveness/auto-filing ----

function statesWith(state: string, name = "main_sess"): Map<string, any> {
  return new Map([[name, { state, effort: "", model: "", ctx: "", since: String(T0), summary: "" }]]);
}
function foldWith(states: Map<string, any> | null) {
  const all = computeFeedItems(states as any);
  const didById = new Map<string, FeedItem>(all.map((i) => [i.itemId, i] as const));
  return computeAskItems(states as any, didById);
}
function writeEventsCache(sid: string, events: any[]) {
  const dir = path.join(STATE, "romp", "events-cache");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `${sid}.json`), JSON.stringify({ data: { events } }));
}

test("DETAILS never re-opens a DONE verdict (latching)", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("links.jsonl", [
    link("r1", ["a1"], "DONE", T0 + 100),
    link("r2", ["a1"], "DETAILS", T0 + 200),   // wrap-up cleanup riding the node
  ]);
  assert.equal(colOf(fold(), "a1"), "completed", "routine DETAILS after DONE is transparent");
});

test("an ANSWER row crosses a DECISION off and renders as the user's ↩ row", () => {
  writeRows("nodes.jsonl", [
    ask("a1", T0),
    { kind: "answer", id: "a1", t: T0 + 200, text: "yes, ship it", turn_id: `${SID}:${T0 + 200}:cafe0001` },
  ]);
  writeRows("links.jsonl", [link("r1", ["a1"], "DECISION", T0 + 100)]);
  const asks = fold();
  assert.equal(colOf(asks, "a1"), "asks", "anchored answer reads in-flight again");
  const a = asks.find((x) => x.itemId === "a1")!;
  assert.ok(a.linked.some((r) => r.answer === true), "the answer renders in the history");
});

test("auto-filing: a settled card rests in COMPLETED; blind/empty states never auto-file", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  // owner idle, no handoffs, nothing filed → settled → auto-filed
  const a = foldWith(statesWith("idle")).find((x) => x.itemId === "a1")!;
  assert.equal(a.liveness, "settled");
  assert.equal(a.column, "completed");
  assert.equal(a.autoFiled, true);
  assert.equal(a.explicitDone, false, "green ring, not blue: the judge never stamped it");
  // tmux unreachable (null/empty states) → liveness unknowable → no auto-filing
  assert.equal(colOf(fold(), "a1"), "asks");
});

test("WAIT exempts a settled card from auto-filing (⏳, stays in WORKING)", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  writeRows("links.jsonl", [link("r1", ["a1"], "WAIT", T0 + 100)]);
  const a = foldWith(statesWith("idle")).find((x) => x.itemId === "a1")!;
  assert.equal(a.column, "asks");
  assert.equal(a.autoFiled, false);
  assert.equal(a.waiting, true);
});

test("claim-lag hold: a busy owner with an unclaimed open turn holds auto-filing", () => {
  writeRows("nodes.jsonl", [ask("a1", T0)]);
  // the owner is mid-turn on a prompt no card has claimed yet
  writeEventsCache(SID, [{ id: `${SID}:${T0 + 500}:feed9999`, t: T0 + 500, open: true }]);
  const a = foldWith(statesWith("working")).find((x) => x.itemId === "a1")!;
  assert.equal(a.column, "asks", "held: the unattributed turn may be this card");
  assert.equal(a.autoFiled, false);
  // …and once the open turn IS this card's (claimed), the card goes active
  writeEventsCache(SID, [{ id: `${SID}:${T0}:abcd1234`, t: T0, open: true }]);
  const b = foldWith(statesWith("working")).find((x) => x.itemId === "a1")!;
  assert.equal(b.liveness, "active");
});
