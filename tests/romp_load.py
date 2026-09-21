"""The test suite's file-path importer: `from romp_load import load_source`.

A test module loads the code under test by path through the stable bin/ names
(`load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))`). The older form,
`SourceFileLoader(...).load_module()`, emits a DeprecationWarning on Python 3.10 and later and its
removal is documented for 3.15; the replacement is kernel/loadsource.py, and this module is how a
test reaches it without a package import. It is importable under every way the suite runs: pytest
and `python -m unittest tests.test_x` import the tests package first, whose __init__ registers this
module under the bare name; a direct `python tests/test_x.py` (or `cd tests && python -m unittest
test_x`) has this directory on sys.path already.

The semantics a test may lean on are load_module()'s, kept on purpose: a name already in
sys.modules is re-executed into the SAME module object, so a test that loads `romp_judge` and then
`romp_kernel` gets a kernel whose `jd` IS its own `jd` handle (and a `_rebind_state` on one is seen
by the other). A test that needs a private copy loads under a private name, as before.

It is also where a DIRECT run of a test module, `python3 tests/test_x.py` (the run seven module
docstrings advertise, and agents use), gets the suite's floor (2026-09-14). pytest and `python -m
unittest tests.test_x` import the tests package before any module, and the package IS the floor: the
mkdtemp hook, the private `romp-tests-*` temp root with TMPDIR redirected into it and the owner
marker the kernel's dead-run sweep reads, the XDG state dir, the dead ports. A direct run never
imported it: sys.path[0] is tests/, so this file resolves as the top-level module `romp_load`, not
`tests.romp_load`, and the run had none of that. Measured against a fresh TMPDIR,
`python3 tests/test_credentials.py` left 86 loose tmp* directories where
`python3 -m unittest tests.test_credentials` left none, and one killed mid-test left everything it
made, unmarked, for good. This import is the one every test module makes in every mode, so the
floor lands here: imported under the bare name while the program being run (`__main__`) is a
`test_*.py` file, the bottom of this module puts the checkout root (the parent of this directory) at
the front of sys.path, where `python -m unittest` from the checkout has it, and imports the package.
No cycle: the package's own `from . import romp_load` executes this file a second time as
`tests.romp_load`, whose name skips the bootstrap, and its setdefault of the bare name keeps the
module the test module asked for. The trigger is the main program's name, not the bare import alone,
on purpose: the `-c` snippets a few tests hand a child put tests/ on sys.path to reach load_source and
carry the state root the child must read in ROMP_STATE_DIR (tests/test_kernel_serve_token_mode.py,
tests/test_planner_seen_memo.py, the smoke helper under tests/test_state_dir_override.py); the
package would pop that variable and re-point XDG_STATE_HOME, so those keep the loader they had. In a
module this import goes ABOVE the state preamble: a directory minted before it is untracked and
outside the root, and leaks under a direct run (nine modules had that order and moved on 2026-09-14;
tests/test_state_isolation_order.py holds the order). tests/test_tempdir_hygiene.py's
BareRunLeavesNothing runs a leaking module both ways and counts what is left.
"""
import importlib.util
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.realpath(__file__))
_ROOT = os.path.dirname(_TESTS_DIR)
_SRC = os.path.join(_ROOT, "kernel", "loadsource.py")
_spec = importlib.util.spec_from_file_location("romp_loadsource", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
load_source = _mod.load_source


def _main_is_a_test_module():
    """Is the program being run a `test_*.py` file, a test module run directly? A `-c` program, an
    interactive session and `python -m <module>` (unittest's or pytest's __main__) all say no."""
    name = os.path.basename(getattr(sys.modules.get("__main__"), "__file__", None) or "")
    return name.startswith("test_") and name.endswith(".py")


if __name__ == "romp_load" and _main_is_a_test_module():
    # The direct run's floor (the docstring's last paragraph). Not guarded: a checkout whose tests package
    # will not import has no floor to give, and the run should say so, not leak quietly.
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import tests  # noqa: F401,E402
