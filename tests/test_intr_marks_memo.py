#!/usr/bin/env python3
"""T401 (3) target 3 (2026-09-13): the interrupt marks (the newest genuine user stop and the newest human prompt) were tallied
by iterating every atom of a session's transcript, which built every pre-cut atom of the assembly (fourteen consecutive stack
samples on one session at a boot). The tally now reads the pre-cut container's light facts and builds only the romp notices a
stop's classification reads, and a memo persisted at STATE/intr-marks.json, keyed on the transcript's stat and the states log's
machine-cut pair taken before any row is read, serves the two maxima across boots. Synthetic fixtures only."""
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
import sys
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import test_asm_checkpoint as TA   # noqa: E402  the hermetic kernel, the goldens and the checkpoint harness

em = TA.em
km = TA.kernel_module()
SID = "11111111-2222-4333-8444-0000000000c3"          # this module's own synthetic sid


def _stats():
    d = dict(km._intr_marks_memo_report())
    with km._INTR_MARKS_STATS_LOCK:
        d["computeMs"] = float(km._intr_marks_memo_stats.get("computeMs", 0.0))   # the raw sum: /perf rounds it to whole ms
    return d


def _turns(*atoms):
    return [{"id": "t1", "t": 1000, "atoms": list(atoms)}]


def _user(t, text, author="human"):
    return {"type": "user", "author": author, "t": t, "uuid": "u%d" % t, "message": {"role": "user", "content": text}}


