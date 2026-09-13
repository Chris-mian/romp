#!/usr/bin/env python3
"""T401 (5a), the stage marks: every thread that can build a pre-cut atom or hydrate a body carries a stage mark, so the
per-stage rows on /perf (asmIndex.materializedByStage, asmCheckpoint.hydratedByStage) never read `none`. The read boot of
2026-09-13 22:01 UTC counted 206 MB hydrated and 100,000 atoms built under `none`: the judge tiers and the request handler
carried no mark, and the tiers' per-session POOL workers carried none even after the tier thread was marked, since a
thread-local does not cross into a pool worker (round two). Hermetic: synthetic fixtures, the kernel and judge loaded against
a temp state directory, threads joined explicitly. The served pin (a real boot over two documented sessions and one real
request) is tests/test_stage_marks_served.py."""
import ast
import inspect
import json
import os
import re as _re
import tempfile
import threading
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_ROOT = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _ROOT
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.makedirs(os.path.join(_ROOT, "romp"), exist_ok=True)
Path(_ROOT, "romp", "session-hosts").write_text("off\n")      # a fresh state root pins the hosts off (the 2026-09-11 rule)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_stage_marks", os.path.join(BIN, "romp-kernel"))

em = km.em
KERNEL_DIR = os.path.join(os.path.dirname(HERE), "kernel")
SOURCES = {"kernel.py": open(os.path.join(KERNEL_DIR, "kernel.py"), encoding="utf-8").read(),
           "judge.py": open(os.path.join(KERNEL_DIR, "judge.py"), encoding="utf-8").read()}
SID = "11111111-2222-4333-8444-0000000000d5"

# Threads that can build no atom and hydrate no body: pure I/O helpers, keyed by SITE (file, enclosing function or "*", target),
# each with the reason it is left unmarked. Anything else the kernel or the judge starts must carry a stage mark (T401 (5a)).
ALLOW = {
    ("kernel.py", "*", "_propagate_judge_settings"): "fans an applied settings body to linked kernels over HTTP",
    ("kernel.py", "*", "_revive_postal_bus"): "re-spawns the postal bus process",
    ("kernel.py", "*", "_wake_when_port_up"): "a socket probe on a dialed tunnel",
    ("kernel.py", "*", "_update_check_loop"): "the main-drift git probe",
    ("kernel.py", "*", "_tunnel_supervisor"): "ssh tunnel supervision and status",
    ("kernel.py", "*", "_run_main_update"): "a git fast-forward of the checkout",
    ("kernel.py", "*", "_push_settings_to_peer"): "peer HTTP with a settings body",
    ("kernel.py", "*", "_parent_watch"): "a pid probe on the spawning manager",
    ("kernel.py", "*", "_login_reader"): "drives the login CLI's output for states",
    ("kernel.py", "*", "_heartbeat"): "WS keepalive frames",
    ("kernel.py", "*", "_ws_sender"): "the WS frame writer",
    ("kernel.py", "*", "_do_warm_commands"): "lists the CLI's slash commands into the commands cache",
    ("kernel.py", "*", "_first_cycle_sampler_run"): "the first-pass stack sampler: reads frames, builds nothing",
    ("kernel.py", "*", "_fleet_restart_run"): "the remote half of a fleet restart over the tunnels, then this kernel's own",
    ("kernel.py", "*", "_ensure_postal_bus"): "starts the postal bus process",
    ("kernel.py", "*", "_sdk"): "constructs the SDK backend, whose boot reconcile reads raw records through the backend, never the "
                                "index or hydrate (sdk_backend.py makes no event-model parse or hydrate call); two wiring pins hold "
                                "its Thread line literal",
    ("kernel.py", "*", "_pusher"): "marks inside: push and connect through _push's decorator",
    ("kernel.py", "*", "_jobs_loop"): "marks inside: jobs.<name> through _job_stage",
    ("kernel.py", "*", "_pf"): "a native file dialog for the paperclip (a closure of the socket loop)",
    ("kernel.py", "*", "_gl"): "a git link subprocess for a file (a closure of the socket loop)",
    ("kernel.py", "*", "_bd"): "a native folder dialog for a field (a closure of the socket loop)",
    ("kernel.py", "*", "_ask"): "one peer's spend call over its tunnel (a closure of the spend rows)",
    ("kernel.py", "*", "one"): "one peer's status call over its tunnel (a closure of the remotes status)",
    ("kernel.py", "*", "work"): "the model price refresh over HTTP (a closure of the price refresh)",
    ("kernel.py", "*", "run"): "web push delivery to subscriptions and the peer relay POST (closures of the two push fan-outs)",
    ("kernel.py", "*", "go"): "the models frame notice (a closure of the model catalog); the warm threads' go closures are wrapped "
                              "in _stage_marked at their Thread lines and never reach this entry",
}


