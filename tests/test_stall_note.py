"""The STALL NOTE (the user 2026-07-23).

A goal that is neither finished nor blocked-on-you, but that romp's nudge gate is quietly holding, used to
say NOTHING for itself: the distiller waits for a completion, the briefer waits for a block, and the card
sat in Working with no explanation while nothing moved it. The staller is the third surface. These cover
the read side (which records count as a stall) and the wiring that keeps the two halves honest — the kernel
WRITES the deferral record and the judge READS it, so a drift between them is silent breakage.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

ROOT = pathlib.Path(__file__).resolve().parents[1]
jd = SourceFileLoader("romp_judge_stall", str(ROOT / "kernel" / "judge.py")).load_module()

FSID = "11111111-2222-3333-4444-555555555555"
GID = FSID + ":g7"
NOW = 1781100000


class StalledFacts(unittest.TestCase):
    """jd.stalled_facts is the judge's view of the kernel's deferral log."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = pathlib.Path(self.tmp.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.tmp.cleanup()

    def _write(self, deferred):
        (jd.STATE / "auto-nudge.json").write_text(json.dumps({"deferred": deferred}))

    def test_a_settled_reason_is_reported(self):
        self._write({GID: {"at": NOW, "why": "the agent's to-do sync is due", "seen": jd.STALL_SEEN}})
        self.assertEqual(jd.stalled_facts(FSID),
                         {GID: {"why": "the agent's to-do sync is due", "since": NOW}})

    def test_a_reason_seen_once_is_not_a_stall(self):
        self._write({GID: {"at": NOW, "why": "a judge pass is mid-flight", "seen": 1}})
        self.assertEqual(jd.stalled_facts(FSID), {}, "momentary churn must not light a card")

    def test_another_session_is_not_mine(self):
        other = "99999999-8888-7777-6666-555555555555:g1"
        self._write({other: {"at": NOW, "why": "the agent's to-do sync is due", "seen": jd.STALL_SEEN}})
        self.assertEqual(jd.stalled_facts(FSID), {}, "goals are keyed by session; only mine are mine")

    def test_a_legacy_bare_int_record_says_nothing(self):
        # Written before the record carried a reason. It is not an error, there is simply no why to show.
        self._write({GID: NOW})
        self.assertEqual(jd.stalled_facts(FSID), {})

    def test_an_unreadable_store_is_not_fatal(self):
        (jd.STATE / "auto-nudge.json").write_text("{ this is not json")
        self.assertEqual(jd.stalled_facts(FSID), {}, "a stall note is an extra, never a reason to fail a pass")

    def test_no_store_at_all_is_not_fatal(self):
        self.assertEqual(jd.stalled_facts(FSID), {})


class StallSurfaceWiring(unittest.TestCase):
    """The stall note is its own card surface, and must not be mistaken for the other two."""

    def test_the_warn_kinds_name_the_stall_surface(self):
        self.assertEqual(jd._warn_line_kind("staller"), ("stall note", "stall"))
        self.assertEqual(jd._warn_line_kind("distiller"), ("summary", "summary"))
        self.assertEqual(jd._warn_line_kind("briefer"), ("decision brief", "brief"))

    def test_a_stall_warn_routes_to_the_stall_surface(self):
        self.assertEqual(jd._warn_surface({"kind": "stall-failed"}), "stall")
        self.assertEqual(jd._warn_surface({"kind": "stall-unreadable"}), "stall")
        self.assertEqual(jd._warn_surface({"kind": "brief-failed"}), "brief")
        self.assertEqual(jd._warn_surface({"kind": "summary-failed"}), "summary")


class StallPrompt(unittest.TestCase):
    """The one thing this prompt must never do is manufacture an interrupt. A stall is romp being the
    bottleneck; telling the user to decide something would turn every wedge into a false 'needs you'."""

    def test_it_forbids_inventing_a_decision_the_user_owes(self):
        sys_prompt = jd.STALL_BRIEF_SYS
        self.assertIn("never invent a decision they", sys_prompt)
        self.assertIn("NOT being asked to decide anything", sys_prompt)

    def test_it_must_not_overrule_the_kernels_reason(self):
        # <holding> is the authoritative mechanical why. A model that re-derives the cause from the work
        # history would report a plausible wrong answer, which is the failure this whole surface exists to end.
        self.assertIn("<holding>", jd.STALL_BRIEF_SYS)
        self.assertIn("Restate <holding> faithfully", jd.STALL_BRIEF_SYS)

    def test_the_call_passes_the_holding_reason_through(self):
        import inspect
        src = inspect.getsource(jd.stall_llm)
        self.assertIn("<holding>", src)
        self.assertIn('judge="staller"', src)


if __name__ == "__main__":
    unittest.main()
