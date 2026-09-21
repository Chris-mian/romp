#!/usr/bin/env python3
"""The death marker's readers: the ghost epoch, the pending drain, and the one-shot finalize
(cluster D of the stuck-card program, 2026-08-13). All fixtures synthetic."""
import json
import os
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
jd = load_source("romp_judge_death", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_death2", os.path.join(BIN, "romp-kernel"))

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"


def _write_marker(sid, **m):
    jd.GONEDIR.mkdir(parents=True, exist_ok=True)
    (jd.GONEDIR / (sid + ".json")).write_text(json.dumps(m))
    jd._gone_memo.pop(sid, None)


def _wipe(sid):
    for p in (jd.GONEDIR / (sid + ".json"), jd.STATESDIR / (sid + ".jsonl"),
              jd.SDKDIR / (sid + ".json"), jd.EPIDIR / (sid + ".jsonl")):
        try:
            p.unlink()
        except OSError:
            pass
    for mod in (jd, km.jd):                            # BOTH judge instances share the state dir; a
        mod._gone_memo.pop(sid, None)                  # deleted-then-recreated file within one mtime
        mod._episode_memo.pop(sid, None)               # tick would otherwise serve a stale memo
        mod._UNREADABLE_LOGGED.discard(str(mod.STATESDIR / (sid + ".jsonl")))   # a read-failure episode ends with the file


def _store(status=None, nodes=None):
    return {"rompUuid": SID, "seq": 1, "placements": {},
            "status": status or {}, "nodes": nodes or {}}


class CliEpoch(unittest.TestCase):
    def tearDown(self):
        _wipe(SID)

    def test_reg_only_marker_only_and_max(self):
        self.assertIsNone(jd._cli_epoch(SID), "neither source → None, today's behavior byte-for-byte")
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"spawnedAt": NOW}))
        self.assertEqual(jd._cli_epoch(SID), NOW)
        _write_marker(SID, t=NOW + 50, by="kill")
        self.assertEqual(jd._cli_epoch(SID), NOW + 50, "a death after the spawn lifts the floor")
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"spawnedAt": NOW + 100}))
        self.assertEqual(jd._cli_epoch(SID), NOW + 100, "a revival's fresh CLI lifts it back")


class DeathPending(unittest.TestCase):
    def tearDown(self):
        for i in range(12):
            _wipe(SID[:-2] + "%02d" % i)

    def _sid(self, i):
        return SID[:-2] + "%02d" % i

    def test_unfinalized_markers_drain_oldest_first_bounded_and_deduped(self):
        import time as _t
        for i in range(9):
            _write_marker(self._sid(i), t=NOW + i, by="boot")
            os.utime(jd.GONEDIR / (self._sid(i) + ".json"), (NOW + i, NOW + i))
        _write_marker(self._sid(9), t=NOW + 9, by="boot", endedAt=NOW + 9)   # finalized → skipped
        os.utime(jd.GONEDIR / (self._sid(9) + ".json"), (NOW + 9, NOW + 9))
        got = jd._death_pending(exclude={self._sid(0)})
        self.assertEqual(len(got), jd.DEATH_DRAIN_PER_PASS, "the queue-drain bound holds")
        self.assertNotIn(self._sid(0), got, "a sid the fleet already covers is never doubled — "
                                            "a duplicate would race two closes on one store")
        self.assertNotIn(self._sid(9), got)
        self.assertEqual(got, sorted(got, key=lambda s: int(s[-2:])), "oldest marker first")

    def test_the_memo_skips_finalized_markers_with_zero_reads(self):
        _write_marker(self._sid(1), t=NOW, by="kill", endedAt=NOW)
        jd._death_pending(exclude=set())               # primes the memo
        p = jd.GONEDIR / (self._sid(1) + ".json")
        mt = p.stat().st_mtime_ns
        self.assertEqual(jd._gone_memo.get(self._sid(1)), (mt, True))


