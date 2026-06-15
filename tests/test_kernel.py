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
        km._tmux_sessions = lambda: {}                 # deterministic: no live tmux in tests (builders fall back)
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        turn = session["turns"][0]
        jd.CAPDIR.mkdir(parents=True)
        (jd.CAPDIR / (SID + ".jsonl")).write_text(
            json.dumps({"id": turn["id"], "grain": "turn", "t": turn["t"], "caption": "Fixed the feed flicker"}) + "\n")
        jd.ARCHDIR.mkdir(parents=True)
        (jd.ARCHDIR / (SID + ".json")).write_text(json.dumps(
            {"headline": "Fixing the feed", "abstract": "Fixed a flicker.", "turns": 1}))
        jd.GOALDIR.mkdir(parents=True)
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 1, "lastNode": "%s:g1" % SID,
            "nodes": {"%s:g1" % SID: {"id": "%s:g1" % SID, "text": "Fix the feed flicker", "parentId": None,
                                      "nodeComplete": True, "blocked": False, "cleared": False,
                                      "trail": [], "t": turn["t"]}},
            "placements": {}, "status": {"%s:g1" % SID: "completed"}}))

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km._tmux_sessions) = self.saved
        self.td.cleanup()

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

    def test_timeline_lane_and_segment_bar(self):
        # the fixture wrote only a turn-grain caption; bind a segment-grain one so the bar tooltip resolves
        session = em.parse_session(str(self.tpath), rompuuid=SID, candidate_files=[str(self.tpath)], now=NOW)
        seg = em.segments(session["turns"][0])[0]
        with (jd.CAPDIR / (SID + ".jsonl")).open("a") as fh:
            fh.write(json.dumps({"id": seg["id"], "grain": "segment", "t": seg["t"],
                                 "caption": "Fixed the feed flicker"}) + "\n")
        m = km.build_timeline(NOW)
        self.assertEqual(m["type"], "timeline")
        self.assertEqual(m["messages"], [], "connectors are a later (courier) increment")
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
