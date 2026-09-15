"""The judges' own process: `romp-judge --serve` (stage three of the process split, plans/judges-process.md, the child's
side). A real child interpreter over a pipe, a synthetic transcript under a temp Claude root, a fake `claude -p` that
answers a fixed result envelope, and a temp state root: one `pass` through the child writes the stores an in-process pass
over the same fixture writes in a fresh interpreter, and the protocol's roads (ready, done, tracking off, malformed,
unknown op, busy, a raising tier, quit, end of input) each answer as the protocol says. No real prompt or transcript text:
every string here is invented."""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the loads (the modules resolve their state root at import time; only pytest runs conftest's floor).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
em = load_source("romp_event_model_serve", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge_serve", os.path.join(BIN, "romp-judge"))

NOW = 1781100000
SID = "11111111-2222-4333-8444-000000000501"
T0 = NOW - 3600
ENVELOPE = os.path.join(HERE, "fixtures", "claude-p-result-envelope-standard.json")

FAKE_CLAUDE = r'''#!/usr/bin/env python3
"""A fake `claude -p` for the judge child's tests: one fixed result envelope, every call logged. Invented text only."""
import json, os, sys
log = os.environ.get("SERVE_TEST_CLAUDE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps(sys.argv[1:3]) + "\n")
if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--version"):
    print("2.1.0 (fake)"); sys.exit(0)
sys.stdin.read()
env = json.load(open(os.environ["SERVE_TEST_ENVELOPE"]))
env["result"] = "A short synthetic caption."
print(json.dumps(env))
'''


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": SID, "cwd": "/TESTDIR",
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": SID, "cwd": "/TESTDIR",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


RECORDS = [uline(T0, "please fix the flicker on the notes page", "u1"),
           aline(T0 + 30, "Fixed the flicker: the list re-rendered on every tick.", "a1", "u1"),
           uline(T0 + 300, "now add a test for it", "u2", "a1"),
           aline(T0 + 360, "Added a test that pins the render count.", "a2", "u2")]

STORE_DIRS = ("captions", "archive", "goals", "goals-archive", "episodes", "states", "names")


def _tree(state_root):
    """{relative path: content} of the judge stores under a state root, the volatile logs (errors, usage, scratch, the units
    cache keyed on this process) left out. An append log (.jsonl) compares as the SORTED tuple of its lines: its rows land in
    the order the tiers' pool workers finish, which differs between any two passes; the rows themselves must be the same."""
    out = {}
    for sub in STORE_DIRS:
        base = Path(state_root) / "romp" / sub
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                data = p.read_bytes()
                out[str(p.relative_to(Path(state_root) / "romp"))] = tuple(sorted(data.splitlines())) if p.suffix == ".jsonl" else data
    return out


class _Child:
    """One `romp-judge --serve` child over a pipe, its stdout lines on a queue, its stderr kept."""
    def __init__(self, env, td):
        self.proc = subprocess.Popen([sys.executable, os.path.join(BIN, "romp-judge"), "--serve"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=td)
        self.lines = queue.Queue()
        self.err = []
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.lines.put), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.err.append), daemon=True).start()

    @staticmethod
    def _pump(stream, sink):
        for line in iter(stream.readline, ""):
            sink(line)

    def send(self, obj):
        self.proc.stdin.write((json.dumps(obj) if not isinstance(obj, str) else obj) + "\n"); self.proc.stdin.flush()

    def line(self, timeout=120):
        """The next protocol line; fails at once when the child has exited with nothing queued (a base whose CLI knows no
        --serve prints its usage and exits 2), else after `timeout` seconds."""
        for _ in range(max(1, int(timeout / 0.25))):
            try:
                return json.loads(self.lines.get(timeout=0.25))
            except queue.Empty:
                if self.proc.poll() is not None and self.lines.empty():
                    break
        raise AssertionError("no protocol line (exit %r; stderr: %s)" % (self.proc.poll(), "".join(self.err)[-600:]))

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=10)


