#!/usr/bin/env python3
"""Tests for build_timeline's token-usage split:
  _session_tokens  — per-session transcript token sums (the SESSIONS half)
  _judge_usage     — the judge PIPELINE rollup from judge-usage.jsonl (per-judge / per-tier)
Synthetic data only (placeholder usage numbers, a temp state dir)."""
import json
import os
import pathlib
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

NOW = 1781100000


def _asst(usage):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [], "usage": usage}})


class SessionTokens(unittest.TestCase):
    def test_sums_usage_across_assistant_messages(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(_asst({"input_tokens": 10, "output_tokens": 5,
                           "cache_creation_input_tokens": 100, "cache_read_input_tokens": 200}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")  # ignored
            f.write(_asst({"input_tokens": 3, "output_tokens": 7, "cache_read_input_tokens": 50}) + "\n")  # missing cache_w
            path = f.name
        try:
            self.assertEqual(km._session_tokens(path),
                             {"in": 13, "out": 12, "cache_w": 100, "cache_r": 250})
        finally:
            os.unlink(path)

    def test_missing_file_returns_zeros(self):
        self.assertEqual(km._session_tokens("/no/such/transcript.jsonl"),
                         {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0})


class JudgeUsageRollup(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = pathlib.Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def _write(self, rows):
        (jd.STATE / "judge-usage.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def test_empty_when_no_log(self):
        r = km._judge_usage(NOW - 3600)
        self.assertEqual(r["total"]["calls"], 0)
        self.assertEqual(r["byJudge"], {})
        self.assertEqual(r["byTier"], {})

    def test_rolls_up_total_byjudge_bytier_and_windows(self):
        self._write([
            {"t": NOW - 100, "judge": "captioner", "tier": "index", "in": 10, "out": 5, "cost": 0.01, "ms": 800},
            {"t": NOW - 50, "judge": "captioner", "tier": "index", "in": 20, "out": 8, "cost": 0.02, "ms": 900},
            {"t": NOW - 30, "judge": "planner", "tier": "triage", "in": 100, "out": 40, "cost": 0.3, "ms": 2500},
            {"t": NOW - 99999, "judge": "planner", "tier": "triage", "in": 999, "out": 999, "cost": 9.9, "ms": 9999},
        ])
        r = km._judge_usage(NOW - 3600)
        self.assertEqual(r["total"]["calls"], 3, "the out-of-window row is dropped")
        self.assertEqual(r["total"]["in"], 130)
        self.assertEqual(r["total"]["out"], 53)
        self.assertAlmostEqual(r["total"]["cost"], 0.33)
        self.assertEqual(r["byJudge"]["captioner"]["calls"], 2)
        self.assertEqual(r["byJudge"]["captioner"]["in"], 30)
        self.assertEqual(r["byJudge"]["planner"]["in"], 100)
        self.assertEqual(r["byTier"]["index"]["calls"], 2)
        self.assertEqual(r["byTier"]["triage"]["in"], 100)

    def test_garbled_lines_are_skipped(self):
        (jd.STATE / "judge-usage.jsonl").write_text(
            '{"t":%d,"judge":"closer","tier":"triage","in":5,"out":2}\nnot json\n' % NOW)
        r = km._judge_usage(NOW - 3600)
        self.assertEqual(r["total"]["calls"], 1)
        self.assertEqual(r["byJudge"]["closer"]["out"], 2)


if __name__ == "__main__":
    unittest.main()
