#!/usr/bin/env python3
"""The drain's belt for a queue the working gate holds (2026-09-19, the note pulled out of #1838): when the backend's
open-turn count holds a session's parked ops while the session's transcript, at rest, shows its last turn closed, the
drain says so once per hold (a `pending-ops.held-working` problem row) and retracts when a later version of the
transcript shows a turn open. The constraints it was designed against: no verdict from absence (no transcript, no
turns, a failing parse say nothing); the transcript is parsed only at rest and once per file version; the note reads no
busy() of its own; a compacting sid is not a hold of this kind; the state clears when the hold ends. Synthetic sids, a
fake backend, the drain-hoists harness."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads (they resolve their state root at import time)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_heldworking", os.path.join(BIN, "romp-kernel"))

SID = "11111111-2222-3333-4444-bbbbbbbbbb01"
SID2 = "11111111-2222-3333-4444-bbbbbbbbbb02"


class _FakeBackend:
    def __init__(self): self.sent = []; self.busy_calls = 0; self._log = None
    def send(self, sid, text, **kw): self.sent.append((sid, text)); return True
    def owns(self, sid): return True
    def busy(self, sid): self.busy_calls += 1; return False
    def turn_seq(self, sid): return 0
    def clearing(self, sid): return False


class HeldWorking(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved_state = jd.STATE
        jd.STATE = Path(self.td.name)
        (jd.STATE / "states").mkdir(parents=True, exist_ok=True)
        self.be = _FakeBackend()
        self._saved = {n: getattr(km, n) for n in
                       ("_compacting_now", "_working_now", "_push_all", "_mark_views_dirty", "_mark_compacting",
                        "_mark_model_pending", "_path_of", "_usage", "_retry_paused_on", "_retry_pause_reason",
                        "_deliver_send_batch", "_parse", "_session_row", "_suspended_after")}
        self._saved_backend = km.Sessions.backend_for
        km._compacting_now = lambda sid: False
        km._working_now = lambda sid: True                  # the gate holds: the count says working
        km._push_all = lambda *a, **k: None
        km._mark_views_dirty = lambda *a, **k: None
        km._mark_compacting = lambda sid: None
        km._mark_model_pending = lambda sid, v: None
        km._usage = lambda: {"limited": None}
        km._retry_paused_on = lambda: False
        km._retry_pause_reason = lambda: ""
        km._deliver_send_batch = lambda be, sid, ops: (ops.clear(), True)[1]
        km._suspended_after = lambda t: False
        km.Sessions.backend_for = staticmethod(lambda sid: self.be)
        self.transcript = Path(self.td.name) / "t.jsonl"
        km._path_of = lambda sid, now=None: (str(self.transcript) if sid == SID else None)
        km._session_row = lambda sid, now=None: {"sid": sid, "name": "web", "path": str(self.transcript)}
        self.parses = 0
        self.turns = [{"ended": True, "atoms": [{"type": "text"}], "t": 1000, "end": 1001}]   # the last turn CLOSED
        def parse(path, sid, now):
            self.parses += 1
            return {"turns": list(self.turns)}
        km._parse = parse
        km._pending_ops.clear(); km._drain_hold.clear(); km._moving.clear(); getattr(km, "_held_working", {}).clear()
        km._pending_ops[SID] = [("send", "typed while the count was stale")]
        self.transcript.write_text("{}\n")

    def tearDown(self):
        for n, v in self._saved.items():
            setattr(km, n, v)
        km.Sessions.backend_for = self._saved_backend
        km._pending_ops.clear(); km._drain_hold.clear(); km._moving.clear(); getattr(km, "_held_working", {}).clear()
        jd.STATE = self.saved_state

    def _rows(self):
        p = jd.STATE / "session-events.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def _kinds(self):
        return [r["kind"] for r in self._rows() if r["kind"].startswith("pending-ops.")]

    def _touch(self, text):
        """A new version of the transcript (a different size, so the stat key moves whatever the clock's grain)."""
        self.transcript.write_text(self.transcript.read_text() + text)

    def test_the_belt_says_once_per_hold_from_a_transcript_at_rest_and_reads_no_busy(self):
        note = getattr(km, "_note_held_working", None)
        self.assertIsNotNone(note, "the drain has a belt for a queue the working gate holds (the base parked in silence)")
        km._apply_pending_ops(1000)                            # cycle one: the stat is recorded, nothing is parsed
        self.assertEqual((self.parses, self._kinds()), (0, []), "the first cycle reads the file's stat only: at rest first")
        km._apply_pending_ops(1001)                            # cycle two: the file rests, one parse, the row
        self.assertEqual(self.parses, 1)
        self.assertEqual(self._kinds(), ["pending-ops.held-working"])
        row = [r for r in self._rows() if r["kind"] == "pending-ops.held-working"][0]
        self.assertEqual((row.get("sid"), row.get("name"), row.get("queued")), (SID, "web", 1))
        for t in (1002, 1003, 1004):
            km._apply_pending_ops(t)
        self.assertEqual((self.parses, self._kinds()), (1, ["pending-ops.held-working"]), "said once; the version was read once")
        self.assertIn(SID, km._pending_ops, "the queue stays held: the belt says, it does not deliver")
        self.assertEqual(self.be.busy_calls, 0, "the belt reads no busy() of its own")

    def test_no_verdict_from_absence(self):
        # an open turn at rest: a real hold, nothing said
        self.turns = [{"ended": False, "atoms": [{"type": "text"}], "t": 1000}]
        km._apply_pending_ops(1000); km._apply_pending_ops(1001); km._apply_pending_ops(1002)
        self.assertEqual((self.parses, self._kinds()), (1, []), "an open turn is the turn's own hold")
        # a parse with no turns: no verdict
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        self.turns = []
        self._touch("x\n")
        km._apply_pending_ops(1003); km._apply_pending_ops(1004); km._apply_pending_ops(1005)
        self.assertEqual((self.parses, self._kinds()), (1, []), "no turns, nothing said")
        # no transcript at all: nothing parsed, nothing said
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        self.transcript.unlink()
        km._apply_pending_ops(1006); km._apply_pending_ops(1007)
        self.assertEqual((self.parses, self._kinds()), (0, []))
        # a parse that raises: no verdict
        self.transcript.write_text("{}\n")
        def boom(path, sid, now): raise ValueError("the transcript is torn")
        km._parse = boom
        km._apply_pending_ops(1008); km._apply_pending_ops(1009)
        self.assertEqual(self._kinds(), [])
        self.assertIn(SID, km._pending_ops)

    def test_a_streaming_transcript_is_never_read_and_a_later_open_turn_retracts(self):
        for t in range(1000, 1006):                            # the file changes every cycle: a turn streaming
            self._touch("row\n")
            km._apply_pending_ops(t)
        self.assertEqual((self.parses, self._kinds()), (0, []), "a file that never rests is never read as closed")
        km._apply_pending_ops(1006)                            # at rest now: read once, closed: the row
        self.assertEqual((self.parses, self._kinds()), (1, ["pending-ops.held-working"]))
        self.turns = [{"ended": False, "atoms": [{"type": "text"}], "t": 1007}]
        self._touch("a new turn\n")
        km._apply_pending_ops(1007)                            # the file moved: at rest first
        self.assertEqual(self.parses, 1)
        km._apply_pending_ops(1008)                            # at rest: read once more, open: the retraction
        self.assertEqual(self.parses, 2)
        self.assertEqual(self._kinds(), ["pending-ops.held-working", "pending-ops.held-working-retracted"])
        km._apply_pending_ops(1009); km._apply_pending_ops(1010)
        self.assertEqual((self.parses, len(self._kinds())), (2, 2), "nothing more until the file changes again")

    def test_the_state_clears_when_the_hold_ends_and_a_compacting_sid_is_not_this_hold(self):
        km._apply_pending_ops(1000); km._apply_pending_ops(1001)
        self.assertEqual(self._kinds(), ["pending-ops.held-working"])
        km._working_now = lambda sid: False                    # the hold ends: the queue drains, the state clears
        km._apply_pending_ops(1002)
        self.assertNotIn(SID, km._pending_ops)
        self.assertNotIn(SID, getattr(km, "_held_working", {}))
        km._pending_ops[SID] = [("send", "again")]             # a new hold says again
        km._working_now = lambda sid: True
        km._apply_pending_ops(1003); km._apply_pending_ops(1004)
        self.assertEqual(self._kinds(), ["pending-ops.held-working", "pending-ops.held-working"])
        # a compacting sid: the compacting gate's hold, no belt state, nothing said
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        kinds_before = self._kinds()
        km._compacting_now = lambda sid: True
        for t in (1005, 1006, 1007):
            km._apply_pending_ops(t)
        self.assertEqual((self.parses, self._kinds(), SID in getattr(km, "_held_working", {})), (0, kinds_before, False))


if __name__ == "__main__":
    unittest.main()
