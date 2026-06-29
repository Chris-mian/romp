#!/usr/bin/env python3
"""_fleet_archived_tops (bin/romp-kernel): the Fleet's "Show completed" surfaces the FULLY-COMPLETED top
tasks the compaction sweep archived out of the live goal tree — so a finished+archived session reappears
instead of vanishing (the user 2026-06-27). Synthetic stores only: placeholder UUIDs, no real data.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_fleetarch", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class FleetArchivedTops(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.arch_dir = Path(self.td.name) / "goals-archive"
        self.arch_dir.mkdir(parents=True)
        self._saved = km.jd.GOALARCHDIR
        km.jd.GOALARCHDIR = self.arch_dir
        km._arch_tops_cache.clear()

    def tearDown(self):
        km.jd.GOALARCHDIR = self._saved
        km._arch_tops_cache.clear()
        self.td.cleanup()

    def _write(self, sid, store):
        (self.arch_dir / (sid + ".json")).write_text(json.dumps(store))

    def test_no_archive_file_returns_empty(self):
        self.assertEqual(km._fleet_archived_tops("no-such-sid"), [])

    def test_surfaces_completed_tops_not_bare_dismissals_or_children(self):
        self._write(SID, {"nodes": {
            "t1": {"text": "Ship feature", "parentId": None, "nodeComplete": True, "t": 100, "mt": 200},
            "t2": {"text": "Investigate idea", "parentId": None, "t": 110, "mt": 150},      # dismissed, never finished
            "t3": {"text": "Write doc", "parentId": None, "t": 120, "mt": 300, "summary": "wrote it"},  # done (takeaway)
            "c1": {"text": "a child", "parentId": "t1", "nodeComplete": True, "t": 130, "mt": 140},      # not a top
        }, "status": {"t2": "cleared"}})
        tops = km._fleet_archived_tops(SID)
        self.assertEqual([n["id"] for n in tops], ["t3", "t1"],
                         "completed tops only, newest-first; no bare-dismissal t2, no child c1")
        self.assertTrue(all(n["depth"] == 0 and n["done"] and n["archived"] and n["children"] == [] for n in tops),
                        "each is a collapsed (childless) done top, tagged archived")

    def test_status_completed_counts_as_done(self):
        self._write(SID, {"nodes": {"t1": {"text": "x", "parentId": None, "t": 1, "mt": 2}},
                          "status": {"t1": "completed"}})
        self.assertEqual([n["id"] for n in km._fleet_archived_tops(SID)], ["t1"])

    def test_cap_limits_count(self):
        nodes = {("t%d" % i): {"text": str(i), "parentId": None, "nodeComplete": True, "t": i, "mt": i}
                 for i in range(30)}
        self._write(SID, {"nodes": nodes, "status": {}})
        self.assertEqual(len(km._fleet_archived_tops(SID, cap=5)), 5)

    def test_mtime_cached(self):
        self._write(SID, {"nodes": {"t1": {"text": "x", "parentId": None, "nodeComplete": True, "t": 1, "mt": 2}},
                          "status": {}})
        a = km._fleet_archived_tops(SID)
        b = km._fleet_archived_tops(SID)
        self.assertIs(a, b, "unchanged archive (same mtime) → cached, no re-projection on the feed hot path")


if __name__ == "__main__":
    unittest.main()
