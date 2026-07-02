#!/usr/bin/env python3
"""Seg-id TIMESTAMP DRIFT must not strand the provisional placeholder or drop caption gists (the user
2026-07-01). The judge records placements/captions keyed by ITS parse's seg id; an SDK message that sat
queued drifts: the optimistic echo lands at SEND time, the real transcript atom at PROCESS time, and the
seg id embeds that t — same trigger-text hash, different middle timestamp. A raw dict hit then misses, so:
  - _provisional_card never saw the placement → a phantom dotted "working" card sat on an IDLE session for
    hours (the live case: turn ended 17:34, still 'Analyzing' at 20:35);
  - the 'Analyzing: <gist>' caption and the timeline message-dot gist silently fell back / vanished.
_seg_placed/_seg_caption resolve through the timestamp-invariant _seg_key, like every anchor read already
does. SYNTHETIC fixtures only — placeholder UUIDs, no real data.
"""
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_segdrift", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _iso(ep):
    import datetime
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _drift(seg_id, secs=48):
    """The SAME segment's id as the judge would have recorded it — middle t shifted (echo SEND time)."""
    p = seg_id.split(":")
    return "%s:%d:%s" % (p[0], int(p[1]) - secs, p[2])


class SegPlacedDrift(unittest.TestCase):
    def _held(self, now):
        td = tempfile.mkdtemp()
        path = os.path.join(td, SID + ".jsonl")
        recs = [{"type": "user", "timestamp": _iso(now - 60), "uuid": "u1", "parentUuid": None,
                 "promptSource": "typed",
                 "message": {"role": "user", "content": "please fix the flaky export test"}},
                {"type": "assistant", "timestamp": _iso(now - 50), "uuid": "a1", "parentUuid": "u1",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}],
                             "stop_reason": "end_turn"}}]
        open(path, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
        s = {"path": path, "sid": SID, "name": "T"}
        turns = km._parse(path, SID, now)["turns"]
        held = km.em.segments(turns[-1])[-1]
        return s, held

    def test_drifted_placement_still_drops_the_placeholder(self):
        # the live bug: placement recorded under the echo-time seg id, live parse carries the real-atom id
        now = int(time.time())
        s, held = self._held(now)
        for suffix in ("", "#p", "#d"):
            store = {"placements": {_drift(held["id"]) + suffix: SID + ":g1"}}
            card = km._provisional_card(s, "T", {"bg": "#fff", "fg": "#000"}, SID, True, now, store=store)
            self.assertIsNone(card, "a placement recorded under a DRIFTED seg id (%r) still gates the "
                                    "placeholder — no phantom working card" % (suffix or "work"))

    def test_retired_placement_counts_as_placed(self):
        # placements[key] = None means the planner RETIRED the segment (skip/final) — still 'ruled on'
        now = int(time.time())
        s, held = self._held(now)
        store = {"placements": {_drift(held["id"]): None}}
        self.assertIsNone(km._provisional_card(s, "T", None, SID, True, now, store=store),
                          "a retired (None) placement is a planner ruling → no placeholder")

    def test_unplaced_segment_still_gets_the_placeholder(self):
        # control: with NO placement at all the placeholder must still appear (the original feature)
        now = int(time.time())
        s, held = self._held(now)
        card = km._provisional_card(s, "T", None, SID, True, now, store={"placements": {}})
        self.assertIsNotNone(card, "an unplaced prompt still surfaces the placeholder")

    def test_seg_placed_helper_semantics(self):
        seg = SID + ":1000:cafebabe"
        drifted = SID + ":952:cafebabe"
        other = SID + ":1000:deadbeef"
        self.assertTrue(km._seg_placed({seg: "x"}, seg), "exact hit")
        self.assertTrue(km._seg_placed({drifted + "#p": "x"}, seg), "drifted prompt-run key matches")
        self.assertFalse(km._seg_placed({other: "x"}, seg), "a DIFFERENT segment (other hash) never matches")


class SegCaptionDrift(unittest.TestCase):
    def test_caption_lookup_survives_drift(self):
        caps = {SID + ":952:cafebabe#p": {"caption": "fix the flaky export test"}}
        self.assertEqual(km._seg_caption(caps, SID + ":1000:cafebabe"), "fix the flaky export test",
                         "the judge-keyed caption resolves through the timestamp-invariant key")
        self.assertEqual(km._seg_caption(caps, SID + ":1000:deadbeef"), "",
                         "a different segment's caption is never borrowed")

    def test_provisional_card_uses_the_drifted_gist(self):
        # end-to-end: with a drift-keyed caption on disk, the placeholder reads 'Analyzing: <gist>'
        now = int(time.time())
        td = Path(tempfile.mkdtemp())
        path = td / (SID + ".jsonl")
        recs = [{"type": "user", "timestamp": _iso(now - 30), "uuid": "u1", "parentUuid": None,
                 "promptSource": "typed",
                 "message": {"role": "user", "content": "please fix the flaky export test"}}]
        path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        turns = km._parse(str(path), SID, now)["turns"]
        held = km.em.segments(turns[-1])[-1]
        saved = km.jd.CAPDIR
        km.jd.CAPDIR = td / "captions"
        km.jd.CAPDIR.mkdir()
        try:
            (km.jd.CAPDIR / (SID + ".jsonl")).write_text(json.dumps(
                {"id": _drift(held["id"]) + "#p", "grain": "prompt", "t": now - 30,
                 "caption": "flaky export test fix"}) + "\n")
            card = km._provisional_card({"path": str(path), "sid": SID, "name": "T"}, "T", None, SID, True,
                                        now, store={"placements": {}})
            self.assertIsNotNone(card)
            self.assertEqual(card["text"], "Analyzing: flaky export test fix",
                             "the gist resolves despite the captioner's drifted key")
        finally:
            km.jd.CAPDIR = saved


if __name__ == "__main__":
    unittest.main()
