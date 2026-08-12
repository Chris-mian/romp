#!/usr/bin/env python3
"""The judging band is built from the per-call LOG as RUN SPANS (the user 2026-06-19, g70): each judge
call plotted at its real wall-clock [sent, recv], glossed from the nearest artifact mark — so a judge that
RAN shows up WHEN it ran (distiller lag, coordinating-courier classifications) instead of back-placed onto
the work it summarizes. Self-contained: drives _run_judging with a synthetic judge-usage.jsonl.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_rs", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

SID = "11111111-2222-3333-4444-555555555555"


class RunJudging(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        jd._active.clear()                               # the in-flight registry is module-level — reset it
        self.td.cleanup()

    def _usage(self, rows):
        with open(jd.STATE / "judge-usage.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_one_span_per_call_at_sent_recv_with_borrowed_gloss(self):
        # a distiller that RAN at [195,205] on a goal that completed back at t=100 — the span is the RUN
        # interval, not the back-placed completion; the text is borrowed from the artifact mark
        self._usage([{"judge": "distiller", "fsid": SID, "t": 205, "sent": 195, "recv": 205,
                      "ms": 10000, "in": 50, "out": 20}])
        semantic = [{"judge": "distiller", "sid": SID, "t": 100, "kind": "distill", "text": "the key takeaway"}]
        marks = km._run_judging(0, {SID}, semantic)
        self.assertEqual(len(marks), 1)
        m = marks[0]
        self.assertEqual((m["t"], m["t1"]), (195, 205), "the mark is the real [sent, recv] RUN span")
        self.assertEqual(m["text"], "the key takeaway", "gloss borrowed from the nearest artifact mark")
        self.assertEqual(m["kind"], "distill")
        self.assertEqual((m["sent"], m["recv"], m["ms"]), (195, 205, 10000))

    def test_a_coordinating_courier_call_shows_even_with_no_artifact_mark(self):
        # a courier classification of a COORDINATING message plants no node → no artifact mark, but its RUN
        # must still surface (this is exactly what the old artifact-derived band missed)
        self._usage([{"judge": "courier", "fsid": SID, "t": 301, "sent": 299, "recv": 301}])
        marks = km._run_judging(0, {SID}, [])
        self.assertEqual(len(marks), 1, "the courier run is visible even though no goal was planted")
        self.assertEqual(marks[0]["text"], "", "no artifact → empty gloss, but the run shows")
        self.assertEqual((marks[0]["t"], marks[0]["t1"]), (299, 301))

    def test_drops_dead_sessions_and_calls_before_the_window(self):
        self._usage([
            {"judge": "planner", "fsid": SID, "t": 51, "sent": 49, "recv": 51},      # alive + in window
            {"judge": "planner", "fsid": "deadbeef", "t": 51, "sent": 49, "recv": 51},  # dead session → dropped
            {"judge": "planner", "fsid": SID, "t": 6, "sent": 4, "recv": 6},         # recv < t0 → dropped
        ])
        marks = km._run_judging(10, {SID}, [])
        self.assertEqual(len(marks), 1, "only the alive, in-window call")
        self.assertEqual(marks[0]["sent"], 49)

    def test_missing_sent_recv_falls_back_to_a_point_at_t(self):
        # a pre-recording row (no sent/recv) → a point at the logged time, never dropped
        self._usage([{"judge": "captioner", "fsid": SID, "t": 100, "ms": 800}])
        marks = km._run_judging(0, {SID}, [])
        self.assertEqual(len(marks), 1)
        self.assertEqual((marks[0]["t"], marks[0]["t1"]), (100, 100), "no span → a point at t")

    def test_an_in_flight_run_shows_as_an_open_span_growing_to_now(self):
        # a judge call STILL running has no usage line yet — it must surface NOW as an open span (open:True,
        # recv:None, t1≈now) so the bar appears WHEN it starts, not back-dated once it ends (the user 2026-06-23)
        self._usage([])
        rid = jd._active_begin("grouper", SID, 500)
        try:
            marks = km._run_judging(0, {SID}, [])
        finally:
            jd._active_end(rid)
        self.assertEqual(len(marks), 1, "the in-flight run is drawn live")
        m = marks[0]
        self.assertEqual((m["judge"], m["t"], m["open"], m["recv"]), ("grouper", 500, True, None))
        self.assertGreaterEqual(m["t1"], 500, "the open span grows to now (t1 >= sent)")

    def test_a_completed_run_is_not_also_double_drawn_as_open(self):
        # the brief log-then-deregister window: the SAME run is both in the usage log AND still registered.
        # Dedup by (sid, judge, sent) → it draws ONCE (the completed span), never two overlapping bars.
        self._usage([{"judge": "closer", "fsid": SID, "t": 610, "sent": 600, "recv": 610}])
        rid = jd._active_begin("closer", SID, 600)       # same (sid, judge, sent) as the completed line
        try:
            marks = km._run_judging(0, {SID}, [])
        finally:
            jd._active_end(rid)
        self.assertEqual(len(marks), 1, "deduped — the completed span only, not a second open one")
        self.assertEqual((marks[0]["t"], marks[0]["recv"]), (600, 610), "the completed span wins")

    def test_an_in_flight_run_for_a_dead_session_is_dropped(self):
        self._usage([])
        rid = jd._active_begin("planner", "deadbeef", 500)
        try:
            marks = km._run_judging(0, {SID}, [])
        finally:
            jd._active_end(rid)
        self.assertEqual(marks, [], "an in-flight run on a non-alive session is not drawn")


class PureDelegationTop(unittest.TestCase):
    """A top-level node whose whole subtree is just courier handoff-tracking (work delegated to peers) is pure
    coordination — _pure_delegation_top flags it so the feed never shows it as an inbox card (the user
    2026-06-23). A top with any own-work leaf still shows."""

    def test_childless_handoff_top_is_pure(self):     # the g53 case: '↪ delegated to <peer>' with no own work
        nodes = {"t": {"id": "t", "parentId": None, "handoff": {"peer": "p", "msgId": "m"}}}
        self.assertTrue(km._pure_delegation_top(nodes, "t"))

    def test_umbrella_of_only_handoffs_is_pure(self):
        nodes = {"t": {"id": "t", "parentId": None},                 # umbrella carries no handoff itself
                 "a": {"id": "a", "parentId": "t", "handoff": {"peer": "p", "msgId": "1"}},
                 "b": {"id": "b", "parentId": "t", "handoff": {"peer": "q", "msgId": "2"}}}
        self.assertTrue(km._pure_delegation_top(nodes, "t"))

    def test_top_with_an_own_work_leaf_is_not_pure(self):
        nodes = {"t": {"id": "t", "parentId": None},
                 "h": {"id": "h", "parentId": "t", "handoff": {"peer": "p", "msgId": "m"}},
                 "w": {"id": "w", "parentId": "t"}}                  # own-work leaf, no handoff → still a card
        self.assertFalse(km._pure_delegation_top(nodes, "t"))

    def test_plain_top_is_not_pure(self):
        self.assertFalse(km._pure_delegation_top({"t": {"id": "t", "parentId": None}}, "t"))


if __name__ == "__main__":
    unittest.main()
