#!/usr/bin/env python3
"""The view-side provenance split's classifier (the user 2026-08-25, option (iii) of the audit
memo): build_feed stamps `internal` on a top card whose evidence chain roots in team-internal
records — peer chatter (coordinate/question mail), romp's own bookkeeping (notices, interrupt
artifacts), machine-injected input — and stamps NOTHING when the walk can't classify confidently
(false-quiet is the failure this option was chosen to avoid: an unclassifiable card SHOWS). The
walk is deterministic and cache-only: records come from the parse cache (a cold cache is
unclassifiable, self-healing on the next warm push), stores are live+archive merged, cross-store
hops follow courier origin links, cross-host origins are unclassifiable by design (their kernel
classifies them; the field rides the merge). SYNTHETIC fixtures only; private synthetic sids."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_provsplit", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

WORKER = "aa15c4a1-0016-4b22-9c33-000000000001"   # private synthetic sids — never the shared placeholder
MGR = "aa15c4a1-0016-4b22-9c33-000000000002"
MID = "1787000000.000000_1.TESTHOST"


def _atom(uuid, typ="user", author=None, text=""):
    a = {"type": typ, "uuid": uuid,
         "message": {"role": typ, "content": [{"type": "text", "text": text}]}}
    if author is not None:
        a["author"] = author
    return a


class AtomKlass(unittest.TestCase):
    """_prov_atom_klass: one record's confident class, or None."""

    def test_human_is_user(self):
        self.assertEqual(km._prov_atom_klass(_atom("u1", author="human", text="fix the exporter")), "user")

    def test_interrupt_artifact_is_internal(self):
        self.assertEqual(km._prov_atom_klass(_atom("u1", author="human",
                                                   text="[Request interrupted by user]")), "internal")

    def test_romp_and_sdk_are_internal(self):
        self.assertEqual(km._prov_atom_klass(_atom("u1", author="romp")), "internal")
        self.assertEqual(km._prov_atom_klass(_atom("u1", author="sdk")), "internal")

    def test_mail_kinds(self):
        for kind, want in (("delegate", "delegate"), ("coordinate", "internal"),
                           ("question", "internal"), ("", None)):
            a = _atom("u1")
            a["author"] = {"peer": None, "mid": MID, "kind": kind}
            self.assertEqual(km._prov_atom_klass(a), want, "kind=%r" % kind)

    def test_attachment_reads_its_markers(self):
        mk = "<!-- romp-msg-id: %s -->" % MID
        att = _atom("q1", typ="attachment", text="body\n" + mk + "\n<!-- romp-msg-kind: coordinate -->")
        self.assertEqual(km._prov_atom_klass(att), "internal")
        att = _atom("q2", typ="attachment", text="body\n" + mk + "\n<!-- romp-msg-kind: delegate -->")
        self.assertEqual(km._prov_atom_klass(att), "delegate")
        att = _atom("q3", typ="attachment", text="<!-- romp-injected -->[romp] restarted")
        self.assertEqual(km._prov_atom_klass(att), "internal")
        att = _atom("q4", typ="attachment", text="queued human dictation, no markers")
        self.assertEqual(km._prov_atom_klass(att), "user")
        att = _atom("q5", typ="attachment", text="   ")
        self.assertIsNone(km._prov_atom_klass(att))

    def test_no_signal_is_none(self):
        self.assertIsNone(km._prov_atom_klass({"type": "user", "uuid": "u1"}))


