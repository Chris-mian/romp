"""A test run leaves nothing in the system temp dir, and its git reads none of the developer's
configuration (2026-09-06).

Two mechanisms, one per half, both in tests/__init__.py (the second was conftest.py's until
2026-09-14). The package wraps tempfile.mkdtemp so every directory the test process mints is
recorded and removed when the run ends (under pytest at session end, under `python -m unittest` at
exit): that is the in-process half, and it covers the 300-odd module preambles and the per-test
mkdtemp calls nobody cleans up. And it covers what the hook cannot see — directories made by child
processes (kernels, git, a shell's `mktemp -d`), mkstemp files, os.mkdir paths — by pointing the
process temp dir (tempfile.tempdir and TMPDIR, so children inherit it) at one private
`romp-tests-*` root, minted before its own state dir so that dir sits inside, marked with the
owning pid for the kernel's dead-run sweep, and removed whole at exit; tests/conftest.py keeps the
pytest side of that removal, at run end with a survivor named. Before both, a full run left ~5,600
entries in /tmp and over a million had piled up; while the root was conftest's, a bare run
(`python -m unittest tests.test_x`) had no redirect and no marker, so every child's `mktemp -d`
and every mkstemp file landed loose in the system temp dir, and a run killed mid-test left
everything it made there, unsweepable. The same conftest points git at no global or system config
(GIT_CONFIG_GLOBAL, GIT_CONFIG_NOSYSTEM) with a synthetic identity: the seed commits had been
running the developer's global pre-commit hook.

Pinned five ways. Hygiene (the hook): it is installed, and a child run of this module under pytest
and under unittest leaves neither the directory it made nor its state root (ROMP_HYGIENE_MARKER
names the file where the child writes both paths). From inside a run, under either entry point:
the floors are in place and children inherit them, and no test pins a temp path to a literal
directory; under pytest, a root that survives removal is named on stderr, and a global and a
system hooksPath cannot reach a fixture commit. End to end: a nested pytest on a leaking module
leaves the system temp dir it was given exactly as it found it, serial and under xdist. Bare, end
to end, in both shapes: a child run of a leaking module shaped like `python -m unittest tests.test_x`
(the package first) and one shaped like `python3 tests/test_x.py` (nothing before the module; its
`from romp_load import load_source` is where the direct run's floor comes from, since 2026-09-14) each
leave their system temp dir as they found it, and killed mid-test each leave exactly one marked root,
which the kernel's sweep removes. The conftest-only
classes skip under a bare unittest run, where conftest never loaded and there is nothing to pin;
the rest run either way. This module loads romp code in one test only (the sweep), never at import.
"""
import ast
import contextlib
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from git_fixture import git, init_repo

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
if "tests" not in sys.modules:
    # A direct script run (`python3 tests/test_tempdir_hygiene.py`) never imports the tests package, so
    # the mkdtemp hook and the temp root would be absent: the first Hygiene check failed and the child
    # runs left two romp-hygiene-* directories behind (the #944 review). Since 2026-09-14 a direct run
    # gets the package from the module's `from romp_load import load_source` (tests/romp_load.py), but
    # this module makes that import inside one test only, after every module-level line, so it imports
    # the package here itself, ahead of the preamble below, so that preamble's directory is tracked and
    # inside the root rather than the one leak this module makes itself; the package also floors
    # XDG_STATE_HOME, as for a unittest run.
    sys.path.insert(0, ROOT)
    import tests  # noqa: F401
# Hermetic state BEFORE the one load this module makes (kernel/sdk_backend.py, inside BareRunLeavesNothing):
# never at import, but tests/test_state_isolation_order.py reads the file, not the run, and these cost nothing.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
IDENT = "romp tests <tests@example.invalid>"

under_conftest = unittest.skipUnless("tests.conftest" in sys.modules,
                                     "the floors under test are tests/conftest.py's (pytest-only)")


def _run(cmd, **kw):
    # T299: a git handed a cwd runs against a FIXTURE repository here and goes through the suite's shared runner
    # (tests/git_fixture.py), which forbids BACKGROUND work on every invocation: `git commit` spawns
    # `git maintenance run --auto`, which on recent git detaches and can still be writing into .git while the
    # TemporaryDirectory removes the repo (the CI flake "Directory not empty: '.git'",
    # tests/test_restart_classifier.py, 2026-09-10). A git with no cwd reads the checkout running the tests, or
    # no repository at all (`--version`, `config --global --list`), and stays the plain run it was.
    if cmd[0] == "git" and "cwd" in kw:
        return git(kw.pop("cwd"), *cmd[1:], check=kw.pop("check", False), timeout=60, **kw)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kw)


MARKER_ENV = "ROMP_HYGIENE_MARKER"


