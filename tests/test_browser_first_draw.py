#!/usr/bin/env python3
"""The browser's own first draw after a restart (2026-09-14). A fresh client's full push runs on its handler thread, which the
pusher's cycles and the restart ledger never timed, so the logo-with-no-panes phase the user saw at 3:58 PM PT on 2026-09-13
had no number. Now the connect push is counted under /perf `pusher.connectPush` (per app too)."""
import os
import sys
import time
import unittest
from unittest import mock
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_asm_checkpoint import kernel_module   # noqa: E402


class ConnectPushTimed(unittest.TestCase):
    def setUp(self):
        self.km = kernel_module()
        self.km._PERF_STATS.reset()

    def tearDown(self):
        self.km._PERF_STATS.reset()

    def test_a_connect_push_is_counted_per_app(self):
        km = self.km
        client = {"app": "feed", "alive": True}
        with mock.patch.object(km, "_push", side_effect=lambda targets, connect=False, live_map=None: time.sleep(0.02)):
            km.Handler._push_one(mock.Mock(), client)
        cp = km._PERF_STATS.snapshot()["pusher"]["connectPush"]
        self.assertEqual(cp["count"], 1)
        self.assertGreaterEqual(cp["ms_last"], 20.0)
        self.assertEqual(cp["ms_max"], cp["ms_last"]); self.assertEqual(cp["ms_sum"], cp["ms_last"])
        self.assertEqual(cp["byApp"]["feed"]["count"], 1)
        self.assertGreaterEqual(cp["byApp"]["feed"]["ms_max"], 20.0)

    def test_a_connect_push_that_raises_is_still_timed(self):
        km = self.km
        with mock.patch.object(km, "_push", side_effect=RuntimeError("wire gone")):
            with self.assertRaises(RuntimeError):
                km.Handler._push_one(mock.Mock(), {"app": "chat"})
        self.assertEqual(km._PERF_STATS.snapshot()["pusher"]["connectPush"]["byApp"]["chat"]["count"], 1)

    def test_a_fresh_snapshot_lists_the_counter_at_zero(self):
        cp = self.km._PerfStats().snapshot()["pusher"]["connectPush"]
        self.assertEqual((cp["count"], cp["ms_sum"], cp["ms_max"], cp["ms_last"], cp["byApp"]), (0, 0.0, 0.0, 0.0, {}))

    def test_the_docs_name_the_counter(self):
        doc = open(os.path.join(os.path.dirname(HERE), "docs", "reference.md"), encoding="utf-8").read()
        self.assertIn("`connectPush`", doc)


if __name__ == "__main__":
    unittest.main()
