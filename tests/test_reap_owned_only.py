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


def _reg(d, sid):
    r = {"sid": sid, "name": "api", "cwd": "/tmp", "alive": True, "lastSid": sid}
    sb.write_reg(Path(d), sid, r)
    return r


def _cli(pid, ppid, sid=SID):
    return "  %d %d /x/claude --output-format stream-json --resume %s --input-format stream-json" % (pid, ppid, sid)


def _scope_line(unit, desc):
    return "%s loaded active running %s" % (unit, desc)


class Boot:
    """One boot of a backend over `d`, against a scripted machine: `ps` (PS_ARGV lines), the two scope listings, the
    CLIs' environment tags and the processes' start times. Records every systemctl stop, every signal and every log
    line; nothing reaches a real process or unit."""

    def __init__(self, d, ps, sessions, hosts, tags, starts=None):
        self.d, self.ps, self.sessions, self.hosts = d, ps, sessions, hosts
        self.tags, self.starts = tags, dict(starts or {})
        self.runs, self.killed, self.said = [], [], []

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
             mock.patch.object(sb.SdkBackend, "_ensure", lambda self_, sid, **k: None):
            be._boot_reconcile([sb.read_reg(Path(self.d), SID)])
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
