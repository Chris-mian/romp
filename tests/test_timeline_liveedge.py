#!/usr/bin/env python3
"""Live-edge advance of the timeline view (obsidian/romp-timeline-view.js).

The timeline glides its right edge between data polls via interpNow(), then re-anchors the time
baseline onto each poll's data.now. Re-anchoring on EVERY poll snapped the edge by the poll-to-poll
arrival jitter (~tens of ms), which at moderate zoom is a visible ~1-2px hiccup in an otherwise smooth
glide (the user 2026-06-15; worse zoomed in). shouldReanchorEdge() makes the edge FREE-RUN off a fixed
baseline and re-snap only on a genuine step (first poll, re-entering live-follow, or > REANCHOR_SEC of
drift = a tab resume / seek / clock skew), so steady jitter no longer moves the edge.

These exercise the pure exports (interpNow, shouldReanchorEdge) through Node — the same CommonJS the
kernel wraps and serves. Synthetic timings only; no real session data.
"""
import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
VIEW_JS = os.path.join(os.path.dirname(HERE), "obsidian", "romp-timeline-view.js")
NODE = shutil.which("node")

# Pure-JS harness: require the real module, run the cases, print {name: [got, want]} as JSON.
_HARNESS = r"""
const { interpNow, shouldReanchorEdge, badgeFor } = require(process.argv[1]);
const r = {};

// --- badgeFor: a session delegating to a subagent shows the orange SUBAGENT chip (#9) ---
r["badge_subagent_label"] = [badgeFor({live: true, state: "subagent"}).label, "SUBAGENT"];
r["badge_subagent_orange"] = [badgeFor({live: true, state: "subagent"}).bg, "#E67E22"];
r["badge_working_unchanged"] = [badgeFor({live: true, state: "working"}).label, "WORKING"];

// --- shouldReanchorEdge: when the live edge's baseline must snap to a fresh data.now ---
r["first_poll_null_anchor"]   = [shouldReanchorEdge(null, null, 1000, 5.0, true,  false), true];
r["entered_live_follow"]      = [shouldReanchorEdge(5.0, 1000, 1200, 5.2, true,  false), true];
r["held_not_live"]            = [shouldReanchorEdge(5.0, 1000, 1200, 5.2, false, false), true];
// LIVE + steady: small poll-arrival jitter must NOT re-anchor (the fix — no per-poll snap)
r["live_jitter_0_1s"]         = [shouldReanchorEdge(5.0, 1000, 2000, 6.1,      true, true), false];
r["live_drift_under_thresh"]  = [shouldReanchorEdge(5.0, 1000, 2000, 6.0+0.49, true, true), false];
// LIVE + genuine step (tab resume / seek / skew): one corrective snap
r["live_resume_2s"]           = [shouldReanchorEdge(5.0, 1000, 2000, 8.0,      true, true), true];
r["live_drift_over_thresh"]   = [shouldReanchorEdge(5.0, 1000, 2000, 6.0+0.51, true, true), true];

// --- interpNow clamp (glide never runs backward; never flings past maxAheadSec) ---
r["interp_not_live"]          = [interpNow(5, 1000, 9999, false, 30), 5];   // held → raw base
r["interp_clamp_ahead"]       = [interpNow(0, 0, 60000, true, 30), 30];     // 60s elapsed capped at 30
r["interp_never_backward"]    = [interpNow(0, 5000, 1000, true, 30), 0];    // clock hiccup → no rewind

// --- regression: a steady live poll train with realistic arrival jitter must produce ZERO re-anchors
//     (no snaps), while a resume poll injected mid-train produces exactly one. ---
const POLL = 1.0, baseLat = 0.120;                 // 1s polls, 120ms baseline transport latency
const jitter = [0, 0.035, -0.020, 0.050, -0.015, 0.005, 0.040, -0.030, 0.012];  // s, deterministic
let baseSec = 0.0, baseMs = (0 + baseLat) * 1000, wasLive = true, snaps = 0;
for (let k = 1; k < jitter.length; k++) {
  const dataNow = k * POLL;                          // server data.now (perfectly periodic)
  const tMs = (dataNow + baseLat + jitter[k]) * 1000;  // local ms when this poll is processed (jittered)
  if (shouldReanchorEdge(baseSec, baseMs, tMs, dataNow, true, wasLive)) { baseSec = dataNow; baseMs = tMs; snaps++; }
  wasLive = true;
}
r["steady_train_snaps"] = [snaps, 0];
// now a resume: local clock jumped 600s ahead of the baseline (tab was backgrounded) -> exactly one snap
const resumeData = 600.0, resumeMs = (600.0 + baseLat) * 1000;
r["resume_snaps"] = [shouldReanchorEdge(baseSec, baseMs, resumeMs, resumeData, true, true) ? 1 : 0, 1];

process.stdout.write(JSON.stringify(r));
"""


@unittest.skipUnless(NODE, "node not available")
class TimelineLiveEdge(unittest.TestCase):
    def test_live_edge_reanchor(self):
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
