#!/usr/bin/env python3
"""T398 (2026-09-12): a boot parsed two documented live leaves whole with no fallback counted, and nothing on GET /perf named the
road the parse took. The assembly's road counters (serve, fold, restore, full with its reason, bypass, the g:<reason> demotions)
ride asmCheckpoint.parse and the boot-health row, beside asmCheckpoint.removed, the document files removed per reason."""
import json
import os
import sys
import unittest
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_asm_checkpoint import em, G, SID, NOW, Harness, kernel_module, _strip   # noqa: E402


class AssemblyRoadCounters(Harness):
    def setUp(self):
        super().setUp()
        kernel_module()                                   # the kernel's first load refreshes the event model's globals: load it
        #                                                   before any counter is read, so the row and the test see one dict

    def _reset(self):
        for k in list(em._ASM_STATS):
            em._ASM_STATS[k] = 0

    def _boot_row_parse(self):
        """The boot-health row's `parse` as the kernel writes it, over THIS test's event model (the kernel module holds its own
        instance; the row reads whichever `em` the kernel names)."""
        km = kernel_module()
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0], km.em); rows = []
        km._append_restart_cut = lambda row: rows.append(row); km._BOOT_HEALTH_DONE[0] = False; km.em = em
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0], km.em = saved
        self.assertEqual(len(rows), 1)
        return rows[0]["parse"]

    def test_the_roads_ride_the_perf_block_with_the_full_parses_reason(self):
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("roads", records(), sent=sent)
        self.fresh(); self._reset()
        self.parse(path)                                                  # no document yet: a full parse, its reason named
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("full:noDocument"), 1, "%s" % parse)
        self.assertEqual(parse["full"], 1)
        self.assertTrue(self.doc(path))
        self.fresh(); self._reset()
        self.parse(path)                                                  # the document restores
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("restore"), 1, "%s" % parse)
        self.parse(path)                                                  # the same tree served from the entry
        self.assertEqual(em.asm_checkpoint_stats()["parse"]["serve"], 1)
        for k in ("serve", "fold", "full", "bypass", "fallback"):
            self.assertIn(k, parse)

    def test_a_from_zero_read_that_replaces_the_leafs_entry_demotes_and_is_counted_as_such(self):
        """The cascade shape under study: an assembly entry stands, a whole reader replaces the leaf's record entry under a new
        generation, and the next parse's gates demote the entry to a FULL parse that consults no document and counted nothing
        anyone could see; now `g:rewrite` and `full:demoted` name it."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("demote", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); self.parse(path); self._reset()                     # the entry stands, restored from the document
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.pop(path, None)
        em._read_jsonl_entry(path, tail_ok=False)                          # a from-zero read: a fresh generation
        self.parse(path)
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("g:rewrite"), 1, "%s" % parse)
        self.assertEqual(parse.get("restore:afterDemote"), 1, "the demoted entry falls to the restore road (T402): %s" % parse)
        self.assertEqual(parse.get("full:demoted", 0), 0, "%s" % parse)
        row = self._boot_row_parse()
        self.assertEqual((row.get("g:rewrite"), row.get("restore:afterDemote")), (1, 1), "the boot row's values: %r" % row)

    def test_a_refused_standing_document_is_booked_as_refused_not_as_none(self):
        """Round one, medium: the restore's refusal unlinked the document before _assemble decided the reason by a stat, so a
        corrupt standing document was booked full:noDocument and a boot whose documents were all refused read as a boot that
        had none. The refusal is recorded per path before the unlink and the parse books full:refused from it."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("removed", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._asm_ckpt_file(path).write_bytes(b"not a document")
        em._ASM_CKPT_STATS["removed"] = {}
        self.fresh(); self._reset(); self.parse(path)
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["removed"], {"fallback:corrupt": 1}, "%s" % st["removed"])
        self.assertFalse(em._asm_ckpt_file(path).exists())
        self.assertEqual((st["parse"].get("full:refused"), st["parse"].get("full:noDocument", 0)), (1, 0),
                         "a document that stood and did not verify: refused, not none: %s" % st["parse"])
        self.assertEqual(self._boot_row_parse().get("full:refused"), 1, "the boot row carries it")

    def test_the_boot_health_row_carries_the_parses_roads(self):
        km = kernel_module()
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0])
        rows = []
        km._append_restart_cut = lambda row: rows.append(row)
        km._BOOT_HEALTH_DONE[0] = False
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0] = saved
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0].get("parse"), dict, "%r" % rows[0])
        for k in ("serve", "fold", "restore", "full", "bypass", "fallback"):
            self.assertIn(k, rows[0]["parse"], "seeded keys: a row without one means zero: %r" % rows[0]["parse"])
        self.assertEqual(rows[0]["parse"], em.asm_checkpoint_stats()["parse"], "the row is the perf block's parse, values and all")

    def test_a_document_write_clears_the_refusal_slot(self):
        """Follow-up, low 1: a refusal recorded by one parse was never cleared at a document write and the restore road returned
        before the pop, so after a fresh document was written a later parse with NO document standing booked full:refused."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("slot", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._asm_ckpt_file(path).write_bytes(b"not a document")
        self.fresh(); self._reset(); self.parse(path)
        self.assertEqual(em.asm_checkpoint_stats()["parse"].get("full:refused"), 1)
        em._asm_ckpt_note(path, "corrupt")                                  # a JUDGE read's refusal, recorded in the slot
        self.assertTrue(self.doc(path), "a fresh document written")          # the write clears the slot
        self.fresh(); modes = []; self.parse(path, modes); self.assertEqual(modes, ["restore"])   # the restore road: no pop
        cp = em._asm_ckpt_file(path); cp.unlink(); cp.with_name(cp.name + ".meta").unlink(missing_ok=True)
        self.fresh(); self._reset(); self.parse(path)
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual((parse.get("full:noDocument"), parse.get("full:refused", 0)), (1, 0), "no document standing: noDocument: %s" % parse)

    def test_every_road_counter_write_goes_through_the_locked_helper(self):
        """Follow-up, low 3: the lock covered two of ten writes; every increment goes through _asm_stat under _ASM_CKPT_LOCK."""
        import inspect, re
        src = inspect.getsource(em)
        bare = [l.strip() for l in src.splitlines() if "_ASM_STATS[" in l and ("+=" in l or "= _ASM_STATS.get(" in l)
                and "(key, 0) + n" not in l]                                # the helper's own line
        self.assertEqual(bare, [], "bare writes: %r" % bare)
        self.assertGreaterEqual(len(re.findall(r"_asm_stat\(", src)), 10)
        self.assertIn("with _ASM_CKPT_LOCK:", inspect.getsource(em._asm_stat))

    def test_the_boot_sweep_counts_the_documents_it_removes(self):
        """Follow-up, low 6: `removed["sweep"]` had no test."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("swept", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._ASM_CKPT_STATS["removed"] = {}
        os.unlink(path)                                                     # the transcript vanishes: the sweep removes its document
        em.checkpoint_sweep()
        self.assertEqual(em.asm_checkpoint_stats()["removed"], {"sweep": 1})
        self.assertFalse(em._asm_ckpt_file(path).exists())

    def _five_shape_file(self, name):
        """Three turns, an attached compaction, two turns: the document's pre-cut records u1 a1 u2 a2 u3 a3."""
        t0 = NOW
        recs = [G.uline(t0, "first ask", "u1"), G.aline(t0 + 10, "first reply", "a1", "u1", stop="end_turn"),
                G.uline(t0 + 20, "second ask", "u2", "a1"), G.aline(t0 + 30, "second reply", "a2", "u2", stop="end_turn"),
                G.uline(t0 + 40, "third ask", "u3", "a2"), G.aline(t0 + 50, "third reply", "a3", "u3", stop="end_turn"),
                G.compact_line(t0 + 600, "b1", "a3"), G.compact_summary_line(t0 + 601, "s1", "b1"),
                G.uline(t0 + 610, "after the compaction", "u4", "s1"), G.aline(t0 + 620, "fourth reply", "a4", "u4", stop="end_turn"),
                G.uline(t0 + 630, "then more", "u5", "a4"), G.aline(t0 + 640, "fifth reply", "a5", "u5", stop="end_turn")]
        return self.write(name, recs), t0

    def _cold(self, path):
        self.fresh(); saved = em._CKPT_DIR_FN; em._CKPT_DIR_FN = None
        try:
            return _strip(self.parse(path))
        finally:
            em._CKPT_DIR_FN = saved

    def test_a_demoted_entry_falls_to_the_restore_road_only_when_the_tail_chains_at_or_after_the_cut(self):
        """T402 round one: a demoted entry went straight to a whole parse; the restore road stands for a descent only when the
        tail re-parents at or after the document's cut. Five shapes against a COLD whole parse: (a) a rewind onto a pre-cut
        interior record and (b) a /clear fork (a null root) in the tail are graph invalidations the document's byte checks
        cannot see, so they parse whole, as before; (c) an api_error spur after the cut, (d) a rewind onto a post-cut record
        and (e) a rewind onto the LAST pre-cut record take the restore road with no whole read."""
        shapes = {
            "a_rewind_pre_interior": (lambda t0: [G.uline(t0 + 700, "a rewind before the cut", "u_rw", "a1")], "full"),
            "b_clear_fork": (lambda t0: [G.uline(t0 + 700, "a clear fork", "u_fork", None)], "full"),
            "c_api_error_spur": (lambda t0: [G.api_error_line(t0 + 700, "e1", "u5"), G.uline(t0 + 710, "after the spur", "u6", "e1")], "restore"),   # the spur roots at the turn's opener (T209's shape)
            "d_rewind_post_cut": (lambda t0: [G.uline(t0 + 700, "a rewind after the cut", "u_rw2", "a4")], "restore"),
            "e_rewind_last_pre": (lambda t0: [G.uline(t0 + 700, "a rewind onto the cut", "u_rw3", "a3")], "restore"),
        }
        for name, (tail, road) in shapes.items():
            with self.subTest(shape=name):
                path, t0 = self._five_shape_file("shape-" + name)
                self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
                self.fresh(); self.parse(path); self._reset()               # the entry stands, restored from the document
                with em._JSONL_CACHE_LOCK:
                    em._RECORD_CACHE_STATS["wholeReads"] = {}
                with open(path, "a") as fh:
                    for r in tail(t0):
                        fh.write(json.dumps(r) + "\n")
                em._read_jsonl_entry(path, tail_ok=True)                   # the entry grows; the gates see the delta
                tree = self.parse(path)
                em.hydrate(tree, SID)                                       # a restored tree's bodies, so the strip can read them
                tree = _strip(tree)
                parse = em.asm_checkpoint_stats()["parse"]
                self.assertEqual(parse.get("g:descent"), 1, "%s: the descent check demoted the entry: %s" % (name, parse))
                if road == "restore":
                    self.assertEqual(parse.get("restore:afterDemote"), 1, "%s: the restore road: %s" % (name, parse))
                    self.assertEqual(em.record_cache_stats()["wholeReads"], {}, "%s: no whole read" % name)
                else:
                    self.assertEqual(parse.get("full:demoted"), 1, "%s: the whole parse, as before: %s" % (name, parse))
                    self.assertEqual(parse.get("restore:descentRefused"), 1, "%s: the tail re-parents into the prefix: %s" % (name, parse))
                self.assertEqual(tree, self._cold(path), "%s: the tree equals a cold whole parse" % name)


if __name__ == "__main__":
    unittest.main()
