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
        jd.MESSAGES.write_text("\n".join(
            json.dumps({"from_id": f, "to_id": t, "t": ts, "id": "m%d" % i}) for i, (f, t, ts) in enumerate(rows)) + "\n")

    def test_unanswered_outbound_to_live_peer_is_a_wait(self):
        self._msgs([(X, Y, 100)])                         # X → Y, no reply back
        g = km._wait_for_graph(0, {X, Y})
        self.assertEqual(g.get(X, {}).get("peerSid"), Y, "X waits on Y")
        self.assertFalse(g[X]["inCycle"])
        self.assertNotIn(Y, g, "Y isn't waiting on anyone")

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
