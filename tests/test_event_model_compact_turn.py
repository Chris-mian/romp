#!/usr/bin/env python3
"""A compact_boundary opens its OWN turn (the user 2026-07-13). As a non-opener it used to absorb into
the previous turn, whose end = max(atom ends) then stretched to the boundary's timestamp — so the
timeline drew a phantom work bar spanning the whole idle gap "leading up to the moment of compaction",
growing live while the compact ran. Now the boundary anchors a fresh turn: the prior turn's bar ends at
its real last activity, the post-compact continuation files under the boundary turn (its bar starts AT
the compaction), and a boundary-only tail reads ended (a completed event, not in-flight work) so it can
never fake an open bar / WORKING. Synthetic transcript only — placeholder UUIDs, no real data."""
import datetime
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model_compact", os.path.join(BIN, "romp-event-model")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _iso(ep):
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _turns(recs):
    td = tempfile.mkdtemp()
    p = os.path.join(td, SID + ".jsonl")
    open(p, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
    sess = em.parse_session(p, rompuuid=SID, name="impl", dir="/TESTDIR",
                            candidate_files=[p], states=None, postal_log=[], now=int(time.time()))
    return sess["turns"]


def _recs(now, with_continuation):
    t_old, t_done = now - 3600, now - 60
    recs = [
        {"type": "user", "timestamp": _iso(t_old), "uuid": "u1", "parentUuid": None,
         "message": {"role": "user", "content": "please do the thing"}},
        {"type": "assistant", "timestamp": _iso(t_old + 30), "uuid": "a1", "parentUuid": "u1",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "done."}],
                     "stop_reason": "end_turn"}},
        {"type": "system", "subtype": "compact_boundary", "timestamp": _iso(t_done), "uuid": "cb1",
         "parentUuid": None, "logicalParentUuid": "a1",
         "compactMetadata": {"trigger": "manual", "preTokens": 100000}},
        {"type": "user", "timestamp": _iso(t_done), "uuid": "cs1", "parentUuid": "cb1",
         "isCompactSummary": True,
         "message": {"role": "user", "content": "This session is being continued from a previous one..."}},
    ]
    if with_continuation:
        recs.append({"type": "assistant", "timestamp": _iso(t_done + 20), "uuid": "a2", "parentUuid": "cs1",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "resuming"}],
                                 "stop_reason": "end_turn"}})
    return recs


class CompactBoundaryTurn(unittest.TestCase):
    def test_boundary_never_stretches_the_previous_turn(self):
        now = int(time.time())
        turns = _turns(_recs(now, with_continuation=True))
        self.assertEqual(len(turns), 2, "the compaction is its own turn, not an absorbed tail")
        old, comp = turns
        self.assertEqual(old["end"], now - 3600 + 30,
                         "the prior turn's bar ends at its real last activity — an hour-long phantom "
                         "work period 'leading up to the compaction' was the bug")
        self.assertTrue(old["ended"])
        self.assertEqual(comp["t"], now - 60, "the compaction turn starts AT the boundary, never before")
        self.assertIn("cb1", [a.get("uuid") for a in comp["atoms"]])

    def test_continuation_work_files_under_the_boundary_turn(self):
        now = int(time.time())
        comp = _turns(_recs(now, with_continuation=True))[1]
        self.assertIn("a2", [a.get("uuid") for a in comp["atoms"]],
                      "the CLI's post-compact continuation rides the compaction turn")
        self.assertTrue(comp["ended"], "the continuation's end_turn settles it")

    def test_a_boundary_only_tail_is_self_contained(self):
        # mid-compaction parse: the boundary landed, the continuation hasn't — the turn must not read
        # open (a phantom growing bar / WORKING on an idle session)
        now = int(time.time())
        comp = _turns(_recs(now, with_continuation=False))[-1]
        self.assertTrue(comp["ended"], "a boundary with no assistant work yet is a completed event")
        self.assertEqual(comp["end"], comp["t"], "zero span — the marker, not a bar")


if __name__ == "__main__":
    unittest.main()
