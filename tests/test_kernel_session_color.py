"""Per-session identity color override (the user 2026-06-29): a right-click tab menu picks a color from the
romp identity palette; the kernel persists it to the names registry (bg + fg word, preserving name + cwd) and
re-broadcasts. SYNTHETIC fixtures only (placeholder uuids, invented paths)."""
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
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class SessionColor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.names = Path(self.tmp) / "names"
        self.names.mkdir()
        self._orig = km.NAMES
        km.NAMES = self.names

    def tearDown(self):
        km.NAMES = self._orig

    def test_palette_has_nine_colors_and_a_fg_word_each(self):
        # the SAME set the tmux launcher / SDK backend assign from — keep all three in sync
        self.assertEqual(len(km._PALETTE), 9)
        self.assertEqual(len(km._PALETTE_FG), 9)
        self.assertIn("#1EA1EB", km._PALETTE)

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

    def test_rejects_a_color_outside_the_palette(self):
        (self.names / SID).write_text("s\t/d\t#1EA1EB\twhite\n")
        self.assertFalse(km._set_session_color(SID, "#abcdef"))
        self.assertEqual((self.names / SID).read_text().split("\t")[2], "#1EA1EB", "unchanged")

    def test_missing_names_file_is_a_safe_noop(self):
        self.assertFalse(km._set_session_color("00000000-0000-0000-0000-000000000000", "#1EA1EB"))

    def test_get_serves_palette_and_ws_handles_setSessionColor(self):
        # the /palette GET serves the set; the WS dispatch routes setSessionColor → _set_session_color + push
        get_src = inspect.getsource(km.Handler.do_GET)
        self.assertIn('p == "/palette"', get_src)
        self.assertIn("_PALETTE", get_src)
        # the WS message branch (in the kernel source) recolors then re-broadcasts
        ksrc = Path(BIN, "romp-kernel").read_text()
        self.assertIn('msg.get("type") == "setSessionColor"', ksrc)
        self.assertIn("_set_session_color(str(msg[\"id\"]), str(msg[\"bg\"]))", ksrc)


if __name__ == "__main__":
    unittest.main()
