#!/usr/bin/env python3
"""A booting kernel reaps only what it can prove it started (2026-09-23).

systemd user units and processes are machine-wide, and a session id is not a kernel's. A lab kernel with a state
directory of its own held a session under the same id as a live session of the machine's real kernel, and each boot of
the lab kernel stopped the live session's host (its CLI exited on SIGTERM), because all three boot reapers decided
ownership from the session id plus the booting kernel's OWN state directory:
  * the orphan CLI reap (lease_census, then _end_cli_tree): any stream-json `claude` on the machine resuming one of our
    ids, with no lease in our directory and no kernel for a parent — a host-held CLI of another kernel is exactly that;
  * the leftover session-scope sweep: every `romp-session-<sid8>-*.scope` on the machine whose CLI we do not own;
  * the leftover host-scope sweep: every `romp-host-<sid8>-*.scope` with no valid lease in our directory.
Now every session CLI carries its kernel's state tag in its environment (ROMP_STATE_TAG) and every session or host scope
carries `romp-state=<tag>` in its Description, and a boot reaps only what carries its own tag. Another kernel's tag is
left alone; no tag at all (an older build's unit or CLI) is left alone too, and one log line names everything left.
A session whose conversation a spared process still holds is not resumed by that boot either (its resume would put a
second CLI on the transcript, two writers on one conversation): it stays down, said once, whatever its state tail says.

Synthetic fixtures only: placeholder session ids, fake pids above pid_max, injected listings and stop calls. Nothing here
lists, creates or stops a real systemd unit, and every backend's state root has session hosts off.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # hermetic BEFORE the load
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_CLI_SCOPE"] = "0"
sb = load_source("romp_sdk_backend_reap_owned", os.path.join(BIN, "romp_sdk_backend.py"))

SID = "11111111-2222-3333-4444-5555aaaa0923"          # the one session id both kernels hold
SID2 = "11111111-2222-3333-4444-5555bbbb0923"         # a second session of the booting kernel, held by nobody else
LINUX = sys.platform.startswith("linux") and os.path.isdir("/proc")


def _pid_max() -> int:
    try:
        return int(open("/proc/sys/kernel/pid_max").read().strip())
    except (OSError, ValueError):
        return 4194304


P = _pid_max()     # fake pids above pid_max: no real process can wear one
MANAGER = P + 1                     # the `systemd --user` subreaper an orphan re-parents to
HOST_A, CLI_A = P + 10, P + 11      # kernel A's live session: its host, and the CLI the host holds
CLI_B = P + 20                      # kernel B's own orphan from its earlier life
CLI_U = P + 30                      # an orphan-shaped CLI whose environment carries no tag (an older build's)
GONE = P + 40                       # a CLI that is gone, its scope still loaded


def _tag(d) -> str:
    """The state tag, written out: the first 16 hex digits of the SHA-256 of the resolved state directory. It is a
    contract across kernel versions (a kernel must recognise the units its previous build made), so it is pinned here
    by hand rather than read back from the code."""
    return hashlib.sha256(os.path.realpath(str(d)).encode()).hexdigest()[:16]


def _root() -> str:
    d = tempfile.mkdtemp()
    Path(d, "session-hosts").write_text("off")   # no real bin/romp-session-host from any backend in this file
    return d


def _reg(d, sid, name="api"):
    r = {"sid": sid, "name": name, "cwd": "/tmp", "alive": True, "lastSid": sid}
    sb.write_reg(Path(d), sid, r)
    return r


def _cli(pid, ppid, sid=SID):
    return "  %d %d /x/claude --output-format stream-json --resume %s --input-format stream-json" % (pid, ppid, sid)


def _scope_line(unit, desc):
    return "%s loaded active running %s" % (unit, desc)


class Boot:
    """One boot of a backend over `d`, against a scripted machine: `ps` (PS_ARGV lines), the two scope listings, the
    CLIs' environment tags and the processes' start times. Records every systemctl stop, every signal, every log
    line and every session the boot went on to start (`started`: the sids handed to _ensure, which is stubbed); nothing
    reaches a real process or unit. `sids` are the registry rows the boot reconciles, SID alone by default."""

    def __init__(self, d, ps, sessions, hosts, tags, starts=None, sids=(SID,)):
        self.d, self.ps, self.sessions, self.hosts = d, ps, sessions, hosts
        self.tags, self.starts, self.sids = tags, dict(starts or {}), tuple(sids)
        self.runs, self.killed, self.said, self.started = [], [], [], []

    def run(self, argv, **kw):
        self.runs.append(list(argv))
        out = ""
        if argv == sb.PS_ARGV:
            out = "\n".join(self.ps) + "\n"
        elif argv == sb.SCOPE_LIST_ARGV:
            out = "\n".join(self.sessions) + "\n"
        elif argv == sb.HOST_SCOPE_LIST_ARGV:
            out = "\n".join(self.hosts) + "\n"
        return mock.Mock(stdout=out, stderr="", returncode=0)

    def go(self):
        be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)
        be._log = lambda m, *a, **k: self.said.append(m)
        with mock.patch.object(sb.subprocess, "run", side_effect=self.run), \
             mock.patch.object(sb.os, "kill", side_effect=lambda p, s: self.killed.append((p, s))), \
             mock.patch.object(sb.os, "killpg", side_effect=lambda p, s: self.killed.append((p, s))), \
             mock.patch.object(sb, "proc_start", lambda p, run=None: self.starts.get(p)), \
             mock.patch.object(sb, "proc_state_tag", lambda p, **k: self.tags.get(p), create=True), \
             mock.patch.object(sb.SdkBackend, "_pid_alive", lambda self_, p: False), \
             mock.patch.object(sb.SdkBackend, "_ensure", lambda self_, sid, **k: self.started.append(sid)):
            be._boot_reconcile([sb.read_reg(Path(self.d), s) for s in self.sids])
        return be

    def stops(self):
        return [a[-1] for a in self.runs if a[:3] == ["systemctl", "--user", "stop"]]

    def signaled(self):
        return sorted({p for p, _ in self.killed})


class TwoKernelsShareASessionId(unittest.TestCase):
    """Kernel A (its own state root) runs SID live through a host; kernel B (another state root) holds a copy of SID,
    lease file and all, and boots. B's boot must leave A's CLI, A's session scope and A's host scope alone, and still
    reap its OWN leftovers of the same id from its earlier life."""

    def test_booting_the_second_kernel_never_touches_the_firsts_session_and_still_reaps_its_own(self):
        dA, dB = _root(), _root()
        _reg(dA, SID)
        _reg(dB, SID)
        now = time.time()
        # A's host holds A's CLI; A's lease names them. B's directory holds a COPY of that lease (the lab kernel's copy of
        # the session), whose beat went stale the moment it was copied: by B's reading, a lease that does not hold.
        lease = {"sid": SID, "fsid": SID, "pid": CLI_A, "start": "1000", "version": "",
                 "holder": {"pid": HOST_A, "start": "500", "kind": "host"}, "t": now}
        sb.write_lease(dA, lease)
        sb.write_lease(dB, dict(lease, t=now - 600))
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER,
              "  %d %d /usr/bin/python3 /x/romp/bin/romp-session-host /x/state/hosts/%s/spawn.json" % (HOST_A, MANAGER, SID),
              _cli(CLI_A, HOST_A),
              _cli(CLI_B, MANAGER)]            # B's own orphan: its kernel died, it re-parented to the user manager
        a_session = "romp-session-%s-%d-1757374800.scope" % (SID[:8], CLI_A)
        a_host = "romp-host-%s-1757374800000.scope" % SID[:8]
        b_session = "romp-session-%s-%d-1757374801.scope" % (SID[:8], CLI_B)
        b_gone = "romp-session-%s-%d-1757374802.scope" % (SID[:8], GONE)      # B's CLI gone, its tool's children live on
        b_host = "romp-host-%s-1757374700000.scope" % SID[:8]                  # B's dead host's scope, still loaded
        sessions = [_scope_line(a_session, "romp session %s romp-state=%s" % (SID, _tag(dA))),
                    _scope_line(b_session, "romp session %s romp-state=%s" % (SID, _tag(dB))),
                    _scope_line(b_gone, "romp session %s romp-state=%s" % (SID, _tag(dB)))]
        hosts = [_scope_line(a_host, "romp session host %s romp-state=%s" % (SID, _tag(dA))),
                 _scope_line(b_host, "romp session host %s romp-state=%s" % (SID, _tag(dB)))]
        boot = Boot(dB, ps, sessions, hosts, tags={CLI_A: _tag(dA), CLI_B: _tag(dB)},
                    starts={CLI_A: "1000", HOST_A: "500"})
        boot.go()
        self.assertNotIn(CLI_A, boot.signaled(), "kernel A's live CLI is never signaled by kernel B's boot")
        self.assertNotIn(HOST_A, boot.signaled())
        self.assertNotIn(a_session, boot.stops(), "kernel A's session scope is never stopped")
        self.assertNotIn(a_host, boot.stops(), "kernel A's host scope is never stopped")
        # …and B's own earlier life is reaped exactly as before
        self.assertEqual(boot.signaled(), [CLI_B], "B's own orphan is ended")
        self.assertEqual(sorted(boot.stops()), sorted([b_session, b_gone, b_host]),
                         "B's orphan's scope, its leftover session scope and its dead host's scope are stopped")
        # no row claims A's CLI was reaped (the copied lease's verdict was 'reaped as an orphan' before)
        rows = [json.loads(l) for l in (Path(dB) / sb.SESSION_EVENTS_FILE).read_text().splitlines()]
        self.assertFalse([r for r in rows if r.get("cliPid") == CLI_A and "reaped" in (r.get("text") or "")], rows)
        self.assertFalse([r for r in rows if r.get("kind") == "reconcile.orphan-reaped" and r.get("cliPid") == CLI_A])
        # what was left alone is said once, by name
        left = [m for m in boot.said if "left alone" in m]
        self.assertEqual(len(left), 1, boot.said)
        for name in (str(CLI_A), a_host):
            self.assertIn(name, left[0])
        self.assertNotIn(a_session, left[0], "the spared CLI's own scope is spared with it, not named twice")
        self.assertIn("another kernel", left[0])
        self.assertIsNotNone(sb.read_lease(dA, SID), "A's own lease is untouched (B never writes outside its root)")


class UntaggedIsLeftAloneAndNamed(unittest.TestCase):
    """A unit or CLI with no state tag at all (an older build's, or one whose environment cannot be read) cannot be
    attributed to this kernel: it is left alone, and ONE log line names every such thing, never stopped silently."""

    def test_untagged_units_and_cli_are_left_alone_and_one_line_names_them(self):
        d = _root()
        _reg(d, SID)
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER, _cli(CLI_U, MANAGER)]
        u_session = "romp-session-%s-%d-1757374800.scope" % (SID[:8], GONE)
        u_cli_scope = "romp-session-%s-%d-1757374801.scope" % (SID[:8], CLI_U)
        u_host = "romp-host-%s-1757374800000.scope" % SID[:8]
        sessions = [_scope_line(u_session, "romp session %s" % SID), _scope_line(u_cli_scope, "romp session %s" % SID)]
        hosts = [_scope_line(u_host, "romp session host %s" % SID)]
        boot = Boot(d, ps, sessions, hosts, tags={})       # no tag readable for any CLI
        boot.go()
        self.assertEqual(boot.signaled(), [], "an untagged CLI is never signaled")
        self.assertEqual(boot.stops(), [], "no untagged unit is stopped")
        left = [m for m in boot.said if "left alone" in m]
        self.assertEqual(len(left), 1, "one line, not one per unit: %r" % boot.said)
        for name in (str(CLI_U), u_session, u_host):
            self.assertIn(name, left[0])
        self.assertNotIn(u_cli_scope, left[0], "the spared CLI's own scope is spared with it, not listed twice")

    def test_a_clean_boot_logs_no_left_alone_line(self):
        d = _root()
        _reg(d, SID)
        boot = Boot(d, ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER], [], [], tags={})
        boot.go()
        self.assertEqual([m for m in boot.said if "left alone" in m], [])


class OwnCrashLeftoverIsStillReaped(unittest.TestCase):
    def test_own_tag_and_a_lease_whose_holder_is_gone_still_reaps(self):
        """The crash case the reaper exists for, unchanged: this kernel died, its CLI carries its tag and a lease whose
        holder is gone; the boot ends the CLI and stops its scope."""
        d = _root()
        _reg(d, SID)
        sb.write_lease(d, {"sid": SID, "fsid": SID, "pid": CLI_B, "start": "7", "version": "",
                           "holder": {"pid": P + 99, "start": "1"}, "t": time.time()})
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER, _cli(CLI_B, MANAGER)]
        unit = "romp-session-%s-%d-1757374800.scope" % (SID[:8], CLI_B)
        boot = Boot(d, ps, [_scope_line(unit, "romp session %s romp-state=%s" % (SID, _tag(d)))], [],
                    tags={CLI_B: _tag(d)}, starts={CLI_B: "7"})
        boot.go()
        self.assertEqual(boot.signaled(), [CLI_B])
        self.assertEqual(boot.stops(), [unit])
        self.assertIsNone(sb.read_lease(d, SID), "the lease that did not hold went with its CLI")
        self.assertEqual([m for m in boot.said if "left alone" in m], [])


class ASparedOrphanHoldsItsConversation(unittest.TestCase):
    """The resume rule meets the tag check. A session whose state tail is machine-active (its turn was cut by the
    kernel's death) is resumed at boot, and until the state tag its orphan was ended FIRST, so the resume never met a
    second writer. An orphan the tag check spares keeps its conversation, so the same boot must not resume that session
    on top of it: _ensure with --resume would be two writers on one transcript, the hazard the reap exists to prevent.
    The session stays down, said once, with nothing of the resume on its disk; a session with no spared orphan resumes
    exactly as before, and so does one whose orphan was this kernel's own and was ended."""

    def _states(self, d, sid):
        return [json.loads(l) for l in (Path(d) / "states" / (sid + ".jsonl")).read_text().splitlines() if l.strip()]

    def test_the_spared_orphans_session_stays_down_and_a_session_without_one_still_resumes(self):
        dA, dB = _root(), _root()
        _reg(dB, SID)
        _reg(dB, SID2, name="web")
        sb.append_state(Path(dB), SID, "working")      # a machine-active tail on each: the resume rule fires on both
        sb.append_state(Path(dB), SID2, "working")
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER,
              _cli(CLI_A, MANAGER)]         # kernel A's CLI on SID: an orphan by B's census, spared by the tag check
        boot = Boot(dB, ps, [], [], tags={CLI_A: _tag(dA)}, sids=(SID, SID2))
        boot.go()
        self.assertNotIn(CLI_A, boot.signaled())
        self.assertEqual(boot.started, [SID2], "the spared orphan's session is never started; the other one resumes")
        down = [m for m in boot.said if "stays down" in m]
        self.assertEqual(len(down), 1, boot.said)
        self.assertIn("api", down[0], "the session is named")
        self.assertIn("did not start", down[0])
        self.assertEqual(len([m for m in boot.said if "left alone" in m]), 1, "the spared process is still named once")
        # nothing of the resume reached SID's disk: no nudge in its queue, no machine-cut stamp on its tail, and the cut
        # tail itself is still there for the boot that finds the conversation free
        self.assertEqual(sb.read_reg(Path(dB), SID).get("queue") or [], [])
        self.assertFalse([r for r in self._states(dB, SID) if "machineCut" in r], self._states(dB, SID))
        self.assertEqual(sb.last_state_value(Path(dB), SID), "working")
        # ...and all of it reached SID2's, as before
        self.assertEqual((sb.read_reg(Path(dB), SID2).get("queue") or [])[:1], [sb.BOOT_RESUME_NUDGE])
        self.assertTrue([r for r in self._states(dB, SID2) if r.get("machineCut") == "restart"])
        rows = [json.loads(l) for l in (Path(dB) / sb.SESSION_EVENTS_FILE).read_text().splitlines()]
        summary = [r for r in rows if r.get("kind") == "reconcile.boot"]
        self.assertEqual(len(summary), 1, rows)
        self.assertEqual((summary[0]["sessions"], summary[0]["resumed"], summary[0]["toStart"]), (2, 1, 1))

    def test_an_untagged_orphan_holds_the_conversation_too(self):
        d = _root()
        _reg(d, SID)
        sb.append_state(Path(d), SID, "retrying")       # any machine-active state, not just working
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER, _cli(CLI_U, MANAGER)]
        boot = Boot(d, ps, [], [], tags={})             # no tag readable: an older build's CLI, spared
        boot.go()
        self.assertEqual(boot.signaled(), [])
        self.assertEqual(boot.started, [], "no resume on top of the untagged CLI")
        self.assertEqual(len([m for m in boot.said if "stays down" in m]), 1, boot.said)
        self.assertEqual(sb.read_reg(Path(d), SID).get("queue") or [], [])
        self.assertFalse([r for r in self._states(d, SID) if "machineCut" in r])

    def test_a_session_whose_own_orphan_was_ended_resumes_as_before(self):
        d = _root()
        _reg(d, SID)
        sb.append_state(Path(d), SID, "working")
        ps = ["  %d 1 /usr/lib/systemd/systemd --user" % MANAGER, _cli(CLI_B, MANAGER)]
        boot = Boot(d, ps, [], [], tags={CLI_B: _tag(d)})   # this kernel's own tag: ended first, as before
        boot.go()
        self.assertEqual(boot.signaled(), [CLI_B], "this kernel's own orphan is ended first")
        self.assertEqual(boot.started, [SID], "...and the session resumes, the conversation free")
        self.assertEqual([m for m in boot.said if "stays down" in m], [])
        self.assertEqual((sb.read_reg(Path(d), SID).get("queue") or [])[:1], [sb.BOOT_RESUME_NUDGE])
        self.assertTrue([r for r in self._states(d, SID) if r.get("machineCut") == "restart"])


