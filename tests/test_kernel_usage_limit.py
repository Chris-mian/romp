#!/usr/bin/env python3
"""Usage-limit banner + auto retry-pause (the user 2026-07-01): when a usage window (5h Session or 7d Weekly)
hits 100% and hasn't reset yet, _usage() flags `limited`, which (a) shows a top banner in the shell and (b)
auto-engages the global retry-pause so romp stops retrying into a rate-limited account (and pauses the judges,
which gate on the same flag). It auto-clears via _auto_resume_retry once a session serves a request again.
Synthetic fixtures only (placeholder ids / hostname TESTHOST)."""
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_ulimit", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd


class UsageLimitSignal(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def _write(self, five_pct, seven_pct, five_reset=None, seven_reset=None):
        fut = int(time.time()) + 3600
        (jd.STATE / "usage.json").write_text(json.dumps({
            "t": int(time.time()),
            "five_hour": {"pct": five_pct, "resets_at": five_reset if five_reset is not None else fut},
            "seven_day": {"pct": seven_pct, "resets_at": seven_reset if seven_reset is not None else fut}}))

    def test_a_maxed_window_is_flagged_limited(self):
        self._write(100, 40)
        lim = km._usage()["limited"]
        self.assertEqual(lim, {"fiveHour": True, "sevenDay": False}, "the 5h Session window is at its limit")

    def test_both_windows_can_be_limited(self):
        self._write(100, 100)
        self.assertEqual(km._usage()["limited"], {"fiveHour": True, "sevenDay": True})

    def test_under_the_limit_is_not_flagged(self):
        self._write(90, 99)
        self.assertIsNone(km._usage()["limited"], "below 100% → no limit")

    def test_a_rolled_over_window_is_not_limited(self):
        # 100% but the reset is in the PAST → the window has rolled; the pct is stale, not a live limit
        self._write(100, 20, five_reset=int(time.time()) - 60)
        self.assertIsNone(km._usage()["limited"], "past resetsAt → rolled over, not limited")


class AutoPauseOnLimit(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)
        self._usage = km._usage
        self._push = km._push_all
        km._push_all = lambda: None

    def tearDown(self):
        jd.STATE = self.saved
        km._usage = self._usage
        km._push_all = self._push
        self.td.cleanup()

    def test_hitting_a_limit_engages_the_retry_pause(self):
        km._usage = lambda: {"limited": {"fiveHour": True, "sevenDay": False}}
        self.assertFalse(km._retry_paused_on())
        km._auto_pause_on_limit()
        self.assertTrue(km._retry_paused_on(), "a usage limit auto-engages the global retry-pause")

    def test_no_limit_leaves_retries_running(self):
        km._usage = lambda: {"limited": None}
        km._auto_pause_on_limit()
        self.assertFalse(km._retry_paused_on(), "under the limit → retries keep running")


class LimitBannerWiring(unittest.TestCase):
    def test_the_shell_has_the_banner_and_the_widget_drives_it(self):
        land = km._landing()
        self.assertIn("<div id=romp-limit>", land)
        self.assertIn("class=rl-msg", land)
        self.assertIn("#romp-limit.show{display:flex}", land)
        js = km._LANDING_USAGE_JS
        self.assertIn("var lb=document.getElementById('romp-limit');", js)
        self.assertIn("lb.classList.toggle('show',on);", js)
        self.assertIn("usage limit reached", js)


if __name__ == "__main__":
    unittest.main()
