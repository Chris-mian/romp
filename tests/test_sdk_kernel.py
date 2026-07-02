#!/usr/bin/env python3
"""Kernel wiring for the unified session API (bin/romp-kernel _drive + Sessions.live merge).

Deterministic: _sdk() is stubbed with a FakeBackend that records calls, so this needs neither the SDK nor
any state on disk. It locks in the routing table — _drive sends each per-session op to whichever backend
OWNS the sid (Sessions.backend_for): SDK-owned sids → the SDK backend, everything else → the tmux backend —
plus the live-session merge. (the user 2026-06-26: tmux + SDK behind one session API.)
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

    def set_effort(self, sid, v):
        self.calls.append(("set_effort", sid, v)); return True

    def rename(self, sid, n):
        self.calls.append(("rename", sid, n)); return True

    def live_sessions(self):
        return {"sid-sdk": {"state": "working", "since": "100", "model": "m",
                            "effort": "", "mode": "acceptEdits"}}

    def live_atoms(self, sid):
        return getattr(self, "_live", {}).get(sid, [])

    def prune_live(self, sid, tx_uuids, tx_texts=(), human_floor=0):
        self.calls.append(("prune_live", sid))


class KernelWiring(unittest.TestCase):
    def setUp(self):
        self.be = FakeBackend()
        self.saved = (km._sdk, km._push_all, km._send_to_app, km.jd.optimistic_followup)
        km._sdk = lambda: self.be
        self.pushes = []
        km._push_all = lambda *a, **k: self.pushes.append(1)
        km._send_to_app = lambda *a, **k: None
        # insulate the real goal store: record the optimistic-reopen call, no disk I/O. Tests that need a
        # "reopened" return flip this to True.
        self.fu_calls = []
        km.jd.optimistic_followup = lambda sid, gid, **kw: (self.fu_calls.append((sid, gid)), False)[1]   # **kw tolerates text=/now=/stub= (judge optimistic_followup signature grew)
        # a compactSession routed by ONE test sets the optimistic compacting flag, which makes a LATER
        # test's setModel PARK instead of applying (the intended mid-compaction behavior) — isolate both.
        km._compact_clicked.clear()
        km._pending_ops.clear()

    def tearDown(self):
        km._sdk, km._push_all, km._send_to_app, km.jd.optimistic_followup = self.saved
        km._compact_clicked.clear()
        km._pending_ops.clear()

    def _route(self, msg):
        return km._drive(msg, {"send": lambda s: None})

    def test_send_routes_to_backend(self):
        self.assertTrue(self._route({"type": "sendMessage", "id": "sid-sdk", "text": "hi"}))
        self.assertIn(("send", "sid-sdk", "hi"), self.be.calls)

    def test_non_sdk_sid_routes_to_the_tmux_backend(self):
        # a non-SDK sid no longer "falls through" — _drive routes it to the tmux backend via
        # Sessions.backend_for (the fallback). The unified dispatch handles BOTH kinds.
        tm = FakeBackend(); tm._owned = set()
        saved = km._TMUX
        km._TMUX = tm
        try:
            self.assertTrue(self._route({"type": "sendMessage", "id": "sid-tmux", "text": "hi"}))
            self.assertIn(("send", "sid-tmux", "hi"), tm.calls)   # routed to the tmux backend
            self.assertEqual(self.be.calls, [])                   # the SDK backend was untouched
        finally:
            km._TMUX = saved
            km._tmux_echo.pop("sid-tmux", None)                   # the optimistic echo wrote here — don't leak it

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

    def test_setmodel_mid_compaction_parks_as_a_queued_command(self):
        # the user 2026-07-01: switching the model while a compaction ran broke the compaction — the
        # kernel now PARKS the change (a queued '/model …' bubble) and _apply_pending_models fires it
        # the moment compaction ends. The optimistic click flag alone is enough to engage the park.
        import time as _time
        km._compact_clicked["sid-sdk"] = _time.time()    # the kernel just sent /compact for this session
        self._route({"type": "setModel", "id": "sid-sdk", "value": "opus"})
        self.assertFalse(any(c[0] == "set_model" for c in self.be.calls),
                         "mid-compaction the backend is NOT touched — that broke the compaction")
        self.assertEqual(km._pending_ops.get("sid-sdk"), [("model", "opus")], "parked for after the compaction")

    def test_seteffort_goes_to_backend_compact_still_slash(self):
        # effort routes to set_effort (the backend reconnects with --effort); compact has no control → slash
        self._route({"type": "setEffort", "id": "sid-sdk", "value": "high"})
        self._route({"type": "compactSession", "id": "sid-sdk"})
        self.assertIn(("set_effort", "sid-sdk", "high"), self.be.calls)
        self.assertFalse(any(c == ("send", "sid-sdk", "/effort high") for c in self.be.calls))
        self.assertIn(("send", "sid-sdk", "/compact"), [c for c in self.be.calls if c[0] == "send"])

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
        return km._drive(msg, {"send": send})

    def _sent_to(self, sid):
        return [c[2] for c in self.be.calls if c[0] == "send" and c[1] == sid]

    def test_askfollowup_resolves_sid_from_itemid(self):
        # unified with tmux (the user 2026-07-01): an itemId follow-up now sends the WRAPPED body on the SDK
        # too — the user's text plus the romp-goal-id marker (for the reopen + the chat's ↩ Follow-up header),
        # no longer raw text. (No goal store in the test → the context quote is empty, so the body is just the
        # text + the marker tail.)
        self.assertTrue(self._route({"type": "askFollowUp", "itemId": "sid-sdk:g1", "text": "more"}))
        sent = self._sent_to("sid-sdk")
        self.assertTrue(sent and sent[0].startswith("more"), "the user's text leads the body")
        self.assertIn("<!-- romp-goal-id: sid-sdk:g1 -->", sent[0], "the goal marker rides along for the reopen")

    def test_askfollowup_optimistically_reopens_the_card(self):
        # SDK parity with the tmux path (the user 2026-06-23): a follow-up on an SDK card reopens its goal NOW
        # (optimistic_followup → board jumps to WORKING + a "Followed up" chip), not just sends the text. A
        # reopen (True) triggers a push so the board updates immediately.
        km.jd.optimistic_followup = lambda sid, gid, **kw: (self.fu_calls.append((sid, gid)), True)[1]   # **kw tolerates text=/now=/stub=
        self.pushes.clear()
        self.assertTrue(self._route({"type": "askFollowUp", "itemId": "sid-sdk:g1", "nudge": True, "text": "status?"}))
        sent = self._sent_to("sid-sdk")
        self.assertTrue(sent and "status?" in sent[0], "the follow-up body carries the text")
        self.assertIn("<!-- romp-injected -->", sent[0], "a nudge is romp-authored → gray bubble marker")
        self.assertIn(("sid-sdk", "sid-sdk:g1"), self.fu_calls, "the SDK follow-up reopens the goal optimistically")
        self.assertTrue(self.pushes, "a reopen pushes the refreshed board at once")

    def test_askfollowup_without_itemid_just_sends(self):
        # a raw follow-up with no goal id (e.g. a typed message routed as askFollowUp) sends only — no reopen.
        self.fu_calls.clear()
        self.assertTrue(self._route({"type": "askFollowUp", "id": "sid-sdk", "text": "hi"}))
        self.assertIn(("send", "sid-sdk", "hi"), self.be.calls)
        self.assertEqual(self.fu_calls, [], "no itemId → nothing to reopen")

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
        km._tmux_echo.clear()                         # isolate the shared tmux-echo store across tests

    def tearDown(self):
        km._sdk, km._sessions, km._push_all, km._send_to_app = self.saved
        km._tmux_echo.clear()

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

    def test_merge_skips_when_no_live_atoms(self):
        session = {"turns": []}
        # a tmux sid with an empty echo store has no live atoms → the owning backend (tmux) returns [] and
        # the merge is a no-op (returns the same object). The SDK case is covered by the tests above.
        self.assertIs(km._merge_live_atoms(session, "sid-tmux"), session)

    def test_merge_reopens_the_turn_for_genuine_live_work(self):
        # a streaming assistant reply IS an in-flight turn — the merge must keep forcing it open
        self.be._live = {"sid-sdk": [{"type": "assistant", "uuid": "w1", "t": 50,
                                      "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}]}
        out = km._merge_live_atoms({"turns": [{"id": "t", "atoms": [{"uuid": "old", "t": 10}], "ended": True}]}, "sid-sdk")
        self.assertFalse(out["turns"][-1]["ended"])

    def test_merge_does_NOT_reopen_the_turn_for_a_command_atom(self):
        # the user 2026-07-02 (second half of the phantom-working fix): client.set_model() streams the
        # CLI's confirmation, msg_to_atom classifies it as a COMMAND atom (a completed exchange) — but
        # live_work still counted it and forced the turn open, and on a fresh session NOTHING ever closes
        # it (no reply is coming; a turn-less control request writes no transcript to supersede the live
        # atom). A command atom must keep the turn's real ended state on BOTH shapes:
        cmd = {"type": "assistant", "uuid": "c1", "t": 50, "command": True,
               "message": {"role": "assistant", "content": [{"type": "text", "text": "Set model to sonnet"}],
                           "stop_reason": "end_turn"}}
        # 1) a fresh session (no turns at all) — the synthesized live turn is born ENDED
        self.be._live = {"sid-sdk": [cmd]}
        out = km._merge_live_atoms({"turns": []}, "sid-sdk")
        self.assertTrue(out["turns"][-1]["ended"], "a lone command confirmation never reads as working")
        self.assertFalse(km._session_working(out["turns"]), "the chip stays consistent with the timeline")
        # 2) appended to an existing ENDED turn — stays ended
        self.be._live = {"sid-sdk": [cmd]}
        out = km._merge_live_atoms({"turns": [{"id": "t", "atoms": [{"uuid": "old", "t": 10}], "ended": True}]}, "sid-sdk")
        self.assertTrue(out["turns"][-1]["ended"])

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


class SdkQueuedIndicator(unittest.TestCase):
    """An SDK session keeps its message queue in MEMORY (no transcript queue-op records), so the chat's
    'queued' indicator must read the backend's pending_queued, not _pending_queued (business 2026-06-23)."""

    def test_queued_event_reads_the_owning_backend_pending_queue(self):
        with open(os.path.join(BIN, "romp-kernel")) as f:
            src = f.read()
        # build_session reads the queued texts from the OWNING backend, uniformly — the SDK from its
        # in-memory queue, tmux from the transcript's queue-operation records (TmuxBackend.pending_queued →
        # _pending_queued). No backend fork in build_session anymore.
        self.assertIn("be = Sessions.backend_for(sid)", src)
        self.assertIn("queued = be.pending_queued(sid)", src)
        self.assertIn("return _pending_queued(p) if p else []", src)   # tmux pending_queued reads the transcript