class MarksMemo(unittest.TestCase):
    def setUp(self):
        with km._INTR_MARKS_DISK_LOCK:                                    # before the state rebind: a kernel without the memo fails here
            km._INTR_MARKS_DISK.clear(); km._INTR_MARKS_DISK_DIRTY[0] = False
        km._intr_marks_memo.clear()
        self.saved_state = km.jd.STATE; km.jd._rebind_state(Path(tempfile.mkdtemp()))
        self.d = tempfile.mkdtemp(); self.path = os.path.join(self.d, SID + ".jsonl"); Path(self.path).write_text("{}\n")
        km._machine_cut_cache.clear() if isinstance(getattr(km, "_machine_cut_cache", None), dict) else None

    def tearDown(self):
        km.jd._rebind_state(self.saved_state)
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK.clear(); km._INTR_MARKS_DISK_DIRTY[0] = False
        km._intr_marks_memo.clear()

    def _key(self):
        return km._intr_marks_key(SID, self.path)

    def test_a_persisted_row_under_a_standing_key_serves_the_marks_without_a_tally(self):
        k = self._key(); self.assertEqual(len(k), 4)
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK[SID] = [k[0], k[1], k[2], k[3], 777, 888]
        s0 = _stats(); m0 = em._ASM_INDEX_STATS["materialized"]
        turns = _turns(_user(1000, "hello"))
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (777, 888), "the persisted maxima, exact")
        s1 = _stats()
        self.assertEqual((s1["restored"] - s0["restored"], s1["computeMs"] - s0["computeMs"]), (1, 0.0), "restored, no tally")
        self.assertEqual(em._ASM_INDEX_STATS["materialized"], m0)
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (777, 888))
        self.assertEqual(_stats()["hit"] - s1["hit"], 1, "the warm cycle is the identity memo's hit")

    def test_an_appended_transcript_a_same_size_rewrite_and_a_new_cut_row_each_bust_the_row(self):
        turns = _turns(_user(1000, "hello"), _user(1200, "[Request interrupted by user]"))
        s0 = _stats()
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (1200, 1000))
        s1 = _stats(); self.assertEqual(s1["miss"] - s0["miss"], 1); self.assertGreater(s1["computeMs"], s0["computeMs"])
        with km._INTR_MARKS_DISK_LOCK:
            row = list(km._INTR_MARKS_DISK[SID]); self.assertEqual(row[4:], [1200, 1000]); self.assertTrue(km._INTR_MARKS_DISK_DIRTY[0])
        km._intr_marks_memo.clear()                                        # a new parse object: the identity memo misses
        with open(self.path, "a") as f:
            f.write("{}\n")                                                # appended: size moves
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (1200, 1000))
        s2 = _stats(); self.assertEqual((s2["miss"] - s1["miss"], s2["restored"] - s1["restored"]), (1, 0), "the row did not serve")
        km._intr_marks_memo.clear()
        st = os.stat(self.path); Path(self.path).write_bytes(b"x" * st.st_size)   # same size, other bytes
        os.utime(self.path, ns=(st.st_mtime_ns + 1_000_000, st.st_mtime_ns + 1_000_000))
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (1200, 1000))
        s3 = _stats(); self.assertEqual((s3["miss"] - s2["miss"], s3["restored"] - s2["restored"]), (1, 0), "mtime_ns busts a same-size rewrite")
        km._intr_marks_memo.clear()
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (1200, 1000))
        s4 = _stats(); self.assertEqual(s4["restored"] - s3["restored"], 1, "nothing moved: the row serves")
        km._intr_marks_memo.clear()
        d = km.jd.STATE / "states"; d.mkdir(parents=True, exist_ok=True)
        with open(d / (SID + ".jsonl"), "a") as f:
            f.write(json.dumps({"state": "waiting", "t": 1250, "machineCut": "restart"}) + "\n")   # a new cut row
        km._machine_cut_cache.clear() if isinstance(getattr(km, "_machine_cut_cache", None), dict) else None
        res = km._interrupt_marks(turns, SID, "judge", path=self.path)
        s5 = _stats(); self.assertEqual((s5["miss"] - s4["miss"], s5["restored"] - s4["restored"]), (1, 0), "a new cut pair busts the row")
        self.assertEqual(res, (0, 1000), "the stop at or before the cut is the machine's, so no user stop stands")

    def test_the_key_is_taken_before_any_row_is_read(self):
        import inspect
        src = inspect.getsource(km._interrupt_marks)
        self.assertLess(src.index("_intr_marks_key(sid, path)"), src.index("_interrupt_marks_facts(turns)"), "key first, then the rows")
        self.assertIn("KEY FIRST", src)

    def test_malformed_persisted_rows_are_refused_and_good_ones_loaded(self):
        p = km._intr_marks_path(); p.parent.mkdir(parents=True, exist_ok=True)
        good = [1, 2, 0.0, "", 5, 6]
        p.write_text(json.dumps({"v": 1, "rows": {SID: good, "not-a-uuid": good, "22222222-2222-4333-8444-0000000000c4": [1, 2, 3],
                                                  "33333333-2222-4333-8444-0000000000c5": ["x", 2, 0.0, "", 5, 6]}}))
        s0 = _stats()
        self.assertEqual(km._load_intr_marks(), 1, "one row trusted")
        self.assertEqual(_stats()["refused"] - s0["refused"], 3, "the non-uuid sid, the short row and the mistyped row refused")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertEqual(km._INTR_MARKS_DISK, {SID: good})
        p.write_text(json.dumps({"v": 99, "rows": {SID: good}}))
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK.clear()
        self.assertEqual(km._load_intr_marks(), 0, "another version: nothing trusted")
        p.write_text("{not json"); self.assertEqual(km._load_intr_marks(), 0, "a torn file: an empty memo, no raise")

    def test_the_file_is_written_only_on_change_under_a_per_writer_tmp_and_a_failed_replace_leaves_no_tmp(self):
        turns = _turns(_user(1000, "hello"))
        km._interrupt_marks(turns, SID, "judge", path=self.path)
        self.assertTrue(km._persist_intr_marks(), "a changed row: written")
        self.assertFalse(km._persist_intr_marks(), "nothing changed since: not written")
        km._intr_marks_memo.clear()
        km._interrupt_marks(turns, SID, "judge", path=self.path)           # the same result under the same key: no change
        self.assertFalse(km._persist_intr_marks(), "the same row again is not a change")
        d = json.loads(km._intr_marks_path().read_text()); self.assertEqual(d["v"], 1); self.assertIn(SID, d["rows"])
        import inspect
        self.assertIn('".tmp.%d.%x" % (os.getpid(), threading.get_ident())', inspect.getsource(km._persist_intr_marks), "a per-writer tmp")
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK_DIRTY[0] = True
        with mock.patch.object(km.os, "replace", side_effect=OSError("EACCES")):
            self.assertFalse(km._persist_intr_marks())
        self.assertEqual([x.name for x in km._intr_marks_path().parent.glob("*.tmp.*")], [], "no tmp left behind")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertTrue(km._INTR_MARKS_DISK_DIRTY[0], "still dirty: retried by the next persist")

    def test_the_forget_road_drops_the_persisted_rows_of_sessions_that_left_the_alive_set(self):
        km._interrupt_marks(_turns(_user(1000, "hello")), SID, "judge", path=self.path)
        km._persist_intr_marks()
        km._intr_marks_forget(set())
        with km._INTR_MARKS_DISK_LOCK:
            self.assertNotIn(SID, km._INTR_MARKS_DISK); self.assertTrue(km._INTR_MARKS_DISK_DIRTY[0])
        self.assertIn("persisted", _stats())

    def test_without_a_path_the_tally_runs_and_nothing_is_persisted(self):
        turns = _turns(_user(1000, "hello"))
        self.assertEqual(km._interrupt_marks(turns, SID, "display"), (0, 1000), "the display family: no path, no row")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertNotIn(SID, km._INTR_MARKS_DISK)


