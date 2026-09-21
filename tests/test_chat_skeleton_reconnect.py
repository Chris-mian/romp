#!/usr/bin/env python3
"""Reconnect skeletons — the kernel half (the user 2026-09-07, whose panes redialed after a long freeze and
pulled every session whole for the one tab on screen).

When a pane's socket died while its browser tab was away (a long freeze, a laptop sleep, a network change),
the redial used to be served as a client that holds nothing: a full {type:"session"} for EVERY tab — 17 frames,
~9 MB on the measured board — for one tab on screen. The page still holds every session it had; it only needs
the one it shows. Now a redial after the bundle's ready declares itself (?reconnect=1, test_pane_shim_return.py) and
the kernel sends THAT client the tab strip with a `skeleton` list (every listed tab but the active one, cheapest
transcript first), the active tab's full session, and a small status frame per skeleton tab so its chip stays
honest. A skeleton tab loads on the user's click (activeTab / needFull), on the client's idle prefetch
(needFull), or on any full the kernel sends for another reason; `ready` (a renderer that just evaluated, so it
holds nothing) clears the whole set. A client that declares no reconnect gets today's frames, byte for byte.

Drives the REAL _push / _push_session_now / _confirm_close_now / Handler._dispatch_ws / Handler._ws over fake
clients (the test_tab_meta_push.py pattern), with build_session stubbed to synthetic payloads and real temp
transcript files of distinct sizes (the size is the kernel's cost proxy). Synthetic only: the notes-api demo
world (web/api/tests/docs), placeholder UUIDs, TESTHOST.
"""
import contextlib
import inspect
import io
import json
import os
import re
import tempfile
import threading
import unittest
from romp_load import load_source
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_skeleton", os.path.join(BIN, "romp-kernel"))

S1 = "11111111-2222-3333-4444-555555555551"   # web   — the tab the page is looking at (mid-size transcript)
S2 = "11111111-2222-3333-4444-555555555552"   # api   — the BIGGEST transcript
S3 = "11111111-2222-3333-4444-555555555553"   # tests — the smallest transcript
S4 = "11111111-2222-3333-4444-555555555554"   # docs  — just created: no transcript on disk yet
GONE = "11111111-2222-3333-4444-555555555559"  # an ended session, listed nowhere
NAMES = {S1: "web", S2: "api", S3: "tests", S4: "docs"}
TAB_ORDER = [S2, S1, S3, S4]                  # big, mid, small — the tab order is NOT the size order
SIZES = {S2: 3000, S1: 2000, S3: 1000}        # transcript bytes; S4 has none
# the journal of a tap that parked on the named road and was landed by the redial's first strip (item 12)
REDIAL_TRAIL = r"\[reveal\] %s sid=\S+ wid=W1: parked[\s\S]*\[reveal\] sid=\S+ wid=W1: consumed \S+ the pane's redial"


def _owners(src, token):
    """The defs whose bodies mention `token` (their own def line excluded): test_11's census, for the asked mark too
    (2026-09-19). Module-level lines count against the preceding def, comments and docstrings included."""
    cur, found = None, set()
    for ln in src.splitlines():
        m = re.match(r"^\s*def (\w+)\(", ln)
        if m:
            cur = m.group(1)
            continue
        if token in ln:
            found.add(cur)
    return found


def _sess(sid, n, state):
    """A synthetic build_session payload: n events (well under WIRE_TAIL, so a full send is the whole thing)."""
    return {"type": "session", "id": sid, "name": NAMES[sid],
            "events": [{"kind": "assistant", "uuid": "u%d" % i, "md": "m%d" % i} for i in range(n)],
            "status": {"state": state, "sinceEpoch": None}, "ledger": None}


class _Self:
    """The handler's `self` for _dispatch_ws: only _push_one is reached by the frames driven here. Records
    the call; runs `push_one` when given one (the real body is _push([client], connect=True))."""
    def __init__(self, push_one=None):
        self.calls = []
        self._po = push_one

    def _push_one(self, client):
        self.calls.append(client)
        if self._po:
            self._po(client)


