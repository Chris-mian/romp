#!/usr/bin/env python3
"""SDK-session lifecycle hardening (2026-07-05: a kernel death stranded every SDK session in
"purgatory" — cut turns never resumed, in-memory queues silently dropped, one orphaned CLI).

Covers the backend half:
  * queue persistence — SdkSession._pending mirrors to the registry on every mutation and is
    re-seeded from it, so a kernel death can DELAY queued turns but never lose them;
  * last_state_value — the cut-turn discriminator reads the last STATE record through the
    interleaved awaiting overlays (the boot heal itself appends one);
  * find_orphan_clis — matches only SDK-driven CLIs (--resume <ours> + stream-json), never a
    tmux session's interactive `claude --resume`;
  * _boot_reconcile — resumes exactly the cut-turn / queued sessions (a user-interrupted or
    cleanly-finished session stays lazy), prepends the visible continuation nudge, reaps orphans;
  * drain — the SIGTERM path stops every running session, counts in-flight turns, and writes NO
    idle/waiting state (the trailing 'working' IS the next boot's resume marker).

All deterministic: no SDK import, no real claude processes (ps/os.kill are patched).
"""
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend", os.path.join(BIN, "romp_sdk_backend.py")).load_module()


def _backend(d=None):
    return sb.SdkBackend(d or tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)


def _reg(d, sid, **extra):
    r = {"sid": sid, "name": "s-" + sid[:4], "cwd": "/tmp", "alive": True, "lastSid": sid}
    r.update(extra)
    sb.write_reg(Path(d), sid, r)
    return r


class LastStateValue(unittest.TestCase):
    def test_reads_through_awaiting_overlays(self):
        d = tempfile.mkdtemp()
        sid = "11111111-2222-3333-4444-555555555555"
        sb.append_state(Path(d), sid, "working")
        sb.append_awaiting(Path(d), sid, False)      # the boot heal appends exactly this overlay
        self.assertEqual(sb.last_state_value(Path(d), sid), "working",
                         "an overlay after the state record must not hide the cut-turn marker")
        # last_state (the literal last line) would have returned the overlay — that's the trap
        self.assertNotIn("state", sb.last_state(Path(d), sid))

    def test_empty_and_missing(self):
        d = tempfile.mkdtemp()
        self.assertEqual(sb.last_state_value(Path(d), "nope"), "")


class FindOrphanClis(unittest.TestCase):
    SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_matches_only_sdk_clis_resuming_ours(self):
        lines = [
            # ours, SDK-driven (stream-json) → matched
            " 4242 /x/claude --output-format stream-json --resume %s --input-format stream-json" % self.SID,
            # a TMUX session's interactive resume (no stream-json mark) → never touched
            " 4243 claude --resume %s --name termsess" % self.SID,
            # SDK-driven but a sid we don't own → not ours to reap
            " 4244 /x/claude --resume ffffffff-0000-1111-2222-333333333333 --input-format stream-json",
            # junk / short lines are skipped, not crashed on
            "garbage", " 99", "",
        ]
        self.assertEqual(sb.find_orphan_clis(lines, [self.SID]), [4242])

    def test_empty_sids_match_nothing(self):
        lines = [" 1 claude --resume  --input-format stream-json"]
        self.assertEqual(sb.find_orphan_clis(lines, [""]), [])


