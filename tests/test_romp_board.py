#!/usr/bin/env python3
"""Tests for bin/romp-board — the independent terminal mirror of the dashboard feed. The point of the
tool is to re-implement the rollup separately from romp-judge, so these tests pin THAT math directly:
a buried blocked leaf flips a top to BLOCKED (the reported bug), a complete subtree heals a stale leaf
block, and the settled gate / cleared filter behave. Synthetic stores only: placeholder UUIDs, invented
text — no real session data.
"""
import json
import os
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
board = SourceFileLoader("romp_board", os.path.join(BIN, "romp-board")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def store(nodes, last=None):
    """A goal store from a compact node spec: {id: (text, parentId, complete, blocked, cleared)}."""
    nd = {}
    for nid, (text, parent, comp, blk, clr) in nodes.items():
        nd[nid] = {"id": nid, "text": text, "parentId": parent, "nodeComplete": comp,
                   "blocked": blk, "cleared": clr, "t": 0}
    return {"rompUuid": SID, "nodes": nd, "status": {}, "lastNode": last}


class RollupTest(unittest.TestCase):
    def test_buried_blocked_leaf_floors_top_to_blocked(self):
        # top -> childA(done) -> grandchild(blocked, incomplete): the exact reported pathology — the
        # visible early sub-goal is done, but a deep block pins the whole goal under BLOCKED.
        s = store({
            "top": ("Ship feature", None, False, False, False),
            "a":   ("Done part", "top", True, False, False),
            "b":   ("Other part", "top", False, False, False),
            "g":   ("waiting on user", "b", False, True, False),
        }, last="top")
        # lastNode=top makes top the focus → not settled, but blocked precedence wins regardless.
        self.assertEqual(board.classify_store(s, session_closed=True)["top"], "blocked")

    def test_complete_subtree_heals_a_stale_leaf_block(self):
        # a block inside an otherwise-complete subtree is moot — the top must NOT read blocked.
        s = store({
            "top": ("Small ask", None, True, False, False),
            "a":   ("step", "top", True, True, False),     # nodeComplete wins, leftover block ignored
        }, last="other")
        self.assertEqual(board.classify_store(s, session_closed=True)["top"], "completed")

    def test_settled_gate_holds_in_focus_complete_goal_working(self):
        s = store({"top": ("Focus goal", None, True, False, False)}, last="top")
        # still the active focus and session alive → working (no premature completed flicker)
        self.assertEqual(board.classify_store(s, session_closed=False)["top"], "working")
        # once settled (session closed) → completed
        self.assertEqual(board.classify_store(s, session_closed=True)["top"], "completed")

    def test_bottom_up_completion(self):
        s = store({
            "top": ("Umbrella", None, False, False, False),
            "a":   ("only child", "top", True, False, False),
        }, last="other")
        self.assertEqual(board.classify_store(s, session_closed=True)["top"], "completed")

    def test_permission_floor(self):
        s = store({"top": ("Active work", None, False, False, False)}, last="top")
        self.assertEqual(board.classify_store(s, session_closed=False, perm_floor=True)["top"], "blocked")

    def test_cleared_node_status(self):
        s = store({"top": ("Dropped", None, False, False, True)}, last="top")
        self.assertEqual(board.classify_store(s, session_closed=False)["top"], "cleared")


class ClearedReplayTest(unittest.TestCase):
    def test_newest_op_wins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            st = Path(d)
            (st / "cleared.jsonl").write_text(
                json.dumps({"id": "x", "t": 1, "op": "clear"}) + "\n"
                + json.dumps({"id": "y", "t": 2, "op": "clear"}) + "\n"
                + json.dumps({"id": "x", "t": 3, "op": "undo"}) + "\n")
            self.assertEqual(board.cleared_ids(st), {"y"})


class BuildBoardTest(unittest.TestCase):
    def setUp(self):
        self._tmux = board.tmux_sessions
        board.tmux_sessions = lambda: {}      # empty tmux → every store treated alive (kernel fallback)

    def tearDown(self):
        board.tmux_sessions = self._tmux

    def _state(self, d, stores, cleared=()):
        st = Path(d)
        (st / "goals").mkdir(parents=True)
        for sid, s in stores.items():
            (st / "goals" / (sid + ".json")).write_text(json.dumps(s))
        if cleared:
            (st / "cleared.jsonl").write_text("".join(
                json.dumps({"id": c, "t": 1, "op": "clear"}) + "\n" for c in cleared))
        return st

    def test_buckets_and_cleared_card_hidden(self):
        import tempfile
        s = store({
            "top": ("Blocked goal", None, False, False, False),
            "g":   ("needs you", "top", False, True, False),
            "done": ("Finished goal", None, True, False, False),
            "drop": ("Cleared goal", None, False, False, False),
        }, last="other")
        with tempfile.TemporaryDirectory() as d:
            st = self._state(d, {SID: s}, cleared=["drop"])
            rows = board.build_board(st)
            self.assertEqual(len(rows), 1)
            by = rows[0]["status"]
            self.assertEqual(by.get("top"), "blocked")
            self.assertEqual(by.get("done"), "completed")
            # render() shows the column labels, hides the cleared card, and always carries raw flags
            out = board.render(rows, board.Style(False))
            self.assertIn("BLOCKED", out)
            self.assertIn("Blocked goal", out)
            self.assertNotIn("Cleared goal", out)     # cleared card filtered out of the render
            self.assertIn("[c=", out)                 # raw flags are always on now


if __name__ == "__main__":
    unittest.main()
