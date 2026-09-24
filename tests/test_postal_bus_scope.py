#!/usr/bin/env python3
"""A bus started from inside a romp session's scope gets a scope of its own (2026-09-22).

The postal bus is one process shared by every session on the machine, but `ensure` spawned it wherever the caller
stood: `start_new_session=True` makes it a session leader, and a new process session is not a new cgroup. So a bus
started by a session's postal MCP server, by the Stop hook's mail check, or by `romp refresh` / `romp mail` typed in a
session's tool shell, lived in that session's transient scope (`romp-session-<sid8>-<pid>-<t>.scope`, named by
bin/romp-cli-scope, or a session host's `romp-host-<sid8>-<t>.scope`), and died when the kernel stopped the scope: the
boot sweep of leftover session scopes and the end of an orphaned CLI's scope both run `systemctl --user stop <unit>`,
which ends every process in the unit's cgroup. The post-merge defect review reproduced that with the kernel's own sweep.

Now a caller inside a romp session (or session host) scope launches the bus as
`systemd-run --user --scope --unit=romp-postal-bus-… -- /bin/sh -c 'exec "$@" 2>&1' … <serve>`, which execs in place,
so the spawned pid is the bus. There is no pre-flight (the Stop hook calls this inside a 10 s budget): the launch is its
own probe, and its non-zero exit before the bus answers, at any check of ensure's wait or at its last, starts the bus in
place with a `fallback:` line in server.log and on stderr. A launcher still waiting on the user manager when ensure's
wait ends is left running, with a `pending:` line, and nothing kills it (the review of this lane, 2026-09-23: a kill
partway through would be a timer, would protect no caller's budget, and would put the bus back in the session's scope
whenever the manager was slow). Each launch's stderr is a capture file of its own, and the sh in the scope points the
bus's stderr back at server.log, so a fallback quotes that launch's words only, never another launcher's (fold 2 of that
review). The kernel, which runs in the service's cgroup, still spawns the bus in place: a service stop is meant to end a
wedged bus there (bin/romp-cli-scope's header). So do ROMP_CLI_SCOPE=0 and a test's temporary state root, so no suite
reaches the real systemd-run but the opt-in tests/test_postal_bus_scope_live.py (ROMP_BUS_SCOPE_LIVE=1), which drops
those signs on purpose. The kernel's orphan reap spares the bus's serve in the bus's own scope
(tests/test_cut_turn_tree_kill.py); a case below reads the kernel's side against the unit and the command a launch
names here.

Every case runs the real script's `ensure` (or `restart`) in a subprocess with a bare environment and scripted seams:
the caller's cgroup text, `which`, the clock's sleep, and a recording `subprocess.Popen` whose launches exit, hang or
answer on the pings as a clock, as the case says. No real systemd-run, no real bus, nothing listens anywhere; the one
case with real processes runs the scope's sh over a stand-in serve. The scope names come from their producers
(bin/romp-cli-scope run against a fake systemd-run, host_transport.host_scope_unit) and from the kernel's own sweep
patterns, so a rename on either side fails here. Synthetic ids only.
"""
import fcntl
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from romp_load import load_source

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
BUS = os.path.join(BIN, "romp-postal-service")
CLI_SCOPE = os.path.join(BIN, "romp-cli-scope")

sb = load_source("romp_sdk_backend_bus_scope", os.path.join(BIN, "romp_sdk_backend.py"))
ht = sb._ht()

SID = "11111111-2222-3333-4444-555555555555"
APP = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/"
SESSION_CG = APP + "romp-session-11111111-4242-1757374800.scope\n"
SERVICE_CG = APP + "romp-manager.service\n"
SWEEP_GLOBS = (sb.SCOPE_LIST_ARGV[-1], sb.HOST_SCOPE_LIST_ARGV[-1])   # what the kernel's boot sweeps list, then stop
SHIM = ["/bin/sh", "-c", 'exec "$@" 2>&1', "romp-postal-bus"]   # postal_service.BUS_SCOPE_SHIM, as its launches carry it

