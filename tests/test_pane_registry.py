#!/usr/bin/env python3
"""The pane registry (plans/panes-as-data.md, phase one). A pane is a record in ONE schema: the shipped panes are the
kernel's code constants (_CODE_PANES, checked at import by _pane_check like the code boards), every other pane a JSON document
under STATE/panes/<id>.json behind define_pane (the board door's twin: POST /pane, GET /panes, `romp pane`). The shell renders
from _pane_order() per request, and the FIRST pin is that with an empty registry the code panes' RENDERING is unchanged: the
body tag, the rail, the phone tabs, the pane row, the column and gutter rules and the gutter calls, slice for slice against
the base kernel's rendering (tests/fixtures/landing-code-panes.json, tests/landing_slices.py). A data pane gets a rail
button, a phone tab (none when experimental), a lazy iframe (data-src), its column and gutter rules and a row in
body[data-panes] that the baked inline scripts read; a URL source is a plain sandboxed iframe with no token, no ?v= and no
protocol, and every shell listener, inline and bundled, drops a message that is not a protocol pane's own (the source
check, fail-closed). The pane set's revision rides every keepalive beside the build token and a page baked with another is
offered a reload.

Every test here reds at the base on BEHAVIOUR (the 1919 read): a pane's file is written by hand the way the door writes it,
and what is asserted is the landing, the routes, the keepalive frame and the executed scripts, never a name.
Synthetic fixtures only (the notes-api demo world; TESTHOST)."""
import contextlib
import html as html_mod
import inspect
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
from landing_slices import slices   # noqa: E402  the code panes' rendering, sliced (the fixture was made with the same function)

os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
_XDG = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _XDG
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(_XDG, "romp"), exist_ok=True)
open(os.path.join(_XDG, "romp", "session-hosts"), "w").write("off\n")
km = load_source("romp_kernel_pane_registry", os.path.join(BIN, "romp-kernel"))
KSRC = open(os.path.join(BIN, "romp-kernel")).read()
FIXTURE = json.load(open(os.path.join(HERE, "fixtures", "landing-code-panes.json")))

SHIPPED = [("chat", "Chat", True), ("timeline", "Sessions", True), ("fleet", "Outline", False), ("feed", "Feed", True),
           ("files", "Files", False), ("artifacts", "Artifacts", False)]   # id, title, today's rail default (the Artifacts pane since 2026-09-19)
EXPERIMENTAL = {"artifacts"}   # the shipped records the gear asks for before showing (plans/panes-as-data.md phase three: the Artifacts pane)
ARTIFACTS_ROW = {"id": "artifacts", "title": "Artifacts", "protocol": "romp", "experimental": True, "on": False, "builtin": True}   # the generic build's row for the shipped record
SHIPPED_IDS = [s[0] for s in SHIPPED]
NOTES = {"id": "notes", "title": "Notes", "source": "pane:notes", "on": True}
DOCS = {"id": "docs", "title": "Docs", "source": "http://TESTHOST:9/docs/", "on": True}          # a URL: protocol none
LAB = {"id": "lab", "title": "Lab", "source": "/feed", "experimental": True}                       # a kernel route, experimental
OFFPANE = {"id": "offpane", "title": "Off", "source": "/feed", "on": False}                        # a kernel route, off by rail default, not experimental
GUARD = "if(!window.__rompPaneSourceOk||!window.__rompPaneSourceOk(e))return;"                    # the inline listeners' read, fail-closed


def _full(d):
    """The record as the door fills it."""
    out = {"title": d["id"].capitalize(), "on": False, "experimental": False,
           "protocol": "none" if d["source"].startswith("http") else "romp"}
    out.update(d)
    return out


def _rows(*defs):
    """The body attribute's rows for these data records (what the inline scripts read): the shipped Artifacts record first (the
    generic build renders every pane after the hand-written five), then the data panes by id."""
    return [ARTIFACTS_ROW] + [{"id": d["id"], "title": d["title"], "protocol": d["protocol"], "experimental": d["experimental"], "on": d["on"], "builtin": False}
                              for d in sorted((_full(x) for x in defs), key=lambda r: r["id"])]


class World:
    """A hermetic state root, the kernel rebound to it, the pane memo cleared; pane files written by hand, as the door writes
    them, so every assertion is on what the kernel RENDERS from the directory."""
    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.orig_state = km.jd.STATE
        km.jd._rebind_state(root / "state")
        (km.jd.STATE / "session-hosts").parent.mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "session-hosts").write_text("off\n")
        self.reset_memos()

    @property
    def pdir(self):
        return km.jd.STATE / "panes"

    def seed(self, *defs):
        self.pdir.mkdir(parents=True, exist_ok=True)
        for d in defs:
            (self.pdir / (d["id"] + ".json")).write_text(json.dumps(_full(d), indent=1, sort_keys=True) + "\n")

    def unseed(self, *ids):
        for i in ids:
            (self.pdir / (i + ".json")).unlink()

    @staticmethod
    def reset_memos():
        # guarded: at a base without the registry these names are absent, and each test reds on its own behaviour
        memo = getattr(km, "_PANES_MEMO", None)
        if isinstance(memo, dict):
            memo["slot"] = None
        getattr(km, "_PANES_BAD", set()).clear()

    def close(self):
        km.jd._rebind_state(self.orig_state)
        self.reset_memos()
        self.td.cleanup()


