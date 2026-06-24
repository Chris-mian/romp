#!/usr/bin/env python3
"""Session order (chat tabs + timeline lanes) is a PURE function of session-order.json — it must NEVER
auto-reshuffle on activity (mtime / status / death), only a user drag reorders (the user 2026-06-24:
"the only thing that should reorder them is the user clicking and dragging").

Pins bin/romp-kernel's _ordered / _ordered_alive / _chat_tab_sessions / _timeline_sessions and the
non-destructive _merge_session_order. Synthetic fleet only: placeholder UUIDs, no real session data.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_order", os.path.join(BIN, "romp-kernel")).load_module()

A = "aaaaaaaa-0000-0000-0000-000000000001"
B = "bbbbbbbb-0000-0000-0000-000000000002"
C = "cccccccc-0000-0000-0000-000000000003"
D = "dddddddd-0000-0000-0000-000000000004"


def sess(sid, mtime):
    return {"sid": sid, "name": sid[:8], "path": "/x/%s.jsonl" % sid, "mtime": mtime}


class SessionOrder(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        # redirect every state read/write (_session_order / _write_session_order) into a temp dir
        self._saved = {"STATE": km.jd.STATE, "_kept_open": km._kept_open,
                       "_alive_sessions": km._alive_sessions, "_sessions": km._sessions,
                       "_hidden_tabs": km._hidden_tabs}
        km.jd.STATE = Path(self.td.name)
        km._kept_open = set()
        km._hidden_tabs = lambda: set()

    def tearDown(self):
        km.jd.STATE = self._saved["STATE"]
        km._kept_open = self._saved["_kept_open"]
        km._alive_sessions = self._saved["_alive_sessions"]
        km._sessions = self._saved["_sessions"]
        km._hidden_tabs = self._saved["_hidden_tabs"]
        self.td.cleanup()

    def order_file(self):
        return json.loads((km.jd.STATE / "session-order.json").read_text())

    def sids(self, rows):
        return [s["sid"] for s in rows]

    # ── _ordered: pure positional, freeze-on-first-sight, ZERO activity input ──────────────────────
    def test_appends_newcomers_in_input_order_and_persists(self):
        out = self.sids(km._ordered([sess(A, 100), sess(B, 200), sess(C, 300)]))
        self.assertEqual(out, [A, B, C])
        self.assertEqual(self.order_file(), [A, B, C])     # frozen to disk

    def test_stable_across_mtime_changes_the_core_bug(self):
        km._ordered([sess(A, 100), sess(B, 200), sess(C, 300)])     # seed
        # B "works" hard (mtime spikes highest), C goes quiet (mtime lowest) — order must NOT move
        out = self.sids(km._ordered([sess(A, 100), sess(B, 99999), sess(C, 5)]))
        self.assertEqual(out, [A, B, C])

    def test_saved_order_wins_over_mtime(self):
        km._write_session_order([C, A, B])
        out = self.sids(km._ordered([sess(A, 999), sess(B, 1), sess(C, 500)]))
        self.assertEqual(out, [C, A, B])                   # disk order honored, mtime ignored

    def test_newcomer_lands_at_end_even_if_newest_by_activity(self):
        km._write_session_order([A, B])
        out = self.sids(km._ordered([sess(A, 1), sess(B, 2), sess(C, 99999)]))
        self.assertEqual(out, [A, B, C])                   # C is newest but appends at END, never jumps to top

    # ── _chat_tab_sessions / _timeline_sessions: stable through activity + death ───────────────────
    def test_chat_tabs_keep_order_when_a_session_dies(self):
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(B, 200), sess(C, 300)]
        km._sessions = lambda now: [sess(A, 100), sess(B, 200), sess(C, 300)]
        self.assertEqual(self.sids(km._chat_tab_sessions(0, {})), [A, B, C])
        # B dies (leaves the alive set); not kept-open → its tab drops, A & C keep their relative order
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(C, 300)]
        self.assertEqual(self.sids(km._chat_tab_sessions(0, {})), [A, C])

    def test_timeline_lanes_never_reshuffle_on_activity(self):
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(B, 200)]
        km._sessions = lambda now: [sess(A, 100), sess(B, 200), sess(C, 50), sess(D, 60)]
        self.assertEqual(self.sids(km._timeline_sessions(0, {})), [A, B, C, D])
        # B works hard + dead lane C's transcript gets touched (both mtimes spike) — lanes must hold
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(B, 99999)]
        km._sessions = lambda now: [sess(A, 100), sess(B, 99999), sess(C, 88888), sess(D, 60)]
        self.assertEqual(self.sids(km._timeline_sessions(0, {})), [A, B, C, D])

    # ── _merge_session_order: a drag moves ONLY what it touched ────────────────────────────────────
    def test_chat_drag_leaves_timeline_only_lanes_in_place(self):
        km._write_session_order([A, B, C, D])              # B, D are timeline-only dead lanes
        # chat shows A & C; user drags them to [C, A] — B and D must keep their slots
        self.assertEqual(km._merge_session_order([C, A]), [C, B, A, D])

    def test_merge_appends_brand_new_sids_at_end(self):
        km._write_session_order([A, B])
        self.assertEqual(km._merge_session_order([B, A, C]), [B, A, C])

    def test_merge_on_empty_existing_is_incoming(self):
        self.assertEqual(km._merge_session_order([A, B, C]), [A, B, C])

    def test_merge_dedupes_and_drops_non_strings(self):
        km._write_session_order([A, B])
        self.assertEqual(km._merge_session_order([B, A, A, 7, None]), [B, A])


if __name__ == "__main__":
    unittest.main()