class Hygiene(unittest.TestCase):
    def test_mkdtemp_is_tracked_in_process(self):
        self.assertTrue(getattr(tempfile.mkdtemp, "romp_tracked", False),
                        "the tests package's mkdtemp hook is not installed")
        marker = os.environ.get(MARKER_ENV)
        if marker:                                   # child mode: leave the evidence the parent checks
            d = tempfile.mkdtemp(prefix="romp-hygiene-child-")
            self.assertTrue(os.path.isdir(d))
            with open(marker, "w") as fh:
                fh.write(d + "\n" + os.environ["XDG_STATE_HOME"] + "\n")

    def _run_child(self, argv):
        scratch = tempfile.mkdtemp(prefix="romp-hygiene-")      # tracked: swept when THIS session ends
        marker = os.path.join(scratch, "paths.txt")
        env = dict(os.environ, **{MARKER_ENV: marker})
        r = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(marker) as fh:
            made, state_root = fh.read().split("\n")[:2]
        self.assertTrue(made and state_root, "the child left no evidence")
        self.assertFalse(os.path.exists(made), "the child's mkdtemp directory survived: " + made)
        self.assertFalse(os.path.exists(state_root), "the child's state root survived: " + state_root)

    @unittest.skipIf(os.environ.get(MARKER_ENV), "child mode")
    def test_pytest_child_session_removes_its_dirs_and_state_root(self):
        self._run_child([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         "tests/test_tempdir_hygiene.py::Hygiene::test_mkdtemp_is_tracked_in_process"])

    @unittest.skipIf(os.environ.get(MARKER_ENV), "child mode")
    def test_unittest_child_run_removes_its_dirs_and_state_root(self):
        self._run_child([sys.executable, "-m", "unittest", "-q",
                         "tests.test_tempdir_hygiene.Hygiene.test_mkdtemp_is_tracked_in_process"])


class PrivateTempRoot(unittest.TestCase):
    """Not under_conftest: the root is the package's, so these hold under `python -m unittest` too."""

    def test_the_process_temp_dir_is_the_private_root(self):
        root = tempfile.gettempdir()
        self.assertTrue(os.path.basename(root).startswith("romp-tests-"), root)
        self.assertTrue(os.path.isdir(root))
        self.assertEqual(os.environ.get("TMPDIR"), root, "children find the root through TMPDIR")

    def test_module_level_state_roots_land_inside_it(self):
        # Whichever module's preamble wrote XDG_STATE_HOME last at collection, it minted the dir
        # after the package redirected the temp root, so it sits inside; so does the package's own.
        root = tempfile.gettempdir()
        xdg = os.environ["XDG_STATE_HOME"]
        self.assertEqual(os.path.commonpath([root, xdg]), root, xdg)
        pkg = sys.modules["tests"]
        self.assertEqual(os.path.realpath(root), os.path.realpath(pkg.TMP_ROOT))
        self.assertEqual(os.path.commonpath([root, pkg.STATE_DIR]), root, pkg.STATE_DIR)
        self.assertTrue(os.path.isdir(pkg.STATE_DIR), pkg.STATE_DIR)

    def test_children_inherit_the_root(self):
        root = tempfile.gettempdir()
        py = _run([sys.executable, "-c", "import tempfile, sys; sys.stdout.write(tempfile.gettempdir())"])
        self.assertEqual(py.stdout, root, "a Python child's tempfile answers with the root")
        with self.subTest(child="mktemp -d"):
            if sys.platform == "darwin":
                # macOS mktemp(1) with no template names its directory from the per-user temp root (the Darwin
                # confstr), not from TMPDIR, so the shell half cannot hold there; no product script relies on it
                # (bin/romp-serve and bin/romp-uninstall hand mktemp an explicit template under a dir they choose)
                self.skipTest("macOS mktemp(1) without a template ignores TMPDIR")
            sh = _run(["mktemp", "-d", "-u"])   # -u: name only, nothing created
            self.assertEqual(os.path.dirname(sh.stdout.strip()), root, "a shell's mktemp -d lands in it")

    def test_the_handed_temp_dir_is_recorded_once_and_the_roots_nest_under_it(self):
        # The one sanctioned way out of the root (tests/test_kernel_socket_deliver._socket_dir, for
        # a socket path that would not fit sun_path) goes to the dir the RUN was handed, never to a
        # literal system path. Recorded once: serially the root sits directly in it; in an xdist
        # worker the worker's root sits inside the controller's and the record is still the dir
        # above both — a worker that re-recorded its own gettempdir() would name the controller's
        # root, one level too deep for the socket under a long TMPDIR.
        handed = os.environ.get("ROMP_TESTS_SYSTEM_TMPDIR")
        self.assertTrue(handed, "the package records the temp dir it replaced")
        handed, root = os.path.realpath(handed), os.path.realpath(tempfile.gettempdir())
        self.assertFalse(os.path.basename(handed).startswith("romp-tests-"), handed)
        self.assertEqual(os.path.commonpath([handed, root]), handed, root)
        between = os.path.relpath(root, handed).split(os.sep)
        self.assertTrue(all(p.startswith("romp-tests-") for p in between), between)
        self.assertEqual(len(between), 2 if os.environ.get("PYTEST_XDIST_WORKER") else 1, between)

    def test_no_test_pins_a_temp_path_to_a_literal_directory(self):
        # A literal directory as a tempfile call's `dir` bypasses the redirect: the socket tests
        # carried dir="/tmp" and left three rompsock* directories in the real /tmp per run, where the
        # nested-run check below could not see them. Static, so it covers every module whether or
        # not a run exercises it; the rule and its shapes are _python_pins' and _shell_pins' (the
        # LiteralPinChecker class pins them on synthetic sources), this applies them to the tree.
        bad = []
        for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
            src = open(path, encoding="utf-8").read()
            if any(c in src for c in TEMPFILE_DIR_POSITION):     # a text prefilter keeps the parse to candidates
                bad += _python_pins(src, os.path.relpath(path, ROOT))
        for path in sorted(glob.glob(os.path.join(HERE, "*.bats")) + glob.glob(os.path.join(HERE, "*.bash"))):
            bad += _shell_pins(open(path, encoding="utf-8").read(), os.path.relpath(path, ROOT))
        self.assertEqual(bad, [], "temp paths take the process temp dir (the private root); a test that "
                         "must leave it falls back to ROMP_TESTS_SYSTEM_TMPDIR — see _socket_dir")


