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
        self.saved_state = km.jd.STATE; root = Path(tempfile.mkdtemp()); km.jd._rebind_state(root)
        (root / "session-hosts").write_text("off\n")                     # a fresh state root pins the hosts off (the 2026-09-11 rule)
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
        k = self._key(); self.assertEqual(len(k), 6, "the transcript's stat, the cut pair, the SDK registry row's stat")
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK[SID] = list(k) + [777, 888]
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
            row = list(km._INTR_MARKS_DISK[SID]); self.assertEqual(row[6:], [1200, 1000]); self.assertTrue(km._INTR_MARKS_DISK_DIRTY[0])
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
        good = [1, 2, 0.0, "", 0, 0, 5, 6]
        p.write_text(json.dumps({"v": 2, "rows": {SID: good, "not-a-uuid": good, "22222222-2222-4333-8444-0000000000c4": [1, 2, 3],
                                                  "33333333-2222-4333-8444-0000000000c5": ["x", 2, 0.0, "", 0, 0, 5, 6]}}))
        s0 = _stats()
        self.assertEqual(km._load_intr_marks(), 1, "one row trusted")
        self.assertEqual(_stats()["refused"] - s0["refused"], 3, "the non-uuid sid, the short row and the mistyped row refused")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertEqual(km._INTR_MARKS_DISK, {SID: good})
        p.write_text(json.dumps({"v": 1, "rows": {SID: [1, 2, 0.0, "", 5, 6]}}))
        with km._INTR_MARKS_DISK_LOCK:
            km._INTR_MARKS_DISK.clear()
        self.assertEqual(km._load_intr_marks(), 0, "a v1 file (the six-element rows): nothing trusted")
        p.write_text("{not json"); self.assertEqual(km._load_intr_marks(), 0, "a torn file: an empty memo, no raise")

    def test_the_file_is_written_only_on_change_under_a_per_writer_tmp_and_a_failed_replace_leaves_no_tmp(self):
        turns = _turns(_user(1000, "hello"))
        km._interrupt_marks(turns, SID, "judge", path=self.path)
        self.assertTrue(km._persist_intr_marks(), "a changed row: written")
        self.assertFalse(km._persist_intr_marks(), "nothing changed since: not written")
        km._intr_marks_memo.clear()
        km._interrupt_marks(turns, SID, "judge", path=self.path)           # the same result under the same key: no change
        self.assertFalse(km._persist_intr_marks(), "the same row again is not a change")
        d = json.loads(km._intr_marks_path().read_text()); self.assertEqual(d["v"], 2); self.assertEqual(len(d["rows"][SID]), 8)
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

    def test_an_armed_rollback_cut_takes_no_key_and_the_sdk_registry_row_is_keyed(self):
        """Round two, medium 3: the key omitted two live inputs of the judge parse: the armed bare-rollback cut (read live, no file)
        and sdk_human (the SDK registry row). Arm, evaluate, clear, evaluate: the second evaluation tallies again and nothing was
        served or persisted from the armed world; the registry row's arrival moves the key."""
        turns = _turns(_user(1000, "hello"))
        saved = km.jd._PENDING_CUT_FN
        km.jd.set_pending_cut_provider(lambda fsid: "cccccccc-2222-4333-8444-0000000000c9" if fsid == SID else "")
        try:
            self.assertIsNone(self._key(), "an armed cut: no key")
            s0 = _stats()
            self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (0, 1000))
            with km._INTR_MARKS_DISK_LOCK:
                self.assertNotIn(SID, km._INTR_MARKS_DISK, "nothing persisted from the armed world")
            self.assertEqual(_stats()["restored"] - s0["restored"], 0)
        finally:
            km.jd.set_pending_cut_provider(saved)
        km._intr_marks_memo.clear()
        s1 = _stats()
        self.assertEqual(km._interrupt_marks(turns, SID, "judge", path=self.path), (0, 1000))
        self.assertEqual(_stats()["miss"] - s1["miss"], 1, "cleared: the evaluation tallies again, then persists")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertIn(SID, km._INTR_MARKS_DISK)
        km._intr_marks_memo.clear()
        reg = km.jd.STATE / "sdk" / (SID + ".json"); reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps({"sid": SID, "alive": True}))                # the registry row arrives: sdk_human flips
        s2 = _stats()
        km._interrupt_marks(turns, SID, "judge", path=self.path)
        self.assertEqual((_stats()["miss"] - s2["miss"], _stats()["restored"] - s2["restored"]), (1, 0), "the registry row is keyed")

    def test_without_a_path_the_tally_runs_and_nothing_is_persisted(self):
        turns = _turns(_user(1000, "hello"))
        self.assertEqual(km._interrupt_marks(turns, SID, "display"), (0, 1000), "the display family: no path, no row")
        with km._INTR_MARKS_DISK_LOCK:
            self.assertNotIn(SID, km._INTR_MARKS_DISK)


