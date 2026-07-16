#!/usr/bin/env python3
"""Conversation rewind — the kernel's rewindSend drive op + its transcript validation.

_rewind_target picks WHERE an edit of user record U cuts the conversation: U's nearest
user/assistant ancestor (the record types the CLI addresses; attachments are spine nodes but not
targets). It refuses, with a human reason, everything the CLI would refuse loudly (and one thing
it wouldn't: a stale click on an already-abandoned branch): a missing record, a pre-compaction
record ("No message found" — verified live 2026-07-16), and the conversation's first message.
Exercised HERE against synthetic transcripts, so the backend's failure path stays reserved for
genuine races. Plus source pins on the drive-op arm (SDK-only gate, busy gate, warn toasts)."""
import inspect
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_rw", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _rec(typ, uuid, parent, text="x", **extra):
    r = {"type": typ, "uuid": uuid, "parentUuid": parent, "sessionId": SID,
         "timestamp": "2026-07-16T10:00:00Z"}
    if typ in ("user", "assistant"):
        r["message"] = {"role": typ, "content": [{"type": "text", "text": text}]}
    r.update(extra)
    return r


class RewindTarget(unittest.TestCase):
    def _transcript(self, recs):
        d = tempfile.mkdtemp()
        p = os.path.join(d, SID + ".jsonl")
        with open(p, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        return p

    def _base(self):
        return [
            _rec("user", "u1", None, "first ask"),
            _rec("assistant", "a1", "u1", "first reply"),
            _rec("user", "u2", "a1", "second ask"),
            _rec("assistant", "a2", "u2", "second reply"),
        ]

    def test_editing_a_message_cuts_at_the_previous_assistant(self):
        p = self._transcript(self._base())
        self.assertEqual(km._rewind_target(p, SID, "u2"), ("a1", None))

    def test_attachment_spine_nodes_are_skipped_not_targeted(self):
        # the CLI parent-chains attachments between the user record and the reply — they're on the
        # spine but aren't addressable messages, so the walk crosses them to the real ancestor
        recs = self._base() + [
            _rec("attachment", "att1", "a2", attachment={"type": "other"}),
            _rec("user", "u3", "att1", "third ask"),
        ]
        p = self._transcript(recs)
        self.assertEqual(km._rewind_target(p, SID, "u3"), ("a2", None))

    def test_the_first_message_has_nothing_to_rewind_to(self):
        p = self._transcript(self._base())
        target, err = km._rewind_target(p, SID, "u1")
        self.assertIsNone(target)
        self.assertIn("first message", err)

    def test_a_record_off_the_active_chain_is_refused(self):
        # u2/a2 were already rewound away (u3 branches from a1) — a stale window's click on the
        # old bubble must not truncate the NEW branch
        recs = self._base() + [_rec("user", "u3", "a1", "second ask, edited"),
                               _rec("assistant", "a3", "u3", "branch reply")]
        p = self._transcript(recs)
        target, err = km._rewind_target(p, SID, "u2")
        self.assertIsNone(target)
        self.assertIn("already rewound", err)

    def test_a_pre_compaction_record_is_refused(self):
        # the CLI only loads post-boundary records; a pre-boundary target exits 1 "No message found"
        recs = self._base() + [
            _rec("system", "cb1", None, subtype="compact_boundary", logicalParentUuid="a2",
                 compactMetadata={"preservedSegment": {"tailUuid": "a2"}}),
            _rec("user", "cs1", "cb1", "summary", isCompactSummary=True),
            _rec("user", "u3", "cs1", "post-compaction ask"),
            _rec("assistant", "a3", "u3", "post-compaction reply"),
        ]
        p = self._transcript(recs)
        target, err = km._rewind_target(p, SID, "u2")
        self.assertIsNone(target)
        self.assertIn("compaction", err)
        # while the FIRST post-compaction message cuts at the replayed summary record — a user-type
        # record the CLI addresses fine (verified live: user-record uuids are valid targets)
        self.assertEqual(km._rewind_target(p, SID, "u3"), ("cs1", None))

    def test_a_missing_record_is_refused(self):
        p = self._transcript(self._base())
        target, err = km._rewind_target(p, SID, "77777777-8888-9999-aaaa-bbbbbbbbbbbb")
        self.assertIsNone(target)
        self.assertIn("isn't in the transcript", err)


class DriveOpPins(unittest.TestCase):
    def test_rewind_send_is_a_drive_op(self):
        src = inspect.getsource(km._drive)
        self.assertIn('"rewindSend"', src)   # in ID_OPS → routed by session id
        self.assertIn('elif t == "rewindSend" and msg.get("uuid") and msg.get("text"):', src)

    def test_refusals_warn_toast_and_never_send(self):
        src = inspect.getsource(km._drive)
        self.assertIn('err = _rewind_send(sid, str(msg["uuid"]), str(msg["text"]))', src)
        self.assertIn('client["send"](json.dumps({"type": "warn", "text": err}))', src)

    def test_rewind_send_gates_on_backend_and_busy(self):
        src = inspect.getsource(km._rewind_send)
        self.assertIn('if not hasattr(be, "rewind"):', src)          # SDK-only (tmux has Esc Esc natively)
        self.assertIn("if _ops_gate(sid):", src)                     # busy/compacting/parked-queue → refuse
        self.assertIn("target, err = _rewind_target(", src)          # transcript validation before the backend

    def test_no_optimistic_kernel_echo_for_a_rewind(self):
        # the edit lands MID-chat at the branch point, not at the tail — the client overlay owns the gap
        src = inspect.getsource(km._drive)
        arm = src[src.index('elif t == "rewindSend"'):src.index('elif t == "interrupt"')]
        self.assertNotIn("_send_or_park", arm)


if __name__ == "__main__":
    unittest.main()