class WalkWorld(unittest.TestCase):
    """The chain walk over synthetic two-session worlds (worker origin -> manager chain)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.paths = {}
        for sid in (WORKER, MGR):
            p = Path(self.td.name) / (sid + ".jsonl")
            p.write_text("{}\n")
            self.paths[sid] = str(p)
        km._prov_auth_cache.clear()
        km._prov_store_cache.clear()

    def tearDown(self):
        for sid in (WORKER, MGR):
            for d in (jd.GOALDIR, jd.GOALARCHDIR):
                try:
                    (d / (sid + ".json")).unlink()
                except OSError:
                    pass
        self.td.cleanup()

    def _seed_parse(self, sid, atoms):
        path = self.paths[sid]
        st = os.stat(path)
        km._parse_cache[path] = ((st.st_mtime, st.st_size), {"turns": [{"atoms": atoms}]})

    def _walk(self):
        return km._ProvenanceWalk([{"sid": s, "path": self.paths[s]} for s in (WORKER, MGR)])

    def _store(self, sid, nodes, archive=False):
        st = {"rompUuid": sid, "nodes": nodes, "placements": {}, "status": {}}
        (jd.save_goal_archive if archive else jd.save_goals)(sid, st)

    def test_direct_user_root(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None, "promptUuid": "u1"}})
        self._seed_parse(WORKER, [_atom("u1", author="human", text="fix the exporter")])
        self.assertEqual(self._walk().klass(WORKER, "g1"), "user")

    def test_direct_internal_root(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None, "promptUuid": "n1"}})
        self._seed_parse(WORKER, [_atom("n1", author="romp", text="[romp] restarted")])
        w = self._walk()
        self.assertEqual(w.klass(WORKER, "g1"), "internal")
        self.assertTrue(w.internal(WORKER, "g1"))

    def test_origin_chain_to_a_user_root(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None,
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID}}})
        self._store(MGR, {"g9": {"id": "g9", "parentId": None, "promptUuid": "hu"},
                          "t1": {"id": "t1", "parentId": "g9"}})
        self._seed_parse(MGR, [_atom("hu", author="human", text="ship the demo")])
        self.assertEqual(self._walk().klass(WORKER, "g1"), "user")

    def test_origin_chain_to_an_internal_root(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None,
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID}}})
        self._store(MGR, {"g9": {"id": "g9", "parentId": None, "promptUuid": "n1"},
                          "t1": {"id": "t1", "parentId": "g9"}})
        self._seed_parse(MGR, [_atom("n1", author="romp", text="[romp] tasks died")])
        self.assertTrue(self._walk().internal(WORKER, "g1"))

    def test_delegate_anchor_defers_to_the_origin_chain(self):
        # a courier-planted card carries BOTH the delegate mail promptUuid and the origin link:
        # the mail record itself is neither user nor internal — the chain continues through origin
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None, "promptUuid": "m1",
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID}}})
        a = _atom("m1")
        a["author"] = {"peer": MGR, "mid": MID, "kind": "delegate"}
        self._seed_parse(WORKER, [a])
        self._store(MGR, {"g9": {"id": "g9", "parentId": None, "promptUuid": "hu"},
                          "t1": {"id": "t1", "parentId": "g9"}})
        self._seed_parse(MGR, [_atom("hu", author="human", text="ship the demo")])
        self.assertEqual(self._walk().klass(WORKER, "g1"), "user")

    def test_archived_sender_nodes_still_resolve(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None,
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID}}})
        self._store(MGR, {"g9": {"id": "g9", "parentId": None, "promptUuid": "hu"},
                          "t1": {"id": "t1", "parentId": "g9"}}, archive=True)
        self._seed_parse(MGR, [_atom("hu", author="human", text="ship the demo")])
        self.assertEqual(self._walk().klass(WORKER, "g1"), "user")

    def test_unclassifiable_defaults_shown(self):
        # (a) origin to a store with no such node; (b) promptUuid outside the cached window;
        # (c) a COLD parse cache — all → None, and internal() is False (the card shows)
        self._store(WORKER, {
            "g1": {"id": "g1", "parentId": None, "origin": {"peer": MGR, "goalId": "gone", "msgId": MID}},
            "g2": {"id": "g2", "parentId": None, "promptUuid": "missing"},
            "g3": {"id": "g3", "parentId": None, "promptUuid": "u1"}})
        self._store(MGR, {})
        self._seed_parse(WORKER, [_atom("u1", author="human", text="hello")])
        w = self._walk()
        self.assertIsNone(w.klass(WORKER, "g1"))
        self.assertIsNone(w.klass(WORKER, "g2"))
        self.assertFalse(w.internal(WORKER, "g1"))
        self.assertFalse(w.internal(WORKER, "g2"))
        km._prov_auth_cache.clear()
        km._parse_cache.pop(self.paths[WORKER], None)   # cold cache → never a cold parse
        w2 = self._walk()
        self.assertIsNone(w2.klass(WORKER, "g3"))

    def test_cross_host_origin_is_unclassifiable_by_design(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None,
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID,
                                               "peerHost": "TESTHOST"}}})
        self._store(MGR, {"g9": {"id": "g9", "parentId": None, "promptUuid": "n1"},
                          "t1": {"id": "t1", "parentId": "g9"}})
        self._seed_parse(MGR, [_atom("n1", author="romp")])
        self.assertIsNone(self._walk().klass(WORKER, "g1"),
                          "another kernel's stores are not ours to read — its row arrives classified")

    def test_ancestor_climb_finds_the_nearest_evidence(self):
        # the leaf has no evidence; its parent's promptUuid resolves
        self._store(WORKER, {"top": {"id": "top", "parentId": None, "promptUuid": "u1"},
                             "kid": {"id": "kid", "parentId": "top"}})
        self._seed_parse(WORKER, [_atom("u1", author="human", text="hello")])
        self.assertEqual(self._walk().klass(WORKER, "kid"), "user")

    def test_parent_cycles_terminate_unclassified(self):
        self._store(WORKER, {"a": {"id": "a", "parentId": "b"},
                             "b": {"id": "b", "parentId": "a"}})
        self.assertIsNone(self._walk().klass(WORKER, "a"))

    def test_origin_cycles_terminate(self):
        self._store(WORKER, {"g1": {"id": "g1", "parentId": None,
                                    "origin": {"peer": MGR, "goalId": "t1", "msgId": MID}}})
        self._store(MGR, {"t1": {"id": "t1", "parentId": None,
                                 "origin": {"peer": WORKER, "goalId": "g1", "msgId": MID}}})
        self.assertIsNone(self._walk().klass(WORKER, "g1"))


if __name__ == "__main__":
    unittest.main()
