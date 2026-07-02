#!/usr/bin/env python3
"""The timeline lane carries the AWAITING-background-work signal (the user 2026-07-01, working-state
audit): the chat chip folds _session_awaiting into its yellow working dot, but the timeline lane showed a
bare READY — the last designed split between the surfaces' working models. build_timeline now emits
`awaitingBg` (the same _session_awaiting why-line, live lanes only) on BOTH the skeleton and the bars
build; the view renders an AWAITING badge in the working-yellow family. Named awaitingBg because the
lane's legacy 'awaiting' STATE and `awaiting` intervals both mean blocked-on-YOU. SYNTHETIC fixtures only
(placeholder UUIDs, invented text)."""
import datetime
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
jd = SourceFileLoader("romp_judge_tlaw", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel_tlaw", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000
T0 = NOW - 600


def _iso(ep):
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class TimelineAwaiting(unittest.TestCase):
    def setUp(self):
        km._downtime[:] = []                            # isolate from the real kernel-downtime.jsonl
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / km.jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        recs = [{"type": "user", "timestamp": _iso(T0), "uuid": "u1", "parentUuid": None,
                 "promptSource": "typed",
                 "message": {"role": "user", "content": "run the long benchmark in the background"}},
                {"type": "assistant", "timestamp": _iso(T0 + 10), "uuid": "a1", "parentUuid": "u1",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "Launched it."}],
                             "stop_reason": "end_turn"}}]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        os.utime(self.tpath, (NOW - 30, NOW - 30))       # recently-touched → discovered as a lane
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self.saved = (km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR, km.jd.STATE, km.NAMES, km._tmux_sessions)
        km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR = names, proj, td / "goals"
        km.jd.STATE = td                                 # sandbox states/ + usage/ + session-flags reads
        km.NAMES = names
        km._tmux_sessions = lambda: {SID: {"state": "waiting", "since": NOW - 100, "model": "", "effort": "",
                                           "context": None, "compactPct": None, "color": None, "mode": ""}}
        (td / "states").mkdir()
        self.states = td / "states" / (SID + ".jsonl")
        km._parse_cache.pop(str(self.tpath), None)
        km._bgtool_cache.clear()

    def tearDown(self):
        (km.jd.NAMES, km.jd.PROJECTS, km.jd.GOALDIR, km.jd.STATE, km.NAMES, km._tmux_sessions) = self.saved
        self.td.cleanup()

    def _lane(self, with_bars=True):
        tl = km.build_timeline(NOW, with_bars=with_bars)
        return next(l for l in tl["sessions"] if l["id"] == SID)

    def test_awaiting_overlay_reaches_the_lane(self):
        self.states.write_text(json.dumps({"t": T0 + 20, "state": "waiting"}) + "\n"
                               + json.dumps({"t": T0 + 21, "awaiting": True, "why": "background benchmark running"}) + "\n")
        self.assertEqual(self._lane()["awaitingBg"], "background benchmark running",
                         "the SDK producer's awaiting overlay reaches the timeline lane, same as the chat")

    def test_cleared_overlay_means_no_awaiting(self):
        self.states.write_text(json.dumps({"t": T0 + 21, "awaiting": True, "why": "bg"}) + "\n"
                               + json.dumps({"t": T0 + 30, "awaiting": False}) + "\n")
        self.assertIsNone(self._lane()["awaitingBg"], "an explicitly cleared overlay reads NOT awaiting")

    def test_skeleton_build_carries_it_too(self):
        # the client renders the lane badge from the SKELETON's state; the bars message carries none — the
        # awaiting cue must not flicker off between the two builds (same lesson as 'compacting', 2026-06-29)
        self.states.write_text(json.dumps({"t": T0 + 21, "awaiting": True, "why": "bg agents"}) + "\n")
        self.assertEqual(self._lane(with_bars=False)["awaitingBg"], "bg agents")

    def test_dead_lane_never_awaits(self):
        km._tmux_sessions = lambda: {}                   # session process gone → window-dead lane
        self.states.write_text(json.dumps({"t": T0 + 21, "awaiting": True, "why": "bg"}) + "\n")
        lane = self._lane()
        self.assertFalse(lane["live"])
        self.assertIsNone(lane["awaitingBg"], "a dead session cannot be awaiting background work")


if __name__ == "__main__":
    unittest.main()
