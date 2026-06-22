#!/usr/bin/env python3
"""build_timeline tags each prompt bar with `nudge` (the user 2026-06-22): a segment opened by a romp
INJECTION (auto-nudge / Nudge button / retry — its trigger carries the romp-injected marker, so the event
model authors it 'romp') gets nudge=True, and the timeline view draws a ⚡ INSIDE that prompt dot plus a
'romp · nudge' tooltip (with the swirl logo) instead of the session name. A genuine human/peer prompt gets
nudge=False. Event-based (keys on the trigger atom's author), never a time heuristic. Self-contained
build_timeline harness; synthetic transcript only — no real session data.
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
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_nb", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd
em = km.em

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 1800


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent=None, stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": stop}}


class NudgeBar(unittest.TestCase):
    def setUp(self):
        km._downtime[:] = []
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        # turn 1: a genuine human prompt. turn 2: a romp NUDGE — the injected marker authors its trigger
        # 'romp', so its bar must come back nudge=True (note: promptSource stays 'typed'; the marker wins).
        recs = [uline(T0, "ship the export feature", "u1"),
                aline(T0 + 20, "Shipped it.", "a1", "u1", stop="end_turn"),
                uline(T0 + 100, "Status on the goal above? <!-- romp-injected -->", "u2", "a1"),
                aline(T0 + 120, "Already deployed and done.", "a2", "u2", stop="end_turn")]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km._tmux_sessions)
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        jd.STATE = td
        km.NAMES = names
        km._tmux_sessions = lambda: {SID: {"state": "idle", "since": NOW - 100, "model": "",
                                           "effort": "", "context": None, "compactPct": None, "color": None}}
        jd.CAPDIR.mkdir(parents=True)
        jd.GOALDIR.mkdir(parents=True)
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        self.segs = [s for turn in session["turns"] for s in em.segments(turn)]

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km._tmux_sessions) = self.saved
        self.td.cleanup()

    def _bars(self):
        bars = km.build_timeline(NOW)["turns"][SID]
        return {b["id"]: b for b in bars}

    def test_human_prompt_is_not_a_nudge_but_the_injected_one_is(self):
        bars = self._bars()
        human, nudge = self.segs[0], self.segs[1]
        self.assertFalse(bars[human["id"]]["nudge"], "a genuine human prompt is NOT a nudge")
        self.assertTrue(bars[nudge["id"]]["nudge"], "the romp-injected segment's bar is flagged nudge")


if __name__ == "__main__":
    unittest.main()
