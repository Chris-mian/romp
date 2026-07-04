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

    def _write(self, five_pct, seven_pct, five_reset=None, seven_reset=None, fable_pct=None):
        fut = int(time.time()) + 3600
        (jd.STATE / "usage.json").write_text(json.dumps({
            "t": int(time.time()),
            "five_hour": {"pct": five_pct, "resets_at": five_reset if five_reset is not None else fut},
            "seven_day": {"pct": seven_pct, "resets_at": seven_reset if seven_reset is not None else fut},
            "fable": {"pct": fable_pct, "resets_at": fut} if fable_pct is not None else None}))

    def test_a_maxed_window_is_flagged_limited(self):
        self._write(100, 40)
        lim = km._usage()["limited"]
        self.assertEqual(lim, {"fiveHour": True, "sevenDay": False, "fable": False},
                         "the 5h Session window is at its limit")

    def test_both_windows_can_be_limited(self):
        self._write(100, 100)
        self.assertEqual(km._usage()["limited"], {"fiveHour": True, "sevenDay": True, "fable": False})

    def test_under_the_limit_is_not_flagged(self):
        self._write(90, 99)
        self.assertIsNone(km._usage()["limited"], "below 100% → no limit")

    def test_a_maxed_fable_window_is_flagged_limited(self):
        # the included Fable 5 weekly allowance (the user 2026-07-02) still flags `limited` at 100% so the
        # banner + the rail's third bar light up — but, unlike 5h/7d, it does NOT engage the retry-pause
        # (the user 2026-07-03; see AutoPauseOnLimit), because it's a MODEL-scoped limit, not account-wide
        self._write(10, 20, fable_pct=100)
        self.assertEqual(km._usage()["limited"], {"fiveHour": False, "sevenDay": False, "fable": True})

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
        km._usage = lambda: {"limited": {"fiveHour": True, "sevenDay": False, "fable": False}}
        self.assertFalse(km._retry_paused_on())
        km._auto_pause_on_limit()
        self.assertTrue(km._retry_paused_on(), "a usage limit auto-engages the global retry-pause")

    def test_no_limit_leaves_retries_running(self):
        km._usage = lambda: {"limited": None}
        km._auto_pause_on_limit()
        self.assertFalse(km._retry_paused_on(), "under the limit → retries keep running")

    def test_a_fable_only_limit_does_not_engage_the_pause(self):
        # Fable-5 is MODEL-scoped (the user 2026-07-03): exhausting it doesn't stop the account from serving
        # Sonnet/Haiku (the judges) or Opus (sessions), so it must NOT engage the global pause. Doing so
        # flapped the judges — the account kept serving requests, so _auto_resume_retry cleared the pause each
        # tick and this re-engaged it, starving the distiller. fable=100% still lights the banner (above).
        km._usage = lambda: {"limited": {"fiveHour": False, "sevenDay": False, "fable": True}}
        km._auto_pause_on_limit()
        self.assertFalse(km._retry_paused_on(), "a model-scoped Fable limit must not pause the judges")

    def test_an_account_limit_still_engages_even_alongside_fable(self):
        # a genuine account-wide limit (5h/7d) engages regardless of the fable window's state
        km._usage = lambda: {"limited": {"fiveHour": True, "sevenDay": False, "fable": True}}
        km._auto_pause_on_limit()
        self.assertTrue(km._retry_paused_on(), "a real 5h/7d limit still engages the pause")


class LimitBannerWiring(unittest.TestCase):
    def test_the_shell_has_the_banner_and_the_widget_drives_it(self):
        land = km._landing()
        self.assertIn("<div id=romp-limit>", land)
        self.assertIn("class=rl-msg", land)
        self.assertIn("#romp-limit.show{display:flex}", land)
        js = km._LANDING_USAGE_JS
        self.assertIn("var lb=document.getElementById('romp-limit');", js)
        self.assertIn("lb.classList.toggle('show',show);", js)
        self.assertIn("usage limit reached", js)

    def test_the_banner_has_a_dismiss_button_gated_on_the_limit_signature(self):
        land = km._landing()
        # a ✕ affordance is in the banner + styled
        self.assertIn("class=rl-x", land)
        self.assertIn("#romp-limit .rl-x", land)
        js = km._LANDING_USAGE_JS
        # dismissal is keyed to WHICH windows are limited (a signature), persisted in localStorage
        self.assertIn("romp:limitDismiss", js)
        self.assertIn("_limPut(_limSig)", js)                 # ✕ stores the current signature → hides
        self.assertIn("sig!==_limGet()", js)                  # a stored signature suppresses re-showing
        self.assertIn("if(!on){_limPut('');}", js)            # a full clear forgets the dismissal
        # a NEW limited-window set has a different signature → the banner returns (episode identity, not a timer)
        self.assertIn("(lim.fiveHour?'5':'')+(lim.sevenDay?'7':'')+(lim.fable?'F':'')", js)


if __name__ == "__main__":
    unittest.main()


class FableBanner(unittest.TestCase):
    def test_the_banner_names_a_maxed_fable_window(self):
        js = km._LANDING_USAGE_JS
        self.assertIn("lim.fiveHour||lim.sevenDay||lim.fable", js, "the banner triggers on the fable window too")
        self.assertIn("names.push('Fable 5 (7d)')", js, "and names it")
