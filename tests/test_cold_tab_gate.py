#!/usr/bin/env python3
"""The cold-tab gate (2026-09-14): a tab no connected page is looking at is not built on a cold kernel.

On the 3:58 PM PT restart (2026-09-13) the first refresh with a browser built the chat of all 27 tabs, 54.6 s of a 72.4 s
refresh, before the cards and the timeline left, for one tab on screen; and each of the 27 attach handshakes at boot ran
a per-session push, a cold build per session. The user's ruling: the selected tab first, the tabs present in the strip
next over later refreshes, hidden tabs never until shown. The client half (romp_chat) makes the restart reload dial the
skeleton diet; this half makes the kernel honour it in the pusher's loop and in the per-session push: a tab with a
transcript, not built since the boot, that every connected chat page holds as a skeleton, is not built. The page's click
or idle prefetch releases the skeleton first, and that push builds it. A warm tab, a Sessions pane, a page that declared no
diet: as before. Drives the REAL _push and _push_session_now over fake clients with build_session stubbed and counted, real
temp transcript files (the size is the kernel's ranking); synthetic only (the notes-api demo world, placeholder ids)."""
import inspect
import json
import os
import tempfile
import time
from unittest import mock
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
with open(os.path.join(os.environ["XDG_STATE_HOME"], "romp", "session-hosts"), "w") as _f:
    _f.write("off")                       # a minted state root pins the hosts off (the 2026-09-11 rule; the fold's low f)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_cold_tab_gate", os.path.join(BIN, "romp-kernel"))

S1 = "11111111-2222-3333-4444-666666666661"   # web   — the tab the page is looking at
S2 = "11111111-2222-3333-4444-666666666662"   # api   — the biggest transcript
S3 = "11111111-2222-3333-4444-666666666663"   # tests — the smallest transcript
S4 = "11111111-2222-3333-4444-666666666664"   # docs  — just created: no transcript on disk
NAMES = {S1: "web", S2: "api", S3: "tests", S4: "docs"}
TAB_ORDER = [S2, S1, S3, S4]
SIZES = {S2: 3000, S1: 2000, S3: 1000}


U_PROMPT = "11111111-2222-3333-4444-000000000001"


