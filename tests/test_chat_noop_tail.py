#!/usr/bin/env python3
"""A chat frame the page already holds is never sent (2026-09-23).

An observer page on a session idle in awaitingBg took a proto-2 chatTail every few seconds while the transcript read
never moved. The frames were two shapes in alternation: a delta anchored just before a running background agent's card,
carrying that card and every event after it, and right behind it an EMPTY tail anchored at the list's last event. Read on
the wire with the full events, the deltas were not repeats: each carried the agent card's progress (a tool call counted,
or only the stamp of the subagent's newest record, a field no page reads). The empty tails were: each carried the same
status, flags and watermark as the delta the page had just applied, and no events, so applying it changed nothing, and
the page rebuilt its window for it all the same. The per-slot dedup cannot see that, because it compares a frame with the
LAST frame (the delta), not with what the page holds after it. PR 2071's anchor rule was not involved: no event of that
list was a streamed one, so every delta began at the change itself.

This module pins the send side: the kernel records, per client and session, what the client holds once a frame lands (the
key its tail ends on, the status, the three view flags, the watermark), and an empty-suffix tail that would leave exactly
that is not sent, on either wire. The agent card half (the subagent's newest-record stamp off the wire) is pinned in
tests/test_subagent_transcripts.py.

SYNTHETIC only: the notes-api demo world, placeholder UUIDs, TESTHOST.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_noop_tail", os.path.join(BIN, "romp-kernel"))

# private synthetic sids (the goal-store fixture rule: never the shared placeholder)
S1 = "7e5a2222-3333-4444-8555-666666660001"   # web: the tab the page watches
NAMES = {S1: "web"}
LEAF1 = "/tmp/TESTHOST/projects/notes-api/%s.jsonl" % S1
AGENT_AT = 10                                   # the running background agent's card sits here, twenty events from the end


def _agent_card(calls):
    return {"kind": "tool", "name": "Agent", "uuid": "m%d" % AGENT_AT, "toolUseId": "toolu_bg_0001", "agentId": "a1111111111111111",
            "agentAsync": True, "agentRunning": True, "output": "", "desc": "check the api tests",
            "agentSteps": [{"tool": "Read", "desc": "tests/test_api.py %d" % i, "ts": "2026-09-23T10:00:%02d.000Z" % i} for i in range(calls)],
            "stepsTotal": calls, "agentGist": {"calls": calls, "since": "2026-09-23T10:00:00.000Z"}}


def _events(n=30, calls=3):
    evs = []
    for i in range(n):
        if i == AGENT_AT:
            evs.append(_agent_card(calls))
        else:
            evs.append({"kind": "user" if i % 2 == 0 else "assistant", "uuid": "m%d" % i, "md": "step %d of the notes-api search" % i})
    return evs


def _status(label="check the api tests"):
    return {"state": "awaitingBg", "sinceEpoch": 1790000000000, "awaitingKind": "tasks", "awaitingCount": 1,
            "awaitingTasks": [label], "awaitingItems": [{"label": label}]}


def _sess(evs, status=None, notify=None, tx=2000, live=7):
    return {"type": "session", "id": S1, "name": NAMES[S1], "events": evs, "status": status or _status(),
            "notify": notify, "hideFromFeed": None, "postalServiceOff": None,
            "wm": {"leaf": LEAF1, "tx": [[1790000000.0 + tx / 1e6, tx], [1790000000.0, 40]], "live": live}}


def _page_apply(page, f):
    """What a page's list becomes once a frame lands: a full replaces it (the lists here are shorter than the wire tail), a
    proto-2 chatTail truncates after its anchor and appends, a proto-1 chatTail truncates at `from` and appends."""
    if f["type"] == "session":
        return [dict(e) for e in f["events"]]
    if "afterUuid" in f:
        keys = [km._event_key(e) for e in page]
        assert f["afterUuid"] in keys, "a tail anchored past what the page holds: %r" % f["afterUuid"]
        return page[:keys.index(f["afterUuid"]) + 1] + [dict(e) for e in f["events"]]
    return page[:f["from"]] + [dict(e) for e in f["events"]]


class _Harness(unittest.TestCase):
    """The real _push over fake clients, build_session stubbed to the world below (the test_chat_resync_kernel.py harness).
    Every push builds afresh (the cycle's cache dropped first), as the live cycle did: the running agent's file moved the
    chat's build signature on every record it wrote."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = os.path.join(self.tmp, S1 + ".jsonl")
        Path(p).write_text("x" * 1000)
        self.path = p
        self.world = _sess(_events())
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame,
                       km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients), km._DEDUP_REPOST_S)
        km._chat_tab_sessions = lambda now, live_map: [{"sid": S1, "name": NAMES[S1], "path": self.path, "anchor": S1}]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None
        km.build_session = lambda sid, now, live_map=None, **kw: json.loads(json.dumps(self.world))
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"; km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"; km.jd.STATE.mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "session-hosts").write_text("off\n")   # a minted state root pins per-session hosts off (CLAUDE.md, 2026-09-11)
        km._DEDUP_REPOST_S = 0.0   # the slot dedup's repost window closed: whatever a cycle decides to send, goes, so a
        #                            test counts the kernel's decisions and not the 60-second window's
        self._reset()
        del km._clients[:]

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session, km._comments_frame,
         km._push_subagents, km.NAMES, km.jd.STATE, clients, km._DEDUP_REPOST_S) = self._saved
        del km._clients[:]
        km._clients.extend(clients)
        self._reset()

    @staticmethod
    def _reset():
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear(); km._chat_baseline_raced.clear()
        km._CHAT_STALE_SAID.clear(); km._push_first.clear()
        km._pusher_wake.clear()

    def _client(self, proto=2):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)), "_frames": frames,
             "cid": "cid-%d" % len(km._clients), "kind": "page", "wid": "W1", "active": S1, "proto": proto}
        km._clients.append(c)
        return c

    @staticmethod
    def _chat(c):
        return [f for f in c["_frames"] if f.get("type") in ("session", "chatTail") and f.get("id") == S1]

    def _push(self, c, n=1):
        for _ in range(n):
            km._built_chat.clear()
            km._push([c])

    def _page(self, c):
        page = []
        for f in self._chat(c):
            page = _page_apply(page, f)
        return page


