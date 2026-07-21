#!/usr/bin/env python3
"""Resume-gate (the user 2026-07-21): an AUTOMATIC mass resume (boot reconcile after a login/kernel
restart) would silently re-hydrate every cut/queued session's FULL transcript at once — a cold-cache
usage spike. A session whose last-known context fill (reg['liveCtx']) is at/above RESUME_GATE_CTX is
held back behind a decision card instead of auto-resumed; the user picks Proceed (resume now), Compact
on resume (/compact first, then resume — the reload is spent once and the window shrinks) or Skip (leave
it dormant). Below the bar, or context unknown, resumes as before. SYNTHETIC fixtures only."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend_gate", os.path.join(BIN, "romp_sdk_backend.py")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
BIG = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class ResumeGate(unittest.TestCase):
    def _backend(self):
        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)
        self.spawned = []
        be._ensure = lambda sid: self.spawned.append(sid)   # never really spawn a CLI in a test
        return be

    def test_gate_ctx_reads_livectx(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "liveCtx": 72})
        self.assertEqual(be._gate_ctx(SID), 72)
        sb.write_reg(be.state_dir, BIG, {"sid": BIG})           # never measured
        self.assertIsNone(be._gate_ctx(BIG))

    def test_threshold_is_configurable_and_default_50(self):
        self.assertEqual(sb.RESUME_GATE_CTX, float(os.environ.get("ROMP_RESUME_GATE_CTX", "50")))

    def test_gated_resumes_serializes_sid_ctx_reason(self):
        be = self._backend()
        be._gated_resumes[SID] = {"ctx": 80, "reason": "cut", "t": 123}
        got = be.gated_resumes()
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["sid"], got[0]["ctx"], got[0]["reason"]), (SID, 80, "cut"))

    def test_proceed_spawns_and_clears_the_gate(self):
        be = self._backend()
        be._gated_resumes[SID] = {"ctx": 80, "reason": "cut", "t": 1}
        self.assertTrue(be.resolve_resume_gate(SID, "proceed"))
        self.assertEqual(self.spawned, [SID])
        self.assertNotIn(SID, be._gated_resumes)

    def test_compact_prepends_slash_compact_then_spawns(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "queue": ["finish the parser"]})
        be._gated_resumes[SID] = {"ctx": 90, "reason": "queued", "t": 1}
        self.assertTrue(be.resolve_resume_gate(SID, "compact"))
        reg = sb.read_reg(be.state_dir, SID)
        self.assertEqual(reg["queue"], ["/compact", "finish the parser"])   # compact runs FIRST
        self.assertEqual(self.spawned, [SID])
        self.assertNotIn(SID, be._gated_resumes)

    def test_skip_leaves_it_dormant(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "queue": ["do x"]})
        be._gated_resumes[SID] = {"ctx": 70, "reason": "cut", "t": 1}
        self.assertTrue(be.resolve_resume_gate(SID, "skip"))
        self.assertEqual(self.spawned, [], "skip must NOT resume — that's the whole point")
        self.assertNotIn(SID, be._gated_resumes)
        self.assertEqual(sb.read_reg(be.state_dir, SID)["queue"], ["do x"], "queue survives for a later drive")

    def test_unknown_sid_is_a_noop(self):
        be = self._backend()
        self.assertFalse(be.resolve_resume_gate(SID, "proceed"))
        self.assertEqual(self.spawned, [])


if __name__ == "__main__":
    unittest.main()
