#!/usr/bin/env python3
"""A brand-new LIVE session has no transcript for its first few seconds, and build_session used to
return None for it — no session frame existed, so its input echo / queued bubble had nothing to render
onto and the first message typed into a just-created session was invisible until the transcript appeared
(the user 2026-07-20: the UI must respond even when the kernel can't get the session going yet).
Discovery misses synthesize a transcriptless entry for a sid that is LIVE — and the backend's live
atoms (the optimistic input echo) merge onto that synthesized frame, so the frame exists from second
zero. Driven through a stub backend (the SessionBackend seam), SYNTHETIC fixtures only."""
import os
import time
import unittest
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_bootstub", os.path.join(BIN, "romp-kernel")).load_module()

SID = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"

# the shape _live_map() always provides for a live session (a booting one has no model/context yet)
_LIVE_META = {"state": "", "since": None, "model": "", "effort": "", "mode": "",
              "context": None, "compactPct": None, "backend": "sdk"}


class _EchoBE:
    """A stub backend owning SID whose only live atom is the optimistic input echo — the same
    synthetic human user atom shape the real backend mints, merged ahead of the (absent) disk parse."""
    def __init__(self, sid, text):
        self.sid, self._atoms = sid, [{
            "type": "user", "uuid": "echo:1111", "session_id": sid, "t": int(time.time()),
            "parentUuid": None, "author": "human", "_echo_text": text,
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}]
    def owns(self, sid): return sid == self.sid
    def live_atoms(self, sid): return list(self._atoms) if sid == self.sid else []
    def prune_live(self, sid, tx_uuids, tx_user_texts=(), human_floor=0): return None
    def pending_queued(self, sid): return []
    def current_ask(self, sid): return None
    def busy(self, sid): return None
    def compacting(self, sid): return None
    def clearing(self, sid): return None
    def launch_error(self, sid): return None
    def live_sessions(self): return {}
    def pending_cut(self, sid): return ""
    def __getattr__(self, name):
        # any other capability probe reads as absent — the documented can't-do-it default
        raise AttributeError(name)


class BootWindowStub(unittest.TestCase):
    def setUp(self):
        self._saved = (km._sessions, km._sdk, km._captions)
        km._sessions = lambda now: []                 # discovery can't see it (no transcript yet)
        km._captions = lambda sid: {}

    def tearDown(self):
        km._sessions, km._sdk, km._captions = self._saved

    def test_live_sid_builds_a_frame_with_its_echo_before_any_transcript(self):
        now = int(time.time())
        km._sdk = lambda: _EchoBE(SID, "first message into a booting session")
        m = km.build_session(SID, now, live_map={SID: _LIVE_META})
        self.assertIsNotNone(m, "a live-but-transcriptless session must still build a frame")
        self.assertEqual(m["id"], SID)
        evs = m.get("events") or []
        self.assertTrue(any("first message into a booting session" in str(e) for e in evs),
                        "the input echo renders onto the synthesized frame")

    def test_a_sid_nowhere_alive_still_builds_nothing(self):
        km._sdk = lambda: None
        m = km.build_session(SID, int(time.time()), live_map={})
        self.assertIsNone(m, "unknown sids stay frameless — the stub is only for LIVE boot windows")

    def test_the_boot_frame_rides_the_real_transcript_path(self):
        # the synthesized entry points at the session's REAL (not-yet-written) transcript path, so the
        # moment the CLI writes it, the same frame simply fills in — nothing to swap, nothing to shadow
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn("sess = _sdk_sess(sid, now)", src)


if __name__ == "__main__":
    unittest.main()
