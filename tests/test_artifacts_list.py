#!/usr/bin/env python3
"""The Artifacts pane's kernel side (plans/artifacts-pane.md, 2026-09-19): the three rules over a parsed session's turns
(the edit tools' file_path and notebook_path; the chat's path tokens and image paths in assistant prose; a drop's saved
path in the person's own user turn), Bash not read; the listing (newest first, one entry per path with the latest mention
winning, a missing file marked, the route's refusal marked, the pane's own two rules, the cap); the listArtifacts op's
request and response shape; the page served at /artifacts; the pane key in the shell's pane set. Every walk and listing
test asks the way the pane asks, through the op on a fake socket over a session whose parse the cache stub answers, and
the page test drives the real GET dispatcher: at the base each red is the pane's own behaviour (the op unanswered, a row
missing, the route answering 404, the landing lacking the rail button), never a helper's missing name (round two, M4).
Synthetic only: a hermetic state root, a private placeholder sid, invented paths under the test's own temp folder."""
import inspect
import io
import html as html_mod
import json
import re
import os
import sys
import tempfile
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))

SID = "11111111-2222-3333-4444-000000000931"
OLD = "11111111-2222-3333-4444-000000000932"     # a second placeholder: the session idle past the caption window (M1), the unknown sid
MAX = 500                                        # the listing's cap (the page says when it bound); a literal here, so the base reds on the count, not on a name
KSRC = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py")).read()


def _atom(kind, t, blocks=None, text=None, author=None, uuid=None):
    content = blocks if blocks is not None else [{"type": "text", "text": text or ""}]
    a = {"type": kind, "t": t, "uuid": uuid or ("u%d" % t), "message": {"role": kind, "content": content}}
    if kind == "user":
        a["author"] = author if author is not None else "human"
    return a


def _tool(name, **inp):
    return {"type": "tool_use", "id": "tu-%s" % name, "name": name, "input": inp}


def _write(t, path):
    return _atom("assistant", t, blocks=[_tool("Write", file_path=path, content="x")])


def _serve_get(path, headers=None):
    """Drive the REAL do_GET dispatcher over a fake socket: (status, body). The auth-hardening tests' shape."""
    h = km.Handler.__new__(km.Handler)
    h.client_address = ("127.0.0.1", 0)
    h.headers = dict(headers or {})
    h.path = path
    h.command = "GET"
    h.request_version = "HTTP/1.1"
    h.wfile = io.BytesIO()
    h.rfile = io.BytesIO()
    h.close_connection = True
    captured = {}
    h.send_response = lambda code, *a: captured.__setitem__("status", code)
    h.send_header = lambda k, v: None
    h.end_headers = lambda: None
    h.log_message = lambda *a: None
    h.do_GET()
    return captured.get("status"), h.wfile.getvalue().decode("utf-8", "replace")


class World:
    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.cwd = root / "notes-api"; self.cwd.mkdir()
        (self.cwd / "figures").mkdir()
        self.claude = self.cwd / ".claude-cfg"; self.claude.mkdir()    # the Claude configuration directory, INSIDE the session's folder: confined, so only the pane's own rule can refuse it (M3)
        self.orig_claude = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.claude)
        self.orig_state, self.orig_names = km.jd.STATE, km.NAMES
        km.jd._rebind_state(root / "state")
        (km.jd.STATE / "session-hosts").parent.mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "session-hosts").write_text("off\n")
        km.jd.NAMES.mkdir(parents=True, exist_ok=True)
        (km.jd.NAMES / SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % self.cwd)
        km.NAMES = km.jd.NAMES
        km._live_scope.names = None
        (km.jd.STATE / "drops").mkdir(parents=True, exist_ok=True)
        self.saved = (km._cwd_of,)
        km._cwd_of = lambda sid: str(self.cwd) if sid == SID else None

    def close(self):
        (km._cwd_of,) = self.saved
        km.jd._rebind_state(self.orig_state); km.NAMES = self.orig_names
        if self.orig_claude is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self.orig_claude
        self.td.cleanup()

    def file(self, rel, data=b"x"):
        p = self.cwd / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return str(p)

    def drop(self, name, data=b"d"):
        p = km.jd.STATE / "drops" / ("1700000000000-" + name); p.write_bytes(data); return str(p)