# The literal-directory rule, one function per language. Python: the `dir` argument of a tempfile
# call — the keyword, or the positional slot the module's signatures give it (the third of mkdtemp,
# mkstemp, mktemp and TemporaryDirectory; the seventh of NamedTemporaryFile and TemporaryFile; the
# eighth of SpooledTemporaryFile) — is a pin when it is a string literal of any value, when any
# string literal inside its expression is an absolute path (an f-string piece, an operand of `+`,
# an os.path.join argument, the default of os.environ.get), or when it is a name or attribute the
# same file assigns such an expression to (followed through assignments a few levels deep). A
# relative literal inside a composed expression (os.path.join(self.dir, "sub")) is a component, not
# a pin; a call that names no absolute path (tempfile.gettempdir(), str(home), self.td.name,
# os.environ.get("X") or ...) is where a dir should come from. Only the tempfile names are read, so
# parse_session(dir="/TESTDIR") is not a hit and a call split over lines is. Shell: `mktemp` handed
# a path under a system temp dir on the same command — as the template, as `-p`'s or `--tmpdir`'s
# value, spaced, attached or `=`-joined, quoted or bare — and any `TMPDIR=` assignment to one (the
# `TMPDIR=/tmp mktemp -d` prefix and an `export` alike: both redirect every child there). A trailing
# comment is not reached and a comment line is skipped. The round-2 review (2026-09-06) found the
# first version reading only the keyword form and only an unquoted, space-separated shell path.
TEMPFILE_DIR_POSITION = {"mkdtemp": 2, "mkstemp": 2, "mktemp": 2, "TemporaryDirectory": 2,
                         "NamedTemporaryFile": 6, "TemporaryFile": 6, "SpooledTemporaryFile": 7}
_SYSTEM_TEMP = r"/(?:tmp|var/tmp|private/tmp|var/folders|dev/shm)\b"
_SH_PIN = re.compile(r"\bmktemp\b[^\n|;&#]*(?:\s-p\s*|[\s=])[\"']?" + _SYSTEM_TEMP
                     + r"|\bTMPDIR=[\"']?" + _SYSTEM_TEMP)


