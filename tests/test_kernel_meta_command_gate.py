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
import json
import os
import tempfile
import unittest
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
    module's state dir, and a kernel loaded later in the same process would restore the queue from it."""
    km._pending_ops.pop(SID, None)
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
            self.assertEqual(sent, [{"type": "warn", "text": state["refused_effort"]}], "the client hears the same words")
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


if __name__ == "__main__":
    unittest.main()
