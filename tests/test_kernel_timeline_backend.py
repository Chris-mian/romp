#!/usr/bin/env python3
"""The timeline's session row names its backend (2026-09-16). The lane's model and effort pickers speak the
session's backend's vocabulary and a live Codex lane draws its effort picker before any level is picked, both
keyed on the row's `backend`; the row carried no such field, so the view read every lane as Claude's and a
Codex lane with no level had no picker at all. The chat tab's meta has carried the field since 2026-06-22
(_session_backend); the lane now carries the same. SYNTHETIC fixtures only (placeholder UUIDs, invented text)."""
import datetime
import json
import os
import tempfile
import unittest
from romp_load import load_source
from pathlib import Path
HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = load_source("romp_judge_tlbk", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_tlbk", os.path.join(BIN, "romp-kernel"))
SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000
T0 = NOW - 600


def _iso(ep):
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class TimelineLaneBackend(unittest.TestCase):
    def setUp(self):
        km._downtime[:] = []                            # isolate from the real kernel-downtime.jsonl
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / km.jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        recs = [{"type": "user", "timestamp": _iso(T0), "uuid": "u1", "parentUuid": None, "promptSource": "typed",
                 "message": {"role": "user", "content": "list the open tickets"}},
                {"type": "assistant", "timestamp": _iso(T0 + 10), "uuid": "a1", "parentUuid": "u1",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "Three are open."}],
                             "stop_reason": "end_turn"}}]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        os.utime(self.tpath, (NOW - 30, NOW - 30))       # recently-touched → discovered as a lane
        names = td / "names"; names.mkdir()
        (names / SID).write_text("api\t%s\t#abcdef\n" % str(cdir))
        self.saved = (km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR, km.jd.STATE, km.NAMES, km._live_map)
        km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR = names, proj, td / "goals"
        km.jd.STATE = td                                 # sandbox states/ + usage/ + session-flags reads
        km.NAMES = names
        (td / "states").mkdir()
        km._parse_cache.pop(str(self.tpath), None)

    def tearDown(self):
        (km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR, km.jd.STATE, km.NAMES, km._live_map) = self.saved
        self.td.cleanup()

    def _lane(self, tm):
        km._live_map = lambda: {SID: tm}
        tl = km.build_timeline(NOW, with_bars=False)     # the skeleton carries it too: the pickers draw from the skeleton
        return next(l for l in tl["sessions"] if l["id"] == SID)

    def test_a_live_codex_lane_names_its_backend_beside_an_empty_effort(self):
        lane = self._lane({"state": "waiting", "since": NOW - 100, "model": "gpt-5-test", "effort": "",
                           "context": None, "compactPct": None, "color": None, "mode": "", "backend": "codex"})
        self.assertEqual(lane["backend"], "codex", "the lane's pickers read the backend from the row")
        self.assertEqual(lane["effort"], "", "no level picked yet: the row still says so, the view draws the picker from the backend")
        self.assertTrue(lane["live"])

    def test_a_live_sdk_lane_names_its_backend_and_keeps_its_level(self):
        lane = self._lane({"state": "waiting", "since": NOW - 100, "model": "Opus 5", "effort": "high",
                           "context": None, "compactPct": None, "color": None, "mode": "", "backend": "sdk"})
        self.assertEqual((lane["backend"], lane["effort"]), ("sdk", "high"))

    def test_the_row_reads_the_field_through_the_tab_meta_helper(self):
        # the same helper the chat tab's meta uses, so a dead lane still reports which kind it was (its docstring)
        import inspect
        self.assertIn('"backend": _session_backend(sid, tm),', inspect.getsource(km.build_timeline))


if __name__ == "__main__":
    unittest.main()
