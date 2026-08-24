#!/usr/bin/env python3
"""A silent mid-turn model swap mints a COMPLETED card (the user 2026-08-23, approved 08-19 and
revived): the API fell back without a request, and the swap was invisible before this. The card
pops into Completed with a done why naming the swap; a user-driven /model pick (pending marker) or
the first learn never mints. SYNTHETIC fixtures."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class FallbackCard(unittest.TestCase):
    def tearDown(self):
        for f in jd.GOALDIR.glob("*"):
            f.unlink()

    def test_mints_a_completed_top_naming_the_swap(self):
        gid = jd.mint_fallback_card(SID, "claude-fable-5", "claude-sonnet-5", ev_t=1_787_500_000)
        self.assertTrue(gid)
        store = jd.load_goals(SID)
        nd = store["nodes"][gid]
        self.assertTrue(nd["nodeComplete"])
        self.assertIn("fell back to claude-sonnet-5", nd["doneWhy"])
        self.assertIn("Model changed automatically: claude-fable-5 → claude-sonnet-5", nd["text"])
        self.assertEqual(store["status"].get(gid), "completed", "pops straight into Completed")
        dones = [e for e in nd["log"] if e.get("kind") == "done"]
        self.assertEqual(len(dones), 1)
        self.assertEqual(dones[0]["src"], "romp", "kernel-authored bookkeeping, never a question")

    def test_the_backend_transition_gates_are_pinned(self):
        src = open(os.path.join(HERE, "..", "kernel", "sdk_backend.py")).read()
        self.assertIn("if self.model and not self._model_pending and not cleared \\", src,
                      "first learns and user-driven picks never mint")
        self.assertIn('on_model_fallback', src)
        ksrc = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn("jd.mint_fallback_card(sid, frm, to)", ksrc, "the kernel wires the hook at boot")


class DowngradeOnlyGate(unittest.TestCase):
    """The card mints ONLY on a known down-tier transition (the user 2026-08-23, whose own upgrade
    to a bigger model wore a "fallback" card): romp only sees its own picks pending, so a /model
    typed inside the CLI arrives as an unrequested transition too — and a capacity fallback never
    moves a session up-tier."""

    def test_rank_and_downgrade_shapes(self):
        # exec just the pure helper block: loading the whole backend pulls the live SDK dependency
        src = open(os.path.join(os.path.dirname(HERE), "kernel", "sdk_backend.py")).read()
        i = src.index("_MODEL_TIERS")
        j = src.index("\nclass SdkSession", i)
        sb = type("NS", (), {})
        ns = {}
        exec(src[i:j], ns)
        sb._model_downgrade = staticmethod(ns["_model_downgrade"])
        self.assertTrue(sb._model_downgrade("claude-fable-5", "claude-sonnet-5"))
        self.assertTrue(sb._model_downgrade("Opus 5", "claude-haiku-4-5"))
        self.assertFalse(sb._model_downgrade("claude-opus-5", "claude-fable-5"), "an upgrade is the user's doing")
        self.assertFalse(sb._model_downgrade("claude-sonnet-5", "claude-sonnet-4-5"), "lateral within a family: no card")
        self.assertFalse(sb._model_downgrade("claude-opus-5", "some-experimental-model"), "unknown target: no card")
        self.assertFalse(sb._model_downgrade("", "claude-haiku-4-5"), "unknown source: no card")

    def test_the_learn_path_wires_the_gate(self):
        src = open(os.path.join(os.path.dirname(HERE), "kernel", "sdk_backend.py")).read()
        self.assertIn("and _model_downgrade(self.model, pm):", src)


if __name__ == "__main__":
    unittest.main()
