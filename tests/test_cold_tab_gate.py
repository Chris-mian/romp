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
from unittest import mock
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

    def test_09d_a_compacting_row_reads_compacting(self):
        self.live[S3]["state"] = "compacting"
        c, statuses = self._skeleton_push()
        self.assertEqual(statuses[S3]["state"], "compacting", "the row's own word, the built chip's leg when the backend states no bracket")

    def test_10_the_handshake_push_resolves_the_set_before_it_decides(self):
        """Round two, low 1: a skeleton client whose redial the pusher has not reached yet holds no set at the handshake push;
        the gate read that as holding nothing and handed the page a full it never asked for. The set is resolved first."""
        c = self._client(reconnect=True, active=S1)         # dialed the diet; no pusher cycle has run yet
        km._clients[:] = [c]
        km._push_session_now(S2)                             # the attach handshake's push
        self.assertEqual(self.built, [], "not built: the set resolved first and S2 is in it")
        strip = self._frames(c, "tabOrder")[0]
        self.assertEqual(strip["skeleton"], [S3, S2], "the strip carried the set")
        self.assertEqual([f["id"] for f in self._frames(c, "session")], [], "no full handed over")
        self.assertEqual([f["id"] for f in self._frames(c, "status")], [S2], "its provisional status instead")

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


if __name__ == "__main__":
    unittest.main()
