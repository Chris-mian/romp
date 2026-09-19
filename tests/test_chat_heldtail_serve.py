"""The kernel serves a proto-2 full frame from the client's held tail so content that exists is never dropped
(the user 2026-09-19). tailLo is re-derived from THIS build's tail (WIRE_TAIL events from the current end), so a
grown session would put tailLo ABOVE a run the page still holds and a shorter one (a fork / rewind) BELOW it. The
kernel reads the client's held tail run first key (heldTailFirst on needFull, or pc["first"] for a connected client
whose base went away) and, when it still maps below the cut, serves from there (a SUPERSET, nothing dropped); when it
is gone from the whole transcript, carries `rebased` so the page sets those turns aside under its notice. A compaction
only floors the head (not a producer) and a cold-boot session outside the discover window ships tailLo null (1877's
regions-less landing), both unchanged.

Synthetic only: placeholder uuid, invented turn text. Hermetic kernel, never the live one.
"""
import json
import os
import re
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
import sys
sys.path.insert(0, HERE)
from test_ship_reship_served import kernel_env          # noqa: E402
from test_fold_checkpoints_served import ChatClient      # noqa: E402

BIN = os.path.join(os.path.dirname(HERE), "bin")
DIST = os.path.join(os.path.dirname(HERE), "vscode-extension", "dist")
SID = "11111111-2222-4333-8444-000000000906"
WIRE_TAIL = 250   # kernel.py: events shipped on a full; the cut is that many before the end


def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); n = s.getsockname()[1]; s.close(); return n


def _pair(i, parent, cwd):
    t0 = 1_700_000_000 + i * 600
    ta = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0))
    tb = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0 + 60))
    u, a = "api-u%03d" % i, "api-a%03d" % i
    return [
        {"type": "user", "uuid": u, "parentUuid": parent, "sessionId": SID, "cwd": cwd, "timestamp": ta,
         "promptSource": "typed", "message": {"role": "user", "content": "turn %d?" % i}},
        {"type": "assistant", "uuid": a, "parentUuid": u, "sessionId": SID, "cwd": cwd, "timestamp": tb,
         "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                     "content": [{"type": "text", "text": "turn %d done." % i}]}},
    ], a


def _turns_text(cwd, lo, hi, boundary_at=None):
    """Turns [lo, hi) as JSONL; a compact_boundary + summary inserted at `boundary_at` when given."""
    recs, parent = [], None
    for i in range(lo, hi):
        if boundary_at is not None and i == boundary_at:
            t0 = 1_700_000_000 + i * 600
            ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0))
            recs.append({"type": "system", "subtype": "compact_boundary", "uuid": "api-cb", "parentUuid": None,
                         "logicalParentUuid": parent, "sessionId": SID, "cwd": cwd, "timestamp": ts,
                         "compactMetadata": {"trigger": "manual", "preTokens": 100000}})
            recs.append({"type": "user", "uuid": "api-sum", "parentUuid": "api-cb", "sessionId": SID, "cwd": cwd,
                         "timestamp": ts, "isCompactSummary": True, "promptId": "cb-pid",
                         "message": {"role": "user", "content": "This session is being continued; summary."}})
            parent = "api-sum"
        r, parent = _pair(i, parent, cwd)
        recs += r
    return "".join(json.dumps(x) + "\n" for x in recs)


