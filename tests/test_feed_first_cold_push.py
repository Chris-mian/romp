#!/usr/bin/env python3
"""Cards first on a cold kernel (2026-09-12): the first push after a boot sends the feed frame to the feed panes before
it builds the chat pages and the timeline; a warm kernel takes no extra step. Hermetic: a temp state root, stubbed
builders, fake clients; no kernel, no sessions."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_tmp_state = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _tmp_state
os.environ["ROMP_STATE_DIR"] = os.path.join(_tmp_state, "romp")
from romp_load import load_source   # noqa: E402

BIN = os.path.join(os.path.dirname(HERE), "bin")
km = load_source("romp_kernel_feed_first", os.path.join(BIN, "romp-kernel"))

S1 = "77777777-1111-2222-3333-444444444401"
S2 = "77777777-1111-2222-3333-444444444402"
FEED = {"type": "feed", "asks": [{"itemId": "g1", "sid": S1, "title": "a card"}], "working": ["web"], "awaiting": []}


def _sess(sid, state):
    """A synthetic build_session payload in the shape the push's chat send expects (the skeleton test's stub)."""
    return {"type": "session", "id": sid, "name": "web" if sid == S1 else "api",
            "events": [{"kind": "assistant", "uuid": "u%d" % i, "md": "m%d" % i} for i in range(3)],
            "status": {"state": state, "sinceEpoch": None}, "ledger": None}


class FeedFirstColdPush(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid in (S1, S2):
            p = os.path.join(self.tmp, sid + ".jsonl"); open(p, "w").write("x" * 10); self.paths[sid] = p
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame,
                       km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients), list(km._built_feed), km._feed_wire,
                       dict(km._wire_stats))
        km._chat_tab_sessions = lambda now, live_map: [{"sid": s, "name": _sess(s, "working")["name"], "path": self.paths[s], "anchor": s} for s in (S1, S2)]
        km._live_map = lambda: {}
        self.seq = []                                        # every frame every client receives, in send order
        self.feed_calls = []
        def cached_feed(now, live_map, sig, connect=False):
            self.feed_calls.append(connect)
            return json.loads(json.dumps(FEED))
        km._cached_feed = cached_feed
        def build(sid, now, live_map=None, **kw):
            self.seq.append(("build", sid))
            return json.loads(json.dumps(_sess(sid, "working")))
        km.build_session = build
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"; km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"; km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear(); del km._clients[:]
        km._built_feed[:] = [None, None, 0.0, 0.0]
        km._feed_wire = None
        self._marks, self._cycles = dict(km._BOOT_MARKS), km._PERF_STATS.pusher.get("cycles", 0)
        km._BOOT_MARKS["firstServe"] = 1.0                   # a kernel that is serving, in its first pusher cycle
        with km._PERF_STATS.lock:
            km._PERF_STATS.pusher["cycles"] = 0
        for k in km._wire_stats:
            km._wire_stats[k] = 0

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame, km._push_subagents,
         km.NAMES, km.jd.STATE, clients, built_feed, km._feed_wire, stats) = self._saved
        del km._clients[:]; km._clients.extend(clients)
        km._built_feed[:] = built_feed
        km._wire_stats.update(stats)
        km._built_chat.clear()
        km._BOOT_MARKS.clear(); km._BOOT_MARKS.update(self._marks)
        with km._PERF_STATS.lock:
            km._PERF_STATS.pusher["cycles"] = self._cycles

    def _client(self, app):
        c = {"app": app, "alive": True, "sent": {}}
        c["send"] = lambda s, c=c: self.seq.append((c["app"], json.loads(s).get("type")))
        return c

    def test_a_cold_kernels_first_push_sends_the_feed_before_any_chat_build(self):
        feed_c, chat_c = self._client("feed"), self._client("chat")
        km._push([feed_c, chat_c])
        kinds = [(a, t) for a, t in self.seq]
        first_feed = kinds.index(("feed", "feed"))
        first_build = kinds.index(("build", S1)) if ("build", S1) in kinds else kinds.index(("build", S2))
        self.assertLess(first_feed, first_build, "the feed frame leaves before the first chat page is built: %r" % kinds)
        self.assertEqual(km._wire_stats["feed_first"], 1)
        self.assertEqual(self.feed_calls[0], False, "the early build is the cycle's own, not a connect serve")

    def test_a_connect_push_during_the_first_cycle_builds_the_feed_too(self):
        # the realistic boot: the browser reconnects a moment after the kernel serves, so the first push with a feed pane is the
        # connect push; the connect arm of the cache serves only a warmed build, which a cold kernel has not got
        feed_c = self._client("feed")
        km._push([feed_c], connect=True)
        self.assertEqual(km._wire_stats["feed_first"], 1, "the early pass ran on the connect push")
        self.assertEqual(self.feed_calls[0], False, "and it BUILT (connect False to the cache), rather than serving a warmed build it has not got")
        self.assertIn(("feed", "feed"), self.seq)

    def test_a_warm_kernel_takes_no_extra_step(self):
        feed_c, chat_c = self._client("feed"), self._client("chat")
        km._built_feed[1] = json.loads(json.dumps(FEED))          # a feed already built since start
        km._push([feed_c, chat_c])
        self.assertEqual(km._wire_stats["feed_first"], 0, "no early pass on a warm kernel")
        self.assertIn(("feed", "feed"), self.seq, "the regular feed section still serves the pane: %r" % self.seq)

    def test_a_later_cycle_takes_no_extra_step(self):
        with km._PERF_STATS.lock:
            km._PERF_STATS.pusher["cycles"] = 1
        km._push([self._client("feed"), self._client("chat")])
        self.assertEqual(km._wire_stats["feed_first"], 0, "only the boot's first cycle sends the feed first")

    def test_no_feed_pane_means_no_early_pass(self):
        chat_c = self._client("chat")
        km._push([chat_c])
        self.assertEqual(km._wire_stats["feed_first"], 0)

    def test_the_early_pass_precedes_the_chat_section_in_the_source(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        push = src[src.index("def _push(targets, connect=False, live_map=None):"):]
        self.assertLess(push.index("_feed_first(now, live_map, targets, connect)"), push.index("chat_list = _chat_tab_sessions(now, live_map)"))


if __name__ == "__main__":
    unittest.main()
