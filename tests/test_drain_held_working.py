#!/usr/bin/env python3
"""The drain's belt for a queue the working gate holds (2026-09-19, the note pulled out of #1838): when the backend's
open-turn COUNT ALONE holds a session's parked ops (a turn counted open, nothing queued to start) while the session's
transcript, at rest, shows its last turn closed, the belt says so once per hold (a `pending-ops.held-working` problem row)
and retracts when a later version of the transcript shows a turn open. The drain records the hold on the pusher's thread;
the jobs thread's pass (_held_working_pass) reads the transcript. The constraints it was designed against: the count is the
one source (never the composite busy(): a queued turn or a feeder waiting with the count at zero is a correct hold, round
two of the review); no verdict from absence (no transcript, no turns, a failing parse say nothing); the transcript is parsed
only at rest and once per file version, never on the pusher; the belt reads no busy() of its own; a compacting sid is not
a hold of this kind; the state clears when the hold ends or the chip is cancelled. Synthetic sids, a fake backend, the
drain-hoists harness."""
import inspect
import json
import os
import tempfile
import threading
import types
import time
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads (they resolve their state root at import time)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
with open(os.path.join(os.environ["XDG_STATE_HOME"], "romp", "session-hosts"), "w") as _f:
    _f.write("off")                                                  # a minted state root pins the per-session hosts off (the repo rule)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_heldworking", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_heldworking", os.path.join(BIN, "romp_sdk_backend.py"))

SID = "11111111-2222-3333-4444-bbbbbbbbbb01"
SID2 = "11111111-2222-3333-4444-bbbbbbbbbb02"


