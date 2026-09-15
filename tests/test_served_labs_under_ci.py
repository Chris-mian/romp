"""Every served lab runs in CI's served job (2026-09-15).

CI's browser-backed step (.github/workflows/ci.yml, "Browser-backed served-page tests") runs ONLY the files its two
globs name, tests/test_*_browser.py and tests/test_*_served.py, under ROMP_SERVED_TESTS_REQUIRE=1; tests/conftest.py
turns a skip in exactly those files into a failure (_is_served_test_file, the same two suffixes). A lab whose name misses
both suffixes therefore skips on the Python matrix runners (no node deps, no browser), never runs in the served job,
and its skip stays a skip: eleven labs stood outside the globs on 2026-09-15, and one of them
(the ship-reship lab, since renamed with the suffix; its NackNoticeSurvivesReload class) hid a real regression on main
for a day.

The pin lists the served labs by CONTENT, from the tree, and checks the names against both name rules:
  a served lab is a test module under tests/ that names playwright (a browser drives it) and either boots the hermetic
  kernel (the romp-kernel module), imports the lab kernel's environment (the ship-reship module), or hands the extension
  package to a node driver (EXT_PKG). tests/test_served_tests_require.py names playwright too, in prose, and does none of
  the three: it drives pytest itself on synthetic files, and stands here as the named control.
  This pin names every marker in its own source and reads the tree only, so it leaves itself out by file name.
Every lab must (1) satisfy the conftest's own predicate, (2) match a glob the CI step's pytest line names, read from the
workflow file, and (3) the CI globs must be the conftest's two suffixes, so the two name rules cannot drift apart.

Synthetic: reads the tree only; no kernel, no browser.
"""
import fnmatch
import glob
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CI_YML = os.path.join(ROOT, ".github", "workflows", "ci.yml")
CONTROL = "test_served_tests_require.py"
CONFTEST = os.path.join(HERE, "conftest.py")


def conftest_module():
    """tests/conftest.py as pytest itself loaded it (its name in the module table is pytest's to choose), so the
    predicate checked is the one the runs use, never a second copy of a module with import-time effects."""
    for m in list(sys.modules.values()):
        if os.path.realpath(getattr(m, "__file__", None) or "") == os.path.realpath(CONFTEST):
            return m
    raise AssertionError("tests/conftest.py is not loaded: run this pin under pytest")


def is_served_lab(text: str) -> bool:
    """A browser drives it, and it boots the hermetic kernel, imports the lab kernel's environment, or hands the
    extension package to a node driver."""
    drives = "playwright" in text
    boots = ("romp-kernel" in text) or ("import test_ship_reship" in text) or ("EXT_PKG" in text)
    return drives and boots


def served_labs():
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        if os.path.basename(path) == os.path.basename(__file__):
            continue   # this pin names every marker in its own text; it is a census, not a lab
        with open(path, encoding="utf-8") as f:
            if is_served_lab(f.read()):
                out.append(os.path.basename(path))
    return out


def ci_served_globs():
    """The file globs on the served step's pytest line: the step that sets ROMP_SERVED_TESTS_REQUIRE to 1."""
    with open(CI_YML, encoding="utf-8") as f:
        text = f.read()
    step = re.search(r'ROMP_SERVED_TESTS_REQUIRE: "1".*?python -m pytest ([^\n]*)', text, re.S)
    if not step:
        raise AssertionError("ci.yml has no pytest line after ROMP_SERVED_TESTS_REQUIRE: \"1\"")
    return [tok for tok in step.group(1).split() if tok.startswith("tests/")]


class _Item:
    """The shape conftest._is_served_test_file reads: an item with a path."""

    def __init__(self, name):
        self.path = os.path.join(HERE, name)
        self.fspath = self.path


class ServedLabsUnderCI(unittest.TestCase):
    def test_the_census_finds_labs_and_excludes_the_control(self):
        labs = served_labs()
        self.assertGreater(len(labs), 50, labs)
        self.assertNotIn(CONTROL, labs, "the require-road pin drives pytest, not a browser")
        self.assertTrue(os.path.exists(os.path.join(HERE, CONTROL)), "the control file is gone; name another")

    def test_every_served_lab_satisfies_the_conftest_predicate(self):
        missed = [n for n in served_labs() if not conftest_module()._is_served_test_file(_Item(n))]
        self.assertEqual(missed, [], "served labs outside the conftest's _browser/_served name rule (their skips stay "
                                     "skips and CI never runs them): %s" % missed)

    def test_every_served_lab_matches_a_glob_the_ci_step_runs(self):
        globs = ci_served_globs()
        self.assertTrue(globs, "the served step's pytest line names no tests/ globs")
        missed = [n for n in served_labs() if not any(fnmatch.fnmatch("tests/" + n, g) for g in globs)]
        self.assertEqual(missed, [], "served labs no CI glob %s runs: %s" % (globs, missed))

    def test_the_ci_globs_are_the_conftest_suffixes(self):
        self.assertEqual(sorted(ci_served_globs()), ["tests/test_*_browser.py", "tests/test_*_served.py"])
        self.assertTrue(conftest_module()._is_served_test_file(_Item("test_x_browser.py")))
        self.assertTrue(conftest_module()._is_served_test_file(_Item("test_x_served.py")))
        self.assertFalse(conftest_module()._is_served_test_file(_Item("test_x.py")))


if __name__ == "__main__":
    unittest.main()
