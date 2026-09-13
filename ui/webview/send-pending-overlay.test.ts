// T389 (the user 2026-09-12): a follow-up sent while a message was provisional drew twice until it landed. The pure rule,
// executed: a pending send's anchor is the last TRANSCRIPT event, never one of the kernel's live overlay cards, which sit
// after the queued group at the tail; anchored on the API-error card, the kernel's copy of the send sat before the anchor
// and never covered it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { OVERLAY_KINDS, reconcilePending, stampBase, type PendingSend, type TailEvent } from "./send-pending";

const P = (text: string, qid: string): PendingSend => ({ text, body: text, ts: 1000, qid });

test("the overlay kinds are the kernel's live cards, the queued group included", () => {
  assert.deepEqual([...OVERLAY_KINDS].sort(), ["apiError", "clearing", "compacting", "queued", "reconnecting", "retrying", "todo"]);
});

test("a send pressed while the API-error card stands at the tail anchors on the last transcript event, not the card", () => {
  const a = P("first, tighten the search index", "echo:" + "a".repeat(32));
  const b = P("second, add the missing test", "echo:" + "b".repeat(32));
  // the frame at B's press: the transcript's tool turn, the kernel's queued group holding A's copy, the API-error overlay
  const atPress: TailEvent[] = [
    { kind: "user", md: "drop the unused import", uuid: "u2" },
    { kind: "tool", uuid: "a2" },
    { kind: "queued", texts: [{ md: a.text, qid: a.qid, cancelable: true }] },
    { kind: "apiError", uuid: "apiError" },
  ];
  const base = stampBase(atPress, b);
  assert.equal(base.after, "a2", "the anchor is the tool turn, the last transcript event; the card wears a word, not a record");
  assert.equal(base.queued, 0, "no copy of B's text was queued at the press");
});

test("the kernel's next push lists both copies after the anchor: both sends are covered, both copies hidden, both bubbles ours", () => {
  const a = P("first, tighten the search index", "echo:" + "a".repeat(32));
  const b = P("second, add the missing test", "echo:" + "b".repeat(32));
  const atPressA: TailEvent[] = [{ kind: "user", md: "drop the unused import", uuid: "u2" }, { kind: "tool", uuid: "a2" }];
  reconcilePending(atPressA, [a]);                       // A's press: stamped against the bare tail
  const afterA: TailEvent[] = [...atPressA, { kind: "queued", texts: [{ md: a.text, qid: a.qid, cancelable: true }] }, { kind: "apiError", uuid: "apiError" }];
  reconcilePending(afterA, [a]);                          // the kernel's push after A: A covered
  reconcilePending(afterA, [a, b]);                       // B's press against that frame: B stamped
  assert.equal(b.at!.after, "a2");
  const afterB: TailEvent[] = [...atPressA,
    { kind: "queued", texts: [{ md: a.text, qid: a.qid, cancelable: true }, { md: b.text, qid: b.qid, cancelable: true }] },
    { kind: "apiError", uuid: "apiError" }];
  const r = reconcilePending(afterB, [a, b]);
  assert.deepEqual(r.keep, [a, b], "both pending");
  assert.deepEqual(r.inject, [a, b], "both bubbles ours, at the tail, in send order");
  assert.deepEqual(r.unqueue, [a, b], "both kernel copies covered: hidden, so neither message draws twice");
  assert.equal(b.received, true, "the kernel's copy proves it received B");
});

