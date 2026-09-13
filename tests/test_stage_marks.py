#!/usr/bin/env python3
"""T323 stage 1 (the user 2026-09-10): a kernel boot must not read every live transcript whole for nobody. The boot
warm parses nothing (it warms discover() only), the feed-only warm parses only sessions that moved since this boot or
are working now, the judges' passes go newest-first and yield between sessions, the two event-keyed tick jobs skip a
session whose transcript and state log are unchanged since their last look (the boot being the first baseline), and
/perf counts every cold parse so the effect is measurable. Hermetic: synthetic files under a temp root, the kernel and
judge loaded against a temp state directory, threads joined explicitly."""
import inspect
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_stage_marks", os.path.join(BIN, "romp-kernel"))
import inspect
import json
import re as _re
import threading
import unittest

em = km.em
KERNEL_SRC = open(km.__file__, encoding="utf-8").read()
SID = "11111111-2222-4333-8444-0000000000d5"

# Threads that can build no atom and hydrate no body: pure I/O helpers, each with the reason it is left unmarked. Anything
# else the kernel starts must carry a stage mark, so a build or a hydration on it never reads `none` (T401 (5a)).
ALLOW = {
    "_propagate_judge_settings": "fans an applied settings body to linked kernels over HTTP",
    "_revive_postal_bus": "re-spawns the postal bus process",
    "_wake_when_port_up": "a socket probe on a dialed tunnel",
    "_update_check_loop": "the main-drift git probe",
    "_tunnel_supervisor": "ssh tunnel supervision and status",
    "_run_main_update": "a git fast-forward of the checkout",
    "_push_settings_to_peer": "peer HTTP with a settings body",
    "_parent_watch": "a pid probe on the spawning manager",
    "_login_reader": "drives the login CLI's output for states",
    "_heartbeat": "WS keepalive frames",
    "_ws_sender": "the WS frame writer",
    "one": "one peer's status call over its tunnel",
    "work": "the model price refresh over HTTP",
    "run": "web push delivery to subscriptions; the peer relay POST",
    "go": "the models frame notice (model-catalog); the warm threads are wrapped in _stage_marked at their Thread line",
    "_pf": "a native file dialog for the paperclip",
    "_bd": "a native folder dialog for a field",
    "_do_warm_commands": "lists the CLI's slash commands into the commands cache",
    "_first_cycle_sampler_run": "the first-pass stack sampler: reads frames, builds nothing",
    "_ask": "one peer's spend call over its tunnel",
    "_fleet_restart_run": "the remote half of a fleet restart over the tunnels, then this kernel's own",
    "_ensure_postal_bus": "starts the postal bus process",
    "_gl": "a git link subprocess for a file",
    "_pusher": "marks inside: push and connect through _push's decorator",
    "_jobs_loop": "marks inside: jobs.<name> through _job_stage",
}


def _thread_targets(text):
    """Every threading.Thread(target=...) in the kernel: (line, target expression)."""
    out = []
    for m in _re.finditer(r"threading\.Thread\(target=([^,\)]+)", text):
        out.append((text.count("\n", 0, m.start()) + 1, m.group(1).strip()))
    return out


def _marked_at_def(text, name, near_line):
    """True when the `def name(` nearest `near_line` (a closure above the Thread line, or a module-level function anywhere)
    is decorated with _stage_marked or sets a stage in its body."""
    lines = text.split("\n")
    order = list(range(near_line - 1, -1, -1)) + list(range(near_line, len(lines)))
    for i in order:
        if _re.match(r"\s*def %s\(" % _re.escape(name), lines[i]):
            head = "\n".join(lines[max(0, i - 3):i])
            body = "\n".join(lines[i:i + 80])
            return "@_stage_marked(" in head or "_set_stage(" in body
    return False