class Harness(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="romp-judge-serve-")
        self.addCleanup(shutil.rmtree, self.td, True)
        self.claude_root = os.path.join(self.td, "claude")
        cdir = os.path.join(self.td, "launchdir"); os.makedirs(cdir)
        munged = jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cdir))
        pdir = os.path.join(self.claude_root, "projects", munged); os.makedirs(pdir)
        with open(os.path.join(pdir, SID + ".jsonl"), "w") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in RECORDS))
        self.cdir = cdir
        self.fake = os.path.join(self.td, "fake_claude_p.py")
        with open(self.fake, "w") as fh:
            fh.write(FAKE_CLAUDE)
        os.chmod(self.fake, 0o755)
        self.children = []
        self.addCleanup(self._close_children)

    def _close_children(self):
        for c in self.children:
            c.close()
            if c.proc.poll() is None:
                c.proc.kill()

    def state_root(self, tag):
        root = os.path.join(self.td, "state-" + tag); os.makedirs(os.path.join(root, "romp", "names"))
        with open(os.path.join(root, "romp", "session-hosts"), "w") as fh:
            fh.write("off")
        with open(os.path.join(root, "romp", "names", SID), "w") as fh:
            fh.write("web\t%s\t#abcdef\n" % self.cdir)
        return root

    def env(self, root, **extra):
        env = dict(os.environ, XDG_STATE_HOME=root, CLAUDE_CONFIG_DIR=self.claude_root, ROMP_CLAUDE_BIN=self.fake,
                   SERVE_TEST_ENVELOPE=ENVELOPE, SERVE_TEST_CLAUDE_LOG=os.path.join(root, "claude-calls.log"),
                   ROMP_POSTAL_PORT=str(20000 + os.getpid() % 20000), ROMP_POSTAL_PEERS="0", ROMP_POSTAL_CLIENT_ONLY="1")
        for k in ("ROMP_STATE_DIR", "ROMP_MANAGER_PID", "ROMP_KERNEL_PORT", "ROMP_JUDGE_SERVE_FAULT"):
            env.pop(k, None)
        env.update(extra)
        return env

    def child(self, root, **extra):
        c = _Child(self.env(root, **extra), self.td)
        self.children.append(c)
        return c

    def calls(self, root):
        p = os.path.join(root, "claude-calls.log")
        return open(p).read().splitlines() if os.path.exists(p) else []


class ReadyLine(Harness):
    def test_the_child_announces_itself_with_the_protocol_and_judge_versions(self):
        root = self.state_root("ready"); c = self.child(root)
        ready = c.line()
        self.assertEqual(ready["op"], "ready")
        self.assertEqual(ready["pid"], c.proc.pid)
        self.assertEqual(ready["protocolVersion"], jd.PROTOCOL_VERSION); self.assertIsInstance(ready["protocolVersion"], int)
        self.assertEqual(ready["judgeVersion"], open(os.path.join(ROOT, "VERSION")).read().strip())
        c.send({"op": "quit"}); c.proc.wait(timeout=60)
        self.assertEqual(c.proc.returncode, 0)


