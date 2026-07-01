#!/usr/bin/env python3
"""Click-to-cite (the user 2026-07-01): a feed card click that resolves to a LIVE goal node attaches a
`cite:{itemId,title}` to the chat `focus` message, so the chat seeds a dismissible composer citation chip.
_cite_for is the resolver; a cleared/missing node yields no chip (so a cleared card never re-opens on send).
Synthetic fixtures only (placeholder UUIDs / TESTHOST)."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_cite", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class CiteFor(unittest.TestCase):
    def setUp(self):
        self._orig = km.jd.load_goals

    def tearDown(self):
        km.jd.load_goals = self._orig

    def _store(self, nodes):
        km.jd.load_goals = lambda fsid: {"nodes": nodes}

    def test_live_goal_node_resolves_to_a_citation(self):
        self._store({SID + ":g1": {"text": "Fix the compaction rendering"}})
        self.assertEqual(km._cite_for(SID + ":g1"),
                         {"itemId": SID + ":g1", "title": "Fix the compaction rendering"})

    def test_a_sub_goal_cites_itself_not_the_top(self):
        # granularity is free: clicking a sub-goal cites the SUB node's own text
        self._store({SID + ":g1": {"text": "Top goal"},
                     SID + ":g2": {"text": "A specific sub-goal", "parentId": SID + ":g1"}})
        self.assertEqual(km._cite_for(SID + ":g2")["title"], "A specific sub-goal")

    def test_cleared_goal_is_not_cited(self):
        # a cleared card is archived out of the live store's intent → no chip (and its follow-up would no-op)
        self._store({SID + ":g1": {"text": "Done and cleared", "cleared": True}})
        self.assertIsNone(km._cite_for(SID + ":g1"))

    def test_unknown_node_or_empty_id_is_not_cited(self):
        self._store({SID + ":g1": {"text": "exists"}})
        self.assertIsNone(km._cite_for(SID + ":gX"), "a node absent from the live store → None")
        self.assertIsNone(km._cite_for(""), "no itemId → None")

    def test_titleless_node_is_not_cited(self):
        self._store({SID + ":g1": {"text": "   "}})
        self.assertIsNone(km._cite_for(SID + ":g1"))


class ShowOnTimelineFocus(unittest.TestCase):
    def setUp(self):
        self._orig = km.jd.load_goals

    def tearDown(self):
        km.jd.load_goals = self._orig

    def test_focus_carries_the_citation_for_a_goal_click(self):
        km.jd.load_goals = lambda fsid: {"nodes": {SID + ":g1": {"text": "Cited goal"}}}
        f = km._show_on_timeline_focus({"sid": SID, "itemId": SID + ":g1", "t": 123, "anchor": "prompt"})
        self.assertEqual(f["type"], "focus")
        self.assertEqual(f["id"], SID)
        self.assertEqual(f["cite"], {"itemId": SID + ":g1", "title": "Cited goal"})

    def test_focus_has_no_cite_for_a_non_goal_target(self):
        km.jd.load_goals = lambda fsid: {"nodes": {}}
        f = km._show_on_timeline_focus({"sid": SID, "itemId": SID + ":reply7", "t": 123})
        self.assertNotIn("cite", f, "a target that isn't a live goal node seeds no chip")


if __name__ == "__main__":
    unittest.main()
