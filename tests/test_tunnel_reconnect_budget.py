#!/usr/bin/env python3
"""Reconnect is BOUNDED (the user 2026-07-22). An unreachable remote used to be re-dialed forever — the
supervisor backed off to a 5-minute ceiling and never gave up, with nothing in the UI saying so, so a box
that was simply switched off sat there retrying all day. Now each host gets TUNNEL_MAX_TRIES attempts, then
the row goes `gave-up` and romp stops dialing until either the next kernel start or an explicit Attach.

Synthetic only — hermetic temp STATE, placeholder hostnames/tokens, no real ssh.
"""
import inspect
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_rbudget", os.path.join(BIN, "romp-kernel")).load_module()


class ReconnectBudget(unittest.TestCase):
    def test_there_is_a_finite_try_budget(self):
        self.assertIsInstance(km.TUNNEL_MAX_TRIES, int)
        self.assertGreater(km.TUNNEL_MAX_TRIES, 0)

    def test_the_supervisor_stops_dialing_once_the_budget_is_spent(self):
        src = inspect.getsource(km._tunnel_supervisor)
        # a row that already gave up is skipped entirely — no respawn
        self.assertIn('if r.get("gave_up"):', src)
        self.assertIn('r["status"] = "gave-up"', src)
        # ...and the budget is what trips it
        self.assertIn("if fails >= TUNNEL_MAX_TRIES:", src)
        self.assertIn('r["gave_up"] = True', src)
        # a healthy tunnel re-arms the budget, so a LATER drop still gets its own attempts
        self.assertIn('r.pop("gave_up", None)', src)

    def test_every_kernel_start_re_arms_the_budget(self):
        # "try to connect on startup every time": a host that gave up last run is tried again this run.
        # fails/next_try/gave_up persist in remotes.json, so boot must clear them or the budget is spent
        # before the supervisor ever runs.
        state = km.jd.STATE
        state.mkdir(parents=True, exist_ok=True)
        km.REMOTES_FILE.write_text(json.dumps([{
            "host": "TESTHOST", "kernel_port": 7433, "local_port": 51000, "token": "tok",
            "fails": 99, "next_try": 9e12, "gave_up": True, "trust": "directed",
        }]))
        km._remotes.clear()
        km._remotes_load()
        r = km._remotes.get("TESTHOST")
        self.assertIsNotNone(r, "the row must still load")
        self.assertEqual(r["fails"], 0, "boot re-arms the try budget")
        self.assertEqual(r["next_try"], 0, "boot clears the backoff deadline")
        self.assertFalse(r.get("gave_up"), "a host that gave up last run is retried on the next start")

    def test_an_explicit_attach_re_arms_the_budget(self):
        # Attach IS the "try again" gesture, so it must clear gave_up — otherwise clicking it on a
        # given-up row would do nothing.
        src = inspect.getsource(km.attach_remote)
        self.assertIn('r.pop("gave_up", None)', src)
        self.assertIn('r["fails"], r["next_try"] = 0, 0', src)

    def test_the_state_is_surfaced_to_the_ui(self):
        # the popover has to be able to SAY romp stopped dialing — a silent forever-retry looked identical
        # to a healthy idle row
        src = inspect.getsource(km._remote_public)
        self.assertIn('"gaveUp": bool(r.get("gave_up"))', src)
        self.assertIn('"maxTries": TUNNEL_MAX_TRIES', src)


if __name__ == "__main__":
    unittest.main()
