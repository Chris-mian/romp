#!/usr/bin/env python3
"""docs/reference.md's `romp board define` paragraph says what feed.css paints for a board's `chip` values.

A data board's category names its chip from the schema's four values; the reference lists them, and since plans/needs-you.md
(phase two) it says what the `blocked` value paints: the Needs you chip's dress, the name kept as a schema value, and no chip
value paints red, the hard stop's alone. Nothing else ties the sentence to the sheet, so these pins hold the doc to the code:
the sentence is quoted here, and feed.css's `.fcol-chip-*` family (the classes feed.ts builds for every board's column
header) is asserted to paint `blocked` in the Needs you token and no value in the red family. Shaped like
tests/test_reference_billing_label.py: text only."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _flat(text):
    return re.sub(r"\s+", " ", text)


REFERENCE = _flat(_read("docs", "reference.md"))
FEED_CSS = _read("ui", "webview", "feed.css")
CARD_BOARDS = _read("plans", "card-boards.md")


class BoardChipSentence(unittest.TestCase):
    def test_the_reference_says_what_the_blocked_chip_paints(self):
        self.assertIn("a `chip` from `working`, `blocked`, `completed` or `neutral`; `blocked` is the Needs you chip's dress, "
                      "the magenta of the category, its name kept as a schema value, and no chip value paints red, which is the "
                      "hard stop's alone", REFERENCE)

    def test_the_sheet_paints_blocked_in_the_token_and_no_chip_value_in_red(self):
        rules = dict(re.findall(r"\.fcol-chip-([a-z]+)\s*\{([^}]*)\}", FEED_CSS))
        self.assertIn("blocked", rules)
        self.assertIn("var(--st-needs-bg)", rules["blocked"], "the blocked chip value is the Needs you dress")
        for name, body in rules.items():
            self.assertNotRegex(body, r"var\(--err\)|var\(--st-blocked-bg\)|#e5484d|#c0392b", "a chip value in the hard stop's red: %s" % name)

    def test_the_plan_agrees(self):
        self.assertIn(".fcol-chip-blocked the Needs you magenta, the name a schema value", CARD_BOARDS)


if __name__ == "__main__":
    unittest.main()
