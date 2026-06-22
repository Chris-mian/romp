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


class SegmentOfUuid(unittest.TestCase):
    """The inverse resolver behind the chat-dot hover: one hovered atom uuid -> (its segment id, ALL of that
    segment's atom uuids). Pins #2 (which feed card owns it) + #3 (which sibling rows light) to EXACT segment
    membership, never a time window. _sessions/_parse/em.segments are stubbed so no on-disk fixture is needed."""

    SEGS = [
        {"id": "s1", "atoms": [{"uuid": "u1"}, {"uuid": "a1"}]},
        {"id": "s2", "atoms": [{"uuid": "u2"}, {"uuid": "a2"}, {"uuid": "a3"}]},
    ]

    def setUp(self):
        self._orig = (km._sessions, km._parse, km.em.segments)
        km._sessions = lambda now: [{"sid": "S", "path": "P"}]
        km._parse = lambda path, sid, now: {"turns": [{"segs": self.SEGS}]}
        km.em.segments = lambda turn: turn["segs"]

    def tearDown(self):
        km._sessions, km._parse, km.em.segments = self._orig

    def test_any_atom_resolves_to_its_segment_and_ALL_its_uuids(self):
        # hovering the middle atom of s2 lights the whole segment (all 3 rows) and names s2 as the card owner
        self.assertEqual(km._segment_of_uuid("S", "a2", 0), ("s2", ["u2", "a2", "a3"]))

    def test_the_trigger_atom_resolves_the_same_as_any_other(self):
        self.assertEqual(km._segment_of_uuid("S", "u1", 0), ("s1", ["u1", "a1"]))

    def test_unknown_uuid_is_None_not_a_throw(self):
        self.assertEqual(km._segment_of_uuid("S", "nope", 0), (None, []))

    def test_empty_uuid_short_circuits(self):
        # the chat 'leave' event carries no uuid -> resolve to nothing -> the handler then clears both surfaces
        self.assertEqual(km._segment_of_uuid("S", "", 0), (None, []))

    def test_unknown_session_is_None(self):
        self.assertEqual(km._segment_of_uuid("MISSING", "a2", 0), (None, []))


class ChatAndFeedHoverRouting(unittest.TestCase):
    """The hover graph is now bidirectional and BY ID: a feed-card hover glows its chat rows (#1 feed->chat),
    and a chat-dot hover lights the owning feed card (#2) + every sibling row in its segment (#3). Pin the
    kernel wiring (the functional resolvers are pinned above + in the owner's fixture suite)."""

    SRC = open(os.path.join(BIN, "romp-kernel")).read()

    def test_inverse_resolver_exists(self):
        self.assertTrue(hasattr(km, "_segment_of_uuid"), "the uuid->segment resolver exists")

    def test_feed_card_hover_glows_chat_by_uuid(self):
        # #1: showAskPath resolves the goal's segments -> their atom uuids -> a chat glow (distinct var gsid)
        self.assertIn("_segment_atom_uuids(gsid, seg_ids", self.SRC)
        self.assertIn('_send_to_app("chat", {"type": "glowTurns"', self.SRC)

    def test_chat_dot_hover_lights_owning_feed_card(self):
        # #2: the dotHover branch maps the hovered atom's segment -> its top feed card(s)
        self.assertIn("_segment_of_uuid(hsid, huuid", self.SRC)
        self.assertIn("_cards_for_segments(hsid, [seg_id])", self.SRC)
        self.assertIn('_send_to_app("feed", {"type": "hoverCards"', self.SRC)

    def test_chat_dot_hover_glows_its_whole_segment(self):
        # #3: the same branch glows EVERY atom uuid in the hovered segment (the sibling dots), by id
        self.assertIn('"sid": hsid, "uuids": seg_uuids', self.SRC)

    def test_ledger_bullet_hover_stays_timeline_only(self):
        # the feed/chat extension is gated to dotHover; a ledgerHover (TOC bullet) must not stomp the glow
        self.assertIn('if msg.get("type") == "dotHover":', self.SRC)


if __name__ == "__main__":
    unittest.main()
