#!/usr/bin/env python3
"""_route_meta_command evaluates the drive-op gate (_ops_gate) exactly as often as the setter it calls
does, and never on its own account. /effort and /fast take _gate_or_park: ONE evaluation, outside the
queue lock, then the locked queue-presence check. /model takes _set_model_or_park's own rule, which
never calls _ops_gate. Each setter returns whether it parked, and that return is what POST /send
answers as `queued`.

The route used to evaluate _ops_gate once more itself, to answer `queued`, and then took the setter's
return anyway: a tmux fork, a discover pass, the usage file and the backend's busy() on the handler
thread, per command, for a value nothing read. The review of #954 (#986) removed that read on
2026-09-07; the #923 merge the same day brought it back. tests/test_model_live_midturn pins the value
of `queued`; this pins its cost. The gate is patched to a counter, so the counts are the gate's own
evaluations and nothing underneath it runs. Synthetic only: a placeholder sid, invented values."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from romp_load import load_source
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the load: the kernel resolves its state root at import time, and only pytest
# runs conftest's floor (a bare unittest run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["ROMP_MANAGER_PORT"] = "1"             # a dead port, never an inherited live one
km = load_source("romp_kernel_meta_gate", os.path.join(BIN, "romp-kernel"))

SID = "11111111-2222-4333-8444-0a0a0a0a0a0a"      # private to this module: parked ops are keyed by sid


class _Backend:
    """A backend that takes every setter; records what fired. Only the three setters' calls: neither the
    route nor a setter reaches any other method on the paths driven here. `effort_ok` is set_effort's
    verdict, the SessionBackend contract's bool: False is a level the Codex model's catalog does not
    offer (CodexBackend.set_effort answers it for an unknown model or an unreadable catalog too)."""
    def __init__(self): self.calls = []; self.effort_ok = True
    def set_model(self, sid, v): self.calls.append(("model", v))
    def set_effort(self, sid, v): self.calls.append(("effort", v)); return self.effort_ok
    def set_fast(self, sid, v): self.calls.append(("fast", v)); return True


def _forget_queue():
    """Drop the sid's parked ops from memory AND the disk mirror: a park writes pending-ops.json under this
    module's state dir, and a kernel loaded later in the same process would restore the queue from it. The
    drain's per-sid bookkeeping (the in-flight head, the drain hold) is dropped too, so no case starts with
    another's leftovers."""
    km._pending_ops.pop(SID, None)
    km._inflight_ops.pop(SID, None)
    km._drain_hold.pop(SID, None)
    km._save_pending_ops()


