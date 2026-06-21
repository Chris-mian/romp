#!/usr/bin/env python3
"""Touchscreen pan/zoom on the timeline view (ui/romp-timeline-view.js).

Phones have no wheel events, so onTouchStart/Move/End drive the same continuous _winSec/_offSec state the
trackpad wheel + sliders write. The rules (the user, mobile webview): ONE finger horizontal → PAN (content
tracks the finger; breaks 🔒); ONE finger horizontal while 🔒locked-to-now → ZOOM with the right edge pinned
at now; ONE finger vertical → native lane scroll (we don't touch it); TWO fingers → PINCH-zoom anchored at
the midpoint. A tap (no movement) is left for the lane's own click/select.

These exercise the real prototype methods through Node with a stub view (geometry + a fake svg rect), so the
gesture MATH is covered without a DOM/draw. Synthetic geometry only; no real session data.
"""
import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
VIEW_JS = os.path.join(os.path.dirname(HERE), "ui", "romp-timeline-view.js")
NODE = shutil.which("node")

# A 1000-unit-wide plot mapped 1:1 to client px (rect.width == g.W), no left margin, identity time-compress,
# now=100000. So compressed seconds == client px * (win/plotW) and the arithmetic stays hand-checkable.
_HARNESS = r"""
const { TimelinePanel } = require(process.argv[1]);
global.localStorage = { store: {}, getItem(k){ return (k in this.store) ? this.store[k] : null; },
  setItem(k, v){ this.store[k] = String(v); } };
const r = {};

function makeView(over) {
  const v = Object.create(TimelinePanel.prototype);
  v._geom = { W: 1000, ml: 0, plotW: 1000, compress: (t) => t };
  v.data = { now: 100000, sessions: [{}] };
  v.svg = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 400 }) };
  v._winSec = 3600; v._offSec = 0; v._lockNow = false;
  v._pinned = false; v._offDirty = false; v._touch = null;
  v.WSTORE = 'w'; v.OSTORE = 'o';
  v.draws = 0; v.ticks = 0;
  v._scheduleDraw = function(){ this.draws++; };
  v._startLiveTick = function(){ this.ticks++; };
  Object.assign(v, over || {});
  return v;
}
let _pd = 0;
function ev(touches){ return { touches, preventDefault: () => { _pd++; } }; }
function tch(x, y){ return { clientX: x, clientY: y }; }
const near = (a, b) => Math.abs(a - b) < 1e-6;

// --- Case A: one-finger horizontal drag PANS (unlocked); content tracks the finger ---
{
  const v = makeView();
  v.onTouchStart(ev([tch(500, 200)]));
  v.onTouchMove(ev([tch(600, 200)]));           // dx=+100, dy=0 → axis x, pan
  // dt = 100px * (3600/1000) = 360; drag right → offset increases (earlier time slides in)
  r["pan_offset"]        = [v._offSec, 360];
  r["pan_window_kept"]   = [v._winSec, 3600];   // a pan never rescales the window
  r["pan_unpinned"]      = [v._pinned, false];
}

// --- Case B: one-finger horizontal drag while 🔒locked ZOOMS, right edge stays at now ---
{
  const v = makeView({ _lockNow: true });
  v.onTouchStart(ev([tch(500, 200)]));
  v.onTouchMove(ev([tch(600, 200)]));           // dx=+100 → zoom in (window * e^-0.1)
  r["lock_zoom_offset0"] = [v._offSec, 0];      // pinned at now
  r["lock_zoom_in"]      = [v._winSec < 3600, true];
  r["lock_zoom_value"]   = [near(v._winSec, 3600 * Math.exp(-0.1)), true];
}

// --- Case C: two-finger PINCH zooms, anchored at the midpoint (the time under it stays put) ---
{
  const v = makeView();
  v.onTouchStart(ev([tch(400, 100), tch(600, 100)]));   // midpoint x=500 → frac 0.5, startDist 200
  v.onTouchMove(ev([tch(300, 100), tch(700, 100)]));    // spread to dist 400 → window halves
  r["pinch_window"]      = [v._winSec, 1800];           // 3600 * (200/400)
  r["pinch_offset"]      = [v._offSec, 900];            // anchor at frac 0.5 preserved
}

// --- Case D: one-finger VERTICAL is native lane scroll — we change nothing and don't preventDefault ---
{
  _pd = 0;
  const v = makeView();
  v.onTouchStart(ev([tch(500, 200)]));
  v.onTouchMove(ev([tch(510, 320)]));           // dy=120 ≫ dx=10 → axis y
  r["vert_offset_kept"]  = [v._offSec, 0];
  r["vert_window_kept"]  = [v._winSec, 3600];
  r["vert_not_prevented"]= [_pd, 0];            // left to the browser to scroll
}

// --- Case E: a tap (down→up, no move) persists nothing — the lane's own click/select handles it ---
{
  const v = makeView();
  v.onTouchStart(ev([tch(500, 200)]));
  v.onTouchEnd({ touches: [], preventDefault: () => {} });
  r["tap_no_persist"]    = [localStorage.getItem('o'), null];
  r["tap_no_draw"]       = [v.draws, 0];
}

// --- Case F: a real pan, on release, persists the offset + re-arms live-follow ---
{
  localStorage.store = {};
  const v = makeView();
  v.onTouchStart(ev([tch(500, 200)]));
  v.onTouchMove(ev([tch(450, 200)]));           // dx=-50 → offset = -180 → clamped to 0 (back at now)
  v.onTouchEnd({ touches: [], preventDefault: () => {} });
  r["pan_back_to_now"]   = [v._offSec, 0];
  r["pan_persisted"]     = [localStorage.getItem('o'), "0"];
  r["pan_relit_tick"]    = [v.ticks >= 1, true];
}

process.stdout.write(JSON.stringify(r));
"""


@unittest.skipUnless(NODE, "node not available")
class TimelineTouch(unittest.TestCase):
    def test_touch_pan_zoom(self):
        out = subprocess.run(
            [NODE, "-e", _HARNESS, VIEW_JS],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(out.returncode, 0, f"node harness failed:\n{out.stderr}")
        results = json.loads(out.stdout)
        for name, (got, want) in results.items():
            self.assertEqual(got, want, f"{name}: got {got!r}, want {want!r}")


if __name__ == "__main__":
    unittest.main()
