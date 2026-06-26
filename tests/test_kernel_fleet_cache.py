"""Feed + timeline are EXPENSIVE to build (re-segment every session ~2.7s) and were rebuilt on EVERY push,
so a reload/idle tick paid the full cost (the user 2026-06-25: "reload/startup still very slow"). They're
now cached, keyed on a fleet fingerprint that busts on any transcript/states/postal change, a judge pass, a
live tmux badge change, a colormap/session-flags change, or a 5s time bucket (so age labels keep advancing).
"""
import os
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class FleetCacheTest(unittest.TestCase):
    def test_sig_is_stable_when_nothing_changes(self):
        now, tmux = int(time.time()), km._tmux_sessions()
        self.assertEqual(km._fleet_view_sig(now, tmux), km._fleet_view_sig(now, tmux))

    def test_sig_busts_on_a_judge_pass(self):
        now, tmux = int(time.time()), km._tmux_sessions()
        a = km._fleet_view_sig(now, tmux)
        km._judge_gen[0] += 1
        try:
            self.assertNotEqual(a, km._fleet_view_sig(now, tmux), "a judge pass must rebuild the views")
        finally:
            km._judge_gen[0] -= 1

    def test_time_bucket_advances_so_age_labels_refresh(self):
        tmux = km._tmux_sessions()
        self.assertEqual(km._fleet_view_sig(0, tmux), km._fleet_view_sig(4, tmux), "same 5s bucket → cache hit")
        self.assertNotEqual(km._fleet_view_sig(0, tmux), km._fleet_view_sig(5, tmux), "next 5s bucket → refresh")

    def test_cached_feed_and_timeline_reuse_on_a_matching_sig(self):
        feed_save = (km._built_feed[0], km._built_feed[1])
        tl_save = (km._built_timeline[0], km._built_timeline[1])
        try:
            f_sentinel = {"type": "feed", "cards": [], "working": []}
            km._built_feed[0], km._built_feed[1] = ("SIG",), f_sentinel
            self.assertIs(km._cached_feed(0, {}, ("SIG",)), f_sentinel, "matching sig reuses, no rebuild")
            t_sentinel = {"type": "data"}
            km._built_timeline[0], km._built_timeline[1] = ("SIG",), t_sentinel
            self.assertIs(km._cached_timeline(0, {}, ("SIG",)), t_sentinel)
        finally:
            km._built_feed[0], km._built_feed[1] = feed_save
            km._built_timeline[0], km._built_timeline[1] = tl_save


if __name__ == "__main__":
    unittest.main()
