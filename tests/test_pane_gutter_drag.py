#!/usr/bin/env python3
"""A pane divider drag resizes the pair LIVE, one layout per animation frame; the store is written once, at release.

The dashboard's chat | Outline | feed panes are sized by flex-grow weights the gutter script (_LANDING_JS in
kernel/kernel.py) writes as --g-* variables on .row. Each write re-lays out the row, and with it every same-origin pane
document in that frame; writing the pair on every mousemove (before 2026-09-08) cost one relayout per pointer step, so
the drag deferred to a landing line (#gv-ghost) and the panes took their widths at release. Since plans/pane-docking.md
section 12 (the user 2026-09-20: what they see while dragging is what they get) the drag is live again, BOUNDED: a move
records the pointer and arms one animation frame; the frame writes the pair's two grows for the latest position, so a
burst of moves costs one relayout and a frame without a move nothing; the store is written once, at release; Escape
restores the grab-time widths live and writes nothing; there is no landing line.

This EXECUTES the real _LANDING_JS in node against a DOM stub (the test_error_center.py pattern; a source pin cannot
show what a handler writes) whose requestAnimationFrame queues callbacks the driver runs with frame(): the grab
normalises the shown panes' grows to their widths; a move writes nothing until the frame, then exactly the pair's two
grows; two moves before a frame coalesce to one write of the latest; the release writes the store once and removes the
listeners; Escape restores and writes nothing; a far drag clamps live at the pair's minimum, min(120 px, a quarter of
the pair); the Outline pane shown places the pair by its own widths; the Files gutter pairs the Files pane with the
rightmost shown column to its left."""
import json
import os
import subprocess
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads: they resolve their state root at import time, and only pytest runs
# conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_gutter_drag", os.path.join(BIN, "romp-kernel"))

