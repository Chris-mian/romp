#!/usr/bin/env python3
"""hideFromFeed takes a session OUT of task tracking (the user 2026-06-23): when the timeline's feed checkbox
is crossed out, the judge's PLANNER and CLOSER skip the session — so no goal backlog accumulates while it's
muted (toggling off→on then surfaces nothing). The captioner/archiver (run_index, the search index) is
deliberately NOT gated, so a muted session stays findable via find_sessions.

Synthetic only — placeholder UUIDs, hermetic temp STATE, no real session data.
"""
import json
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

MUTED = "11111111-1111-1111-1111-111111111111"
VISIBLE = "22222222-2222-2222-2222-222222222222"


class HiddenFromFeed(unittest.TestCase):
    def setUp(self):
        self._saved_state = jd.STATE
        self._td = tempfile.mkdtemp()
        jd.STATE = Path(self._td)

    def tearDown(self):
        jd.STATE = self._saved_state
        shutil.rmtree(self._td, ignore_errors=True)

    def _mute(self, sid, flag="hideFromFeed"):
        (jd.STATE / "session-flags.json").write_text(json.dumps({sid: {flag: True}}))

    # ── the flag reader ──
    def test_reader_reads_the_flag(self):
        self.assertFalse(jd._hidden_from_feed(MUTED), "no flags file → not hidden")
        self._mute(MUTED)
        self.assertTrue(jd._hidden_from_feed(MUTED))
        self.assertFalse(jd._hidden_from_feed(VISIBLE), "a different session is unaffected")

    def test_reader_fails_open_on_corruption(self):
        (jd.STATE / "session-flags.json").write_text("{not valid json")
        self.assertFalse(jd._hidden_from_feed(MUTED), "a corrupt flags file must NOT wedge the judge")

    def test_postaloff_does_not_stop_tracking(self):
        self._mute(MUTED, flag="postalOff")
        self.assertFalse(jd._hidden_from_feed(MUTED), "postalOff (mailbox) alone must not stop task tracking")

    # ── the planner/closer fleet gate ──
    def _fleet(self):
        return [(MUTED, "/tmp/m.jsonl", None, "muted"), (VISIBLE, "/tmp/v.jsonl", None, "visible")]

    def _run_collecting(self, runner_name, worker_name, worker_ret):
        seen = []
        saved_disc = jd.discover
        saved_worker = getattr(jd, worker_name)
        jd.discover = lambda now: self._fleet()
        setattr(jd, worker_name, lambda fsid, path, now: (seen.append(fsid), worker_ret)[1])
        try:
            getattr(jd, runner_name)(now=1700000000)
        finally:
            jd.discover = saved_disc
            setattr(jd, worker_name, saved_worker)
        return seen

    def test_planner_skips_a_muted_session(self):
        self._mute(MUTED)
        seen = self._run_collecting("run_plan", "_plan_session", 0)
        self.assertEqual(seen, [VISIBLE], "the planner plans only the visible session, skipping the muted one")

    def test_closer_skips_a_muted_session(self):
        self._mute(MUTED)
        seen = self._run_collecting("run_close", "_close_session", [])
        self.assertEqual(seen, [VISIBLE], "the closer skips the muted session")

    def test_unmuted_sessions_are_all_tracked(self):
        seen = self._run_collecting("run_plan", "_plan_session", 0)   # no flag set
        self.assertEqual(sorted(seen), sorted([MUTED, VISIBLE]), "with no flag, every session is planned")


if __name__ == "__main__":
    unittest.main()