class StageMarksCensus(unittest.TestCase):
    def test_every_kernel_thread_is_marked_or_a_listed_io_helper(self):
        """T401 (5a): the read boot's builds and hydrations sat under stage `none` because the judge tiers and the request
        handler carried no mark. Every thread the kernel starts is marked (wrapped in _stage_marked at its Thread line,
        decorated at its def, or setting a stage in its body) or is a pure I/O helper listed above with its reason."""
        unmarked = []
        for line, target in _thread_targets(KERNEL_SRC):
            if target.startswith("_stage_marked("):
                continue
            names = _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", target)          # a conditional target names several functions
            names = [n for n in names if _re.search(r"\bdef %s\(" % _re.escape(n), KERNEL_SRC)]   # functions only, not the condition's variables
            for name in names:
                if name in ALLOW or _marked_at_def(KERNEL_SRC, name, line):
                    continue
                unmarked.append((line, name))
        self.assertEqual(unmarked, [], "threads that can reach a build or a hydration without a stage mark")
        self.assertTrue(_thread_targets(KERNEL_SRC), "the census saw the kernel's threads")

    def test_every_request_method_is_marked_with_its_route(self):
        for m in ("do_OPTIONS", "do_HEAD", "do_GET", "do_POST"):
            i = KERNEL_SRC.index("    def %s(self):" % m)
            head = KERNEL_SRC[max(0, i - 200):i]
            self.assertIn('@_stage_marked(lambda self: "http.%s." + _route_seg(self.path))' % m.split("_")[1], head, m)
        self.assertIn('_set_stage("judge." + threading.current_thread().name)', inspect.getsource(km._run_tier), "the tier threads")

    def test_the_route_segment_names_the_stage(self):
        self.assertEqual([km._route_seg(p) for p in ("/chat/x/y", "/ws", "/remote/h/ws", "/", "", "/perf?stacks=1", "/state?x=1")],
                         ["chat", "ws", "remote", "root", "root", "perf", "state"])


class BuildsCountUnderTheThreadsStage(unittest.TestCase):
    """A build from a marked thread lands under its name in asmIndex.materializedByStage; an unmarked thread's reads `none`."""

    def setUp(self):
        self._prev_provider = em._READ_STAGE_FN[0]
        em.set_read_stage_provider(km._current_read_stage)   # several kernel loads share one event model in a pytest process: the
        #                                                       provider must be THIS load's, whose thread-local the marks set

    def tearDown(self):
        em._READ_STAGE_FN[0] = self._prev_provider

    def _index(self):
        recs = [["r%d" % i, None, "u", None, i, 1000 + i, 0, None, None, None] for i in range(3)]
        rows = [json.dumps({"r": i, "s": {"type": "user", "author": "human", "t": 1000 + i}, "seq": i}, separators=(",", ":")) for i in range(3)]
        idx = em.LazyIndex({"atoms": rows, "records": recs, "fsids": []}, SID, "/TESTDIR/x.jsonl")
        return em.LazyAtoms(idx, range(3))

    def _build_on(self, runner):
        la = self._index()
        before = dict(em.asm_index_stats()["materializedByStage"])
        th = threading.Thread(target=runner, args=(lambda: la[0],)); th.start(); th.join(10)
        after = em.asm_index_stats()["materializedByStage"]
        return {k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0)}

    def test_a_tier_threads_build_lands_under_judge_and_its_tier_name(self):
        delta = self._build_on(lambda build: km._run_tier(build))
        # the thread's name is the tier's: the census marks judge.<name>; a plain Thread carries Thread-N, still under judge.
        self.assertEqual(len(delta), 1, delta)
        key = next(iter(delta)); self.assertTrue(key.startswith("judge.Thread-") or key.startswith("judge."), key)
        self.assertEqual(delta[key], 1)

    def test_a_request_handlers_build_lands_under_http_and_its_route(self):
        marked = km._stage_marked("http.POST.state")(lambda build: build())
        delta = self._build_on(marked)
        self.assertEqual(list(delta), ["http.POST.state:<lambda>"], delta)

    def test_an_unmarked_threads_build_reads_none_the_read_boots_face(self):
        delta = self._build_on(lambda build: build())
        self.assertEqual(len(delta), 1, delta); self.assertTrue(next(iter(delta)).startswith("none:"), delta)

    def test_the_index_block_carries_the_per_stage_map(self):
        st = em.asm_index_stats()
        self.assertIn("materializedByStage", st); self.assertIsInstance(st["materializedByStage"], dict)


if __name__ == "__main__":
    unittest.main()