def _api_error_tail(path, text="API Error: 500 server_error"):
    """A transcript whose LAST productive record is an api error (Claude Code's isApiErrorMessage flag, the exact invariant
    _api_error reads): a user prompt, then the failed assistant record. Synthetic."""
    recs = [{"type": "user", "uuid": U_PROMPT, "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]}},
            {"type": "assistant", "uuid": "aaaaaaaa-0000-0000-0000-000000000001", "parentUuid": U_PROMPT,
             "isApiErrorMessage": True, "apiErrorStatus": 500, "error": "server_error",
             "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}]
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def _sess(sid, n, state):
    return {"type": "session", "id": sid, "name": NAMES[sid],
            "events": [{"kind": "assistant", "uuid": "u%d" % i, "md": "m%d" % i} for i in range(n)],
            "status": {"state": state, "sinceEpoch": None}, "ledger": None}


class ColdTabGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid, n in SIZES.items():
            p = os.path.join(self.tmp, sid + ".jsonl")
            with open(p, "w") as f:
                f.write("x" * n)
            self.paths[sid] = p
        self.paths[S4] = os.path.join(self.tmp, S4 + ".jsonl")   # never written
        self.SESS = {S1: _sess(S1, 5, "working"), S2: _sess(S2, 7, "working"),
                     S3: _sess(S3, 3, "waiting"), S4: _sess(S4, 0, "waiting")}
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
                       km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients))
        km._chat_tab_sessions = lambda now, live_map: [
            {"sid": sid, "name": NAMES[sid], "path": self.paths[sid], "anchor": sid} for sid in TAB_ORDER]
        # live rows for every session: the gate states a skeleton tab's status from the row, so without one it builds
        self.live = {sid: {"state": "working" if sid in (S1, S2) else "waiting", "since": 1781100000, "model": "", "effort": "",
                           "mode": "", "backend": "sdk"} for sid in TAB_ORDER}
        km._live_map = lambda: dict(self.live)
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
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        del km._clients[:]
        km._pusher_wake.clear()
        km._PERF_STATS.reset()
        self.skip0 = km._VIEW_STATS.get("chatSkipCold", 0)   # .get: at a base without the counter the failure lands in the test, after setUp, so tearDown runs

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
         km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, clients) = self._saved
        del km._clients[:]; km._clients.extend(clients)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        km._PERF_STATS.reset()

    def _client(self, app="chat", **kw):
        frames = []
        c = {"app": app, "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)), "_frames": frames}
        c.update(kw)
        return c

    @staticmethod
    def _frames(c, typ):
        return [f for f in c["_frames"] if f["type"] == typ]

    def _skipped(self):
        return km._PERF_STATS.snapshot()["builds"]["chat"]["coldSkipped"]

    def test_01_a_skeleton_page_on_a_cold_kernel_gets_only_its_tab_built(self):
        c = self._client(reconnect=True, active=S1)          # the restart reload's dial: the diet, and the tab on screen
        km._clients[:] = [c]
        km._push([c])
        self.assertEqual(sorted(self.built), sorted([S1, S4]), "the watched tab and the transcript-less one: %r" % self.built)
        self.assertEqual([f["id"] for f in self._frames(c, "session")], [S1, S4])
        strip = self._frames(c, "tabOrder")[0]
        self.assertEqual(strip["skeleton"], [S3, S2], "the skeleton set, smallest transcript first, as before")
        statuses = {f["id"]: f["status"] for f in self._frames(c, "status")}
        self.assertEqual(set(statuses), {S2, S3}, "a status per skeleton tab still goes, from the live row")
        self.assertEqual((statuses[S2]["state"], statuses[S3]["state"]), ("working", "ready"), "the row's word: working, waiting -> ready")
        self.assertTrue(all(st.get("provisional") for st in statuses.values()), "marked provisional until the tab's first build")
        self.assertEqual(statuses[S2]["sinceEpoch"], 1781100000 * 1000)
        for k in ("apiTooLong", "apiSpendLimit", "apiModelLimit", "apiAuthErr", "apiRefusal", "awaitingWhy", "awaitingKind",
                  "retrySuppressed", "retryNextAt", "backend", "model"):
            self.assertIn(k, statuses[S3], "the on-you and awaiting keys ride the provisional status: %s" % k)
        self.assertEqual(self._skipped(), 2)
        self.assertEqual(km._VIEW_STATS["chatSkipCold"] - self.skip0, 2)

    def test_02_a_page_that_declared_no_diet_is_served_whole_as_today(self):
        c = self._client(active=S1)                          # no reconnect, no skeleton term: a fresh page
        km._clients[:] = [c]
        km._push([c])
        self.assertEqual(sorted(self.built), sorted(TAB_ORDER))
        self.assertEqual(self._skipped(), 0)

    def test_03_one_page_holding_the_tab_whole_means_it_is_built_for_both(self):
        a = self._client(reconnect=True, active=S1)
        b = self._client(active=S2)                          # a second dashboard looking at the big tab, no diet
        km._clients[:] = [a, b]
        km._push([a, b])
        self.assertEqual(sorted(self.built), sorted(TAB_ORDER), "b holds no set, so every tab is built: %r" % self.built)
        self.assertEqual({f["id"] for f in self._frames(a, "status")}, {S3, S2}, "a's skeleton tabs still get their status frames")
        self.assertEqual(self._skipped(), 0)

    def test_04_a_sessions_pane_needs_every_ledger_so_nothing_is_skipped(self):
        c = self._client(reconnect=True, active=S1)
        sessions_pane = self._client(app="fleet")       # the pane's existing app id on the wire
        km._clients[:] = [c, sessions_pane]
        km._push([c, sessions_pane])
        self.assertEqual(sorted(self.built), sorted(TAB_ORDER))
        self.assertEqual(self._skipped(), 0)

    def test_05_a_warm_kernel_serves_and_status_frames_the_skeleton_tabs_as_before(self):
        fresh = self._client(active=S1, ready=True, proto=2)  # the same render floor as the redial below, so the
        km._clients[:] = [fresh]                             #  cached builds' signatures hold across the two pushes
        km._push([fresh])                                    # warms _built_chat for every tab
        self.assertEqual(sorted(self.built), sorted(TAB_ORDER))
        del self.built[:]
        c = self._client(reconnect=True, active=S1, proto=2)
        km._clients[:] = [c]
        km._push([c])
        self.assertEqual(self.built, [], "every tab is served from the cache")
        self.assertEqual({f["id"] for f in self._frames(c, "status")}, {S3, S2}, "the cached builds' statuses go, as before")
        self.assertFalse(any(f["status"].get("provisional") for f in self._frames(c, "status")), "the built statuses, not the row's")
        self.assertEqual(self._skipped(), 0)

    def test_06_the_per_session_push_skips_a_cold_skeleton_tab_and_builds_it_once_released(self):
        c = self._client(reconnect=True, active=S1)
        km._clients[:] = [c]
        km._push([c])                                        # resolves the set: S3 and S2 are skeletons
        del self.built[:]
        n_status = len(self._frames(c, "status"))
        km._push_session_now(S2)                             # the attach handshake's push for a tab the page holds as a skeleton
        self.assertEqual(self.built, [], "not built: the page did not ask for it")
        self.assertEqual([f["id"] for f in self._frames(c, "session")], [S1, S4], "and no full was handed over")
        self.assertEqual(len(self._frames(c, "status")), n_status, "the same live status is deduped on its slot")
        self.assertEqual(self._skipped(), 3, "two in the refresh, one here")
        km._release_skeleton(c, S2)                          # the click or the prefetch
        km._push_session_now(S2)
        self.assertEqual(self.built, [S2], "released, the push builds it")
        self.assertIn(S2, [f["id"] for f in self._frames(c, "session")])

    def test_07_the_per_session_push_builds_a_transcript_less_tab_and_a_tab_some_page_holds_whole(self):
        c = self._client(reconnect=True, active=S1)
        km._clients[:] = [c]
        km._push([c])
        del self.built[:]
        km._push_session_now(S4)                             # a just-created session: never a skeleton, built as before
        self.assertEqual(self.built, [S4])
        b = self._client(active=S2)                          # a page holding S2 whole joins
        km._clients[:] = [c, b]
        del self.built[:]
        km._push_session_now(S2)
        self.assertEqual(self.built, [S2], "one page holds it whole: built")

    def test_07b_a_tab_with_no_live_row_is_built_as_before(self):
        self.live.pop(S2)                                    # the kernel cannot state S2's status without a build
        c = self._client(reconnect=True, active=S1)
        km._clients[:] = [c]
        km._push([c])
        self.assertEqual(sorted(self.built), sorted([S1, S2, S4]), "S2 built (no row), S3 gated: %r" % self.built)
        self.assertEqual(self._skipped(), 1)

    def _skeleton_push(self):
        c = self._client(reconnect=True, active=S1)
        km._clients[:] = [c]
        km._push([c])
        return c, {f["id"]: f["status"] for f in self._frames(c, "status")}

    def test_08_the_targeted_push_carries_the_comments_frame_so_a_mark_lands_with_its_turn(self):
        # THE KERNEL-ASYMMETRY FIX (2026-09-23, plans/tab-state-badge.md): the {type:"comments"} frame rode ONLY the full
        # pusher cycle, so a page that connected before the session was alive got the chat frame from this targeted push
        # but the comments frame a whole cycle later (tens of seconds under load), and a comment's mark trailed its turn.
        # _push_session_now now rides the comments frame too, on the same per-sid dedup slot. Stub _comments_frame to
        # answer for ONE session; the targeted push for it must deliver that frame to the chat client.
        fr = {"type": "comments", "id": S2, "threads": [{"tid": "t1", "anchorUuid": "a1", "exact": "x"}]}
        km._comments_frame = lambda sid, live_map: fr if sid == S2 else None
        c = self._client()
        km._clients[:] = [c]
        km._push_session_now(S2)
        got = self._frames(c, "comments")
        self.assertEqual([f["id"] for f in got], [S2], "the targeted push delivered the comments frame for this session")
        self.assertEqual(got[0]["threads"][0]["anchorUuid"], "a1", "the frame is the one _comments_frame built")
        # a session that never had a thread (_comments_frame None) rides no comments frame on the targeted push
        c2 = self._client()
        km._clients[:] = [c2]
        km._push_session_now(S1)
        self.assertEqual(self._frames(c2, "comments"), [], "a storeless session's targeted push carries no comments frame")

    def test_09a_an_api_error_tail_reads_blocked_provisionally_as_it_would_built(self):
        _api_error_tail(self.paths[S3])                      # S3's transcript ends in an api error; its row is idle
        c, statuses = self._skeleton_push()
        self.assertNotIn(S3, self.built, "still not built")
        self.assertEqual(statuses[S3]["state"], "blocked", "the built chip's api-error leg, from the same cached tail read")
        self.assertTrue(statuses[S3]["provisional"])
        self.assertEqual((statuses[S3]["apiTooLong"], statuses[S3]["apiSpendLimit"], statuses[S3]["apiAuthErr"],
                          statuses[S3]["apiRefusal"], statuses[S3]["apiModelLimit"]), (False, False, False, False, False),
                         "a transient 500: none of the on-you flags")
        self.assertEqual(statuses[S2]["state"], "working", "a working row is never read as blocked: the api-error leg is gated on idle")

    def test_09b_a_prompt_too_long_error_carries_the_on_you_flag(self):
        _api_error_tail(self.paths[S3], text="API Error: 400 prompt is too long: 250000 tokens > 200000 maximum")
        c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "blocked")
        self.assertTrue(statuses[S3]["apiTooLong"], "the on-you leg the built chip paints red rides the provisional status")

    def test_09c_an_awaited_background_task_reads_awaitingbg_with_its_why(self):
        aw = {"kind": "agents", "why": "waiting on 2 agents", "since": 1781100000, "count": 2,
              "items": [{"kind": "agent", "id": "a1", "label": "one"}, {"kind": "agent", "id": "a2", "label": "two"}]}
        def awaiting(sid, path, idle, stamp=False):
            return dict(aw) if sid == S3 else None
        with mock.patch.object(km, "_session_awaiting", awaiting):   # the built chip's own source (stamps and rows: a store read)
            c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "awaitingBg")
        self.assertEqual((statuses[S3]["awaitingWhy"], statuses[S3]["awaitingKind"], statuses[S3]["awaitingCount"]),
                         ("waiting on 2 agents", "agents", 2))
        self.assertEqual(len(statuses[S3]["awaitingItems"]), 2)
        self.assertEqual(statuses[S2]["state"], "working", "a working row is not asked about awaiting: an active turn is working")

    def test_09d_compacting_follows_the_built_chips_order(self):
        """Round four, low c: the backend's bracket when it states one; else the row's word, disproved by a compact boundary
        since the row's since (a tail read), the open turn standing in by the row's working."""
        self.live[S3]["state"] = "compacting"
        c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "compacting", "no bracket, a compacting row, no boundary since: the row's word holds")
        del km._clients[:]; km._built_chat.clear()
        class _No:
            def compacting(self, sid):
                return False                                 # the backend states the bracket is closed
        with mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: _No())):
            c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "ready", "a stated bracket outranks the row's word")
        del km._clients[:]; km._built_chat.clear()
        with open(self.paths[S3], "a") as f:                   # a compaction landed after the row's since: over
            f.write("\n" + json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "cccccccc-0000-0000-0000-000000000009",
                                       "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(1781100000 + 60))}) + "\n")
        c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "ready", "a boundary since the row's since disproves the row's word")

    def test_12_a_click_between_the_decision_and_the_send_leaves_the_full_last(self):
        """Round three, low b, executed (round four, low b): the real _push over a client whose click lands INSIDE the gate's
        decision, releasing the tab's skeleton and sending the full the click asked for; the gate's status send finds the tab
        released and sends nothing, so the raced tab's frames end at the full. The same for _push_session_now."""
        c = self._client(reconnect=True, active=S1)
        km._clients[:] = [c]
        real = km._light_status
        def clicking(sid, path, tm, now):
            light = real(sid, path, tm, now)
            if sid == S2:                                    # the click: the page releases the skeleton and asks for the full,
                km._release_skeleton(c, S2)                  #  which lands on the ("chat", S2) slot before the gate's send
                with km._client_lock(c):
                    km._send_client(c, ("chat", S2), {"type": "session", "id": S2, "name": "api", "events": [], "status": {"state": "working"}})
            return light
        with mock.patch.object(km, "_light_status", clicking):
            km._push([c])
        kinds = [(f["type"], f["id"]) for f in c["_frames"] if f.get("id") == S2]
        self.assertEqual(kinds[-1], ("session", S2), "the raced tab's frames end at the full, never a provisional status after it: %r" % kinds)
        self.assertNotIn(("status", S2), kinds)
        self.assertIn(S3, {f["id"] for f in self._frames(c, "status")}, "the tab nobody clicked still got its provisional status")
        # the per-session push, the same race
        km._built_chat.clear(); del c["_frames"][:]; c["sent"].clear(); c["skeleton"] = {S2, S3}; c["skeletonOrder"] = [S3, S2]   # a fresh page's state
        with mock.patch.object(km, "_light_status", clicking):
            km._push_session_now(S2)
        kinds = [(f["type"], f["id"]) for f in c["_frames"] if f.get("id") == S2]
        self.assertEqual(kinds[-1], ("session", S2), "the handshake push too: %r" % kinds)
        self.assertNotIn(("status", S2), kinds)

    def test_10_the_handshake_push_resolves_the_set_before_it_decides(self):
        """Round two, low 1: a skeleton client whose redial the pusher has not reached yet holds no set at the handshake push;
        the gate read that as holding nothing and handed the page a full it never asked for. The set is resolved first."""
        c = self._client(reconnect=True, active=S1)         # dialed the diet; no pusher cycle has run yet
        km._clients[:] = [c]
        km._push_session_now(S2)                             # the attach handshake's push
        self.assertEqual(self.built, [], "not built: the set resolved first and S2 is in it")
        self.assertIsNone(getattr(km._SEND_ROAD, "name", None),
                          "the cold-skip early return resets the road mark too (2026-09-19 review: the dispatch thread runs other pushes)")
        strip = self._frames(c, "tabOrder")[0]
        self.assertEqual(strip["skeleton"], [S3, S2], "the strip carried the set")
        self.assertEqual([f["id"] for f in self._frames(c, "session")], [], "no full handed over")
        self.assertEqual([f["id"] for f in self._frames(c, "status")], [S2], "its provisional status instead")
        sends = km._PERF_STATS.snapshot()["sends"]["full"]        # every frame of this push reads under its road (2026-09-19)
        self.assertEqual((sends.get("status.targeted") or {}).get("count"), 1, "the gate's status is counted under status.targeted: %r" % sends)
        self.assertNotIn("status", sends, "not under the pusher's plain slot")
        self.assertEqual((sends.get("taborder.targeted") or {}).get("count"), 1, "the strip too")

    def test_11_the_gate_reads_every_connected_client_not_only_this_pushs_targets(self):
        """Round two, low 2: a connect push targets one column; another connected column's watched tab must not be skipped."""
        a = self._client(reconnect=True, active=S1)
        b = self._client(reconnect=True, active=S3)          # a second column, looking at S3
        km._clients[:] = [a, b]
        km._push([a], connect=True)                          # a's connect push alone
        self.assertIn(S3, self.built, "b's watched tab is built even though b is not a target: %r" % self.built)
        self.assertNotIn(S2, self.built, "S2, held as a skeleton by both, is skipped")
        del self.built[:]
        km._built_chat.clear()
        sessions_pane = self._client(app="fleet")            # a Sessions pane connected but not among the targets
        km._clients[:] = [a, b, sessions_pane]
        km._push([a], connect=True)
        self.assertEqual(sorted(self.built), sorted(TAB_ORDER), "a connected Sessions pane disables the gate for every push")

    def test_08_the_gate_reads_each_set_under_the_clients_lock_and_the_docs_name_the_counter(self):
        src = inspect.getsource(km._held_as_skeleton_by_all)
        self.assertIn("with _client_lock(c):", src)
        self.assertFalse(km._held_as_skeleton_by_all(S2, []), "no client, no gate")
        for fn in (km._push, km._push_session_now):
            self.assertIn("_held_as_skeleton_by_all(", inspect.getsource(fn), fn.__name__)
        self.assertLess(inspect.getsource(km._push).index("_held_as_skeleton_by_all("),
                        inspect.getsource(km._push).index("sig = _chat_build_sig(s, _tm, now, live_map=live_map)"),
                        "the gate stands before the signature and the build")
        doc = open(os.path.join(os.path.dirname(HERE), "docs", "reference.md"), encoding="utf-8").read()
        self.assertIn("`coldSkipped`", doc)


