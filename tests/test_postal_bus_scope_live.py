#!/usr/bin/env python3
"""OPT-IN, real systemd: a postal bus started from inside a session's scope outlives both ways the kernel ends that
session (2026-09-23, the review of the bus-scope lane, which asked for one real-systemd check beside the scripted
seams of tests/test_postal_bus_scope.py and tests/test_cut_turn_tree_kill.py).

  * The scope stop. A caller standing in for a session's postal MCP server runs inside a transient scope named like
    a session's (`romp-session-TESTHOST-…`), calls the real `ensure` and stays alive, as the MCP server does. Stopping
    that scope, as the kernel's boot sweep and its end of an orphaned CLI do, must leave the bus answering.
  * The orphan reap's tree walk. The same caller one level down (sh standing in for the CLI, then the MCP stand-in,
    then the bus), and the real SdkBackend._end_cli_tree on the sh pid with a real `ps` listing: systemd-run execs the
    bus in place, so the bus is still in that tree, and the walk must spare it.

Run only when ROMP_BUS_SCOPE_LIVE=1 and ROMP_BUS_SCOPE_LIVE_DIR names a writable directory outside the temporary
directory (for example /var/tmp), on Linux, with a user manager that starts a transient scope: otherwise the class
is skipped (a class-level skip, so a run of this module alone exits 0, and nothing touches systemd at import; the
preflight scope starts in setUpClass, fold 2 of that review), and CI and every default run execute nothing here. It
starts and stops real transient units
on this machine's user manager, which is why it is opt-in: the caller's scope (`romp-session-TESTHOST-live-…`, a name
the kernel's sweep never matches, since TESTHOST is not a hex session id) and the bus's own (`romp-postal-bus-…`), and
it stops every one it made. Everything else is private: the state root sits under ROMP_BUS_SCOPE_LIVE_DIR, outside the
temporary directory, because under a temporary root the bus starts in place by design (_test_root_signal); HOME sits inside it;
the port is a free loopback one, never the machine's; ROMP_KERNEL_PORT=1 answers nothing; the serve token is
synthetic. The children get an environment built from scratch, without PYTEST_CURRENT_TEST, for the same reason. Only
a process carrying this test's own state root is ever signaled by the cleanup.
"""
import json
import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

LIVE_VAR = "ROMP_BUS_SCOPE_LIVE"
DIR_VAR = "ROMP_BUS_SCOPE_LIVE_DIR"
# The state root must sit OUTSIDE the temporary directory, since under it the bus is a test's and starts in place
# (_test_root_signal), so the operator names a writable directory for the opt-in run; the tests' hygiene rule forbids
# pinning a temp path to a literal directory, so there is no default (2026-09-23, the CI run of this lane)
STATE_PARENT = os.environ.get(DIR_VAR, "")


def _gate():
    """Why this module runs nothing here, or None. Reads the environment and PATH only: nothing touches systemd."""
    if os.environ.get(LIVE_VAR) != "1":
        return "opt-in: %s=1 starts real transient scopes on this machine's user manager" % LIVE_VAR
    if not sys.platform.startswith("linux") or not (shutil.which("systemd-run") and shutil.which("systemctl")):
        return "no systemd here"
    if not STATE_PARENT:
        return "opt-in: %s names a writable directory outside the temporary directory for the state root" % DIR_VAR
    if not os.access(STATE_PARENT, os.W_OK):
        return "%s is not writable" % STATE_PARENT
    return None


HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BUS = os.path.join(ROOT, "bin", "romp-postal-service")
BACKEND = os.path.join(ROOT, "bin", "romp_sdk_backend.py")
PY = sys.executable

CALLER = r'''
import importlib.util as u, importlib.machinery as m, sys, time
l = m.SourceFileLoader("live_postal", sys.argv[1]); s = u.spec_from_loader("live_postal", l); p = u.module_from_spec(s)
l.exec_module(p)
print("ensure-returned %s" % p.ensure(), flush=True)
time.sleep(300)                   # the MCP stand-in lives on, as the real one does for the CLI's life
'''

REAP = r'''
import importlib.util as u, importlib.machinery as m, json, os, subprocess, sys, tempfile
path, cli, root = sys.argv[1], int(sys.argv[2]), sys.argv[3]
l = m.SourceFileLoader("live_sdk_backend", path); s = u.spec_from_loader("live_sdk_backend", l)
sb = u.module_from_spec(s); sys.modules["live_sdk_backend"] = sb; l.exec_module(sb)
d = tempfile.mkdtemp(dir=root)
open(os.path.join(d, "session-hosts"), "w").write("off")   # a bare state dir with hosts off (the repo's rule)
logs = []
be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
be._log = lambda msg, **k: logs.append(str(msg))
ps = subprocess.run(sb.PS_ARGV, capture_output=True, text=True, timeout=10).stdout.splitlines()
print(json.dumps({"res": be._end_cli_tree(cli, ps), "logs": logs}))
'''


def _free_port():
    while True:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        if port != 25302:
            return port


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _scope_of(pid):
    try:
        with open("/proc/%d/cgroup" % pid) as f:
            return f.read().strip().rsplit("/", 1)[-1]
    except OSError:
        return ""


def _listed(unit):
    r = subprocess.run(["systemctl", "--user", "list-units", "--all", "--plain", "--no-legend", "--no-pager", unit],
                       capture_output=True, text=True, timeout=10)
    return bool(r.stdout.strip())


def _stop(unit):
    if _listed(unit):
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, text=True, timeout=30)