class TheTag(unittest.TestCase):
    def test_the_tag_is_the_hash_of_the_resolved_state_directory(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.assertEqual(sb.state_tag_of(a), _tag(a))
        self.assertRegex(sb.state_tag_of(a), r"\A[0-9a-f]{16}\Z")
        self.assertNotEqual(sb.state_tag_of(a), sb.state_tag_of(b), "two state roots are two kernels")
        link = os.path.join(tempfile.mkdtemp(), "link")
        os.symlink(a, link)
        self.assertEqual(sb.state_tag_of(link), sb.state_tag_of(a), "a symlink to the root is the same kernel")
        self.assertEqual(sb.state_tag_of(Path(a)), sb.state_tag_of(a))

    def test_a_unit_lines_tag_is_read_from_its_description(self):
        t = "0123456789abcdef"
        line = _scope_line("romp-session-11111111-4242-1.scope", "romp session %s romp-state=%s" % (SID, t))
        self.assertEqual(sb.unit_state_tag(line), t)
        self.assertIsNone(sb.unit_state_tag(_scope_line("romp-session-11111111-4242-1.scope", "romp session %s" % SID)))
        self.assertIsNone(sb.unit_state_tag("romp-session-11111111-4242-1.scope loaded active running romp-state=0123"),
                          "a malformed tag is no tag")
        self.assertIsNone(sb.unit_state_tag("romp-session-11111111-4242-1.scope loaded active running x romp-state=%sff" % t))
        self.assertIsNone(sb.unit_state_tag(""))
        self.assertEqual(sb.unit_state_tags([line, "", "run-x.scope loaded active running y"]),
                         {"romp-session-11111111-4242-1.scope": t, "run-x.scope": None})

    def test_both_scope_listings_ask_for_the_full_description(self):
        for argv in (sb.SCOPE_LIST_ARGV, sb.HOST_SCOPE_LIST_ARGV):
            self.assertIn("--full", argv, "a truncated description would drop the tag")
            self.assertTrue(argv[-1].endswith("*.scope"), "the glob stays last")

    @unittest.skipUnless(LINUX, "reads /proc/<pid>/environ")
    def test_a_processs_tag_is_read_from_its_environment(self):
        t = "fedcba9876543210"
        env = dict(os.environ, ROMP_STATE_TAG=t)
        tagged = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE, env=env)
        self.addCleanup(tagged.wait, timeout=10); self.addCleanup(tagged.stdin.close)
        env.pop("ROMP_STATE_TAG")
        bare = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE, env=env)
        self.addCleanup(bare.wait, timeout=10); self.addCleanup(bare.stdin.close)
        env["ROMP_STATE_TAG"] = "not-a-tag"
        bad = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE, env=env)
        self.addCleanup(bad.wait, timeout=10); self.addCleanup(bad.stdin.close)
        self.assertEqual(sb.proc_state_tag(tagged.pid), t)
        self.assertIsNone(sb.proc_state_tag(bare.pid))
        self.assertIsNone(sb.proc_state_tag(bad.pid), "a value of another shape is no tag")
        self.assertIsNone(sb.proc_state_tag(P + 5), "a pid no process wears has no tag")

    def test_without_procfs_the_tag_comes_from_ps_E(self):
        t = "fedcba9876543210"
        calls = []
        def run(argv, **kw):
            calls.append(list(argv))
            return mock.Mock(stdout="/x/claude --resume %s HOME=/h ROMP_STATE_TAG=%s PATH=/bin\n" % (SID, t), returncode=0)
        self.assertEqual(sb.proc_state_tag(4242, run=run, procfs=False), t)
        self.assertEqual(calls[0][0], "ps")
        self.assertIn("-E", calls[0])
        self.assertIsNone(sb.proc_state_tag(4242, run=lambda a, **k: mock.Mock(stdout="/x/claude a b\n"), procfs=False))
        def boom(argv, **kw):
            raise OSError("no ps")
        self.assertIsNone(sb.proc_state_tag(4242, run=boom, procfs=False))


class TheProducersTagWhatTheyStart(unittest.TestCase):
    def test_a_host_scope_carries_the_tag_in_its_description(self):
        d = _root()
        be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
        be.cli_scope = True
        spec = Path(d, "hosts", SID, "spawn.json")
        spec.parent.mkdir(parents=True)
        spec.write_text("{}")
        seen = []
        class _Popen:
            def __init__(self, argv, **kw):
                seen.append(list(argv))
        with mock.patch.object(sb.shutil, "which", lambda n: "/usr/bin/" + n), \
             mock.patch.object(sb.subprocess, "Popen", _Popen):
            be._spawn_host(type("S", (), {"sid": SID, "name": "api"})(), spec)
        self.assertEqual(seen[0][0], "systemd-run")
        self.assertIn("--description=romp session host %s romp-state=%s" % (SID, _tag(d)), seen[0])


if __name__ == "__main__":
    unittest.main()
