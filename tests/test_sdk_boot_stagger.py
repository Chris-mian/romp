#!/usr/bin/env python3
"""Staggered boot-reconcile resumes (2026-07-20). Spawning every reconciled session's CLI at once
detonated a fleet-wide CPU storm — each resumed claude burns ~a full core catching up on its
transcript, so a 13-session restart pegged the machine (load ~20) and starved the kernel's own boot;
the user's restart looked hung. The reconcile now spawns behind BOOT_RESUME_CONCURRENCY semaphore
slots, each freed by the EVENT that the CLI is past its catch-up burst (its first init message, or
its thread dying), with the acquire timeout as a loud backstop only.

All deterministic: no SDK import, no real claude processes, no sleeps as the mechanism — the tests
synchronize on the stub's own call events.
"""
import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
sb = SourceFileLoader("romp_sdk_backend_stagger", os.path.join(BIN, "romp_sdk_backend.py")).load_module()


def _backend(d=None, log=None):
    return sb.SdkBackend(d or tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None,
                         log=log or (lambda *a, **k: None))


def _reg(d, sid, **extra):
    r = {"sid": sid, "name": "s-" + sid[:4], "cwd": "/tmp", "alive": True, "lastSid": sid}
    r.update(extra)
    sb.write_reg(Path(d), sid, r)
    return r


def _cut_regs(d, n):
    """n registries whose state tail is 'working' — cut turns the reconcile must resume."""
    regs = []
    for i in range(n):
        sid = "11111111-bbbb-0000-0000-%012d" % i
        regs.append(_reg(d, sid))
        sb.append_state(Path(d), sid, "working")
    return regs


class StaggerBoundsConcurrency(unittest.TestCase):
    def test_fourth_spawn_waits_for_a_released_slot(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        calls = queue.Queue()          # every _ensure call lands here the moment it happens
        releases = []                  # parked slot-release callbacks, NOT fired automatically
        rel_lock = threading.Lock()

        def fake_ensure(sid, on_boot_settled=None):
            with rel_lock:
                releases.append(on_boot_settled)
            calls.put(sid)

        be._ensure = fake_ensure
        regs = _cut_regs(d, sb.BOOT_RESUME_CONCURRENCY + 2)
        with mock.patch.object(sb.subprocess, "run", return_value=mock.Mock(stdout="")):
            t = threading.Thread(target=be._boot_reconcile, args=(regs,), daemon=True)
            t.start()
            # the first CONCURRENCY spawns happen freely
            first = [calls.get(timeout=10) for _ in range(sb.BOOT_RESUME_CONCURRENCY)]
            self.assertEqual(len(first), sb.BOOT_RESUME_CONCURRENCY)
            # spawn N+1 must NOT arrive while every slot is held (small negative window is the
            # only way to observe "did not happen")
            with self.assertRaises(queue.Empty):
                calls.get(timeout=0.4)
            # the settle EVENT frees a slot → the next spawn follows at once
            with rel_lock:
                cb = releases[0]
            self.assertIsNotNone(cb, "a fresh spawn must carry the slot release")
            cb()
            calls.get(timeout=10)      # spawn N+1 arrives
            with rel_lock:
                for r in releases[1:]:
                    if r:
                        r()
            calls.get(timeout=10)      # the final spawn arrives once more slots free
            t.join(timeout=10)
            self.assertFalse(t.is_alive(), "the sweep finishes once every spawn got a slot")

    def test_backstop_expiry_continues_the_sweep_loudly(self):
        d = tempfile.mkdtemp()
        logs = []
        be = _backend(d, log=lambda m: logs.append(str(m)))
        ensured = []
        be._ensure = lambda sid, on_boot_settled=None: ensured.append(sid)   # NEVER settles
        regs = _cut_regs(d, sb.BOOT_RESUME_CONCURRENCY + 2)
        with mock.patch.object(sb, "BOOT_RESUME_SLOT_S", 0.05), \
             mock.patch.object(sb.subprocess, "run", return_value=mock.Mock(stdout="")):
            be._boot_reconcile(regs)
        self.assertEqual(len(ensured), len(regs),
                         "wedged CLIs must never trap the sweep — every session still spawns")
        self.assertTrue(any("backstop expired" in m for m in logs),
                        "the backstop path is LOUD, never silent")


class FireBootSettled(unittest.TestCase):
    def _session(self, d=None):
        d = d or tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-cccc-0000-0000-000000000001"
        return be, sb.SdkSession(be, _reg(d, sid))   # never started: pure surface

    def test_fires_exactly_once(self):
        _, s = self._session()
        fired = []
        s.on_boot_settled = lambda: fired.append(1)
        s._fire_boot_settled()
        s._fire_boot_settled()                       # the init path racing the death path
        self.assertEqual(fired, [1])

    def test_callback_exception_never_propagates(self):
        _, s = self._session()
        s.on_boot_settled = mock.Mock(side_effect=RuntimeError("boom"))
        s._fire_boot_settled()                       # must not raise

    def test_thread_death_fires_the_release(self):
        be, s = self._session()
        fired = []
        s.on_boot_settled = lambda: fired.append(1)

        async def dies():
            raise RuntimeError("spawn failed")

        s._amain = dies
        with mock.patch.object(be, "_on_session_gone"):
            s._run()                                 # synchronous: the real thread body
        self.assertEqual(fired, [1], "a dead thread frees its boot-stagger slot")


class EnsureNoSpawnPaths(unittest.TestCase):
    def test_dead_registry_settles_immediately(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-dddd-0000-0000-000000000001"
        _reg(d, sid, alive=False)
        fired = []
        self.assertIsNone(be._ensure(sid, on_boot_settled=lambda: fired.append(1)))
        self.assertEqual(fired, [1], "no spawn → no CPU burst → the slot frees at once")

    def test_missing_registry_settles_immediately(self):
        be = _backend()
        fired = []
        self.assertIsNone(be._ensure("11111111-dddd-0000-0000-000000000002",
                                     on_boot_settled=lambda: fired.append(1)))
        self.assertEqual(fired, [1])

    def test_already_running_session_settles_immediately(self):
        d = tempfile.mkdtemp()
        be = _backend(d)
        sid = "11111111-dddd-0000-0000-000000000003"
        _reg(d, sid)
        alive = mock.Mock()
        alive.thread.is_alive.return_value = True
        be.sessions[sid] = alive
        fired = []
        self.assertIs(be._ensure(sid, on_boot_settled=lambda: fired.append(1)), alive)
        self.assertEqual(fired, [1], "an already-live session holds no slot")


if __name__ == "__main__":
    unittest.main()
