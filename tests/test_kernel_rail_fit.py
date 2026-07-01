"""On a SHORT window the far-left rail used to overflow — the ⚙ gear spilled off the bottom over the feed (the
user 2026-06-27). Fix: the rail splits into a SCROLLABLE top (toggles + usage) and a FIXED bottom (refresh +
gear, always visible). The usage bars DEGRADE GRACEFULLY when room runs out (fitRail bumps data-ruc: shorter
bars -> drop % -> drop 5h/7d labels -> hidden last, the user 2026-07-01); only if even the toggles don't fit do
they scroll (hidden scrollbar). So the gear/refresh never collide with the labels."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class RailFit(unittest.TestCase):
    def test_rail_splits_into_scroll_top_and_fixed_actions(self):
        land = km._landing()
        # the toggles + usage live in a scrollable wrapper; the actions in a fixed, bottom-pinned one
        self.assertIn("<div class=rail-scroll>", land)
        self.assertIn("<div class=rail-acts>", land)
        # the actions are AFTER the scroll wrapper in the DOM (so they're the fixed bottom group)
        self.assertLess(land.index("class=rail-scroll"), land.index("class=rail-acts"))
        self.assertLess(land.index("id=rail-usage"), land.index("class=rail-acts"), "usage scrolls; actions are fixed")

    def test_scroll_group_styling_and_hidden_scrollbar(self):
        land = km._landing()
        self.assertIn(".rail-scroll{flex:0 1 auto;min-height:0;display:flex;flex-direction:column;gap:6px;"
                      "overflow-y:auto;overflow-x:hidden;scrollbar-width:none}", land)
        self.assertIn(".rail-scroll::-webkit-scrollbar{width:0;height:0}", land)
        self.assertIn(".rail-acts{flex:0 0 auto;display:flex;flex-direction:column;gap:2px;margin-top:auto;padding-bottom:2px}", land)
        self.assertIn(".pane-rail{flex:0 0 30px;box-sizing:border-box;display:flex;flex-direction:column;gap:6px;"
                      "padding:8px 0;background:#202021;border-right:1px solid #2c2c2d;z-index:10;overflow:hidden}", land)

    def test_usage_bars_degrade_gracefully_when_tight(self):
        land = km._landing()
        self.assertNotIn(".rail-scroll.rail-tight #rail-usage{display:none}", land, "no more vanish-all-at-once")
        self.assertNotIn("#rail-refresh{margin-top:auto}", land, "the old per-action pin is gone")
        # the degrade order: shorter bars, then drop the % readout, then the 5h/7d labels, then hide LAST
        self.assertIn("#rail-usage[data-ruc='1'] .ru-bars{height:24px}", land, "level 1: compress bars")
        self.assertIn("#rail-usage[data-ruc='2'] .ru-lab{display:none}", land, "level 2: drop the % readout")
        self.assertIn("#rail-usage[data-ruc='3'] .ru-win{display:none}", land, "level 3: drop the 5h/7d labels")
        self.assertIn("#rail-usage[data-ruc='4']{display:none}", land, "level 4: hide only as a last resort")

    def test_fitRail_bumps_the_level_until_it_fits_and_re_runs(self):
        js = km._LANDING_USAGE_JS
        self.assertIn("function fitRail()", js)
        self.assertIn("var sc=el.parentNode;", js)
        # walk levels 0..4, setting data-ruc, stopping at the first that fits
        self.assertIn("for(var lvl=0;lvl<=4;lvl++){el.dataset.ruc=String(lvl);if(sc.scrollHeight<=sc.clientHeight+1)break;}", js)
        self.assertIn("window.addEventListener('resize',fitRail)", js)
        self.assertIn("render=function(u){_render(u);fitRail();}", js, "re-fit after the bars re-render")
        self.assertIn("requestAnimationFrame(fitRail)", js, "fit once on load")


if __name__ == "__main__":
    unittest.main()
