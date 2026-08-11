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
                       "_alive_sessions": km._alive_sessions, "_sessions": km._sessions}
        km.jd.STATE = Path(self.td.name)
        km._kept_open = set()

    def tearDown(self):
        km.jd.STATE = self._saved["STATE"]
        km._kept_open = self._saved["_kept_open"]
        km._alive_sessions = self._saved["_alive_sessions"]
        km._sessions = self._saved["_sessions"]
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

    # ── _gc_session_order: self-clean GONE sids, keep everything still around ───────────────────────
    def test_gc_prunes_gone_sids_keeps_survivors_in_order(self):
        km._write_session_order([A, B, C, D])
        km._gc_session_order({A, C})                       # B, D are gone (not alive, no transcript)
        self.assertEqual(self.order_file(), [A, C])        # gone sids dropped; survivors keep their order

    def test_gc_is_a_noop_when_nothing_is_gone(self):
        km._write_session_order([A, B, C])
        km._gc_session_order({A, B, C, D})                 # all present (D just isn't in the order yet)
        self.assertEqual(self.order_file(), [A, B, C])     # unchanged

    def test_chat_push_prunes_a_truly_gone_session_from_the_file(self):
        km._write_session_order([A, B, C])
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(C, 300)]    # B not alive
        km._sessions = lambda now: [sess(A, 100), sess(C, 300)]               # B's transcript gone → GONE
        km._chat_tab_sessions(0, {})
        self.assertEqual(self.order_file(), [A, C])        # B pruned on a chat push (self-cleaning)

    def test_chat_push_keeps_a_dead_but_in_window_session(self):
        km._write_session_order([A, B, C])
        km._alive_sessions = lambda now, tmux: [sess(A, 100), sess(C, 300)]    # B not alive...
        km._sessions = lambda now: [sess(A, 100), sess(B, 200), sess(C, 300)]  # ...but B is still in-window
        km._chat_tab_sessions(0, {})
        self.assertEqual(self.order_file(), [A, B, C])     # dead-but-in-window B keeps its slot

    # ── fork identity: a /clear/revive (new fsid, SAME anchor) keeps its slot, never jumps to the END ──────
    def test_a_fork_slots_after_its_anchor_not_at_the_end(self):
        km._write_session_order([A, B, C])
        A2 = "aaaaaaaa-0000-0000-0000-0000000000a2"        # A forks → new fsid, same anchor A
        def f(sid, anchor):
            return {"sid": sid, "name": sid[:8], "anchor": anchor, "path": "/x/%s.jsonl" % sid, "mtime": 1}
        out = self.sids(km._ordered([f(A, A), f(B, B), f(C, C), f(A2, A)]))
        self.assertEqual(self.order_file(), [A, A2, B, C])  # A2 inherits A's place, not the END
        self.assertEqual(out, [A, A2, B, C])

    def test_a_genuinely_new_session_still_appends_at_the_end(self):
        km._write_session_order([A, B])
        def f(sid, anchor):
            return {"sid": sid, "name": sid[:8], "anchor": anchor, "path": "/x/%s.jsonl" % sid, "mtime": 1}
        D2 = "dddddddd-0000-0000-0000-0000000000d2"
        self.sids(km._ordered([f(A, A), f(B, B), f(D2, D2)]))   # D2 is its own anchor → no sibling
        self.assertEqual(self.order_file(), [A, B, D2])

    # ── the silent-reorder bug: a SELF-anchored fork (discover's lexical scan anchored it to itself) must
    #    STILL inherit its session's slot by NAME, not jump to the END (the user 2026-06-29) ─────────────
    def test_a_self_anchored_fork_inherits_by_NAME_not_the_end(self):
        # A relaunch/clear of the session named "obsidian" mints a new fsid that — because it has its OWN
        # names entry, scanned first — discover SELF-anchors (anchor == its own sid). The OLD inheritance
        # keyed on that anchor, so it found no sibling and appended at the END (obsidian jumped). Keying on
        # the stable NAME, the fork lands right after its same-name sibling instead.
        km._write_session_order([A, B, C])
        OBS2 = "00000000-0000-0000-0000-00000000ob2"          # lexically-small fork → discover self-anchors it
        def f(sid, name, anchor):
            return {"sid": sid, "name": name, "anchor": anchor, "path": "/x/%s.jsonl" % sid, "mtime": 1}
        # A is the original "obsidian"; OBS2 is its relaunch fork, self-anchored, but SAME name "obsidian"
        out = self.sids(km._ordered([f(A, "obsidian", A), f(B, "bee", B), f(C, "see", C),
                                     f(OBS2, "obsidian", OBS2)]))
        self.assertEqual(self.order_file(), [A, OBS2, B, C], "the fork inherits obsidian's slot, not the END")
        self.assertEqual(out, [A, OBS2, B, C])

    def test_relaunch_transfers_the_slot_across_a_chat_push_gc(self):
        # End-to-end through _chat_tab_sessions: the OLD fsid is dead-but-in-window while the relaunch fork is
        # alive; ordering must run BEFORE the GC so the fork inherits the slot in the SAME build (a GC-first
        # order would drop the old fsid first, leaving the fork no sibling → it would jump to the END).
        km._write_session_order([A, B, C])                     # A = "obsidian" original, in slot 0
        OBS2 = "00000000-0000-0000-0000-00000000ob2"
        def f(sid, name):
            return {"sid": sid, "name": name, "path": "/x/%s.jsonl" % sid, "mtime": 1}
        # the dead original A is NOT in the live input, so _ordered resolves its NAME from the names registry
        # (in production its names entry persists across a relaunch — both fsids keep one). Stub that lookup.
        reg = {A: "obsidian", OBS2: "obsidian", B: "bee", C: "see"}
        saved_name_of = km._name_of
        km._name_of = lambda sid: reg.get(sid)
        self.addCleanup(lambda: setattr(km, "_name_of", saved_name_of))
        # A is no longer alive (relaunched) but its transcript is still in-window; OBS2 is the live fork
        km._alive_sessions = lambda now, tmux: [f(OBS2, "obsidian"), f(B, "bee"), f(C, "see")]
        km._sessions = lambda now: [f(A, "obsidian"), f(OBS2, "obsidian"), f(B, "bee"), f(C, "see")]
        out = self.sids(km._chat_tab_sessions(0, {}))
        # OBS2 inherited slot 1 (right after A); A is dead-but-in-window so it keeps its slot in the FILE
        self.assertEqual(self.order_file(), [A, OBS2, B, C])
        # the LIVE tabs are OBS2, B, C (dead A isn't rendered) — OBS2 sits FIRST in obsidian's slot, NOT at
        # the end behind B and C, which is where the self-anchored-fork bug pushed it.
        self.assertEqual(out, [OBS2, B, C], "the fork renders in obsidian's slot (first), not at the end")


if __name__ == "__main__":
    unittest.main()