class ProvisionalLegsMatchBuilt(unittest.TestCase):
    """Round three (the medium): over constructed legs, the provisional status equals the REAL built status on every key the
    skeleton chip painter reads (tab-widgets.ts and render.ts: the state, the five on-you flags, faded, ctx, ctxColor and
    ctxTone), plus the tints. A real session on disk (the snapshot test's fixture shape), the real build_session."""
    PAINTER_KEYS = ("state", "apiTooLong", "apiSpendLimit", "apiModelLimit", "apiAuthErr", "apiRefusal", "faded", "ctx", "ctxColor",
                    "ctxTone", "ctxOver", "needsYou", "needsYouCount", "modelColor", "effortColor", "modelTone", "effortTone")

    @staticmethod
    def _painter_keys_from_source():
        """The status fields the skeleton chip painter reads, taken from the page's source (round four, low a): the strip
        signature's skeleton branch in render.ts (kst?.X), the fields tabStateClass reads in tab-state.ts (s!.X) and the
        widget status fields (ctx, ctxColor, ctxTone, faded). The class's tuple must cover them, so it cannot go green while
        a painter key disagrees."""
        import re as _re
        ui = os.path.join(os.path.dirname(HERE), "ui", "webview")
        render = open(os.path.join(ui, "render.ts"), encoding="utf-8").read()
        i = render.index('renderKind(skeletonTabs, id, !!s) === "skeleton"'); j = render.index("makePlaceholderTab's reads", i)
        keys = set(_re.findall(r"kst\?\.(\w+)", render[i:j]))
        state = open(os.path.join(ui, "tab-state.ts"), encoding="utf-8").read()
        k = state.index("export function tabStateClass"); l = state.index("\n}\n", k)
        keys |= set(_re.findall(r"s[!?]\.(\w+)", state[k:l]))
        widgets = open(os.path.join(ui, "tab-widgets.ts"), encoding="utf-8").read()
        m = _re.search(r"interface WidgetStatus extends TabStateLike \{([^}]*)\}", widgets)
        keys |= set(_re.findall(r"(\w+)\?:", m.group(1))) if m else set()
        return keys

    def test_the_painter_key_list_covers_every_field_the_page_reads(self):
        src_keys = self._painter_keys_from_source()
        self.assertTrue(src_keys, "the source scan found the painter's reads")
        for k in ("state", "needsYou", "faded", "ctx", "ctxColor", "ctxTone", "apiTooLong"):
            self.assertIn(k, src_keys, "the scan reads the known fields: %s" % k)
        self.assertTrue(src_keys <= set(self.PAINTER_KEYS), "painter keys the class does not compare: %r" % sorted(src_keys - set(self.PAINTER_KEYS)))

    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); td = Path(self.td.name)
        jd = km.jd
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE, km.NAMES, km.Sessions.live, km._sdk)
        names = td / "names"; names.mkdir(); proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        for d in (jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR):
            d.mkdir()
        jd.STATE = td; km.NAMES = names; km._sdk = lambda: None
        cdir = td / "work"; cdir.mkdir()
        import re as _re
        pdir = proj / _re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir))); pdir.mkdir(parents=True)
        self.path = str(pdir / (S3 + ".jsonl"))
        (names / S3).write_text("%s\t%s\t#abcdef\n" % ("tests", str(cdir)))
        self.now = int(time.time())

    def tearDown(self):
        jd = km.jd
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE, km.NAMES, km.Sessions.live, km._sdk) = self.saved
        km._live_scope.snapshot = None
        self.td.cleanup()

    def _plain_transcript(self):
        recs = [{"type": "user", "uuid": U_PROMPT, "timestamp": "2026-06-11T00:00:00.000Z", "promptSource": "typed",
                 "message": {"role": "user", "content": "hello there"}},
                {"type": "assistant", "uuid": "aaaaaaaa-0000-0000-0000-000000000002", "parentUuid": U_PROMPT,
                 "timestamp": "2026-06-11T00:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}}]
        with open(self.path, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        self._idle_after(recs[-1]["timestamp"])

    def _idle_after(self, iso):
        """The states log's idle transition after the last record: the event model closes the turn on it, so the built chip
        reads the transcript as idle (an open last turn reads working, by design, whatever the row says)."""
        import datetime as _dt
        t = _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=_dt.timezone.utc).timestamp()
        sd = Path(km.jd.STATE) / "states"; sd.mkdir(exist_ok=True)
        (sd / (S3 + ".jsonl")).write_text(json.dumps({"t": t + 10, "state": "idle"}) + "\n")

    def _row(self, **kw):
        row = {"state": "waiting", "since": self.now - 30, "model": "claude-sonnet-5", "effort": "high", "context": 37, "ctxOver": False,
               "mode": "", "compactPct": None, "color": None, "backend": "sdk"}
        row.update(kw)
        return row

    def _legs(self, row):
        live = {S3: row}
        km.Sessions.live = lambda: dict(live)
        km._live_scope.snapshot = None
        built = km.build_session(S3, self.now, live)["status"]
        light = km._light_status(S3, self.path, row, self.now)
        return {k: built.get(k) for k in self.PAINTER_KEYS}, {k: light.get(k) for k in self.PAINTER_KEYS}

    def test_the_painter_keys_agree_on_every_leg(self):
        legs = []
        self._plain_transcript(); legs.append(("idle, context 37", self._row()))
        legs.append(("idle, over the window", self._row(context=100, ctxOver=True)))
        legs.append(("idle, no context", self._row(context=None)))
        legs.append(("faded: idle for hours", self._row(since=self.now - 5 * 3600)))
        for name, row in legs:
            with self.subTest(leg=name):
                built, light = self._legs(row)
                self.assertEqual(light, built, "%s: the provisional status differs from the built one" % name)
        _api_error_tail(self.path); self._idle_after("2026-06-11T00:00:05.000Z")
        built, light = self._legs(self._row())
        self.assertEqual(built["state"], "blocked", "the leg is what it claims")
        self.assertEqual(light, built, "api error: the provisional status differs from the built one")
        _api_error_tail(self.path, text="API Error: 400 prompt is too long: 250000 tokens > 200000 maximum"); self._idle_after("2026-06-11T00:00:05.000Z")
        built, light = self._legs(self._row())
        self.assertTrue(built["apiTooLong"])
        self.assertEqual(light, built, "prompt too long: the provisional status differs from the built one")
        # the Needs you ring's input (round four): the feed's verdict, both ways and before the first feed build
        self._plain_transcript()
        saved_needs = km._feed_needs_input[0]
        try:
            for verdict, name in (({S3}, "a needs-you card filed"), (set(), "no card"), (None, "before the first feed build")):
                km._feed_needs_input[0] = verdict
                built, light = self._legs(self._row())
                self.assertEqual(light["needsYou"], built["needsYou"], name)
                self.assertEqual(light, built, "%s: the provisional status differs from the built one" % name)
        finally:
            km._feed_needs_input[0] = saved_needs
        self._plain_transcript()
        class _Be:
            """A backend that states the compaction bracket; every other question the real build asks it reads as nothing."""
            def compacting(self, sid):
                return True
            def pending_queued(self, sid):
                return []
            def __getattr__(self, name):
                return lambda *a, **k: None
        with mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: _Be())):
            built, light = self._legs(self._row(state="compacting"))
        self.assertEqual(built["state"], "compacting")
        self.assertEqual(light, built, "compacting by the bracket: the provisional status differs from the built one")
        # no bracket (the hermetic module's backend_for is None): the row's word, disproved by a boundary since the row's since
        self._plain_transcript()
        built, light = self._legs(self._row(state="compacting", since=self.now - 30))
        self.assertEqual((built["state"], light["state"]), ("compacting", "compacting"), "a compacting row with no boundary since: both compacting")
        with open(self.path, "a") as f:                       # a compaction landed after the row's since: the compaction is over
            f.write(json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "cccccccc-0000-0000-0000-000000000001",
                                "parentUuid": "aaaaaaaa-0000-0000-0000-000000000002",
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(self.now))}) + "\n")
        self._idle_after(time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(self.now)))
        built, light = self._legs(self._row(state="compacting", since=self.now - 30))
        self.assertEqual(light["state"], built["state"], "a boundary since the row's since disproves the row's word on both roads")
        self.assertNotEqual(light["state"], "compacting")


