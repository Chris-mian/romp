#!/usr/bin/env python3
"""The postal bus is token-gated (Jupyter's model, shared with the kernel): every route
except the /ping liveness probe requires the machine's serve token — loopback included,
since loopback is reachable by every local user and the bus can wake sessions and inject
mail into their prompts. Accepted forms: X-Romp-Token (same-machine clients, read from
the 0600 file) and ?token= (a peer bus dialing through the ssh forward with the DIALED
machine's token). Also pins the peer-token plumbing: /peer notifies carry the peer's
token, a token-less down notify keeps the last known one, and the dialer sends ?token=.

Synthetic only — hermetic temp state dir, placeholder names, no real session data.
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state dir; the sessions-file seam signals "no live kernel" to the bus.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
_SESS = os.path.join(os.environ["XDG_STATE_HOME"], "sessions.json")
Path(_SESS).write_text("[]")
os.environ["ROMP_SESSIONS_FILE"] = _SESS
ps = SourceFileLoader("romp_postal_token", os.path.join(BIN, "romp-postal-service")).load_module()

TOK = ps.SERVE_TOKEN


def _code(port, path, headers=None, method="GET", data=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                 headers=dict(headers or {}), method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class BusTokenGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_ping_is_exempt(self):
        self.assertEqual(_code(self.port, "/ping"), 200)

    def test_tokenless_requests_denied(self):
        self.assertEqual(_code(self.port, "/agents"), 403)
        self.assertEqual(_code(self.port, "/peers"), 403)
        self.assertEqual(_code(self.port, "/inbox?id=x"), 403)
        self.assertEqual(_code(self.port, "/send", method="POST", data=b"{}"), 403)
        self.assertEqual(_code(self.port, "/peer", method="POST", data=b"{}"), 403)

    def test_header_token_authorizes(self):
        self.assertEqual(_code(self.port, "/peers", headers={"X-Romp-Token": TOK}), 200)

    def test_query_token_authorizes_the_peer_dial_form(self):
        # A peer bus dials /peer-exchange through the ssh forward with ?token= — same
        # acceptance on any route (here /peers, which needs no exchange payload).
        self.assertEqual(_code(self.port, "/peers?token=" + TOK), 200)

    def test_wrong_token_denied(self):
        self.assertEqual(_code(self.port, "/peers", headers={"X-Romp-Token": "wrong"}), 403)
        self.assertEqual(_code(self.port, "/peers?token=wrong"), 403)


class PeerTokenPlumbing(unittest.TestCase):
    def test_peer_update_stores_token_and_down_notify_keeps_it(self):
        ps.peer_update({"host": "TESTHOST", "port": 45001, "up": True, "token": "peer-tok"})
        self.assertEqual(ps.PEERS["TESTHOST"]["token"], "peer-tok")
        ps.peer_update({"host": "TESTHOST", "port": 45001, "up": False})   # down carries no token
        self.assertEqual(ps.PEERS["TESTHOST"]["token"], "peer-tok",
                         "a token-less transition must keep the last known peer token")
        ps.PEERS.pop("TESTHOST", None)

    def test_peer_http_sends_the_peer_token_as_query(self):
        seen = {}

        class Capture(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path
                body = json.dumps({}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ps._peer_http(srv.server_address[1], {"host": "TESTHOST"}, token="peer-tok")
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(seen.get("path"), "/peer-exchange?token=peer-tok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