class SdkMetadataParity(unittest.TestCase):
    """SDK sessions should surface the same statusline metadata as tmux (the user 2026-06-24): model/mode on
    OPEN (eager-connect), the git branch derived straight from the FOLDER, and a context-fill bar."""

    def test_git_branch_derived_from_folder(self):
        import subprocess, tempfile
        repo = os.path.dirname(BIN)   # the romp repo itself
        expected = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
        self.assertEqual(km._git_branch(repo), expected, "branch comes straight from the folder, no transcript")
        self.assertEqual(km._git_branch(tempfile.mkdtemp()), "", "not a repo → ''")
        self.assertEqual(km._git_branch(""), "", "no dir → ''")

    def test_open_eager_connects_sdk_branch_fallback_and_ctx_passthrough(self):
        with open(os.path.join(BIN, "romp-kernel")) as f:
            src = f.read()
        # opening a session eager-connects the SDK backend → model/mode publish before the first message
        oor = src.split("def _open_or_revive", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("be.connect(sid)", oor)
        # sysinfo branch falls back to the folder when the transcript lacks it
        self.assertIn('meta.get("gitBranch") or _git_branch(scwd)', src)
        # the SDK merge passes the backend's context-fill % through (was hardcoded None)
        self.assertIn('ctx = st.get("ctx")', src)
        self.assertIn("ctx if isinstance(ctx, (int, float)) else None", src)


if __name__ == "__main__":
    unittest.main()
