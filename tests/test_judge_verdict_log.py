#!/usr/bin/env python3
"""P3.1 dual-write + P3.2 shadow fold (the user 2026-07-06, design/judge-simplification-plan.md).

record_verdict = the gate AND the recorder fused: a verdict that passes may_apply appends an event to
the node's append-only log before the caller writes the flags (flags stay authoritative until the P3.3
flip). _fold_node_state derives the node's verdict state from the log alone; the property that kills
the replay bug class: SHUFFLING the log never changes the fold (ordering is reconstructed, not
assumed). _shadow_fold_check writes fold-vs-flags divergences for logBorn tops (E4). Synthetic only."""
import json
import os
import random
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_vlog", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
G1 = SID + ":g1"
T = 1781100000


def node(**kw):
    nd = {"id": G1, "text": "Ship it", "parentId": None, "nodeComplete": False,
          "blocked": False, "cleared": False, "trail": [], "t": T - 500, "mt": T - 100}
    nd.update(kw)
    return nd


class RecordVerdict(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))
        self.store = {"rompUuid": SID, "nodes": {G1: node()}, "placements": {}, "status": {}}

    def test_allowed_verdict_appends_denied_leaves_no_trace(self):
        nd = self.store["nodes"][G1]
        self.assertTrue(jd.record_verdict(self.store, nd, "judge", "done", T, why="shipped", seg="s1"))
        self.assertEqual(len(nd["log"]), 1)
        e = nd["log"][0]
        self.assertEqual((e["src"], e["kind"], e["ev_t"], e["why"], e["seg"]),
                         ("judge", "done", T, "shipped", "s1"))
        nd["followupAt"] = T + 100                        # the user acts later
        self.assertFalse(jd.record_verdict(self.store, nd, "judge", "done", T + 50, why="stale replay"))
        self.assertEqual(len(nd["log"]), 1, "a gated-out verdict leaves NO event")

    def test_log_cap_truncates_oldest(self):
        nd = self.store["nodes"][G1]
        for i in range(jd.LOG_CAP + 10):
            jd.record_verdict(self.store, nd, "judge", "done", T + i)
        self.assertEqual(len(nd["log"]), jd.LOG_CAP)
        self.assertTrue(nd["logTrunc"])
        self.assertEqual(nd["log"][0]["ev_t"], T + 10, "oldest dropped")


class TheFold(unittest.TestCase):
    def test_replayed_stale_done_loses_by_ordering_not_by_a_guard(self):
        # yesterday's bug class, told in fold terms: events may ARRIVE in any order; evidence
        # ordering decides. A stale done (ev_t before the user's reopen) appended LATE still loses.
        nd = node(log=[
            {"ev_t": T + 100, "src": "user", "kind": "reopen", "at": T + 100},
            {"ev_t": T + 50, "src": "judge", "kind": "done", "at": T + 999},   # replayed late
        ])
        self.assertEqual(jd._fold_node_state(nd), "open")

    def test_done_at_the_floor_lands_block_at_the_floor_voids(self):
        base = [{"ev_t": T + 100, "src": "user", "kind": "reopen", "at": T + 100}]
        nd = node(log=base + [{"ev_t": T + 100, "src": "judge", "kind": "done", "at": T + 101}])
        self.assertEqual(jd._fold_node_state(nd), "done", "the resolving turn shares the stamp: lands")
        nd = node(log=base + [{"ev_t": T + 100, "src": "judge", "kind": "block", "at": T + 101}])
        self.assertEqual(jd._fold_node_state(nd), "open", "a block computed from the answered ask: void")
        nd = node(log=base + [{"ev_t": T + 101, "src": "judge", "kind": "block", "at": T + 102}])
        self.assertEqual(jd._fold_node_state(nd), "blocked", "a genuinely new ask blocks")

    def test_shuffle_invariance(self):
        log = [
            {"ev_t": T + 10, "src": "judge", "kind": "done", "at": T + 11},
            {"ev_t": T + 20, "src": "user", "kind": "reopen", "at": T + 20},
            {"ev_t": T + 30, "src": "judge", "kind": "block", "at": T + 31},
            {"ev_t": T + 40, "src": "user", "kind": "reopen", "at": T + 40},
            {"ev_t": T + 50, "src": "judge", "kind": "done", "at": T + 51},
            {"ev_t": T + 15, "src": "judge", "kind": "block", "at": T + 300},  # stale replay
        ]
        want = jd._fold_node_state(node(log=list(log)))
        self.assertEqual(want, "done")
        rng = random.Random(7)
        for _ in range(20):
            rng.shuffle(log)
            self.assertEqual(jd._fold_node_state(node(log=list(log))), want,
                             "the fold must be invariant to arrival order")

    def test_agent_done_ordering_and_clear(self):
        # "the agent is never gated" governs write ACCEPTANCE (may_apply); the fold still orders by
        # evidence. The user reopening AFTER the agent's done wins (later evidence, higher authority)...
        nd = node(log=[
            {"ev_t": T + 100, "src": "user", "kind": "reopen", "at": T + 100},
            {"ev_t": T + 50, "src": "agent", "kind": "done", "at": T + 200},
        ])
        self.assertEqual(jd._fold_node_state(nd), "open", "the user's later reopen outranks the agent's earlier done")
        # ...an agent done AT the floor lands (unlike a judge block there), and after it, plainly
        nd = node(log=[
            {"ev_t": T + 100, "src": "user", "kind": "reopen", "at": T + 100},
            {"ev_t": T + 100, "src": "agent", "kind": "done", "at": T + 200},
        ])
        self.assertEqual(jd._fold_node_state(nd), "done")
        nd = node(log=[{"ev_t": T, "src": "judge", "kind": "done", "at": T},
                       {"ev_t": T + 1, "src": "user", "kind": "clear", "at": T + 1}])
        self.assertEqual(jd._fold_node_state(nd), "cleared")


