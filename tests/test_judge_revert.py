#!/usr/bin/env python3
"""jd.drop_goals_after(fsid, cut_t): a chat delete/edit rolls the CONVERSATION back to just before cut_t; the
cards MINTED from the now-abandoned turns (node["t"] >= cut_t) are orphans, so they are archived out of the
live store — whole subtrees. Deliberately narrow: verdicts an abandoned turn applied to a PRE-EXISTING card
are left alone (the user chose this simpler shape over surgically reverting the append-only diary + the
durable override journal). All fixtures are SYNTHETIC (placeholder UUIDs, invented text).
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000
T0 = NOW - 3600
CUT = T0 + 50          # everything minted at/after CUT is abandoned; T0..T0+49 survives


class RevertBase(unittest.TestCase):
    def setUp(self):
        self._saved_state = jd.STATE
        self.td = tempfile.TemporaryDirectory()
        jd._rebind_state(Path(self.td.name))

    def tearDown(self):
        jd._rebind_state(self._saved_state)
        self.td.cleanup()

    def _store(self):
        return {"rompUuid": SID, "seq": 0, "placementsV": jd.PLACEMENTS_V, "nodes": {},
                "placements": {}, "status": {}}

    def _nid(self, seq):
        return "%s:g%d" % (SID, seq)


class DropGoalsAfter(RevertBase):
    def test_a_card_minted_after_the_cut_is_archived_whole_subtree(self):
        s = self._store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Survivor"}], [])          # born < CUT
        jd.apply_plan(s, "s2", T0 + 100, [{"do": "mint", "why": "x", "text": "Born in range"}], jd.open_menu(s))
        jd.apply_plan(s, "s3", T0 + 110, [{"do": "sub", "why": "x", "under": 2, "text": "sub of born"}], jd.open_menu(s))
        jd.rollup_status(s, session_closed=False)
        jd.save_goals(SID, s)
        archived = jd.drop_goals_after(SID, CUT)
        self.assertEqual(archived, 2, "the born-in-range top AND its sub are archived")
        live = jd.load_goals(SID)["nodes"]
        self.assertIn(self._nid(1), live, "the survivor stays in the live store")
        self.assertNotIn(self._nid(2), live, "the born-in-range top is gone from the live store")
        self.assertNotIn(self._nid(3), live, "its sub goes with it")
        arch = jd.load_goal_archive(SID)["nodes"]
        self.assertIn(self._nid(2), arch, "the born-in-range top moved to the archive")
        self.assertIn(self._nid(3), arch, "the sub moved with it")

    def test_a_born_in_range_sub_under_a_surviving_parent_is_archived_alone(self):
        s = self._store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Survivor top"}], [])
        jd.apply_plan(s, "s2", T0 + 100, [{"do": "sub", "why": "x", "under": 1, "text": "late sub"}], jd.open_menu(s))
        jd.save_goals(SID, s)
        archived = jd.drop_goals_after(SID, CUT)
        self.assertEqual(archived, 1, "only the late sub is archived; its pre-cut parent survives")
        live = jd.load_goals(SID)["nodes"]
        self.assertIn(self._nid(1), live)
        self.assertNotIn(self._nid(2), live)

    def test_removing_a_born_in_range_blocked_sub_re_rolls_the_surviving_parents_status(self):
        s = self._store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Parent"}], [])
        jd.apply_plan(s, "s2", T0 + 100, [{"do": "sub", "why": "x", "under": 1, "text": "late blocked sub"}],
                      jd.open_menu(s))
        jd.apply_plan(s, "s3", T0 + 110, [{"do": "block", "why": "owed", "goal": 2}], jd.open_menu(s))  # block the sub
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][self._nid(1)], "blocked", "premise: the late sub's block rolls up to the parent")
        jd.save_goals(SID, s)
        jd.drop_goals_after(SID, CUT)
        n = jd.load_goals(SID)
        self.assertEqual(n["status"][self._nid(1)], "working",
                         "with the born-in-range blocked sub gone, the parent re-rolls to working")

    def test_nothing_in_range_is_a_noop(self):
        s = self._store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        jd.save_goals(SID, s)
        self.assertEqual(jd.drop_goals_after(SID, CUT), 0, "no card born at/after the cut → nothing archived")
        self.assertIn(self._nid(1), jd.load_goals(SID)["nodes"], "the pre-cut card is untouched")

    def test_a_pre_existing_cards_verdicts_are_left_alone(self):
        # deliberate scope: a verdict an abandoned turn applied to a card born BEFORE the cut is NOT reverted
        # (that would need diary + override-journal surgery). Only born-in-range cards are dropped.
        s = self._store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Pre-existing"}], [])
        jd.apply_plan(s, "s2", T0 + 100, [{"do": "block", "why": "owed", "goal": 1}], jd.open_menu(s))  # ev_t after CUT
        jd.rollup_status(s, session_closed=False)
        jd.save_goals(SID, s)
        self.assertEqual(jd.drop_goals_after(SID, CUT), 0, "the pre-existing card is not born-in-range → not archived")
        n = jd.load_goals(SID)
        self.assertTrue(n["nodes"][self._nid(1)]["blocked"],
                        "its block (from a now-abandoned turn) is intentionally left in place")

    def test_empty_store_is_a_noop(self):
        jd.save_goals(SID, self._store())
        self.assertEqual(jd.drop_goals_after(SID, CUT), 0)


if __name__ == "__main__":
    unittest.main()