DRIVER = r'''
import importlib.util as u, importlib.machinery as m, json, os, shutil as real_shutil, subprocess as real, sys, time as real_time, types
bus, verbs, cfg = sys.argv[1], sys.argv[2].split("+"), json.loads(sys.argv[3])
s = u.spec_from_loader("romp_postal_scope_probe", m.SourceFileLoader("romp_postal_scope_probe", bus))
p = u.module_from_spec(s); s.loader.exec_module(p)
rec = {"popen": [], "kw": [], "run": [], "killed": [], "pings": 0, "oks": []}
plan, live = cfg["launches"], []

class Launch:
    """one Popen, played by cfg's plan entry i on the pings as a clock: it exits with `rc` once `exit_after` more pings
    have passed (at once without it), first writing `write` to its stderr (systemd-run's refusal: its stderr is its own
    capture file, an in-place serve's is server.log), or its bus answers after `answers_after` more pings (never, when
    absent). While it runs it holds a copy of its stderr, as a real launcher does, so a capture's flock lives on in it
    until it exits or its bus comes up (the sh in the scope has pointed the bus's stderr at server.log by then)"""
    def __init__(self, argv, **kw):
        i = len(rec["popen"])
        rec["popen"].append(list(argv))
        rec["kw"].append({"start_new_session": kw.get("start_new_session"),
                          "stderr": os.path.basename(getattr(kw["stderr"], "name", "") or "")})
        self.how, self.pid, self.at, self.returncode, self.up = (plan[i] if i < len(plan) else {}), 424200 + i, rec["pings"], None, False
        self.fd = os.dup(kw["stderr"].fileno())
        live.append(self)
        self.step()
    def step(self):
        if self.fd is None:
            return
        n = rec["pings"] - self.at
        if self.how.get("rc") is not None and n >= self.how.get("exit_after", 0):
            if self.how.get("write"):
                os.write(self.fd, self.how["write"].encode())
            self.returncode = self.how["rc"]
            os.close(self.fd); self.fd = None
        elif self.how.get("answers_after") is not None and n > self.how["answers_after"]:
            self.up = True
            os.close(self.fd); self.fd = None
    def poll(self):
        self.step()
        return self.returncode
    def kill(self):
        rec["killed"].append(self.pid); self.returncode = -9
    def wait(self, timeout=None):
        return self.returncode

def ping():
    rec["pings"] += 1
    for l in live:
        l.step()
    if cfg.get("holder_after") is not None and rec["pings"] > cfg["holder_after"]:
        return True                           # a bus some other caller started holds the port and answers from here on
    return any(l.up for l in live)

def run(argv, **kw):
    rec["run"].append(list(argv))
    return real.CompletedProcess(argv, 0, stdout="", stderr="")

class Shutil:
    def __getattr__(self, name): return getattr(real_shutil, name)
    def which(self, name): return (cfg["which"] + "/" + name) if cfg["which"] else None
class Time:
    def __getattr__(self, name): return getattr(real_time, name)
    def sleep(self, s): pass                  # the wait's ticks are counted, not slept

p.subprocess = types.SimpleNamespace(Popen=Launch, run=run, DEVNULL=real.DEVNULL, PIPE=real.PIPE,
                                     CompletedProcess=real.CompletedProcess, TimeoutExpired=real.TimeoutExpired)
p.shutil, p.time, p.ping = Shutil(), Time(), ping
p._proc_cgroup = lambda *a: cfg["cgroup"]     # the seam: the caller's /proc/self/cgroup
p._fixed_port_refusal = lambda: None          # the hermetic-port belt has its own module
if not cfg.get("real_test_root"):
    p._test_root_signal = lambda: None        # this driver's state root is a temporary one; the case below reads it for real
held = []
for c in cfg.get("seed_captures") or []:      # captures an earlier ensure's launches left: finished, or still held
    p.STATE.mkdir(parents=True, exist_ok=True)
    (p.STATE / c["name"]).write_text(c["text"])
    if c.get("held"):
        f = open(p.STATE / c["name"], "rb"); p.fcntl.flock(f.fileno(), p.fcntl.LOCK_EX); held.append(f)
for verb in verbs:
    rec["oks"].append(bool(getattr(p, verb)()))
rec["ok"] = rec["oks"][-1]
rec["log"] = p.LOG.read_text() if p.LOG.exists() else ""
rec["captures"] = sorted(x.name for x in p.STATE.glob("bus-launch-*"))   # what is left of the launches' own stderr
print(json.dumps(rec))
'''

ANSWERS = {"answers_after": 0}   # the bus answers at the first ping after its launch


