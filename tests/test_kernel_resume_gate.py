#!/usr/bin/env python3
"""Kernel side of the resume-gate (the user 2026-07-21): _resume_gate_asks turns the SDK backend's
deferred high-context sessions into needs_input decision cards (state "largeResume", carrying the
last-known context %), and the resumeGate drive op routes the user's Proceed / Compact / Skip choice to
the backend's resolve_resume_gate. SYNTHETIC fixtures only."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_resumegate", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class _FakeSdk:
    def __init__(self, gated):
        self._gated = gated
        self.resolved = []

    def gated_resumes(self):
        return self._gated

    def resolve_resume_gate(self, sid, choice):
        self.resolved.append((sid, choice))
        return True


class ResumeGateCards(unittest.TestCase):
    def setUp(self):
        self._saved_sdk = km._sdk
        self.fake = _FakeSdk([{"sid": SID, "ctx": 82, "reason": "cut", "t": 1000}])
        km._sdk = lambda: self.fake

    def tearDown(self):
        km._sdk = self._saved_sdk

    def test_gated_session_becomes_a_largeResume_needs_input_card(self):
        cards = km._resume_gate_asks(2000, set())
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["itemId"], "resume:" + SID)
        self.assertEqual(c["sid"], SID)
        self.assertEqual(c["column"], "needs_input")
        self.assertFalse(c["live"])
        self.assertEqual(c["blocked"]["state"], "largeResume")
        self.assertEqual(c["blocked"]["ctx"], 82)          # last-known context % rides the card
        self.assertIn("82%", c["text"])

    def test_cleared_itemid_suppresses_its_card(self):
        self.assertEqual(km._resume_gate_asks(2000, {"resume:" + SID}), [])

    def test_unknown_context_renders_without_a_number(self):
        self.fake._gated = [{"sid": SID, "ctx": None, "reason": "queued", "t": 1000}]
        c = km._resume_gate_asks(2000, set())[0]
        self.assertIsNone(c["blocked"]["ctx"])
        self.assertIn("~?%", c["text"])

    def test_no_sdk_backend_means_no_cards(self):
        km._sdk = lambda: None
        self.assertEqual(km._resume_gate_asks(2000, set()), [])


class ResumeGateDriveOp(unittest.TestCase):
    def setUp(self):
        self._saved = (km._sdk, km.Sessions.backend_for, km._mark_views_dirty)
        self.fake = _FakeSdk([])
        km._sdk = lambda: self.fake
        km.Sessions.backend_for = lambda sid: object()   # resumeGate never touches the per-sid backend
        km._mark_views_dirty = lambda *a, **k: None

    def tearDown(self):
        km._sdk, km.Sessions.backend_for, km._mark_views_dirty = self._saved

    def test_each_choice_routes_to_resolve_resume_gate(self):
        client = {"send": lambda s: None}
        for choice in ("proceed", "compact", "skip"):
            self.fake.resolved.clear()
            self.assertTrue(km._drive({"type": "resumeGate", "id": SID, "choice": choice}, client))
            self.assertEqual(self.fake.resolved, [(SID, choice)])

    def test_a_bogus_choice_is_rejected(self):
        client = {"send": lambda s: None}
        # not one of proceed/compact/skip → the guard skips it (returns False, nothing resolved)
        km._drive({"type": "resumeGate", "id": SID, "choice": "nuke"}, client)
        self.assertEqual(self.fake.resolved, [])


if __name__ == "__main__":
    unittest.main()
