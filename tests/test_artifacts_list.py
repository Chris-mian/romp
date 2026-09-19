#!/usr/bin/env python3
"""The Artifacts pane's kernel side (plans/artifacts-pane.md, 2026-09-19): the three rules over a parsed session's turns
(the edit tools' file_path and notebook_path; the chat's path tokens and image paths in assistant prose; a drop's saved
path in the person's own user turn), Bash not read; the listing (newest first, one entry per path with the latest mention
winning, a missing file marked, the route's refusal marked, the cap); the listArtifacts op's request and response shape;
the page served at /artifacts; the pane key in the shell's pane set. Synthetic only: a hermetic state root, a private
placeholder sid, invented paths under the test's own temp folder."""
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))

SID = "11111111-2222-3333-4444-000000000931"
KSRC = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py")).read()


def _atom(kind, t, blocks=None, text=None, author=None, uuid=None):
    content = blocks if blocks is not None else [{"type": "text", "text": text or ""}]
    a = {"type": kind, "t": t, "uuid": uuid or ("u%d" % t), "message": {"role": kind, "content": content}}
    if kind == "user":
        a["author"] = author if author is not None else "human"
    return a


def _tool(name, **inp):
    return {"type": "tool_use", "id": "tu-%s" % name, "name": name, "input": inp}


class World:
    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.cwd = root / "notes-api"; self.cwd.mkdir()
        (self.cwd / "figures").mkdir()
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
        self.td.cleanup()

    def file(self, rel, data=b"x"):
        p = self.cwd / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return str(p)

    def drop(self, name, data=b"d"):
        p = km.jd.STATE / "drops" / ("1700000000000-" + name); p.write_bytes(data); return str(p)