def _run(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, "the shell script threw: " + r.stderr[:1500]
    return json.loads(r.stdout.strip().splitlines()[-1])


def _has(tc, needle, page, msg=""):
    # assertTrue, not assertIn: a failure must never print the landing
    tc.assertTrue(needle in page, "missing from the page: %r %s" % (needle, msg))


def _lacks(tc, needle, page, msg=""):
    tc.assertTrue(needle not in page, "present in the page: %r %s" % (needle, msg))


def _attr_rows(page):
    m = re.search(r"<body class='po-chat po-feed po-timeline' data-panes=\"([^\"]*)\">", page)
    return json.loads(html_mod.unescape(m.group(1))) if m else None


def _rail(page):
    return re.findall(r"<div class=rail-btn data-pane=([a-z0-9_-]+)>([^<]*)</div>", page)


# ── the first pin: the code panes render as before ───────────────────────────────────────────────────────────────
class TheCodePanesRender(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_00_the_code_panes_rendering_is_unchanged_with_an_empty_registry_and_after_a_define_and_remove(self):
        # THE FIRST PIN (plans/panes-as-data.md, section 7): with no data pane the kernel renders the code panes as the base
        # kernel did, slice for slice (the fixture names the base); the page as a whole gains the guards and the attribute
        # reads, deliberately. A pane file written by hand changes the page; removing it brings the bytes back exactly.
        h0 = km._landing()
        self.assertTrue(h0 == km._landing(), "the landing is a pure function of the registry and the build")
        got = slices(h0)
        for name, text in FIXTURE["slices"].items():
            self.assertTrue(got.get(name) == text, "the %s slice differs from the base rendering (fixture from %s): %d vs %d chars"
                            % (name, FIXTURE["made_from"], len(got.get(name, "")), len(text)))
        # with no data pane the attribute carries exactly the shipped record the generic build renders (the Artifacts pane), and
        # none of a data pane's markers
        self.assertEqual(_attr_rows(h0), [ARTIFACTS_ROW], "the attribute: the Artifacts record alone")
        _lacks(self, " data-protocol=none sandbox=", h0); _lacks(self, "id=gv-notes", h0); _lacks(self, "/pane/", h0)
        self.w.seed(NOTES)
        h1 = km._landing()
        self.assertTrue(h1 != h0, "a pane file changes the page"); self.assertEqual([r["id"] for r in _attr_rows(h1)], ["artifacts", "notes"])
        s1 = slices(h1)
        self.assertTrue(s1["body_tag"] != got["body_tag"] and s1["rail_buttons"] != got["rail_buttons"], "the body tag and the rail carry the pane")
        self.w.unseed("notes")
        self.assertTrue(km._landing() == h0, "define then remove: the bytes are back")


# ── the doors ─────────────────────────────────────────────────────────────────────────────────────────────────────
class TheDoors(unittest.TestCase):
    """POST /pane, GET /panes and GET /pane/<id>/... in /board's shape; the schema is the door's, so it is pinned through it."""
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def _req(self, path, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Romp-Token"] = os.environ["ROMP_SERVE_TOKEN"]
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    def _call(self, path, body=None, token=True):
        st, _, raw = self._req(path, body, token)
        try:
            return st, json.loads(raw.decode() or "{}")
        except ValueError:
            return st, {"raw": raw.decode(errors="replace")}

    def test_the_shipped_panes_are_records_the_door_lists_and_the_rail_renders_from(self):
        st, r = self._call("/panes")
        self.assertEqual(st, 200, "GET /panes answers")
        rows = r["panes"]
        self.assertEqual([(p["id"], p["title"], p["on"]) for p in rows], SHIPPED, "the shipped panes, in the rail's order, with today's rail defaults as `on`")
        self.assertTrue(all(p["builtin"] and p["protocol"] == "romp" and p["experimental"] == (p["id"] in EXPERIMENTAL) and p["source"] == "/" + p["id"] for p in rows), rows)
        self.assertEqual(r["rev"], "0", "no data pane: the set's revision is zero")
        self.assertEqual(_rail(km._landing()), [(p["id"], p["title"]) for p in rows], "the rail renders the same records")

    def test_the_door_fills_the_defaults_and_refuses_by_member(self):
        st, r = self._call("/pane", {"id": "notes", "source": "/feed"})
        self.assertEqual(st, 200, "POST /pane answers")
        self.assertEqual(r, {"ok": True, "pane": {"id": "notes", "title": "Notes", "source": "/feed", "on": False, "experimental": False, "protocol": "romp"}, "rev": r.get("rev")})
        self.assertNotEqual(r["rev"], "0")
        st, r = self._call("/pane", dict(DOCS)); self.assertEqual(r["pane"]["protocol"], "none", "a URL source is a plain iframe: protocol none by default")
        st, r = self._call("/pane", {"id": "notes", "title": "  Notes  ", "source": "pane:notes", "on": True, "experimental": True, "protocol": "romp"})
        self.assertEqual((r["pane"]["title"], r["pane"]["on"], r["pane"]["experimental"]), ("Notes", True, True))
        for bad, word in (
                ({"id": "notes", "source": "/feed", "colour": "red"}, "unknown member colour"),
                ({"id": "Notes", "source": "/feed"}, "id must"),
                ({"id": "n" * 33, "source": "/feed"}, "id must"),
                ({"id": "feed", "source": "/feed"}, "reserved"),
                ({"id": "tl", "source": "/feed"}, "derives"),            # the band renders id=tl-pane: a data pane tl would render it twice (the 1920 read)
                ({"id": "ghost", "source": "/feed"}, "derives"),
                ({"id": "col", "source": "/feed"}, "derives"),           # the tab drag's rectangle is #col-ghost
                ({"id": "a", "source": "/feed"}, "derives"),             # the hand-written gutters are gv-a to gv-d
                ({"id": "chat-notes", "source": "/feed"}, "chat column"),   # f-chat-<n> is a chat column's frame shape
                ({"id": "settings", "source": "/feed"}, "reserved"),
                ({"id": "artifacts", "source": "/feed"}, "reserved"),
                ({"id": "notes", "title": "x" * 25, "source": "/feed"}, "title must"),
                ({"id": "notes", "title": "   ", "source": "/feed"}, "title must"),
                ({"id": "notes"}, "source must"),
                ({"id": "notes", "source": "feed"}, "source must"),
                ({"id": "notes", "source": "//TESTHOST/x"}, "source must"),
                ({"id": "notes", "source": "ftp://TESTHOST/x"}, "source must"),
                ({"id": "notes", "source": "pane:other"}, "pane:notes"),
                ({"id": "notes", "source": "/feed", "on": "yes"}, "on must"),
                ({"id": "notes", "source": "/feed", "experimental": 1}, "experimental must"),
                ({"id": "notes", "source": "/feed", "protocol": "http"}, "protocol must"),
                (dict(DOCS, protocol="romp"), "protocol none")):
            st, r = self._call("/pane", bad)
            self.assertEqual((st, r.get("ok")), (200, False), (bad, r)); self.assertIn(word, r.get("error", ""), (bad, r))
        self.assertFalse((self.w.pdir / "feed.json").exists(), "a refusal writes nothing")
        st, r = self._call("/pane", b"[]"); self.assertEqual(st, 400, "a malformed body")
        st, r = self._call("/pane", {}); self.assertEqual(st, 400); self.assertIn("pane definition", r["error"])
        self.assertNotEqual(self._call("/pane", NOTES, token=False)[0], 200, "no token: refused")
        self.assertNotEqual(self._call("/panes", token=False)[0], 200)

    def test_define_replaces_a_pane_whole_remove_deletes_it_and_a_shipped_or_unknown_id_is_refused(self):
        st, r = self._call("/pane", NOTES); self.assertEqual((st, r.get("ok")), (200, True), r); self.assertEqual(r["pane"], _full(NOTES))
        rev = r["rev"]
        self.assertEqual(json.loads((self.w.pdir / "notes.json").read_text()), _full(NOTES), "the file holds the filled record, not the request")
        st, r = self._call("/panes"); self.assertEqual([p["id"] for p in r["panes"]], SHIPPED_IDS + ["notes"]); self.assertEqual(r["rev"], rev)
        self.assertEqual([p["builtin"] for p in r["panes"]], [True] * len(SHIPPED) + [False])
        self.assertEqual({k: v for k, v in r["panes"][len(SHIPPED)].items() if k != "builtin"}, _full(NOTES))
        st, r = self._call("/pane", dict(NOTES, title="Notebook")); self.assertEqual((st, r["ok"]), (200, True))
        self.assertEqual(_rail(km._landing())[-1], ("notes", "Notebook"), "a define replaces the pane whole and the rail says so")
        self._call("/pane", DOCS); self._call("/pane", LAB)
        st, r = self._call("/panes"); self.assertEqual([p["id"] for p in r["panes"]], SHIPPED_IDS + ["docs", "lab", "notes"], "data panes by id after the shipped panes")
        st, r = self._call("/pane", {"remove": "chat"}); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("shipped", r["error"])
        st, r = self._call("/pane", {"remove": "scratch"}); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("no pane", r["error"])
        for i in ("notes", "docs"):
            st, r = self._call("/pane", {"remove": i}); self.assertEqual((st, r["ok"]), (200, True))
        st, r = self._call("/pane", {"remove": "lab"}); self.assertEqual((st, r), (200, {"ok": True, "rev": "0"}))
        self.assertFalse((self.w.pdir / "notes.json").exists())
        st, r = self._call("/panes"); self.assertEqual([p["id"] for p in r["panes"]], SHIPPED_IDS)

    def test_the_state_root_serves_a_panes_page_its_shim_and_the_theme_and_nothing_outside_it(self):
        self.assertEqual(self._req("/pane/notes/")[0], 404, "an undefined pane has no page")
        self.w.seed(NOTES, LAB)
        pdir = self.w.pdir / "notes"; pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "index.html").write_text("<!doctype html><script src=shim.js></script><link rel=stylesheet href=theme.css><h1>Notes</h1>")
        (pdir / "app.js").write_text("window.notesApp=1;")
        (km.jd.STATE / "secret.txt").write_text("not served")
        st, ct, body = self._req("/pane/notes/")
        self.assertEqual((st, ct), (200, "text/html; charset=utf-8")); self.assertIn(b"<h1>Notes</h1>", body)
        self.assertEqual(self._req("/pane/notes/index.html")[2], body)
        st, ct, body = self._req("/pane/notes/app.js"); self.assertEqual((st, ct, body), (200, "text/javascript", b"window.notesApp=1;"))
        st, ct, body = self._req("/pane/notes/shim.js"); self.assertEqual((st, ct), (200, "text/javascript"))
        shim = body.decode()
        self.assertIn('var APP="notes";var LABEL="Notes";', shim, "the pane shim for this id: the page speaks the protocol by one script tag")
        st, r = self._call("/panes")
        self.assertIn('var LOADEDPV="%s";' % r["rev"], shim, "baked with the pane set's revision the door reports")
        self.assertIn("notePanes", shim, "and it hands a moved revision to the reload core")
        self.assertIn("var NOSTALE=true;", shim, "no pushed view reaches a state-root page, so the stale prompt is never armed for it (the 1919 read: the banner after every reconnect, never retired); the Files pane's rule, tests/test_files_pane.py")
        self.assertIn('_shim(pid, _dist_ver(), no_stale=True, pv=snap["rev"], data=snap["data"])', KSRC, "served with the stale prompt off and the same listing's revision")
        st, ct, body = self._req("/pane/notes/theme.css"); self.assertEqual((st, ct), (200, "text/css")); self.assertTrue(body.startswith(b"@font-face"), body[:40])
        self.assertEqual(self._req("/pane/notes/missing.js")[0], 404)
        self.assertEqual(self._req("/pane/notes/..%2F..%2Fsecret.txt")[0], 404, "no path leaves the pane's directory")
        self.assertEqual(self._req("/pane/notes/%2E%2E/%2E%2E/secret.txt")[0], 404)
        self.assertEqual(self._req("/pane/lab/")[0], 404, "a route-source pane has no state-root page")
        self.assertEqual(self._req("/pane/feed/")[0], 404, "nor a shipped one")
        self.assertNotEqual(self._req("/pane/notes/", token=False)[0], 200, "behind the token like every route")

    def test_the_state_root_shim_bakes_the_routes_one_snapshot_into_both_its_revision_slots(self):
        # the 1952 read (round two): the shim's keepalive gate LOADEDPV was baked from a second read while the reload core's PANES0
        # took the route's snapshot, so across a define the two disagreed and the gate never called notePanes for the very revision
        # that changed. Executed: the listing is hooked to define a second record after its first call; the route lists once, and the
        # shim's two slots carry that one revision
        self.w.seed(NOTES)
        pdir = self.w.pdir / "notes"; pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "index.html").write_text("<!doctype html><script src=shim.js></script>")
        real = km._panes_snapshot
        calls, who = [], []

        def hooked():
            snap = real()
            if not who:
                who.append(threading.get_ident())
            if threading.get_ident() != who[0]:   # the keepalive thread's own listing is not the route's
                return snap
            calls.append(snap["rev"])
            if len(calls) == 1:
                self.w.seed(DOCS)
            return snap
        km._panes_snapshot = hooked
        try:
            st, ct, body = self._req("/pane/notes/shim.js")
        finally:
            km._panes_snapshot = real
        shim = body.decode()
        self.assertEqual(st, 200); self.assertEqual(len(calls), 1, "the route lists once and hands the revision down: %r" % calls)
        self.assertIn('PANES0="%s"' % calls[0], shim, "the reload core's revision is the route's snapshot's")
        self.assertIn('var LOADEDPV="%s";' % calls[0], shim, "and so is the keepalive gate's (a second read would have baked the define's revision here)")
        self.w.unseed("docs")

    def test_a_page_baked_with_one_revision_is_offered_a_reload_when_the_keepalive_carries_another(self):
        # the reload core the shim embeds, executed: notePanes with the baked revision says nothing, another revision stands
        # the OFFER worded for the panes (never a self-reload); the shell's own socket and the shim hand the keepalive's pv to it
        st, r = self._call("/panes"); pv0 = r.get("rev", "0")
        core = km._reload_core(3)
        out = _run(_RELOAD_STUB + core + _RELOAD_DRIVER.replace("__PV0__", json.dumps(pv0)))
        self.assertIsNone(out["before"], "nothing offered on a current page")
        self.assertIsNone(out["same"], "the baked revision on the keepalive: nothing to say")
        self.assertEqual((out["moved"] or {}).get("text"), "The set of panes changed. Reload to see it.", "a moved revision: the offer, worded for the panes: %r" % out)
        self.assertEqual(((out["moved"] or {}).get("pv"), (out["moved"] or {}).get("code")), ("abc123", ""), "the revision rides its own slot, the build's code untouched (the 1919 read)")
        self.assertFalse(out["reloaded"], "an OFFER, never a self-reload")
        self.assertIn("if(m&&m.type==='ka'&&m.pv&&window.__rompReload&&window.__rompReload.notePanes)window.__rompReload.notePanes(m.pv);", km._LANDING_MOBILE_JS, "the shell's own socket hands pv to the core")
        self.assertIn('if(msg&&msg.type==="ka"&&LOADEDPV&&msg.pv&&msg.pv!==LOADEDPV){var RP=window.__rompReload;if(RP&&RP.notePanes)RP.notePanes(msg.pv);}', KSRC,
                      "the pane shim hands a moved revision to the reload core, before the pinned ka branch")


# ── the store, read through the landing and the keepalive ─────────────────────────────────────────────────────────
class TheStore(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_a_pane_file_written_by_hand_renders_a_bad_one_is_skipped_and_named_once_and_a_rewrite_in_place_is_read(self):
        self.w.seed(NOTES)
        self.assertEqual(_rail(km._landing())[-1], ("notes", "Notes"), "the directory is the registry: a file the door would write renders")
        (self.w.pdir / "bad.json").write_text("{")
        (self.w.pdir / "other.json").write_text(json.dumps(_full(dict(NOTES, id="notes2"))))   # names another pane than its file
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rail = _rail(km._landing()); km._landing()
        self.assertEqual([k for k, _ in rail], SHIPPED_IDS + ["notes"], "a bad file is skipped, never rendered")
        lines = [ln for ln in err.getvalue().splitlines() if "[panes]" in ln]
        self.assertEqual(len(lines), 2, "each bad file is named once, on stderr, however many builds: %r" % lines)
        self.assertTrue(any("bad.json" in ln for ln in lines) and any("other.json" in ln and "notes2" in ln for ln in lines), lines)
        # an in-place rewrite (an editor, a shell redirection) moves the file's stat: the next build reads it
        fp = self.w.pdir / "notes.json"
        fp.write_text(json.dumps(_full(dict(NOTES, title="Notebook"))))
        st = os.stat(fp); os.utime(fp, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
        self.assertEqual(_rail(km._landing())[-1], ("notes", "Notebook"))

    def test_the_landing_and_the_shim_bake_the_revision_of_the_one_listing_their_build_read(self):
        # the 1919 read: _landing listed the registry once for its builders and _stale_block listed it again through _reload_core,
        # so a define landing between the two baked the new revision into a page showing the old set, which was never offered a reload
        self.assertIn('PANES0="abc"', km._reload_core(3, pv="abc"), "the reload core bakes the revision it is handed")
        self.assertIn('PANES0="%s"' % km._panes_rev(), km._reload_core(3), "and this kernel's when handed none")
        src = inspect.getsource(km._landing)
        self.assertIn("snap = _panes_snapshot()", src); self.assertIn('panes = _pane_order(snap["data"]); pv = snap["rev"]', src, "one listing: the list and the revision from it")
        self.assertIn("_stale_block(v, pv)", src, "the reload core takes that revision")
        self.assertIn("def _stale_block(v, pv=None):", KSRC); self.assertIn("def _shim(app, v=0, no_stale=False, pv=None, data=None):", KSRC)

    def test_a_build_offer_and_a_pane_set_offer_stand_together_and_a_decline_covers_both(self):
        core = km._reload_core_js(3, boot="b1", code="C0")
        r = _run(_RELOAD_STUB + core.replace('PANES0="%s"' % km._panes_rev(), 'PANES0="P0"') + _RELOAD_TWO_DRIVER)
        self.assertEqual((r["build"]["code"], r["build"]["text"]), ("C1", km.RELOAD_OFFER_MSG), "a build offer: %r" % r["build"])
        self.assertEqual(r["behind"]["text"], km.RELOAD_OFFER_BEHIND_MSG)
        self.assertEqual((r["panesBeside"]["code"], r["panesBeside"]["pv"], r["panesBeside"]["text"]), ("C1", "B", km.RELOAD_OFFER_BEHIND_MSG),
                         "the pane set moving beside a standing build offer keeps the build's words and rides the revision: %r" % r["panesBeside"])
        self.assertEqual(r["buildAgain"], r["panesBeside"]); self.assertEqual(r["panesAgain"], r["panesBeside"], "nothing new: the one offer stands")
        self.assertIsNone(r["declined"], "Not now clears the offer")
        self.assertIsNone(r["buildAfterDecline"], "the declined build is not re-offered")
        self.assertIsNone(r["panesAfterDecline"], "nor the declined revision")
        self.assertEqual((r["newRevision"]["pv"], r["newRevision"]["code"]), ("C", "C1"), "a NEW revision is new information: offered again, the build beside it: %r" % r["newRevision"])
        r2 = _run(_RELOAD_STUB + core.replace('PANES0="%s"' % km._panes_rev(), 'PANES0="P0"') + _RELOAD_PANES_ONLY_DRIVER)
        self.assertEqual((r2["panes"]["pv"], r2["panes"]["code"], r2["panes"]["text"]), ("B", "", km.RELOAD_OFFER_PANES_MSG), "the revision alone: the panes words: %r" % r2["panes"])
        self.assertIsNone(r2["declined"], "declined, the same revision offers nothing")
        self.assertEqual((r2["moved"]["pv"], r2["moved"]["text"]), ("C", km.RELOAD_OFFER_PANES_MSG), "another revision offers again")

    def test_one_listing_per_build_executed_a_define_forced_between_the_former_reads_changes_neither_the_set_nor_the_baked_revision(self):
        # the 1952 read (round two): the one-listing item was pinned by source strings alone; here the listing is HOOKED: the first
        # snapshot call defines a second record after it returns, so a build that listed again would render or bake the new set.
        # The landing: one call, the rows the first snapshot's, PANES0 its revision, one PANES0 occurrence. The shim: the route's
        # snapshot handed through, no further call, PANES0 and LOADEDPV equal; _shim handed nothing reads once and bakes both from it.
        self.w.seed(NOTES)
        real = km._panes_snapshot
        calls, who = [], []

        def hooked():
            snap = real()
            if not who:
                who.append(threading.get_ident())
            if threading.get_ident() != who[0]:   # the keepalive thread's own listing is not this build's
                return snap
            calls.append(snap["rev"])
            if len(calls) == 1:
                self.w.seed(DOCS)   # a define landing between two listings, if a build made two
            return snap
        km._panes_snapshot = hooked
        try:
            html = km._landing()
        finally:
            km._panes_snapshot = real
        self.assertEqual(len(calls), 1, "one listing per landing build: %r" % calls)
        rows = json.loads(html_mod.unescape(re.search(r' data-panes="([^"]*)"', html).group(1)))
        self.assertEqual([r["id"] for r in rows if not r.get("builtin")], ["notes"], "the rendered set is the first snapshot's (the define landed after it): %r" % rows)
        self.assertEqual(html.count('PANES0="'), 1, "one baked revision on the page")
        self.assertIn('PANES0="%s"' % calls[0], html, "the reload core's revision is the same snapshot's")
        self.w.unseed("docs")
        # _shim handed no revision: ONE read, both slots from it
        calls.clear()
        km._panes_snapshot = hooked
        try:
            direct = km._shim("notes", 3)
        finally:
            km._panes_snapshot = real
        self.assertEqual(len(calls), 1, "one read when handed none: %r" % calls)
        self.assertIn('PANES0="%s"' % calls[0], direct); self.assertIn('var LOADEDPV="%s";' % calls[0], direct)
        self.w.unseed("docs")
        self.assertIn('var LOADEDPV="abc";', km._shim("notes", 3, pv="abc"), "handed a revision, the shim's gate bakes it too")

    def test_the_revision_rides_the_keepalive_beside_the_build_token_and_moves_on_a_change(self):
        def frame():
            got = []
            saved = list(km._clients)
            km._clients[:] = [{"app": "feed", "wid": "", "send": got.append, "alive": True}]
            try:
                km._keepalive_all()
            finally:
                km._clients[:] = saved
            return json.loads(got[0])
        f0 = frame()
        self.assertEqual((f0["type"], f0["dv"], f0.get("pv")), ("ka", km._dist_ver(), "0"), "pv rides beside dv; zero with no data pane: %r" % f0)
        self.w.seed(NOTES); r1 = frame().get("pv")
        self.assertNotEqual(r1, "0"); self.assertEqual(r1, frame().get("pv"), "stable while nothing changes")
        # the revision is a digest of the CHECKED records (the 1919 read): an identical re-define, a bare touch and a malformed file
        # the listing skips move the files' stats and nothing a page can be stale against, so none of them offers a reload
        self.w.seed(NOTES); self.assertEqual(frame().get("pv"), r1, "an identical re-define leaves the revision")
        os.utime(self.w.pdir / "notes.json", None); self.assertEqual(frame().get("pv"), r1, "a touch leaves it")
        (self.w.pdir / "bad.json").write_text("{not json"); self.assertEqual(frame().get("pv"), r1, "a malformed file the listing skips leaves it")
        (self.w.pdir / "bad.json").unlink()
        self.w.seed(dict(NOTES, title="Notebook")); r1b = frame().get("pv"); self.assertNotEqual(r1b, r1, "a changed record moves it"); self.w.seed(NOTES); self.assertEqual(frame().get("pv"), r1)
        self.w.seed(DOCS); r2 = frame().get("pv"); self.assertNotEqual(r2, r1)
        self.w.unseed("docs", "notes")
        self.assertEqual(frame().get("pv"), "0")


# ── the landing with data panes ───────────────────────────────────────────────────────────────────────────────────
class TheLanding(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_a_data_pane_renders_a_rail_button_a_tab_a_lazy_iframe_its_rules_and_the_attribute(self):
        self.w.seed(NOTES, DOCS, LAB)
        page = km._landing()
        self.assertEqual(_rail(page), [(i, t) for i, t, _ in SHIPPED] + [("docs", "Docs"), ("lab", "Lab"), ("notes", "Notes")], "the shipped panes, then the data panes by id")
        _has(self, "<button data-pane=notes>Notes</button>", page, "a phone tab")
        _has(self, "<button data-pane=docs>Docs</button>", page)
        _lacks(self, "data-pane=lab>Lab</button>", page, "an experimental pane has no phone tab")
        _has(self, '<div class=gv id=gv-notes></div><div class=pane id=notes-pane><iframe id=f-notes data-src="/pane/notes/" data-protocol=romp></iframe></div>', page,
             "a state-root pane loads /pane/<id>/ when shown (data-src, the optional panes' rule)")
        _has(self, '<div class=gv id=gv-docs></div><div class=pane id=docs-pane><iframe id=f-docs data-src="http://TESTHOST:9/docs/" data-protocol=none sandbox="allow-scripts allow-forms allow-popups"></iframe></div>', page,
             "a URL pane: the URL as given (no ?v=, no token), sandboxed, marked protocol none")
        _has(self, '<iframe id=f-lab data-src="/feed" data-protocol=romp></iframe>', page, "a kernel route as given")
        self.assertLess(page.index("id=artifacts-pane"), page.index("id=gv-docs")); self.assertLess(page.index("id=gv-docs"), page.index("id=gv-notes"))
        self.assertLess(page.index("id=gv-notes"), page.index("<div id=col-ghost>"), "the data panes sit in the pane row, after the shipped columns")
        _has(self, "#notes-pane{flex:var(--g-notes,40) 1 0}body:not(.po-notes) #notes-pane{display:none}", page)
        _has(self, "body:not(.po-docs) #gv-docs,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files):not(.po-artifacts) #gv-docs{display:none}", page,
             "the first data gutter hides with its pane off or with no shown column before it (the shipped columns from the records)")
        _has(self, "body:not(.po-notes) #gv-notes,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files):not(.po-artifacts):not(.po-docs):not(.po-lab) #gv-notes{display:none}", page)
        mob = page[page.index("#chat-pane,#fleet-pane,#feed-pane,#files-pane,#tl-pane{display:contents!important}"):]
        _has(self, "#artifacts-pane,#docs-pane,#lab-pane,#notes-pane{display:contents!important}#f-artifacts.m-on,#f-docs.m-on,#f-lab.m-on,#f-notes.m-on{display:block}", mob[:600],
             "the phone's rules for the generic panes ride the media block beside the hand five's: the tab, not the po flag, says which pane shows, and the shown tab's iframe displays")
        self.assertEqual(_attr_rows(page), _rows(NOTES, DOCS, LAB), "the attribute carries what the inline scripts and the pane bundles read, never the source")
        n_scripts = page.count("<script>")
        self.w.unseed("notes", "docs", "lab")
        self.assertEqual(n_scripts, km._landing().count("<script>"), "no inline script is added for a data pane: the baked ones read the attribute")

    def test_a_title_is_escaped_in_the_rail_the_tab_and_the_attribute(self):
        self.w.seed({"id": "x", "title": "A <b>&", "source": "/feed", "on": True})
        page = km._landing()
        _has(self, "<div class=rail-btn data-pane=x>A &lt;b&gt;&amp;</div>", page)
        _has(self, "<button data-pane=x>A &lt;b&gt;&amp;</button>", page)
        attr = re.search(r"data-panes=\"([^\"]*)\"", page).group(1)
        self.assertNotIn("<", attr); self.assertNotIn('"', attr)
        self.assertEqual(next(r["title"] for r in _attr_rows(page) if r["id"] == "x"), "A <b>&")


# ── the inline scripts read the attribute; the source check ─────────────────────────────────────────────────────────
_PANES_STUB = r"""
'use strict';
const ATTR = __ATTR__;
const KEYS = ['chat','timeline','fleet','feed','files'].concat(__DATA_IDS__);   // the hand five; the Artifacts record rides the rows like a data pane (the 1922 read: hand-listed too, it was built twice)
const PROTO = __PROTO__;
const POSTED = {}, CLS = new Set(['po-chat', 'po-feed', 'po-timeline']), STORE = {}, STORAGE = [], TABS = [], SETS = {};
const frames = {};
KEYS.forEach((k) => { const attrs = (k === 'chat' || k === 'files') ? { src: '/' + k } : { 'data-src': '/' + k }; if (PROTO[k]) attrs['data-protocol'] = PROTO[k]; frames['f-' + k] = {
  attrs, getAttribute: (a) => (a in attrs ? attrs[a] : null), setAttribute: (a, v) => { attrs[a] = v; if (a === 'src') SETS[k] = (SETS[k] || 0) + 1; },
  contentWindow: { postMessage: (m) => { (POSTED[k] = POSTED[k] || []).push(JSON.parse(JSON.stringify(m))); } },
  addEventListener() {} }; });
const BTNS = {};
KEYS.forEach((k) => { BTNS[k] = { hidden: false, title: '', getAttribute: (a) => (a === 'data-pane' ? k : null), classList: { toggle() {} }, addEventListener() {} }; });
let TAB = 'chat', MOBILE = false;
global.window = global;
global.localStorage = { getItem: (k) => (k in STORE ? STORE[k] : null), setItem: (k, v) => { STORE[k] = v; } };
global.location = { search: '' };
global.URLSearchParams = class { get() { return null; } };
global.Event = class { constructor(t) { this.type = t; } };
global.addEventListener = (ev, f) => { if (ev === 'storage') STORAGE.push(f); };
global.dispatchEvent = () => true;
global.document = {
  body: { classList: { toggle: (c, on) => { if (on) CLS.add(c); else CLS.delete(c); }, contains: (c) => CLS.has(c) },
          getAttribute: (a) => (a === 'data-tab' ? TAB : a === 'data-panes' ? ATTR : null) },
  querySelectorAll: (sel) => { if (sel === '.rail-btn[data-pane]') return KEYS.map((k) => BTNS[k]); const m = /data-pane=([\w-]+)/.exec(sel); return m && BTNS[m[1]] ? [BTNS[m[1]]] : []; },
  getElementById: (id) => frames[id] || null,
};
window.__rompMobileOn = () => MOBILE;
window.__rompMobileTab = (t) => { TABS.push(t); TAB = t; };
__SEED__
"""

# the ON-SCREEN gate, executed (the 1922 read: no row was enabled in the gear while off screen, the one state in which the gate acts,
# so a mutant copying src for every enabled generic pane passed the harness): the gear has the Artifacts pane enabled and a
# non-experimental data pane is on:false; at boot neither loads; the rail toggle loads each
_GATE_DRIVER = r"""
const out = {};
const st = () => ({ artSrc: frames['f-artifacts'].attrs.src || null, artHidden: BTNS.artifacts.hidden, artOn: CLS.has('po-artifacts'), offSrc: frames['f-offpane'].attrs.src || null, offHidden: BTNS.offpane.hidden, offOn: CLS.has('po-offpane') });
out.boot = st();
window.__rompPaneToggle('artifacts', true); window.__rompPaneToggle('offpane', true);
out.on = st();
console.log(JSON.stringify(out));
"""

# a PHONE (the 1922 read): a generic pane loads by its TAB alone, never by the desktop flag; the current tab's frame loads on the
# controller's apply (the boot, the layout flip), once
_PHONE_DRIVER = r"""
const out = {};
out.boot = { notesSrc: frames['f-notes'].attrs.src || null, notesOn: CLS.has('po-notes'), artSrc: frames['f-artifacts'].attrs.src || null, sets: Object.assign({}, SETS) };
const reapply = () => { if (window.__rompPaneApply) window.__rompPaneApply(); };   // absent at a base without it: the reads below red on behaviour, not on a missing name
TAB = 'notes'; reapply();
out.tabNotes = { notesSrc: frames['f-notes'].attrs.src || null, sets: Object.assign({}, SETS) };
reapply();
out.again = { sets: Object.assign({}, SETS) };
TAB = 'chat'; reapply();
out.tabChat = { docsSrc: frames['f-docs'].attrs.src || null, sets: Object.assign({}, SETS) };
MOBILE = false; reapply();   // the layout flips to the desktop: every pane whose flag is on loads
out.desktop = { docsSrc: frames['f-docs'].attrs.src || null, sets: Object.assign({}, SETS) };
console.log(JSON.stringify(out));
"""

_PANES_DRIVER = r"""
const last = (k) => (POSTED[k] || []).slice(-1)[0];
const out = {};
out.boot = { notes: CLS.has('po-notes'), lab: CLS.has('po-lab'), docs: CLS.has('po-docs'), labHidden: BTNS.lab.hidden, notesHidden: BTNS.notes.hidden,
             notesSrc: frames['f-notes'].attrs.src || null, labSrc: frames['f-lab'].attrs.src || null,
             told: last('notes') ? last('notes').on : null, docsTold: (POSTED.docs || []).length };
window.__rompPaneToggle('notes');                 // the rail button: off
out.off = { notes: CLS.has('po-notes'), store: JSON.parse(STORE['romp-panes'] || 'null'), told: last('notes') ? last('notes').on.notes : null };
window.__rompPaneToggle('lab', true);             // not in this dashboard (experimental, the gear off): refused
out.labRefused = { lab: CLS.has('po-lab') };
STORE['romp:settings'] = JSON.stringify({ panes: { lab: true } }); STORAGE.forEach((f) => f({ key: 'romp:settings' }));   // the gear's row turns it on
out.labOn = { hidden: BTNS.lab.hidden, lab: CLS.has('po-lab'), labSrc: frames['f-lab'].attrs.src || null };
window.__rompPaneToggle('lab', true);
out.labShown = { lab: CLS.has('po-lab'), told: last('notes') ? last('notes').on.lab : null, docsTold: (POSTED.docs || []).length };
STORE['romp:settings'] = JSON.stringify({ panes: { notes: false } }); STORAGE.forEach((f) => f({ key: 'romp:settings' }));   // the gear hides the notes pane
out.notesGone = { hidden: BTNS.notes.hidden, notes: CLS.has('po-notes'), inTold: last('chat') ? ('notes' in last('chat').on) : null };
console.log(JSON.stringify(out));
"""

_SOURCE_STUB = r"""
'use strict';
const ORIGIN = 'http://TESTHOST:7432';
const W = { romp: {}, none: {}, stranger: {} };
const FR = [ { contentWindow: W.romp, getAttribute: (a) => (a === 'data-protocol' ? 'romp' : null) },
             { contentWindow: W.none, getAttribute: (a) => (a === 'data-protocol' ? 'none' : null) },
             { contentWindow: {}, getAttribute: () => null } ];
const HANDLERS = [], TOGGLES = [];
global.window = global;
global.location = { origin: ORIGIN };
global.addEventListener = (ev, f) => { if (ev === 'message') HANDLERS.push(f); };
global.document = { getElementById: () => null, querySelectorAll: (s) => (s === 'iframe' ? FR : []), addEventListener() {} };
global.setTimeout = () => 0;
window.__rompPaneToggle = (k, to) => { TOGGLES.push([k, to]); };
"""

_SOURCE_DRIVER = r"""
const ok = window.__rompPaneSourceOk;
const ev = (source, origin) => ({ source, origin: origin || ORIGIN, data: { romp: 'toggleFleet', to: 'fleet' } });
const out = { defined: typeof ok };
if (typeof ok === 'function') {
  out.romp = ok(ev(W.romp)); out.none = ok(ev(W.none)); out.shell = ok(ev(window)); out.stranger = ok(ev(W.stranger));
  out.otherOrigin = ok(ev(W.romp, 'http://TESTHOST:9')); out.noSource = ok({ origin: ORIGIN, data: {} }); out.nothing = ok(null);
  W.romp.parent = window; W.none.parent = window;
  out.nestedInRomp = ok(ev({ parent: W.romp })); out.nestedInNone = ok(ev({ parent: W.none }));
}
// the Outline's bridge handler, fed a forged toggle from the URL pane, one from a frame nested in a protocol pane, and a real one
HANDLERS.forEach((h) => h(ev(W.none)));
HANDLERS.forEach((h) => h(ev({ parent: W.romp })));
out.forgedToggles = TOGGLES.length;
HANDLERS.forEach((h) => h(ev(W.romp)));
out.realToggles = TOGGLES.length;
console.log(JSON.stringify(out));
"""

# the same bridge handler on a page WITHOUT the shell's check: fail-closed, nothing is acted on
_CLOSED_DRIVER = r"""
const ev = (source) => ({ source, origin: ORIGIN, data: { romp: 'toggleFleet', to: 'fleet' } });
HANDLERS.forEach((h) => h(ev(W.romp)));
console.log(JSON.stringify({ defined: typeof window.__rompPaneSourceOk, toggles: TOGGLES.length }));
"""


def _stub(rows, seed=""):
    """The pane controller's DOM stub for `rows` (the body attribute as the landing carries it), with `seed` run before the script."""
    return (_PANES_STUB.replace("__ATTR__", json.dumps(json.dumps(rows))).replace("__DATA_IDS__", json.dumps([r["id"] for r in rows]))
            .replace("__PROTO__", json.dumps({r["id"]: r["protocol"] for r in rows})).replace("__SEED__", seed))


class TheInlineScripts(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_the_pane_controller_shows_a_data_pane_by_its_flag_hides_an_experimental_one_until_the_gear_asks_and_tells_no_url_pane(self):
        rows = _rows(NOTES, DOCS, LAB)   # the attribute as the landing carries it, for the executed script
        stub = _stub(rows)
        r = _run(stub + km._LANDING_COLLAPSE_JS + _PANES_DRIVER)
        b = r["boot"]
        self.assertTrue(b["notes"], "on: true puts the pane on screen at boot: %r" % b)
        self.assertEqual(b["notesSrc"], "/notes", "a shown data pane's iframe gets its src (the optional panes' rule)")
        self.assertFalse(b["notesHidden"]); self.assertTrue(b["docs"], b)
        self.assertFalse(b["lab"]); self.assertTrue(b["labHidden"], "experimental: not in this dashboard until the gear's row asks")
        self.assertIsNone(b["labSrc"], "an experimental pane never loads until asked for")
        self.assertEqual(b["told"], {"chat": True, "timeline": True, "fleet": False, "feed": True, "files": False, "docs": True, "notes": True},
                         "the broadcast names the data panes beside the shipped ones (the experimental ones, the Artifacts record and the lab pane, are not in this dashboard until the gear asks)")
        self.assertEqual(b["docsTold"], 0, "a URL pane (protocol none) is told nothing")
        self.assertEqual((r["off"]["notes"], r["off"]["store"]["notes"], r["off"]["told"]), (False, False, False), "the rail toggle, persisted, broadcast")
        self.assertFalse(r["labRefused"]["lab"])
        self.assertEqual((r["labOn"]["hidden"], r["labOn"]["lab"], r["labOn"]["labSrc"]), (False, True, "/lab"),
                         "the gear's row turning a pane on brings it on screen and loads it (the optional panes' live reconcile)")
        self.assertEqual((r["labShown"]["lab"], r["labShown"]["told"], r["labShown"]["docsTold"]), (True, True, 0), "and the panes are told; the URL pane still nothing")
        self.assertEqual((r["notesGone"]["hidden"], r["notesGone"]["notes"], r["notesGone"]["inTold"]), (True, False, False), "a gear-hidden data pane is gone from the dashboard and from the broadcast")

    def test_a_generic_pane_enabled_in_the_gear_loads_only_when_it_comes_on_screen(self):
        rows = _rows(NOTES, DOCS, LAB, OFFPANE)
        r = _run(_stub(rows, "STORE['romp:settings'] = JSON.stringify({ panes: { artifacts: true } });") + km._LANDING_COLLAPSE_JS + _GATE_DRIVER)
        b = r["boot"]
        self.assertEqual((b["artHidden"], b["artOn"], b["artSrc"]), (False, False, None), "the Artifacts pane enabled in the gear: its button back, off screen by its rail default, NOT loaded: %r" % b)
        self.assertEqual((b["offHidden"], b["offOn"], b["offSrc"]), (False, False, None), "a non-experimental on:false data pane: in the dashboard, off screen, not loaded")
        o = r["on"]
        self.assertEqual((o["artOn"], o["artSrc"], o["offOn"], o["offSrc"]), (True, "/artifacts", True, "/offpane"), "the rail toggle brings each on screen and loads it once: %r" % o)

    def test_on_a_phone_a_generic_pane_loads_by_its_tab_alone_and_the_current_tab_loads_on_the_apply(self):
        rows = _rows(NOTES, DOCS, LAB)
        r = _run(_stub(rows, "MOBILE = true; TAB = 'chat'; STORE['romp-panes'] = JSON.stringify({ notes: true, docs: true });") + km._LANDING_COLLAPSE_JS + _PHONE_DRIVER)
        b = r["boot"]
        self.assertEqual((b["notesOn"], b["notesSrc"], b["artSrc"]), (True, None, None), "the desktop flag on, the phone on the chat tab: the notes pane is NOT loaded into a frame the phone never shows: %r" % b)
        generic = lambda sets: {k: v for k, v in sets.items() if k not in ("chat", "timeline", "fleet", "feed", "files")}   # the hand-written optional panes load by their flag on every layout (unchanged)
        self.assertEqual(generic(b["sets"]), {}, "no generic pane's src written at boot on a phone: %r" % b["sets"])
        self.assertEqual((r["tabNotes"]["notesSrc"], generic(r["tabNotes"]["sets"])), ("/notes", {"notes": 1}), "the current tab's frame loads on the apply (the boot, the layout flip): %r" % r["tabNotes"])
        self.assertEqual(generic(r["again"]["sets"]), {"notes": 1}, "and once")
        self.assertEqual(r["tabChat"]["docsSrc"], None, "another tab current: the docs pane (flag on) still not loaded")
        self.assertEqual(r["desktop"]["docsSrc"], "/docs", "the layout flipped to the desktop: the flag loads it: %r" % r["desktop"])

    def test_the_source_check_takes_a_protocol_frame_and_drops_the_shell_a_stranger_a_foreign_origin_a_url_pane_and_a_nested_frame(self):
        r = _run(_SOURCE_STUB + km._LANDING_BOOT_JS + km._LANDING_FLEET_JS + _SOURCE_DRIVER)
        self.assertEqual(r.get("forgedToggles"), 0, "a toggleFleet forged by the URL pane or by a frame nested in a pane must not toggle: %r" % r)
        self.assertEqual(r.get("realToggles"), 1, "a protocol pane's own toggle lands: %r" % r)
        self.assertEqual({k: r.get(k) for k in ("romp", "none", "shell", "stranger", "otherOrigin", "noSource", "nothing", "nestedInRomp", "nestedInNone")},
                         {"romp": True, "none": False, "shell": False, "stranger": False, "otherOrigin": False, "noSource": False, "nothing": False,
                          "nestedInRomp": False, "nestedInNone": False}, "the check rules on the IMMEDIATE source frame (plans/panes-as-data.md section 5)")

    def test_a_listener_on_a_page_without_the_check_acts_on_nothing(self):
        # fail-closed (the 1919 read): the bridge handler executed without the boot script that defines the check
        r = _run(_SOURCE_STUB + km._LANDING_FLEET_JS + _CLOSED_DRIVER)
        self.assertEqual(r, {"defined": "undefined", "toggles": 0}, "no check on the page, no message acted on: %r" % r)

    def test_every_shell_listener_reads_the_one_check_inline_and_bundled_and_the_baked_maps_read_the_attribute(self):
        # the census: every `message` listener the landing registers (except the service worker's, which is the worker's own
        # channel), every listener in the sources of the bundles the landing loads, and the built bundles themselves
        html = km._landing()
        regs = [m.start() for m in re.finditer(r"addEventListener\('message',", html)]
        self.assertGreaterEqual(len(regs), 14, "the shell's message listeners: %d" % len(regs))
        open_ones, sw = [], 0
        for i in regs:
            if html[max(0, i - 4):i] == "swc.":
                sw += 1; continue
            m = re.match(r"addEventListener\('message',function\(e\)\{", html[i:i + 80])   # the guard reads `e`, so the listener is a function of e
            if not m or not html[i + m.end():].startswith(GUARD):   # the FIRST statement, not anywhere in the next 200 characters (the 1919 read)
                open_ones.append(html[i:i + 140])
        self.assertEqual(sw, 1, "the service worker's notificationClick listener, on the worker's channel")
        self.assertEqual(open_ones, [], "every inline listener reads the check, fail-closed, as its first statement")
        self.assertIn("window.__rompPaneSourceOk=function(e)", km._LANDING_BOOT_JS, "defined by the first script on the page")
        self.assertLess(html.index("window.__rompPaneSourceOk=function(e)"), regs[0], "before any listener is registered")
        names = sorted(set(re.findall(r"src=/dist/([a-z-]+)\.js", html)))
        self.assertIn("palette-main", names); self.assertIn("panedock-main", names)
        listeners = {}
        for n in names:
            fp = os.path.join(ROOT, "ui", "webview", n + ".ts")
            if not os.path.exists(fp):
                continue
            src = open(fp).read()
            for m in re.finditer(r'addEventListener\(\s*"message"|on\(\s*window\s*,\s*"message"', src):
                tail = src[m.start():m.start() + 400]
                listeners.setdefault(n, []).append("paneSourceOk(" in tail or "protocolFrame(" in tail)
        self.assertEqual(sorted(listeners), ["palette-main", "panedock-main"], "the shell bundles with message listeners: %r" % listeners)
        self.assertTrue(all(all(v) for v in listeners.values()), "every bundled listener reads the one check: %r" % listeners)
        self.assertIn("if (!paneSourceOk(e)) return null;", open(os.path.join(ROOT, "ui", "webview", "panedock-main.ts")).read(), "the kit's frame lookup reads it first")
        # the BUILT bundles are read by tests/test_pane_registry_served.py (TheBuiltBundles), which CI's browser job runs with the extension
        # built; here that leg skipped in every pytest cell and its pass was invisible (the 1919 read)

    def test_the_baked_maps_read_the_attribute(self):
        # executed in every CI cell (the 1922 read: these pins sat behind a dist gate that skipped them everywhere but a built checkout)
        self.assertIn("PANE['f-'+p.id]=p.id+'-pane';COLS.push('f-'+p.id);", km._LANDING_FOCUS_JS, "the focus ring's map and column list")
        self.assertIn("if(!(p.id in PN))PN[p.id]=String(p.title||p.id);", km._LANDING_ERRS_JS, "the bell's titles")
        self.assertIn("F[p.id]=document.getElementById('f-'+p.id);", km._LANDING_MOBILE_JS, "the phone's frames")
        self.assertIn("var sf=F[p];if(mobileOn()&&window.__rompPaneToggle&&sf&&sf.getAttribute&&!sf.getAttribute('src')&&sf.getAttribute('data-src'))sf.setAttribute('src',sf.getAttribute('data-src'));", km._LANDING_MOBILE_JS,
                      "a phone shows a pane by its tab: the tap loads the shown pane's iframe once, generically (the 1922 read: a data pane's tab showed a blank pane), on a phone only and once the pane controller has parsed (its boot apply copies the current tab's frame)")
        self.assertIn("if(!btn)p='chat';", km._LANDING_MOBILE_JS, "a pane with no tab button falls to the chat, never a bare return (a stale remembered key)")
        self.assertIn("window.__rompPaneApply=apply;", km._LANDING_COLLAPSE_JS, "the controller's apply is re-run on the layout flip")
        self.assertIn("try{window.__rompPaneApply&&window.__rompPaneApply();}catch(e){}try{window.__rompPanesTell&&window.__rompPanesTell();}catch(e){}", km._LANDING_MOBILE_JS, "the media query's change event re-applies, then re-tells")
        self.assertIn("var load=mob?(tab===k&&(k in po)):!!po[k];", km._LANDING_COLLAPSE_JS, "on a phone a generic pane loads by its tab alone, never by the desktop flag")
        self.assertIn("KEYS[p.id+'-pane']=p.id;", km._LANDING_JS, "a data pane's grow key")
        self.assertIn("gutter('gv-'+p.id,function(){for(var j=i-1;j>=0;j--){if(document.body.classList.contains('po-'+key(seq[j])))return seq[j];}return lastChat();},me);", km._LANDING_JS,
                      "one gutter per data pane, its left neighbour the rightmost shown column before it")
        self.assertIn('var seq=["fleet-pane", "feed-pane", "files-pane"].concat(', km._LANDING_JS, "the hand-written columns, then every generic pane (the Artifacts record, the data panes) from the attribute")


_RELOAD_STUB = r"""
// the browser the reload core thinks it runs in (tests/test_dashboard_auto_reload.py's harness, the members this scenario touches)
var LISTENERS = {}, STORE = {}, LOCAL = {}, RELOADS = 0, WLISTENERS = {};
var document = {
  createElement: function () { return { id: "", innerHTML: "", classList: { add: function () {}, remove: function () {} } }; },
  addEventListener: function (t, f) { (LISTENERS[t] = LISTENERS[t] || []).push(f); },
  getSelection: function () { return { rangeCount: 0, isCollapsed: true, toString: function () { return ""; } }; },
  hasFocus: function () { return true; },
  getElementById: function () { return null; },
  activeElement: null,
  body: { classList: { remove: function () {}, add: function () {} }, appendChild: function () {} },
  querySelectorAll: function () { return []; }
};
var _setTimeout = globalThis.setTimeout;
function setTimeout(f, ms) { if (ms > 0) return 1; return _setTimeout(f, ms); }
function clearTimeout() {}
var window = { addEventListener: function (t, f) { (WLISTENERS[t] = WLISTENERS[t] || []).push(f); } };
window.parent = window;
var location = { pathname: "/", reload: function () { RELOADS++; } };
var sessionStorage = { setItem: function (k, v) { STORE[k] = v; }, getItem: function (k) { return k in STORE ? STORE[k] : null; }, removeItem: function (k) { delete STORE[k]; } };
var localStorage = { setItem: function (k, v) { LOCAL[k] = v; }, getItem: function (k) { return k in LOCAL ? LOCAL[k] : null; }, removeItem: function (k) { delete LOCAL[k]; } };
function fetch() { return new Promise(function () {}); }
"""
_RELOAD_DRIVER = r"""
const R = window.__rompReload; const out = {};
out.before = R.offered();
if (R.notePanes) { R.notePanes(__PV0__); out.same = R.offered(); R.notePanes('abc123'); out.moved = R.offered(); }
else { out.same = null; out.moved = null; }
out.reloaded = RELOADS > 0;
console.log(JSON.stringify(out));
"""

# the two offers side by side (the 1919 read: one seen.code slot, so the panes offer and the build offer overwrote each other's
# standing offer on every keepalive, and a declined build was re-offered once a panes offer had been declined too)
_RELOAD_TWO_DRIVER = r"""
const R = window.__rompReload; const out = {};
R.noteVersion({ code_ident: 'C1' }); out.build = R.offered();
R.behind(); out.behind = R.offered();
R.notePanes('B'); out.panesBeside = R.offered();            // the pane set moved too: the standing BUILD offer keeps its words, and carries the revision
R.noteVersion({ code_ident: 'C1' }); out.buildAgain = R.offered();   // nothing new: the same offer stands
R.notePanes('B'); out.panesAgain = R.offered();
R.dismiss(); out.declined = R.offered();                    // Not now: covers the build AND the revision it was made against
R.noteVersion({ code_ident: 'C1' }); out.buildAfterDecline = R.offered();
R.notePanes('B'); out.panesAfterDecline = R.offered();
R.notePanes('C'); out.newRevision = R.offered();            // a NEW revision is new information: offered, with the panes words alone? no: the build is still new beside it
console.log(JSON.stringify(out));
"""

_RELOAD_PANES_ONLY_DRIVER = r"""
const R = window.__rompReload; const out = {};
R.notePanes('B'); out.panes = R.offered();                  // the revision the sole new information: the panes words
R.dismiss(); R.notePanes('B'); out.declined = R.offered();  // declined, the same revision offers nothing
R.notePanes('C'); out.moved = R.offered();                  // another revision offers again
console.log(JSON.stringify(out));
"""


if __name__ == "__main__":
    unittest.main()