def _drive(verb="ensure", cgroup=SESSION_CG, which="/usr/bin", launches=(ANSWERS,), real_test_root=False,
           holder_after=None, seed_log="", seed_captures=(), **env_over):
    root = tempfile.mkdtemp(prefix="postal-bus-scope-")
    try:
        with open(os.path.join(root, "session-hosts"), "w") as f:
            f.write("off")   # the repo's rule for a test that mints its own state root (nothing here starts a host)
        if seed_log:         # server.log as a machine has it: an earlier bus's lines already there
            os.makedirs(os.path.join(root, "postal"))
            with open(os.path.join(root, "postal", "server.log"), "w") as f:
                f.write(seed_log)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": "/nonexistent/bus-scope-home", "ROMP_KERNEL_NO_OPEN": "1",
               "ROMP_SERVE_TOKEN": "testtok-bus-scope", "ROMP_STATE_DIR": root, "ROMP_POSTAL_PORT": "1",
               "ROMP_KERNEL_PORT": "1"}
        env.update(env_over)
        cfg = {"cgroup": cgroup, "which": which, "launches": list(launches), "real_test_root": real_test_root,
               "holder_after": holder_after, "seed_captures": list(seed_captures)}
        r = subprocess.run([sys.executable, "-c", DRIVER, BUS, verb, json.dumps(cfg)],
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-1500:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        out["stderr"] = r.stderr
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _cli_scope_unit():
    """The unit name the real bin/romp-cli-scope gives a session's scope, read off a fake systemd-run first on PATH (it
    records each --unit= and exits 0; the wrapper's pre-flight carries none)"""
    d = tempfile.mkdtemp(prefix="bus-scope-cli-")
    try:
        fake, units = os.path.join(d, "systemd-run"), os.path.join(d, "units")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do case "$a" in --unit=*) printf "%s\\n" "${a#--unit=}" >> "$UNITS";; esac; done\n'
                    'exit 0\n')
        os.chmod(fake, 0o755)
        env = {"PATH": d + ":/usr/bin:/bin", "HOME": "/nonexistent/bus-scope-home", "UNITS": units,
               "ROMP_CLI_REAL": "/bin/true", "ROMP_SID": SID}
        r = subprocess.run(["/bin/sh", CLI_SCOPE, "--input-format", "stream-json"], env=env, capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-800:]
        with open(units) as f:
            names = f.read().split()
        assert len(names) == 1, names
        return names[0] + ".scope"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _unit_of(argv):
    units = [a for a in argv if a.startswith("--unit=")]
    return units[0][len("--unit="):] if len(units) == 1 else None


REFUSAL = "Failed to connect to bus: No such file or directory\n"
TIMEOUT = "Failed to start transient scope unit: Connection timed out\n"


def _notes(out, kind):
    return [ln for ln in out["log"].splitlines() if ("[postal] %s:" % kind) in ln]