class MetaCommandGateCost(unittest.TestCase):
    def setUp(self):
        self.be = _Backend()
        self.gate_calls = []
        self.verdict = False
        _forget_queue()
        km._moving.discard(SID)
        stubs = {
            "_ops_gate": lambda sid: (self.gate_calls.append(str(sid)), self.verdict)[1],
            "_compacting_now": lambda sid, **k: False,   # the model setter's own gates, quiet here
            "_working_now": lambda sid: False,
            "_limit_hold": lambda sid: None,             # the account gate is its own axis
            "_mark_model_pending": lambda *a, **k: None,
            "_note_model_pick": lambda *a, **k: None,
        }
        for name, stub in stubs.items():
            p = mock.patch.object(km, name, stub)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(_forget_queue)

    def _route(self, text):
        self.gate_calls.clear()
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, text, state=state), text)
        return len(self.gate_calls), state.get("queued")

    def test_effort_and_fast_evaluate_the_gate_once_and_model_never_when_they_fire(self):
        self.assertEqual(self._route("/effort high"), (1, False))
        self.assertEqual(self._route("/fast on"), (1, False))
        self.assertEqual(self._route("/model opus"), (0, False), "the model setter has its own rule; no _ops_gate")
        self.assertEqual(self.be.calls, [("effort", "high"), ("fast", "on"), ("model", "opus")], "each fired once")
        self.assertNotIn(SID, km._pending_ops)

    def test_the_counts_are_the_same_when_the_gate_parks(self):
        # `queued` comes from the setter's own return, so a park costs the same single evaluation
        self.verdict = True
        self.assertEqual(self._route("/effort high"), (1, True))
        self.assertEqual(self._route("/fast on"), (1, True))
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):   # the model setter's own park
            self.assertEqual(self._route("/model opus"), (0, True))
        self.assertEqual(self.be.calls, [], "nothing fired: every op parked")
        self.assertEqual([op[0] for op in km._pending_ops[SID]], ["effort", "fast", "model"], "parked in press order")

    def test_codex_effort_commands_reach_the_backend_instead_of_becoming_prompts(self):
        with mock.patch.object(km, "_codex", return_value=self.be):
            self.assertEqual(self._route("/effort ultra"), (1, False))
            self.assertEqual(self.be.calls, [("effort", "ultra")])
            self.verdict = True
            self.assertEqual(self._route("/effort future-level"), (1, True))
            self.assertEqual(km._pending_ops[SID][-1], ("effort", "future-level"))
            self.assertEqual(self.be.calls, [("effort", "ultra")], "a parked pick waits its turn")

    # The setter's verdict used to be dropped (only `parked` came back), so a Codex level the model's catalog
    # does not offer answered ok while nothing moved. It returns (took, parked) like the fast setter now, the
    # route files the refusal for POST /send and tells a client, and an offered level still answers plain ok.
    def test_a_codex_level_the_catalog_does_not_offer_is_refused_with_the_reason(self):
        sent = []
        client = {"send": lambda t: sent.append(json.loads(t))}
        with mock.patch.object(km, "_codex", return_value=self.be):
            self.be.effort_ok = False
            state = {}
            self.assertTrue(km._route_meta_command(self.be, SID, "/effort ultra", client, state=state))
            self.assertIn("Codex catalog does not offer", state["refused_effort"])
            self.assertIn("'ultra'", state["refused_effort"], "the refused level is named")
            self.assertIs(state["queued"], False)
            self.assertEqual(sent, [{"type": "settingRefused", "gesture": "command", "sid": SID, "flag": "effort",
                                     "text": state["refused_effort"]}],
                             "the client hears the same words, on the timeline's own frame (never a bare warn)")
            self.assertEqual(self.be.calls, [("effort", "ultra")], "the backend was asked, and said no")
            self.assertNotIn(SID, km._pending_ops, "a refusal parks nothing")

    def test_a_codex_level_the_catalog_offers_is_taken_and_answers_ok(self):
        sent = []
        client = {"send": lambda t: sent.append(json.loads(t))}
        with mock.patch.object(km, "_codex", return_value=self.be):
            state = {}
            self.assertTrue(km._route_meta_command(self.be, SID, "/effort ultra", client, state=state))
            self.assertNotIn("refused", state)
            self.assertIs(state["queued"], False)
            self.assertEqual(sent, [], "nothing to say: the level landed")
            self.assertEqual(self.be.calls, [("effort", "ultra")])

    def test_the_effort_setter_returns_took_and_parked_like_the_fast_setter(self):
        self.be.effort_ok = False
        self.assertEqual(km._set_effort_or_park(self.be, SID, "ultra"), (False, False), "refused: not taken, not queued")
        self.be.effort_ok = True
        self.assertEqual(km._set_effort_or_park(self.be, SID, "ultra"), (True, False), "landed now")
        self.verdict = True
        self.assertEqual(km._set_effort_or_park(self.be, SID, "ultra"), (True, True), "parked: taken, queued")
        self.assertEqual(self.be.calls, [("effort", "ultra"), ("effort", "ultra")], "the parked pick waits its turn")
        self.assertEqual(km._pending_ops[SID], [("effort", "ultra")])

    def test_a_new_effort_on_an_unowned_session_is_refused_not_sent(self):
        state = {}
        self.assertTrue(km._route_meta_command(km._UNOWNED, SID, "/effort future-level", state=state))
        self.assertIn("not delivered", state["refused"])
        self.assertNotIn(SID, km._pending_ops)


