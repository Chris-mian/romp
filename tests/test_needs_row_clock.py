"""The Needs you row's face is still across the clock (round three of the box content PR, a contributor's review): the feed build
re-stamps every tree node's recency tint (trgb) on every 5 s build, and with the tree copied whole onto the row the row's face, the chat
signature and the page's row key moved with time alone (590 to 1397 face moves per 96 h in the contributor's runs, each a chat rebuild and
a status frame to every chat client). The row carries a projection of each node onto the fields the shared builder reads (kernel
_NEEDS_ROW_TREE_FIELDS), so two real feed builds five minutes apart over one unchanged store give an equal row, an equal face and an equal
keyed value for every card field, while the card's own tint moved between them (the premise, read from the feed).
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from romp_load import load_source

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="romp-needs-row-clock-")   # the hermetic preamble (tests/test_state_isolation_order.py): before the first romp load
os.environ.pop("ROMP_STATE_DIR", None)                                          # a live kernel exports it to its sessions, and it outranks the XDG floor
km = load_source("romp_kernel_needs_row_clock", os.path.join(os.path.dirname(__file__), "..", "kernel", "kernel.py"))
jd = km.jd

SID = "33333333-4444-5555-6666-777777777777"
NOW = 1781200000


class NeedsRowAcrossTheClock(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        (td / "session-hosts").write_text("off")
        self.saved = (jd.STATE, jd.GOALDIR, jd.GOALARCHDIR, jd.NAMES)
        jd.STATE = td
        jd.GOALDIR = td / "goals"
        jd.GOALARCHDIR = td / "goals-archive"
        jd.NAMES = td / "names"
        jd.GOALDIR.mkdir(parents=True)
        jd.NAMES.mkdir(parents=True)
        self.sessions = [{"sid": SID, "name": "web", "path": "/nonexistent/%s.jsonl" % SID, "anchor": 0, "mtime": 0}]
        self.patches = [mock.patch.object(km, "_alive_sessions", lambda now, live: list(self.sessions)),
                        mock.patch.object(km, "_warm_fleet_bg", lambda now: None)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        g1, g2 = SID + ":g1", SID + ":g2"
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 3, "lastNode": g1, "closedTurns": [], "placements": {},
            "status": {g1: "blocked", g2: "working"},
            "nodes": {g1: {"id": g1, "text": "which database does the suite target?", "parentId": None, "nodeComplete": False, "blocked": True,
                           "blockWhy": "which database does the suite target?", "blockSummary": "Postgres in CI, SQLite locally: which do the fixtures load into?",
                           "cleared": False, "trail": [], "t": NOW - 3600, "log": [{"ev_t": NOW - 3000, "src": "planner", "kind": "block", "why": "asked", "at": NOW - 3000}]},
                      g2: {"id": g2, "text": "wire the fixtures directory", "parentId": g1, "nodeComplete": False, "blocked": False,
                           "cleared": False, "trail": [], "t": NOW - 1800, "log": []}}}))

    def tearDown(self):
        jd.STATE, jd.GOALDIR, jd.GOALARCHDIR, jd.NAMES = self.saved
        self.td.cleanup()

    def test_two_builds_five_minutes_apart_give_an_equal_row_face_and_key_while_the_cards_tint_moved(self):
        live = {SID: {"state": "ready"}}
        f1 = km.build_feed(NOW, live)
        f2 = km.build_feed(NOW + 300, live)
        a1 = next(a for a in f1["asks"] if a["itemId"] == SID + ":g1")
        a2 = next(a for a in f2["asks"] if a["itemId"] == SID + ":g1")
        self.assertEqual(a1["category"], "needs_input", "the question is a Needs you card: %r" % {k: a1.get(k) for k in ("category", "column", "blocked")})
        self.assertTrue(a1.get("tree") and a2.get("tree"), "the card carries its tree: %r" % a1.get("tree"))
        self.assertNotEqual([r.get("trgb") for r in a1["tree"]], [r.get("trgb") for r in a2["tree"]], "the premise: the card's tree tint moved with the clock between the two builds")
        r1, r2 = km._needs_you_rows(f1).get(SID), km._needs_you_rows(f2).get(SID)
        self.assertTrue(r1 and r2, "the rows: %r" % (r1,))
        self.assertEqual(r1, r2, "the row is the same across the clock (before: the tree's tint rode the row, and its face moved with time alone)")
        self.assertEqual(km._needs_rows_face({SID: r1}), km._needs_rows_face({SID: r2}), "and so is the face the pusher wakes on")
        for f in getattr(km, "_NEEDS_ROW_CARD_FIELDS", ()):   # a kernel before the box content round carries no card fields on the row (main e2798226): nothing to key
            with self.subTest(field=f):
                self.assertEqual(km._row_field_key(r1[0].get(f)), km._row_field_key(r2[0].get(f)), "the keyed value of %s is still across the clock" % f)
        for r in (r1[0].get("tree") or []):   # a row before the round carries no tree at all (main e2798226)
            self.assertFalse(set(r) & {"trgb", "last", "whoWorking", "log"}, "the projection carries none of the tint or the modal's fields: %r" % sorted(r))
            self.assertTrue(set(r) <= set(getattr(km, "_NEEDS_ROW_TREE_FIELDS", ())), "and nothing outside the builder's fields: %r" % sorted(r))


if __name__ == "__main__":
    unittest.main()