class QueuePersistence(unittest.TestCase):
    def test_enqueue_and_unqueue_mirror_to_registry(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-2222-3333-4444-666666666666"
        reg = _reg(d, sid)
        s = sb.SdkSession(be, reg)                   # never started: pure kernel-thread surface
        s.enqueue("first")
        s.enqueue("second")
        self.assertEqual(sb.read_reg(Path(d), sid).get("queue"), ["first", "second"])
        self.assertEqual(s.unqueue(0), "first")
        self.assertEqual(sb.read_reg(Path(d), sid).get("queue"), ["second"],
                         "a canceled turn leaves the persisted queue too")

    def test_init_seeds_pending_from_persisted_queue(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-2222-3333-4444-777777777777"
        reg = _reg(d, sid, queue=["held over", "", 42, "and this"])
        s = sb.SdkSession(be, reg)
        self.assertEqual(s.pending(), ["held over", "and this"],
                         "restores strings only — junk entries never wedge delivery")


class BootReconcile(unittest.TestCase):
    def _setup(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        be._ensured = []
        be._ensure = lambda sid: be._ensured.append(sid)
        return d, be

    def test_resumes_exactly_cut_and_queued_sessions(self):
        d, be = self._setup()
        cut = "11111111-aaaa-0000-0000-000000000001"       # tail 'working' → cut by the kernel death
        queued = "11111111-aaaa-0000-0000-000000000002"    # finished, but has a persisted queue
        interrupted = "11111111-aaaa-0000-0000-000000000003"  # user interrupt wrote 'idle'
        finished = "11111111-aaaa-0000-0000-000000000004"  # clean turn end wrote 'waiting'
        dead = "11111111-aaaa-0000-0000-000000000005"
        regs = [_reg(d, cut), _reg(d, queued, queue=["waiting msg"]),
                _reg(d, interrupted), _reg(d, finished), _reg(d, dead, alive=False)]
        sb.append_state(Path(d), cut, "working")
        sb.append_state(Path(d), queued, "waiting")
        sb.append_state(Path(d), interrupted, "working")
        sb.append_state(Path(d), interrupted, "idle")      # the user-interrupt marker
        sb.append_state(Path(d), finished, "waiting")
        sb.append_state(Path(d), dead, "working")          # dead: even a 'working' tail stays dead
        with mock.patch.object(sb.subprocess, "run",
                               return_value=mock.Mock(stdout="")):
            be._boot_reconcile(regs)
        self.assertEqual(sorted(be._ensured), sorted([cut, queued]),
                         "user-interrupted / finished / dead sessions stay lazy")

    def test_cut_turn_gets_the_nudge_prepended_before_its_queue(self):
        d, be = self._setup()
        cut = "11111111-aaaa-0000-0000-00000000000a"
        _reg(d, cut, queue=["sent during the outage"])
        sb.append_state(Path(d), cut, "working")
        sb.append_awaiting(Path(d), cut, False)            # the boot heal's overlay must not mask the cut
        with mock.patch.object(sb.subprocess, "run", return_value=mock.Mock(stdout="")):
            be._boot_reconcile([sb.read_reg(Path(d), cut)])
        q = sb.read_reg(Path(d), cut).get("queue")
        self.assertEqual(q, [sb.BOOT_RESUME_NUDGE, "sent during the outage"],
                         "the visible continuation nudge is fed FIRST, then the restored backlog")
        self.assertEqual(be._ensured, [cut])

    def test_reaps_orphans_but_never_tmux(self):
        d, be = self._setup()
        sid = "11111111-aaaa-0000-0000-00000000000b"
        _reg(d, sid)
        sb.append_state(Path(d), sid, "working")
        ps = ("  555 /x/claude --output-format stream-json --resume %s --input-format stream-json\n"
              "  556 claude --resume %s --name termsess\n") % (sid, sid)
        killed = []
        with mock.patch.object(sb.subprocess, "run", return_value=mock.Mock(stdout=ps)), \
             mock.patch.object(sb.os, "kill", side_effect=lambda p, s: killed.append((p, s))):
            be._boot_reconcile([sb.read_reg(Path(d), sid)])
        self.assertEqual(killed, [(555, sb.signal.SIGTERM)],
                         "the SDK orphan is reaped; the tmux CLI on the same sid is untouched")

    def test_reconcile_is_opt_in(self):
        # Constructing the backend plain (tests, ad-hoc) must NOT spawn a reconcile thread; the
        # kernel opts in with reconcile=True. Pinned by patching the method and constructing both ways.
        d = tempfile.mkdtemp()
        sid = "11111111-aaaa-0000-0000-00000000000c"
        _reg(d, sid)
        sb.append_state(Path(d), sid, "working")
        with mock.patch.object(sb.SdkBackend, "_boot_reconcile") as br:
            sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
            self.assertEqual(br.call_count, 0)
            sb.SdkBackend(d, "/bin/true", lambda *a, **k: None, reconcile=True)
            deadline = time.time() + 5
            while br.call_count == 0 and time.time() < deadline:
                time.sleep(0.01)                     # the reconcile runs on its own thread
            self.assertEqual(br.call_count, 1)


class Drain(unittest.TestCase):
    def test_drain_stops_sessions_and_writes_no_state(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-aaaa-0000-0000-00000000000d"
        reg = _reg(d, sid)
        sb.append_state(Path(d), sid, "working")     # an in-flight turn's stamp
        s = sb.SdkSession(be, reg)
        s.inflight = 1
        s.thread = threading.Thread(target=lambda: time.sleep(0.01), daemon=True)
        s.thread.start()
        be.sessions[sid] = s
        r = be.drain(1.0)
        self.assertEqual((r["stopped"], r["inflight"]), (1, 1))
        self.assertTrue(s.ended, "shutdown was requested on the session")
        self.assertEqual(sb.last_state_value(Path(d), sid), "working",
                         "drain writes no idle/waiting — the trailing 'working' IS the boot "
                         "reconcile's resume marker")

    def test_drain_with_nothing_running_is_a_quiet_noop(self):
        be = _backend()
        self.assertEqual(be.drain(0.1), {"stopped": 0, "inflight": 0, "unjoined": 0})


if __name__ == "__main__":
    unittest.main()
