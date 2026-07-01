#!/usr/bin/env python3
"""SDK-sourced /usage bars (the user 2026-06-30).

The rail's rate-limit bars (5h Session + 7d Weekly) read usage.json. Under tmux that file is written by
Claude Code's statusline.sh; an SDK session has NO statusline, so the bars went stale/blank there. The
Agent SDK's DESIGNED source is the RateLimitEvent stream — each carries one window's utilization (0.0-1.0)
+ resets_at. SdkBackend._record_rate_limit accumulates those and writes the SAME usage.json shape, so the
same kernel _usage() reader lights the bars for SDK sessions too. Synthetic fixtures (duck-typed info)."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend", os.path.join(BIN, "romp_sdk_backend.py")).load_module()


def _info(rate_limit_type, utilization, resets_at=None):
    """A duck-typed RateLimitInfo (only the fields _record_rate_limit reads)."""
    return SimpleNamespace(rate_limit_type=rate_limit_type, utilization=utilization, resets_at=resets_at)


class RecordRateLimit(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.state = Path(self.td.name)
        self.be = sb.SdkBackend(self.state, "claude", lambda *a: None)

    def tearDown(self):
        self.td.cleanup()

    def _usage(self):
        return json.loads((self.state / "usage.json").read_text())

    def test_accumulates_both_windows_into_the_statusline_shape(self):
        # each window arrives as its OWN event; the merged file must carry BOTH (utilization → pct)
        self.be._record_rate_limit(_info("five_hour", 0.10, 1782787200))
        self.be._record_rate_limit(_info("seven_day", 0.11, 1783364400))
        u = self._usage()
        self.assertEqual(u["five_hour"], {"pct": 10, "resets_at": 1782787200})
        self.assertEqual(u["seven_day"], {"pct": 11, "resets_at": 1783364400})
        self.assertIsInstance(u["t"], int)

    def test_weekly_takes_the_binding_highest_seven_day_variant(self):
        # opus / sonnet sub-limits also feed the weekly bar; the BINDING (highest) one wins
        self.be._record_rate_limit(_info("seven_day", 0.11, 1))
        self.be._record_rate_limit(_info("seven_day_opus", 0.40, 2))
        self.assertEqual(self._usage()["seven_day"]["pct"], 40, "the highest weekly variant is the binding limit")

    def test_overage_and_unmodeled_windows_are_ignored(self):
        self.be._record_rate_limit(_info("five_hour", 0.25, 5))
        self.be._record_rate_limit(_info("overage", 0.99, 9))       # not a bar window
        self.be._record_rate_limit(_info(None, 0.99, 9))            # no type
        u = self._usage()
        self.assertEqual(u["five_hour"]["pct"], 25)
        self.assertIsNone(u["seven_day"], "overage/None never populate the weekly bar")

    def test_non_numeric_utilization_writes_nothing(self):
        self.be._record_rate_limit(_info("five_hour", None, 5))
        self.assertFalse((self.state / "usage.json").exists(), "a malformed event is dropped, not written")

    def test_the_kernel_usage_reader_lights_the_bars_from_what_the_sdk_wrote(self):
        # End-to-end: the SDK writer + the kernel reader agree on usage.json (no statusline in the loop).
        self.be._record_rate_limit(_info("five_hour", 0.10, 1782787200))
        self.be._record_rate_limit(_info("seven_day", 0.11, 1783364400))
        SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
        SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
        os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
        os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
        km = SourceFileLoader("romp_kernel_rl", os.path.join(BIN, "romp-kernel")).load_module()
        saved = km.jd.STATE
        km.jd.STATE = self.state
        try:
            u = km._usage()
        finally:
            km.jd.STATE = saved
        self.assertIsNotNone(u)
        self.assertEqual(u["fiveHour"]["pct"], 10)
        self.assertEqual(u["sevenDay"]["pct"], 11)
        self.assertEqual(u["fiveHour"]["resetsAt"], 1782787200)


if __name__ == "__main__":
    unittest.main()
