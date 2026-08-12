#!/usr/bin/env python3
"""WS heartbeat isolation (bin/romp-kernel). The keepalive must live on its OWN thread, not inside the
pusher loop: when the beat rode _pusher, a heavy _push_all() under GIL contention could stretch one loop
iteration past the shim's STALE_MS watchdog, and the client force-closed a healthy socket — the false
"disconnected / reconnecting" banner (2026-07-20). These tests pin (a) the beat arriving on cadence with
NO pusher running at all, (b) beats continuing while a push is wedged, and (c) the pusher no longer
carrying the beat inline (source pin, so a refactor can't quietly move it back).
"""
import inspect
import os
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_hb", os.path.join(BIN, "romp-kernel")).load_module()


class WsHeartbeat(unittest.TestCase):
    def setUp(self):
        self.saved_ka = km.KEEPALIVE_S
        with km._clients_lock:
            self.saved_clients = list(km._clients)
            km._clients[:] = []

    def tearDown(self):
        km.KEEPALIVE_S = self.saved_ka
        with km._clients_lock:
            km._clients[:] = self.saved_clients

    def _fake_client(self):
        frames = []
        client = {"app": "feed", "send": frames.append, "alive": True}
        with km._clients_lock:
            km._clients.append(client)
        return frames

    def test_beat_arrives_without_any_pusher(self):
        # The heartbeat thread alone (no _pusher running) must deliver ka frames on cadence —
        # proof the beat no longer depends on pusher loop iterations.
        frames = self._fake_client()
        km.KEEPALIVE_S = 0.05
        threading.Thread(target=km._heartbeat, daemon=True).start()
        deadline = time.time() + 3.0
        while time.time() < deadline and len(frames) < 3:
            time.sleep(0.02)
        self.assertGreaterEqual(len(frames), 3, "heartbeat thread must beat on its own cadence")
        self.assertIn('"type": "ka"', frames[0])

    def test_beat_survives_a_wedged_push(self):
        # The failure mode behind the false banner, end to end: the REAL _pusher loop enters a push
        # that never finishes (stand-in for a heavy fleet build under GIL contention). The beat must
        # keep flowing anyway. _push_all stays wedged for the process lifetime on purpose — restoring
        # it would let the leaked daemon pusher run real tick jobs against live tmux mid-test-run.
        frames = self._fake_client()
        km.KEEPALIVE_S = 0.05
        wedge = threading.Event()                       # never set → the push never returns
        km._push_all = lambda *a, **k: wedge.wait()   # accepts the cycle's snapshot kwarg
        threading.Thread(target=km._pusher, daemon=True).start()
        threading.Thread(target=km._heartbeat, daemon=True).start()
        deadline = time.time() + 3.0
        while time.time() < deadline and len(frames) < 3:
            time.sleep(0.02)
        self.assertGreaterEqual(len(frames), 3, "a wedged push must not starve the keepalive")

    def test_pusher_no_longer_beats_inline(self):
        # Source pin: the pusher loop must not call the keepalive — if it ever grows one back, the
        # slow-iteration starvation returns. The beat belongs to _heartbeat exclusively.
        self.assertNotIn("_keepalive_all", inspect.getsource(km._pusher),
                         "the WS keepalive must live on the _heartbeat thread, not in _pusher")
        self.assertIn("_keepalive_all", inspect.getsource(km._heartbeat))

    def test_dead_client_is_flagged_not_fatal(self):
        # A client whose socket raises on send must be flagged dead without killing the beat for others.
        bad = {"app": "feed", "send": self._boom, "alive": True}
        with km._clients_lock:
            km._clients.append(bad)
        frames = self._fake_client()   # healthy client AFTER the bad one → send order hits bad first
        km._keepalive_all()
        self.assertFalse(bad["alive"], "a failing send must flag the client dead")
        # >= 1, not == 1: leaked heartbeat threads from earlier tests may land a stray (identical) beat
        self.assertGreaterEqual(len(frames), 1, "a bad client must not block the beat to healthy ones")

    @staticmethod
    def _boom(_s):
        raise BrokenPipeError("socket gone")


if __name__ == "__main__":
    unittest.main()
