#!/usr/bin/env python3
"""T401 follow-up (2026-09-13): the spend guard listed every alive session's subagents tree WHOLE on the pusher thread in the
boot's first cycle (4.2 s on one boot: 60 trees, 16,752 agent transcripts in 1,542 directories, the largest 2,581 files). The
guard's job skips the boot's first cycle, and the tree memo is persisted (STATE/spend-tree/<sid>.json, written when dirty and at
exit) and loaded lazily when the session's guard first runs, so a boot stats directories and lists nothing until one moves; a
corrupt memo relists; the reads are counted under memos.spendTree. Synthetic trees only."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_spend_guard import km, jd   # noqa: E402  the hermetic kernel

SID = "11111111-2222-3333-4444-00000000b401"


def _stats():
    return dict(km._SPEND_TREE_STATS)


class SpendTreeMemo(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(); self.proj = os.path.join(self.td, "proj"); os.makedirs(self.proj)
        self.leaf = os.path.join(self.proj, SID + ".jsonl"); Path(self.leaf).write_text("{}\n")
        self.sub = os.path.join(self.proj, SID, "subagents"); os.makedirs(os.path.join(self.sub, "workflows", "wf_1"))
        self.files = []
        for i in range(6):
            p = os.path.join(self.sub, "agent-%d.jsonl" % i); Path(p).write_text("{}\n"); self.files.append(p)
        for i in range(4):
            p = os.path.join(self.sub, "workflows", "wf_1", "step-%d.jsonl" % i); Path(p).write_text("{}\n"); self.files.append(p)
        old = time.time() - 3600
        for p in self.files + [self.sub, os.path.join(self.sub, "workflows"), os.path.join(self.sub, "workflows", "wf_1")]:
            os.utime(p, (old, old))
        self.saved_state = jd.STATE; jd._rebind_state(Path(tempfile.mkdtemp()))
        km._SPEND_TREE_CACHE.clear()
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0

    def tearDown(self):
        km._SPEND_TREE_CACHE.clear(); jd._rebind_state(self.saved_state)

    def _window(self, since):
        return km._spend_window_files(self.leaf, since, now=time.time())

    def test_a_boot_with_a_standing_memo_stats_directories_and_lists_no_file(self):
        """The first process lists the tree whole and persists the memo at exit; the next process loads it lazily at the
        session's first guard run and stats the three directories, no listing, no file stat for the cold files."""
        far = time.time() + 10 ** 6                               # a window in the future: every file is cold
        self._window(far)
        s1 = _stats(); self.assertEqual(s1["listings"], 3, "the first process listed the tree: %s" % s1)
        self.assertEqual(km._persist_spend_trees(force=True), 1)
        self.assertTrue(km._spend_tree_path(self.leaf).exists())
        km._SPEND_TREE_CACHE.clear()                              # the next process
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0
        got = self._window(far)
        s2 = _stats()
        self.assertEqual(s2["loaded"], 1, s2)
        self.assertEqual(s2["listings"], 0, "a standing memo lists no file: %s" % s2)
        self.assertEqual(s2["dirStats"], 3, "one stat per directory: %s" % s2)
        self.assertEqual(s2["fileStats"], 0, "cold files are not statted at the boot: %s" % s2)
        self.assertEqual(got, [self.leaf])

    def test_a_directory_whose_mtime_moved_is_relisted_alone(self):
        far = time.time() + 10 ** 6
        self._window(far); km._persist_spend_trees(force=True); km._SPEND_TREE_CACHE.clear()
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0
        Path(os.path.join(self.sub, "workflows", "wf_1", "step-9.jsonl")).write_text("{}\n")   # the deepest directory moves
        self._window(far)
        s = _stats()
        self.assertEqual(s["listings"], 1, "the moved directory alone was relisted: %s" % s)
        self.assertIn(os.path.join(self.sub, "workflows", "wf_1", "step-9.jsonl"), km._SPEND_TREE_CACHE[self.leaf]["files"])

    def test_a_corrupt_memo_relists_and_is_counted(self):
        far = time.time() + 10 ** 6
        self._window(far); km._persist_spend_trees(force=True); km._SPEND_TREE_CACHE.clear()
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0
        km._spend_tree_path(self.leaf).write_text("{not json")
        self._window(far)
        s = _stats()
        self.assertEqual((s["loadFailed"], s["listings"]), (1, 3), "a corrupt memo is relisted whole, never raised: %s" % s)
        km._spend_tree_path(self.leaf).write_text(json.dumps({"dirs": {"x": "not a number"}, "files": {}}))
        km._SPEND_TREE_CACHE.clear(); self._window(far)
        self.assertEqual(_stats()["loadFailed"], 2, "a misshapen memo too")

    def test_the_boots_first_cycle_carries_no_guard_listing(self):
        calls = []
        saved = (km._PERF_STATS.pusher.get("cycles", 0),)
        with mock.patch.object(km, "_spend_guard_tick", side_effect=lambda now, live_map: calls.append(now)), \
             mock.patch.dict(km._PERF_STATS.pusher, {"cycles": 0}):
            src = None
            import inspect
            src = inspect.getsource(km._pusher_cycle_jobs)
        self.assertIn('if _PERF_STATS.pusher.get("cycles", 0) >= 1:', src, "the guard's job is gated on a completed cycle")
        self.assertIn("_job_stage('spendGuard'", src)
        self.assertIn("_job_stage('persistSpendTrees'", src, "the memo is written when dirty each cycle")
        import inspect
        self.assertIn("_persist_spend_trees(force=True)", inspect.getsource(km._drain_and_exit), "and at exit")
        self.assertEqual(saved[0], km._PERF_STATS.pusher.get("cycles", 0))

    def test_the_perf_memos_carry_the_reads(self):
        rep = km._spend_tree_memo_report()
        self.assertEqual(set(rep), {"entries", "bytes", "bound", "dirStats", "fileStats", "listings", "loaded", "loadFailed", "written"})


if __name__ == "__main__":
    unittest.main()
