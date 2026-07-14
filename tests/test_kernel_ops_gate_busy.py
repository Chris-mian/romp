#!/usr/bin/env python3
"""The drive-op park/fire gate reads the backend's AUTHORITATIVE busy signal, not the lagging cached parse
(the user 2026-07-14). Reproduced live: pressing compact -> set-model -> send ~150ms apart while an SDK turn
was in flight delivered OUT of press-order — compact bypassed the FIFO and fired immediately, because
_working_now read the CACHED transcript parse, which hadn't caught the just-started turn yet (the transcript
is written only once the turn produces output). So the gate saw 'not working' and let /compact through, ahead
of the model/message pressed right after it, which then parked and stalled.

The fix: SessionBackend.busy(sid) exposes the truth the backend already knows (SdkSession.inflight); the SDK
overrides it, tmux leaves it None (→ unchanged cached-parse fallback). _working_now — and thus _ops_gate —
prefers it. These tests pin that a session the backend reports BUSY parks every drive op even when the cached
parse still shows it idle. Synthetic only — no real session data."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # isolate: importing the kernel must not touch live state
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
km = SourceFileLoader("romp_kernel_opsbusy", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class _FakeBackend:
    """A backend that OWNS the sid and reports an authoritative busy flag — like the SDK's inflight."""
    def __init__(self, busy_val):
        self._busy = busy_val

    def owns(self, sid):
        return True

    def busy(self, sid):
        return self._busy


class OpsGateAuthoritativeBusy(unittest.TestCase):
    def setUp(self):
        self._saved_sdk = km._sdk
        # the cached parse ALWAYS reports idle here — the lag we are defeating (a just-started turn the
        # transcript hasn't recorded). Any correct answer must come from the backend, not this.
        self._saved_parse = km._parse_cached
        km._parse_cached = lambda *a, **k: {"turns": []}
        km._pending_ops.pop(SID, None)

    def tearDown(self):
        km._sdk = self._saved_sdk
        km._parse_cached = self._saved_parse
        km._pending_ops.pop(SID, None)

    def _use_backend(self, busy_val):
        be = _FakeBackend(busy_val)
        km._sdk = lambda: be
        return be

    def test_working_now_prefers_the_backend_over_the_cached_parse(self):
        self._use_backend(True)
        self.assertTrue(km._working_now(SID),
                        "backend says a turn is in flight → working, even though the cached parse lags idle")
        self._use_backend(False)
        self.assertFalse(km._working_now(SID), "backend says idle → not working")

    def test_a_none_busy_signal_falls_back_to_the_cached_parse(self):
        # tmux (and a dormant SDK sid) return None → the event-model parse decides, exactly as before.
        self._use_backend(None)
        self.assertFalse(km._working_now(SID), "None busy → cached parse (idle here) → not working")

    def test_compact_parks_when_the_backend_is_busy_despite_an_idle_cached_parse(self):
        # THE reproduced bug: compact pressed while a turn is truly in flight must PARK (join the FIFO), not
        # fire immediately ahead of the ops pressed right after it.
        self._use_backend(True)
        self.assertTrue(km._ops_gate(SID),
                        "an in-flight turn (authoritative) parks the op — no cached-parse race window")

    def test_quiet_session_still_fires_immediately(self):
        # the gate must not over-park: a genuinely idle session with no queue fires now (unchanged behavior).
        self._use_backend(False)
        self.assertFalse(km._ops_gate(SID), "idle + no queue + not compacting → fire immediately")


if __name__ == "__main__":
    unittest.main()
