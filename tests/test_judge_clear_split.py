#!/usr/bin/env python3
"""Clear-time auto-split (the user 2026-07-07, via ui — the buried-SwiftBar case): a distinct nested
deliverable — born from its OWN user ask (promptUuid differs from the top's) and grown or still open —
is promoted to its own top-level goal BEFORE the parent's clear archives it, instead of silently
vanishing with an unrelated card. Split over warn: reversible, no dialogs; the appearing card is the
notice. A childless done leaf sweeps normally; a user-CITED follow-up subtree stays by declaration;
agent-decomposed steps (no promptUuid) never split. Synthetic fixtures only."""
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_STATE_TMP = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _STATE_TMP
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
kern = SourceFileLoader("romp_kernel_clearsplit", os.path.join(BIN, "romp-kernel")).load_module()
jd = kern.jd

SID = "11111111-2222-3333-4444-555555555555"
T = 1781097000
PU_A, PU_B = "aaaa-prompt", "bbbb-prompt"


def _swiftbar_store(deliverable_done=True, cited=False):
    """The real shape: top T (its own prompt) → c1 → c2 (agent steps, no promptUuid) → D (a DIFFERENT
    user prompt) → d1, d2. All complete when deliverable_done."""
    ids = {k: "%s:g%d" % (SID, i + 1) for i, k in enumerate(("T", "c1", "c2", "D", "d1", "d2"))}
    store = {"rompUuid": SID, "seq": 6, "placements": {}, "status": {}, "nodes": {}}

    def put(key, parent, pu=None, **kw):
        store["nodes"][ids[key]] = jd.GuardedNode(
            {"id": ids[key], "text": key, "parentId": ids[parent] if parent else None,
             "nodeComplete": False, "blocked": False, "cleared": False, "promptUuid": pu,
             "trail": [], "t": T, "mt": T, "log": [], **kw})

    put("T", None, pu=PU_A)
    put("c1", "T")
    put("c2", "c1")
    put("D", "c2", pu=PU_B, **({"cited": True} if cited else {}))
    put("d1", "D")
    put("d2", "D")
    if deliverable_done:
        for k in ("T", "c1", "c2", "D", "d1", "d2"):
            jd.record_verdict(store, store["nodes"][ids[k]], "closer", "done", T + 10, why="built")
    return store, ids


class SplitDistinct(unittest.TestCase):
    def test_buried_deliverable_is_promoted_with_its_subtree(self):
        store, ids = _swiftbar_store()
        moved = jd.split_distinct_subtrees(store, ids["T"])
        self.assertEqual(moved, [ids["D"]])
        self.assertIsNone(store["nodes"][ids["D"]]["parentId"], "D is its own top now")
        self.assertEqual(store["nodes"][ids["D"]]["splitFrom"], ids["T"], "provenance kept")
        self.assertEqual(store["nodes"][ids["d1"]]["parentId"], ids["D"], "the subtree rides along")
        jd.rollup_status(store, True)
        self.assertEqual(store["status"][ids["D"]], "completed", "finished work → its own Completed card")

    def test_open_distinct_leaf_splits_but_done_leaf_sweeps(self):
        # open work is never silently swept, even childless; a done childless leaf goes with its parent
        store, ids = _swiftbar_store()
        gid = SID + ":g7"
        store["nodes"][gid] = jd.GuardedNode({"id": gid, "text": "leaf", "parentId": ids["c1"],
                                              "nodeComplete": False, "blocked": False, "cleared": False,
                                              "promptUuid": "cccc-prompt", "trail": [], "t": T, "log": []})
        self.assertIn(gid, jd.split_distinct_subtrees(store, ids["T"]), "open distinct leaf → split")
        store2, ids2 = _swiftbar_store()
        gid2 = SID + ":g7"
        store2["nodes"][gid2] = jd.GuardedNode({"id": gid2, "text": "leaf", "parentId": ids2["c1"],
                                                "nodeComplete": False, "blocked": False, "cleared": False,
                                                "promptUuid": "cccc-prompt", "trail": [], "t": T, "log": []})
        jd.record_verdict(store2, store2["nodes"][gid2], "closer", "done", T + 10, why="done")
        self.assertNotIn(gid2, jd.split_distinct_subtrees(store2, ids2["T"]),
                         "a childless DONE leaf ('also add tests') sweeps with its parent")

    def test_cited_subtree_stays_by_declaration(self):
        store, ids = _swiftbar_store(cited=True)
        self.assertEqual(jd.split_distinct_subtrees(store, ids["T"]), [],
                         "the user cited this card for that follow-up — its subtree belongs here")

    def test_agent_steps_never_split(self):
        store, ids = _swiftbar_store()
        store["nodes"][ids["D"]]["promptUuid"] = None  # agent-decomposed shape: no own user ask
        self.assertEqual(jd.split_distinct_subtrees(store, ids["T"]), [])

    def test_clear_all_promotes_then_clears_only_the_parent(self):
        store, ids = _swiftbar_store()
        jd.rollup_status(store, True)
        jd.save_goals(SID, store)
        kern._clear_all([ids["T"]])
        st = jd.load_goals(SID)
        self.assertTrue(st["nodes"][ids["T"]]["cleared"], "the cleared card is cleared")
        self.assertFalse(st["nodes"][ids["D"]].get("cleared"), "the deliverable did NOT go with it")
        self.assertIsNone(st["nodes"][ids["D"]]["parentId"])
        jd.rollup_status(st, True)
        self.assertEqual(st["status"][ids["D"]], "completed", "…it has its own card in Completed")


if __name__ == "__main__":
    unittest.main()
