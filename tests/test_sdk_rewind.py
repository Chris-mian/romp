#!/usr/bin/env python3
"""Conversation rewind — the chat's edit-message branch (SDK backend side).

Editing a past user message rewinds the conversation to just before it and sends the edited
text as the next turn, via the CLI's designed `--resume-session-at <record uuid>` flag riding
the SDK's extra_args passthrough (verified live 2026-07-16: the branch is written IN PLACE —
same fsid, new records with parentUuid=target — and a bad target exits 1 loudly, touching
nothing). These tests cover the backend's write-side machinery:

  * the pure helpers (transcript_path / last_record_uuid / rewind_disposition) EXECUTED, since
    the one-shot leaf guard is the crash-safety core: a heal/resume mid-rewind-turn must NOT
    re-apply the flag (that would truncate the very turn it delivered);
  * source pins on the SdkSession/SdkBackend wiring (the input gate that holds the edit turn
    until a rewound client is up, the reconnect that never defers on rewind-held turns, the
    ResultMessage consume, the refused-connect cleanup, and rewind()'s busy/queued refusals).
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend_rw", os.path.join(BIN, "romp_sdk_backend.py")).load_module()
BACKEND_SRC = open(os.path.join(BIN, "romp_sdk_backend.py")).read()


class TranscriptPath(unittest.TestCase):
    def test_encodes_every_non_alphanumeric_as_dash(self):
        # matches the CLI exactly — underscores and spaces included (the underscore-dir lesson)
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "my_proj dir")
            os.makedirs(sub)
            p = sb.transcript_path(sub, "abc-123")
            base = os.path.basename(os.path.dirname(p))
            self.assertNotIn("_", base)
            self.assertNotIn(" ", base)
            self.assertTrue(p.endswith("abc-123.jsonl"))

    def test_realpaths_a_symlinked_launch_dir(self):
        # a symlinked cwd writes transcripts under the PHYSICAL path (the CLI realpaths)
        with tempfile.TemporaryDirectory() as d:
            real = os.path.join(d, "real")
            os.makedirs(real)
            link = os.path.join(d, "link")
            os.symlink(real, link)
            self.assertEqual(sb.transcript_path(link, "x"), sb.transcript_path(real, "x"))


class LastRecordUuid(unittest.TestCase):
    def _write(self, lines):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        f.write("\n".join(lines) + "\n")
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_returns_the_last_uuid_bearing_record(self):
        p = self._write([
            json.dumps({"type": "user", "uuid": "u1"}),
            json.dumps({"type": "assistant", "uuid": "a1"}),
            json.dumps({"type": "last-prompt"}),          # uuid-less trailer — skipped
            json.dumps({"type": "queue-operation"}),
        ])
        self.assertEqual(sb.last_record_uuid(p), "a1")

    def test_missing_and_empty_files_return_empty(self):
        self.assertEqual(sb.last_record_uuid("/nonexistent/nope.jsonl"), "")
        self.assertEqual(sb.last_record_uuid(self._write([""])), "")

    def test_junk_tail_lines_are_skipped(self):
        p = self._write([
            json.dumps({"type": "assistant", "uuid": "a9"}),
            '{"uuid": "trunca',                            # a partial/corrupt line — skipped, not fatal
        ])
        self.assertEqual(sb.last_record_uuid(p), "a9")


class RewindDisposition(unittest.TestCase):
    def test_applies_only_while_the_leaf_is_unmoved(self):
        self.assertEqual(sb.rewind_disposition("t1", "leaf0", "leaf0"), "apply")

    def test_spent_once_the_conversation_moved(self):
        # the rewind turn's own records landed (or a crash-heal resumed mid-turn): re-applying
        # would truncate the delivered turn — the flag is spent, resume plainly
        self.assertEqual(sb.rewind_disposition("t1", "leaf0", "leaf1"), "spent")

    def test_spent_when_the_transcript_is_unreadable(self):
        self.assertEqual(sb.rewind_disposition("t1", "leaf0", ""), "spent")

    def test_none_without_a_pending_rewind(self):
        self.assertEqual(sb.rewind_disposition("", "leaf0", "leaf0"), "none")


class WiringPins(unittest.TestCase):
    def test_options_arms_via_extra_args_one_shot(self):
        # the SDK has no typed field for --resume-session-at → extra_args (designed passthrough),
        # applied only on rewind_disposition's say-so
        self.assertIn('kw["extra_args"] = {"resume-session-at": sess._rewind_to}', BACKEND_SRC)
        self.assertIn('disp = rewind_disposition(sess._rewind_to, sess._rewind_leaf,', BACKEND_SRC)
        self.assertIn('sess._rewind_armed = True', BACKEND_SRC)

    def test_spent_flag_is_cleared_from_session_and_reg(self):
        self.assertIn('elif disp == "spent":', BACKEND_SRC)
        self.assertIn('self._update_reg(sess.sid, rewindTo="", rewindLeaf="")', BACKEND_SRC)

    def test_input_gate_holds_the_edit_until_a_rewound_client_is_up(self):
        # feeding the edit turn to the un-rewound client is the wrong-branch delivery this kills
        self.assertIn("blocked = blocked or bool(self._rewind_to and not self._rewind_armed)", BACKEND_SRC)

    def test_reconnect_never_defers_on_rewind_held_turns(self):
        # rewind-held turns can't start until the reconnect arms them — deferring would deadlock
        self.assertIn("held = bool(self._rewind_to and not self._rewind_armed)", BACKEND_SRC)
        self.assertIn("if self.inflight == 0 and (held or not self._pending):", BACKEND_SRC)

    def test_result_message_consumes_the_flag(self):
        self.assertIn("# the rewind turn settled — the flag is CONSUMED", BACKEND_SRC)

    def test_refused_connect_fails_loudly_and_drops_the_held_edit(self):
        # a CLI exit-1 on the rewind connect: drop flag + queue head, toast, reconnect plainly —
        # never a crash-loop (the flag would re-apply forever: the leaf never moved)
        self.assertIn("if self._rewind_armed and not connected:", BACKEND_SRC)
        self.assertIn("def _rewind_failed(self, exc):", BACKEND_SRC)
        self.assertIn("your edited message was NOT sent", BACKEND_SRC)

    def test_rewind_refuses_busy_compacting_and_queued(self):
        self.assertIn("def rewind(self, sid: str, target_uuid: str, text: str)", BACKEND_SRC)
        self.assertIn("if self.busy(sid) or self.compacting(sid):", BACKEND_SRC)
        self.assertIn('return False, "messages are queued for this session', BACKEND_SRC)

    def test_rewind_persists_the_flag_before_ensuring_the_thread(self):
        # a fresh session thread seeds _rewind_to from the reg — writing after _ensure could race
        # the first connect and strand the held queue
        i_reg = BACKEND_SRC.index("self._update_reg(sid, rewindTo=target_uuid, rewindLeaf=leaf)")
        i_ensure = BACKEND_SRC.index("s = self._ensure(sid)", i_reg - 2000)
        self.assertLess(i_reg, i_ensure)

    def test_session_seeds_rewind_state_from_the_reg(self):
        self.assertIn('self._rewind_to = reg.get("rewindTo") or ""', BACKEND_SRC)
        self.assertIn('self._rewind_leaf = reg.get("rewindLeaf") or ""', BACKEND_SRC)


if __name__ == "__main__":
    unittest.main()
