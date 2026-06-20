#!/usr/bin/env python3
"""Stop/interrupt → the chat chip should flip to 'ready' (the user 2026-06-20). The chip is driven by the
event-model open-turn signal (open turn AND no idle atom). A normal turn flips it via the transcript's
end_turn; an Esc INTERRUPT writes no end_turn and the Stop hook doesn't fire, so the kernel records a
state:"idle" transition itself (_record_idle) → an idle atom lands in the open turn → the chip reads ready.
Isolated from test_kernel.py (a peer is churning it). Synthetic fixtures only."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_intr", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent, stop):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": stop}}


class RecordIdle(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def test_appends_a_backdated_idle_state_record(self):
        km._record_idle(SID, NOW)
        rows = [json.loads(l) for l in (jd.STATE / "states" / (SID + ".jsonl")).read_text().splitlines() if l]
        self.assertEqual(rows, [{"t": NOW - 1, "state": "idle"}],
                         "one idle transition, backdated 1s so its [start,end] span is non-empty immediately")

    def test_no_sid_is_a_noop(self):
        km._record_idle("", NOW)
        self.assertFalse((jd.STATE / "states").exists(), "no sid → nothing written, no crash")


class IdleAtomFlipsTheOpenTurn(unittest.TestCase):
    """The mechanism: an idle state record (what _record_idle writes) becomes an idle atom inside the OPEN
    turn, so the chip's open_now (= not ended AND no idle atom) goes False → 'ready'."""

    def _open_session(self, states):
        # an OPEN turn: the last assistant stops on tool_use (no end_turn), so the turn never 'ends'
        recs = [uline(T0, "do the thing", "u1"),
                aline(T0 + 10, "working on it", "a1", "u1", "tool_use")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / (SID + ".jsonl")
            p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
            return em.parse_session(str(p), rompuuid=SID, candidate_files=[str(p)], states=states, now=NOW)

    def test_open_turn_is_working_without_an_idle_record(self):
        lt = self._open_session(states=[])["turns"][-1]
        self.assertFalse(lt["ended"], "a tool_use stop leaves the turn open")
        self.assertFalse(any(a["type"] == "idle" for a in lt["atoms"]), "no idle record → no idle atom → still working")

    def test_idle_record_lands_an_idle_atom_in_the_open_turn(self):
        # the interrupt's idle record (backdated 1s, like _record_idle)
        lt = self._open_session(states=[{"t": NOW - 1, "state": "idle"}])["turns"][-1]
        self.assertFalse(lt["ended"], "the turn still never got end_turn")
        self.assertTrue(any(a["type"] == "idle" for a in lt["atoms"]),
                        "the idle transition becomes an idle atom in the open turn → the chip flips to ready")


if __name__ == "__main__":
    unittest.main()
