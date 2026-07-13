"""The ↻ kernel-restart button is decoupled from Debug mode (the user 2026-06-24).

It used to be hidden unless Debug mode was on (an `applyDebug()` helper in the gear JS toggled its
`style.display` off `s.debug`). The user wanted it ALWAYS visible, so that gating is gone — Debug now
only governs the timeline's judging band. Source-level pin against the kernel's embedded gear chrome.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class RefreshButtonDecoupledTest(unittest.TestCase):
    def test_refresh_button_is_always_present(self):
        # the ↻ moved to the shell's far-left rail (the user 2026-06-25) so it persists regardless of which
        # panes are open — always present, still POSTs /restart then polls /healthz and reloads.
        html = km._landing()
        self.assertIn("id=rail-refresh", html)
        self.assertIn("fetch('/restart',{method:'POST'})", html)
        self.assertNotIn("id=rrefresh", _gear_src())   # gone from the feed gear

    def test_refresh_button_is_not_gated_on_debug(self):
        # the old applyDebug() helper (which hid #rrefresh unless s.debug) is gone entirely …
        self.assertNotIn("applyDebug", _gear_src())
        # … and nothing else hides the refresh button by toggling its display off the debug flag
        self.assertNotRegex(_gear_src(), r"rf\.style\.display\s*=")
        self.assertNotRegex(_gear_src(), r"rrefresh[^\n]*display:none")

    def test_judge_toggles_do_not_touch_the_refresh_button(self):
        # the judge-set toggles (which replaced the single Debug toggle) save the pref + emit, but never
        # re-run any refresh-button visibility logic — the ↻ is always visible
        self.assertIn("s.showIndexJudges = jix.checked", _gear_src())
        self.assertIn("s.showTriageJudges = jtr.checked", _gear_src())
        self.assertNotRegex(_gear_src(), r"checked;[^\n]*applyDebug")


if __name__ == "__main__":
    unittest.main()


# The gear moved from kernel-inline strings into the shared feed bundle
# (2026-07-13): ui/webview/gear.js is the single source both hosts render, so
# the gear pins read THAT file (and feed.css for its styling).
def _gear_src():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "ui" / "webview" / "gear.js").read_text()


def _gear_css_src():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "ui" / "webview" / "gear.css").read_text()
