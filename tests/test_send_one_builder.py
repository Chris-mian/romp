#!/usr/bin/env python3
"""ONE builder of chat frames: the pusher cycle. A per-session event that wants its frame at once NAMES its
session to that cycle; it never builds a whole session of its own beside it (2026-09-23).

The user watched a message they had just sent land in the chat and vanish a moment later, and an earlier
agent reply flash out and back on most sends. Both are one shape: two whole-session builders, each with its
own transcript read, handing a client their lists in either order, so the older list arrives last and is
taken as the kernel's newest word. The second builder was added at the SDK's queue pop (66486701) to land
one small flip — the copy has left romp's queue for the CLI, so the pane drops the ✎ it can no longer honour
(send-pending.ts `handed`) — and firing at the instant the CLI takes the message and writes its record put
it in an exact race with the cycle's own read of the same file.

The flip is a state change, not a transcript. The pop now names its sid to the one cycle (_push_session_soon)
and lets the poke it already sends wake it; the cycle ranks a named sid with the watched tabs, re-reads the
names at the top of every build (a pop commonly lands while a cycle is in flight, since the send woke the
pusher milliseconds before it) and flushes each build as it lands, so the flip waits at most one tab's build
and no second list of that session exists to be ordered. PR 2050's watermark guard stays as the loud backstop
it should always have been, not the fix.

Drives the REAL _push over fake clients with build_session stubbed (the test_chat_skeleton_reconnect.py
harness, as the stale-build guard's module does). SYNTHETIC only: the notes-api demo world, placeholder UUIDs.
"""
import inspect
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_one_builder", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_one_builder", os.path.join(os.path.dirname(HERE), "kernel", "sdk_backend.py"))

S1 = "11111111-2222-3333-4444-555555555551"   # web: the session the send lands in
S2 = "11111111-2222-3333-4444-555555555552"   # api: another open tab
S3 = "11111111-2222-3333-4444-555555555553"   # tests: a third
NAMES = {S1: "web", S2: "api", S3: "tests"}


def _sess(sid, n=3):
    evs = [{"kind": "user" if i % 2 == 0 else "assistant", "uuid": "m%d" % i,
            "md": "step %d of the notes-api search" % i, "ts": "2026-09-23T10:00:%02dZ" % i} for i in range(n)]
    return {"type": "session", "id": sid, "name": NAMES[sid], "events": evs,
            "status": {"state": "working", "sinceEpoch": 1790000000}}