class _FakeBackend:
    def __init__(self): self.sent = []; self.busy_calls = 0; self._log = None; self.count_open = True
    def send(self, sid, text, **kw): self.sent.append((sid, text)); return True
    def owns(self, sid): return True
    def busy(self, sid): self.busy_calls += 1; return False
    def count_says_open(self, sid): return self.count_open        # the count alone: inflight > 0 with nothing queued
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

    def _cycle(self, t):
        """One pusher cycle (the drain records the hold) and one jobs pass (the belt reads), as the two threads interleave."""
        km._apply_pending_ops(t)
        jobs = getattr(km, "_held_working_pass", None)         # absent at the base: the drives then red on their assertions
        if jobs is not None:
            jobs(t)

    def _touch(self, text):
        """A new version of the transcript (a different size, so the stat key moves whatever the clock's grain)."""
        self.transcript.write_text(self.transcript.read_text() + text)

    def test_the_belt_says_once_per_hold_from_a_transcript_at_rest_and_reads_no_busy(self):
        note = getattr(km, "_held_working_pass", None)
        self.assertIsNotNone(note, "the drain has a belt for a queue the working gate holds (the base parked in silence)")
        self._cycle(1000)                                      # cycle one: the stat is recorded, nothing is parsed
        self.assertEqual((self.parses, self._kinds()), (0, []), "the first cycle reads the file's stat only: at rest first")
        self._cycle(1001)                                      # cycle two: the file rests, one parse, the row
        self.assertEqual(self.parses, 1)
        self.assertEqual(self._kinds(), ["pending-ops.held-working"])
        row = [r for r in self._rows() if r["kind"] == "pending-ops.held-working"][0]
        self.assertEqual((row.get("sid"), row.get("name"), row.get("queued")), (SID, "web", 1))
        self.assertIn("1 parked item waits", row.get("text") or "", "the singular agrees with its verb")
        for t in (1002, 1003, 1004):
            self._cycle(t)
        self.assertEqual((self.parses, self._kinds()), (1, ["pending-ops.held-working"]), "said once; the version was read once")
        self.assertIn(SID, km._pending_ops, "the queue stays held: the belt says, it does not deliver")
        self.assertEqual(self.be.busy_calls, 0, "the belt reads no busy() of its own")

    def test_no_verdict_from_absence(self):
        # an open turn at rest: a real hold, nothing said
        self.turns = [{"ended": False, "atoms": [{"type": "text"}], "t": 1000}]
        self._cycle(1000); self._cycle(1001); self._cycle(1002)
        self.assertEqual((self.parses, self._kinds()), (1, []), "an open turn is the turn's own hold")
        # a parse with no turns: no verdict
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        self.turns = []
        self._touch("x\n")
        self._cycle(1003); self._cycle(1004); self._cycle(1005)
        self.assertEqual((self.parses, self._kinds()), (1, []), "no turns, nothing said")
        # no transcript at all: nothing parsed, nothing said
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        self.transcript.unlink()
        self._cycle(1006); self._cycle(1007)
        self.assertEqual((self.parses, self._kinds()), (0, []))
        # a parse that raises: no verdict
        self.transcript.write_text("{}\n")
        def boom(path, sid, now): raise ValueError("the transcript is torn")
        km._parse = boom
        self._cycle(1008); self._cycle(1009)
        self.assertEqual(self._kinds(), [])
        self.assertIn(SID, km._pending_ops)

    def test_a_streaming_transcript_is_never_read_and_a_later_open_turn_retracts(self):
        for t in range(1000, 1006):                            # the file changes every cycle: a turn streaming
            self._touch("row\n")
            self._cycle(t)
        self.assertEqual((self.parses, self._kinds()), (0, []), "a file that never rests is never read as closed")
        self._cycle(1006)                                      # at rest now: read once, closed: the row
        self.assertEqual((self.parses, self._kinds()), (1, ["pending-ops.held-working"]))
        self.turns = [{"ended": False, "atoms": [{"type": "text"}], "t": 1007}]
        self._touch("a new turn\n")
        self._cycle(1007)                                      # the file moved: at rest first
        self.assertEqual(self.parses, 1)
        self._cycle(1008)                                      # at rest: read once more, open: the retraction
        self.assertEqual(self.parses, 2)
        self.assertEqual(self._kinds(), ["pending-ops.held-working", "pending-ops.held-working-retracted"])
        self._cycle(1009); self._cycle(1010)
        self.assertEqual((self.parses, len(self._kinds())), (2, 2), "nothing more until the file changes again")

    def test_the_state_clears_when_the_hold_ends_and_a_compacting_sid_is_not_this_hold(self):
        self._cycle(1000); self._cycle(1001)
        self.assertEqual(self._kinds(), ["pending-ops.held-working"])
        km._working_now = lambda sid: False                    # the hold ends: the queue drains, the state clears
        self._cycle(1002)
        self.assertNotIn(SID, km._pending_ops)
        self.assertNotIn(SID, getattr(km, "_held_working", {}))
        km._pending_ops[SID] = [("send", "again")]             # a new hold says again
        km._working_now = lambda sid: True
        self._cycle(1003); self._cycle(1004)
        self.assertEqual(self._kinds(), ["pending-ops.held-working", "pending-ops.held-working"])
        # a compacting sid: the compacting gate's hold, no belt state, nothing said
        getattr(km, "_held_working", {}).clear(); self.parses = 0
        kinds_before = self._kinds()
        km._compacting_now = lambda sid: True
        for t in (1005, 1006, 1007):
            self._cycle(t)
        self.assertEqual((self.parses, self._kinds(), SID in getattr(km, "_held_working", {})), (0, kinds_before, False))

    def test_the_count_alone_is_the_source_never_the_composite_busy(self):
        """Round two of the review: busy() is inflight > 0 OR a queued turn, and the feeder holds its queue with the count at
        zero in states where the hold is correct (a parked deploy restart, an armed reconnect after a settings switch, a
        pending rewind, the gap between send() and the feeder's pop); the transcript then rests with its last turn closed
        because no turn runs, and a belt on busy() called a proper hold a stale count. The belt reads the count alone."""
        self.be.count_open = False                             # the working gate holds (busy() True) with the count at zero
        for t in (1000, 1001, 1002, 1003):
            self._cycle(t)
        self.assertEqual((self.parses, self._kinds()), (0, []), "a hold the count does not carry alone is not read, not said")
        self.assertIn(SID, km._pending_ops, "the hold stands (it is correct)")
        km._working_now = lambda sid: False                    # the feeder catches up: the queue drains, the state clears
        self._cycle(1004)
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(self._kinds(), [], "and nothing to retract, because nothing was said")

    def test_the_backends_count_reader_is_inflight_with_nothing_queued(self):
        """SdkBackend.count_says_open against the four shapes: a turn running (True), a turn queued with the count at zero
        (False: the feeder's correct hold), both (False: the queue is about to run), neither (False), a sid it does not run (None)."""
        fn = getattr(sb.SdkBackend, "count_says_open", None)
        self.assertIsNotNone(fn, "the backend exposes the count alone (the base had only the composite busy())")
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, True))
        with open(os.path.join(d, "session-hosts"), "w") as f:
            f.write("off")                                            # this backend's own state root: hosts off (the repo rule)
        be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None, log=lambda *a, **k: None)
        mk = lambda inflight, pending: types.SimpleNamespace(inflight=inflight, _pending=list(pending), _lock=threading.Lock())
        for inflight, pending, want in ((1, [], True), (0, ["queued"], False), (1, ["queued"], False), (0, [], False)):
            be.sessions[SID] = mk(inflight, pending)
            self.assertIs(be.count_says_open(SID), want, "inflight=%d pending=%r" % (inflight, pending))
            self.assertEqual(be.busy(SID), inflight > 0 or bool(pending), "busy() stays the composite it was")
        be.sessions.pop(SID, None)
        self.assertIsNone(be.count_says_open(SID))

    def test_cancelling_the_chip_clears_the_belt_so_the_next_hold_says_again(self):
        """Round two: _cancel_parked popped the queue and the drain hold but not the belt's state, so after the user cancelled
        the chip (the natural reaction) and typed again into the same stuck session, the surviving state (said, the same
        parsed key) filed no row and did not even parse."""
        self._cycle(1000); self._cycle(1001)
        self.assertEqual((self.parses, self._kinds()), (1, ["pending-ops.held-working"]))
        self.assertIsNone(km._cancel_parked(SID, 0, "typed while the count was stale"), "the chip cancels")
        self.assertNotIn(SID, km._pending_ops)
        self.assertNotIn(SID, getattr(km, "_held_working", {}), "the belt's state goes with the queue")
        km._pending_ops[SID] = [("send", "typed again")]        # the user types again into the same stuck session
        self._cycle(1002); self._cycle(1003)
        self.assertEqual((self.parses, self._kinds()), (2, ["pending-ops.held-working", "pending-ops.held-working"]),
                         "the new hold is read and said again")

    def test_the_pushers_cycle_does_no_parse_the_jobs_pass_does(self):
        """Promoted in round two: the belt had put a transcript parse back inside the pusher's cycle (emptied of per-cycle
        transcript work on 2026-09-05, serving every client, no watchdog): a held session whose turn is open paid a parse at
        every tool boundary that rested one cycle. The drain records the hold; the jobs pass reads."""
        threads = []
        def parse(path, sid, now):
            threads.append(threading.current_thread().name); return {"turns": list(self.turns)}
        km._parse = parse
        def on(name, fn):
            out = []
            t = threading.Thread(target=lambda: out.append(fn()), name=name); t.start(); t.join(5)
            return out
        for t in (1000, 1001, 1002, 1003):
            on("pusher", lambda t=t: km._apply_pending_ops(t))
        self.assertEqual(threads, [], "the pusher's cycles parsed nothing across a held sid at rest")
        self.assertIn(SID, getattr(km, "_held_working", {}), "and recorded the hold")
        jobs = getattr(km, "_held_working_pass", None)
        self.assertIsNotNone(jobs, "the jobs pass carries the belt")
        on("jobs", lambda: jobs(1004)); on("jobs", lambda: jobs(1005))
        self.assertEqual(threads, ["jobs"], "the jobs pass read the transcript once, at rest")
        self.assertEqual(self._kinds(), ["pending-ops.held-working"])
        self.assertNotIn("_parse(", inspect.getsource(km._apply_pending_ops) + inspect.getsource(km._mark_held_working),
                         "no parse on the drain's road, by source")
        self.assertIn("_job_stage('heldWorking', lambda: _held_working_pass(now))", inspect.getsource(km._jobs_pass),
                      "the belt is a job of the jobs pass, after the others")

    def test_a_hold_that_lifts_during_the_parse_files_nothing_and_leaves_no_orphan(self):
        """Round three of the review: the pass read the count at the top of a sid, parsed with no lock for tens of
        milliseconds, and filed with no re-check, so a hold that lifted mid-parse (the turn settling and the drain delivering
        and popping both dicts, or the user cancelling the chip) still got a row saying '0 parked items wait', never retracted
        (the retraction arm reads an entry that no longer exists), with a said mark on an orphaned entry. The decision and the
        write now run under the queue lock against the live queue and the live entry."""
        for lift in ("delivered", "cancelled"):
            km._pending_ops.clear(); getattr(km, "_held_working", {}).clear(); self.parses = 0
            km._pending_ops[SID] = [("send", "typed while the count was stale")]
            def parse(path, sid, now, lift=lift):
                self.parses += 1
                if lift == "delivered":                              # the other thread: the turn settled, the drain delivered and popped
                    km._pending_ops.pop(SID, None); getattr(km, "_held_working", {}).pop(SID, None)
                else:                                                # the other thread: the user cancelled the chip
                    km._cancel_parked(SID, 0, "typed while the count was stale")
                return {"turns": list(self.turns)}
            km._parse = parse
            self._cycle(1000); self._cycle(1001)                     # the second pass parses; the hold lifts inside the parse
            self.assertEqual(self.parses, 1, lift)
            self.assertEqual(self._kinds(), [], "%s: a hold that lifted mid-parse files no row" % lift)
            self.assertEqual(dict(getattr(km, "_held_working", {})), {}, "%s: and leaves no orphaned entry" % lift)
            self.assertNotIn(SID, km._pending_ops)


if __name__ == "__main__":
    unittest.main()
