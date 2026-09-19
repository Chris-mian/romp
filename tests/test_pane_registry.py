#!/usr/bin/env python3
"""The pane registry (plans/panes-as-data.md, phase one). A pane is a record in ONE schema: the shipped panes are the
kernel's code constants (_CODE_PANES, checked at import by _pane_check like the code boards), every other pane a JSON document
under STATE/panes/<id>.json behind define_pane (the board door's twin: POST /pane, GET /panes, `romp pane`). The shell renders
from _pane_order() per request, and the FIRST pin is that with an empty registry its landing is byte-identical to the
five-constant landing. A data pane gets a rail button, a phone tab (none when experimental), a lazy iframe (data-src), its
column and gutter rules and a row in body[data-panes] that the five baked inline scripts read; a URL source is a plain
sandboxed iframe with no token, no ?v= and no protocol, and the shell's handlers drop a message from it (the source check).
The pane set's revision rides every keepalive beside the build token and a page baked with another is offered a reload.
Synthetic fixtures only (the notes-api demo world; TESTHOST)."""
import contextlib
import html as html_mod
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
_XDG = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _XDG
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(_XDG, "romp"), exist_ok=True)
open(os.path.join(_XDG, "romp", "session-hosts"), "w").write("off\n")
km = load_source("romp_kernel_pane_registry", os.path.join(BIN, "romp-kernel"))
KSRC = open(os.path.join(BIN, "romp-kernel")).read()

SHIPPED = ["chat", "timeline", "fleet", "feed", "files", "artifacts"]   # the shipped panes (the Artifacts pane since 2026-09-19)
NOTES = {"id": "notes", "title": "Notes", "source": "pane:notes", "on": True}
DOCS = {"id": "docs", "title": "Docs", "source": "http://TESTHOST:9/docs/", "on": True}          # a URL: protocol none
LAB = {"id": "lab", "title": "Lab", "source": "/feed", "experimental": True}                       # a kernel route, experimental
GUARD = "if(window.__rompPaneSourceOk&&!window.__rompPaneSourceOk(e))return;"


def _full(d):
    """The record as the check fills it."""
    out = {"title": d["id"].capitalize(), "on": False, "experimental": False,
           "protocol": "none" if d["source"].startswith("http") else "romp"}
    out.update(d)
    return out


class World:
    """A hermetic state root, the kernel rebound to it, the pane memo cleared."""
    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.orig_state = km.jd.STATE
        km.jd._rebind_state(root / "state")
        (km.jd.STATE / "session-hosts").parent.mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "session-hosts").write_text("off\n")
        self.reset_memos()

    @staticmethod
    def reset_memos():
        # guarded: at a base without the registry these names are absent, and each test must then red on its own behaviour
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


