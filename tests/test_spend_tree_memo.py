#!/usr/bin/env python3
"""T401 follow-up (2026-09-13): the spend guard listed every alive session's subagents tree WHOLE on the pusher thread in the
boot's first cycle (4.2 s on one boot: 60 trees, 16,752 agent transcripts in 1,542 directories, the largest 2,581 files). The
guard's job skips the boot's first cycle, and the tree memo is persisted (STATE/spend-tree/<sid>.json, written when dirty and at
exit) and loaded lazily when the session's guard first runs, so a boot stats directories and lists nothing until one moves; a
corrupt memo relists; the reads are counted under memos.spendTree. Round two: the load saves the listings, and the one stat per
file that remains (an append while the kernel was down moves no directory's mtime) is spread over the cycles that follow,
hot first, at most SPEND_GUARD_RESTAT_PER_CYCLE a cycle; a memo naming another root or a foreign path is not trusted; the
directory is swept of memos whose leaf is gone; the exit's write retries a dump under the pusher's mutation. Synthetic trees only."""
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
        self.assertEqual(s2["fileStats"], 10, "every file is statted once after the load (ten here, under the per-cycle bound): %s" % s2)
        self.assertEqual(s2["entryStats"], 0, "and no listing's per-entry stats: %s" % s2)
        self.assertEqual(got, [self.leaf])
        self.assertNotIn("restat", km._SPEND_TREE_CACHE[self.leaf], "the spread re-stat is done")

    def _second_boot(self, full_age_s=600.0):
        """The first process lists and persists; the memo's full epoch is aged; the cache is the next process's (empty)."""
        far = time.time() + 10 ** 6
        self._window(far); km._persist_spend_trees(force=True); km._SPEND_TREE_CACHE.clear()
        p = km._spend_tree_path(self.leaf); d = json.loads(p.read_text()); d["full"] = time.time() - full_age_s; p.write_text(json.dumps(d))
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0

    def test_the_re_stat_after_a_load_is_spread_and_finds_a_file_appended_while_the_kernel_was_down(self):
        """Round two, MEDIUM: the loaded memo's full epoch was the previous kernel's last pass, so the first guard cycle
        after a restart statted every file at once (16,752 over 60 trees, the base's count). The re-stat is needed (an
        append moves no directory's mtime) but spread: at most SPEND_GUARD_RESTAT_PER_CYCLE files a cycle, hot first, the
        tree whole within ceil(files / N) cycles, and a file appended during the gap is found by then."""
        coldest = time.time() - 7200                                   # the file to be appended is the COLDEST the memo knows, so
        os.utime(self.files[7], (coldest, coldest))                    #  hot-first puts it last in the spread: found in the third cycle
        self._second_boot(full_age_s=600.0)                            #  (among equal stored mtimes the order is the listing's, which
        now = time.time(); os.utime(self.files[7], (now, now))        #  differs by filesystem: CI found it in the first cycle and then
        since = now - 100                                             #  statted it as hot in two more, 12 not 10; the count below is
        with mock.patch.object(km, "SPEND_GUARD_RESTAT_PER_CYCLE", 4):   #  exact only with the order pinned)
            got1 = km._spend_window_files(self.leaf, since, now=now)
            s1 = _stats()
            self.assertEqual(s1["fileStats"], 4, "the first cycle stats at most N files: %s" % s1)
            self.assertEqual(s1["listings"], 0, "and lists nothing: %s" % s1)
            self.assertEqual(len(km._SPEND_TREE_CACHE[self.leaf]["restat"]), 6, "six remain for the next cycles")
            self.assertEqual(km._SPEND_TREE_CACHE[self.leaf]["restat"][-1], self.files[7], "hot first: the coldest is last")
            self.assertNotIn(self.files[7], got1, "not found yet")
            for _ in range(2):                                        # ceil(10 / 4) = 3 cycles in all
                got = km._spend_window_files(self.leaf, since, now=now)
            s = _stats()
            self.assertEqual(s["fileStats"], 10, "every file statted once by the third cycle: %s" % s)
            self.assertNotIn("restat", km._SPEND_TREE_CACHE[self.leaf], "the spread is spent")
            self.assertIn(self.files[7], got, "the appended file is in the window by then")
            self.assertEqual(km._spend_window_files(self.leaf, since, now=now), got, "and a fourth cycle adds no stat beyond the hot one")
            self.assertEqual(_stats()["fileStats"], 11, "steady state: the one hot file (found, it is hot from then on): %s" % _stats())
        self.assertEqual(got1, [self.leaf])

    def test_a_memo_naming_another_root_is_a_failed_load_and_a_foreign_path_is_dropped(self):
        """Round two, lows 1 and 6: a shaped memo whose dirs do not name this session's root counted loaded and listed
        the tree whole, so the boot read could not tell a healthy load from a stale layout; and a shaped memo's paths were
        trusted wherever they pointed, so a corrupted memo keeping the root plus a foreign live path billed that file."""
        far = time.time() + 10 ** 6
        self._window(far); km._persist_spend_trees(force=True); km._SPEND_TREE_CACHE.clear()
        p = km._spend_tree_path(self.leaf); good = json.loads(p.read_text())
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0
        p.write_text(json.dumps({"dirs": {os.path.join(self.td, "elsewhere", "subagents"): 1.0}, "files": {}, "full": time.time()}))
        self._window(far)
        s = _stats()
        self.assertEqual((s["loaded"], s["loadFailed"], s["listings"]), (0, 1, 3), "another root: a failed load, relisted whole: %s" % s)
        km._SPEND_TREE_CACHE.clear()
        for k in km._SPEND_TREE_STATS:
            km._SPEND_TREE_STATS[k] = 0
        foreign = os.path.join(self.td, "foreign.jsonl"); Path(foreign).write_text("{}\n")
        now = time.time(); os.utime(foreign, (now, now))
        bad = dict(good); bad["files"] = dict(good["files"]); bad["files"][foreign] = now
        bad["dirs"] = dict(good["dirs"]); bad["dirs"][os.path.dirname(foreign)] = now
        p.write_text(json.dumps(bad))
        got = km._spend_window_files(self.leaf, now - 100, now=now)
        s = _stats()
        self.assertEqual(s["loaded"], 1, "the root is named, so the memo loads: %s" % s)
        self.assertNotIn(foreign, got, "a path outside the root is never billed to the session")
        self.assertNotIn(foreign, km._SPEND_TREE_CACHE[self.leaf]["files"])
        self.assertNotIn(os.path.dirname(foreign), km._SPEND_TREE_CACHE[self.leaf]["dirs"])

    def test_the_exits_write_retries_a_dump_the_pusher_moved_under_it(self):
        """Round two, low 2: the exit's memo write runs from the SIGTERM handler while the pusher may mutate the dicts, so
        json.dumps can raise RuntimeError past the except OSError and skip every later memo; the dump is retried."""
        far = time.time() + 10 ** 6
        self._window(far)
        real = json.dumps; calls = []
        def flaky(obj, *a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("dictionary changed size during iteration")
            return real(obj, *a, **k)
        with mock.patch.object(km.json, "dumps", flaky):
            n = km._persist_spend_trees(force=True)
        self.assertEqual(n, 1, "the memo was written on the retry")
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(km._spend_tree_path(self.leaf).read_text())["leaf"], self.leaf, "the memo names its leaf")

    def test_the_first_persist_sweeps_memos_whose_leaf_is_gone(self):
        """Round two, low 3: STATE/spend-tree had no reaper, so a memo outlived its session forever (0.73 MB for the largest
        tree); the first persist of a kernel life removes the memos whose leaf no longer exists, the checkpoint sweep's shape."""
        d = jd.STATE / km._SPEND_TREE_DIR; d.mkdir(parents=True)
        gone = os.path.join(self.proj, "22222222-2222-3333-4444-00000000b402.jsonl")
        (d / "22222222-2222-3333-4444-00000000b402.json").write_text(json.dumps({"leaf": gone, "dirs": {}, "files": {}, "full": 0}))
        (d / "33333333-2222-3333-4444-00000000b403.json").write_text(json.dumps({"dirs": {}, "files": {}, "full": 0}))   # no leaf named
        (d / "44444444-2222-3333-4444-00000000b404.json").write_text("{not json")
        far = time.time() + 10 ** 6
        self._window(far)
        with mock.patch.object(km, "_SPEND_TREE_SWEPT", [False]):
            km._persist_spend_trees(force=True)
            self.assertEqual(_stats()["swept"], 3, "the gone, the unnamed and the corrupt: %s" % _stats())
            self.assertEqual(sorted(x.name for x in d.glob("*.json")), [SID + ".json"], "the live session's memo stands")
            km._persist_spend_trees(force=True)
            self.assertEqual(_stats()["swept"], 3, "once per kernel life")

    def test_a_fresh_listing_counts_its_per_entry_stats(self):
        """Round two, low 5: a listing's per-entry stats (one per DirEntry) went uncounted, so a fresh listing reported
        listings 343, fileStats 0 while performing about 2,900 stats."""
        self._window(time.time() + 10 ** 6)
        s = _stats()
        self.assertEqual((s["listings"], s["entryStats"]), (3, 12), "ten files and two subdirectories: %s" % s)

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

    def test_the_perf_memos_carry_the_reads(self):
        rep = km._spend_tree_memo_report()
        self.assertEqual(set(rep), {"entries", "bytes", "bound", "dirStats", "fileStats", "entryStats", "listings", "loaded", "loadFailed",
                                    "written", "swept"})


