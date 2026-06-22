#!/usr/bin/env python3
"""The DEBUG timeline band renders a ⚡ per auto-nudge fire (the user 2026-06-22): build_timeline reads
STATE/nudge-events.jsonl via _nudge_marks and emits {sid, gid, t, count} marks in the horizon for ALIVE
sessions; the view draws each as a lightning bolt at its fire time, escalating to a red warning at
count>=4. Self-contained: drives _nudge_marks against a synthetic nudge-events.jsonl."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_nm", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

SID = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-8888-7777-6666-555555555555"


class NudgeMarks(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def _write(self, events):
        (jd.STATE / "nudge-events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    def test_reads_in_horizon_for_alive_sessions(self):
        self._write([
            {"sid": SID, "gid": SID + ":g1", "t": 1000, "count": 1},      # in window, alive
            {"sid": SID, "gid": SID + ":g1", "t": 1100, "count": 2},      # in window, alive
            {"sid": SID, "gid": SID + ":g1", "t": 500, "count": 1},       # BEFORE t0 → dropped
            {"sid": OTHER, "gid": OTHER + ":g1", "t": 1200, "count": 1},  # not in alive_sids → dropped
        ])
        marks = km._nudge_marks(900, {SID})
        self.assertEqual([(m["t"], m["count"]) for m in marks], [(1000, 1), (1100, 2)],
                         "only in-horizon fires for alive sessions, in log order")
        self.assertTrue(all(m["sid"] == SID and m["gid"] == SID + ":g1" for m in marks))

    def test_missing_or_garbage_log_is_empty(self):
        self.assertEqual(km._nudge_marks(0, {SID}), [], "no log → no marks (best-effort)")
        (jd.STATE / "nudge-events.jsonl").write_text("not json\n{bad}\n")
        self.assertEqual(km._nudge_marks(0, {SID}), [], "garbage lines are skipped, never raise")


if __name__ == "__main__":
    unittest.main()
