#!/usr/bin/env python3
"""Stage one b (2026-09-15), the restore-equality oracle over the settled-turn cut as an independent module: nineteen
transcript shapes, each parsed cold and then through the checkpoint writer and the restore, and for EVERY shape the tree the
document road yields, hydrated, equals the cold parse, whether the road was a restore, a refusal at restore (the cold walk
serves), or a refusal at write time under a NAMED skip reason. No shape may restore to a differing world, and no shape may
be refused for an unnamed reason. The shapes are the ones the review of the stage's first head enumerated (the verifier's
list), built from the golden builders: synthetic transcripts only."""
import json
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import test_asm_checkpoint as T   # noqa: E402  the harness, the builders and the shared event-model module
import test_event_model_golden as G   # noqa: E402

em, NOW, SID = T.em, T.NOW, T.SID
compacting_variant, turns_after, ring_records, strip, doc_of = T.compacting_variant, T._turns_after, T._ring_records, T._strip, T._doc

NAMED_SKIPS = set(em._ASM_SKIP_STRUCTURAL) | {"stat", "offsets", "write", "noEntry", "noBoundary", "written", "restored"}


def _last(recs):
    return T._last_uuid(recs)


def _opener(t=NOW - 3600, n=3):
    """`n` settled turns chained from a null root."""
    recs = [G.uline(t, "opening ask", "u1", None), G.aline(t + 5, "opening reply", "a1", "u1", stop="end_turn")]
    return recs + turns_after(recs, "op", n - 1, dt=30)


def _shapes():
    """name -> (records at write time, records appended after the write or None)."""
    base = _opener()
    mcd = list(G.SINGLE_FILE["manual_compact_detached"][0]())
    shapes = {}
    shapes["plain"] = (base, None)
    shapes["compacted"] = (compacting_variant(base, "c"), None)
    shapes["adopted manual compact pair"] = (mcd + turns_after(mcd, "m", 2), None)
    shapes["cut exactly at an adopted pair"] = (mcd + turns_after(mcd, "m1", 1), None)
    shapes["the stage-one ring"] = (ring_records() + turns_after(ring_records(), "r", 2), None)
    ring = ring_records()
    shapes["a ring across the cut"] = (ring + [G.uline(NOW + 200, "re-rooted onto the ring's child", "u_late", "a1"),
                                               G.aline(NOW + 205, "answered from there", "a_late", "u_late", stop="end_turn")], None)
    shapes["an open last turn"] = (base + [G.uline(NOW + 900, "still being answered", "u_open", _last(base))], None)
    shapes["a single turn"] = (base[:2], None)
    dup = base + [G.uline(NOW + 900, "the same record twice", "d1", _last(base)), G.uline(NOW + 900, "the same record twice", "d1", _last(base)),
                  G.aline(NOW + 905, "reply", "a_d1", "d1", stop="end_turn")]
    shapes["repeated uuids"] = (dup, None)
    odd = base + turns_after(base, "ts", 1)
    odd[2] = dict(odd[2]); odd[2]["timestamp"] = None                      # a null stamp (the parse repairs it from the last one)
    odd[3] = dict(odd[3]); del odd[3]["timestamp"]                         # a missing stamp
    shapes["non-string timestamps"] = (odd, None)                          # (a NUMERIC stamp is refused by the parser itself, before any
    #                                                                          document: parse_z reads a string; outside this oracle)
    shapes["tail first record whose parent differs after last-wins"] = (mcd + turns_after(mcd, "lw", 1), None)   # u2's raw parent the stdout, resolved the summary
    leaf_child = base + [G.uline(NOW + 900, "the pre-cut leaf's only child lands in the tail", "u_child", _last(base)),
                         G.aline(NOW + 905, "reply", "a_child", "u_child", stop="end_turn")]
    shapes["a pre-cut leaf gaining its only child in the tail"] = (base, leaf_child[len(base):])
    rep = base + [G.uline(NOW + 900, "re-parented onto the opener", "u_rp", "a1"), G.aline(NOW + 905, "reply", "a_rp", "u_rp", stop="end_turn")]
    shapes["two settled turns then a re-parented turn"] = (rep, None)
    shapes["growth between write and restore onto a pre-cut record"] = (base, [G.uline(NOW + 900, "rewound onto the opener", "u_g", "a1"),
                                                                                G.aline(NOW + 905, "reply", "a_g", "u_g", stop="end_turn")])
    tool = [G.uline(NOW - 3600, "run it", "u1", None), G.aline(NOW - 3595, "running", "a1", "u1", tools=("Bash",), stop="tool_use"),
            G.trline(NOW - 3590, "tu_a1_0", "tr1", "a1"), G.aline(NOW - 3585, "done", "a1b", "tr1", stop="end_turn")]
    shapes["a tool pair split by the cut"] = (tool + turns_after(tool, "tp", 2), None)
    shapes["a sidechain record in the tail"] = (base, [dict(G.uline(NOW + 900, "a side ask", "sc1", _last(base)), isSidechain=True),
                                                       G.uline(NOW + 910, "then the main line", "u_sc", _last(base)),
                                                       G.aline(NOW + 915, "reply", "a_sc", "u_sc", stop="end_turn")])
    shapes["a summary record in the tail"] = (base, [G.compact_summary_line(NOW + 900, "s_t", _last(base)),
                                                     G.uline(NOW + 910, "after the summary", "u_s", "s_t"), G.aline(NOW + 915, "reply", "a_s", "u_s", stop="end_turn")])
    sup = base + [G.uline(NOW + 900, "a later copy of the opener's reply uuid", "a1", _last(base)),   # a1 superseded last-wins
                  G.uline(NOW + 910, "parented on the superseded uuid", "u_sup", "a1"), G.aline(NOW + 915, "reply", "a_sup", "u_sup", stop="end_turn")]
    shapes["a pre-cut record superseded by last-wins that a tail record parents on"] = (sup, None)
    att = [G.uline(NOW - 3600, "hello", "u1", None), G.aline(NOW - 3595, "hi", "a1", "u1", stop="end_turn"), G.attline(NOW - 3594, "a queued prompt", "att_1", "a1"),
           G.uline(NOW - 3590, "second", "u2", "a1"), G.aline(NOW - 3585, "reply", "a2", "u2", stop="end_turn")]   # nothing parents on att_1
    att = att + turns_after(att, "at", 2)
    shapes["the attachment shape"] = (att + [G.uline(NOW + 900, "reusing the attachment's uuid", "att_1", _last(att)),
                                             G.aline(NOW + 905, "answered", "a_att", "att_1", stop="end_turn")], None)
    return shapes


