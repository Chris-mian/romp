#!/usr/bin/env python3
"""T386 stage 2 (plans/chat-history-regions.md Part B, the kernel): every history reply names its TURN SPAN so the page can place
it among its regions; a gap's page is asked by span (loadTurns) and served exactly; and the per-client base is TAIL-ONLY: a reply
moves the client's base only when its span reaches the tail run, so the kernel never withholds a delta from a reader in older
history (no client is ever detached). Over the render-floor fixture (a restored parse whose pre-cut turns are lazy) the pages
before the floor and the floor'd list equal the whole build, so a span's events are checked against the whole. Synthetic
transcripts only (the stage 4a served fixture's builder)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from test_chat_pages import NOW, SID, Harness, _client, _strip, em, km, transcript  # noqa: E402  the hermetic preamble (a temp XDG root, the kernel loaded from bin) runs on import


class WindowSpans(Harness):
    def _boot(self):
        recs = transcript(NOW - 86400, turns=120, compact_every=25)
        self.write(recs)
        whole = self.whole()
        self.document()
        m = self.restored()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        frame = sent[-1]
        return whole, m, frame, c

    def test_the_full_frame_names_the_tail_runs_first_turn_and_the_page_size(self):
        whole, m, frame, _ = self._boot()
        self.assertIn("tailLo", frame, "the full frame names where the tail run starts, so the page can lay a gap before it")
        self.assertGreater(frame["tailLo"], 0, "a restored parse's tail does not start at the head")
        self.assertEqual(frame["pageTurns"], km.PAGE_TURNS, "the page the gaps ask by")
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        self.assertLessEqual(frame["tailLo"], len(turns))
        # the tail run's first event is the first event of turn tailLo
        first_tail = next(a["uuid"] for a in turns[frame["tailLo"]]["atoms"] if a.get("uuid"))
        resident = [e["uuid"] for e in _strip(frame["events"])]
        self.assertEqual(resident[0], first_tail, "the run the page holds starts at the named turn")

    def test_load_around_carries_its_span_and_no_connected_verdict(self):
        whole, m, frame, c = self._boot()
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        anchor = whole[len(whole) // 4]["uuid"]
        w = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW, base=c["echat"][SID])
        self.assertNotIn("missing", w)
        self.assertEqual(len(w["span"]), 2, "a window names [lo, hi) in the kernel's turn numbering")
        lo, hi = w["span"]
        self.assertLess(lo, hi); self.assertLessEqual(hi, len(turns))
        self.assertIn(anchor, [e["uuid"] for e in w["events"]], "the anchor is inside its window")
        self.assertEqual([e["uuid"] for e in w["events"]], [e["uuid"] for e in km._chat_history_page(SID, lo, hi, NOW)], "the window IS the span's page")
        self.assertNotIn("connected", w, "no detached verdict: the tail run is always resident on the page")
        head = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": whole[0]["uuid"]}, NOW, base=c["echat"][SID])
        self.assertEqual(head["span"][0], 0, "a window reaching the head spans from turn 0, whatever the head cards' own index: %r" % head["span"])
        self.assertEqual([e["uuid"] for e in head["events"][:len(self.head_cards)]], [e["uuid"] for e in self.head_cards], "…and carries the head cards")
        self.assertNotIn("_base", {k: v for k, v in w.items() if v is not None}, "a window short of the tail moves no base") if hi < frame["tailLo"] else None

    def test_load_older_carries_its_span_and_the_tail_only_base(self):
        whole, m, frame, c = self._boot()
        base = c["echat"][SID]
        oldest = _strip(frame["events"])[0]["uuid"]
        r = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": oldest}, NOW, base=base)
        self.assertNotIn("missing", r)
        self.assertEqual(r["span"][1], frame["tailLo"], "the chunk before the tail ends where the tail run starts")
        lo, hi = r["span"]
        self.assertLess(lo, hi)
        self.assertEqual([e["uuid"] for e in r["events"][len(self.head_cards) if lo == 0 else 0:]], [e["uuid"] for e in km._chat_history_page(SID, lo, hi, NOW)], "the span is honest: its events are exactly the turns it names")
        self.assertTrue(r.get("_base") and r["_base"].get("first"), "a page joining the tail run moves the client's base to its first event: the tail-only base")
        self.assertEqual(r["_base"]["first"], km._event_key(r["events"][len(self.head_cards) if lo == 0 else 0]), "…its first TRANSCRIPT event (the head cards ride a chunk that reaches the head, and are no base)")
        # a page deep in history, not touching the tail, moves nothing
        if lo > 0:
            deep = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": r["events"][0]["uuid"]}, NOW, base=base)
            self.assertNotIn("missing", deep)
            self.assertEqual(deep["span"][1], lo, "the chunks tile: each ends where the next begins")
            self.assertFalse(deep.get("_base"), "a chunk short of the tail moves no base (the reader is not detached, the tail's deltas keep flowing)")

    def test_load_turns_serves_exactly_the_span_asked_with_the_head_cards_at_the_head(self):
        whole, m, frame, c = self._boot()
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        for lo, hi in ((0, 16), (16, 48), (20, 37), (frame["tailLo"] - 5, frame["tailLo"])):
            with self.subTest(lo=lo, hi=hi):
                n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": lo, "hi": hi}, NOW, base=c["echat"][SID])
                self.assertNotIn("missing", n)
                self.assertEqual(n["span"], [lo, hi], "the span comes back as asked (alignment is the page's rule, chat-regions.ts pagesToAsk)")
                self.assertEqual(n["head"], lo == 0)
                body = n["events"][len(self.head_cards):] if lo == 0 else n["events"]
                if lo == 0:
                    self.assertEqual([e["uuid"] for e in n["events"][:len(self.head_cards)]], [e["uuid"] for e in self.head_cards], "the head cards ride the head page")
                self.assertEqual([e["uuid"] for e in body], [e["uuid"] for e in km._chat_history_page(SID, lo, hi, NOW)])
                if hi >= frame["tailLo"]:
                    self.assertTrue(n.get("_base") and n["_base"].get("first"), "a span reaching the tail moves the base to its first event")
                else:
                    self.assertFalse(n.get("_base"), "a span short of the tail moves no base")
        empty = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": 40, "hi": 40}, NOW)
        self.assertTrue(empty["missing"], "an empty span is missing, never a silent empty run")
        past = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": len(turns) + 5, "hi": len(turns) + 9}, NOW)
        self.assertTrue(past["missing"], "a span past the transcript is missing")
        self.assertEqual(past["span"], [len(turns) + 5, len(turns) + 9], "…and echoes the ASKED span, not the clamp, so the page's gapLoading key clears (T386 stage 2, low 3)")

    def test_load_turns_head_page_carries_the_head_cards_at_floor_zero(self):
        # round seven, medium 2: with no render floor the head cards are IN the floor'd list (turn index -1, above turn 0) and the
        # reply's head_cards field is empty, so the head page must start at the list's first event or the system context and the
        # /clear card never reach a reader who scrolls to the top (the reply says head, so nothing asks again)
        recs = transcript(NOW - 86400, turns=40)                           # no compaction: the whole build stands at floor 0
        self.write(recs)
        # the floor-0 build itself, cards and all (the harness's whole() strips them), from a fresh process with no document, as whole()
        # builds it: a build over the module's shared state left a stale lazy index behind for the next module (CI, round seven)
        self.fresh(); saved = em._CKPT_DIR_FN; em._CKPT_DIR_FN = None
        try:
            m0 = km.build_session(SID, NOW, {}, floor=0)
        finally:
            em._CKPT_DIR_FN = saved
        whole = m0["events"]
        self.assertEqual(int(m0.get("floor") or 0), 0, "the build stands at floor 0: %r" % m0.get("floor"))
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        tix = km._turn_index_of_events(whole, turns)
        self.assertEqual(tix[0], -1, "the fixture fact: a head card leads the floor-0 list: %r" % whole[0].get("kind"))
        first_turn0 = next(i for i, ti in enumerate(tix) if ti >= 0)
        self.assertGreater(first_turn0, 0, "…at least one card above turn 0")
        n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": 0, "hi": 16}, NOW)
        self.assertNotIn("missing", n); self.assertTrue(n["head"]); self.assertEqual(n["span"], [0, 16])
        end = next((i for i, ti in enumerate(tix) if ti >= 16), len(whole))
        self.assertEqual([e["uuid"] for e in n["events"]], [e["uuid"] for e in whole[:end]],
                         "the head page at floor 0 starts at the list's first event, the head cards riding along, through turn 15")
        self.assertEqual(n["events"][0]["uuid"], whole[0]["uuid"], "the first event served is the first card")

    def test_a_socket_before_its_ready_gets_no_chat_frame_and_its_ready_brings_the_declared_wire(self):
        # round eleven: the kernel used to serve INDEX frames to a socket that had not yet sent `ready` (the pusher fires from the socket's
        # open, the bundle evaluates later), so a proto-2 page whose ready lost that race held an index frame at its reload restore and
        # landed through the older wire (the mid-run reload red on CI: a reload-restore write, then loadOlder, loadAround 0)
        whole, m, frame, c = self._boot()
        fresh = {"send": (lambda s: sent.append(json.loads(s))), "echat": {}, "handshake": False}   # a real socket before its ready, as the accept marks it
        sent = []
        rows = []
        from unittest import mock
        with mock.patch.object(km, "_client_diag_append", lambda fp, line: rows.append((fp.name, json.loads(line)))):
            km._send_chat_locked(fresh, m, None, 0, False)
            km._send_chat_locked(fresh, m, None, 0, False)                          # a second push while the handshake is still out
        self.assertEqual(sent, [], "a socket before its ready gets no chat frame: %r" % [f.get("type") for f in sent])
        self.assertNotIn(SID, fresh["echat"], "…and the kernel believes it holds nothing")
        # the follow-up after PR 1584, low 2: what the kernel withholds is said ONCE per socket, in the client diagnostics file
        self.assertEqual([(n, r["what"], r["surface"], r["data"]["sid"]) for n, r in rows], [("client-diag.jsonl", "chatWithheld", "kernel", SID)],
                         "one row for the socket, not one per withheld frame: %r" % rows)
        fresh["proto"] = 2; fresh["handshake"] = True                               # the handshake declares the uuid wire
        km._send_chat_locked(fresh, m, None, 0, False)
        self.assertEqual([f.get("type") for f in sent], ["session"], "the first frame after the handshake is the session")
        self.assertEqual(sent[0].get("proto"), 2, "…in the wire the handshake declared: %r" % {k: sent[0].get(k) for k in ("proto", "tailLo", "headFrom")})
        self.assertIsInstance(sent[0].get("tailLo"), int, "a proto-2 frame names the tail run's first turn")

    def test_load_newer_is_retired(self):
        self._boot()
        r = km._chat_history_reply(SID, {"type": "loadNewer", "id": SID, "after": "11111111-2222-3333-4444-000000000001"}, NOW)
        self.assertTrue(r.get("missing") and r.get("retired"), "the walk toward the tail is gone: the tail run is always resident (T386 stage 2): %r" % r)


if __name__ == "__main__":
    unittest.main()
