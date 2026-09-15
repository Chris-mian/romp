#!/usr/bin/env python3
"""The chat "no history, no scroll" bug: a documented leaf whose FLOORED list begins with a durable note (a retry
recovery, a gaveup, an orphan reply, an effort change, a command gesture, flushed into the idle gap before the cut
turn) has a synthesized uuid no turn carries, so _turn_index_of_events gives that first event turn index -1. The
tail-run's first turn (tailLo) was `max(0, tix[head_from])`, which clamped -1 to 0: the page then derived one run
from turn 0, no head gap, headKnown true, and never asked for the history above the floor — the reported symptom.

Executed on the real functions (no document, no browser): a synthetic floored list led by an orphan note, over a
parse whose turns do not carry that note's uuid. `_tail_lo` must report the first PLACED turn, never 0. The two
sibling clamps (`_turn_of_key` and the loadOlder span, same file) are pinned to the shared `_first_mapped_turn`.
SYNTHETIC fixtures only (placeholder uuids)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from romp_load import load_source  # noqa: E402

km = load_source("romp_kernel_tail_lo", os.path.join(os.path.dirname(HERE), "bin", "romp-kernel"))

SID = "11111111-2222-3333-4444-555555555555"
KERNEL_SRC = Path(os.path.dirname(HERE), "kernel", "kernel.py").read_text()


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

    def test_the_sibling_head_clamps_use_the_shared_helper(self):
        # the same max(0, tix[...]) head clamp sat in _turn_of_key and the loadOlder reply's span; both now route
        # a leading-note index through _first_mapped_turn rather than clamping it to turn 0
        self.assertIn("fm = _first_mapped_turn(tix, p)", KERNEL_SRC, "_turn_of_key routes a note key through the helper")
        self.assertIn("_span_lo = _first_mapped_turn(tix, frm)", KERNEL_SRC, "the loadOlder span's head edge uses the helper")
        self.assertNotIn("return max(0, tix[head_from])", KERNEL_SRC, "_tail_lo no longer clamps a leading note to 0")
        self.assertNotIn("[max(0, tix[frm]), max(0, tix[p - 1]) + 1]", KERNEL_SRC, "the loadOlder span no longer clamps its head edge to 0")


if __name__ == "__main__":
    unittest.main()
