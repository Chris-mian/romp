#!/usr/bin/env python3
"""Postal isolation holds on every sanctioned route (the user 2026-07-10): the mailbox-off boundary was
enforced only inside the postal bus (send_message), so agent mail could reach an isolated session through
the kernel's /send or /deliver — a peer's probe did exactly that. Now /deliver refuses a mailbox-off
target outright (the bus keeps the banner parked until the mailbox reopens), and /send refuses
postal-SHAPED content (the same recognizers _genuine_queued uses) to isolated targets while plain text
still passes — /send is the HUMAN channel and the user must always reach their own isolated session.
Synthetic fixtures only."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_isolation", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class PostalShaped(unittest.TestCase):
    """Agent mail by shape: the banner markers, and nothing else."""

    def test_banner_markers_are_agent_mail(self):
        self.assertTrue(km._postal_shaped("#################### POSTAL\nDELEGATE: take this"))
        self.assertTrue(km._postal_shaped("a delivered note <!-- romp-msg-id: 123 -->"))
        self.assertTrue(km._postal_shaped("\U0001F4EC mail from a peer"))

    def test_plain_user_text_is_not(self):
        self.assertFalse(km._postal_shaped("please write the handoff plan to a file"))
        self.assertFalse(km._postal_shaped(""))
        self.assertFalse(km._postal_shaped(None))


class PostalIsolated(unittest.TestCase):
    """_postal_isolated reads the session's mailbox flag, legacy key included."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = km.jd.STATE
        km.jd.STATE = Path(self.td.name)

    def tearDown(self):
        km.jd.STATE = self.saved
        self.td.cleanup()

    def _flags(self, flags):
        (km.jd.STATE / "session-flags.json").write_text(json.dumps({SID: flags}))

    def test_reads_the_mailbox_flag_and_legacy_twin(self):
        for key in ("postalServiceOff", "postalOff"):
            self._flags({key: True})
            self.assertTrue(km._postal_isolated(SID), key)
        self._flags({})
        self.assertFalse(km._postal_isolated(SID))

    def _raw_flags(self, flags):
        (km.jd.STATE / "session-flags.json").write_text(json.dumps(flags))

    def test_the_master_key_isolates_a_session_with_no_override(self):
        # The master default (the user 2026-08-27): sessions a person opened separately are separate work,
        # so cross-session mail is off unless a session opts in. "*" can never collide with a sid.
        self._raw_flags({km.POSTAL_ALL_KEY: {"postalServiceOff": True}})
        self.assertTrue(km._postal_isolated(SID))
        self.assertTrue(km._postal_isolated("99999999-8888-7777-6666-555555555555"))

    def test_a_session_opt_IN_beats_the_master(self):
        # most-specific-wins, the notify bell's rule — an explicit False is a real answer, not an absence
        self._raw_flags({km.POSTAL_ALL_KEY: {"postalServiceOff": True}, SID: {"postalServiceOff": False}})
        self.assertFalse(km._postal_isolated(SID))

    def test_a_session_override_isolates_with_the_master_absent(self):
        self._raw_flags({SID: {"postalServiceOff": True}})
        self.assertTrue(km._postal_isolated(SID))

    def test_no_flags_at_all_leaves_the_postal_service_on(self):
        self._raw_flags({})
        self.assertFalse(km._postal_isolated(SID), "romp's shipped default is unchanged — mail works")


class RouteGates(unittest.TestCase):
    """Source pins: both routes gate on isolation, with the intended semantics."""

    def setUp(self):
        self.src = open(os.path.join(BIN, "romp-kernel")).read()

    def test_send_refuses_postal_shaped_mail_to_isolated_targets(self):
        self.assertIn('if _postal_shaped(body["text"]) and _postal_isolated(sid):', self.src)

    def test_deliver_refuses_isolated_targets_outright_and_parks(self):
        self.assertIn('if _postal_isolated(sid):', self.src)
        self.assertIn('"injected": False', self.src.split('u.path == "/deliver"')[1][:2000],
                      "the bus reads injected:false and keeps the banner parked in its maildir")

    def test_the_refusals_name_the_boundary(self):
        self.assertGreaterEqual(self.src.count("mailbox is OFF"), 2)


class PolicyPins(unittest.TestCase):
    """The norms declare an isolation refusal final — the residual a route gate can't close."""

    def test_mcp_instructions_declare_refusal_final(self):
        src = open(os.path.join(BIN, "romp-postal-service")).read()
        self.assertIn("An isolation refusal is FINAL", src)
        self.assertIn("do NOT reroute", src)

    def test_skill_declares_refusal_final(self):
        p = os.path.join(os.path.dirname(BIN), "claude", "skills", "romp-postal", "SKILL.md")
        src = open(p).read()
        self.assertIn("An isolation refusal is final", src)


if __name__ == "__main__":
    unittest.main()
