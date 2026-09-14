#!/usr/bin/env python3
"""Single-flight builds (2026-09-14). At the first browser-attached boot on the cards-first code (12:06 PM PT) every pane's
socket redialed after the outage and each connect push built its own copy of the same cold work on its handler thread while
the pusher built it too: five to seven cold builders of one feed, one timeline and the same chat tabs on one interpreter,
each five to seven times slower for it (push.feedFirst 106 s, connect pushes 109 to 130 s, cards at 131 s). Now a feed or
timeline build in flight on one thread is the build every later caller serves (one lock each), the connect path's live-only
timeline waits for a full build in flight instead of parsing beside it, and a chat tab in flight on another thread is waited
for and re-read from the cache. Hermetic: the builders are stubbed to sleep and count; two threads race each call."""
import inspect
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_single_flight", os.path.join(BIN, "romp-kernel"))

S1 = "11111111-2222-3333-4444-777777777771"
S2 = "11111111-2222-3333-4444-777777777772"
NAMES = {S1: "web", S2: "api"}
FEED = {"type": "feed", "asks": [], "working": [], "awaiting": []}


def _race(fn, n=2):
    """Run `fn` on n threads at once; return their results in start order."""
    out = [None] * n
    go = threading.Event()
    def run(i):
        go.wait(); out[i] = fn()
    ths = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ths: t.start()
    go.set()
    for t in ths: t.join(20)
    return out


class FeedAndTimelineSingleFlight(unittest.TestCase):
    def setUp(self):
        self.saved = (km.build_feed, km.build_timeline, list(km._built_feed), list(km._built_timeline), km._views_dirty[0],
                      dict(km._VIEW_STATS))
        km._built_feed[:] = [None, None, 0.0, 0.0]
        km._built_timeline[:] = [None, None, 0.0, 0.0]
        km._views_dirty[0] = 0.0
        self.builds = []
        def feed(now, live_map):
            self.builds.append("feed"); time.sleep(0.3); return json.loads(json.dumps(FEED))
        def timeline(now, live_map, with_bars=True, live_only=False):
            self.builds.append("tl:%s" % ("live" if live_only else "full")); time.sleep(0.3)
            return {"lanes": [], "turns": {}, "judging": {}, "messages": [], "now": now}
        km.build_feed, km.build_timeline = feed, timeline
        km._PERF_STATS.reset()

    def tearDown(self):
        (km.build_feed, km.build_timeline, bf, bt, km._views_dirty[0], vs) = self.saved
        km._built_feed[:] = bf; km._built_timeline[:] = bt
        km._VIEW_STATS.clear(); km._VIEW_STATS.update(vs)
        km._PERF_STATS.reset()

    def test_two_cold_feed_callers_build_once_and_both_get_the_frame(self):
        now = int(time.time())
        with mock.patch.object(km, "_task_tracking_on", lambda: True):
            got = _race(lambda: km._cached_feed(now, {}, ("sig",), False))
        self.assertEqual(self.builds, ["feed"], "one build for two racing callers: %r" % self.builds)
        self.assertTrue(all(g and g.get("type") == "feed" for g in got), got)
        self.assertEqual(km._VIEW_STATS["feedWaited"], 1, "the second caller waited for the first's build and served it")
        b = km._PERF_STATS.snapshot()["builds"]["feed"]
        self.assertEqual((b["cached"], b["built"]), (1, 1))

    def test_a_connect_caller_racing_the_pushers_cold_feed_build_serves_it(self):
        now = int(time.time())
        with mock.patch.object(km, "_task_tracking_on", lambda: True):
            got = _race(lambda: km._cached_feed(now, {}, ("sig",), False), n=1) + \
                  _race(lambda: km._cached_feed(now, {}, ("other",), True), n=1)   # sequential here; the race is below
        self.assertEqual(self.builds, ["feed"], "a connect never rebuilds a warmed feed: %r" % self.builds)
        del self.builds[:]
        km._built_feed[:] = [None, None, 0.0, 0.0]
        with mock.patch.object(km, "_task_tracking_on", lambda: True):
            fns = [lambda: km._cached_feed(now, {}, ("sig",), False), lambda: km._cached_feed(now, {}, ("other",), True)]
            out = [None, None]; go = threading.Event()
            def run(i):
                go.wait(); out[i] = fns[i]()
            ths = [threading.Thread(target=run, args=(i,)) for i in range(2)]
            for t in ths: t.start()
            go.set()
            for t in ths: t.join(20)
        self.assertEqual(self.builds, ["feed"], "the cold connect waited for the pusher's build (or the pusher for the connect's): %r" % self.builds)
        self.assertTrue(all(o and o.get("type") == "feed" for o in out))

    def test_two_cold_timeline_callers_build_once(self):
        now = int(time.time())
        got = _race(lambda: km._cached_timeline(now, {}, ("sig",), False))
        self.assertEqual(self.builds, ["tl:full"], self.builds)
        self.assertTrue(all(g and "lanes" in g for g in got))
        self.assertEqual(km._VIEW_STATS["tlWaited"], 1)

    def test_a_dirty_mark_after_the_build_still_rebuilds_for_the_pusher(self):
        now = int(time.time())
        with mock.patch.object(km, "_task_tracking_on", lambda: True):
            km._cached_feed(now, {}, ("sig",), False)
            km._views_dirty[0] = time.time() + 1          # a kernel-side mutation after the build's start
            km._cached_feed(now, {}, ("sig",), False)
        self.assertEqual(self.builds, ["feed", "feed"], "the lock is single-flight, not a cache: a dirty pusher call rebuilds")

    def test_the_locks_are_reentrant_and_named(self):
        self.assertTrue(km._FEED_BUILD_LOCK.acquire(blocking=False)); self.assertTrue(km._FEED_BUILD_LOCK.acquire(blocking=False))
        km._FEED_BUILD_LOCK.release(); km._FEED_BUILD_LOCK.release()
        src = inspect.getsource(km._cached_feed)
        self.assertIn("with _FEED_BUILD_LOCK:", src)
        self.assertIn("with _TL_BUILD_LOCK:", inspect.getsource(km._cached_timeline))
        push = inspect.getsource(km._push)
        self.assertIn("with _TL_BUILD_LOCK:", push, "the connect path's live-only timeline waits for a full build in flight")
        self.assertLess(push.index("with _TL_BUILD_LOCK:"), push.index("if not live_first:"))


