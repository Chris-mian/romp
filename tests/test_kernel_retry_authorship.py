#!/usr/bin/env python3
"""An auto-retry is romp's action, not the human's, so it must be authored romp-injected (gray bubble) on
BOTH backends (the user 2026-06-30). The SDK retry used to go out as a bare "retry" → authored 'human' (blue),
and the planner mis-read each bare "retry" as a user message and force-pinned a junk goal per retry via the
never-skip hard guard ("retry — kept on the board…") — 71 of them in one API-error storm. The marker makes
author_of return 'romp', so the echo + transcript render gray AND the planner skips a work-less retry instead
of minting a goal. Source-level pin (the apiRetry handler isn't easily exercised end-to-end here).
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
KERNEL = os.path.join(os.path.dirname(HERE), "bin", "romp-kernel")


class RetryAuthorship(unittest.TestCase):
    def setUp(self):
        self.src = open(KERNEL).read()

    def test_retry_is_always_romp_injected_on_both_backends(self):
        # the apiRetry handler sends the MARKED retry unconditionally (no tmux/SDK split)
        self.assertIn('be.send(sid, "retry\\n\\n<!-- romp-injected -->")', self.src)

    def test_the_old_backend_split_is_gone(self):
        # the bare-"retry"-for-SDK branch (which authored it human) must not survive
        self.assertNotRegex(self.src, r'if be is _TMUX else "retry"\)')


if __name__ == "__main__":
    unittest.main()
