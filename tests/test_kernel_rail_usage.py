"""The Claude /usage rate-limit bars moved from the timeline toolbar to the left RAIL (the user 2026-06-26),
to shrink the timeline. They live in a different document (the shell), so the timeline iframe POSTS its usage
data to the shell ({romp:'usage'}) and the shell renders compact vertical bar-pairs (used % colored + elapsed
% slate) under the refresh button, with the full detail on hover. Standalone (Obsidian) keeps its own copy.
"""
import os
import pathlib
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class RailUsage(unittest.TestCase):
    def setUp(self):
        self.html = km._landing()

    def test_the_rail_hosts_the_usage_bars_under_the_refresh_button(self):
        self.assertIn("id=rail-usage", self.html, "a usage container sits in the rail")
        # ...positioned AFTER the refresh action (so it renders beneath it)
        self.assertLess(self.html.index("id=rail-refresh"), self.html.index("id=rail-usage"))
        self.assertIn(".ru-bar{", self.html, "the compact vertical bar styling")
        self.assertIn(".ru-lab{", self.html, "the percentage label styling")

    def test_the_shell_renders_the_posted_usage_with_the_timeline_colours_and_hover(self):
        self.assertIn("romp==='usage'", self.html, "the shell listens for the timeline's usage post")
        for win in ("fiveHour", "sevenDay"):
            self.assertIn(win, self.html, "renders both rate-limit windows")
        for col in ("#c0392b", "#e0b020", "#54B204"):                       # red / amber / green, same as the timeline
            self.assertIn(col, self.html, "used-bar colour %s (matches the timeline usage bars)" % col)
        self.assertIn("ru-w title=", self.html, "each window carries a native title — full detail on hover")
        self.assertIn("resets in", self.html, "the hover detail includes the reset countdown")

    def test_the_timeline_forwards_usage_to_the_shell_and_hides_its_own_copy_when_embedded(self):
        tv = (pathlib.Path(BIN).parent / "ui" / "romp-timeline-view.js").read_text()
        # only when embedded (window.parent !== window) — standalone/Obsidian keeps drawing them locally
        self.assertIn("window.parent !== window", tv)
        self.assertIn("romp: 'usage'", tv, "the timeline posts its usage data to the shell")
        self.assertIn("this._usageWrap.style.display = 'none'", tv, "and hides its own toolbar copy")


if __name__ == "__main__":
    unittest.main()
