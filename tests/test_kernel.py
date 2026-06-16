#!/usr/bin/env python3
"""Tests for bin/romp-kernel's view-builder (records → the WS payloads the tuned UI bundles
consume). The WS transport + HTTP serving aren't unit-tested; the projection — atoms→ChatEvent
(chat), goals→feed cards, ledger→TOC — is. Synthetic fleet only: invented text, placeholder
UUIDs; no real session data.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ["ROMP_SERVE_TOKEN"] = "testtok"            # known token for the serve-security test
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None, ps="typed"):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": ps, "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent=None, tools=(), stop="end_turn"):
    content = [{"type": "text", "text": text}] if text else []
    for i, n in enumerate(tools):
        content.append({"type": "tool_use", "id": "tu_%s_%d" % (uuid, i), "name": n,
                        "input": {"file_path": "/x/y.py", "old_string": "a", "new_string": "b"}})
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": content, "stop_reason": stop}}


def trline(t, tool_use_id, uuid, parent, content="ok", is_error=False):
    b = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        b["is_error"] = True
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": [b]}}


class ViewBuilder(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        recs = [uline(T0, "fix the feed flicker", "u1", ps="typed"),
                aline(T0 + 20, "Looking at the renderer.", "a1", "u1", tools=("Edit",), stop="tool_use"),
                trline(T0 + 25, "tu_a1_0", "r1", "a1", content="edited"),
                aline(T0 + 40, "Fixed the feed flicker.", "a2", "r1", stop="end_turn")]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km._tmux_sessions)
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        jd.STATE = td                                  # sandbox the timeline helpers (usage/states/mail)
        km.NAMES = names
        # deterministic tmux: the fixture session is ALIVE + idle (so the alive-only filter shows it);
        # individual tests override this map to exercise other states.
        km._tmux_sessions = lambda: {SID: {"state": "idle", "since": NOW - 100, "model": "",
                                           "effort": "", "context": None, "compactPct": None, "color": None}}
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        turn = session["turns"][0]
        jd.CAPDIR.mkdir(parents=True)
        (jd.CAPDIR / (SID + ".jsonl")).write_text(
            json.dumps({"id": turn["id"], "grain": "turn", "t": turn["t"], "caption": "Fixed the feed flicker"}) + "\n")
        jd.ARCHDIR.mkdir(parents=True)
        (jd.ARCHDIR / (SID + ".json")).write_text(json.dumps(
            {"headline": "Fixing the feed", "abstract": "Fixed a flicker.", "turns": 1}))
        jd.GOALDIR.mkdir(parents=True)
        g1, g2 = "%s:g1" % SID, "%s:g2" % SID
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 2, "lastNode": g1,
            "nodes": {g1: {"id": g1, "text": "Fix the feed flicker", "parentId": None,
                           "nodeComplete": True, "blocked": False, "cleared": False, "trail": [], "t": turn["t"]},
                      g2: {"id": g2, "text": "Awaiting a decision", "parentId": None,
                           "nodeComplete": False, "blocked": True, "cleared": False, "trail": [], "t": turn["t"]}},
            "placements": {}, "status": {g1: "completed", g2: "blocked"}}))

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km._tmux_sessions) = self.saved
        self.td.cleanup()

    def test_parse_cache_hits_until_the_file_changes(self):
        """The build hot path parses via _parse, cached by the transcript's (mtime,size): an unchanged
        transcript returns the SAME parsed object; a changed one re-parses."""
        km._parse_cache.clear()
        a = km._parse(str(self.tpath), SID, NOW)
        b = km._parse(str(self.tpath), SID, NOW)
        self.assertIs(a, b, "unchanged transcript → cached parse re-used")
        with self.tpath.open("a") as f:                  # append → size (and mtime) change
            f.write(json.dumps(uline(NOW, "more", "uX", ps="typed")) + "\n")
        c = km._parse(str(self.tpath), SID, NOW)
        self.assertIsNot(a, c, "changed transcript → re-parsed")

    def test_send_client_dedups_per_client(self):
        """A client gets a payload once; an identical re-push is skipped; a changed one is sent (the
        diff-push that stops the 4s pusher from re-sending unchanged chat sessions)."""
        out = []
        c = {"app": "feed", "send": lambda s: out.append(s), "alive": True}
        km._send_client(c, ("feed",), {"type": "feed", "x": 1})
        km._send_client(c, ("feed",), {"type": "feed", "x": 1})
        self.assertEqual(len(out), 1, "identical payload is not re-sent")
        km._send_client(c, ("feed",), {"type": "feed", "x": 2})
        self.assertEqual(len(out), 2, "a changed payload is sent")

    def test_producer_sig_tracks_browser_and_transcripts(self):
        """The producer gate's fingerprint: a browser connecting changes it (so triage runs to build the
        new client's inbox), and each discovered transcript's mtime is in it (so a new turn triggers)."""
        s_off, s_on = km._producer_sig(False), km._producer_sig(True)
        self.assertEqual((s_off["__browser__"], s_on["__browser__"]), (False, True))
        self.assertNotEqual(s_off, s_on, "a browser connecting changes the sig → triage runs")
        self.assertIn(str(self.tpath), s_on, "each discovered transcript's mtime is fingerprinted")

    def test_session_payload_shape(self):
        m = km.build_session(SID, NOW)
        self.assertEqual(m["type"], "session")
        self.assertEqual(m["id"], SID)
        self.assertEqual(m["color"], {"bg": "#abcdef", "fg": "#ffffff"})
        kinds = [e["kind"] for e in m["events"]]
        self.assertEqual(kinds, ["user", "assistant", "tool", "assistant"], "atoms reshape to ChatEvent[]")

    def test_user_event_and_human_flag(self):
        m = km.build_session(SID, NOW)
        u = next(e for e in m["events"] if e["kind"] == "user")
        self.assertEqual(u["md"], "fix the feed flicker")
        self.assertTrue(u["human"])

    def test_tool_event_pairs_output_and_diff(self):
        m = km.build_session(SID, NOW)
        tool = next(e for e in m["events"] if e["kind"] == "tool")
        self.assertEqual(tool["name"], "Edit")
        self.assertEqual(tool["output"], "edited", "the matching tool_result fills the tool event's output")
        self.assertIn("- a", tool["diff"]); self.assertIn("+ b", tool["diff"])
        self.assertEqual(tool["file"], "/x/y.py")

    def test_ledger_is_toc_from_archive_and_captions(self):
        m = km.build_session(SID, NOW)
        self.assertEqual(m["ledger"]["summary"], "Fixing the feed")
        self.assertTrue(any(b["text"] == "Fixed the feed flicker" for b in m["ledger"]["bullets"]))

    def test_ledger_bullets_are_newest_first(self):
        # A second, LATER captioned turn → the ledger must list newest-first: render shows bullets[0] at
        # the TOP and reads it as "the newest" for the summary hue. Regression for the oldest-on-top bug.
        # u2's parentUuid chains to the prior turn's last assistant (a2) so the leaf (a3) traces back
        # through BOTH turns — that's how a real transcript tree links successive prompts.
        with self.tpath.open("a") as f:
            f.write(json.dumps(uline(T0 + 100, "now fix the sort order", "u2", parent="a2", ps="typed")) + "\n")
            f.write(json.dumps(aline(T0 + 120, "Sorted it.", "a3", "u2", stop="end_turn")) + "\n")
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        turns = session["turns"]
        self.assertGreaterEqual(len(turns), 2, "fixture should now span two turns")
        caps = [{"id": turns[0]["id"], "grain": "turn", "t": turns[0]["t"], "caption": "Fixed the feed flicker"},
                {"id": turns[1]["id"], "grain": "turn", "t": turns[1]["t"], "caption": "Sorted the ledger"}]
        (jd.CAPDIR / (SID + ".jsonl")).write_text("\n".join(json.dumps(c) for c in caps) + "\n")
        bullets = km.build_session(SID, NOW)["ledger"]["bullets"]
        ts = [b["t"] for b in bullets]
        self.assertEqual(ts, sorted(ts, reverse=True), "ledger bullets must be newest-first")
        self.assertEqual(bullets[0]["text"], "Sorted the ledger", "newest caption sits on top")

    def test_session_list_for_picker(self):
        # the + picker's payload (requestSessions → sessionList). Was always empty: bin/romp-kernel had
        # no requestSessions handler, so the kernel never replied. Running sessions first; archive headline
        # as the summary; the names-registry color.
        items = km._session_list(NOW, km._tmux_sessions())
        self.assertTrue(items, "picker must list the live session")
        it = next(i for i in items if i["id"] == SID)
        self.assertEqual(it["name"], "testsess")
        self.assertTrue(it["running"], "SID is alive in tmux → running")
        self.assertEqual(it["time"], "running")
        self.assertEqual(it["summary"], "Fixing the feed")
        self.assertEqual(it["color"], {"bg": "#abcdef", "fg": "#ffffff"})

    def test_rel_ago_buckets(self):
        self.assertEqual(km._rel_ago(1000, 1000), "just now")
        self.assertEqual(km._rel_ago(1000, 1000 - 120), "2m ago")
        self.assertEqual(km._rel_ago(1000 + 7200, 1000), "2h ago")
        self.assertEqual(km._rel_ago(3 * 86400, 0), "3d ago")

    def test_todo_card_folds_taskcreate_taskupdate(self):
        # TaskCreate/TaskUpdate fold into ONE {kind:"todo"} card (the old TS transcript.foldTasks); the
        # task id comes from TaskCreate's "Task #N" result; the raw Task* tool calls are NOT emitted (the
        # webview hides them via ACK_TOOLS, so the kernel skips them and emits only the folded checklist).
        def asst(t, uuid, parent, blocks, stop="end_turn"):
            return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
                    "message": {"role": "assistant", "content": blocks, "stop_reason": stop}}
        tc = {"type": "tool_use", "id": "tc1", "name": "TaskCreate",
              "input": {"subject": "Wire the picker", "activeForm": "Wiring the picker"}}
        tu = {"type": "tool_use", "id": "tu1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "in_progress"}}
        with self.tpath.open("a") as f:
            f.write(json.dumps(uline(T0 + 100, "make a plan", "u2", parent="a2", ps="typed")) + "\n")
            f.write(json.dumps(asst(T0 + 110, "a3", "u2", [{"type": "text", "text": "Planning."}, tc], stop="tool_use")) + "\n")
            f.write(json.dumps(trline(T0 + 112, "tc1", "r2", "a3", content="Task #1 created successfully: Wire the picker")) + "\n")
            f.write(json.dumps(asst(T0 + 120, "a4", "r2", [tu])) + "\n")
        m = km.build_session(SID, NOW)
        todos = [e for e in m["events"] if e["kind"] == "todo"]
        self.assertEqual(len(todos), 1, "exactly one folded todo card")
        tasks = todos[0]["tasks"]
        self.assertEqual([t["id"] for t in tasks], ["1"])
        self.assertEqual(tasks[0]["subject"], "Wire the picker")
        self.assertEqual(tasks[0]["activeForm"], "Wiring the picker")
        self.assertEqual(tasks[0]["status"], "in_progress", "TaskUpdate moved it to in_progress")
        self.assertFalse(any(e["kind"] == "tool" and e["name"] in ("TaskCreate", "TaskUpdate") for e in m["events"]),
                         "raw Task* tool calls are folded away, not shown as tool cards")

    def test_queued_event_from_cache(self):
        # a message queued in the TUI while busy/compacting (pane-scraped into _queued_cache) surfaces as a
        # {kind:"queued"} card at the bottom — the "vanished during compaction" fix
        km._queued_cache[SID] = ["fix the flaky test", "bump the version"]
        try:
            m = km.build_session(SID, NOW)
            q = [e for e in m["events"] if e["kind"] == "queued"]
            self.assertEqual(len(q), 1, "one queued card")
            self.assertEqual(q[0]["texts"], ["fix the flaky test", "bump the version"])
            self.assertEqual(m["events"][-1]["kind"], "queued", "queued sits at the bottom, by the composer")
        finally:
            km._queued_cache.pop(SID, None)

    def _asst(self, t, uuid, parent, blocks, stop="end_turn"):
        return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
                "message": {"role": "assistant", "content": blocks, "stop_reason": stop}}

    def test_subagent_running_state_and_card(self):
        # an in-flight Task (tool_use with no tool_result yet) → 'subagent' chip + a {kind:"subagent"} card
        task = {"type": "tool_use", "id": "tk1", "name": "Task", "input": {"description": "audit the auth flow"}}
        with self.tpath.open("a") as f:
            f.write(json.dumps(uline(T0 + 100, "go audit auth", "u2", parent="a2", ps="typed")) + "\n")
            f.write(json.dumps(self._asst(T0 + 110, "a3", "u2",
                    [{"type": "text", "text": "Delegating."}, task], stop="tool_use")) + "\n")
        m = km.build_session(SID, NOW)
        self.assertEqual(m["status"]["state"], "subagent", "in-flight subagent → orange subagent chip")
        cards = [e for e in m["events"] if e["kind"] == "subagent"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["desc"], "audit the auth flow")

    def test_completed_subagent_not_running(self):
        # a Task WITH a tool_result → not in flight → no subagent chip/card
        task = {"type": "tool_use", "id": "tk2", "name": "Task", "input": {"description": "x"}}
        with self.tpath.open("a") as f:
            f.write(json.dumps(uline(T0 + 100, "go", "u2", parent="a2", ps="typed")) + "\n")
            f.write(json.dumps(self._asst(T0 + 110, "a3", "u2", [task], stop="tool_use")) + "\n")
            f.write(json.dumps(trline(T0 + 120, "tk2", "r2", "a3", content="subagent report")) + "\n")
            f.write(json.dumps(self._asst(T0 + 130, "a4", "r2", [{"type": "text", "text": "done"}])) + "\n")
        m = km.build_session(SID, NOW)
        self.assertNotEqual(m["status"]["state"], "subagent")
        self.assertFalse(any(e["kind"] == "subagent" for e in m["events"]))

    def test_feed_buckets_goal_and_streams_caption(self):
        d = km.build_feed(NOW)
        self.assertEqual(d["type"], "feed")
        comp = [a for a in d["asks"] if a["column"] == "completed"]
        self.assertEqual(len(comp), 1)
        self.assertEqual(comp[0]["text"], "Fix the feed flicker")
        self.assertEqual(comp[0]["tree"][0]["status"], "done")
        self.assertTrue(any(c["did"] == "Fixed the feed flicker" for c in d["items"]))
        # card tint is the recency colormap (age → hawaii ramp), not a flat session color
        self.assertEqual(comp[0]["trgb"], list(km.cm.age_rgb(NOW - comp[0]["t"])))
        self.assertNotEqual(comp[0]["trgb"], km._rgb(comp[0]["color"]), "not the flat session color")
        self.assertTrue(all(c["standalone"] for c in d["items"]), "stream cards must be standalone or the render hides them")

    def test_feed_non_handoff_card_has_no_origin(self):
        comp = next(a for a in km.build_feed(NOW)["asks"] if a["column"] == "completed")
        self.assertIsNone(comp["origin"], "a normal (non-courier) card carries no handoff origin")

    def test_feed_live_permission_floors_focus_card_to_blocked(self):
        """A session stopped on a LIVE permission prompt floors its active-focus card under BLOCKED
        (it.blocked) — the hard floor, beats the goal's planner status; the render's askColumn then
        files it under needsInput and shows the ⏸ approval badge."""
        g = "%s:g5" % SID
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 5, "lastNode": g,
            "nodes": {g: {"id": g, "text": "Work in progress", "parentId": None,
                          "nodeComplete": False, "blocked": False, "cleared": False, "trail": [], "t": NOW - 50}},
            "placements": {}, "status": {g: "working"}}))
        km._tmux_sessions = lambda: {SID: {"state": "permission", "since": NOW - 30, "model": "",
                                           "effort": "", "context": None, "compactPct": None, "color": None}}
        card = next(a for a in km.build_feed(NOW)["asks"] if a["itemId"] == g)
        self.assertEqual(card["blocked"]["state"], "permission", "a live permission prompt floors the focus card")
        self.assertEqual(card["blocked"]["since"], NOW - 30)

    def test_feed_permission_does_not_floor_a_completed_focus(self):
        """The floor applies only to an OPEN focus goal — a live prompt while the focus is already
        completed (the block is on not-yet-placed new work) leaves the completed card alone."""
        # default store: lastNode = g1 (completed). A permission state must NOT floor g1.
        km._tmux_sessions = lambda: {SID: {"state": "permission", "since": NOW - 30, "model": "",
                                           "effort": "", "context": None, "compactPct": None, "color": None}}
        comp = next(a for a in km.build_feed(NOW)["asks"] if a["column"] == "completed")
        self.assertIsNone(comp["blocked"], "a completed focus card is not floored by a live prompt")

    def test_feed_no_permission_no_hard_block(self):
        comp = next(a for a in km.build_feed(NOW)["asks"] if a["column"] == "completed")
        self.assertIsNone(comp["blocked"], "no live permission (idle) → no hard block floor")

    def test_feed_courier_handoff_resolves_origin_sender(self):
        """A goal planted by the courier carries origin:{peer:<senderSid>,...}; build_feed resolves
        the sender's rompUuid to a display name + color for the '↪ from <sender>' marker."""
        sender = "99999999-8888-7777-6666-555555555555"
        (jd.NAMES / sender).write_text("sendersess\t/elsewhere\t#ff8800\n")
        g = "%s:g7" % SID
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 7, "lastNode": g,
            "nodes": {g: {"id": g, "text": "Do the handed-off work", "parentId": None,
                          "nodeComplete": False, "blocked": False, "cleared": False, "trail": [], "t": NOW - 50,
                          "origin": {"peer": sender, "goalId": sender + ":g1", "msgId": "m-abc.123"}}},
            "placements": {}, "status": {g: "working"}}))
        card = next(a for a in km.build_feed(NOW)["asks"] if a["itemId"] == g)
        self.assertEqual(card["origin"], {"peer": "sendersess", "peerSid": sender,
                                          "color": {"bg": "#ff8800", "fg": "#ffffff"}},
                         "origin.peer (a sid) resolves to the sender's name + color")

    def test_feed_handoff_origin_falls_back_to_short_sid_when_unnamed(self):
        """If the sender isn't in the names registry, fall back to a short sid (never crash / show blank)."""
        sender = "abcdef00-0000-0000-0000-000000000000"
        g = "%s:g8" % SID
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 8, "lastNode": g,
            "nodes": {g: {"id": g, "text": "Orphaned handoff", "parentId": None,
                          "nodeComplete": False, "blocked": False, "cleared": False, "trail": [], "t": NOW - 50,
                          "origin": {"peer": sender, "goalId": None, "msgId": "m-x.1"}}},
            "placements": {}, "status": {g: "working"}}))
        card = next(a for a in km.build_feed(NOW)["asks"] if a["itemId"] == g)
        self.assertEqual(card["origin"]["peer"], sender[:8])
        self.assertIsNone(card["origin"]["color"])

    def test_feed_clear_and_undo(self):
        g1 = "%s:g1" % SID
        self.assertTrue(any(a["itemId"] == g1 for a in km.build_feed(NOW)["asks"]))
        km._clear_ask(g1)
        d = km.build_feed(NOW)
        self.assertFalse(any(a["itemId"] == g1 for a in d["asks"]), "a cleared ask is hidden")
        self.assertTrue(d["canUndoClear"]); self.assertEqual(d["dismissedCount"], 1)
        km._undo_clear()
        d2 = km.build_feed(NOW)
        self.assertTrue(any(a["itemId"] == g1 for a in d2["asks"]), "undo restores it")
        self.assertFalse(d2["canUndoClear"])

    def test_feed_clear_all_then_undo_restores_the_batch(self):
        d0 = km.build_feed(NOW)
        ids = [a["itemId"] for a in d0["asks"]] + [c["itemId"] for c in d0["items"]]
        self.assertTrue(ids, "fixture has cards to clear")
        km._clear_all(ids)
        d1 = km.build_feed(NOW)
        self.assertEqual(len(d1["asks"]) + len(d1["items"]), 0, "clear-all empties the feed")
        self.assertTrue(d1["canUndoClear"])
        km._undo_clear()
        d2 = km.build_feed(NOW)
        self.assertEqual(len(d2["asks"]), len(d0["asks"]), "one undo restores the whole batch")
        self.assertFalse(d2["canUndoClear"])

    def test_alive_filter_drops_dead_sessions(self):
        # the hard filter: only sessions alive in tmux appear anywhere (feed/timeline/chat tabs)
        self.assertEqual(km._alive_sessions(NOW, {"other-sid": {}}), [], "dead session dropped")
        alive = km._alive_sessions(NOW, {SID: {"state": "working"}})
        self.assertEqual([s["sid"] for s in alive], [SID])

    def test_clear_all_clears_blocked_too(self):
        d0 = km.build_feed(NOW)
        self.assertTrue([a for a in d0["asks"] if a["column"] == "needs_input"], "fixture has a blocked ask")
        km._clear_all([a["itemId"] for a in d0["asks"]])
        self.assertEqual([a for a in km.build_feed(NOW)["asks"] if a["column"] == "needs_input"], [],
                         "clear-all clears the blocked column too")

    def test_chat_chip_working_is_event_model_not_tmux(self):
        # @claude-state says "working" but the fixture's turn ENDED -> chip is ready, not working:
        # working is the stable event-model signal (open turn), not the laggy tmux state (the user's
        # "working shows blue / flickers" regression)
        km._tmux_sessions = lambda: {SID: {"state": "working", "since": NOW - 5, "model": "Opus 4.8",
                                           "effort": "max", "context": 30, "compactPct": None, "color": None}}
        self.assertEqual(km.build_session(SID, NOW)["status"]["state"], "ready",
                         "ended turn -> ready even when tmux says working")

    def test_close_session_hides_tab(self):
        # the × hides the tab (reversible), does not kill the session
        self.assertEqual(km._hidden_tabs(), set())
        km._set_hidden_tab(SID, True)
        self.assertIn(SID, km._hidden_tabs())
        km._set_hidden_tab(SID, False)
        self.assertNotIn(SID, km._hidden_tabs())

    def test_split_reminders(self):
        p, r = km._split_reminders("do the thing <system-reminder>be careful</system-reminder> now")
        self.assertNotIn("system-reminder", p); self.assertIn("do the thing", p); self.assertIn("now", p)
        self.assertEqual(r, ["be careful"])
        self.assertEqual(km._split_reminders("plain prompt"), ("plain prompt", []))

    def test_name_of_resolves_sid(self):
        # a postal atom's peer is the sender's SID; resolve it to a name (+ color via _name_color)
        self.assertEqual(km._name_of(SID), "testsess")
        self.assertEqual(km._name_color(SID), {"bg": "#abcdef", "fg": "#ffffff"})
        self.assertIsNone(km._name_of("no-such-sid"))

    def test_postal_connectors(self):
        # timeline message connectors from the postal log: a sent row joined to its exec by id, with
        # BOTH ends alive lanes; a message to a non-alive session is dropped (no endpoint)
        md = jd.STATE / "timeline"; md.mkdir(parents=True, exist_ok=True)
        a, b = "aaaa1111", "bbbb2222"
        (md / "messages.jsonl").write_text(
            json.dumps({"ev": "sent", "id": "m1", "from_id": a, "to_id": b, "t": NOW - 30,
                        "from": "alpha", "body": "do X"}) + "\n"
            + json.dumps({"ev": "exec", "id": "m1", "t": NOW - 20}) + "\n"
            + json.dumps({"ev": "sent", "id": "m2", "from_id": a, "to_id": "deadsid", "t": NOW - 30,
                          "from": "alpha", "body": "y"}) + "\n")
        msgs = km._postal_messages(NOW, {a, b}, {a: "alpha", b: "beta"})
        self.assertEqual(len(msgs), 1, "only the connector with BOTH ends alive")
        m = msgs[0]
        self.assertEqual((m["fromId"], m["toId"]), (a, b))
        self.assertEqual(m["exec"], NOW - 20); self.assertTrue(m["hasExec"]); self.assertFalse(m["pending"])
        self.assertEqual(m["text"], "do X")

    def test_postal_connector_binds_to_planted_goal(self):
        # a courier connector carries toGoal = the goal it planted in the recipient (origin.msgId match)
        md = jd.STATE / "timeline"; md.mkdir(parents=True, exist_ok=True)
        a, b = "aaaa1111", "bbbb2222"
        (md / "messages.jsonl").write_text(
            json.dumps({"ev": "sent", "id": "m1", "from_id": a, "to_id": b, "t": NOW - 30, "from": "alpha", "body": "do X"}) + "\n"
            + json.dumps({"ev": "exec", "id": "m1", "t": NOW - 20}) + "\n"
            + json.dumps({"ev": "sent", "id": "m9", "from_id": a, "to_id": b, "t": NOW - 25, "from": "alpha", "body": "fyi"}) + "\n")
        gb = "%s:g1" % b
        (jd.GOALDIR / (b + ".json")).write_text(json.dumps({
            "rompUuid": b, "seq": 1, "nodes": {gb: {"id": gb, "text": "Handed-off work", "parentId": None,
                "nodeComplete": False, "blocked": False, "cleared": False, "trail": [], "t": NOW - 20,
                "origin": {"peer": a, "goalId": a + ":g1", "msgId": "m1"}}},
            "placements": {}, "status": {gb: "working"}}))
        msgs = {m["id"]: m for m in km._postal_messages(NOW, {a, b}, {a: "alpha", b: "beta"})}
        self.assertEqual(msgs["m1"]["toGoal"], gb, "the connector binds to the goal it planted")
        self.assertIsNone(msgs["m9"]["toGoal"], "a message that planted no goal has toGoal None")

    def test_postal_connector_summary_from_captions(self):
        # the connector carries the Haiku caption (message-summaries.jsonl); the timeline shows it over
        # the verbose raw body, which stays as the fallback
        md = jd.STATE / "timeline"; md.mkdir(parents=True, exist_ok=True)
        a, b = "aaaa1111", "bbbb2222"
        (md / "messages.jsonl").write_text(
            json.dumps({"ev": "sent", "id": "m1", "from_id": a, "to_id": b, "t": NOW - 30, "from": "alpha",
                        "body": "a long verbose body that the user finds too noisy"}) + "\n"
            + json.dumps({"ev": "exec", "id": "m1", "t": NOW - 20}) + "\n")
        (md / "message-summaries.jsonl").write_text(json.dumps({"id": "m1", "summary": "asked for X"}) + "\n")
        km._msg_sum_cache.clear()
        m = km._postal_messages(NOW, {a, b}, {a: "alpha", b: "beta"})[0]
        self.assertEqual(m["summary"], "asked for X", "connector carries the caption")
        self.assertEqual(m["text"], "a long verbose body that the user finds too noisy", "raw body kept as fallback")

    def test_postal_card_carries_caption(self):
        # the incoming CHAT card carries the Haiku caption too (renderPostal shows it over the verbose
        # body, full message on hover); the raw body stays as the fallback
        md = jd.STATE / "timeline"; md.mkdir(parents=True, exist_ok=True)
        (md / "message-summaries.jsonl").write_text(json.dumps({"id": "m1", "summary": "asks to rebase onto main"}) + "\n")
        km._msg_sum_cache.clear()
        ev = {"kind": "user", "md": "see this <!-- romp-msg-id: m1 -->", "uuid": "u", "ts": "t"}
        index = {"m1": {"from": "alpha", "fromId": None, "body": "a long verbose handoff body the user finds noisy",
                        "id": "m1", "t": NOW - 30, "park": False}}
        cards = km._hydrate_postal([ev], index)
        self.assertEqual(len(cards), 1)
        self.assertEqual((cards[0]["kind"], cards[0]["direction"]), ("postal", "in"))
        self.assertEqual(cards[0]["summary"], "asks to rebase onto main", "card carries the caption")
        self.assertEqual(cards[0]["body"], "a long verbose handoff body the user finds noisy", "raw body kept (hover)")

    def test_msg_summaries_cached_until_change(self):
        md = jd.STATE / "timeline"; md.mkdir(parents=True, exist_ok=True)
        f = md / "message-summaries.jsonl"
        km._msg_sum_cache.clear()
        f.write_text(json.dumps({"id": "x", "summary": "one"}) + "\n")
        self.assertEqual(km._msg_summaries(), {"x": "one"})
        f.write_text(json.dumps({"id": "x", "summary": "a longer caption"}) + "\n")   # size change → invalidate
        self.assertEqual(km._msg_summaries(), {"x": "a longer caption"}, "re-read after the file changes")

    def test_seg_mids_extracts_markers(self):
        seg = {"atoms": [
            {"message": {"content": [{"type": "text", "text": "hi <!-- romp-msg-id: m1 -->"}]}},
            {"message": {"content": [{"type": "tool_result", "content": "inbox: <!-- romp-msg-id: m2 -->"}]}},
            {"message": {"content": "plain <!-- romp-msg-id: m3 -->"}}]}
        self.assertEqual(set(km._seg_mids(seg)), {"m1", "m2", "m3"},
                         "msg ids from text blocks, check_inbox tool_results, and string content")

    def test_bind_message_exec_id_join(self):
        """A connector binds its exec to the recipient segment that carries its msg id (process-start),
        so the line shows transit = sent → became-actionable, not the log delivery time."""
        turns = {"B": [{"start": 1000, "mids": ["m1"], "prompt": "x"}]}
        messages = [{"id": "m1", "toId": "B", "fromId": "A", "from": "alpha", "fromOrig": "alpha",
                     "sent": 900, "exec": 905, "pending": False}]
        km._bind_message_execs(messages, turns)
        self.assertEqual(messages[0]["exec"], 1000, "exec bound to the recipient's process-start")
        self.assertFalse(messages[0]["pending"])

    def test_bind_message_exec_text_heuristic(self):
        """No marker on the recipient turn → bind by a turn soon after send whose prompt names the sender."""
        turns = {"B": [{"start": 1000, "mids": [], "prompt": "picking up a note from alpha"}]}
        messages = [{"id": "m9", "toId": "B", "fromId": "A", "from": "alpha", "fromOrig": "alpha",
                     "sent": 998, "exec": 998, "pending": False}]
        km._bind_message_execs(messages, turns)
        self.assertEqual(messages[0]["exec"], 1000, "bound by the sender-naming turn")

    def test_bind_message_exec_unbound_left_alone(self):
        turns = {"B": [{"start": 1000, "mids": [], "prompt": "unrelated work"}]}
        messages = [{"id": "mz", "toId": "B", "from": "alpha", "fromOrig": "alpha",
                     "sent": 900, "exec": 905, "pending": True}]
        km._bind_message_execs(messages, turns)
        self.assertEqual((messages[0]["exec"], messages[0]["pending"]), (905, True),
                         "no id-join and no text match → connector keeps its log exec/pending")

    def test_goal_segments_collects_subtree_trails(self):
        """_goal_segments(goalId) → every segment id in the goal's subtree (the timeline work-bars to
        light when the feed card is hovered — showAskPath reverse highlight)."""
        top, sub, step = "%s:g1" % SID, "%s:g2" % SID, "%s:g3" % SID
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 3,
            "nodes": {
                top:  {"id": top,  "text": "Top",  "parentId": None, "nodeComplete": False, "blocked": False,
                       "cleared": False, "trail": ["segA"], "t": NOW - 90},
                sub:  {"id": sub,  "text": "Sub",  "parentId": top,  "nodeComplete": False, "blocked": False,
                       "cleared": False, "trail": ["segB", "segC"], "t": NOW - 80},
                step: {"id": step, "text": "Step", "parentId": sub,  "nodeComplete": True,  "blocked": False,
                       "cleared": False, "trail": ["segD"], "t": NOW - 70}},
            "placements": {}, "status": {top: "working"}}))
        self.assertEqual(set(km._goal_segments(top)), {"segA", "segB", "segC", "segD"}, "the whole subtree")
        self.assertEqual(set(km._goal_segments(sub)), {"segB", "segC", "segD"}, "a sub-goal → itself + its steps")
        self.assertEqual(km._goal_segments("%s:gX" % SID), [], "unknown goal → empty")

    def test_session_events_and_ledger_carry_tlid_dot_vs_bar(self):
        """Each event carries tlId — a message/prompt → the segment's DOT (promptId), work → the BAR
        (workId) — and a TOC bullet → the turn's DOT, so a chat hover lights the right glyph (the
        restored dot/bar split)."""
        m = km.build_session(SID, NOW)
        seg = em.segments(em.parse_session(str(self.tpath), rompuuid=SID,
                                           candidate_files=[str(self.tpath)], now=NOW)["turns"][0])[0]
        prompt_id, work_id = seg["trigger"], km._seg_anchors(seg["atoms"])[0]
        u = next(e for e in m["events"] if e["kind"] == "user")
        self.assertEqual(u["tlId"], prompt_id, "a user message lights the DOT (promptId)")
        work = [e for e in m["events"] if e["kind"] in ("assistant", "tool")]
        self.assertTrue(work and all(e["tlId"] == work_id for e in work), "work events light the BAR (workId)")
        self.assertTrue(m["ledger"]["bullets"] and all(b.get("tlId") == prompt_id for b in m["ledger"]["bullets"]),
                        "a TOC bullet lights the turn's start dot")

    def test_timeline_bars_carry_prompt_and_work_ids(self):
        """Timeline bars carry promptId (the dot atom) + workId (the bar atom) — the targets the chat
        hover's tlId matches, splitting message→dot from work→bar in the view's dotLit/barLit."""
        bars = km.build_timeline(NOW)["turns"][SID]
        seg = em.segments(em.parse_session(str(self.tpath), rompuuid=SID,
                                           candidate_files=[str(self.tpath)], now=NOW)["turns"][0])[0]
        self.assertEqual(bars[0]["promptId"], seg["trigger"], "bar promptId = the prompt atom (dot)")
        self.assertEqual(bars[0]["workId"], km._seg_anchors(seg["atoms"])[0], "bar workId = the first work atom (bar)")

    def test_hydrate_postal_in_uses_clean_body_not_boilerplate(self):
        """A received message (user text with the romp-msg-id marker) → a clean 'in' card whose body
        comes from the timeline log, NOT the delivered #### banner/footer boilerplate (the user)."""
        a = "aaaa1111"
        (jd.NAMES / a).write_text("alpha\t/dir\t#00ff00\n")
        index = {"m1": {"id": "m1", "from": "alpha", "fromId": a, "toId": SID,
                        "body": "the clean message", "t": NOW - 10, "park": False}}
        raw = ("####################\n## 📬 from alpha\n####################\n"
               "the clean message\n<!-- romp-msg-id: m1 -->\n(to reply: romp --mail send ...)")
        out = km._hydrate_postal([{"kind": "user", "md": raw, "uuid": "u1", "ts": "x", "human": False}], index)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["kind"], out[0]["direction"]), ("postal", "in"))
        self.assertEqual(out[0]["body"], "the clean message", "renders the log body, not the boilerplate")
        self.assertEqual(out[0]["peer"], "alpha")
        self.assertEqual(out[0]["color"], {"bg": "#00ff00", "fg": "#ffffff"})

    def test_hydrate_postal_out_from_send_tool(self):
        """A send_message tool call → an OUTGOING card (the sent-message rendering the user wants back)."""
        (jd.NAMES / "zzzz9999").write_text("beta\t/dir\t#0000ff\n")
        ev = {"kind": "tool", "name": "mcp__romp-postal__send_message",
              "input": json.dumps({"to": "beta", "body": "ASK: do X"}), "output": "Delivered to 'beta'.",
              "isError": False, "uuid": "t1", "ts": "x"}
        out = km._hydrate_postal([ev], {})
        self.assertEqual((out[0]["kind"], out[0]["direction"]), ("postal", "out"))
        self.assertEqual((out[0]["peer"], out[0]["body"], out[0]["status"]), ("beta", "ASK: do X", "delivered"))
        self.assertEqual(out[0]["color"], {"bg": "#0000ff", "fg": "#ffffff"}, "recipient color resolved by name")

    def test_hydrate_postal_out_from_cli_bash_send(self):
        """A `romp --mail send` Bash call → an outgoing card too, once delivery is confirmed."""
        ev = {"kind": "tool", "name": "Bash", "input": 'romp --mail send beta "hi there"',
              "output": "[romp mail] delivered to beta", "isError": False, "uuid": "t2", "ts": "x"}
        out = km._hydrate_postal([ev], {})
        self.assertEqual((out[0]["direction"], out[0]["peer"], out[0]["body"]), ("out", "beta", "hi there"))

    def test_hydrate_postal_passes_through_unresolved(self):
        """A marker with no matching log entry, or a plain event, stays unchanged (never half-rendered)."""
        ev = {"kind": "user", "md": "hi <!-- romp-msg-id: missing -->", "uuid": "u9"}
        self.assertEqual(km._hydrate_postal([ev], {}), [ev], "unresolved marker → unchanged")
        plain = {"kind": "assistant", "md": "just a reply", "uuid": "a1"}
        self.assertEqual(km._hydrate_postal([plain], {}), [plain], "a non-postal event is untouched")

    def test_ordered_alive_is_stable_under_activity(self):
        """Lanes/tabs must not auto-shuffle when a session becomes active: a fresh session is appended
        once and keeps its slot even when its mtime later jumps ahead (the user 2026-06-15)."""
        saved = km._alive_sessions
        try:
            km._alive_sessions = lambda now, tmux: [{"sid": "A", "mtime": 100}, {"sid": "B", "mtime": 50}]
            first = [s["sid"] for s in km._ordered_alive(NOW, {})]
            # B now becomes the most-recently-active (its mtime jumps past A) — the order must NOT change
            km._alive_sessions = lambda now, tmux: [{"sid": "A", "mtime": 100}, {"sid": "B", "mtime": 999}]
            second = [s["sid"] for s in km._ordered_alive(NOW, {})]
            self.assertEqual(first, ["A", "B"], "new sessions frozen newest-active-first, once")
            self.assertEqual(second, first, "activity (mtime) must not reorder existing lanes/tabs")
        finally:
            km._alive_sessions = saved

    def test_session_order_roundtrip_and_sort(self):
        # the shared order persists, and chat tabs + timeline lanes follow it (drag-sync parity)
        km._write_session_order(["b", "a", "c"])
        self.assertEqual(km._session_order(), ["b", "a", "c"])
        fake = [{"sid": "a", "mtime": 3}, {"sid": "b", "mtime": 2}, {"sid": "c", "mtime": 1}]
        saved = km._alive_sessions
        km._alive_sessions = lambda now, tmux: list(fake)
        try:
            self.assertEqual([s["sid"] for s in km._ordered_alive(NOW, {})], ["b", "a", "c"],
                             "living sessions follow the saved shared order")
        finally:
            km._alive_sessions = saved

    def test_chat_chip_sinceepoch_is_millis(self):
        # render's elapsedMs does Date.now()(ms) - sinceEpoch, so sinceEpoch must be epoch MILLIS,
        # not seconds (a seconds value rendered ~494,000h — the "400,000 hours" bug)
        st = km.build_session(SID, NOW)["status"]
        self.assertIsNotNone(st["sinceEpoch"])
        self.assertGreater(st["sinceEpoch"], 10 ** 12, "sinceEpoch is epoch millis")

    def test_timeline_lane_and_segment_bar(self):
        # the fixture wrote only a turn-grain caption; bind a segment-grain one so the bar tooltip resolves
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        seg = em.segments(session["turns"][0])[0]
        with (jd.CAPDIR / (SID + ".jsonl")).open("a") as fh:
            fh.write(json.dumps({"id": seg["id"], "grain": "segment", "t": seg["t"],
                                 "caption": "Fixed the feed flicker"}) + "\n")
        m = km.build_timeline(NOW)
        self.assertEqual(m["type"], "timeline")
        self.assertEqual(m["messages"], [], "no postal log in the test sandbox")
        self.assertIsNone(m["usage"], "no usage.json in the temp state")
        self.assertIsNone(m["focus"]); self.assertIsNone(m["hover"])
        lane = next(s for s in m["sessions"] if s["id"] == SID)
        self.assertEqual(lane["color"], "#abcdef", "lane color is the hex string, not {bg,fg}")
        self.assertEqual(lane["state"], "idle", "turn ended, no blocked goal -> idle")
        self.assertEqual(lane["model"], "", "tmux-sourced lane decorations are deferred")
        bars = m["turns"][SID]
        self.assertEqual(len(bars), 1, "the one-input turn is one segment bar")
        bar = bars[0]
        self.assertEqual(bar["start"], T0)
        self.assertGreater(bar["end"], bar["start"])
        self.assertEqual(bar["prompt"], "fix the feed flicker")
        self.assertEqual(bar["summary"], "Fixed the feed flicker", "caption binds to the segment id")
        self.assertEqual(bar["src"], "typed")
        self.assertEqual(bar["workUuid"], "a1", "first assistant atom = work anchor")
        self.assertEqual(bar["replyUuid"], "a2", "last assistant-with-text = reply anchor")
        self.assertFalse(bar["open"], "the turn ended -> bar not open")

    def test_timeline_state_and_metadata_from_tmux(self):
        # live lanes take state + model/effort/context from tmux @claude-* vars (the READY badge =
        # state "waiting"); badgeFor hides the badge unless live, so live must be true here
        km._tmux_sessions = lambda: {SID: {"state": "waiting", "since": NOW - 10, "model": "Opus 4.8",
                                           "effort": "xhigh", "context": 43, "compactPct": None,
                                           "color": "#abcdef"}}
        lane = next(s for s in km.build_timeline(NOW)["sessions"] if s["id"] == SID)
        self.assertTrue(lane["live"])
        self.assertEqual(lane["state"], "waiting", "tmux state drives the lane (waiting -> READY badge)")
        self.assertEqual(lane["model"], "Opus 4.8")
        self.assertEqual(lane["effort"], "xhigh")
        self.assertEqual(lane["context"], 43)

    def test_chat_chip_maps_tmux_state(self):
        # the chat chip maps tmux state: permission -> awaiting, plus model/effort/ctx for the statusline
        km._tmux_sessions = lambda: {SID: {"state": "permission", "since": NOW - 5, "model": "Opus 4.8",
                                           "effort": "max", "context": 20, "compactPct": None, "color": None}}
        st = km.build_session(SID, NOW)["status"]
        self.assertEqual(st["state"], "awaiting", "permission -> awaiting chip")
        self.assertEqual(st["model"], "Opus 4.8")
        self.assertEqual(st["ctx"], "20")


