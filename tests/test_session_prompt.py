#!/usr/bin/env python3
"""The romp harness prompt (claude/romp-session-prompt.md) is appended to EVERY session's system prompt
(tmux via --append-system-prompt, SDK via the designed system_prompt field). It must keep its EXPLICIT
done/not-done reporting instruction, so a session never reports — and the closer never marks — partial
work as complete (the user 2026-06-26: things were getting marked completed that weren't). These pin the
load-bearing intent so a future "make it lighter" edit can't quietly drop it."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
PROMPT = os.path.join(os.path.dirname(HERE), "claude", "romp-session-prompt.md")


class SessionPrompt(unittest.TestCase):
    def setUp(self):
        with open(PROMPT) as f:
            self.text = f.read()
        # collapse line wraps so phrase matches survive prose reflow
        self.flat = re.sub(r"\s+", " ", self.text).lower()

    def test_requires_an_explicit_not_done_account(self):
        # not just "say when done" — the NOT-done side must be called out as explicitly as the done side
        self.assertIn("not done", self.flat,
                      "the prompt must require an explicit account of what is NOT done, not only 'done'")

    def test_asks_for_a_bulleted_done_notdone_list(self):
        # the user's ask: a clear, direct, bulleted Done / Not done list when there's a mix
        self.assertRegex(self.flat, r"done\s*/\s*not done",
                         "the prompt must ask for a bulleted Done / Not done list")

    def test_forbids_implying_completion_while_work_remains(self):
        # the anti-false-completion rule that protects against the closer marking partial work complete
        self.assertIn("while pieces remain", self.flat,
                      "the prompt must forbid stating/implying a task is complete while pieces remain")

    def test_preliminary_step_is_not_the_work(self):
        # reading/mapping/planning a refactor is not doing it (the g405 false-completion pattern)
        self.assertIn("preliminary step", self.flat,
                      "the prompt must say a preliminary step (reading/mapping/planning) is not finishing the work")


if __name__ == "__main__":
    unittest.main()
