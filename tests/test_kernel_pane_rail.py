"""Far-left pane rail in the shell (the user 2026-06-24).

Replaces the two per-pane vertical strips between the top panes with ONE thin vertical toolbar on the far
left, holding Chat / Fleet / Feed toggles. Each pane is an independent binary on/off, in a fixed visual
order — Chat leftmost, Fleet middle, Feed rightmost — and any subset (or none, or all) can be shown at
once. Fleet is its OWN pane now (no longer an overlay swapped inside the chat pane). The timeline keeps its
own separate minimize (the opaque top-right cut-out). Source-level pin against km._landing().
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class PaneRailTest(unittest.TestCase):
    def setUp(self):
        self.html = km._landing()

    def test_far_left_rail_holds_chat_fleet_feed_timeline_toggles_in_fixed_order(self):
        # one thin toolbar on the far left; FOUR toggle buttons, ordered to match the panes' left→right order
        self.assertIn("<div class=pane-rail>", self.html)
        self.assertIn("<div class=rail-btn data-pane=chat>Chat</div>", self.html)
        self.assertIn("<div class=rail-btn data-pane=fleet>Fleet</div>", self.html)
        self.assertIn("<div class=rail-btn data-pane=feed>Feed</div>", self.html)
        self.assertIn("<div class=rail-btn data-pane=timeline>Timeline</div>", self.html)
        # Chat before Fleet before Feed before Timeline in the rail (fixed top-to-bottom order)
        idxs = [self.html.index("data-pane=" + k) for k in ("chat", "fleet", "feed", "timeline")]
        self.assertEqual(idxs, sorted(idxs), "rail order must be Chat, Fleet, Feed, Timeline")
        # the old per-pane strips + the show-fleet swap + the timeline minimize bar are gone
        self.assertNotIn("pane-strip", self.html)
        self.assertNotIn("strip-toggle", self.html)
        self.assertNotIn("show-fleet", self.html)
        self.assertNotIn("tl-collapse", self.html)
        self.assertNotIn("cc-tl", self.html)

    def test_four_independent_panes_in_fixed_order_with_gutters_between(self):
        # the panes appear in DOM order chat | gv-a | fleet | gv-b | feed | gv-c | timeline (fixed visual order)
        order = ["id=chat-pane", "id=gv-a", "id=fleet-pane", "id=gv-b", "id=feed-pane", "id=gv-c", "id=tl-pane"]
        idxs = [self.html.index(tok) for tok in order]
        self.assertEqual(idxs, sorted(idxs), "panes/gutters must be chat | fleet | feed | timeline")
        # each pane is shown/hidden independently by its own body.po-* class
        self.assertIn("body:not(.po-chat) #chat-pane{display:none}", self.html)
        self.assertIn("body:not(.po-fleet) #fleet-pane{display:none}", self.html)
        self.assertIn("body:not(.po-feed) #feed-pane{display:none}", self.html)
        self.assertIn("body:not(.po-timeline) #tl-pane{display:none}", self.html)

    def test_default_layout_is_chat_plus_feed(self):
        # today's layout is the default: Chat + Feed on, Fleet off (inlined on <body> so first paint is right)
        self.assertIn("<body class='po-chat po-feed'>", self.html)

    def test_gutters_show_only_between_two_visible_panes(self):
        # gv-a sits chat|fleet → only when BOTH are shown
        self.assertIn("body:not(.po-chat) #gv-a,body:not(.po-fleet) #gv-a{display:none}", self.html)
        # gv-b sits (fleet|chat)|feed → it doubles as the chat|feed gutter when fleet is off, so it hides only
        # when feed is off OR neither chat nor fleet is on (feed would then be the lone pane)
        self.assertIn("body:not(.po-feed) #gv-b,body:not(.po-chat):not(.po-fleet) #gv-b{display:none}", self.html)
        # gv-c sits (rightmost of feed/fleet/chat)|timeline → hides when timeline is off OR nothing is to its left
        self.assertIn("body:not(.po-timeline) #gv-c,body:not(.po-chat):not(.po-fleet):not(.po-feed) #gv-c{display:none}", self.html)

    def test_lit_rail_button_is_the_romp_accent(self):
        # the shell defines the accent locally (it loads no styles.css) and the ON toggle uses it
        self.assertIn(":root{--accent:#9cd2ff", self.html)
        self.assertIn(".rail-btn.on{color:var(--accent)", self.html)

    def test_rail_drives_a_persisted_pane_controller_exposed_for_the_legacy_toggle(self):
        # the controller toggles po-* from the rail, persists the set, and exposes __rompPaneToggle so the
        # legacy {romp:'toggleFleet'} postMessage routes through the same path
        self.assertIn("var PK='romp-panes',po={chat:true,fleet:false,feed:true,timeline:false}", self.html)
        self.assertIn("window.__rompPaneToggle=togglePane", self.html)
        self.assertIn("togglePane(b.getAttribute('data-pane'))", self.html)
        self.assertIn("document.body.classList.toggle('po-chat',!!po.chat)", self.html)
        # ?panes=chat,fleet bookmarks an explicit set
        self.assertIn("get('panes')", self.html)

    def test_panes_are_resizable_by_flex_grow_persisted_per_pane(self):
        # each pane grows by a per-pane var the gutters write; the drag normalises visible panes to their px
        # widths first (so it shifts only the pair it sits between) and persists the grows across reloads
        self.assertIn("#chat-pane{flex:var(--g-chat,60) 1 0}#fleet-pane{flex:var(--g-fleet,34) 1 0}#feed-pane{flex:var(--g-feed,40) 1 0}#tl-pane{flex:var(--g-timeline,40) 1 0}", self.html)
        self.assertIn("var GK='romp-pane-grow'", self.html)
        self.assertIn("setGrow(key(id),document.getElementById(id).offsetWidth)", self.html)
        self.assertIn("localStorage.setItem(GK,JSON.stringify(grow))", self.html)
        # gv-b picks its left neighbour live: fleet when shown, else chat (so it's the chat|feed gutter too)
        self.assertIn("document.body.classList.contains('po-fleet')?'fleet-pane':'chat-pane'", self.html)

    def test_timeline_is_the_fourth_rail_pane_not_a_bottom_band(self):
        # the timeline is its own rail-toggled pane now (the user 2026-06-24): no bottom band, no grid, no
        # minimize button. .col is a plain flex column holding the single .row of panes.
        self.assertIn(".col{display:flex;flex-direction:column;height:100vh}", self.html)
        self.assertNotIn("grid-template-rows", self.html)        # the bottom-band grid is gone
        self.assertNotIn("tl-collapse", self.html)               # no minimize button
        self.assertNotIn("collapse-btn", self.html)
        self.assertNotIn("id=gh", self.html)                     # no horizontal splitter
        self.assertIn("<div class=pane id=tl-pane><iframe id=f-timeline src=/timeline></iframe></div>", self.html)

    def test_rail_and_fleet_pane_are_hidden_on_mobile(self):
        # mobile shows one pane at a time via the bottom tab bar, not the rail; the desktop po-* pane-hiding
        # must NOT leak in (the tab bar governs), so chat/feed/timeline panes are forced back to display:contents
        self.assertIn(".gv,.pane-rail{display:none}", self.html)
        self.assertIn("#chat-pane,#feed-pane,#tl-pane{display:contents!important}", self.html)
        self.assertIn("#fleet-pane{display:none!important}", self.html)   # Fleet stays desktop-only


if __name__ == "__main__":
    unittest.main()