class ViaOp(unittest.TestCase):
    """The listing the way the pane asks for it: listArtifacts on a fake socket over a session the sweep names, whose
    parse the cache stub answers with the turns the test wrote. The session doors are stubbed too (no SDK registry, an
    empty wide walk), so the one-sid resolution is the sweep's answer unless a test says otherwise."""

    def setUp(self):
        self.w = World()
        self.path = str(self.w.cwd / "transcript.jsonl")
        self.saved = (km._sessions, km._parse_cached, km.jd.parsed_session, km._sdk, km._discover_wide, dict(km._PATH_LINK_CACHE))
        km._sessions = lambda now, window=None, forks=True: [{"sid": SID, "name": "web", "path": self.path, "mtime": 1}]
        km._sdk = lambda: None
        km._discover_wide = lambda now, window: {}
        self.cached = None
        km._parse_cached = lambda path: self.cached
        self.parsed = {"turns": []}
        self.parses = []
        km.jd.parsed_session = lambda sid, files, now, **kw: (self.parses.append((sid, list(files), kw)) or self.parsed)

    def tearDown(self):
        km._sessions, km._parse_cached, km.jd.parsed_session, km._sdk, km._discover_wide, cache = self.saved
        km._PATH_LINK_CACHE.clear(); km._PATH_LINK_CACHE.update(cache)
        self.w.close()

    def ask(self, sid=SID, req=1):
        sent = []
        client = {"app": "artifacts", "wid": "w1", "alive": True, "send": lambda raw: sent.append(json.loads(raw))}
        km.Handler._dispatch_ws(None, {"type": "listArtifacts", "sid": sid, "reqId": req}, client)
        self.assertEqual(len(sent), 1, "the op is answered on the asking socket")
        r = sent[0]
        self.assertEqual((r.get("type"), r.get("reqId"), r.get("sid")), ("artifactsListing", req, sid), "the listing, by request id: %r" % r)
        return r

    def listing(self, turns, link_cache=None):
        self.cached = {"turns": turns}
        km._PATH_LINK_CACHE.clear(); km._PATH_LINK_CACHE.update(link_cache or {})
        r = self.ask()
        self.assertEqual(r["error"], "")
        return r

    @staticmethod
    def rows(r):
        return [(it["path"], it["t"], it["via"]) for it in r["items"]]