@unittest.skipIf(_gate(), _gate() or "")
class RealSystemdBusScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--collect",
                              "--unit=testhost-bus-scope-live-preflight-%d" % time.time_ns(), "--", "true"],
                             capture_output=True, text=True, timeout=30)
        if pre.returncode != 0:
            raise unittest.SkipTest("no user manager starts a transient scope here: %s"
                                    % (pre.stderr.strip() or pre.returncode))

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=STATE_PARENT, prefix="TESTHOST-bus-scope-live-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "home"))
        self.port = _free_port()
        path = os.path.dirname(shutil.which("systemd-run")) + ":/usr/local/bin:/usr/bin:/bin"
        env = {"PATH": path, "HOME": os.path.join(self.root, "home"), "LANG": "C.UTF-8",
               "ROMP_STATE_DIR": os.path.join(self.root, "state"), "XDG_STATE_HOME": os.path.join(self.root, "xdg"),
               "ROMP_POSTAL_PORT": str(self.port), "ROMP_KERNEL_PORT": "1", "ROMP_KERNEL_NO_OPEN": "1",
               "ROMP_SERVE_TOKEN": "testtok-bus-scope-live"}
        for k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):   # how systemd-run reaches the user manager
            if os.environ.get(k):
                env[k] = os.environ[k]
        self.env = env

    def _mine(self, pid):
        """A process carrying this test's own state root; nothing else is ever signaled here."""
        try:
            with open("/proc/%d/environ" % pid, "rb") as f:
                return ("ROMP_STATE_DIR=%s" % self.env["ROMP_STATE_DIR"]).encode() in f.read().split(b"\0")
        except OSError:
            return False

    def _end(self, pid):
        """the bus: not this process's child, so gone once its pid answers no signal"""
        if pid and _alive(pid) and self._mine(pid):
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while _alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)

    def _end_launcher(self, launcher):
        """the caller: this process's own child, so reaped here"""
        if launcher.poll() is None and self._mine(launcher.pid):
            launcher.terminate()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if self._mine(launcher.pid):
                launcher.kill()
            launcher.wait(timeout=10)

    def _ping(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/ping" % self.port, timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def _start_caller(self, cli_shell):
        """The caller in a session-named scope of its own; returns (launcher, unit, bus pid) once its ensure returned"""
        unit = "romp-session-TESTHOST-live-%d.scope" % time.time_ns()
        argv = [PY, "-c", CALLER, BUS]
        if cli_shell:                 # sh stands in for the CLI: it forks the MCP stand-in and waits on it
            argv = ["sh", "-c", '"$0" -c "$1" "$2"; exit $?'] + argv[:1] + argv[2:]
        launcher = subprocess.Popen(["systemd-run", "--user", "--scope", "--quiet", "--collect", "--unit=" + unit,
                                     "--description=TESTHOST bus-scope live test caller", "--"] + argv,
                                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL, start_new_session=True, text=True)
        self.addCleanup(_stop, unit)
        self.addCleanup(self._end_launcher, launcher)
        self.addCleanup(launcher.stdout.close)
        ready, _, _ = select.select([launcher.stdout], [], [], 30)
        line = launcher.stdout.readline() if ready else ""
        self.assertEqual(line.strip(), "ensure-returned True", "the caller's ensure brought the bus up")
        with open(os.path.join(self.root, "state", "postal", "server.pid")) as f:
            bus = int(f.read().strip())
        self.assertTrue(self._mine(bus), "server.pid names this test's own bus")
        bus_unit = _scope_of(bus)
        self.addCleanup(_stop, bus_unit)
        self.addCleanup(self._end, bus)
        self.assertTrue(bus_unit.startswith("romp-postal-bus-") and bus_unit.endswith(".scope"),
                        "the bus runs in a scope of its own, not %s" % (
                            "the caller's, where it runs here" if bus_unit == unit else "in %s" % bus_unit[:24]))
        self.assertTrue(self._ping())
        postal = os.path.join(self.root, "state", "postal")
        self.assertEqual([n for n in os.listdir(postal) if n.startswith("bus-launch-")], [],
                         "the launch's own capture was released and removed once its bus answered")
        with open(os.path.join(postal, "server.log")) as f:
            self.assertIn("[postal] bus up on http://127.0.0.1:%d (pid %d)" % (self.port, bus), f.read(),
                          "the bus's own stderr reached server.log through the scope's sh")
        return launcher, unit, bus

    def test_stopping_the_callers_scope_leaves_the_bus_it_started_answering(self):
        _, unit, bus = self._start_caller(cli_shell=False)
        subprocess.run(["systemctl", "--user", "stop", unit], check=True, capture_output=True, timeout=30)
        self.assertTrue(_alive(bus), "the bus outlived the caller's scope")
        self.assertTrue(self._ping(), "and still answers")

    def test_the_orphan_reap_spares_the_bus_the_mcp_stand_in_started(self):
        launcher, _, bus = self._start_caller(cli_shell=True)
        env = dict(self.env, ROMP_CLI_SCOPE="0")   # the reaping kernel probes no scope support of its own
        r = subprocess.run([PY, "-c", REAP, BACKEND, str(launcher.pid), self.root], env=env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["res"].get("spared"), 1, out)
        self.assertTrue(any("spared" in ln and str(bus) in ln for ln in out["logs"]), out["logs"])
        self.assertTrue(_alive(bus), "the bus outlived the reap of its caller's tree")
        self.assertTrue(self._ping(), "and still answers")
        self.assertIsNotNone(launcher.wait(timeout=10), "the CLI stand-in itself was ended")


if __name__ == "__main__":
    unittest.main()
