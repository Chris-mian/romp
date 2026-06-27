"""The GLOBAL colormap (the user 2026-06-26) now colors the CONTEXT-window % bars too, not just the feed
recency tint + the usage "used" bar. The kernel computes the color SERVER-SIDE (ctxColor=[r,g,b]) where it
builds each payload — the timeline lanes (build_timeline) and the chat status (build_session) — so the three
client surfaces (timeline battery, chat statusline battery, chat tab-tooltip battery) just apply it, exactly
like the usage bar. The gear's colormap label is global now ("Colormap", not "Feed colormap").
"""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class ContextColormap(unittest.TestCase):
    def test_build_timeline_colors_the_lane_context_bar_server_side(self):
        src = inspect.getsource(km.build_timeline)
        self.assertIn("ctx_stops = cm.stops_for(_colormap())", src, "the global colormap stops are read once")
        self.assertIn('"ctxColor"', src, "each lane carries a server-computed context color")
        self.assertIn("cm.ramp(1 - (tm[\"context\"] or 0) / 100.0, ctx_stops)", src,
                      "context% maps onto the global colormap, REVERSED so the battery is unaffected by a map flip")

    def test_build_session_status_carries_a_context_color(self):
        src = inspect.getsource(km.build_session)
        self.assertIn('"ctxColor"', src, "the chat status carries a server-computed context color")
        self.assertIn("cm.ramp(1 - tm[\"context\"] / 100.0, cm.stops_for(_colormap()))", src,
                      "context% maps onto the global colormap, REVERSED (1 - pct)")

    def test_context_reversal_keeps_color_through_a_map_flip(self):
        # the point of reading context REVERSED (1 - pct): flipping the colormap (reversing its stops) leaves
        # the context battery's color for any fill UNCHANGED — the identity ramp(1-v, reversed) == ramp(v,
        # stops). A forward-reading surface (feed cards, fleet) switches with the flip; the battery doesn't
        # (the user 2026-06-27).
        stops = km.cm.stops_for("aurora")
        rev = list(reversed(stops))
        for v in (0.0, 0.3, 0.5, 0.8, 1.0):
            self.assertEqual(km.cm.ramp(1 - v, rev), km.cm.ramp(v, stops),
                             "context (reversed, on the flipped map) == its color before the flip")

    def test_context_color_is_none_when_there_is_no_context_yet(self):
        # both payloads guard on context is not None so a dormant/never-reported lane sends no color
        self.assertIn('if tm and tm["context"] is not None else None', inspect.getsource(km.build_timeline))
        self.assertIn('if tm["context"] is not None else None', inspect.getsource(km.build_session))

    def test_the_gear_colormap_label_is_global_not_feed_only(self):
        self.assertIn(">Colormap<", km._GEAR_HTML, "the label is global now")
        self.assertNotIn(">Feed colormap<", km._GEAR_HTML, "no longer scoped to the feed")

    def test_ramp_maps_higher_to_the_bright_end_on_a_darklight_map(self):
        # ramp(v) walks v=0→stops[0] to v=1→stops[-1]; on a DARK→LIGHT map (hawaii) a higher fill lands
        # brighter. (The default 'aurora' is intentionally ISO-LUMINANT — it conveys value by hue, not
        # brightness — so this brightness check is pinned on hawaii, not cm.DEFAULT.)
        stops = km.cm.stops_for("hawaii")
        lo, hi = km.cm.ramp(0.1, stops), km.cm.ramp(0.95, stops)
        self.assertGreater(sum(hi), sum(lo), "fuller context → brighter color on a dark→light map")


if __name__ == "__main__":
    unittest.main()
