#!/usr/bin/env python3
"""A check-in handshake must not undo the trust you set (the user 2026-07-29).

Symptom: a remote was set to trusted, over and over, and kept coming back as directed — its mail
quarantining again minutes later. The setting was not being forgotten by the store; it was being
OVERWRITTEN. checkin_apply rebuilt the peer's row from scratch on every handshake with a hardcoded
"trust": "directed", and the handshake repeats once per tunnel INCARNATION: every reconnect, tunnel
respawn and kernel restart on the checking-in machine.

The mismatch is invisible from the sending end, which is why it read as a store that forgets: the level
a peer DECLARES comes from its own row, so the sender kept displaying "they hold yours: trusted" while
the receiver was quarantining. A re-check-in is the same relationship reconnecting, not a new one.

Synthetic only — placeholder hosts/ports/tokens, hermetic temp STATE, no ssh.
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_citrust", os.path.join(BIN, "romp-kernel")).load_module()

BODY = {"host": "TESTHOST", "kernelPort": 29855, "busPort": 25302, "token": "peertok"}


class CheckinTrust(unittest.TestCase):
    def setUp(self):
        km._remotes.clear()
        with km._known_lock:
            km._known.clear()

    def tearDown(self):
        km._remotes.clear()
        with km._known_lock:
            km._known.clear()

    def test_a_first_checkin_is_directed_the_safe_default(self):
        payload, status = km.checkin_apply(dict(BODY))
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "directed")

    def test_a_LEVEL_YOU_SET_survives_the_next_handshake(self):
        # this is the bug: the mobile reconnects (or its kernel restarts) and hands in the same details
        km.checkin_apply(dict(BODY))
        km.set_trust("TESTHOST", "trusted")
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")
        km.checkin_apply(dict(BODY))
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted",
                         "a reconnect must not silently re-gate a host you trusted")

    def test_isolated_survives_too_the_refusal_is_a_boundary(self):
        # an isolation refusal is the user's boundary; a reconnect re-opening it would be worse than
        # the directed case, since isolation means no postal contact at all
        km.checkin_apply(dict(BODY))
        km.set_trust("TESTHOST", "isolated")
        km.checkin_apply(dict(BODY))
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "isolated")

    def test_the_level_is_remembered_so_it_survives_a_kernel_restart_too(self):
        km.checkin_apply(dict(BODY))
        km.set_trust("TESTHOST", "trusted")
        self.assertEqual(km.known_trust("TESTHOST"), "trusted", "the remembered entry tracks the choice")
        # a restart loses _remotes' live rows; the next handshake rebuilds from what was remembered
        km._remotes.clear()
        km.checkin_apply(dict(BODY))
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")

    def test_a_checkin_under_a_NEW_name_carries_nothing_over(self):
        # the same mobile re-checking in as another name is a different key: it must not inherit a level
        # chosen for the old one, since trust is judged by origin name at the gate
        km.checkin_apply(dict(BODY))
        km.set_trust("TESTHOST", "trusted")
        km.checkin_apply(dict(BODY, host="OTHERHOST"))
        self.assertEqual(km._remotes["OTHERHOST"]["trust"], "directed")

    def test_an_ssh_attached_row_of_the_same_name_is_still_refused(self):
        km._remotes["TESTHOST"] = {"host": "TESTHOST", "trust": "trusted", "checkin_peer": False}
        payload, status = km.checkin_apply(dict(BODY))
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted", "the ssh row is untouched")


if __name__ == "__main__":
    unittest.main()
