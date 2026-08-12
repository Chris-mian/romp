#!/usr/bin/env python3
"""The bus's lifetime follows the MACHINE's romp role, not just local sessions. A quiet hub —
kernel up, zero local sessions — self-stopped on the local-session count alone, and every
cross-host message through it silently parked until a manual `ensure` (verified twice,
2026-08-12): peers dial a machine's bus for presence and INBOUND mail, so it must keep listening
while the kernel runs. Two guards land here:

- bus: the autostop gate (_idle_tick) counts a live local kernel (_kernel_up, /healthz) as a
  reason to stay, alongside local clients. No kernel and no clients → the old self-stop.
- kernel: a REFUSED bus notify kicks _revive_postal_bus (single-flight ensure) — boot-time ensure
  can't help a kernel that is already up when its bus dies, and the supervisor otherwise retried
  into the dead bus forever.

Synthetic everything: hermetic state dir, stub HTTP server for the kernel, dead ports, no ssh.
"""
import http.server
import os
import socket
import tempfile
import threading
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
pm = SourceFileLoader("romp_postal_buslife", os.path.join(BIN, "romp-postal-service")).load_module()
km = SourceFileLoader("romp_kernel_buslife", os.path.join(BIN, "romp-kernel")).load_module()


def _dead_port():
    """A port with nothing listening: bind, read it, close — refused instantly afterwards."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _HealthzStub:
    """A minimal kernel: answers /healthz 200, everything else 404."""

    def __enter__(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                ok = self.path == "/healthz"
                self.send_response(200 if ok else 404)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % self.srv.server_port

    def __exit__(self, *a):
        self.srv.shutdown()


class KernelUp(unittest.TestCase):
    def setUp(self):
        self._base = pm.KERNEL_BASE
        self._seam = os.environ.pop("ROMP_SESSIONS_FILE", None)

    def tearDown(self):
        pm.KERNEL_BASE = self._base
        if self._seam is not None:
            os.environ["ROMP_SESSIONS_FILE"] = self._seam

    def test_true_when_healthz_answers(self):
        with _HealthzStub() as base:
            pm.KERNEL_BASE = base
            self.assertTrue(pm._kernel_up())

    def test_false_when_nothing_listens(self):
        pm.KERNEL_BASE = "http://127.0.0.1:%d" % _dead_port()
        self.assertFalse(pm._kernel_up())

    def test_false_under_the_no_kernel_test_seam(self):
        # ROMP_SESSIONS_FILE means "a test with no live kernel" (_kernel_post's seam) — the gate
        # must read the same way, so the bats autostop tests stay hermetic on a dev machine whose
        # REAL kernel is up on the default port.
        with _HealthzStub() as base:
            pm.KERNEL_BASE = base
            os.environ["ROMP_SESSIONS_FILE"] = "/nonexistent"
            self.assertFalse(pm._kernel_up())


class IdleGate(unittest.TestCase):
    def setUp(self):
        self._ku = pm._kernel_up

    def tearDown(self):
        pm._kernel_up = self._ku

    def test_local_clients_keep_the_bus_no_kernel_probe_needed(self):
        pm._kernel_up = lambda: (_ for _ in ()).throw(AssertionError("must not probe with clients present"))
        self.assertEqual(pm._idle_tick(3, 1), (0, False))

    def test_a_live_kernel_keeps_a_sessionless_bus(self):
        pm._kernel_up = lambda: True
        idle, stop = pm._idle_tick(0, 0)
        self.assertEqual((idle, stop), (0, False), "a quiet hub serves inbound peers; it must not stop")
        # even a count already at the brink resets — the kernel IS the client
        self.assertEqual(pm._idle_tick(0, pm.IDLE_GRACE - 1), (0, False))

    def test_no_kernel_and_no_clients_still_self_stops(self):
        pm._kernel_up = lambda: False
        idle = 0
        for _ in range(pm.IDLE_GRACE - 1):
            idle, stop = pm._idle_tick(0, idle)
            self.assertFalse(stop)
        idle, stop = pm._idle_tick(0, idle)
        self.assertTrue(stop, "a machine with no kernel and no sessions keeps the old autostop")


class RefusedNotifyRevives(unittest.TestCase):
    def setUp(self):
        self._bp = km.BUS_PORT
        self._ens = km._ensure_postal_bus
        km.BUS_PORT = _dead_port()
        self.kicked = threading.Event()
        km._ensure_postal_bus = self.kicked.set
        km._bus_reviving[0] = False

    def tearDown(self):
        km.BUS_PORT = self._bp
        km._ensure_postal_bus = self._ens
        km._bus_reviving[0] = False

    def test_refused_peer_notify_kicks_one_ensure(self):
        self.assertFalse(km._notify_bus_peer("TESTHOST", 1, True), "the caller still sees the failure")
        self.assertTrue(self.kicked.wait(5), "the refusal must kick a revive")

    def test_refused_origin_trust_notify_kicks_too(self):
        self.assertFalse(km._notify_bus_origin_trust("TESTHOST", "directed"))
        self.assertTrue(self.kicked.wait(5))

    def test_revive_is_single_flight(self):
        km._bus_reviving[0] = True            # an ensure is (pretend) already in flight
        km._revive_postal_bus()               # a second kick must coalesce, not stack
        self.assertFalse(self.kicked.wait(0.3), "no second ensure while one is in flight")
        km._bus_reviving[0] = False
        km._revive_postal_bus()
        self.assertTrue(self.kicked.wait(5), "released → the next kick runs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