class RowTallyEqualsAtomTally(TA.Harness):
    """The tally over the pre-cut container's light facts equals the tally over built atoms on every golden, and builds no
    atom but the romp notices; the cold cost is linear in the rows."""

    def test_every_golden_agrees_and_the_lazy_road_builds_no_atom_but_a_notice(self):
        lazy_seen = []
        for name in sorted(TA.G.SINGLE_FILE):
            with self.subTest(scenario=name):
                records, sent = TA.G.SINGLE_FILE[name]
                path = self.write(name, records(), sent=sent)
                whole = self.cold(path)
                atoms_all = [a for t in whole["turns"] for a in (t.get("atoms") or [])]
                want = km._interrupt_marks_atoms(atoms_all, 0.0, "")
                self.fresh(); self.parse(path); self.doc(path)            # the document, written from the whole parse's tree
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
                    lazy_seen.append(name)
        self.assertGreater(len(lazy_seen), 0, "the compacting goldens restore lazily: %r" % lazy_seen)

    def test_every_user_row_of_every_golden_document_agrees_field_by_field(self):
        """Round two, medium 1: the maxima can agree while a row's fields do not; every user row of every golden document is
        compared field by field, the light facts against the built atom: type, t, author and the interrupt flag."""
        rows = mism = 0
        for name in sorted(TA.G.SINGLE_FILE):
            records, sent = TA.G.SINGLE_FILE[name]
            path = self.write(name, records(), sent=sent)
            self.fresh(); self.parse(path); self.doc(path); self.fresh(); tree = self.parse(path)
            for t in tree["turns"]:
                atoms = t.get("atoms")
                if not isinstance(atoms, em.LazyAtoms):
                    continue
                for i, f in atoms.user_facts():
                    if f.get("_light") is None:
                        continue
                    a = atoms[i]; rows += 1
                    got = (f.get("type"), f.get("t"), f.get("author", ""), em.is_interrupt_record(f))
                    want = (a.get("type"), a.get("t"), a.get("author", ""), em.is_interrupt_record(a))
                    if got != want:
                        mism += 1
        self.assertGreater(rows, 0, "the goldens carry lazy user rows")
        self.assertEqual(mism, 0, "%d of %d user rows differ between the light facts and the built atom" % (mism, rows))

    def test_a_stop_between_a_queued_prompts_send_and_its_landing_agrees(self):
        """The shape medium 1 named: an absorbed queued prompt carries its LANDING time in the scalars and its SEND time in the
        record row; a stop between the two must read the same on both roads (the landing wins, so the stop is older)."""
        records = [("r0", "u", 1000, {"type": "user", "author": "human", "t": 1000}, None),
                   ("r1", "u", 1100, {"type": "user", "author": "human", "t": 1100}, {"ir": True}),
                   ("r2", "u", 1050, {"type": "user", "author": "human", "t": 1200}, None)]   # sent at 1050, landed at 1200
        recs = [[u, None, kind, None, i, t, 0, None, None, None] for i, (u, kind, t, sc, lz) in enumerate(records)]
        rows = []
        for i, (u, kind, t, sc, lz) in enumerate(records):
            row = {"r": i, "s": dict(sc), "seq": i}
            if lz: row["lz"] = dict(lz, k="user", h="00000000", nt=True); row["i"] = i   # a lazy row names its body's index
            rows.append(row)
        index = em.LazyIndex({"atoms": rows, "records": recs, "fsids": []}, SID, self.td / "x.jsonl")
        atoms = em.LazyAtoms(index, range(len(rows)))
        facts = km._interrupt_marks_atoms(km._interrupt_marks_facts([{"id": "t1", "t": 1000, "atoms": atoms}]), 0.0, "")
        built = km._interrupt_marks_atoms([atoms[i] for i in range(len(rows))], 0.0, "")
        self.assertEqual(facts, built); self.assertEqual(built, (1100, 1200), "the stop at 1100 and the LANDING at 1200, not the send at 1050")
        self.assertLess(built[0], built[1], "the landing time outranks the stop, so a reader finds the stop older than the last prompt")

    def test_the_cold_tally_over_the_lazy_road_is_linear_in_the_rows_and_builds_nothing(self):
        """Round two, low 2: the linearity test drove plain dicts; a restored LazyIndex is the road the change is about."""
        def lazy(n):
            recs = [[("u%d" % i), None, "u" if i % 2 == 0 else "a", None, i, 1000 + i, 0, None, None, None] for i in range(n)]
            rows = [{"r": i, "s": {"type": "user" if i % 2 == 0 else "assistant", "author": "human" if i % 2 == 0 else None, "t": 1000 + i}, "seq": i}
                    for i in range(n)]
            index = em.LazyIndex({"atoms": rows, "records": recs, "fsids": []}, SID, self.td / "y.jsonl")
            return [{"id": "t1", "t": 1000, "atoms": em.LazyAtoms(index, range(n))}]
        m0 = em._ASM_INDEX_STATS["materialized"]
        t0 = time.perf_counter(); r1 = km._interrupt_marks_atoms(km._interrupt_marks_facts(lazy(4000)), 0.0, ""); dt1 = time.perf_counter() - t0
        t0 = time.perf_counter(); r4 = km._interrupt_marks_atoms(km._interrupt_marks_facts(lazy(16000)), 0.0, ""); dt4 = time.perf_counter() - t0
        self.assertEqual(em._ASM_INDEX_STATS["materialized"], m0, "no atom built over 20,000 lazy rows")
        self.assertEqual((r1, r4), ((0, 4998), (0, 16998)))
        self.assertLess(dt4 / max(dt1, 1e-6), 8.0, "four times the rows under eight times the time on the lazy road (%.3f vs %.3f s)" % (dt1, dt4))
        self.assertLess(dt4, 2.0)


if __name__ == "__main__":
    unittest.main()
