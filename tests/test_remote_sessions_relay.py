#!/usr/bin/env python3
"""GET /remote/<host>/sessions (2026-09-14): relay ONE read of an attached host's own /sessions through this kernel's
tunnel, for a same-machine client that lists a peer's sessions with the identity colors that host's dashboard draws
(an editor plugin's session picker). Since 2026-09-08 a peer's serve token never leaves its machine (/tunnels
publishes only `hasToken`), so the direct read such a client used to make is gone. Pinned here:
  - the remote sees its OWN token, never the caller's; the rows come back re-read through a whitelist (id, name,
    state, dir, bg, fg), so a peer's extra keys never pass and a row without a usable id is dropped;
  - the two colors must be #rrggbb or a CSS color word, else ''; free text is inert and bounded;
  - 404 for an unknown host, 502 for a dead tunnel or a body that is not a list, the peer's own status mirrored
    otherwise (an older build's 404), and the whole route sits behind the local auth gate.
Synthetic throughout: TESTHOST, placeholder ids, the notes-api demo sessions."""
import json
import os
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
# the rail test's kernel load (hermetic XDG, ROMP_SERVE_TOKEN, NO_OPEN): one kernel module for these routes
from tests.test_api_health_rail import km  # noqa: E402

REMOTE_TOKEN = "remote-token-DO-NOT-USE"
SID_WEB = "11111111-2222-3333-4444-555555555555"
SID_API = "22222222-2222-3333-4444-555555555555"
ROWS = [
    {"id": SID_WEB, "name": "web", "state": "working", "dir": "/tmp/notes-api", "bg": "#4ea8a9", "fg": "white",
     "lastSid": SID_WEB, "backend": "sdk", "compacting": False, "working": "", "token": "never-relayed"},
    {"id": SID_API, "name": "api<script>alert(1)</script>", "state": "waiting", "bg": "url(javascript:x)",
     "fg": "#0C1A2E"},
    {"name": "no id at all"},
    {"id": "an id with spaces", "name": "tests"},
    {"id": SID_WEB + "\n", "name": "trailing newline id"},
    "not a row",
]


class _FakeRemote(BaseHTTPRequestHandler):
    """A remote kernel that serves /sessions to the right token only, and records what it was asked."""
    body = ROWS
    seen = []

    def do_GET(self):
        _FakeRemote.seen.append((self.path, self.headers.get("X-Romp-Token")))
        if (self.headers.get("X-Romp-Token") or "") != REMOTE_TOKEN:
            self.send_response(403); self.end_headers(); self.wfile.write(b"bad token"); return
        if not self.path.startswith("/sessions"):
            self.send_response(404); self.end_headers(); self.wfile.write(b"nope"); return
        payload = json.dumps(_FakeRemote.body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Whitelist(unittest.TestCase):
    """_remote_session_public_row: the shape one relayed row may take."""

    def test_the_six_fields_pass_and_nothing_else(self):
        row = km._remote_session_public_row(ROWS[0])
        self.assertEqual(row, {"id": SID_WEB, "name": "web", "state": "working", "dir": "/tmp/notes-api",
                               "bg": "#4ea8a9", "fg": "white"})

    def test_markup_is_inert_and_a_color_that_is_not_one_is_blank(self):
        row = km._remote_session_public_row(ROWS[1])
        self.assertEqual(row["name"], "apiscriptalert(1)/script")
        self.assertEqual(row["bg"], "", "a CSS function is not an identity color")
        self.assertEqual(row["fg"], "#0C1A2E")
        self.assertEqual(row["dir"], "")

    def test_a_row_without_a_usable_id_is_dropped(self):
        for bad in ROWS[2:]:
            self.assertIsNone(km._remote_session_public_row(bad), repr(bad))


class Relay(unittest.TestCase):
    """GET /remote/<host>/sessions through km.Handler."""

    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        _FakeRemote.body, _FakeRemote.seen = ROWS, []
        self.fake = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRemote)
        threading.Thread(target=self.fake.serve_forever, daemon=True).start()
        with km._remotes_lock:
            self._saved = dict(km._remotes)
            km._remotes.clear()
            km._remotes["TESTHOST"] = {"host": "TESTHOST", "kernel_port": 29855, "local_port": self.fake.server_address[1],
                                       "token": REMOTE_TOKEN, "status": "up", "sids": [], "trust": "directed"}
            km._remotes["DEADHOST"] = {"host": "DEADHOST", "kernel_port": 29855, "local_port": _free_port(),
                                       "token": REMOTE_TOKEN, "status": "up", "sids": [], "trust": "directed"}

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.clear(); km._remotes.update(self._saved)
        self.srv.shutdown(); self.srv.server_close()
        self.fake.shutdown(); self.fake.server_close()

    def _get(self, path, token=True):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("GET", path, headers=({"X-Romp-Token": km.TOKEN} if token else {}))
        r = c.getresponse(); body = r.read(); ct = r.getheader("Content-Type") or ""; c.close()
        return r.status, body, ct

    def test_the_rows_pass_through_the_whitelist_with_the_remote_token_rewritten_in(self):
        st, body, ct = self._get("/remote/TESTHOST/sessions")
        self.assertEqual(st, 200, body[:200])
        self.assertTrue(ct.startswith("application/json"))
        doc = json.loads(body)
        self.assertEqual(doc["ok"], True)
        self.assertEqual(doc["host"], "TESTHOST")
        self.assertEqual([r["id"] for r in doc["sessions"]], [SID_WEB, SID_API], "rows without a usable id are gone")
        self.assertEqual(set(doc["sessions"][0]), {"id", "name", "state", "dir", "bg", "fg"},
                         "a peer's extra keys (lastSid, backend, a stray token) never pass")
        self.assertEqual(doc["sessions"][0]["bg"], "#4ea8a9")
        self.assertEqual(_FakeRemote.seen[-1], ("/sessions", REMOTE_TOKEN), "the remote saw its OWN token, never the caller's")

    def test_an_unknown_host_is_404_and_a_dead_tunnel_is_502(self):
        st, body, _ = self._get("/remote/NOSUCHHOST/sessions")
        self.assertEqual(st, 404)
        self.assertIn(b"no attached host", body)
        st, body, _ = self._get("/remote/DEADHOST/sessions")
        self.assertEqual(st, 502)
        self.assertIn(b"not answering", body)

    def test_a_body_that_is_not_a_list_is_a_502_naming_the_host(self):
        _FakeRemote.body = {"error": "an older build's shape"}
        st, body, _ = self._get("/remote/TESTHOST/sessions")
        self.assertEqual(st, 502)
        self.assertIn(b"TESTHOST", body)

    def test_the_relay_is_behind_the_local_auth_gate(self):
        st, _, _ = self._get("/remote/TESTHOST/sessions", token=False)
        self.assertIn(st, (401, 403))
        self.assertEqual([s for s in _FakeRemote.seen if s[0] == "/sessions"], [],
                         "an unauthenticated read never reaches the remote")


if __name__ == "__main__":
    unittest.main()
