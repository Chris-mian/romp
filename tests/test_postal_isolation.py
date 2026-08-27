#!/usr/bin/env python3
"""Postal isolation (the user 2026-06-23): a session with the timeline lane's mailbox toggled off
(postalServiceOff — legacy postalOff — in the kernel's session-flags.json) is invisible to list_agents, can't send, and can't receive —
for working privately. These pin the flag reader + the read_box RECEIVE gate at the unit level; the
end-to-end /send + /agents enforcement is in tests/romp-postal.bats.

Synthetic only — placeholder UUIDs, hermetic temp state dir, no real session data.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()      # hermetic; constants resolve under here at import
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal-service")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _set_flag(sid, postal_off):
    pm.SESSION_FLAGS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(pm.SESSION_FLAGS.read_text()) if pm.SESSION_FLAGS.exists() else {}
    if postal_off:
        data[sid] = {"postalOff": True}     # legacy key on purpose: pins back-compat (reader honours old + new)
    else:
        data.pop(sid, None)
    pm.SESSION_FLAGS.write_text(json.dumps(data))


class PostalOff(unittest.TestCase):
    def tearDown(self):
        try:
            pm.SESSION_FLAGS.unlink()
        except OSError:
            pass

    def test_default_not_isolated(self):
        self.assertFalse(pm._postal_off(SID), "no flags file → on the Romp Postal Service")
        self.assertFalse(pm._postal_off(""), "empty sid → not isolated")

    def test_flag_toggles_isolation(self):
        _set_flag(SID, True)
        self.assertTrue(pm._postal_off(SID))
        _set_flag(SID, False)
        self.assertFalse(pm._postal_off(SID), "clearing the flag rejoins the Romp Postal Service")

    def test_other_flags_do_not_isolate(self):
        pm.SESSION_FLAGS.parent.mkdir(parents=True, exist_ok=True)
        pm.SESSION_FLAGS.write_text(json.dumps({SID: {"hideFromFeed": True}}))   # muted from feed, NOT postal
        self.assertFalse(pm._postal_off(SID), "hideFromFeed alone must not isolate from postal")

    def test_malformed_flags_file_fails_open(self):
        pm.SESSION_FLAGS.write_text("{not valid json")
        self.assertFalse(pm._postal_off(SID), "a corrupt flags file must NOT wedge messaging (fail open)")

    def _write_flags(self, flags):
        pm.SESSION_FLAGS.parent.mkdir(parents=True, exist_ok=True)
        pm.SESSION_FLAGS.write_text(json.dumps(flags))

    def test_the_master_key_isolates_every_session_with_no_opinion(self):
        # The master default (the user 2026-08-27): separate sessions a person opened are separate pieces
        # of work, so cross-session mail is off unless a session opts in. Reserved "*" — never a uuid.
        self._write_flags({pm.POSTAL_ALL_KEY: {"postalServiceOff": True}})
        self.assertTrue(pm._postal_off(SID), "a session with no override follows the master")
        self.assertTrue(pm._postal_off("22222222-3333-4444-5555-666666666666"), "…and so does any other")

    def test_a_session_can_opt_IN_over_a_master_default(self):
        # most-specific-wins, the notify bell's rule: an explicit False outranks a master True, so a
        # genuinely collaborating group keeps its mail while everything else stays quiet
        self._write_flags({pm.POSTAL_ALL_KEY: {"postalServiceOff": True},
                           SID: {"postalServiceOff": False}})
        self.assertFalse(pm._postal_off(SID))

    def test_a_session_override_still_isolates_with_the_master_off(self):
        self._write_flags({pm.POSTAL_ALL_KEY: {"postalServiceOff": False},
                           SID: {"postalServiceOff": True}})
        self.assertTrue(pm._postal_off(SID))

    def test_this_reader_and_the_kernels_cannot_drift(self):
        # One store, two readers, and a disagreement is a live hazard: were only the kernel to honour the
        # master, this service would go on advertising peers and taking sends the kernel calls isolated.
        self.assertEqual(pm.POSTAL_ALL_KEY, "*")
        kernel_src = open(os.path.join(BIN, "romp-kernel"), encoding="utf-8").read()
        self.assertIn('POSTAL_ALL_KEY = "*"', kernel_src)
        self.assertIn("master = _session_flags().get(POSTAL_ALL_KEY)", kernel_src)

    def test_read_box_holds_mail_while_isolated(self):
        box = pm.MAILROOT / SID / "new"
        box.mkdir(parents=True, exist_ok=True)
        (box / "msg1").write_text("From: peer\nFrom-Id: x\nDate: now\n\nhello\n")
        _set_flag(SID, True)
        self.assertEqual(pm.read_box(SID, consume=True), [],
                         "isolated → a drain delivers nothing")
        self.assertTrue((box / "msg1").exists(),
                        "the message stays in new/ (not consumed) until the session reconnects")
        _set_flag(SID, False)
        got = pm.read_box(SID, consume=True)
        self.assertEqual([m["body"] for m in got], ["hello"],
                         "reconnecting delivers the held mail")


class WiringAcrossSurfaces(unittest.TestCase):
    """The postalServiceOff flag spans three files (kernel boot exposure → timeline render/toggle → postal
    enforcement). Pin the cross-surface wiring by name so a rename can't silently disconnect a surface."""

    def test_kernel_boot_exposes_postaloff(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn('"postalServiceOff": _session_flag(sid, "postalServiceOff")', src,
                      "the kernel must publish postalServiceOff in the session boot so the timeline can render it")

    def test_timeline_view_draws_and_toggles_the_mailbox(self):
        # Since 2026-07-28 the mailbox lives in the lane GEAR's drop-down (LANE_TOGGLES) rather than as
        # its own lane icon — the row still draws the mailboxIcon and toggles postalServiceOff through
        # the same _setSessionFlag persistence.
        src = open(os.path.join(os.path.dirname(BIN), "ui", "romp-timeline-view.js")).read()
        self.assertIn("mailboxIcon", src, "the gear menu draws the (monochrome) mailbox icon")
        self.assertIn("flag: 'postalServiceOff', label: 'Postal service', icon: mailboxIcon", src,
                      "the gear menu row toggles the postalServiceOff flag")
        self.assertIn("this._setSessionFlag(s, t.flag, next);", src, "menu rows persist via _setSessionFlag")


if __name__ == "__main__":
    unittest.main(verbosity=2)