class ChatTabSingleFlight(unittest.TestCase):
    """The pusher's push and a connect push building the same cold tab at once: one build, the second serves the cache."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid in (S1, S2):
            p = os.path.join(self.tmp, sid + ".jsonl"); open(p, "w").write("x" * 100); self.paths[sid] = p
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame,
                       km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients), dict(km._VIEW_STATS))
        km._chat_tab_sessions = lambda now, live_map: [{"sid": s, "name": NAMES[s], "path": self.paths[s], "anchor": s} for s in (S1, S2)]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None
        self.builds = []
        self.lock = threading.Lock()
        def build(sid, now, live_map=None, **kw):
            with self.lock:
                self.builds.append(sid)
            time.sleep(0.4)
            return {"type": "session", "id": sid, "name": NAMES[sid],
                    "events": [{"kind": "assistant", "uuid": "u1", "md": "m1"}], "status": {"state": "working", "sinceEpoch": None}, "ledger": None}
        km.build_session = build
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"; km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"; km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        del km._clients[:]
        km._CHAT_INFLIGHT.clear()

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame, km._push_subagents,
         km.NAMES, km.jd.STATE, clients, vs) = self._saved
        del km._clients[:]; km._clients.extend(clients)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        km._VIEW_STATS.clear(); km._VIEW_STATS.update(vs)
        km._CHAT_INFLIGHT.clear()

    def _client(self, **kw):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)), "_frames": frames,
             "ready": True, "proto": 2}
        c.update(kw)
        return c

    def test_a_connect_push_racing_the_cycle_builds_each_tab_once(self):
        a, b = self._client(active=S1), self._client(active=S1)
        km._clients[:] = [a, b]
        w0 = km._VIEW_STATS["chatWaited"]
        _race_fns = [lambda: km._push([a, b]), lambda: km._push([b], connect=True)]
        go = threading.Event()
        def run(i):
            go.wait(); _race_fns[i]()
        ths = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in ths: t.start()
        go.set()
        for t in ths: t.join(30)
        self.assertEqual(sorted(self.builds), [S1, S2], "each tab built once across the two pushes: %r" % self.builds)
        self.assertGreaterEqual(km._VIEW_STATS["chatWaited"] - w0, 1, "the later push waited and served the cache")
        self.assertEqual({f["id"] for f in b["_frames"] if f["type"] == "session"}, {S1, S2}, "the connect client still got both tabs")
        self.assertEqual(km._CHAT_INFLIGHT, {}, "no claim left behind")

    def test_a_failing_build_releases_its_waiters(self):
        a = self._client(active=S1)
        km._clients[:] = [a]
        def boom(sid, now, live_map=None, **kw):
            with self.lock:
                self.builds.append(sid)
            time.sleep(0.2); raise RuntimeError("read failed")
        km.build_session = boom
        with mock.patch.object(km, "CHAT_INFLIGHT_WAIT_S", 5.0), mock.patch.object(km.sys, "stderr", mock.Mock()):
            t0 = time.monotonic()
            go = threading.Event()
            def run():
                go.wait(); km._push([a])
            ths = [threading.Thread(target=run) for _ in range(2)]
            for t in ths: t.start()
            go.set()
            for t in ths: t.join(30)
            dt = time.monotonic() - t0
        self.assertLess(dt, 4.0, "the waiter was released by the failing builder, not by the bound: %.1f s" % dt)
        self.assertEqual(km._CHAT_INFLIGHT, {}, "no claim left behind")


if __name__ == "__main__":
    unittest.main()
