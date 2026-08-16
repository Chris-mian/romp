#!/usr/bin/env python3
"""The global retry-pause is an API-HEALTH flag, not a permanent switch. The user flips "stop all
auto-retries" to calm the auto-retry + judge storm during an API / usage-limit outage — but the judge
tier is gated on `not _retry_paused_on()`, so a pause that never clears silently kills EVERY judge for
hours (the user 2026-06-30, who noted none of the judges were running and called it an API problem that should
clear the second a successful non-API-error response arrives on any session). _auto_resume_retry
clears it event-based: the first live session that is NOT blocked on an API error AND wrote fresh output
since the pause began (mtime past the pause floor) proves the account can serve requests again.
"""
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_rp", os.path.join(BIN, "romp-kernel")).load_module()


class RetryPauseAutoResume(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self._orig_state = km.jd.STATE
        km.jd.STATE = self.dir                          # retry-paused.json lives under jd.STATE
        self._orig_alive = km._alive_sessions
        self._orig_apierr = km._api_error
        self._orig_push = km._push_all
        km._push_all = lambda *a, **k: None             # no clients in the test

    def tearDown(self):
        km.jd.STATE = self._orig_state
        km._alive_sessions = self._orig_alive
        km._api_error = self._orig_apierr
        km._push_all = self._orig_push
        self.td.cleanup()

    def _transcript(self, name, mtime):
        p = self.dir / name
        p.write_text("{}\n")
        os.utime(p, (mtime, mtime))
        return str(p)

    # --- the flag records its pause instant ---
    def test_pause_records_a_floor_timestamp(self):
        km._set_retry_paused(True)
        self.assertTrue(km._retry_paused_on())
        self.assertGreater(km._retry_pause_ts(), 0, "a pause records WHEN it began (the auto-resume floor)")
        km._set_retry_paused(False)
        self.assertFalse(km._retry_paused_on())
        self.assertEqual(km._retry_pause_ts(), 0.0, "un-pausing drops the floor")

    # --- recovery clears it ---
    def test_fresh_healthy_session_clears_the_pause(self):
        km._set_retry_paused(True)
        floor = km._retry_pause_ts()
        path = self._transcript("healthy.jsonl", floor + 5)   # wrote output AFTER the pause
        km._alive_sessions = lambda now, tmux: [{"sid": "s1", "path": path}]
        km._api_error = lambda p: None                        # not blocked on an API error
        km._auto_resume_retry(int(time.time()), {})
        self.assertFalse(km._retry_paused_on(), "a served request after the pause proves recovery → resume")

    # --- an api-errored session is NOT proof of recovery ---
    def test_still_errored_session_keeps_the_pause(self):
        km._set_retry_paused(True)
        floor = km._retry_pause_ts()
        path = self._transcript("errored.jsonl", floor + 5)   # fresh mtime, but the last record is an API error
        km._alive_sessions = lambda now, tmux: [{"sid": "s1", "path": path}]
        km._api_error = lambda p: {"text": "overloaded", "status": 529}
        km._auto_resume_retry(int(time.time()), {})
        self.assertTrue(km._retry_paused_on(), "a session still blocked on an API error must not clear the pause")

    # --- a stale success (from before the outage) is NOT proof ---
    def test_stale_session_keeps_the_pause(self):
        km._set_retry_paused(True)
        floor = km._retry_pause_ts()
        path = self._transcript("stale.jsonl", floor - 60)    # last wrote BEFORE the pause
        km._alive_sessions = lambda now, tmux: [{"sid": "s1", "path": path}]
        km._api_error = lambda p: None
        km._auto_resume_retry(int(time.time()), {})
        self.assertTrue(km._retry_paused_on(), "no fresh output since the pause → no evidence the API recovered")

    # --- no-op when not paused ---
    def test_noop_when_not_paused(self):
        km._set_retry_paused(False)
        called = []
        km._alive_sessions = lambda now, tmux: called.append(1) or []
        km._auto_resume_retry(int(time.time()), {})
        self.assertEqual(called, [], "not paused → the resume check does no work")


if __name__ == "__main__":
    unittest.main()