class OneChatFrameBuilder(unittest.TestCase):
    """The kernel half: the ask names a sid and wakes the one cycle, builds nothing itself, and the cycle
    builds a named sid first."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid in (S1, S2, S3):
            p = os.path.join(self.tmp, sid + ".jsonl")
            Path(p).write_text("x" * 1000)
            self.paths[sid] = p
        self.SESS = {sid: _sess(sid) for sid in (S1, S2, S3)}
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
                       km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients))
        km._chat_tab_sessions = lambda now, live_map: [
            {"sid": sid, "name": NAMES[sid], "path": self.paths[sid], "anchor": sid} for sid in (S1, S2, S3)]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None
        self.built = []
        self.on_build = None                           # a hook run inside a tab's build: the pop landing mid-cycle

        def build(sid, now, live_map=None, **kw):
            self.built.append(sid)
            if self.on_build:
                self.on_build(sid)
            return json.loads(json.dumps(self.SESS[sid]))
        km.build_session = build
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"; km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"; km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        km._chat_baseline_raced.clear(); km._push_first.clear()
        del km._clients[:]
        km._pusher_wake.clear()

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
         km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, clients) = self._saved
        del km._clients[:]
        km._clients.extend(clients)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        km._chat_baseline_raced.clear(); km._push_first.clear()
        km._pusher_wake.clear()

    def _client(self, **kw):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)),
             "_frames": frames, "cid": "cid-%d" % len(km._clients), "kind": "page", "wid": "W1"}
        c.update(kw)
        return c

    def test_01_the_ask_names_the_sid_and_wakes_the_cycle_and_builds_nothing(self):
        a = self._client(active=S2, proto=2)
        km._clients.append(a)
        km._push([a])                                  # the cycle's first pass: every tab built once
        self.built[:] = []
        km._pusher_wake.clear()
        km._push_session_soon(S1)
        self.assertEqual(self.built, [], "the ask builds no chat frame of its own: the cycle is the one builder")
        self.assertEqual(len(km._push_first), 1, "…it names the sid for the next cycle: %r" % (km._push_first,))
        self.assertIn(S1, km._push_first)
        self.assertTrue(km._pusher_wake.is_set(), "…and wakes that cycle, so the flip does not wait out the backstop")

    def test_02_the_named_sid_is_built_first_by_the_cycle(self):
        # S2 is the watched tab and ranks first either way; S3, the named one, ranks WITH it, ahead of S1, so the
        # build order is [S2, S3, S1]. Without the ranking clause the stable sort keeps the chat list's order for
        # the two unranked tabs, [S2, S1, S3], so the assertion pins the rank itself and not the list's order
        # (naming S1, first in the list, was satisfied by the stable sort alone).
        a = self._client(active=S2, proto=2)
        km._clients.append(a)
        km._push([a])
        self.built[:] = []
        km._built_chat.clear()                         # every tab rebuilds, so the order below is the cycle's own
        km._push_session_soon(S3)
        km._push([a])
        self.assertLess(self.built.index(S3), self.built.index(S1),
                        "the named session is built (and flushed) before the tabs nobody is waiting on: %r" % (self.built,))

    def test_03_the_cycle_drains_the_names_it_served(self):
        a = self._client(active=S2, proto=2)
        km._clients.append(a)
        km._push_session_soon(S1)
        km._push([a])
        self.assertEqual(km._push_first, set(), "a cycle that ran takes the names with it: %r" % (km._push_first,))

    def test_04_a_connect_push_reads_the_names_but_never_eats_them(self):
        # a connect push serves ONE client; the ordering the next cycle owes everyone must survive it
        a = self._client(active=S2, proto=2)
        km._clients.append(a)
        km._push_session_soon(S1)
        km._push([a], connect=True)
        self.assertIn(S1, km._push_first, "the connect push left the name for the cycle: %r" % (km._push_first,))

    def test_05_the_drain_is_one_step(self):
        km._push_first.update({S1, S2})
        self.assertEqual(km._push_first_drain(), {S1, S2})
        self.assertEqual(km._push_first, set(), "drained in one step: a second cycle re-orders nothing")
        self.assertEqual(km._push_first_drain(), set())

    def test_06_a_name_landing_mid_loop_is_built_next_in_the_same_cycle(self):
        # SdkBackend.send() wakes the pusher milliseconds before the queue pop, so the pop's name commonly lands while
        # a cycle is in flight. Read once per cycle, it waited out the rest of that cycle (every other tab's build, the
        # feed and timeline sections) and the next cycle's prelude; the loop re-reads the names at the top of every
        # build and moves the named tab to the front of what is left, so it waits one tab's build at most.
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        self.on_build = lambda sid: km._push_session_soon(S3) if sid == S1 else None   # named during the first tab's build
        km._push([a])
        self.assertEqual(self.built, [S1, S3, S2],
                         "the session named during the first build is built next, ahead of the unranked tab: %r" % (self.built,))
        self.assertEqual(km._push_first, set(), "…and the in-flight cycle took the name with it: %r" % (km._push_first,))

    def test_07_a_name_landing_during_the_last_build_is_served_again_before_the_feed_section(self):
        # The watched tab is built first, so a pop for it landing while the LAST tab builds names a session this cycle
        # has already served, with a frame that predates the pop. The list ran dry; the loop drains once more and serves
        # it a second time in the same cycle, before the feed and timeline sections begin, not in the next cycle.
        a = self._client(active=S1, proto=2)
        km._clients.append(a)

        def late(sid):
            if sid == S3:
                km._push_session_soon(S1)
                km._built_chat.pop(S1, None)           # the pop moved S1's signature (its queued tuple): the cached build no longer matches
        self.on_build = late
        km._push([a])
        self.assertEqual(self.built, [S1, S2, S3, S1],
                         "the named session's second pass, in the same cycle: %r" % (self.built,))
        self.assertEqual(km._push_first, set(), "…and the name went with it: %r" % (km._push_first,))

    def test_08_a_sid_is_re_queued_once_per_cycle_and_a_further_name_is_the_next_cycles(self):
        # the cycle must end: a name for a sid this cycle has already served twice goes back into the set
        a = self._client(active=S1, proto=2)
        km._clients.append(a)

        def late(sid):
            if sid in (S2, S3):
                km._push_session_soon(S1)
                km._built_chat.pop(S1, None)
        self.on_build = late
        km._push([a])
        self.assertEqual(self.built, [S1, S2, S1, S3],
                         "S2's name earns S1 a second pass; S3's does not earn a third: %r" % (self.built,))
        self.assertEqual(km._push_first, {S1}, "the further name is left for the next cycle: %r" % (km._push_first,))

    def test_09_a_connect_push_leaves_a_mid_loop_name_for_the_cycle(self):
        # the connect push serves one client in the standing order and drains nothing, mid-loop included
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        self.on_build = lambda sid: km._push_session_soon(S3) if sid == S1 else None
        km._push([a], connect=True)
        self.assertEqual(self.built, [S1, S2, S3], "the standing order, the named tab not moved: %r" % (self.built,))
        self.assertIn(S3, km._push_first, "…and the name is left for the cycle: %r" % (km._push_first,))


class HandOffNamesTheCycle(unittest.TestCase):
    """The backend half: the queue pop asks the cycle, and the ask cannot stall the session's event loop."""

    SID = "11111111-2222-3333-4444-555555555555"

    def test_the_pop_names_the_cycle_and_builds_no_frame_of_its_own(self):
        # The pop in inputs() is the moment a queued copy leaves _pending for the CLI's stdin, where no recall
        # exists: the pane must learn NOW so the bubble drops its ✎ (the user 2026-09-19). 66486701 landed that
        # with the targeted whole-session push — a second builder racing the cycle's read of the very file the
        # CLI is writing (the user 2026-09-22: the row landed, then vanished). Source-pinned like the other
        # inputs() rules (a nested closure); the callback's mechanics are the tests below.
        src = inspect.getsource(sb.SdkSession)
        i = src.index("self._inflight_texts.append(item)")
        k = src.index('yield {"type": "user",', i)
        seg = src[i:k]
        self.assertIn("self.backend._push_soon(self.sid)", seg,
                      "the pop names its sid to the one pusher cycle, between the pop and the yield")
        self.assertNotIn("self.backend._push_session(self.sid)", seg,
                         "…and builds no whole-session frame of its own here: one builder of chat frames")
        self.assertIn("self.backend._poke()", seg[:seg.index("self.backend._push_soon(self.sid)")],
                      "…after the poke, which already wakes that cycle")

    def test_the_ask_reaches_the_kernel_callback_on_the_callers_own_thread(self):
        # a set add and an Event set: nothing to thread, and nothing that can stall the session's asyncio loop
        got, where = [], []
        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None,
                           push_soon=lambda sid: (got.append(sid), where.append(threading.current_thread().name)))
        be._push_soon(self.SID)
        self.assertEqual(got, [self.SID])
        self.assertEqual(where, [threading.current_thread().name], "no thread of its own: the ask is non-blocking")

    def test_without_the_callback_it_falls_back_to_the_pusher_wake(self):
        woke = []
        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None, push=lambda: woke.append(True))
        be._push_soon(self.SID)
        self.assertEqual(woke, [True], "an older kernel still gets its frame from the plain wake, never a silent no-op")

    def test_a_failing_ask_is_contained_logged_and_still_wakes(self):
        logs, woke = [], []

        def boom(sid):
            raise RuntimeError("nope")

        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None,
                           push_soon=boom, push=lambda: woke.append(True), log=logs.append)
        be._push_soon(self.SID)   # must not raise into the feeder
        self.assertTrue(any("push-soon" in str(m) for m in logs), "the failure is reported, not swallowed: %r" % logs)
        self.assertEqual(woke, [True], "…and the frame still goes out on the plain wake")

    def test_the_kernel_wires_the_ask(self):
        src = inspect.getsource(km)
        self.assertIn("push_soon=_push_session_soon", src, "the SDK backend is constructed with the ask wired")


if __name__ == "__main__":
    unittest.main()