def _sites(fname, text):
    """Every Thread, Timer and pool construction in `text`, by the ast: (line, ctor, enclosing function name, target expression
    source or None). A regex could not cross a newline nor tell name= from target=; the ast reads both, in any keyword order."""
    tree = ast.parse(text)
    spans = []                                               # (start, end, name) of every function, innermost resolved below
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))
    def enclosing(line):
        best = None
        for a, b, n in spans:
            if a <= line <= b and (best is None or (b - a) < (best[1] - best[0])):
                best = (a, b, n)
        return best[2] if best else "<module>"
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        ctor = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if ctor not in ("Thread", "Timer", "ThreadPoolExecutor", "_TimedPool"):
            continue
        target = None
        if ctor == "Thread":
            kw = next((k for k in node.keywords if k.arg == "target"), None)
            target = kw.value if kw is not None else (node.args[1] if len(node.args) > 1 else None)
        elif ctor == "Timer":
            kw = next((k for k in node.keywords if k.arg == "function"), None)
            target = kw.value if kw is not None else (node.args[1] if len(node.args) > 1 else None)
        out.append((node.lineno, ctor, enclosing(node.lineno), ast.get_source_segment(text, target) if target is not None else None))
    return out


def _marked_at_def(text, name):
    """True when a `def name(` in `text` is decorated with _stage_marked or sets a stage in its body."""
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if _re.match(r"\s*def %s\(" % _re.escape(name), l):
            head = "\n".join(lines[max(0, i - 3):i])
            body = "\n".join(lines[i:i + 80])
            if "@_stage_marked(" in head or "_set_stage(" in body:
                return True
    return False


