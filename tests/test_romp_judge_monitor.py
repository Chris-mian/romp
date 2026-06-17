#!/usr/bin/env python3
"""Tests for bin/romp-judge-monitor (the `romp -j` judges health view). Exercises build_model() against
synthetic state — backlog (pending = parsed units not yet captioned), the manager.log exception scan
(producer crashes + crash-vs-clean restart classification), and the verdict. probe_kernel/tmux_alive are
monkeypatched so the model is deterministic without a live kernel or tmux."""
import json
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
mon = SourceFileLoader("romp_judge_monitor", os.path.join(BIN, "romp-judge-monitor")).load_module()

NOW = 1781600000
SID = "11111111-2222-3333-4444-555555555555"


class JudgeMonitor(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.state = self.dir / "romp"
        for d in ("names", "captions", "judge-units-cache"):
            (self.state / d).mkdir(parents=True)
        (self.state / "names" / SID).write_text("feature-x\t/tmp/x\t#1EA1EB\twhite\n")
        # Deterministic: pretend the kernel is up and this session is alive in tmux.
        mon.probe_kernel = lambda: {"alive": True, "uptime_s": 120, "sha": "abc1234", "pid": 999, "url": "x"}
        mon.tmux_alive = lambda: {SID}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _uid(self, ut):
        return "%s:%d:h%d" % (SID, ut, ut)

    def _cache(self, unit_ts):
        tasks = [{"text": "u", "writes": [{"id": self._uid(ut), "grain": g, "t": ut}
                                          for g in ("segment", "turn")]} for ut in unit_ts]
        (self.state / "judge-units-cache" / (SID + ".json")).write_text(json.dumps({"key": [], "tasks": tasks}))

    def _captions(self, unit_ts):
        lines = [json.dumps({"id": self._uid(ut), "grain": g, "t": ut, "caption": "x"})
                 for ut in unit_ts for g in ("segment", "turn")]
        (self.state / "captions" / (SID + ".jsonl")).write_text("\n".join(lines) + "\n")

    def test_backlog_counts_uncaptioned_units(self):
        self._cache([NOW - 300, NOW - 200, NOW - 100])   # 3 parsed units
        self._captions([NOW - 300])                       # 1 captioned → 2 pending
        m = mon.build_model(self.state, NOW)
        self.assertEqual(m["backlog"]["total_pending"], 2)
        self.assertEqual(m["sessions"][0]["pending"], 2)
        self.assertEqual(m["sessions"][0]["name"], "feature-x")
        self.assertAlmostEqual(m["sessions"][0]["oldest_pending_age_s"], 200, delta=1)
        self.assertAlmostEqual(m["backlog"]["last_caption_age_s"], 300, delta=1)
        self.assertEqual(m["verdict"], "warn")            # backlog older than 45s + kernel up

    def test_all_captioned_is_ok(self):
        self._cache([NOW - 50, NOW - 40])
        self._captions([NOW - 50, NOW - 40])
        m = mon.build_model(self.state, NOW)
        self.assertEqual(m["backlog"]["total_pending"], 0)
        self.assertEqual(m["verdict"], "ok")

    def test_producer_crash_is_warn_even_with_no_backlog(self):
        self._cache([NOW - 30]); self._captions([NOW - 30])
        (self.state / "manager.log").write_text("producer: Traceback (most recent call last):\n  boom\n")
        m = mon.build_model(self.state, NOW)
        self.assertEqual(m["exceptions"]["producer_crashes"], 1)
        self.assertEqual(m["verdict"], "warn")

    def test_clean_sigterm_restarts_are_not_crashes(self):
        self._cache([NOW - 30]); self._captions([NOW - 30])
        (self.state / "manager.log").write_text(
            "[romp-manager] kernel 'main' exited (code=null sig=SIGTERM) — respawning in 0ms [#1]\n"
            "[romp-manager] kernel 'main' exited (code=1 sig=null) — respawning in 0ms [#2]\n")
        m = mon.build_model(self.state, NOW)
        self.assertEqual(m["exceptions"]["kernel_restarts"], 2)
        self.assertEqual(m["exceptions"]["kernel_crashes"], 1)   # only the code=1/sig=null exit is a crash
        self.assertEqual(m["verdict"], "warn")

    def test_kernel_down_is_down(self):
        mon.probe_kernel = lambda: {"alive": False}
        self._cache([NOW - 30]); self._captions([NOW - 30])
        m = mon.build_model(self.state, NOW)
        self.assertEqual(m["verdict"], "down")

    def test_render_colors_backlog_and_identity_names(self):
        # Informative colour: a big backlog (>=5 pending) goes red, and each session name renders in its
        # romp identity #hex via an ANSI truecolour escape.
        mon._USE_COLOR = True
        try:
            self._cache([NOW - 600, NOW - 500, NOW - 400, NOW - 300, NOW - 200, NOW - 100])  # 6 pending
            self._captions([])
            out = mon.render(mon.build_model(self.state, NOW))
            self.assertIn("\x1b[31m", out)                # red — a pile of pending (>=5)
            self.assertIn("\x1b[1;38;2;30;161;235m", out)  # identity-colour name (#1EA1EB → 30;161;235)
        finally:
            mon._USE_COLOR = False

    def test_render_plain_when_color_off(self):
        mon._USE_COLOR = False
        self._cache([NOW - 100]); self._captions([])
        out = mon.render(mon.build_model(self.state, NOW))
        self.assertNotIn("\x1b[", out)                    # no ANSI escapes at all


if __name__ == "__main__":
    unittest.main(verbosity=2)
