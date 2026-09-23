#!/usr/bin/env python3
"""The reference documents the tab STATE BADGE as the default (plans/tab-state-badge.md, the 2026-09-23 flip): the
count dot and the amber left dot are what a tab shows by default, the dashed rings and the phone's bar/border the
switched-off shapes. A regex over the two paragraphs, in the pattern of tests/test_host_transport.py, so the doc cannot
drift back to calling the ring the default."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


class TabBadgeDoc(unittest.TestCase):
    def test_the_reference_makes_the_count_dot_the_default_not_the_ring(self):
        doc = open(os.path.join(ROOT, "docs", "reference.md")).read()
        i = doc.index("### The rings on a tab")
        para = flat(doc[i:doc.index("### Tags and groups in the tab strip", i)])
        # Needs you defaults to the top-right count dot, not the ring
        self.assertIn('a small **magenta dot** sits at the tab\'s\ntop-right corner'.replace("\n", " "), para,
                      "the Needs-you default is the top-right count dot")
        self.assertIn("carrying a count of what needs you", para)
        # retrying defaults to the hollow amber left dot (a shape cue)
        self.assertIn("hollow **amber left dot**", para, "retrying's default is the hollow amber left dot")
        # the setting is ON by default; the rings are the switched-off shapes
        self.assertIn("is **on by default**", para, "the State badge setting is on by default")
        self.assertIn("Turn it OFF to swap\nthose two back to the outline shapes".replace("\n", " "), para,
                      "the rings are the switched-off shapes, not the default")
        self.assertNotIn("off by default", para, "the reference no longer calls the ring/the setting the default")
        self.assertNotIn("what shows when the setting is off (the default)", para)
        # the notification and one-colour sentences name the cue/count dot, not the ring/picker's bar as what shows
        self.assertNotIn("the ring is that card", para, "the notification's cue is the card by the default dot, not 'the ring'")
        self.assertIn("the cue is that card", para)
        self.assertNotIn("a card's question mark, the ring, the picker's bar", para, "the one-colour list names the count dot, the ring/bar as the switched-off shapes")
        self.assertIn("the tab's count dot (its dashed ring with the badge off)", para)


if __name__ == "__main__":
    unittest.main()
