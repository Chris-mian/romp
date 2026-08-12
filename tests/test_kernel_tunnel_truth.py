#!/usr/bin/env python3
"""Tunnel status tells the end-to-end truth (the user 2026-07-10): the old check was the LOCAL -L
listener accepting — which ssh always does, even when the far side resets every connection — so a
remote host with no kernel running read 'up' (TESTHOST), every action routed to it silently vanished,
and the /sessions + /version polls failing left no mark. _tunnel_status derives from the poll that
actually crossed the tunnel; an alive tunnel with nobody answering is 'no-kernel', surfaced in the
popover with the next step. The /send remote forward reports a dead far kernel instead of ok:true.
Synthetic fixtures only."""
import os
import unittest
from importlib.machinery import SourceFileLoader
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_tunnel", os.path.join(BIN, "romp-kernel")).load_module()


class TunnelStatus(unittest.TestCase):
    """_tunnel_status(proc_alive, port_up, remote_answered) — the full matrix."""

    def test_answering_remote_is_up(self):
        self.assertEqual(km._tunnel_status(True, True, True), "up")

    def test_alive_tunnel_with_a_dead_far_kernel_is_no_kernel(self):
        self.assertEqual(km._tunnel_status(True, True, False), "no-kernel",
                         "the local listener accepting is NOT health — the far kernel never answered")

    def test_local_port_not_up_yet_is_starting(self):
        self.assertEqual(km._tunnel_status(True, False, False), "starting")

    def test_dead_tunnel_proc_is_down(self):
        self.assertEqual(km._tunnel_status(False, True, True), "down")
        self.assertEqual(km._tunnel_status(False, False, False), "down")


class SourcePins(unittest.TestCase):
    def setUp(self):
        self.src = open(os.path.join(BIN, "romp-kernel")).read()

    def test_supervisor_derives_status_from_the_poll(self):
        self.assertIn("_tunnel_status(_tunnel_proc_alive(r), up, sids is not None)", self.src)

    def test_no_kernel_carries_the_next_step_detail(self):
        self.assertIn("no kernel answering through the tunnel", self.src)

    def test_popover_labels_and_colors_the_new_status(self):
        self.assertIn("'no-kernel':'kernel not answering'", self.src)
        self.assertIn("t.status==='no-kernel'", self.src)

    def test_send_remote_forward_reports_a_dead_far_kernel(self):
        self.assertIn("isn't answering — message not delivered", self.src)


if __name__ == "__main__":
    unittest.main()
