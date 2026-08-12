#!/usr/bin/env python3
"""Sender 'still undelivered' backstop (the user 2026-06-29): the orphan sweep only bounces mail to a DEAD
recipient. Mail can also strand UNREAD in a LIVE-but-idle recipient's box (the stale-bus bug). _warn_stuck_mail
warns the live SENDER once, after STUCK_GRACE, and LEAVES the message for eventual delivery — gated on the
recipient being idle/waiting so a mid-turn recipient never trips a false alarm.

Synthetic only — placeholder UUIDs, no real session data.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = SourceFileLoader("romp_postal_undelivered", os.path.join(BIN, "romp-postal-service")).load_module()

SENDER = "11111111-1111-1111-1111-111111111111"
RECIP = "22222222-2222-2222-2222-222222222222"


class StuckMailWarning(unittest.TestCase):
    def setUp(self):
        self._seamfile = os.path.join(tempfile.mkdtemp(), "sessions.json")
        os.environ["ROMP_SESSIONS_FILE"] = self._seamfile      # local_agents() reads this instead of a live kernel
        for d in (pm.MAILROOT, pm.WARNED, pm.MAILPENDING):     # isolate each test
            shutil.rmtree(d, ignore_errors=True)

    def tearDown(self):
        os.environ.pop("ROMP_SESSIONS_FILE", None)

    def _set_recip_state(self, state):
        Path(self._seamfile).write_text(json.dumps(
            [{"id": SENDER, "name": "alice", "state": "idle"},
             {"id": RECIP, "name": "bob", "state": state}]))

    def _age_recip_mail(self, secs):
        old = time.time() - secs
        for f in (pm.MAILROOT / RECIP / "new").iterdir():
            os.utime(f, (old, old))

    def _sender_box(self):
        return pm.read_box(SENDER, consume=False)

    def test_idle_recipient_stuck_past_grace_warns_sender_once_and_keeps_the_mail(self):
        self._set_recip_state("idle")
        mid = pm.deliver(RECIP, "alice", SENDER, "please review my PR")
        self._age_recip_mail(pm.STUCK_GRACE + 60)
        pm._warn_stuck_mail()
        sb = self._sender_box()
        self.assertEqual(len(sb), 1, "the live sender is warned exactly once")
        self.assertIn("STILL UNDELIVERED", sb[0]["body"])
        self.assertIn("bob", sb[0]["body"], "the warning names the unreachable recipient")
        self.assertTrue((pm.MAILROOT / RECIP / "new" / mid).exists(),
                        "a live recipient's message is LEFT in new/ — it may still deliver (not bounced)")
        pm._warn_stuck_mail()
        self.assertEqual(len(self._sender_box()), 1, "the one-time marker prevents a duplicate warning")

    def test_working_recipient_is_not_warned(self):
        self._set_recip_state("working")
        pm.deliver(RECIP, "alice", SENDER, "ping while you work")
        self._age_recip_mail(pm.STUCK_GRACE + 60)
        pm._warn_stuck_mail()
        self.assertEqual(self._sender_box(), [],
                         "a mid-turn recipient legitimately waits for its next turn — no false alarm")

    def test_fresh_mail_within_grace_is_not_warned(self):
        self._set_recip_state("idle")
        pm.deliver(RECIP, "alice", SENDER, "just sent")     # mtime ~ now, within STUCK_GRACE
        pm._warn_stuck_mail()
        self.assertEqual(self._sender_box(), [], "within the grace the normal delivery path still owns it")

    def test_marker_is_pruned_once_the_message_delivers(self):
        self._set_recip_state("idle")
        mid = pm.deliver(RECIP, "alice", SENDER, "warn then deliver")
        self._age_recip_mail(pm.STUCK_GRACE + 60)
        pm._warn_stuck_mail()
        self.assertTrue((pm.WARNED / mid).exists(), "warned once → marker written")
        pm.read_box(RECIP, consume=True)                    # the recipient finally drains it (new/ -> cur/)
        pm._warn_stuck_mail()
        self.assertFalse((pm.WARNED / mid).exists(),
                         "the marker is pruned once the message left new/ so WARNED stays bounded")


if __name__ == "__main__":
    unittest.main()