# ── the schema ──────────────────────────────────────────────────────────────────────────────────────────────────
class TheSchema(unittest.TestCase):
    def test_the_five_shipped_panes_are_records_in_the_schema_and_the_order_constant_derives_from_them(self):
        recs = list(km._CODE_PANES)
        self.assertEqual([p["id"] for p in recs], SHIPPED)
        self.assertEqual([p["title"] for p in recs], ["Chat", "Sessions", "Outline", "Feed", "Files", "Artifacts"])
        self.assertEqual([p["on"] for p in recs], [True, True, False, True, False, False], "today's rail defaults are the records' `on`")
        self.assertTrue(all(p["protocol"] == "romp" and not p["experimental"] and p["source"] == "/" + p["id"] for p in recs))
        for p in recs:
            d, err = km._pane_check(dict(p), allow_reserved=True)
            self.assertIsNone(err); self.assertEqual(d, p, "a shipped record passes its own check unchanged")
        self.assertEqual(km._PANE_ORDER, tuple((p["id"], p["title"]) for p in recs), "the (key, label) constant the pins read derives from the records")
        self.assertEqual(km._pane_label("timeline"), "Sessions")
        self.assertEqual(km._pane_order(), recs, "with an empty registry the order is the shipped panes")

    def test_the_check_fills_the_defaults_and_refuses_by_member(self):
        d, err = km._pane_check({"id": "notes", "source": "/feed"})
        self.assertIsNone(err)
        self.assertEqual(d, {"id": "notes", "title": "Notes", "source": "/feed", "on": False, "experimental": False, "protocol": "romp"})
        d, err = km._pane_check(dict(DOCS))
        self.assertIsNone(err); self.assertEqual(d["protocol"], "none", "a URL source is a plain iframe: protocol none by default")
        d, err = km._pane_check({"id": "notes", "title": "  Notes  ", "source": "pane:notes", "on": True, "experimental": True, "protocol": "romp"})
        self.assertIsNone(err); self.assertEqual((d["title"], d["on"], d["experimental"]), ("Notes", True, True))
        for bad, word in (
                ("not a dict", "JSON object"),
                ({"id": "notes", "source": "/feed", "colour": "red"}, "unknown member colour"),
                ({"id": "Notes", "source": "/feed"}, "id must"),
                ({"id": "n" * 33, "source": "/feed"}, "id must"),
                ({"id": "feed", "source": "/feed"}, "reserved"),
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
            d, err = km._pane_check(bad)
            self.assertIsNone(d, bad); self.assertIn(word, err or "", (bad, err))


# ── the store ───────────────────────────────────────────────────────────────────────────────────────────────────
class TheStore(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_define_writes_the_record_whole_and_the_order_reads_the_data_panes_after_the_shipped_five_by_id(self):
        self.assertEqual(km._panes_data(), {})
        d, err = km.define_pane(dict(NOTES))
        self.assertIsNone(err); self.assertEqual(d, _full(NOTES))
        fp = km.jd.STATE / "panes" / "notes.json"
        self.assertEqual(json.loads(fp.read_text()), _full(NOTES), "the file holds the filled record, not the request")
        self.assertEqual([p["id"] for p in km._pane_order()], SHIPPED + ["notes"])
        self.assertEqual(km._data_panes(), [_full(NOTES)])
        km.define_pane(dict(DOCS)); km.define_pane(dict(LAB))
        self.assertEqual([p["id"] for p in km._pane_order()], SHIPPED + ["docs", "lab", "notes"], "data panes by id after the shipped panes")
        d, err = km.define_pane(dict(NOTES, title="Notebook"))
        self.assertIsNone(err)
        self.assertEqual(km._panes_data()["notes"]["title"], "Notebook", "a define replaces the pane whole")
        self.assertEqual(km._pane_label("notes"), "Notebook", "the label reads the whole list")
        d, err = km.define_pane(dict(NOTES, id="feed"))
        self.assertIsNone(d); self.assertIn("reserved", err)
        self.assertFalse((km.jd.STATE / "panes" / "feed.json").exists(), "a refusal writes nothing")

    def test_a_bad_file_is_skipped_and_named_once_and_a_rewrite_in_place_is_read(self):
        km.define_pane(dict(NOTES))
        pdir = km.jd.STATE / "panes"
        (pdir / "bad.json").write_text("{")
        (pdir / "other.json").write_text(json.dumps(_full(dict(NOTES, id="notes2"))))   # names another pane than its file
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(sorted(km._panes_data()), ["notes"])
            km._PANES_MEMO["slot"] = None
            self.assertEqual(sorted(km._panes_data()), ["notes"])
        lines = [ln for ln in err.getvalue().splitlines() if "[panes]" in ln]
        self.assertEqual(len(lines), 2, "each bad file is named once, on stderr: %r" % lines)
        self.assertTrue(any("bad.json" in ln for ln in lines) and any("other.json" in ln and "notes2" in ln for ln in lines), lines)
        # an in-place rewrite (an editor, a shell redirection) moves the file's stat: the memo re-reads
        fp = pdir / "notes.json"
        fp.write_text(json.dumps(_full(dict(NOTES, title="Notebook"))))
        st = os.stat(fp); os.utime(fp, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
        self.assertEqual(km._panes_data()["notes"]["title"], "Notebook")

    def test_remove_refuses_a_shipped_pane_and_an_unknown_id_and_deletes_the_file(self):
        ok, err = km.remove_pane("feed"); self.assertFalse(ok); self.assertIn("shipped", err)
        ok, err = km.remove_pane("nope"); self.assertFalse(ok); self.assertIn("no pane", err)
        km.define_pane(dict(NOTES))
        ok, err = km.remove_pane("notes"); self.assertTrue(ok); self.assertIsNone(err)
        self.assertFalse((km.jd.STATE / "panes" / "notes.json").exists())
        self.assertEqual([p["id"] for p in km._pane_order()], SHIPPED)

    def test_the_revision_is_zero_with_no_panes_and_moves_on_a_define_and_on_a_remove(self):
        self.assertEqual(km._panes_rev(), "0")
        km.define_pane(dict(NOTES)); r1 = km._panes_rev()
        self.assertNotEqual(r1, "0"); self.assertEqual(r1, km._panes_rev(), "stable while nothing changes")
        km.define_pane(dict(DOCS)); r2 = km._panes_rev()
        self.assertNotEqual(r2, r1)
        km.remove_pane("docs"); km.remove_pane("notes")
        self.assertEqual(km._panes_rev(), "0")


# ── the landing ─────────────────────────────────────────────────────────────────────────────────────────────────
def _has(tc, needle, page, msg=""):
    # assertTrue, not assertIn: a failure must never print the landing
    tc.assertTrue(needle in page, "missing from the page: %r %s" % (needle, msg))


def _lacks(tc, needle, page, msg=""):
    tc.assertTrue(needle not in page, "present in the page: %r %s" % (needle, msg))


def _attr_rows(page):
    m = re.search(r"<body class='po-chat po-feed po-timeline' data-panes=\"([^\"]*)\">", page)
    return json.loads(html_mod.unescape(m.group(1))) if m else None


class TheLanding(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def test_00_the_code_panes_landing_is_byte_identical_with_an_empty_registry(self):
        # THE FIRST PIN (plans/panes-as-data.md, section 7): a kernel with no data pane serves the landing it served before the
        # registry existed, byte for byte: no attribute, no protocol marks, no registry markup, and a define followed by a
        # remove leaves the bytes exactly as they were.
        h0 = km._landing()
        self.assertTrue(h0 == km._landing(), "the landing is a pure function of the registry and the build")
        _has(self, "<body class='po-chat po-feed po-timeline'>", h0)
        # the markup's markers, never the inline scripts' quoted reads of the attribute (those are baked in and read nothing)
        _lacks(self, ' data-panes="', h0); _lacks(self, " data-protocol=romp>", h0); _lacks(self, " data-protocol=none sandbox=", h0)
        _lacks(self, "id=gv-notes", h0); _lacks(self, "/pane/", h0)
        d, err = km.define_pane(dict(NOTES)); self.assertIsNone(err)
        h1 = km._landing()
        self.assertTrue(h1 != h0); _has(self, ' data-panes="', h1)
        ok, err = km.remove_pane("notes"); self.assertTrue(ok)
        self.assertTrue(km._landing() == h0, "define then remove: the bytes are back")

    def test_a_data_pane_renders_a_rail_button_a_tab_a_lazy_iframe_its_rules_and_the_attribute(self):
        for d in (NOTES, DOCS, LAB):
            self.assertIsNone(km.define_pane(dict(d))[1])
        page = km._landing()
        rail = re.search(r"<div class=rail-btn data-pane=chat>.*?data-pane=notes>Notes</div>", page).group(0)
        self.assertTrue(rail.endswith("<div class=rail-btn data-pane=files>Files</div><div class=rail-btn data-pane=artifacts>Artifacts</div>"
                                      "<div class=rail-btn data-pane=docs>Docs</div><div class=rail-btn data-pane=lab>Lab</div><div class=rail-btn data-pane=notes>Notes</div>"), rail)
        _has(self, "<button data-pane=notes>Notes</button>", page, "a phone tab")
        _has(self, "<button data-pane=docs>Docs</button>", page)
        _lacks(self, "data-pane=lab>Lab</button>", page, "an experimental pane has no phone tab")
        _has(self, '<div class=gv id=gv-notes></div><div class=pane id=notes-pane><iframe id=f-notes data-src="/pane/notes/" data-protocol=romp></iframe></div>', page,
             "a state-root pane loads /pane/<id>/ when shown (data-src, the optional panes' rule)")
        _has(self, '<div class=gv id=gv-docs></div><div class=pane id=docs-pane><iframe id=f-docs data-src="http://TESTHOST:9/docs/" data-protocol=none sandbox="allow-scripts allow-forms allow-popups"></iframe></div>', page,
             "a URL pane: the URL as given (no ?v=, no token), sandboxed, marked protocol none")
        _has(self, '<iframe id=f-lab data-src="/feed" data-protocol=romp></iframe>', page, "a kernel route as given")
        self.assertLess(page.index("id=artifacts-pane"), page.index("id=gv-docs")); self.assertLess(page.index("id=gv-docs"), page.index("id=gv-notes"))
        self.assertLess(page.index("id=gv-notes"), page.index("</div><div id=tl-pane") if "</div><div id=tl-pane" in page else len(page), "the data panes sit in the pane row, after Files")
        _has(self, "#notes-pane{flex:var(--g-notes,40) 1 0}body:not(.po-notes) #notes-pane{display:none}", page)
        _has(self, "body:not(.po-docs) #gv-docs,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files):not(.po-artifacts) #gv-docs{display:none}", page,
             "the first data gutter hides with its pane off or with no shown column before it")
        _has(self, "body:not(.po-notes) #gv-notes,body:not(.po-chat):not(.po-fleet):not(.po-feed):not(.po-files):not(.po-artifacts):not(.po-docs):not(.po-lab) #gv-notes{display:none}", page)
        rows = _attr_rows(page)
        self.assertEqual(rows, [{"id": "docs", "title": "Docs", "protocol": "none", "experimental": False, "on": True},
                                {"id": "lab", "title": "Lab", "protocol": "romp", "experimental": True, "on": False},
                                {"id": "notes", "title": "Notes", "protocol": "romp", "experimental": False, "on": True}],
                         "the attribute carries what the inline scripts and the pane bundles read, never the source")
        for d in (NOTES, DOCS, LAB):
            km.remove_pane(d["id"])
        self.assertEqual(page.count("<script>"), km._landing().count("<script>"), "no inline script is added for a data pane: the baked ones read the attribute")

    def test_a_title_is_escaped_in_the_rail_the_tab_and_the_attribute(self):
        self.assertIsNone(km.define_pane({"id": "x", "title": "A <b>&", "source": "/feed", "on": True})[1])
        page = km._landing()
        _has(self, "<div class=rail-btn data-pane=x>A &lt;b&gt;&amp;</div>", page)
        _has(self, "<button data-pane=x>A &lt;b&gt;&amp;</button>", page)
        attr = re.search(r"data-panes=\"([^\"]*)\"", page).group(1)
        self.assertNotIn("<", attr); self.assertNotIn('"', attr)
        self.assertEqual(_attr_rows(page)[0]["title"], "A <b>&")


# ── the inline scripts read the attribute ───────────────────────────────────────────────────────────────────────
_PANES_STUB = r"""
'use strict';
const ATTR = __ATTR__;
const KEYS = ['chat','timeline','fleet','feed','files','artifacts'].concat(__DATA_IDS__);
const PROTO = __PROTO__;
const POSTED = {}, CLS = new Set(['po-chat', 'po-feed', 'po-timeline']), STORE = {}, STORAGE = [], TABS = [];
const frames = {};
KEYS.forEach((k) => { const attrs = (k === 'chat' || k === 'files') ? { src: '/' + k } : { 'data-src': '/' + k }; if (PROTO[k]) attrs['data-protocol'] = PROTO[k]; frames['f-' + k] = {
  attrs, getAttribute: (a) => (a in attrs ? attrs[a] : null), setAttribute: (a, v) => { attrs[a] = v; },
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
"""

_PANES_DRIVER = r"""
const last = (k) => (POSTED[k] || []).slice(-1)[0];
const out = {};
out.boot = { notes: CLS.has('po-notes'), lab: CLS.has('po-lab'), docs: CLS.has('po-docs'), labHidden: BTNS.lab.hidden, notesHidden: BTNS.notes.hidden,
             notesSrc: frames['f-notes'].attrs.src || null, labSrc: frames['f-notes'] && frames['f-lab'].attrs.src || null,
             told: last('notes') ? last('notes').on : null, chatTold: last('chat') ? last('chat').on : null, docsTold: (POSTED.docs || []).length };
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
  const nestedRomp = { parent: W.romp }, nestedNone = { parent: W.none };
  W.romp.parent = window; W.none.parent = window;
  out.nestedRomp = ok(ev(nestedRomp)); out.nestedNone = ok(ev(nestedNone));
}
// the Outline's bridge handler, fed a forged toggle from the URL pane and a real one from a protocol pane
HANDLERS.forEach((h) => h(ev(W.none)));
out.forgedToggles = TOGGLES.length;
HANDLERS.forEach((h) => h(ev(W.romp)));
out.realToggles = TOGGLES.length;
console.log(JSON.stringify(out));
"""


class TheInlineScripts(unittest.TestCase):
    def setUp(self): self.w = World()
    def tearDown(self): self.w.close()

    def _attr(self, *defs):
        for d in defs:
            self.assertIsNone(km.define_pane(dict(d))[1])
        rows = _attr_rows(km._landing())
        return json.dumps(json.dumps(rows)), json.dumps([r["id"] for r in rows]), json.dumps({r["id"]: r["protocol"] for r in rows})

    def test_the_pane_controller_shows_a_data_pane_by_its_flag_hides_an_experimental_one_until_the_gear_asks_and_tells_no_url_pane(self):
        attr, ids, proto = self._attr(NOTES, DOCS, LAB)
        stub = _PANES_STUB.replace("__ATTR__", attr).replace("__DATA_IDS__", ids).replace("__PROTO__", proto)
        r = _run(stub + km._LANDING_COLLAPSE_JS + _PANES_DRIVER)
        b = r["boot"]
        self.assertTrue(b["notes"], "on: true puts the pane on screen at boot: %r" % b)
        self.assertEqual(b["notesSrc"], "/notes", "a shown data pane's iframe gets its src (the optional panes' rule)")
        self.assertFalse(b["notesHidden"]); self.assertTrue(b["docs"], b)
        self.assertFalse(b["lab"]); self.assertTrue(b["labHidden"], "experimental: not in this dashboard until the gear's row asks")
        self.assertIsNone(b["labSrc"], "an experimental pane never loads until asked for")
        self.assertEqual(b["told"], {"chat": True, "timeline": True, "fleet": False, "feed": True, "files": False, "artifacts": False, "docs": True, "notes": True},
                         "the broadcast names the data panes beside the shipped ones (the experimental one is not in this dashboard)")
        self.assertEqual(b["docsTold"], 0, "a URL pane (protocol none) is told nothing")
        self.assertEqual((r["off"]["notes"], r["off"]["store"]["notes"], r["off"]["told"]), (False, False, False), "the rail toggle, persisted, broadcast")
        self.assertFalse(r["labRefused"]["lab"])
        self.assertEqual((r["labOn"]["hidden"], r["labOn"]["lab"], r["labOn"]["labSrc"]), (False, True, "/lab"),
                         "the gear's row turning a pane on brings it on screen and loads it (the optional panes' live reconcile)")
        self.assertEqual((r["labShown"]["lab"], r["labShown"]["told"], r["labShown"]["docsTold"]), (True, True, 0), "and the panes are told; the URL pane still nothing")
        self.assertEqual((r["notesGone"]["hidden"], r["notesGone"]["notes"], r["notesGone"]["inTold"]), (True, False, False), "a gear-hidden data pane is gone from the dashboard and from the broadcast")

    def test_the_source_check_takes_a_protocol_frame_and_drops_the_shell_a_stranger_a_foreign_origin_and_a_url_pane(self):
        r = _run(_SOURCE_STUB + km._LANDING_BOOT_JS + km._LANDING_FLEET_JS + _SOURCE_DRIVER)
        self.assertEqual(r.get("forgedToggles"), 0, "a toggleFleet forged by the URL pane must not toggle: %r" % r)
        self.assertEqual(r.get("realToggles"), 1, "a protocol pane's toggle lands: %r" % r)
        self.assertEqual(r["defined"], "function")
        self.assertEqual({k: r[k] for k in ("romp", "none", "shell", "stranger", "otherOrigin", "noSource", "nothing", "nestedRomp", "nestedNone")},
                         {"romp": True, "none": False, "shell": False, "stranger": False, "otherOrigin": False, "noSource": False, "nothing": False,
                          "nestedRomp": True, "nestedNone": False})

    def test_every_shell_handler_reads_the_source_check_and_the_baked_maps_read_the_attribute(self):
        self.assertGreaterEqual(KSRC.count(GUARD), 11, "the boot, Outline bridge, unseen-log, notify, socket-state, usage, settings bridge, hosts, mobile reveal, feed reveal and stale handlers")
        for name in ("_LANDING_BOOT_JS", "_LANDING_FLEET_JS", "_LANDING_ERRS_JS", "_LANDING_USAGE_JS", "_LANDING_MOBILE_JS", "_LANDING_SETTINGS_JS", "_LANDING_REVEAL_JS"):
            self.assertIn(GUARD, getattr(km, name), name)
        self.assertIn("window.__rompPaneSourceOk=function(e)", km._LANDING_BOOT_JS, "defined by the first script on the page")
        self.assertLess(KSRC.index('"<script>" + _LANDING_BOOT_JS'), KSRC.index('"<script>" + _LANDING_ERRS_JS'))
        self.assertIn("PANE['f-'+p.id]=p.id+'-pane';COLS.push('f-'+p.id);", km._LANDING_FOCUS_JS, "the focus ring's map and column list")
        self.assertIn("if(!(p.id in PN))PN[p.id]=String(p.title||p.id);", km._LANDING_ERRS_JS, "the bell's titles")
        self.assertIn("F[p.id]=document.getElementById('f-'+p.id);", km._LANDING_MOBILE_JS, "the phone's frames")
        self.assertIn("KEYS[p.id+'-pane']=p.id;", km._LANDING_JS, "a data pane's grow key")
        self.assertIn("gutter('gv-'+p.id,function(){for(var j=i-1;j>=0;j--){if(document.body.classList.contains('po-'+key(seq[j])))return seq[j];}return lastChat();},me);", km._LANDING_JS,
                      "one gutter per data pane, its left neighbour the rightmost shown column before it")
        self.assertIn("var DPANES=[];try{DPANES=JSON.parse(document.body.getAttribute('data-panes')||'[]')||[];}catch(e){DPANES=[];}", km._LANDING_JS)


# ── the doors and the state-root pages ──────────────────────────────────────────────────────────────────────────
class TheDoors(unittest.TestCase):
    """POST /pane, GET /panes and GET /pane/<id>/... in /board's shape."""
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

    def test_the_routes_answer_in_the_board_doors_shape(self):
        self.assertNotEqual(self._call("/pane", NOTES, token=False)[0], 200, "no token: refused")
        self.assertNotEqual(self._call("/panes", token=False)[0], 200)
        st, r = self._call("/pane", b"[]"); self.assertEqual(st, 400)
        st, r = self._call("/pane", {}); self.assertEqual(st, 400); self.assertIn("pane definition", r["error"])
        st, r = self._call("/pane", dict(NOTES, id="feed")); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("reserved", r["error"])
        st, r = self._call("/pane", dict(NOTES, source="feed")); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("source must", r["error"])
        st, r = self._call("/pane", NOTES); self.assertEqual((st, r["ok"]), (200, True)); self.assertEqual(r["pane"], _full(NOTES))
        rev = r["rev"]; self.assertNotEqual(rev, "0")
        st, r = self._call("/panes"); self.assertEqual(st, 200)
        self.assertEqual([p["id"] for p in r["panes"]], SHIPPED + ["notes"])
        self.assertEqual([p["builtin"] for p in r["panes"]], [True] * len(SHIPPED) + [False])
        self.assertEqual(r["rev"], rev)
        self.assertEqual({k: v for k, v in r["panes"][len(SHIPPED)].items() if k != "builtin"}, _full(NOTES))
        st, r = self._call("/pane", {"remove": "chat"}); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("shipped", r["error"])
        st, r = self._call("/pane", {"remove": "scratch"}); self.assertEqual((st, r["ok"]), (200, False)); self.assertIn("no pane", r["error"])
        st, r = self._call("/pane", {"remove": "notes"}); self.assertEqual((st, r), (200, {"ok": True, "rev": "0"}))
        st, r = self._call("/panes"); self.assertEqual([p["id"] for p in r["panes"]], SHIPPED)

    def test_the_state_root_serves_a_panes_page_its_shim_and_the_theme_and_nothing_outside_it(self):
        self.assertEqual(self._req("/pane/notes/")[0], 404, "an undefined pane has no page")
        self._call("/pane", NOTES); self._call("/pane", LAB)
        pdir = km.jd.STATE / "panes" / "notes"; pdir.mkdir(parents=True, exist_ok=True)
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
        self.assertIn('var LOADEDPV="%s";' % km._panes_rev(), shim, "baked with the pane set's revision")
        self.assertIn("notePanes", shim)
        st, ct, body = self._req("/pane/notes/theme.css"); self.assertEqual((st, ct), (200, "text/css")); self.assertTrue(body.startswith(b"@font-face"), body[:40])
        self.assertEqual(self._req("/pane/notes/missing.js")[0], 404)
        self.assertEqual(self._req("/pane/notes/..%2F..%2Fsecret.txt")[0], 404, "no path leaves the pane's directory")
        self.assertEqual(self._req("/pane/notes/%2E%2E/%2E%2E/secret.txt")[0], 404)
        self.assertEqual(self._req("/pane/lab/")[0], 404, "a route-source pane has no state-root page")
        self.assertEqual(self._req("/pane/feed/")[0], 404, "nor a shipped one")
        self.assertNotEqual(self._req("/pane/notes/", token=False)[0], 200, "behind the token like every route")

    def test_the_keepalive_carries_the_pane_set_revision_and_a_page_baked_with_another_is_offered_a_reload(self):
        self.assertIn('s = json.dumps({"type": "ka", "dv": _dist_ver(), "pv": _panes_rev()})', KSRC, "pv rides every keepalive beside dv")
        self.assertIn('if(msg&&msg.type==="ka"&&LOADEDPV&&msg.pv&&msg.pv!==LOADEDPV){var RP=window.__rompReload;if(RP&&RP.notePanes)RP.notePanes(msg.pv);}', KSRC, "the pane shim hands a moved revision to the reload core, before the pinned ka branch")
        self.assertIn("if(m&&m.type==='ka'&&m.pv&&window.__rompReload&&window.__rompReload.notePanes)window.__rompReload.notePanes(m.pv);", km._LANDING_MOBILE_JS, "the shell's own socket too")
        self.assertEqual(km.RELOAD_OFFER_PANES_MSG, "The set of panes changed. Reload to see it.")
        core = km._reload_core(3)
        self.assertIn("panes:" + json.dumps(km.RELOAD_OFFER_PANES_MSG), core); self.assertIn("PANES0=%s" % json.dumps(km._panes_rev()), core)
        r = _run(_RELOAD_STUB + core + _RELOAD_DRIVER.replace("__PV0__", json.dumps(km._panes_rev())))
        self.assertIsNone(r["before"], "nothing offered on a current page")
        self.assertIsNone(r["same"], "the baked revision on the keepalive: nothing to say")
        self.assertEqual((r["moved"] or {}).get("text"), km.RELOAD_OFFER_PANES_MSG, "a moved revision: the offer, worded for the panes: %r" % r)
        self.assertEqual((r["moved"] or {}).get("code"), "panes:abc123")
        self.assertFalse(r["reloaded"], "an OFFER, never a self-reload")


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
R.notePanes(__PV0__); out.same = R.offered();
R.notePanes('abc123'); out.moved = R.offered();
out.reloaded = RELOADS > 0;
console.log(JSON.stringify(out));
"""


if __name__ == "__main__":
    unittest.main()