class HeldTailServe(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.lab = tempfile.mkdtemp(prefix="heldtail-")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self.lab, ignore_errors=True)

    def _boot(self, name, turns_text, mtime_age=0):
        state = os.path.join(self.lab, name, "xdg", "romp")
        claude = os.path.join(self.lab, name, "claude")
        cwd = os.path.join(self.lab, name, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "names", SID).write_text("%s\t%s\t\t\n" % ("api", cwd))
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "api", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True}))
        p = os.path.join(proj, SID + ".jsonl")
        Path(p).write_text(turns_text(cwd))
        if mtime_age:
            old = int(time.time()) - mtime_age
            os.utime(p, (old, old))
        port, tok = _free_port(), "tok-" + name
        env = kernel_env(os.path.join(self.lab, name), claude, DIST, port, tok, ROMP_HOST_NAME=name.upper())
        log = os.path.join(self.lab, name + "-kernel.log")
        proc = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
        self.procs.append(proc)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=1)
                return port, tok, p, cwd, state
            except Exception:
                time.sleep(0.5)
        raise unittest.SkipTest("kernel %s never served /healthz" % name)

    @staticmethod
    def _first_full(c):
        for fr in c.frames(45):
            if fr.get("type") == "session" and fr.get("id") == SID:
                return fr
        raise AssertionError("no session frame in 45 s")

    @staticmethod
    def _tail_first_key(fr):
        """The frame's tail run first key = its firstUuid (the page's resident tail run older edge)."""
        return fr.get("firstUuid")

    def _bust(self, state, p, cwd, turns_text):
        Path(p).write_text(turns_text(cwd))
        Path(os.path.dirname(p), "_bust_%d" % int(time.time() * 1000)).write_text("x")   # a dir entry: busts the discover fingerprint
        Path(state, "names", "_bust").write_text("x")
        time.sleep(4)   # let a pusher cycle re-discover and rebuild

    def _repair_full(self, c, held_first, with_key=True):
        """Send a needFull (carrying heldTailFirst unless with_key is False), return the repair full frame."""
        msg = {"type": "needFull", "id": SID, "why": "gap"}
        if with_key and held_first:
            msg["heldTailFirst"] = held_first
        c.send(msg)
        return self._first_full(c)

    # ── K1: served from the held base when the key maps BELOW the cut (grow), tailLo == the held run's lo ──
    def test_k1_served_from_held_base_on_a_grown_session(self):
        port, tok, p, cwd, state = self._boot("grow", lambda cwd: _turns_text(cwd, 0, 600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        full1 = self._first_full(c)
        held = self._tail_first_key(full1)                       # api-u475 for 600 turns (WIRE_TAIL from the end)
        self.assertEqual((full1.get("tailLo"), held), (475, "api-u475"), "premise: the held tail run begins at 475: %r" % full1.get("tailLo"))
        self._bust(state, p, cwd, lambda cwd: _turns_text(cwd, 0, 800))   # grow to 800: the WIRE_TAIL cut is now ~675
        full2 = self._repair_full(c, held)
        self.assertEqual(full2.get("tailLo"), 475,
                         "the repair full is served from the held base (a superset), NOT re-cut at ~675: tailLo=%r firstUuid=%r n=%d"
                         % (full2.get("tailLo"), full2.get("firstUuid"), len(full2.get("events") or [])))
        self.assertEqual(full2.get("firstUuid"), "api-u475")
        self.assertNotIn("rebased", full2, "a grown session is served, never set aside: %r" % {k: full2.get(k) for k in ("tailLo", "rebased")})

    # ── K2: a shrink (fork / rewind) that drops the held tail from the transcript emits `rebased`, not a silent low frame ──
    def test_k2_a_shrink_that_drops_the_held_tail_rebases(self):
        port, tok, p, cwd, state = self._boot("shrink", lambda cwd: _turns_text(cwd, 0, 600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        full1 = self._first_full(c)
        held = self._tail_first_key(full1)                       # api-u475
        self._bust(state, p, cwd, lambda cwd: _turns_text(cwd, 0, 250))   # rewind: turns 250..599 gone from the transcript
        full2 = self._repair_full(c, held)
        self.assertTrue(full2.get("rebased") is True,
                        "the held tail is gone from the transcript: the frame carries rebased so the page sets it aside, not a silent low-tailLo drop: %r"
                        % {k: full2.get(k) for k in ("tailLo", "rebased", "firstUuid")})

    # ── K3: the needFull WIRE field serves from the held base (pc is cleared by the needFull, so this is not pc["first"]) ──
    def test_k3_a_needfull_with_the_held_key_serves_from_it(self):
        # the reconnect vehicle rides needFull, not `ready`: a redial sends NO ready (federation.ts, the reconnect=1 URL
        # is the handshake), so heldTailFirst travels on the needFull the page's guard 3 fires when a plain frame would
        # drop a held run. The needFull clears echat[sid] (pc None), so the WIRE field is the only source here, pinning
        # it apart from the connected pc["first"] path (K1/K2). The session grew to 800; the page holds its tail from 475.
        port, tok, p, cwd, state = self._boot("needkey", lambda cwd: _turns_text(cwd, 0, 800))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)                                       # the connect full (tailLo ~675)
        full = self._repair_full(c, "api-u475")                  # a needFull naming the held base at 475
        self.assertEqual(full.get("tailLo"), 475,
                         "the needFull named a held base at 475: the repair full is served from there (a superset), NOT re-cut at ~675: tailLo=%r firstUuid=%r"
                         % (full.get("tailLo"), full.get("firstUuid")))
        self.assertEqual(full.get("firstUuid"), "api-u475")
        self.assertNotIn("rebased", full, "the held base still maps (grown session): served, not set aside: %r" % {k: full.get(k) for k in ("tailLo", "rebased")})

    # ── K4: a compaction is NOT a producer (it floors the head, does not renumber): no rebased, tailLo tracks the current end ──
    def test_k4_a_compaction_does_not_rebase(self):
        port, tok, p, cwd, state = self._boot("compact", lambda cwd: _turns_text(cwd, 0, 600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        full1 = self._first_full(c)
        held = self._tail_first_key(full1)
        self._bust(state, p, cwd, lambda cwd: _turns_text(cwd, 0, 606, boundary_at=600))   # a compaction near the tail + 5 turns
        full2 = self._repair_full(c, held)
        self.assertNotIn("rebased", full2, "a compaction floors the head, it is not a shorter tail: never rebased: %r" % {k: full2.get(k) for k in ("tailLo", "rebased")})
        self.assertIsNotNone(full2.get("tailLo"), "a compaction keeps a numeric tailLo (the head floor, not a renumber): %r" % full2.get("tailLo"))

    # ── K5: a session outside the discover window ships tailLo null (1877's regions-less landing), unchanged ──
    def test_k5_a_cold_session_outside_the_window_ships_tailLo_null(self):
        port, tok, p, cwd, state = self._boot("cold", lambda cwd: _turns_text(cwd, 0, 600), mtime_age=30 * 86400)
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        full1 = self._first_full(c)
        self.assertIsNone(full1.get("tailLo"), "a transcript older than the discover window ships tailLo null (sess is None in _tail_run_start): %r" % full1.get("tailLo"))
        self.assertNotIn("rebased", full1, "the cold-boot null frame is 1877's regions-less landing, not a rebase: %r" % {k: full1.get(k) for k in ("tailLo", "rebased")})


    # ── K6 / interop: an OLDER page reconnects with NO heldTails; the kernel emits today's plain frame (the field is
    #    additive, read only when present). new page / old kernel is the mirror: an old kernel ignores heldTailFirst the
    #    same way and sends the plain frame, which the new page's guard 3 contains (pinned by the relay lab's straddle_lying).
    def test_k6_interop_older_page_reconnect_gets_the_plain_frame(self):
        port, tok, p, cwd, state = self._boot("interop", lambda cwd: _turns_text(cwd, 0, 800))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})                    # no heldTails: an older page
        full = self._first_full(c)
        self.assertEqual(full.get("tailLo"), 675, "with no held key the kernel emits its plain WIRE_TAIL frame (cut at ~675): %r" % full.get("tailLo"))
        self.assertNotIn("rebased", full, "nothing new for an older page: %r" % {k: full.get(k) for k in ("tailLo", "rebased")})


if __name__ == "__main__":
    unittest.main()