class Walk(ViaOp):
    def test_rule_one_reads_the_edit_tools_paths_and_not_a_bash_command(self):
        w = self.w
        turns = [{"t": 100, "atoms": [
            _atom("assistant", 100, blocks=[_tool("Write", file_path=str(w.cwd / "report.md"), content="# r")]),
            _atom("assistant", 110, blocks=[_tool("Edit", file_path="src/app.py", old_string="a", new_string="b")]),           # relative: the session's cwd
            _atom("assistant", 120, blocks=[_tool("MultiEdit", file_path=str(w.cwd / "src" / "app.py"), edits=[])]),
            _atom("assistant", 130, blocks=[_tool("NotebookEdit", notebook_path=str(w.cwd / "nb.ipynb"), new_source="x")]),
            _atom("assistant", 140, blocks=[_tool("Bash", command="python plot.py > %s" % (w.cwd / "figures" / "loss.png"))]),   # the road not taken
            _atom("assistant", 150, blocks=[_tool("Read", file_path=str(w.cwd / "README.md"))]),                                 # a read is not a put
        ]}]
        r = self.listing(turns)
        self.assertEqual(self.rows(r), [(str(w.cwd / "nb.ipynb"), 130, "notebook"), (str(w.cwd / "src" / "app.py"), 120, "multiedit"), (str(w.cwd / "report.md"), 100, "write")],
                         "newest first; app.py once, by its latest edit; the Bash redirect and the Read are not puts")

    def test_rule_two_reads_the_paths_the_chat_would_link_and_render_from_the_prose(self):
        w = self.w
        real = w.file("figures/accuracy.png", b"\x89PNG")
        turns = [{"t": 200, "atoms": [
            _atom("assistant", 200, text="The figure is at %s and the notes in %s" % (real, str(w.cwd / "notes.md")), uuid="a1"),   # notes.md does not exist
            _atom("assistant", 210, text="A plot at %s (not written yet) and see docs/guide.md for the rest." % (w.cwd / "figures" / "later.png"), uuid="a2"),
            _atom("assistant", 220, text="Also file://%s" % real, uuid="a3"),
            _atom("user", 230, text="thanks, %s looks right" % real),                                                          # the person's prose is not the session's
        ]}]
        cache = {(SID, "a1"): ({str(w.cwd / "notes.md"): str(w.cwd / "notes.md")}, (), {})}                                    # the chat verified notes.md when it built that message
        rows = self.rows(self.listing(turns, link_cache=cache))
        self.assertEqual([x for x in rows if x[0] == real], [(real, 220, "rendered")], "an existing image path in the prose, dated by its latest mention (the file:// URI names the same file; the person's own prose at 230 is not the session's output)")
        self.assertIn((str(w.cwd / "notes.md"), 200, "rendered"), rows, "a path the chat verified for that message, gone now: listed (and marked missing)")
        self.assertIn((str(w.cwd / "figures" / "later.png"), 210, "rendered"), rows, "an image path by extension: the figure rule renders it at its mention")
        self.assertNotIn(str(w.cwd / "docs" / "guide.md"), [x[0] for x in rows], "a bare path-shaped word that is no file and was never verified is not an artifact")

    def test_rule_three_reads_a_drop_in_the_persons_turn_as_an_image_block_or_as_text(self):
        w = self.w
        d1 = w.drop("sketch.png"); d2 = w.drop("data.csv")
        elsewhere = w.file("figures/mine.png")
        turns = [{"t": 300, "atoms": [
            _atom("user", 300, blocks=[{"type": "image", "source": {"type": "path", "path": d1}}, {"type": "text", "text": "what do you make of this?"}]),
            _atom("user", 310, text="and the numbers: %s" % d2),
            _atom("user", 320, text="compare with %s" % elsewhere),                                                           # a user path outside drops: not a drop
            _atom("user", 330, text="a peer's note naming %s" % d1, author="teammate"),                                     # not the person's turn
        ]}]
        self.assertEqual(self.rows(self.listing(turns)), [(d2, 310, "drop"), (d1, 300, "drop")])

    def test_the_listing_keeps_one_entry_per_path_newest_first_marks_missing_and_refused_and_caps(self):
        w = self.w
        real = w.file("report.md", b"# r"); secret = w.file(".env", b"KEY=1"); gone = str(w.cwd / "gone.md")
        outside = str(Path(tempfile.gettempdir()) / ("romp-art-outside-%d.txt" % os.getpid())); Path(outside).write_text("x")
        try:
            turns = [{"t": 100, "atoms": [_write(100, real), _write(105, gone), _atom("assistant", 120, text="the report at %s" % real), _write(130, secret), _write(140, outside)]}]
            r = self.listing(turns)
            self.assertEqual((r["capped"], r["max"]), (False, MAX))
            self.assertEqual(self.rows(r), [(outside, 140, "write"), (secret, 130, "write"), (real, 120, "rendered"), (gone, 105, "write")],
                             "newest first; report.md once, dated and worded by its latest mention")
            by = {it["path"]: it for it in r["items"]}
            self.assertEqual((by[real]["exists"], by[real]["kind"], by[real]["refused"], by[real]["name"]), (True, "markdown", "", "report.md"))
            self.assertEqual((by[gone]["exists"], by[gone]["size"], by[gone]["mtime"]), (False, None, None), "a missing file is listed and marked, never hidden")
            self.assertEqual(by[secret]["refused"], "a secrets-shaped name", "the route's own refusal, named")
            self.assertTrue(by[outside]["refused"].startswith("outside the session"), by[outside]["refused"])
            many = [{"t": 1000, "atoms": [_write(1000 + i, str(w.cwd / ("f%04d.md" % i))) for i in range(MAX + 7)]}]
            r = self.listing(many)
            self.assertTrue(r["capped"]); self.assertEqual(len(r["items"]), MAX); self.assertEqual(r["items"][0]["t"], 1000 + MAX + 6, "the newest survive the cap")
        finally:
            os.unlink(outside)

    def test_the_panes_own_two_rules_and_a_drops_name_under_any_rule(self):
        # round two (2026-09-19): M3, a path under the Claude configuration directory is refused by the pane's own rule (the route
        # serves it: home is a confinement root); low a, a drop keeps its dropped name whichever rule named it last; low b, a kind
        # the preview does not show is an ordinary kind, listed plain, the route's confinement still judging it
        w = self.w
        cfg = w.claude / "todos" / "notes.md"; cfg.parent.mkdir(); cfg.write_text("# t")
        d = w.drop("sketch.png", b"\x89PNG")
        model = w.file("data/model.pkl", b"\x80\x04\x95")
        outside = str(Path(tempfile.gettempdir()) / ("romp-art-outside-%d.pkl" % os.getpid())); Path(outside).write_bytes(b"\x80")
        try:
            turns = [{"t": 400, "atoms": [
                _write(400, str(cfg)),
                _atom("user", 410, blocks=[{"type": "image", "source": {"type": "path", "path": d}}, {"type": "text", "text": "this one"}]),
                _atom("assistant", 420, text="I cleaned up %s and saved the model to %s" % (d, model)),
                _write(430, outside),
            ]}]
            by = {it["path"]: it for it in self.listing(turns)["items"]}
            self.assertEqual((by[str(cfg)]["exists"], by[str(cfg)]["kind"], by[str(cfg)]["refused"]), (True, "markdown", "under the Claude configuration directory"),
                             "the agent's own state, named by the thread: listed, marked, never fetched")
            self.assertEqual((by[d]["via"], by[d]["name"], by[d]["refused"]), ("rendered", "sketch.png", ""), "the drop's dropped name, though the prose named it last")
            self.assertEqual((by[model]["kind"], by[model]["refused"]), ("other", ""), "kind other is listed plain")
            self.assertEqual((by[outside]["kind"], by[outside]["refused"]), ("other", "outside the session's folder and your home"), "the route's confinement still judges a kind-other file")
        finally:
            os.unlink(outside)