# Everything _LANDING_JS touches, and nothing else: .col (the timeline band's --tl var, never driven here),
# .row (records every --g-* write, in order), the gutters and panes by id with offsetWidth and a client rect,
# getComputedStyle(el).display for shown(), body.classList (po-* reads, drag/dragv writes), localStorage (the grow store's
# writes counted), a requestAnimationFrame queue the driver drains with frame(), and the window's mousemove/mouseup/keydown
# listeners a drag installs and removes. f-timeline is present (the served shell always carries the iframe) so the 'load'
# hookup runs; the event is never fired.
HARNESS = r"""
'use strict';
const STORE = {}; let STORE_WRITES = 0;   // every write of the grow store, counted: the release writes once
global.localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); if (k === 'romp-pane-grow') STORE_WRITES++; },
  removeItem: (k) => { delete STORE[k]; },
};
// the browser's animation frames, as a queue the driver drains with frame(): a move arms ONE callback, the frame runs it
const FRAMES = []; let FRAME_IDS = 0;
function frame() { const fs = FRAMES.splice(0); fs.forEach((f) => f.cb()); return fs.length; }
const WRITES = [];   // every --g-* write on .row, in order: [name, value]
const ROW = {};      // the current --g-* values (the script's `grow` object is a closure)
const rowEl = {
  style: { setProperty: (k, v) => { ROW[k] = v; WRITES.push([k, v]); }, removeProperty: (k) => { delete ROW[k]; } },
};   // gutter() reads no rect: the pair's widths are offsetWidth (the landing line that read rects retired, plans/pane-docking.md section 12)
// the column: the band's --tl height variable, as the band gutter (#gh) reads and writes it (getPropertyValue at the grab, a
// setter per applied frame, the remover on Escape from a band with no inline height); every write recorded
const COL = { tl: '' }; const TL_WRITES = [];   // [op, value]
const colEl = {
  style: { getPropertyValue: (k) => (k === '--tl' ? COL.tl : ''), setProperty: (k, v) => { if (k === '--tl') { COL.tl = v; TL_WRITES.push(['set', v]); } },
           removeProperty: (k) => { if (k === '--tl') { COL.tl = ''; TL_WRITES.push(['remove', null]); } } },
  getBoundingClientRect: () => ({ bottom: 800 }),
};
function mkEl(id, w, left, display) {
  return {
    id: id, offsetWidth: w, _left: left, _display: display, _ls: {},
    style: {},
    addEventListener(k, f) { (this._ls[k] = this._ls[k] || []).push(f); },
    fire(k, ev) { (this._ls[k] || []).slice().forEach((f) => f(ev)); },
  };
}
const EL = {};
['gh', 'gv-a', 'gv-b', 'gv-c', 'f-timeline'].forEach((id) => { EL[id] = mkEl(id, 7, 0, 'flex'); });
// chat 600 px at the left edge, the Outline pane hidden (so gv-b is the chat | feed gutter), feed 400 px
// after the 7 px gutter: the divider sits at x = 600; the Files pane hidden until the last drags
EL['chat-pane'] = mkEl('chat-pane', 600, 0, 'flex');
EL['fleet-pane'] = mkEl('fleet-pane', 300, 0, 'none');
EL['feed-pane'] = mkEl('feed-pane', 400, 607, 'flex');
EL['files-pane'] = mkEl('files-pane', 300, 0, 'none');
const WL = {};
global.window = {
  innerHeight: 900,
  addEventListener: (k, f) => { (WL[k] = WL[k] || []).push(f); },
  removeEventListener: (k, f) => { WL[k] = (WL[k] || []).filter((g) => g !== f); },
  requestAnimationFrame: (cb) => { const id = ++FRAME_IDS; FRAMES.push({ id, cb }); return id; },
  cancelAnimationFrame: (id) => { const i = FRAMES.findIndex((f) => f.id === id); if (i >= 0) FRAMES.splice(i, 1); },
};
global.getComputedStyle = (el) => ({ display: el._display });
const BODY = new Set(['po-chat', 'po-feed', 'po-timeline']);
global.document = {
  querySelector: (sel) => (sel === '.col' ? colEl : sel === '.row' ? rowEl : null),
  getElementById: (id) => EL[id] || null,
  body: { classList: {
    contains: (c) => BODY.has(c),
    add: (...cs) => cs.forEach((c) => BODY.add(c)),
    remove: (...cs) => cs.forEach((c) => BODY.delete(c)),
  } },
};
function winFire(k, ev) { (WL[k] || []).slice().forEach((f) => f(ev)); }
function snap() {
  return {
    writes: WRITES.length,
    grows: Object.assign({}, ROW),
    drag: BODY.has('drag'), dragv: BODY.has('dragv'),
    listeners: { move: (WL['mousemove'] || []).length, up: (WL['mouseup'] || []).length, esc: (WL['keydown'] || []).length },
    framesArmed: FRAMES.length,
    store: JSON.parse(STORE['romp-pane-grow'] || 'null'), storeWrites: STORE_WRITES,
    tl: COL.tl, tlWrites: TL_WRITES.length,
  };
}
// the browser lays the panes out from the written grows; the stub has no layout engine, so it is told the
// shown panes' widths, left to right, and places each after the one before it plus the 7 px gutter
function layout(widths) {
  let x = 0;
  [['chat', 'chat-pane'], ['fleet', 'fleet-pane'], ['feed', 'feed-pane'], ['files', 'files-pane']].forEach(([k, id]) => {
    if (!(k in widths)) return;
    EL[id].offsetWidth = widths[k]; EL[id]._left = x; x += widths[k] + 7;
  });
}
"""

