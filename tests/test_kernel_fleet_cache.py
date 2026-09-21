"""Feed + timeline are EXPENSIVE to build (re-segment every session ~2.7s) and were rebuilt on EVERY push,
so a reload/idle tick paid the full cost (the user 2026-06-25, who found reload/startup still very slow). They're
now cached, keyed on a fleet fingerprint that busts on any transcript/states/postal change, a judge pass, a
live badge change, a colormap/session-flags change, or a 5s time bucket (so age labels keep advancing).
"""
import os
import time
import unittest
from unittest import mock
from romp_load import load_source
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))


class FleetCacheTest(unittest.TestCase):
    def test_sig_is_stable_when_nothing_changes(self):
        now, live_map = int(time.time()), km._live_map()
        self.assertEqual(km._fleet_view_sig(now, live_map), km._fleet_view_sig(now, live_map))

    def test_sig_busts_on_a_judge_pass(self):
        now, live_map = int(time.time()), km._live_map()
        a = km._fleet_view_sig(now, live_map)
        km._judge_gen[0] += 1
        try:
            self.assertNotEqual(a, km._fleet_view_sig(now, live_map), "a judge pass must rebuild the views")
        finally:
            km._judge_gen[0] -= 1

    def test_time_bucket_advances_so_age_labels_refresh(self):
        live_map = km._live_map()
        self.assertEqual(km._fleet_view_sig(0, live_map), km._fleet_view_sig(4, live_map), "same 5s bucket → cache hit")
        self.assertNotEqual(km._fleet_view_sig(0, live_map), km._fleet_view_sig(5, live_map), "next 5s bucket → refresh")

    def test_cached_feed_and_timeline_reuse_on_a_matching_sig(self):
        feed_save = list(km._built_feed)
        tl_save = list(km._built_timeline)
        dirty_save = km._views_dirty[0]
        try:
            km._views_dirty[0] = 0.0
            f_sentinel = {"type": "feed", "cards": [], "working": []}
            km._built_feed[:] = [("SIG",), f_sentinel, time.time(), time.time()]
            self.assertIs(km._cached_feed(0, {}, ("SIG",)), f_sentinel, "matching sig reuses, no rebuild")
            t_sentinel = {"type": "data"}
            km._built_timeline[:] = [("SIG",), t_sentinel, time.time(), time.time()]
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
            km._built_feed[:] = [("SIG",), f_stale, time.time(), time.time()]   # fresh build: same sig AND inside REBUILD_MIN_S
            km._mark_views_dirty()                                 # the mutation lands after the build
            got = km._cached_feed(int(time.time()), {}, ("SIG",))
            self.assertIsNot(got, f_stale, "a dirty mark newer than the build must force a rebuild")
        finally:
            km._built_feed[:] = feed_save
            km._views_dirty[0] = dirty_save

    def test_a_dirty_mark_in_the_same_clock_tick_as_the_build_still_busts_the_cache(self):
        """2026-09-16 (the macOS CI leg, and any fast box): the build's start stamp and the dirty mark are both wall stamps,
        and the strict compare served the stale payload when the two landed in one clock tick. The rule is one function,
        _dirty_since, with `>=`; forced here by pinning the clock to one value for the build and the mark, never by sleeping."""
        feed_save = list(km._built_feed)
        dirty_save = km._views_dirty[0]
        try:
            T = 1789500000.123456
            f_stale = {"type": "feed", "cards": ["stale"]}
            with mock.patch.object(km.time, "time", return_value=T):
                km._built_feed[:] = [("SIG",), f_stale, km.time.time(), km.time.time()]   # a build stamped at T
                km._mark_views_dirty()                                                    # the mutation lands at T as well
                self.assertEqual(km._views_dirty[0], km._built_feed[3], "the mark and the start share one tick")
                got = km._cached_feed(int(T), {}, ("SIG",))
            self.assertIsNot(got, f_stale, "a dirty mark in the build's own tick must force a rebuild (the base served the stale payload)")
            with mock.patch.object(km.time, "time", return_value=T):                      # the rule and the pusher's gate, at the head
                km._built_feed[:] = [("SIG",), f_stale, km.time.time(), km.time.time()]
                km._mark_views_dirty()
                self.assertTrue(km._dirty_since(km._built_feed[3]), "an equal tick is not older than the build's read")
                self.assertFalse(km._feed_servable(("SIG",), False), "the pusher's cache does not serve it")
        finally:
            km._built_feed[:] = feed_save
            km._views_dirty[0] = dirty_save

    def test_the_timeline_pure_feed_and_thread_caches_ask_the_same_rule(self):
        """The census of every dirty-mark compare against a build's start: four sites, one rule (_dirty_since); the timeline
        driven at an equal tick, the other two pinned on the call."""
        import inspect
        tl_save = list(km._built_timeline); dirty_save = km._views_dirty[0]
        try:
            T = 1789500000.5
            km._built_timeline[:] = [("SIG",), {"type": "timeline"}, T, T]
            km._views_dirty[0] = T
            self.assertFalse(km._timeline_cache_fresh(("SIG",)), "a timeline built in the mark's tick is not fresh (the base served it)")
            km._views_dirty[0] = T - 1e-6
            self.assertTrue(km._timeline_cache_fresh(("SIG",)), "a mark older than the start leaves the build fresh")
        finally:
            km._built_timeline[:] = tl_save; km._views_dirty[0] = dirty_save
        self.assertIn("return _views_dirty[0] >= started", inspect.getsource(km._dirty_since))
        for fn, call in ((km._feed_servable, "_dirty_since(e[3])"), (km._timeline_cache_fresh, "_dirty_since(e[3])"),
                         (km._pure_feed, "_dirty_since(pf[2])")):
            self.assertIn(call, inspect.getsource(fn), fn.__name__)
        src = open(km.__file__).read()
        self.assertIn("and not _dirty_since(hit[3]):", src, "the thread cache")
        self.assertNotIn("_views_dirty[0] > ", src, "no strict compare against the mark survives")
        self.assertNotIn("_views_dirty[0] <= ", src)

    def test_the_pure_feed_rebuilds_at_an_equal_tick(self):
        """GET /feed.json's own copy (_PURE_FEED) asks the same rule: a mark in its build's tick busts it (round two: driven,
        not only pinned). The pusher has no audience, the signature stands and the clock is inside the rebuild floor, so the
        dirty rule is the only thing that can bust the copy."""
        T = 1789500001.25
        stale = {"type": "feed", "cards": ["stale"]}
        saved = (km._PURE_FEED, km._views_dirty[0], km._pusher_has_feed_audience, km._fleet_view_sig, km.build_feed, km._task_tracking_on)
        try:
            km._pusher_has_feed_audience = lambda: False
            km._fleet_view_sig = lambda now, live_map: ("SIG",)
            km.build_feed = lambda now, live_map=None: {"type": "feed", "cards": []}
            km._task_tracking_on = lambda: True
            with mock.patch.object(km.time, "time", return_value=T):
                km._PURE_FEED = (stale, km.time.time(), km.time.time(), ("SIG",))     # a copy built and finished at T
                km._views_dirty[0] = km.time.time()                                   # the mutation lands at T
                got = km._pure_feed(int(T), {})
            self.assertIsNot(got, stale, "the GET copy built in the mark's tick is rebuilt, never served (the base served it)")
            self.assertEqual(got.get("cards"), [])
        finally:
            (km._PURE_FEED, km._views_dirty[0], km._pusher_has_feed_audience, km._fleet_view_sig, km.build_feed, km._task_tracking_on) = saved

    def test_the_thread_cache_misses_at_an_equal_tick(self):
        """The comment-thread cache (_built_thread) asks the same rule (round two: driven). Its key is stubbed to a constant so
        the only question left is the mark against the entry's start stamp; a miss rebuilds through build_session (stubbed)."""
        T = 1789500002.5
        tsid = "77777777-2222-4333-8444-000000000777"
        saved = (dict(km._built_thread), km._views_dirty[0], km._thread_reg, km._sdk_sess, km._chat_build_sig, km._chat_sig_ok,
                 km.build_session, km._comment_thread_row_created)
        try:
            km._thread_reg = lambda t: {}
            km._sdk_sess = lambda t, now: object()
            km._chat_build_sig = lambda *a, **k: ("SIG",)
            km._chat_sig_ok = lambda t: None
            km.build_session = lambda t, now, live_map=None: {"events": [{"uuid": "fresh"}]}
            km._comment_thread_row_created = lambda t: 0
            key = ("SIG", None)                                                     # the stubbed signature plus no states row
            with mock.patch.object(km.time, "time", return_value=T):
                km._built_thread[tsid] = (key, None, [{"uuid": "stale"}], km.time.time())   # an entry whose build started at T
                km._views_dirty[0] = km.time.time()                                        # the mutation lands at T
                got = km._thread_events(tsid, None, int(T), {})
            self.assertEqual(got, [{"uuid": "fresh"}], "an entry built in the mark's tick is a miss, rebuilt (the base served the stale events)")
            km._views_dirty[0] = T - 1e-6
            self.assertEqual(km._thread_events(tsid, None, int(T), {}), [{"uuid": "fresh"}], "a mark older than the start serves the (now fresh) entry")
        finally:
            km._built_thread.clear(); km._built_thread.update(saved[0])
            (km._views_dirty[0], km._thread_reg, km._sdk_sess, km._chat_build_sig, km._chat_sig_ok, km.build_session, km._comment_thread_row_created) = saved[1:]

    def test_a_mutation_landing_mid_build_is_not_swallowed_by_that_build(self):
        """A build takes ~1-1.6s and reads the stores one session at a time, so a mutation landing
        MID-build may or may not have been read — its payload can predate the gesture while its finish
        postdates it. The dirty floor therefore keys on the build's START: comparing against the finish
        swallowed exactly that case (the user 2026-07-28: a reply landed while a build was in flight,
        the reply's dirty mark lost to that build's completion, and the pre-reply payload — the card
        still Completed — was re-served until the next sig bust, the window a client fallback needs to
        bounce a just-replied card back to Completed)."""
        feed_save = list(km._built_feed)
        dirty_save = km._views_dirty[0]
        real_build = km.build_feed
        def build_with_midflight_reply(now, live_map):
            time.sleep(0.005)                         # a real build runs ~1s; keep the mark measurably
            km._mark_views_dirty()                    # past the start stamp, then: the reply lands while
            return {"type": "feed", "cards": []}      # this build is mid-read. fresh dict → `is` tells builds apart
        try:
            km._views_dirty[0] = 0.0
            km._built_feed[:] = [None, None, 0.0, 0.0]
            km.build_feed = build_with_midflight_reply
            f1 = km._cached_feed(int(time.time()), {}, ("SIG",))
            km.build_feed = lambda now, live_map: {"type": "feed", "cards": []}
            f2 = km._cached_feed(int(time.time()), {}, ("SIG",))
            self.assertIsNot(f2, f1, "a mark set during the build postdates its start → must rebuild")
            f3 = km._cached_feed(int(time.time()), {}, ("SIG",))
            self.assertIs(f3, f2, "the mark predates the SECOND build's start → reuse, no rebuild loop")
        finally:
            km.build_feed = real_build
            km._built_feed[:] = feed_save
            km._views_dirty[0] = dirty_save

    def test_a_connect_still_serves_the_warmed_build_even_when_dirty(self):
        """connect NEVER rebuilds (instant reload is the contract) — the pusher's next tick, woken by
        _mark_views_dirty itself, refreshes the view for everyone within a beat."""
        feed_save = list(km._built_feed)
        dirty_save = km._views_dirty[0]
        try:
            f_warm = {"type": "feed", "cards": ["warm"]}
            km._built_feed[:] = [("OLD",), f_warm, time.time(), time.time()]
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