class OnePass(Harness):
    def test_one_pass_through_the_child_writes_the_stores_an_in_process_pass_writes(self):
        root = self.state_root("child"); c = self.child(root)
        self.assertEqual(c.line()["op"], "ready")
        c.send({"op": "pass", "seq": 1, "now": NOW + 0.5, "tracking": True})
        done = c.line()
        self.assertEqual((done["op"], done["seq"], done["tierStarts"]), ("done", 1, 2), done)
        self.assertGreaterEqual(done["wallMs"], 0.0); self.assertGreaterEqual(done["tierCpuMs"], 0.0); self.assertGreaterEqual(done["workerCpuMs"], 0.0)
        self.assertIsNone(done["failures"], done["failures"])
        self.assertIn("wholeReads", done["recordCache"]); self.assertIn("parse", done["asmCheckpoint"])
        c.send({"op": "quit"}); c.proc.wait(timeout=60); self.assertEqual(c.proc.returncode, 0)
        child_calls = self.calls(root)
        self.assertTrue(child_calls, "the pass reached the model road through the fake CLI")
        # the reference: the same fixture, the in-process pass (both tiers under one frame) in a FRESH interpreter over its own root
        ref = self.state_root("ref")
        prog = "\n".join([
            "import os, sys",
            "sys.path.insert(0, %r)" % HERE,
            "from romp_load import load_source",
            "jd = load_source('romp_judge_ref', %r)" % os.path.join(BIN, "romp-judge"),
            "frame = jd.begin_pass_frame()",
            "jd.run_index(now=%d)" % NOW,
            "jd.run_triage(now=%d)" % NOW,
            "jd.end_pass_frame(frame)",
        ])
        r = subprocess.run([sys.executable, "-c", prog], env=self.env(ref), cwd=self.td, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(_tree(root), _tree(ref), "the child's stores are the in-process pass's, file for file")
        self.assertEqual(len(child_calls), len(self.calls(ref)), "the same number of model calls")
        self.assertTrue(all(l.startswith("romp-judge: ") for l in c.err if l.strip()), "every stderr line carries the prefix: %r" % c.err[:5])

    def test_tracking_off_starts_no_tier_and_makes_no_call(self):
        root = self.state_root("off"); c = self.child(root)
        self.assertEqual(c.line()["op"], "ready")
        c.send({"op": "pass", "seq": 7, "now": NOW, "tracking": False})
        done = c.line()
        self.assertEqual((done["op"], done["seq"], done["tierStarts"], done["failures"]), ("done", 7, 0, None), done)
        self.assertEqual(self.calls(root), [], "no kernel-initiated model call with tracking off")
        self.assertEqual(_tree(root).keys() - {"names/" + SID}, set(), "no store written")
        c.send({"op": "quit"}); c.proc.wait(timeout=60); self.assertEqual(c.proc.returncode, 0)


class Roads(Harness):
    def test_a_malformed_line_and_an_unknown_op_are_answered_and_the_loop_continues(self):
        root = self.state_root("bad"); c = self.child(root)
        self.assertEqual(c.line()["op"], "ready")
        c.send("this is not json")
        self.assertEqual(c.line(), {"op": "error", "seq": None, "reason": "malformed"})
        c.send("[1, 2, 3]")
        self.assertEqual(c.line(), {"op": "error", "seq": None, "reason": "malformed"})
        c.send({"op": "dance", "seq": 4})
        self.assertEqual(c.line(), {"op": "error", "seq": 4, "reason": "unknownOp"})
        c.send({"op": "pass", "seq": 5, "now": NOW, "tracking": False})
        self.assertEqual(c.line()["seq"], 5, "the loop still answers a pass")
        c.send({"op": "quit"}); c.proc.wait(timeout=60); self.assertEqual(c.proc.returncode, 0)

    def test_a_pass_during_a_pass_is_refused_busy_and_never_queued(self):
        root = self.state_root("busy"); c = self.child(root, ROMP_JUDGE_SERVE_FAULT="sleep:index:2.0")
        self.assertEqual(c.line()["op"], "ready")
        c.send({"op": "pass", "seq": 1, "now": NOW, "tracking": True})
        time.sleep(0.3)                                        # the first pass is inside its sleeping tier
        c.send({"op": "pass", "seq": 2, "now": NOW, "tracking": True})
        first, second = c.line(), c.line()
        self.assertEqual(first, {"op": "error", "seq": 2, "reason": "busy"}, "the second request is refused at once")
        self.assertEqual((second["op"], second["seq"]), ("done", 1))
        c.send({"op": "pass", "seq": 3, "now": NOW, "tracking": False})
        third = c.line()
        self.assertEqual((third["op"], third["seq"]), ("done", 3), "nothing was queued: no done for seq 2, the next pass answers")
        c.send({"op": "quit"}); c.proc.wait(timeout=60); self.assertEqual(c.proc.returncode, 0)

    def test_a_tier_that_raises_is_counted_and_the_pass_still_answers(self):
        root = self.state_root("raise"); c = self.child(root, ROMP_JUDGE_SERVE_FAULT="raise:triage")
        self.assertEqual(c.line()["op"], "ready")
        c.send({"op": "pass", "seq": 1, "now": NOW, "tracking": True})
        done = c.line()
        self.assertEqual((done["op"], done["seq"], done["tierStarts"]), ("done", 1, 2))
        self.assertEqual(done["failures"]["count"], 1); self.assertIn("RuntimeError", done["failures"]["first"])
        c.send({"op": "pass", "seq": 2, "now": NOW, "tracking": False})
        self.assertEqual(c.line()["seq"], 2, "the child is alive after a tier crash")
        c.send({"op": "quit"}); c.proc.wait(timeout=60); self.assertEqual(c.proc.returncode, 0)
        joined = "".join(c.err)
        self.assertIn("romp-judge: serve tier triage:", joined)
        self.assertTrue(all(l.startswith("romp-judge: ") for l in c.err if l.strip()), "every stderr line carries the prefix")

    def test_the_end_of_input_ends_the_child_with_exit_zero(self):
        root = self.state_root("eof"); c = self.child(root)
        self.assertEqual(c.line()["op"], "ready")
        c.proc.stdin.close(); c.proc.wait(timeout=60)
        self.assertEqual(c.proc.returncode, 0)
        self.assertIn("romp-judge: serve: exiting", "".join(c.err))


class Pins(unittest.TestCase):
    def test_main_dispatches_serve_and_the_usage_names_it(self):
        import inspect
        src = inspect.getsource(jd.main)
        self.assertIn('args[0] == "--serve"', src)
        self.assertIn("sys.exit(serve())", src)
        self.assertIn("--serve |", src, "the usage line names the arm")

    def test_the_pass_mirrors_the_producer(self):
        import inspect
        src = inspect.getsource(jd._serve_pass)
        self.assertIn("frame = begin_pass_frame()", src); self.assertIn("end_pass_frame(frame)", src)
        self.assertIn("run_index(now=now)", src); self.assertIn("run_triage(now=now)", src)
        self.assertIn("judge_worker_cpu_ms()", src)
        self.assertIn('_set_stage("judge." + tier)', inspect.getsource(jd._serve_tier), "the tier threads carry their stage mark")
        self.assertIn("em.set_stage_provider(_set_stage)", inspect.getsource(jd.serve), "the child installs its own provider")


if __name__ == "__main__":
    unittest.main()
