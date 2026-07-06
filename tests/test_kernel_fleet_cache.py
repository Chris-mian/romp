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
        feed_save = list(km._built_feed)
        tl_save = list(km._built_timeline)
        dirty_save = km._views_dirty[0]
        try:
            km._views_dirty[0] = 0.0
            f_sentinel = {"type": "feed", "cards": [], "working": []}
            km._built_feed[:] = [("SIG",), f_sentinel, time.time()]
            self.assertIs(km._cached_feed(0, {}, ("SIG",)), f_sentinel, "matching sig reuses, no rebuild")
            t_sentinel = {"type": "data"}
            km._built_timeline[:] = [("SIG",), t_sentinel, time.time()]
            self.assertIs(km._cached_timeline(0, {}, ("SIG",)), t_sentinel)
        finally:
            km._built_feed[:] = feed_save
            km._built_timeline[:] = tl_save
            km._views_dirty[0] = dirty_save

    def test_views_dirty_mark_busts_the_cache_past_sig_and_throttle(self):
        """An optimistic kernel-side mutation (a parked-op chip, a follow-up reopen, a clear, a
        model-pending stamp) lives in memory or a goal store — NO file-mtime signature sees it, and the
        REBUILD_MIN_S throttle would otherwise serve the stale pre-change payload on the very push meant
        to show it (the user 2026-07-05: a reply on a distilled card lagged its move to Working)."""
        feed_save = list(km._built_feed)
        dirty_save = km._views_dirty[0]
        try:
            f_stale = {"type": "feed", "cards": ["stale"]}
            km._built_feed[:] = [("SIG",), f_stale, time.time()]   # fresh build: same sig AND inside REBUILD_MIN_S
            km._mark_views_dirty()                                 # the mutation lands after the build
            got = km._cached_feed(int(time.time()), {}, ("SIG",))
            self.assertIsNot(got, f_stale, "a dirty mark newer than the build must force a rebuild")
        finally:
            km._built_feed[:] = feed_save
            km._views_dirty[0] = dirty_save

    def test_a_connect_still_serves_the_warmed_build_even_when_dirty(self):
        """connect NEVER rebuilds (instant reload is the contract) — the pusher's next tick, woken by
        _mark_views_dirty itself, refreshes the view for everyone within a beat."""
        feed_save = list(km._built_feed)
        dirty_save = km._views_dirty[0]
        try:
            f_warm = {"type": "feed", "cards": ["warm"]}
            km._built_feed[:] = [("OLD",), f_warm, time.time()]
            km._mark_views_dirty()
            self.assertIs(km._cached_feed(int(time.time()), {}, ("NEW",), connect=True), f_warm)
        finally:
            km._built_feed[:] = feed_save
            km._views_dirty[0] = dirty_save

    def test_mark_views_dirty_wakes_the_pusher(self):
        km._pusher_wake.clear()
        try:
            km._mark_views_dirty()
            self.assertTrue(km._pusher_wake.is_set(), "the dirty mark must also wake the pusher NOW")
        finally:
            km._pusher_wake.clear()


if __name__ == "__main__":
    unittest.main()
