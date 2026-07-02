#!/usr/bin/env python3
"""ANY drive op sent while a session compacts is PARKED in ONE FIFO queue (the user 2026-07-02): messages,
/model AND /effort. The chat renders the queue as bubbles in park order, and _apply_pending_ops delivers
in exactly that order the moment compaction ends (the rendering IS the execution order — the user hit a
parked message rendering BEFORE the model change parked ahead of it). A repeated model/effort pick
replaces its earlier parked op in place. Same event-corroborated _compacting_now gate as ever; a parked
send stamps its optimistic echo only when it actually fires (an early echo killed the compacting cue).
SYNTHETIC fixtures only."""
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
        self.calls = []

    def send(self, sid, text):
        self.calls.append(("send", text))
        return True

    def set_model(self, sid, value):
        self.calls.append(("model", value))
        return True

    def set_effort(self, sid, value):
        self.calls.append(("effort", value))
        return True


class OpQueueParkOrDeliver(unittest.TestCase):
    def setUp(self):
        self.be = _FakeBackend()
        self.echoes = []
        self._saved = (km._compacting_now, km.Sessions.backend_for, km._push_all, km._optimistic_echo)
        km._push_all = lambda: None
        km._optimistic_echo = lambda sid, text, author="human": self.echoes.append((text, author))
        km._pending_ops.clear()

    def tearDown(self):
        (km._compacting_now, km.Sessions.backend_for, km._push_all, km._optimistic_echo) = self._saved
        km._pending_ops.clear()

    def test_not_compacting_everything_applies_immediately(self):
        km._compacting_now = lambda sid: False
        km._send_or_park(self.be, SID, "hello there", echo="human")
        km._set_model_or_park(self.be, SID, "opus")
        km._set_effort_or_park(self.be, SID, "high")
        self.assertEqual(self.be.calls, [("send", "hello there"), ("model", "opus"), ("effort", "high")])
        self.assertEqual(self.echoes, [("hello there", "human")], "the instant echo still fires")
        self.assertNotIn(SID, km._pending_ops)

    def test_compacting_parks_everything_in_order(self):
        # the user's exact repro: model change, then a message — the queue must hold THAT order
        km._compacting_now = lambda sid: True
        km._set_model_or_park(self.be, SID, "opus")
        km._send_or_park(self.be, SID, "now do the thing", echo="human")
        km._set_effort_or_park(self.be, SID, "medium")
        self.assertEqual(self.be.calls, [], "mid-compaction the backend is NOT touched")
        self.assertEqual(self.echoes, [], "no echo atom lands — an echo would kill the compacting cue")
        self.assertEqual(km._pending_ops.get(SID),
                         [("model", "opus"), ("send", "now do the thing", "human"), ("effort", "medium")],
                         "ONE queue, in park order — messages and slash commands interleaved as sent")

    def test_repeat_model_or_effort_replaces_in_place_messages_append(self):
        km._compacting_now = lambda sid: True
        km._set_model_or_park(self.be, SID, "opus")
        km._send_or_park(self.be, SID, "first", echo=None)
        km._set_model_or_park(self.be, SID, "sonnet")     # re-pick → replaces the parked model IN PLACE
        km._send_or_park(self.be, SID, "second", echo=None)
        self.assertEqual(km._pending_ops.get(SID),
                         [("model", "sonnet"), ("send", "first", None), ("send", "second", None)])

    def test_apply_delivers_fifo_when_compaction_ends_and_not_before(self):
        km._pending_ops[SID] = [("model", "opus"), ("send", "go", "human"), ("effort", "high")]
        km.Sessions.backend_for = lambda sid: self.be
        km._compacting_now = lambda sid: True
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [], "still compacting → still parked")
        self.assertIn(SID, km._pending_ops)
        km._compacting_now = lambda sid: False
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("model", "opus"), ("send", "go"), ("effort", "high")],
                         "delivered in park order — the order the chat rendered")
        self.assertEqual(self.echoes, [("go", "human")], "echo only where the send path echoed")
        self.assertNotIn(SID, km._pending_ops, "consumed — never re-delivered")

    def test_dead_session_queue_is_dropped_not_retried(self):
        km._pending_ops[SID] = [("send", "into the void", None)]
        km._compacting_now = lambda sid: False

        def dead(sid):
            raise RuntimeError("no such session")
        km.Sessions.backend_for = dead
        km._apply_pending_ops()                         # must not raise
        self.assertNotIn(SID, km._pending_ops, "a dead session's queue is dropped, never retried forever")

    def test_producer_ticks_the_apply(self):
        import inspect
        src = inspect.getsource(km._producer)
        self.assertIn("_apply_pending_ops()", src, "the producer tick delivers the parked queue")


class SendPathsPark(unittest.TestCase):
    """Every drive path routes through a park helper, so no path can slip a mid-compaction op."""

    def test_ws_drive_paths_use_the_parks(self):
        with open(os.path.join(BIN, "romp-kernel")) as f:
            src = f.read()
        self.assertIn('_send_or_park(be, sid, str(msg["text"]), echo="human")', src,
                      "the composer send parks mid-compaction")
        self.assertIn("_send_or_park(be, sid, body,", src, "the follow-up/nudge send parks mid-compaction")
        self.assertIn("_send_or_park(be, sid, cmd)", src, "the timeline sendCommand parks mid-compaction")
        self.assertIn('_set_effort_or_park(be, sid, str(msg["value"]))', src,
                      "the setEffort drive op parks mid-compaction (the user 2026-07-02: it slipped through)")
        self.assertIn('_set_effort_or_park(be, sid, cmd[len("/effort "):].strip())', src,
                      "the timeline /effort parks mid-compaction")


class QueuedBubble(unittest.TestCase):
    def test_build_session_renders_the_op_queue_in_park_order(self):
        import inspect
        src = inspect.getsource(km.build_session)
        self.assertIn("pending_ops = _pending_ops.get(sid) or []", src)
        self.assertIn("if queued or pending_ops:", src,
                      "the queued indicator shows even when a parked op is the only pending item")
        self.assertIn("for op in pending_ops:", src, "ONE loop, park order — rendering IS execution order")
        self.assertIn("_split_followup(op[1])", src,
                      "a parked message renders like a queued message (same follow-up treatment)")


if __name__ == "__main__":
    unittest.main()
