#!/usr/bin/env python3
"""T401 (5b), the boot arc: the chat merge sets over a RESTORED session read the pre-cut turns above the echo floor through the
index's light facts instead of building every atom of those turns. The 5a read boot (01:28 UTC 2026-09-14) hydrated 206 MB
of user texts under push and connect through `_atom_user_texts<-_merge_tx_sets`, and the earlier read built 56,663 atoms
there, most of them assistant rows the derivation never needed: a pre-cut turn above the floor contributes its uuids and its
text-bearing uuids from the turn scalars already, so only its USER rows with text need building and reading. The derivation
stays EQUAL to the whole build's: every golden made to compact, at several floors, compared as the full projection the landing
check reads (the cold oracle); the floor's semantics are untouched. Synthetic fixtures only."""
import json
import os
import sys
import unittest
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import test_asm_checkpoint as TA   # noqa: E402  the hermetic kernel, the goldens and the checkpoint harness

em = TA.em
km = TA.kernel_module()
G = TA.G
SID = "11111111-2222-4333-8444-0000000000e5"          # this module's own synthetic sid


def _sets(session, floor):
    km._merge_sets_memo.clear()                               # memoized per sid on the session object: a fresh derivation each call
    u, tu, tx, tt, hf = km._merge_tx_sets(session, SID, floor)
    return (sorted(u), sorted(tu), sorted(tx), dict(tt), hf)


def _reference(session, floor):
    """The derivation as it was before 5b, over the same tree: every atom of a pre-cut turn at or above the floor built and read
    (the cold oracle for the sets; the floor's semantics are the same on both roads)."""
    tx_uuids, tx_text_uuids, tx_texts, tx_text_t = set(), set(), set(), {}
    for turn in session["turns"]:
        pcs = em.turn_scalar(turn, "pcs")
        if pcs is not None:
            tx_uuids.update(u for u in turn["uuids"] if u)
            tx_text_uuids.update(pcs)
            if floor is None or (turn.get("maxT") or 0) < floor:
                continue
        for a in turn["atoms"]:
            if a.get("uuid"):
                tx_uuids.add(a["uuid"])
                if km._atom_prose_chars(a) > 0:
                    tx_text_uuids.add(a["uuid"])
            for t in km._atom_user_texts(a):
                tx_texts.add(t)
                tx_text_t[t] = max(tx_text_t.get(t, 0), float(a.get("t") or 0))
    return (sorted(tx_uuids), sorted(tx_text_uuids), sorted(tx_texts), dict(tx_text_t), km._human_turn_floor(session))


def _user_rows_with_text_above(tree, floor):
    """The count of restored pre-cut user rows with text in turns at or above the floor, read from the DOCUMENT rows' recorded
    scalars (type, the lazy header's text bit, an inline body) without building anything: the bound the derivation's builds must
    stay under, taken before the derivation runs (round two, low 4)."""
    n = 0
    for t in tree["turns"]:
        la = t.get("atoms")
        if not isinstance(la, em.LazyAtoms) or floor is None or (t.get("maxT") or 0) < floor:
            continue
        for k in la._rows:
            row = la._index._row(k)
            sc = row.get("s") or {}
            typ = sc.get("type") or ({"u": "user", "a": "assistant", "s": "system"}.get(la._index.records[row["r"]][2], "user") if row.get("r") is not None else None)
            if typ != "user":
                continue
            lz = row.get("lz")
            if (lz is not None and lz.get("nt")) or (lz is None and "m" in row):
                n += 1
    return n


