"""A boot splash paints with the dashboard shell the instant a reload lands, so the user sees "something's
happening" before the panes connect + parse (the user 2026-06-26: "a delay before anything even shows...
it would be fine to immediately pop up some kind of loading romp dialogue with some moving dots").

It's a full-window centered romp wordmark + pulsing accent-blue dots in the served landing HTML; it fades the
moment ANY pane posts {romp:'ready'} (the timeline lanes render first, no parse), with a 5s backstop so a
slow/closed pane can never trap the user behind it. Pins the shell HTML + the timeline's ready signal.
"""
import os
import pathlib
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class BootSplash(unittest.TestCase):
    def setUp(self):
        self.html = km._landing()

    def test_the_shell_paints_a_centered_romp_splash_with_dots(self):
        self.assertIn("id=romp-boot", self.html, "a full-window boot overlay rides in the shell HTML")
        self.assertIn("rb-dots", self.html, "the moving-dots loading cue")
        self.assertIn("#9cd2ff", self.html, "the romp accent blue (loading-dot use)")
        self.assertIn("@keyframes rb-bnc", self.html, "the dots are animated")
        # the overlay sits before the panes so it covers the whole window from the first paint
        self.assertLess(self.html.index("id=romp-boot"), self.html.index("id=f-chat"))

    def test_the_splash_fades_on_first_content_with_a_backstop(self):
        self.assertIn("romp==='ready'", self.html, "fade the splash when a pane signals first content")
        self.assertIn("classList.add('gone')", self.html)
        self.assertIn("setTimeout(hide,5000)", self.html, "a backstop so it can never trap the user")

    def test_the_timeline_signals_ready_to_the_shell(self):
        tv = (pathlib.Path(BIN).parent / "ui" / "romp-timeline-view.js").read_text()
        self.assertIn("_signalReady()", tv, "the timeline tells the shell it has first content")
        self.assertIn("postMessage({ romp: 'ready' }", tv)
        self.assertIn("this._readySent", tv, "signalled at most once")
        # fired on the main paint AND the empty-state paint (so the splash always clears)
        self.assertEqual(tv.count("this._signalReady()"), 2, "called on both the lanes paint and the empty-state paint")


if __name__ == "__main__":
    unittest.main()
