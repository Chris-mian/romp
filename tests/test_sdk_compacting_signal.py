#!/usr/bin/env python3
"""Authoritative compacting signal for SDK sessions (the user 2026-07-14). The kernel used to infer an SDK
compaction from an OPTIMISTIC stamp with a 180s cap; when /compact found NOTHING to compact, no compact_boundary
event ever landed, so that cap held parked ops (a model pick, a queued message) hostage for up to 3 minutes —
the "message landed but took no action". The SDK now BRACKETS compaction exactly: SdkSession._compacting is set
when /compact is delivered and cleared event-based by the compact_boundary (a real compaction landed → the
continuation is normal work) OR by the /compact turn's ResultMessage (nothing-to-compact → no boundary comes).
The backend exposes it via compacting(sid); the kernel's _compacting prefers it over the optimistic path.

Synthetic only — no real session data, no SDK dependency (the module imports claude_agent_sdk lazily, inside
_amain, so SdkSession is constructible and _on_message drivable with fake message classes here)."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
sb = SourceFileLoader("romp_sdk_backend_compact", os.path.join(BIN, "romp_sdk_backend.py")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


# fake SDK message classes + instances: _on_message is passed the classes, so isinstance checks work.
class AssistantMessage: ...
class ResultMessage: ...
class SystemMessage:
    def __init__(self, subtype, data=None):
        self.subtype = subtype
        self.data = data or {}


class _FakeBackend:
    def __init__(self, state_dir):
        self.state_dir = state_dir
    def _turn_completed(self, sid): pass
    def retire_live_work(self, sid): pass
    def _poke(self): pass
    def _update_reg(self, *a, **k): pass
    def _forward(self, s, msg): pass


class _CompactCmd(unittest.TestCase):
    def test_is_compact_cmd(self):
        self.assertTrue(sb._is_compact_cmd("/compact"))
        self.assertTrue(sb._is_compact_cmd("  /compact  "))
        self.assertTrue(sb._is_compact_cmd("/compact focus on the API design"))
        self.assertFalse(sb._is_compact_cmd("/compactify"), "a look-alike command is not /compact")
        self.assertFalse(sb._is_compact_cmd("please /compact later"), "only a leading invocation counts")
        self.assertFalse(sb._is_compact_cmd("hello"))


class _Transitions(unittest.TestCase):
    def _session(self):
        s = sb.SdkSession(_FakeBackend(tempfile.mkdtemp()), {"sid": SID, "name": "x"})
        # neutralize the async/loop side-effects _on_message fires; we only assert the _compacting flag
        self._saved = sb.asyncio.ensure_future
        sb.asyncio.ensure_future = lambda coro: (coro.close() if hasattr(coro, "close") else None)
        return s

    def tearDown(self):
        if hasattr(self, "_saved"):
            sb.asyncio.ensure_future = self._saved

    def test_boundary_clears_compacting(self):
        s = self._session()
        s._compacting = True                       # a /compact is in flight
        s._on_message(SystemMessage("compact_boundary"), AssistantMessage, ResultMessage, SystemMessage)
        self.assertFalse(s._compacting, "a real compaction landed → compacting ends (continuation is normal work)")

    def test_result_clears_compacting_when_nothing_to_compact(self):
        # THE bug: no boundary ever comes for a no-op /compact — the turn just settles. The ResultMessage must
        # clear the flag, or the kernel's optimistic latch would strand parked ops for 180s.
        s = self._session()
        s._compacting = True
        s._on_message(ResultMessage(), AssistantMessage, ResultMessage, SystemMessage)
        self.assertFalse(s._compacting, "no-op /compact settles with no boundary → compacting still ends")


class _BackendSurface(unittest.TestCase):
    def _backend(self):
        be = sb.SdkBackend.__new__(sb.SdkBackend)   # skip __init__ (no thread/venv); we only exercise busy/compacting
        be.sessions = {}
        return be

    def test_compacting_and_busy_are_none_for_an_unowned_sid(self):
        be = self._backend()
        self.assertIsNone(be.compacting(SID), "not running here → no authoritative signal")
        self.assertIsNone(be.busy(SID))

    def test_compacting_reflects_the_session_flag(self):
        import threading
        be = self._backend()
        s = sb.SdkSession(_FakeBackend(tempfile.mkdtemp()), {"sid": SID, "name": "x"})
        s._lock = threading.Lock()
        be.sessions[SID] = s
        s._compacting = True
        self.assertTrue(be.compacting(SID))
        s._compacting = False
        self.assertFalse(be.compacting(SID))


if __name__ == "__main__":
    unittest.main()
