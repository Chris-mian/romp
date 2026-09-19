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


def U(i):   # a real record uuid for turn i's user event (the tail run's first key is this; M1a's regex checks the uuid shape)
    return "11111111-2222-3333-4444-%012d" % i


def A(i):   # turn i's assistant event uuid
    return "11111111-2222-3333-4444-%012d" % (500000 + i)


def _pair(i, parent, cwd):
    t0 = 1_700_000_000 + i * 600
    ta = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0))
    tb = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0 + 60))
    u, a = U(i), A(i)
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

    def _repair_full(self, c, held_first, with_key=True):
        """Send a needFull (carrying heldTailFirst unless with_key is False), return the repair full frame."""
        msg = {"type": "needFull", "id": SID, "why": "gap"}
        if with_key and held_first:
            msg["heldTailFirst"] = held_first
        c.send(msg)
        return self._first_full(c)

    # ── K1: served from the held base when the key maps BELOW the cut (grow), tailLo == the held run's lo ──
    def test_k1_served_from_held_base_when_the_key_maps_below_the_cut(self):
        # deterministic: an 800-turn session, a needFull naming the held tail run at turn 475 (BELOW the ~675 WIRE_TAIL
        # cut). The repair is served from 475, a SUPERSET, tailLo the held lo, no ask. The premise is the held key's
        # position, not a timed transcript rewrite.
        port, tok, p, cwd, state = self._boot("serve", lambda cwd: _turns_text(cwd, 0, 800))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)
        full = self._repair_full(c, U(475))
        self.assertEqual((full.get("tailLo"), full.get("firstUuid")), (475, U(475)),
                         "served from the held base at 475 (below the ~675 cut), not re-cut: tailLo=%r firstUuid=%r" % (full.get("tailLo"), full.get("firstUuid")))
        self.assertGreater(len(full.get("events") or []), 251, "a superset: it carries the held run and the growth, more than one WIRE_TAIL: n=%d" % len(full.get("events") or []))
        self.assertNotIn("rebased", full, "the held base maps: served, never set aside: %r" % {k: full.get(k) for k in ("tailLo", "rebased")})

    # ── K2: a needFull whose held key the CURRENT (shorter) session lacks -- a fork, a rewind -- rebases ──
    def test_k2_a_needfull_whose_held_key_the_session_lacks_rebases(self):
        # deterministic: a 250-turn session and a needFull naming U(475), a turn this session never had (the shrink's END
        # STATE without a timed rewrite). The held key is not in the current transcript, so the repair carries rebased and
        # the page sets the stale run aside, not a silent low-tailLo drop.
        port, tok, p, cwd, state = self._boot("gone", lambda cwd: _turns_text(cwd, 0, 250))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)
        full = self._repair_full(c, U(475))
        self.assertTrue(full.get("rebased") is True,
                        "the held key is not in the current transcript: rebased, so the page sets the stale run aside: %r"
                        % {k: full.get(k) for k in ("tailLo", "rebased", "firstUuid")})

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
        full = self._repair_full(c, U(475))                      # a needFull naming the held base at 475
        self.assertEqual(full.get("tailLo"), 475,
                         "the needFull named a held base at 475: the repair full is served from there (a superset), NOT re-cut at ~675: tailLo=%r firstUuid=%r"
                         % (full.get("tailLo"), full.get("firstUuid")))
        self.assertEqual(full.get("firstUuid"), U(475))
        self.assertNotIn("rebased", full, "the held base still maps (grown session): served, not set aside: %r" % {k: full.get(k) for k in ("tailLo", "rebased")})

    # ── K4: a compaction is NOT a producer (it floors the head, does not renumber): no rebased, tailLo tracks the current end ──
    def test_k4_a_compaction_does_not_rebase(self):
        # deterministic: boot the compacted transcript directly (a compact_boundary at turn 600 + 5 turns). A compaction
        # floors the head, it does not renumber, so the held tail key (turn 475, still present) is served, never rebased.
        port, tok, p, cwd, state = self._boot("compact", lambda cwd: _turns_text(cwd, 0, 606, boundary_at=600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)
        full = self._repair_full(c, U(475))
        self.assertNotIn("rebased", full, "a compaction is not a shorter tail: the held key is present, never rebased: %r" % {k: full.get(k) for k in ("tailLo", "rebased")})
        self.assertIsNotNone(full.get("tailLo"), "a compaction keeps a numeric tailLo (a head floor, not a renumber): %r" % full.get("tailLo"))

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


    # ── K7 / M1a: an overlay-card kind or a Codex echo-<hex> key (no colon, not a uuid) is KEPT, never rebased ──
    def test_k7_an_overlay_or_echo_key_never_rebases(self):
        # _key_in_transcript checks a uuid SHAPE, not a colon; `todo` and `echo-<hex>` carry no colon and are not record
        # uuids, so they are kept. Red at the base (the colon test: `todo` had no colon, the membership scan ran, found
        # nothing, and emitted rebased=True on an intact 600-turn transcript).
        port, tok, p, cwd, state = self._boot("overlay", lambda cwd: _turns_text(cwd, 0, 600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)
        for bad in ("todo", "echo-abcdef123456"):
            full = self._repair_full(c, bad)
            self.assertNotIn("rebased", full, "a non-uuid key %r is kept, never rebased on an intact transcript: %r" % (bad, {k: full.get(k) for k in ("tailLo", "rebased")}))

    # ── K8 / M3: the wire key is consumed and cleared, so a no-key needFull after a keyed one gets today's plain frame ──
    def test_k8_a_no_key_needfull_after_a_keyed_one_is_not_served_from_the_remembered_key(self):
        # Red at the base (heldTailFirst[sid] persisted, so the second, keyless needFull was served from the remembered
        # key: a second rebased the page never asked for).
        port, tok, p, cwd, state = self._boot("m3", lambda cwd: _turns_text(cwd, 0, 600))
        c = ChatClient(port, tok, SID)
        c.send({"type": "ready", "proto": 2})
        self._first_full(c)
        r1 = self._repair_full(c, U(5000))                       # a keyed needFull naming a base GONE from this 600-turn session
        self.assertTrue(r1.get("rebased") is True, "premise: the keyed needFull for a gone base rebased: %r" % {k: r1.get(k) for k in ("tailLo", "rebased")})
        r2 = self._repair_full(c, None, with_key=False)          # a NO-key needFull (a click, the prefetch)
        self.assertNotIn("rebased", r2, "a no-key needFull after a keyed one gets today's plain frame, not the remembered key's rebased (M3): %r" % {k: r2.get(k) for k in ("tailLo", "rebased")})

    # ── K9 / M2: the held-key local must not clobber the `held_first` BOOL _note_chat_full reads (firstHeld on baseGone) ──
    def test_k9_the_held_key_local_does_not_clobber_the_firstheld_bool(self):
        # M2 (2026-09-19 round two): a baseGone full's chatFull row must read firstHeld from the BOOL (held_first =
        # `pf is not None`, False on a baseGone), never the held-tail KEY. A BEHAVIOURAL pin here is inherently racy: it
        # needs a proactive baseGone full, which depends on the pusher re-discovering a fingerprint-busted shrink and
        # pushing within a bound, and a cold or contended box misses even 45 s (observed on a fresh detached checkout).
        # No synchronous, echat-preserving push exists to force it (activeTab only wakes the pusher). So this pins the fix
        # at the source, where it is exact and deterministic: the held-tail key is its own local `held_key`, the
        # `held_first` bool is set and unclobbered, and the bool is the argument _note_chat_full receives for firstHeld.
        # Red at the round-one head, where `held_first = pc.get("first")` reassigned the bool to the key.
        src = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py")).read()
        i = src.index("def _send_chat_proto2(")
        fn = src[i:src.index("\ndef ", i + 1)]
        self.assertIn('held_key = pc.get("first")', fn, "the held-tail key is its OWN local (held_key), not the held_first bool")
        self.assertIn("held_first = pf is not None", fn, "the held_first BOOL is set")
        self.assertNotIn('held_first = pc.get("first")', fn, "the bool must not be reassigned to the key (the round-one bug)")
        self.assertIn("_note_chat_full(c, sid, reason, change_from, total, held_first, pl is not None)", fn,
                      "the BOOL held_first is what _note_chat_full receives for firstHeld")

if __name__ == "__main__":
    unittest.main()