class DeathFinalize(unittest.TestCase):
    def tearDown(self):
        _wipe(SID)

    def test_a_settled_dead_store_with_open_tops_ends_loudly(self):
        _write_marker(SID, t=NOW, by="kill")
        st = _store(status={SID + ":g1": "working"},
                    nodes={SID + ":g1": {"id": SID + ":g1", "parentId": None,
                                         "text": "an unfinished thing", "t": NOW - 100, "log": []}})
        jd._death_finalize(SID, st, settled=True)
        m = json.loads((jd.GONEDIR / (SID + ".json")).read_text())
        self.assertEqual(m.get("endedAt"), NOW, "one-shot: the finalize is keyed on the marker's t")
        settles = jd.episode_settles(SID)
        ended = [v for k, v in settles.items() if str(k).startswith("ended:")]
        self.assertTrue(ended and ended[0]["settled"][0]["text"] == "an unfinished thing",
                        "cards END loudly — the /clear treatment, not a silent vanish")

    def test_nothing_open_still_finalizes_without_a_record(self):
        # the final gate's second finding: most sessions die with nothing open, and the dedup stamp
        # must fire for them or they sit in the pending queue forever
        _write_marker(SID, t=NOW, by="kill")
        jd._death_finalize(SID, _store(), settled=True)
        m = json.loads((jd.GONEDIR / (SID + ".json")).read_text())
        self.assertEqual(m.get("endedAt"), NOW)
        self.assertEqual([k for k in jd.episode_settles(SID) if str(k).startswith("ended:")], [])

    def test_a_superseded_marker_retires_instead_of_stranding(self):
        # the final gate's third finding: die → revive before the drain → the marker must EXIT the
        # pending queue (retired as superseded), or the drain's finite-queue bound is a lie
        _write_marker(SID, t=NOW, by="gone")
        jd.STATESDIR.mkdir(parents=True, exist_ok=True)
        with open(jd.STATESDIR / (SID + ".jsonl"), "a") as f:
            f.write(json.dumps({"t": NOW + 60, "state": "waiting"}) + "\n")
        jd._death_finalize(SID, _store(), settled=False)
        m = json.loads((jd.GONEDIR / (SID + ".json")).read_text())
        self.assertTrue(m.get("superseded") and m.get("endedAt") == NOW)

    def test_unsettled_waits_for_the_closer(self):
        _write_marker(SID, t=NOW, by="kill")
        jd._death_finalize(SID, _store(), settled=False)
        self.assertNotIn("endedAt", json.loads((jd.GONEDIR / (SID + ".json")).read_text()))

    def _unreadable_rows(self):
        if not os.path.exists(jd.ERRORS):
            return []
        rows = [json.loads(l) for l in open(jd.ERRORS) if l.strip()]
        return [r for r in rows if r.get("err") == "states-unreadable" and r.get("fsid") == SID]

    @unittest.skipIf(os.geteuid() == 0, "root reads a mode-000 file")
    def test_an_unreadable_states_file_defers_the_finalize(self):
        # the supersession read is the ONE input that tells a revived session from a really-dead one.
        # Before the fix a states file that existed but could not be read answered exactly like "no row
        # newer than the marker": a revived session's marker took the real-end branch, a permanent 'ended'
        # record naming its still-open cards reached the bell, and nothing could take it back (a finalized
        # marker is never re-read). Unreadable is not evidence either way: the finalize waits — at the BACK of
        # the oldest-first drain, the cut walk's move (review fold): a permission bit never clears on its own,
        # and a marker left at the head would cost the drain one of its DEATH_DRAIN_PER_PASS slots every pass.
        _write_marker(SID, t=NOW, by="gone")
        marker = jd.GONEDIR / (SID + ".json")
        os.utime(marker, (NOW, NOW))                       # the oldest marker in the queue
        before = marker.stat().st_mtime_ns
        jd.STATESDIR.mkdir(parents=True, exist_ok=True)
        sp = jd.STATESDIR / (SID + ".jsonl")
        with open(sp, "a") as f:
            f.write(json.dumps({"t": NOW + 60, "state": "waiting"}) + "\n")   # the revival row
        st = _store(status={SID + ":g1": "working"},
                    nodes={SID + ":g1": {"id": SID + ":g1", "parentId": None,
                                         "text": "an unfinished thing", "t": NOW - 100, "log": []}})
        os.chmod(sp, 0)
        try:
            jd._judge_ctx.stage_incomplete = False
            jd._death_finalize(SID, st, settled=True)
            m = json.loads((jd.GONEDIR / (SID + ".json")).read_text())
            self.assertNotIn("endedAt", m, "an unreadable states file is not 'no newer evidence': the finalize waits")
            self.assertGreater(marker.stat().st_mtime_ns, before,
                               "…at the BACK of the drain, not its head: the deferred marker is rotated like a cut one")
            self.assertEqual([k for k in jd.episode_settles(SID) if str(k).startswith("ended:")], [],
                             "no 'ended' record for a session the pass could not tell from a revived one")
            self.assertTrue(jd._judge_ctx.stage_incomplete, "the failed read marks the stage: no closer stamp lands")
            self.assertEqual(len(self._unreadable_rows()), 1, "one loud row")
            jd._death_finalize(SID, st, settled=True)
            self.assertNotIn("endedAt", json.loads((jd.GONEDIR / (SID + ".json")).read_text()))
            self.assertEqual(len(self._unreadable_rows()), 1, "one row per failure episode, not per pass")
        finally:
            os.chmod(sp, 0o644)
        jd._death_finalize(SID, st, settled=True)
        m = json.loads((jd.GONEDIR / (SID + ".json")).read_text())
        self.assertTrue(m.get("superseded") and m.get("endedAt") == NOW,
                        "readable again: the deferred supersession lands and the marker retires")
        self.assertEqual([k for k in jd.episode_settles(SID) if str(k).startswith("ended:")], [],
                         "the revived session's open cards were never declared ended")


