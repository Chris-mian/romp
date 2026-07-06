#!/usr/bin/env python3
"""The feed's "Move to Working" recategorize (the user 2026-07-06): user_move is a follow-up WITHOUT a
message — reopen/unblock the goal, stamp the followupAt evidence floor, plant the provisional stub when
the subtree is all-done — plus the _done_is_stale guard (a done verdict from evidence at/before the move
must not snap the card back to Completed) and the grouper's everDone guard REMOVAL (a reopened once-done
top is groupable again). All fixtures are SYNTHETIC (placeholder UUIDs)."""
import json
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
import os

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_usermove", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
G1 = SID + ":g1"
G2 = SID + ":g2"
G3 = SID + ":g3"
NOW = 1781100000


def node(nid, text, parent=None, done=False, blocked=False, **kw):
    nd = {"id": nid, "text": text, "parentId": parent, "nodeComplete": done,
          "blocked": blocked, "cleared": False, "trail": [], "t": NOW - 600, "mt": NOW - 300}
    nd.update(kw)
    return nd


class UserMoveBlocked(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _write(self, store):
        jd.save_goals(SID, store)

    def test_blocked_to_working_clears_descendant_block(self):
        # the block sits on a DESCENDANT (the planner blocked a sub) — _reopen alone wouldn't reach it
        store = {"rompUuid": SID, "seq": 2, "placements": {}, "status": {},
                 "nodes": {G1: node(G1, "Ship the feature", blocked=True, blockWhy="pick a name"),
                           G2: node(G2, "Decide the name", parent=G1, blocked=True)}}
        jd.rollup_status(store, False)
        self.assertEqual(store["status"][G1], "blocked")
        self._write(store)

        self.assertTrue(jd.user_move(SID, G1, now=NOW))
        st = jd.load_goals(SID)
        self.assertEqual(st["status"][G1], "working")
        self.assertFalse(st["nodes"][G1]["blocked"])
        self.assertFalse(st["nodes"][G2]["blocked"])
        self.assertEqual(st["nodes"][G1]["followupAt"], NOW)     # sort floor + staleness floor armed
        self.assertFalse(st["nodes"][G1].get("followupPending"))  # NO chip: nothing is in flight
        # an open sub exists, so no stub was needed
        self.assertFalse(any(n.get("provisional") for n in st["nodes"].values()))

    def test_completed_to_working_plants_stub_and_stays_working(self):
        # all children genuinely done → without the stub, bottom-up is_complete re-completes at once
        store = {"rompUuid": SID, "seq": 2, "placements": {}, "status": {},
                 "nodes": {G1: node(G1, "Build the exporter", done=True, settledDone=True,
                                    settledAt=NOW - 100, everDone=True),
                           G2: node(G2, "Write the writer", parent=G1, done=True)}}
        jd.rollup_status(store, True)
        self.assertEqual(store["status"][G1], "completed")
        self._write(store)

        self.assertTrue(jd.user_move(SID, G1, now=NOW))
        st = jd.load_goals(SID)
        self.assertEqual(st["status"][G1], "working")
        stubs = [n for n in st["nodes"].values() if n.get("provisional")]
        self.assertEqual(len(stubs), 1)
        self.assertEqual(stubs[0]["parentId"], G1)
        self.assertFalse(stubs[0]["nodeComplete"])
        # _reopen effects rode along: everDone provenance, settledAt → deltaSince for the delta re-distill
        self.assertTrue(st["nodes"][G1]["everDone"])
        self.assertNotIn("settledAt", st["nodes"][G1])
        self.assertEqual(st["nodes"][G1]["deltaSince"], NOW - 100)
        # a SECOND move must not stack a second stub
        self.assertTrue(jd.user_move(SID, G1, now=NOW + 5))
        st = jd.load_goals(SID)
        self.assertEqual(len([n for n in st["nodes"].values() if n.get("provisional")]), 1)

    def test_view_cleared_refused(self):
        store = {"rompUuid": SID, "seq": 1, "placements": {}, "status": {},
                 "nodes": {G1: node(G1, "Old thing", done=True)}}
        self._write(store)
        (Path(self.td) / "cleared.jsonl").write_text(json.dumps({"id": G1, "op": "clear"}) + "\n")
        self.assertFalse(jd.user_move(SID, G1, now=NOW))

    def test_missing_goal_refused(self):
        self._write({"rompUuid": SID, "seq": 0, "placements": {}, "status": {}, "nodes": {}})
        self.assertFalse(jd.user_move(SID, G1, now=NOW))


class StaleDoneGuard(unittest.TestCase):
    """A done verdict from evidence at/before the user's move is VOID; newer evidence completes normally."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _moved_store(self):
        store = {"rompUuid": SID, "seq": 2, "placements": {}, "status": {},
                 "nodes": {G1: node(G1, "Build the exporter", done=True),
                           G2: node(G2, "Write the writer", parent=G1, done=True)}}
        jd.rollup_status(store, True)
        jd.save_goals(SID, store)
        jd.user_move(SID, G1, now=NOW)
        return jd.load_goals(SID)

    def test_closer_stale_done_void_fresh_done_lands(self):
        store = self._moved_store()
        menu = [store["nodes"][G1]]
        # replayed verdict, evidence STRICTLY before the move → void
        self.assertEqual(jd.apply_close(store, menu, {"done": {1: "did it"}}, t=NOW - 30), [])
        self.assertFalse(store["nodes"][G1]["nodeComplete"])
        # genuinely newer evidence → completes normally (the floor, never a pin)
        self.assertEqual(jd.apply_close(store, menu, {"done": {1: "did it"}}, t=NOW + 60), [G1])
        self.assertTrue(store["nodes"][G1]["nodeComplete"])

    def test_done_at_exactly_the_stamp_lands(self):
        # the deliberate </<= asymmetry vs _block_is_stale (the user 2026-07-06): a nudge/follow-up's own
        # turn carries trigger t == followupAt, and its work RESOLVING the goal must land — with <= the
        # resolving turn voided itself and the card wedged in Working (the stuck 'drag' card).
        store = self._moved_store()
        menu = [store["nodes"][G1]]
        self.assertEqual(jd.apply_close(store, menu, {"done": {1: "did it"}}, t=NOW), [G1])
        self.assertTrue(store["nodes"][G1]["nodeComplete"])

    def test_planner_stale_done_void_fresh_done_lands(self):
        store = self._moved_store()
        menu = [{"id": G1, "text": "Build the exporter"}]
        ops = [{"do": "done", "goal": 1, "why": "already finished"}]
        jd.apply_plan(store, "seg-stale", NOW - 30, list(ops), menu, place_key="seg-stale")
        self.assertFalse(store["nodes"][G1]["nodeComplete"])
        jd.apply_plan(store, "seg-fresh", NOW + 60, list(ops), menu, place_key="seg-fresh")
        self.assertTrue(store["nodes"][G1]["nodeComplete"])

    def test_stale_block_still_void_too(self):
        # the same followupAt floor keeps guarding blocks (pre-existing behavior, same stamp)
        store = self._moved_store()
        menu = [store["nodes"][G1]]
        jd.apply_close(store, menu, {"block": {1: "waiting on you"}}, t=NOW)
        self.assertFalse(store["nodes"][G1]["blocked"])


class GrouperMovesEverDone(unittest.TestCase):
    """The never-move-an-everDone-node guard is REMOVED (the user 2026-07-06): a reopened once-done top
    is live work again, so the grouper may nest it — an erroneous split pushed back to Working re-merges."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_group_relinks_everdone_top(self):
        store = {"rompUuid": SID, "seq": 3, "placements": {}, "status": {},
                 "nodes": {G1: node(G1, "Fix the parser", everDone=True),   # reopened once-done top
                           G2: node(G2, "Parser rewrite umbrella"),
                           G3: node(G3, "Add parser tests")}}
        tops = [store["nodes"][G1], store["nodes"][G2], store["nodes"][G3]]
        ops = [{"do": "group", "goal": 1, "under": 2, "why": "same parser effort"}]
        self.assertEqual(jd.apply_group(store, tops, ops, NOW), 1)
        self.assertEqual(store["nodes"][G1]["parentId"], G2)


if __name__ == "__main__":
    unittest.main()