class StageMarksCensus(unittest.TestCase):
    def test_every_thread_and_pool_site_in_the_kernel_and_the_judge_is_marked_or_a_listed_io_helper(self):
        """T401 (5a): every Thread, Timer and pool construction site in kernel.py and judge.py, walked by the ast (keyword order
        and aliases included): a Thread or Timer target is marked (wrapped in _stage_marked at the site, decorated at its def, or
        setting a stage in its body) or is a pure I/O helper listed by SITE with its reason; a pool is marked by its submit, which
        carries the submitter's stage into the worker (pinned below), so a pool site needs no mark of its own."""
        unmarked, pools, seen = [], 0, 0
        for fname, text in SOURCES.items():
            for line, ctor, enclosing, target in _sites(fname, text):
                seen += 1
                if ctor in ("ThreadPoolExecutor", "_TimedPool"):
                    pools += 1
                    continue
                if target is None:
                    unmarked.append((fname, line, enclosing, "<no target the census can read>")); continue
                if target.startswith("_stage_marked("):
                    continue
                names = [n for n in _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", target) if _re.search(r"\bdef %s\(" % _re.escape(n), text)]
                if not names:
                    unmarked.append((fname, line, enclosing, target)); continue
                for name in names:
                    if (fname, enclosing, name) in ALLOW or (fname, "*", name) in ALLOW or _marked_at_def(text, name):
                        continue
                    unmarked.append((fname, line, enclosing, name))
        self.assertEqual(unmarked, [], "sites that can reach a build or a hydration without a stage mark (file, line, enclosing, target)")
        self.assertGreaterEqual(seen, 40, "the census walked the construction sites: %d" % seen)
        self.assertGreaterEqual(pools, 7, "the judge's pools are sites the census walked: %d" % pools)

    def test_the_pools_submit_carries_the_submitters_stage_into_the_worker(self):
        src = inspect.getsource(jd._TimedPool.submit)
        self.assertIn("stage = em._read_stage()", src, "the submitter's mark is read at submit")
        self.assertIn("em._set_stage_mark(stage)", src, "and set on the worker")
        self.assertIn("em._set_stage_mark(prev)", src, "and the worker's previous mark restored in the finally")
        self.assertIn("em.set_stage_provider(_set_stage)", SOURCES["kernel.py"], "the kernel installs its setter")

    def test_every_request_method_is_marked_with_its_route_and_the_tier_runner_with_its_tier(self):
        src = SOURCES["kernel.py"]
        for m in ("do_OPTIONS", "do_HEAD", "do_GET", "do_POST"):
            i = src.index("    def %s(self):" % m)
            head = src[max(0, i - 200):i]
            self.assertIn('@_stage_marked(lambda self: "http.%s." + _route_seg(self.path))' % m.split("_")[1], head, m)
        self.assertIn('_set_stage("judge." + threading.current_thread().name)', inspect.getsource(km._run_tier), "the tier threads")

    def test_the_route_names_the_stage_with_two_segments_where_the_roads_differ_by_the_second(self):
        self.assertEqual([km._route_seg(p) for p in ("/chat/x/y", "/ws", "/remote/h/ws", "/", "", "/perf?stacks=1", "/state?x=1",
                                                      "/push/relay", "/push", "/tunnels/dial?x=1", "/usage/fleet", "/usage")],
                         ["chat", "ws", "remote", "root", "root", "perf", "state", "push.relay", "push", "tunnels.dial", "usage.fleet", "usage"])

    def test_the_rows_noted_flag_is_set_by_compare_and_set_under_the_notes_lock(self):
        """1610 low 4, pinned by source: the race (two threads finding the corrupt row at once) is not observable in a test (60
        barrier trials noted once at head and base), so the shape is pinned: the check and the set sit under _ASM_CKPT_LOCK."""
        src = inspect.getsource(em.LazyIndex._refuse_rows)
        i_lock, i_check, i_set = src.index("with _ASM_CKPT_LOCK:"), src.index("if self._rows_noted:"), src.index("self._rows_noted = True")
        self.assertLess(i_lock, i_check); self.assertLess(i_check, i_set)


class BuildsCountUnderTheThreadsStage(unittest.TestCase):
    """A build from a marked thread lands under its name in asmIndex.materializedByStage; a build inside a judge pool worker lands
    under the tier that submitted it; an unmarked thread's reads `none`."""

    def setUp(self):
        self._prev = (em._READ_STAGE_FN[0], em._SET_STAGE_FN[0])
        em.set_read_stage_provider(km._current_read_stage)   # several kernel loads share one event model in a pytest process: the
        em.set_stage_provider(km._set_stage)                 #  providers must be THIS load's, whose thread-local the marks set

    def tearDown(self):
        em._READ_STAGE_FN[0], em._SET_STAGE_FN[0] = self._prev

    def _index(self):
        recs = [["r%d" % i, None, "u", None, i, 1000 + i, 0, None, None, None] for i in range(3)]
        rows = [json.dumps({"r": i, "s": {"type": "user", "author": "human", "t": 1000 + i}, "seq": i}, separators=(",", ":")) for i in range(3)]
        idx = em.LazyIndex({"atoms": rows, "records": recs, "fsids": []}, SID, "/TESTDIR/x.jsonl")
        return em.LazyAtoms(idx, range(3))

    def _build_on(self, runner, name=None):
        la = self._index()
        before = dict(em.asm_index_stats()["materializedByStage"])
        th = threading.Thread(target=runner, args=(lambda: la[0],), name=name); th.start(); th.join(10)
        after = em.asm_index_stats()["materializedByStage"]
        return {k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0)}

    def test_a_tier_threads_build_lands_under_judge_and_its_tier_name(self):
        delta = self._build_on(lambda build: km._run_tier(build), name="triage")
        self.assertEqual(list(delta), ["judge.triage:<lambda>"], delta)

    def test_a_pool_workers_build_lands_under_the_tier_that_submitted_it(self):
        """Round two's medium: the tier thread was marked but its per-session pool workers built under `none` (1930 of 1930 builds
        on a served boot). The pool's submit carries the mark; a build inside the worker lands under judge.<tier>."""
        def tier(build):
            with jd._TimedPool(max_workers=1) as ex:
                ex.submit(build).result(10)
        delta = self._build_on(lambda build: km._run_tier(lambda: tier(build)), name="triage")
        self.assertEqual(list(delta), ["judge.triage:<lambda>"], delta)

    def test_a_pool_worker_restores_its_previous_mark_after_the_run(self):
        seen = []
        def tier():
            with jd._TimedPool(max_workers=1) as ex:
                ex.submit(lambda: seen.append(km._current_read_stage())).result(10)
                ex.submit(lambda: seen.append(km._current_read_stage())).result(10)
                ex.submit(lambda: None).result(10)
                seen.append(ex.submit(lambda: km._current_read_stage()).result(10))
        th = threading.Thread(target=lambda: km._run_tier(tier), name="index"); th.start(); th.join(10)
        self.assertEqual(seen, ["judge.index", "judge.index", "judge.index"], seen)

    def test_an_unmarked_threads_build_reads_none_the_read_boots_face(self):
        delta = self._build_on(lambda build: build())
        self.assertEqual(len(delta), 1, delta); self.assertTrue(next(iter(delta)).startswith("none:"), delta)

    def test_the_index_block_carries_the_per_stage_map(self):
        st = em.asm_index_stats()
        self.assertIn("materializedByStage", st); self.assertIsInstance(st["materializedByStage"], dict)


if __name__ == "__main__":
    unittest.main()
