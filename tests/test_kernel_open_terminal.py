"""Click the statusline folder → run a CONFIGURABLE opener for that dir on the kernel's machine (the user
2026-06-27). With no config it uses the OS default opener (`open` on macOS / `xdg-open` on Linux — the one
portable "open this" command); a user overrides via $ROMP_OPEN_FOLDER or ~/.config/romp/open-folder with a
command whose `{dir}` placeholder is substituted (else the path is appended) — e.g. `open -a Ghostty {dir}`.
SYNTHETIC fixtures; subprocess is stubbed so nothing actually launches."""
import inspect
import os
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

GOOD = "/tmp/TESTHOST/somedir"


class OpenFolder(unittest.TestCase):
    def setUp(self):
        self._popen, self._isdir = km.subprocess.Popen, km.os.path.isdir
        self._env = dict(os.environ)
        self.calls = []
        km.subprocess.Popen = lambda argv, **kw: self.calls.append(list(argv))
        km.os.path.isdir = lambda p: p == GOOD
        os.environ.pop("ROMP_OPEN_FOLDER", None)
        os.environ["HOME"] = tempfile.mkdtemp()   # isolate ~/.config/romp/open-folder from the real machine

    def tearDown(self):
        km.subprocess.Popen, km.os.path.isdir = self._popen, self._isdir
        os.environ.clear(); os.environ.update(self._env)

    def test_no_config_uses_the_os_default_opener(self):
        km._open_folder(GOOD)
        self.assertEqual(len(self.calls), 1)
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        self.assertEqual(self.calls[0], [opener, GOOD], "the OS default folder opener")

    def test_override_with_dir_placeholder(self):
        os.environ["ROMP_OPEN_FOLDER"] = "open -a Ghostty {dir}"
        km._open_folder(GOOD)
        self.assertEqual(self.calls[0], ["open", "-a", "Ghostty", GOOD], "{dir} is substituted in place")

    def test_override_without_placeholder_appends_the_dir(self):
        os.environ["ROMP_OPEN_FOLDER"] = "code"
        km._open_folder(GOOD)
        self.assertEqual(self.calls[0], ["code", GOOD], "no {dir} → the path is appended as the last arg")

    def test_a_nonexistent_dir_is_a_no_op(self):
        km._open_folder("/no/such/TESTHOST/dir")
        self.assertEqual(self.calls, [])

    def test_blank_cwd_is_a_no_op(self):
        km._open_folder("")
        self.assertEqual(self.calls, [])

    def test_folder_opener_reads_env_override(self):
        os.environ["ROMP_OPEN_FOLDER"] = "  ghostty --working-directory={dir}  "
        self.assertEqual(km._folder_opener(), "ghostty --working-directory={dir}", "trimmed env override")

    def test_dispatch_routes_openFolder(self):
        src = inspect.getsource(km)
        self.assertIn('msg.get("type") == "openFolder" and msg.get("cwd")', src)
        self.assertIn('_open_folder(str(msg["cwd"]))', src)


if __name__ == "__main__":
    unittest.main()
