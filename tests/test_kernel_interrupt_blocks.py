#!/usr/bin/env python3
"""Interrupted → Blocked (the user 2026-07-07, extending the stalled rule): the user stopped the session
mid-turn, nothing moves until they speak, so the focus goal records a block verdict (src "interrupt") and
reaches Needs-you via the normal ladder. Their next message lifts OUR block with an explicit unblock event
(the same event that re-arms auto-nudge); a REAL judge verdict recorded in between owns the card and
stays. XDG isolation before the kernel loads. Synthetic fixtures only."""
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_STATE_TMP = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _STATE_TMP
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
kern = SourceFileLoader("romp_kernel_intrblk", os.path.join(BIN, "romp-kernel")).load_module()
jd = kern.jd

SID = "11111111-2222-3333-4444-555555555555"
GID = SID + ":g1"
NOW = int(time.time())


def _seed(status="working"):
    store = {"rompUuid": SID, "seq": 1, "placements": {}, "status": {},
             "lastNode": GID,
             "nodes": {GID: {"id": GID, "text": "Ship the widget", "parentId": None,
                             "nodeComplete": False, "blocked": False, "cleared": False,
                             "trail": [], "t": NOW - 600, "mt": NOW - 300}}}
    jd.rollup_status(store, False)
    jd.save_goals(SID, store)
    return store


class InterruptBlocks(unittest.TestCase):
    def setUp(self):
        kern._write_auto_nudge({"enabled": True, "nudged": {}})

    def test_interrupt_blocks_the_focus_goal_via_the_diary(self):
        _seed()
        gid = kern._record_interrupt_block(SID)
        self.assertEqual(gid, GID)
        st = jd.load_goals(SID)
        self.assertEqual(st["status"][GID], "blocked", "the stopped focus goal needs the user")
        ev = [e for e in st["nodes"][GID]["log"] if e["kind"] == "block"]
        self.assertEqual([e["src"] for e in ev], ["interrupt"])
        self.assertIn("waiting on your next instruction", ev[0]["why"])

    def test_reengage_lifts_our_block_with_an_unblock_event(self):
        _seed()
        kern._record_interrupt_block(SID)
        kern._lift_interrupt_block(SID, GID)
        st = jd.load_goals(SID)
        self.assertEqual(st["status"][GID], "working", "the user spoke → the block lifts")
        kinds = [(e["src"], e["kind"]) for e in st["nodes"][GID]["log"]]
        self.assertIn(("user", "unblock"), kinds, "lifted by an explicit event — the diary stays the authority")

    def test_a_real_judge_block_recorded_since_stays(self):
        _seed()
        kern._record_interrupt_block(SID)
        st = jd.load_goals(SID)
        jd.record_verdict(st, st["nodes"][GID], "closer", "block", NOW + 10, why="pick a name")
        jd.rollup_status(st, False)
        jd.save_goals(SID, st)
        kern._lift_interrupt_block(SID, GID)
        st = jd.load_goals(SID)
        self.assertEqual(st["status"][GID], "blocked", "a genuine verdict owns the card; the lift is a no-op")

    def test_no_working_focus_means_nothing_to_block(self):
        store = _seed()
        jd.record_verdict(store, store["nodes"][GID], "closer", "done", NOW - 10, why="shipped")
        store["nodes"][GID]["nodeComplete"] = True   # (a hand-flip alone would be reverted by the fold)
        jd.rollup_status(store, True)
        jd.save_goals(SID, store)
        self.assertIsNone(kern._record_interrupt_block(SID))

    def test_marker_bookkeeping(self):
        kern._set_intr_blocked(SID, GID)
        self.assertEqual(kern._intr_blocked(SID), GID)
        kern._set_intr_blocked(SID, None)
        self.assertIsNone(kern._intr_blocked(SID))


if __name__ == "__main__":
    unittest.main()
