#!/usr/bin/env python3
"""The shell's notification center (the user 2026-07-27) must actually WORK, not just parse.

Errors used to drop as fixed banners from the top of the screen and got in the way; they now land as
entries behind the bell in the bottom bar's action cluster. This EXECUTES the real injected
_LANDING_ERRS_JS in node against a DOM stub (the test_remotes_panel_render.py pattern — source pins
can't catch scope slips in this class of inline JS) and drives the full story:

  a visible pane's WS drop logs an entry + reddens the bell with an unread count; a repeat of the same
  drop coalesces (event-exact, no time window); a HIDDEN pane's drop logs nothing; opening the popover
  marks everything seen; panes can post {romp:'notify'}; per-row clear and Clear all empty the store;
  entries persist in localStorage.

Synthetic only — no network, no real DOM.
"""
import json
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_errc", os.path.join(BIN, "romp-kernel")).load_module()

HARNESS = r"""
'use strict';
const STORE = {};
global.localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
  removeItem: (k) => { delete STORE[k]; },
};
function mkEl(id) {
  return {
    id: id, hidden: true, textContent: '', title: '', className: '',
    children: [], _cls: new Set(), _ls: {}, _html: '', _badge: null,
    classList: null,   // filled below (needs `this`)
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) { return sel === '.rerr-badge' ? this._badge : null; },
    addEventListener(k, f) { (this._ls[k] = this._ls[k] || []).push(f); },
    fire(k, ev) { (this._ls[k] || []).forEach((f) => f(ev || { stopPropagation() {}, target: null })); },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; this.children = []; },
  };
}
function withCls(el) {
  el._cls = new Set();
  el.classList = {
    add: (c) => el._cls.add(c), remove: (c) => el._cls.delete(c),
    toggle: (c, on) => { if (on === undefined) on = !el._cls.has(c); if (on) el._cls.add(c); else el._cls.delete(c); },
    contains: (c) => el._cls.has(c),
  };
  return el;
}
const EL = {};
['rail-errs', 'merr', 'rerr-back', 'rerr-list', 'rerr-clear', 'rerr-x', 'rerr-filters'].forEach((id) => {
  EL[id] = withCls(mkEl(id));
});
const BODY = new Set(['po-chat', 'po-feed', 'po-timeline']);   // fleet pane hidden, like the real default
const WL = {};
global.window = {
  addEventListener: (k, f) => { (WL[k] = WL[k] || []).push(f); },
};
global.document = {
  getElementById: (id) => EL[id] || null,
  createElement: () => withCls(mkEl('')),
  body: { classList: { contains: (c) => BODY.has(c) } },
};
function post(data) { (WL['message'] || []).forEach((f) => f({ data: data })); }
function notes() { return JSON.parse(STORE['romp:notices'] || '[]'); }
"""

