#!/usr/bin/env python3
"""The SessionBackend contract (the user 2026-06-26): tmux + SDK behind ONE clean session API, and NOTHING
above the backend shells tmux. These tests pin (a) both backends honor the ABC and (b) the no-raw-tmux
guard — so a future tmux leak into the higher layers fails CI instead of silently rotting the abstraction.
"""
import os
import re
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_session_backend", os.path.join(BIN, "romp_session_backend.py")).load_module()

ABSTRACT = sorted(sb.SessionBackend.__abstractmethods__)


class AbcContract(unittest.TestCase):
    def test_abc_lists_the_expected_contract(self):
        for m in ("owns", "live_sessions", "send", "interrupt", "set_model", "set_mode", "set_effort",
                  "spawn", "resume", "kill", "rename",
                  "pending_queued", "live_atoms", "prune_live", "on_ask", "current_ask"):
            self.assertIn(m, ABSTRACT, "SessionBackend must declare %s as part of the contract" % m)

    def test_coordination_methods_exist_as_concrete_defaults_for_now(self):
        # working_note/set_working_note/wake are part of the target contract but start as concrete no-op
        # defaults (the SDK gap is filled in P3); assert they exist and the base is a safe no-op.
        for m in ("working_note", "set_working_note", "wake"):
            self.assertTrue(hasattr(sb.SessionBackend, m), "the ABC declares %s (concrete default for now)" % m)
        self.assertNotIn("wake", ABSTRACT, "coordination methods are concrete defaults until P3")

    def test_sdk_backend_honors_every_abstract_method(self):
        # SdkBackend is SDK-gated so it can't import the ABC when the dep is absent; it conforms by
        # duck-typing. Assert at the SOURCE level (no SDK dep needed) that it DEFINES each abstract method,
        # so the duck-typing can't silently drift from the contract.
        src = open(os.path.join(BIN, "romp_sdk_backend.py"), encoding="utf-8").read()
        defs = set(re.findall(r"\n    def ([a-z_]+)\s*\(", src))
        for m in ABSTRACT:
            self.assertIn(m, defs, "SdkBackend must implement the SessionBackend method %s" % m)


# quoted-literal markers — a raw `["tmux"` subprocess list, a tmux SUBCOMMAND string arg, or a tmux @-var
# NAME string. Matching only QUOTED literals (not bare words) means prose in comments/docstrings that merely
# mentions "send-keys" or "@claude-state" is NOT flagged — only actual tmux code is.
_TMUX_MARKERS = [
    (re.compile(r'\[\s*["\']tmux["\']'), "raw tmux subprocess list"),
    (re.compile(r'["\'](?:send-keys|list-sessions|paste-buffer|capture-pane|set-buffer|kill-session|'
                r'rename-session|display-message|pane_in_mode)["\']'), "tmux subcommand literal"),
    (re.compile(r'["\']@(?:claude|romp|identity)-[a-z-]*["\']'), "tmux @-var literal"),
]


def _scan_tmux(text, skip_span=None):
    """Lines (1-based) of `text` that hold a raw-tmux marker in CODE (a trailing #comment is dropped first),
    excluding the optional [start,end) line span. Returns [(lineno, desc, line)]."""
    out = []
    for i, line in enumerate(text.split("\n")):
        if skip_span and skip_span[0] <= i < skip_span[1]:
            continue
        code = line.split("#", 1)[0]
        for rx, desc in _TMUX_MARKERS:
            if rx.search(code):
                out.append((i + 1, desc, line.strip()[:90]))
    return out


class NoRawTmuxOutsideTmuxBackend(unittest.TestCase):
    """The leak guard (the user 2026-06-26): raw tmux lives ONLY in bin/romp-kernel's TmuxBackend class; the
    higher layers (build_*, the _drive dispatch, GET /sessions, the postal bus) speak the SessionBackend API.
    A future tmux call shelled outside the class fails CI instead of silently re-coupling the kernel to tmux."""

    KERNEL = os.path.join(BIN, "romp-kernel")

    def _span(self, lines):
        start = next(i for i, l in enumerate(lines) if l.startswith("class TmuxBackend("))
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i] and lines[i][0] not in " \t#)"), len(lines))
        return start, end

    def test_no_raw_tmux_outside_the_class(self):
        lines = open(self.KERNEL, encoding="utf-8").read().split("\n")
        leaks = _scan_tmux("\n".join(lines), skip_span=self._span(lines))
        self.assertEqual(leaks, [], "raw tmux leaked outside TmuxBackend:\n"
                         + "\n".join("  L%d [%s]: %s" % x for x in leaks))

    def test_the_class_actually_owns_the_raw_tmux(self):
        # so the span exclusion above isn't vacuously passing — the raw tmux really IS in the class
        lines = open(self.KERNEL, encoding="utf-8").read().split("\n")
        start, end = self._span(lines)
        body = "\n".join(lines[start:end])
        self.assertIn('["tmux"]', body, "TmuxBackend holds the raw tmux subprocess primitives")
        self.assertIn('"send-keys"', body)
        self.assertIn('"list-sessions"', body)


class PostalSessionControlOffTmux(unittest.TestCase):
    """P2 + the P3 working-note: the postal bus ENUMERATES sessions and PUBLISHES its working-note through the
    kernel, never tmux. (Delivery's live pane-inject, the tmux status-bar mail/peer chrome, the @claude-state
    picker-grace, and the self-identity fallback are the remaining P3 relocation — NOT yet asserted here; this
    guard pins only what is already off tmux so it can't regress.)"""

    POSTAL = os.path.join(BIN, "romp-postal")

    def test_session_enumeration_goes_through_the_kernel(self):
        src = open(self.POSTAL, encoding="utf-8").read()
        self.assertNotIn('"list-sessions"', src, "local_agents reads the kernel's GET /sessions, not tmux list-sessions")
        self.assertIn("_kernel_sessions", src, "postal enumerates sessions via the kernel")

    def test_working_note_goes_through_the_kernel_not_a_tmux_var(self):
        src = open(self.POSTAL, encoding="utf-8").read()
        self.assertNotIn('"@romp-working"', src, "set_working publishes via the kernel store (POST /working), not the @romp-working var")
        self.assertIn('"/working"', src, "postal POSTs the working-note to the kernel")


if __name__ == "__main__":
    unittest.main()
