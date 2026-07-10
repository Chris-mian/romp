#!/usr/bin/env python3
"""A user resolve survives a racing judge-pass save (the user 2026-07-10).

The kernel's _resolve_node runs on a handler thread while a triage pass may
hold the same session's goal store in memory across a model call; both sides
write the whole store file (atomic rename, last writer wins), so the pass's
stale save could erase the user's resolve — the nodeComplete flag AND its
diary event alike, leaving nothing to re-derive the action from. Fix: the
kernel journals the resolve to overrides/<fsid>.jsonl before touching the
store (the cleared.jsonl pattern — the event is the write) and jd.load_goals
replays the journal idempotently, so the clobbered write re-applies on the
very next load.

All fixtures are SYNTHETIC (placeholder UUIDs, invented text).

Covers:
- the clobber interleave: a stale judge copy saved after the user's resolve
  erases it on disk; the next load_goals re-applies it, with exactly one
  user/done event in the node's log
- idempotence: when the resolve's own save survived, later loads add no
  second event
- the supersede guard: a later user reopen outranks the journal — replay
  must NOT re-complete a card the user deliberately reopened
- a journal line naming a node the store lacks is skipped without error
- a corrupt journal line is skipped, later lines still replay
"""
import json
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
import os

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-666666666666"
NID = "goal:1"
T0 = 1781100000


def _open_store():
    """A store with one OPEN top goal, in the on-disk shape load_goals expects."""
    return {"rompUuid": SID, "seq": 1, "placements": {}, "status": {NID: "working"},
            "nodes": {NID: {"id": NID, "parentId": None, "t": T0, "mt": T0,
                            "text": "wire the widget", "log": []}}}


class ResolveOverrideReplay(unittest.TestCase):
    def setUp(self):
        self._saved_state = jd.STATE
        self._td = Path(tempfile.mkdtemp())
        jd._rebind_state(self._td)             # STATE + every derived dir, incl. the overrides journal

    def tearDown(self):
        jd._rebind_state(self._saved_state)
        shutil.rmtree(self._td, ignore_errors=True)

    def _user_events(self, store):
        return [e for e in store["nodes"][NID].get("log", [])
                if e.get("src") == "user" and e.get("kind") == "done"]

    def test_clobbered_resolve_reapplies_on_the_next_load(self):
        jd.save_goals(SID, _open_store())
        judge_copy = jd.load_goals(SID)               # the pass loads BEFORE the user acts
        # the user resolves: journal first, then apply + save (what _resolve_node does)
        jd.append_override(SID, NID, "resolve", T0 + 100)
        user_store = jd.load_goals(SID)               # replay applies the journaled resolve
        self.assertTrue(user_store["nodes"][NID].get("nodeComplete"))
        jd.save_goals(SID, user_store)
        jd.save_goals(SID, judge_copy)                # the pass's STALE save lands last (the race)
        raw = json.loads((jd.GOALDIR / (SID + ".json")).read_text())
        self.assertFalse(raw["nodes"][NID].get("nodeComplete"),
                         "precondition: the stale save really erased the resolve on disk")
        healed = jd.load_goals(SID)                   # replay heals it
        self.assertTrue(healed["nodes"][NID].get("nodeComplete"))
        self.assertEqual(len(self._user_events(healed)), 1)
        self.assertEqual(healed["nodes"][NID]["mt"], T0 + 100)

    def test_surviving_resolve_gains_no_second_event(self):
        jd.save_goals(SID, _open_store())
        jd.append_override(SID, NID, "resolve", T0 + 100)
        jd.save_goals(SID, jd.load_goals(SID))        # the resolve's own save survives
        for _ in range(3):                            # every later load replays as a no-op
            store = jd.load_goals(SID)
            self.assertTrue(store["nodes"][NID].get("nodeComplete"))
            self.assertEqual(len(self._user_events(store)), 1)

    def test_later_user_reopen_outranks_the_journal(self):
        jd.save_goals(SID, _open_store())
        jd.append_override(SID, NID, "resolve", T0 + 100)
        store = jd.load_goals(SID)                    # resolve applies and survives
        jd.save_goals(SID, store)
        store = jd.load_goals(SID)                    # the user later reopens (follow-up / undo)
        self.assertTrue(jd.record_verdict(store, store["nodes"][NID], "user", "reopen", T0 + 200,
                                          why="Follow-up: not actually finished."))
        jd.save_goals(SID, store)
        healed = jd.load_goals(SID)                   # replay must NOT re-complete past the reopen
        self.assertFalse(healed["nodes"][NID].get("nodeComplete"))
        self.assertEqual(len(self._user_events(healed)), 1)

    def test_unknown_node_is_skipped(self):
        jd.save_goals(SID, _open_store())
        jd.append_override(SID, "goal:gone", "resolve", T0 + 100)
        store = jd.load_goals(SID)                    # no crash, nothing applied
        self.assertFalse(store["nodes"][NID].get("nodeComplete"))
        self.assertEqual(len(self._user_events(store)), 0)

    def test_corrupt_line_is_skipped_later_lines_replay(self):
        jd.save_goals(SID, _open_store())
        jd.OVERRIDES.mkdir(parents=True, exist_ok=True)
        with (jd.OVERRIDES / (SID + ".jsonl")).open("a") as f:
            f.write("{not json\n")
        jd.append_override(SID, NID, "resolve", T0 + 100)
        store = jd.load_goals(SID)
        self.assertTrue(store["nodes"][NID].get("nodeComplete"))
        self.assertEqual(len(self._user_events(store)), 1)


if __name__ == "__main__":
    unittest.main()
