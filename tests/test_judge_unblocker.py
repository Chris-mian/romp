#!/usr/bin/env python3
"""The UNBLOCKER (the user 2026-07-11): a sub-goal blocked on a question stays blocked forever unless
work files on that exact node — an answer given in passing files wherever the planner judges it to
serve, so a dormant blocked sub never hears it (nimbus: the card sat in Needs-you for hours on a
buried sub whose mAh/logging question the very next conversation stretch had answered). The pass
re-examines open blocked SUBS against the conversation since their block and lifts via the same
record_verdict("unblock") every other lift uses. Event-gated per node (blockCheckT vs the newest ended
turn), model stubbed. All fixtures SYNTHETIC (invented text, placeholder UUIDs).
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent=None):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": "end_turn"}}


class UnblockerBase(unittest.TestCase):
    def setUp(self):
        self._saved_state = jd.STATE
        self._td = tempfile.mkdtemp()
        jd._rebind_state(Path(self._td))
        jd.GOALDIR.mkdir(parents=True, exist_ok=True)
        jd._PARSE_CACHE.clear()
        self._saved_llm = jd.unblock_llm
        self.calls = []

    def tearDown(self):
        jd.unblock_llm = self._saved_llm
        jd._rebind_state(self._saved_state)
        shutil.rmtree(self._td, ignore_errors=True)

    def _stub(self, reply):
        def fake(blocks_text, since_text):
            self.calls.append((blocks_text, since_text))
            return reply
        jd.unblock_llm = fake

    def _store(self, block_t, top_done=False, block_top_instead=False):
        """top > sub, the sub blocked at block_t on a concrete question. Built as plain dicts BEFORE
        save (protected flags are diary-owned once loaded — GuardedNode). block_top_instead puts the
        block on the TOP (sub stays open); top_done completes the ancestor."""
        top, sub = SID + ":g1", SID + ":g2"
        blk = {"blocked": True, "blockWhy": "what is the pack's mAh rating?",
               "log": [{"ev_t": block_t, "src": "planner", "kind": "block",
                        "why": "what is the pack's mAh rating?", "at": block_t}]}
        opn = {"blocked": False, "log": []}
        store = {"rompUuid": SID, "seq": 2, "lastNode": top, "placements": {}, "status": {},
                 "nodes": {
                     top: dict({"id": top, "text": "enable the autonomous run", "parentId": None,
                                "nodeComplete": top_done, "cleared": False,
                                "trail": [], "t": T0, "mt": T0},
                               **(blk if block_top_instead else opn)),
                     sub: dict({"id": sub, "text": "clarify the worker pool", "parentId": top,
                                "nodeComplete": False, "cleared": False,
                                "trail": [], "t": T0, "mt": block_t},
                               **(opn if block_top_instead else blk)),
                 }}
        jd.save_goals(SID, store)
        return top, sub

    def _transcript(self, turns):
        """Write a transcript of ENDED turns [(t, user_text, reply_text), ...] + return its path."""
        recs, prev = [], None
        for i, (t, ask, reply) in enumerate(turns):
            u, a = "u%d" % i, "a%d" % i
            recs.append(uline(t, ask, u, parent=prev))
            recs.append(aline(t + 5, reply, a, parent=u))
            prev = a
        # a final ended turn needs a successor or an idle terminator; a trailing user line ends the last reply turn
        p = Path(self._td) / (SID + ".jsonl")
        p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        return str(p)


class Unblocker(UnblockerBase):
    def test_an_answered_in_passing_block_is_lifted(self):
        top, sub = self._store(block_t=T0 + 100)
        path = self._transcript([(T0 + 50, "set up the load experiment", "planning it"),
                                 (T0 + 200, "it is a 10,000mAh pack, go ahead", "great, proceeding"),
                                 (T0 + 300, "how is it going?", "campaign armed")])
        self._stub('{"verdicts": [{"n": 1, "do": "lift", "why": "the user said 10,000mAh in a later message"}]}')
        lifted = jd._unblock_session(SID, path, NOW)
        self.assertEqual(lifted, [sub])
        store = jd.load_goals(SID)
        self.assertFalse(store["nodes"][sub]["blocked"], "the stale block is lifted")
        self.assertIn("answered in passing", (store["nodes"][sub].get("log") or [])[-1].get("why", ""),
                      "the lift rides the diary with its provenance")
        self.assertIn("what is the pack's mAh rating?", self.calls[0][0], "the block's question is shown")
        self.assertIn("10,000mAh", self.calls[0][1], "the after-conversation is shown")

    def test_a_hold_keeps_the_block_and_the_watermark_prevents_reasking(self):
        top, sub = self._store(block_t=T0 + 100)
        path = self._transcript([(T0 + 200, "unrelated other work", "done that")])
        self._stub('{"verdicts": [{"n": 1, "do": "hold", "why": ""}]}')
        self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        store = jd.load_goals(SID)
        self.assertTrue(store["nodes"][sub]["blocked"], "held: still genuinely waiting")
        self.assertGreater(store["nodes"][sub].get("blockCheckT") or 0, T0 + 100,
                           "the watermark advanced to the examined evidence")
        # same evidence again → no second model call (event-gated)
        self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        self.assertEqual(len(self.calls), 1, "no new ended turn → no re-ask")
        # a NEWER ended turn re-arms the examination
        path2 = self._transcript([(T0 + 200, "unrelated other work", "done that"),
                                  (T0 + 900, "more talk", "more replies"),
                                  (T0 + 950, "tail", "tail reply")])
        jd._PARSE_CACHE.clear()
        jd._unblock_session(SID, path2, NOW)
        self.assertEqual(len(self.calls), 2, "new evidence → examined again")

    def test_a_blocked_top_is_never_examined(self):
        top, sub = self._store(block_t=T0 + 100, block_top_instead=True)
        path = self._transcript([(T0 + 200, "the plan is confirmed", "proceeding")])
        self._stub('{"verdicts": [{"n": 1, "do": "lift", "why": "confirmed"}]}')
        self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        self.assertEqual(self.calls, [], "a blocked TOP is the card's Needs-you — never lifted here")

    def test_a_block_under_a_completed_ancestor_is_skipped_as_moot(self):
        top, sub = self._store(block_t=T0 + 100, top_done=True)
        path = self._transcript([(T0 + 200, "later talk", "later reply")])
        self._stub('{"verdicts": [{"n": 1, "do": "lift", "why": "x"}]}')
        self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        self.assertEqual(self.calls, [], "any_blocked already ignores blocks inside a completed subtree")

    def test_a_parse_failure_holds_and_gives_up_after_the_cap(self):
        top, sub = self._store(block_t=T0 + 100)
        path = self._transcript([(T0 + 200, "the answer is 10,000mAh", "noted")])
        self._stub("not json at all")
        for _ in range(jd.JUDGE_FAIL_CAP):
            self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        store = jd.load_goals(SID)
        self.assertTrue(store["nodes"][sub]["blocked"], "malformed replies never lift anything")
        self.assertGreater(store["nodes"][sub].get("blockCheckT") or 0, 0,
                           "after the give-up cap the watermark advances (a newer turn re-arms)")
        n_before = len(self.calls)
        jd._unblock_session(SID, path, NOW)
        self.assertEqual(len(self.calls), n_before, "given up on this evidence — no more calls")

    def test_an_empty_reply_is_a_failed_call_and_retries_next_pass(self):
        top, sub = self._store(block_t=T0 + 100)
        path = self._transcript([(T0 + 200, "the answer is 10,000mAh", "noted")])
        self._stub("")
        self.assertEqual(jd._unblock_session(SID, path, NOW), [])
        store = jd.load_goals(SID)
        self.assertFalse(store["nodes"][sub].get("blockCheckT"), "no watermark advance on a failed call")

    def test_a_mid_call_store_change_is_never_clobbered_and_the_drift_is_logged(self):
        # The model call takes seconds and save_goals is last-writer-wins: verdicts must apply to a
        # FRESH load, never the pre-call snapshot. Simulate a user acting mid-call: the stub (running
        # where the model call would) rewrites the store — resolves the blocked sub AND adds a new
        # node — then returns a lift. The lift must be SKIPPED (drift-skip row logged), the user's
        # resolution must stand, and the concurrently-added node must survive the pass's save.
        top, sub = self._store(block_t=T0 + 100)
        path = self._transcript([(T0 + 200, "it is a 10,000mAh pack", "noted")])
        other = SID + ":g9"

        def fake(blocks_text, since_text):
            self.calls.append((blocks_text, since_text))
            st = jd.load_goals(SID)
            jd.record_verdict(st, st["nodes"][sub], "user", "done", T0 + 500,
                              why="crossed off by the user mid-call")
            st["nodes"][other] = {"id": other, "text": "typed while the model ran", "parentId": None,
                                  "nodeComplete": False, "blocked": False, "cleared": False,
                                  "trail": [], "t": T0 + 500, "mt": T0 + 500, "log": []}
            jd.save_goals(SID, st)
            return '{"verdicts": [{"n": 1, "do": "lift", "why": "the user said 10,000mAh"}]}'
        jd.unblock_llm = fake

        self.assertEqual(jd._unblock_session(SID, path, NOW), [], "no lift lands on a node that moved on")
        store = jd.load_goals(SID)
        self.assertTrue(store["nodes"][sub].get("nodeComplete"), "the user's mid-call resolution stands")
        self.assertIn(other, store["nodes"], "a node added mid-call survives the pass's save (fresh-load apply)")
        rows = [json.loads(line) for line in jd.ERRORS.read_text().splitlines()] if jd.ERRORS.exists() else []
        self.assertTrue(any(r.get("err") == "drift-skip" for r in rows),
                        "the race is observable: a drift-skip row lands in judge-errors")


if __name__ == "__main__":
    unittest.main()
