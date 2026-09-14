#!/usr/bin/env python3
"""POST /remote/<host>/new and /remote/<host>/send (2026-09-14): relay ONE control call to an attached host's own
kernel through this kernel's tunnel, how an action lands on that machine: a session spawned THERE, and its briefing
sent before this kernel's supervisor poll has learned the new sid (POST /send here would route it nowhere). The
editor plugin's new-experiment command needs both; it used to post to the tunnel port with the peer token /tunnels
published, gone since 2026-09-08. Pinned here:
  - the remote sees its OWN token, never the caller's; the JSON object body crosses as sent;
  - the peer's verdict is mirrored with its status (a 409 refusal stays a 409 with its words), never rewritten
    into "not answering";
  - 404 for an unknown host or an op outside {new, send}, 400 for a body that is not a JSON object (the remote is
    never reached), 502 for a dead tunnel or a peer that answered without a JSON verdict, every one as JSON {ok, error};
  - the route sits behind the local auth gate.
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
SID_NEW = "33333333-2222-3333-4444-555555555555"


class _FakeRemote(BaseHTTPRequestHandler):
    """A remote kernel that answers POST /new and POST /send to the right token only, and records what it saw."""
    seen = []
    plain = False   # answer /new with a non-JSON body (an older build's prose)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = raw
        _FakeRemote.seen.append((self.path, self.headers.get("X-Romp-Token"), body))
        if (self.headers.get("X-Romp-Token") or "") != REMOTE_TOKEN:
            self._reply(403, b'{"ok": false, "error": "bad token"}'); return
        if self.path == "/new":
            if _FakeRemote.plain:
                self._reply(200, b"created", ctype="text/plain"); return
            if body.get("name") == "taken":
                self._reply(409, json.dumps({"ok": False, "error": "a session of that name is already live",
                                             "nameTaken": True}).encode()); return
            self._reply(200, json.dumps({"ok": True, "id": SID_NEW, "existing": False}).encode()); return
        if self.path == "/send":
            self._reply(200, json.dumps({"ok": True, "queued": False}).encode()); return
        self._reply(404, b'{"ok": false, "error": "no such route"}')

    def _reply(self, status, payload, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Relay(unittest.TestCase):
    """POST /remote/<host>/{new,send} through km.Handler."""

    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        _FakeRemote.seen, _FakeRemote.plain = [], False
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

    def _post(self, path, body, token=True, raw=None):
        import http.client
        payload = raw if raw is not None else json.dumps(body).encode()
        hdrs = {"Content-Type": "application/json", "Content-Length": str(len(payload))}
        if token:
            hdrs["X-Romp-Token"] = km.TOKEN
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("POST", path, payload, hdrs)
        r = c.getresponse(); data = r.read(); c.close()
        try:
            doc = json.loads(data)
        except ValueError:
            doc = None
        return r.status, doc, data

    def test_new_crosses_with_the_remote_token_and_its_verdict_comes_back(self):
        st, doc, data = self._post("/remote/TESTHOST/new", {"name": "web", "dir": "/tmp/notes-api"})
        self.assertEqual(st, 200, data[:200])
        self.assertEqual(doc, {"ok": True, "id": SID_NEW, "existing": False})
        self.assertEqual(_FakeRemote.seen[-1], ("/new", REMOTE_TOKEN, {"name": "web", "dir": "/tmp/notes-api"}),
                         "the remote saw its OWN token and the body as sent")

    def test_send_crosses_the_same_way(self):
        st, doc, _ = self._post("/remote/TESTHOST/send", {"id": SID_NEW, "text": "read the note and begin"})
        self.assertEqual(st, 200)
        self.assertEqual(doc, {"ok": True, "queued": False})
        self.assertEqual(_FakeRemote.seen[-1][0], "/send")
        self.assertEqual(_FakeRemote.seen[-1][2]["id"], SID_NEW)

    def test_a_peer_s_refusal_keeps_its_status_and_its_words(self):
        st, doc, _ = self._post("/remote/TESTHOST/new", {"name": "taken", "dir": "/tmp/notes-api"})
        self.assertEqual(st, 409)
        self.assertEqual(doc["ok"], False)
        self.assertIn("already live", doc["error"])
        self.assertIs(doc.get("nameTaken"), True, "the peer's own fields ride through")

    def test_unknown_host_and_unknown_op_are_404_and_the_remote_is_never_reached(self):
        st, doc, _ = self._post("/remote/NOSUCHHOST/new", {"name": "web"})
        self.assertEqual(st, 404)
        self.assertEqual(doc["ok"], False)
        self.assertIn("no attached host", doc["error"])
        st, _, _ = self._post("/remote/TESTHOST/end", {"id": SID_NEW})
        self.assertNotEqual(st, 200, "only new and send relay")
        self.assertEqual(_FakeRemote.seen, [], "nothing reached the remote")

    def test_a_body_that_is_not_an_object_is_400_before_the_remote_is_reached(self):
        st, doc, _ = self._post("/remote/TESTHOST/new", None, raw=b'["not", "an", "object"]')
        self.assertEqual(st, 400)
        self.assertEqual(doc["ok"], False)
        self.assertEqual(_FakeRemote.seen, [])

    def test_a_dead_tunnel_and_a_peer_without_a_json_verdict_are_502(self):
        st, doc, _ = self._post("/remote/DEADHOST/new", {"name": "web"})
        self.assertEqual(st, 502)
        self.assertIn("not answering", doc["error"])
        _FakeRemote.plain = True
        st, doc, _ = self._post("/remote/TESTHOST/new", {"name": "web"})
        self.assertEqual(st, 502)
        self.assertIn("no JSON verdict", doc["error"])
        self.assertIn("TESTHOST", doc["error"])

    def test_the_relay_is_behind_the_local_auth_gate(self):
        st, _, _ = self._post("/remote/TESTHOST/new", {"name": "web"}, token=False)
        self.assertIn(st, (401, 403))
        self.assertEqual(_FakeRemote.seen, [], "an unauthenticated call never reaches the remote")


if __name__ == "__main__":
    unittest.main()
