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
        self.assertNotIn("id=rrefresh", km._GEAR_HTML)   # gone from the feed gear

    def test_refresh_button_is_not_gated_on_debug(self):
        # the old applyDebug() helper (which hid #rrefresh unless s.debug) is gone entirely …
        self.assertNotIn("applyDebug", km._GEAR_JS)
        # … and nothing else hides the refresh button by toggling its display off the debug flag
        self.assertNotRegex(km._GEAR_JS, r"rf\.style\.display\s*=")
        self.assertNotRegex(km._GEAR_JS, r"rrefresh[^\n]*display:none")

    def test_judge_toggles_do_not_touch_the_refresh_button(self):
        # the judge-set toggles (which replaced the single Debug toggle) save the pref + emit, but never
        # re-run any refresh-button visibility logic — the ↻ is always visible
        self.assertIn("s.showIndexJudges=jix.checked", km._GEAR_JS)
        self.assertIn("s.showTriageJudges=jtr.checked", km._GEAR_JS)
        self.assertNotRegex(km._GEAR_JS, r"checked;[^\n]*applyDebug")


if __name__ == "__main__":
    unittest.main()
