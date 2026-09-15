#!/usr/bin/env python3
"""The chat "no history, no scroll" bug: a documented leaf whose FLOORED list begins with a durable note (a retry
recovery, a gaveup, an orphan reply, an effort change, a command gesture, flushed into the idle gap before the cut
turn) has a synthesized uuid no turn carries, so _turn_index_of_events gives that first event turn index -1. The
tail-run's first turn (tailLo) was `max(0, tix[head_from])`, which clamped -1 to 0: the page then derived one run
from turn 0, no head gap, headKnown true, and never asked for the history above the floor: the reported symptom.

Executed on the real functions (no document, no browser): a synthetic floored list led by an orphan note, over a
parse whose turns do not carry that note's uuid. `_tail_lo` must report the first PLACED turn, never 0. The two
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
            got = km._tail_lo(SID, evs, 0, 1700000000)
            self.assertEqual(got, 3, "tailLo is the first PLACED turn (3), not 0: a leading note must not read as the head")
            self.assertNotEqual(got, 0, "the bug reported 0 (max(0, -1)), collapsing the head gap")
        finally:
            km._sessions, km._parse = saved

    def test_tail_lo_none_when_the_whole_floored_list_is_unplaced(self):
        turns = [_turn(0)]
        evs = [{"uuid": "orphan:1700000000:0"}, {"uuid": "retried:1700000001:0"}]   # no placed event at all
        saved = (km._sessions, km._parse)
        km._sessions = lambda now=None, **kw: [{"sid": SID, "name": "web", "path": "/tmp/x.jsonl", "mtime": 0, "anchor": SID}]
        km._parse = lambda path, sid, now: {"turns": turns}
        try:
            self.assertIsNone(km._tail_lo(SID, evs, 0, 1700000000), "None when the parse cannot place the head (the page asks by the tail's first key)")
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