class CrossPane(unittest.TestCase):
    def test_send_to_app_routes_by_app(self):
        got = {"chat": [], "feed": []}
        chat = {"app": "chat", "send": lambda s: got["chat"].append(s), "alive": True}
        feed = {"app": "feed", "send": lambda s: got["feed"].append(s), "alive": True}
        with km._clients_lock:
            km._clients[:] = [chat, feed]
        try:
            km._send_to_app("chat", {"type": "focus", "id": "S1"})
        finally:
            with km._clients_lock:
                km._clients[:] = []
        self.assertEqual(len(got["chat"]), 1, "only chat clients get the chat-routed message")
        self.assertEqual(len(got["feed"]), 0)
        self.assertIn("focus", got["chat"][0]); self.assertIn("S1", got["chat"][0])

    def test_showontimeline_anchor_maps_to_focus_kind(self):
        # a feed TITLE click sends anchor:"prompt" → land on the user's MESSAGE turn; a sub-thing /
        # work click sends no anchor → the nearest turn (the assistant response). (the user 2026-06-15)
        self.assertEqual(km._focus_kind("prompt"), "user")
        self.assertIsNone(km._focus_kind("work"))
        self.assertIsNone(km._focus_kind(None))


class FeedDetail(unittest.TestCase):
    def test_read_feed_detail_cache(self):
        # the expand paragraph that fills the feed-card modal's "…": present in cache → returned;
        # missing → None; empty paragraph (the writer wrote nothing for a legacy id) → None.
        import tempfile, pathlib
        orig = km.FEEDDETAIL
        with tempfile.TemporaryDirectory() as td:
            km.FEEDDETAIL = pathlib.Path(td)
            try:
                (km.FEEDDETAIL / "D1.json").write_text(json.dumps({"paragraph": "shipped the fix", "next_steps": ["watch CI"]}))
                self.assertEqual(km._read_feed_detail("D1")["paragraph"], "shipped the fix")
                self.assertIsNone(km._read_feed_detail("nope"), "no cache file → None")
                (km.FEEDDETAIL / "E.json").write_text(json.dumps({"paragraph": ""}))
                self.assertIsNone(km._read_feed_detail("E"), "empty paragraph → None")
            finally:
                km.FEEDDETAIL = orig


