#!/usr/bin/env python3
"""The kernel's and the bus's HTTP servers bind without reverse-resolving their own address (2026-09-16).

Python's HTTPServer.server_bind runs `socket.getfqdn(host)` after bind() and before listen(). On a host whose
resolver cannot reverse-resolve loopback quickly the server sits there before it accepts anything: GitHub's
macOS 15 and 16 images block about 36 seconds per server (the bats macOS leg died at its 35-minute ceiling
because every Python stub and the postal bus, one per test, paid it; the same tests take 0.2 s on Linux), and a
Mac with a stale resolver would keep the kernel or the bus from answering for as long. server_name feeds
nothing either program reads, so the bind sets it to the bind address. Pinned here: the stock class DOES call
getfqdn at construction (the positive control, so the pin below means something), the kernel's and the bus's
classes do not and name their address, both serve sites construct those classes (source pins), and no
bats-inline stub constructs the stock class (the bats leg is where the cost landed)."""
import glob
import inspect
import os
import re
import socket
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_bindpin", os.path.join(BIN, "romp-kernel"))
pm = load_source("romp_postal_bindpin", os.path.join(BIN, "romp-postal-service"))


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _construct(cls, handler):
    """Construct a server of `cls` on a free loopback port with socket.getfqdn recorded, never resolved -> (server, calls)."""
    calls = []
    real = socket.getfqdn

    def recorder(name=""):
        calls.append(name)
        return name or "recorded"      # never the resolver: the pin is about the CALL, not this box's DNS
    with mock.patch.object(socket, "getfqdn", recorder):
        srv = cls(("127.0.0.1", 0), handler)
    assert socket.getfqdn is real
    return srv, calls


class BindWithoutReverseLookup(unittest.TestCase):
    def test_the_stock_server_reverse_resolves_its_address_at_construction(self):
        # the positive control: without it the assertions below could pass against a Python that never looked up
        srv, calls = _construct(ThreadingHTTPServer, _Quiet)
        try:
            self.assertEqual(calls, ["127.0.0.1"], "HTTPServer.server_bind asks getfqdn for the bind address")
        finally:
            srv.server_close()

    def test_the_kernels_server_never_asks_the_resolver_and_names_its_address(self):
        srv, calls = _construct(km._LoopbackServer, km.Handler)
        try:
            self.assertEqual(calls, [], "the kernel's bind must not reverse-resolve 127.0.0.1 (36 s on a slow resolver)")
            self.assertEqual((srv.server_name, srv.server_port), ("127.0.0.1", srv.server_address[1]))
            self.assertTrue(srv.allow_reuse_address, "HTTPServer's reuse flag rides along")
        finally:
            srv.server_close()

    def test_the_bus_server_never_asks_the_resolver_and_names_its_address(self):
        srv, calls = _construct(pm._LoopbackServer, pm.Handler)
        try:
            self.assertEqual(calls, [], "the bus's bind must not reverse-resolve 127.0.0.1")
            self.assertEqual((srv.server_name, srv.server_port), ("127.0.0.1", srv.server_address[1]))
        finally:
            srv.server_close()

    def test_both_serve_sites_construct_the_loopback_class(self):
        self.assertIn("_LoopbackServer((BIND, PORT), Handler)", inspect.getsource(km.main))
        self.assertNotIn("ThreadingHTTPServer((BIND, PORT), Handler)", inspect.getsource(km.main))
        self.assertIn("_LoopbackServer((HOST, PORT), Handler)", inspect.getsource(pm.serve))
        self.assertNotIn("ThreadingHTTPServer((HOST, PORT), Handler)", inspect.getsource(pm.serve))

    def test_no_bats_inline_stub_constructs_the_stock_server(self):
        # the bats leg starts a Python stub per test (romp.bats, romp-headless.bats, romp-manager-ensure.bats): each
        # paid the lookup once, 36 s a test, 35 minutes a run; a stub constructs a class whose server_bind skips it
        stock = re.compile(r"(?<![\w.])HTTPServer\(\(|http\.server\.HTTPServer\(\(")
        hits = []
        for fn in sorted(glob.glob(os.path.join(HERE, "*.bats"))):
            for i, line in enumerate(open(fn), 1):
                if stock.search(line):
                    hits.append("%s:%d: %s" % (os.path.basename(fn), i, line.strip()[:80]))
        self.assertEqual(hits, [], "a bats-inline stub constructs the stock HTTPServer, whose bind reverse-resolves")


if __name__ == "__main__":
    unittest.main()
