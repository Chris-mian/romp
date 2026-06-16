#!/usr/bin/env python3
"""Regression guards for two romp-kernel serve-layer hardening fixes:

  L2 — the serve token is compared in constant time (hmac.compare_digest), not
       with ==, so a network (tailnet) client gets no timing oracle on the token.
  M3 — an ABSENT Host header counts as local only when bound to loopback. When
       serving off-box (ROMP_SERVE_HOST=0.0.0.0), a Host-less client must NOT
       bypass the token gate (otherwise a raw socket with no Host + no Origin got
       in unauthenticated).

Synthetic only — no real session data; the gate decision touches no session state.
Mirrors tests/test_kernel_ws_auth.py's module load order.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


def _inst(host):
    """A Handler with just enough state to call _is_local_host (no socket)."""
    h = km.Handler.__new__(km.Handler)
    h.headers = {} if host is None else {"Host": host}
    return h


class TokenCompare(unittest.TestCase):
    def test_ct_eq_matches_and_differs(self):
        self.assertTrue(km._ct_eq("abc", "abc"))
        self.assertFalse(km._ct_eq("abc", "abd"))
        self.assertFalse(km._ct_eq("abc", "abcd"))   # length differs

    def test_ct_eq_never_raises_on_odd_input(self):
        self.assertFalse(km._ct_eq(None, "x"))
        self.assertFalse(km._ct_eq("x", None))


class LocalHostGate(unittest.TestCase):
    def setUp(self):
        self._bind = km.BIND

    def tearDown(self):
        km.BIND = self._bind

    def test_absent_host_is_local_only_on_loopback(self):
        km.BIND = "127.0.0.1"
        self.assertTrue(_inst("")._is_local_host())     # empty Host, loopback bind → local
        self.assertTrue(_inst(None)._is_local_host())   # missing Host header → local
        km.BIND = "0.0.0.0"
        self.assertFalse(_inst("")._is_local_host())    # off-box bind → empty Host NOT local
        self.assertFalse(_inst(None)._is_local_host())

    def test_loopback_host_always_local(self):
        km.BIND = "0.0.0.0"
        self.assertTrue(_inst("127.0.0.1")._is_local_host())
        self.assertTrue(_inst("localhost:7433")._is_local_host())


if __name__ == "__main__":
    unittest.main(verbosity=2)