class Listing(ViaOp):
    def setUp(self):
        super().setUp()
        self.parsed = {"turns": [{"t": 100, "atoms": [_write(100, str(self.w.cwd / "report.md"))]}]}

    def test_the_listing_reads_the_cached_parse_first_and_parses_once_under_the_readers_key_when_it_misses(self):
        r = self.ask(req=1)
        self.assertEqual(r["error"], ""); self.assertEqual([it["name"] for it in r["items"]], ["report.md"]); self.assertEqual((r["capped"], r["max"]), (False, MAX))
        self.assertEqual([(p[0], p[1]) for p in self.parses], [(SID, [self.path])], "the cache missed: one parse into the shared store")
        # low d (round two): the write goes under the key the reader (_parse_cached, the chat's build) reads: the states log and the
        # display's sdk_human; under another key the first write never satisfied the first read and every request re-parsed
        kw = self.parses[0][2]
        self.assertEqual(kw.get("states"), str(km.jd.STATE / "states" / (SID + ".jsonl")), "the states log path the chat's build passes")
        self.assertEqual(kw.get("sdk_human"), km._display_sdk_human(SID), "the display's sdk_human answer")
        self.cached = self.parsed
        r = self.ask(req=2)
        self.assertEqual(len(self.parses), 1, "a warm cache: no parse")
        r = self.ask(sid=OLD, req=3)
        self.assertEqual((r["error"], r["items"]), ("no session with that id has a transcript here", []))

    def test_a_session_idle_past_the_caption_window_still_lists(self):
        # M1 (round two): the selector is the picker's thirty-day list while the sweep reaches back 48 hours, so a session idle two
        # days was offered and answered "no transcript here"; the one-sid API (_session_row) resolves it through the wide walk
        km._sessions = lambda now, window=None, forks=True: []                                       # idle past the sweep's window: not in it
        km._discover_wide = lambda now, window: {SID: (SID, Path(self.path), SID, "web")}         # discover's cached wide walk knows it
        r = self.ask(req=4)
        self.assertEqual(r["error"], "", "a five-day-old session lists")
        self.assertEqual([it["name"] for it in r["items"]], ["report.md"])

    def test_the_op_answers_the_asking_socket_by_request_id_with_the_listing(self):
        sent = []
        client = {"app": "artifacts", "wid": "w1", "alive": True, "send": lambda raw: sent.append(json.loads(raw))}
        km.Handler._dispatch_ws(None, {"type": "listArtifacts", "sid": SID, "reqId": 7}, client)
        self.assertEqual(len(sent), 1); r = sent[0]
        self.assertEqual((r["type"], r["reqId"], r["sid"], r["error"], r["capped"], r["max"]), ("artifactsListing", 7, SID, "", False, MAX))
        self.assertEqual([it["name"] for it in r["items"]], ["report.md"])
        km.Handler._dispatch_ws(None, {"type": "listArtifacts", "reqId": 8}, client)
        self.assertEqual((sent[1]["error"], sent[1]["items"]), ("no session named", []))