class Walk(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

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
        got = km._artifacts_walk(turns, SID, link_cache={})
        self.assertEqual(got, [(str(w.cwd / "report.md"), 100, "write"), (str(w.cwd / "src" / "app.py"), 110, "edit"),
                               (str(w.cwd / "src" / "app.py"), 120, "multiedit"), (str(w.cwd / "nb.ipynb"), 130, "notebook")])

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
        got = km._artifacts_walk(turns, SID, link_cache=cache)
        self.assertIn((real, 200, "rendered"), got, "an existing image path in the prose")
        self.assertIn((str(w.cwd / "notes.md"), 200, "rendered"), got, "a path the chat verified for that message, gone now: listed (and marked missing later)")
        self.assertIn((str(w.cwd / "figures" / "later.png"), 210, "rendered"), got, "an image path by extension: the figure rule renders it at its mention")
        self.assertNotIn((str(w.cwd / "docs" / "guide.md"), 210, "rendered"), got, "a bare path-shaped word that is no file and was never verified is not an artifact")
        self.assertIn((real, 220, "rendered"), got, "a file:// URI names the same file")
        self.assertEqual([m for m in got if m[1] == 230], [], "the person's own prose is not the session's output")

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
        got = km._artifacts_walk(turns, SID, link_cache={})
        self.assertEqual(got, [(d1, 300, "drop"), (d2, 310, "drop")])

    def test_the_listing_keeps_one_entry_per_path_newest_first_marks_missing_and_refused_and_caps(self):
        w = self.w
        real = w.file("report.md", b"# r"); secret = w.file(".env", b"KEY=1"); gone = str(w.cwd / "gone.md")
        outside = str(Path(tempfile.gettempdir()) / ("romp-art-outside-%d.txt" % os.getpid())); Path(outside).write_text("x")
        try:
            mentions = [(real, 100, "write"), (gone, 105, "write"), (real, 120, "rendered"), (secret, 130, "write"), (outside, 140, "write")]
            items, capped = km._artifacts_items(mentions, SID)
            self.assertFalse(capped)
            self.assertEqual([(it["path"], it["t"], it["via"]) for it in items], [(outside, 140, "write"), (secret, 130, "write"), (real, 120, "rendered"), (gone, 105, "write")],
                             "newest first; report.md once, dated and worded by its latest mention")
            by = {it["path"]: it for it in items}
            self.assertEqual((by[real]["exists"], by[real]["kind"], by[real]["refused"], by[real]["name"]), (True, "markdown", "", "report.md"))
            self.assertEqual((by[gone]["exists"], by[gone]["size"], by[gone]["mtime"]), (False, None, None), "a missing file is listed and marked, never hidden")
            self.assertEqual(by[secret]["refused"], "a secrets-shaped name", "the route's own refusal, named")
            self.assertTrue(by[outside]["refused"].startswith("outside the session"), by[outside]["refused"])
            many = [(str(w.cwd / ("f%04d.md" % i)), 1000 + i, "write") for i in range(km.ARTIFACTS_MAX + 7)]
            items, capped = km._artifacts_items(many, SID)
            self.assertTrue(capped); self.assertEqual(len(items), km.ARTIFACTS_MAX); self.assertEqual(items[0]["t"], 1000 + km.ARTIFACTS_MAX + 6, "the newest survive the cap")
        finally:
            os.unlink(outside)


class Listing(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.saved = (km._sessions, km._parse_cached, km.jd.parsed_session)
        self.path = str(self.w.cwd / "transcript.jsonl")
        km._sessions = lambda now, window=None, forks=True: [{"sid": SID, "name": "web", "path": self.path, "mtime": 1}]
        self.parsed = {"turns": [{"t": 100, "atoms": [_atom("assistant", 100, blocks=[_tool("Write", file_path=str(self.w.cwd / "report.md"), content="x")])]}]}
        self.cached = None
        km._parse_cached = lambda path: self.cached
        self.parses = []
        km.jd.parsed_session = lambda sid, files, now, **kw: (self.parses.append((sid, list(files))) or self.parsed)

    def tearDown(self):
        km._sessions, km._parse_cached, km.jd.parsed_session = self.saved
        self.w.close()

    def test_the_listing_reads_the_cached_parse_first_and_parses_once_when_it_misses(self):
        body, err = km._artifacts_list(SID, now=500)
        self.assertEqual(err, ""); self.assertEqual(self.parses, [(SID, [self.path])], "the cache missed: one parse into the shared store")
        self.assertEqual([it["name"] for it in body["items"]], ["report.md"]); self.assertEqual((body["capped"], body["max"]), (False, km.ARTIFACTS_MAX))
        self.cached = self.parsed
        body, err = km._artifacts_list(SID, now=500)
        self.assertEqual(self.parses, [(SID, [self.path])], "a warm cache: no parse")
        self.assertEqual(km._artifacts_list("11111111-2222-3333-4444-000000000932", now=500), (None, "no session with that id has a transcript here"))

    def test_the_op_answers_the_asking_socket_by_request_id_with_the_listing(self):
        sent = []
        client = {"app": "artifacts", "wid": "w1", "alive": True, "send": lambda raw: sent.append(json.loads(raw))}
        km.Handler._dispatch_ws(None, {"type": "listArtifacts", "sid": SID, "reqId": 7}, client)
        self.assertEqual(len(sent), 1); r = sent[0]
        self.assertEqual((r["type"], r["reqId"], r["sid"], r["error"], r["capped"], r["max"]), ("artifactsListing", 7, SID, "", False, km.ARTIFACTS_MAX))
        self.assertEqual([it["name"] for it in r["items"]], ["report.md"])
        km.Handler._dispatch_ws(None, {"type": "listArtifacts", "reqId": 8}, client)
        self.assertEqual((sent[1]["error"], sent[1]["items"]), ("no session named", []))


def _has(tc, needle, hay):
    tc.assertIn(needle, hay)


class Shell(unittest.TestCase):
    """The dashboard grows a sixth pane, rightmost after Files, OFF by default and hidden behind its own control (the Files
    control's shape, a fresh key): every hand-written pane list in the landing JS names it (the shipped naming pattern the
    timeline owner asked for, exactly: artifacts-pane, f-artifacts with data-src, po-artifacts, --g-artifacts, the
    _PANE_ORDER entry and its LBL word), so the registry folds it in by key and route."""

    def setUp(self):
        self.html = km._landing()

    def test_the_landing_names_the_pane_in_every_hand_list(self):
        h = self.html
        _has(self, "<div class=rail-btn data-pane=artifacts>Artifacts</div>", h); _has(self, "<button data-pane=artifacts>Artifacts</button>", h)
        flat = h.replace('"\n            "', "")
        _has(self, '<div class=gv id=gv-d></div><div class=pane id=artifacts-pane><iframe id=f-artifacts data-src=/artifacts></iframe></div>', flat)
        self.assertLess(h.index("id=files-pane"), h.index("id=gv-d")); self.assertLess(h.index("id=gv-d"), h.index("id=artifacts-pane")); self.assertLess(h.index("id=artifacts-pane"), h.index("id=gh"))
        _has(self, "#artifacts-pane{flex:var(--g-artifacts,40) 1 0}", h); _has(self, "body:not(.po-artifacts) #artifacts-pane{display:none}", h)
        _has(self, "body:not(.po-artifacts) #gv-d,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files) #gv-d{display:none}", h)
        _has(self, "<body class='po-chat po-feed po-timeline'>", h)   # not po-artifacts: off by default
        _has(self, "po={chat:true,fleet:false,feed:true,timeline:true,files:false,artifacts:false}", h)
        _has(self, "po={chat:false,fleet:false,feed:false,timeline:false,files:false,artifacts:false}", h)
        _has(self, "document.body.classList.toggle('po-artifacts',!!po.artifacts)", h); _has(self, "artifacts:'artifacts pane'", h)
        _has(self, "'f-artifacts':'artifacts-pane'", km._LANDING_FOCUS_JS); _has(self, "var COLS=['f-chat','f-fleet','f-feed','f-files','f-artifacts']", km._LANDING_FOCUS_JS)
        _has(self, "['f-chat','f-fleet','f-feed','f-files','f-artifacts','f-timeline','f-settings'].forEach", km._LANDING_ESC_JS)
        _has(self, "['f-chat','f-fleet','f-feed','f-files','f-artifacts','f-timeline','f-settings'].forEach", km._LANDING_MOBILE_JS)
        _has(self, "artifacts:document.getElementById('f-artifacts')", km._LANDING_MOBILE_JS)
        _has(self, "var PANES=['chat-pane','fleet-pane','feed-pane','files-pane','artifacts-pane'];", h); _has(self, "grow={chat:60,fleet:34,feed:40,files:40,artifacts:40}", h)
        _has(self, "id==='files-pane'?'files':'artifacts'", h)
        _has(self, "gutter('gv-d',function(){var c=document.body.classList;return c.contains('po-files')?'files-pane':c.contains('po-feed')?'feed-pane':c.contains('po-fleet')?'fleet-pane':lastChat();},'artifacts-pane');", h)
        self.assertEqual(dict(km._PANE_ORDER).get("artifacts"), "Artifacts"); _has(self, "var PN=" + json.dumps(dict(km._PANE_ORDER)) + ";", km._LANDING_ERRS_JS)

    def test_the_artifacts_controls_own_setting_hides_it_in_both_layouts_and_loads_the_page_once(self):
        js = km._LANDING_COLLAPSE_JS
        _has(self, "function artifactsCtl(){try{var st=JSON.parse(localStorage.getItem('romp:settings')||'null');return !!(st&&st.showArtifactsControl===true);}catch(e){return false;}}", js)
        _has(self, "document.body.classList.toggle('no-artifacts-control',!actl);", js)
        _has(self, "if(k==='artifacts'&&!artifactsCtl())return;", js)
        _has(self, "return {romp:'panes',on:on,avail:{files:filesCtl(),artifacts:artifactsCtl()}};", js)
        _has(self, "if(actl&&af&&!af.getAttribute('src')&&af.getAttribute('data-src'))af.setAttribute('src',af.getAttribute('data-src'));", js)   # loaded once, when the control is on
        _has(self, "if(!actl&&po.artifacts){po.artifacts=false;if(qp===null)saveP();}", js)
        _has(self, "body.no-artifacts-control .rail-btn[data-pane=artifacts],body.no-artifacts-control #mtabs button[data-pane=artifacts]{display:none}", self.html)
        mob = km._LANDING_MOBILE_JS
        _has(self, "function artifactsCtlM(){try{var st=JSON.parse(localStorage.getItem('romp:settings')||'null');return !!(st&&st.showArtifactsControl===true);}catch(e){return false;}}", mob)
        _has(self, "if(p==='artifacts'&&!artifactsCtlM())p='chat';", mob)

    def test_the_pane_is_in_the_one_ordering_after_files_and_the_viewer_set(self):
        self.assertEqual(km._PANE_ORDER[-1], ("artifacts", "Artifacts")); self.assertEqual(km._PANE_ORDER[-2], ("files", "Files"))
        self.assertIn('c.get("app") in ("chat", "fleet", "timeline", "feed", "files", "artifacts")', KSRC, "a dashboard with only this pane open counts as a viewer")

    def test_the_page_is_served_at_its_route_with_the_no_stale_shim_and_its_bundle(self):
        html = km._artifacts_page()
        self.assertIn("<title>Romp · artifacts</title>", html); self.assertIn("<body class=artifacts-pane>", html); self.assertIn("<div id=artifacts-root></div>", html)
        self.assertIn("/dist/artifacts.js?v=", html); self.assertIn("/dist/federation.js?v=", html); self.assertIn("/dist/styles.css?v=", html)
        self.assertIn('if p == "/artifacts":', KSRC); self.assertIn("return self._send(200, _artifacts_page(), \"text/html; charset=utf-8\", cache=\"no-cache\")", KSRC)
        self.assertIn('_shim("artifacts", v, no_stale=True)', inspect.getsource(km._artifacts_page), "no pushed view: the stale prompt is never armed for this page")
        self.assertIn(".art-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))", html, "the pane's own stylesheet rides the page")


if __name__ == "__main__":
    unittest.main()
