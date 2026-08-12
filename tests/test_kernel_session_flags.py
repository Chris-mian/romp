#!/usr/bin/env python3
"""Per-session view flags (the user 2026-06-19): a persisted {sid: {flag: true}} dict under STATE, set
from the timeline lane gear. The only flag today is hideFromFeed — a session whose prompts shouldn't mint
feed cards (it stays on the timeline). These pin the storage helpers + the web boot hook. Synthetic only."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_sf", os.path.join(BIN, "romp-kernel")).load_module()
# the kernel's helpers read/write jd.STATE; sandbox THAT module's STATE (the one the kernel actually uses)
jd = km.jd


class SessionFlags(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)
        km._flags_cache.clear()

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def test_default_is_empty(self):
        self.assertEqual(km._session_flags(), {})
        self.assertFalse(km._session_flag("sid1", "hideFromFeed"))

    def test_set_get_then_unset_drops_the_entry(self):
        km._set_session_flag("sid1", "hideFromFeed", True)
        self.assertTrue(km._session_flag("sid1", "hideFromFeed"))
        self.assertEqual(km._session_flags(), {"sid1": {"hideFromFeed": True}})
        km._set_session_flag("sid1", "hideFromFeed", False)
        self.assertFalse(km._session_flag("sid1", "hideFromFeed"))
        self.assertEqual(km._session_flags(), {}, "removing the last flag drops the whole session entry")

    def test_sessions_are_independent(self):
        km._set_session_flag("a", "hideFromFeed", True)
        km._set_session_flag("b", "hideFromFeed", False)
        self.assertTrue(km._session_flag("a", "hideFromFeed"))
        self.assertFalse(km._session_flag("b", "hideFromFeed"))
        self.assertNotIn("b", km._session_flags(), "a never-set / cleared flag isn't persisted")

    def test_cache_invalidates_on_write(self):
        self.assertEqual(km._session_flags(), {})           # primes the (empty) read path
        km._set_session_flag("a", "hideFromFeed", True)     # changes the file
        self.assertTrue(km._session_flag("a", "hideFromFeed"), "the (mtime_ns,size) cache key sees the write")

    def test_unknown_flag_value_is_false(self):
        km._set_session_flag("a", "hideFromFeed", True)
        self.assertFalse(km._session_flag("a", "someFutureFlag"), "an unset flag reads False")

    def test_web_boot_exposes_the_set_flag_hook(self):
        # the timeline web page posts setSessionFlag via this host hook (kernel _TIMELINE_BOOT)
        self.assertIn("__rompTimelineSetFlag", km._TIMELINE_BOOT)
        self.assertIn("setSessionFlag", km._TIMELINE_BOOT)


class AutoNudgeWiring(unittest.TestCase):
    """The Auto Nudge toggle is a SERVER-SIDE behavior, so the feed gear posts setAutoNudge to the kernel
    and the checkbox reflects the kernel's state via /version (not localStorage) — the user 2026-06-19."""

    def test_gear_has_the_autonudge_toggle_posting_to_the_kernel(self):
        self.assertIn("rs-autonudge", _gear_src(), "the gear panel has an Auto Nudge checkbox")
        self.assertIn("Auto Nudge", _gear_src())
        self.assertIn("setAutoNudge", _gear_src(), "toggling posts the server-side message")

    def test_version_reports_autonudge_state_for_the_checkbox(self):
        saved = jd.STATE
        td = tempfile.TemporaryDirectory()
        jd.STATE = Path(td.name)
        km._autonudge_cache.clear()
        try:
            self.assertTrue(km._version_info()["autoNudge"], "on by default (no state file)")
            km._set_auto_nudge(False)
            self.assertFalse(km._version_info()["autoNudge"], "an explicit off is respected")
            km._set_auto_nudge(True)
            self.assertTrue(km._version_info()["autoNudge"], "the gear reads the kernel's authoritative state")
        finally:
            jd.STATE = saved
            td.cleanup()

    def test_default_on_even_when_state_file_lacks_the_key(self):
        saved = jd.STATE
        td = tempfile.TemporaryDirectory()
        jd.STATE = Path(td.name)
        km._autonudge_cache.clear()
        try:
            (Path(td.name) / "auto-nudge.json").write_text('{"nudged": {}}')  # present, no "enabled" key
            self.assertTrue(km._auto_nudge_on(), "a state file missing the enabled key still defaults on")
        finally:
            jd.STATE = saved
            td.cleanup()


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