def _has(tc, needle, hay):
    tc.assertIn(needle, hay)


class Shell(unittest.TestCase):
    """The dashboard's sixth pane is a RECORD in the kernel's _CODE_PANES (plans/panes-as-data.md, phase three: id artifacts, title
    Artifacts, source /artifacts, off by default, experimental), rendered by the GENERIC pane build like a data pane: its rail
    button, its gutter and column after Files, its column and gutter rules, its row in body[data-panes] for the inline scripts
    and the gear's Panes row, no phone tab (experimental). None of the hand-written hooks of its first landing remain, and its
    bespoke control (showArtifactsControl) is gone: the gear's generic row, off by default, is the control; the iframe takes
    its src only when the pane comes ON SCREEN (the round-two M2 constraint), never when merely enabled."""

    def setUp(self):
        self.html = km._landing()

    def test_the_landing_renders_the_record_generically_and_no_hand_hook_remains(self):
        h = self.html
        rec = next(p for p in km._CODE_PANES if p["id"] == "artifacts")
        self.assertEqual(rec, {"id": "artifacts", "title": "Artifacts", "source": "/artifacts", "on": False, "experimental": True, "protocol": "romp"})
        _has(self, "<div class=rail-btn data-pane=artifacts>Artifacts</div>", h)
        self.assertNotIn("<button data-pane=artifacts>", h, "experimental: no phone tab")
        _has(self, '<div class=gv id=gv-artifacts></div><div class=pane id=artifacts-pane><iframe id=f-artifacts data-src="/artifacts" data-protocol=romp></iframe></div>', h)
        self.assertLess(h.index("id=files-pane"), h.index("id=gv-artifacts")); self.assertLess(h.index("id=artifacts-pane"), h.index("id=gv-ghost"))
        _has(self, "#artifacts-pane{flex:var(--g-artifacts,40) 1 0}body:not(.po-artifacts) #artifacts-pane{display:none}", h)
        _has(self, "body:not(.po-artifacts) #gv-artifacts,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files) #gv-artifacts{display:none}", h)
        m = re.search(r"<body class='po-chat po-feed po-timeline' data-panes=\"([^\"]*)\">", h)
        self.assertIsNotNone(m, "the record rides the attribute the inline scripts and the gear read")
        rows = json.loads(html_mod.unescape(m.group(1)))
        self.assertEqual(rows[0], {"id": "artifacts", "title": "Artifacts", "protocol": "romp", "experimental": True, "on": False, "builtin": True})
        for gone in ("gv-d", "artifactsCtl", "no-artifacts-control", "showArtifactsControl", "po-artifacts',!!po.artifacts", "artifacts:false", "'f-artifacts':'artifacts-pane'", "artifacts:'artifacts pane'",
                     "grow={chat:60,fleet:34,feed:40,files:40,artifacts:40}", "'files':'artifacts'"):
            self.assertNotIn(gone, h, "a hand-written hook of the first landing remains: %r" % gone)
        for name in ("_LANDING_FOCUS_JS", "_LANDING_ESC_JS", "_LANDING_MOBILE_JS", "_LANDING_COLLAPSE_JS", "_LANDING_JS"):
            self.assertNotIn("artifacts", getattr(km, name), "%s names the pane by hand" % name)
        self.assertEqual(dict(km._PANE_ORDER).get("artifacts"), "Artifacts"); _has(self, "var PN=" + json.dumps(dict(km._PANE_ORDER)) + ";", km._LANDING_ERRS_JS)

    def test_the_generic_build_gates_the_load_on_the_pane_coming_on_screen_never_on_the_gear_alone(self):
        # round two, M2: a dashboard load with the pane enabled in the gear but off screen must not load the page (its first load
        # walks the remembered session's transcript). The generic build: the reconcile copies data-src to src for a HAND-written
        # optional pane when enabled, never for a generic one (DPX); the apply copies it for a generic pane when its po flag is on.
        js = km._LANDING_COLLAPSE_JS
        _has(self, "if(en){if(!(k in DPX)&&f&&!f.getAttribute('src')&&f.getAttribute('data-src'))f.setAttribute('src',f.getAttribute('data-src'));", js)
        _has(self, "var gf=document.getElementById('f-'+k);if(po[k]&&gf&&!gf.getAttribute('src')&&gf.getAttribute('data-src'))gf.setAttribute('src',gf.getAttribute('data-src'));", js)
        _has(self, "function optOn(){var on={};OPT.forEach(function(k){on[k]=!DPX[k];});", js)   # an experimental record is off in the gear until asked for
        self.assertNotIn("showArtifactsControl", open(os.path.join(ROOT, "ui", "webview", "settings.ts")).read(), "the bespoke key is gone")
        self.assertNotIn("rs-artctl", open(os.path.join(ROOT, "ui", "webview", "gear.js")).read(), "the bespoke gear row is gone: the generic Panes row is the control")

    def test_the_pane_is_in_the_one_ordering_after_files_and_the_viewer_set(self):
        self.assertEqual(km._PANE_ORDER[-1], ("artifacts", "Artifacts")); self.assertEqual(km._PANE_ORDER[-2], ("files", "Files"))
        self.assertIn('c.get("app") in ("chat", "fleet", "timeline", "feed", "files", "artifacts")', KSRC, "a dashboard with only this pane open counts as a viewer")

    def test_the_page_is_served_at_its_route_with_the_no_stale_shim_and_its_bundle(self):
        status, html = _serve_get("/artifacts", {"X-Romp-Token": km.TOKEN})
        self.assertEqual(status, 200, "the route answers the pane's page")
        self.assertIn("<title>Romp · artifacts</title>", html); self.assertIn("<body class=artifacts-pane>", html); self.assertIn("<div id=artifacts-root></div>", html)
        self.assertIn("/dist/artifacts.js?v=", html); self.assertIn("/dist/federation.js?v=", html); self.assertIn("/dist/styles.css?v=", html)
        self.assertIn('_shim("artifacts", v, no_stale=True)', inspect.getsource(km._artifacts_page), "no pushed view: the stale prompt is never armed for this page")
        self.assertIn(".art-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))", html, "the pane's own stylesheet rides the page")
        self.assertIn(".art-note{", html, "the note beside the count: what the last click could not do (round two, low b)")


if __name__ == "__main__":
    unittest.main()
