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

    def test_a_skipped_look_still_runs_the_parse_free_debt_reminder(self):
        d = tempfile.mkdtemp(); r = _row(d, SID_OLD, old=True); calls = []; now = time.time(); asked = []
        self._look(r, now, calls)
        self.assertEqual(self._look(r, now + 1, calls, _fire_debt_reminder=lambda sid, now_, alive: (asked.append((sid, now_)), True)[1]), True)
        self.assertEqual(asked, [(SID_OLD, now + 1)], "the skip asked the debt reminder, which needs no parse")
        self.assertEqual(calls, [SID_OLD])

    def test_the_pass_walks_by_recency_and_yields_after_the_first_cold_parse_with_a_client(self):
        d = tempfile.mkdtemp()
        older, newer = _row(d, SID_OLD, old=True), _row(d, SID_NEW, old=False)
        seen = []
        def look(s, now, live_map, nudged, waitfor, alive_ids=None, wake_only=False, cleared=None):
            seen.append(s["sid"]); km._NUDGE_HORIZON.cold = getattr(km._NUDGE_HORIZON, "cold", 0) + 1   # a cold parse paid
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
        self.assertEqual(seen, [SID_NEW], "the most recent session first; the rest deferred after the first cold parse")
        self.assertEqual(km._NUDGE_WALK_STATS["deferredSessions"], 1)
        seen.clear()
        with mock.patch.multiple(km, **quiet):
            km._auto_nudge_pass(time.time(), {}, True)                   # no client: the whole walk, in recency order
        self.assertEqual(seen, [SID_NEW, SID_OLD])
        self.assertEqual(km._NUDGE_WALK_STATS["deferredSessions"], 1, "no yield without a client")

    def test_the_perf_memos_and_the_boot_row_carry_the_walk(self):
        self.assertIn("nudgeWalk", km._PERF_STATS.snapshot()["memos"])
        self.assertEqual(set(km._PERF_STATS.snapshot()["memos"]["nudgeWalk"]), set(km._NUDGE_WALK_STATS))
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0], dict(km._NUDGE_WALK_FIRST), km._NUDGE_WALK_FIRST_OPEN[0]); rows = []
        km._append_restart_cut = lambda row: rows.append(row); km._BOOT_HEALTH_DONE[0] = False
        km._NUDGE_WALK_FIRST["skipped"][:] = [SID_OLD]; km._NUDGE_WALK_FIRST["parsed"][:] = [SID_NEW]; km._NUDGE_WALK_FIRST["deferred"] = 2
        km._NUDGE_WALK_FIRST_OPEN[0] = True
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0] = saved[0], saved[1]
            km._NUDGE_WALK_FIRST.update(saved[2]); km._NUDGE_WALK_FIRST_OPEN[0] = saved[3]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["nudgeWalk"], {"skipped": [SID_OLD], "parsed": [SID_NEW], "deferred": 2}, rows[0])


if __name__ == "__main__":
    unittest.main()
