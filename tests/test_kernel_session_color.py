"""Per-session identity color override (the user 2026-06-29) + the selectable palette (the user
2026-07-12): a right-click tab menu picks a color from the ACTIVE identity palette; the kernel persists
it to the names registry (bg + fg word, preserving name + cwd) and re-broadcasts. The gear's Session
colors picker switches the whole SET (STATE/palette): the kernel remaps every stored color to the same
slot in the new set, rewrites the shell launcher's STATE/palette-colors mirror, and pushes. SYNTHETIC
fixtures only (placeholder uuids, invented paths)."""
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
SID2 = "22222222-3333-4444-5555-666666666666"


class SessionColor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.names = Path(self.tmp) / "names"
        self.names.mkdir()
        self._orig = km.NAMES
        km.NAMES = self.names
        self._state = km.jd.STATE
        km.jd.STATE = Path(self.tmp) / "state"      # _set_palette persists STATE/palette + the shell mirror
        km._pal_cache.update({"name": km.pal.DEFAULT, "mt": None})   # drop the mtime cache between sandboxes

    def tearDown(self):
        km.NAMES = self._orig
        km.jd.STATE = self._state
        km._pal_cache.update({"name": km.pal.DEFAULT, "mt": None})

    def test_active_palette_has_nine_colors_and_a_fg_word_each(self):
        # the SAME set the tmux launcher / SDK backend assign from — romp_palette is the single source
        self.assertEqual(len(km.pal.colors(km._palette_name())), 9)
        self.assertEqual(len(km.pal.fgs(km._palette_name())), 9)
        self.assertIn("#1EA1EB", km.pal.colors(km._palette_name()))

    def test_set_color_rewrites_bg_and_fg_preserving_name_and_cwd(self):
        (self.names / SID).write_text("mysess\t/proj/TESTHOST/app\t#1EA1EB\twhite\n")
        self.assertTrue(km._set_session_color(SID, "#54B204"))
        parts = (self.names / SID).read_text().rstrip("\n").split("\t")
        self.assertEqual(parts[0], "mysess", "name preserved")
        self.assertEqual(parts[1], "/proj/TESTHOST/app", "cwd preserved")
        self.assertEqual(parts[2], "#54B204", "new bg written")
        self.assertEqual(parts[3], "black", "the palette's fg word for green")
        # _name_color reads it back (fg is always white on the dashboard)
        self.assertEqual(km._name_color(SID), {"bg": "#54B204", "fg": "#ffffff"})

    def test_set_color_accepts_a_swatch_from_any_known_palette(self):
        # a right-click menu rendered just before a palette switch still lands its click — the value
        # is validated against EVERY set, and the owning set supplies the fg word
        (self.names / SID).write_text("s\t/d\t#1EA1EB\twhite\n")
        phase0 = km.pal.PALETTES["phase"]["bg"][0]
        self.assertTrue(km._set_session_color(SID, phase0))
        parts = (self.names / SID).read_text().rstrip("\n").split("\t")
        self.assertEqual(parts[2], phase0)
        self.assertEqual(parts[3], km.pal.PALETTES["phase"]["fg"][0])

    def test_rejects_a_color_outside_every_palette(self):
        (self.names / SID).write_text("s\t/d\t#1EA1EB\twhite\n")
        self.assertFalse(km._set_session_color(SID, "#abcdef"))
        self.assertEqual((self.names / SID).read_text().split("\t")[2], "#1EA1EB", "unchanged")

    def test_missing_names_file_is_a_safe_noop(self):
        self.assertFalse(km._set_session_color("00000000-0000-0000-0000-000000000000", "#1EA1EB"))

    def test_set_palette_remaps_the_fleet_slot_for_slot(self):
        # sessions on romp slots 0 and 3, plus one color no palette owns (must be left alone)
        (self.names / SID).write_text("a\t/d\t#1EA1EB\twhite\n")
        (self.names / SID2).write_text("b\t/d\t#DD42FF\twhite\n")
        (self.names / "custom").write_text("c\t/d\t#ABCDEF\twhite\n")
        self.assertTrue(km._set_palette("phase"))
        pb, pf = km.pal.PALETTES["phase"]["bg"], km.pal.PALETTES["phase"]["fg"]
        self.assertEqual((self.names / SID).read_text().rstrip("\n").split("\t")[2:], [pb[0], pf[0]])
        self.assertEqual((self.names / SID2).read_text().rstrip("\n").split("\t")[2:], [pb[3], pf[3]])
        self.assertEqual((self.names / "custom").read_text().rstrip("\n").split("\t")[2],
                         "#ABCDEF", "an unowned color is not remapped")
        self.assertEqual((km.jd.STATE / "palette").read_text(), "phase", "the choice persists")
        self.assertEqual(km._palette_name(), "phase")
        # the shell launcher's mirror carries the ACTIVE set (bg<TAB>fg per line)
        lines = (km.jd.STATE / "palette-colors").read_text().rstrip("\n").split("\n")
        self.assertEqual([ln.split("\t") for ln in lines], [[b, f] for b, f in zip(pb, pf)])

    def test_set_palette_round_trip_restores_original_colors(self):
        (self.names / SID).write_text("a\t/d\t#4EA8A9\twhite\n")   # romp slot 2
        self.assertTrue(km._set_palette("romaO"))
        self.assertEqual((self.names / SID).read_text().split("\t")[2],
                         km.pal.PALETTES["romaO"]["bg"][2])
        self.assertTrue(km._set_palette("romp"))
        self.assertEqual((self.names / SID).read_text().split("\t")[2], "#4EA8A9",
                         "slot identity survives a switch there and back")

    def test_set_palette_rejects_an_unknown_name(self):
        (self.names / SID).write_text("a\t/d\t#1EA1EB\twhite\n")
        self.assertFalse(km._set_palette("neon-vaporwave"))
        self.assertEqual(km._palette_name(), "romp")
        self.assertEqual((self.names / SID).read_text().split("\t")[2], "#1EA1EB")

    def test_get_serves_palette_choices_and_ws_handles_the_pick(self):
        # /palette serves the ACTIVE swatches + every choosable set + the active name (the gear's picker
        # and the tab menu both read it — the client holds no color literals)
        get_src = inspect.getsource(km.Handler.do_GET)
        self.assertIn('p == "/palette"', get_src)
        self.assertIn('"palettes":', get_src)
        self.assertIn('"active":', get_src)
        # the WS branches: setSessionColor recolors one session; setPalette switches the set
        ksrc = Path(BIN, "romp-kernel").read_text()
        self.assertIn('msg.get("type") == "setSessionColor"', ksrc)
        self.assertIn("_set_session_color(str(msg[\"id\"]), str(msg[\"bg\"]))", ksrc)
        self.assertIn('msg.get("type") == "setPalette"', ksrc)
        self.assertIn('_set_palette(str(msg["name"]))', ksrc)

    def test_set_palette_rebroadcasts_and_boot_heals_the_mirror(self):
        src = inspect.getsource(km._set_palette)
        self.assertIn('_send_to_app("chat", {"type": "palette"', src, "open tab menus get fresh swatches")
        self.assertIn("_mark_views_dirty()", src, "tabs/cards/lanes repaint in the new colors")
        self.assertIn("_write_palette_mirror()", inspect.getsource(km.main),
                      "boot rewrites the shell mirror so bin/romp can never assign from a stale set")

    def test_gear_offers_the_session_colors_picker(self):
        html = _gear_src()
        self.assertIn(">Session colors<", html)
        self.assertIn("id=rs-pal-btn", html)
        self.assertIn("id=rs-pal-list", html)
        self.assertIn("{ type: 'setPalette', name: name }", _gear_src())
        self.assertIn("plFill(); fill(); }", _gear_src(),
                      "gear open re-reads the server-authoritative choice from /palette")


if __name__ == "__main__":
    unittest.main()


# The gear moved from kernel-inline strings into the shared feed bundle
# (2026-07-13): ui/webview/gear.js is the single source both hosts render, so
# the gear pins read THAT file (and feed.css for its styling).
def _gear_src():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "ui" / "webview" / "gear.js").read_text()


def _gear_css_src():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "ui" / "webview" / "gear.css").read_text()
