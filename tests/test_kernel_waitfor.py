#!/usr/bin/env python3
"""The fleet WAIT-FOR graph (the user 2026-06-22): a session X 'waits on' peer Y when X's latest message to
Y has no reply back and Y is ALIVE. It's a functional graph (each X → one Y), so following the chains
detects deadlock CYCLES. build_feed attaches it per working card (waitingOn) for the 'waiting on <thread>'
chip + the auto-nudge gate. Self-contained: drives _wait_for_graph against a synthetic messages.jsonl.

Note: a DIRECT 2-cycle (X↔Y) is impossible by construction — whoever messaged most recently is the waiter,
the other's older message counts as answered — so a real deadlock is a 3+ chain that loops."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_wf", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

X = "aaaaaaaa-0000-0000-0000-000000000001"
Y = "bbbbbbbb-0000-0000-0000-000000000002"
Z = "cccccccc-0000-0000-0000-000000000003"


class WaitFor(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.MESSAGES
        jd.MESSAGES = Path(self.td.name) / "messages.jsonl"

    def tearDown(self):
        jd.MESSAGES = self.saved
        self.td.cleanup()

    def _msgs(self, rows):
        # rows are (from, to, t) or (from, to, t, body); default body is a reply-required QUESTION so the
        # base wait-edge tests fire (only QUESTION/ASK messages create a wait — the user 2026-06-22)
        def rec(i, r):
            body = r[3] if len(r) > 3 else "QUESTION: status?"
            return json.dumps({"from_id": r[0], "to_id": r[1], "t": r[2], "id": "m%d" % i, "body": body})
        jd.MESSAGES.write_text("\n".join(rec(i, r) for i, r in enumerate(rows)) + "\n")

    def test_unanswered_outbound_to_live_peer_is_a_wait(self):
        self._msgs([(X, Y, 100)])                         # X → Y QUESTION, no reply back
        g = km._wait_for_graph(0, {X, Y})
        self.assertEqual(g.get(X, {}).get("peerSid"), Y, "X waits on Y")
        self.assertFalse(g[X]["inCycle"])
        self.assertNotIn(Y, g, "Y isn't waiting on anyone")

    def test_only_reply_required_messages_create_a_wait(self):
        self._msgs([(X, Y, 100, "COORDINATE: heads-up, I landed the thing")])   # FYI, no reply expected
        self.assertEqual(km._wait_for_graph(0, {X, Y}), {}, "a COORDINATE/FYI is not a wait")
        self._msgs([(X, Y, 100, "QUESTION: can you confirm the schema?")])      # reply REQUIRED
        self.assertEqual(km._wait_for_graph(0, {X, Y}).get(X, {}).get("peerSid"), Y, "a QUESTION is a wait")

    def test_a_reply_of_any_kind_answers_the_question(self):
        # X asks; Y replies with a COORDINATE — any reply clears X's wait, and Y's non-question reply doesn't
        # make Y wait on X (so an actively-coordinating session doesn't show a spurious chip)
        self._msgs([(X, Y, 100, "QUESTION: status?"), (Y, X, 200, "COORDINATE: here you go, done")])
        g = km._wait_for_graph(0, {X, Y})
        self.assertNotIn(X, g, "any reply answers X's question")
        self.assertNotIn(Y, g, "Y's reply was a COORDINATE, not a question → Y isn't waiting")

    def test_a_reply_flips_the_wait_to_the_replier(self):
        # Y replies to X → X's outbound is answered (X no longer waits), but Y's reply is now the unanswered
        # latest, so the ball is in X's court: Y waits on X. (A reply is a message too; the graph can't tell
        # an answer from a counter-question, so it conservatively treats the last sender as waiting.)
        self._msgs([(X, Y, 100), (Y, X, 200)])
        g = km._wait_for_graph(0, {X, Y})
        self.assertNotIn(X, g, "X is no longer waiting — Y replied")
        self.assertEqual(g.get(Y, {}).get("peerSid"), X, "now Y waits on X's response")

    def test_dead_peer_is_not_a_wait(self):
        self._msgs([(X, Y, 100)])
        self.assertEqual(km._wait_for_graph(0, {X}), {}, "Y not alive → X isn't waiting on it")

    def test_three_way_cycle_is_a_deadlock(self):
        self._msgs([(X, Y, 100), (Y, Z, 100), (Z, X, 100)])   # X→Y→Z→X, each the latest unanswered
        g = km._wait_for_graph(0, {X, Y, Z})
        self.assertEqual((g[X]["peerSid"], g[Y]["peerSid"], g[Z]["peerSid"]), (Y, Z, X))
        self.assertTrue(all(g[s]["inCycle"] for s in (X, Y, Z)), "X→Y→Z→X is a deadlock cycle")

    def test_chain_to_a_sink_is_not_a_cycle(self):
        self._msgs([(X, Y, 100), (Y, Z, 100)])            # X→Y→Z, Z a sink (waits on no one)
        g = km._wait_for_graph(0, {X, Y, Z})
        self.assertEqual((g[X]["peerSid"], g[Y]["peerSid"]), (Y, Z))
        self.assertFalse(g[X]["inCycle"] or g[Y]["inCycle"], "a chain to a sink is not a deadlock")
        self.assertNotIn(Z, g)

    def test_picks_the_most_recent_unanswered_peer(self):
        self._msgs([(X, Y, 100), (X, Z, 200)])            # X waits on both; the chip shows the most-recent (Z)
        g = km._wait_for_graph(0, {X, Y, Z})
        self.assertEqual(g[X]["peerSid"], Z, "X's primary wait is its most-recent unanswered outbound")


if __name__ == "__main__":
    unittest.main()


class DeclaredKindWins(unittest.TestCase):
    """The schema `kind` field is the designed intent source (send_message REQUIRES it); the body regex
    is only the fallback for legacy rows that predate the field (the 2026-07-22 unification)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.MESSAGES
        jd.MESSAGES = Path(self.td.name) / "messages.jsonl"

    def tearDown(self):
        jd.MESSAGES = self.saved
        self.td.cleanup()

    def _msgs(self, rows):
        # rows are (from, to, t, body, kind); kind="" omits the field (a legacy row)
        def rec(i, r):
            o = {"from_id": r[0], "to_id": r[1], "t": r[2], "id": "m%d" % i, "body": r[3]}
            if r[4]:
                o["kind"] = r[4]
            return json.dumps(o)
        jd.MESSAGES.write_text("\n".join(rec(i, r) for i, r in enumerate(rows)) + "\n")

    def test_kind_question_creates_the_wait_without_any_lead_word(self):
        self._msgs([(X, Y, 100, "can you confirm the schema shape?", "question")])
        self.assertEqual(km._wait_for_graph(0, {X, Y}).get(X, {}).get("peerSid"), Y,
                         "the declared question is a wait even without a QUESTION: lead word")

    def test_a_declared_coordinate_never_creates_a_wait(self):
        self._msgs([(X, Y, 100, "QUESTION: rhetorical, just flagging the rename", "coordinate")])
        self.assertEqual(km._wait_for_graph(0, {X, Y}), {},
                         "the declared kind outranks a question-shaped body")

    def test_legacy_rows_without_kind_keep_the_regex_fallback(self):
        self._msgs([(X, Y, 100, "QUESTION: which port?", "")])
        self.assertEqual(km._wait_for_graph(0, {X, Y}).get(X, {}).get("peerSid"), Y)
        self._msgs([(X, Y, 100, "heads-up: landed the thing", "")])
        self.assertEqual(km._wait_for_graph(0, {X, Y}), {})
