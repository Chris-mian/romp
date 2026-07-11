#!/usr/bin/env python3
"""may_apply — THE arbitration gate (plan P1, the user 2026-07-06), plus the P2 placement-identity
migration. The authority ladder (user > agent > judges; a user action floors judge evidence; view-clear
seals) is stated and tested HERE, once — write sites just ask the gate. Includes the ratchet: a lint
test that fails if any code outside may_apply calls the staleness guards directly, so the ladder can't
quietly re-scatter. Synthetic fixtures only."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_mayapply", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
G1 = SID + ":g1"
FA = 1781100000


def node(**kw):
    nd = {"id": G1, "text": "Ship it", "parentId": None, "nodeComplete": False,
          "blocked": False, "cleared": False, "trail": [], "t": FA - 500, "mt": FA - 100}
    nd.update(kw)
    return nd


class TheLadder(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))
        self.store = {"rompUuid": SID, "nodes": {G1: node(followupAt=FA)}, "placements": {}, "status": {}}

    def test_judge_done_floor_equality_lands(self):
        nd = self.store["nodes"][G1]
        self.assertFalse(jd.may_apply(self.store, nd, "judge", "done", FA - 1), "older evidence: void")
        self.assertTrue(jd.may_apply(self.store, nd, "judge", "done", FA), "the resolving turn shares the stamp: lands")
        self.assertTrue(jd.may_apply(self.store, nd, "judge", "done", FA + 1), "newer evidence: lands")

    def test_judge_block_floor_equality_voids(self):
        nd = self.store["nodes"][G1]
        self.assertFalse(jd.may_apply(self.store, nd, "judge", "block", FA - 1), "older evidence: void")
        self.assertFalse(jd.may_apply(self.store, nd, "judge", "block", FA), "computed from the answered ask: void")
        self.assertTrue(jd.may_apply(self.store, nd, "judge", "block", FA + 1), "a genuinely new ask: blocks")

    def test_no_user_floor_means_judges_flow(self):
        nd = node()   # no followupAt
        self.assertTrue(jd.may_apply(self.store, nd, "judge", "done", FA - 999))
        self.assertTrue(jd.may_apply(self.store, nd, "judge", "block", FA - 999))

    def test_agent_verdicts_never_gated(self):
        nd = self.store["nodes"][G1]
        self.assertTrue(jd.may_apply(self.store, nd, "agent", "done", FA - 999),
                        "the agent's own to-do list outranks judge-evidence floors")

    def test_view_clear_seals_reopen_for_every_source(self):
        nd = self.store["nodes"][G1]
        self.assertTrue(jd.may_apply(self.store, nd, "user", "reopen"))
        (Path(self.td) / "romp").mkdir(parents=True, exist_ok=True)
        (jd.STATE / "cleared.jsonl").parent.mkdir(parents=True, exist_ok=True)
        (jd.STATE / "cleared.jsonl").write_text(json.dumps({"id": G1, "op": "clear"}) + "\n")
        self.assertFalse(jd.may_apply(self.store, nd, "user", "reopen"), "crossed off → sealed")
        self.assertFalse(jd.may_apply(self.store, nd, "judge", "reopen"), "sealed against ALL sources")


class LintNoScatteredGuards(unittest.TestCase):
    def test_staleness_guards_only_called_from_may_apply(self):
        # THE RATCHET: the ladder lives in may_apply and nowhere else. A new write site calling the
        # guards directly re-scatters the policy — fail it here.
        src = Path(os.path.join(BIN, "romp-judge")).read_text()
        offenders = []
        for i, line in enumerate(src.splitlines(), 1):
            s = line.strip()
            if s.startswith("def ") or s.startswith("#") or s.startswith('"'):
                continue
            if "_done_is_stale(" in s or "_block_is_stale(" in s:
                offenders.append((i, s))
        # the only two permitted call lines are inside may_apply's body
        self.assertEqual(len(offenders), 2, "guards called outside may_apply: %r" % offenders)
        for _, s in offenders:
            self.assertTrue(s.startswith("return not "), "unexpected guard call shape: %r" % s)


class PlacementsMigration(unittest.TestCase):
    def test_pre_versioning_store_seals_too(self):
        # Originally grandfathered (adopted without sealing) — no longer safe once the atom set grew
        # (2026-07-10): an unversioned store predates versioning itself, so a revive would replay every
        # newly-visible atom in its history as fresh goals. Sealed like any other version mismatch.
        store = {"rompUuid": SID, "nodes": {}, "placements": {SID + ":100:aa": SID + ":g1"}, "status": {}}
        changed = jd._migrate_placements(store, [SID + ":200:bb"], live={SID + ":200:bb"})
        self.assertTrue(changed)
        self.assertEqual(store["placementsV"], jd.PLACEMENTS_V)
        self.assertIsNone(store["placements"][SID + ":200:bb"], "sealed: revived history cannot replay")
        self.assertEqual(store["placements"][SID + ":100:aa"], SID + ":g1", "existing keys untouched")

    def test_fresh_empty_store_adopts_without_sealing(self):
        # an unversioned store with NOTHING recorded is a brand-new session, not a pre-versioning
        # dormant one — its first asks must plan, not seal (load_goals stamps new stores at birth)
        store = {"rompUuid": SID, "nodes": {}, "placements": {}, "status": {}}
        changed = jd._migrate_placements(store, [SID + ":200:bb"], live={SID + ":200:bb"})
        self.assertTrue(changed)
        self.assertEqual(store["placementsV"], jd.PLACEMENTS_V)
        self.assertNotIn(SID + ":200:bb", store["placements"], "a fresh session's first ask still plans")

    def test_version_mismatch_seals_ready_unplaced_units(self):
        store = {"rompUuid": SID, "placementsV": jd.PLACEMENTS_V - 1, "nodes": {},
                 "placements": {SID + ":100:aa": SID + ":g1"}, "status": {}}
        ready = [SID + ":200:bb", SID + ":300:cc", SID + ":100:aa"]
        jd._migrate_placements(store, ready, live=set(ready))
        self.assertEqual(store["placementsV"], jd.PLACEMENTS_V)
        self.assertIsNone(store["placements"][SID + ":200:bb"], "sealed: dormant history cannot replay")
        self.assertIsNone(store["placements"][SID + ":300:cc"])
        self.assertEqual(store["placements"][SID + ":100:aa"], SID + ":g1", "an exact-placed key is untouched")

    def test_current_version_is_a_noop(self):
        store = {"rompUuid": SID, "placementsV": jd.PLACEMENTS_V, "nodes": {}, "placements": {}, "status": {}}
        self.assertFalse(jd._migrate_placements(store, [SID + ":200:bb"], live=set()))
        self.assertEqual(store["placements"], {})


if __name__ == "__main__":
    unittest.main()