test("the landing of the first changes the first alone: its record retires it by id, the copies of the second and third still cover theirs", () => {
  const a = P("first, tighten the search index", "echo:" + "a".repeat(32));
  const b = P("second, add the missing test", "echo:" + "b".repeat(32));
  const c = P("third, run the formatter once more", "echo:" + "c".repeat(32));
  const copy = (p: PendingSend) => ({ md: p.text, qid: p.qid, cancelable: true });
  const tail: TailEvent[] = [{ kind: "user", md: "drop the unused import", uuid: "u2" }, { kind: "tool", uuid: "a2" }];
  reconcilePending(tail, [a]);                                                                    // A's press
  reconcilePending([...tail, { kind: "queued", texts: [copy(a)] }], [a, b]);                      // B's press: A's copy listed
  reconcilePending([...tail, { kind: "queued", texts: [copy(a), copy(b)] }], [a, b, c]);          // C's press: both listed
  const held = reconcilePending([...tail, { kind: "queued", texts: [copy(a), copy(b), copy(c)] }], [a, b, c]);
  assert.deepEqual(held.unqueue, [a, b, c], "three copies, three covers: each message one row, the page's own");
  assert.deepEqual(held.inject, [a, b, c]);
  // the CLI takes A and writes its record; the kernel pairs the record with A's id and lists the two copies it still holds
  const landing: TailEvent[] = [...tail, { kind: "user", md: a.text, uuid: "la1", qid: a.qid }, { kind: "queued", texts: [copy(b), copy(c)] }];
  const r = reconcilePending(landing, [a, b, c]);
  assert.deepEqual(r.landed, [{ p: a, idx: 2 }], "A's record retires A, by id");
  assert.deepEqual(r.keep, [b, c], "B and C still pending");
  assert.deepEqual(r.unqueue, [b, c], "their copies still cover them: hidden, the page's bubbles stay the rows");
  assert.deepEqual(r.inject, [b, c]);
  assert.deepEqual(r.lost, []);
  assert.equal(b.at!.after, "a2", "B's anchor did not move on A's landing");
  assert.equal(c.at!.after, "a2", "nor C's");
});

test("the echo half: an idle session's echo atom at the tail with an overlay card after it, then a second send: both covered by their echoes", () => {
  // the verifier's probe at the head (T389 review, low 2): echoHide names both echo atoms, both sends read received, the base was wrong
  const a = P("first, tighten the search index", "echo:" + "a".repeat(32));
  const b = P("second, add the missing test", "echo:" + "b".repeat(32));
  const tail: TailEvent[] = [{ kind: "user", md: "drop the unused import", uuid: "u2" }, { kind: "assistant", uuid: "a2" }];
  reconcilePending(tail, [a]);                                                                          // A's press against the bare tail
  const echoA: TailEvent = { kind: "user", md: a.text, uuid: a.qid };                                   // the kernel's echo atom wears A's id
  const todo: TailEvent = { kind: "todo", uuid: "todo" };
  reconcilePending([...tail, echoA, todo], [a]);                                                        // the push after A: its echo, the card last
  reconcilePending([...tail, echoA, todo], [a, b]);                                                     // B's press against that frame
  assert.equal(b.at!.after, "a2", "B anchors on the last transcript event: neither A's echo (replaced by A's record when it lands) nor the card");
  const echoB: TailEvent = { kind: "user", md: b.text, uuid: b.qid };
  const r = reconcilePending([...tail, echoA, echoB, todo], [a, b]);
  assert.deepEqual(r.echoHide, [2, 3], "both echo atoms covered: hidden, ours drawn");
  assert.deepEqual(r.inject, [a, b]);
  assert.deepEqual(r.keep, [a, b]);
  assert.equal(a.received && b.received, true, "both sends proven received by their echoes");
});

test("the same push before the fix's rule: anchored on the card, the copy sat before the anchor and never covered (the shape the lab saw)", () => {
  // stampBase with the card taken as stable puts `after` at the card; scanning from after it finds no queued copy
  const b = P("second, add the missing test", "echo:" + "b".repeat(32));
  b.at = { after: "apiError", seen: [], queued: 0 };   // the anchor the old rule produced
  const afterB: TailEvent[] = [
    { kind: "tool", uuid: "a2" },
    { kind: "queued", texts: [{ md: b.text, qid: b.qid, cancelable: true }] },
    { kind: "apiError", uuid: "apiError" }];
  const r = reconcilePending(afterB, [b]);
  assert.deepEqual(r.unqueue, [], "nothing after the card: the copy is not read as the cover, the message draws twice");
  assert.deepEqual(r.inject, [b]);
});