DRIVER = r"""
const out = {};
out.boot = snap();
// 1) grab gv-b at the divider, move the pointer 100 px left: nothing until the frame; the frame writes the pair; release persists once
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 600 });
out.grab = snap();
winFire('mousemove', { clientX: 500 });
out.moveBeforeFrame = snap();
out.framesRun = frame();
out.move = snap();
out.moveWrites = WRITES.slice(out.moveBeforeFrame.writes);
winFire('mouseup', {});
out.release = snap();
out.releaseWrites = WRITES.slice(out.move.writes);
layout({ chat: 500, feed: 500 });
// 2) a second grab at the new divider: two moves before a frame coalesce to one write of the latest; then dragged far past the
//    right edge: the clamp holds the pair's minimum live
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 500 });
out.grab2 = snap();
winFire('mousemove', { clientX: 540 });
winFire('mousemove', { clientX: 560 });
out.twoMovesArmed = snap();
out.frames2 = frame();
out.coalesced = snap();
out.coalescedWrites = WRITES.slice(out.twoMovesArmed.writes);
winFire('mousemove', { clientX: 1590 });
frame();
out.move2 = snap();
winFire('mouseup', {});
out.release2 = snap();
out.release2Writes = WRITES.slice(out.move2.writes);
layout({ chat: 880, feed: 120 });
// 3) Escape mid-drag: the grab-time widths come back live and nothing is written to the store
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 880 });
out.grab3 = snap();
winFire('mousemove', { clientX: 700 });
frame();
out.move3 = snap();
winFire('keydown', { key: 'Escape', preventDefault() {}, stopPropagation() {} });
out.escaped = snap();
out.escapeWrites = WRITES.slice(out.move3.writes);
frame();
out.afterEscapeFrame = snap();
// 3b) the release lands in the SAME frame as the last move (no frame between): the release itself applies the last recorded
//     position, cancels the armed frame, and persists once; a frame afterwards writes nothing
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 880 });
winFire('mousemove', { clientX: 800 });
out.sameFrameMoved = snap();
winFire('mouseup', {});
out.sameFrameReleased = snap();
out.sameFrameReleaseWrites = WRITES.slice(out.sameFrameMoved.writes);
out.sameFrameLaterFrame = frame();
out.sameFrameAfterFrame = snap();
layout({ chat: 880, feed: 120 });   // back to the widths the later steps assume (the stub has no layout engine)
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 800 }); winFire('mousemove', { clientX: 880 }); frame(); winFire('mouseup', {});
out.relaid = snap();
// 4) a grab whose right pane is gone from the document
const feed = EL['feed-pane'];
delete EL['feed-pane'];
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 880 });
out.orphan = snap();
EL['feed-pane'] = feed;
// 5) the Outline pane shown, so gv-b is the Outline | feed gutter (its left pane at client left 307: chat 300 plus the gutter),
//    and a narrow pair (200 | 200) whose minimum is a quarter of it, 100
BODY.add('po-fleet');
EL['fleet-pane']._display = 'flex';
layout({ chat: 300, fleet: 200, feed: 200 });
EL['gv-b'].fire('mousedown', { preventDefault() {}, clientX: 507 });
out.grab5 = snap();
winFire('mousemove', { clientX: 457 });
frame();
out.move5 = snap();
out.move5Writes = WRITES.slice(out.grab5.writes);
winFire('mousemove', { clientX: 350 });
frame();
out.move5far = snap();
winFire('mouseup', {});
out.release5 = snap();
out.release5Writes = WRITES.slice(out.move5far.writes);
// 6) the Files pane shown: gv-c's left pane is the rightmost SHOWN of feed, the Outline and chat. All four shown first
//    (chat 300 | Outline 100 | feed 300 | files 200, the divider at 714), then the feed hidden (chat 300 | Outline 250 |
//    files 250, the divider at 557), then the Outline hidden too (chat 500 | files 300, the divider at 500); each drag moves
//    the pointer 50 px left of the divider and releases
BODY.add('po-files');
EL['files-pane']._display = 'flex';
layout({ chat: 300, fleet: 100, feed: 300, files: 200 });
EL['gv-c'].fire('mousedown', { preventDefault() {}, clientX: 714 });
out.grab6 = snap();
winFire('mousemove', { clientX: 664 }); frame();
winFire('mouseup', {});
out.release6Writes = WRITES.slice(out.grab6.writes);
BODY.delete('po-feed');
EL['feed-pane']._display = 'none';
layout({ chat: 300, fleet: 250, files: 250 });
EL['gv-c'].fire('mousedown', { preventDefault() {}, clientX: 557 });
out.grab7 = snap();
winFire('mousemove', { clientX: 507 }); frame();
winFire('mouseup', {});
out.release7Writes = WRITES.slice(out.grab7.writes);
BODY.delete('po-fleet');
EL['fleet-pane']._display = 'none';
layout({ chat: 500, files: 300 });
EL['gv-c'].fire('mousedown', { preventDefault() {}, clientX: 500 });
out.grab8 = snap();
winFire('mousemove', { clientX: 450 }); frame();
winFire('mouseup', {});
out.release8Writes = WRITES.slice(out.grab8.writes);
out.release8 = snap();
// 9) the BAND's gutter (#gh, the --tl height variable; the column's bottom at 800, the pointer's distance from it is the
//    height, floored at 48 and capped): a release with the frame still armed lands the height itself and cancels the frame;
//    Escape with a frame armed cancels it and writes the grab-time height back; a band with NO inline height at the grab
//    has the variable REMOVED on Escape (the else branch)
EL['gh'].fire('mousedown', { preventDefault() {}, clientY: 500 });
out.bandGrab = snap();
winFire('mousemove', { clientY: 700 });
out.bandMoved = snap();
winFire('mouseup', {});
out.bandFrameless = snap();
out.bandFramelessLater = frame();
out.bandAfterLater = snap();
EL['gh'].fire('mousedown', { preventDefault() {}, clientY: 700 });
winFire('mousemove', { clientY: 600 });
out.bandMoved2 = snap();
winFire('keydown', { key: 'Escape', preventDefault() {}, stopPropagation() {} });
out.bandEscaped = snap();
out.bandEscapedLater = frame();
COL.tl = '';   // no inline height (a fresh dashboard's band is content-sized by autosize alone)
EL['gh'].fire('mousedown', { preventDefault() {}, clientY: 700 });
winFire('mousemove', { clientY: 650 });
frame();
out.bandNoTlMoved = snap();
winFire('keydown', { key: 'Escape', preventDefault() {}, stopPropagation() {} });
out.bandNoTlEscaped = snap();
out.tlWrites = TL_WRITES.slice();
console.log(JSON.stringify(out));
"""


class PaneGutterDragExecutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = HARNESS + km._LANDING_JS + DRIVER
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        assert r.returncode == 0, "the gutter script threw: " + r.stderr[:800]
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_boot_writes_the_four_default_grows_and_arms_nothing(self):
        b = self.out["boot"]
        self.assertEqual(b["writes"], 4)   # the four default grows of the hand-written columns (the generic panes come from body[data-panes])
        self.assertEqual(b["grows"], {"--g-chat": 60, "--g-fleet": 34, "--g-feed": 40, "--g-files": 40})
        self.assertFalse(b["drag"] or b["dragv"])
        self.assertEqual(b["listeners"], {"move": 0, "up": 0, "esc": 0}, "no drag listeners before a grab")
        self.assertEqual((b["framesArmed"], b["storeWrites"]), (0, 0))

    def test_the_grab_normalises_the_shown_panes_and_installs_the_drag(self):
        g = self.out["grab"]
        # the two shown panes are written as their px widths (the hidden Outline pane keeps its grow)
        self.assertEqual(g["writes"], self.out["boot"]["writes"] + 2)
        self.assertEqual(g["grows"], {"--g-chat": 600, "--g-fleet": 34, "--g-feed": 400, "--g-files": 40})
        self.assertTrue(g["drag"] and g["dragv"], "body.drag and body.dragv during the drag: the iframes pointer-transparent")
        self.assertEqual(g["listeners"], {"move": 1, "up": 1, "esc": 1}, "move, release and Escape")
        self.assertEqual(g["framesArmed"], 0, "nothing armed until a move")

    def test_a_move_arms_one_frame_and_the_frame_writes_the_pair_live(self):
        g, b, m = self.out["grab"], self.out["moveBeforeFrame"], self.out["move"]
        self.assertEqual(b["writes"], g["writes"], "a move writes nothing itself")
        self.assertEqual(b["framesArmed"], 1, "one animation frame armed")
        self.assertEqual(self.out["framesRun"], 1)
        self.assertEqual(self.out["moveWrites"], [["--g-chat", 500], ["--g-feed", 500]], "the frame writes exactly the pair's two grows for the pointer's position: the panes resize LIVE")
        self.assertEqual(m["grows"], {"--g-chat": 500, "--g-fleet": 34, "--g-feed": 500, "--g-files": 40})
        self.assertEqual(m["storeWrites"], 0, "the store is not written per frame")
        self.assertTrue(m["drag"] and m["dragv"])

    def test_the_release_writes_the_store_once_and_removes_the_listeners(self):
        m, r = self.out["move"], self.out["release"]
        self.assertEqual(self.out["releaseWrites"], [], "the frame already applied the pair: the release writes no grow of its own")
        self.assertEqual(r["grows"], m["grows"])
        self.assertEqual(r["storeWrites"], 1, "the grows persist once, at release")
        self.assertEqual(r["store"], {"chat": 500, "fleet": 34, "feed": 500, "files": 40})
        self.assertFalse(r["drag"] or r["dragv"], "body.drag and body.dragv are removed")
        self.assertEqual(r["listeners"], {"move": 0, "up": 0, "esc": 0}, "the drag's window listeners are removed")
        self.assertEqual(r["framesArmed"], 0)

    def test_two_moves_before_a_frame_coalesce_to_one_write_of_the_latest_and_a_far_drag_clamps_live(self):
        # chat 500 | feed 500: two moves arm ONE frame, which writes the latest position (560); then the pointer at 1590
        # (asking for chat 1590) lands the divider at 880: the pair's minimum is min(120, 1000 * 0.25) = 120
        g2, t, c, m2, r2 = self.out["grab2"], self.out["twoMovesArmed"], self.out["coalesced"], self.out["move2"], self.out["release2"]
        self.assertEqual(g2["grows"], {"--g-chat": 500, "--g-fleet": 34, "--g-feed": 500, "--g-files": 40})
        self.assertEqual(t["framesArmed"], 1, "a second move before the frame arms nothing more")
        self.assertEqual(t["writes"], g2["writes"], "and writes nothing")
        self.assertEqual(self.out["frames2"], 1)
        self.assertEqual(self.out["coalescedWrites"], [["--g-chat", 560], ["--g-feed", 440]], "one write of the latest position")
        self.assertEqual(m2["grows"], {"--g-chat": 880, "--g-fleet": 34, "--g-feed": 120, "--g-files": 40}, "the clamp holds live")
        self.assertEqual(self.out["release2Writes"], [])
        self.assertEqual(r2["store"], {"chat": 880, "fleet": 34, "feed": 120, "files": 40})
        self.assertEqual(r2["storeWrites"], 2, "one write per release")

    def test_escape_restores_the_grab_widths_live_and_writes_nothing(self):
        g3, m3, e, a = self.out["grab3"], self.out["move3"], self.out["escaped"], self.out["afterEscapeFrame"]
        self.assertEqual(m3["grows"], {"--g-chat": 700, "--g-fleet": 34, "--g-feed": 300, "--g-files": 40}, "the drag moved the pair")
        self.assertEqual(self.out["escapeWrites"], [["--g-chat", 880], ["--g-feed", 120]], "Escape writes the grab-time widths back, live")
        self.assertEqual(e["grows"], g3["grows"])
        self.assertEqual(e["storeWrites"], m3["storeWrites"], "nothing persisted")
        self.assertFalse(e["drag"] or e["dragv"]); self.assertEqual(e["listeners"], {"move": 0, "up": 0, "esc": 0}, "the drag is over")
        self.assertEqual(e["framesArmed"], 0, "an armed frame is cancelled")
        self.assertEqual(a["grows"], e["grows"], "a later frame changes nothing")

    def test_a_release_in_the_same_frame_as_the_last_move_lands_that_position_and_persists_once(self):
        # chat 880 | feed 120 (the layout after Escape), the pointer 80 px left with no frame between the move and the release:
        # the frame is armed and has not run when the button comes up
        m, r, a = self.out["sameFrameMoved"], self.out["sameFrameReleased"], self.out["sameFrameAfterFrame"]
        self.assertEqual(m["framesArmed"], 1, "the move armed a frame that has not run")
        self.assertEqual(m["grows"]["--g-chat"], 880, "and wrote nothing itself")
        self.assertEqual(self.out["sameFrameReleaseWrites"], [["--g-chat", 800], ["--g-feed", 200]], "the release applies the last recorded position itself: what was under the pointer is what lands")
        self.assertEqual(r["framesArmed"], 0, "the armed frame is cancelled at the release, on this path too")
        self.assertEqual(r["storeWrites"], m["storeWrites"] + 1, "and the store is written once")
        self.assertEqual(r["store"], {"chat": 800, "fleet": 34, "feed": 200, "files": 40})
        self.assertEqual(r["listeners"], {"move": 0, "up": 0, "esc": 0})
        self.assertEqual(self.out["sameFrameLaterFrame"], 0, "no frame left to run")
        self.assertEqual(a["writes"], r["writes"], "a later frame writes nothing")

    def test_the_bands_gutter_lands_a_frameless_release_itself_and_escape_restores_or_removes_the_height(self):
        # the band's divider (#gh) sizes --tl live per frame like the column gutters: a release with the frame armed writes
        # the height once and cancels the frame; Escape with a frame armed cancels it and writes the grab-time height back;
        # from a band with no inline height, Escape REMOVES the variable (the else branch, reached by nothing before)
        g, m, r, a = self.out["bandGrab"], self.out["bandMoved"], self.out["bandFrameless"], self.out["bandAfterLater"]
        self.assertTrue(g["drag"], "body.drag for the band's drag too")
        self.assertEqual(m["framesArmed"], 1, "the move armed a frame and wrote nothing"); self.assertEqual(m["tlWrites"], g["tlWrites"])
        self.assertEqual(r["tl"], "100px", "the release landed the pointer's height (800 - 700) itself: %r" % r)
        self.assertEqual(r["tlWrites"], g["tlWrites"] + 1, "one height write, at the release")
        self.assertEqual(r["framesArmed"], 0, "the armed frame was cancelled"); self.assertEqual(self.out["bandFramelessLater"], 0)
        self.assertEqual(a["tlWrites"], r["tlWrites"], "a later frame writes nothing")
        self.assertFalse(r["drag"] or r["dragv"], "the drag classes are gone")
        m2, e = self.out["bandMoved2"], self.out["bandEscaped"]
        self.assertEqual(m2["framesArmed"], 1)
        self.assertEqual(e["tl"], "100px", "Escape writes the grab-time height back: %r" % e)
        self.assertEqual(e["tlWrites"], m2["tlWrites"] + 1, "one write, the restore")
        self.assertEqual(e["framesArmed"], 0, "the armed frame was cancelled"); self.assertEqual(self.out["bandEscapedLater"], 0)
        self.assertEqual(e["listeners"], {"move": 0, "up": 0, "esc": 0})
        n, ne = self.out["bandNoTlMoved"], self.out["bandNoTlEscaped"]
        self.assertEqual(n["tl"], "150px", "the frame wrote the height (800 - 650)")
        self.assertEqual(ne["tl"], "", "Escape from a band with no inline height REMOVES the variable")
        self.assertEqual(self.out["tlWrites"][-1], ["remove", None], "through the remover: %r" % self.out["tlWrites"][-3:])
        self.assertEqual(ne["storeWrites"], n["storeWrites"], "the band persists nothing")

    def test_a_grab_whose_pane_is_gone_arms_nothing(self):
        # the pair is resolved before anything else happens: no drag classes to leave the col-resize cursor stuck, no
        # normalisation writes, no window listeners
        e, o = self.out["relaid"], self.out["orphan"]
        self.assertEqual(o["writes"], e["writes"], "a grab with a missing pane writes nothing")
        self.assertFalse(o["drag"] or o["dragv"], "no drag class is left on the body")
        self.assertEqual(o["listeners"], {"move": 0, "up": 0, "esc": 0})
        self.assertEqual(o["grows"], e["grows"])

    def test_with_the_outline_pane_shown_the_pair_is_the_outline_and_the_feed_and_a_narrow_pair_clamps_at_a_quarter(self):
        # gv-b's left pane is now the Outline pane (at client left 307: chat 300 and a 7 px gutter); the drag moves the
        # Outline | feed pair by its own widths, the chat untouched; Outline 200 | feed 200: min(120, 400 * 0.25) = 100, so
        # the pointer at 350 (asking for Outline 43) clamps the Outline at 100
        o, g5, m5, m5f, r5 = self.out["orphan"], self.out["grab5"], self.out["move5"], self.out["move5far"], self.out["release5"]
        self.assertEqual(g5["writes"], o["writes"] + 3, "all three shown panes are normalised")
        self.assertEqual(g5["grows"], {"--g-chat": 300, "--g-fleet": 200, "--g-feed": 200, "--g-files": 40})
        self.assertEqual(self.out["move5Writes"], [["--g-fleet", 150], ["--g-feed", 250]], "the pointer 50 px left: the Outline gives 50 to the feed, live")
        self.assertEqual(m5f["grows"], {"--g-chat": 300, "--g-fleet": 100, "--g-feed": 300, "--g-files": 40}, "the clamp at a quarter of the pair, live; the chat grow untouched")
        self.assertEqual(self.out["release5Writes"], [])
        self.assertEqual(r5["store"], {"chat": 300, "fleet": 100, "feed": 300, "files": 40})
        self.assertFalse(r5["drag"] or r5["dragv"])
        self.assertEqual(r5["listeners"], {"move": 0, "up": 0, "esc": 0})

    def test_the_files_gutter_pairs_the_files_pane_with_the_rightmost_shown_column_to_its_left(self):
        # every shown pane is normalised at the grab (four, then three, then two), and the drag moves the PAIR the gutter
        # resolved by what is shown at grab time: feed | files, then Outline | files, then chat | files
        r5, g6, g7, g8, r8 = self.out["release5"], self.out["grab6"], self.out["grab7"], self.out["grab8"], self.out["release8"]
        self.assertEqual(g6["writes"], r5["writes"] + 4, "all four shown panes are normalised")
        self.assertEqual(g6["grows"], {"--g-chat": 300, "--g-fleet": 100, "--g-feed": 300, "--g-files": 200})
        self.assertEqual(self.out["release6Writes"], [["--g-feed", 250], ["--g-files", 250]], "the feed is the left pane while it is shown")
        self.assertEqual(g7["grows"], {"--g-chat": 300, "--g-fleet": 250, "--g-feed": 250, "--g-files": 250}, "the hidden feed keeps its grow")
        self.assertEqual(self.out["release7Writes"], [["--g-fleet", 200], ["--g-files", 300]], "feed hidden: the Outline is the left pane")
        self.assertEqual(self.out["release8Writes"], [["--g-chat", 450], ["--g-files", 350]], "feed and Outline hidden: the chat is")
        self.assertEqual(r8["store"], {"chat": 450, "fleet": 200, "feed": 250, "files": 350}, "the grows persist at release")
        self.assertFalse(r8["drag"] or r8["dragv"])
        self.assertEqual(r8["listeners"], {"move": 0, "up": 0, "esc": 0})


if __name__ == "__main__":
    unittest.main()
