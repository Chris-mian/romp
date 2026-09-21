#!/usr/bin/env python3
"""Lifecycle validation for the Road B freeze (issue #1735, kernel/gc_freeze.py).

The freeze keeps the loaded decoded heap out of the collector's walk, so the tests prove the
collector still behaves: the trigger logic folds a load in cheaply and reclaims a release with
an unfreeze; the env switch turns it off; an acyclic object frozen then dropped dies by
reference counting while a frozen CYCLE survives until a reclaim; re-folding a transcript across
a freeze forces no reread; the gc hook still counts the collections that do run; and a warm
collection after the freeze walks far fewer objects than the cold one. Every fixture is
synthetic. Real-collector tests unfreeze in tearDown so the freeze never leaks to another test.
"""
import gc
import json
import os
import sys
import tempfile
import unittest
import weakref
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
GC_FREEZE = os.path.join(ROOT, "kernel", "gc_freeze.py")

sys.path.insert(0, os.path.join(ROOT, "tests"))
from romp_load import load_source   # brought in before the state preamble (the mkdtemp hook and TMPDIR redirect ride it)

# hermetic before any romp module load (never load romp modules against live state)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts").write_text("off")
os.environ["ROMP_POSTAL_CLIENT_ONLY"] = "1"

gf = load_source("romp_gc_freeze", GC_FREEZE)


class FakeGc:
    """Records the collector calls a reconcile makes, in order, so the trigger logic is pinned
    without touching the real collector."""
    def __init__(self):
        self.calls = []
    def collect(self, *a):
        self.calls.append("collect")
    def freeze(self):
        self.calls.append("freeze")
    def unfreeze(self):
        self.calls.append("unfreeze")


class TriggerLogic(unittest.TestCase):
    def test_a_load_folds_in_and_a_release_reclaims(self):
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=fake, clock=lambda: 0.0)
        # nothing loaded yet: not due; a first load makes the initial freeze due
        self.assertFalse(c.due(inserts=0, releases=0))
        self.assertTrue(c.due(inserts=3, releases=0), "the first freeze is due once something is loaded")
        self.assertEqual(c.reconcile(inserts=3, releases=0), "initial")
        self.assertEqual(fake.calls, ["collect", "freeze"], "the initial freeze collects then freezes, no unfreeze")
        # a small load since the freeze is NOT material; a load past the threshold is a cheap fold-in
        self.assertFalse(c.due(inserts=3 + 7, releases=0), "under the threshold does not fire per parse")
        self.assertTrue(c.due(inserts=3 + 8, releases=0))
        fake.calls.clear()
        self.assertEqual(c.reconcile(inserts=3 + 8, releases=0), "load")
        self.assertEqual(fake.calls, ["collect", "freeze"], "a load fold-in does not unfreeze: it walks only the unfrozen")
        # a release since the freeze needs the unfreeze reclaim
        self.assertTrue(c.due(inserts=3 + 8, releases=1))
        fake.calls.clear()
        self.assertEqual(c.reconcile(inserts=3 + 8, releases=1), "release")
        self.assertEqual(fake.calls, ["unfreeze", "collect", "freeze"], "a release reclaim unfreezes, collects, re-freezes")
        self.assertEqual((c.freezes, c.reclaims), (2, 1), "two freezes (initial + load) and one reclaim counted for /perf")

    def test_the_env_switch_turns_it_off(self):
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "off"}))
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "0"}))
        self.assertTrue(gf.enabled_from_env({}), "on by default")
        self.assertTrue(gf.enabled_from_env({"ROMP_GC_FREEZE": "on"}))
        fake = FakeGc()
        c = gf.GcFreeze(enabled=False, gc=fake)
        self.assertFalse(c.due(inserts=100, releases=5))
        self.assertIsNone(c.reconcile(inserts=100, releases=5))
        self.assertEqual(fake.calls, [], "a disabled controller never touches the collector")


class Cyclic:
    """A weakref-able node so a reference cycle can be watched by a weakref oracle."""
    __slots__ = ("other", "__weakref__")


