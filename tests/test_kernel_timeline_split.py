"""Timeline ships in TWO messages so the lanes paint before the heavy bars (the user 2026-06-25, "startup
still slow" → "load everything else and have the bars load after").

build_timeline(with_bars=False) builds only the LANES SKELETON (sessions/status, no turns/judging/messages/
nudges); _push sends it as {type:"data"} FIRST, then the cached full build's detail rides a {type:"bars"}
message. Profiling drove this: the timeline was 551ms/1940KB and ~95% of that is bars+judging, so the
skeleton is tiny and lands immediately. (The dead `tokens` field — nothing reads it — was dropped too.)
"""
import inspect
import json
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class BuildGating(unittest.TestCase):
    def test_build_timeline_gates_the_heavy_fields_on_with_bars(self):
        src = inspect.getsource(km.build_timeline)
        self.assertIn("with_bars=True", src, "the skeleton/bars switch")
        self.assertIn("if not with_bars:", src, "skeleton skips the per-segment bar dicts")
        self.assertIn("if with_bars:", src, "turns[sid] + judging + messages + nudges are gated")
        self.assertIn('"tokens": []', src, "the dead (unread) token-window field is no longer computed")

    def test_the_host_shim_routes_a_bars_message_to_applyBars(self):
        boot = km._TIMELINE_BOOT
        self.assertIn('m.type==="bars"', boot)
        self.assertIn("panel.applyBars(m)", boot)

    def test_the_lanes_skeleton_does_not_parse_any_transcript(self):
        # cold-start speed (the user 2026-06-26): a fresh kernel (the refresh button = POST /restart) re-parses
        # every transcript (~1.3s). The lanes don't need it — derive them from tmux + goals + the transcript
        # mtime. Only the {type:"bars"} build (with_bars=True) does the real parse.
        calls = {"parse": 0}
        o_ts, o_parse = km._timeline_sessions, km._parse
        km._timeline_sessions = lambda now, tmux: [{"sid": "S", "name": "n", "path": "/no/such/transcript"}]
        km._parse = lambda path, sid, now: (calls.__setitem__("parse", calls["parse"] + 1), {"turns": []})[1]
        try:
            km.build_timeline(0, {}, with_bars=False)
            self.assertEqual(calls["parse"], 0, "the lanes skeleton must NOT parse a transcript")
            km.build_timeline(0, {}, with_bars=True)
            self.assertGreater(calls["parse"], 0, "the bars build DOES parse")
        finally:
            km._timeline_sessions, km._parse = o_ts, o_parse


class PushSplit(unittest.TestCase):
    def test_push_ships_the_lanes_skeleton_before_the_bars(self):
        sent = []
        client = {"app": "timeline", "send": sent.append, "sent": {}, "alive": True}
        SKEL = {"type": "timeline", "sessions": [{"id": "S"}], "turns": {}, "judging": [],
                "messages": [], "nudges": [], "tokens": [], "now": 1, "usage": {}}
        FULL = {"type": "timeline", "sessions": [{"id": "S"}], "turns": {"S": [{"id": "b1"}]},
                "judging": [{"k": "planner"}], "messages": [{"m": 1}], "nudges": [{"n": 1}], "now": 1}
        o_bt, o_ct, o_tmux, o_sig = (km.build_timeline, km._cached_timeline,
                                     km._tmux_sessions, km._fleet_view_sig)
        km.build_timeline = lambda now, tmux, with_bars=True: (FULL if with_bars else SKEL)
        km._cached_timeline = lambda now, tmux, sig, connect=False: FULL
        km._tmux_sessions = lambda: {}
        km._fleet_view_sig = lambda now, tmux: ("sig",)
        try:
            km._push([client])
        finally:
            (km.build_timeline, km._cached_timeline,
             km._tmux_sessions, km._fleet_view_sig) = o_bt, o_ct, o_tmux, o_sig
        msgs = [json.loads(s) for s in sent]
        types = [m["type"] for m in msgs]
        self.assertIn("data", types)
        self.assertIn("bars", types)
        self.assertLess(types.index("data"), types.index("bars"), "lanes skeleton ships BEFORE the bars")
        skel = msgs[types.index("data")]["data"]
        self.assertEqual(skel["turns"], {}, "the {type:data} message is the lanes skeleton — no bars")
        bars = msgs[types.index("bars")]
        self.assertEqual(bars["turns"], {"S": [{"id": "b1"}]}, "the heavy bars ride the {type:bars} message")
        for k in ("judging", "messages", "nudges"):
            self.assertIn(k, bars, "the whole time-plotted detail rides the bars message")


if __name__ == "__main__":
    unittest.main()
