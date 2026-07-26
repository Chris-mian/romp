#!/usr/bin/env python3
"""The SWEEPER (the user 2026-07-26): an open working goal with real evidence is reachable only through
turn menus, so once its last turn is closed as still-open, a reply that delivers its outcome on a
sibling card's thread never reaches it — the planner files that reply under the goal it was asked
about, and the first card sits working forever (2026-07-25: a docs top sat working across a
session-wide all-done reply until the user cleared it by hand). The delivered-elsewhere gap was
already closed for BLOCKED goals (the unblocker) and evidence-less mints (the starved channel); the
sweeper is the third leg: open working goals WITH evidence, re-examined against the conversation
since they last heard anything, settled via the same record_verdict("done") the closer uses.
Event-gated per node (sweepCheckT vs the newest ended turn), model stubbed, conservative hold
default. All fixtures SYNTHETIC (invented text, placeholder UUIDs, the notes-api demo domain).
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
jd = SourceFileLoader("romp_judge_sweep", os.path.join(BIN, "romp-judge")).load_module()

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


def _node(nid, text, parent=None, trail=(), log=(), **extra):
    """A plain-dict node BEFORE save (protected flags are diary-owned once loaded — GuardedNode)."""
    nd = {"id": nid, "text": text, "parentId": parent, "nodeComplete": False, "cleared": False,
          "blocked": False, "trail": list(trail), "log": list(log), "t": T0, "mt": T0}
    nd.update(extra)
    return nd


class SweeperBase(unittest.TestCase):
    def setUp(self):
        self._saved_state = jd.STATE
        self._td = tempfile.mkdtemp()
        jd._rebind_state(Path(self._td))
        jd.GOALDIR.mkdir(parents=True, exist_ok=True)
        jd._PARSE_CACHE.clear()
        self._saved_llm = jd.sweep_llm
        self.calls = []

    def tearDown(self):
        jd.sweep_llm = self._saved_llm
        jd._rebind_state(self._saved_state)
        shutil.rmtree(self._td, ignore_errors=True)

    def _stub(self, reply):
        def fake(goals_text, since_text):
            self.calls.append((goals_text, since_text))
            return reply
        jd.sweep_llm = fake

    def _store(self, nodes):
        store = {"rompUuid": SID, "seq": 2, "lastNode": nodes[0]["id"], "placements": {},
                 "status": {}, "nodes": {nd["id"]: nd for nd in nodes}}
        jd.save_goals(SID, store)
        return store

    def _transcript(self, turns):
        """Write a transcript of ENDED turns [(t, user_text, reply_text), ...] + return its path."""
        recs, prev = [], None
        for i, (t, ask, reply) in enumerate(turns):
            u, a = "u%d" % i, "a%d" % i
            recs.append(uline(t, ask, u, parent=prev))
            recs.append(aline(t + 5, reply, a, parent=u))
            prev = a
        p = Path(self._td) / (SID + ".jsonl")
        p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        return str(p)


# The worked-elsewhere fixture both suites below share: goal A ("migrate the notes-api auth") settled
# normally; goal B ("write the notes-api deployment guide") worked earlier (trail), then a later status
# reply on A's thread reports B's outcome delivered too.
def _trail(ts):
    return [SID + ":%d:s%d" % (t, i) for i, t in enumerate(ts)]


class SweepCandidates(SweeperBase):
    def test_a_trail_bearing_open_goal_qualifies(self):
        g = SID + ":g2"
        self._store([_node(g, "write the deployment guide", trail=_trail([T0 + 90, T0 + 100]))])
        cands = jd._sweep_candidates(jd.load_goals(SID))
        self.assertEqual([c[0] for c in cands], [g])
        self.assertEqual(cands[0][2], T0 + 100, "heard = the newest trail segment's turn time")

    def test_a_diary_bearing_goal_qualifies_and_heard_reads_the_diary(self):
        g = SID + ":g2"
        self._store([_node(g, "tune the api rate limits",
                           log=[{"ev_t": T0 + 200, "src": "planner", "kind": "note", "at": T0 + 200}])])
        cands = jd._sweep_candidates(jd.load_goals(SID))
        self.assertEqual([c[0] for c in cands], [g])
        self.assertEqual(cands[0][2], T0 + 200, "heard = the newest diary event's evidence time")

    def test_an_evidence_less_mint_is_the_starved_channels_not_ours(self):
        # the exact complement: trail<=1 and no log → _starved_candidates territory, never nominated here
        g = SID + ":g2"
        self._store([_node(g, "a bare minted ask", trail=_trail([T0 + 90]))])
        self.assertEqual(jd._sweep_candidates(jd.load_goals(SID)), [])

    def test_ruled_and_owned_nodes_are_skipped(self):
        base = _trail([T0 + 90, T0 + 100])
        self._store([
            _node(SID + ":g1", "done already", trail=base, nodeComplete=True),
            _node(SID + ":g2", "blocked on the user", trail=base, blocked=True),   # the unblocker owns it
            _node(SID + ":g3", "cleared by hand", trail=base, cleared=True),
            _node(SID + ":g4", "agent still owes work", trail=base,
                  agentTask={"key": "k1", "status": "open"}),
        ])
        self.assertEqual(jd._sweep_candidates(jd.load_goals(SID)), [])


class Sweeper(SweeperBase):
    def _worked_elsewhere(self):
        a, b = SID + ":g1", SID + ":g2"
        self._store([
            _node(a, "migrate the notes-api auth", nodeComplete=True),
            _node(b, "write the notes-api deployment guide", trail=_trail([T0 + 90, T0 + 100])),
        ])
        path = self._transcript([
            (T0 + 50, "start the deployment guide", "drafting the guide now"),
            (T0 + 500, "status on the migration?",
             "Migration done, and the deployment guide shipped with it - both pages are live, nothing left on either."),
            (T0 + 600, "thanks, wrapping up", "all wrapped"),
        ])
        return a, b, path

    def test_an_outcome_delivered_elsewhere_settles_the_goal(self):
        a, b, path = self._worked_elsewhere()
        self._stub('{"verdicts": [{"n": 1, "do": "settle", "why": "the status reply says the guide shipped and is live"}]}')
        self.assertEqual(jd._sweep_session(SID, path, NOW), [b])
        store = jd.load_goals(SID)
        nd = store["nodes"][b]
        self.assertTrue(nd["nodeComplete"], "the moved-past goal is completed")
        ev = next(e for e in reversed(nd.get("log") or [])
                  if e.get("src") == "sweeper")        # the settle STAMP (src 'romp') rides after the verdict
        self.assertEqual(ev.get("kind"), "done")
        self.assertIn("delivered elsewhere", ev.get("why", ""), "provenance rides the diary")
        self.assertIn("deployment guide", self.calls[0][0], "the goal is shown to the model")
        self.assertIn("both pages are live", self.calls[0][1], "the after-conversation is shown")

    def test_a_hold_keeps_the_goal_and_the_watermark_prevents_reasking(self):
        a, b, path = self._worked_elsewhere()
        self._stub('{"verdicts": [{"n": 1, "do": "hold", "why": ""}]}')
        self.assertEqual(jd._sweep_session(SID, path, NOW), [])
        store = jd.load_goals(SID)
        self.assertFalse(store["nodes"][b]["nodeComplete"], "held: still genuinely open")
        self.assertGreater(store["nodes"][b].get("sweepCheckT") or 0, T0 + 100,
                           "the watermark advanced to the examined evidence")
        # same evidence again → no second model call (event-gated)
        self.assertEqual(jd._sweep_session(SID, path, NOW), [])
        self.assertEqual(len(self.calls), 1, "no new ended turn → no re-ask")
        # a NEWER ended turn re-arms the examination
        path2 = self._transcript([
            (T0 + 50, "start the deployment guide", "drafting the guide now"),
            (T0 + 500, "status on the migration?", "migration done, guide shipped too"),
            (T0 + 900, "one more look", "looked"),
            (T0 + 950, "tail", "tail reply"),
        ])
        jd._PARSE_CACHE.clear()
        jd._sweep_session(SID, path2, NOW)
        self.assertEqual(len(self.calls), 2, "new evidence → examined again")

    def test_a_goal_merely_unmentioned_is_never_settled_by_parse_tolerance(self):
        # conservative-parse floor: garbage or out-of-range replies hold everything
        a, b, path = self._worked_elsewhere()
        self._stub('{"verdicts": [{"n": 7, "do": "settle", "why": "out of range"}]}')
        self.assertEqual(jd._sweep_session(SID, path, NOW), [])
        self.assertFalse(jd.load_goals(SID)["nodes"][b]["nodeComplete"])

    def test_parse_failures_advance_the_watermark_only_at_the_fail_cap(self):
        a, b, path = self._worked_elsewhere()
        self._stub("not json at all")
        for i in range(jd.JUDGE_FAIL_CAP):
            self.assertEqual(jd._sweep_session(SID, path, NOW), [])
        store = jd.load_goals(SID)
        self.assertGreater(store["nodes"][b].get("sweepCheckT") or 0, T0 + 100,
                           "the give-up advances the watermark so the pass is not re-asked forever")
        self.assertEqual(store.get("sweepFails"), 0, "the counter resets with the give-up")

    def test_a_node_that_moved_on_during_the_call_is_drift_skipped(self):
        a, b, path = self._worked_elsewhere()

        def fake(goals_text, since_text):
            # the user clears the node while the model call is in flight: rewrite the RAW store file
            # (plain dicts on disk — GuardedNode only guards loaded nodes)
            p = jd.GOALDIR / (SID + ".json")
            obj = json.loads(p.read_text())
            obj["nodes"][b]["cleared"] = True
            p.write_text(json.dumps(obj))
            self.calls.append((goals_text, since_text))
            return '{"verdicts": [{"n": 1, "do": "settle", "why": "shipped"}]}'
        jd.sweep_llm = fake
        self.assertEqual(jd._sweep_session(SID, path, NOW), [], "the stale settle is skipped, not applied")


if __name__ == "__main__":
    unittest.main()
