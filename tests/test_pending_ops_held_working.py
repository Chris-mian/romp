#!/usr/bin/env python3
"""The parked-ops drain says when it holds a queue on the backend's word alone (2026-09-18). _apply_pending_ops skips a sid
while _working_now reads true, and _working_now prefers the backend's live signal (an open-turn count or a pending queue) to
the transcript. When that signal is stale (a host's count a folded turn left high, adopted at every attach), the session
reads Ready on the page and Working to the drain, and every input sits parked with no line anywhere: on the user's laptop
three inputs waited two days. The source is fixed in the host and the hello; this pins the belt: the first such cycle
writes one stderr line and one session-events row (kind pending-ops.held-working, the parked count), later cycles say
nothing more, and once the hold lifts the queue delivers and a new hold is said again. A hold the transcript agrees with (an
open turn) says nothing. SYNTHETIC fixtures only: a placeholder uuid, invented texts."""
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
km = load_source("romp_kernel_heldworking", os.path.join(BIN, "romp-kernel"))
km._limit_hold = lambda sid: None
SID = "11111111-2222-3333-4444-565656565656"
_OTHER_JOBS = ("_push_all", "_lift_spent_awaiting", "_death_sweep_tick", "_end_on_idle_sweep", "_deferral_sweep_tick", "_auto_nudge_tick",
               "_interrupt_block_tick", "_auto_pause_on_limit", "_usage_poll_tick", "_auto_pause_on_spend_limit", "_auto_resume_retry",
               "_auto_resume_session_retry", "_auto_retry_tick", "_idle_queue_drive_tick", "_clear_done_working_notes")


class _Backend:
    """busy() answers from a flag the test flips: the stale-count shape is busy True over a transcript with no open turn.
    Every busy() read is counted (the note must add none of its own); pending_queued() is the pending-queue road."""
    def __init__(self):
        self.open = True
        self.calls = []
        self.logs = []
        self.busy_reads = 0
        self.pending = []
    def busy(self, sid):
        self.busy_reads += 1
        return self.open
    def pending_queued(self, sid):
        return list(self.pending)
    def forwards_sends(self):
        return False
    def send(self, sid, text):
        self.calls.append(("send", text)); return True
    def set_model(self, sid, value):
        self.calls.append(("model", value)); return True
    def turn_seq(self, sid):
        return 0
    def _log(self, msg, problem=False, ring_text=None):
        self.logs.append((msg, problem, ring_text))


