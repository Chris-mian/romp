"""The Settings gear groups its rows into labelled SUBSECTIONS (the user 2026-06-24): Chat / Feed /
Sessions / Debug, in that order, so the settings read by surface instead of one flat list. (The Feed's
'Oldest first' toggle was removed 2026-06-27 — the feed is always oldest-at-top now.)
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class SettingsSectionsTest(unittest.TestCase):
    def test_the_subsection_headers_are_present_in_order(self):
        h = km._gear_html()
        self.assertIn("<div class='rs-sec rs-sec-first'>Chat</div>", h)
        self.assertIn("<div class=rs-sec>Feed</div>", h)
        self.assertIn("<div class=rs-sec>Sessions</div>", h)
        self.assertIn("<div class=rs-sec>Timeline</div>", h)
        self.assertIn("<div class=rs-sec>Debug</div>", h)
        # in order: Chat < Feed < Sessions < Timeline < Debug
        self.assertLess(h.index(">Chat<"), h.index(">Feed<"))
        self.assertLess(h.index(">Feed<"), h.index(">Sessions<"))
        self.assertLess(h.index(">Sessions<"), h.index(">Timeline<"))
        self.assertLess(h.index(">Timeline<"), h.index(">Debug<"))

    def test_each_setting_sits_under_the_right_section(self):
        h = km._gear_html()
        # Chat: compact + branch come before the Feed header
        self.assertLess(h.index("id=rs-compact"), h.index(">Feed<"))
        self.assertLess(h.index("id=rs-branch"), h.index(">Feed<"))
        # Feed: colormap between Feed and Sessions (the Oldest-first toggle was removed 2026-06-27)
        self.assertTrue(h.index(">Feed<") < h.index("id=rs-cmap") < h.index(">Sessions<"))
        self.assertNotIn("rs-oldest", h)
        # Sessions: backend, default dir, auto-nudge between Sessions and Timeline
        self.assertTrue(h.index(">Sessions<") < h.index("id=rs-backend") < h.index(">Timeline<"))
        self.assertTrue(h.index(">Sessions<") < h.index("id=rs-defaultdir") < h.index(">Timeline<"))
        self.assertTrue(h.index(">Sessions<") < h.index("id=rs-autonudge") < h.index(">Timeline<"))
        # Timeline: collapse idle gaps between Timeline and Debug (the user 2026-06-25, moved from the toolbar)
        self.assertTrue(h.index(">Timeline<") < h.index("id=rs-collapsegaps") < h.index(">Debug<"))
        # Debug: debug mode, analytics, version after Debug
        self.assertLess(h.index(">Debug<"), h.index("id=rs-debug"))
        self.assertLess(h.index(">Debug<"), h.index("id=ra-open"))
        self.assertLess(h.index(">Debug<"), h.index("id=rsver"))

    def test_collapse_gaps_is_wired_to_the_shared_collapseGaps_setting(self):
        # the gear JS persists/loads romp:settings.collapseGaps; the timeline reads it (see romp-timeline-view.js)
        self.assertIn("collapseGaps:true", km._GEAR_JS)
        self.assertIn("s.collapseGaps=cg.checked", km._GEAR_JS)

    def test_section_header_styling_exists(self):
        self.assertIn("#rsettings .rs-sec{", km._GEAR_CSS)
        self.assertIn("#rsettings .rs-sec-first{border-top:0", km._GEAR_CSS)

    def test_oldest_first_toggle_is_gone(self):
        # the feed is always oldest-at-top now → no checkbox, no wiring (the user 2026-06-27)
        self.assertNotIn("rs-oldest", km._gear_html())
        self.assertNotIn("oldestFirst", km._GEAR_JS)


if __name__ == "__main__":
    unittest.main()
