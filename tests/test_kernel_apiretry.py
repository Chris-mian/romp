#!/usr/bin/env python3
"""The API-error "Retry" pastes "retry" into the session to resume the stalled turn — tagged with the
romp-injected marker so the chat renders it as a GRAY romp bubble (romp sent it), not a blue human "retry"
prompt (the user 2026-06-19). Source-pin on the kernel's inject + an end-to-end author_of check.
"""
import os
import re
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
SRC = open(os.path.join(BIN, "romp-kernel")).read()
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()


class ApiRetryRendersAsRomp(unittest.TestCase):
    def test_the_apiretry_handler_tags_retry_with_the_romp_injected_marker(self):
        # the apiRetry handler (now in the unified _drive) injects "retry" carrying the marker on tmux, not a
        # bare "retry"; the SDK re-drives via its own queue and sends the bare command.
        ap = SRC.split('t == "apiRetry"', 1)[1].split("elif t ==", 1)[0]
        self.assertIn("romp-injected", ap, "the injected retry carries the romp-injected marker (tmux)")
        self.assertIn('if be is _TMUX else "retry"', ap, "marked on tmux, bare on the SDK")

    def test_that_injected_retry_is_authored_romp_not_human(self):
        # end-to-end: the exact text romp pastes → author 'romp' (the gray bubble), NOT 'human', even though
        # it arrives via a paste+Enter that Claude Code records as promptSource='typed'
        blocks = [{"type": "text", "text": "retry\n\n<!-- romp-injected -->"}]
        self.assertEqual(em.author_of(blocks, "typed", {}), "romp",
                         "the romp-injected marker wins over promptSource=typed → renders as a romp bubble")
        # sanity: a bare 'retry' (the old behavior) would have been a human prompt
        self.assertEqual(em.author_of([{"type": "text", "text": "retry"}], "typed", {}), "human")


if __name__ == "__main__":
    unittest.main()