class SettledCutOracle(T.Harness):
    def test_every_shape_equals_the_cold_parse_or_is_refused_under_a_named_reason(self):
        shapes = _shapes()
        self.assertEqual(len(shapes), 19, sorted(shapes))
        roads = {}
        for name, (recs, later) in shapes.items():
            with self.subTest(shape=name):
                path = self.write("oracle-" + "".join(ch if ch.isalnum() else "-" for ch in name)[:48], recs)
                self.fresh(); self.parse(path)
                em._ASM_CKPT_STATS["skipped"] = {}; em._ASM_CKPT_STATS["fallbacks"] = {}
                wrote = self.doc(path)
                if later:
                    pp = Path(path); pp.write_text(pp.read_text() + "".join(json.dumps(r) + "\n" for r in later))
                cold = self.cold(path)
                if not wrote:
                    skipped = em.asm_checkpoint_stats()["skipped"]
                    self.assertEqual(len(skipped), 1, "%s: one named reason: %s" % (name, skipped))
                    self.assertTrue(set(skipped) <= NAMED_SKIPS, "%s: a named refusal: %s" % (name, skipped))
                    roads[name] = "skip:" + next(iter(skipped))
                self.fresh(); modes = []
                tree = self.parse(path, modes); em.hydrate(tree, SID)
                self.assertEqual(strip(tree), cold, "%s: the document road equals the cold parse" % name)
                if wrote:
                    roads[name] = "restore" if modes == ["restore"] else "refused"
                    if modes != ["restore"]:
                        # a refusal at restore is booked on the restore's own counters (the chain proof), never silent
                        self.assertGreater(em._ASM_STATS.get("restore:chainRefused", 0), 0, "%s: the refusal is counted" % name)
                self.fresh(); modes = []
                tree = self.parse(path, modes); em.hydrate(tree, SID)
                self.assertEqual(strip(tree), cold, "%s: and the parse after the refusal's offered rewrite equals it too" % name)
        self.assertEqual(len(roads), 19, roads)
        restored = sorted(n for n, r in roads.items() if r == "restore")
        self.assertGreaterEqual(len(restored), 10, "most shapes restore: %s" % roads)
        for name in ("plain", "compacted", "adopted manual compact pair", "the stage-one ring", "an open last turn", "a tool pair split by the cut"):
            self.assertEqual(roads[name], "restore", "%s restores: %s" % (name, roads))
        self.assertEqual(roads["a single turn"], "skip:noCut")
        self.assertEqual(roads["a ring across the cut"], "skip:reuse", roads)                       # the three refusals the body names,
        self.assertEqual(roads["a pre-cut record superseded by last-wins that a tail record parents on"], "skip:reuse", roads)   # pinned so a
        self.assertEqual(roads["two settled turns then a re-parented turn"], "skip:unsplittable", roads)   # verdict flip cannot pass (1695 low 5)
        self.assertEqual(roads["the attachment shape"], "restore", "the cut falls before the attachment; the pair is the tail: %s" % roads)


if __name__ == "__main__":
    unittest.main()