if __name__ == "__main__":
    unittest.main()


def _stamped(i, t, boundary=False, pad=0):
    """One synthetic transcript line stamped at epoch `t`: a system compact_boundary record or a user record padded to
    `pad` bytes of text so a file can be sized to the tail read's windows."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
    if boundary:
        return json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "b%d" % i, "timestamp": ts}) + "\n"
    return json.dumps({"type": "user", "uuid": "u%d" % i, "timestamp": ts,
                       "message": {"role": "user", "content": [{"type": "text", "text": "x" * pad}]}}) + "\n"


class CompactBoundaryTailRead(unittest.TestCase):
    """The tail read behind the provisional chip's compacting leg (the fold of the gate's queued lows): a row with no since
    asks for any boundary, a record whose timestamp is not a string is skipped rather than raised, the answer is memoized
    per path against the file's size, and the slices read every byte once with the seam handled."""
    T0 = 1_780_000_000

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.jsonl")
        km._COMPACT_BOUNDARY_MEMO.clear()

    def _write(self, lines):
        with open(self.path, "w") as f:
            f.writelines(lines)

    def test_a_row_without_a_since_asks_for_any_boundary(self):
        self._write([_stamped(1, self.T0), _stamped(2, self.T0 + 5, boundary=True), _stamped(3, self.T0 + 9)])
        self.assertTrue(km._compact_boundary_since(self.path, None), "no since: a boundary anywhere disproves, as the built read does")
        self.assertTrue(km._compact_boundary_since(self.path, 0))
        self.assertFalse(km._compact_boundary_since(self.path, self.T0 + 6), "a since after the boundary: nothing since")

    def test_a_timestamp_that_is_not_a_string_is_skipped_never_raised(self):
        with open(self.path, "w") as f:
            f.write(json.dumps({"type": "system", "subtype": "compact_boundary", "timestamp": 12345}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": 12345}) + "\n")
            f.write("[1, 2, 3]\n")
            f.write(_stamped(9, self.T0 + 9))
        self.assertFalse(km._compact_boundary_since(self.path, self.T0), "a bool, on a file whose records are not what the read expects")
        self.assertIsInstance(km._light_status(S3, self.path, {"state": "compacting", "since": self.T0}, time.time()), dict,
                              "the provisional status stands on such a file too")

    def test_the_answer_is_memoized_per_path_against_the_files_size(self):
        self._write([_stamped(1, self.T0), _stamped(2, self.T0 + 9)])
        self.assertFalse(km._compact_boundary_since(self.path, self.T0))
        size = os.path.getsize(self.path)
        boundary = _stamped(2, self.T0 + 9, boundary=True)
        self._write([_stamped(1, self.T0, pad=size - len(_stamped(1, self.T0)) - len(boundary)), boundary])
        self.assertEqual(os.path.getsize(self.path), size, "the rewrite keeps the size")
        self.assertFalse(km._compact_boundary_since(self.path, self.T0), "same path, same size, same question: the memoized answer, no read")
        with open(self.path, "a") as f:
            f.write(_stamped(3, self.T0 + 10))
        self.assertTrue(km._compact_boundary_since(self.path, self.T0), "a changed size reads again")
        self.assertFalse(km._compact_boundary_since(self.path, self.T0 + 20), "a different question reads again")

    def test_slices_read_every_byte_once_and_a_record_torn_at_a_seam_is_still_read(self):
        # the boundary record straddles the seam between the first window and the second slice: its head is carried
        win = km.COMPACT_TAIL_WINDOW
        boundary = _stamped(2, self.T0 + 5, boundary=True)
        head = _stamped(1, self.T0 + 1, pad=win // 2)
        tail_pad = win - len(boundary) // 2 - len(_stamped(3, self.T0 + 9))   # the tail is half a boundary short of one window,
        tail = _stamped(3, self.T0 + 9, pad=tail_pad)                          # so the seam (size - win) falls inside the boundary line
        self._write([head, boundary, tail])
        size = os.path.getsize(self.path)
        seam = size - win
        self.assertTrue(len(head) < seam < len(head) + len(boundary), "the seam falls inside the boundary record")
        reads = []
        real_open = open
        class _F:
            def __init__(self, f): self.f = f
            def seek(self, n): return self.f.seek(n)
            def read(self, n): reads.append(n); return self.f.read(n)
            def __enter__(self): return self
            def __exit__(self, *a): return self.f.__exit__(*a)
        with mock.patch.object(km, "open", lambda *a, **k: _F(real_open(*a, **k)), create=True):
            self.assertTrue(km._compact_boundary_since(self.path, self.T0), "the torn boundary is read whole across the seam")
        self.assertEqual(reads, [win, size - win], "two slices, the first window and the remainder: every byte read once, no re-read of the tail")