class TmuxInject(unittest.TestCase):
    def test_tmux_send_sequence(self):
        calls = []
        real_run, real_sleep = km.subprocess.run, km.time.sleep
        km.subprocess.run = lambda args, **k: calls.append(list(args)) or type("R", (), {"stdout": ""})()
        km.time.sleep = lambda s: None
        try:
            km._tmux_send("mysess", "hello world", _async=False)
        finally:
            km.subprocess.run, km.time.sleep = real_run, real_sleep
        # set-buffer the text → bracketed paste-buffer to the session → Enter to submit
        self.assertTrue(any(a[:2] == ["tmux", "set-buffer"] and "hello world" in a for a in calls))
        self.assertTrue(any(a[:2] == ["tmux", "paste-buffer"] and "mysess" in a for a in calls))
        self.assertTrue(any(a[:2] == ["tmux", "send-keys"] and "Enter" in a for a in calls))


class ParentWatch(unittest.TestCase):
    def test_pid_alive(self):
        self.assertTrue(km._pid_alive(os.getpid()))
        self.assertFalse(km._pid_alive(2147483646), "a non-existent pid is not alive")


class WsFraming(unittest.TestCase):
    def test_accept_key(self):
        # RFC6455 example key → accept
        self.assertEqual(km._ws_accept("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")


class ServeSecurity(unittest.TestCase):
    """The serve-layer gate (design/read-side.md): Origin/Host validation on every request AND the
    /ws upgrade (kills the cross-site WS hole token-free), + ROMP_SERVE_TOKEN for non-local reach.
    Runs the REAL handler over a loopback server (GET /feed is a static page → no model calls)."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _code(self, path, headers):
        import urllib.request, urllib.error
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_local_request_allowed(self):
        self.assertEqual(self._code("/feed", {}), 200)

    def test_restart_endpoint_acks_post(self):
        """The web Restart button (↻) POSTs /restart; the kernel must ACK {ok,restarting} (and, with a
        manager, relay /restart-all so the kernel process relaunches). Regression guard: the Python
        rewrite dropped do_POST entirely, so the button silently no-op'd and the user had to pkill.
        No ROMP_MANAGER_PORT here → it acks without restarting anything."""
        import urllib.request, json as _json
        saved = os.environ.pop("ROMP_MANAGER_PORT", None)   # never trigger a real restart-all in a test
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/restart" % self.port, method="POST", data=b"")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(_json.loads(r.read().decode()), {"ok": True, "restarting": True})
        finally:
            if saved is not None:
                os.environ["ROMP_MANAGER_PORT"] = saved

    def test_unknown_post_path_is_404(self):
        import urllib.request, urllib.error
        req = urllib.request.Request("http://127.0.0.1:%d/nope" % self.port, method="POST", data=b"")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        self.assertEqual(code, 404)

    def test_timeline_page_served(self):
        # the combined shell's third pane: /timeline injects the shared obsidian TimelinePanel verbatim
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d/timeline" % self.port, timeout=5) as r:
            self.assertEqual(r.status, 200)
            body = r.read().decode("utf-8", "replace")
        self.assertIn("TimelinePanel", body, "the shared obsidian view is injected")
        self.assertIn("app=timeline", body, "the page drives panel.update over the kernel WS")

    def test_landing_has_three_panes(self):
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d/" % self.port, timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
        for pane in ("src=/chat", "src=/feed", "src=/timeline"):
            self.assertIn(pane, body)

    def test_cross_site_origin_rejected(self):
        self.assertEqual(self._code("/feed", {"Origin": "http://evil.example"}), 403)

    def test_cross_site_ws_upgrade_rejected(self):
        # the ClawJacked hole: a foreign-Origin /ws upgrade must be rejected before upgrading
        self.assertEqual(self._code("/ws?app=chat", {
            "Origin": "http://evil.example", "Upgrade": "websocket", "Connection": "Upgrade",
            "Sec-WebSocket-Key": "x", "Sec-WebSocket-Version": "13"}), 403)

    def test_same_origin_ws_passes_gate(self):
        # same-origin upgrade passes the gate (101); urllib can't complete the upgrade, so a 101
        # surfaces as a non-403 — assert it's NOT rejected
        self.assertNotEqual(self._code("/ws?app=chat", {
            "Origin": "http://127.0.0.1:%d" % self.port, "Host": "127.0.0.1:%d" % self.port,
            "Upgrade": "websocket", "Connection": "Upgrade",
            "Sec-WebSocket-Key": "x", "Sec-WebSocket-Version": "13"}), 403)

    def test_healthz_exempt(self):
        self.assertEqual(self._code("/healthz", {"Origin": "http://evil.example"}), 200)

    def test_nonlocal_host_needs_token(self):
        h = {"Host": "100.64.1.2:%d" % self.port}
        self.assertEqual(self._code("/feed", h), 403)
        self.assertEqual(self._code("/feed?token=testtok", h), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
