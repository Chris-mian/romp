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
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

NOW = 1781100000


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _asst(usage, ts=None):
    o = {"type": "assistant", "message": {"role": "assistant", "content": [], "usage": usage}}
    if ts is not None:
        o["timestamp"] = ts
    return json.dumps(o)


class SessionTokens(unittest.TestCase):
    def test_sums_windowed_usage_across_assistant_messages(self):
        t0 = NOW - 3600
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(_asst({"input_tokens": 10, "output_tokens": 5,
                           "cache_creation_input_tokens": 100, "cache_read_input_tokens": 200}, iso(NOW - 100)) + "\n")
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")  # ignored
            f.write(_asst({"input_tokens": 3, "output_tokens": 7, "cache_read_input_tokens": 50}, iso(NOW - 50)) + "\n")  # missing cache_w
            f.write(_asst({"input_tokens": 999, "output_tokens": 999}, iso(NOW - 99999)) + "\n")  # OUTSIDE the window → dropped
            path = f.name
        try:
            self.assertEqual(km._session_tokens(path, t0),
                             {"in": 13, "out": 12, "cache_w": 100, "cache_r": 250})
        finally:
            os.unlink(path)

    def test_missing_file_returns_zeros(self):
        self.assertEqual(km._session_tokens("/no/such/transcript.jsonl", NOW - 3600),
                         {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0})


class TokenWindows(unittest.TestCase):
    """_token_windows splits sessions + the judge pipeline across the two Claude meters (5h / 7d),
    each windowed independently. _judge_usage reads jd.STATE, so point it at a temp dir."""
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = pathlib.Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def test_splits_sessions_and_pipeline_by_5h_and_week(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, dir=self.td.name) as f:
            f.write(_asst({"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 5000}, iso(NOW - 3600)) + "\n")  # in 5h
            f.write(_asst({"input_tokens": 40, "output_tokens": 10}, iso(NOW - 3 * 86400)) + "\n")    # in week, not 5h
            f.write(_asst({"input_tokens": 999, "output_tokens": 999}, iso(NOW - 30 * 86400)) + "\n")  # older than a week
            path = f.name
        (jd.STATE / "judge-usage.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"t": NOW - 1800, "judge": "captioner", "tier": "index", "in": 10, "out": 5, "cost": 0.01, "ms": 100},
            {"t": NOW - 2 * 86400, "judge": "planner", "tier": "triage", "in": 70, "out": 30, "cost": 0.2, "ms": 200},
            {"t": NOW - 20 * 86400, "judge": "planner", "tier": "triage", "in": 9, "out": 9, "cost": 9, "ms": 9},
        ]) + "\n")
        tk = km._token_windows([path], NOW)
        # 5h: only the first transcript msg + the first judge call
        self.assertEqual(tk["fiveHour"]["sessions"], {"in": 100, "out": 20, "cache_r": 5000})
        self.assertEqual(tk["fiveHour"]["pipeline"]["total"]["in"], 10)
        self.assertEqual(tk["fiveHour"]["pipeline"]["total"]["calls"], 1)
        # week: first two transcript msgs + first two judge calls (the >week rows drop)
        self.assertEqual(tk["week"]["sessions"], {"in": 140, "out": 30, "cache_r": 5000})
        self.assertEqual(tk["week"]["pipeline"]["total"]["in"], 80)
        self.assertEqual(tk["week"]["pipeline"]["total"]["calls"], 2)
        self.assertEqual(tk["windows"], {"fiveHour": km.WIN_5H, "week": km.WIN_WEEK})

    def test_no_paths_no_log_is_zero_but_shaped(self):
        tk = km._token_windows([], NOW)
        self.assertEqual(tk["fiveHour"]["sessions"], {"in": 0, "out": 0, "cache_r": 0})
        self.assertEqual(tk["week"]["pipeline"]["total"]["calls"], 0)


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


class MonitorJudgeUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mon = SourceFileLoader("romp_judge_monitor", os.path.join(BIN, "romp-judge-monitor")).load_module()

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_rollup_windows_and_buckets(self):
        (self.state / "judge-usage.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"t": NOW - 100, "judge": "captioner", "tier": "index", "in": 10, "out": 5, "cost": 0.01, "ms": 800},
            {"t": NOW - 50, "judge": "planner", "tier": "triage", "in": 100, "out": 40, "cost": 0.3, "ms": 2500},
            {"t": NOW - 999999, "judge": "planner", "tier": "triage", "in": 9, "out": 9, "cost": 9.9, "ms": 1},
        ]) + "\n")
        u = self.mon.judge_usage(self.state, NOW)
        self.assertEqual(u["total"]["calls"], 2, "the >24h row is windowed out")
        self.assertAlmostEqual(u["total"]["cost"], 0.31)
        self.assertEqual(u["by_tier"]["triage"]["in"], 100)
        self.assertEqual(u["by_judge"]["captioner"]["calls"], 1)

    def test_render_shows_pipeline_section_sorted_by_cost(self):
        model = {"t": NOW, "verdict": "ok",
                 "kernel": {"alive": True, "uptime_s": 100, "sha": "abc", "pid": 1},
                 "exceptions": {"producer_crashes": 0, "kernel_crashes": 0, "kernel_restarts": 0, "last_crash": None},
                 "judge_errors": {"count_1h": 0, "count_15m": 0, "last": None},
                 "backlog": {"total_pending": 0, "oldest_pending_age_s": None, "last_caption_age_s": None, "active_sessions": 0},
                 "sessions": [],
                 "usage": {"total": {"calls": 5, "in": 1000, "out": 500, "cost": 0.5, "ms": 4000},
                           "by_tier": {"index": {"calls": 3, "in": 300, "out": 100, "cost": 0.1, "ms": 1000},
                                       "triage": {"calls": 2, "in": 700, "out": 400, "cost": 0.4, "ms": 3000}},
                           "by_judge": {"planner": {"calls": 2, "in": 700, "out": 400, "cost": 0.4, "ms": 3000},
                                        "captioner": {"calls": 3, "in": 300, "out": 100, "cost": 0.1, "ms": 1000}},
                           "window_s": 86400}}
        self.mon._USE_COLOR = False
        txt = self.mon.render(model)
        self.assertIn("pipeline cost", txt)
        self.assertIn("$0.50", txt)
        self.assertLess(txt.index("planner"), txt.index("captioner"), "judges sorted by cost (planner first)")


