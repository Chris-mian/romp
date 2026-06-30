#!/usr/bin/env python3
"""An auto-nudge must NOT reopen an already-completed goal (the user 2026-06-30). Repro of the
completed→blocked regression: the auto-nudge fires on a 'working' goal, a later judge pass completes it, then
the agent's nudge-reply ("…blocked on you: waiting for your go-ahead") is processed as a nudge unit. The OLD
nudge-phase called _reopen() unconditionally — un-completing the goal — and then re-blocked it from the reply,
so a completed card flipped to blocked (rollup precedence: blocked > completed). The fix: if the nudge target
is already done, the nudge is moot → place nothing, leave it completed. Synthetic transcript only.
"""
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_nudgereopen", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
GID = SID + ":g1"


def _iso(ep):
    import datetime
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class NudgeNoReopenCompleted(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))
        jd._PARSE_CACHE.clear()
        # a completed top goal (the closer finished it)
        self.store = {"rompUuid": SID, "seq": 1,
                      "nodes": {GID: {"id": GID, "text": "Clarify the design", "parentId": None,
                                      "nodeComplete": True, "blocked": False, "cleared": False,
                                      "trail": [], "t": 1000, "mt": 2000}},
                      "placements": {}, "status": {GID: "completed"}, "lastNode": GID}
        jd.save_goals(SID, self.store)
        # stubs: a nudge resolution that, if it ran, would BLOCK the goal (so the bug would manifest)
        self._plan_calls = []
        self._saved = (jd.plan_llm, jd.plan_prompt_llm, jd._group_store)
        jd.plan_llm = lambda *a, **k: self._plan_calls.append(k) or '{"ops":[{"do":"block","n":1,"why":"waiting on the user"}]}'
        jd.plan_prompt_llm = lambda *a, **k: ""
        jd._group_store = lambda *a, **k: None

    def tearDown(self):
        jd.plan_llm, jd.plan_prompt_llm, jd._group_store = self._saved

    def _nudge_transcript(self):
        """One ENDED turn opened by an AUTO-nudge message (romp-injected + romp-auto + romp-goal-id) targeting
        GID, with an assistant 'waiting on you' reply → classified as a nudge unit for GID."""
        path = os.path.join(self.td, SID + ".jsonl")
        t = 3000
        nudge_text = ("Status on the goal above: what's done, what's left, and is anything blocked?"
                      "<!-- romp-injected --><!-- romp-auto --><!-- romp-goal-id: %s -->" % GID)
        recs = [
            {"type": "user", "uuid": "n1", "parentUuid": None, "timestamp": _iso(t),
             "message": {"role": "user", "content": nudge_text}},
            {"type": "assistant", "uuid": "a1", "parentUuid": "n1", "timestamp": _iso(t + 2),
             "message": {"role": "assistant", "stop_reason": "end_turn",
                         "content": [{"type": "text", "text": "Done — it's blocked on you: waiting for your go-ahead."}]}},
        ]
        open(path, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
        return path

    def test_auto_nudge_reply_does_not_reopen_or_block_a_completed_goal(self):
        path = self._nudge_transcript()
        # sanity: the segment really is classified as a nudge unit targeting GID
        sess = jd.parsed_session(SID, [path], time.time())
        units = [u for u in jd.plan_units(sess) if u[1] == "nudge"]
        self.assertEqual(len(units), 1, "the auto-nudge reply is a nudge unit")
        self.assertEqual(units[0][5], GID, "...targeting the completed goal")

        jd._plan_session(SID, path, time.time())

        store = jd.load_goals(SID)
        nd = store["nodes"][GID]
        self.assertTrue(nd.get("nodeComplete"), "the completed goal stays completed — never reopened")
        self.assertFalse(nd.get("blocked"), "and is NOT re-blocked by the nudge reply")
        self.assertFalse(nd.get("everDone"), "_reopen was never called (no everDone marker)")
        self.assertEqual(store["status"].get(GID), "completed", "rolled-up status stays completed")
        self.assertEqual(self._plan_calls, [], "the nudge LLM resolution is never even invoked on a done goal")
        # the unit is recorded processed so it doesn't re-run every pass
        self.assertIn(units[0][0], store["placements"])

    def test_reopen_of_a_completed_goal_writes_an_instrumentation_line(self):
        # TEMP instrumentation: _reopen un-completing a done goal logs a 'reopen-done' line tagged by caller,
        # so a completed→blocked flip is attributable in the wild. (Remove with the instrumentation.)
        Gx = SID + ":gx"
        st = {"rompUuid": SID, "seq": 1,
              "nodes": {Gx: {"id": Gx, "text": "x", "parentId": None, "nodeComplete": True,
                             "blocked": False, "cleared": False, "trail": [], "t": 1}},
              "placements": {}, "status": {}}
        jd._reopen(st, Gx, by="followup")
        diag = Path(self.td) / "nudge-diag.jsonl"
        lines = [json.loads(l) for l in diag.read_text().splitlines()] if diag.exists() else []
        rd = [l for l in lines if l.get("event") == "reopen-done"]
        self.assertEqual(len(rd), 1)
        self.assertEqual(rd[0]["by"], "followup")
        self.assertEqual(rd[0]["gid"], Gx)


if __name__ == "__main__":
    unittest.main()
