#!/usr/bin/env python3
"""The suite-wide cli-scope floor (tests/conftest.py, 2026-09-05): no test may start a REAL transient
scope. Constructing the SDK backend decides once whether to spawn session CLIs through `systemd-run
--scope` (sdk_backend.cli_scope_supported), and that verdict defaults to ON under ROMP_SUPERVISED, which
every tool shell of a session on a self-hosted install inherits from the service — so a suite run from
one would probe the live user manager at every backend construction and leave a scope behind for every
launch. conftest.py floors ROMP_CLI_SCOPE=0 at import, so collection-time constructions are covered, and
re-asserts it per test through an autouse fixture, because a module-level write in a test file also
executes at collection and would otherwise hold for the rest of the run.

Pinned on conftest's SOURCE, not on the value at run time. tests/test_cli_scope.py sets ROMP_CLI_SCOPE=0
itself at import (for a bare unittest run of that module), and pytest collects every module on every
worker before any test runs, so under a full run the value reads "0" whether or not conftest set it:
dropping the floor failed nothing. Each half of the floor has its own pin here; nothing here sets the
value. Synthetic throughout: the only input is conftest.py's text.
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
CONFTEST = os.path.join(HERE, "conftest.py")


def _sets_cli_scope_off(stmt):
    """Is `stmt` the statement os.environ["ROMP_CLI_SCOPE"] = "0"? (Set, not setdefault: "0" is the
    one value the switch reads as off, so no outer intent is being overridden.)"""
    if not isinstance(stmt, ast.Assign):
        return False
    if not (isinstance(stmt.value, ast.Constant) and stmt.value.value == "0"):
        return False
    for t in stmt.targets:
        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) and t.value.attr == "environ"
                and isinstance(t.slice, ast.Constant) and t.slice.value == "ROMP_CLI_SCOPE"):
            return True
    return False


def _is_autouse_fixture(fn):
    """Is `fn` decorated @pytest.fixture(autouse=True)?"""
    for d in fn.decorator_list:
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "fixture"):
            continue
        for kw in d.keywords:
            if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


class CliScopeFloor(unittest.TestCase):
    def setUp(self):
        with open(CONFTEST) as f:
            self.body = ast.parse(f.read(), filename=CONFTEST).body

    def test_the_import_time_floor_is_a_module_level_statement(self):
        # Top level only: a set inside a function does not run at collection, and collection is when a
        # test module's import-time backend construction would reach the real systemd-run.
        self.assertTrue(any(_sets_cli_scope_off(stmt) for stmt in self.body),
                        'tests/conftest.py must set os.environ["ROMP_CLI_SCOPE"] = "0" at module level — '
                        "without it a test module that builds an SDK backend at import, under an inherited "
                        "ROMP_SUPERVISED, probes the real user manager and scopes every launch")

    def test_an_autouse_fixture_re_asserts_the_floor_per_test(self):
        fixtures = [fn for fn in self.body if isinstance(fn, ast.FunctionDef) and _is_autouse_fixture(fn)]
        self.assertTrue(fixtures, "tests/conftest.py has no autouse fixtures at all")
        self.assertTrue(any(any(_sets_cli_scope_off(stmt) for stmt in fn.body) for fn in fixtures),
                        'no autouse fixture in tests/conftest.py sets os.environ["ROMP_CLI_SCOPE"] = "0" — '
                        "one test module's import-time write or pop would otherwise hold for every test after it")

    def test_the_value_holds_while_this_test_runs(self):
        # The run-time half, read only. Under a full run this cannot tell conftest's floor from
        # test_cli_scope.py's own preamble (module docstring). Alone — `pytest tests/test_cli_scope_floor.py`
        # — nothing but conftest's floor sets the value, so this fails only once the floor is gone (and the
        # shell does not export "0" itself); while the floor stands it overrides whatever the shell exports.
        self.assertEqual(os.environ.get("ROMP_CLI_SCOPE"), "0", "conftest's floor is not in effect")


if __name__ == "__main__":
    unittest.main()
