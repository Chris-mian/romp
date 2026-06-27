"""A session HARD-BLOCKED on a live prompt (permission / picker) BEFORE the planner has minted any goal — e.g.
an SDK session that fired an AskUserQuestion on its very first turn — used to be INVISIBLE in the feed: the
hard-block floor can only floor an EXISTING focus card under BLOCKED, and with zero goals there's nothing to
floor, so the block never reached the Blocked column (the user 2026-06-27). build_feed now synthesizes an
ephemeral needs-input placeholder (_blocked_placeholder) carrying a `blocked` badge so feed.ts files it under
BLOCKED. SYNTHETIC fixtures only (placeholder ids, no real data)."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
COLOR = {"bg": "#123456", "fg": "#ffffff"}


def _card(perm_state):
    # a path that doesn't exist → _parse raises → the placeholder falls back to its generic awaiting text,
    # which is exactly the worst case we must still surface.
    s = {"path": "/nonexistent/TESTHOST/transcript.jsonl"}
    return km._blocked_placeholder(s, "TESTHOST", COLOR, SID, True, 1_700_000_000, perm_state, 1_699_999_900)


class BlockedNoGoal(unittest.TestCase):
    def test_picker_block_makes_a_needs_input_card_with_a_blocked_badge(self):
        c = _card("picker")
        self.assertEqual(c["column"], "needs_input", "filed under the Blocked column")
        self.assertEqual(c["blocked"]["state"], "picker", "carries the live picker block badge")
        self.assertTrue(c["provisional"], "a lightweight placeholder (dim + dashed, no clear/modal)")
        self.assertEqual(c["needsYou"], 1)
        self.assertEqual(c["tree"], [], "no goal node")
        self.assertTrue(c["itemId"].startswith("blocked:"), "stable per-session id, distinct from provisional:")
        self.assertEqual(c["text"], "Awaiting your input", "generic fallback when the prompt can't be parsed")

    def test_permission_block_says_awaiting_your_approval(self):
        c = _card("permission")
        self.assertEqual(c["column"], "needs_input")
        self.assertEqual(c["blocked"]["state"], "permission")
        self.assertEqual(c["text"], "Awaiting your approval")
        self.assertEqual(c["blocked"]["what"], "this session is stopped awaiting your approval")

    def test_build_feed_synthesizes_it_only_when_blocked_with_no_floorable_goal(self):
        src = inspect.getsource(km.build_feed)
        # the synthesis is gated: a live perm/picker state AND no top goal to floor under BLOCKED (perm_top None)
        self.assertIn("perm_state in _NEEDS_INPUT_STATES and perm_top is None", src)
        self.assertIn("_blocked_placeholder(s, name, color, fsid, live, now, perm_state", src)
        # and only inside the "no working card" branch, so it never duplicates a real/provisional card
        self.assertIn("if not had_working and ps:", src)

    def test_placeholder_carries_no_goal_node_so_it_is_replaced_when_the_planner_runs(self):
        # turnId/turnIds empty + provisional → feed.ts dims it and gives it no Clear/Nudge/modal; the real
        # card (minted once the ask is answered and the planner places the work) supersedes it.
        c = _card("picker")
        self.assertIsNone(c["turnId"])
        self.assertEqual(c["turnIds"], [])
        self.assertIsNone(c["blockWhy"])


if __name__ == "__main__":
    unittest.main()
