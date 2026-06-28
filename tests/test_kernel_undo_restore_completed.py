"""UndoClear of a COMPLETED card must bring it back COMPLETED — not flicker through "working"/"⏳ awaiting"
and vanish (the user 2026-06-27). rollup_status only keeps a top completed when it's `settled` or carries the
durable `settledDone` flag; a completed top that lacks settledDone, restored into an OPEN session that
re-focuses it, gets demoted to "working" by the re-roll and then picked up by build_feed's awaiting floor.
_restore_goal_archive now stamps settledDone on each restored completed TOP so completion is sticky. SYNTHETIC
fixtures only (placeholder ids)."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _run_restore(archive):
    """Drive _restore_goal_archive with in-memory goal-store accessors; return the resulting live store."""
    jd = km.jd
    live = {"nodes": {}, "status": {}}
    captured = {}
    orig = {n: getattr(jd, n) for n in ("load_goal_archive", "save_goal_archive", "load_goals", "save_goals")}
    jd.load_goal_archive = lambda sid: archive
    jd.save_goal_archive = lambda sid, a: None
    jd.load_goals = lambda sid: live
    jd.save_goals = lambda sid, s: captured.update(store=s)
    try:
        km._restore_goal_archive([SID + ":n1"])
    finally:
        for n, fn in orig.items():
            setattr(jd, n, fn)
    return captured.get("store", live)


class UndoRestoreCompleted(unittest.TestCase):
    def test_completed_top_comes_back_with_sticky_settledDone(self):
        iid = SID + ":n1"
        # an archived COMPLETED top that LACKS settledDone (the ≈5% gap) — the case that used to flicker
        archive = {"nodes": {iid: {"id": iid, "parentId": None, "nodeComplete": False, "text": "x"}},
                   "status": {iid: "completed"}}
        store = _run_restore(archive)
        self.assertIn(iid, store["nodes"], "the node is moved back to the live store")
        self.assertEqual(store["status"].get(iid), "completed", "its archived completed status is restored")
        self.assertTrue(store["nodes"][iid].get("settledDone"),
                        "a restored completed top is stamped settledDone so the re-roll keeps it completed")

    def test_explicit_nodeComplete_top_is_also_stamped(self):
        iid = SID + ":n1"
        archive = {"nodes": {iid: {"id": iid, "parentId": None, "nodeComplete": True, "text": "x"}},
                   "status": {iid: "completed"}}
        store = _run_restore(archive)
        self.assertTrue(store["nodes"][iid].get("settledDone"))

    def test_a_blocked_top_is_NOT_force_completed(self):
        iid = SID + ":n1"
        archive = {"nodes": {iid: {"id": iid, "parentId": None, "nodeComplete": False, "text": "x"}},
                   "status": {iid: "blocked"}}
        store = _run_restore(archive)
        self.assertFalse(store["nodes"][iid].get("settledDone"),
                         "a blocked/working top re-derives normally — never force-completed on restore")

    def test_undo_still_restores_then_unclears_in_order(self):
        # the fix lives in _restore_goal_archive, which _undo_clear calls BEFORE _mark_nodes_cleared(False)
        src = inspect.getsource(km._undo_clear)
        self.assertIn("_restore_goal_archive(restored)", src)
        self.assertIn("_mark_nodes_cleared(restored, False)", src)
        self.assertLess(src.index("_restore_goal_archive"), src.index("_mark_nodes_cleared"),
                        "restore FIRST so the un-clear re-roll finds the nodes (with settledDone) and holds completed")


if __name__ == "__main__":
    unittest.main()
