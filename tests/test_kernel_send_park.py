#!/usr/bin/env python3
"""A MESSAGE sent while a session compacts is PARKED, not delivered (the user 2026-07-02: a
mid-compaction send rendered instantly as a landed chat bubble — no queued cue — and its optimistic
echo opened a turn that killed the 'compacting' indicator). The kernel parks it in _pending_sends,
build_session renders it as a queued bubble, and _apply_pending_sends (producer tick, AFTER
_apply_pending_models so a parked model change is in effect first) delivers it the moment compaction
ends — the same event-corroborated _compacting_now gate the model park uses. SYNTHETIC fixtures only."""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_sendpark", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class _FakeBackend:
    def __init__(self):
        self.sent = []

    def send(self, sid, text):
        self.sent.append((sid, text))
        return True


class SendParkOrDeliver(unittest.TestCase):
    def setUp(self):
        self.be = _FakeBackend()
        self.echoes = []
        self._saved = (km._compacting_now, km.Sessions.backend_for, km._push_all, km._optimistic_echo)
        km._push_all = lambda: None
        km._optimistic_echo = lambda sid, text, author="human": self.echoes.append((sid, text, author))
        km._pending_sends.clear()

    def tearDown(self):
        (km._compacting_now, km.Sessions.backend_for, km._push_all, km._optimistic_echo) = self._saved
        km._pending_sends.clear()

    def test_not_compacting_sends_immediately_with_echo(self):
        km._compacting_now = lambda sid: False
        km._send_or_park(self.be, SID, "hello there", echo="human")
        self.assertEqual(self.be.sent, [(SID, "hello there")], "no compaction → delivered now")
        self.assertEqual(self.echoes, [(SID, "hello there", "human")], "the instant echo still fires")
        self.assertNotIn(SID, km._pending_sends)

    def test_compacting_parks_instead_of_sending(self):
        km._compacting_now = lambda sid: True
        km._send_or_park(self.be, SID, "hello there", echo="human")
        self.assertEqual(self.be.sent, [], "mid-compaction the backend is NOT touched")
        self.assertEqual(self.echoes, [], "no echo atom lands — an echo would kill the compacting cue")
        self.assertEqual(km._pending_sends.get(SID), [("hello there", "human")])

    def test_parked_sends_keep_their_order(self):
        km._compacting_now = lambda sid: True
        km._send_or_park(self.be, SID, "first", echo="human")
        km._send_or_park(self.be, SID, "second", echo=None)
        self.assertEqual(km._pending_sends.get(SID), [("first", "human"), ("second", None)],
                         "every parked message keeps its slot — nothing collapses to last-wins")

    def test_apply_delivers_when_compaction_ends_and_not_before(self):
        km._pending_sends[SID] = [("first", "human"), ("second", None)]
        km.Sessions.backend_for = lambda sid: self.be
        km._compacting_now = lambda sid: True
        km._apply_pending_sends()
        self.assertEqual(self.be.sent, [], "still compacting → still parked")
        self.assertIn(SID, km._pending_sends)
        km._compacting_now = lambda sid: False
        km._apply_pending_sends()
        self.assertEqual(self.be.sent, [(SID, "first"), (SID, "second")], "delivered in send order")
        self.assertEqual(self.echoes, [(SID, "first", "human")], "echo only where the send path echoed")
        self.assertNotIn(SID, km._pending_sends, "consumed — never re-delivered")

    def test_dead_session_park_is_dropped_not_retried(self):
        km._pending_sends[SID] = [("into the void", None)]
        km._compacting_now = lambda sid: False

        def dead(sid):
            raise RuntimeError("no such session")
        km.Sessions.backend_for = dead
        km._apply_pending_sends()                       # must not raise
        self.assertNotIn(SID, km._pending_sends, "a dead session's park is dropped, never retried forever")

    def test_producer_ticks_sends_after_models(self):
        import inspect
        src = inspect.getsource(km._producer)
        self.assertIn("_apply_pending_sends()", src, "the producer tick delivers parked sends")
        self.assertLess(src.index("_apply_pending_models()"), src.index("_apply_pending_sends()"),
                        "a model change parked in the same compaction applies BEFORE the message opens a turn")


class SendPathsPark(unittest.TestCase):
    """Every user-send path routes through _send_or_park, so no path can slip a mid-compaction send."""

    def test_ws_send_paths_use_the_park(self):
        import inspect
        src = inspect.getsource(km._dispatch_drive) if hasattr(km, "_dispatch_drive") else ""
        if not src:  # the handler lives inline; pin the file itself
            with open(os.path.join(BIN, "romp-kernel")) as f:
                src = f.read()
        self.assertIn('_send_or_park(be, sid, str(msg["text"]), echo="human")', src,
                      "the composer send parks mid-compaction")
        self.assertIn("_send_or_park(be, sid, body,", src, "the follow-up/nudge send parks mid-compaction")
        self.assertIn("_send_or_park(be, sid, cmd)", src, "the timeline sendCommand parks mid-compaction")


class QueuedBubble(unittest.TestCase):
    def test_build_session_renders_parked_sends_as_queued_bubbles(self):
        import inspect
        src = inspect.getsource(km.build_session)
        self.assertIn("pending_sends = _pending_sends.get(sid) or []", src)
        self.assertIn("if queued or pending_model or pending_sends:", src,
                      "the queued indicator shows even when a parked send is the only pending item")
        self.assertIn("for t, _echo in pending_sends:", src,
                      "each parked send renders like a queued message (same _split_followup treatment)")


if __name__ == "__main__":
    unittest.main()
