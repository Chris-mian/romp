"""Follow-up messages render cleanly (the user 2026-06-27): a romp follow-up prepends the goal context as a
`> …` blockquote and trails <!-- romp-* --> markers. For the chat we strip both and keep just the body,
surfacing the goal title separately so the turn shows a compact "Follow-up · <goal>" header. Applied to BOTH
landed human turns and pending queued messages so the two render the same. SYNTHETIC fixtures only."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

FOLLOWUP = ("> Clarify storage and application of default model/effort settings (done)\n"
            "> The question was fully answered: new SDK sessions start immediately with hardcoded defaults.\n\n"
            "Can you make those persist so a change I make is remembered and reapplied at startup?\n\n"
            "<!-- romp-injected --><!-- romp-goal-id: 48466e32-497a-4801-8372-be12ebac29e1:g2 -->")


class SplitFollowup(unittest.TestCase):
    def test_strips_the_quote_and_markers_keeps_body_and_goal(self):
        goal, body, fu = km._split_followup(FOLLOWUP)
        self.assertTrue(fu)
        self.assertEqual(goal, "Clarify storage and application of default model/effort settings (done)")
        self.assertEqual(body, "Can you make those persist so a change I make is remembered and reapplied at startup?")
        self.assertNotIn("romp-goal-id", body, "the comment marker is gone")
        self.assertNotIn(">", body, "the goal-context quote is gone")

    def test_plain_message_passes_through(self):
        goal, body, fu = km._split_followup("just a normal message")
        self.assertFalse(fu)
        self.assertIsNone(goal)
        self.assertEqual(body, "just a normal message")

    def test_no_goal_line_still_strips_markers_and_flags_followup(self):
        goal, body, fu = km._split_followup("hey can you retry that\n\n<!-- romp-goal-id: S:g1 -->")
        self.assertTrue(fu)
        self.assertEqual(body, "hey can you retry that")
        self.assertIsNone(goal, "no quote → no goal title, but still a follow-up")

    def test_build_session_applies_it_to_queued_and_landed(self):
        src = inspect.getsource(km.build_session)
        self.assertIn('"kind": "queued", "texts": qmsgs', src, "queued ships per-message md objects")
        self.assertIn("_split_followup(t)", src, "each queued message is cleaned")
        self.assertIn("fu_goal, fu_body, fu = _split_followup(prompt)", src, "landed human turns are cleaned")
        self.assertIn('ev["followUp"] = True', src)


if __name__ == "__main__":
    unittest.main()
