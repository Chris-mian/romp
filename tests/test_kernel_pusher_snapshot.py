#!/usr/bin/env python3
"""The pusher cycle takes ONE liveness snapshot (the 2026-08-10 CPU fix).

Every _tmux_sessions() read forks `tmux list-sessions` and sweeps the whole SDK reg registry.
The pusher's cycle used to take NINE of them — one inside _push plus one per tick job — at its
0.5s cadence, which profiling attributed as the kernel's single hottest thread (~50-90% of one
core sustained, three quarters of total process CPU). The jobs all take the map as a parameter
by design, so the fix is purely structural: one snapshot at cycle start, handed to everything.

SYNTHETIC fixtures only: placeholder UUIDs, invented names.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_pushsnap", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"


class OneSnapshotPerCycle(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km.Sessions.live, km._sdk,
                      km._auto_nudge_tick, km._clear_done_working_notes)
        names = td / "names"; names.mkdir()
        proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        for d in (jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR):
            d.mkdir()
        jd.STATE = td
        km.NAMES = names
        km._sdk = lambda: None
        # a real session on disk, so the push leg builds it and the DEEP helpers (the awaiting/bg-task
        # sources, the feed's per-session gates) actually run — the reads this fix removes hide there
        cdir = td / "work"; cdir.mkdir()
        pdir = proj / jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        rec = {"type": "user", "timestamp": "2026-06-11T00:00:00.000Z", "uuid": "u1",
               "parentUuid": None, "promptSource": "typed",
               "message": {"role": "user", "content": "hello there"}}
        (pdir / (SID + ".jsonl")).write_text(json.dumps(rec) + "\n")
        (names / SID).write_text("web\t%s\t#abcdef\n" % str(cdir))
        self.row = {SID: {"state": "waiting", "since": NOW - 5, "model": "", "effort": "",
                          "context": None, "compactPct": None, "color": None, "mode": "",
                          "backend": "tmux"}}
        self.saved_clients = list(km._clients)

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km.Sessions.live, km._sdk,
         km._auto_nudge_tick, km._clear_done_working_notes) = self.saved
        with km._clients_lock:
            km._clients[:] = self.saved_clients
        km._live_scope.snapshot = None
        self.td.cleanup()

    def test_one_cycle_reads_liveness_once_however_deep_the_call(self):
        # count REAL liveness reads (Sessions.live — the tmux fork + reg sweep), not the delegator:
        # inside the cycle's scope every _tmux_sessions() call, at any depth of the build stack,
        # must be served the cycle's one snapshot instead of taking a fresh read
        reads = []
        row = self.row
        km.Sessions.live = lambda: (reads.append(1), dict(row))[1]
        got = {}
        # bracket the job list: the FIRST and the LAST tick job must both receive the cycle's one map
        km._auto_nudge_tick = lambda now, tmux: got.setdefault("first", tmux)
        km._clear_done_working_notes = lambda now, tmux: got.setdefault("last", tmux)
        sent = []
        with km._clients_lock:   # a connected chat client, so the _push leg builds for real
            km._clients[:] = [{"app": "chat", "alive": True, "wid": "", "qbytes": 0,
                               "send": sent.append}]
        km._pusher_cycle()
        self.assertEqual(len(reads), 1, "one fork + one reg sweep per cycle — that IS the fix")
        self.assertIn(SID, got.get("first") or {}, "the jobs got the cycle's snapshot")
        self.assertIs(got.get("first"), got.get("last"))
        self.assertTrue(any('"type": "session"' in s or '"type":"session"' in s.replace(" ", "")
                            for s in sent), "the push leg really built the session")
        self.assertIsNone(km._live_scope.snapshot, "the scope ends with the cycle")
        # OUTSIDE a cycle the delegator reads fresh — a WS handler must never see a stale snapshot
        n = len(reads)
        km._tmux_sessions()
        self.assertEqual(len(reads), n + 1)

    def test_build_session_reuses_the_callers_snapshot(self):
        # build_session used to take a FRESH liveness read per session build (the bgTasks line) — on
        # the pusher's hottest path that was a tmux fork + reg sweep per tab per push
        reads = []
        row = self.row
        km.Sessions.live = lambda: (reads.append(1), dict(row))[1]
        m = km.build_session(SID, NOW, dict(self.row))
        self.assertIsNotNone(m)
        self.assertEqual(reads, [], "a provided snapshot is enough — no fresh liveness reads")


if __name__ == "__main__":
    unittest.main()
