#!/usr/bin/env python3
"""A slash command that fires lifecycle hooks (e.g. /compact) echoes each one back in its OUTPUT as
"PreCompact [~/.claude/hooks/tmux-status.sh] completed successfully" — internal plumbing the user never wants
to see (the user 2026-06-30: "what is this pre-compact thing?"). build_session strips those notices from a
command's output text via _strip_hook_notices; when nothing else remains, the atom is dropped entirely (the
✦ Compacted boundary already marks the compaction). This tests the stripper directly.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_hn", os.path.join(BIN, "romp-kernel")).load_module()


class StripHookNotices(unittest.TestCase):
    def test_compact_output_reduces_to_its_lead(self):
        txt = ("Compacted PreCompact [~/.claude/hooks/tmux-status.sh] completed successfully "
               "PostCompact [~/.claude/hooks/tmux-status.sh] completed successfully")
        self.assertEqual(km._strip_hook_notices(txt), "Compacted")

    def test_output_that_is_only_notices_becomes_empty_so_the_atom_is_dropped(self):
        txt = "PreCompact [~/.claude/hooks/tmux-status.sh] completed successfully"
        self.assertEqual(km._strip_hook_notices(txt), "", "nothing but notices → empty → build_session drops it")

    def test_real_prose_is_untouched(self):
        # no bracketed-path notice → left exactly as-is (whitespace-normalized)
        s = "The build completed successfully after two retries."
        self.assertEqual(km._strip_hook_notices(s), s)

    def test_prose_mentioning_a_bracketed_path_without_the_notice_shape_is_kept(self):
        s = "Wrote the config [prod] and moved on."
        self.assertEqual(km._strip_hook_notices(s), s)


if __name__ == "__main__":
    unittest.main()
