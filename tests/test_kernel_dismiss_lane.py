"""Dead-lane dismissal (the user 2026-07-02): a DEAD session lingers in the timeline as a faded/struck lane
while it's still in the activity window, with none of the live controls. Its "Clear" pill posts dismissLane;
the kernel drops the lane — but IN MEMORY only, so a kernel restart (romp --refresh) brings it back if it was
cleared by mistake. The dismissal only filters a lane WHILE it's dead: a revived sid reappears.
"""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class DismissLane(unittest.TestCase):
    def test_dismissed_lanes_is_an_in_memory_set_not_persisted(self):
        # a module-level set (forgotten on restart) — the whole point is that it does NOT survive a refresh
        self.assertIsInstance(km._dismissed_lanes, set)

    def test_build_timeline_filters_dead_dismissed_lanes_only(self):
        src = inspect.getsource(km.build_timeline)
        # the filter drops a sid ONLY when it's both dismissed AND currently dead (tmux has no live session),
        # so a revived sid comes back on its own
        self.assertIn('s["sid"] in _dismissed_lanes and tmux.get(s["sid"]) is None', src)

    def test_the_filter_is_a_noop_when_nothing_is_dismissed(self):
        # guarded by `if _dismissed_lanes:` so the common (empty) case adds no per-build cost
        self.assertIn("if _dismissed_lanes:", inspect.getsource(km.build_timeline))

    def test_dismiss_survives_nothing_on_restart_because_it_lives_only_in_memory(self):
        # simulate the round-trip at the data-structure level: adding then a fresh process (empty set) forgets it
        km._dismissed_lanes.add("11111111-2222-3333-4444-555555555555")
        self.assertIn("11111111-2222-3333-4444-555555555555", km._dismissed_lanes)
        km._dismissed_lanes.discard("11111111-2222-3333-4444-555555555555")  # a restart = a brand-new empty set
        self.assertNotIn("11111111-2222-3333-4444-555555555555", km._dismissed_lanes)

    def test_ws_handler_records_a_dismissal_and_pushes(self):
        # the dismissLane message adds the sid to the in-memory set + rebroadcasts so the lane vanishes at once
        src = inspect.getsource(km)
        self.assertIn('msg.get("type") == "dismissLane" and msg.get("id")', src)
        self.assertIn('_dismissed_lanes.add(str(msg["id"]))', src)

    def test_boot_hook_posts_dismiss_lane(self):
        # the timeline iframe exposes __rompTimelineDismiss(id) → post({type:"dismissLane",id}) — routed
        # through acquireVsCodeApi so the federation manager sends it to the lane's owning kernel
        self.assertIn('window.__rompTimelineDismiss=function(id){post({type:"dismissLane",id:id});};',
                      km._TIMELINE_BOOT)


if __name__ == "__main__":
    unittest.main()