class HeldOnTheBackendsWord(unittest.TestCase):
    def setUp(self):
        self.be = _Backend()
        self.turns = [{"t": 1, "end": 2, "ended": True, "atoms": [{"type": "user", "t": 1}]}]     # the last turn CLOSED: no open turn
        self.cache_hit = True                                                                   # the cached parse answers (else a miss)
        self.parse_raises = False                                                               # the authoritative parse fails
        self.parses = 0
        self._patches = [
            mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: self.be)),
            mock.patch.object(km, "_compacting_now", lambda sid, **k: False),
            mock.patch.object(km, "_path_of", lambda sid: "/nonexistent/transcript.jsonl"),
            mock.patch.object(km, "_parse_cached", lambda path: self.cached(path)),
            mock.patch.object(km, "_parse", lambda path, sid, now: self.parsed(path, sid, now)),
            mock.patch.object(km, "_name_of", lambda sid: "web"),
            mock.patch.object(km, "_names_snapshot", lambda: {}),
            mock.patch.object(km, "_live_map", lambda: {SID: {"state": "waiting", "backend": "sdk"}}),
        ] + [mock.patch.object(km, name, lambda *a, **k: None) for name in _OTHER_JOBS]
        for p in self._patches:
            p.start()
        with km._pending_ops_lock:
            km._pending_ops.clear()
        getattr(km, "_HELD_WORKING_SAID", set()).clear()
        self.events = km.jd.STATE / "session-events.jsonl"
        try:
            self.events.unlink()
        except OSError:
            pass

    def tearDown(self):
        for p in self._patches:
            p.stop()
        with km._pending_ops_lock:
            km._pending_ops.clear()

    def cached(self, path):
        return {"turns": self.turns} if self.cache_hit else None

    def parsed(self, path, sid, now):
        self.parses += 1
        if self.parse_raises:
            raise OSError("the transcript could not be read")
        return {"turns": self.turns}

    def _rows(self):
        if not self.events.exists():
            return []
        return [json.loads(l) for l in self.events.read_text().splitlines() if l.strip()]

    def _drain(self):
        err = io.StringIO()
        with redirect_stderr(err):
            km._apply_pending_ops(time.time())
        return err.getvalue()

    def test_a_queue_held_by_a_stale_working_signal_is_said_once_and_delivers_when_the_hold_lifts(self):
        km._park_op(SID, ("send", "hello after the restart", "human"))
        km._park_op(SID, ("send", "and a second one", "human"))
        out = self._drain() + self._drain() + self._drain()
        self.assertEqual(out.count("pending-ops: web: 2 parked input(s) held because the backend counts an open turn while its transcript shows none"), 1,
                         "one line for the hold, not one per cycle (the base said nothing at all): %r" % out)
        rows = [r for r in self._rows() if r.get("kind") == "pending-ops.held-working"]
        self.assertEqual(len(rows), 1, "one session-events row for the hold: %r" % self._rows())
        self.assertEqual((rows[0].get("sid"), rows[0].get("parked"), rows[0].get("transcript")), (SID, 2, "no open turn"))
        self.assertEqual([p for _, p, _ in self.be.logs].count(True), 1, "the row rings the error center once (a decision-shaped fault)")
        self.assertEqual(self.be.busy_reads, 3, "three cycles, three busy() reads: the gate's one per cycle, none of the note's own")
        self.assertEqual(self.be.calls, [], "the hold still holds: nothing delivered on the backend's word")
        self.be.open = False                                                      # the hold lifts (the count settled)
        self._drain()
        self.assertEqual([c[0] for c in self.be.calls], ["send"], "the parked sends deliver (one coalesced run) once the session reads quiet")
        self.assertIn("hello after the restart", self.be.calls[0][1]); self.assertIn("and a second one", self.be.calls[0][1])
        self.be.open = True
        km._park_op(SID, ("send", "again", "human"))
        out2 = self._drain()
        self.assertEqual(out2.count("pending-ops: web:"), 1, "a new hold is said again after a lift")

    def test_a_cache_miss_is_read_authoritatively_and_never_reads_as_no_open_turn(self):
        """Round two of 1838: _parse_cached never parses and misses on every actively written transcript (and always with
        no client refreshing it), so a miss read as 'no open turn' blamed a real turn. On a miss the note parses the
        transcript itself; when that parse says the turn is open, nothing is said; when it cannot read, the hold is said
        as unverified, never as idle."""
        self.cache_hit = False
        self.turns = [{"t": 1, "atoms": [{"type": "user", "t": 1}]}]              # OPEN on the authoritative read
        km._park_op(SID, ("send", "typed mid-turn", "human"))
        out = self._drain() + self._drain()
        self.assertEqual(self.parses, 2, "the miss is answered by the kernel's own parse, once per cycle")
        self.assertNotIn("pending-ops:", out, "a real turn behind a cache miss says nothing (the earlier head blamed it)")
        self.assertEqual([r for r in self._rows() if r.get("kind") == "pending-ops.held-working"], [])
        self.parse_raises = True                                                  # the transcript cannot be read at all
        out = self._drain()
        self.assertIn("could not be read; the hold is unverified", out, "an unreadable transcript is said as unknown")
        rows = [r for r in self._rows() if r.get("kind") == "pending-ops.held-working"]
        self.assertEqual([r.get("transcript") for r in rows], ["unknown"])
        self.assertNotIn("shows none", out, "never 'no open turn' from a miss")

    def test_a_pending_queue_on_the_backend_is_a_real_hold_and_says_nothing(self):
        self.be.pending = ["a send queued and about to run"]
        km._park_op(SID, ("model", "opus"))
        out = self._drain() + self._drain()
        self.assertNotIn("pending-ops:", out, "the pending-queue road is a real hold, not a stale count")
        self.assertEqual([r for r in self._rows() if r.get("kind") == "pending-ops.held-working"], [])

    def test_a_hold_the_transcript_agrees_with_says_nothing(self):
        self.turns = [{"t": 1, "atoms": [{"type": "user", "t": 1}]}]              # the last turn OPEN: a real turn
        km._park_op(SID, ("send", "typed mid-turn", "human"))
        out = self._drain() + self._drain()
        self.assertNotIn("pending-ops:", out, "a real turn is a real hold")
        self.assertEqual([r for r in self._rows() if r.get("kind") == "pending-ops.held-working"], [])


if __name__ == "__main__":
    unittest.main()