def _fake_self(path):
    """A connect handler with a peer that closes at once (the test_view_deltas.py HandlerWiring shape)."""
    class FakeSelf:
        headers = {"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
        rfile = io.BytesIO(); wfile = io.BytesIO()
        connection = type("FakeSock", (), {"sendall": lambda self, b: None, "shutdown": lambda self, how: None})()
        close_connection = False
        def send_response(self, *a): pass
        def send_header(self, *a): pass
        def end_headers(self): pass
    FakeSelf.path = path
    return FakeSelf()


class SkeletonReconnect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid, n in SIZES.items():          # real files: os.path.getsize is the kernel's ranking, so it must stat
            p = os.path.join(self.tmp, sid + ".jsonl")
            with open(p, "w") as f:
                f.write("x" * n)              # content is irrelevant to the kernel here; the SIZE is the cost proxy
            self.paths[sid] = p
        self.paths[S4] = os.path.join(self.tmp, S4 + ".jsonl")   # never written: the transcript-less session
        self.SESS = {S1: _sess(S1, 5, "working"), S2: _sess(S2, 7, "working"),
                     S3: _sess(S3, 3, "waiting"), S4: _sess(S4, 0, "waiting")}
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
                       km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients))
        km._chat_tab_sessions = lambda now, live_map: [
            {"sid": sid, "name": NAMES[sid], "path": self.paths[sid], "anchor": sid} for sid in TAB_ORDER]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None          # no feed build — the chat frames are what is pinned
        self.built = []

        def build(sid, now, live_map=None, **kw):
            self.built.append(sid)
            return json.loads(json.dumps(self.SESS[sid]))   # a fresh copy per build, as the real builder returns
        km.build_session = build
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"
        km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"
        km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear()
        km._prev_chat_events.clear()
        km._prev_chat_ledger.clear()
        km._chat_baseline_raced.clear()   # the detector's mark (tests 23 to 27) is not left for the next test
        del km._clients[:]
        km._pusher_wake.clear()

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
         km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, clients) = self._saved
        del km._clients[:]
        km._clients.extend(clients)
        km._built_chat.clear()
        km._prev_chat_events.clear()
        km._prev_chat_ledger.clear()
        km._chat_baseline_raced.clear()   # the detector's mark (tests 23 to 27) is not left for the next test

    # ── helpers ──
    def _client(self, **kw):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)),
             "_frames": frames}
        c.update(kw)
        return c

    @staticmethod
    def _frames(c, typ=None):
        return [f for f in c["_frames"] if typ is None or f["type"] == typ]

    def _sessions(self, c):
        return [f["id"] for f in self._frames(c, "session")]

    def _statuses(self, c):
        return [(f["id"], f["status"]) for f in self._frames(c, "status")]

    def _tab_orders(self, c):
        return self._frames(c, "tabOrder")

    def _diag_rows(self, what):
        """The client-diag rows of one `what` in this test's state root; none when no row was ever filed."""
        fp = km.jd.STATE / "client-diag.jsonl"
        if not fp.exists():
            return []
        return [r for r in (json.loads(ln) for ln in fp.read_text().splitlines() if ln.strip()) if r.get("what") == what]

    # ── §4.1 item 1 ──
    def test_00a_a_sid_already_held_whole_is_never_listed_when_the_set_resolves(self):
        # a full that won the race (a create's _push_session_now landing between the flag's pop and the set's write)
        # used to be re-listed as skeleton and then starved of tails (review find 2026-09-07): the resolve is atomic
        # under the client lock now, and a sid echat already holds is excluded outright
        import inspect
        c = self._client(active=S1, reconnect=True)
        c.setdefault("echat", {})[S3] = ("11111111-2222-3333-4444-555555555553", 0)
        km._push([c])
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S2], "S3 is held whole → not a skeleton")
        self.assertEqual(c["skeleton"], {S2})
        self.assertTrue(c["skeleton"].isdisjoint(c["echat"]), "the two stores never both hold a sid")
        src = inspect.getsource(km._resolve_reconnect)
        self.assertLess(src.index("with _client_lock(c):"), src.index('c.pop("reconnect"'), "flag, stats and write: one locked step")

    def test_00b_a_skeleton_sid_whose_session_left_the_strip_leaves_the_set_and_its_status_slot(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        self.assertEqual(c["skeleton"], {S2, S3})
        orig = km._chat_tab_sessions
        km._chat_tab_sessions = lambda now, live_map: [s for s in orig(now, live_map) if s["sid"] != S3]   # S3 ended
        try:
            km._push([c])
        finally:
            km._chat_tab_sessions = orig
        self.assertEqual(c["skeleton"], {S2}, "a session the strip no longer lists is not a skeleton (review find 2026-09-07)")
        self.assertEqual(self._tab_orders(c)[-1]["skeleton"], [S2], "…and no strip names a sid its order lacks")
        self.assertNotIn(("status", S3), c["sent"], "its status slot went with it")

    def test_01_a_reconnecting_client_gets_the_strip_with_skeleton_and_one_full(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        self.assertEqual(self._sessions(c), [S1, S4],
                         "one full for the tab on screen — plus the transcript-less one, which is never a skeleton")
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1)
        self.assertEqual(to[0]["order"], TAB_ORDER)
        self.assertEqual(to[0]["skeleton"], [S3, S2],
                         "ascending transcript size (small, big) — NOT tab order (big, small), and never the active")
        self.assertEqual(sorted(self._statuses(c)),
                         sorted([(S2, self.SESS[S2]["status"]), (S3, self.SESS[S3]["status"])]),
                         "one status frame per skeleton sid, carrying that session's status")
        self.assertEqual(c["skeleton"], {S2, S3})
        self.assertEqual(c["skeletonOrder"], [S3, S2])
        self.assertEqual(set(c["echat"]), {S1, S4}, "echat knows only the tabs that were sent whole")
        for sid in (S2, S3):
            self.assertNotIn(("chat", sid), c["sent"], "a skeleton sid never took the chat slot")
            self.assertIn(("status", sid), c["sent"], "…it rode its own status slot")
        self.assertIsNone(c.get("reconnect"), "one-shot: the first strip sender consumed it")
        types = [f["type"] for f in c["_frames"]]
        self.assertNotIn("chatTail", types)
        self.assertLess(types.index("tabOrder"), types.index("session"), "strip first")
        first_sess = self._frames(c, "session")[0]
        self.assertEqual(first_sess["id"], S1, "the active tab's full is the first session frame")
        self.assertLess(c["_frames"].index(first_sess), c["_frames"].index(self._frames(c, "status")[0]),
                        "the status frames trail the active full")

    # ── item 2 ──
    def test_02_the_next_cycle_sends_no_skeleton_sid_and_its_status_dedups(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        c["_frames"].clear()
        km._push([c])
        self.assertEqual([f for f in c["_frames"] if f["type"] in ("session", "chatTail") and f["id"] in (S2, S3)],
                         [], "no chat of any shape for a skeleton sid")
        self.assertEqual(self._statuses(c), [], "an unchanged status is deduped on its slot")
        for sid in (S2, S3):
            self.assertIsNone(km._built_chat[sid][2],
                              "the lazy full serialization was never materialized for a skeleton sid")
        self.assertIsNotNone(km._built_chat[S1][2], "…while the active tab's full send did materialize it")
        # a real transition: the status changes WITH the transcript, as it does live (the build cache keys on the
        # file stat) → exactly one status frame, for that sid, and still no full
        self.SESS[S2]["status"]["state"] = "waiting"
        with open(self.paths[S2], "a") as f:
            f.write("y")
        c["_frames"].clear()
        km._push([c])
        self.assertEqual(self._statuses(c), [(S2, {"state": "waiting", "sinceEpoch": None})])
        self.assertEqual(self._sessions(c), [], "still no full for a skeleton sid")
        self.assertEqual(c["skeleton"], {S2, S3}, "a status change releases nothing")

    # ── item 3 ──
    def test_03_activetab_releases_exactly_one_and_wakes_the_pusher(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        c["_frames"].clear()
        km._pusher_wake.clear()
        km.Handler._dispatch_ws(_Self(), {"type": "activeTab", "id": S2}, c)
        self.assertEqual(c["skeleton"], {S3}, "only the clicked tab left the set")
        self.assertEqual(c["active"], S2)
        self.assertTrue(km._pusher_wake.is_set(), "the click is the event the next cycle rides")
        self.assertNotIn(("status", S2), c["sent"], "its status slot went with it")
        km._push([c])
        self.assertEqual(self._sessions(c), [S2], "the released tab's full — and no S3")
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1, "the strip is re-sent: its skeleton list changed, so its sig changed")
        self.assertEqual(to[0]["skeleton"], [S3])
        self.assertEqual(self._statuses(c), [], "S3's status is unchanged → deduped")

    def test_03b_activetab_naming_a_remote_or_unknown_id_releases_nothing(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        km.Handler._dispatch_ws(_Self(), {"type": "activeTab", "id": "gpu1:" + S2}, c)
        self.assertEqual(c["skeleton"], {S2, S3})
        km.Handler._dispatch_ws(_Self(), {"type": "activeTab", "id": None}, c)
        self.assertEqual(c["skeleton"], {S2, S3})

    # ── item 4 ──
    def test_04_needfull_releases_exactly_one_and_repairs_now(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        km.Handler._dispatch_ws(_Self(), {"type": "activeTab", "id": S2}, c)   # S2 loads on its click…
        km._push([c])
        c["_frames"].clear()
        h = _Self()                                                             # …S3 on the idle prefetch's ask
        km.Handler._dispatch_ws(h, {"type": "needFull", "id": S3, "why": "prefetch"}, c)   # `why` is the client's diagnostic; ignored here
        self.assertEqual(c["skeleton"], set(), "the set emptied")
        self.assertNotIn(("status", S3), c["sent"], "_client_reset_chat_sid popped the status slot with the release")
        self.assertEqual(h.calls, [c], "the repair push ran on the handler thread, not on the next tick")
        km._push([c], connect=True)                                             # what that _push_one does
        self.assertEqual(self._sessions(c), [S3])
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1, "the strip changed (no set) → re-sent")
        self.assertEqual(to[0].get("skeleton"), [], "an empty set is SAID as [] once a set has existed: the federated merge keeps a host's last list on an absent key")
        # the control for test_04b (2026-09-19): in the pusher-first order the ask marks the sid asked-whole too, and the
        # full that answers it consumes the mark all the same
        self.assertNotIn(S3, c.get("askedFull") or (), "the full that answered the ask consumed its mark")

    def test_04b_a_needfull_that_is_the_redials_first_strip_sender_is_answered_with_a_full(self):
        # THE ASK AS THE REDIAL'S FIRST STRIP SENDER (2026-09-19). A redial's fresh client: `reconnect` armed at the
        # handshake, no pusher cycle has resolved its set yet, and the page's gap ask for ANOTHER tab lands first (the dead
        # socket's frames draining from the shim's FIFO after the open, or the idle prefetch over the old socket's
        # still-held skeleton set). The needFull arm's reset released nothing (no set exists yet), and its own repair push
        # ran _resolve_reconnect, which built the set from the active hint and an empty echat: the asked sid qualified as
        # a skeleton, the strip named it, and the ask was answered with a STATUS frame, which never clears the page's
        # one-shot latch (render.ts awaitingFull). The tab stayed a skeleton until clicked, and the idle prefetch chain
        # (skeleton-tabs.ts nextPrefetch, null while any skeleton sid is in flight) was dead for the socket's life; the
        # kernel filed no row. Reproduced deterministically here; plausible live, where the window is one pusher cycle
        # wide. Now the ask marks the sid asked-whole for this client, every set decision honors the mark as it honors
        # echat, and the full that answers the ask consumes it.
        # `c` is deliberately NOT in km._clients, as test_04's is: appended, _push's cold-tab gate would read it through
        # _all_chat and S2 (never built since the boot, held as a skeleton by the only client) would take the light-status
        # path instead of _send_chat_or_status; the assertions would then hold only because the live map is {} here.
        # test_04d runs the gate on purpose, with a live row.
        c = self._client(active=S1, reconnect=True)
        h = type("H", (), {"_push_one": km.Handler._push_one})()   # the REAL _push_one body: it reads module globals alone
        km.Handler._dispatch_ws(h, {"type": "needFull", "id": S3, "why": "gap"}, c)
        self.assertEqual(sorted(self._sessions(c)), sorted([S1, S3, S4]), "the active, the asked, the transcript-less")
        self.assertEqual([s for s, _ in self._statuses(c)], [S2], "one status: the tab nobody asked for")
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S2], "the strip never names the asked sid")
        self.assertEqual(c["skeleton"], {S2})
        self.assertEqual(sorted(c["echat"]), sorted([S1, S3, S4]),
                         "the three fulls and nothing else: the mark's doing, not a full that won a race")
        self.assertNotIn(S3, c.get("askedFull") or (), "the full consumed the mark")
        types = [f["type"] for f in c["_frames"]]
        self.assertLess(types.index("tabOrder"), types.index("session"), "the strip is ahead of every full: the set's invariant")
        self.assertEqual(self._diag_rows("needFullStatus"), [], "the tripwire never fires on the designed path")

    def test_04b_relay_a_needfull_with_no_active_is_answered_with_a_full_on_the_relay_too(self):
        # The federated face of the same defect (2026-09-19): ui/webview/federation.ts holds a needFull per sid while the
        # relay is down and flushes it at the relay's open BEFORE romp:hostRelayUp fires, and render.ts clears awaitingFull
        # only on the LOCAL socket's open, so a status answer on the relay latched the remote tab for the page's life. The
        # remote dial carries no active unless the watched tab is that host's, and skeleton=1 from the page's own terms, so
        # the ask lands in _resolve_reconnect's no-active relay branch: the second set-building comprehension, which
        # test_04b never reaches.
        c = self._client(kind="relay", reconnect=True, dietSkeleton=True)   # no active
        h = type("H", (), {"_push_one": km.Handler._push_one})()
        km.Handler._dispatch_ws(h, {"type": "needFull", "id": S3, "why": "gap"}, c)
        self.assertEqual(sorted(self._sessions(c)), sorted([S3, S4]),
                         "the asked and the transcript-less (build order ranks the transcript-less first)")
        self.assertEqual(sorted(s for s, _ in self._statuses(c)), sorted([S1, S2]), "a status per other transcript-bearing tab")
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S1, S2], "cheapest first, never the asked")
        self.assertEqual(c["skeleton"], {S1, S2})
        self.assertEqual(sorted(c["echat"]), sorted([S3, S4]))
        self.assertNotIn(S3, c.get("askedFull") or ())
        types = [f["type"] for f in c["_frames"]]
        self.assertLess(types.index("tabOrder"), types.index("session"))

    def test_04b_proto2_the_live_redials_wire_answers_the_ask_with_a_full_and_consumes_the_mark(self):
        # The wire a live redial declares (2026-09-19): the shim's redial term carries &proto=<readyProto> (test_10), so the
        # handshake registers proto 2 and _send_chat_locked hands every full to _send_chat_proto2, whose discard beside the
        # {first, last} base write is the one a live client's consumption rests on. test_04b drives the index wire alone,
        # so without this twin a later edit that returned before that discard on this wire kept the module green (test_04e
        # pins the two tokens' order, not that the line is reached) while every live redial's mark lingered; a stale mark
        # only widens the gate's build and never re-lists the sid, so the harm is bounded, and the live path is shown.
        c = self._client(active=S1, reconnect=True, proto=2)
        h = type("H", (), {"_push_one": km.Handler._push_one})()
        km.Handler._dispatch_ws(h, {"type": "needFull", "id": S3, "why": "gap"}, c)
        self.assertEqual(sorted(self._sessions(c)), sorted([S1, S3, S4]), "the active, the asked, the transcript-less")
        asked = [f for f in self._frames(c, "session") if f["id"] == S3]
        self.assertEqual([f.get("proto") for f in asked], [2], "the asked full went once, on the uuid-anchored wire")
        self.assertEqual((asked[0].get("firstUuid"), asked[0].get("lastUuid")), ("u0", "u2"), "anchored on its own events")
        self.assertEqual([s for s, _ in self._statuses(c)], [S2], "one status: the tab nobody asked for")
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S2], "the strip never names the asked sid")
        # the transcript-less S4 went whole too (asserted above) and records NO base (2026-09-19, the review of the meter): a
        # proto-2 base is the tail run's two edges, and a list with no events has none; written as a both-None base, the
        # entry made every repost of the empty frame count as a full to a base holder and file a row
        self.assertEqual(sorted(c["echat"]), sorted([S1, S3]))
        self.assertTrue(all(isinstance(b, dict) for b in c["echat"].values()), "proto-2 bases: {first, last} dicts, never index tuples")
        self.assertNotIn(S3, c.get("askedFull") or (), "the proto-2 full consumed the mark")
        self.assertEqual(self._diag_rows("needFullStatus"), [], "the tripwire never fires on the designed path")

    def test_04c_a_status_for_an_asked_sid_is_said_on_the_record_and_answered_with_the_full(self):
        # The tripwire (2026-09-19), forced by hand: the set has ONE writer (_resolve_reconnect), which excludes an asked
        # sid, and every other touch shrinks it, so a set naming an asked sid is unreachable by construction (test_04b
        # runs the designed path and finds no row). If a future writer breaches it, the status branch files one
        # client-diag row (the _note_history_reply shape) naming the client and the sid, and falls through to the full:
        # the ask is answered, never frozen. The client models a socket past its handshake (no handshake key, so
        # _send_chat_locked serves it on the index wire).
        c = self._client(active=S1, skeleton={S3}, skeletonOrder=[S3], askedFull={S3})
        self.assertFalse(km._held_as_skeleton_by_all(S3, [c]), "an asked sid is never held as a skeleton, even when a set names it")
        self.assertTrue(km._held_as_skeleton_by_all(S3, [self._client(active=S1, skeleton={S3}, skeletonOrder=[S3])]),
                        "…while the unasked twin is: the mark alone makes the difference")
        km._send_chat_or_status(c, json.loads(json.dumps(self.SESS[S3])), None, 3, False)
        self.assertEqual(self._sessions(c), [S3], "the full, not the status")
        self.assertEqual(self._statuses(c), [])
        self.assertEqual(c["skeleton"], set(), "the full's release")
        self.assertEqual(c["askedFull"], set(), "…consumed the mark")
        self.assertIn(S3, c["echat"])
        rows = self._diag_rows("needFullStatus")
        self.assertEqual(len(rows), 1, "one row for the breach")
        self.assertEqual(set(rows[0]), {"t", "wid", "surface", "what", "data"}, "the _note_history_reply shape")
        self.assertEqual((rows[0]["surface"], rows[0]["what"], rows[0]["data"]["sid"]), ("kernel", "needFullStatus", S3))
        self.assertEqual(set(rows[0]["data"]), {"sid", "cid", "kind"})
        last = (km.jd.STATE / "client-diag.jsonl").read_text().splitlines()[-1]
        self.assertEqual(json.loads(last)["what"], "needFullStatus", "the row is the file's last line")
        # the fall-through is not a guaranteed full: with `reconnect` armed the guard below the branch withholds the
        # session frame for the strip sender's push, as it withholds every session frame; the row is filed all the same
        d = self._client(active=S1, reconnect=True, skeleton={S3}, skeletonOrder=[S3], askedFull={S3})
        km._send_chat_or_status(d, json.loads(json.dumps(self.SESS[S3])), None, 3, False)
        self.assertEqual(d["_frames"], [], "withheld by the guard: no status, no full")
        self.assertEqual(len(self._diag_rows("needFullStatus")), 2, "…and said on the record all the same")
        self.assertEqual(d["skeleton"], {S3}, "nothing released here: the strip sender's push answers")
        # the helper joins no owner set: none of the set's tokens anywhere in its body (test_11's census is exact)
        src = inspect.getsource(km._note_needfull_status)
        for tok in ('"skeleton"', '"skeletonOrder"', "_release_skeleton_locked(", "_tab_order_frame(", "_send_chat_locked("):
            self.assertNotIn(tok, src, tok)

    def test_04c_proto2_the_tripwires_fall_through_consumes_the_mark_on_the_live_wire_too(self):
        # test_04c's forced breach on the wire a live redial declares (2026-09-19): the fall-through's full goes through
        # _send_chat_proto2, so the mark's consumption shown here is the one live clients rest on
        c = self._client(active=S1, skeleton={S3}, skeletonOrder=[S3], askedFull={S3}, proto=2)
        km._send_chat_or_status(c, json.loads(json.dumps(self.SESS[S3])), None, 3, False)
        self.assertEqual([(f["id"], f.get("proto")) for f in self._frames(c, "session")], [(S3, 2)], "the full, on the uuid-anchored wire")
        self.assertEqual(self._statuses(c), [], "not the status")
        self.assertEqual(c["skeleton"], set(), "the full's release")
        self.assertEqual(c["askedFull"], set(), "consumed beside the {first, last} base write")
        self.assertIsInstance(c["echat"][S3], dict)
        self.assertEqual(len(self._diag_rows("needFullStatus")), 1, "one row for the breach, as on the index wire")

    def test_04d_the_cold_tab_gate_never_holds_an_asked_sid(self):
        # _held_as_skeleton_by_all reads the asked mark as it reads echat, in both its reads (2026-09-19). The UNRESOLVED
        # prediction is the reachable one: between the handler thread's mark and its own push's resolve, another push's
        # gate (the pusher's cycle over every connected client) reads this client with `reconnect` still armed, and
        # predicted the asked tab held as a skeleton, so a cold asked tab was not built by that push (cost only); the
        # prediction now matches what the resolve will do with the mark. The RESOLVED read's guard is test_04c's forced state.
        c = self._client(active=S1, reconnect=True)
        km.Handler._dispatch_ws(_Self(), {"type": "needFull", "id": S3, "why": "gap"}, c)   # a bare _Self: the mark stands, no push yet
        self.assertEqual(c.get("askedFull"), {S3}, "the ask marked the sid on the client")
        self.assertIs(c.get("reconnect"), True, "…and resolved nothing: no strip sender has run")
        self.assertFalse(km._held_as_skeleton_by_all(S3, [c]), "the asked tab is not predicted held")
        self.assertTrue(km._held_as_skeleton_by_all(S2, [c]), "…while the unasked one still is")
        # …and the ask-first flow WITH the gate in play (the client in _clients; the asked tab cold, with a live row the
        # gate could state a status from): the asked tab is built and sent whole, and no status frame goes for it
        km._clients.append(c)
        km._live_map = lambda: {S3: {"state": "waiting", "since": 1781100000, "model": "", "effort": "", "mode": "", "backend": "sdk"}}
        self.assertFalse(km._built_chat, "cold: nothing built since the boot")
        h = type("H", (), {"_push_one": km.Handler._push_one})()
        h._push_one(c)
        self.assertIn(S3, self.built, "the asked tab was built: the gate did not hold it")
        self.assertEqual(sorted(self._sessions(c)), sorted([S1, S3, S4]))
        self.assertEqual([s for s, _ in self._statuses(c)], [S2], "one status, the tab nobody asked for")
        self.assertEqual(c["skeleton"], {S2})
        self.assertNotIn(S3, c.get("askedFull") or ())

    def test_04e_source_pins_the_asked_mark_has_one_writer_and_every_reader_holds_the_lock(self):
        # the exactness guarantee for a set with one writer (2026-09-19): both set-building comprehensions in
        # _resolve_reconnect exclude an asked sid; the mark is read under the client's lock; written in
        # _client_reset_chat_sid after the release and before the def's end; consumed where each full branch writes its
        # echat entry, never inside _release_skeleton_locked (a click must not settle an ask no full has answered); dropped
        # whole by the ready arm's reset beside the set; and touched nowhere else
        rr = inspect.getsource(km._resolve_reconnect)
        self.assertEqual(rr.count("sid not in asked"), 2, "the relay no-active branch and the active branch")
        self.assertLess(rr.index("with _client_lock(c):"), rr.index('asked = c.get("askedFull") or ()'))
        rs = inspect.getsource(km._client_reset_chat_sid)
        self.assertLess(rs.index("with _client_lock(client):"), rs.index("_release_skeleton_locked(client, sid)"))
        self.assertLess(rs.index("_release_skeleton_locked(client, sid)"), rs.index('client.setdefault("askedFull", set()).add(sid)'))
        hs = inspect.getsource(km._held_as_skeleton_by_all)
        self.assertEqual(hs.count("sid not in asked"), 2, "the resolved read and the unresolved prediction")
        self.assertLess(hs.index("with _client_lock(c):"), hs.index('asked = c.get("askedFull") or ()'))
        for fn in (km._send_chat_proto2, km._send_chat_locked):
            s = inspect.getsource(fn)
            self.assertLess(s.index("_release_skeleton_locked(c, sid)"), s.index('(c.get("askedFull") or set()).discard(sid)'), fn.__name__)
        self.assertNotIn("askedFull", inspect.getsource(km._release_skeleton_locked), "a click's release settles no ask")
        rb = inspect.getsource(km._client_reset_chat_base)
        self.assertLess(rb.index("with _client_lock(client):"), rb.index('client.pop("askedFull", None)'))
        self.assertLess(rb.index('client.pop("askedFull", None)'), rb.index('if client.pop("skeletonOnReady", False):'),
                        "beside the set's pops, not inside the re-arm block")
        so = inspect.getsource(km._send_chat_or_status)
        self.assertLess(so.index('if sid in (c.get("skeleton") or ()):'), so.index('if sid in (c.get("askedFull") or ()):'))
        self.assertLess(so.index('if sid in (c.get("askedFull") or ()):'), so.index('if c.get("skeletonOnReady") or c.get("reconnect"):'),
                        "nested in the status branch, ahead of the guard the fall-through still meets")
        self.assertEqual(_owners(inspect.getsource(km), '"askedFull"'),
                         {"_client_reset_chat_sid", "_client_reset_chat_base", "_resolve_reconnect", "_held_as_skeleton_by_all",
                          "_send_chat_or_status", "_send_chat_proto2", "_send_chat_locked"},
                         "the mark is touched only in these, each under the client's slot lock")
        # the byte windows tests/test_chat_delta_resync.py and ui/webview/chat-delta-resync.test.ts read still hold their pins
        src = inspect.getsource(km)
        j = src.find("def _client_reset_chat_sid(client, sid):")
        for tok in ('"echat"', ".pop(sid, None)", '("chat", sid)'):
            self.assertIn(tok, src[j:j + 1200], tok + " within the 1200-character window from the def")

    # ── item 5 ──
    def test_05_a_push_session_now_for_a_skeleton_tab_sends_its_status_only_and_keeps_the_skeleton(self):
        # Until 2026-09-19 this push handed EVERY client a full (change_from forced to 0), which loaded a skeleton tab the
        # page never asked for; it goes through the pusher's per-client road now, so a tab the page holds as a skeleton
        # gets the status frame the pusher would send it and stays a skeleton until the click or the prefetch
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        c["_frames"].clear()
        km._clients.append(c)
        self.SESS[S3]["status"]["state"] = "working"   # the flip the push exists for (an unchanged status dedups on its slot)
        km._push_session_now(S3)                       # a create / handshake for a tab the page holds as skeleton
        self.assertEqual(self._sessions(c), [], "no full for a tab the page holds as a skeleton")
        self.assertEqual(self._statuses(c), [(S3, {"state": "working", "sinceEpoch": None})], "its status instead")
        self.assertEqual(c["skeleton"], {S2, S3}, "still a skeleton: the click or the prefetch releases it")
        self.assertIn(("status", S3), c["sent"])
        self.assertNotIn(("chat", S3), c["sent"])
        self.assertEqual(self._tab_orders(c), [], "its strip was identical to the one already held → deduped")
        c["_frames"].clear()
        c["sent"].pop(("taborder",))                   # the slot popped so the next strip is visible
        km._push([c])
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S3, S2], "the next cycle's strip still lists both")
        self.assertEqual(self._sessions(c), [], "and hands over no full either")

    # ── item 6 ──
    def test_06_a_fresh_client_is_unchanged(self):
        c = self._client(active=S1)
        km._push([c])
        self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER), "every full, as today")
        self.assertEqual(self._statuses(c), [], "no status frames for a client that declared no reconnect")
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1)
        self.assertEqual(set(to[0]), {"type", "order", "tabs", "views", "live", "selfHost"},
                         "today's frame, key for key (T258's `live` rides every strip; `selfHost` names the viewing "
                         "kernel since 2026-09-06): no new key for a client that did not declare a reconnect")
        for sid in TAB_ORDER:
            self.assertIn(("chat", sid), c["sent"])
        self.assertNotIn("skeleton", c)
        self.assertNotIn("skeletonOrder", c)
        self.assertFalse([k for k in c["sent"] if k[0] == "status"])

    def test_06b_ready_pops_the_set_and_the_repush_is_every_full(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        self.assertEqual(c["skeleton"], {S2, S3})
        c["_frames"].clear()
        c["reconnect"] = True                          # whatever the flag's state, the reset pops it before its push
        km.Handler._dispatch_ws(_Self(), {"type": "needFull", "id": S3, "why": "gap"}, c)   # an ask no push answered (a bare
        self.assertEqual(c.get("askedFull"), {S3})   #  _Self runs no push_one): its mark stands into the ready (2026-09-19)
        h = _Self(lambda cl: km._push([cl], connect=True))   # the real _push_one body
        km.Handler._dispatch_ws(h, {"type": "ready"}, c)
        for k in ("skeleton", "skeletonOrder", "reconnect", "askedFull"):
            self.assertNotIn(k, c, k)                  # a renderer that just evaluated holds nothing and asked nothing
        self.assertFalse([k for k in c["sent"] if k[0] == "status"], "every status slot went with the set")
        self.assertEqual(h.calls, [c])
        self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER), "the following push sends every full")
        self.assertNotIn("skeleton", self._tab_orders(c)[0], "no set → no key")

    # ── item 7 ──
    def test_07_no_active_hint_means_no_skeleton(self):
        c = self._client(reconnect=True)
        km._push([c])
        self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER), "the kernel cannot know what the page shows → everything")
        self.assertNotIn("skeleton", self._tab_orders(c)[0])
        self.assertNotIn("skeleton", c)
        self.assertIsNone(c.get("reconnect"), "consumed all the same")

    # ── item 8 ──
    def test_08_dedup_slots_flip_from_status_to_chat_on_release(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])
        self.assertIn(("status", S2), c["sent"])
        self.assertNotIn(("chat", S2), c["sent"])
        km.Handler._dispatch_ws(_Self(), {"type": "activeTab", "id": S2}, c)
        self.assertNotIn(("status", S2), c["sent"], "the release drops the status slot at once")
        km._push([c])
        self.assertIn(("chat", S2), c["sent"])
        self.assertNotIn(("status", S2), c["sent"])

    # ── item 9 ──
    def test_09_the_handshake_records_the_flag_and_wakes_the_pusher(self):
        # the third dial is a later chat column's FIRST (the split, 2026-09-11): skeleton=1 arms `reconnect` like a redial
        # AND `skeletonOnReady`, the flag the ready arm's reset spares (test_11_a runs the cycle). The fourth is that
        # column's REDIAL (the shim reads skeleton=1 off the address on every dial, reconnect=1 once its gate passes):
        # `reconnect` alone — its page said ready on an earlier socket, so no arm would ever pop the flag, and armed it
        # left the client unstamped for the page's life (review find 2026-09-11; test_11_c runs the cycle)
        for path, expect, view, flag, diet in (("/ws?app=chat&delta=1&iid=page-9&active=%s&reconnect=1" % S1, True, False, False, False),
                                         ("/ws?app=chat&delta=1&iid=page-9&active=%s" % S1, False, False, False, False),
                                         ("/ws?app=chat&delta=1&iid=page-9&active=%s&col=2&skeleton=1" % S1, True, True, True, True),
                                         ("/ws?app=chat&delta=1&iid=page-9&active=%s&col=2&reconnect=1&skeleton=1" % S1, True, True, False, True),
                                         ("/ws?app=feed&delta=1&iid=page-9&active=%s&skeleton=1" % S1, False, False, False, False)):   # a non-chat socket carrying the term arms nothing (PR 1661 round two; the follow-up's executed row)
            got = []
            real_reg, real_recv = km._register_ws_client, km._ws_recv
            km._register_ws_client = lambda c: (got.append(c), km._clients.append(c))
            km._ws_recv = lambda rfile: (0x8, b"", True)              # the peer closes at once
            km._pusher_wake.clear()
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    km.Handler._ws(_fake_self(path))
            finally:
                km._register_ws_client, km._ws_recv = real_reg, real_recv
                for c in got:
                    if c in km._clients:
                        km._clients.remove(c)
            self.assertEqual(len(got), 1, path)
            c = got[0]
            self.assertEqual(c.get("active"), S1)
            self.assertEqual(c.get("iid"), "page-9")
            self.assertTrue(c.get("delta"))
            if expect:
                self.assertIs(c.get("reconnect"), True, path)
                self.assertTrue(km._pusher_wake.is_set(), "the reconnect is the event; no backstop wait")
            else:
                self.assertIsNone(c.get("reconnect"), path)
                self.assertFalse(km._pusher_wake.is_set(), "a fresh page wakes nothing new")
            if view:
                self.assertEqual(c.get("col"), "2")
            if flag:
                self.assertIs(c.get("skeletonOnReady"), True, "a later chat column's first dial: the flag that survives the ready arm's reset")
            else:
                self.assertNotIn("skeletonOnReady", c, path + ": a redial (or no skeleton) arms no flag no arm would pop")
            if diet:
                self.assertIs(c.get("dietSkeleton"), True, path + ": a skeleton=1 chat dial marks the client dieted (durable), so a no-active resolve skeletons ALL its tabs")
            else:
                self.assertNotIn("dietSkeleton", c, path + ": no skeleton=1 (or a non-chat socket) marks no diet")

    # ── item 10 ──
    def test_10_source_pins_every_strip_sender_resolves_and_uses_the_one_builder(self):
        src = inspect.getsource(km)
        self.assertEqual(src.count('{"type": "tabOrder"'), 1,
                         "exactly one tabOrder literal in the kernel — inside _tab_order_frame, the builder that "
                         "carries the skeleton list; a hand-built frame would erase the set on the client")
        self.assertIn('{"type": "tabOrder"', inspect.getsource(km._tab_order_frame))
        for fn in (km._push, km._push_session_now, km._confirm_close_now):
            s = inspect.getsource(fn)
            self.assertIn("_resolve_reconnect(c, chat_list)", s, fn.__name__)
            self.assertIn("_send_tab_order(c, tab_order, tab_meta, live_map)", s, fn.__name__)
            self.assertLess(s.index("_resolve_reconnect(c, chat_list)"), s.index("_send_tab_order(c, tab_order, tab_meta, live_map)"),
                            fn.__name__ + ": resolve BEFORE the strip")
            self.assertIn("_consume_pending_reveal(c", s, fn.__name__ + ": a redial's first strip consumes a parked reveal")
            self.assertLess(s.index("_send_tab_order(c, tab_order, tab_meta, live_map)"), s.index("_consume_pending_reveal(c"),
                            fn.__name__ + ": the strip BEFORE the focus it names a tab of")
        i = src.find('msg.get("type") == "ready"')
        body = src[i:i + 2600]
        self.assertNotIn("_send_tab_order(client", body,
                         "the ready arm sends no strip of its own: its connect push (_push_one) resolves the flag and sends the strip")
        self.assertNotIn('client["send"](json.dumps({"type": "tabOrder"', src, "no strip bypasses the builder")
        i = src.find('msg.get("type") == "activeTab"')
        body = src[i:i + 700]
        self.assertIn('_release_skeleton(client, str(msg["id"]))', body)
        self.assertLess(body.index("_release_skeleton("), body.index("_pusher_wake.set()"),
                        "release, THEN wake — the woken cycle must see the released sid")
        s = inspect.getsource(km._send_chat_locked)
        self.assertIn("_release_skeleton_locked(c, sid)", s)
        self.assertLess(s.index("head_from = max(0, total - WIRE_TAIL)"), s.index("_release_skeleton_locked(c, sid)"),
                        "in the FULL branch — after the tail branch has returned")
        self.assertIn("_release_skeleton_locked(client, sid)", inspect.getsource(km._client_reset_chat_sid))
        s = inspect.getsource(km._client_reset_chat_base)
        for k in ('client.pop("skeleton", None)', 'client.pop("skeletonOrder", None)',
                  'client.pop("reconnect", None)', 'k[0] in ("chat", "status", "taborder", "activeChat")'):
            self.assertIn(k, s)
        s = inspect.getsource(km._push)
        self.assertIn("_send_chat_or_status(c, m, ms, change_from, led_changed)", s)
        self.assertNotIn("= _send_chat(c, m, ms, change_from, led_changed)", s,
                         "the pusher's per-client send goes through the skeleton-aware twin")
        self.assertIn('+((everConnected&&bundleReady&&readyAcked&&!readyQueued)?"&reconnect=1&proto="+readyProto:"")', km._shim("chat", 1),
                      "the shim declares the redial once the kernel's caps frame has answered its bundle's ready")
        self.assertIn('if(msg&&msg.type==="caps")readyAcked=true;', km._shim("chat", 1),
                      "the latch is the caps frame, the ready arm's reply (_send_caps)")
        s = inspect.getsource(km.Handler._ws)
        self.assertIn('reconnect = (q.get("reconnect") or [""])[0] == "1"', s)
        self.assertIn('client["reconnect"] = True', s)
        self.assertLess(s.index("_register_ws_client(client)"),
                        s.index('if client.get("reconnect"):\n            _pusher_wake.set()'),
                        "registered first, then woken — the pusher must find the client in _clients")

    def test_10b_a_close_confirmation_as_the_first_strip_already_carries_the_set(self):
        # the behavioral twin: the ≤1-cycle gap between the handshake and the pusher's first pass, filled by an
        # off-cycle strip — it must not paint the page's stale sessions as loaded tabs
        c = self._client(active=S1, reconnect=True)
        km._clients.append(c)
        self.assertTrue(km._confirm_close_now(GONE))
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1)
        self.assertEqual(to[0]["skeleton"], [S3, S2])
        self.assertEqual(c["skeleton"], {S2, S3})
        self.assertIsNone(c.get("reconnect"), "consumed by the confirmation, so the pusher's pass resolves nothing new")
        c["_frames"].clear()
        km._push([c])
        self.assertEqual(self._tab_orders(c), [], "the pusher's identical strip dedups")
        self.assertEqual(self._sessions(c), [S1, S4], "…and its fulls are exactly the reconnect set's complement")

    def test_10c_skeleton_for_ranks_by_size_skips_the_active_and_the_transcript_less(self):
        rows = km._chat_tab_sessions(0, {})
        self.assertEqual(km._skeleton_for({}, S1, rows), [S3, S2])
        self.assertEqual(km._skeleton_for({}, S3, rows), [S1, S2])
        self.assertEqual(km._skeleton_for({}, "gpu1:" + S1, rows), [S3, S1, S2],
                         "a remote/viewer/closed hint matches nothing: every local transcript is skeleton")
        self.assertEqual(km._skeleton_for({}, S1, rows + [{"sid": GONE, "path": None}]), [S3, S2],
                         "a path-less row is skipped, not a crash")

    # ── item 11 ──
    def test_11_every_touch_of_the_set_is_under_the_clients_slot_lock(self):
        src = inspect.getsource(km)
        lines = src.splitlines()

        def owners(token):
            """The defs whose bodies mention `token` (their own def line excluded)."""
            cur, found = None, set()
            for ln in lines:
                m = re.match(r"^\s*def (\w+)\(", ln)
                if m:
                    cur = m.group(1)
                    continue
                if token in ln:
                    found.add(cur)
            return found

        self.assertEqual(owners('"skeleton"') | owners('"skeletonOrder"'),
                         {"_client_reset_chat_base", "_release_skeleton_locked", "_resolve_reconnect",
                          "_held_as_skeleton_by_all",   # the cold-tab gate's reader (2026-09-14), under the lock
                          "_send_light_status",         # ...and its status send, membership re-checked under the lock (round three)
                          "_tab_order_frame", "_send_chat_or_status", "_send_tab_order",
                          # the two READERS of the connect query's skeleton=1 term (a later chat column's dial,
                          # 2026-09-11): _ws sets the client's `reconnect` and `skeletonOnReady` flags from it, and
                          # _shim writes the term; neither touches the client's set
                          "_ws", "_shim"},
                         "the set is touched only in its helpers — a new site must join this list AND take the lock")
        for name in ("_client_reset_chat_base", "_resolve_reconnect", "_send_chat_or_status", "_send_tab_order"):
            s = inspect.getsource(getattr(km, name))
            self.assertLess(s.index("with _client_lock("), s.index('"skeleton"'), name + ": the lock comes first")
        # the two lock-free helpers are reached only from bodies that hold the lock
        self.assertEqual(owners("_release_skeleton_locked("),
                         {"_release_skeleton", "_send_chat_locked", "_send_chat_proto2", "_client_reset_chat_sid"})   # _send_chat_proto2: reached from _send_chat_locked alone (T323 stage 4b)
        self.assertEqual(owners("_tab_order_frame("), {"_send_tab_order"})
        for name in ("_release_skeleton", "_client_reset_chat_sid", "_send_tab_order"):
            s = inspect.getsource(getattr(km, name))
            self.assertLess(s.index("with _client_lock("), s.index("_release_skeleton_locked(" if name != "_send_tab_order" else "_tab_order_frame("), name)
        self.assertEqual(owners("_send_chat_locked("), {"_send_chat", "_send_chat_or_status"},
                         "_send_chat_locked has no lock-free caller")
        for name in ("_send_chat", "_send_chat_or_status"):
            s = inspect.getsource(getattr(km, name))
            self.assertLess(s.index("with _client_lock("), s.index("_send_chat_locked("), name)

    # ── a later chat column: a skeleton client from its FIRST dial (the split, 2026-09-11) ──
    def test_11_a_skeleton_dial_survives_the_ready_reset(self):
        # The shell opens a later chat column as /chat?col=N&skeleton=1 with the column's state blob naming the session
        # it opens on, so the page's FIRST dial carries active=<sid>&skeleton=1 and _ws arms both flags (test_09). A
        # pusher cycle before the bundle's ready serves the strip (with the skeleton list) and the statuses into a
        # document that cannot hear it yet, and WITHHOLDS the session frames (review find 2026-09-11: the one full crossed
        # the wire twice per open); the ready arm's _client_reset_chat_base pops the set and `reconnect`, and the survivor
        # (`skeletonOnReady`) re-arms the flag for the connect push the page CAN hear — the same view, and THAT push's one
        # full is the only one. Until that ready the client is not stamped and a parked reveal stands: the arm's own stamp
        # and consume land it, as for any fresh page.
        km._PENDING_REVEAL[0] = None
        km._live_map = lambda: {S1: {}}       # the tapped session is live, so the reveal is a focus, not a revive
        try:
            trail = io.StringIO()
            with contextlib.redirect_stderr(trail):
                self.assertFalse(km._reveal_request(S1, "W1", via="sw"), "a tap for the window parks: no ready pane yet")
            c = self._client(active=S1, reconnect=True, skeletonOnReady=True, wid="W1")
            # 1. the pusher's cycle BEFORE the ready: the set, the strip, a status per other tab — no session frame (the
            #    document cannot hear it, and the ready arm re-sends the one full anyway), no stamp, no consume
            with contextlib.redirect_stderr(trail):
                km._push([c])
            self.assertEqual(c["skeleton"], {S2, S3})
            to = self._tab_orders(c)
            self.assertEqual(len(to), 1)
            self.assertEqual(to[0]["skeleton"], [S3, S2], "the strip carries the set, as a redial's does")
            self.assertEqual(self._sessions(c), [], "no session frame before the ready: the connect push the arm makes is the one full")
            self.assertEqual(sorted(s for s, _ in self._statuses(c)), sorted([S2, S3]), "a status per other tab")
            self.assertEqual(c.get("echat") or {}, {}, "…and nothing is believed held: the arm's push sends the full, not a delta")
            self.assertNotIn("ready", c, "a pre-ready pop stamps nothing: the page has no listener yet")
            self.assertEqual(km._PENDING_REVEAL[0], {"sid": S1, "wid": "W1"}, "…and consumes nothing: the park stands for the ready arm")
            self.assertEqual(self._frames(c, "focus"), [])
            self.assertIsNone(c.get("reconnect"), "the pop consumed the handshake's flag")
            self.assertIs(c.get("skeletonOnReady"), True, "the survivor is untouched by the pop")
            self.assertNotIn("the pane's redial", trail.getvalue(), "no strip stood in for a ready: this page posts one")
            # 2. the ready arm: the reset pops the set and the flag, the survivor re-arms it, the connect push serves the
            #    same view again, the arm stamps the client and the park lands behind the strip
            c["_frames"].clear()
            h = _Self(lambda cl: km._push([cl], connect=True))   # the real _push_one body
            with contextlib.redirect_stderr(trail):
                km.Handler._dispatch_ws(h, {"type": "ready"}, c)
            self.assertEqual(h.calls, [c])
            self.assertNotIn("skeletonOnReady", c, "popped once, by the arm")
            self.assertIsNone(c.get("reconnect"), "re-armed past the reset and consumed by the connect push's resolve")
            self.assertEqual(c["skeleton"], {S2, S3}, "the set is back: the connect push served the view, not the board")
            to = self._tab_orders(c)
            self.assertEqual(len(to), 1, "the reset cleared the strip's slot, so the strip went again")
            self.assertEqual(to[0]["skeleton"], [S3, S2])
            self.assertEqual(self._sessions(c), [S1, S4], "the one full (+ the transcript-less), from this push alone")
            self.assertEqual(sorted(s for s, _ in self._statuses(c)), sorted([S2, S3]))
            self.assertIs(c.get("ready"), True)
            self.assertIsNone(km._PENDING_REVEAL[0], "the park was consumed at the ready")
            types = [f["type"] for f in c["_frames"]]
            self.assertEqual(types.count("focus"), 1, "one focus")
            self.assertLess(types.index("tabOrder"), types.index("focus"), "behind the strip that names its tab")
            self.assertEqual([(f["id"], f["live"]) for f in self._frames(c, "focus")], [(S1, True)])
            self.assertRegex(trail.getvalue(), r"\[reveal\] sw sid=\S+ wid=W1: parked[\s\S]*\[reveal\] sid=\S+ wid=W1: consumed")
            # 3. the next cycle: an ordinary skeleton client from here (test_02's regime), nothing parked
            c["_frames"].clear()
            with contextlib.redirect_stderr(trail):
                km._push([c])
            self.assertEqual(self._sessions(c), [], "no full for a skeleton sid, and the active is held")
            self.assertEqual(self._frames(c, "focus"), [])
        finally:
            km._PENDING_REVEAL[0] = None

    def test_11_d_a_pusher_iteration_landing_in_the_ready_arms_gap_sends_no_full(self):
        # THE SECOND FULL ON A NEW COLUMN'S SOCKET (a slow runner, 2026-09-12; reproduced at the wire: 18 of 27 opens carried
        # full frames for sessions the column does not hold, up to six per open, and the page asked for none). The pusher
        # cycle the handshake woke is still in its per-session loop when the ready arm runs. The arm's reset pops the set
        # and `reconnect`, the survivor re-arms `reconnect`, and the arm's connect push rebuilds the set only at its own
        # _resolve_reconnect, past a liveness sweep and the tab list. In that gap the client had no set and no
        # `skeletonOnReady`, and _send_chat_or_status read nothing else: every session the pusher's loop visited fell
        # through to _send_chat_locked, a full for a tab the column holds as a skeleton, an echat entry, and the arm's
        # strip dropped the sid from its skeleton list as held whole. The guard reads `reconnect` too now (a client with
        # the flag armed has no set yet; the strip sender that pops it sends the active tab's full itself), and the reset
        # pops the survivor and re-arms under its own lock, so no instant exists with neither flag set.
        def in_the_gap(cl, sid):
            """The pusher's per-session iteration for `sid`, landing on the handler thread's _push_one: the instant after
            the arm's reset and re-arm, before its push's _resolve_reconnect."""
            self.assertNotIn("skeleton", cl, "the reset popped the set")
            self.assertNotIn("skeletonOnReady", cl, "…and the survivor")
            self.assertIs(cl.get("reconnect"), True, "…and re-armed the flag for the connect push")
            m = json.loads(json.dumps(self.SESS[sid]))
            km._send_chat_or_status(cl, m, None, len(m["events"]), False)
        # 1. the loop reaches a session the column does NOT hold (the wire shape: every extra full was another tab's)
        c = self._client(active=S1, reconnect=True, skeletonOnReady=True)
        km._push([c])                                 # the pre-ready cycle: the set, the strip, a status per other tab
        self.assertEqual(self._sessions(c), [])
        c["_frames"].clear()
        h = _Self(lambda cl: (in_the_gap(cl, S2), km._push([cl], connect=True)))
        with contextlib.redirect_stderr(io.StringIO()):
            km.Handler._dispatch_ws(h, {"type": "ready"}, c)
        self.assertEqual(h.calls, [c])
        self.assertEqual(self._sessions(c), [S1, S4], "the one full (+ the transcript-less): the pusher's iteration for S2 in the gap sent none")
        self.assertEqual(sorted(s for s, _ in self._statuses(c)), sorted([S2, S3]), "S2 is a status, as every other tab")
        to = self._tab_orders(c)
        self.assertEqual(len(to), 1)
        self.assertEqual(to[0]["skeleton"], [S3, S2], "S2 is still on the strip's skeleton list: no full won a race against the set")
        self.assertEqual(c["skeleton"], {S2, S3})
        self.assertEqual(sorted(c["echat"]), sorted([S1, S4]), "believed held: the active tab and the transcript-less, nothing else")
        types = [f["type"] for f in c["_frames"]]
        self.assertLess(types.index("tabOrder"), types.index("session"), "the strip is ahead of every full: the set's invariant")
        # 2. the loop reaches the ACTIVE session in the gap: its full crosses once, from the arm's push, behind the strip
        c = self._client(active=S1, reconnect=True, skeletonOnReady=True)
        km._push([c])
        c["_frames"].clear()
        h = _Self(lambda cl: (in_the_gap(cl, S1), km._push([cl], connect=True)))
        with contextlib.redirect_stderr(io.StringIO()):
            km.Handler._dispatch_ws(h, {"type": "ready"}, c)
        self.assertEqual([f["type"] for f in c["_frames"] if f.get("id") == S1 and f["type"] in ("session", "chatTail")], ["session"],
                         "one full for the active tab and no tail behind it: the iteration in the gap neither sent it nor left a base")
        self.assertEqual(self._sessions(c), [S1, S4])
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S3, S2])
        types = [f["type"] for f in c["_frames"]]
        self.assertLess(types.index("tabOrder"), types.index("session"))
        # 3. the withheld road under the baseline seed (2026-09-21): an attach handshake's targeted push reaches the pre-ready
        # column BEFORE the pusher's first cycle does (27 of them at a boot). Its set resolves here, unstamped, the strip and
        # the statuses go, and the watched tab's session frame is withheld until the ready; the seed ran all the same and
        # wrote a baseline no client holds. The frame nobody took seeds nothing; the ready arm's connect push, the one full,
        # seeds it. Parts 1 and 2 ran cycles, whose write-after-deliver is the baseline's designed advance and not the seed,
        # so their entries are cleared: this socket dials before any cycle has written.
        km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        c = self._client(active=S1, reconnect=True, skeletonOnReady=True)
        km._clients.append(c)
        km._push_session_now(S1)                      # the handshake, before the cycle
        self.assertEqual(c["skeleton"], {S2, S3}, "the set resolved at the handshake push")
        self.assertIs(c.get("skeletonOnReady"), True, "...and the client is still before its ready")
        self.assertEqual(self._sessions(c), [], "the watched tab's frame is withheld until the ready")
        self.assertEqual(dict(km._prev_chat_events), {},
                         "a frame no client took seeds nothing; the map holds %r"
                         % ({sid[-1]: len(evs) for sid, evs in km._prev_chat_events.items()},))
        c["_frames"].clear()
        h = _Self(lambda cl: km._push([cl], connect=True))
        with contextlib.redirect_stderr(io.StringIO()):
            km.Handler._dispatch_ws(h, {"type": "ready"}, c)
        self.assertEqual(self._sessions(c), [S1, S4], "the ready arm's push delivers the watched tab whole (and the transcript-less)")
        self.assertEqual(km._prev_chat_events.get(S1), self.SESS[S1]["events"], "...and that delivery is what seeds the sid")
        self.assertEqual(sorted(km._prev_chat_events), [S1], "the skeleton tabs, status frames again, seed nothing")
        # the source: the iteration reads `reconnect` beside `skeletonOnReady`; the reset re-arms under its lock, right
        # behind the pop, and the arm no longer pops or re-arms on its own (two statements outside the lock were the instant)
        so = inspect.getsource(km._send_chat_or_status)
        self.assertIn('if c.get("skeletonOnReady") or c.get("reconnect"):', so)
        rs = inspect.getsource(km._client_reset_chat_base)
        self.assertLess(rs.index("with _client_lock(client):"), rs.index('client.pop("reconnect", None)'))
        self.assertLess(rs.index('client.pop("reconnect", None)'),
                        rs.index('if client.pop("skeletonOnReady", False):\n            client["reconnect"] = True'))
        arm = inspect.getsource(km.Handler)
        body = arm[arm.index('msg.get("type") == "ready"'):][:3500]
        self.assertNotIn('client.pop("skeletonOnReady"', body)

    def test_11_c_a_later_columns_redial_is_stamped_by_its_first_strip_and_lands_a_parked_reveal(self):
        # The shim reads skeleton=1 off the address on EVERY dial of a later column, so its redial after a kernel restart
        # or a laptop sleep carries reconnect=1 AND skeleton=1. Armed with `skeletonOnReady`, that client was never stamped:
        # its page said ready on an earlier socket, no arm ever popped the flag, and _resolve_reconnect's fresh guard held
        # for the page's life — no reveal aimed at it, a parked one never consumed (review find 2026-09-11). _ws arms
        # `reconnect` alone for it (test_09's fourth dial), and the redial is served like any redial (test_12): the first
        # strip stamps the client, still carries the skeleton list, and the park lands behind it.
        km._PENDING_REVEAL[0] = None
        km._live_map = lambda: {S1: {}}       # the tapped session is live, so the reveal is a focus, not a revive
        got = []
        real_reg, real_recv = km._register_ws_client, km._ws_recv
        km._register_ws_client = lambda cl: got.append(cl)
        km._ws_recv = lambda rfile: (0x8, b"", True)              # the peer closes at once
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                km.Handler._ws(_fake_self("/ws?app=chat&delta=1&iid=page-11c&wid=W1&active=%s&col=2&reconnect=1&skeleton=1" % S1))
        finally:
            km._register_ws_client, km._ws_recv = real_reg, real_recv
        self.assertEqual(len(got), 1)
        armed = {k: got[0][k] for k in ("reconnect", "skeletonOnReady") if k in got[0]}   # exactly what the real handshake armed
        self.assertEqual(armed, {"reconnect": True}, "a redial of a later column: the redial flag alone")
        try:
            trail = io.StringIO()
            with contextlib.redirect_stderr(trail):
                self.assertFalse(km._reveal_request(S1, "W1", via="sw"), "no stamped pane for the window: parked")
            c = self._client(active=S1, wid="W1", **armed)
            with contextlib.redirect_stderr(trail):
                km._push([c])
            self.assertIs(c.get("ready"), True, "the redial's first strip stamps the client, as for any redial")
            self.assertIsNone(km._PENDING_REVEAL[0], "the park was consumed")
            self.assertIsNone(c.get("reconnect"))
            self.assertNotIn("skeletonOnReady", c)
            types = [f["type"] for f in c["_frames"]]
            self.assertEqual(types.count("focus"), 1, "one focus: the parked tap")
            self.assertLess(types.index("tabOrder"), types.index("focus"), "behind the strip that names its tab")
            self.assertEqual([(f["id"], f["live"]) for f in self._frames(c, "focus")], [(S1, True)])
            self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S3, S2], "still a skeleton client of the session it opened on")
            self.assertEqual(self._sessions(c), [S1, S4], "one full (+ the transcript-less): the diet, not the board, and not withheld — this page listens")
            self.assertRegex(trail.getvalue(), REDIAL_TRAIL % "sw", "the journal says the redial landed the park")
            # …and a tap that arrives now is aimed at it directly (stamped), never parked
            km._clients.append(c)
            c["_frames"].clear()
            with contextlib.redirect_stderr(trail):
                self.assertTrue(km._reveal_request(S1, "W1", via="sw"), "a stamped client for the window takes the tap")
            self.assertEqual([f["type"] for f in c["_frames"]], ["focus"])
            self.assertIsNone(km._PENDING_REVEAL[0])
        finally:
            km._PENDING_REVEAL[0] = None

    def test_11_b_a_relay_skeleton_dial_with_no_active_diets_all_its_tabs_through_the_cycle_and_ready(self):
        # LOW (2026-09-15, the federated dial), the full flow that pins the ready arm's reset ORDER: a RELAY fresh
        # skeleton dial (kind relay, skeletonOnReady) with NO active hint diets every transcript-bearing tab. Before
        # the ready the strip lists all of them as skeletons with a status each and NO full (the pre-ready gate holds
        # the fulls for the arm's push); at the ready _client_reset_chat_base pops the set and re-arms from
        # skeletonOnReady, the durable dietSkeleton survives, and the connect push rebuilds the SAME all-tabs set, so a
        # skeletoned tab is never sent full. A LOCAL page in the same state keeps the whole push (test_11_e).
        c = self._client(kind="relay", reconnect=True, skeletonOnReady=True, dietSkeleton=True)   # no active
        km._push([c])
        self.assertEqual(self._sessions(c), [], "no full before the ready (the arm's push serves the diet)")
        self.assertEqual(self._tab_orders(c)[0].get("skeleton"), [S3, S1, S2], "the strip lists every transcript-bearing tab as a skeleton")
        self.assertEqual(sorted(c.get("skeleton") or []), sorted([S1, S2, S3]))
        self.assertNotIn("ready", c, "a pre-ready pop stamps nothing")
        self.assertIsNone(c.get("reconnect"))
        c["_frames"].clear()
        h = _Self(lambda cl: km._push([cl], connect=True))
        with contextlib.redirect_stderr(io.StringIO()):
            km.Handler._dispatch_ws(h, {"type": "ready"}, c)
        self.assertNotIn("skeletonOnReady", c)
        self.assertEqual(sorted(c.get("skeleton") or []), sorted([S1, S2, S3]), "the all-tabs set survives the ready reset")
        for sid in (S1, S2, S3):
            self.assertNotIn(sid, self._sessions(c), "a skeletoned tab is never sent full, even at the ready")
        self.assertIs(c.get("ready"), True)

    def test_11_e_the_no_active_diet_is_scoped_to_relay_clients(self):
        # the resolve's no-active diet builds the all-tabs set ONLY for a RELAY client (the hub pane through the
        # splice); a LOCAL page (kind page) that dialed the diet with no active, and a plain reconnect, both keep the
        # fail-safe whole push; a local page's page-side recovery is not browser-proven yet (the follow-up).
        rows = km._chat_tab_sessions(0, {})
        relay = {"app": "chat", "kind": "relay", "reconnect": True, "dietSkeleton": True}
        self.assertTrue(km._resolve_reconnect(relay, rows))
        self.assertEqual(relay.get("skeletonOrder"), [S3, S1, S2], "every transcript-bearing tab a skeleton, cheapest first")
        self.assertNotIn(S4, relay.get("skeleton") or set(), "the transcript-less tab is built whole")
        local = {"app": "chat", "kind": "page", "reconnect": True, "dietSkeleton": True}
        self.assertTrue(km._resolve_reconnect(local, rows))
        self.assertIsNone(local.get("skeleton"), "a LOCAL diet page with no active is served whole (pending the follow-up)")
        plain = {"app": "chat", "kind": "relay", "reconnect": True}   # relay but did NOT diet
        self.assertTrue(km._resolve_reconnect(plain, rows))
        self.assertIsNone(plain.get("skeleton"), "a non-diet reconnect with no active is served whole")
        # FOLD 2, the cold-tab gate on an UNRESOLVED diet client (reconnect armed, no set yet): a relay diet client
        # with no active is read as holding EVERY tab as a skeleton, so the per-session route builds none it will
        # skeleton (cost only); a local diet page holds nothing (whole push).
        relay_unresolved = {"app": "chat", "kind": "relay", "reconnect": True, "dietSkeleton": True}
        self.assertTrue(km._held_as_skeleton_by_all(S1, [relay_unresolved]), "an unresolved relay diet client with no active holds every tab as a skeleton")
        local_unresolved = {"app": "chat", "kind": "page", "reconnect": True, "dietSkeleton": True}
        self.assertFalse(km._held_as_skeleton_by_all(S1, [local_unresolved]), "a local unresolved diet page holds nothing")

    # ── item 12 ──
    def test_12_a_reveal_parked_while_the_page_had_no_socket_lands_behind_the_redials_first_strip(self):
        # A push tap (or a deep link, or a vanished notification) reached the kernel while the page's socket was
        # dead: /reveal found no ready chat pane for the window and parked. The page redials with ?reconnect=1 and
        # its bundle, which posted ready once, never posts another, so no ready arm runs for the new socket. The
        # pusher's first strip for the redial is the event that stands in: it stamps the client, sends the strip,
        # then delivers the parked focus, so the focus names a tab the strip has already listed.
        km._PENDING_REVEAL[0] = None
        km._live_map = lambda: {S1: {}}       # the tapped session is live, so the reveal is a focus, not a revive
        try:
            trail = io.StringIO()
            with contextlib.redirect_stderr(trail):
                self.assertFalse(km._reveal_request(S1, "W1", via="vanish"), "no socket for the window: parked")
                self.assertEqual(km._PENDING_REVEAL[0], {"sid": S1, "wid": "W1"})
                c = self._client(active=S1, reconnect=True, wid="W1")
                km._push([c])
            self.assertIs(c.get("ready"), True, "the redial's first strip stamps the client as the ready arm would")
            self.assertIsNone(km._PENDING_REVEAL[0], "the park was consumed")
            types = [f["type"] for f in c["_frames"]]
            self.assertIn("focus", types, "the parked focus landed on the redialed socket")
            self.assertLess(types.index("tabOrder"), types.index("focus"), "behind the strip that names its tab")
            self.assertLess(types.index("focus"), types.index("session"), "and ahead of the cycle's session frames")
            focus = self._frames(c, "focus")
            self.assertEqual(len(focus), 1)
            self.assertEqual((focus[0]["id"], focus[0]["live"]), (S1, True))
            self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S3, S2], "the redial is still served as a skeleton set")
            self.assertRegex(trail.getvalue(), REDIAL_TRAIL % "vanish", "the journal says which event landed the park")
            # the next cycle consumes nothing: the flag is gone, and there is nothing parked
            c["_frames"].clear()
            with contextlib.redirect_stderr(io.StringIO()):
                km._push([c])
            self.assertEqual(self._frames(c, "focus"), [])
            # a fresh page (no redial) with a park for its window is left to its own ready, as before
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(km._reveal_request(S1, "W2", via="sw"))
                fresh = self._client(active=S1, wid="W2")
                km._push([fresh])
            self.assertEqual(self._frames(fresh, "focus"), [], "no redial: the strip consumes nothing")
            self.assertNotIn("ready", fresh)
            self.assertEqual(km._PENDING_REVEAL[0], {"sid": S1, "wid": "W2"}, "the park stands for the ready arm")
        finally:
            km._PENDING_REVEAL[0] = None

    def _park_for_a_redialing_page(self, via):
        """A tap parked while the window had no socket, then the page's redial registered at its handshake:
        the client is in _clients with the flag and no stamp, exactly as _ws leaves it before any strip."""
        km._PENDING_REVEAL[0] = None
        km._live_map = lambda: {S1: {}}       # the tapped session is live, so the reveal is a focus, not a revive
        trail = io.StringIO()
        with contextlib.redirect_stderr(trail):
            self.assertFalse(km._reveal_request(S1, "W1", via=via), "no socket for the window: parked")
        c = self._client(active=S1, reconnect=True, wid="W1")
        km._clients.append(c)
        return c, trail

    def _assert_landed_behind_the_first_strip(self, c, trail, via):
        self.assertIs(c.get("ready"), True, "stamped by the strip sender that popped the flag")
        self.assertIsNone(c.get("reconnect"))
        self.assertIsNone(km._PENDING_REVEAL[0], "the park was consumed")
        types = [f["type"] for f in c["_frames"]]
        self.assertIn("focus", types)
        self.assertLess(types.index("tabOrder"), types.index("focus"), "behind the strip that names its tab")
        self.assertEqual([(f["id"], f["live"]) for f in self._frames(c, "focus")], [(S1, True)])
        self.assertEqual(self._tab_orders(c)[0]["skeleton"], [S3, S2], "the strip is still the redial's skeleton strip")
        self.assertRegex(trail.getvalue(), REDIAL_TRAIL % via)

    def test_12b_a_close_confirmation_as_the_redials_first_strip_lands_the_park_too(self):
        # the off-cycle sender that can be the FIRST strip a redialing page sees (test_10b): it stamps and consumes
        # like the pusher's pass does, so a park does not wait for the next cycle
        c, trail = self._park_for_a_redialing_page("sw")
        try:
            with contextlib.redirect_stderr(trail):
                self.assertTrue(km._confirm_close_now(GONE))
            self._assert_landed_behind_the_first_strip(c, trail, "sw")
        finally:
            km._PENDING_REVEAL[0] = None

    def test_12c_a_session_push_as_the_redials_first_strip_lands_the_park_too(self):
        # the other off-cycle sender (a create or a handshake for one tab, test_05), as the redial's first strip
        c, trail = self._park_for_a_redialing_page("link")
        try:
            with contextlib.redirect_stderr(trail):
                km._push_session_now(S3)
            self._assert_landed_behind_the_first_strip(c, trail, "link")
            self.assertEqual(self._sessions(c), [], "no full follows for a tab the redialed page holds as a skeleton")
            self.assertEqual(self._statuses(c), [(S3, {"state": "waiting", "sinceEpoch": None})], "its status does")
        finally:
            km._PENDING_REVEAL[0] = None

    def test_12d_the_ready_arm_over_a_still_flagged_client_lands_the_park_once_as_the_ready(self):
        # the arm's path and the strip's cannot both land one park: _client_reset_chat_base pops the flag before the
        # connect push, so that push's strip resolves nothing, and the arm's own consume (after the push) is the one;
        # the journal names the ready, not the redial, and there is one focus (green before and after the change)
        c, trail = self._park_for_a_redialing_page("sw")
        try:
            h = _Self(lambda cl: km._push([cl], connect=True))   # the real _push_one body
            with contextlib.redirect_stderr(trail):
                km.Handler._dispatch_ws(h, {"type": "ready"}, c)
            self.assertEqual(h.calls, [c])
            self.assertIs(c.get("ready"), True)
            self.assertIsNone(km._PENDING_REVEAL[0])
            for k in ("skeleton", "skeletonOrder", "reconnect"):
                self.assertNotIn(k, c, k)
            types = [f["type"] for f in c["_frames"]]
            self.assertEqual(types.count("focus"), 1, "one focus: the arm's")
            self.assertLess(types.index("tabOrder"), types.index("focus"))
            self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER), "the arm's push is every full, no set")
            self.assertRegex(trail.getvalue(), r"consumed \S+ the pane's ready")
            self.assertNotIn("the pane's redial", trail.getvalue(), "the strip inside the arm's push resolved no flag")
        finally:
            km._PENDING_REVEAL[0] = None



    # ── the targeted push serves each client from the base it holds (2026-09-19) ──
    def _targeted_sends(self):
        """(fulls, deltas) the targeted road has sent so far, from /perf's sends map: its frames read apart from the pusher's."""
        snap = km._PERF_STATS.snapshot()["sends"]
        return tuple((snap[k].get("chat.targeted") or {}).get("count", 0) for k in ("full", "delta"))

    def test_13_a_caught_up_client_gets_no_full_from_the_per_session_push(self):
        # Every targeted push (the SDK connect handshake, the Codex backend's stream events, a create, a fork) used to
        # send EVERY client a full {type:"session"} (change_from forced to 0), which a page holding the tab whole treats
        # as a reconnect repair: the window rebuilt and the reader's place re-derived, some 450 times a day live. It
        # goes through the pusher's per-client road now: a caught-up client gets a chatTail, empty when nothing changed
        # against the shared baseline, and a client with no base still gets the full it needs.
        c = self._client(active=S1, proto=2)
        km._clients.append(c)
        km._push([c])                                    # the cycle: every tab whole, the baseline advanced
        self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER))
        baseline = list(km._prev_chat_events[S1])
        sends0 = self._targeted_sends()
        c["_frames"].clear()
        km._push_session_now(S1)                         # the handshake (or any targeted) push for a tab it holds whole
        # (the no-full assertion is green on the unchanged kernel too, whose identical full was deduped on the slot; the
        # empty-suffix tail asserted right after it is the first red one, that kernel having no tail road for this push;
        # the status flip below is the user-visible symptom: a whole session frame as soon as anything differed)
        self.assertEqual(self._sessions(c), [], "a client that holds the tab whole gets no full frame")
        self.assertEqual([(t["id"], t["afterUuid"], t["events"]) for t in self._frames(c, "chatTail")], [(S1, "u4", [])],
                         "one empty-suffix tail: nothing changed against the baseline")
        self.assertNotIn("ledger", self._frames(c, "chatTail")[0], "a ledger unchanged against the shared baseline does not ride the tail")
        self.assertIsNone(getattr(km._SEND_ROAD, "name", None),
                          "the road mark is reset when the push returns (2026-09-19 review: the dispatch thread runs other pushes)")
        # the flip the push exists for still lands: the status rides the tail, and so does a ledger that changed against the
        # baseline (the 2026-09-19 review: led_changed forced either way left every module driving this push green). The
        # targeted push never advances that baseline, so changed means changed against the map the pusher's cycle left
        self.SESS[S1]["status"]["state"] = "waiting"
        self.SESS[S1]["ledger"] = {"toc": ["judged"]}
        c["_frames"].clear()
        km._push_session_now(S1)
        self.assertEqual(self._sessions(c), [], "a status change is a tail, not a full")
        tails = self._frames(c, "chatTail")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"], t.get("ledger")) for t in tails],
                         [("u4", [], "waiting", {"toc": ["judged"]})], "the tail carries the changed ledger")
        # new content arrives as the suffix after what it holds
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})
        c["_frames"].clear()
        km._push_session_now(S1)
        self.assertEqual(self._sessions(c), [])
        tails = self._frames(c, "chatTail")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in tails], [("u4", ["u5"])])
        # a change below its last (a tool fill) re-sends from the change
        self.SESS[S1]["events"][3]["md"] = "m3 filled"
        c["_frames"].clear()
        km._push_session_now(S1)
        self.assertEqual(self._sessions(c), [])
        tails = self._frames(c, "chatTail")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in tails], [("u2", ["u3", "u4", "u5"])])
        # a client with no base still gets the full it needs; the shared baseline is left alone throughout
        fresh = self._client(active=S1, proto=2)
        km._clients.append(fresh)
        km._push_session_now(S1)
        self.assertEqual(self._sessions(fresh), [S1])
        self.assertEqual(self._frames(fresh, "chatTail"), [])
        self.assertEqual(km._prev_chat_events[S1], baseline, "only a push that reaches every client advances the baseline")
        # /perf reads this road's frames apart from the pusher's: the four tails and the one full above
        fulls, deltas = self._targeted_sends()
        self.assertEqual((fulls - sends0[0], deltas - sends0[1]), (1, 4), "sends.<kind>.chat.targeted counts the targeted road")

    def test_14_a_skeleton_holder_gets_its_status_only_and_stays_a_skeleton(self):
        c = self._client(active=S1, reconnect=True, proto=2)
        km._push([c])                                    # the redial's set resolves: S3 and S2 are skeletons
        self.assertEqual(c["skeleton"], {S2, S3})
        km._clients.append(c)
        b = self._client(active=S3, proto=2)             # another page holds S3 whole
        km._clients.append(b)
        km._push([b])
        self.SESS[S3]["status"]["state"] = "working"     # the flip
        c["_frames"].clear(); b["_frames"].clear()
        km._push_session_now(S3)
        self.assertEqual(self._sessions(c), [], "no full for a tab the page holds as a skeleton")
        self.assertEqual(self._statuses(c), [(S3, {"state": "working", "sinceEpoch": None})])
        self.assertEqual(c["skeleton"], {S2, S3}, "still a skeleton: the click or the prefetch releases it")
        self.assertNotIn(("chat", S3), c["sent"])
        self.assertEqual(self._sessions(b), [], "the page holding it whole gets no full either")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(b, "chatTail")],
                         [("u2", [], "working")])

    def test_15_a_targeted_push_landing_mid_cycle_anchors_no_tail_past_what_a_client_holds(self):
        # The pusher wrote the shared baseline BEFORE serving its clients, and the targeted push reads that baseline on
        # another thread (the Codex pump, the SDK handshake) with nothing ordering the two. Landing in the write-to-send
        # gap, the push diffed its build against an equal baseline and anchored an EMPTY tail at the list's last event,
        # one the racing client did not hold yet; the page reads a tail past what it holds as a gap and asks for a full,
        # the very frame the routing removed (review find, 2026-09-19). Two rules close it: the baseline advances only
        # AFTER the cycle's sends, so a push in the gap reads the older one and re-sends the overlap (both wires); and
        # the proto-2 no-change tail anchors at the client's held last, not the list's (test_16, the sender's side).
        c = self._client(active=S1, proto=2)                 # the uuid-anchored wire
        d = self._client(active=S1)                          # the index wire
        km._clients.extend([c, d])
        km._push([c, d])                                     # the cycle: both hold u0..u4 whole; the baseline is u0..u4
        self.assertEqual(sorted(self._sessions(c)), sorted(TAB_ORDER))
        self.assertEqual(sorted(self._sessions(d)), sorted(TAB_ORDER))
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})   # grown since the baseline
        km._built_chat.clear()                               # the next cycle rebuilds and sees the growth
        c["_frames"].clear(); d["_frames"].clear()
        real = km._send_chat_or_status
        fired = []

        def racing(cl, m, ms, change_from, led_changed):
            """The cycle's first per-client send for S1: the targeted push lands on its own thread right here, after the
            cycle computed its diff and (before the change) wrote the baseline, before it served anyone."""
            if m["id"] == S1 and not fired:
                fired.append(1)
                km._push_session_now(S1)
            return real(cl, m, ms, change_from, led_changed)
        km._send_chat_or_status = racing
        try:
            km._push([c, d])
        finally:
            km._send_chat_or_status = real
        self.assertEqual(fired, [1], "the targeted push ran inside the cycle's per-client loop")
        held = {"u0", "u1", "u2", "u3", "u4"}
        for cl in (c, d):
            self.assertEqual(self._sessions(cl), [], "no full: nothing asked for a repair")
        tails = [t for t in self._frames(c, "chatTail") if t["id"] == S1]   # the other tabs' empty-suffix tails are the rebuild's, not this race's
        self.assertTrue(tails, "the proto-2 client was served")
        for t in tails:
            self.assertIn(t["afterUuid"], held, "a tail anchored at an event the client does not hold is a gap ask: %r" % t["afterUuid"])
            self.assertEqual([e["uuid"] for e in t["events"]], ["u5"], "the missing event, from the anchor it holds")
        tails = [t for t in self._frames(d, "chatTail") if t["id"] == S1]
        self.assertTrue(tails, "the index client was served")
        for t in tails:
            self.assertLessEqual(t["from"], len(held), "a tail from past what the client holds is a gap ask: from %r" % t["from"])
            self.assertEqual([e["uuid"] for e in t["events"]], ["u5"])

    def test_16_the_no_change_tail_anchors_at_the_clients_held_last_not_the_lists(self):
        # The proto-2 no-change branch (nothing moved against the baseline) anchored its empty tail at the LIST's last
        # event. A client behind that list, the cycle that advanced the baseline not having reached it yet (test_15's
        # race seen from the sender's side), received a tail anchored past what it holds: a gap ask, then a full. It is
        # anchored at the client's held last now and carries the events the client lacks (2026-09-19).
        c = self._client(active=S1, proto=2)
        km._clients.append(c)
        km._push([c])                                        # holds u0..u4
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})
        km._prev_chat_events[S1] = json.loads(json.dumps(self.SESS[S1]["events"]))   # a baseline one event AHEAD of the client, by hand
        c["_frames"].clear()
        km._push_session_now(S1)
        self.assertEqual(self._sessions(c), [])
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(c, "chatTail")], [("u4", ["u5"])],
                         "anchored at ITS held last and carrying the missing event, not an empty tail anchored past it")

    def test_17_a_client_armed_for_the_ready_arms_connect_push_gets_no_session_frame_from_the_targeted_push(self):
        # A later chat column before its bundle's ready (skeletonOnReady armed, the split 2026-09-11): the pusher's loop
        # withholds its session frames and the ready arm's connect push is the one full (test_11_d). The targeted push
        # bypassed that guard and handed it a full it could not hear; through the pusher's road it gets the strip and
        # nothing else here. Pinned for this road too (review find, 2026-09-19): the guard had owners for the pusher's loop only.
        c = self._client(active=S1, skeletonOnReady=True)
        km._clients.append(c)
        km._push_session_now(S3)
        self.assertEqual(len(self._tab_orders(c)), 1, "the strip goes: cheap, and heard once the bundle wins the race")
        self.assertEqual(self._sessions(c), [], "no session frame: the ready arm's connect push is the one full")
        self.assertEqual(self._statuses(c), [], "and no status for it: the client holds no set yet")
        self.assertNotIn(("chat", S3), c["sent"])
        self.assertNotIn(("status", S3), c["sent"])

    # ── the startup baseline (2026-09-19): a sid's first whole frame establishes the shared baseline, never advances it ──
    def _why(self):
        """The proto-2 full frames' reason map on /perf (pusher.chatFullWhy), as the collector holds it now."""
        return km._PERF_STATS.snapshot()["pusher"]["chatFullWhy"]

    @staticmethod
    def _u3(c):
        """(frame type, u3's text) for every S1 frame that carried the u3 card, in arrival order: which build of that
        card the client holds is the last entry."""
        out = []
        for f in c["_frames"]:
            if f.get("id") != S1:
                continue
            for e in f.get("events") or []:
                if e.get("uuid") == "u3":
                    out.append((f["type"], e["md"]))
        return out

    @staticmethod
    def _card(c, sid, uuid):
        """(frame type, the card's text) for every `sid` frame that carried the `uuid` card, in arrival order: the _u3
        shape for any session and card (tests 31 and 32)."""
        out = []
        for f in c["_frames"]:
            if f.get("id") != sid:
                continue
            for e in f.get("events") or []:
                if e.get("uuid") == uuid:
                    out.append((f["type"], e["md"]))
        return out

    def _strip_without(self, sid, fn):
        """Run fn with `sid` dropped from the tab strip (the session ended or was hidden): the test_00b shape."""
        orig = km._chat_tab_sessions
        km._chat_tab_sessions = lambda now, live_map: [s for s in orig(now, live_map) if s["sid"] != sid]
        try:
            fn()
        finally:
            km._chat_tab_sessions = orig

    def test_18_a_connect_push_seeds_the_baseline_so_the_targeted_push_and_the_first_cycle_send_tails_not_fulls(self):
        # The shared baseline (_prev_chat_events) had ONE writer, the pusher's non-connect cycle, so a sid whose first
        # whole frame since the boot came from a connect push (the redial's watched tab, then every tab the page's idle
        # prefetch releases) left its clients holding a base and the kernel holding no baseline. _chat_diff reads 0 with
        # none, and 0 against a held base is the full road: every targeted push for the sid (the SDK handshake, a Codex
        # stream event) and the cycle's own first build re-sent the whole session, counted changeAt0 and filed as a
        # chatFull row with both edges held, a repaint the page treats as a reconnect repair (42 of them in the three
        # minutes after a restart with 22 sessions and a dashboard, none after; 2026-09-19). The first whole frame now
        # seeds the baseline when none exists, whichever sender sent it; the cycle's write-after-deliver advance stands.
        # Each step flips the status first: an identical frame would dedup on its slot and hide the full (the review).
        km._PERF_STATS.reset()
        c = self._client(active=S1, proto=2)
        km._clients.append(c)
        km._push([c], connect=True)                      # the ready arm's connect push: every tab whole, noBase
        self.assertEqual(km._prev_chat_events.get(S1), self.SESS[S1]["events"],
                         "the first whole frame establishes the baseline (the connect push wrote none before)")
        self.assertNotIn(S4, km._prev_chat_events, "an empty list records no baseline, as it records no base")
        self.assertEqual(self._diag_rows("chatFull"), [], "a fresh client holds no base: nothing filed")
        c["_frames"].clear()
        self.SESS[S1]["status"]["state"] = "waiting"     # the flip the handshake push exists for
        km._push_session_now(S1)                         # the handshake
        self.assertEqual(self._sessions(c), [], "the handshake push sends a tail, not a whole session frame")
        self.assertEqual([(t["id"], t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(c, "chatTail")],
                         [(S1, "u4", [], "waiting")], "the empty-suffix tail carries the flip")
        self.assertNotIn("changeAt0", self._why(), "no full counted against the seeded baseline")
        self.assertEqual(self._diag_rows("chatFull"), [], "and no chatFull row for the base holder")
        c["_frames"].clear()
        self.SESS[S1]["status"]["state"] = "working"     # flipped again, so the cycle's frame is not the handshake's
        km._built_chat.clear()                           # the pusher's first build of the sid since the boot
        km._push([c])
        self.assertEqual(self._sessions(c), [], "the cycle's first build is a tail too, not the changeAt0 full")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(c, "chatTail") if t["id"] == S1],
                         [("u4", [], "working")])
        self.assertNotIn("changeAt0", self._why())
        self.assertEqual(self._diag_rows("chatFull"), [])
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "the cycle's own write, as before")

    def test_19_the_seed_never_moves_a_present_baseline(self):
        # The guard the seed lives under: only a push that reaches EVERY client may ADVANCE the baseline (the 2026-07-28
        # stranded-delta lesson, test_chat_delta_resync). A connect push over a grown list finds a baseline present and
        # leaves it byte for byte, so the next cycle's tail to the older client carries what it lacks. Green before the
        # seed and after it: the pin that seeding when absent is not advancing.
        c = self._client(active=S1, proto=2)
        km._clients.append(c)
        km._push([c])                                    # the cycle: the baseline is u0..u4
        baseline = km._prev_chat_events[S1]
        before = json.loads(json.dumps(baseline))
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})
        km._built_chat.clear()
        d = self._client(active=S1, proto=2)             # a second page opens: its connect push builds the grown list
        km._clients.append(d)
        km._push([d], connect=True)
        self.assertEqual(self._sessions(d).count(S1), 1, "the fresh client got its full")
        self.assertIs(km._prev_chat_events[S1], baseline, "a present baseline is never replaced by a whole-frame send")
        self.assertEqual(km._prev_chat_events[S1], before)
        c["_frames"].clear(); d["_frames"].clear()
        km._push([c, d])                                 # the next cycle
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(c, "chatTail") if t["id"] == S1],
                         [("u4", ["u5"])], "the older client is served what it lacks: the baseline was not moved past it")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(d, "chatTail") if t["id"] == S1],
                         [("u4", ["u5"])], "the fresh client re-applies the overlap since the baseline, idempotently")

    def test_20_a_content_frame_replaces_an_empty_baseline(self):
        # A transcript-less session's cycle build writes [] as its baseline, and an empty list records no base on any
        # client (the empty-frame rule), so nothing is stranded by reading it as absent: the first content frame, from
        # whichever sender, becomes the baseline, and the targeted push after it sends a tail.
        km._prev_chat_events[S4] = []                    # the pusher's transcript-less build, by hand
        km._prev_chat_ledger[S4] = None
        self.SESS[S4]["events"] = [{"kind": "user", "uuid": "u0", "md": "m0"}, {"kind": "assistant", "uuid": "u1", "md": "m1"}]
        c = self._client(active=S4, proto=2)
        km._clients.append(c)
        km._push([c], connect=True)
        self.assertEqual(km._prev_chat_events.get(S4), self.SESS[S4]["events"], "content replaces the empty baseline")
        c["_frames"].clear()
        self.SESS[S4]["status"]["state"] = "working"
        km._push_session_now(S4)
        self.assertEqual(self._sessions(c), [], "the targeted push after it is a tail")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(c, "chatTail") if t["id"] == S4],
                         [("u1", [], "working")])

    def test_21_a_tab_that_left_the_strip_leaves_every_clients_base_and_the_baseline(self):
        # The pusher popped the baseline of a tab the strip stopped listing, and only for a sid its build cache held,
        # while every client's echat kept the base. With the seed, a re-entering tab's first whole frame would have
        # seeded a baseline while clients held an older base: the 2026-07-28 shape. The page tears a tab down when the
        # strip stops listing it (applyTabOrder), so the kernel's belief that a socket still holds it is false from that
        # moment: the eviction walks the union of the build cache and the baseline map now, and forgets every alive chat
        # client's base and dedup slot for the gone sid (2026-09-19). A tab that left is a never-seeded one again (no
        # client's base, no baseline, no mark), and the re-entry is a noBase full for everyone, with no row.
        km._PERF_STATS.reset()
        c = self._client(active=S1, proto=2)
        d = self._client(active=S3, proto=2)
        km._clients.extend([c, d])
        km._push([c, d])                                 # both hold S3 whole; the baseline has it
        for cl in (c, d):
            self.assertIn(S3, cl["echat"])
            self.assertIn(("chat", S3), cl["sent"])
        self.assertIn(S3, km._prev_chat_events)
        km._built_chat.pop(S3, None)                     # no cache entry for it: a baseline a targeted push seeded has none
        self._strip_without(S3, lambda: km._push([c, d]))
        for cl in (c, d):
            self.assertNotIn(S3, cl["echat"], "the base for a tab the page tore down is forgotten")
            self.assertNotIn(("chat", S3), cl["sent"], "and its dedup slot with it")
        self.assertNotIn(S3, km._prev_chat_events, "the baseline goes, with a cache entry or without one")
        self.assertNotIn(S3, km._prev_chat_ledger)
        c["_frames"].clear(); d["_frames"].clear()
        km._push([c, d])                                 # the tab re-enters the strip
        for cl in (c, d):
            self.assertEqual(self._sessions(cl), [S3], "a noBase full for everyone")
        self.assertNotIn("changeAt0", self._why())
        self.assertEqual(self._diag_rows("chatFull"), [], "no client held a base for it: nothing filed")

    def test_22_an_empty_build_after_a_seeded_full_takes_the_stand_in_road(self):
        # _empty_build_regresses reads the baseline as what the clients hold with content. Before the seed a connect
        # push's content full left none, so a transcript read that came back empty on the next cycle was no regression
        # against nothing: the empty frame went, counted `empty`, filed a row and blanked the pane. Seeded, the empty
        # build is the failed read it is: nothing sent for the sid, the episode said once on stderr.
        km._PERF_STATS.reset()
        km._EMPTY_BUILD_NOTED.discard(S1)
        c = self._client(active=S1, proto=2)
        km._clients.append(c)
        km._push([c], connect=True)                      # S1 content, whole
        c["_frames"].clear()
        self.SESS[S1]["events"] = []                     # the next read comes back empty
        km._built_chat.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([c])
        self.assertEqual([f for f in self._frames(c, "session") if f["id"] == S1], [], "no empty session frame reaches the client")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(self._diag_rows("chatFull"), [])
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its baseline held 5 events", err.getvalue(), "the seeded wording: the count is the baseline's length (2026-09-21)")
        self.assertIn("keeping the previous build until content returns", err.getvalue(), "...and the previous build stands in")
        self.assertNotIn("clients hold at least", err.getvalue(), "not the marked road's words")

    def _race(self, first, second_inside_first_send_to):
        """Two whole-frame senders on a baseline-less sid, delivered to client b in the inverted order: `first` runs and
        reads the baseline absent; while it sends S1 to `second_inside_first_send_to`, the u3 card fills and `second`
        (the closure) runs whole, sends its newer full and seeds; then the first sender's OLDER full lands on b."""
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        real = km._send_chat_or_status
        fired = []
        target = {"a": a, "b": b}[second_inside_first_send_to]

        def hook(cl, m, ms, change_from, led_changed):
            if m["id"] == S1 and cl is target and not fired:
                fired.append(1)
                self.SESS[S1]["events"][3]["md"] = "m3 filled"   # the card filled after the first sender's build
                km._send_chat_or_status = real
                try:
                    first["second"](b)
                finally:
                    km._send_chat_or_status = hook
            return real(cl, m, ms, change_from, led_changed)
        km._send_chat_or_status = hook
        try:
            first["first"](b)
        finally:
            km._send_chat_or_status = real
        self.assertEqual(fired, [1], "the second sender ran inside the first one's send loop")
        self.assertEqual(self._u3(b)[-1], ("session", "m3"), "b's last frame from the race is the OLDER full")
        return a, b

    def _the_cycle_repairs(self, a, b):
        """After the next cycle, the u3 card every client last received is the filled one (the frames are not cleared: a
        client that already held the filled build is served nothing new, its identical full dedups, and stands repaired)."""
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle builds the filled list
        for cl in (a, b):
            self.assertEqual(self._u3(cl)[-1], ("session", "m3 filled"), "the cycle's full repairs every client")
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "and the cycle's write establishes the baseline")

    def test_23_two_whole_frame_senders_racing_on_a_baseline_less_sid_keep_no_baseline_and_the_cycle_repairs_both(self):
        # Order one (the correctness review of the seed, 2026-09-19): the targeted push T builds the list with the u3
        # card pending and reads the baseline absent; while it sends a, a connect push C for page b builds the list with
        # u3 filled, hands b that full and seeds; then T's older full lands on a and on b, and b ends holding the OLDER
        # card. A seed that only wrote when absent left the newer list as the baseline: the next cycle diffed filled
        # against filled and nothing re-sent u3 to b short of a reconnect. The seed reads back the baseline it diffed
        # against: absent then and a DIFFERENT list now means a racing whole-frame sender wrote, per-client delivery
        # order is whichever thread reached each client's lock first, and no one list describes every base holder, so
        # the seed POPS the entry (and marks the sid, test 25) and the next cycle's full repairs every client, as it did
        # before the seed.
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertNotIn(S1, km._prev_chat_events, "two whole-frame senders raced: no list describes every base holder, none is kept")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self._the_cycle_repairs(a, b)

    def test_24_the_other_order_an_older_connect_push_landing_after_the_newer_targeted_push_keeps_no_baseline_either(self):
        # Order two: the connect push C for page b (u3 pending) has read the baseline absent and is about to send b;
        # the targeted push T (u3 filled) runs whole in that gap, fulls to a and b, seeds; then C's older full lands on
        # b. C's own seed finds a list other than the one it read and pops it.
        a, b = self._race({"first": lambda b: km._push([b], connect=True),
                           "second": lambda b: km._push_session_now(S1)}, "b")
        self.assertNotIn(S1, km._prev_chat_events, "the connect push's seed found a racing sender's list and kept none")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self._the_cycle_repairs(a, b)

    def test_25_a_single_client_push_between_the_race_and_the_cycle_re_seeds_nothing_and_the_cycle_still_repairs(self):
        # The detector's pop (tests 23 and 24) leaves clients holding bases with NO baseline, the state a never-seeded sid
        # is in too, and a seed that could not tell them apart was undone by the next single-client push (the review of
        # the detector, 2026-09-19): a needFull, or the idle prefetch releasing any tab on any page (one connect push per
        # released tab at a boot, while a cold cycle takes 30-84 s), read the baseline absent, sent ITS client a
        # changeAt0 full (repairing that one) and seeded from its build, so the cycle diffed equal lists and handed the
        # other holder of the older build an empty-suffix tail: a card that filled between the two racing builds stayed
        # stale until a reconnect, with no chatFull row. On the stock kernel the same sequence self-healed, the cycle's
        # full reaching everyone. The pop now MARKS the sid (_chat_baseline_raced): no seed writes while the mark stands,
        # and the cycle's write-after-deliver, which reaches every alive chat client, clears it with the write.
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertNotIn(S1, km._prev_chat_events)
        self.assertEqual(self._u3(a)[-1], ("session", "m3"), "a holds the older build too: the targeted push's full landed on both")
        rows0 = len(self._diag_rows("chatFull"))
        km._push([b], connect=True)                      # a needFull or an idle-prefetch release for page b, before any cycle
        self.assertEqual(self._u3(b)[-1], ("session", "m3 filled"), "b's own full repairs b, as before the seed")
        self.assertEqual(len(self._diag_rows("chatFull")) - rows0, 1, "b held a base: its full is a changeAt0 with a row")
        self.assertNotIn(S1, km._prev_chat_events,
                         "a single-client push after the race re-seeds nothing: a still holds the older build")
        self.assertIn(S1, km._chat_baseline_raced, "the pop is on record until an every-client sender writes")
        rows1 = len(self._diag_rows("chatFull"))
        self._the_cycle_repairs(a, b)                    # every client's last u3 is the filled one; the baseline re-established
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle reached every client: the mark clears with its write")
        rows = [r["data"] for r in self._diag_rows("chatFull")[rows1:]]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)],
                         "the stale holder got the cycle's changeAt0 full, with its row; b's identical full deduped on its slot")

    def test_26_two_seeds_that_both_read_the_baseline_absent_cannot_both_write(self):
        # The seed's read-back and write were two steps under no lock (the review, 2026-09-19): two whole-frame senders
        # whose loops ended close together could both read the map absent before either assigned, both write, the last
        # writer win, and the detector never fire, so a client holding the first writer's list was stranded exactly as
        # under a seed with no detector. The read-back and the write are one step under _chat_baseline_lock now. Driven
        # over the real seed with the map's `get` parked on its first call: the second seed must wait for the lock, then
        # read the first's list, differ, and pop it.
        older = {"id": S1, "events": json.loads(json.dumps(self.SESS[S1]["events"])), "ledger": None}
        self.SESS[S1]["events"][3]["md"] = "m3 filled"
        newer = {"id": S1, "events": json.loads(json.dumps(self.SESS[S1]["events"])), "ledger": None}
        parked, gate = threading.Event(), threading.Event()
        real = km._prev_chat_events

        class Parking(dict):
            def get(self, key, default=None):
                if not parked.is_set():                  # the FIRST seed's read-back: parked between its read and its write
                    parked.set()
                    gate.wait(10)
                return dict.get(self, key, default)
        km._prev_chat_events = Parking()
        try:
            first = threading.Thread(target=km._seed_chat_baseline, args=(S1, older, None))
            first.start()
            self.assertTrue(parked.wait(10), "the first seed parked at its read-back")
            second = threading.Thread(target=km._seed_chat_baseline, args=(S1, newer, None))
            second.start()
            second.join(0.5)
            self.assertTrue(second.is_alive(), "the second seed waits for the lock while the first is between its read and its write")
            gate.set()
            first.join(10)
            second.join(10)
            self.assertFalse(first.is_alive() or second.is_alive(), "both seeds ran to the end")
            self.assertNotIn(S1, km._prev_chat_events, "the second seed read the first's list, differed, and popped it")
            self.assertIn(S1, km._chat_baseline_raced, "...and marked the sid: the race is on record")
        finally:
            gate.set()
            km._prev_chat_events = real

    def _tails_cycle_under_a_mid_loop_mark(self):
        """Test 27's interleaving, through the cycle that sent tails (a helper since 2026-09-21, replayed by tests 47 and
        50): the targeted push T reads the baseline absent, builds the list with the u3 card pending and hands a (and b)
        its full, its seed step held back; the connect push C for page b builds the filled list, hands b its full and
        seeds it; the cycle reads that seed as present, builds the list grown by u5 and hands each client a tail from u4,
        and T's seed step lands at the cycle's first send, pops C's list and marks the sid. Returns (a, b) with that cycle
        done: a holds the pending card, every client holds six events, the mark stands and the baseline is absent."""
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        real_seed = km._seed_chat_baseline
        held = []

        def hold_first(sid, m, seen):
            if not held:                                 # T's seed step, held back
                held.append((sid, m, seen))
                return
            real_seed(sid, m, seen)
        km._seed_chat_baseline = hold_first
        fired = []
        try:
            km._push_session_now(S1)                     # T: the baseline absent, u3 pending, a full to a (and to b)
            self.assertEqual([h[2] for h in held], [None], "T read the baseline absent; its seed step is held")
            self.assertEqual(self._u3(a)[-1], ("session", "m3"))
            self.assertNotIn(S1, km._prev_chat_events)
            self.SESS[S1]["events"][3]["md"] = "m3 filled"   # the card fills after T's build
            km._push([b], connect=True)                  # C: b's full with u3 filled, and the seed
            self.assertEqual(km._prev_chat_events.get(S1), self.SESS[S1]["events"], "C seeded the filled list")
            self.assertEqual(self._u3(b)[-1], ("session", "m3 filled"))
            self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})   # grown before the cycle builds
            km._built_chat.clear()
            real_send = km._send_chat_or_status

            def at_first_send(cl, m, ms, change_from, led_changed):
                """The cycle's first per-client send for S1: the cycle has read the baseline present and diffed against it,
                and T's seed step lands here, on its own thread in the live kernel."""
                if m["id"] == S1 and not fired:
                    fired.append(1)
                    real_seed(*held[0])
                    self.assertNotIn(S1, km._prev_chat_events, "T's seed found C's list, not its own, and popped it")
                    self.assertIn(S1, km._chat_baseline_raced, "...and marked the sid")
                return real_send(cl, m, ms, change_from, led_changed)
            km._send_chat_or_status = at_first_send
            try:
                km._push([a, b])                         # the cycle
            finally:
                km._send_chat_or_status = real_send
        finally:
            km._seed_chat_baseline = real_seed
        self.assertEqual(fired, [1], "T's seed step ran inside the cycle's per-client loop")
        return a, b

    def test_27_a_cycle_that_sent_tails_leaves_a_mark_set_during_its_loop_standing_and_the_next_cycle_repairs(self):
        # The cycle's write-after-deliver cleared the sid's raced mark with its write unconditionally, on the grounds that
        # the cycle reached every alive chat client. That holds only when the cycle read the baseline ABSENT (change 0:
        # a full to every base holder). Read PRESENT, the loop sends tails, anchored at the change or the client's held
        # last, and a tail never re-sends an event below its anchor. The interleaving, on a baseline-less sid at a boot:
        # the targeted push T reads the baseline absent, builds the list with the u3 card pending and hands a its full;
        # a connect push C for page b builds the list with u3 filled, hands b its full and seeds it; the cycle reads that
        # seed as present, builds the list grown by u5 and hands a a tail from u4; then T's own seed step runs, finds a
        # list it did not write, pops it and marks the sid; the cycle's write re-established the list and CLEARED the
        # mark, so nothing re-sent u3 to a until a reconnect (on the merge base, with no seed, the cycle read the baseline
        # absent and its change-0 full repaired a). A cycle whose loop sent tails now leaves a mark set during that loop
        # standing and writes nothing; the next cycle reads the baseline absent, sends every base holder the full, then
        # writes and clears. T's seed step is held back from T's own run and replayed, with T's arguments, at the cycle's
        # first send: T between its send loop and its seed while the cycle has read the baseline and is delivering.
        a, b = self._tails_cycle_under_a_mid_loop_mark()
        self.assertEqual(self._sessions(a).count(S1), 1, "the cycle sent a no full for the sid: it diffed against the seeded list")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(a, "chatTail") if t["id"] == S1],
                         [("u4", ["u5"])], "a's tail starts after its held last: u3 sits below the anchor and is not re-sent")
        self.assertEqual(self._u3(a)[-1], ("session", "m3"), "a still holds the pending card")
        self.assertIn(S1, km._chat_baseline_raced, "a cycle that sent tails leaves the mark standing")
        self.assertNotIn(S1, km._prev_chat_events, "and writes no baseline over the pop")
        self.assertNotIn(S1, km._prev_chat_ledger)
        km._push([a, b])                                 # the next cycle: no baseline, so every base holder gets the full
        self.assertEqual(self._sessions(a).count(S1), 2, "the next cycle sends a the whole session")
        self.assertEqual(self._u3(a)[-1], ("session", "m3 filled"), "...which repairs the card")
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle that sent the fulls clears the mark")
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "and writes the baseline")

    def _build_hosts(self, second, inside, after):
        """Wrap the stubbed builder so the FIRST S1 build computes its payload from the transcript as it stands, then sets
        the u3 card to `inside`, runs `second` (a whole-frame sender that builds, sends and then seeds or writes) INSIDE
        the build, sets the card to `after` and only then hands the first payload back: two builders whose transcript
        reads and whose baseline reads interleave. Returns the list the wrapper appends to when it fires."""
        real = km.build_session
        fired = []

        def build(sid, now, live_map=None, **kw):
            m = real(sid, now, live_map, **kw)
            if sid == S1 and not fired:
                fired.append(1)
                self.SESS[S1]["events"][3]["md"] = inside    # the transcript as the inner sender's build reads it
                km.build_session = real                      # the inner sender builds whole, with the stock stub
                try:
                    second()
                finally:
                    km.build_session = build
                self.SESS[S1]["events"][3]["md"] = after     # the transcript as every later build reads it
            return m
        km.build_session = build
        return fired

    def _older_build_hosts(self, second):
        """The first S1 build is the OLDER one (the u3 card pending): the card fills inside it and `second` builds the
        filled list, so the sender whose build read the transcript first is the one whose baseline read lands after the
        other's seed."""
        return self._build_hosts(second, inside="m3 filled", after="m3 filled")

    def _the_repair_files_a_row_per_stale_holder(self, a, b, rows0, stale):
        """The next cycle reads the baseline absent and sends every base holder the full: a client holding the older card
        gets the changeAt0 full with its row; one already holding the filled build is sent the identical full, which
        dedups on its slot (test 25), so the rows added count the stale holders alone."""
        self._the_cycle_repairs(a, b)
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle reached every client with a full: the mark clears with its write")
        rows = [r["data"] for r in self._diag_rows("chatFull")[rows0:]]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * stale, "one changeAt0 full per stale holder, each with its row")

    def test_28_a_sender_whose_build_read_the_transcript_before_a_racing_seed_takes_the_detectors_road(self):
        # The seed's lower bound (the post-merge review of the seed, 2026-09-19): the detector compares the baseline the
        # sender READ against the one in the map at its seed step, and that read sat AFTER the build. A sender whose
        # build read the transcript BEFORE another sender's, but whose baseline read landed after that sender's seed,
        # read the seed as a PRESENT baseline: it diffed its older list against the newer one, sent the difference as
        # tails (or, to a fresh client, as a full), and its seed declined, since a present baseline is never touched.
        # The map then held the newer list while some client held the older card, the next cycle diffed equal lists,
        # and the client kept the stale card with no row and no mark. The interleaving, on a baseline-less sid: the
        # targeted push T builds the list with the u3 card pending; while its build runs, the card fills and a connect
        # push C for page b builds the filled list, hands b its full and seeds it; T's baseline read then finds C's
        # list. Note that the strand reaches the NEWER sender's own client too: b had the filled card from C, and T's
        # tail anchored at the change regressed it. Both reads now come BEFORE the build, so T reads the baseline as it
        # stood when its build began, absent here, sends fulls, and its seed step finds a list it did not read: the
        # detector's road, a pop and a mark, and the next cycle's full repairs every base holder with a row each. The
        # cost, stated in the seed's docstring: two fulls per client per race, where the strand was silent.
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        fired = self._older_build_hosts(lambda: km._push([b], connect=True))   # C, inside T's build
        km._push_session_now(S1)                         # T: its build read the transcript first
        self.assertEqual(fired, [1], "the connect push ran inside the targeted push's build")
        self.assertNotIn(S1, km._prev_chat_events, "T's seed found a list it did not read and popped it")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self.assertIn(S1, km._chat_baseline_raced, "...and marked the sid: the race is on record")
        self.assertEqual(self._u3(a)[-1], ("session", "m3"), "a holds T's older build")
        self.assertEqual(self._u3(b)[-1], ("session", "m3"),
                         "b held the filled card from C's full; T's older list regressed it, as a change-0 full against b's base "
                         "(T read the baseline absent; read present, as before, T sent the same regression as a tail at the change)")
        rows0 = len(self._diag_rows("chatFull"))
        self._the_repair_files_a_row_per_stale_holder(a, b, rows0, stale=2)   # both hold the older card

    def test_28b_the_connect_push_as_the_older_builder_takes_the_detectors_road_too(self):
        # The other pairing: the connect push A for page a builds the list with u3 pending; inside its build the card
        # fills and the targeted push B builds the filled list, hands a and b their fulls and seeds it; A's baseline
        # read then finds B's list, sends a a tail anchored at the change that regresses the card B had just filled,
        # and its seed declines. a kept the stale card until a reconnect, with no row and no mark. Read before the
        # build, A finds the baseline absent, its seed pops B's list and marks the sid, and the next cycle repairs.
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        km._built_chat.clear()                           # nothing cached: the connect push builds
        fired = self._older_build_hosts(lambda: km._push_session_now(S1))   # B, inside A's build
        km._push([a], connect=True)                      # A: its build read the transcript first
        self.assertEqual(fired, [1], "the targeted push ran inside the connect push's build")
        self.assertNotIn(S1, km._prev_chat_events, "A's seed found a list it did not read and popped it")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self.assertIn(S1, km._chat_baseline_raced)
        self.assertEqual(self._u3(a)[-1], ("session", "m3"), "a held the filled card from B's full; A's older change-0 full regressed it")
        self.assertEqual(self._u3(b)[-1], ("session", "m3 filled"), "b holds B's filled build: A targeted a alone")
        rows0 = len(self._diag_rows("chatFull"))
        self._the_repair_files_a_row_per_stale_holder(a, b, rows0, stale=1)   # a alone; b's identical full dedups

    def test_28c_the_cycles_write_landing_inside_a_newer_senders_build_reads_as_a_race_the_accepted_cost(self):
        """The accepted cost of reading the baseline before the build, pinned so the deferred build-start stamp has its red
        test for this face (the review of the change, 2026-09-21). The detector compares the baseline a sender READ with
        the one in the map at its seed step, and with the read before the build it can no longer tell a racing
        single-client SEED that landed mid-build (test 28: the sender's list the OLDER one, a client stranded without the
        pop) from the cycle's every-client WRITE landing mid-build with the sender's list the NEWER one: no client is
        stale, yet the seed reads absent-then-different, pops the cycle's baseline and marks the sid. The map's content
        carries no order (a filled card has the length of its unfilled twin), and a written-by-the-cycle flag is not
        sound (a connect seed, then the cycle's tails and write, then an older targeted push's fulls: declining the pop
        there re-opens the strand), so the pop stands and the cost is paid: the sender's change-0 full to every base
        holder with a changeAt0 row each, then the next cycle's change-0 full to every base holder with a row each when
        the session frame moved or the repost window passed since the sender's full (the status flip below is what makes
        the third frame leave; unchanged within the window it dedups on the client's slot and files no row). The
        kernel before this change sent one tail per client here, no mark, no row, and this test against it fails at the
        first frame assertion (each client holds the cycle's full then a tail): that is its red, the changed behavior
        pinned, not a defect it caught. The boot's ordinary interleaving: the cycle's cold build of the watched tab beside
        the attach handshake's targeted push, the transcript moving between the two reads. Bounded by the number of
        senders building the sid at once; a stamp of the build's start kept beside the baseline, its own item, is the
        discriminator that removes it."""
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        self.SESS[S1]["events"][3]["md"] = "m3 filled"   # the transcript as T's build reads it: the NEWER list
        fired = self._build_hosts(lambda: km._push([a, b]), inside="m3", after="m3 filled")   # the cycle inside T's build, over the
        km._push_session_now(S1)                         # OLDER transcript its own build read first; T read the baseline absent
        self.assertEqual(fired, [1], "the cycle built, sent and wrote inside the targeted push's build")
        for cl in (a, b):
            self.assertEqual(self._u3(cl), [("session", "m3"), ("session", "m3 filled")],
                             "the cycle's noBase full, then T's change-0 full: every client holds the newer list, nobody is stale")
        self.assertNotIn(S1, km._prev_chat_events, "T's seed read the baseline absent and found the cycle's list: popped")
        self.assertIn(S1, km._chat_baseline_raced, "...and marked, with no stale holder: the false positive")
        rows = [r["data"] for r in self._diag_rows("chatFull")]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "T's full to each base holder, filed as the racing shape")
        self.SESS[S1]["status"]["state"] = "waiting"     # flipped: the frame moved, so the next cycle's full leaves rather than deduping on the slot (test 18)
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle: the baseline absent, so every base holder gets the full
        for cl in (a, b):
            self.assertEqual(self._sessions(cl).count(S1), 3, "a third whole frame for a client that was never stale")
            self.assertEqual(self._u3(cl)[-1], ("session", "m3 filled"))
        rows = [r["data"] for r in self._diag_rows("chatFull")[2:]]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "...with its row per base holder")
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle's write clears the mark")
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "and re-establishes the baseline")

    def test_29_a_connect_push_seeds_only_the_tabs_it_handed_to_a_client_whole(self):
        # The seed's premise was that a build reaching it had been handed to clients whole. A redialing client holds every
        # tab but the active one as a skeleton, and the per-client loop hands it a status frame for each of those
        # (_send_chat_or_status), no whole frame; the connect push's seed ran all the same, after the loop, and wrote a
        # baseline no client holds for every skeleton tab (the post-merge review of the seed, 2026-09-21). A list no
        # client holds is no lower bound on any base holder, and with another sender's list in the map the detector read
        # it as a race (test 31). The seed runs only for a sid some client in the loop took whole.
        c = self._client(active=S1, reconnect=True, proto=2)
        km._clients.append(c)
        km._push([c], connect=True)                      # the redial's connect push: S1 whole, S2 and S3 as status frames
        self.assertEqual(c["skeleton"], {S2, S3})
        self.assertEqual(self._sessions(c), [S1, S4], "whole frames for the watched tab and the transcript-less one (an empty list, outside the set)")
        self.assertEqual(sorted(sid for sid, st in self._statuses(c)), sorted([S2, S3]), "a status frame per skeleton tab")
        self.assertEqual(km._prev_chat_events.get(S1), self.SESS[S1]["events"], "the tab handed over whole seeds, as in test 18")
        seeded = {sid[-1]: len(evs) for sid, evs in km._prev_chat_events.items()}
        self.assertNotIn(S2, km._prev_chat_events, "a tab the client got as a status frame seeds nothing; seeded: %r" % (seeded,))
        self.assertNotIn(S3, km._prev_chat_events, "a tab the client got as a status frame seeds nothing; seeded: %r" % (seeded,))
        self.assertNotIn(S2, km._prev_chat_ledger)
        self.assertNotIn(S3, km._prev_chat_ledger)

    def test_30_a_targeted_push_whose_every_client_holds_the_tab_as_a_skeleton_seeds_nothing(self):
        # The targeted push's road (2026-09-21): a handshake or a stream event for a tab every connected page holds as a
        # skeleton hands each page a status frame and no whole frame (test 05), and its seed wrote the build as the sid's
        # baseline all the same. Driven with no cycle before it and no live row, so the cold-tab gate stands down and the
        # push builds: the shape of a cached or live-row-less tab, the one the gate does not cover.
        c = self._client(active=S1, reconnect=True, proto=2)
        km._clients.append(c)
        km._push_session_now(S3)                         # the redial's first strip sender: the set resolves here, S3 in it
        self.assertEqual(c["skeleton"], {S2, S3})
        self.assertEqual(self.built, [S3], "the gate stood down: the push built the tab")
        self.assertEqual(self._sessions(c), [], "no whole frame for a tab the page holds as a skeleton")
        self.assertEqual(self._statuses(c), [(S3, {"state": "waiting", "sinceEpoch": None})], "its status instead")
        self.assertNotIn(S3, km._prev_chat_events,
                         "a push that handed its build to no client seeds nothing; the map holds %r"
                         % ({sid[-1]: len(evs) for sid, evs in km._prev_chat_events.items()},))
        self.assertNotIn(S3, km._prev_chat_ledger)

    def test_31_a_status_only_sender_racing_a_whole_frame_sender_pops_nothing_and_the_pushes_after_it_send_tails(self):
        # The false race (2026-09-21): page a holds S3 as a skeleton, page b is looking at it, and the sid has no baseline
        # (a boot before the first cycle, a tab re-entering after the eviction). a's connect push reads the baseline
        # absent and, while its loop hands a the status frame for S3, a targeted push for S3 (the handshake, a stream
        # event) builds the list with the u1 card filled, hands b that full and seeds it. a's seed then found a list other
        # than its own and read it as a race between two whole-frame senders: it popped b's list and marked the sid,
        # though b is the only base holder and holds exactly the list that was popped. The repair was the next cycle's
        # changeAt0 full to every base holder, with a chatFull row each, the frame the seed exists to remove; until then
        # every targeted push for the sid (a status flip) re-sent b the whole session too. A sender that handed its build
        # to no client seeds nothing and pops nothing: the whole-frame sender's seed stands and the pushes after it send
        # tails.
        km._PERF_STATS.reset()
        a = self._client(active=S1, reconnect=True, proto=2)
        b = self._client(active=S3, proto=2)
        km._clients.extend([a, b])
        real = km._send_chat_or_status
        fired = []

        def hook(cl, m, ms, change_from, led_changed):
            if m["id"] == S3 and cl is a and not fired:
                fired.append(1)
                self.SESS[S3]["events"][1]["md"] = "m1 filled"   # the card fills after the connect push's build
                km._send_chat_or_status = real
                try:
                    km._push_session_now(S3)             # the whole-frame sender: b's full, a's status frame, and the seed
                finally:
                    km._send_chat_or_status = hook
            return real(cl, m, ms, change_from, led_changed)
        km._send_chat_or_status = hook
        try:
            km._push([a], connect=True)                  # the status-only sender, for S3
        finally:
            km._send_chat_or_status = real
        self.assertEqual(fired, [1], "the targeted push ran inside the connect push's send loop")
        self.assertEqual(self._sessions(b).count(S3), 1, "b got its full from the targeted push")
        self.assertEqual(self._card(b, S3, "u1")[-1], ("session", "m1 filled"))
        self.assertEqual(self._sessions(a).count(S3), 0, "a holds S3 as a skeleton: no whole frame from either sender")
        self.assertEqual(km._prev_chat_events.get(S3), self.SESS[S3]["events"],
                         "the whole-frame sender's seed stands: the status-only sender had no list of its own to race with")
        self.assertNotIn(S3, km._chat_baseline_raced, "nobody raced: no mark")
        self.assertEqual(self._diag_rows("chatFull"), [], "b held no base before its full: nothing filed")
        a["_frames"].clear(); b["_frames"].clear()
        self.SESS[S3]["status"]["state"] = "working"     # the flip the next targeted push exists for
        km._push_session_now(S3)
        self.assertEqual(self._sessions(b), [], "the next targeted push is a tail to b, not a whole session")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(b, "chatTail") if t["id"] == S3],
                         [("u2", [], "working")], "the empty-suffix tail carries the flip")
        self.assertEqual(self._sessions(a), [], "a is still a skeleton holder")
        self.assertNotIn("changeAt0", self._why(), "no full counted against the popped baseline")
        self.assertEqual(self._diag_rows("chatFull"), [], "and no chatFull row for the base holder")
        a["_frames"].clear(); b["_frames"].clear()
        self.SESS[S3]["events"].append({"kind": "assistant", "uuid": "u3", "md": "m3"})   # the transcript grows
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle
        self.assertEqual([s for s in self._sessions(b) if s == S3], [],
                         "the cycle diffs against the standing baseline: a tail for S3, not the repair full (the other tabs are b's first)")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(b, "chatTail") if t["id"] == S3],
                         [("u2", ["u3"])], "b is served what it lacks")
        self.assertNotIn("changeAt0", self._why())
        self.assertEqual(self._diag_rows("chatFull"), [])
        self.assertEqual(km._prev_chat_events[S3], self.SESS[S3]["events"], "the cycle's write, as before")

    def test_32_a_status_only_sender_landing_between_a_whole_frame_senders_build_and_its_baseline_read_strands_nobody(self):
        # The inverted order of test 31 (2026-09-21): the targeted push T builds S3 with the u1 card pending; between
        # T's build and T's baseline read, a's connect push builds the filled list, hands a its status frame for S3 and,
        # seeding from a frame no client took, wrote the filled list as the baseline. T then read a baseline present,
        # diffed its older list against the newer one and handed b (no base) the OLDER full, and declined its own seed as
        # a present baseline requires. The next cycle built the filled list, equal to the baseline, and b's only S3 frame
        # was an empty tail: u1 stayed pending on b with no row and no repair short of a reconnect. With the status-only
        # sender seeding nothing, T reads the baseline absent, seeds the list it handed b, and the cycle's diff against
        # that list re-sends the filled card as a tail.
        a = self._client(active=S1, reconnect=True, proto=2)
        b = self._client(active=S3, proto=2)
        km._clients.extend([a, b])
        real_build = km.build_session
        fired = []

        def build(sid, now, live_map=None, **kw):
            m = real_build(sid, now, live_map, **kw)     # T's payload, u1 pending
            if sid == S3 and not fired:
                fired.append(1)
                self.SESS[S3]["events"][1]["md"] = "m1 filled"   # the card fills after T's build
                km.build_session = real_build
                try:
                    km._push([a], connect=True)          # the status-only sender, between T's build and T's baseline read
                finally:
                    km.build_session = build
            return m
        km.build_session = build
        try:
            km._push_session_now(S3)                     # T
        finally:
            km.build_session = real_build
        self.assertEqual(fired, [1], "the connect push ran between T's build and T's baseline read")
        self.assertEqual(self._sessions(a).count(S3), 0, "a holds S3 as a skeleton: no whole frame from either sender")
        self.assertEqual(self._card(b, S3, "u1"), [("session", "m1")], "b's one full, from T, carries the pending card")
        self.assertEqual([e["md"] for e in km._prev_chat_events.get(S3) or []], ["m0", "m1", "m2"],
                         "T's list, the one b holds, is the baseline: the status-only sender wrote none")
        a["_frames"].clear(); b["_frames"].clear()
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle builds the filled list
        self.assertEqual(self._card(b, S3, "u1"), [("chatTail", "m1 filled")],
                         "the cycle's tail against T's list re-sends the filled card; S3 frames to b: %r"
                         % ([(f["type"], [e["uuid"] for e in f.get("events") or []]) for f in b["_frames"] if f.get("id") == S3],))
        self.assertEqual(km._prev_chat_events[S3], self.SESS[S3]["events"], "and the cycle's write advances the baseline")

    def test_33_a_targeted_push_to_a_socket_before_its_ready_seeds_nothing(self):
        # The third no-delivery road (2026-09-21): a real socket before its ready (handshake False, as the accept marks it)
        # gets no chat frame from the locked send, which counts the frame withheld and writes no base (the window-spans
        # module's pre-ready shape). A targeted push whose only client is such a socket handed its build to nobody and
        # seeded the sid from it all the same; it seeds nothing now, and the socket's ready reset and connect push bring
        # the first whole frame, which seeds.
        c = self._client(proto=2, echat={}, handshake=False)
        km._clients.append(c)
        km._push_session_now(S1)                         # the handshake push, landing before the socket's ready
        self.assertEqual(self.built, [S1], "the push built the tab: no set, so the cold-tab gate stood down")
        self.assertEqual(self._sessions(c), [], "no chat frame reaches a socket before its ready")
        self.assertEqual(c.get("withheld"), 1, "...the frame is counted withheld")
        self.assertEqual(c["echat"], {}, "...and no base is recorded")
        self.assertEqual(dict(km._prev_chat_events), {},
                         "a build handed to no client seeds nothing; the map holds %r"
                         % ({sid[-1]: len(evs) for sid, evs in km._prev_chat_events.items()},))
        self.assertEqual(dict(km._prev_chat_ledger), {})

    def test_34_a_marked_sid_with_neither_cache_entry_nor_baseline_is_forgotten_when_its_tab_leaves(self):
        # A pin of the eviction's walk of the marks and its clear (the post-merge review of the seed, 2026-09-21). The
        # strip-exit eviction walks the union of the build cache, the baseline map and the detector's marks, so a sid the
        # detector popped, which has neither a cache entry (a targeted push caches nothing, and the connect push's entry
        # is evicted with the rest) nor a baseline, is still found when its tab leaves the strip: its mark cleared, every
        # client's base and dedup slot for it forgotten. With the marks dropped from the walk such a sid stayed marked
        # for the kernel's life, every client kept a base the page had torn down, and the re-entry cost each base holder
        # a changeAt0 full with a row (or deduped as identical) instead of the noBase full a never-seeded sid gets.
        # Amending test 21 would catch the clear alone, since S3 there is found through the baseline map; the walk's
        # third member needs a marked sid with nothing else to be found by. Green before this change; red with the marks
        # dropped from the walk and their clear removed (the review's mutation).
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        km._built_chat.pop(S1, None)                     # no cache entry: the marks are the one place the sid is found
        self.assertNotIn(S1, km._prev_chat_events, "premise: the race popped the baseline")
        self.assertIn(S1, km._chat_baseline_raced, "premise: ...and marked the sid")
        for cl in (a, b):
            self.assertIn(S1, cl["echat"], "premise: both clients hold a base")
        km._PERF_STATS.reset()
        rows0 = len(self._diag_rows("chatFull"))         # the race itself filed a changeAt0 row
        self._strip_without(S1, lambda: km._push([a, b]))
        self.assertNotIn(S1, km._chat_baseline_raced, "the eviction walks the marks: a sid found by its mark alone is forgotten")
        for cl in (a, b):
            self.assertNotIn(S1, cl["echat"], "every client's base for the gone tab goes with it")
            self.assertNotIn(("chat", S1), cl["sent"], "and its dedup slot")
        a["_frames"].clear(); b["_frames"].clear()
        km._built_chat.clear()
        km._push([a, b])                                 # the tab re-enters the strip
        for cl in (a, b):
            self.assertEqual(self._sessions(cl), [S1], "a noBase full for everyone, as for a never-seeded sid")
        self.assertNotIn("changeAt0", self._why(), "no full counted against a held base")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "no client held a base for it: nothing filed")
        self.assertIn(S1, km._prev_chat_events, "the cycle's write re-establishes the baseline")
        self.assertNotIn(S1, km._chat_baseline_raced)

    def test_35_a_cycles_empty_build_over_a_popped_baseline_takes_the_stand_in_road(self):
        # The empty-build guard read the baseline as what the clients hold with content (test 22). After the detector's
        # pop (tests 23 and 24), or a tails-only cycle that skipped its write (test 27), the sid has NO baseline while
        # every client holds content, so a transcript read that came back empty before the repairing cycle was no
        # regression against nothing: the cycle sent every base holder an empty session frame, counted `empty` with a
        # chatFull row each and no stderr line, and its write put [] over the pop and took the mark off, so content's
        # return was one more full to everyone (the post-merge review of the seed, 2026-09-21). The pane did not blank,
        # since the page absorbs the frame as status-shaped; the cost was meter noise, the lost stderr line and the
        # redundant full. A marked sid is one whose clients hold content: the empty build takes the stand-in road, the
        # note names the count stashed at the pop, and the mark and the absent baseline stand for the next cycle's
        # repair. The two builds.chat counters are read here too: one pop, then one repair.
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertNotIn(S1, km._prev_chat_events, "premise: the race popped the baseline")
        self.assertIn(S1, km._chat_baseline_raced, "premise: ...and marked the sid")
        km._EMPTY_BUILD_NOTED.discard(S1)
        rows0 = len(self._diag_rows("chatFull"))         # the race itself filed a changeAt0 row
        a["_frames"].clear(); b["_frames"].clear()
        content = self.SESS[S1]["events"]
        self.SESS[S1]["events"] = []                     # the next read comes back empty
        km._built_chat.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b])                             # the cycle
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1], [],
                             "no empty session frame reaches a base holder")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "and no chatFull row")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 5 events", err.getvalue(),
                      "...with the count at the pop: no whole frame was handed under the mark since")
        self.assertIn("sending nothing for it until content returns", err.getvalue(), "the marked wording: nothing is kept or sent")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands: this cycle sent no base holder a full")
        self.assertNotIn(S1, km._prev_chat_events, "and the baseline stays absent: no [] is written over the pop")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0), "one pop counted, no repair yet")
        self.SESS[S1]["events"] = content                # content returns
        self._the_cycle_repairs(a, b)                    # the next cycle's full to every base holder
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 1), "the repair counted")
        doc = open(os.path.join(os.path.dirname(HERE), "docs", "reference.md"), encoding="utf-8").read()
        self.assertIn("`baselineRaced`", doc, "the reference glosses the counter")
        self.assertIn("`baselineRepaired`", doc)

    def test_36_a_targeted_pushs_empty_build_over_a_popped_baseline_takes_the_stand_in_road_too(self):
        # The same over the targeted push (2026-09-21): a handshake or a stream event for a marked sid whose transcript
        # read came back empty sent every base holder an empty session frame, counted `empty` with a row each and no
        # stderr line, the mark standing and the baseline absent all the same. The push now sends nothing for the sid and
        # says the failed read once; the periodic pusher owns the sid until content returns, and the next cycle's full
        # repairs every base holder and takes the mark off. The count the note names is the one at the pop, RAISED by
        # every whole frame handed under the mark: a targeted push over a longer list under the standing mark diffs
        # change 0 against the absent baseline, hands every base holder its full, and its seed declines under the mark,
        # so a stash left at the pop's count named the shorter list (5) while every client held the longer one (7).
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertNotIn(S1, km._prev_chat_events, "premise: the race popped the baseline")
        self.assertIn(S1, km._chat_baseline_raced, "premise: ...and marked the sid")
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})   # the transcript grows under the mark
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u6", "md": "m6"})
        km._push_session_now(S1)                         # a targeted push under the standing mark: a full to every base holder
        for cl in (a, b):
            self.assertEqual(len([f for f in self._frames(cl, "session") if f["id"] == S1][-1]["events"]), 7,
                             "every base holder was handed the longer list whole")
        self.assertIn(S1, km._chat_baseline_raced, "the push's seed declined under the mark")
        self.assertNotIn(S1, km._prev_chat_events, "and wrote nothing")
        km._EMPTY_BUILD_NOTED.discard(S1)
        km._PERF_STATS.reset()
        rows0 = len(self._diag_rows("chatFull"))
        a["_frames"].clear(); b["_frames"].clear()
        content = self.SESS[S1]["events"]
        self.SESS[S1]["events"] = []                     # the next read comes back empty
        km._built_chat.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push_session_now(S1)                     # the targeted push
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1], [],
                             "no empty session frame reaches a base holder")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "and no chatFull row")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 7 events", err.getvalue(),
                      "...with the count raised by the whole frame handed under the mark, not the 5 at the pop")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent")
        self.SESS[S1]["events"] = content                # content returns
        self.SESS[S1]["status"]["state"] = "waiting"     # flipped, so the repair's full is not the targeted push's frame deduping on the slot (test 28c)
        self._the_cycle_repairs(a, b)                    # the next cycle's full to every base holder
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")

    def test_37_a_cycles_empty_build_over_a_popped_baseline_with_a_cached_build_hands_no_base_holder_the_cached_list(self):
        """The cached-hit road under the mark (2026-09-21): after the race the connect push's build sits in the cache (the
        filled list) while the baseline is popped and the sid marked. The next cycle's signature misses (the transcript
        grew), its build comes back empty, and the guard reads the mark: no frame for the sid reaches any client, a
        cached build or not, the mark and the absent baseline stand, and the next content cycle's full repairs every base
        holder; the counters read one pop and no repair, then one repair. This test first pinned the stand-in road (the
        post-merge review of the mark, 2026-09-21): the cached list went to every base holder as a change-0 full and the
        write took the mark off, and since a baseline is absent under the mark the stand-in always left as a full, so it
        rewound every holder ahead of it, the shorter face (test 44) and the same-length face (test 45). The seeded case's
        road, a present baseline with a targeted push's tail leaving both clients ahead of it, sends the stand-in as a
        lastGone full at both heads: pre-existing, outside this change. Red before the change at the S1-frame assertion,
        where the stand-in reached both and the mark came off."""
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        hit = km._built_chat.get(S1)
        self.assertIsNotNone(hit, "premise: the connect push cached its build")
        self.assertEqual(hit[1]["events"][3]["md"], "m3 filled", "premise: ...the filled list")
        self.assertNotIn(S1, km._prev_chat_events, "premise: the race popped the baseline")
        self.assertIn(S1, km._chat_baseline_raced, "premise: ...and marked the sid")
        for cl in (a, b):
            self.assertEqual(self._u3(cl)[-1], ("session", "m3"), "premise: both hold the older card")
        km._EMPTY_BUILD_NOTED.discard(S1)
        rows0 = len(self._diag_rows("chatFull"))
        a["_frames"].clear(); b["_frames"].clear()
        content = self.SESS[S1]["events"]
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the cycle builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b])                             # the cycle
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1], [],
                             "no frame for the sid reaches a base holder: the cached build is no stand-in under the mark")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "and no chatFull row")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 5 events", err.getvalue())
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands: this cycle sent no base holder a full")
        self.assertNotIn(S1, km._prev_chat_events, "and the baseline stays absent")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0), "one pop counted, no repair yet")
        self.SESS[S1]["events"] = content                # content returns
        self._the_cycle_repairs(a, b)                    # the next content cycle's full to every base holder
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 1), "the repair counted")

    def test_38_a_base_another_sender_writes_on_a_loop_client_after_its_status_send_is_not_this_loops_delivery(self):
        # The seed's delivery signal was a read of the clients' bases AFTER the loop (the post-merge review of the seed's
        # guard, 2026-09-21): whether some loop client held a base for the sid at the seed step, a state read and not the
        # loop's own event. A base another whole-frame sender wrote on a loop client between that client's status send
        # and the seed step counted as this loop's delivery, so a status-only pass seeded, and its list differing from the
        # map's, the detector popped the other sender's list and marked the sid: one pop and mark, and the next cycle's
        # change-0 full with a chatFull row to every base holder, the frame the seed exists to remove. The shape: a
        # targeted push (a backend thread, no lock across its loop) over a sid every page holds as a skeleton, preempted
        # between its last status send and its seed step while one page's reader thread handles that page's needFull for
        # the sid and the connect push it runs inline hands the page the full and seeds. The signal is the loop's own
        # event now, recorded where the client's echat entry is written, on the sending thread inside the loop that
        # sends: the other sender's write is its own loop's delivery, this loop handed its build to nobody and seeds
        # nothing, and the other sender's seed stands.
        km._PERF_STATS.reset()
        a = self._client(active=S1, reconnect=True, proto=2)
        b = self._client(active=S1, reconnect=True, proto=2)
        km._clients.extend([a, b])
        km._push([a], connect=True)                      # each page's ready arm: S1 whole, S2 and S3 as skeletons
        km._push([b], connect=True)
        self.assertEqual((a["skeleton"], b["skeleton"]), ({S2, S3}, {S2, S3}), "premise: every page holds S3 as a skeleton")
        self.assertNotIn(S3, km._prev_chat_events, "premise: no baseline for S3 (a status frame seeds nothing, test 29)")
        a["_frames"].clear(); b["_frames"].clear()
        real = km._send_chat_or_status
        fired = []
        h = type("H", (), {"_push_one": km.Handler._push_one})()   # the REAL _push_one body: _push([client], connect=True)

        def hook(cl, m, ms, change_from, led_changed):
            out = real(cl, m, ms, change_from, led_changed)   # b's status frame for S3: the targeted push's LAST send
            if m["id"] == S3 and cl is b and not fired:
                fired.append(1)
                self.SESS[S3]["events"][1]["md"] = "m1 filled"   # the card fills after the targeted push's build
                km._built_chat.pop(S3, None)             # ...so the connect push's signature misses the premise's cached build and it builds
                km._send_chat_or_status = real
                try:                                     # b's reader thread, in the gap before the targeted push's seed step:
                    km.Handler._dispatch_ws(h, {"type": "needFull", "id": S3, "why": "prefetch"}, b)   # the prefetch's ask, its connect push inline
                finally:
                    km._send_chat_or_status = hook
            return out
        km._send_chat_or_status = hook
        try:
            km._push_session_now(S3)                     # the targeted push: a status frame to a and to b, then its seed step
        finally:
            km._send_chat_or_status = real
        self.assertEqual(fired, [1], "the ask and its connect push ran between the targeted push's last status send and its seed step")
        self.assertEqual(self._card(b, S3, "u1"), [("session", "m1 filled")], "b's one full, from its own connect push, carries the filled card")
        self.assertEqual(self._sessions(a).count(S3), 0, "a holds S3 as a skeleton: no whole frame from either sender")
        self.assertNotIn(S3, km._chat_baseline_raced,
                         "a base the other sender wrote on b is not the targeted push's delivery: no pop, no mark")
        self.assertEqual(km._prev_chat_events.get(S3), self.SESS[S3]["events"],
                         "the connect push's list, the one b holds, is the baseline; the map holds %r"
                         % ({sid[-1]: len(evs) for sid, evs in km._prev_chat_events.items()},))
        self.assertEqual(km._PERF_STATS.snapshot()["builds"]["chat"]["baselineRaced"], 0, "nothing counted raced")
        a["_frames"].clear(); b["_frames"].clear()
        self.SESS[S3]["events"].append({"kind": "assistant", "uuid": "u3", "md": "m3"})   # the transcript grows
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle
        self.assertEqual([s for s in self._sessions(b) if s == S3], [],
                         "the cycle diffs against the standing baseline: a tail to b, not the change-0 repair full")
        self.assertEqual([(t["afterUuid"], [e["uuid"] for e in t["events"]]) for t in self._frames(b, "chatTail") if t["id"] == S3],
                         [("u2", ["u3"])], "b is served what it lacks")
        self.assertEqual(self._sessions(a).count(S3), 0, "a is still a skeleton holder")
        self.assertNotIn("changeAt0", self._why(), "no full counted against a popped baseline")
        self.assertEqual(self._diag_rows("chatFull"), [], "and no chatFull row for the base holder")
        self.assertEqual(km._prev_chat_events[S3], self.SESS[S3]["events"], "the cycle's write, as before")

    def test_39_the_first_content_frame_over_an_empty_baseline_seeds_through_the_targeted_push_too(self):
        # The targeted push's copy of the seed guard reads the baseline as `not _seen`, absent OR empty, as the connect
        # push's copy does, and test 20 pins that copy alone (the post-merge review of the guard, 2026-09-21). A
        # transcript-less session's cycle write leaves [] as its baseline, and an empty list records no base on any
        # client, so a copy here that drifted to a None-only check would let the first content frame a stream event
        # hands a fresh client (a Codex session's first turn, before the pusher's next cycle) seed nothing, and every
        # targeted push after it would re-send every base holder a changeAt0 full with a row until the cycle wrote.
        # Driven through _push_session_now with a fresh client: the content frame seeds, and the push after it is a tail.
        km._PERF_STATS.reset()
        km._prev_chat_events[S4] = []                    # the pusher's transcript-less build, by hand
        km._prev_chat_ledger[S4] = None
        self.SESS[S4]["events"] = [{"kind": "user", "uuid": "u0", "md": "m0"}, {"kind": "assistant", "uuid": "u1", "md": "m1"}]
        c = self._client(active=S4, proto=2)
        km._clients.append(c)
        km._push_session_now(S4)                         # the first content frame: a stream event's targeted push
        self.assertEqual(self._sessions(c), [S4], "a fresh client gets the full")
        self.assertEqual(km._prev_chat_events.get(S4), self.SESS[S4]["events"], "content replaces the empty baseline on this road too")
        c["_frames"].clear()
        self.SESS[S4]["status"]["state"] = "working"     # the flip the next push exists for
        km._push_session_now(S4)
        self.assertEqual(self._sessions(c), [], "the targeted push after it is a tail, not a changeAt0 full")
        self.assertEqual([(t["afterUuid"], t["events"], t["status"]["state"]) for t in self._frames(c, "chatTail") if t["id"] == S4],
                         [("u1", [], "working")], "the empty-suffix tail carries the flip")
        self.assertNotIn("changeAt0", self._why(), "no full counted against the seeded baseline")
        self.assertEqual(self._diag_rows("chatFull"), [], "and no chatFull row for the base holder")

    def test_40_the_cycles_write_landing_inside_an_older_senders_build_is_the_strand_face_the_pop_repairs(self):
        """The cell test 28c's mirror left unnamed (the post-merge review of the read placement, 2026-09-21): the cycle's
        every-client write as the writer inside a sender's build, with the sender's list the OLDER one. The targeted push
        T reads the baseline absent and builds the list with the u3 card pending; inside its build the card fills and the
        cycle runs whole, reads the baseline absent too, hands a and b a noBase full of the filled list and writes it;
        then T's change-0 fulls of the older list land on both, so every client holds the older card over the cycle's
        newer one, T's seed reads absent-then-different, pops the cycle's baseline and marks the sid, and the next cycle's
        fulls repair both: a strand face, the pop its repair, two changeAt0 rows at the push and two at the repair (no
        status flip: the repair's frame differs from T's on every client, so nothing dedups). The kernel before the read
        moved (the merge base of the read-placement change, its kernel swapped in for the run) read the cycle's write as a
        PRESENT baseline after T's build, diffed T's older list against it and sent the older card as a tail at the change
        with no pop, no mark and no row, and the next cycle diffed equal lists: every client on the older card for good.
        This test is red there at the first frame assertion, a tail where the change-0 full is."""
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        fired = self._older_build_hosts(lambda: km._push([a, b]))   # the cycle inside T's build, over the filled card
        km._push_session_now(S1)                         # T: its build read the pending card first; the baseline absent
        self.assertEqual(fired, [1], "the cycle built, sent and wrote inside the targeted push's build")
        for cl in (a, b):
            self.assertEqual(self._u3(cl), [("session", "m3 filled"), ("session", "m3")],
                             "the cycle's noBase full, then T's change-0 full of the OLDER list: every client holds the older card")
        self.assertNotIn(S1, km._prev_chat_events, "T's seed read the baseline absent and found the cycle's list: popped")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self.assertIn(S1, km._chat_baseline_raced, "...and marked: two stale holders on record")
        rows = [r["data"] for r in self._diag_rows("chatFull")]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "T's full to each base holder, filed as the racing shape")
        self._the_repair_files_a_row_per_stale_holder(a, b, len(rows), stale=2)   # both hold the older card; no flip needed

    def test_41_an_older_senders_seed_landing_inside_a_newer_targeted_pushs_build_is_the_false_positive_with_another_writer(self):
        """The partition's other unnamed cell (the same review): a whole-frame SEED, not the cycle's write, landing inside
        a build whose list is the NEWER one, two targeted pushes on one sid, which nothing serializes. T2 reads the
        baseline absent and builds the list with the u3 card filled; inside its build the card reads pending and T1 runs
        whole, reads the baseline absent, hands a and b a noBase full of the older list and seeds it; then T2's change-0
        fulls of the filled list land on both, so no client is stale, yet T2's seed reads absent-then-different, pops T1's
        list and marks the sid, and the next cycle's fulls go to every base holder once more: test 28c's false positive
        with a different writer, two rows at the push and two at the next cycle. The status flips before that cycle, as
        in 28c, so its full leaves rather than deduping on the slot within the repost window (unflipped, the second row
        count reads short). The kernel before the read moved sent one tail per client here."""
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        self.SESS[S1]["events"][3]["md"] = "m3 filled"   # the transcript as T2's build reads it: the NEWER list
        fired = self._build_hosts(lambda: km._push_session_now(S1), inside="m3", after="m3 filled")   # T1 inside T2's build
        km._push_session_now(S1)                         # T2: the baseline absent
        self.assertEqual(fired, [1], "the older targeted push built, sent and seeded inside the newer one's build")
        for cl in (a, b):
            self.assertEqual(self._u3(cl), [("session", "m3"), ("session", "m3 filled")],
                             "T1's noBase full, then T2's change-0 full: every client holds the newer list, nobody is stale")
        self.assertNotIn(S1, km._prev_chat_events, "T2's seed read the baseline absent and found T1's list: popped")
        self.assertNotIn(S1, km._prev_chat_ledger)
        self.assertIn(S1, km._chat_baseline_raced, "...and marked, with no stale holder: the false positive, another writer")
        rows = [r["data"] for r in self._diag_rows("chatFull")]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "T2's full to each base holder, filed as the racing shape")
        self.SESS[S1]["status"]["state"] = "waiting"     # flipped: the frame moved, so the next cycle's full leaves (unflipped it dedups)
        km._built_chat.clear()
        km._push([a, b])                                 # the next cycle: the baseline absent, so every base holder gets the full
        for cl in (a, b):
            self.assertEqual(self._sessions(cl).count(S1), 3, "a third whole frame for a client that was never stale")
            self.assertEqual(self._u3(cl)[-1], ("session", "m3 filled"))
        rows = [r["data"] for r in self._diag_rows("chatFull")[2:]]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "...with its row per base holder")
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle's write clears the mark")
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "and re-establishes the baseline")

    def test_42_the_cycle_as_the_sender_that_read_the_baseline_absent_with_a_seed_inside_its_build_pays_fulls_and_marks_nothing(self):
        """The face outside the pop (the same review): the cycle itself read the baseline absent, and a whole-frame sender
        seeded inside its build. The cycle builds the list with the u3 card pending; inside its build the card fills and
        the targeted push T runs whole, reads the baseline absent, hands a and b a noBase full of the filled list and
        seeds it; then the cycle's build returns the older list, its diff against the absent baseline it read is 0, and
        every base holder gets a change-0 full of the OLDER list with a changeAt0 row. The cycle has no seed step, so
        nothing is popped or marked, and its write puts the older list over T's seed, correctly: that list is what every
        client now holds. The next cycle builds the filled list, diffs against the older baseline and repairs by a tail at
        the change, with no new row. Cost, and a changeAt0 reading on the meter from a race the detector does not mark
        (nothing marked, no strand). The kernel before the read moved read T's seed as a PRESENT baseline after the cycle's
        build and sent the same older list by a tail at the change, no row: this test is red there at the frame assertion,
        the frame shape (tails where the change-0 fulls are), the changed behavior pinned, not a defect it caught."""
        km._PERF_STATS.reset()
        a = self._client(active=S1, proto=2)
        b = self._client(active=S1, proto=2)
        km._clients.extend([a, b])
        fired = self._older_build_hosts(lambda: km._push_session_now(S1))   # T inside the cycle's build, over the filled card
        km._push([a, b])                                 # the cycle: its build read the pending card first; the baseline absent
        self.assertEqual(fired, [1], "the targeted push built, sent and seeded inside the cycle's build")
        for cl in (a, b):
            self.assertEqual(self._u3(cl), [("session", "m3 filled"), ("session", "m3")],
                             "T's noBase full, then the cycle's change-0 full of the OLDER list, not a tail at the change")
        rows = [r["data"] for r in self._diag_rows("chatFull")]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)] * 2, "a changeAt0 row per base holder: the racing shape, from a race the detector does not mark")
        self.assertEqual(self._why().get("changeAt0"), 2, "...and the meter reads two, a race it does not mark")
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle has no seed step: nothing marked")
        self.assertEqual(km._prev_chat_events[S1][3]["md"], "m3",
                         "the cycle's write put its older list over T's seed: the list every client holds")
        km._built_chat.clear()                           # the next cycle rebuilds and reads the filled card
        km._push([a, b])
        for cl in (a, b):
            self.assertEqual(self._sessions(cl).count(S1), 2, "no third whole frame")
            self.assertEqual(self._u3(cl)[-1], ("chatTail", "m3 filled"), "the next cycle repairs by a tail at the change")
        self.assertEqual(len(self._diag_rows("chatFull")), 2, "...with no new row")
        self.assertEqual(self._why().get("changeAt0"), 2, "...and no new count")
        self.assertNotIn(S1, km._chat_baseline_raced)
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "and writes the filled list")

    def test_43_the_cycles_baseline_read_sits_before_the_single_flight_wait(self):
        """The placement half the read-before-build tests leave unpinned (the same review): the cycle's baseline read
        comes before the single-flight wait as well as before the build, so a served list and a built list both diff
        against the baseline as it stood before the iteration read anything. Pinned on frames, not the mark. The targeted
        push T, a sender still mid-flight (its seed step never runs here), read the baseline absent and handed a its full
        with the u3 card pending; the card fills, page b connects, and the cycle for a and b finds another thread
        building S1 and waits; while it waits, b's connect push builds the filled list, hands b its full and seeds. The
        cycle read the baseline before the wait, absent, so the waited-for list goes out as change-0 fulls: a's repairs
        the stale card at once with one changeAt0 row, and b's is the frame its slot already holds, which dedups, so no
        chatTail follows b's full. The mutant that moves the read after the wait reads the connect push's seed as present
        and sends tails: b gets an empty tail after its full, and a keeps the pending card with no row until the next
        cycle. Both placements write the baseline, and neither has set the mark by then."""
        km._PERF_STATS.reset()
        a = self._client(active=S1, proto=2)
        km._clients.append(a)
        real_seed = km._seed_chat_baseline
        km._seed_chat_baseline = lambda sid, m, seen: None   # T's seed step never lands: the sender stays mid-flight
        try:
            km._push_session_now(S1)                     # T: the baseline absent, u3 pending, a full to a
        finally:
            km._seed_chat_baseline = real_seed
        self.assertEqual(self._u3(a), [("session", "m3")], "a holds the pending card from a sender still mid-flight")
        self.assertNotIn(S1, km._prev_chat_events)
        self.SESS[S1]["events"][3]["md"] = "m3 filled"   # the card fills before the cycle
        b = self._client(active=S1, proto=2)
        km._clients.append(b)
        real_claim = km._chat_inflight_claim
        fired = []

        class Waited(threading.Event):
            """The other builder's Event: the wait on it is when b's connect push builds, sends and seeds."""
            def wait(self, timeout=None):
                fired.append(1)
                km._push([b], connect=True)
                return True

        def claim(sid):
            if sid == S1 and not fired:
                return Waited()                          # another thread is building S1: wait for it
            return real_claim(sid)
        km._chat_inflight_claim = claim
        try:
            km._push([a, b])                             # the cycle
        finally:
            km._chat_inflight_claim = real_claim
        self.assertEqual(fired, [1], "the connect push ran inside the cycle's single-flight wait")
        self.assertEqual(self._sessions(b).count(S1), 1, "b's one full, from its connect push")
        self.assertEqual([t for t in self._frames(b, "chatTail") if t["id"] == S1], [],
                         "no chatTail follows b's full: the cycle's identical full dedups on b's slot")
        self.assertEqual(self._u3(a), [("session", "m3"), ("session", "m3 filled")],
                         "a's stale card is repaired by this cycle's change-0 full, not left for the next one")
        rows = [r["data"] for r in self._diag_rows("chatFull")]
        self.assertEqual([(r["reason"], r["changeFrom"], r["firstHeld"], r["lastHeld"]) for r in rows],
                         [("changeAt0", 0, True, True)], "one row, a's")
        self.assertNotIn(S1, km._chat_baseline_raced, "no mark: the mid-flight sender's seed has not run")
        self.assertEqual(km._prev_chat_events[S1], self.SESS[S1]["events"], "the cycle's write, in both placements")

    def test_44_a_targeted_push_under_the_mark_then_an_empty_read_hands_no_base_holder_the_shorter_cached_list(self):
        """The shorter face of the stand-in under the mark (the post-merge review of the mark, 2026-09-21). After the race
        the connect push's 5-event build sits in the cache; a targeted push under the standing mark builds the list grown
        to 7, hands every base holder its full and caches nothing (its seed declines under the mark and raises the count
        to 7). The next cycle's signature misses and its read comes back empty, so the guard reads the mark with a cached
        hit: before the change the 5-event list went to every base holder as a change-0 full and became the baseline, the
        mark came off, and the two newest cards left every pane until the next content cycle's tail, where the kernel
        before the mark's empty frame moved no card. Now no frame for the sid reaches any client, the mark and the absent
        baseline stand, and the next content cycle's full repairs every base holder (the status flipped first, as test 36
        does, so that full is not the targeted push's frame deduping on the slot). Red before the change at the S1-frame
        assertion (a 5-event frame at each client)."""
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        hit = km._built_chat.get(S1)
        self.assertIsNotNone(hit, "premise: the connect push cached its build")
        self.assertEqual(len(hit[1]["events"]), 5, "premise: ...the 5-event list")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u5", "md": "m5"})   # the transcript grows under the mark
        self.SESS[S1]["events"].append({"kind": "assistant", "uuid": "u6", "md": "m6"})
        km._push_session_now(S1)                         # a targeted push under the standing mark: a full to every base holder
        for cl in (a, b):
            self.assertEqual(len([f for f in self._frames(cl, "session") if f["id"] == S1][-1]["events"]), 7,
                             "premise: every base holder was handed the longer list whole")
        self.assertIs(km._built_chat.get(S1), hit, "premise: the targeted push cached nothing, so the 5-event build is still the cache's")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the push's seed declined under the mark")
        self.assertNotIn(S1, km._prev_chat_events, "premise: ...and wrote nothing")
        km._EMPTY_BUILD_NOTED.discard(S1)
        rows0 = len(self._diag_rows("chatFull"))
        a["_frames"].clear(); b["_frames"].clear()
        content = self.SESS[S1]["events"]
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the cycle builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b])                             # the cycle
        for cl in (a, b):
            self.assertEqual([len(f["events"]) for f in self._frames(cl, "session") if f["id"] == S1], [],
                             "no frame for the sid reaches a base holder showing 7 events: the 5-event cache is no stand-in")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "and no chatFull row")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 7 events", err.getvalue(), "...with the count raised by the whole frame handed under the mark")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent: no 5-event list is put down under holders of 7")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0), "one pop counted, no repair yet")
        self.SESS[S1]["events"] = content                # content returns
        self.SESS[S1]["status"]["state"] = "waiting"     # flipped, so the repair's full is not the targeted push's frame deduping on the slot (test 36)
        self._the_cycle_repairs(a, b)                    # the next content cycle's full to every base holder
        for cl in (a, b):
            self.assertEqual(len([f for f in self._frames(cl, "session") if f["id"] == S1][-1]["events"]), 7,
                             "...the 7-event list, whole: no client was ever shown a card older than the one it showed")
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 1), "the repair counted")

    def test_45_the_other_orders_cache_keeps_the_older_list_and_an_empty_read_hands_it_to_nobody(self):
        """The same-length face (the post-merge review of the mark, 2026-09-21), test 24's order: the connect push C (u3
        pending) reads the baseline absent and is about to send b; the targeted push T (u3 filled) runs whole in that
        gap, fulls to a and b, seeds; C's older full lands on b, and C's seed pops. C caches AFTER its sends, so the
        cache keeps the OLDER list with u3 unfilled while a shows the filled card, and a length compare against the
        mark's count cannot tell the two apart. The next cycle's read comes back empty: before the change the older list
        went to both as a change-0 full and became the baseline, so a showed the unfilled card again until the next
        tail. Now no frame for the sid reaches a or b, a keeps the filled card, the mark and the absent baseline stand,
        and the next content cycle's full repairs b (a's identical full dedups on its slot). Red before the change where
        a's last u3 card is asserted still filled."""
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push([b], connect=True),
                           "second": lambda b: km._push_session_now(S1)}, "b")
        hit = km._built_chat.get(S1)
        self.assertIsNotNone(hit, "premise: the connect push cached its build after its sends")
        self.assertEqual(hit[1]["events"][3]["md"], "m3", "premise: ...the OLDER list, u3 unfilled")
        self.assertEqual(len(hit[1]["events"]), 5, "premise: ...of the same length as the filled one")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        self.assertEqual(self._u3(a)[-1], ("session", "m3 filled"), "premise: a shows the filled card (T's full alone reached it)")
        self.assertEqual(self._u3(b)[-1], ("session", "m3"), "premise: b shows the older card (C's full landed last)")
        km._EMPTY_BUILD_NOTED.discard(S1)
        rows0 = len(self._diag_rows("chatFull"))
        content = self.SESS[S1]["events"]
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the cycle builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b])                             # the cycle
        self.assertEqual(self._u3(a)[-1], ("session", "m3 filled"),
                         "a still shows the filled card: the cache's older list is no stand-in under the mark")
        self.assertEqual(self._u3(b)[-1], ("session", "m3"), "b is not repaired by this cycle either: nothing went for the sid")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "no chatFull row")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 5 events", err.getvalue())
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent")
        self.SESS[S1]["events"] = content                # content returns
        self._the_cycle_repairs(a, b)                    # the next content cycle's full: b repaired, a's identical full dedups
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")

    def test_46_a_connect_push_under_the_mark_whose_read_came_back_empty_hands_its_target_no_frame_cached_or_not(self):
        """The connect push as the third road under the mark (the post-merge review of the mark, 2026-09-21): a page
        dialing in for a marked sid whose transcript read comes back empty. With the connect push's build in the cache
        (the filled list after the race), the guard before the change handed the target the cached list as a noBase full;
        with nothing cached its `continue` sent nothing, where the kernel before the mark sent an empty noBase full at
        once. Both arms are the no-frame shape now: the target gets the strip and every other tab, nothing for the marked
        sid until the next content cycle, and the mark and the absent baseline stand (a connect push never clears a
        mark). The cached arm is red before the change (a 5-event frame at the target)."""
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertIsNotNone(km._built_chat.get(S1), "premise: the connect push cached its build")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        self.assertNotIn(S1, km._prev_chat_events, "premise: ...and popped the baseline")
        content = self.SESS[S1]["events"]
        km._EMPTY_BUILD_NOTED.discard(S1)
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the connect push builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        c1 = self._client(active=S1, proto=2)            # the cached arm: the 5-event build is in the cache
        km._clients.append(c1)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([c1], connect=True)
        self.assertNotIn(S1, self._sessions(c1), "the cached arm: no frame for the marked sid reaches the target (the cached list is no stand-in)")
        self.assertIn(S2, self._sessions(c1), "...while the push reached it with the other tabs")
        self.assertNotIn(S1, c1.get("echat") or {}, "the target holds no base for the sid")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent")
        km._built_chat.clear()                           # the no-cache arm
        c2 = self._client(active=S1, proto=2)
        km._clients.append(c2)
        km._push([c2], connect=True)
        self.assertNotIn(S1, self._sessions(c2), "the no-cache arm: nothing for the marked sid either")
        self.assertIn(S2, self._sessions(c2))
        self.assertNotIn(S1, c2.get("echat") or {})
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events)
        self.SESS[S1]["events"] = content                # content returns: the next cycle's full to every base holder and both new pages
        km._built_chat.clear()
        km._push([a, b, c1, c2])
        for cl in (a, b, c1, c2):
            self.assertEqual(self._u3(cl)[-1], ("session", "m3 filled"), "the content cycle's full reaches every client")
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")
        self.assertEqual(km._prev_chat_events.get(S1), content, "and writes the baseline")

    def test_47_the_counters_read_one_pop_and_no_repair_after_a_cycle_that_sent_tails_under_a_mid_loop_mark(self):
        """The counters off the happy path (the post-merge review of the mark, 2026-09-21): test 27's interleaving after a
        collector reset. The cycle that sent tails leaves the mark and skips its write, so it counts no repair, whatever
        it sent; the next cycle, which reads the baseline absent and sends every base holder the full, counts the one.
        Red under a mutant counting a repair wherever the write block finds a mark, the tails cycle included: (1, 1)
        where (1, 0) is read here."""
        km._PERF_STATS.reset()
        a, b = self._tails_cycle_under_a_mid_loop_mark()
        self.assertIn(S1, km._chat_baseline_raced, "premise: the tails cycle left the mark standing")
        self.assertNotIn(S1, km._prev_chat_events, "premise: and wrote nothing")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0),
                         "one pop counted (T's seed step inside the cycle's loop), and the tails cycle counted no repair")
        km._push([a, b])                                 # the next cycle: the baseline absent, a full to every base holder
        self.assertNotIn(S1, km._chat_baseline_raced, "the cycle that sent the fulls clears the mark")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 1), "...and counts the one repair")

    def test_48_the_counters_read_one_pop_and_no_repair_after_a_connect_push_under_the_mark(self):
        """Test 25's connect push under the mark after a collector reset (the post-merge review of the mark, 2026-09-21):
        its seed takes the declining arm, which raises the count and counts nothing, and a connect push never writes or
        clears, so the counters stay at one pop and no repair. Red under a mutant counting a pop in the declining arm:
        (2, 0) where (1, 0) is read here."""
        km._PERF_STATS.reset()
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0), "premise: one pop, no repair")
        km._push([b], connect=True)                      # a needFull or an idle-prefetch release for page b, under the mark
        self.assertEqual(self._u3(b)[-1], ("session", "m3 filled"), "b's own full repairs b (test 25)")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands: the seed declined")
        self.assertNotIn(S1, km._prev_chat_events, "and wrote nothing")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0),
                         "the declining arm counts no pop, and a connect push counts no repair")

    def test_49_the_pops_count_is_the_longer_of_the_two_racing_lists_whichever_was_seeded(self):
        """The count stashed at the pop (the post-merge review of the mark, 2026-09-21), pinned by direct seed calls in
        test 26's shape, since every race fixture pops two lists of equal length: a seeded 5-event list against this
        sender's 6 reads 6, and a seeded 6 against this sender's 5 reads 6 too. The count is the longest list some client
        was handed whole under the mark (its meaning for the note, _chat_prior_n), so it is the longer of the two,
        whichever was in the map. Red under a mutant storing this sender's length alone (5 in the second case) or the
        seeded list's alone (5 in the first)."""
        five = {"id": S1, "events": json.loads(json.dumps(self.SESS[S1]["events"])), "ledger": None}
        six = {"id": S1, "events": json.loads(json.dumps(self.SESS[S1]["events"]))
               + [{"kind": "assistant", "uuid": "u5", "md": "m5"}], "ledger": None}
        km._seed_chat_baseline(S1, five, None)           # the first sender seeds 5
        self.assertEqual(km._prev_chat_events.get(S1), five["events"])
        km._seed_chat_baseline(S1, six, None)            # the second read the map absent before its sends, finds 5 now, pops
        self.assertNotIn(S1, km._prev_chat_events, "the detector popped the seeded list")
        self.assertEqual(km._chat_baseline_raced.get(S1), 6, "seeded 5 against this sender's 6: the count reads 6")
        self.assertEqual(km._chat_prior_n(S1), 6, "...and the note reads it")
        km._chat_baseline_raced.clear()
        km._seed_chat_baseline(S1, six, None)            # the other way round: 6 seeded
        self.assertEqual(km._prev_chat_events.get(S1), six["events"])
        km._seed_chat_baseline(S1, five, None)           # this sender's 5 differs
        self.assertNotIn(S1, km._prev_chat_events)
        self.assertEqual(km._chat_baseline_raced.get(S1), 6, "seeded 6 against this sender's 5: the count reads 6 too")
        self.assertEqual(km._chat_prior_n(S1), 6)

    def test_50_an_empty_read_after_a_cycle_that_sent_tails_under_a_mid_loop_mark_sends_nothing_and_names_the_pops_count(self):
        """Test 27's interleaving, then an empty build with the tails cycle's 6-event build in the cache (the post-merge
        review of the mark, 2026-09-21): the baseline absent and the sid marked while every client holds six events.
        Before the change the cached list went to both as a change-0 full and the write took the mark off (a repaired by
        the stand-in). Now no frame for the sid reaches either client, neither an empty one nor the cached list, the mark
        and the absent baseline stand, and the note names 5: the longest list some client was handed WHOLE under the mark
        is the popped 5-event list, since the tails cycle handed its 6-event list by tails, which raise nothing
        (_chat_prior_n), so the count is a minimum for the note, not what every holder has (6). The next content cycle
        repairs a. Red before the change at the S1-frame assertion."""
        km._PERF_STATS.reset()
        a, b = self._tails_cycle_under_a_mid_loop_mark()
        hit = km._built_chat.get(S1)
        self.assertIsNotNone(hit, "premise: the tails cycle cached its build")
        self.assertEqual(len(hit[1]["events"]), 6, "premise: ...the 6-event list")
        for cl in (a, b):
            self.assertEqual([[e["uuid"] for e in t["events"]] for t in self._frames(cl, "chatTail") if t["id"] == S1], [["u5"]],
                             "premise: every client holds six events, the sixth by a tail")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the mark stands after the tails cycle")
        self.assertNotIn(S1, km._prev_chat_events, "premise: the baseline is absent")
        km._EMPTY_BUILD_NOTED.discard(S1)
        rows0 = len(self._diag_rows("chatFull"))
        a["_frames"].clear(); b["_frames"].clear()
        content = self.SESS[S1]["events"]
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the cycle builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b])                             # the cycle
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1], [],
                             "no frame for the sid: neither an empty one nor the cached 6-event list as a stand-in")
            self.assertEqual([t for t in self._frames(cl, "chatTail") if t["id"] == S1], [], "and no tail")
        self.assertNotIn("empty", self._why(), "no full counted as `empty`")
        self.assertEqual(len(self._diag_rows("chatFull")), rows0, "and no chatFull row")
        self.assertIn("came back EMPTY", err.getvalue(), "the failed read is said on stderr")
        self.assertIn("its clients hold at least 5 events", err.getvalue(),
                      "the pop's count: the tails cycle handed nothing whole, so its 6 never raised it (a minimum, not every holder's 6)")
        self.assertIn("sending nothing for it until content returns", err.getvalue(),
                      "the marked wording: no build is kept under the mark, and none is sent")
        self.assertNotIn("keeping the previous build", err.getvalue(), "not the seeded road's words")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 0), "one pop counted, no repair yet")
        self.SESS[S1]["events"] = content                # content returns
        self._the_cycle_repairs(a, b)                    # the next content cycle's full to every base holder
        self.assertNotIn(S1, km._chat_baseline_raced, "...and its write takes the mark off")
        chat = km._PERF_STATS.snapshot()["builds"]["chat"]
        self.assertEqual((chat["baselineRaced"], chat["baselineRepaired"]), (1, 1), "the repair counted")

    def test_51_an_empty_read_under_the_mark_with_a_cached_build_keeps_the_sessions_outline_row(self):
        """The Outline row under the mark (the review of this change, 2026-09-21). The feed frame's `ledgers` list is
        built from the cycle's `chat_sessions`, and the Outline pane replaces its rows wholesale on every feed frame; the
        first cut of this change took the no-cache road under the mark with a cached build too, and that `continue`
        skipped the append, so on the empty cycle the session's row left the Outline and came back with the next content
        cycle, a payload change driven by a failed transcript read (the stand-in road kept the row, since the stand-in
        rode into the list). Now the cached build still rides `chat_sessions` for its ledger while no frame goes for the
        sid and the write block is skipped. Green at the base (the stand-in road), red at this change's first cut (the
        sid missing from the Outline's ledgers on the empty cycle)."""
        feed = {"type": "feed", "items": [], "asks": [], "working": [], "awaiting": [], "stateUnknown": [], "order": [],
                "sessions": [], "hosts": [], "pendingHosts": [], "pendingDead": []}
        km._cached_feed = lambda *a, **k: json.loads(json.dumps(feed))   # a feed build, so the ledgers attach runs (tearDown restores)
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertIsNotNone(km._built_chat.get(S1), "premise: the connect push cached its build")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        o = self._client(app="fleet")                    # the Outline pane, dialing in for the empty cycle
        km._clients.append(o)
        km._EMPTY_BUILD_NOTED.discard(S1)
        a["_frames"].clear(); b["_frames"].clear()
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses and the cycle builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            km._push([a, b, o])                          # the cycle
        feeds = self._frames(o, "feed")
        self.assertTrue(feeds, "the Outline got its feed frame: %r" % [f["type"] for f in o["_frames"]])
        rows = [r["sid"] for r in feeds[-1]["ledgers"]]
        self.assertIn(S1, rows, "the marked session keeps its Outline row on the empty cycle: the cached build's ledger rides the list")
        self.assertEqual(set(rows), set(TAB_ORDER), "...beside every other tab's row")
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1], [], "while no frame for the sid goes to a base holder")
        self.assertIn("came back EMPTY", err.getvalue())
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")
        self.assertNotIn(S1, km._prev_chat_events, "the baseline stays absent")

    def test_52_the_empty_cycle_under_the_mark_releases_the_single_flight_claim_before_the_next_tab(self):
        """The single-flight release inside the widened guard branch (the review of this change, 2026-09-21). A cycle whose
        signature misses claims the sid's build (single-flight: a second thread building the same tab waits on the
        claim), and the `continue` under the mark skips the loop's tail, where the claim is normally released. The
        thread's scope close after the loop releases whatever a raise left, so a recorder over the release alone sees
        the sid with the branch's release dropped too; the pin is WHEN: at the loop's first send for another tab, after
        the marked tab's iteration, the claim is gone from the inflight map and the release was recorded already. With
        the branch's release dropped the claim stands until the scope close, and a builder of the same tab on another
        thread would wait the whole bound for the rest of this push. Red under that mutant."""
        a, b = self._race({"first": lambda b: km._push_session_now(S1),
                           "second": lambda b: km._push([b], connect=True)}, "a")
        self.assertIsNotNone(km._built_chat.get(S1), "premise: the connect push cached its build")
        self.assertIn(S1, km._chat_baseline_raced, "premise: the race marked the sid")
        km._EMPTY_BUILD_NOTED.discard(S1)
        with open(self.paths[S1], "a") as f:
            f.write("x" * 10)                            # the transcript grew: the signature misses, the cycle claims and builds
        self.SESS[S1]["events"] = []                     # ...and the read comes back empty
        del self.built[:]
        real_done, real_send = km._chat_inflight_done, km._send_chat_or_status
        trail = []

        def record(sid):
            trail.append(("done", sid))
            return real_done(sid)

        def at_next_tab(cl, m, ms, change_from, led_changed):
            """The loop's first send for a tab other than the marked one: the marked tab's iteration is over."""
            if m["id"] != S1 and not any(t[0] == "send" for t in trail):
                trail.append(("send", m["id"], S1 in km._CHAT_INFLIGHT,
                              S1 in (getattr(km._live_scope, "chat_claims", None) or [])))
            return real_send(cl, m, ms, change_from, led_changed)
        km._chat_inflight_done, km._send_chat_or_status = record, at_next_tab
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                km._push([a, b])                         # the cycle
        finally:
            km._chat_inflight_done, km._send_chat_or_status = real_done, real_send
        self.assertIn(S1, self.built, "premise: the cycle built the marked tab (its signature missed, so it claimed)")
        sends = [t for t in trail if t[0] == "send"]
        self.assertEqual(len(sends), 1, "the loop went on to another tab: %r" % (trail,))
        self.assertEqual(sends[0][2:], (False, False),
                         "at the next tab's first send the claim is gone from the inflight map and this thread's scope: %r" % (trail,))
        self.assertLess(trail.index(("done", S1)), trail.index(sends[0]),
                        "...released inside the guard's branch, before the loop moved on, not by the scope close after it: %r" % (trail,))
        for cl in (a, b):
            self.assertEqual([f for f in self._frames(cl, "session") if f["id"] == S1 and not f.get("events")], [],
                             "and no empty frame went")
        self.assertIn(S1, km._chat_baseline_raced, "the mark stands")