class TheFlip(unittest.TestCase):
    """P3.3: the log is the authority; flags are a materialized cache rollup rewrites from history."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def test_backfill_preserves_every_legacy_state(self):
        # pre-dual-write stores (no logBorn): the flip must change NOTHING visible, by construction
        legacy = {
            SID + ":g1": dict(node(), id=SID + ":g1", nodeComplete=True),                       # done
            SID + ":g2": dict(node(), id=SID + ":g2", blocked=True, followupAt=T - 100),        # blocked past a follow-up
            SID + ":g3": dict(node(), id=SID + ":g3", cleared=True),                            # user-cleared
            SID + ":g4": dict(node(), id=SID + ":g4", everDone=True),                           # reopened once-done, open
        }
        store = {"rompUuid": SID, "placements": {}, "status": {}, "nodes": legacy}
        jd.rollup_status(store, True)
        st = store["status"]
        self.assertEqual((st[SID + ":g1"], st[SID + ":g2"], st[SID + ":g3"], st[SID + ":g4"]),
                         ("completed", "blocked", "cleared", "working"))
        for nd in store["nodes"].values():
            self.assertTrue(nd.get("logBorn"), "every node self-migrated")
            self.assertTrue(all(e.get("synth") for e in nd["log"]), "backfilled events are tagged synth")
        before = {nid: (nd["nodeComplete"], nd["blocked"], nd["cleared"]) for nid, nd in store["nodes"].items()}
        jd.rollup_status(store, True)                 # idempotent: a second pass changes nothing
        after = {nid: (nd["nodeComplete"], nd["blocked"], nd["cleared"]) for nid, nd in store["nodes"].items()}
        self.assertEqual(before, after)

    def test_history_overwrites_an_out_of_band_flag_write(self):
        # THE TEETH: a flag mutated without an event is restored from history on the next rollup
        nd = node(logBorn=True, nodeComplete=False,
                  log=[{"ev_t": T, "src": "judge", "kind": "done", "at": T}])
        store = {"rompUuid": SID, "placements": {}, "status": {}, "nodes": {G1: nd}}
        jd.rollup_status(store, True)
        self.assertTrue(nd["nodeComplete"], "the log's done outranks the wiped flag")
        self.assertEqual(store["status"][G1], "completed")
        # and the reverse: a hand-set done with NO history is demoted
        ghost = dict(node(), id=SID + ":g2", logBorn=True, nodeComplete=True, log=[])
        store["nodes"][SID + ":g2"] = ghost
        jd.rollup_status(store, True)
        self.assertFalse(ghost["nodeComplete"], "a flag with no history behind it does not survive")
        self.assertEqual(store["status"][SID + ":g2"], "working")

    def test_rolled_up_children_keep_their_tree_derived_cache(self):
        top = node(logBorn=True, nodeComplete=True,
                   log=[{"ev_t": T, "src": "judge", "kind": "done", "at": T}])
        kid = dict(node(), id=SID + ":g2", parentId=G1, logBorn=True, log=[])
        store = {"rompUuid": SID, "placements": {}, "status": {}, "nodes": {G1: top, SID + ":g2": kid}}
        jd.rollup_status(store, True)                 # roll-down resolves the open child under the done top
        self.assertTrue(kid["nodeComplete"] and kid["rolledUp"])
        jd.rollup_status(store, True)                 # materialize must not fight roll-down across passes
        self.assertTrue(kid["nodeComplete"] and kid["rolledUp"])
        self.assertEqual(store["status"][G1], "completed")


class DualWriteThroughTheSites(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def test_planner_done_records_event_and_e6_sample(self):
        store = {"rompUuid": SID, "nodes": {G1: node()}, "placements": {}, "status": {}, "lastNode": G1}
        menu = [{"id": G1, "text": "Ship it"}]
        jd.apply_plan(store, "seg-x", T, [{"do": "done", "goal": 1, "why": "shipped"}], menu, place_key="seg-x")
        log = store["nodes"][G1]["log"]
        self.assertEqual([(e["src"], e["kind"]) for e in log], [("judge", "done")])
        self.assertEqual(log[0]["seg"], "seg-x")
        samples = [json.loads(l) for l in (jd.STATE / "eager-done-samples.jsonl").read_text().splitlines()]
        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0]["focusHeld"], "G1 was the focus top at verdict time")

    def test_user_move_records_a_user_reopen(self):
        store = {"rompUuid": SID, "placements": {}, "status": {},
                 "nodes": {G1: node(nodeComplete=True, everDone=True)}}
        jd.rollup_status(store, True)
        jd.save_goals(SID, store)
        jd.user_move(SID, G1, now=T + 500)
        st = jd.load_goals(SID)
        kinds = [(e["src"], e["kind"], e["ev_t"]) for e in st["nodes"][G1]["log"]]
        self.assertIn(("user", "reopen", T + 500), kinds)

    def test_closer_verdicts_record(self):
        store = {"rompUuid": SID, "nodes": {G1: node()}, "placements": {}, "status": {}}
        jd.apply_close(store, [store["nodes"][G1]], {"block": {1: "pick a name"}}, t=T)
        self.assertEqual([(e["src"], e["kind"], e["why"]) for e in store["nodes"][G1]["log"]],
                         [("judge", "block", "pick a name")])


if __name__ == "__main__":
    unittest.main()
