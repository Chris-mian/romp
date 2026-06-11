#!/usr/bin/env python3
"""Unit tests for the stuck-working healer's pure decision (romp-idle-dots).

Born from the 2026-06-10 test_slector incident: a terminal Esc-interrupt fires
NO Claude hook, so @claude-state sat at "working" for 34+ minutes, stranding
the chat-view chip, the timeline work-bar, and the ghostty tab dot at once.
The trap these tests encode: a stale `since` ALONE cannot distinguish an
interrupted session from one legitimately inside a long tool call — only the
pane content can ("esc to interrupt" = genuinely busy; idle composer ❯ = heal).

Run:  python3 tests/test_romp_idle_dots.py
"""
import os
import sys
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
dots = SourceFileLoader("romp_idle_dots_t", os.path.join(SCRIPTS, "romp-idle-dots")).load_module()

NOW = 1_781_153_000
STALE = NOW - 2_000          # well past STUCK_AFTER_SECS
FRESH = NOW - 30             # inside it

# pane snapshots (trimmed to the discriminating tails)
PANE_IDLE = "  Finished the run.\n\n✻ Sautéed for 8s\n\n❯ \n  ctx:7%  Opus 4.8\n"
PANE_BUSY = "✶ Reticulating… (esc to interrupt)\n"
# a long tool call: composer hidden, spinner present — the false-positive trap
PANE_LONG_TOOL = "  Bash(npm test) … running\n✶ Testing… (esc to interrupt · ctrl+t)\n❯ \n"
PANE_WEIRD = "some full-screen app output, no composer, no spinner\n"


class TestDiagnose(unittest.TestCase):
    def test_interrupted_session_heals(self):
        # the incident: working + stale + idle composer
        self.assertEqual(dots.diagnose("working", STALE, NOW, False, PANE_IDLE), "heal")

    def test_stuck_compacting_heals_too(self):
        self.assertEqual(dots.diagnose("compacting", STALE, NOW, False, PANE_IDLE), "heal")

    def test_long_tool_call_is_left_alone(self):
        # THE TRAP: stale since + frozen transcript, but genuinely working —
        # the spinner marker must veto the heal even with a ❯ visible
        self.assertEqual(dots.diagnose("working", STALE, NOW, False, PANE_LONG_TOOL), "leave")
        self.assertEqual(dots.diagnose("working", STALE, NOW, False, PANE_BUSY), "leave")

    def test_fresh_since_never_captures_a_heal(self):
        self.assertEqual(dots.diagnose("working", FRESH, NOW, False, PANE_IDLE), "leave")

    def test_non_stuckable_states_left_alone(self):
        for st in ("waiting", "idle", "permission"):
            self.assertEqual(dots.diagnose(st, STALE, NOW, False, PANE_IDLE), "leave")

    def test_copy_mode_pane_is_unjudgeable(self):
        # scrolled-back pane shows history, not live state — never judge it
        self.assertEqual(dots.diagnose("working", STALE, NOW, True, PANE_IDLE), "leave")

    def test_unrecognized_pane_is_conservative(self):
        self.assertEqual(dots.diagnose("working", STALE, NOW, False, PANE_WEIRD), "leave")

    def test_garbage_since_left_alone(self):
        self.assertEqual(dots.diagnose("working", "", NOW, False, PANE_IDLE), "leave")
        self.assertEqual(dots.diagnose("working", "nope", NOW, False, PANE_IDLE), "leave")


if __name__ == "__main__":
    unittest.main(verbosity=1)
