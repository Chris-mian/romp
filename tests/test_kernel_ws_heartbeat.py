#!/usr/bin/env python3
"""WS heartbeat + client staleness watchdog (the user 2026-06-29). The pusher DEDUPS, so a quiet fleet sends
no view frames; a client whose socket goes SILENTLY half-open (TCP dead, no onclose) then receives nothing and
never recovers — the feed froze on stale cards (a 'blocked in picker' card that the session had long left)
until a manual reload. Fix: the kernel sends a tiny 'ka' keepalive to every client on a fixed cadence, and the
page shim stamps lastRecv on every frame + a watchdog force-reconnects (→ reload-resync) when it stops arriving.

Synthetic only — no real session data.
"""
import json
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

KSRC = open(os.path.join(BIN, "romp-kernel"), encoding="utf-8").read()


class Keepalive(unittest.TestCase):
    def setUp(self):
        self._saved = list(km._clients)

    def tearDown(self):
        km._clients[:] = self._saved

    def test_keepalive_sends_a_ka_frame_to_every_client(self):
        got_a, got_b = [], []
        km._clients[:] = [
            {"app": "feed", "wid": "", "send": got_a.append, "alive": True},
            {"app": "timeline", "wid": "", "send": got_b.append, "alive": True},
        ]
        km._keepalive_all()
        self.assertEqual([json.loads(x) for x in got_a], [{"type": "ka"}], "feed client got one keepalive")
        self.assertEqual([json.loads(x) for x in got_b], [{"type": "ka"}], "timeline client too — every app, not just one")

    def test_keepalive_marks_a_broken_client_not_alive(self):
        def boom(_s):
            raise OSError("broken pipe")
        c = {"app": "feed", "wid": "", "send": boom, "alive": True}
        km._clients[:] = [c]
        km._keepalive_all()                              # must not raise; a dead socket is flagged for reaping
        self.assertFalse(c["alive"], "a send failure marks the client dead (reaped by the pusher), not crash the loop")


class ShimWatchdogSourcePins(unittest.TestCase):
    # Source-level pins: the shim JS is embedded in the kernel and not unit-runnable here, so assert the
    # heartbeat/watchdog wiring is present (mirrors the chat-compacting-icon source-pin style).
    def test_pusher_emits_a_periodic_keepalive(self):
        self.assertIn("KEEPALIVE_S", KSRC)
        self.assertIn("_keepalive_all()", KSRC)
        self.assertIn("_last_keepalive", KSRC)

    def test_both_shims_stamp_lastrecv_and_watchdog_reconnect(self):
        # _shim (feed/chat/fleet) AND the timeline inline shim each declare lastRecv + STALE_MS ...
        self.assertGreaterEqual(KSRC.count("var lastRecv=0;var STALE_MS=30000;"), 2)
        # ... stamp it on every frame ...
        self.assertGreaterEqual(KSRC.count("lastRecv=Date.now()"), 4)   # onopen + onmessage in each of the two shims
        # ... and force-close a stale-but-open socket so onclose → reconnect → reload fires.
        self.assertGreaterEqual(KSRC.count("Date.now()-lastRecv>STALE_MS"), 2)

    def test_shim_ignores_the_keepalive_frame(self):
        self.assertIn('if(msg&&msg.type==="ka")return;', KSRC)


if __name__ == "__main__":
    unittest.main()