class RestartDiet(unittest.TestCase):
    """The user's ruling (2026-09-14): after a reload the selected tab builds first, the strip's other tabs spread over later refreshes,
    hidden tabs not until shown; and restarts are invisible, so the one reload the reload core fires is the one the user accepts when a
    newer build is offered (2026-09-16), a fresh page on a kernel that has the build. The client half: the main chat pane's FIRST dial after any reload the core fired is a skeleton
    dial (the later column's shape), so the kernel's existing handshake serves the strip with the skeleton set, one full for the active
    tab and a status per other tab; a redial carries the diet through reconnect=1 as before. Pinned in the served shim's source: the
    reload core keeps the reason and the document's path in a durable record (announce() removes the announce record before a pane
    dials, and a pane inside the shell never announces); the chat shim alone reads it, removes it BEFORE parsing (a malformed record is
    consumed too), and dials skeleton=1 on its first socket when the record names the shell or a chat document; a column and a skeleton
    view leave the record alone; every other pane's shim carries the false alone; the kernel arms the term for a chat socket only."""

    def test_the_first_dial_after_a_restart_reload_is_a_skeleton_dial(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        fire = src[src.index("function fire(){"):src.index("var heldFor=null;")]
        self.assertIn("sessionStorage.setItem('romp:reloadReason',JSON.stringify({reason:owed.reason,path:location.pathname,t:Date.now()}))", fire,
                      "the reload core keeps the reason and the document's path durably when it fires (the announce record is consumed before the panes dial)")
        chat, feed = km._shim("chat"), km._shim("feed")
        self.assertIn("""var RESTART_DIET=false;if(!COL&&!SKEL){var rr=null;try{var raw=sessionStorage.getItem('romp:reloadReason');sessionStorage.removeItem('romp:reloadReason');rr=raw?JSON.parse(raw):null;}catch(e){}RESTART_DIET=!!(rr&&typeof rr==='object'&&typeof rr.reason==='string'&&(rr.path===undefined||rr.path==='/'||String(rr.path).indexOf('/chat')===0));}""", chat,
                      "the chat shim removes the record BEFORE parsing it and dials the diet on any reload the core fired for the shell or a chat document, only for an object with the fields (a scalar is consumed and diets nothing): a main pane, not a column, not a skeleton view")
        self.assertIn("sessionStorage.setItem('romp:reloadReason',JSON.stringify({reason:owed.reason,path:location.pathname,t:Date.now()}))", src,
                      "the reload core's record names the document that reloaded, so a standalone feed page's reload steers no chat dial")
        read = "sessionStorage.getItem('romp:reloadReason')"   # the READ; the reload core's write of the record rides every page's shim
        self.assertNotIn(read, feed, "a non-chat pane's shim never reads the record (round two, medium 2)")
        self.assertIn("var RESTART_DIET=false;", feed, "…it carries the false alone, so the shared dial line still compiles")
        for other in ("fleet", "files", "timeline", "settings"):
            self.assertNotIn(read, km._shim(other), other)
        self.assertIn('skeleton = (q.get("skeleton") or [""])[0] == "1" and app == "chat"', src, "the kernel arms the skeleton diet for a chat socket alone (round two, medium 2)")
        self.assertIn("""((SKEL||(RESTART_DIET&&!everConnected))?"&skeleton=1":"")""", src,
                      "the dial carries skeleton=1 for a column, or for the main pane's FIRST socket after a restart reload (a redial dials as before)")
        # the kernel side the dial lands on is unchanged and already pinned above: skeleton=1 without reconnect arms skeletonOnReady at the
        # handshake, and the ready arm serves the strip with the skeleton set, one full for the active tab, a status per other tab
        self.assertIn('client["skeletonOnReady"] = True', src)

if __name__ == "__main__":
    unittest.main()