class FirstCycleGate(unittest.TestCase):
    """The guard's job and the boot's first cycle, driven through whole pusher cycles (no tree fixture: this class must
    collect and run at a base that has no tree memo at all, so its red is the gate's absence and nothing else)."""

    def test_the_boots_first_cycle_carries_no_guard_listing(self):
        """Two whole pusher cycles with the cycle counter floored at zero: the guard ran zero times after cycle one and once
        after cycle two (round two, low 4: behavioural, not a source pin)."""
        calls = []
        saved_push = km._push_all
        km._push_all = lambda live_map=None: None
        self.addCleanup(setattr, km, "_push_all", saved_push)
        with mock.patch.object(km, "_spend_guard_tick", side_effect=lambda now, live_map: calls.append(now)), \
             mock.patch.dict(km._PERF_STATS.pusher, {"cycles": 0}):
            km._pusher_cycle()
            self.assertEqual(len(calls), 0, "the boot's first cycle runs no guard")
            self.assertEqual(km._PERF_STATS.pusher.get("cycles"), 1, "the cycle counted itself")
            km._pusher_cycle()
            self.assertEqual(len(calls), 1, "the second cycle runs it")
        import inspect
        self.assertIn("_persist_spend_trees(force=True)", inspect.getsource(km._drain_and_exit), "the memo is written at exit too")


if __name__ == "__main__":
    unittest.main()
