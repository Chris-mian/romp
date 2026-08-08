#!/usr/bin/env python3
"""The opening chip's deciding event is per-backend.

A session whose transcript doesn't exist yet reads "opening" (2026-08-05: a just-spawned tab said
"Working" over a clock with no honest base). For tmux the transcript's first record is the only
observable, so the file IS the event. For an SDK session it isn't: a fresh SDK session writes NO
transcript until its first turn, so keying the chip on the file left a fully-up, idle session wearing
the animated opening dots until the user's first message — indefinitely (the user 2026-08-08, who read
minutes of dots as creation still running). The SDK backend knows the earlier designed event — the
handshake (snapshot `connected`, set the moment the client context opens) — and the override stands
down on it.

SYNTHETIC fixtures only (placeholder uuid, temp dirs), modeled on test_chat_payload_clock_invariant.
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
jd = SourceFileLoader("romp_judge_openchip", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel_openchip", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000


class OpeningChipDecidingEvent(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        self.pdir = proj / jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        self.pdir.mkdir(parents=True)
        names = td / "names"; names.mkdir()
        (names / SID).write_text("web\t%s\t#abcdef\n" % str(cdir))
        # Patch BOTH judge instances: this module's `jd` and the kernel's own `km.jd` — kernel.py loads
        # judge.py itself (SourceFileLoader "romp_judge"), so they are distinct module objects, and
        # _sessions()/discover() reads km.jd. Patching only the test's jd leaves discovery scanning the
        # real ~/.claude/projects, and the fixture transcript is never found (chip stuck "opening").
        self.saved = [(m, k, getattr(m, k)) for m in (jd, km.jd)
                      for k in ("NAMES", "PROJECTS", "CAPDIR", "ARCHDIR", "GOALDIR", "STATE")]
        self.saved += [(km, "NAMES", km.NAMES), (km, "_tmux_sessions", km._tmux_sessions),
                       (km, "_GLOBAL_CLAUDE_MD", km._GLOBAL_CLAUDE_MD)]
        for m in (jd, km.jd):
            m.NAMES, m.PROJECTS = names, proj
            m.CAPDIR, m.ARCHDIR, m.GOALDIR = td / "captions", td / "archive", td / "goals"
            m.STATE = td
        km.NAMES = names
        km._GLOBAL_CLAUDE_MD = td / "no-global-claude.md"
        self.tm = {"state": "waiting", "since": NOW - 5, "model": "Opus 5", "effort": "xhigh",
                   "context": None, "compactPct": None, "color": None, "backend": "sdk"}
        km._tmux_sessions = lambda: {SID: dict(self.tm)}

    def tearDown(self):
        for m, k, v in self.saved:
            setattr(m, k, v)
        self.td.cleanup()

    def _state(self):
        m = km.build_session(SID, NOW)
        self.assertIsNotNone(m, "fixture session must build")
        return (m.get("status") or {}).get("state")

    def test_no_transcript_and_no_handshake_is_opening(self):
        # spawned but the CLI hasn't proven up and nothing is on disk → opening (the 2026-08-05 rule)
        self.assertEqual(self._state(), "opening")

    def test_the_sdk_handshake_ends_opening_before_any_transcript_exists(self):
        # a fresh SDK session is fully open the moment its client connects — its transcript only
        # appears with the FIRST TURN, so the file must not keep the dots up on a ready session
        self.tm["connected"] = True
        self.assertEqual(self._state(), "ready",
                         "connected + idle = ready to take a message; the dots would be a lie")

    def test_the_transcripts_first_record_still_ends_opening(self):
        # the tmux path (no `connected` signal): the file landing remains the deciding event. A
        # COMPLETED turn, so the chip settles to ready rather than working (an open turn).
        def iso(t):
            return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")
        (self.pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in [
            {"type": "user", "timestamp": iso(NOW - 60), "uuid": "u1", "parentUuid": None,
             "promptSource": "typed", "message": {"role": "user", "content": "start the notes-api spike"}},
            {"type": "assistant", "timestamp": iso(NOW - 20), "uuid": "a1", "parentUuid": "u1",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Spike is up."}],
                         "stop_reason": "end_turn"}},
        ]) + "\n")
        self.assertEqual(self._state(), "ready")