DRIVER = r"""
const out = {};
// 1) a VISIBLE pane's drop logs an entry + reddens the bell (no count badge — it clipped, 2026-07-27)
post({ romp: 'wsState', app: 'chat', state: 'down' });
out.afterDrop = { n: notes().length, text: notes()[0].text,
  red: EL['rail-errs']._cls.has('has'), mred: EL['merr']._cls.has('has') };
// 2) up then down again — the SAME error coalesces into one entry with a count (no flood)
post({ romp: 'wsState', app: 'chat', state: 'up' });
post({ romp: 'wsState', app: 'chat', state: 'down' });
out.afterRepeat = { n: notes().length, times: notes()[0].n };
// 3) a HIDDEN pane's drop logs nothing (fleet is toggled off)
post({ romp: 'wsState', app: 'fleet', state: 'down' });
out.afterHidden = { n: notes().length };
// 4) panes can feed the center directly
post({ romp: 'notify', kind: 'warn', text: 'TESTHOST delivery failed' });
out.afterNotify = { n: notes().length };
// 5) opening the popover marks everything seen (red stays while chat is still down). Each row leads
// with the feed's own chip vocabulary: [chip, message, time, clear] — newest entry first.
EL['rail-errs'].fire('click');
out.afterOpen = { open: !EL['rerr-back'].hidden, rows: EL['rerr-list'].children.length,
  red: EL['rail-errs']._cls.has('has'),
  newestChip: EL['rerr-list'].children[0].children[0].textContent,
  newestChipCls: EL['rerr-list'].children[0].children[0].className,
  newestFirst: EL['rerr-list'].children[0].children[1].textContent,
  connChip: EL['rerr-list'].children[1].children[0].textContent };
// 6) per-row clear drops just that entry ([chip, msg, time, del] — del is the 4th cell)
EL['rerr-list'].children[0].children[3].fire('click');
out.afterRowClear = { n: notes().length, rows: EL['rerr-list'].children.length };
// 7) Clear all empties the store and shows the empty state
EL['rerr-clear'].fire('click');
out.afterClearAll = { n: notes().length, rows: EL['rerr-list'].children.length,
  empty: EL['rerr-list'].children[0].textContent };
// 8) once the pane reconnects, the live red cue clears too
post({ romp: 'wsState', app: 'chat', state: 'up' });
out.afterReconnect = { red: EL['rail-errs']._cls.has('has') };
// 9) the filter bar built one toggle chip per kind, in order, conn ("offline") first
out.filterBar = { n: EL['rerr-filters'].children.length,
  first: EL['rerr-filters'].children[0].textContent,
  labels: EL['rerr-filters'].children.map((c) => c.textContent).join('|') };
// 10) muting offline: its entries stop rendering, stop counting, and the live-down cue stays dark
EL['rerr-filters'].children[0].fire('click');
post({ romp: 'wsState', app: 'chat', state: 'down' });
out.afterMute = { stored: STORE['romp:errFilters'], n: notes().length,
  red: EL['rail-errs']._cls.has('has'),
  emptyText: EL['rerr-list'].children[0].textContent };
// 11) unmuting shows what happened while muted, and the unread entry re-reddens the bell
EL['rerr-filters'].children[0].fire('click');
out.afterUnmute = { red: EL['rail-errs']._cls.has('has'), rows: EL['rerr-list'].children.length,
  chip: EL['rerr-list'].children[0].children[0].textContent };
console.log(JSON.stringify(out));
"""


class ErrorCenterExecutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = HARNESS + km._LANDING_ERRS_JS + DRIVER
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        assert r.returncode == 0, "the center's JS threw: " + r.stderr[:800]
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_a_visible_pane_drop_logs_and_reddens_the_bell(self):
        a = self.out["afterDrop"]
        self.assertEqual(a["n"], 1)
        self.assertIn("Chat", a["text"])
        self.assertTrue(a["red"], "the rail bell goes red")
        self.assertTrue(a["mred"], "the mobile bell goes red too")

    def test_a_repeat_of_the_same_error_coalesces(self):
        a = self.out["afterRepeat"]
        self.assertEqual(a["n"], 1, "no flood: the same error is one entry")
        self.assertEqual(a["times"], 2, "with a count")

    def test_a_hidden_panes_drop_logs_nothing(self):
        self.assertEqual(self.out["afterHidden"]["n"], 1)

    def test_panes_can_post_notify(self):
        self.assertEqual(self.out["afterNotify"]["n"], 2)

    def test_opening_marks_seen_but_a_live_problem_keeps_the_cue(self):
        a = self.out["afterOpen"]
        self.assertTrue(a["open"])
        self.assertEqual(a["rows"], 2)
        self.assertTrue(a["red"], "chat is still down → the live cue stays")
        self.assertIn("delivery failed", a["newestFirst"], "newest entry renders first")

    def test_rows_lead_with_the_feeds_chip_vocabulary(self):
        # the user 2026-07-27: a stalled entry should wear the SAME chip the card wears in the feed.
        # The kind maps to the chip label + a k-<kind> colour class mirroring the .fask-* family.
        a = self.out["afterOpen"]
        self.assertEqual(a["newestChip"], "warning")
        self.assertEqual(a["newestChipCls"], "rerr-chip k-warn")
        self.assertEqual(a["connChip"], "offline")

    def test_per_row_clear_and_clear_all(self):
        self.assertEqual(self.out["afterRowClear"]["n"], 1)
        self.assertEqual(self.out["afterRowClear"]["rows"], 1)
        self.assertEqual(self.out["afterClearAll"]["n"], 0)
        self.assertEqual(self.out["afterClearAll"]["rows"], 1)
        self.assertEqual(self.out["afterClearAll"]["empty"], "No errors")

    def test_reconnect_clears_the_live_cue(self):
        self.assertFalse(self.out["afterReconnect"]["red"])

    def test_the_filter_bar_has_one_toggle_per_kind(self):
        # the user 2026-07-28: every high-level category gets a toggle (offline fires so often it
        # drowns the rest). The toggles ARE the chips, in the same order entries wear them.
        a = self.out["filterBar"]
        self.assertEqual(a["n"], 8)
        self.assertEqual(a["first"], "offline")
        self.assertEqual(a["labels"],
                         "offline|limit|judge|warning|stalled|follow-up failed|retrying|api error")

    def test_muting_a_kind_hides_counts_and_live_cue_but_keeps_the_entries(self):
        a = self.out["afterMute"]
        self.assertEqual(a["stored"], '{"conn":1}', "the choice persists")
        self.assertEqual(a["n"], 1, "the entry is still STORED while muted")
        self.assertFalse(a["red"], "a muted kind neither counts unread nor holds the live-down cue")
        self.assertIn("hidden by the filters", a["emptyText"])

    def test_unmuting_shows_what_happened_and_re_reddens(self):
        a = self.out["afterUnmute"]
        self.assertTrue(a["red"], "the entry logged while muted was never seen")
        self.assertEqual(a["rows"], 1)
        self.assertEqual(a["chip"], "offline")


class ErrorCenterWiring(unittest.TestCase):
    def test_the_shell_mounts_bell_popover_and_script(self):
        html = km._landing()
        for pin in ("id=rail-errs", "id=rerr-back", "id=rerr-list", "id=rerr-clear", "id=merr"):
            self.assertIn(pin, html)
        self.assertNotIn("rerr-badge", html)   # the count badge clipped and is gone (the user 2026-07-27)
        self.assertIn("title='Errors — click to open'", html)   # the bell says what it is
        # the panel speaks the shared modal vocabulary (network panel / settings card), never the
        # undefined --vscode-font-family shorthand that rendered oversized in the browser shell
        self.assertIn("font:13px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif}#rerr-panel .rerr-top", html)
        # the chip family mirrors feed.css's .fask-* colours
        self.assertIn(".rerr-chip.k-stalled,.rerr-chip.k-warn{color:#ffd166", html)
        self.assertIn(".rerr-chip.k-nudge{color:#ff6a6a", html)
        # the per-kind filter bar sits between header and list, chips doubling as the toggles
        self.assertIn("id=rerr-filters", html)
        self.assertIn(".rerr-fbtn.off{opacity:0.35;border-style:dashed}", html)
        # timestamps wear the SHARED recency ramp: the standalone dist bundle is loaded BEFORE the
        # errs script and read behind a feature test (dim default if the bundle is stale/missing)
        self.assertLess(html.index("/dist/age-color-global.js"), html.index("window.__rompAgeColor"))
        self.assertIn("if(window.__rompAgeColor)tm.style.color=window.__rompAgeColor(", html)
        self.assertIn("window.__rompNotify=function", html)
        # the mobile bar routes its bell to the same popover
        self.assertIn("errs:function(){try{window.__rompOpenErrs&&window.__rompOpenErrs();}catch(e){}}", html)

    def test_the_old_top_banners_are_gone(self):
        html = km._landing()
        for gone in ("id=romp-offline", "id=romp-limit", "id=romp-judge-degraded"):
            self.assertNotIn(gone, html)


if __name__ == "__main__":
    unittest.main()
