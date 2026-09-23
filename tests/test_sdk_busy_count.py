#!/usr/bin/env python3
"""busy_count — the quiet-window gate for deferred deploy refreshes (the user 2026-07-20). Peers'
`romp --refresh` deploys bounced the kernel 11x in one day, each cutting in-flight SDK turns; the
manager now defers a deploy until the kernel's /busy reports zero. busy_count must mirror exactly what
a restart would DISRUPT: sessions with inflight > 0, plus (T240) sessions with live background work —
a Workflow run or a background agent, which has no turn in flight between its own turns — and never
ended sessions or queued turns (the persisted queue survives a bounce losslessly), nor (2026-09-22) a
session under a per-session host, which the restart detaches with its turn and its work still running.
Synthetic; no SDK import."""
import os
import tempfile
import unittest
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
sb = load_source("romp_sdk_backend_busy", os.path.join(BIN, "romp_sdk_backend.py"))


def _sess(inflight, ended=False, bg=False, hosted=False, name="web"):
    s = mock.Mock()
    s.name = name
    s.inflight = inflight
    s.ended = ended
    s._bg_tasks = {"w1": {"type": "local_workflow"}} if bg else {}   # a Mock attribute would read truthy
    s._subagents = {}
    # a kernel child unless `hosted` (2026-09-22): the count skips a session under a host (T315), and a Mock's
    # auto-attribute would read as a live host, so both host fields are set either way
    s._host = object() if hosted else None
    s._host_intent = False
    return s


def _backend(logs=None):
    # a state root of its own, so hosts are pinned off in it (this module runs none)
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "session-hosts"), "w") as f:
        f.write("off")
    return sb.SdkBackend(d, "/bin/true", lambda *a, **k: None, log=(logs.append if logs is not None else None))


class BusyCount(unittest.TestCase):
    def _backend(self):
        return _backend()

    def test_counts_inflight_and_background_unended_sessions(self):
        be = self._backend()
        be.sessions = {"a": _sess(1), "b": _sess(0), "c": _sess(2), "d": _sess(1, ended=True)}
        self.assertEqual(be.busy_count(), 2,
                         "idle and ended sessions are not turns a restart would cut")
        be.sessions["e"] = _sess(0, bg=True)            # a Workflow between its own turns (T240)
        self.assertEqual(be.busy_count(), 3, "background work is disrupted by a restart too")
        self.assertEqual(be.busy_breakdown(), (2, 1), "counted once each, in flight first")
        be.sessions["f"] = _sess(0, ended=True, bg=True)
        self.assertEqual(be.busy_count(), 3, "an ended session's leftovers are nobody's work")

    def test_empty_backend_is_quiet(self):
        self.assertEqual(self._backend().busy_count(), 0)

    def test_kernel_serves_busy_route(self):
        # Source pin: the kernel must expose busy_count as GET /busy (auth-exempt, like /healthz) —
        # the manager polls it tokenless while a deploy refresh is pending.
        ksrc = open(os.path.join(BIN, "romp-kernel"), encoding="utf-8").read()
        get_src = ksrc.split("def do_GET", 1)[1]     # the GET router only (do_HEAD authorizes too)
        self.assertIn('if p == "/busy":', get_src)
        self.assertIn("busy_count", get_src)
        # served BEFORE the auth gate, beside the other exempt routes
        self.assertLess(get_src.index('if p == "/busy":'),
                        get_src.index("ok, self._set_cookie, why = self._authorize(q)"))


class HostedWorkIsNotRestartWork(unittest.TestCase):
    """2026-09-22 (a post-merge review of a kernel refresh from an older main): a session under a per-session
    host (T315; on by default since T348) is DETACHED by a restart, never cut (cut_list), so neither its turn
    nor its background work is anything the quiet window or `romp down` waits on. Counting it held a quiet
    refresh, and the drain hold over every idle session's queued turn, while the drain itself recorded no cut.
    A kernel child's turn and background work still count (T240)."""

    def test_a_box_with_only_hosted_work_is_quiet(self):
        be = _backend()
        mid_attach = _sess(1, name="tests")
        mid_attach._host_intent = True                       # no host yet, but the drain detaches it by intent
        be.sessions = {"a": _sess(1, hosted=True, name="web"), "b": _sess(0, bg=True, hosted=True, name="api"),
                       "c": mid_attach}
        self.assertEqual(be.would_cut(), [], "sanity: the drain would detach all three, and cut nothing")
        self.assertEqual(be.busy_breakdown(), (0, 0), "a hosted turn and hosted background work survive the restart")
        self.assertEqual(be.busy_count(), 0)
        self.assertEqual(be.inflight_names(), [], "nothing here is about to be cut")

    def test_a_kernel_child_beside_hosted_work_still_counts_alone(self):
        be = _backend()
        be.sessions = {"a": _sess(1, hosted=True, name="web"), "b": _sess(1, name="api"),
                       "c": _sess(0, bg=True, name="tests"), "d": _sess(0, bg=True, hosted=True, name="web2")}
        self.assertEqual(be.busy_breakdown(), (1, 1), "the kernel children's turn and workflow, nothing hosted")
        self.assertEqual(be.busy_count(), 2)
        self.assertEqual(be.inflight_names(), ["api"],
                         "/down names only the turn the stop cuts, never the hosted one beside it")
        self.assertEqual(be.inflight_names(), [c["name"] for c in be.would_cut()],
                         "the drain's own cut list, for sessions not already ending (T143: an ending session's live turn is the drain's alone)")

    def test_the_going_down_line_counts_only_the_turns_the_stop_cuts(self):
        logs = []
        be = _backend(logs)
        mid = _sess(1, name="tests"); mid._host_intent = True    # mid-attach by intent: the stop detaches it too (2026-09-22)
        be.sessions = {"a": _sess(1, hosted=True, name="web"), "b": _sess(1, name="api"), "c": mid}
        be.quiesce(5)
        try:
            line = [str(l) for l in logs if "going down" in str(l)]
            self.assertEqual(len(line), 1, logs)
            self.assertIn("going down: 1 in-flight turn(s);", line[0], "the kernel child's turn, not the hosted or mid-attach one")
        finally:
            be._drain_wake_timer.cancel()


if __name__ == "__main__":
    unittest.main()