class UnchangedWorldSendsNothing(_Harness):
    def test_a_session_waiting_on_background_work_with_nothing_moving_is_sent_one_frame_in_twelve_cycles(self):
        """The page connects, and then twelve cycles build the same world: one frame, the full. Before the fix the first
        cycle after the full sent an empty tail at the list's last event (the change against the baseline read `none`,
        and the slot held the full's bytes, not the tail's), and with the repost window passed every cycle sent it again."""
        a = self._client()
        self._push(a, 12)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session"], "one full, then nothing: %r" % [(f["type"], f.get("afterUuid"), len(f.get("events") or [])) for f in frames])
        self.assertEqual(self._page(a), self.world["events"])

    def test_the_agent_card_moving_is_one_frame_carrying_the_card_on_and_then_nothing(self):
        """The observed shape: the running agent's card counts a tool call while the transcript read stands still. Exactly one
        frame goes: a tail anchored at the event before the card, carrying the card and the events after it (the wire
        truncates after its anchor, so nothing short of that can carry a change twenty events from the end). The cycles
        after it send nothing; before the fix the next one sent the empty tail the page already held."""
        a = self._client()
        self._push(a)
        self.world = _sess(_events(calls=4))
        self._push(a)
        self._push(a, 10)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"], "%r" % [(f["type"], f.get("afterUuid"), len(f.get("events") or [])) for f in frames])
        tail = frames[1]
        self.assertEqual(km._last_anchor(self.world["events"]), "m29",
                         "nothing streamed: PR 2071's anchor rule ends the base on the list's last event, so it moved nothing here")
        self.assertEqual(tail["afterUuid"], "m%d" % (AGENT_AT - 1), "anchored at the event before the card: the change itself")
        self.assertEqual(tail["events"][0]["agentGist"]["calls"], 4)
        self.assertEqual(len(tail["events"]), 30 - AGENT_AT)
        self.assertEqual(self._page(a), self.world["events"], "the page holds the kernel's list")

    def test_every_repeat_of_the_observed_cycle_is_one_frame_per_change(self):
        """Five progress steps of the agent, each followed by quiet cycles: five tails, one per step, and no empty ones."""
        a = self._client()
        self._push(a)
        for calls in range(4, 9):
            self.world = _sess(_events(calls=calls))
            self._push(a, 3)
        frames = self._chat(a)
        self.assertEqual([(f["type"], len(f.get("events") or [])) for f in frames],
                         [("session", 30)] + [("chatTail", 30 - AGENT_AT)] * 5)

    def test_a_status_change_alone_is_one_empty_tail_carrying_it(self):
        a = self._client()
        self._push(a)
        self.world = _sess(_events(), status=_status("run the api tests"))
        self._push(a, 4)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"])
        self.assertEqual(frames[1]["events"], [])
        self.assertEqual(frames[1]["afterUuid"], "m29")
        self.assertEqual(frames[1]["status"]["awaitingTasks"], ["run the api tests"], "the new status rides it")

    def test_a_flag_change_alone_is_one_empty_tail_carrying_it(self):
        a = self._client()
        self._push(a)
        self.world = _sess(_events(), notify=True)
        self._push(a, 4)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"])
        self.assertIs(frames[1]["notify"], True)

    def test_a_newer_watermark_alone_is_one_empty_tail_carrying_it(self):
        """The page's stale-build rule reads the watermark it holds: a newer reading of an unchanged list still reaches it."""
        a = self._client()
        self._push(a)
        self.world = _sess(_events(), tx=2100, live=8)
        self._push(a, 4)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"])
        self.assertEqual(frames[1]["wm"]["tx"][0][1], 2100)

    def test_a_card_that_left_the_end_of_the_list_is_still_truncated(self):
        """An empty tail truncates too: a trailing overlay card that went away (a queued bubble landing) leaves the page by
        that tail, anchored at the list's new last event, so it is not a frame the page already holds."""
        a = self._client()
        self.world = _sess(_events() + [{"kind": "queued", "uuid": "queued", "md": "and the readme too"}])
        self._push(a)
        self.world = _sess(_events())
        self._push(a, 4)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"])
        self.assertEqual((frames[1]["afterUuid"], frames[1]["events"]), ("m29", []))
        self.assertEqual(self._page(a), self.world["events"], "the card left the page")


