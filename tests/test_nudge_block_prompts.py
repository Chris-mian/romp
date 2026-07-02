#!/usr/bin/env python3
"""Auto-Nudge prompt + planner block rule (the user 2026-06-19).

A goal that finished a phase and is parked awaiting the user's go-ahead was showing WORKING (and
getting auto-nudged) instead of BLOCKED. Two paired fixes guarded here:

  Fix 1 — the nudge prompt asks for the done-vs-blocked split, not a bare "status?", and the kernel
          constant stays in sync with the manual Nudge button in the webview.
  Fix 2 — the planner's block rule explicitly treats "finished phase awaiting your go-ahead" as a
          block, so a status report alongside reported progress no longer reads as working.
"""
import os
import re
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")

# romp-kernel imports romp-judge as `jd` at load, which imports romp-event-model — load deps first
# (mirrors tests/test_kernel_cachebust.py).
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel_nudge", os.path.join(BIN, "romp-kernel")).load_module()

FEED_TS = os.path.join(ROOT, "ui", "webview", "feed.ts")
OLD_BARE_STATUS = "What is the status of the above goal?"


class AutoNudgePrompt(unittest.TestCase):
    def test_kernel_constant_is_the_only_copy(self):
        # the manual feed Nudge button was REMOVED (the user 2026-06-30) — auto-nudge is the only nudge, so
        # the kernel constant is the single copy of the prompt and feed.ts must carry NO nudge button text
        # (the old in-sync check went stale when the button left and silently failed on the missing regex).
        src = open(FEED_TS, encoding="utf-8").read()
        self.assertNotRegex(src, r'nudge\.onclick', "the manual Nudge button stays removed")

    def test_prompt_elicits_done_and_blocked_on_user(self):
        t = km.AUTO_NUDGE_TEXT.lower()
        self.assertNotEqual(km.AUTO_NUDGE_TEXT, OLD_BARE_STATUS,
                            "the bare status question is what caused the working/blocked mis-classification")
        self.assertIn("done", t, "nudge should ask what's done")
        self.assertIn("blocked", t, "nudge should ask what's blocked")
        self.assertTrue("me" in t or "you" in t,
                        "nudge should ask whether anything is blocked waiting on the user")

    def test_prompt_reads_like_a_person_not_a_status_form(self):
        # g13 (the user 2026-07-01): the nudge must read like an ordinary user turn, never disclose an
        # automated/tracking origin, and not open with a form-like "Status on the goal above:" header.
        t = km.AUTO_NUDGE_TEXT.lower()
        for robotic in ("status on the goal above", "romp", "automated", "tracking"):
            self.assertNotIn(robotic, t, robotic)
        self.assertTrue(km.AUTO_NUDGE_TEXT[0].isupper() and "?" in km.AUTO_NUDGE_TEXT,
                        "a natural question, addressed to the session")


class PlannerBlockRule(unittest.TestCase):
    def test_block_rule_covers_awaiting_go_ahead(self):
        sys = jd.PLAN_SYS.lower()
        self.assertIn("go-ahead", sys,
                      "planner block rule must name the 'awaiting your go-ahead' case")
        self.assertIn("does not keep it working", sys,
                      "planner must say reported progress does not keep an awaiting-user goal working")


if __name__ == "__main__":
    unittest.main()
