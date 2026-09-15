#!/usr/bin/env python3
"""The chat "no history, no scroll" bug: a documented leaf whose FLOORED list begins with a durable note (a retry
recovery, a gaveup, an orphan reply, an effort change, a command gesture, flushed into the idle gap before the cut
turn) has a synthesized uuid no turn carries, so _turn_index_of_events gives that first event turn index -1. The
tail-run's first turn (tailLo) was `max(0, tix[head_from])`, which clamped -1 to 0: the page then derived one run
from turn 0, no head gap, headKnown true, and never asked for the history above the floor: the reported symptom.

Executed on the real functions (no document, no browser): a synthetic floored list led by an orphan note, over a
parse whose turns do not carry that note's uuid. `_tail_run_start`, the frame's one reader of the tail run's first turn since
the snap of 2026-09-15 (it replaced `_tail_lo`), must report the first PLACED turn, never 0. The two
sibling clamps (`_turn_of_key` and the loadOlder span, same file) are pinned to the shared `_first_mapped_turn`.
SYNTHETIC fixtures only (placeholder uuids)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from romp_load import load_source  # noqa: E402

# make the state root hermetic BEFORE loading romp code (test_state_isolation_order.py): the loader resolves
# STATE from ROMP_STATE_DIR || XDG_STATE_HOME/romp at import time, so a direct run must not touch the real one
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
_ST = Path(os.environ["XDG_STATE_HOME"]) / "romp"
_ST.mkdir(parents=True, exist_ok=True)
(_ST / "session-hosts").write_text("off\n")  # this module mints its own state root: hosts off (CLAUDE.md)

km = load_source("romp_kernel_tail_lo", os.path.join(os.path.dirname(HERE), "bin", "romp-kernel"))

SID = "11111111-2222-3333-4444-555555555555"


def _turn(i):
    return {"atoms": [{"uuid": "u%d" % i, "t": 1000 + i}, {"uuid": "a%d" % i, "t": 1000 + i}]}


class TailLoLeadingNote(unittest.TestCase):
    def test_first_mapped_turn_skips_a_leading_unplaced_event(self):
        f = km._first_mapped_turn
        self.assertEqual(f([-1, 3, 3, 4], 0), 3, "the first placed turn after a leading note")
        self.assertEqual(f([2, 3], 0), 2, "a placed first event is itself")
        self.assertEqual(f([-1, -1], 0), None, "all unplaced: None, so the caller can say the parse cannot tell")
        self.assertEqual(f([5, 6, 7], 1), 6, "honours the start index")

    def test_tail_lo_reports_the_first_placed_turn_not_zero_for_a_leading_note(self):
        turns = [_turn(i) for i in range(6)]                     # a parse of six turns
        # the floored list begins at turn 3, but a DURABLE NOTE (an orphan reply) was flushed just ahead of it:
        # its synthesized uuid is in no turn, so _turn_index_of_events gives it -1
        evs = [{"uuid": "orphan:1700000000:0", "kind": "note"}]
        for i in (3, 4, 5):
            evs += [{"uuid": "u%d" % i}, {"uuid": "a%d" % i}]
        saved = (km._sessions, km._parse)
        km._sessions = lambda now=None, **kw: [{"sid": SID, "name": "web", "path": "/tmp/x.jsonl", "mtime": 0, "anchor": SID}]
        km._parse = lambda path, sid, now: {"turns": turns}
        try:
            tix = km._turn_index_of_events(evs, turns)
            self.assertEqual(tix[0], -1, "the leading note is unplaced (tix -1): %r" % tix)
            self.assertEqual(tix[1], 3, "the first real event is turn 3: %r" % tix)
            start, got = km._tail_run_start(SID, evs, 0, 1700000000)
            self.assertEqual(got, 3, "tailLo is the first PLACED turn (3), not 0: a leading note must not read as the head")
            self.assertNotEqual(got, 0, "the bug reported 0 (max(0, -1)), collapsing the head gap")
            self.assertEqual(start, 0, "the run keeps the leading note at its head: a cut on an unplaced event stays")
        finally:
            km._sessions, km._parse = saved

    def _stubbed(self, turns, tix_override=None):
        """The regions wire over a synthetic list: discovery, the parse and (optionally) the turn index stubbed."""
        saved = (km._sessions, km._parse, km._turn_index_of_events, km.WIRE_TAIL, km.build_session)
        km._sessions = lambda now=None, **kw: [{"sid": SID, "name": "web", "path": "/tmp/x.jsonl", "mtime": 0, "anchor": SID}]
        km._parse = lambda path, sid, now: {"turns": turns}
        if tix_override is not None:
            km._turn_index_of_events = lambda evs, turns: list(tix_override)
        return saved

    def _restore(self, saved):
        km._sessions, km._parse, km._turn_index_of_events, km.WIRE_TAIL, km.build_session = saved

    def _partition(self, evs, cut):
        """The REAL frame builder (a proto-2 client's full frame, the wire tail lowered to put the cut at `cut`) and the REAL gap
        reply (loadTurns for [0, tailLo)): the page's events plus the frame's, in order, against the whole list."""
        km.WIRE_TAIL = len(evs) - cut
        m = {"type": "session", "id": SID, "events": evs, "status": {}, "floor": 0}
        km.build_session = lambda sid, now, live_map=None, **kw: m
        sent = []
        c = {"send": lambda s: sent.append(__import__("json").loads(s)), "sent": {}, "proto": 2, "echat": {}}
        km._send_chat_locked(c, m, None, 0, False)
        frame = sent[-1]
        reply = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": 0, "hi": frame["tailLo"]}, 1700000000, base=c["echat"][SID])
        return frame, reply

    def test_the_run_edge_is_one_function_for_the_frame_and_the_gap_page(self):
        """The rule stated on _turn_run_edge: the run of turn t begins at the first index whose turn index reaches t, and the gap
        page for [lo, t) ends exactly there. Contiguous shapes (every real build's) and the review's non-monotone stub, driven
        through the real frame builder and the real gap reply: the page's events plus the frame's are the whole list, once."""
        turns = [_turn(i) for i in range(6)]
        turns[5]["atoms"] = [{"uuid": "x5"}, {"uuid": "y5"}, {"uuid": "z5"}]
        # the ordinary shape: a contiguous last turn, the cut inside it, the run from the turn's first event
        evs = [{"uuid": "u0", "kind": "user"}, {"uuid": "a0", "kind": "assistant"}, {"uuid": "u1", "kind": "user"}, {"uuid": "a1", "kind": "assistant"},
               {"uuid": "x5", "kind": "user"}, {"uuid": "y5", "kind": "assistant"}, {"uuid": "z5", "kind": "assistant"}]
        saved = self._stubbed(turns)
        try:
            self.assertEqual(km._turn_index_of_events(evs, turns), [0, 0, 1, 1, 5, 5, 5])
            self.assertEqual(km._turn_run_edge([0, 0, 1, 1, 5, 5, 5], 5), 4)
            self.assertEqual(km._tail_run_start(SID, evs, 6, 1700000000), (4, 5), "the whole contiguous turn, from its first event")
            self.assertEqual(km._tail_run_start(SID, evs, 2, 1700000000), (2, 1), "a cut already at a turn's first event stays")
            frame, reply = self._partition(evs, 6)
            self.assertEqual((frame["tailLo"], [e["uuid"] for e in frame["events"]]), (5, ["x5", "y5", "z5"]))
            self.assertEqual([e["uuid"] for e in reply["events"]] + [e["uuid"] for e in frame["events"]], [e["uuid"] for e in evs], "the gap page and the run partition the list")
        finally:
            self._restore(saved)
        # the review's non-monotone index ([0, 5, 1, 1, 2, 2, 5, 5], cut 6): no builder produces it today; the rule keeps the partition
        saved = self._stubbed(turns, tix_override=[0, 5, 1, 1, 2, 2, 5, 5])
        try:
            self.assertEqual(km._turn_run_edge([0, 5, 1, 1, 2, 2, 5, 5], 5), 1, "the first index that reaches turn 5")
            evs2 = [{"uuid": u} for u in ("u0", "x5", "u1", "a1", "u2", "a2", "y5", "z5")]
            self.assertEqual(km._tail_run_start(SID, evs2, 6, 1700000000), (1, 5), "the frame's run begins at the edge, the page before it ends there")
        finally:
            self._restore(saved)

    def test_the_gap_page_and_the_frame_partition_the_list_on_a_non_monotone_index(self):
        """The medium of the 2026-09-16 read, through the REAL frame builder and the REAL gap reply alone (no new name touched, so an
        older kernel reaches the assertion): on the review's stub ([0, 5, 1, 1, 2, 2, 5, 5], cut 6) the gap page for [0, tailLo)
        plus the frame's resident events are the whole list, once. The backward walk left events 1 to 5 in neither."""
        turns = [_turn(i) for i in range(6)]
        turns[5]["atoms"] = [{"uuid": "x5"}, {"uuid": "y5"}, {"uuid": "z5"}]
        evs2 = [{"uuid": "u0", "kind": "user"}, {"uuid": "x5", "kind": "user"}, {"uuid": "u1", "kind": "user"}, {"uuid": "a1", "kind": "assistant"},
                {"uuid": "u2", "kind": "user"}, {"uuid": "a2", "kind": "assistant"}, {"uuid": "y5", "kind": "assistant"}, {"uuid": "z5", "kind": "assistant"}]
        saved = self._stubbed(turns, tix_override=[0, 5, 1, 1, 2, 2, 5, 5])
        try:
            frame, reply = self._partition(evs2, 6)
            self.assertEqual(frame["tailLo"], 5)
            self.assertEqual([e["uuid"] for e in reply["events"]] + [e["uuid"] for e in frame["events"]], [e["uuid"] for e in evs2],
                             "pages plus resident are the whole list, once: nothing in neither region, nothing in both")
        finally:
            self._restore(saved)

    def test_a_cut_on_an_unplaced_event_inside_a_turn_resolves_to_the_turns_edge(self):
        """tix [3, 3, -1, 3, 3], cut 2 (on the note): the run begins at the turn's edge, 0; the head of the turn is never stranded.
        No builder produces a -1 inside a turn today (the index carries the previous placed turn forward); the rule holds anyway."""
        turns = [_turn(i) for i in range(4)]
        evs = [{"uuid": "u3", "kind": "user"}, {"uuid": "a3", "kind": "assistant"}, {"uuid": "orphan:1700000000:0", "kind": "note"}, {"uuid": "x3", "kind": "user"}, {"uuid": "y3", "kind": "assistant"}]
        saved = self._stubbed(turns, tix_override=[3, 3, -1, 3, 3])
        try:
            self.assertEqual(km._tail_run_start(SID, evs, 2, 1700000000), (0, 3))
            frame, reply = self._partition(evs, 2)
            self.assertEqual([e["uuid"] for e in frame["events"]], [e["uuid"] for e in evs], "the whole turn is the run")
            self.assertEqual(reply["events"], [], "nothing before it")
        finally:
            self._restore(saved)

    def test_the_index_builder_says_once_when_a_turn_index_decreases(self):
        """The regions' run labels assume a nondecreasing index; _turn_index_of_events says so on stderr ONCE if a build ever
        produces a decrease (the partition holds regardless, by _turn_run_edge)."""
        import io, sys as _sys
        turns = [_turn(i) for i in range(6)]
        turns[5]["atoms"] = [{"uuid": "x5"}, {"uuid": "y5"}]
        evs = [{"uuid": "u0"}, {"uuid": "x5"}, {"uuid": "u1"}, {"uuid": "y5"}]   # turn 5's event early: the index reads 0, 5, 1, 5
        km._tix_decrease_said[0] = False
        err = io.StringIO(); saved = _sys.stderr; _sys.stderr = err
        try:
            self.assertEqual(km._turn_index_of_events(evs, turns), [0, 5, 1, 5])
            self.assertEqual(km._turn_index_of_events(evs, turns), [0, 5, 1, 5])
        finally:
            _sys.stderr = saved
            km._tix_decrease_said[0] = False
        lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, "said once, however many builds: %r" % lines)
        self.assertIn("chat regions: the built list's turn index decreased (1 after 5 at event 2)", lines[0])

    def test_tail_lo_none_when_the_whole_floored_list_is_unplaced(self):
        turns = [_turn(0)]
        evs = [{"uuid": "orphan:1700000000:0"}, {"uuid": "retried:1700000001:0"}]   # no placed event at all
        saved = (km._sessions, km._parse)
        km._sessions = lambda now=None, **kw: [{"sid": SID, "name": "web", "path": "/tmp/x.jsonl", "mtime": 0, "anchor": SID}]
        km._parse = lambda path, sid, now: {"turns": turns}
        try:
            self.assertEqual(km._tail_run_start(SID, evs, 0, 1700000000), (0, None), "the plain cut and None when the parse cannot place the head (the page asks by the tail's first key)")
        finally:
            km._sessions, km._parse = saved

    def _reply(self, msg):
        # drive the real _chat_history_reply over a floored list led by an orphan note: turns 0..5 in the parse,
        # the floored list starts at turn 3 (floor 3) but a durable note is flushed ahead of it (tix[0] = -1)
        turns = [_turn(i) for i in range(6)]
        evs = [{"uuid": "orphan:1700000000:0", "kind": "note"}]
        for i in (3, 4, 5):
            evs += [{"uuid": "u%d" % i}, {"uuid": "a%d" % i}]
        saved = (km._live_map, km._sessions, km.build_session, km._parse)
        km._live_map = lambda: {}
        km._sessions = lambda now=None, **kw: [{"sid": SID, "name": "web", "path": "/tmp/x.jsonl", "mtime": 0, "anchor": SID}]
        km.build_session = lambda sid, now, live_map, floor=None, **kw: {"events": evs, "floor": 3, "headCards": []}
        km._parse = lambda path, sid, now: {"turns": turns}
        try:
            anchor = km._event_key(evs[3])                    # u4, in the floored list
            return km._chat_history_reply(SID, dict(msg, **({"before": anchor} if msg["type"] == "loadOlder" else {"uuid": anchor})), 1700000000, None)
        finally:
            km._live_map, km._sessions, km.build_session, km._parse = saved

    def test_the_history_reply_head_edges_report_the_first_placed_turn(self):
        # the two sibling clamps (_turn_of_key, the loadOlder span) and the loadAround window span, executed through
        # the real _chat_history_reply: a leading note must never make the head edge read as turn 0
        older = self._reply({"type": "loadOlder"})
        self.assertEqual(older.get("type"), "chatHead", "loadOlder answers a chatHead: %r" % older)
        self.assertEqual(older["span"][0], 3, "loadOlder's head-edge span is the first placed turn (3), not 0 (the bug): %r" % older["span"])
        around = self._reply({"type": "loadAround"})
        self.assertEqual(around.get("type"), "chatWindow", "loadAround answers a chatWindow: %r" % around)
        self.assertEqual(around["span"][0], 3, "loadAround's window head-edge span is the first placed turn (3), not 0 (the bug): %r" % around["span"])


if __name__ == "__main__":
    unittest.main()
