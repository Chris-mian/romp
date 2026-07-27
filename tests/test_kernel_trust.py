#!/usr/bin/env python3
"""Per-host trust model, kernel side: the remotes registry stores a trust level (trusted|directed|
isolated), defaulting to directed; set_trust validates + persists it; _remote_public/_tunnels expose it
(the channel the bus reads); the /tunnels/trust route drives it; and _quarantine_cards surfaces a held
message from a directed peer as a needs-you feed card.

Synthetic only — hermetic temp STATE, placeholder hostnames/mids, invented notes-domain sessions.
"""
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


def _row(host, **extra):
    r = {"host": host, "kernel_port": 29855, "local_port": 5000, "bus_port": 5001, "token": "t",
         "proc": None, "status": "up", "detail": "", "sids": [], "trust": "directed"}
    r.update(extra)
    return r


class SetTrust(unittest.TestCase):
    def setUp(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")

    def test_default_is_directed_in_public_view(self):
        pub = km._remote_public(km._remotes["TESTHOST"])
        self.assertEqual(pub["trust"], "directed")

    def test_set_trust_updates_and_persists(self):
        pub, err = km.set_trust("TESTHOST", "trusted")
        self.assertIsNone(err)
        self.assertEqual(pub["trust"], "trusted")
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")
        # persistence: reload from remotes.json and confirm the level survived
        km._remotes_save()
        km._remotes.clear()
        km._remotes_load()
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")

    def test_set_trust_rejects_bad_level(self):
        pub, err = km.set_trust("TESTHOST", "whatever")
        self.assertIsNone(pub)
        self.assertIn("trust must be one of", err)

    def test_set_trust_unattached_host_is_origin_only(self):
        # Trust is judged BY ORIGIN at delivery (the user 2026-07-25): a host with no tunnel here —
        # its mail arrives relayed through a hub — can carry a tier. The level lands in the
        # remembered-hosts table and reaches the bus as an origin-only row.
        calls = []
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: calls.append((h, t)) or True
        try:
            pub, err = km.set_trust("FARBOX", "trusted")
        finally:
            km._notify_bus_origin_trust = saved
        self.assertIsNone(err)
        self.assertEqual(pub, {"host": "FARBOX", "trust": "trusted", "originOnly": True})
        self.assertEqual(km.known_trust("FARBOX"), "trusted", "the remembered table IS the store")
        self.assertEqual(calls, [("FARBOX", "trusted")], "the bus learns the origin row now")

    def test_push_origin_trust_rows_covers_only_unattached(self):
        # The supervisor pushes remembered-but-unattached tiers once per (host, level); attached
        # hosts stay the (up, trust)-keyed full notify's job.
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        km._known.clear()                         # order-independent: other tests seed this table
        km._known_note("TESTHOST", "trusted")     # attached → not this path's job
        km._known_note("FARBOX", "isolated")      # unattached → pushed
        km._origin_trust_pushed.clear()
        calls = []
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: calls.append((h, t)) or True
        try:
            km._push_origin_trust_rows()
            km._push_origin_trust_rows()          # memoized: no duplicate push
            km._known_note("FARBOX", "directed")  # a level CHANGE re-pushes
            km._push_origin_trust_rows()
        finally:
            km._notify_bus_origin_trust = saved
        self.assertEqual(calls, [("FARBOX", "isolated"), ("FARBOX", "directed")])

    def test_load_defaults_missing_trust_to_directed(self):
        # a pre-trust remotes.json row (no "trust" key) reads back as directed
        km._remotes.clear()
        km._remotes["OLD"] = {k: v for k, v in _row("OLD").items() if k != "trust"}
        km._remotes_save()
        km._remotes.clear()
        km._remotes_load()
        self.assertEqual(km._remotes["OLD"]["trust"], "directed")


class TrustRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", path, json.dumps(body),
                  {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
        r = c.getresponse()
        data = json.loads(r.read().decode() or "{}")
        c.close()
        return r.status, data

    def test_route_sets_trust(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        code, data = self._post("/tunnels/trust", {"host": "TESTHOST", "trust": "isolated"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tunnel"]["trust"], "isolated")

    def test_route_rejects_bad_level(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        code, data = self._post("/tunnels/trust", {"host": "TESTHOST", "trust": "bogus"})
        self.assertEqual(code, 400)
        self.assertFalse(data["ok"])

    def test_route_unattached_host_sets_origin_trust(self):
        km._remotes.clear()
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: True
        try:
            code, data = self._post("/tunnels/trust", {"host": "GHOST", "trust": "trusted"})
        finally:
            km._notify_bus_origin_trust = saved
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tunnel"], {"host": "GHOST", "trust": "trusted", "originOnly": True})


class QuarantineCards(unittest.TestCase):
    def _write_held(self, mid, frm="api", to="web", origin="TESTHOST", body="ship the parser fix"):
        qdir = km.jd.STATE / "postal" / "quarantine"
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / (mid + ".json")).write_text(json.dumps(
            {"mid": mid, "to": to, "toId": "sess-web", "frm": frm, "frmId": "id-api",
             "body": body, "kind": "coordinate", "origin": origin, "at": 1000}))

    def setUp(self):
        qdir = km.jd.STATE / "postal" / "quarantine"
        if qdir.exists():
            for f in qdir.glob("*.json"):
                f.unlink()

    def test_builds_a_needs_you_card(self):
        self._write_held("qc-1")
        cards = km._quarantine_cards(2000, set())
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["itemId"], "quarantine:qc-1")
        self.assertEqual(c["column"], "needs_input")
        self.assertEqual(c["blocked"]["state"], "quarantine")
        self.assertEqual(c["blocked"]["frm"], "api")
        self.assertEqual(c["blocked"]["to"], "web")
        self.assertEqual(c["blocked"]["origin"], "TESTHOST")
        self.assertEqual(c["blocked"]["body"], "ship the parser fix")

    def test_card_is_compact_title_plus_gist(self):
        """The card reads "New message" under the RECIPIENT session's name, with the bus-style 90-char
        gist for the one-line body (the user 2026-07-26 — the full body lives in the decision modal)."""
        self._write_held("qc-4", body="  ship   the\nparser fix  " + "x" * 200)
        c = km._quarantine_cards(2000, set())[0]
        self.assertEqual(c["text"], "New message")
        gist = c["blocked"]["gist"]
        self.assertTrue(gist.startswith("ship the parser fix"), gist)
        self.assertEqual(len(gist), 90, "whitespace-collapsed and clamped like the federation gossip gist")

    def test_cleared_card_is_hidden(self):
        self._write_held("qc-2")
        self.assertEqual(km._quarantine_cards(2000, {"quarantine:qc-2"}), [])

    def test_no_dir_is_empty(self):
        # nothing held → no cards, no crash
        self.assertEqual(km._quarantine_cards(2000, set()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
