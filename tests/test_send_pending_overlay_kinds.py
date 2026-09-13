"""T389: the chat's pending-send rule excludes the kernel's live overlay cards from the anchors a send may take (send-pending.ts
OVERLAY_KINDS); the kernel names those kinds in one place (kernel.py _OVERLAY_KINDS). The two lists are one list: a kind
added on either side without the other lets a send anchor on a card that sits after the queued group, and the message
draws twice until it lands (the shape the T389 lab saw)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class OverlayKindsAgree(unittest.TestCase):
    def test_the_client_anchors_rule_and_the_kernels_overlay_kinds_are_one_list(self):
        ts = open(os.path.join(ROOT, "ui", "webview", "send-pending.ts")).read()
        py = open(os.path.join(ROOT, "kernel", "kernel.py")).read()
        m_ts = re.search(r'export const OVERLAY_KINDS: ReadonlySet<string> = new Set\(\[([^\]]*)\]\);', ts)
        m_py = re.search(r'_OVERLAY_KINDS = frozenset\(\(([^)]*)\)\)', py)
        self.assertIsNotNone(m_ts, "send-pending.ts names the overlay kinds")
        self.assertIsNotNone(m_py, "kernel.py names the overlay kinds")
        ts_kinds = sorted(re.findall(r'"([a-zA-Z]+)"', m_ts.group(1)))
        py_kinds = sorted(re.findall(r'"([a-zA-Z]+)"', m_py.group(1)))
        self.assertEqual(ts_kinds, py_kinds, "one list on both sides")
        self.assertIn("apiError", ts_kinds); self.assertIn("queued", ts_kinds)
        self.assertRegex(ts, r'const stableUuid = \(e: TailEvent\): boolean => !!e\.uuid && !isOptimisticUuid\(e\.uuid\) && !isKernelEchoUuid\(e\.uuid\) && !OVERLAY_KINDS\.has\(e\.kind\);',
                         "the anchor rule reads the list")


if __name__ == "__main__":
    unittest.main()