class BusScope(unittest.TestCase):
    SERVE = [sys.executable, BUS, "serve"]

    def _assert_own_scope(self, out, launch=0):
        argv = out["popen"][launch]
        self.assertEqual(argv[:3], ["systemd-run", "--user", "--scope"], "the bus leaves the caller's scope: %r" % argv)
        self.assertIn("--quiet", argv)
        self.assertIn("--collect", argv)
        unit = _unit_of(argv)
        self.assertIsNotNone(unit, argv)
        self.assertTrue(unit.startswith("romp-postal-bus-"), unit)
        for glob in SWEEP_GLOBS:
            self.assertFalse(fnmatch.fnmatchcase(unit + ".scope", glob), "no kernel sweep lists the bus's scope: %s" % glob)
        self.assertEqual(argv[argv.index("--") + 1:], SHIM + self.SERVE,
                         "exec in place: the scope runs the sh, which execs the serve itself")
        self.assertEqual(out["kw"][launch]["start_new_session"], True)
        self.assertEqual(out["kw"][launch]["stderr"], "bus-launch-%s.err.new" % unit,
                         "systemd-run's stderr is the launch's own capture, not server.log")

    def _assert_in_place(self, out):
        self.assertTrue(out["ok"])
        self.assertEqual(out["popen"], [self.SERVE])
        self.assertEqual(out["kw"][0]["stderr"], "server.log")
        self.assertEqual(out["run"], [])
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        self.assertEqual(out["captures"], [])

    # ── red before the fix: the bus stayed in the caller's scope ────────────────────────────────────────────────────
    def test_a_bus_started_from_inside_a_session_scope_gets_a_scope_of_its_own(self):
        out = _drive(cgroup=SESSION_CG)
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 1, out)
        self.assertEqual(out["run"], [], "no pre-flight: the launch is its own probe, inside the Stop hook's budget")
        self.assertEqual(out["killed"], [])
        self.assertEqual(out["captures"], [], "the launch that became the bus left no capture behind")
        self.assertNotIn("no ensure was still watching", out["log"] + out["stderr"],
                         "a launch that became the bus leaves the sweep silent (2026-09-23, the second verify pass)")

    def test_romp_refresh_from_a_session_shell_restarts_the_bus_into_its_own_scope(self):
        """`romp refresh` runs `romp-postal-service restart` from the caller's shell: no pid file here, so straight to
        ensure, and the fresh bus must not land in the caller's session scope"""
        out = _drive(verb="restart", cgroup=SESSION_CG)
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])

    def test_every_scope_the_kernel_stops_or_a_launcher_names_is_one_the_bus_leaves(self):
        """the names come from their producers and from the kernel's sweep patterns, so renaming either side without
        the other fails here (the prefixes in postal_service are a copy: KEEP IN SYNC)"""
        units = [_cli_scope_unit(), ht.host_scope_unit(SID) + ".scope"]
        units += [g.replace("*", "11111111-4242-1757374800") for g in SWEEP_GLOBS]
        self.assertTrue(units[0].startswith("romp-session-11111111-"), units[0])
        for unit in units:
            self.assertTrue(any(fnmatch.fnmatchcase(unit, g) for g in SWEEP_GLOBS), "a scope the kernel sweeps: " + unit)
            out = _drive(cgroup=APP + unit + "\n")
            self._assert_own_scope(out)
            self.assertTrue(out["ok"], unit)

    def test_a_refused_scope_starts_the_bus_in_place_and_says_so(self):
        """systemd-run exits with its reason in its capture: that exit, before the bus answered, is the event that
        starts the bus in place, said in the log and to the caller, quoting the launch's own words"""
        refused = {"rc": 1, "write": REFUSAL}
        out = _drive(cgroup=SESSION_CG, launches=(refused, ANSWERS))
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 2, out)
        self.assertEqual(out["popen"][1], self.SERVE, "then in place")
        self.assertEqual(out["killed"], [])
        note = _notes(out, "fallback")
        self.assertEqual(len(note), 1, out["log"])
        self.assertIn("exited 1 before the bus answered (Failed to connect to bus: No such file or directory)", note[0])
        self.assertIn("inside romp-session-11111111-4242-1757374800.scope", note[0], "names the scope it now shares")
        self.assertIn("[postal] fallback:", out["stderr"], "and tells the caller too")
        self.assertEqual(out["captures"], [], "the capture is removed once read")
        self.assertEqual(len([ln for ln in out["log"].splitlines() if "Failed to connect" in ln]), 1,
                         "its words are said once, in the fallback line: %s" % out["log"])
        self.assertEqual(out["kw"][1], {"start_new_session": True, "stderr": "server.log"},
                         "the bus in place runs detached, its stderr the log, as before the lane")

    def test_a_refusal_seen_only_at_the_waits_last_check_still_starts_the_bus_in_place(self):
        """fold 2 of the review (2026-09-23): a launcher whose non-zero exit only the check after ensure's loop saw once
        started no bus and wrote nothing. That check now reads the exit as every tick does: the fallback line, quoting
        the launch, and the bus in place; ensure's wait is over, so it returns False while that bus comes up"""
        late = {"rc": 1, "exit_after": 41, "write": TIMEOUT}   # launched at ping 1: exits at ping 42, the last check's
        out = _drive(cgroup=SESSION_CG, launches=(late, ANSWERS))
        self._assert_own_scope(out)
        self.assertFalse(out["ok"], "the in-place bus answers after the wait")
        self.assertEqual(len(out["popen"]), 2, "the launcher, then the bus in place: %r" % out["popen"])
        self.assertEqual(out["popen"][1], self.SERVE)
        note = _notes(out, "fallback")
        self.assertEqual(len(note), 1, out["log"])
        self.assertIn("exited 1 before the bus answered (Failed to start transient scope unit: Connection timed out)",
                      note[0])
        self.assertEqual(_notes(out, "pending"), [], "an exited launch is not pending")
        self.assertEqual(out["captures"], [])

    def test_a_launch_still_waiting_on_the_user_manager_is_left_running_past_the_wait(self):
        """a launcher that neither exits nor answers is systemd-run still waiting on the user manager. Nothing kills it
        (the review of this lane, 2026-09-23): it holds no caller, since its output goes to server.log and its capture,
        and it runs in a process session of its own, and a kill would put the bus back in the session's scope just when
        the manager was about to answer. ensure returns as for any slow bus, and a `pending:` line says what is still
        under way and what comes of a later non-zero exit"""
        out = _drive(cgroup=SESSION_CG, launches=({}, ANSWERS))
        self._assert_own_scope(out)
        self.assertFalse(out["ok"], "no bus answered within the wait")
        self.assertEqual(len(out["popen"]), 1, "no in-place bus beside the launcher: %r" % out["popen"])
        self.assertEqual(out["killed"], [], "the launcher is left running")
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        note = _notes(out, "pending")
        self.assertEqual(len(note), 1, out["log"])
        unit = _unit_of(out["popen"][0])
        self.assertIn("(pid 424200, %s)" % unit, note[0], "names the launcher left running")
        self.assertIn("if it exits non-zero instead of starting the bus, no bus comes of it: the next ensure logs what it "
                      "said and tries again", note[0])
        self.assertIn("[postal] pending:", out["stderr"], "and tells the caller too")
        self.assertEqual(out["captures"], ["bus-launch-%s.err" % unit], "its capture, still held, is left to it")

    def test_a_fallback_quotes_its_own_launch_never_another_pending_one(self):
        """fold 2 of the review (2026-09-23): server.log is shared, so the fallback once quoted the last line it gained,
        which could be an earlier ensure's pending launcher refusing late. Here the first ensure's launch is left
        pending; during the second ensure's wait it exits with a refusal, and the second's own launch exits silent. The
        second's fallback quotes nothing, and the first launch's words reach server.log on a line of their own that
        names its unit, once its capture is no longer held"""
        first = {"rc": 1, "exit_after": 43, "write": TIMEOUT}   # launched at ping 1: exits at ping 44, in the second wait
        out = _drive(verb="ensure+ensure", cgroup=SESSION_CG, launches=(first, {"rc": 1}, ANSWERS))
        self.assertEqual(out["oks"], [False, True], out["log"])
        self.assertEqual(len(out["popen"]), 3, out["popen"])
        self.assertEqual(len(_notes(out, "pending")), 1, out["log"])
        note = _notes(out, "fallback")
        self.assertEqual(len(note), 1, out["log"])
        self.assertNotIn("Connection timed out", note[0], "another launch's words are not this one's")
        self.assertIn("exited 1 before the bus answered; starting the bus in place", note[0])
        self._assert_own_scope(out, 0)
        self._assert_own_scope(out, 1)
        self.assertEqual(out["popen"][2], self.SERVE)
        first_unit = _unit_of(out["popen"][0])
        said = [ln for ln in out["log"].splitlines() if "Connection timed out" in ln]
        self.assertEqual(said, ["[postal] the launch into a scope of its own as %s, which no ensure was still watching, "
                                "said: Failed to start transient scope unit: Connection timed out" % first_unit],
                         out["log"])
        self.assertEqual(out["captures"], [], "every finished launch's capture is gone")

    def test_an_earlier_launchs_leftover_words_are_logged_first_and_a_held_capture_is_left(self):
        """fold 2 of the review (2026-09-23): what a launch no ensure was still watching said reaches server.log when the
        next ensure launches, ahead of that ensure's own lines and attributed to the launch's unit, and its capture goes;
        a capture another launch still holds is left to it, however old"""
        done_unit, held_unit = "romp-postal-bus-1111-2222", "romp-postal-bus-3333-4444"
        seeds = ({"name": "bus-launch-%s.err" % done_unit, "text": TIMEOUT},
                 {"name": "bus-launch-%s.err" % held_unit, "text": "", "held": True})
        out = _drive(cgroup=SESSION_CG, launches=({"rc": 1, "write": REFUSAL}, ANSWERS), seed_captures=seeds)
        self.assertTrue(out["ok"])
        lines = out["log"].splitlines()
        said = [i for i, ln in enumerate(lines) if "which no ensure was still watching" in ln]
        fell = [i for i, ln in enumerate(lines) if "[postal] fallback:" in ln]
        self.assertEqual(len(said), 1, out["log"])
        self.assertEqual(lines[said[0]], "[postal] the launch into a scope of its own as %s, which no ensure was still "
                         "watching, said: Failed to start transient scope unit: Connection timed out" % done_unit)
        self.assertEqual(len(fell), 1, out["log"])
        self.assertLess(said[0], fell[0], "the earlier launch's words come first")
        self.assertNotIn("Connection timed out", lines[fell[0]])
        self.assertEqual(out["captures"], ["bus-launch-%s.err" % held_unit], "the held capture is left, the others gone")

    def test_an_in_place_ensure_logs_a_leftover_launchs_words_too(self):
        """fold 2 of the review (2026-09-23): the pending line promises the next ensure logs what a late launch said, and
        the next ensure may be the kernel's, in place: it sweeps the finished captures as a scoped one does"""
        done_unit = "romp-postal-bus-1111-2222"
        out = _drive(cgroup=SERVICE_CG, seed_captures=({"name": "bus-launch-%s.err" % done_unit, "text": TIMEOUT},))
        self.assertTrue(out["ok"])
        self.assertEqual(out["popen"], [self.SERVE])
        self.assertIn("[postal] the launch into a scope of its own as %s, which no ensure was still watching, said: "
                      "Failed to start transient scope unit: Connection timed out" % done_unit, out["log"])
        self.assertEqual(out["captures"], [])

    def test_a_bus_slow_to_answer_is_left_to_answer_late_in_the_wait(self):
        """a launch that neither exits nor answers for most of the wait (a slow bus, or a slow user manager) is left to
        answer late in it, with no fallback and no note: nothing but its exit or its answer is read"""
        out = _drive(cgroup=SESSION_CG, launches=({"answers_after": 30},))
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 1, out)
        self.assertEqual(out["killed"], [])
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        self.assertNotIn("pending", out["log"] + out["stderr"])

    def test_a_launch_that_exits_0_because_another_bus_holds_the_port_is_not_a_fallback(self):
        """serve exits 0 when its bind finds the port taken (`bus already running`), and systemd-run passes that exit
        through, since it execs the serve. So a launch that exits 0 while another caller's bus is still coming up is
        no refusal: no fallback line and no second serve, and ensure waits for the bus holding the port"""
        out = _drive(cgroup=SESSION_CG, launches=({"rc": 0},), holder_after=3)
        self._assert_own_scope(out)
        self.assertTrue(out["ok"], "the port holder answered a few pings later")
        self.assertEqual(len(out["popen"]), 1, "no in-place serve after an exit 0: %r" % out["popen"])
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        self.assertNotIn("no ensure was still watching", out["log"] + out["stderr"], "an exit 0 says nothing afterward")

    def test_a_launch_that_exits_0_with_no_bus_answering_is_neither_a_fallback_nor_pending(self):
        """fold 2 of the review (2026-09-23), the pending line's second guard: an exited launch is not pending, and an
        exit 0 is no refusal, so a launch that exits 0 while nothing answers writes neither line and ensure returns
        False; the next ensure tries again"""
        out = _drive(cgroup=SESSION_CG, launches=({"rc": 0},))
        self._assert_own_scope(out)
        self.assertFalse(out["ok"])
        self.assertEqual(len(out["popen"]), 1, out["popen"])
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        self.assertNotIn("pending", out["log"] + out["stderr"])
        self.assertEqual(out["captures"], [])

    def test_a_refused_launch_while_another_callers_bus_answers_is_no_fallback(self):
        """fold 2 of the review (2026-09-23): the failure test pings once more before it calls an exit a refusal, since
        another caller's bus may hold the port by then; here it does, so one launch and no fallback line"""
        out = _drive(cgroup=SESSION_CG, launches=({"rc": 1, "write": REFUSAL}, {}), holder_after=2)
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 1, "no in-place serve beside the answering bus: %r" % out["popen"])
        self.assertNotIn("fallback", out["log"] + out["stderr"])
        self.assertEqual(out["captures"], [])
        # its own ensure watched it, so its words are said as a launch that lost to another bus, never as one nobody
        # was watching (2026-09-23, the second verify pass of this lane)
        self.assertIn("exited 1 while another bus answered; it said: " + REFUSAL.strip(), out["log"])
        self.assertNotIn("no ensure was still watching", out["log"] + out["stderr"])

    def test_a_fallback_happens_once_while_the_in_place_bus_starts(self):
        """a real in-place bus takes a few ticks to import and bind; until it answers, the refused launcher's exit must
        not be read again, or every tick would write another fallback line and start another serve"""
        refused = {"rc": 1, "write": REFUSAL}
        out = _drive(cgroup=SESSION_CG, launches=(refused, {"answers_after": 3}))
        self._assert_own_scope(out)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 2, "the launcher, then one in-place serve: %r" % out["popen"])
        self.assertEqual(out["popen"][1], self.SERVE)
        self.assertEqual(len(_notes(out, "fallback")), 1, out["log"])

    def test_a_silent_refused_launch_quotes_nothing_from_an_earlier_bus(self):
        """the fallback quotes only what the launch itself said: a launcher that exits without a word gets no reason of
        its own, never an earlier bus's last line"""
        old = "[postal] bus up on http://127.0.0.1:1 (pid 4141), a line an earlier bus left\n"
        out = _drive(cgroup=SESSION_CG, launches=({"rc": 1}, ANSWERS), seed_log=old)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["popen"]), 2, out)
        self.assertTrue(out["log"].startswith(old), "the earlier line is still there, untouched")
        note = _notes(out, "fallback")
        self.assertEqual(len(note), 1, out["log"])
        self.assertIn("exited 1 before the bus answered; starting the bus in place", note[0])
        self.assertNotIn("earlier bus", note[0])

    def test_the_scopes_sh_sends_the_bus_stderr_to_server_log_releases_the_capture_and_keeps_the_pid(self):
        """fold 2 of the review (2026-09-23), with real processes and no systemd: the sh the bus's scope runs before the
        serve (BUS_SCOPE_SHIM, read off a launch) points the serve's stderr at its stdout, the log, and execs it, so the
        pid is still the one launched, what the serve writes lands in the log and never in the capture, and the
        capture's flock is released while the serve still runs: the sign the sweep reads for a finished launch"""
        shim = _drive(cgroup=SESSION_CG)["popen"][0]
        shim = shim[shim.index("--") + 1:-len(self.SERVE)]
        self.assertEqual(shim, SHIM)
        d = tempfile.mkdtemp(prefix="bus-scope-shim-")
        try:
            log_path, cap_path = os.path.join(d, "server.log"), os.path.join(d, "bus-launch-x.err")
            serve = [sys.executable, "-c", "import os, sys; sys.stderr.write('serve says\\n'); sys.stderr.flush(); "
                     "print(os.getpid(), flush=True); sys.stdin.read()"]
            with open(log_path, "a") as logf, open(cap_path, "a+b") as cap:
                fcntl.flock(cap.fileno(), fcntl.LOCK_EX)
                proc = subprocess.Popen(shim + serve, stdout=logf, stderr=cap, stdin=subprocess.PIPE)
            try:
                for _ in range(600):   # its first line, not a clock: the serve's own pid on its stdout
                    with open(log_path) as f:
                        lines = f.read().split()
                    if str(proc.pid) in lines or proc.poll() is not None:
                        break
                    time.sleep(0.05)
                self.assertIn(str(proc.pid), lines, "exec in place: the serve runs as the pid launched")
                self.assertIsNone(proc.poll(), "the serve still runs")
                with open(cap_path, "rb") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)   # raises while anyone still holds it
                    self.assertEqual(f.read(), b"", "nothing the serve wrote went to the capture")
                with open(log_path) as f:
                    self.assertIn("serve says", f.read())
            finally:
                proc.stdin.close()
                proc.wait(timeout=30)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_kernels_orphan_reap_reads_the_scope_and_the_serve_this_launch_names(self):
        """the kernel spares a process only when its cgroup is the bus's own scope in the producer's whole shape and its
        command is the bus's serve (sdk_backend.bus_scope_unit_of and _is_postal_bus_serve, their names a copy of
        postal_service's and bin/'s: KEEP IN SYNC), so the unit and the commands a launch names must read as those
        there, under every name bin/ gives the script"""
        argv = _drive(cgroup=SESSION_CG)["popen"][0]
        unit = _unit_of(argv)
        self.assertIsNotNone(unit)
        self.assertEqual(sb.bus_scope_unit_of(APP + unit + ".scope\n"), unit + ".scope")
        self.assertIsNone(sb.bus_scope_unit_of(SESSION_CG), "a session's own scope is not the bus's")
        self.assertTrue(sb._is_postal_bus_serve(" ".join(self.SERVE)), "the serve itself")
        self.assertTrue(sb._is_postal_bus_serve(" ".join(argv[argv.index("--") + 1:])), "and the sh the scope runs first")
        for cmd in ("", "serve", " ".join(self.SERVE[:-1] + ["mcp"])):
            self.assertFalse(sb._is_postal_bus_serve(cmd), repr(cmd))
        target = os.path.realpath(os.path.join(ROOT, "postal", "postal_service.py"))
        names = [n for n in os.listdir(BIN) if os.path.realpath(os.path.join(BIN, n)) == target]
        self.assertIn("romp-postal-service", names)
        for name in names + ["postal_service.py"]:
            self.assertIn(name, sb.POSTAL_BUS_SERVE_NAMES, "a name the bus's script runs under")
            self.assertTrue(sb._is_postal_bus_serve("python3 /x/%s serve" % name), name)

    # ── unchanged: everyone else starts the bus in place ────────────────────────────────────────────────────────────
    @unittest.skipUnless(os.path.exists("/proc/self/cgroup"), "no procfs here")
    def test_the_caller_cgroup_is_read_from_this_process(self):
        """The scripted driver stubs _proc_cgroup, so only the opt-in live module read the real one; this pins it in the
        default run: the caller's own cgroup, never another process's (2026-09-23, the second verify pass of this lane)"""
        p = load_source("romp_postal_service_bus_scope_cgroup", os.path.join(ROOT, "postal", "postal_service.py"))
        with open("/proc/self/cgroup") as f:
            self.assertEqual(p._proc_cgroup(), f.read())

    def test_the_kernels_bus_stays_in_the_service_cgroup(self):
        """the kernel's boot ensure runs in the manager service's cgroup, where a service stop is meant to end a wedged
        bus: spawned in place, no systemd-run at all"""
        self._assert_in_place(_drive(cgroup=SERVICE_CG))

    def test_an_in_place_bus_that_answers_at_the_ping_after_the_wait_counts(self):
        """fold 2 of the review (2026-09-23): the ping after ensure's loop is the wait's last check, and a bus that
        answers there is up"""
        out = _drive(cgroup=SERVICE_CG, launches=({"answers_after": 40},))   # launched at ping 1: answers at ping 42
        self.assertTrue(out["ok"])
        self.assertEqual(out["popen"], [self.SERVE])

    def test_an_in_place_launch_that_never_answers_writes_no_pending_line(self):
        """fold 2 of the review (2026-09-23), the pending line's first guard: it is about a launch into a scope of its
        own, so an in-place bus that has not answered by the end of the wait says nothing of the kind"""
        out = _drive(cgroup=SERVICE_CG, launches=({},))
        self.assertFalse(out["ok"])
        self.assertEqual(out["popen"], [self.SERVE])
        self.assertNotIn("pending", out["log"] + out["stderr"])
        self.assertNotIn("fallback", out["log"] + out["stderr"])

    def test_no_procfs_or_no_systemd_run_spawns_in_place(self):
        for cgroup, which in (("", "/usr/bin"), (SESSION_CG, "")):
            with self.subTest(cgroup=cgroup, which=which):
                self._assert_in_place(_drive(cgroup=cgroup, which=which))

    def test_scopes_off_spawns_in_place(self):
        """ROMP_CLI_SCOPE=0 turns the session scopes off, and the bus's with them (it is also pytest's floor)"""
        self._assert_in_place(_drive(cgroup=SESSION_CG, ROMP_CLI_SCOPE="0"))

    def test_a_bus_under_a_temporary_state_root_spawns_in_place(self):
        """a test's bus is not the machine's: under a temporary state root the bus starts in place even from inside a
        session scope, so no suite run from a session's shell reaches the real systemd-run unless it roots its state
        outside the temporary directory on purpose, as only the opt-in live module does (the shell suites that start
        real buses, tests/romp-postal.bats among them, root under mktemp)"""
        self._assert_in_place(_drive(cgroup=SESSION_CG, real_test_root=True))


if __name__ == "__main__":
    unittest.main()
