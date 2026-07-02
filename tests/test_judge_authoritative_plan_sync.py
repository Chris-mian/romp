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
        # born OPEN under watch, then completed → kept as authoritative-done
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [])]), "s0", T0)
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [("completed",)])]), "s1", T0 + 10)
        nd = agent_nodes(store)["1"]
        self.assertTrue(nd["nodeComplete"])
        # agent RE-OPENS it (completed → in_progress) → the done WE stamped is withdrawn
        jd._sync_declared_plan(store, plan_session([("Phase A", "Doing A", [("in_progress",)])]), "s2", T0 + 20)
        self.assertEqual(nd["agentTask"]["status"], "open")
        self.assertFalse(nd["nodeComplete"])

    def test_completed_item_is_never_minted_retroactively(self):
        """The regression (the user 2026-07-01): an idle session's ALREADY-completed to-do items must NOT
        pop up as fresh completed cards. A done/cancelled item with no node is skipped, not minted."""
        store = fresh_store()
        s = plan_session([("Done phase", "Doing", [("completed",)]),
                          ("Cancelled phase", "Doing", [("cancelled",)]),
                          ("Live phase", "Doing", [])])
        jd._sync_declared_plan(store, s, "s1", T0 + 10)
        keys = set(agent_nodes(store))
        self.assertEqual(keys, {"3"}, "only the OPEN item (#3) is minted; done/cancelled backlog is not")
        self.assertEqual(agent_nodes(store)["3"]["agentTask"]["status"], "open")

    def test_backlog_done_node_self_heals_away(self):
        """A pre-fix backlog mint — a DONE agentTask node that was never watched-open (agentBornOpen absent)
        — is deleted on the next sync, clearing the flooded completed cards."""
        store = fresh_store()
        store["seq"] = 1
        store["nodes"]["11111111-2222-3333-4444-555555555555:g1"] = {
            "id": "11111111-2222-3333-4444-555555555555:g1", "text": "Phase 1 (already done)", "parentId": None,
            "nodeComplete": True, "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0,
            "agentTask": {"key": "1", "status": "done", "raw": "completed"}}   # NO agentBornOpen → backlog
        s = plan_session([("Phase 1 (already done)", "Doing", [("completed",)])])
        self.assertTrue(jd._sync_declared_plan(store, s, "s1", T0 + 10))
        self.assertEqual(agent_nodes(store), {}, "the born-done backlog node is self-healed away")

    def test_open_backlog_node_is_adopted_not_deleted(self):
        """A pre-fix OPEN agentTask node (marker absent) is ADOPTED (marker added), never deleted — so it
        keeps holding its goal working and is protected from the done-heal when it later completes."""
        store = fresh_store()
        store["seq"] = 1
        nid = "11111111-2222-3333-4444-555555555555:g1"
        store["nodes"][nid] = {"id": nid, "text": "Live phase", "parentId": None, "nodeComplete": False,
                               "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0,
                               "agentTask": {"key": "1", "status": "open", "raw": "in_progress"}}
        jd._sync_declared_plan(store, plan_session([("Live phase", "Doing", [("in_progress",)])]), "s1", T0 + 10)
        self.assertIn(nid, store["nodes"], "an open backlog node is kept")
        self.assertTrue(store["nodes"][nid].get("agentBornOpen"), "and adopted (marker added)")


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


class BlockedAuthority(unittest.TestCase):
    """Stalled-with-open-to-dos (design/stalled-open-todos-nudge.md): the agent CANNOT self-mark a to-do
    blocked (Claude Code's to-do system has no such state), so when the fork nudge elicits "blocked because
    …" the PLANNER blocks the open agentTask node — and that block must STICK. The rollup contract that
    makes it stick: blocked outranks the authoritative-open tier (open_task only gates completeness), and
    the stale-block heal clears blocks only on COMPLETE nodes, which an open-task node never is. These pin
    that contract so the fork-nudge → planner-block → needs-you path can't silently break."""

    def _blocked_open_todo(self, umbrella_complete=False):
        store = fresh_store()
        store["nodes"] = {
            "T": {"id": "T", "text": "umbrella", "parentId": None, "nodeComplete": umbrella_complete,
                  "blocked": False, "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0},
            "C": {"id": "C", "text": "wire the adapter", "parentId": "T", "nodeComplete": False,
                  "blocked": True, "blockWhy": "needs the staging credentials from the user",
                  "cleared": False, "trail": ["seg0"], "t": T0, "mt": T0 + 10, "agentBornOpen": True,
                  "agentTask": {"key": "1", "status": "open", "raw": "pending"}},
        }
        store["lastNode"] = "T"
        return store

    def test_block_on_open_todo_rolls_up_blocked(self):
        store = self._blocked_open_todo()
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "blocked",
                         "a planner block on an open agent to-do pulls the top to blocked/needs-you")
        self.assertTrue(store["nodes"]["C"]["blocked"], "the raw block flag survives the rollup")
        self.assertEqual(store["nodes"]["C"]["blockWhy"], "needs the staging credentials from the user")

    def test_block_outranks_a_flat_done_umbrella(self):
        """Even when the closer flat-DONE'd the top, a blocked still-open to-do keeps the card in
        needs-you: the open-task authority holds the top un-complete, so any_blocked isn't short-circuited
        and the stale-block heal never fires."""
        store = self._blocked_open_todo(umbrella_complete=True)
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "blocked")

    def test_block_survives_a_declared_plan_resync(self):
        """_sync_declared_plan refreshes agentTask status but must not touch a planner block: while the
        agent's list still says the item is open, the block (+ its why) rides along un-clobbered."""
        store = self._blocked_open_todo()
        jd._sync_declared_plan(store, plan_session([("wire the adapter", "Wiring", [])]), "s1", T0 + 50)
        self.assertTrue(store["nodes"]["C"]["blocked"], "re-sync of a still-open item keeps the block")
        self.assertEqual(store["nodes"]["C"]["blockWhy"], "needs the staging credentials from the user")
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "blocked")

    def test_crossing_off_the_blocked_todo_heals_the_block(self):
        """Positive control: once the agent completes the item, the block's answer is moot — the sync
        stamps authoritative-done and the rollup's stale-block heal clears the raw flag + blockWhy."""
        store = self._blocked_open_todo()
        jd._sync_declared_plan(store, plan_session([("wire the adapter", "Wiring", [("completed",)])]),
                               "s2", T0 + 100)
        jd.rollup_status(store, True)
        self.assertEqual(store["status"]["T"], "completed")
        self.assertFalse(store["nodes"]["C"]["blocked"], "a complete node can't stay blocked")
        self.assertNotIn("blockWhy", store["nodes"]["C"])


if __name__ == "__main__":
    unittest.main()
