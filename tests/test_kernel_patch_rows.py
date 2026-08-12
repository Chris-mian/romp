"""_patch_rows: Claude Code's structuredPatch (toolUseResult) → numbered diff rows with REAL file line numbers
+ context, used for the chat's Edit/MultiEdit diff gutter (the user 2026-06-29). SYNTHETIC fixtures only."""
import os
import unittest
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class PatchRows(unittest.TestCase):
    def test_real_line_numbers_with_context_and_a_hunk_header(self):
        sp = [{
            "oldStart": 10, "oldLines": 4, "newStart": 10, "newLines": 4,
            "lines": [" ctx_before", "-removed_a", "+added_a", " ctx_after"],
        }]
        rows = km._patch_rows(sp)
        # leading @@ header (no numbers), then the lines with real old/new numbers
        self.assertEqual(rows[0], {"sign": "@", "text": "@@ -10 +10 @@", "oldNo": None, "newNo": None})
        self.assertEqual(rows[1], {"sign": " ", "text": "ctx_before", "oldNo": 10, "newNo": 10})
        self.assertEqual(rows[2], {"sign": "-", "text": "removed_a", "oldNo": 11, "newNo": None})
        self.assertEqual(rows[3], {"sign": "+", "text": "added_a", "oldNo": None, "newNo": 11})
        self.assertEqual(rows[4], {"sign": " ", "text": "ctx_after", "oldNo": 12, "newNo": 12})

    def test_multiple_hunks_each_get_their_own_header_and_numbering(self):
        sp = [
            {"oldStart": 1, "newStart": 1, "lines": ["+first"]},
            {"oldStart": 50, "newStart": 51, "lines": ["-gone"]},
        ]
        rows = km._patch_rows(sp)
        heads = [r for r in rows if r["sign"] == "@"]
        self.assertEqual(len(heads), 2)
        self.assertEqual(heads[1]["text"], "@@ -50 +51 @@")
        # the second hunk's removed line numbers from its own oldStart
        gone = [r for r in rows if r["text"] == "gone"][0]
        self.assertEqual(gone["oldNo"], 50)
        self.assertIsNone(gone["newNo"])

    def test_empty_or_malformed_patch_is_safe(self):
        self.assertEqual(km._patch_rows([]), [])
        self.assertEqual(km._patch_rows(None), [])
        self.assertEqual(km._patch_rows([{"lines": ["+x"]}]), [])   # no oldStart/newStart → skipped

    def test_payload_is_capped(self):
        big = [{"oldStart": 1, "newStart": 1, "lines": ["+l%d" % i for i in range(2000)]}]
        rows = km._patch_rows(big)
        self.assertLessEqual(len(rows), 601)


if __name__ == "__main__":
    unittest.main()
