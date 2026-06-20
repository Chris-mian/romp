"""The ledger TOC and the feed cards must deep-link a goal node to the SAME chat turn BY UUID, not by the
old nearest-time heuristic (the user 2026-06-19). Both build_session (the ledger) and build_feed (the cards)
resolve a node's (promptAnchorUuid, anchorUuid) through the ONE shared helper km._node_anchor_uuids, so they
cannot drift apart. This pins the helper's resolution and the shared-call anti-drift property."""
import os
import re
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class NodeAnchorResolution(unittest.TestCase):
    # seg id -> the .turn[data-uuid] anchors (prompt = the segment's trigger / user message; work = its reply)
    SEG_TRIG = {"s1": "u-aaa", "s2": "u-bbb", "s3": "u-ccc"}
    SEG_WORK = {"s1": "a-aaa", "s2": "a-bbb", "s3": "a-ccc"}

    def test_open_node_anchors_to_its_FIRST_trail_segment(self):
        # an OPEN node (not resolved) deep-links to where it was MINTED: trail[0] for BOTH prompt and work.
        nd = {"trail": ["s1", "s2", "s3"]}
        prompt, work = km._node_anchor_uuids(nd, self.SEG_TRIG, self.SEG_WORK, resolved=False)
        self.assertEqual(prompt, "u-aaa")        # trail[0] trigger
        self.assertEqual(work, "a-aaa")          # trail[0] work (minted)

    def test_resolved_node_work_anchors_to_its_LAST_trail_segment(self):
        # a RESOLVED node (done / blocked) keeps the prompt on trail[0] but moves the WORK anchor to trail[-1]
        # (where it was checked off / blocked) — the mt convention the mark + time zones jump to.
        nd = {"trail": ["s1", "s2", "s3"]}
        prompt, work = km._node_anchor_uuids(nd, self.SEG_TRIG, self.SEG_WORK, resolved=True)
        self.assertEqual(prompt, "u-aaa")        # trail[0] trigger (the minting message) — unchanged
        self.assertEqual(work, "a-ccc")          # trail[-1] work (the resolution)

    def test_single_segment_trail(self):
        nd = {"trail": ["s2"]}
        self.assertEqual(km._node_anchor_uuids(nd, self.SEG_TRIG, self.SEG_WORK, True), ("u-bbb", "a-bbb"))
        self.assertEqual(km._node_anchor_uuids(nd, self.SEG_TRIG, self.SEG_WORK, False), ("u-bbb", "a-bbb"))

    def test_empty_trail_yields_no_anchors(self):
        # no filed segments → no uuid to land on → (None, None); the render then falls back to nearest-time.
        self.assertEqual(km._node_anchor_uuids({"trail": []}, self.SEG_TRIG, self.SEG_WORK, True), (None, None))
        self.assertEqual(km._node_anchor_uuids({}, self.SEG_TRIG, self.SEG_WORK, False), (None, None))

    def test_segment_missing_from_the_map_degrades_to_None(self):
        # a trail segment the chat parse didn't surface (rewound / orphaned) → None for that anchor, not a throw.
        nd = {"trail": ["sX", "sY"]}
        self.assertEqual(km._node_anchor_uuids(nd, self.SEG_TRIG, self.SEG_WORK, True), (None, None))


class SharedHelperAntiDrift(unittest.TestCase):
    """The whole point of the helper: the feed and the ledger can't drift. Guard that BOTH build_feed and
    build_session resolve node anchors through km._node_anchor_uuids (not a private re-implementation)."""

    def test_both_builders_call_the_one_helper(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        # the helper is defined once
        self.assertEqual(len(re.findall(r"def _node_anchor_uuids\(", src)), 1, "helper defined exactly once")
        # both view-builders bodies reference it
        def body(fn):
            m = re.search(r"\ndef %s\(.*?(?=\ndef )" % fn, src, re.S)
            self.assertIsNotNone(m, "found %s" % fn)
            return m.group(0)
        self.assertIn("_node_anchor_uuids(", body("build_session"), "the ledger resolves anchors via the helper")
        self.assertIn("_node_anchor_uuids(", body("build_feed"), "the feed resolves anchors via the helper")


class GlowByIdRouting(unittest.TestCase):
    """The timeline->chat glow lights a hovered bar's segments BY ID (their atom uuids), not a +/-2s time
    window — the time heuristic the user banned (2026-06-19/20). Pin the kernel side. (The functional
    _segment_atom_uuids test lives with the session fixture in test_kernel.py's owner's suite; here we pin
    the helper's presence + the handler wiring without that fixture.)"""

    def test_segment_atom_uuids_helper_exists(self):
        self.assertTrue(hasattr(km, "_segment_atom_uuids"), "the seg->atom-uuid resolver exists")

    def test_timeline_hover_glows_by_uuid_not_time_range(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn("_segment_atom_uuids(hsid, seg_ids", src)         # the handler resolves segs -> atom uuids
        self.assertIn('"glowTurns", "groups": groups, "mids": []', src)
        self.assertIn('"uuids": uuids', src)                            # sent as uuids...
        self.assertNotIn('"ranges": [[t0, t1]]', src)                  # ...not the old +/-2s time window


if __name__ == "__main__":
    unittest.main()
