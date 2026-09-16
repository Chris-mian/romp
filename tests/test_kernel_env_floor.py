#!/usr/bin/env python3
"""The suite-wide CLI-binary floor (tests/conftest.py: ROMP_CLAUDE_BIN=/bin/false) holds for every test, in both halves the
cli-scope floor has (tests/test_cli_scope_floor.py): set at import, and re-asserted per test by an autouse fixture, because a
test module's module-level write executes at COLLECTION and holds for every test after it. The case that wrote this
(2026-09-16): tests/test_login_flow.py set its login mock as the CLI at module level, so under a whole run every lab kernel
(kernel_env passes ROMP_CLAUDE_BIN through) ran its judges against the mock, whose answers the planner's coerce floor turned
into goals; the auto-nudge fired into sessions no CLI could run, and the nudge walk read the parked nudges as the user's
queued input for both boots of tests/test_fold_checkpoints_served.py, one red only under a whole suite, green alone. The
second pin walks every test module for a module-level assignment to the name and names the offender. Synthetic throughout:
the inputs are the test files' text."""
import ast
import glob
import os
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
CONFTEST = os.path.join(HERE, "conftest.py")
NAME = "ROMP_CLAUDE_BIN"


def _assigns_env(stmt, name):
    """Is `stmt` an assignment os.environ[name] = ...?"""
    if not isinstance(stmt, ast.Assign):
        return False
    for t in stmt.targets:
        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) and t.value.attr == "environ"
                and isinstance(t.slice, ast.Constant) and t.slice.value == name):
            return True
    return False


def _is_autouse_fixture(fn):
    for d in fn.decorator_list:
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "fixture"):
            continue
        for kw in d.keywords:
            if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


class CliBinaryFloor(unittest.TestCase):
    def setUp(self):
        with open(CONFTEST) as f:
            self.body = ast.parse(f.read(), filename=CONFTEST).body

    def test_an_autouse_fixture_re_asserts_the_binary_floor_per_test(self):
        fixtures = [fn for fn in self.body if isinstance(fn, ast.FunctionDef) and _is_autouse_fixture(fn)]
        self.assertTrue(fixtures, "tests/conftest.py has no autouse fixtures at all")
        self.assertTrue(any(any(_assigns_env(stmt, NAME) for stmt in fn.body) for fn in fixtures),
                        "no autouse fixture in tests/conftest.py sets os.environ[%r]: one test module's import-time write would "
                        "hold for every lab kernel after it (the served checkpoint lab's judges answered by a login mock)" % NAME)

    def test_no_test_module_assigns_the_binary_at_module_level(self):
        offenders = []
        for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
            with open(path) as f:
                try:
                    body = ast.parse(f.read(), filename=path).body
                except SyntaxError:
                    continue
            for stmt in body:                              # top level only: a set inside setUp runs per test and is restored
                if _assigns_env(stmt, NAME):
                    offenders.append("%s:%d" % (os.path.basename(path), stmt.lineno))
        self.assertEqual(offenders, [], "these test modules set os.environ[%r] at module level, which executes at collection "
                                        "and reaches every lab kernel of the run; set it in setUp and restore it in tearDown" % NAME)

    def test_the_value_holds_while_this_test_runs(self):
        self.assertEqual(os.environ.get(NAME), "/bin/false", "the floor, re-asserted by the fixture before this test")


if __name__ == "__main__":
    unittest.main()
