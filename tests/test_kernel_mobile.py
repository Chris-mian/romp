#!/usr/bin/env python3
"""Mobile shell: the combined landing page collapses to a one-pane-at-a-time tab switcher on a
narrow/touch viewport, and the kernel tells the shell to switch to Chat when a feed/timeline tap
brings the chat forward. Pure-HTML + routing asserts; no real session data.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_mobile", os.path.join(BIN, "romp-kernel")).load_module()


class LandingShell(unittest.TestCase):
    def test_three_panes_are_addressable_iframes(self):
        html = km._landing()
        for fid in ("id=f-chat", "id=f-feed", "id=f-timeline"):
            self.assertIn(fid, html)

    def test_mobile_tabbar_one_button_per_pane(self):
        html = km._landing()
        self.assertIn("id=mtabs", html)
        for pane in ("data-pane=chat", "data-pane=feed", "data-pane=timeline"):
            self.assertIn(pane, html)

    def test_desktop_unchanged_tabbar_hidden_until_breakpoint(self):
        html = km._landing()
        self.assertIn("#mtabs{display:none}", html)   # hidden by default (desktop)
        self.assertIn("@media", html)                 # a breakpoint reveals it + collapses to one pane
        self.assertIn(".m-on{display:block}", html)   # the single active pane on mobile
        # the desktop 3-pane grid is still here untouched
        self.assertIn(".col{display:grid", html)
        self.assertIn("src=/chat", html)
        self.assertIn("src=/feed", html)
        self.assertIn("src=/timeline", html)

    def test_mobile_pane_has_explicit_height_not_auto(self):
        # regression: the mobile pane was sized with height:auto + bottom offset; mobile browsers read
        # height:auto on an iframe as "size to content" and collapse it (chat shrank to its tab bar).
        html = km._landing()
        self.assertIn("100dvh", html)                          # explicit, address-bar-aware viewport height
        self.assertNotIn("height:auto;display:none", html)     # the collapsing iframe rule is gone

    def test_shell_uses_flex_column_so_bar_cannot_cover_the_pane(self):
        # regression: the fixed-position bar overlapped the chat composer. A flex column tiles the pane
        # and the bar so they can't overlap; one pane shows at a time, keyed off body[data-tab].
        html = km._landing()
        self.assertIn("body[data-tab=timeline] .row{display:none}", html)
        self.assertIn("data-tab", km._LANDING_MOBILE_JS)       # show() marks the active pane on <body>

    def test_shell_reveal_listener_wired(self):
        html = km._landing()
        self.assertIn("app=shell", html)              # shell WS catches kernel reveals (feed/timeline tap)
        self.assertIn("'reveal'", html)               # ...and window reveals (timeline deep-link)

    def test_splitter_queries_the_timeline_iframe_that_exists(self):
        # regression: the desktop splitter used to getElementById('t') with no such element, throwing
        # on every load (which also killed any script after it). It must query the real iframe id.
        self.assertIn("id=f-timeline", km._landing())             # the iframe carries this id
        self.assertIn("getElementById('f-timeline')", km._LANDING_JS)
        self.assertNotIn("getElementById('t')", km._LANDING_JS)   # the stale id is gone

    def test_mobile_switcher_is_isolated_in_its_own_script(self):
        # the switcher runs in a separate <script> so a splitter throw can't disable the tab bar
        # (splitter + mobile switcher + the build-staleness banner = 3 isolated scripts)
        html = km._landing()
        self.assertEqual(html.count("<script>"), 3)

    def test_bottom_bar_is_text_only_and_compact(self):
        html = km._landing()
        self.assertNotIn("class=ic", html)                       # no icon spans — text labels only
        self.assertIn(">Chat</button>", html)                    # plain text label, no icon child
        self.assertIn("#mtabs{display:flex;flex:0 0 auto", html)  # sized to its text, not a tall fixed bar


class ChatSessionPicker(unittest.TestCase):
    def test_chat_page_collapses_tabs_into_a_header_on_mobile(self):
        chat = km._chat_page()
        self.assertIn("#mhdr", chat)                        # the compact header replaces the tab strip
        self.assertIn("#tabbar #tabs{display:none}", chat)  # the wrapping multi-row tab strip is hidden
        self.assertIn("id='mcur'", km._CHAT_MOBILE_JS)      # current-session button that opens the list
        self.assertIn("id='mlist'", km._CHAT_MOBILE_JS)     # the dropdown list of sessions

    def test_desktop_hides_the_mobile_header_and_list(self):
        # regression: #mlist (a #tabbar sibling, not inside #mhdr) had no desktop rule, so on desktop it
        # rendered the session rows as plain text in the tab bar. Both must be hidden off-mobile.
        self.assertIn("#mhdr,#mlist{display:none}", km._CHAT_MOBILE_CSS)

    def test_picker_is_custom_colored_not_native_select(self):
        # a native <select> can't render the per-session identity colors, so the picker is our own element
        js, css = km._CHAT_MOBILE_JS, km._CHAT_MOBILE_CSS
        self.assertNotIn("createElement('select')", js)   # not native
        self.assertIn("--chip-bg", js)                    # reads each session's identity color
        self.assertIn("#mcur.colored", css)               # the current button wears that color

    def test_picker_routes_a_pick_and_wires_new_session_and_summary(self):
        js = km._CHAT_MOBILE_JS
        self.assertIn(".tab[data-id", js)             # a row tap clicks the real tab (render.js focuses it)
        self.assertIn("MutationObserver", js)         # re-syncs as tabs change
        self.assertIn(".tab-add", js)                 # + → open / new session
        self.assertIn(".tab-collapse", js)            # ▾ → toggle the summary


class RevealRouting(unittest.TestCase):
    def test_reveal_chat_focuses_chat_and_nudges_shell(self):
        sent = []
        orig = km._send_to_app
        km._send_to_app = lambda app, msg: sent.append((app, msg))
        try:
            km._reveal_chat({"type": "focus", "id": "s1"})
        finally:
            km._send_to_app = orig
        apps = [a for a, _ in sent]
        self.assertIn("chat", apps)                   # still focuses the chat clients (unchanged behavior)
        self.assertIn("shell", apps)                  # AND tells the mobile shell to show the Chat tab
        chat_msg = next(m for a, m in sent if a == "chat")
        shell_msg = next(m for a, m in sent if a == "shell")
        self.assertEqual(chat_msg["id"], "s1")        # the original focus payload is preserved verbatim
        self.assertEqual(shell_msg, {"type": "reveal", "pane": "chat"})


if __name__ == "__main__":
    unittest.main()
