#!/usr/bin/env python3
"""Tests for build_timeline's `data.judging` feed (the judging-timeline band under the lanes).

`_derive_judging` reshapes the REAL artifacts the summarizer judges write — captions/<sid>.jsonl,
the goal tree's nodes, archive/<sid>.json — into {judge, sid, t, kind, text} marks the timeline view
draws as a second timeline. Synthetic data only (placeholder UUID, invented captions/goals)."""
import os
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")
# romp-judge must load first: romp-kernel imports it as `jd` at module load.
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 7200          # a 2-hour window for the derivation


def marks(caps, nodes, t0=T0):
    out = []
    km._derive_judging(SID, caps, {"nodes": nodes}, t0, out)
    return out


class DeriveJudging(unittest.TestCase):
    def test_captioner_one_mark_per_caption_grain_preserved(self):
        caps = {"u1": {"id": "u1", "grain": "segment", "t": NOW - 100, "caption": "Fixed the flicker"},
                "u2": {"id": "u2", "grain": "turn", "t": NOW - 40, "caption": "Wrapped the turn"}}
        cap = [m for m in marks(caps, {}) if m["judge"] == "captioner"]
        self.assertEqual(len(cap), 2)
        self.assertEqual({m["kind"] for m in cap}, {"segment", "turn"})
        self.assertTrue(all(m["sid"] == SID for m in cap))
        self.assertEqual(next(m for m in cap if m["kind"] == "turn")["text"], "Wrapped the turn")

    def test_captions_outside_the_window_are_dropped(self):
        caps = {"old": {"id": "old", "grain": "segment", "t": NOW - 99999, "caption": "ancient"}}
        self.assertEqual(marks(caps, {}), [])

    def test_captioner_volume_capped_per_session(self):
        caps = {str(i): {"id": str(i), "grain": "segment", "t": NOW - (200 - i), "caption": "c%d" % i}
                for i in range(km.JUDGE_CAP_LIMIT + 25)}
        cap = [m for m in marks(caps, {}) if m["judge"] == "captioner"]
        self.assertEqual(len(cap), km.JUDGE_CAP_LIMIT, "keeps only the most-recent JUDGE_CAP_LIMIT")
        # the kept set is the NEWEST ones (largest t)
        self.assertEqual(min(m["t"] for m in cap), NOW - (200 - 25))

    def test_planner_mint_sub_done_block(self):
        nodes = {
            "g1": {"id": "g1", "parentId": None, "t": NOW - 200, "text": "Top goal"},          # mint
            "g2": {"id": "g2", "parentId": "g1", "t": NOW - 150, "text": "a step"},             # sub
            "g3": {"id": "g3", "parentId": "g1", "t": NOW - 300, "text": "ship it",
                   "nodeComplete": True, "doneWhy": "shipped", "mt": NOW - 90},                 # sub + done
            "g4": {"id": "g4", "parentId": "g1", "t": NOW - 250, "text": "blocked one",
                   "blocked": True, "blockWhy": "needs a key", "mt": NOW - 80},                 # sub + block
        }
        kinds = {m["kind"] for m in marks({}, nodes) if m["judge"] == "planner"}
        self.assertEqual(kinds, {"mint", "sub", "done", "block"})

    def test_grouper_courier_closer_keyed_off_node_flags(self):
        nodes = {
            "u": {"id": "u", "parentId": None, "t": NOW - 100, "text": "umbrella", "umbrella": True},
            "h": {"id": "h", "parentId": None, "t": NOW - 90, "text": "handoff goal",
                  "origin": {"peer": "PEER", "msgId": "m1"}},
            "c": {"id": "c", "parentId": "x", "t": NOW - 300, "text": "swept goal",
                  "negComplete": True, "nodeComplete": True, "doneWhy": "no work left", "mt": NOW - 70},
        }
        out = marks({}, nodes)
        by_judge = {m["judge"] for m in out}
        self.assertIn("grouper", by_judge)
        self.assertIn("courier", by_judge)
        self.assertIn("closer", by_judge)
        self.assertEqual(next(m for m in out if m["judge"] == "grouper")["kind"], "group")
        self.assertEqual(next(m for m in out if m["judge"] == "courier")["kind"], "plant")
        self.assertEqual(next(m for m in out if m["judge"] == "closer")["kind"], "close")
        # an umbrella / handoff node is owned by its judge — NOT also double-counted as a planner place
        planner_texts = {m["text"] for m in out if m["judge"] == "planner"}
        self.assertNotIn("umbrella", planner_texts)
        self.assertNotIn("handoff goal", planner_texts)

    def test_closer_wins_over_planner_done_for_a_swept_node(self):
        nodes = {"c": {"id": "c", "parentId": "x", "t": NOW - 300, "text": "swept",
                       "negComplete": True, "nodeComplete": True, "doneWhy": "done", "mt": NOW - 70}}
        completions = [m for m in marks({}, nodes) if m["kind"] in ("close", "done")]
        self.assertEqual([m["judge"] for m in completions], ["closer"], "negComplete → closer, not planner-done")

    def test_node_without_t_is_skipped(self):
        self.assertEqual(marks({}, {"bad": {"id": "bad", "parentId": None, "text": "no t"}}), [])

    def test_distiller_keyed_off_distilledMt_with_the_summary(self):
        nodes = {"g1": {"id": "g1", "parentId": None, "t": NOW - 300, "text": "Top goal",
                        "nodeComplete": True, "doneWhy": "done", "mt": NOW - 80,
                        "distilledMt": NOW - 70, "summary": "The key takeaway."}}
        dj = [m for m in marks({}, nodes) if m["judge"] == "distiller"]
        self.assertEqual(len(dj), 1)
        self.assertEqual(dj[0]["kind"], "distill")
        self.assertEqual(dj[0]["t"], NOW - 70)
        self.assertEqual(dj[0]["text"], "The key takeaway.", "the distiller mark carries the goal's summary")


if __name__ == "__main__":
    unittest.main()
