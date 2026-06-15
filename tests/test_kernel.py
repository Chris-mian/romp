#!/usr/bin/env python3
"""Tests for bin/romp-kernel's view-builder (records → feed / chat / timeline payloads).

The HTTP serving + producer thread aren't unit-tested; the view-builder — the meaningful
projection logic, and the SINGLE view-builder per design/read-side.md — is. Synthetic fleet:
invented text, placeholder UUIDs, hostname TESTHOST; no real session data.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None, ps="typed"):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": ps, "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent=None, stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": stop}}


class ViewBuilder(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        recs = [uline(T0, "fix the feed flicker", "u1", ps="typed"),
                aline(T0 + 30, "Fixed the feed flicker.", "a1", "u1", stop="end_turn")]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        # point the producer/record globals at the temp fleet
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR)
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        # synthetic records: parse to get real ids, then write matching captions
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        turn = session["turns"][0]
        seg = em.segments(turn)[0]
        jd.CAPDIR.mkdir(parents=True)
        (jd.CAPDIR / (SID + ".jsonl")).write_text(
            json.dumps({"id": seg["id"], "grain": "segment", "t": seg["t"], "caption": "Fixed the feed flicker"}) + "\n"
            + json.dumps({"id": turn["id"], "grain": "turn", "t": turn["t"], "caption": "Fixed the feed flicker"}) + "\n")
        jd.ARCHDIR.mkdir(parents=True)
        (jd.ARCHDIR / (SID + ".json")).write_text(json.dumps(
            {"headline": "Fixing the feed", "abstract": "Fixed a flicker in the feed.", "turns": 1}))
        jd.GOALDIR.mkdir(parents=True)
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 1, "lastNode": "%s:g1" % SID,
            "nodes": {"%s:g1" % SID: {"id": "%s:g1" % SID, "text": "Fix the feed flicker", "parentId": None,
                                      "nodeComplete": True, "blocked": False, "cleared": False,
                                      "trail": [seg["id"]], "t": seg["t"]}},
            "placements": {seg["id"]: "%s:g1" % SID},
            "status": {"%s:g1" % SID: "completed"}}))

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR) = self.saved
        self.td.cleanup()

    def test_feed_buckets_goal_and_streams_caption(self):
        d = km.view_feed(NOW)
        self.assertEqual(len(d["columns"]["completed"]), 1, "the completed goal lands in the completed column")
        self.assertEqual(d["columns"]["completed"][0]["text"], "Fix the feed flicker")
        self.assertTrue(d["columns"]["completed"][0]["trail"]["done"])
        self.assertTrue(any(c["caption"] == "Fixed the feed flicker" for c in d["stream"]),
                        "the turn caption appears in the stream")

    def test_chat_renders_toc_and_event_tree(self):
        d = km.view_chat(SID)
        self.assertEqual(d["headline"], "Fixing the feed")
        self.assertTrue(any(t["caption"] == "Fixed the feed flicker" for t in d["toc"]), "TOC shows the turn caption")
        kinds = [a["type"] for a in d["atoms"]]
        self.assertIn("user", kinds)
        self.assertIn("assistant", kinds)
        u = next(a for a in d["atoms"] if a["type"] == "user")
        self.assertEqual(u["author"], "human")
        self.assertIn("fix the feed flicker", u["text"])

    def test_timeline_lane_has_segment_bar_with_caption(self):
        d = km.view_timeline(NOW)
        self.assertEqual(len(d["lanes"]), 1)
        bars = d["lanes"][0]["bars"]
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["caption"], "Fixed the feed flicker")
        self.assertLessEqual(d["lo"], bars[0]["t"])
        self.assertGreaterEqual(d["hi"], bars[0]["end"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