class RealCollector(unittest.TestCase):
    def tearDown(self):
        gc.unfreeze()                                # never leak a freeze to another test
        gc.collect()

    def test_acyclic_dies_by_refcount_under_the_freeze_a_cycle_waits_for_the_reclaim(self):
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        # an acyclic object frozen and then dropped is reclaimed at once by reference counting
        acyclic = Cyclic(); acyclic.other = None
        wa = weakref.ref(acyclic)
        c.reconcile(inserts=1, releases=0)           # initial freeze folds `acyclic` into the frozen set
        del acyclic
        self.assertIsNone(wa(), "an acyclic frozen object dies by refcount when its owner drops it, freeze or no freeze")
        # a reference cycle frozen and then dropped survives a LOAD fold-in and is reclaimed only by a RELEASE reclaim
        a = Cyclic(); b = Cyclic(); a.other = b; b.other = a
        wcyc = weakref.ref(a)
        c.reconcile(inserts=2, releases=0)           # a load fold-in that freezes the cycle
        del a, b
        c.reconcile(inserts=3, releases=0)           # another load fold-in (no release): does NOT unfreeze
        self.assertIsNotNone(wcyc(), "a frozen cycle survives a load fold-in: it is not walked")
        c.reconcile(inserts=3, releases=1)           # a release reclaim: unfreeze, collect, re-freeze
        self.assertIsNone(wcyc(), "the frozen cycle is reclaimed once a release reconcile unfreezes and collects")

    def test_the_gc_hook_still_counts_the_collections_that_run(self):
        seen = []
        cb = lambda phase, info: seen.append(phase)
        gc.callbacks.append(cb)
        try:
            c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
            c.reconcile(inserts=1, releases=0)       # a freeze runs a collection
            c.reconcile(inserts=2, releases=1)       # a reclaim runs one too
            self.assertIn("start", seen, "the gc callbacks fire for the collections a reconcile runs (the /perf hook keeps counting)")
        finally:
            gc.callbacks.remove(cb)

    def test_a_warm_collection_after_the_freeze_walks_far_fewer_objects(self):
        # cold: a heap of cycles the collector must walk and can reclaim
        heap = []
        for _ in range(20000):
            x = Cyclic(); y = Cyclic(); x.other = y; y.other = x
            heap.append(x)
        gc.collect()
        cold_stats = gc.get_stats()[2]["collections"]
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.reconcile(inserts=1, releases=0)           # freeze the heap out of the walk
        # warm: a small new batch of garbage; the full collection now walks only it
        before = gc.get_stats()[2]["collected"]
        junk = []
        for _ in range(200):
            x = Cyclic(); y = Cyclic(); x.other = y; y.other = x
            junk.append(x)
        del junk
        gc.collect()
        warm_collected = gc.get_stats()[2]["collected"] - before
        self.assertLess(warm_collected, 20000, "a warm full collection after the freeze reclaims only the post-freeze garbage, not the frozen heap")
        self.assertGreater(gc.get_freeze_count(), 20000, "the frozen count shows the loaded heap left the collector's walk")


def _uline(sid, t, text, uid, parent=None):
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"type": "user", "timestamp": iso, "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "cwd": "/home/TESTHOST/proj", "message": {"role": "user", "content": text}}


def _aline(sid, t, text, uid, parent):
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"type": "assistant", "timestamp": iso, "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


class NoRereadChurn(unittest.TestCase):
    def tearDown(self):
        gc.unfreeze()
        gc.collect()

    def test_freezing_forces_no_whole_transcript_reread(self):
        """A freeze must not make the reader re-read a transcript it already cached: the record
        cache's whole-read and insert counters do not move when the same file is folded again
        after a freeze."""
        em = load_source("romp_event_model_gcf", os.path.join(BIN, "romp-event-model"))
        sid = "11111111-2222-3333-4444-aaaaaaaaaa01"
        recs = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
        d = tempfile.mkdtemp()
        p = os.path.join(d, sid + ".jsonl")
        Path(p).write_text("".join(json.dumps(r) + "\n" for r in recs))
        em.parse_session(p, rompuuid=sid)                 # first parse: a whole read fills the cache
        s1 = em.record_cache_stats()
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.reconcile(inserts=1, releases=0)                # freeze the loaded records
        em.parse_session(p, rompuuid=sid)                 # re-parse the unchanged file
        s2 = em.record_cache_stats()
        self.assertEqual(s2["inserts"], s1["inserts"], "no new insert: the freeze did not evict the cached records")
        self.assertEqual(s2.get("wholeReads"), s1.get("wholeReads"), "no new whole read: the freeze forced no reread")

    def test_the_load_trigger_fires_off_the_real_record_cache_counter(self):
        """The kernel keys the reconcile on the record cache's real insert counter: parsing transcripts grows it,
        and once it grows past the threshold the controller is due and a reconcile freezes the loaded objects."""
        em = load_source("romp_event_model_gcf2", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        base_ins = int(em.record_cache_stats().get("inserts") or 0)
        for i in range(10):
            sid = "11111111-2222-3333-4444-bbbbbbbb%04d" % i
            recs = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                    _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
            p = os.path.join(d, sid + ".jsonl")
            Path(p).write_text("".join(json.dumps(r) + "\n" for r in recs))
            em.parse_session(p, rompuuid=sid)
        st = em.record_cache_stats()
        inserts = int(st.get("inserts") or 0)
        releases = int(st.get("evictions") or 0) + int(st.get("dropped") or 0)
        self.assertGreaterEqual(inserts - base_ins, 8, "ten parses grew the cache's insert counter past the load threshold")
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=gc)
        self.assertTrue(c.due(inserts, releases), "the load trigger reads the real insert counter and is due")
        frozen_before = gc.get_freeze_count()
        self.assertEqual(c.reconcile(inserts, releases), "initial")
        self.assertGreater(gc.get_freeze_count(), frozen_before, "the reconcile froze the loaded objects out of the collector's walk")


if __name__ == "__main__":
    unittest.main()
