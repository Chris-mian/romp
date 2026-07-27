#!/usr/bin/env python3
"""_echo_clear_targets: the parse-identity backfill's clear selection (the user 2026-07-26).

The one-time sweep re-mints goals for placements orphaned by the 435d9df segment-identity change;
minted nodes whose evidence is entirely older than the age cutoff are bookkeeping echoes and get
cleared at the LARGEST all-old-subtree granularity — a mixed-age top keeps its fresh outcomes and
only the all-old sub clears; pre-existing nodes are never touched. Synthetic stores only."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_echobackfill", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1785200000
OLD = NOW - 3 * 86400          # evidence well past the 24h cutoff
FRESH = NOW - 3600             # evidence from this afternoon


def _store(nodes):
    return {"rompUuid": SID, "nodes": nodes, "status": {}, "placements": {}}


def _n(gid, t, parent=None, cleared=False):
    return {"id": gid, "text": "x", "parentId": parent, "t": t,
            "nodeComplete": False, "blocked": False, "cleared": cleared}


class EchoClearTargets(unittest.TestCase):
    def test_all_old_minted_top_clears_at_the_top(self):
        g, s1, s2 = SID + ":g1", SID + ":g2", SID + ":g3"
        store = _store({g: _n(g, OLD), s1: _n(s1, OLD, g), s2: _n(s2, OLD, g)})
        self.assertEqual(jd._echo_clear_targets(store, {g, s1, s2}, NOW), [g],
                         "largest granularity: one clear at the top, the subtree rides roll-down")

    def test_mixed_age_top_keeps_fresh_and_clears_only_the_old_sub(self):
        g, old, fresh = SID + ":g1", SID + ":g2", SID + ":g3"
        store = _store({g: _n(g, OLD), old: _n(old, OLD, g), fresh: _n(fresh, FRESH, g)})
        self.assertEqual(jd._echo_clear_targets(store, {g, old, fresh}, NOW), [old],
                         "a mixed-age top keeps its fresh outcomes; only the all-old sub clears")

    def test_old_minted_sub_under_a_pre_existing_top_clears_the_sub_only(self):
        top, sub = SID + ":g1", SID + ":g2"
        store = _store({top: _n(top, OLD), sub: _n(sub, OLD, top)})
        self.assertEqual(jd._echo_clear_targets(store, {sub}, NOW), [sub],
                         "a pre-existing top is never a target even when its evidence is old")

    def test_fresh_mints_and_untouched_old_nodes_yield_nothing(self):
        g, h = SID + ":g1", SID + ":g2"
        store = _store({g: _n(g, FRESH), h: _n(h, OLD)})
        self.assertEqual(jd._echo_clear_targets(store, {g}, NOW), [],
                         "fresh mints stay; old nodes the sweep did not mint stay")

    def test_already_cleared_descendant_lets_the_ancestor_clear_but_is_not_re_emitted(self):
        g, done = SID + ":g1", SID + ":g2"
        store = _store({g: _n(g, OLD), done: _n(done, OLD, g, cleared=True)})
        self.assertEqual(jd._echo_clear_targets(store, {g}, NOW), [g],
                         "an already-cleared sub is off the board — it neither blocks nor re-clears")


if __name__ == "__main__":
    unittest.main()