class NewPagesAndAsksStillGetTheFull(_Harness):
    def test_a_ready_reset_gets_the_full_over_an_unchanged_world(self):
        a = self._client()
        self._push(a, 3)
        km._client_reset_chat_base(a)                      # a renderer that just evaluated holds nothing
        self._push(a, 3)
        self.assertEqual([f["type"] for f in self._chat(a)], ["session", "session"])

    def test_a_needfull_gets_the_full_over_an_unchanged_world(self):
        a = self._client()
        self._push(a, 3)
        km._client_reset_chat_sid(a, S1)                   # the page asked for the session whole
        self._push(a, 3)
        self.assertEqual([f["type"] for f in self._chat(a)], ["session", "session"])

    def test_a_second_page_gets_its_own_full_while_the_first_gets_nothing(self):
        a = self._client()
        self._push(a, 2)
        b = self._client()
        self._push(b, 2)
        km._built_chat.clear()
        km._push([a, b])
        self.assertEqual([f["type"] for f in self._chat(a)], ["session"])
        self.assertEqual([f["type"] for f in self._chat(b)], ["session"])


class StreamedRunKeepsPr2071sGuarantee(_Harness):
    """PR 2071 ends a client's base on the last RECORDED event, so a delta re-sends whatever the page holds past it. The
    held-view rule touches only the EMPTY tail, so that guarantee stands: the page never misses an event, even when the
    streamed atoms leave the list for records under other keys (a retried try)."""

    def _streamed(self, keys):
        return [{"kind": "assistant", "uuid": k, "md": "streaming %s" % k, "streamed": True} for k in keys]

    def test_the_page_tracks_the_list_through_a_retried_stream_and_quiet_cycles_send_nothing(self):
        a = self._client()
        base = _events(n=12)
        self.world = _sess(base + self._streamed(["s12", "s13"]))
        self._push(a, 3)
        self.assertEqual(self._page(a), self.world["events"])
        self.world = _sess(base + self._streamed(["s12", "s13", "s14"]), live=8)
        self._push(a, 3)
        frames = self._chat(a)
        self.assertEqual(frames[-1]["afterUuid"], "m11", "the delta re-sends the streamed run from the last record (PR 2071)")
        self.assertEqual(self._page(a), self.world["events"])
        # the try is retried: its atoms never land, and the retry's records carry other keys
        self.world = _sess(base + [{"kind": "assistant", "uuid": "r12", "md": "the retry's answer"}], tx=2300, live=9)
        self._push(a, 3)
        self.assertEqual(self._page(a), self.world["events"], "no streamed atom stranded, no record missing")
        self.assertEqual([f["type"] for f in self._chat(a)], ["session", "chatTail", "chatTail"],
                         "one frame per change, none for the quiet cycles between them")


class IndexWire(_Harness):
    def test_a_proto1_page_is_sent_nothing_for_an_unchanged_world_and_one_tail_per_change(self):
        a = self._client(proto=1)
        self._push(a, 6)
        self.assertEqual([f["type"] for f in self._chat(a)], ["session"])
        self.world = _sess(_events(calls=4))
        self._push(a, 6)
        frames = self._chat(a)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"])
        self.assertEqual(frames[1]["from"], AGENT_AT)
        self.assertEqual(self._page(a), self.world["events"])


if __name__ == "__main__":
    unittest.main()
