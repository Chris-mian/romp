#!/usr/bin/env python3
"""The chat frame's watermark (2026-09-22): a build that read an OLDER world than the one a client already holds is never
sent to it, as a full or as a delta.

The user watched a message they had just sent land in the chat, vanish two seconds later, and come back only on a
reload. The remote kernel's own rows (a `lastGone:record` full filed at the send's second) and the transcript's record
chain fixed the sequence: the CLI took the message at once and wrote its record; a build that had parsed that record
landed the row on the page; a later build, from a parse that had NOT read the record but a live tail that still held the
echo and the streamed reply, reached the same client after it, and the page took the older list as the kernel's newest
word. Two builders read the transcript in either order (the pusher cycle and the targeted push the SDK backend runs at
its queue pop, 66486701) and hand their lists to a client in either order; nothing ordered the sends. Now every chat
frame carries what its build READ (kernel.py _chat_wm: the transcript's parse key, the live tail's revision), the senders
record it beside the client's echat entry and refuse an older build to a base holder (_chat_wm_older), saying so once on
stderr and filing a `chatStale` client-diag row per refusal.

Drives the REAL _push / _push_session_now over fake clients with build_session stubbed to synthetic payloads (the
test_chat_skeleton_reconnect.py harness), plus one real build_session over a temp transcript for the stamp itself.
SYNTHETIC only: the notes-api demo world, placeholder UUIDs, TESTHOST.
"""
import json
import os
import re
import tempfile
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
km = load_source("romp_kernel_stale_guard", os.path.join(BIN, "romp-kernel"))
jd = km.jd

S1 = "11111111-2222-3333-4444-555555555551"   # web: the tab the page holds whole
S2 = "11111111-2222-3333-4444-555555555552"   # api: the other tab
NAMES = {S1: "web", S2: "api"}
LEAF1 = "/tmp/TESTHOST/projects/notes-api/%s.jsonl" % S1


def _ev(i, kind="user"):
    return {"kind": kind, "uuid": "m%d" % i, "md": "step %d of the notes-api search" % i, "ts": "2026-09-22T10:00:%02dZ" % i}


def _sess(sid, n, tx_size, live, leaf=None):
    """A synthetic chat frame with `n` events and a watermark that read `tx_size` transcript bytes at live revision `live`."""
    evs = [_ev(i, "user" if i % 2 == 0 else "assistant") for i in range(n)]
    return {"type": "session", "id": sid, "name": NAMES.get(sid, sid[:8]), "events": evs, "status": {"state": "working", "sinceEpoch": 1790000000},
            "wm": {"leaf": leaf or LEAF1, "tx": [[1790000000.0 + tx_size / 1e6, tx_size], [1790000000.0, 40]], "live": live}}


class StaleBuildGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid in (S1, S2):
            p = os.path.join(self.tmp, sid + ".jsonl")
            Path(p).write_text("x" * 1000)
            self.paths[sid] = p
        self.SESS = {S1: _sess(S1, 5, 2000, 7), S2: _sess(S2, 3, 900, 2)}
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
                       km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients))
        km._chat_tab_sessions = lambda now, live_map: [{"sid": sid, "name": NAMES[sid], "path": self.paths[sid], "anchor": sid} for sid in (S1, S2)]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None
        self.built = []

        def build(sid, now, live_map=None, **kw):
            self.built.append(sid)
            return json.loads(json.dumps(self.SESS[sid]))
        km.build_session = build
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"; km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"; km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear(); km._chat_baseline_raced.clear()
        km._CHAT_STALE_SAID.clear()
        del km._clients[:]
        km._pusher_wake.clear()

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
         km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, clients) = self._saved
        del km._clients[:]
        km._clients.extend(clients)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear(); km._chat_baseline_raced.clear()
        km._CHAT_STALE_SAID.clear()

    # ── helpers ──
    def _client(self, **kw):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)), "_frames": frames,
             "cid": "cid-%d" % len(km._clients), "kind": "page", "wid": "W1"}
        c.update(kw)
        return c

    @staticmethod
    def _chat_frames(c, sid):
        return [f for f in c["_frames"] if f.get("type") in ("session", "chatTail") and f.get("id") == sid]

    def _rows(self, what):
        fp = km.jd.STATE / "client-diag.jsonl"
        if not fp.exists():
            return []
        return [r for r in (json.loads(ln) for ln in fp.read_text().splitlines() if ln.strip()) if r.get("what") == what]

    def _older(self, sid=S1, n=4, tx=1500, live=9):
        """The build the OLDER reader produced: fewer transcript bytes read (the landed record not among them), a newer live
        tail (the echo still in it, the streamed reply after): the user's shape."""
        self.SESS[sid] = _sess(sid, n, tx, live)
        km._built_chat.clear()   # a fresh build, never the cache's copy of the newer one

    # ── the rule, pure ──
    def test_00_the_rule(self):
        new, last = _sess(S1, 4, 1500, 9)["wm"], _sess(S1, 5, 2000, 7)["wm"]
        self.assertTrue(km._chat_wm_older(new, last), "fewer transcript bytes read: older, whatever the live tail did")
        self.assertFalse(km._chat_wm_older(last, new), "the newer parse is never older")
        self.assertTrue(km._chat_wm_older(_sess(S1, 5, 2000, 6)["wm"], last), "the same parse, an older live tail: older")
        self.assertFalse(km._chat_wm_older(_sess(S1, 5, 2000, 7)["wm"], last), "equal: not older")
        self.assertFalse(km._chat_wm_older(_sess(S1, 4, 1500, 9, leaf=LEAF1 + ".fork")["wm"], last), "another leaf never compares")
        self.assertFalse(km._chat_wm_older({"leaf": LEAF1, "tx": [[1.0, 1500]], "live": 9}, last), "a key of another shape never compares")
        self.assertFalse(km._chat_wm_older({"leaf": LEAF1, "tx": [[1.0, 1500], [3.0, 90]], "live": 9},
                                           {"leaf": LEAF1, "tx": [[2.0, 2000], [1.0, 40]], "live": 9}), "a mixed reading carries something new")
        self.assertFalse(km._chat_wm_older({"leaf": LEAF1, "tx": None, "live": 9}, last), "a missing key never compares")
        self.assertTrue(km._chat_wm_older({"leaf": LEAF1, "tx": None, "live": 3}, {"leaf": LEAF1, "tx": None, "live": 9}), "no key on either side: the revision decides")
        self.assertFalse(km._chat_wm_older({"leaf": LEAF1, "tx": None, "live": "abc"}, {"leaf": LEAF1, "tx": None, "live": "abd"}), "a backend without a counter is unordered")
        self.assertFalse(km._chat_wm_older(None, last)); self.assertFalse(km._chat_wm_older(new, None))

    def test_00b_a_backend_without_a_counter_carries_no_live_component(self):
        """Sessions.live_rev answers a backend with no live_rev method (the Codex backend) with its serialized live atoms, the typed
        text among them; the frame's watermark rides every frame and delta and is written verbatim to client-diag and stderr on a
        refusal, so it carries `live` only as an int (2026-09-23): a string, a bool or nothing yields None, and such frames order on
        the tx rows alone."""
        parsed = {"_txKey": [[1790000000.0, 2000], [1790000000.0, 40]]}
        atoms = json.dumps([{"type": "user", "author": "human", "text": "typed words that must never ride the wire", "t": 1790000000}])
        self.assertIsNone(km._chat_wm(LEAF1, parsed, atoms)["live"], "a serialized tail is never carried")
        self.assertIsNone(km._chat_wm(LEAF1, parsed, True)["live"], "a bool is not a revision")
        self.assertIsNone(km._chat_wm(LEAF1, parsed, None)["live"])
        self.assertEqual(km._chat_wm(LEAF1, parsed, 57)["live"], 57, "the SDK backend's counter rides as is")
        self.assertEqual(km._chat_wm(LEAF1, parsed, 0)["live"], 0)
        self.assertNotIn("never ride the wire", json.dumps(km._chat_wm(LEAF1, parsed, atoms)), "no event text on the frame's watermark")
        # such frames order on the parse rows alone: equal rows never compare, a row behind is older
        a, b = km._chat_wm(LEAF1, parsed, atoms), km._chat_wm(LEAF1, parsed, atoms)
        self.assertFalse(km._chat_wm_older(a, b)); self.assertFalse(km._chat_wm_older(b, a))
        self.assertTrue(km._chat_wm_older(km._chat_wm(LEAF1, {"_txKey": [[1790000000.0, 1500], [1790000000.0, 40]]}, atoms), b))

    # ── the senders ──
    def test_01_an_older_build_after_a_newer_one_is_not_sent_to_a_proto2_base_holder_and_is_filed(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push([a])
        held = self._chat_frames(a, S1)
        self.assertEqual([f["type"] for f in held], ["session"], "a holds the newer build whole")
        self.assertEqual(held[0]["wm"], self.SESS[S1]["wm"], "the frame carries what its build read")
        self.assertEqual(a["echatWm"][S1], self.SESS[S1]["wm"], "…and the client's slot records it")
        self._older()
        km._push_session_now(S1)                       # the targeted push, its build from the older reading
        self.assertEqual(len(self._chat_frames(a, S1)), 1, "the older build reached the client neither as a full nor as a delta: %r"
                         % [(f["type"], len(f.get("events") or [])) for f in self._chat_frames(a, S1)])
        rows = self._rows("chatStale")
        self.assertEqual(len(rows), 1, "one chatStale row per refusal: %r" % rows)
        d = rows[0]["data"]
        self.assertEqual((d["sid"], d["kind"], d["liveFrame"], d["liveHeld"]), (S1, "page", 9, 7))
        self.assertEqual((d["txFrame"][0][1], d["txHeld"][0][1]), (1500, 2000), "the row names both readings' transcript rows")
        self.assertEqual(a["echatWm"][S1]["tx"][0][1], 2000, "the floor is still the newer build's")
        # the next NEWER build flows again, as a delta against the base the client holds
        self.SESS[S1] = _sess(S1, 6, 2400, 10); km._built_chat.clear()
        km._push([a])
        self.assertEqual([f["type"] for f in self._chat_frames(a, S1)], ["session", "chatTail"], "a newer build lands as the delta it is")
        self.assertEqual(self._chat_frames(a, S1)[-1]["wm"]["tx"][0][1], 2400)
        self.assertEqual(len(self._rows("chatStale")), 1, "no second row for a frame that went")

    def test_02_the_index_wire_is_guarded_too(self):
        a = self._client(active=S1)                    # no proto: the index wire
        km._clients.append(a)
        km._push([a])
        self.assertEqual([f["type"] for f in self._chat_frames(a, S1)], ["session"])
        self._older()
        km._push_session_now(S1)
        self.assertEqual(len(self._chat_frames(a, S1)), 1, "the index client kept the newer list too")
        self.assertEqual(len(self._rows("chatStale")), 1)

    def test_03_the_older_build_reaching_the_pusher_cycle_is_refused_there_too(self):
        # the other pairing: the targeted push handed the newer list; the cycle's build read the older transcript
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push_session_now(S1)
        self.assertEqual([f["type"] for f in self._chat_frames(a, S1)], ["session"])
        self._older()
        km._push([a])
        self.assertEqual(len(self._chat_frames(a, S1)), 1, "the cycle's older build did not reach the client")
        self.assertEqual(len(self._rows("chatStale")), 1)

    def test_04_a_client_holding_no_base_takes_any_build(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        self._older()                                  # the first build this client ever sees is the older one: nothing to compare
        km._push([a])
        self.assertEqual([f["type"] for f in self._chat_frames(a, S1)], ["session"], "a client holding nothing is served")
        self.assertEqual(self._rows("chatStale"), [])

    def test_05_a_reset_drops_the_floor_with_the_base(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push([a])
        km._client_reset_chat_sid(a, S1)               # needFull: the client re-bases and holds nothing for S1
        self.assertNotIn(S1, a.get("echatWm", {}), "the floor went with the base")
        self._older()
        km._push_session_now(S1)
        self.assertEqual(len(self._chat_frames(a, S1)), 2, "the ask is answered with whatever the kernel now has: no floor stands")
        km._client_reset_chat_base(a)
        self.assertEqual(a.get("echatWm"), {}, "ready: every floor goes")

    def test_06_another_leaf_is_never_older(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push([a])
        self.SESS[S1] = _sess(S1, 2, 300, 1, leaf=LEAF1 + ".fork"); km._built_chat.clear()   # a rewind: a new transcript, fewer bytes
        km._push_session_now(S1)
        self.assertEqual(len(self._chat_frames(a, S1)), 2, "a build of another leaf is the kernel's word about a new file: sent")
        self.assertEqual(self._rows("chatStale"), [])

    def test_07_the_stderr_line_is_said_once_per_session_and_the_rows_count_every_refusal(self):
        import contextlib, io
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push([a])
        self._older()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push_session_now(S1)
            km._push_session_now(S1)
        lines = [ln for ln in err.getvalue().splitlines() if "older than the one" in ln]
        self.assertEqual(len(lines), 1, "one line per session per kernel life: %r" % lines)
        self.assertIn(S1[:8], lines[0])
        self.assertNotIn("notes-api", lines[0], "the line carries no text, only the session's id prefix and the readings")
        self.assertEqual(len(self._rows("chatStale")), 2, "…while every refusal files its row")

    def test_08_the_watermark_rides_the_frame_through_the_relay_shape_untouched(self):
        # the hub prefixes ids on the way in (ui/webview/federation.ts prefixInbound): unknown fields pass through, so a remote
        # kernel's watermark reaches the page as sent. Pinned here by the wire: the kernel puts it top-level on both frame types.
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        km._push([a])
        self.SESS[S1] = _sess(S1, 6, 2400, 8); km._built_chat.clear()
        km._push([a])
        full, tail = self._chat_frames(a, S1)
        self.assertEqual((full["type"], tail["type"]), ("session", "chatTail"))
        for f in (full, tail):
            self.assertEqual(set(f["wm"]), {"leaf", "tx", "live"})
            self.assertEqual(f["wm"]["leaf"], LEAF1)


class TheStamp(unittest.TestCase):
    """build_session stamps what it read: the parse's fileset key (as jd.parsed_session served the tree) and the live revision."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE, km.NAMES, km._sdk)
        names = td / "names"; names.mkdir()
        proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        for d in (jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR):
            d.mkdir()
        jd.STATE = td
        km.NAMES = names
        km._sdk = lambda: None
        cdir = td / "work"; cdir.mkdir()
        pdir = proj / re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        rec = {"type": "user", "timestamp": "2026-09-22T10:00:00.000Z", "uuid": "u1", "parentUuid": None, "promptSource": "typed",
               "message": {"role": "user", "content": "tighten the notes-api search"}}
        self.path = str(pdir / (S1 + ".jsonl"))
        Path(self.path).write_text(json.dumps(rec) + "\n")
        (names / S1).write_text("web\t%s\t#abcdef\n" % str(cdir))

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE, km.NAMES, km._sdk) = self.saved
        self.td.cleanup()

    def test_the_frame_carries_the_parse_key_the_tree_was_served_under_and_a_live_revision(self):
        now = 1790000000
        m = km.build_session(S1, now, live_map={})
        self.assertIsNotNone(m, "the session builds")
        wm = m.get("wm")
        self.assertIsInstance(wm, dict)
        self.assertEqual(wm["leaf"], self.path)
        st = os.stat(self.path)
        rows = wm["tx"]
        self.assertIsInstance(rows, list)
        self.assertIn([st.st_mtime, st.st_size], [list(r) for r in rows], "the transcript's own [mtime, size] row is among the key's rows: %r" % rows)
        self.assertIn(type(wm["live"]), (int, type(None)), "the live revision when the backend counts one, else nothing (never a backend's serialized tail)")
        # an append moves the key: the next build's rows are at or past the last's, and the older frame reads as older
        with open(self.path, "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-09-22T10:00:05.000Z", "uuid": "a1", "parentUuid": "u1",
                                "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}}) + "\n")
        os.utime(self.path, (st.st_mtime + 2, st.st_mtime + 2))
        m2 = km.build_session(S1, now + 5, live_map={})
        self.assertTrue(km._chat_wm_older(m["wm"], m2["wm"]), "the first build read less: older than the second: %r vs %r" % (m["wm"], m2["wm"]))
        self.assertFalse(km._chat_wm_older(m2["wm"], m["wm"]))


if __name__ == "__main__":
    unittest.main()


class LandingAnchor(StaleBuildGuard):
    """The delta that lands a send never anchors before the previous human turn (the user 2026-09-22, second report: an
    EARLIER message vanished when a new send landed). Two shapes, over the real senders: the echo at the tail of the
    client's base (a9d9ace5: an in-flight echo sorts after every atom of its turn) replaced by the CLI's record and its
    reply; and the streamed reply's key changing under the landing (a one-block live atom whose record splits into
    `uuid#n` events), which sends a full frame instead. In both the frame the client receives carries the previous human
    turn, and the delta's anchor is the record before the echo, never that turn or anything above it."""

    def _base(self, a):
        evs = [{"kind": "user", "uuid": "u0", "md": "first ask"}, {"kind": "assistant", "uuid": "a0", "md": "first reply"},
               {"kind": "user", "uuid": "u1", "md": "the previous message"},
               {"kind": "assistant", "uuid": "a1", "md": "thinking, streamed"},
               {"kind": "user", "uuid": "echo:11111111222233334444555555555555", "md": "the new message", "echo": True}]
        self.SESS[S1] = dict(_sess(S1, 0, 2000, 7), events=evs)
        km._built_chat.clear()
        km._push([a])
        held = self._chat_frames(a, S1)
        self.assertEqual([f["type"] for f in held], ["session"])
        self.assertEqual([e["uuid"] for e in held[0]["events"]], ["u0", "a0", "u1", "a1", "echo:11111111222233334444555555555555"])
        self.assertEqual(a["echat"][S1]["last"], "a1", "the base's last edge is the record before the echo, never the echo (2026-09-19)")

    def test_10_the_landing_delta_anchors_on_the_record_before_the_echo_and_carries_only_the_suffix(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        self._base(a)
        evs = [{"kind": "user", "uuid": "u0", "md": "first ask"}, {"kind": "assistant", "uuid": "a0", "md": "first reply"},
               {"kind": "user", "uuid": "u1", "md": "the previous message"},
               {"kind": "assistant", "uuid": "a1", "md": "thinking, streamed"},
               {"kind": "user", "uuid": "u2", "md": "the new message", "qid": "echo:11111111222233334444555555555555"},
               {"kind": "assistant", "uuid": "a2", "md": "the reply"}]
        self.SESS[S1] = dict(_sess(S1, 0, 2400, 8), events=evs)
        km._built_chat.clear()
        km._push([a])
        frames = self._chat_frames(a, S1)
        self.assertEqual([f["type"] for f in frames], ["session", "chatTail"], "the landing is a delta, never a full")
        tail = frames[-1]
        self.assertEqual(tail["afterUuid"], "a1", "anchored on the record before the echo")
        self.assertEqual([e["uuid"] for e in tail["events"]], ["u2", "a2"], "the suffix: the landed record and the reply; the previous human turn is not in it and not before the anchor's replacement")
        self.assertNotIn("u1", [e["uuid"] for e in tail["events"]])
        self.assertEqual(a["echat"][S1]["last"], "a2")

    def test_11_the_streamed_replys_key_splitting_under_the_landing_sends_a_full_that_carries_the_previous_turn(self):
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        self._base(a)
        evs = [{"kind": "user", "uuid": "u0", "md": "first ask"}, {"kind": "assistant", "uuid": "a0", "md": "first reply"},
               {"kind": "user", "uuid": "u1", "md": "the previous message"},
               {"kind": "assistant", "uuid": "a1", "key": "a1#0", "md": "thinking, recorded"},
               {"kind": "assistant", "uuid": "a1", "key": "a1#1", "md": "the text block of the same record"},
               {"kind": "user", "uuid": "u2", "md": "the new message", "qid": "echo:11111111222233334444555555555555"}]
        self.SESS[S1] = dict(_sess(S1, 0, 2400, 8), events=evs)
        km._built_chat.clear()
        km._push([a])
        frames = self._chat_frames(a, S1)
        self.assertEqual([f["type"] for f in frames], ["session", "session"], "the held last edge (a1) is gone from the list: a full frame (lastGone:record)")
        full = frames[-1]
        self.assertEqual([e.get("key") or e["uuid"] for e in full["events"]], ["u0", "a0", "u1", "a1#0", "a1#1", "u2"], "the whole tail run, the previous human turn included")
        rows = self._rows("chatFull")
        self.assertEqual([r["data"]["reason"] for r in rows], ["lastGone:record"], "the shape the remote kernel filed at each of the user's sends")