class AttachRunUsage(unittest.TestCase):
    """_attach_run_usage greedily matches each judging mark to the judge's nearest real call in
    judge-usage.jsonl (same fsid+judge), so a band block's tooltip can sum members' ms + tokens."""
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = pathlib.Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def test_matches_marks_to_nearest_runs_same_session(self):
        (jd.STATE / "judge-usage.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"t": NOW - 95, "judge": "captioner", "fsid": "S1", "ms": 800, "in": 10, "out": 5},
            {"t": NOW - 45, "judge": "captioner", "fsid": "S1", "ms": 900, "in": 20, "out": 8},
            {"t": NOW - 40, "judge": "captioner", "fsid": "S2", "ms": 700, "in": 30, "out": 9},
        ]) + "\n")
        judging = [
            {"judge": "captioner", "sid": "S1", "t": NOW - 100, "kind": "segment", "text": "a"},
            {"judge": "captioner", "sid": "S1", "t": NOW - 50, "kind": "turn", "text": "b"},
            {"judge": "planner", "sid": "S1", "t": NOW - 50, "kind": "mint", "text": "c"},
        ]
        km._attach_run_usage(judging, NOW - 3600, {"S1", "S2"})
        self.assertEqual((judging[0]["ms"], judging[0]["in"], judging[0]["out"]), (800, 10, 5))
        self.assertEqual((judging[1]["ms"], judging[1]["in"], judging[1]["out"]), (900, 20, 8), "each run consumed once")
        self.assertEqual((judging[2]["ms"], judging[2]["in"], judging[2]["out"]), (0, 0, 0), "planner mark unmatched → zeros")

    def test_no_log_leaves_zeros(self):
        judging = [{"judge": "captioner", "sid": "S1", "t": NOW, "kind": "segment", "text": "x"}]
        km._attach_run_usage(judging, NOW - 3600, {"S1"})
        self.assertEqual((judging[0]["ms"], judging[0]["in"], judging[0]["out"]), (0, 0, 0))


class TokenAnalytics(unittest.TestCase):
    """_token_analytics: ONE arbitrary window (the analytics modal's period picker) → the coding
    SESSIONS total vs the judge pipeline broken out per judge AND per tier. discover() supplies the
    session fleet; jd.STATE points at a temp judge-usage.jsonl."""
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved_state, self.saved_discover = jd.STATE, jd.discover
        jd.STATE = pathlib.Path(self.td.name)

    def tearDown(self):
        jd.STATE, jd.discover = self.saved_state, self.saved_discover
        self.td.cleanup()

    def test_window_splits_sessions_vs_per_judge_and_tier(self):
        p1 = pathlib.Path(self.td.name) / "s1.jsonl"
        p1.write_text(_asst({"input_tokens": 100, "output_tokens": 20}, iso(NOW - 1800)) + "\n" +     # in window
                      _asst({"input_tokens": 999, "output_tokens": 999}, iso(NOW - 99999)) + "\n")     # outside → dropped
        p2 = pathlib.Path(self.td.name) / "s2.jsonl"
        p2.write_text(_asst({"input_tokens": 30, "output_tokens": 8}, iso(NOW - 600)) + "\n")
        jd.discover = lambda now: [("fs1", p1, "a1", "s1"), ("fs2", p2, "a2", "s2")]
        (jd.STATE / "judge-usage.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"t": NOW - 900, "judge": "captioner", "tier": "index", "in": 10, "out": 4, "cost": 0.01, "ms": 50},
            {"t": NOW - 800, "judge": "archiver", "tier": "index", "in": 6, "out": 2, "cost": 0.01, "ms": 40},
            {"t": NOW - 700, "judge": "planner", "tier": "triage", "in": 70, "out": 30, "cost": 0.2, "ms": 300},
            {"t": NOW - 50000, "judge": "planner", "tier": "triage", "in": 999, "out": 999, "cost": 9, "ms": 9},  # >1h → dropped
        ]) + "\n")
        a = km._token_analytics(NOW, 3600)
        self.assertEqual(a["window"], 3600)
        self.assertEqual(a["sessions"], {"in": 130, "out": 28}, "both sessions summed, windowed")
        self.assertEqual(a["judges"]["total"]["in"], 86, "10+6+70; the >1h planner call dropped")
        self.assertEqual(set(a["judges"]["byJudge"]), {"captioner", "archiver", "planner"})
        self.assertEqual(a["judges"]["byJudge"]["planner"]["out"], 30)
        self.assertEqual(a["judges"]["byTier"]["index"]["in"], 16, "captioner+archiver share the index tier")
        self.assertEqual(a["judges"]["byTier"]["triage"]["in"], 70)

    def test_empty_fleet_and_no_log_is_zero_but_shaped(self):
        jd.discover = lambda now: []
        a = km._token_analytics(NOW, 86400)
        self.assertEqual(a["sessions"], {"in": 0, "out": 0})
        self.assertEqual(a["judges"]["total"]["calls"], 0)
        self.assertEqual(a["judges"]["byJudge"], {})


if __name__ == "__main__":
    unittest.main()
