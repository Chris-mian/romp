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

    def set_model(self, sid, v):
        self.calls.append(("set_model", sid, v)); return True

    def rename(self, sid, n):
        self.calls.append(("rename", sid, n)); return True

    def live_sessions(self):
        return {"sid-sdk": {"state": "working", "since": "100", "model": "m",
                            "effort": "", "mode": "acceptEdits"}}

    def live_atoms(self, sid):
        return getattr(self, "_live", {}).get(sid, [])

    def prune_live(self, sid, tx_uuids, tx_texts=()):
        self.calls.append(("prune_live", sid))


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

    def test_setmodel_goes_live_not_slash(self):
        # model is a runtime control request (set_model), NOT a /model slash injection the SDK ignores
        self._route({"type": "setModel", "id": "sid-sdk", "value": "opus"})
        self.assertIn(("set_model", "sid-sdk", "opus"), self.be.calls)
        self.assertFalse(any(c == ("send", "sid-sdk", "/model opus") for c in self.be.calls))

    def test_effort_and_compact_still_slash_for_now(self):
        # effort has no SDK runtime control (Task #4 reconnects); compact has none either → still slash sends
        self._route({"type": "setEffort", "id": "sid-sdk", "value": "high"})
        self._route({"type": "compactSession", "id": "sid-sdk"})
        sends = [c for c in self.be.calls if c[0] == "send"]
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


class LiveTailAndOpen(unittest.TestCase):
    """The live-tail merge + the transcript-less open fix (a just-created SDK session has no transcript,
    so discover() can't see it — without these it never opened: the user 2026-06-22)."""

    def setUp(self):
        self.be = FakeBackend()
        self.saved = (km._sdk, km._sessions, km._push_all, km._send_to_app)
        km._sdk = lambda: self.be
        km._push_all = lambda *a, **k: None
        km._send_to_app = lambda *a, **k: None

    def tearDown(self):
        km._sdk, km._sessions, km._push_all, km._send_to_app = self.saved

    def test_merge_appends_fresh_live_atom_non_mutating(self):
        self.be._live = {"sid-sdk": [{"type": "assistant", "uuid": "new1", "t": 50,
                                      "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}]}
        session = {"turns": [{"id": "t", "atoms": [{"uuid": "old", "t": 10}], "ended": True}]}
        out = km._merge_live_atoms(session, "sid-sdk")
        self.assertEqual([a.get("uuid") for a in out["turns"][-1]["atoms"]], ["old", "new1"])  # sorted by t
        self.assertIsNot(out, session)                                   # copy, not mutation
        self.assertEqual(session["turns"][-1]["atoms"], [{"uuid": "old", "t": 10}])  # original untouched

    def test_merge_dedups_by_uuid(self):
        self.be._live = {"sid-sdk": [{"type": "assistant", "uuid": "dup", "t": 50,
                                      "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}}]}
        session = {"turns": [{"id": "t", "atoms": [{"uuid": "dup", "t": 10}], "ended": True}]}
        out = km._merge_live_atoms(session, "sid-sdk")
        self.assertEqual(len(out["turns"][-1]["atoms"]), 1)              # transcript already has it → not re-added

    def test_merge_skips_non_sdk(self):
        session = {"turns": []}
        self.assertIs(km._merge_live_atoms(session, "sid-tmux"), session)   # not SDK-backed → unchanged

    def test_alive_sessions_includes_transcriptless_sdk(self):
        km._sessions = lambda now: []                                   # discover sees nothing (no transcript yet)
        alive = km._alive_sessions(1000, {"sid-sdk": {"state": "waiting"}})
        self.assertIn("sid-sdk", [s["sid"] for s in alive])             # still opens


class Responsiveness(unittest.TestCase):
    """The chat pusher is event-driven + short-poll so BOTH backends feel snappy (the user 2026-06-22):
    the SDK live-tail and /tick wake it instantly; a 0.5s backstop covers tmux mid-turn streaming."""

    def test_tick_wakes_the_pusher_and_short_backstop(self):
        with open(os.path.join(BIN, "romp-kernel")) as f:
            src = f.read()
        self.assertIn("_pusher_wake.wait(0.5)", src)                  # short backstop poll
        tick = src.split('u.path == "/tick"', 1)[1].split("return self._send", 1)[0]
        self.assertIn("_pusher_wake.set()", tick)                     # /tick wakes the pusher (tmux turn-end shows now)


if __name__ == "__main__":
    unittest.main()
