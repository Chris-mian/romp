#!/usr/bin/env python3
"""Authoritative-tier plan-sync (the user 2026-07-01): the agent's OWN live to-do list (Claude
Code's Task tool) is mirrored DETERMINISTICALLY into the goal graph as `agentTask` nodes, and an
agent-declared-OPEN item is authoritative — its open state trumps a judge/rollup 'done'.

Covers:
- em.declared_plan   — folding TaskCreate/TaskUpdate (+ results) into ordered {key,text,status}.
- jd._sync_declared_plan — find-or-create by stable Task id; idempotent; status refresh; reopen.
- jd.rollup_status   — an agentTask-open descendant holds its top WORKING even when the umbrella
                       was flat-marked complete; a crossed-off item lets normal roll-up proceed.

All fixtures SYNTHETIC (invented text, placeholder UUIDs, hostname TESTHOST).
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent, stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": text}] if text else [],
                        "stop_reason": stop}}


def tcreate(t, uuid, parent, subject, active, tool_id):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "stop_reason": "tool_use",
                        "content": [{"type": "tool_use", "id": tool_id, "name": "TaskCreate",
                                     "input": {"subject": subject, "activeForm": active}}]}}


def tupdate(t, uuid, parent, task_id, status, tool_id):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "stop_reason": "tool_use",
                        "content": [{"type": "tool_use", "id": tool_id, "name": "TaskUpdate",
                                     "input": {"taskId": task_id, "status": status}}]}}


def tres(t, uuid, parent, tool_use_id, text):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": text}]}}


def build_session(records, now=NOW, rompuuid=SID):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / (rompuuid + ".jsonl")
        p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return em.parse_session(str(p), rompuuid=rompuuid, candidate_files=[str(p)], now=now)


def plan_session(items, now=NOW):
    """A synthetic session that declares `items` = [(subject, active, [(status_after,)...])] via the
    Task tool. Returns the parsed session. Task #N ids are assigned in creation order."""
    recs = [uline(T0, "run the migration", "u1")]
    parent, t, n = "u1", T0 + 5, 0
    for subject, active, updates in items:
        n += 1
        tc = "tc%d" % n
        recs.append(tcreate(t, "ac%d" % n, parent, subject, active, tc)); t += 1
        recs.append(tres(t, "rc%d" % n, "ac%d" % n, tc,
                         "Task #%d created successfully. Use TaskUpdate to update it." % n)); t += 1
        parent = "rc%d" % n
        for j, (status,) in enumerate(updates):
            tu = "tu%d_%d" % (n, j)
            recs.append(tupdate(t, "au%d_%d" % (n, j), parent, str(n), status, tu)); t += 1
            recs.append(tres(t, "ru%d_%d" % (n, j), "au%d_%d" % (n, j), tu, "Task #%d updated." % n)); t += 1
            parent = "ru%d_%d" % (n, j)
    recs.append(aline(t + 1, "On it.", "aend", parent, stop="end_turn"))
    return build_session(recs, now=now)


def fresh_store():
    return {"rompUuid": SID, "seq": 0, "nodes": {}, "placements": {}, "status": {}}


def agent_nodes(store):
    return {nd["agentTask"]["key"]: nd for nd in store["nodes"].values() if nd.get("agentTask")}


class DeclaredPlanAdapter(unittest.TestCase):
    def test_folds_taskcreate_taskupdate_in_order(self):
        s = plan_session([
            ("Design v3", "Designing v3", [("completed",)]),
            ("Rewire store", "Rewiring store", []),
        ])
        items = em.declared_plan(s)
        self.assertEqual([it["text"] for it in items], ["Design v3", "Rewire store"],
                         "creation order preserved")
        self.assertEqual({it["key"]: it["status"] for it in items},
                         {"1": "completed", "2": "pending"})

    def test_last_update_wins(self):
        s = plan_session([("Phase 2a", "Doing 2a", [("in_progress",), ("completed",)])])
        self.assertEqual(em.declared_plan(s)[0]["status"], "completed")

    def test_empty_when_no_task_tool(self):
        s = build_session([uline(T0, "hi", "u1"), aline(T0 + 5, "hello", "a1", "u1")])
        self.assertEqual(em.declared_plan(s), [])