def _floors(whole):
    """The floors that stress the derivation: none (no live echo), a floor exactly at a pre-cut user row's time, a floor between
    two turns, a floor days back (a dropped echo), and one past the newest atom (nothing above it)."""
    ts = sorted(float(a.get("t") or 0) for t in whole["turns"] for a in (t.get("atoms") or []) if a.get("type") == "user" and a.get("t"))
    mid = ts[len(ts) // 2] if ts else 0.0
    return [None, mid, mid + 0.5, (ts[0] - 3 * 86400) if ts else 0.0, (ts[-1] + 1) if ts else 1.0]


class RestoredSetsEqualTheWholeBuilds(TA.Harness):
    def test_every_golden_made_to_compact_gives_the_same_five_at_every_floor_and_builds_only_user_rows_with_text(self):
        for name in sorted(G.SINGLE_FILE):
            records, sent = G.SINGLE_FILE[name]
            path = self.write("variant-" + name, TA.compacting_variant(records(), name[:6]), sent=sent)
            whole = self.cold(path)
            self.fresh(); self.parse(path); self.assertTrue(self.doc(path), "%s: a document is written: %s" % (name, em.asm_checkpoint_stats()))
            self.fresh(); modes = []; tree = self.parse(path, modes)
            self.assertEqual(modes, ["restore"], name)
            for floor in _floors(whole):
                with self.subTest(scenario=name, floor=floor):
                    self.fresh(); tree = self.parse(path)                          # a fresh restore: nothing built yet
                    expect_rows = _user_rows_with_text_above(tree, floor)          # from the recorded scalars, BEFORE the derivation
                    m0 = em._ASM_INDEX_STATS["materialized"]
                    got = _sets(tree, floor)
                    built = em._ASM_INDEX_STATS["materialized"] - m0
                    self.fresh(); ref_tree = self.parse(path)
                    want = _reference(ref_tree, floor)                             # today's road over another fresh restore
                    self.assertEqual(got, want, "the five sets over the light road equal the every-atom road's")
                    self.assertLessEqual(built, expect_rows, "%s at floor %r: only user rows with text above the floor are built (%d built, %d such rows)" % (name, floor, built, expect_rows))
                    if floor is None:
                        self.assertEqual(built, 0, "no floor: no pre-cut atom built")


class TheShapesTheFloorStresses(TA.Harness):
    """Synthetic restored trees through the real index: a user row above and an assistant row below the floor inside one turn,
    a turn with no user text, a row whose light facts lack the text bit, an echo exactly at the floor, a dropped echo days old."""

    def _tree(self, rows_spec, floor_turn_max):
        """A one-turn restored tree over a synthetic index. rows_spec: (kind, t, has_text, lz_or_None) per row."""
        recs = [["r%d" % i, None, ("u" if k == "user" else "a"), None, i, t, 0, None, None, None] for i, (k, t, nt, lz) in enumerate(rows_spec)]
        rows = []
        for i, (k, t, nt, lz) in enumerate(rows_spec):
            row = {"r": i, "s": {"type": k, "author": ("human" if k == "user" else None), "t": t}, "seq": i}
            if k == "user" and nt:
                row["m"] = {"role": "user", "content": "a prompt at %d" % t}          # a user row WITH text carries its body inline: no
                #                                                                        transcript stands behind this synthetic index to
                #                                                                        hydrate from, and an inline row is flagged for the
                #                                                                        build (its text bit unknown: the safe road builds it)
            elif lz is not None:
                row["lz"] = dict(lz, k=("user" if k == "user" else "assistant"), h="00000000", nt=nt); row["i"] = i
            rows.append(json.dumps(row, separators=(",", ":")))
        index = em.LazyIndex({"atoms": rows, "records": recs, "fsids": []}, SID, self.td / "shapes.jsonl")
        atoms = em.LazyAtoms(index, range(len(rows)))
        turn = {"id": "t1", "t": rows_spec[0][1], "end": floor_turn_max, "ended": True, "pre": True, "atoms": atoms,
                "uuids": [r[0] for r in recs], "maxT": floor_turn_max, "pcs": [], "hT": None, "lastT": floor_turn_max, "segs": []}
        return {"turns": [turn], "cutTurn": 1}, index

    def _run(self, tree, floor):
        km._merge_sets_memo.clear()
        m0 = em._ASM_INDEX_STATS["materialized"]
        b0 = km._merge_sets_stats.get("builtAboveFloor", 0)
        out = km._merge_tx_sets(tree, SID, floor)
        return out, em._ASM_INDEX_STATS["materialized"] - m0, km._merge_sets_stats.get("builtAboveFloor", 0) - b0

    def test_a_user_row_above_and_an_assistant_row_below_the_floor_builds_the_user_row_alone(self):
        tree, _ = self._tree([("assistant", 1000, True, {"pc": 40}), ("user", 1100, True, {"ir": False})], 1100)
        out, built, above = self._run(tree, 1050)                 # the turn's maxT is above the floor: the derivation reads it
        self.assertEqual((built, above), (1, 1), "the user row alone is built; the assistant row below the floor never is")
        self.assertEqual(sorted(out[0]), ["r0", "r1"], "the uuids come from the turn scalars")

    def test_a_turn_with_no_user_text_builds_nothing(self):
        tree, _ = self._tree([("assistant", 1000, True, {"pc": 40}), ("user", 1100, False, {"ir": False})], 1100)
        out, built, above = self._run(tree, 900)
        self.assertEqual((built, above), (0, 0), "a textless user row contributes no landing key and is never built")
        self.assertEqual(sorted(out[2]), [])

    def test_a_row_whose_light_facts_lack_the_text_bit_is_built_the_safe_road(self):
        tree, _ = self._tree([("user", 1000, True, None)], 1000)  # an inline-body row: no lazy header, so no text bit in the facts
        out, built, above = self._run(tree, 900)
        self.assertEqual((built, above), (1, 1), "unknown text: the row is built and read, never skipped")
        self.assertEqual(len(out[2]), 1, "its text is a landing key")

    def test_an_echo_exactly_at_the_floor_reads_the_turn(self):
        tree, _ = self._tree([("user", 1000, True, {"ir": False})], 1000)
        out, built, above = self._run(tree, 1000)                 # maxT == floor: at or after the send, so it is read
        self.assertEqual((built, above), (1, 1))

    def test_a_dropped_echo_days_old_reads_every_turn_above_it_and_the_floor_age_is_counted(self):
        tree, _ = self._tree([("user", 1000, True, {"ir": False}), ("assistant", 1060, True, {"pc": 10})], 1060)
        km._merge_sets_stats["floorAgeMaxS"] = 0.0
        out, built, above = self._run(tree, 1060 - 3 * 86400)
        self.assertEqual((built, above), (1, 1), "the user row with text is built; the assistant row is not")
        self.assertAlmostEqual(km._merge_sets_stats["floorAgeMaxS"], 3 * 86400, delta=1.0, msg="the floor's age at the newest atom")

    def test_three_forced_misses_over_one_tree_count_builds_once(self):
        """Round two, low 1: builtAboveFloor counted rows READ above the floor (3, 3, 3 over three misses); it counts BUILDS (1, 0, 0)."""
        tree, _ = self._tree([("user", 1000, True, None), ("assistant", 1060, True, {"pc": 10})], 1060)
        deltas = [self._run(tree, 900)[2] for _ in range(3)]
        self.assertEqual(deltas, [1, 0, 0], "the first miss builds the user row; the next two find it built")

    def test_the_floor_age_reads_from_the_newest_atom_over_every_turn_and_skips_a_zero_floor(self):
        """Round two, low 2: the age was taken from pre-turn maxT alone (the top of the pre-cut region) and a 0.0 floor latched the
        gauge at epoch scale. The newest atom over every turn, the live tail included; a zero floor records nothing."""
        tree, _ = self._tree([("user", 1000, True, None)], 1000)
        tree["turns"].append({"id": "t2", "t": 5000, "end": 5000, "ended": True, "atoms": [                 # a plain tail turn
            {"type": "user", "author": "human", "uuid": "z1", "t": 5000, "message": {"role": "user", "content": "tail prompt"}}]})
        km._merge_sets_stats["floorAgeMaxS"] = 0.0
        self._run(tree, 900)
        self.assertAlmostEqual(km._merge_sets_stats["floorAgeMaxS"], 5000 - 900, delta=0.5, msg="from the tail's newest atom, not the pre-cut top")
        km._merge_sets_stats["floorAgeMaxS"] = 0.0
        self._run(tree, 0.0)
        self.assertEqual(km._merge_sets_stats["floorAgeMaxS"], 0.0, "a zero floor (an echo with no send time) records no age")

    def test_a_turn_below_the_floor_is_skipped_whole(self):
        tree, _ = self._tree([("user", 1000, True, {"ir": False})], 1000)
        out, built, above = self._run(tree, 2000)
        self.assertEqual((built, above), (0, 0))

    def test_the_report_carries_the_two_counters(self):
        rep = km._merge_sets_report()
        self.assertIn("floorAgeMaxS", rep); self.assertIn("builtAboveFloor", rep)


class ReadersOfTheFiveOutputs(unittest.TestCase):
    def test_every_reader_of_the_merge_sets_reads_fields_the_light_facts_carry(self):
        """The census the design asked for: every caller of _merge_tx_sets and every consumer of its five outputs reads uuids, texts,
        the newest time per text and the human floor, none of which needs a field the light facts lack (type, uuid, t, author, the
        interrupt flag, the text bit); the texts themselves come from built rows as before."""
        src = open(km.__file__, encoding="utf-8").read()
        callers = [l for l in src.splitlines() if "_merge_tx_sets(" in l and "def _merge_tx_sets" not in l]
        self.assertEqual(len(callers), 1, callers)
        self.assertIn("tx_uuids, tx_text_uuids, tx_texts, tx_text_t, human_floor = _merge_tx_sets(session, sid, echo_floor)", callers[0])
        self.assertIn("be.prune_live(sid, tx_uuids, tx_text_t, human_floor)", src, "prune_live reads uuids, the text times and the floor")
        self.assertIn("in tx_texts for k in sb.echo_keys(text)", src, "the landing check reads the texts")


if __name__ == "__main__":
    unittest.main()
