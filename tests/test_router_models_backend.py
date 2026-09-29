#!/usr/bin/env python3
"""The assistant-turn model guard in SdkSession._on_message, driven end to end (review round 2, 2026-09-22).

An AssistantMessage teaches the session its model badge only when the id is REAL: one that names Claude, or a
gateway id the process knows through _router_declared (the operator's ROMP_ROUTER_MODELS united with the ids
the kernel told it via set_router_ids), or the session's own picked raw id. Injected turns carry
model="<synthetic>" and must never reach the badge. Before this module the declared-id clause was unpinned:
reverting it, or widening the guard to `m != "<synthetic>"`, left the suite green. Each case here drives a
message through _on_message the way tests/test_sdk_backend.py's synthetic-badge test does and reads the badge
back:

- a declared id (ROMP_ROUTER_MODELS) is learned verbatim;
- an undeclared non-Claude id ("<synthetic>", an invented "zz-9-x") leaves the badge where it was — the
  invented one is what catches the widened guard;
- an id known only through set_router_ids (a gateway listing's) is learned;
- an id unknown to the twin but equal to the session's own picked raw id (self._model_id) is learned: the
  session running it is the proof it is real (a contract the lead is adding in parallel; red until it lands).

Synthetic only: placeholder sid, invented ids, a backend over a temp state root with session hosts off.
"""
import os
import sys
import tempfile
import unittest

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the load — the module resolves its state root at import time, and only pytest runs
# conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ.pop("ROMP_ROUTER_MODELS", None)
sb = load_source("romp_sdk_backend_router_guard", os.path.join(BIN, "romp_sdk_backend.py"))

SID = "11111111-2222-3333-4444-555555555555"


class _TextBlock:
    def __init__(self, text): self.text = text


class _AssistantMessage:
    def __init__(self, content, model, uuid="a1", stop_reason="end_turn"):
        self.content, self.model, self.uuid, self.stop_reason = content, model, uuid, stop_reason


class _ResultMessage:
    uuid = "r1"


class _Sys:                                  # a stand-in for SystemMessage (an isinstance argument only)
    pass


# _on_message and msg_to_atom match by type name
_TextBlock.__name__ = "TextBlock"
_AssistantMessage.__name__ = "AssistantMessage"
_ResultMessage.__name__ = "ResultMessage"


def _env(tc, key, value):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    tc.addCleanup(lambda: os.environ.__setitem__(key, prev) if prev is not None else os.environ.pop(key, None))


class AssistantTurnGuard(unittest.TestCase):
    def setUp(self):
        _env(self, "ROMP_ROUTER_MODELS", None)
        self._ids = sb._ROUTER_IDS
        sb.set_router_ids(())
        self.addCleanup(lambda: setattr(sb, "_ROUTER_IDS", self._ids))
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "session-hosts"), "w") as f:
            f.write("off")                   # a minted state root is outside conftest's belt (repo rule, 2026-09-11)
        self.be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)

    def _session(self, reg=None):
        s = sb.SdkSession(self.be, dict({"sid": SID, "name": "n", "cwd": "/tmp"}, **(reg or {})))
        return s

    def _turn(self, s, mid):
        s._on_message(_AssistantMessage([_TextBlock("hi")], model=mid), _AssistantMessage, _ResultMessage, _Sys)

    def _seeded(self):
        s = self._session()
        self._turn(s, "claude-opus-4-8")
        self.assertEqual(s.model, "Opus 4.8", "a first-party id seeds the badge")
        return s

    def test_a_declared_id_is_learned_verbatim(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra, gw-5.6-luna")
        s = self._seeded()
        self._turn(s, "gw-6-astra")
        self.assertEqual(s.model, "gw-6-astra", "a declared gateway id is a real id: the badge shows it verbatim")
        self.assertEqual(s._model_id, "gw-6-astra", "and it is the raw id behind the badge")

    def test_an_undeclared_non_claude_id_leaves_the_badge_untouched(self):
        s = self._seeded()
        for mid in ("<synthetic>", "zz-9-x"):
            self._turn(s, mid)
            self.assertEqual(s.model, "Opus 4.8", "%r is not a real id here: the last good badge sticks" % mid)
            self.assertEqual(s._model_id, "claude-opus-4-8", mid)

    def test_an_id_known_only_through_set_router_ids_is_learned(self):
        # a gateway listing's id: the kernel tells the module (kernel._router_tell_backend); the variable never names it
        s = self._seeded()
        sb.set_router_ids({"gw-7-nova"})
        self._turn(s, "gw-7-nova")
        self.assertEqual(s.model, "gw-7-nova")
        self.assertEqual(s._model_id, "gw-7-nova")

    def test_an_id_equal_to_the_sessions_own_picked_raw_id_is_learned(self):
        # unknown to the twin (nothing declared, nothing told: a process that restarted with the switch off) but the
        # session's registry row carries it as the raw id it runs — the session running it is the proof it is real
        s = self._session({"liveModelId": "gw-8-orion"})
        self.assertEqual(s._model_id, "gw-8-orion")
        self.assertEqual(s.model, "", "no badge seeded: the learn is what fills it")
        self.assertNotIn("gw-8-orion", sb._router_declared(), "the twin does not know it")
        self._turn(s, "gw-8-orion")
        self.assertEqual(s.model, "gw-8-orion", "the session's own picked raw id is learned")

    def test_the_sessions_own_id_does_not_open_the_door_to_other_ids(self):
        s = self._session({"liveModel": "gw-8-orion", "liveModelId": "gw-8-orion"})
        self._turn(s, "zz-9-x")
        self.assertEqual(s.model, "gw-8-orion", "an unknown id that is not the session's own stays out")
        self._turn(s, "<synthetic>")
        self.assertEqual(s.model, "gw-8-orion")


if __name__ == "__main__":
    unittest.main()
