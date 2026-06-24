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
        # the button itself is unchanged — still in the gear, still POSTs /restart
        self.assertIn("id=rrefresh", km._GEAR_HTML)
        self.assertIn("fetch('/restart',{method:'POST'})", km._GEAR_JS)

    def test_refresh_button_is_not_gated_on_debug(self):
        # the old applyDebug() helper (which hid #rrefresh unless s.debug) is gone entirely …
        self.assertNotIn("applyDebug", km._GEAR_JS)
        # … and nothing else hides the refresh button by toggling its display off the debug flag
        self.assertNotRegex(km._GEAR_JS, r"rf\.style\.display\s*=")
        self.assertNotRegex(km._GEAR_JS, r"rrefresh[^\n]*display:none")

    def test_debug_toggle_no_longer_touches_the_refresh_button(self):
        # the Debug checkbox handler still saves the pref + emits the settings event, but no longer
        # re-runs any refresh-button visibility logic
        self.assertIn("s.debug=db.checked", km._GEAR_JS)
        self.assertNotRegex(km._GEAR_JS, r"db\.checked;[^\n]*applyDebug")


if __name__ == "__main__":
    unittest.main()