class BellCarriesTheEnd(unittest.TestCase):
    def setUp(self):
        # km.jd is the SHARED "romp_judge" module object, which other test files may rebind to
        # their own state dirs mid-suite — pin its paths to OURS for the duration (the production
        # kernel holds exactly one instance, so this is a harness artifact, not a code path)
        self._saved = (km.jd.STATE, km.jd.NAMES, km.jd.GONEDIR, km.jd.STATESDIR,
                       km.jd.EPIDIR, km.jd.SDKDIR)
        km.jd.STATE, km.jd.NAMES, km.jd.GONEDIR = jd.STATE, jd.NAMES, jd.GONEDIR
        km.jd.STATESDIR, km.jd.EPIDIR, km.jd.SDKDIR = jd.STATESDIR, jd.EPIDIR, jd.SDKDIR
        km.jd._episode_memo.clear()

    def tearDown(self):
        (km.jd.STATE, km.jd.NAMES, km.jd.GONEDIR, km.jd.STATESDIR,
         km.jd.EPIDIR, km.jd.SDKDIR) = self._saved
        _wipe(SID)
        try:
            (jd.NAMES / SID).unlink()
        except OSError:
            pass

    def test_a_dead_finalized_session_with_open_cards_reaches_the_bell(self):
        _write_marker(SID, t=NOW, by="kill", endedAt=NOW)
        jd.append_episode_settle(SID, "ended:%d" % NOW, NOW + 1,
                                 [{"id": SID + ":g1", "text": "an unfinished thing"}])
        jd.NAMES.mkdir(parents=True, exist_ok=True)
        (jd.NAMES / SID).write_text("web\t/tmp\t#123456\t#fff\n")
        rows = km._boundary_clear_notices([])          # the dead sid is by definition not in alive
        mine = [r for r in rows if r["sid"] == SID]
        diag = "marker=%r settles=%r gone=%r rows=%r" % (
            km.jd._death_marker(SID), km.jd.episode_settles(SID),
            sorted(p.name for p in (km.jd.STATE / "gone").iterdir()), rows)
        self.assertTrue(mine and mine[0].get("ended") and mine[0]["titles"] == ["an unfinished thing"], diag)

    def test_the_name_reuse_guard_suppresses_only_the_interrupt(self):
        _write_marker(SID, t=NOW, by="kill", endedAt=NOW)
        jd.append_episode_settle(SID, "ended:%d" % NOW, NOW + 1, [{"id": SID + ":g1", "text": "x"}])
        jd.NAMES.mkdir(parents=True, exist_ok=True)
        (jd.NAMES / SID).write_text("web\t/tmp\t#123456\t#fff\n")
        alive = [{"sid": "22222222-3333-4444-5555-666666666666", "name": "web"}]
        saved = jd.episode_settles
        jd.episode_settles = lambda sid: {} if sid != SID else saved(sid)
        try:
            rows = km._boundary_clear_notices(alive)
        finally:
            jd.episode_settles = saved
        self.assertEqual([r for r in rows if r["sid"] == SID], [],
                         "'web ended' ringing beside a LIVE web misreads — records stay on disk, "
                         "only the interrupt is suppressed")


class RunClosePins(unittest.TestCase):
    def test_the_drain_is_deduped_and_window_independent(self):
        import inspect
        src = inspect.getsource(jd.run_close)
        self.assertIn('pending = _death_pending(exclude=fleet_sids)', src)
        self.assertIn('discover(now, window=DEATH_BACKFILL_WINDOW)', src)

    def test_the_finalize_rides_every_close(self):
        # …told NOT settled when the walk was CUT at a failed call (2026-09-03): a dead session is swept
        # only through the death drain, so finalizing its marker off a walk that left turns unswept
        # would strand them for good (the behavioral pin is test_judge.py SweepSession)
        import inspect
        self.assertIn('_death_finalize(fsid, store, settled and not cut)', inspect.getsource(jd._close_session))


if __name__ == "__main__":
    unittest.main()