class SyncFindOrCreate(unittest.TestCase):
    def test_mints_one_node_per_item_idempotently(self):
        store = fresh_store()
        s = plan_session([("Phase A", "Doing A", []), ("Phase B", "Doing B", [])])
        self.assertTrue(jd._sync_declared_plan(store, s, "seg1", T0 + 50))
        self.assertEqual(len(agent_nodes(store)), 2)
        # re-sync of the SAME session mutates nothing (no duplicate nodes, returns False)
        self.assertFalse(jd._sync_declared_plan(store, s, "seg1", T0 + 60))
        self.assertEqual(len(store["nodes"]), 2)
        for nd in store["nodes"].values():                       # minted as tops for the grouper to place
            self.assertIsNone(nd["parentId"])
            self.assertEqual(nd["agentTask"]["status"], "open")
            self.assertFalse(nd["nodeComplete"])

    def test_status_refresh_stamps_authoritative_done(self):
        store = fresh_store()
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [])]), "seg1", T0 + 50)
        nd = agent_nodes(store)["1"]
        self.assertEqual(nd["agentTask"]["status"], "open")
        # the agent crosses it off → the SAME node flips to authoritative-done
        done_s = plan_session([("Phase A", "Doing A", [("completed",)])])
        self.assertTrue(jd._sync_declared_plan(store, done_s, "seg2", T0 + 100))
        self.assertEqual(len(agent_nodes(store)), 1, "still one node (find-or-create by key)")
        self.assertEqual(nd["agentTask"]["status"], "done")
        self.assertTrue(nd["nodeComplete"])

    def test_reopen_clears_only_our_done(self):
        store = fresh_store()
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [("completed",)])]), "s1", T0 + 10)
        nd = agent_nodes(store)["1"]
        self.assertTrue(nd["nodeComplete"])
        # agent RE-OPENS it (completed → in_progress) → the done WE stamped is withdrawn
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [("in_progress",)])]), "s2", T0 + 20)
        self.assertEqual(nd["agentTask"]["status"], "open")
        self.assertFalse(nd["nodeComplete"])

    def test_cancelled_is_not_open(self):
        store = fresh_store()
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [("cancelled",)])]), "s1", T0 + 10)
        nd = agent_nodes(store)["1"]
        self.assertEqual(nd["agentTask"]["status"], "done", "cancelled is abandoned, not owed — never open")


class RollupAuthority(unittest.TestCase):
    def _umbrella_with_child(self, child_task_status, umbrella_complete=True):
        """An umbrella top flat-marked complete, with one child carrying an agentTask."""
        store = fresh_store()
        store["nodes"] = {
            "T": {"id": "T", "text": "umbrella", "parentId": None, "nodeComplete": umbrella_complete,
                  "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0},
            "C": {"id": "C", "text": "phase 2b", "parentId": "T", "nodeComplete": (child_task_status == "done"),
                  "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0,
                  "agentTask": {"key": "2", "status": child_task_status, "raw": "in_progress"}},
        }
        store["lastNode"] = "T"
        return store

    def test_open_todo_trumps_completed_umbrella(self):
        """The screenshot bug: the umbrella was flat-DONE'd but a to-do under it is still open, so the
        card must read WORKING, not completed."""
        store = self._umbrella_with_child("open")
        jd.rollup_status(store, True)                            # session closed → would normally settle-complete
        self.assertEqual(store["status"]["T"], "working",
                         "an authoritative-open descendant holds the top working")

    def test_crossed_off_todo_lets_umbrella_complete(self):
        """Positive control: once the agent crosses the item off, normal completion resumes."""
        store = self._umbrella_with_child("done")
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "completed")

    def test_no_done_rolldown_onto_open_subtree(self):
        """A completed sibling branch must not stamp done onto the open to-do's node via roll-down."""
        store = self._umbrella_with_child("open", umbrella_complete=False)
        # add a genuinely-done sibling so bottom-up doesn't complete T either
        store["nodes"]["D"] = {"id": "D", "text": "phase 1", "parentId": "T", "nodeComplete": True,
                               "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0}
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "working")
        self.assertFalse(store["nodes"]["C"].get("nodeComplete"),
                         "the open to-do node is never auto-completed")


if __name__ == "__main__":
    unittest.main()