def _dir_argument(call):
    """The `dir` argument's node, from the keyword or the positional slot; None when absent or when a
    starred argument makes the positions unknowable."""
    for kw in call.keywords:
        if kw.arg == "dir":
            return kw.value
    pos = TEMPFILE_DIR_POSITION[_call_name(call)]
    if len(call.args) > pos and not any(isinstance(a, ast.Starred) for a in call.args):
        return call.args[pos]
    return None


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _assignments(tree):
    """Every `name = value`, `self.name = value` (annotated or augmented too) in the module, keyed by
    the target's source text — one scope, since a test module's names are few."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for t in targets:
            if isinstance(t, (ast.Name, ast.Attribute)):
                out.setdefault(ast.unparse(t), []).append(value)
    return out


def _pinned(node, assigned, depth=3):
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if any(isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.startswith("/")
           for sub in ast.walk(node)):
        return True
    if depth and isinstance(node, (ast.Name, ast.Attribute)):
        return any(_pinned(v, assigned, depth - 1) for v in assigned.get(ast.unparse(node), ()))
    return False


def _python_pins(src, label):
    """`label:line: call` for every tempfile call in `src` whose dir is a literal directory."""
    tree = ast.parse(src)
    assigned = _assignments(tree)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in TEMPFILE_DIR_POSITION:
            d = _dir_argument(node)
            if d is not None and _pinned(d, assigned):
                bad.append("%s:%d: %s" % (label, node.lineno, ast.get_source_segment(src, node).splitlines()[0]))
    return bad


def _shell_pins(text, label):
    """`label:line: text` for every line of a shell source that points mktemp, or TMPDIR, at a
    literal system temp dir."""
    return ["%s:%d: %s" % (label, n, line.strip()) for n, line in enumerate(text.splitlines(), 1)
            if not line.lstrip().startswith("#") and _SH_PIN.search(line)]


class LiteralPinChecker(unittest.TestCase):
    """The rule on synthetic sources: every shape the round-2 review listed as passing the first
    version is a hit, and every legitimate spelling in the tree is not."""

    PREAMBLE = textwrap.dedent('''\
        import os, tempfile
        from tempfile import mkdtemp
        PINNED = "/tmp"
        VIA = PINNED
        root = tempfile.mkdtemp()
        home = root

        class T:
            def setUp(self):
                self.pinned = "/tmp/" + "x"
                self.dir = os.path.realpath(tempfile.mkdtemp())
                self.td = tempfile.TemporaryDirectory()
                name = "x"
                CALL
    ''')

    PINNED_PY = [
        'tempfile.mkdtemp(dir="/tmp")',
        'tempfile.mkdtemp(prefix="x",\n                 dir="/tmp")',                 # split over lines
        'mkdtemp(dir="/tmp")',                                                       # the bare name
        'tempfile.mkdtemp("", "x", "/tmp")',                                         # by position
        'tempfile.mkstemp("", "x", "/tmp")',
        'tempfile.mktemp("", "x", "/tmp")',
        'tempfile.TemporaryDirectory(None, None, "/tmp")',
        'tempfile.NamedTemporaryFile("w", -1, None, None, ".jsonl", "x", "/tmp")',  # the seventh
        'tempfile.TemporaryFile("w+b", -1, None, None, None, None, "/var/tmp")',
        'tempfile.SpooledTemporaryFile(0, "w+b", -1, None, None, None, None, "/tmp")',
        'tempfile.mkdtemp(dir=f"/tmp/{name}")',                                       # composed
        'tempfile.mkdtemp(dir="/tmp/" + name)',
        'tempfile.mkdtemp(dir=os.path.join("/tmp", name))',
        'tempfile.mkdtemp(dir=os.environ.get("TMPDIR", "/tmp"))',
        'tempfile.mkdtemp(dir=PINNED)',                                              # a name bound to one
        'tempfile.mkdtemp(dir=VIA)',
        'tempfile.mkdtemp(dir=self.pinned)',
        'tempfile.mkdtemp(dir="fixtures")',                                          # any plain literal
        'tempfile.mkdtemp(dir="/TESTDIR")',
    ]
    UNPINNED_PY = [
        'tempfile.mkdtemp()',
        'tempfile.mkdtemp(prefix="rompsock")',
        'tempfile.mkdtemp(dir=tempfile.gettempdir())',
        'tempfile.mkdtemp(prefix="rompsock", dir=os.environ.get("ROMP_TESTS_SYSTEM_TMPDIR") or tempfile.gettempdir())',
        'tempfile.TemporaryDirectory(dir=str(home))',
        'tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, dir=self.td.name)',
        'tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)',
        'tempfile.mkdtemp(dir=os.path.join(self.dir, "sub"))',                       # a relative component
        'tempfile.mkdtemp(dir=None)',
        'tempfile.mkdtemp("", "x", None)',
        'tempfile.mkdtemp(dir=root)',                                                # bound to a mkdtemp
        'tempfile.mkdtemp(dir=self.dir)',
        'tempfile.mkdtemp(dir=home)',
        'parse_session(dir="/TESTDIR")',                                             # not a tempfile call
        'shutil.rmtree("/tmp/x")',
        'open("/tmp/x").read()',
    ]

    def _pins(self, call):
        src = self.PREAMBLE.replace("CALL", textwrap.indent(call, " " * 8).lstrip())
        return _python_pins(src, "t.py")

    def test_python_shapes_that_pin_are_hits(self):
        for call in self.PINNED_PY:
            with self.subTest(call=call):
                pins = self._pins(call)
                self.assertEqual(len(pins), 1, pins)
                self.assertTrue(pins[0].startswith("t.py:%d: " % (self.PREAMBLE[:self.PREAMBLE.index("CALL")].count("\n") + 1)), pins)
                self.assertIn(call.splitlines()[0], pins[0])

    def test_python_shapes_that_do_not_pin_are_clean(self):
        for call in self.UNPINNED_PY:
            with self.subTest(call=call):
                self.assertEqual(self._pins(call), [])

    PINNED_SH = [
        'TEST_DIR="$(mktemp -d /tmp/x.XXXX)"',
        'TEST_DIR="$(mktemp -d "/tmp/x.XXXX")"',                # quoted
        "TEST_DIR=\"$(mktemp -d '/tmp/x.XXXX')\"",
        'd=$(mktemp -p /tmp)',
        'd=$(mktemp -p "/tmp")',
        'd=$(mktemp -p/tmp -d)',                                 # attached
        'd=$(mktemp -d --tmpdir=/tmp)',                          # =-joined
        'd=$(mktemp --tmpdir="/var/tmp" -d)',
        'd=$(mktemp --tmpdir /private/tmp)',
        'd=$(TMPDIR=/tmp mktemp -d)',                            # the prefix form
        'd=$(TMPDIR="/tmp" mktemp -d)',
        'export TMPDIR=/tmp',                                    # redirects every child there
        'TMPDIR=/var/folders/x/T',
        '    mktemp -d /var/tmp/x.XXXX',
        'run mktemp -d /dev/shm/x.XXXX',
    ]
    UNPINNED_SH = [
        'TEST_DIR="$(mktemp -d)"',
        'TEST_DIR="$(mktemp -d "$TMPDIR/x.XXXX")"',
        'd=$(mktemp -p "$TMPDIR")',
        'd=$(mktemp --tmpdir="$TEST_DIR")',
        'd=$(TMPDIR="$TEST_DIR" mktemp -d)',
        'export FAKE_TMPDIR="$TEST_DIR/fake"',                   # a name ENDING in TMPDIR is not the variable
        'export TMPDIR=/nonexistent',
        'TEST_DIR="$(mktemp -d -u)"',
        '# mktemp -d /tmp/x.XXXX',                               # a comment line
        '    # d=$(TMPDIR=/tmp mktemp -d)',
        'TEST_DIR="$(mktemp -d)"   # not /tmp',                  # a trailing comment
        '[ -d /tmp ]',
        'grep -qxF "FAKE_TMPDIR=$TEST_DIR/fake" "$FAKE_ENV"',
    ]

    def test_shell_shapes_that_pin_are_hits(self):
        for line in self.PINNED_SH:
            with self.subTest(line=line):
                self.assertEqual(_shell_pins("setup() {\n" + line + "\n}\n", "t.bats"), ["t.bats:2: " + line.strip()])

    def test_shell_shapes_that_do_not_pin_are_clean(self):
        for line in self.UNPINNED_SH:
            with self.subTest(line=line):
                self.assertEqual(_shell_pins("setup() {\n" + line + "\n}\n", "t.bats"), [])


@under_conftest
class RunEndNotice(unittest.TestCase):
    """A root that survives the run-end removal is named on stderr, once, rather than left standing
    with the run green. `shutil.rmtree(..., ignore_errors=True)` swallows a child still writing under
    the root and a 000-mode directory a test left behind (shutil's fd-based walk cannot open it, so
    the root's rmdir is never reached); the stand-in here is the latter."""

    def test_conftest_removes_the_packages_root_which_holds_the_state_dir(self):
        # One root per process, the package's: conftest imports it rather than minting a second, and the
        # package's state dir sits INSIDE it (minted after the redirect), so the root is the one thing a
        # run puts in the system temp dir and the one thing conftest removes (BareRunLeavesNothing counts
        # it, in a system temp dir of its own). Until 2026-09-14 the state dir was minted before conftest's
        # redirect and sat BESIDE the root, a second top-level entry conftest held (and marked) for the
        # run-end removal on its own.
        conftest, pkg = sys.modules["tests.conftest"], sys.modules["tests"]
        root = tempfile.gettempdir()
        self.assertEqual(os.path.realpath(root), os.path.realpath(pkg.TMP_ROOT))
        self.assertEqual(conftest._TMP_ROOT, pkg.TMP_ROOT, "conftest removes the package's root, not one of its own")
        self.assertEqual(os.path.commonpath([root, pkg.STATE_DIR]), root, pkg.STATE_DIR)

    @unittest.skipIf(os.geteuid() == 0, "root can remove a 000-mode directory")
    def test_a_root_that_survives_removal_is_named_on_stderr(self):
        conftest = sys.modules["tests.conftest"]
        root = tempfile.mkdtemp()                       # a stand-in root, inside the real one
        locked = os.path.join(root, "locked")
        os.mkdir(locked)
        open(os.path.join(locked, "f"), "w").close()
        os.chmod(locked, 0)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.addCleanup(lambda: os.path.isdir(locked) and os.chmod(locked, 0o700))

        # The real hook, on the stand-in only (the run's own root is live and not this test's).
        with patch.object(conftest, "_TMP_ROOT", root):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                conftest.pytest_unconfigure(None)
            self.assertTrue(os.path.isdir(root), "the 000-mode child keeps the root standing")
            self.assertEqual(err.getvalue(), "[tests] not removed at run end: %s\n" % root)

            err = io.StringIO()                          # the atexit fallback: same survivor, silent
            with contextlib.redirect_stderr(err):
                conftest._remove_run_dirs()
            self.assertEqual(err.getvalue(), "")

            os.chmod(locked, 0o700)                      # control: a removable root says nothing
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                conftest.pytest_unconfigure(None)
            self.assertFalse(os.path.exists(root))
            self.assertEqual(err.getvalue(), "")


def _git_version():
    out = _run(["git", "--version"]).stdout.split()
    m = re.match(r"(\d+)\.(\d+)", out[2] if len(out) > 2 else "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


@under_conftest
@unittest.skipIf(_git_version() < (2, 32), "GIT_CONFIG_GLOBAL needs git >= 2.32")
class GitFloor(unittest.TestCase):
    def test_git_reads_no_global_config_and_has_the_synthetic_identity(self):
        self.assertEqual(_run(["git", "config", "--global", "--list"]).stdout, "")
        self.assertTrue(_run(["git", "var", "GIT_AUTHOR_IDENT"]).stdout.startswith(IDENT + " "))
        self.assertTrue(_run(["git", "var", "GIT_COMMITTER_IDENT"]).stdout.startswith(IDENT + " "))

    def _hostile_repo(self, td):
        """A stand-in for the developer's configuration: a pre-commit hook that refuses every commit
        and leaves a marker, a config file wiring it in through core.hooksPath, and a repo with one
        staged file. Returns (marker, cfg, repo)."""
        hooks = os.path.join(td, "hooks")
        os.makedirs(hooks)
        marker = os.path.join(td, "hook-ran")
        with open(os.path.join(hooks, "pre-commit"), "w") as f:
            f.write("#!/bin/sh\necho ran > '%s'\nexit 1\n" % marker)
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        cfg = os.path.join(td, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[core]\n\thooksPath = %s\n" % hooks)
        repo = os.path.join(td, "repo")
        os.makedirs(repo)
        init_repo(repo, "-q")   # no ident: the commit below pins the conftest floor's identity, not a local one
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        _run(["git", "add", "a.txt"], cwd=repo, check=True)
        return marker, cfg, repo

    COMMIT = ["git", "commit", "-q", "-m", "seed"]

    def test_a_global_hooks_path_cannot_reach_a_fixture_commit(self):
        # The hostile config as the GLOBAL file. Live first, then floored (the suite's own env).
        with tempfile.TemporaryDirectory() as td:
            marker, cfg, repo = self._hostile_repo(td)
            live = _run(self.COMMIT, cwd=repo, env=dict(os.environ, GIT_CONFIG_GLOBAL=cfg))
            self.assertNotEqual(live.returncode, 0, "the probe is live: the hook blocks the commit")
            self.assertTrue(os.path.exists(marker))
            os.remove(marker)

            floored = _run(self.COMMIT, cwd=repo)
            self.assertEqual(floored.returncode, 0, floored.stderr)
            self.assertFalse(os.path.exists(marker), "no global hook reaches a fixture commit")
            self.assertEqual(_run(["git", "log", "-1", "--format=%an <%ae>"], cwd=repo).stdout.strip(), IDENT)

    def test_a_system_hooks_path_cannot_reach_a_fixture_commit_either(self):
        # The hostile config as the SYSTEM file: GIT_CONFIG_SYSTEM (git >= 2.32, like GIT_CONFIG_GLOBAL)
        # is a root-free stand-in for /etc/gitconfig, and GIT_CONFIG_NOSYSTEM=1 is the half of the
        # floor that hides it — the global probe above says nothing about it. The assertion is the
        # commit's outcome: `git config --system --list` prints the file under NOSYSTEM too.
        with tempfile.TemporaryDirectory() as td:
            marker, cfg, repo = self._hostile_repo(td)
            live_env = dict(os.environ, GIT_CONFIG_SYSTEM=cfg)
            live_env.pop("GIT_CONFIG_NOSYSTEM", None)
            live = _run(self.COMMIT, cwd=repo, env=live_env)
            self.assertNotEqual(live.returncode, 0, "the probe is live: the system hook blocks the commit")
            self.assertTrue(os.path.exists(marker))
            os.remove(marker)

            floored = _run(self.COMMIT, cwd=repo, env=dict(os.environ, GIT_CONFIG_SYSTEM=cfg))
            self.assertEqual(floored.returncode, 0, floored.stderr)
            self.assertFalse(os.path.exists(marker), "no system hook reaches a fixture commit")


LEAKY_MODULE = textwrap.dedent('''\
    import os, subprocess, sys, tempfile, unittest
    from git_fixture import git, init_repo    # the suite's runner (tests/__init__.py registers it under tests.conftest)
    ROOT = os.environ["TMPDIR"]
    STATE = tempfile.mkdtemp()            # a module preamble's state root: never cleaned by the module

    class Leak(unittest.TestCase):
        def test_everything_lands_under_the_private_root(self):
            self.assertTrue(os.path.basename(ROOT).startswith("romp-tests-"), ROOT)
            d = tempfile.mkdtemp()            # a seed repo, the shape that leaked: never cleaned
            fd, f = tempfile.mkstemp()
            os.close(fd)
            init_repo(d, "-q")                # no background git work: a detached maintenance would outlive the run
            open(os.path.join(d, "a.txt"), "w").write("a\\n")
            git(d, "add", "a.txt")
            git(d, "commit", "-q", "-m", "seed")
            made = [STATE, d, f]
            if sys.platform != "darwin":      # macOS mktemp(1) without a template ignores TMPDIR (the Darwin per-user root)
                made.append(subprocess.run(["mktemp", "-d"], capture_output=True, text=True, check=True).stdout.strip())
            for p in made:
                self.assertEqual(os.path.commonpath([ROOT, p]), ROOT, p)
''')


@under_conftest
class RunLeavesNothing(unittest.TestCase):
    """A nested pytest, handed a fresh directory as its system temp dir and loading this repo's
    conftest as a plugin, runs a module that leaks every way the suite does: after it exits the
    directory holds exactly what it held before.

    The fresh directory is the whole check; the machine's real system temp dir is not diffed. It
    would be cheap (a prefix-filtered os.scandir over 101k entries measured 0.10 s, 2026-09-06) but
    not attributable: that dir is shared with every process on the box, and with other checkouts
    running this suite beside it, romp-prefixed entries appeared there about twice a minute (345
    bursts in three hours, measured the same day) — a before/after diff over a nested run of a few
    seconds would fail a third of the time with nothing wrong. Only a literal path can reach it past
    TMPDIR, and PrivateTempRoot pins that class statically."""

    def _nested(self, *extra):
        fresh = tempfile.mkdtemp()
        case = os.path.join(fresh, "case")
        os.makedirs(case)
        with open(os.path.join(case, "test_leak.py"), "w") as f:
            f.write(LEAKY_MODULE)
        env = dict(os.environ, TMPDIR=fresh, PYTHONDONTWRITEBYTECODE="1")
        for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_CURRENT_TEST",
            "PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT",
            "ROMP_TESTS_SYSTEM_TMPDIR"):        # a fresh run records its own handed dir (the package setdefaults it)
            env.pop(var, None)
        r = subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.conftest", "-p", "no:cacheprovider",
                            "-q", *extra, os.path.join(case, "test_leak.py")],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 passed", r.stdout)
        self.assertEqual(sorted(os.listdir(fresh)), ["case"],
                         "the run must leave the system temp dir as it found it")

    def test_a_run_removes_everything_it_created_under_the_system_temp_dir(self):
        self._nested()

    @unittest.skipUnless(importlib.util.find_spec("xdist"), "pytest-xdist not installed")
    def test_under_xdist_the_run_leaves_nothing_either(self):
        # Pins the outcome, not each process's hook: a worker's root sits inside the controller's
        # (it inherits that TMPDIR), so the controller's removal alone would satisfy this.
        self._nested("-n", "2")


BARE_LEAKY_MODULE = textwrap.dedent('''\
    import os, subprocess, sys, tempfile, time, unittest
    FIRST_IMPORTS
    os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # the module preamble's state root, AFTER the import as in every module
    os.environ.pop("ROMP_STATE_DIR", None)
    READY = os.environ.get("ROMP_HYGIENE_READY")

    class Leak(unittest.TestCase):
        def test_leaks_every_way_a_bare_run_can(self):
            tempfile.mkdtemp()                                                  # tracked: the hook's exit sweep removes it
            fd, _ = tempfile.mkstemp()                                          # a file: the hook never sees it
            os.close(fd)
            subprocess.run(["mktemp", "-d"], check=True, capture_output=True)   # a child's directory: nor that
            if READY:                                                           # the killed leg: say so, then wait for the kill
                open(READY, "w").close()
                time.sleep(600)

    if __name__ == "__main__":
        unittest.main()
''')
# The module's first imports, one set per shape of bare run. `python -m unittest tests.test_x` imports the
# package before the module, so the module's own `from romp_load import load_source` finds the name the
# package registered; a direct `python3 tests/test_x.py` imports nothing before the module, and that same
# line is where the package comes from (tests/romp_load.py's bootstrap, 2026-09-14).
UNITTEST_SHAPED_IMPORTS = ("import tests   # noqa: F401  the package first, then the module: the order `python -m unittest tests.test_x` runs them in\n"
                           "from romp_load import load_source   # noqa: F401  every module's one import; here the package's registration")
DIRECT_SHAPED_IMPORTS = "from romp_load import load_source   # noqa: F401  every module's one import, and here the first thing that runs"


class BareRunLeavesNothing(unittest.TestCase):
    """A bare run, handed a fresh directory as its system temp dir, runs a module that leaks every way a bare
    run can: a module preamble's mkdtemp, a tracked mkdtemp in a test, a mkstemp file, a child's `mktemp -d`.
    Finished, it leaves the directory as it found it; killed mid-test (SIGKILL, as a kernel restart cutting
    the tool shell does: no atexit, no sweep, no removal), it leaves exactly one entry, a `romp-tests-*` root
    whose marker names the dead pid, and the kernel's boot sweep removes it. Two shapes of bare run, each
    both ways: the tests package imported before the module and no conftest, which is what `python -m
    unittest tests.test_x` is; and the module alone, which is what `python3 tests/test_x.py` is, where
    nothing imports the package and the module's `from romp_load import load_source`, its first import as in
    every module, is where the floor comes from (tests/romp_load.py's bootstrap). Until 2026-09-14 the root
    and the marker were conftest's, so a bare run of either shape left the mkstemp file and the `mktemp -d`
    directory loose on a normal exit and, killed, everything it made plus an unmarked romp-tests-state-* dir
    the sweep had to refuse; the package took them the same day, and the direct run still had nothing, not
    even the hook: `python3 tests/test_credentials.py` left 86 loose tmp* directories in a fresh TMPDIR where
    `python3 -m unittest tests.test_credentials` left none. The child is the subject, so this runs under
    pytest and under a bare run of this module alike. The kill waits on the child's own ready-file, never on
    a timer."""

    def _bare_child(self, kill=False, direct=False):
        """(Popen, fresh, ready): the leaky module, `test_bare_leak.py` (a test module's name), written OUTSIDE
        `fresh` and run as a script with TMPDIR at `fresh`, none of the parent run's own names, and a
        ready-file to write before it sleeps when `kill` is asked. Two shapes. The unittest-shaped child (the
        default) has the checkout on its PYTHONPATH and imports the package first, as `python -m unittest
        tests.test_x` does before the module. The direct-shaped child has the checkout's tests/ directory on
        its PYTHONPATH instead, the stand-in for sys.path[0], which a module IN tests/ gets for free: its
        `from romp_load import load_source` resolves the file under its bare name as `python3 tests/test_x.py`
        does, nothing has imported the package, and this test puts the checkout root on no path (the loader
        does). Its cwd is a directory of its own: a script run never has the cwd on sys.path, and the floor
        must not depend on where the run started."""
        scratch = tempfile.mkdtemp(prefix="romp-hygiene-bare-")      # tracked: inside this run's root
        fresh = os.path.join(scratch, "systmp")
        os.mkdir(fresh)
        module = os.path.join(scratch, "test_bare_leak.py")
        with open(module, "w") as fh:
            fh.write(BARE_LEAKY_MODULE.replace("FIRST_IMPORTS", DIRECT_SHAPED_IMPORTS if direct else UNITTEST_SHAPED_IMPORTS))
        on_path = HERE if direct else ROOT
        env = dict(os.environ, TMPDIR=fresh, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.pathsep.join(p for p in (on_path, os.environ.get("PYTHONPATH")) if p))
        for var in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_CURRENT_TEST",
                    "PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", MARKER_ENV,
                    "ROMP_TESTS_SYSTEM_TMPDIR"):        # a fresh run records its own handed dir (the package setdefaults it)
            env.pop(var, None)
        ready = os.path.join(scratch, "ready")
        if kill:
            env["ROMP_HYGIENE_READY"] = ready
        cwd = ROOT
        if direct:
            cwd = os.path.join(scratch, "cwd")
            os.mkdir(cwd)
        proc = subprocess.Popen([sys.executable, module], cwd=cwd, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        def _reap():
            # kill a child still running on a failure path, then reap it: a killed child left unwaited
            # is a zombie until this process exits. Drain the pipe only while it is still open (a test
            # that already read the child to its end has closed it, and a second communicate raises)
            if proc.poll() is None:
                proc.kill()
            if proc.stdout is not None and not proc.stdout.closed:
                proc.communicate()
            else:
                proc.wait()
        self.addCleanup(_reap)
        return proc, fresh, ready

    def _finished_run_leaves_nothing(self, direct):
        proc, fresh, _ = self._bare_child(direct=direct)
        out, _ = proc.communicate(timeout=120)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("Ran 1 test", out)
        self.assertEqual(os.listdir(fresh), [], "a %s run must leave the system temp dir as it found it"
                         % ("direct" if direct else "bare"))

    def _killed_run_leaves_one_marked_root_the_sweep_removes(self, direct):
        proc, fresh, ready = self._bare_child(kill=True, direct=direct)
        deadline = time.monotonic() + 60
        while not os.path.exists(ready):           # loop-ok: bounded wait on the child's ready-file, the event itself
            if proc.poll() is not None:
                self.fail("the child ended before it was ready:\n" + proc.communicate()[0])
            self.assertLess(time.monotonic(), deadline, "the child never said it was ready")
            time.sleep(0.02)
        proc.kill()
        proc.communicate()
        entries = os.listdir(fresh)
        self.assertEqual(len(entries), 1, "a killed %s run leaves exactly its root, marked: %r"
                         % ("direct" if direct else "bare", entries))
        root = os.path.join(fresh, entries[0])
        self.assertTrue(entries[0].startswith("romp-tests-") and os.path.isdir(root), entries)
        with open(os.path.join(root, "romp-tests-owner.json")) as fh:
            self.assertEqual(json.load(fh)["pid"], proc.pid, "the marker names the dead run")
        # ...and the kernel's boot sweep over that system temp dir sees a dead owner and removes it. Loaded
        # here, not at import: this module loads no romp code until this line (a private name, as the
        # siblings that load the backend do).
        from romp_load import load_source
        sb = load_source("romp_sdk_backend_hygiene", os.path.join(ROOT, "bin", "romp_sdk_backend.py"))
        self.assertEqual(sb.sweep_dead_test_roots(fresh), 1)
        self.assertEqual(os.listdir(fresh), [])

    def test_a_finished_bare_run_leaves_the_system_temp_dir_as_it_found_it(self):
        self._finished_run_leaves_nothing(direct=False)

    def test_a_bare_run_killed_mid_test_leaves_one_marked_root_the_sweep_removes(self):
        self._killed_run_leaves_one_marked_root_the_sweep_removes(direct=False)

    def test_a_finished_direct_run_leaves_the_system_temp_dir_as_it_found_it(self):
        # Red before the loader's bootstrap: the direct child had no hook, no root and no redirect, so the
        # preamble's dir, the test's mkdtemp, the mkstemp file and the `mktemp -d` dir all survived, loose.
        self._finished_run_leaves_nothing(direct=True)

    def test_a_direct_run_killed_mid_test_leaves_one_marked_root_the_sweep_removes(self):
        # Red before it too: the same four entries, none of them a marked root the sweep would take.
        self._killed_run_leaves_one_marked_root_the_sweep_removes(direct=True)

if __name__ == "__main__":
    unittest.main()      # the package import for a direct run is at the top of the module, with the reason
