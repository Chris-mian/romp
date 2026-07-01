"""The Claude /usage rate-limit bars moved from the timeline toolbar to the left RAIL (the user 2026-06-26),
to shrink the timeline. They live in a different document (the shell), so the timeline iframe POSTS its usage
data to the shell ({romp:'usage'}) and the shell renders compact vertical bar-pairs (used % colored + elapsed
% slate) under the refresh button, with the full detail on hover. Standalone (Obsidian) keeps its own copy.
"""
import inspect
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

    def test_the_rail_usage_sticks_to_the_top_with_refresh_and_settings_at_the_bottom(self):
        # the user 2026-06-26/27: usage sits in the scrollable TOP group (under the toggles); refresh + settings
        # are in the FIXED .rail-acts at the BOTTOM, settings (⛭ rail-gear) at the very bottom, refresh above it.
        self.assertIn("id=rail-usage", self.html, "a usage container sits in the rail")
        self.assertLess(self.html.index("id=rail-usage"), self.html.index("id=rail-refresh"),
                        "usage is above refresh (top group)")
        self.assertLess(self.html.index("id=rail-refresh"), self.html.index("id=rail-gear"),
                        "refresh is above settings (settings is the very bottom)")
        self.assertIn(".rail-acts{flex:0 0 auto;display:flex;flex-direction:column;gap:2px;margin-top:auto;padding-bottom:2px}",
                      self.html, "the bottom action group is pinned down")
        self.assertIn(".ru-bar{", self.html, "the compact vertical bar styling")
        self.assertIn(".ru-lab{", self.html, "the percentage label styling")

    def test_the_shell_renders_the_posted_usage_colormapped_with_a_hover_panel(self):
        self.assertIn("romp==='usage'", self.html, "the shell listens for the timeline's usage post")
        for win in ("fiveHour", "sevenDay"):
            self.assertIn(win, self.html, "renders both rate-limit windows")
        # the used bar wears the SELECTED COLORMAP colour (server-computed in _usage, read here as seg.color)
        self.assertIn("seg.color", self.html, "the used bar is colored by the selected colormap")
        self.assertIn("cm.ramp(pct / 100.0, stops)", inspect.getsource(km._usage),
                      "_usage maps used-% onto the global colormap")
        # ONE shared hover PANEL for BOTH windows (the user 2026-06-26): it reproduces the used/elapsed bars
        # that used to sit under the timeline, with the reset countdown, and NO explanatory prose.
        self.assertIn("#ru-tip{", self.html, "a styled hover tooltip panel")
        self.assertIn("resets in", self.html, "the panel includes the reset countdown")

    def test_the_usage_tooltip_is_one_shared_panel_reproducing_both_windows_bars(self):
        # a SINGLE tooltip on the whole rail-usage area (mouseenter on el), not a per-window panel
        self.assertIn("el.addEventListener('mouseenter',showTip)", self.html, "one shared tooltip for the area")
        self.assertIn("['fiveHour','sevenDay'].filter", self.html, "the tooltip covers BOTH windows at once")
        # it reproduces the used + elapsed bars (the exact set that used to sit under the timeline)
        self.assertIn("ru-tip-track", self.html, "horizontal used/elapsed bars in the tooltip")
        self.assertIn(">used<", self.html)
        self.assertIn(">elapsed<", self.html)
        # and drops the old explanatory prose ("...rate-limit window") — no extra stuff
        self.assertNotIn("rate-limit window", self.html, "no explanatory prose, just the bars + %")

    def test_the_timeline_forwards_usage_to_the_shell_and_hides_its_own_copy_when_embedded(self):
        tv = (pathlib.Path(BIN).parent / "ui" / "romp-timeline-view.js").read_text()
        # only when embedded (window.parent !== window) — standalone/Obsidian keeps drawing them locally
        self.assertIn("window.parent !== window", tv)
        self.assertIn("romp: 'usage'", tv, "the timeline posts its usage data to the shell")
        self.assertIn("this._usageWrap.style.display = 'none'", tv, "and hides its own toolbar copy")


if __name__ == "__main__":
    unittest.main()
