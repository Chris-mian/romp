#!/usr/bin/env python3
"""T401 (2), 2026-09-13: the auto-nudge walk parsed every alive session on every pass, cold at boot (58.9 s of a 63 s first
cycle on the first boot with per-stage rows). Its parse is gated now: skipped while the session's transcript, state log and
store are unchanged since the last completed look AND no clock leg that look declined on has come due; the skip repeats the
recorded verdict and still runs the parse-free debt reminder. The pass walks by recency and, with a client connected, yields
after the first cold parse. Synthetic sessions only."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_boot_parse_gating import km, _row, SID_OLD, SID_NEW   # noqa: E402  the hermetic kernel and the row builder

COMMON = dict(_session_flag=lambda sid, flag: False, _compacting_now=lambda *a, **k: False, _api_error=lambda path: False,
              _session_working=lambda turns: True, _auto_nudge_data=lambda: {}, _fire_debt_reminder=lambda sid, now, alive_ids: False)
STOPPED = [{"id": "t1", "t": 1000, "ended": True, "atoms": [{"t": 1000, "type": "user"}]}]


class NudgeWalkParseGate(unittest.TestCase):
    def setUp(self):
        km._TICK_SEEN.clear()
        for k in km._NUDGE_WALK_STATS:
            km._NUDGE_WALK_STATS[k] = 0
        km._NUDGE_HORIZON.notes = None

    def _look(self, r, now, calls, **over):
        patches = dict(COMMON, **over)
        with mock.patch.multiple(km, **patches), \
             mock.patch.object(km.jd, "parsed_session", side_effect=lambda sid, paths, now: (calls.append(sid), {"turns": STOPPED})[1]), \
             mock.patch.object(km.jd, "_parse_entry", side_effect=lambda sid, session=None, turns=None: None):
            return km._auto_nudge_session(r, now, {}, {}, {}, alive_ids={r["sid"]})

    def test_an_unchanged_session_with_no_clock_leg_skips_its_parse_and_repeats_its_verdict(self):
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []; now = time.time()
        self.assertEqual(self._look(r, now, calls), "working")
        self.assertEqual(self._look(r, now + 5, calls), "working", "the skip repeats the recorded verdict")
        self.assertEqual(calls, [SID_OLD], "one parse across two looks of an unchanged session with no clock leg")
        self.assertEqual((km._NUDGE_WALK_STATS["looks"], km._NUDGE_WALK_STATS["parses"], km._NUDGE_WALK_STATS["skippedParses"]), (2, 1, 1))
        Path(r["path"]).write_text(Path(r["path"]).read_text() + "\n")   # the transcript moves
        self.assertEqual(self._look(r, now + 10, calls), "working")
        self.assertEqual(calls, [SID_OLD, SID_OLD], "a moved file is evaluated")
        self.assertIn(("auto-nudge", SID_OLD), km._TICK_SEEN, "the memo persists with the tick memo")

    def test_a_look_that_never_parsed_records_nothing(self):
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []
        self.assertEqual(self._look(r, time.time(), calls, _session_flag=lambda sid, flag: True), "muted")
        self.assertNotIn(("auto-nudge", SID_OLD), km._TICK_SEEN)
        self.assertEqual(calls, [])

    def test_a_noted_clock_flip_evaluates_when_due_and_an_unbounded_note_never_skips(self):
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); now = time.time()
        st = km._session_files_stat(r)
        km._nudge_look_done(r, st, [now + 100, now + 50], "working")
        self.assertEqual(km._nudge_look_check(r, now)[0::2], (True, "working"), "before the earliest flip: skip")
        self.assertEqual(km._nudge_look_check(r, now + 50)[0], False, "at the flip: evaluate")
        self.assertEqual(km._NUDGE_WALK_STATS["clockDue"], 1)
        km._nudge_look_done(r, st, [now + 100, None], "working")
        self.assertEqual(km._nudge_look_check(r, now)[0], False, "a leg released by something not in the files: never skipped")
        self.assertEqual(km._NUDGE_WALK_STATS["unbounded"], 1)
        km._nudge_look_done(r, st, [], None)
        self.assertEqual(km._nudge_look_check(r, now + 10 ** 6)[0::2], (True, None), "no clock leg: skippable while the files stand")
        os.utime(r["path"], (now - 1, now - 1))
        self.assertEqual(km._nudge_look_check(r, now)[0], False, "a moved file: evaluate")

    def test_the_clock_notes_collect_only_inside_a_look(self):
        km._NUDGE_HORIZON.notes = None
        km._nudge_clock(5.0)                                             # outside a look: a no-op
        km._NUDGE_HORIZON.notes = []
        km._nudge_clock(7.0); km._nudge_clock(None)
        self.assertEqual(km._NUDGE_HORIZON.notes, [7.0, None])
        km._NUDGE_HORIZON.notes = None

    def test_a_standing_deferral_notes_an_unbounded_release(self):
        km._NUDGE_HORIZON.notes = []
        with mock.patch.multiple(km, _auto_nudge_data=lambda: {"deferred": {}}, _write_auto_nudge=lambda d: True):
            self.assertFalse(km._nudge_deferred_ok("g1", "a reviver is pending", time.time(), SID_OLD))
        self.assertEqual(km._NUDGE_HORIZON.notes, [None], "a deferral is released by a judge pass watermark, not the session's files")
        km._NUDGE_HORIZON.notes = None

    def test_a_skipped_look_repeats_the_verdict_and_sends_nothing(self):
        """Round one, medium 1: the skip road ran the debt reminder with none of the session-level gates the full road applies
        before every send (idle, judged, unqueued), so the second look of a session the user stopped sent a reminder the full
        road refused. The skip repeats the recorded verdict and nothing else."""
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []; now = time.time(); asked = []
        self._look(r, now, calls)
        self.assertEqual(self._look(r, now + 1, calls, _fire_debt_reminder=lambda sid, now_, alive: (asked.append((sid, now_)), True)[1]), "working")
        self.assertEqual(asked, [], "the skip road sends nothing: every send sits behind the full road's gates")
        self.assertEqual(calls, [SID_OLD])

    def test_the_memo_survives_a_restart_through_the_loader(self):
        """Round one, medium 2: the loader kept rows of length six and the nudge's rows are eight long, so after a restart every
        cold parse was paid again, the case the gate exists for. The memo round-trips: done, persisted, cleared, loaded, skip."""
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); now = time.time()
        saved_state = km.jd.STATE; km.jd.STATE = Path(tempfile.mkdtemp())
        try:
            km._nudge_look_done(r, km._session_files_stat(r), [now + 3600], "working")
            self.assertTrue(km._persist_tick_seen(force=True))
            km._TICK_SEEN.clear()
            self.assertGreaterEqual(km._load_tick_seen(), 1, "the persisted nudge row loads")
            self.assertEqual(km._nudge_look_check(r, now)[0::2], (True, "working"), "the next kernel skips on the loaded memo")
            self.assertEqual(km._nudge_look_check(r, now + 3600)[0], False, "and its flip still holds")
        finally:
            km.jd.STATE = saved_state

    def test_the_files_the_memo_keys_on_include_the_stores_identity_and_the_walks_logs(self):
        """Round one, low 2: the stat covered the store file alone, while the shared store's identity is three files (the store,
        its override journal, its archive) and the placement gate reads the episode and clears logs; a journal write whose store
        save did not land changed the world under a skip."""
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True)
        saved_state = km.jd.STATE; km.jd._rebind_state(Path(tempfile.mkdtemp()))
        try:
            st0 = km._session_files_stat(r)
            self.assertEqual(len(st0), 14, "seven files, (mtime, size) each")
            jp = km.jd._overrides_dir() / (SID_OLD + ".jsonl"); jp.parent.mkdir(parents=True, exist_ok=True); jp.write_text("{}\n")
            self.assertNotEqual(km._session_files_stat(r), st0, "the override journal moves the stat")
            st1 = km._session_files_stat(r)
            (km.jd.STATE / "cleared.jsonl").write_text("{}\n")
            self.assertNotEqual(km._session_files_stat(r), st1, "the clears log moves the stat")
        finally:
            km.jd._rebind_state(saved_state)

    def test_the_pass_walks_by_recency_and_yields_after_the_first_cold_parse_with_a_client(self):
        d = tempfile.mkdtemp()
        older, newer = _row(d, SID_OLD, old=True), _row(d, SID_NEW, old=False)
        seen = []; cold_for = {SID_NEW}                                  # only the newer session is cold, and it STAYS cold (a parse
        def look(s, now, live_map, nudged, waitfor, alive_ids=None, wake_only=False, cleared=None):   # that never caches)
            seen.append(s["sid"])
            if s["sid"] in cold_for:
                km._NUDGE_HORIZON.cold = getattr(km._NUDGE_HORIZON, "cold", 0) + 1; km._NUDGE_HORIZON.cold_last = True
            return None
        quiet = dict(_auto_nudge_data=lambda: {}, _auto_nudge_resume=lambda: None, _alive_sessions=lambda now, live_map: [older, newer],
                     _wait_for_graph=lambda now, ids: {}, _cleared_ids=lambda: set(), _auto_nudge_on=lambda: True,
                     _auto_nudge_session=look, _compact_suggest_tick=lambda sid, live, now: False, _relay_tick=lambda now, ids: None,
                     _debt_backstop_tick=lambda now: None, _dead_wait_sweep=lambda ids, nudged, now: None,
                     _awaiting_wake_outcomes=lambda now, ids: False, _push_soon=lambda: None, _pop_walk_gate=lambda k: None)
        with km._clients_lock:
            km._clients.append({"app": "feed", "wid": "lab", "send": lambda *a, **k: None, "alive": True, "dedup": {}})
        try:
            with mock.patch.multiple(km, **quiet):
                km._auto_nudge_pass(time.time(), {}, True)
        finally:
            with km._clients_lock:
                km._clients[:] = [c for c in km._clients if c.get("wid") != "lab"]
        self.assertEqual(seen, [SID_NEW], "the most recent session first; the rest deferred after a look that PAID a cold parse")
        self.assertEqual(km._NUDGE_WALK_STATS["deferredSessions"], 1)
        self.assertEqual(km._NUDGE_WALK_CURSOR[0], SID_OLD, "the first deferred session is where the next pass resumes")
        seen.clear()
        with km._clients_lock:
            km._clients.append({"app": "feed", "wid": "lab", "send": lambda *a, **k: None, "alive": True, "dedup": {}})
        try:
            with mock.patch.multiple(km, **quiet):
                km._auto_nudge_pass(time.time(), {}, True)               # the next pass resumes at the deferred session (round one,
        finally:                                                         #  medium 3): the older one is looked at BEFORE the cold
            with km._clients_lock:                                       #  head can yield again; a warm look never yields
                km._clients[:] = [c for c in km._clients if c.get("wid") != "lab"]
        self.assertEqual(seen, [SID_OLD, SID_NEW], "every session is reached within as many passes as there are cold parses")
        self.assertEqual(km._NUDGE_WALK_STATS["deferredSessions"], 1, "the rotated pass reached the end: nothing deferred")
        self.assertIsNone(km._NUDGE_WALK_CURSOR[0])
        seen.clear(); cold_for.update({SID_NEW, SID_OLD})
        with mock.patch.multiple(km, **quiet):
            km._auto_nudge_pass(time.time(), {}, True)                   # no client: the whole walk, cold or not
        self.assertEqual(seen, [SID_NEW, SID_OLD])
        self.assertEqual(km._NUDGE_WALK_STATS["deferredSessions"], 1, "no yield without a client")

    def test_the_perf_memos_and_the_boot_row_carry_the_walk(self):
        self.assertIn("nudgeWalk", km._PERF_STATS.snapshot()["memos"])
        self.assertEqual(set(km._PERF_STATS.snapshot()["memos"]["nudgeWalk"]), set(km._NUDGE_WALK_STATS))
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0], dict(km._NUDGE_WALK_FIRST), km._NUDGE_WALK_FIRST_OPEN[0]); rows = []
        km._append_restart_cut = lambda row: rows.append(row); km._BOOT_HEALTH_DONE[0] = False
        km._NUDGE_WALK_FIRST["skipped"][:] = [SID_OLD[:8]]; km._NUDGE_WALK_FIRST["parsed"][:] = [SID_NEW[:8]]; km._NUDGE_WALK_FIRST["deferred"] = 2
        km._NUDGE_WALK_FIRST_OPEN[0] = True
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0] = saved[0], saved[1]
            km._NUDGE_WALK_FIRST.update(saved[2]); km._NUDGE_WALK_FIRST_OPEN[0] = saved[3]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["nudgeWalk"], {"skipped": [SID_OLD[:8]], "parsed": [SID_NEW[:8]], "deferred": 2}, rows[0])

    def test_the_row_carries_eight_of_the_sid_and_at_most_forty(self):
        """The attachUnsettled convention for session ids in the restart ledger."""
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []
        saved = (list(km._NUDGE_WALK_FIRST["parsed"]), km._NUDGE_WALK_FIRST_OPEN[0])
        km._NUDGE_WALK_FIRST["parsed"][:] = ["x"] * 40; km._NUDGE_WALK_FIRST_OPEN[0] = True
        try:
            self._look(r, time.time(), calls)
            self.assertEqual(len(km._NUDGE_WALK_FIRST["parsed"]), 40, "capped at forty")
            km._NUDGE_WALK_FIRST["parsed"][:] = []
            Path(r["path"]).write_text(Path(r["path"]).read_text() + "\n")
            self._look(r, time.time() + 1, calls)
            self.assertEqual(km._NUDGE_WALK_FIRST["parsed"], [SID_OLD[:8]], "eight characters of the sid")
        finally:
            km._NUDGE_WALK_FIRST["parsed"][:] = saved[0]; km._NUDGE_WALK_FIRST_OPEN[0] = saved[1]

    def test_a_wake_only_look_neither_skips_nor_records_and_is_counted(self):
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []; now = time.time()
        with mock.patch.multiple(km, **COMMON), \
             mock.patch.object(km.jd, "parsed_session", side_effect=lambda sid, paths, now: (calls.append(sid), {"turns": STOPPED})[1]), \
             mock.patch.object(km.jd, "_parse_entry", side_effect=lambda sid, session=None, turns=None: None):
            for i in range(2):
                km._auto_nudge_session(r, now + i, {}, {}, {}, alive_ids={r["sid"]}, wake_only=True)
        self.assertEqual(calls, [SID_OLD, SID_OLD], "two parses: a wake-only look never skips")
        self.assertNotIn(("auto-nudge", SID_OLD), km._TICK_SEEN, "and records nothing: the toggle is not a file")
        self.assertEqual(km._NUDGE_WALK_STATS["wakeOnly"], 2)




class RedundancySkipKeepsItsDeadMan(unittest.TestCase):
    """Round one, HIGH: the redundancy skip in _judge_batch parked the goal (answeredAt written) and continued with no clock
    note, so the look recorded a flip of nothing-can-flip; a quiet session never moves its files, every later look skipped,
    and the 6 h parked dead-man never fired. The probe the read used: base fired fired-parked-backstop at now + 6 h + 60 s,
    the head answered None. Drives the real look over the quiet-session harness (its OWN kernel instance) with a REAL
    transcript file, since the gate stats the files."""

    def setUp(self):
        import test_nudge_memo_deadlock as M
        self.M = M; self.K = M.km
        self.h = M.MemoDeadlock("test_a_parked_goal_sleeps_silently"); self.h.setUp()
        self.K._TICK_SEEN.clear()
        for k in self.K._NUDGE_WALK_STATS:
            self.K._NUDGE_WALK_STATS[k] = 0
        d = tempfile.mkdtemp(); self.path = os.path.join(d, M.SID + ".jsonl")
        Path(self.path).write_text("{}\n")

    def tearDown(self):
        self.h.tearDown()

    def _tick(self, now):
        nudged = dict(self.K._auto_nudge_data().get("nudged", {}))
        return self.K._auto_nudge_session({"sid": self.M.SID, "path": self.path}, now, {}, nudged, {})

    def test_a_redundancy_skip_notes_the_parked_dead_man_and_the_backstop_fires_on_time(self):
        M, K = self.M, self.K
        self.h.judge_replies = [True]                                     # the judge rules the report redundant: a skip, a park
        self.assertIs(self._tick(M.NOW), False, "the full road: nothing fired")
        rows = self.h._rows()
        self.assertEqual([r.get("verdict") for r in rows], ["skipped-redundant"], rows)
        memo = K._TICK_SEEN.get(("auto-nudge", M.SID))
        self.assertIsNotNone(memo, "the look recorded its memo")
        flip = memo[-2]
        self.assertEqual(flip, M.NOW + K.AWAITING_DEADMAN_SECS, "the skip notes the parked dead-man it opened, not nothing-can-flip")
        self.assertIsNone(self._tick(M.NOW + 60), "inside the window: the parse is skipped, the verdict repeated")
        self.assertEqual(K._NUDGE_WALK_STATS["skippedParses"], 1)
        late = M.NOW + K.AWAITING_DEADMAN_SECS + 60
        self.assertIs(self._tick(late), True, "past the dead-man the look evaluates and the backstop fires")
        self.assertEqual([r.get("verdict") for r in self.h._rows()][-1], "fired-parked-backstop")
        self.assertEqual(len(self.h.sent), 1)
        self.assertEqual(K._NUDGE_WALK_STATS["clockDue"], 1)


if __name__ == "__main__":
    unittest.main()
