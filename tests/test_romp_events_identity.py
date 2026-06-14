# Session-identity merge (the user 2026-06-12): romp-events groups a session's fork transcripts so the
# timeline shows ONE lane per conversation. The key must be the conversation's UUID LINEAGE, not its
# display name — a brand-new session that reuses a dead session's name (their case: killed "Debugger" +
# new "Debugger") shares the customTitle but NOT the conversation graph, so it must get its own lane.
# A resume/skill fork keeps the name AND links into the parent's graph (shared parentUuid node) → merged;
# a /clear or a new same-name session starts a disjoint graph → separate. These pin _session_sids().
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
ev = SourceFileLoader("romp_events_id", os.path.join(SCRIPTS, "romp-events")).load_module()

NOW = 1781100000                      # fixed clock; files are written "now" so they pass the HORIZON cutoff
ANCHOR = "aaaaaaaa-0000-0000-0000-000000000001"
FORK = "ffffffff-0000-0000-0000-000000000002"
NEWSES = "11111111-0000-0000-0000-000000000003"


def _ct():                            # the custom-title line every romp transcript carries
    return json.dumps({"type": "custom-title", "customTitle": "Debugger"})


def _line(uuid, parent):              # a conversation node: its own uuid + the parent it points at
    return json.dumps({"type": "user", "uuid": uuid, "parentUuid": parent,
                       "message": {"role": "user", "content": "x"}})


def _write(proj, fsid, lines):
    (proj / (fsid + ".jsonl")).write_text("\n".join(lines) + "\n")


class SessionIdentity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._projects = Path(self._tmp.name) / "projects"
        self._work = Path(self._tmp.name) / "work"
        self._work.mkdir(parents=True)
        self._orig = ev.PROJECTS
        ev.PROJECTS = self._projects
        ev._NODES_CACHE.clear()
        self.proj = ev._proj_dir(str(self._work))   # PROJECTS / mangled(realpath(work))
        self.proj.mkdir(parents=True)
        # anchor conversation: a1 -> a2
        _write(self.proj, ANCHOR, [_ct(), _line("a1", None), _line("a2", "a1")])

    def tearDown(self):
        ev.PROJECTS = self._orig
        ev._NODES_CACHE.clear()
        self._tmp.cleanup()

    def test_resume_fork_sharing_lineage_merges(self):
        # f1 forks from the anchor's a2 (shared node) → same conversation
        _write(self.proj, FORK, [_ct(), _line("f1", "a2"), _line("f2", "f1")])
        sids = set(ev._session_sids(str(self._work), ANCHOR, "Debugger", NOW))
        self.assertIn(FORK, sids)
        self.assertIn(ANCHOR, sids)

    def test_new_session_reusing_the_name_does_not_merge(self):
        # disjoint graph (fresh root n1, no node shared with the anchor) despite the same customTitle
        _write(self.proj, NEWSES, [_ct(), _line("n1", None), _line("n2", "n1")])
        sids = set(ev._session_sids(str(self._work), ANCHOR, "Debugger", NOW))
        self.assertNotIn(NEWSES, sids)
        self.assertEqual(sids, {ANCHOR})

    def test_mixed_merges_only_the_lineage_fork(self):
        _write(self.proj, FORK, [_ct(), _line("f1", "a2"), _line("f2", "f1")])
        _write(self.proj, NEWSES, [_ct(), _line("n1", None), _line("n2", "n1")])
        sids = set(ev._session_sids(str(self._work), ANCHOR, "Debugger", NOW))
        self.assertEqual(sids, {ANCHOR, FORK})

    def test_same_name_but_no_shared_node_is_separate_even_when_parent_only_links(self):
        # a fork that links by parentUuid alone (its parent a2 lives only in the anchor) still merges,
        # proving the test is on the GRAPH (uuid ∪ parentUuid), not on duplicated message bodies.
        _write(self.proj, FORK, [_ct(), _line("f1", "a2")])
        merged = set(ev._session_sids(str(self._work), ANCHOR, "Debugger", NOW))
        self.assertEqual(merged, {ANCHOR, FORK})

    def test_three_hop_fork_chain_folds_transitively(self):
        # A resume-fork links ONLY to its immediate parent (back-pointer, not a copy — see the case
        # above), so in a chain A->B->C the grandchild C shares NO node with anchor A directly. The merge
        # must be TRANSITIVE: B links A (b1.parent=a2), C links B (c1.parent=b2) → all three are one
        # conversation, one lane. (A non-transitive anchor-only intersection drops C — the regression
        # this guards: it would split the oldest segment of a twice-resumed session into its own lane.)
        B = "bbbbbbbb-0000-0000-0000-000000000004"
        C = "cccccccc-0000-0000-0000-000000000005"
        _write(self.proj, B, [_ct(), _line("b1", "a2"), _line("b2", "b1")])   # fork of the anchor
        _write(self.proj, C, [_ct(), _line("c1", "b2"), _line("c2", "c1")])   # fork of the fork (links to B only)
        sids = set(ev._session_sids(str(self._work), ANCHOR, "Debugger", NOW))
        self.assertEqual(sids, {ANCHOR, B, C}, "the whole resume chain must fold into one lane")

    def test_three_hop_chain_folds_from_the_latest_anchor_too(self):
        # The live sid is usually the NEWEST transcript, so the anchor can be the chain's TAIL. Folding
        # must reach back through the middle fork to the root: anchor C, C links B, B links A → {A,B,C}.
        B = "bbbbbbbb-0000-0000-0000-000000000004"
        C = "cccccccc-0000-0000-0000-000000000005"
        _write(self.proj, B, [_ct(), _line("b1", "a2"), _line("b2", "b1")])
        _write(self.proj, C, [_ct(), _line("c1", "b2"), _line("c2", "c1")])
        sids = set(ev._session_sids(str(self._work), C, "Debugger", NOW))
        self.assertEqual(sids, {ANCHOR, B, C}, "folding from the tail must reach the root through the middle fork")


if __name__ == "__main__":
    unittest.main()
