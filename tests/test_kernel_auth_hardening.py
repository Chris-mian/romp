#!/usr/bin/env python3
"""Regression guards for two romp-kernel serve-layer hardening fixes:

  L2 — the serve token is compared in constant time (hmac.compare_digest), not
       with ==, so a network (tailnet) client gets no timing oracle on the token.
  M3 — locality is judged by the REAL TCP peer address (self.client_address), NOT
       the client-settable Host header. A remote client could otherwise send
       `Host: localhost` to forge locality and skip the token gate entirely — a
       proven bypass that reached authed routes (incl. POST /send = agent control)
       when serving off-box (ROMP_SERVE_HOST=0.0.0.0). Only a loopback peer is
       trusted without a token; every off-box client must present it.

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


def _inst(peer, host=None):
    """A Handler with just enough state to call _is_local_host (no socket).
    `peer` is the TCP client IP (self.client_address[0]); `host` is an optional
    forged Host header that must have NO effect on the locality decision."""
    h = km.Handler.__new__(km.Handler)
    h.client_address = None if peer is None else (peer, 0)
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
    def test_loopback_peer_is_local(self):
        # A genuine loopback connection is trusted without a token, regardless of Host.
        self.assertTrue(_inst("127.0.0.1")._is_local_host())
        self.assertTrue(_inst("::1")._is_local_host())
        self.assertTrue(_inst("::ffff:127.0.0.1")._is_local_host())
        self.assertTrue(_inst("127.0.0.1", host="anything.example")._is_local_host())

    def test_remote_peer_not_local_even_with_spoofed_host(self):
        # THE bypass regression: a remote client forging Host: localhost / 127.0.0.1
        # must NOT be treated as local — it has to present the serve token. This is
        # what protects every authed route reached through _authorize, incl. POST
        # /send (prompt injection into live agents).
        self.assertFalse(_inst("157.131.32.137", host="localhost")._is_local_host())
        self.assertFalse(_inst("10.0.0.5", host="127.0.0.1")._is_local_host())
        self.assertFalse(_inst("100.92.170.123", host="localhost:7433")._is_local_host())
        self.assertFalse(_inst("203.0.113.9", host="::1")._is_local_host())

    def test_missing_or_empty_peer_fails_closed(self):
        self.assertFalse(_inst(None, host="localhost")._is_local_host())
        self.assertFalse(_inst("", host="localhost")._is_local_host())


if __name__ == "__main__":
    unittest.main(verbosity=2)
