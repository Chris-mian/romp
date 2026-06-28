"""Click the statusline folder → open a terminal in that dir on the kernel's machine (the user 2026-06-27).
There's no portable "default terminal" API (macOS has no folder→terminal handler), so _open_terminal honors an
explicit override ($ROMP_TERMINAL / ~/.config/romp/terminal), then the launched-from terminal, then the first
INSTALLED popular terminal (Ghostty/iTerm/… before Terminal), then the OS default. SYNTHETIC fixtures;
subprocess is stubbed so the test never launches anything."""
import inspect
import os
import sys
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

GOOD = "/tmp/TESTHOST/somedir"


class _R:
    def __init__(self, rc=0): self.returncode = rc


class OpenTerminal(unittest.TestCase):
    def setUp(self):
        self._run, self._popen, self._isdir = km.subprocess.run, km.subprocess.Popen, km.os.path.isdir
        self._env = dict(os.environ)
        self.calls = []
        km.subprocess.run = lambda argv, **kw: self.calls.append(argv) or _R(0)   # every app "installed"
        km.subprocess.Popen = lambda argv, **kw: self.calls.append(("popen", argv, kw.get("cwd")))
        km.os.path.isdir = lambda p: p == GOOD
        os.environ.pop("ROMP_TERMINAL", None)
        os.environ.pop("TERM_PROGRAM", None)

    def tearDown(self):
        km.subprocess.run, km.subprocess.Popen, km.os.path.isdir = self._run, self._popen, self._isdir
        os.environ.clear(); os.environ.update(self._env)

    def _launch(self):
        # on macOS the launch is the `open -a <app> <dir>` call (probes use `open -Ra`); on Linux it's the Popen.
        if sys.platform == "darwin":
            return next((c for c in self.calls if isinstance(c, list) and "-a" in c), None)
        return next((c for c in self.calls if isinstance(c, tuple) and c[0] == "popen"), None)

    def test_opens_a_terminal_in_an_existing_dir(self):
        km._open_terminal(GOOD)
        launch = self._launch()
        self.assertIsNotNone(launch, "a terminal is launched for a real dir")
        if sys.platform == "darwin":
            self.assertEqual(launch[-1], GOOD, "the chosen dir is the open target")
        else:
            self.assertEqual(launch[2], GOOD, "the terminal starts in the chosen dir (Popen cwd)")

    @unittest.skipUnless(sys.platform == "darwin", "macOS open -a path")
    def test_explicit_override_wins(self):
        os.environ["ROMP_TERMINAL"] = "Ghostty"
        km._open_terminal(GOOD)
        launch = self._launch()
        self.assertEqual(launch, ["open", "-a", "Ghostty", GOOD], "the user's $ROMP_TERMINAL is honored first")

    def test_a_nonexistent_dir_is_a_no_op(self):
        km._open_terminal("/no/such/TESTHOST/dir")
        self.assertEqual(self.calls, [], "never launches for a path that isn't a directory")

    def test_blank_cwd_is_a_no_op(self):
        km._open_terminal("")
        self.assertEqual(self.calls, [])

    def test_terminal_pref_reads_env(self):
        os.environ["ROMP_TERMINAL"] = "  iTerm  "
        self.assertEqual(km._terminal_pref(), "iTerm", "trimmed env override")

    def test_dispatch_routes_openTerminal(self):
        src = inspect.getsource(km)
        self.assertIn('msg.get("type") == "openTerminal" and msg.get("cwd")', src)
        self.assertIn('_open_terminal(str(msg["cwd"]))', src)


if __name__ == "__main__":
    unittest.main()