class RefusalReachesTheClient(unittest.TestCase):
    """What a CLIENT hears when the backend refuses an effort level or a fast toggle: the route and the setter
    are pinned above, these pin the arms that reach a pane. The frame is the timeline's own settingRefused
    shape (type settingRefused, gesture command, the sid, the flag, the reason), never a bare warn: the chat
    read a warn arriving during a create as that create's verdict and struck the provisional tab, and the
    timeline page renders no warn at all, so a lane-menu pick's refusal was dropped there and its optimistic
    dim ran out its 20 s timer, though both pages already handle settingRefused. Three roads answer with it: the
    setEffort and setFast ops in _drive (this pane's socket), _route_meta_command with a client (the lane
    menu's sendCommand, the composer's typed command), its unowned arm included, whose flag is the command
    head's word, and the parked-op drain (_apply_pending_ops), which fires a pick the gate parked once the
    session is quiet: no client is at hand there, so it addresses the chat page through _send_to_app, and it
    writes the walk's own `pending ops apply: ... refused` stderr line, as the command and compact arms do.
    POST /send (_deliver_text) has no socket and answers ok False with the words instead. The stub is vouched as
    the Codex backend for the effort cases ("ultra" is admitted only for a Codex session); the /fast cases route
    un-vouched, since a live Codex session's /fast is refused above the setter by the Codex slash guard (#1864),
    so the fast arm's client is an SDK or unowned session.
    Synthetic only: a placeholder sid, an invented level."""

    def setUp(self):
        self.be = _Backend()
        self.be.effort_ok = False
        self.verdict = False                   # _ops_gate's answer: False fires the pick now, True parks it
        self.frames = []                       # _send_to_app: (app, frame)
        _forget_queue()
        km._moving.discard(SID)
        stubs = {
            "_ops_gate": lambda sid: self.verdict,       # nothing parks by default: the pick reaches the backend
            "_compacting_now": lambda sid, **k: False,   # the model setter's own gates, quiet here; the drain's too
            "_working_now": lambda sid: False,
            "_limit_hold": lambda sid: None,             # the account gate is its own axis
            "_codex": lambda: self.be,          # the pick is vouched as a Codex one (the route admits a level outside
                                                # _EFFORT_VALUES only for one); _effort_refusal picks the catalog words
            "_name_of": lambda sid: "web",      # _drive's session gate (_kernel_knows) admits a session this kernel has
            "_push_soon": lambda *a, **k: None,
            "_send_to_app": lambda app, m: self.frames.append((app, m)),   # the drain's addressee: the chat page
        }
        for name, stub in stubs.items():
            p = mock.patch.object(km, name, stub)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: self.be))   # _drive resolves be here
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(_forget_queue)

    @staticmethod
    def _client():
        sent = []
        return {"send": lambda t: sent.append(json.loads(t))}, sent

    @staticmethod
    def _frame(flag, text):
        return {"type": "settingRefused", "gesture": "command", "sid": SID, "flag": flag, "text": text}

    def test_the_set_effort_op_answers_a_refused_level_with_one_setting_refused_frame_and_parks_nothing(self):
        client, sent = self._client()
        self.assertTrue(km._drive({"type": "setEffort", "id": SID, "value": "ultra"}, client))
        why = km._effort_refusal(self.be, "ultra")
        self.assertIn("Codex catalog does not offer", why)
        self.assertEqual(sent, [self._frame("effort", why)], "one frame, on the timeline's shape: its own type and the sid")
        self.assertEqual(self.be.calls, [("effort", "ultra")], "the backend was asked, and said no")
        self.assertNotIn(SID, km._pending_ops, "a refusal parks nothing")

    def test_the_set_fast_op_answers_its_refusal_on_the_same_frame(self):
        self.be.set_fast = lambda sid, v: False          # a dormant SDK session: no live CLI to apply it
        client, sent = self._client()
        self.assertTrue(km._drive({"type": "setFast", "id": SID, "value": "on"}, client))
        self.assertEqual(len(sent), 1, sent)
        self.assertEqual({k: sent[0].get(k) for k in ("type", "gesture", "sid", "flag")},
                         {"type": "settingRefused", "gesture": "command", "sid": SID, "flag": "fast"})
        self.assertIn("fast mode", sent[0]["text"])
        self.assertNotIn(SID, km._pending_ops, "a refusal parks nothing")

    def test_the_command_route_answers_a_refused_fast_toggle_on_the_same_frame(self):
        # the effort arm's frame is pinned above (a level the catalog does not offer); this is the /fast arm's.
        # Not vouched as a Codex session for this call: a live Codex session's /fast is refused above the setter
        # by the Codex slash guard (#1864), so the fast arm's client is an SDK or unowned session.
        self.be.set_fast = lambda sid, v: False
        client, sent = self._client()
        state = {}
        with mock.patch.object(km, "_codex", lambda: None):
            self.assertTrue(km._route_meta_command(self.be, SID, "/fast on", client, state=state))
        self.assertIs(state["queued"], False)
        self.assertEqual([tuple(m.get(k) for k in ("type", "gesture", "sid", "flag")) for m in sent],
                         [("settingRefused", "command", SID, "fast")], sent)
        self.assertIn("fast mode", sent[0]["text"])

    def test_the_command_route_answers_an_unowned_sessions_pick_on_the_same_frame_with_the_heads_flag(self):
        # the unowned arm: a session no running backend owns (a dead Codex lane whose menu still offers its gpt
        # models, a dead SDK lane) takes no setting, and this refusal is the one place the client hears that the
        # pick went nowhere. The flag is the command head's word (model, effort or fast), the key each page's
        # pending map is filed under; the refused state and the stderr line stay as they were.
        for text, flag in (("/model gpt-5-test", "model"), ("/effort ultra", "effort"), ("/fast on", "fast")):
            client, sent = self._client()
            state = {}
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertTrue(km._route_meta_command(km._UNOWNED, SID, text, client, state=state), text)
            self.assertEqual([tuple(m.get(k) for k in ("type", "gesture", "sid", "flag")) for m in sent],
                             [("settingRefused", "command", SID, flag)], (text, sent))
            self.assertIn("no running backend owns this session", sent[0]["text"])
            self.assertEqual(state["refused"], sent[0]["text"], "POST /send answers ok False with the same words")
            self.assertIn("meta command %s for %s refused" % (text.split()[0], SID), err.getvalue(),
                          "the stderr line stays as it was")
            self.assertNotIn(SID, km._pending_ops, "refused before any park")
        self.assertEqual(self.be.calls, [], "no backend was asked: nobody owns the session")

    # The drain's arm. A pick the gate parks (a compaction, an open turn, a queue ahead of it) meets the backend
    # only when the queue drains, and the setter's verdict moves with it: the drain read that verdict for the
    # command and compact kinds and dropped it for effort and fast, so a level the backend refused at fire time
    # (a Codex model whose catalog does not offer it after a model change under the park) was popped with no
    # frame, no stderr line and no reply, and the queued chip retired as if the level had landed. The drain has
    # no client at hand (the pusher thread runs it), so the frame goes to the chat page through _send_to_app.
    def _park_then_drain(self, text, codex=True):
        """Park `text` through the route under a gate that says busy, then lift the gate and run the drain once
        (bare, as the pusher calls it). Returns what the drain wrote to stderr. `codex` False lifts the class's
        vouch for the ROUTE call alone (a /fast on a Codex session is refused above the setter, #1864: see the
        class docstring); the drain runs as is, its effort and fast arms consult no vouch."""
        self.verdict = True
        state = {}
        with mock.patch.object(km, "_codex", lambda: self.be if codex else None):   # the class's vouch, or none
            self.assertTrue(km._route_meta_command(self.be, SID, text, state=state), text)
        self.assertIs(state["queued"], True, "the gate parked it")
        self.assertEqual(self.be.calls, [], "nothing applies before the gate lifts")
        self.verdict = False
        err = io.StringIO()
        with redirect_stderr(err):
            km._apply_pending_ops()
        self.assertNotIn(SID, km._pending_ops, "popped once, never replayed")
        return err.getvalue()

    def test_a_parked_level_the_backend_refuses_at_the_drain_is_said_to_the_chat_and_on_stderr(self):
        err = self._park_then_drain("/effort ultra")
        self.assertEqual(self.be.calls, [("effort", "ultra")], "the backend was asked once, at the drain, and said no")
        self.assertEqual(self.frames, [("chat", self._frame("effort", km._effort_refusal(self.be, "ultra")))],
                         "one frame to the chat, the setEffort op's shape and words")
        self.assertIn("pending ops apply: _Backend refused '/effort ultra' for " + SID[:8], err,
                      "the stderr line the command and compact arms write")

    def test_a_parked_fast_toggle_the_backend_refuses_at_the_drain_is_said_the_same_way(self):
        self.be.set_fast = lambda sid, v: False          # a Codex session has no fast mode; an SDK session the backend
        err = self._park_then_drain("/fast on", codex=False)   # holds no row for. Routed as an SDK session (the helper)
        self.assertEqual([(a, m["type"], m["gesture"], m["sid"], m["flag"]) for a, m in self.frames],
                         [("chat", "settingRefused", "command", SID, "fast")], self.frames)
        self.assertIn("fast mode", self.frames[0][1]["text"])
        self.assertIn("pending ops apply: _Backend refused '/fast on' for " + SID[:8], err)

    def test_a_parked_level_the_backend_takes_at_the_drain_says_nothing(self):
        self.be.effort_ok = True
        err = self._park_then_drain("/effort ultra")
        self.assertEqual(self.be.calls, [("effort", "ultra")])
        self.assertEqual(self.frames, [], "nothing to say: the level landed")
        self.assertEqual(err, "", "and no stderr line")

    def test_a_refused_level_is_said_even_when_a_repeat_pick_replaced_the_head_while_the_backend_had_it(self):
        # The head stays visible while the backend has it, so a pick made during the call finds the queue and
        # parks behind it; a same-kind pick REPLACES the head in place (a new tuple), the identity pop then
        # leaves the slot alone (`took` False) and the replacement delivers on the next iteration of the same
        # pass. Its arrival does not unsay the first pick's refusal: one frame and one line, for the level the
        # backend refused, and nothing for the level it took.
        parked = []
        def set_effort(sid, v):
            self.be.calls.append(("effort", v))
            if v == "ultra":
                parked.append(km._park_behind_queue(SID, ("effort", "other")))   # a handler's pick, mid-call
                return False
            return True
        self.be.set_effort = set_effort
        err = self._park_then_drain("/effort ultra")
        self.assertEqual(parked, [True], "the repeat pick found the in-flight head and took its slot")
        self.assertEqual(self.be.calls, [("effort", "ultra"), ("effort", "other")], "refused, then the replacement")
        self.assertEqual(self.frames, [("chat", self._frame("effort", km._effort_refusal(self.be, "ultra")))],
                         "one frame, for the refused pick; the replacement landed and says nothing")
        self.assertIn("pending ops apply: _Backend refused '/effort ultra' for " + SID[:8], err)
        self.assertEqual(err.count("pending ops apply"), 1, err)
        self.assertNotIn("other", err, "no line for the level the backend took")

    def test_a_setter_answering_none_at_the_drain_is_not_reported_as_a_refusal(self):
        # Strict `is False`: the SessionBackend contract is a bool and every shipped setter keeps it, so a
        # setter that answers None (a stub, an older backend) is outside the contract and is not read as a
        # refusal; only False is. Both arms, since each reads its own verdict.
        self.be.effort_ok = None
        self.be.set_fast = lambda sid, v: (self.be.calls.append(("fast", v)), None)[1]
        err = self._park_then_drain("/effort ultra")
        self.assertEqual(self.be.calls, [("effort", "ultra")])
        self.be.calls.clear()
        err += self._park_then_drain("/fast on", codex=False)
        self.assertEqual(self.be.calls, [("fast", "on")])
        self.assertEqual(self.frames, [], "None is not False: nothing is said")
        self.assertEqual(err, "", "and no stderr line")


if __name__ == "__main__":
    unittest.main()
