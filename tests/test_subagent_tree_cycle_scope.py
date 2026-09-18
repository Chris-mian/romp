#!/usr/bin/env python3
"""One sample of a session's subagents tree per pusher cycle, however many readers ask (2026-09-18).

The walk memo (_SUBAGENT_TREES, 2026-09-16) made an unchanged tree cost one lstat per known directory instead of a
listing, but every reader still paid that validation itself: within ONE pusher cycle the chat build's sidecar-map reads
(_stamp_agents, then _awaiting_items_payload -> _session_background_items -> _awaiting_live_rows, then _awaiting_nest for
the agent row it minted), the feed key's _subagent_dirs_ident, the feed derivation's _session_awaiting and a viewer
frame's agent-file re-walk on a cache miss (its first open, or after a file landed in a directory the walk read; the
frame's hit-path re-stats are a separate route) each re-validated the same root. Live on the measured kernel that was
63,473 validations, 5.2 M lstats and 346 s of validation wall over 3,867 cycles; the ~39,500 outside the feed key are the
candidates, an estimated 30-50% of all validations re-samples of a root another reader had taken in the same cycle, and
the `scoped` tally measures the realized share. The fix is the _live_scope idiom the liveness map, the names registry,
the discover rows and the billing
availability already use: _pusher_cycle (and _jobs_cycle, and a connect push's chat loop on a handler thread through
_chat_push_scopes_open) opens `subagent_trees`, the first reader of a root validates or walks, every later reader of the
cycle is served that sample with no lstat, and the slot is cleared with the cycle.

Pinned here, red-first on the count: (1) one cycle with a chat client validates or walks the root exactly once and serves
the rest from the sample (on stock the chat build alone reads the map three times before the feed key, so the count is
more than one, and `scoped` is not a key of the stats); (2) outside a scope every call samples afresh (the handler-thread
contract); (3) a directory change landing after a cycle's sample is seen by the next cycle, whose one sample is then a
miss; (4) the jobs pass opens and closes the slot like the pusher; (5) a connect push on a handler thread shares one
sample across its chat loop and closes its own scope with it; (6) an EMPTY answer (no root, or not a directory) is never
scoped, so a tree appearing under an open scope is found by _subagent_file rather than memoized as a miss under a stamp
newer than the listing it read (the refuter's amendment). Synthetic fixtures only: placeholder ids, the notes-api demo
world (sessions web and api), a temp directory."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads (the tests/test_kernel_pusher_snapshot.py preamble): the kernel and the judge resolve
# their state root at import, and only pytest runs conftest's floor. The root minted here is outside conftest's belt, so
# session hosts are switched off in it too (a state root with no `session-hosts` file starts a real host for any session
# it connects).
_ROOT = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _ROOT
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.makedirs(os.path.join(_ROOT, "romp"), exist_ok=True)
with open(os.path.join(_ROOT, "romp", "session-hosts"), "w") as _fh:
    _fh.write("off")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_subagent_tree_cycle_scope", os.path.join(BIN, "romp-kernel"))
jd = km.jd

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"       # web: the session with a subagents tree and an Agent in flight
SID2 = "11111111-2222-3333-4444-565656565656"      # api: a plain session, no subagents directory
AID = "a1111111111111111"                          # the top-level agent
AID_WF = "a2222222222222222"                       # a workflow agent, one level down
AID_NEW = "a3333333333333333"                      # the agent whose directory lands mid-test
TU, TU_WF, TU_NEW = "toolu_tree_0001", "toolu_tree_0002", "toolu_tree_0003"
AGED_NS = 10_000_000_000                           # ten seconds: past the racy window, as tests/test_subagent_tree_memo.py ages


def _age(root):
    """Every directory under `root` stamped ten seconds ago, so the memo may vouch for it."""
    t = time.time_ns() - AGED_NS
    for r, _ds, _fs in os.walk(root):
        os.utime(r, ns=(t, t))


class _World(unittest.TestCase):
    """The tests/test_kernel_pusher_snapshot.py cycle world, extended with a subagents tree: a hermetic state root, two
    sessions on disk (web with a transcript whose last record is an Agent tool_use without its result, so the turn is
    open, and a subagents tree beside it; api with a user record alone), web's live row carrying the Agent launch in its
    bgTasks set without a taskId (so _bg_live_norm yields an agent row with no agentId, and _awaiting_live_rows reads
    the sidecar map for it, then _awaiting_nest reads it again for the row it minted), the pusher's ticks stubbed, the
    racy window closed as the memo tests close it, and every scope slot cleared after each test."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km.Sessions.live, km._sdk,
                      km._auto_nudge_tick, km._clear_done_working_notes,
                      km._turn_notify_tick, km._api_health_frame, km._api_health_push, km._lift_spent_awaiting)
        names = td / "names"; names.mkdir()
        proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        for d in (jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR):
            d.mkdir()
        jd.STATE = td
        km.NAMES = names
        km._sdk = lambda: None
        cdir = td / "notes-api"; cdir.mkdir()
        pdir = proj / jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        user = {"type": "user", "timestamp": "2026-06-11T00:00:00.000Z", "uuid": "u1",
                "parentUuid": None, "promptSource": "typed",
                "message": {"role": "user", "content": "check the api tests"}}
        launch = {"type": "assistant", "timestamp": "2026-06-11T00:00:05.000Z", "uuid": "a1", "parentUuid": "u1",
                  "message": {"role": "assistant", "content": [
                      {"type": "tool_use", "id": TU, "name": "Agent",
                       "input": {"description": "check the api tests", "prompt": "look at the failing test"}}]}}
        self.paths = {}
        for sid, name, recs in ((SID, "web", (user, launch)), (SID2, "api", (user,))):
            self.paths[sid] = str(pdir / (sid + ".jsonl"))
            (pdir / (sid + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
            (names / sid).write_text("%s\t%s\t#abcdef\n" % (name, str(cdir)))
        # web's subagents tree, the tests/test_subagent_tree_memo.py shape: one agent pair at the top, one workflow
        # agent's pair under workflows/wf_<id>/
        self.subdir = pdir / SID / "subagents"
        self.wf = self.subdir / "workflows" / ("wf_%016x" % (int(SID[-4:], 16)))
        self.wf.mkdir(parents=True)
        (self.subdir / ("agent-%s.meta.json" % AID)).write_text(json.dumps(
            {"agentType": "general-purpose", "description": "check the api tests", "spawnDepth": 1, "toolUseId": TU}))
        (self.subdir / ("agent-%s.jsonl" % AID)).write_text("")
        (self.wf / ("agent-%s.meta.json" % AID_WF)).write_text(json.dumps(
            {"agentType": "Workflow", "description": "tidy the readme", "spawnDepth": 1, "toolUseId": TU_WF}))
        (self.wf / ("agent-%s.jsonl" % AID_WF)).write_text("")
        _age(str(self.subdir))
        self.roots = [str(self.subdir), str(km._subagents_dir(self.paths[SID2]))]
        meta = {"state": "waiting", "since": NOW - 5, "model": "", "effort": "", "context": None,
                "compactPct": None, "color": None, "mode": "", "backend": "sdk"}
        self.row = {SID: dict(meta, bgTasks=[{"toolUseId": TU, "desc": "check the api tests", "since": NOW - 3,
                                              "type": "local_agent"}]),
                    SID2: dict(meta)}
        km.Sessions.live = lambda: dict(self.row)
        # the pusher's ticks and the jobs pass's, stubbed: none of them is a reader of the tree, and none is under test
        km._turn_notify_tick = lambda now, live_map: None
        km._api_health_frame = lambda now, live_map: None
        km._api_health_push = lambda frame: None
        km._lift_spent_awaiting = lambda now, live_map: None
        km._clear_done_working_notes = lambda now, live_map: None
        self.saved_clients = list(km._clients)
        # os.utime back-dates mtime but sets ctime to now, and the racy mask covers both stamps: the window is closed so
        # the memo can vouch for the aged fixture (the tests/test_subagent_tree_memo.py _Tree rule)
        self._racy = mock.patch.object(km, "_SUBAGENT_DIR_RACY_NS", 0)
        self._racy.start()
        self._forget()

    def _forget(self):
        for r in self.roots:
            km._SUBAGENT_TREES.pop(r, None)
        km._SUBAGENT_META_CACHE.clear()
        km._SUBAGENT_FILE_CACHE.clear()
        km._built_chat.clear()
        km._built_feed[:] = [None, None, 0.0, 0.0]

    def tearDown(self):
        self._racy.stop()
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km.Sessions.live, km._sdk,
         km._auto_nudge_tick, km._clear_done_working_notes,
         km._turn_notify_tick, km._api_health_frame, km._api_health_push, km._lift_spent_awaiting) = self.saved
        with km._clients_lock:
            km._clients[:] = self.saved_clients
        # every scope slot, so a failing test cannot leak a cycle's memo into the next on this thread
        for k in ("snapshot", "sessions", "paths", "names", "auth", "msgsum", "files_stat", "files_dirty",
                  "subagent_trees", "chat_shared", "chat_push_owned"):
            setattr(km._live_scope, k, None)
        km._chat_dep_scope.deps = None
        self._forget()
        self.td.cleanup()

    def _chat_client(self):
        """A connected chat client, so the push leg builds the tabs for real; returns the list its sends land in."""
        sent = []
        with km._clients_lock:
            km._clients[:] = [{"app": "chat", "alive": True, "wid": "", "qbytes": 0, "send": sent.append}]
        return sent

    @staticmethod
    def _validations(before, after):
        """How many times the memo validated or walked: hit + miss moved."""
        return (after["hit"] + after["miss"]) - (before["hit"] + before["miss"])


class OneSampleOfEachRootPerCycle(_World):
    def test_one_pusher_cycle_samples_a_subagents_root_once_however_many_readers(self):
        """RED FIRST. In this fixture the chat build is the cycle's first reader and reads the sidecar map three times
        (_stamp_agents; _awaiting_items_payload -> _session_background_items -> _awaiting_live_rows, since the Agent
        tool_use has no result, so the turn is open and _session_awaiting answers None before reading, in build_session
        and in _feed_session_entry alike; then _awaiting_nest for the agent row it minted), and the feed key's
        _subagent_dirs_ident reads the tree once more: on stock each is a validation of its own, so the count is more
        than one, and `scoped` is not a key of the stats. With the cycle scope the first read is the cycle's one sample
        and the rest are served from it."""
        sent = self._chat_client()
        before = dict(km._SUBAGENT_TREE_STATS)
        km._pusher_cycle()
        after = dict(km._SUBAGENT_TREE_STATS)
        self.assertTrue(any('"type": "session"' in s for s in sent), "the push leg really built the session")
        self.assertEqual(self._validations(before, after), 1,
                         "one validation or walk of the root per cycle: the chat build's sidecar-map reads and the feed key "
                         "read one sample")
        self.assertGreaterEqual(after["scoped"] - before.get("scoped", 0), 2, "the later readers were served the sample")
        self.assertIsNone(getattr(km._live_scope, "subagent_trees", None), "the scope ends with the cycle")

    def test_outside_a_cycle_every_call_samples_afresh(self):
        """The handler-thread contract (a WS viewer frame, GET /feed.json): no scope open, every call validates."""
        km._live_scope.subagent_trees = None
        root = str(self.subdir)
        before = dict(km._SUBAGENT_TREE_STATS)
        km._subagent_tree(root)
        km._subagent_tree(root)
        after = dict(km._SUBAGENT_TREE_STATS)
        self.assertEqual(self._validations(before, after), 2, "no scope, no memo: two calls are two samples")
        self.assertEqual(after["scoped"], before["scoped"], "nothing was served from a scope")

    def test_a_change_after_the_cycles_sample_is_seen_by_the_next_cycle(self):
        """The exactness claim: once per cycle, never stale past the cycle. A workflow directory and its sidecar land
        after cycle one's sample; cycle two's one sample is a miss (the tree changed), the memo holds the new directory,
        and the feed key's subagents component moved for the session. The chat tab is cycle two's first reader here too:
        its taskout dependency on the workflows directory rebuilds it. The feed is forced to rebuild with a dirty mark
        (the refuter's amendment): within REBUILD_MIN_S _feed_servable would otherwise serve cycle one's build and the
        key would never be re-taken."""
        self._chat_client()
        km._pusher_cycle()
        root = str(self.subdir)
        self.assertIn(root, km._SUBAGENT_TREES, "cycle one sampled the root")
        new = self.subdir / "workflows" / ("wf_%016x" % 0xee)
        new.mkdir()
        (new / ("agent-%s.meta.json" % AID_NEW)).write_text(json.dumps(
            {"agentType": "Workflow", "description": "check the readme links", "spawnDepth": 1, "toolUseId": TU_NEW}))
        (new / ("agent-%s.jsonl" % AID_NEW)).write_text("")
        feed_before = km._feed_memo_report()["miss_by"].get("subagents", 0)
        before = dict(km._SUBAGENT_TREE_STATS)
        km._mark_views_dirty()
        km._pusher_cycle()
        after = dict(km._SUBAGENT_TREE_STATS)
        self.assertIn(str(new), km._SUBAGENT_TREES[root][0], "the next cycle's sample holds the new directory")
        self.assertEqual(self._validations(before, after), 1, "again exactly one sample of the root")
        self.assertEqual(after["miss"] - before["miss"], 1, "...and it was a miss: the tree changed")
        self.assertEqual(km._feed_memo_report()["miss_by"].get("subagents", 0) - feed_before, 1,
                         "the feed key's subagents component moved for the session")
        self.assertIsNone(getattr(km._live_scope, "subagent_trees", None))

    def test_the_jobs_pass_opens_and_closes_the_scope(self):
        """The housekeeping pass's twin (the reminder walk's _session_awaiting readers share one sample per root per pass;
        precedent: the snapshot test's jobs twin). RED FIRST: on stock the slot never exists."""
        got = {}
        km._auto_nudge_tick = lambda now, live_map, **kw: got.setdefault(
            "open", isinstance(getattr(km._live_scope, "subagent_trees", None), dict))
        km._jobs_cycle()
        self.assertIs(got.get("open"), True, "the pass opened the scope before its jobs ran")
        self.assertIsNone(getattr(km._live_scope, "subagent_trees", None), "the scope ends with the pass")

    def test_a_connect_push_on_a_handler_thread_shares_one_sample_across_its_chat_loop(self):
        """A push outside any cycle (a fresh client on its handler thread) opens the slot for its chat loop through
        _chat_push_scopes_open, as it opens the caption-map slot and the names snapshot there, and closes exactly what
        it opened (the ownership rule tests/test_chat_build_sig_inputs.py pins for names and msgsum). The feed is warmed
        by a cycle first, so the connect serves it and never rebuilds; the tab is dropped from _built_chat so the
        connect rebuilds it. RED FIRST: on stock the rebuilt tab validates three times."""
        self._chat_client()
        km._pusher_cycle()                                     # warms the feed: the connect serves it, no feed key read
        km._built_chat.clear()                                 # the tab rebuilds on the connect
        km._live_scope.subagent_trees = None                   # no cycle scope on this thread
        sent = []
        client = {"app": "chat", "alive": True, "wid": "", "qbytes": 0, "send": sent.append}
        before = dict(km._SUBAGENT_TREE_STATS)
        km._push([client], connect=True)
        after = dict(km._SUBAGENT_TREE_STATS)
        self.assertTrue(any('"type": "session"' in s for s in sent), "the connect push built the tab")
        self.assertEqual(self._validations(before, after), 1, "the push's chat loop shared one sample of the root")
        self.assertIsNone(getattr(km._live_scope, "subagent_trees", None), "the push's own scope closes with its chat loop")
        self.assertIsNone(getattr(km._live_scope, "chat_push_owned", None), "the owned slot list was consumed by the close")

    def test_an_empty_answer_is_never_scoped_so_a_tree_appearing_under_an_open_scope_is_found(self):
        """The refuter's amendment: _subagent_file_walk stamps the root itself with a fresh _dir_stamp and reads its
        listing through _find_agent_file; served an older EMPTY sample it would memoize a nested agent's miss under a
        stamp newer than the listing it read, a stale miss that outlives the cycle because _subagent_file's hit path
        re-stats and never re-walks. So a zero-directory answer (no root, or not a directory) is never stored in the
        scope, and every caller re-lstats such a root as today. On the spec's storage rule as written this returned None
        twice."""
        tpath = self.paths[SID2]                               # api: no subagents directory yet
        own = km._subagents_dir(tpath)
        self.assertFalse(own.exists())
        km._live_scope.subagent_trees = {}
        try:
            self.assertEqual(km._subagent_tree(str(own)), ((), ()))
            self.assertNotIn(str(own), km._live_scope.subagent_trees, "an empty answer carries no stamp: not scoped")
            wf = own / "workflows" / ("wf_%016x" % 0xab)
            wf.mkdir(parents=True)
            (wf / ("agent-%s.meta.json" % AID_NEW)).write_text(json.dumps({"agentType": "Workflow", "toolUseId": TU_NEW}))
            (wf / ("agent-%s.jsonl" % AID_NEW)).write_text("")
            self.assertEqual(km._subagent_file(tpath, AID_NEW), wf / ("agent-%s.jsonl" % AID_NEW),
                             "found inside the scope: the empty sample did not stand in for the tree")
            self.assertIn(str(own), km._live_scope.subagent_trees, "the walked tree, with its stamps, is the scoped sample")
        finally:
            km._live_scope.subagent_trees = None
        self.assertEqual(km._subagent_file(tpath, AID_NEW), wf / ("agent-%s.jsonl" % AID_NEW),
                         "and after the scope: the memo holds the path, not a None")


if __name__ == "__main__":
    unittest.main()
