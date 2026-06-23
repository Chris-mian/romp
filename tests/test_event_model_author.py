#!/usr/bin/env python3
"""author_of's sdk_human path (the user 2026-06-22): a human message to an SDK-backed romp session
lands in the transcript as promptSource "sdk" (it arrives over the programmatic stream-json channel),
so without this it rendered as the gray 'sdk' author instead of the blue human bubble. With sdk_human
set, an UNMARKED 'sdk' prompt is the human; romp-injected / postal markers still win."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(SCRIPTS, "romp-event-model")).load_module()

TEXT = [{"type": "text", "text": "do the thing"}]
INJECTED = [{"type": "text", "text": "status update <!-- romp-injected -->"}]


class AuthorSdkHuman(unittest.TestCase):
    def test_sdk_prompt_is_human_only_for_sdk_backed_sessions(self):
        self.assertEqual(em.author_of(TEXT, "sdk", {}, sdk_human=True), "human")   # SDK session → the human
        self.assertEqual(em.author_of(TEXT, "sdk", {}, sdk_human=False), "sdk")    # elsewhere → genuine sdk

    def test_default_is_unchanged_sdk(self):
        self.assertEqual(em.author_of(TEXT, "sdk", {}), "sdk")                      # default off → no behavior change

    def test_romp_injected_marker_wins_over_sdk_human(self):
        # a romp nudge to an SDK session is still gray 'romp', not the human, even with sdk_human on
        self.assertEqual(em.author_of(INJECTED, "sdk", {}, sdk_human=True), "romp")

    def test_typed_and_system_unaffected(self):
        self.assertEqual(em.author_of(TEXT, "typed", {}, sdk_human=True), "human")
        self.assertEqual(em.author_of(TEXT, "system", {}, sdk_human=True), "system")


if __name__ == "__main__":
    unittest.main()
