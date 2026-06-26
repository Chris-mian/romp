#!/usr/bin/env python3
"""The working-note (set_working / `romp --mail working`) goes through the kernel's backend-agnostic store
(POST /working), NOT the tmux @romp-working var — so an SDK session can publish one and postal never shells
tmux for it (the user 2026-06-26). Synthetic only — placeholder ids, hostname-free.
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()      # hermetic; constants resolve under here at import
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal")).load_module()


class WorkingNoteThroughKernel(unittest.TestCase):
    def setUp(self):
        self._saved = (pm._publish_working, pm.tmux, pm.my_id)
        self.published = []
        pm._publish_working = lambda sid, text: (self.published.append((sid, text)), True)[1]
        self.tmux_calls = []
        pm.tmux = lambda *a, **k: (self.tmux_calls.append(a), "")[1]
        pm.my_id = lambda: "sid-self"

    def tearDown(self):
        pm._publish_working, pm.tmux, pm.my_id = self._saved

    def test_cli_working_posts_to_the_kernel_and_shells_no_tmux(self):
        rc = pm.cli_working(["editing", "feed.ts"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.published, [("sid-self", "editing feed.ts")])
        self.assertEqual(self.tmux_calls, [], "cli_working must not shell tmux")

    def test_cli_working_clear_publishes_empty(self):
        pm.cli_working([])
        self.assertEqual(self.published, [("sid-self", "")])

    def test_source_routes_set_working_through_the_kernel_not_tmux(self):
        src = open(os.path.join(BIN, "romp-postal")).read()
        self.assertIn('KERNEL_BASE + "/working"', src, "_publish_working POSTs to the kernel working endpoint")
        self.assertIn("_publish_working(mid, text)", src, "the set_working MCP tool routes through the kernel")
        self.assertNotIn('"@romp-working"', src, "no tmux @romp-working var write remains in postal")


if __name__ == "__main__":
    unittest.main()
