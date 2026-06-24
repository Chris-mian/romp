"""Per-pane vertical button STRIP in the shell (the user 2026-06-24).

The chat (right edge) and feed (left edge) panes each grow a thin vertical rail that HOLDS the minimize
button, and — on the chat — the rotated Fleet/Chat toggles (replacing the chat-tab-bar pill). The iframe is
inset by --strip so the rail reserves its own space rather than overlaying content. The timeline keeps its
own horizontal edge bar. Source-level pin against km._landing().
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class PaneStripTest(unittest.TestCase):
    def setUp(self):
        self.html = km._landing()

    def test_each_inner_edge_pane_has_a_strip_holding_its_minimize_button(self):
        # chat strip on the right, feed strip on the left; the collapse buttons live INSIDE the strips now
        self.assertIn("<div class=pane-strip id=chat-strip>", self.html)
        self.assertIn("<div class=pane-strip id=feed-strip>", self.html)
        self.assertIn("<div class=strip-btn id=chat-collapse", self.html)
        self.assertIn("<div class=strip-btn id=feed-collapse", self.html)
        # the timeline keeps its own horizontal edge bar (NOT a strip)
        self.assertIn("<div class=collapse-btn id=tl-collapse", self.html)

    def test_the_strip_reserves_space_by_sizing_the_iframe_explicitly(self):
        # the rail is a dedicated column, not an overlay. iframes are REPLACED elements, so top+bottom with
        # height:auto would collapse them to ~150px — size them EXPLICITLY (full height, width = pane minus the
        # strip) instead. The feed strip is narrower (only a minimize button) than the chat's (Chat/Fleet labels).
        self.assertIn(".pane-strip{position:absolute;top:0;bottom:0;width:var(--strip,20px)", self.html)
        self.assertIn("#chat-pane>iframe,#feed-pane>iframe{position:absolute;top:0;height:100%;width:calc(100% - var(--strip,20px))}", self.html)
        self.assertIn("#chat-pane>iframe{left:0}", self.html)
        self.assertIn("#feed-pane>iframe{right:0}", self.html)
        self.assertIn("#chat-pane{--strip:18px}#feed-pane{--strip:12px}", self.html)   # feed rail narrower than chat's

    def test_chat_strip_has_rotated_fleet_and_chat_toggles_lit_in_romp_blue(self):
        self.assertIn("<div class=strip-toggle data-fleet=chat", self.html)
        self.assertIn("<div class=strip-toggle data-fleet=fleet", self.html)
        # rotated, reading top-to-bottom; the live view's button is lit in the romp accent
        self.assertIn(".strip-toggle{flex:0 0 auto;writing-mode:vertical-rl", self.html)
        self.assertIn(".strip-toggle.on{color:#9cd2ff}", self.html)
        # clicking a toggle posts the SAME {romp:'toggleFleet',to:...} the old pill sent; .on tracks show-fleet
        self.assertIn("window.postMessage({romp:'toggleFleet',to:b.getAttribute('data-fleet')}", self.html)
        self.assertIn("b.classList.toggle('on',(b.getAttribute('data-fleet')==='fleet')===on)", self.html)

    def test_collapsed_chat_rail_keeps_the_fleet_chat_toggles_and_clicking_expands(self):
        # the Fleet/Chat toggles are NOT hidden when the chat collapses (the user 2026-06-24) — so Fleet stays
        # reachable from the rail; the redundant lowercase 'chat' label is dropped for the chat pane.
        self.assertNotIn("body.cc-chat #chat-strip .strip-toggle", self.html)        # toggles no longer hidden
        self.assertNotIn("body.cc-chat #chat-pane .pane-label", self.html)           # chat label dropped (toggles are it)
        self.assertIn("body.cc-feed #feed-pane .pane-label{display:block", self.html)  # feed still labels its rail
        # clicking a toggle on a collapsed rail expands the pane first (clicks the collapse button), then shows the view
        self.assertIn("if(document.body.classList.contains('cc-chat')){var cb=document.getElementById('chat-collapse');if(cb)cb.click();}", self.html)

    def test_a_collapsed_pane_drops_the_blue_focus_ring(self):
        # collapsed = not open → no blue focus ring; it reads gray/minimised even if it held focus (the user 2026-06-24)
        self.assertIn("body.cc-chat #chat-pane.pane-focused::after,body.cc-feed #feed-pane.pane-focused::after,body.cc-tl #tl-pane.pane-focused::after{display:none}", self.html)

    def test_strip_is_hidden_on_mobile_and_the_iframe_inset_is_reset(self):
        # mobile shows one pane at a time (no strip); the desktop iframe inset must be undone there too
        self.assertIn(".pane{display:contents}.collapse-btn,.pane-label,.pane-strip{display:none}", self.html)
        self.assertIn("#chat-pane>iframe,#feed-pane>iframe{position:static;inset:auto;width:100%;height:100%}", self.html)


if __name__ == "__main__":
    unittest.main()
