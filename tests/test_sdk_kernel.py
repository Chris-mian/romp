#!/usr/bin/env python3
"""Kernel wiring for the SDK backend (bin/romp-kernel _sdk_route + _tmux_sessions merge).

Deterministic: _sdk() is stubbed with a FakeBackend that records calls, so this needs
neither the SDK nor any state on disk. It locks in the routing table (which drive ops go to
the backend, which fall through to tmux) and the live-session merge.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class FakeBackend:
    def __init__(self):
        self.calls = []
        self._owned = {"sid-sdk"}

    def owns(self, sid):
        return sid in self._owned

    def send(self, sid, text):
        self.calls.append(("send", sid, text)); return True

    def interrupt(self, sid):
        self.calls.append(("interrupt", sid)); return True

    def kill(self, sid):
        self.calls.append(("kill", sid)); return True

    def on_ask(self, sid, kind, payload=None):
        self.calls.append(("on_ask", sid, kind, payload)); return True

    def set_mode(self, sid, m):
        self.calls.append(("set_mode", sid, m)); return True

    def rename(self, sid, n):
        self.calls.append(("rename", sid, n)); return True

    def live_sessions(self):
        return {"sid-sdk": {"state": "working", "since": "100", "model": "m",
                            "effort": "", "mode": "acceptEdits"}}


class KernelWiring(unittest.TestCase):
    def setUp(self):
        self.be = FakeBackend()
        self.saved = (km._sdk, km._push_all, km._send_to_app)
        km._sdk = lambda: self.be
        km._push_all = lambda *a, **k: None
        km._send_to_app = lambda *a, **k: None

    def tearDown(self):
        km._sdk, km._push_all, km._send_to_app = self.saved

    def _route(self, msg):
        return km._sdk_route(msg, {"send": lambda s: None})

    def test_send_routes_to_backend(self):
        self.assertTrue(self._route({"type": "sendMessage", "id": "sid-sdk", "text": "hi"}))
        self.assertIn(("send", "sid-sdk", "hi"), self.be.calls)

    def test_non_owned_sid_falls_through(self):
        self.assertFalse(self._route({"type": "sendMessage", "id": "sid-tmux", "text": "hi"}))
        self.assertEqual(self.be.calls, [])           # nothing routed; tmux path will handle it

    def test_ui_op_falls_through_even_for_sdk_sid(self):
        # closeTab/openSession are backend-agnostic UI ops → never intercepted
        self.assertFalse(self._route({"type": "closeTab", "id": "sid-sdk"}))
        self.assertFalse(self._route({"type": "openSession", "id": "sid-sdk"}))

    def test_ask_ops_map_to_on_ask(self):
        self._route({"type": "answerAsk", "id": "sid-sdk", "target": 2})
        self._route({"type": "toggleAsk", "id": "sid-sdk", "target": 1})
        self._route({"type": "submitAsk", "id": "sid-sdk"})
        self._route({"type": "addCustomAsk", "id": "sid-sdk", "text": "custom"})
        self._route({"type": "cancelAsk", "id": "sid-sdk"})
        self._route({"type": "askText", "id": "sid-sdk", "text": "raw"})
        on_ask = [c for c in self.be.calls if c[0] == "on_ask"]
        self.assertEqual(on_ask, [
            ("on_ask", "sid-sdk", "answer", 2),
            ("on_ask", "sid-sdk", "toggle", 1),
            ("on_ask", "sid-sdk", "submit", None),
            ("on_ask", "sid-sdk", "custom", "custom"),
            ("on_ask", "sid-sdk", "cancel", None),
            ("on_ask", "sid-sdk", "text", "raw"),
        ])

    def test_interrupt_and_kill(self):
        self.assertTrue(self._route({"type": "interrupt", "id": "sid-sdk"}))
        self.assertTrue(self._route({"type": "endSession", "id": "sid-sdk"}))
        self.assertIn(("interrupt", "sid-sdk"), self.be.calls)
        self.assertIn(("kill", "sid-sdk"), self.be.calls)

    def test_model_effort_compact_map_to_slash_sends(self):
        self._route({"type": "setModel", "id": "sid-sdk", "value": "opus"})
        self._route({"type": "setEffort", "id": "sid-sdk", "value": "high"})
        self._route({"type": "compactSession", "id": "sid-sdk"})
        sends = [c for c in self.be.calls if c[0] == "send"]
        self.assertIn(("send", "sid-sdk", "/model opus"), sends)
        self.assertIn(("send", "sid-sdk", "/effort high"), sends)
        self.assertIn(("send", "sid-sdk", "/compact"), sends)

    def test_setmode_and_rename(self):
        self._route({"type": "setMode", "id": "sid-sdk", "value": "plan"})
        self._route({"type": "renameSession", "id": "sid-sdk", "name": "newname"})
        self.assertIn(("set_mode", "sid-sdk", "plan"), self.be.calls)
        self.assertIn(("rename", "sid-sdk", "newname"), self.be.calls)

    def test_rename_rejects_bad_name(self):
        warned = []
        self.assertTrue(self._route_capture({"type": "renameSession", "id": "sid-sdk",
                                             "name": "bad name!"}, warned))
        self.assertTrue(any("session names" in w for w in warned))
        self.assertFalse(any(c[0] == "rename" for c in self.be.calls))

    def _route_capture(self, msg, sink):
        import json
        def send(s):
            try:
                sink.append(json.loads(s).get("text", ""))
            except Exception:
                pass
        return km._sdk_route(msg, {"send": send})

    def test_askfollowup_resolves_sid_from_itemid(self):
        self.assertTrue(self._route({"type": "askFollowUp", "itemId": "sid-sdk:g1", "text": "more"}))
        self.assertIn(("send", "sid-sdk", "more"), self.be.calls)

    def test_tmux_sessions_merges_sdk_rows(self):
        sess = km._tmux_sessions()                     # merges tmux (real/empty) + the fake SDK row
        self.assertIn("sid-sdk", sess)
        row = sess["sid-sdk"]
        self.assertEqual(row["state"], "working")
        self.assertEqual(row["since"], 100)            # string -> int via _num
        self.assertEqual(row["model"], "m")
        self.assertIsNone(row["context"])              # SDK rows have no pane-OCR context%
        self.assertIsNone(row["compactPct"])


if __name__ == "__main__":
    unittest.main()
