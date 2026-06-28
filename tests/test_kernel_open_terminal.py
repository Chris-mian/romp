"""Click the statusline folder → open a terminal in that dir on the kernel's machine (the user 2026-06-27).
_open_terminal validates the path and shells `open -a <app> <dir>` on macOS. SYNTHETIC fixtures; subprocess is
stubbed so the test never actually launches a terminal."""
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


class OpenTerminal(unittest.TestCase):
    def setUp(self):
        self._run = km.subprocess.run
        self._isdir = km.os.path.isdir
        self.calls = []
        km.subprocess.run = lambda argv, **kw: self.calls.append(argv) or type("R", (), {"returncode": 0})()
        km.os.path.isdir = lambda p: p == GOOD

    def tearDown(self):
        km.subprocess.run = self._run
        km.os.path.isdir = self._isdir

    @unittest.skipUnless(sys.platform == "darwin", "macOS open path")
    def test_opens_a_terminal_in_an_existing_dir(self):
        km._open_terminal(GOOD)
        self.assertEqual(len(self.calls), 1, "one launch")
        argv = self.calls[0]
        self.assertEqual(argv[0], "open")
        self.assertEqual(argv[1], "-a")
        self.assertEqual(argv[-1], GOOD, "the chosen dir is the target")

    def test_a_nonexistent_dir_is_a_no_op(self):
        km._open_terminal("/no/such/TESTHOST/dir")
        self.assertEqual(self.calls, [], "never launches for a path that isn't a directory")

    def test_blank_cwd_is_a_no_op(self):
        km._open_terminal("")
        self.assertEqual(self.calls, [])

    def test_dispatch_routes_openTerminal(self):
        src = inspect.getsource(km)
        self.assertIn('msg.get("type") == "openTerminal" and msg.get("cwd")', src)
        self.assertIn('_open_terminal(str(msg["cwd"]))', src)


if __name__ == "__main__":
    unittest.main()
