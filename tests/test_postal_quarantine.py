#!/usr/bin/env python3
"""Per-host trust model, bus side (postal_service): the inbound gate in _relay_in holds mail from a
DIRECTED peer for human approval instead of injecting it, delivers a TRUSTED peer's mail as today, and
silently drops an ISOLATED peer's mail. The quarantine store + quarantine_decide (approve/deny) back the
feed's blocked card. peer_update carries the per-host trust the gate reads.

Synthetic only — hermetic temp state dir, placeholder mids, invented notes-domain sessions, no real data.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
# One live local session ("web") via the sessions-file seam (no live kernel needed).
_SESS = os.path.join(os.environ["XDG_STATE_HOME"], "sessions.json")
Path(_SESS).write_text(json.dumps([{"id": "sess-web", "name": "web", "dir": "/tmp/notes-api",
                                    "state": "waiting", "working": ""}]))
os.environ["ROMP_SESSIONS_FILE"] = _SESS
ps = SourceFileLoader("romp_postal_quar", os.path.join(BIN, "romp-postal-service")).load_module()


def _relay(mid, body="ship it", frm="api", origin=None):
    m = {"mid": mid, "to": "web", "frm": frm, "frm_id": "id-" + frm, "body": body, "kind": "coordinate"}
    if origin:
        m["origin"] = origin
    return m


class InboundTrustGate(unittest.TestCase):
    def setUp(self):
        os.environ["ROMP_SESSIONS_FILE"] = _SESS   # pin OUR sessions seam (read live; a later-collected postal test clobbers it)
        # fresh peer table + empty stores each test
        ps.PEERS.clear()
        for d in (ps.QUARANTINE, ps.MAILROOT / "sess-web" / "new"):
            try:
                for f in d.glob("*"):
                    f.unlink()
            except OSError:
                pass

    def _set_trust(self, host, level, up=True):
        ps.peer_update({"host": host, "port": 47101, "up": up, "trust": level})

    def test_trusted_delivers(self):
        self._set_trust("TESTHOST", "trusted")
        verdict, _ = ps._relay_in("TESTHOST", _relay("q-trusted-1"))
        self.assertEqual(verdict, "ack")
        self.assertEqual(ps.quarantine_list(), [], "trusted mail must NOT be quarantined")
        box = ps.read_box("sess-web", consume=False)
        self.assertTrue(any("ship it" in (msg.get("body") or "") for msg in box),
                        "trusted mail must be delivered to the recipient's maildir")

    def test_directed_quarantines(self):
        self._set_trust("TESTHOST", "directed")
        verdict, _ = ps._relay_in("TESTHOST", _relay("q-directed-1"))
        self.assertEqual(verdict, "ack", "the sender is ack'd (stops resending) even though it's held")
        held = ps.quarantine_list()
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["mid"], "q-directed-1")
        self.assertEqual(held[0]["to"], "web")
        self.assertEqual(held[0]["origin"], "TESTHOST")
        self.assertEqual(ps.read_box("sess-web", consume=False), [],
                         "directed mail must NOT reach the session until approved")

    def test_isolated_drops(self):
        self._set_trust("TESTHOST", "isolated")
        verdict, _ = ps._relay_in("TESTHOST", _relay("q-iso-1"))
        self.assertEqual(verdict, "ack")
        self.assertEqual(ps.quarantine_list(), [], "isolated mail is dropped, not held")
        self.assertEqual(ps.read_box("sess-web", consume=False), [], "isolated mail is not delivered")

    def test_unknown_origin_defaults_to_directed(self):
        # No PEERS entry (a race before the kernel notify lands) → safe default: hold, never auto-inject.
        verdict, _ = ps._relay_in("MYSTERY", _relay("q-unknown-1"))
        self.assertEqual(verdict, "ack")
        self.assertEqual(len(ps.quarantine_list()), 1)
        self.assertEqual(ps.read_box("sess-web", consume=False), [])

    def test_origin_only_trust_row_governs_relayed_mail(self):
        # Trust-by-origin end to end (the user 2026-07-25): the user tiers a host they have NO
        # tunnel to (an origin-only, portless row); its mail arriving relayed through a hub is
        # judged by that tier — trusted injects instead of holding.
        self._set_trust("EDGE", "trusted")                      # the hub we ARE connected to
        ps.peer_update({"host": "ORIGIN", "trust": "trusted", "originOnly": True})
        verdict, _ = ps._relay_in("EDGE", _relay("q-origin-1", origin="ORIGIN"))
        self.assertEqual(verdict, "ack")
        self.assertEqual(len(list(ps.QUARANTINE.glob("*.json"))), 0,
                         "an origin-only trusted tier delivers, no hold")

    def test_forwarded_origin_is_the_trust_key(self):
        # A 2-hop message carries m["origin"] = the true origin; the gate keys on it, not the direct peer.
        self._set_trust("EDGE", "trusted")       # the direct peer we received from
        self._set_trust("ORIGIN", "directed")    # the true origin — its level governs
        verdict, _ = ps._relay_in("EDGE", _relay("q-fwd-1", origin="ORIGIN"))
        self.assertEqual(verdict, "ack")
        self.assertEqual(len(ps.quarantine_list()), 1, "the ORIGIN's directed level must hold it")


class QuarantineDecide(unittest.TestCase):
    def setUp(self):
        os.environ["ROMP_SESSIONS_FILE"] = _SESS   # pin OUR sessions seam (see InboundTrustGate.setUp)
        ps.PEERS.clear()
        ps.peer_update({"host": "TESTHOST", "port": 47101, "up": True, "trust": "directed"})
        for d in (ps.QUARANTINE, ps.MAILROOT / "sess-web" / "new"):
            try:
                for f in d.glob("*"):
                    f.unlink()
            except OSError:
                pass

    def test_approve_delivers_and_clears(self):
        ps._relay_in("TESTHOST", _relay("q-appr-1", body="original text"))
        ok, err = ps.quarantine_decide("q-appr-1", "approve")
        self.assertTrue(ok, err)
        self.assertEqual(ps.quarantine_list(), [], "approved message leaves the hold")
        box = ps.read_box("sess-web", consume=False)
        self.assertTrue(any("original text" in (m.get("body") or "") for m in box),
                        "approve delivers the held message")

    def test_approve_with_edited_text(self):
        ps._relay_in("TESTHOST", _relay("q-appr-2", body="raw peer text"))
        ok, err = ps.quarantine_decide("q-appr-2", "approve", text="edited by the human")
        self.assertTrue(ok, err)
        box = ps.read_box("sess-web", consume=False)
        self.assertTrue(any("edited by the human" in (m.get("body") or "") for m in box))
        self.assertFalse(any("raw peer text" in (m.get("body") or "") for m in box),
                         "the edited text replaces the peer's original")

    def test_deny_drops_without_delivering(self):
        ps._relay_in("TESTHOST", _relay("q-deny-1"))
        ok, err = ps.quarantine_decide("q-deny-1", "deny")
        self.assertTrue(ok, err)
        self.assertEqual(ps.quarantine_list(), [])
        self.assertEqual(ps.read_box("sess-web", consume=False), [], "deny delivers nothing")

    def test_decide_unknown_mid_errors(self):
        ok, err = ps.quarantine_decide("no-such-mid", "approve")
        self.assertFalse(ok)
        self.assertIn("no held message", err)


class PeerUpdateTrust(unittest.TestCase):
    def test_default_and_keep_last_known(self):
        ps.PEERS.clear()
        ps.peer_update({"host": "H", "port": 1, "up": True})                 # no trust → directed
        self.assertEqual(ps.PEERS["H"]["trust"], "directed")
        ps.peer_update({"host": "H", "port": 1, "up": True, "trust": "trusted"})
        self.assertEqual(ps.PEERS["H"]["trust"], "trusted")
        ps.peer_update({"host": "H", "port": 1, "up": False})                # trustless down-notify keeps it
        self.assertEqual(ps.PEERS["H"]["trust"], "trusted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
