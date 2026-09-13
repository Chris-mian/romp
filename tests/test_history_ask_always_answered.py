#!/usr/bin/env python3
"""T402 (the user 2026-09-12): the chat's "Loading earlier messages" pill stayed on a reader at the tail and could not be dismissed.
One never-answered road was the kernel's: a history ask (loadOlder, loadAround, loadNewer) whose reply built as None, or whose
handler raised, sent NOTHING back, and the page waits on the reply to end the pill and to allow the next ask. Every history ask is
answered now: a reply of the ask's own type, marked missing, carrying the reason. Drives the REAL WS dispatch against a hermetic
state root with a proto-2 client whose send is captured. Synthetic fixtures only."""
import json
import os
import tempfile
import threading
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
with open(os.path.join(os.environ["XDG_STATE_HOME"], "romp", "session-hosts"), "w") as _f:
    _f.write("off")   # a state root of our own: no real host for any session (the Testing rule)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_hask", os.path.join(BIN, "romp-kernel"))

UNKNOWN = "aaaaaaaa-1111-2222-3333-444444444444"   # a session this kernel has never heard of: no build to answer from


class HistoryAskAlwaysAnswered(unittest.TestCase):
    def client(self):
        sent = []
        return {"wid": "11111111-2222-3333-4444-555555555555", "proto": 2, "send": sent.append, "echat": {}, "lock": threading.RLock()}, sent

    def frames(self, sent):
        return [json.loads(x) for x in sent]

    def test_an_ask_with_no_session_to_answer_from_is_answered_missing_with_the_reason(self):
        for kind, reply_type, extra in (("loadOlder", "chatHead", {"before": "22222222-3333-4444-5555-000000000010"}),
                                        ("loadAround", "chatWindow", {"uuid": "22222222-3333-4444-5555-000000000010"}),
                                        ("loadNewer", "chatMore", {"after": "22222222-3333-4444-5555-000000000010"})):
            client, sent = self.client()
            km.Handler._dispatch_ws(None, {"type": kind, "id": UNKNOWN, **extra}, client)
            fr = [f for f in self.frames(sent) if f.get("type") == reply_type]
            self.assertEqual(len(fr), 1, "%s: one reply of its own type, even with nothing to answer from: %r" % (kind, self.frames(sent)))
            self.assertTrue(fr[0].get("missing"), "%s: marked missing: %r" % (kind, fr[0]))
            self.assertIn("error", fr[0], "%s: the reason rides the reply: %r" % (kind, fr[0]))
            self.assertEqual(fr[0].get("id"), UNKNOWN)

    def test_a_handler_that_raises_still_answers(self):
        client, sent = self.client()
        saved = km._chat_history_reply
        def boom(*a, **k):
            raise RuntimeError("synthetic fault in the reply builder")
        km._chat_history_reply = boom
        try:
            km.Handler._dispatch_ws(None, {"type": "loadOlder", "id": UNKNOWN, "before": "22222222-3333-4444-5555-000000000010"}, client)
        finally:
            km._chat_history_reply = saved
        fr = [f for f in self.frames(sent) if f.get("type") == "chatHead"]
        self.assertEqual(len(fr), 1, "the fault is answered, not swallowed: %r" % self.frames(sent))
        self.assertTrue(fr[0].get("missing"))
        self.assertIn("synthetic fault", fr[0].get("error", ""))

    # ---- round two (lows 2 and 3): a reply the kernel could not build is a FAULT carrying the ask's own key, on both wires ----

    def test_a_fault_reply_carries_the_asks_key_under_the_name_the_page_reads_and_says_fault(self):
        for kind, reply_type, ask_key, reply_key in (("loadOlder", "chatHead", "before", "beforeUuid"),
                                                     ("loadAround", "chatWindow", "uuid", "anchor"),
                                                     ("loadNewer", "chatMore", "after", "afterUuid")):
            client, sent = self.client()
            km.Handler._dispatch_ws(None, {"type": kind, "id": UNKNOWN, ask_key: "22222222-3333-4444-5555-000000000010"}, client)
            fr = [f for f in self.frames(sent) if f.get("type") == reply_type]
            self.assertEqual(len(fr), 1, kind)
            self.assertTrue(fr[0].get("fault"), "%s: a fault, not a verdict on the anchor: %r" % (kind, fr[0]))
            self.assertEqual(fr[0].get(reply_key), "22222222-3333-4444-5555-000000000010", "%s: the ask's key rides back as %s: %r" % (kind, reply_key, fr[0]))

    def test_the_index_wire_answers_every_ask_too(self):
        # the legacy loadOlder (an integer `before`, the index wire): a head already reached is an empty chunk from 0; an empty build
        # and a raising build are FAULTS carrying the ask's `before`, so the page's wait ends whatever happened here
        client, sent = self.client()
        km.Handler._dispatch_ws(None, {"type": "loadOlder", "id": UNKNOWN, "before": 0}, client)
        fr = [f for f in self.frames(sent) if f.get("type") == "chatHead"]
        self.assertEqual(len(fr), 1, "before 0: answered: %r" % self.frames(sent))
        self.assertEqual((fr[0].get("from"), fr[0].get("before"), fr[0].get("events")), (0, 0, []), "nothing older: the head: %r" % fr[0])
        self.assertFalse(fr[0].get("missing"), fr[0])
        client, sent = self.client()
        km.Handler._dispatch_ws(None, {"type": "loadOlder", "id": UNKNOWN, "before": 40}, client)
        fr = [f for f in self.frames(sent) if f.get("type") == "chatHead"]
        self.assertEqual(len(fr), 1, "an empty build: answered: %r" % self.frames(sent))
        self.assertTrue(fr[0].get("fault") and fr[0].get("missing"), "a fault, with the ask's before: %r" % fr[0])
        self.assertEqual(fr[0].get("before"), 40, fr[0])
        client, sent = self.client()
        saved = km.build_session
        def boom(*a, **k):
            raise RuntimeError("synthetic fault in the build")
        km.build_session = boom
        try:
            km.Handler._dispatch_ws(None, {"type": "loadOlder", "id": UNKNOWN, "before": 40}, client)
        finally:
            km.build_session = saved
        fr = [f for f in self.frames(sent) if f.get("type") == "chatHead"]
        self.assertEqual(len(fr), 1, "a raising build: answered: %r" % self.frames(sent))
        self.assertTrue(fr[0].get("fault"), fr[0])
        self.assertEqual(fr[0].get("before"), 40, fr[0])
        self.assertIn("synthetic fault", fr[0].get("error", ""))


if __name__ == "__main__":
    unittest.main()