class RowTallyEqualsAtomTally(TA.Harness):
    """The tally over the pre-cut container's light facts equals the tally over built atoms on every golden, and builds no
    atom but the romp notices; the cold cost is linear in the rows."""

    def test_every_golden_agrees_and_the_lazy_road_builds_no_atom_but_a_notice(self):
        for name in sorted(TA.G.SINGLE_FILE):
            with self.subTest(scenario=name):
                records, sent = TA.G.SINGLE_FILE[name]
                path = self.write(name, records(), sent=sent)
                whole = self.cold(path)
                atoms_all = [a for t in whole["turns"] for a in (t.get("atoms") or [])]
                want = km._interrupt_marks_atoms(atoms_all, 0.0, "")
                self.fresh(); self.parse(path)                             # the document
                self.fresh(); modes = []; tree = self.parse(path, modes)   # restored: lazy pre-cut atoms
                m0 = em._ASM_INDEX_STATS["materialized"]
                users = km._interrupt_marks_facts(tree["turns"])
                got = km._interrupt_marks_atoms(users, 0.0, "")
                self.assertEqual(got, want, "%s: the row tally equals the atom tally" % name)
                romp_rows = sum(1 for a in users if a.get("author") == "romp")
                self.assertLessEqual(em._ASM_INDEX_STATS["materialized"] - m0, romp_rows,
                                     "%s: no atom built but the romp notices (%d)" % (name, romp_rows))
                if modes == ["restore"]:
                    self.assertTrue(any(isinstance(t.get("atoms"), em.LazyAtoms) for t in tree["turns"]), "%s: a lazy turn was exercised" % name)

    def test_the_cold_tally_is_linear_in_the_rows(self):
        def n_turns(n):
            return [{"id": "t%d" % i, "t": 1000 + i, "atoms": [_user(1000 + i, "prompt %d" % i), {"type": "assistant", "t": 1000 + i, "uuid": "a%d" % i}]} for i in range(n)]
        t0 = time.perf_counter(); km._interrupt_marks_atoms(km._interrupt_marks_facts(n_turns(2000)), 0.0, ""); dt1 = time.perf_counter() - t0
        t0 = time.perf_counter(); km._interrupt_marks_atoms(km._interrupt_marks_facts(n_turns(8000)), 0.0, ""); dt4 = time.perf_counter() - t0
        self.assertLess(dt4, max(0.5, dt1 * 16), "four times the rows in well under sixteen times the time, no bodies built (%.3f vs %.3f s)" % (dt1, dt4))
        self.assertLess(dt4, 1.0, "8,000 turns tallied in under a second")


if __name__ == "__main__":
    unittest.main()
