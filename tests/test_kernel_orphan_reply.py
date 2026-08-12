#!/usr/bin/env python3
"""Kernel side of orphan-reply durability (the user 2026-07-21): _orphan_replies reads the durable markers the
SDK backend wrote (append_orphan_reply), and build_session interleaves the lost assistant text back at its
timestamp as a normal assistant bubble, DEDUP'd against what the transcript DID keep so a retry that re-replied
never doubles. SYNTHETIC only."""
import inspect
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
km = SourceFileLoader("romp_kernel_orphan", os.path.join(BIN, "romp-kernel")).load_module()
sb = SourceFileLoader("romp_sdk_backend_orphan_k", os.path.join(BIN, "romp_sdk_backend.py")).load_module()


class OrphanReplyReader(unittest.TestCase):
    def test_write_then_read_returns_orphans_oldest_first(self):
        sid = "TESTHOST-orphan-1"
        (km.jd.STATE / "states").mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "states" / (sid + ".jsonl")).unlink(missing_ok=True)
        sb.append_orphan_reply(km.jd.STATE, sid, "u2", "second", t=2000)
        sb.append_orphan_reply(km.jd.STATE, sid, "u1", "first", t=1000)
        got = km._orphan_replies(sid)
        self.assertEqual(got, [{"t": 1000, "uuid": "u1", "text": "first"},
                               {"t": 2000, "uuid": "u2", "text": "second"}])

    def test_no_file_or_blank_text_is_empty(self):
        self.assertEqual(km._orphan_replies("TESTHOST-nope-orphan"), [])
        sid = "TESTHOST-orphan-blank"
        (km.jd.STATE / "states" / (sid + ".jsonl")).unlink(missing_ok=True)
        sb.append_orphan_reply(km.jd.STATE, sid, "u", "   ", t=10)   # whitespace-only → not surfaced
        self.assertEqual(km._orphan_replies(sid), [])

    def test_orphan_markers_do_not_disturb_the_plain_state_reader(self):
        sid = "TESTHOST-orphan-2"
        (km.jd.STATE / "states" / (sid + ".jsonl")).unlink(missing_ok=True)
        sb.append_state(km.jd.STATE, sid, "working", t=10)
        sb.append_orphan_reply(km.jd.STATE, sid, "u", "a lost reply", t=20)
        self.assertEqual(km._last_state(sid)[0], "working")     # the orphan line has no "state" key → skipped

    def test_atom_md_joins_text_blocks_only(self):
        a = {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "x"}, {"type": "text", "text": "hello "},
            {"type": "tool_use", "name": "Bash"}, {"type": "text", "text": "world"}]}}
        self.assertEqual(km._atom_md(a), "hello world")


class OrphanInterleaveAndDedup(unittest.TestCase):
    def test_build_session_interleaves_the_orphan_as_an_assistant_bubble(self):
        src = inspect.getsource(km.build_session)
        self.assertIn("orphans = _orphan_replies(sid)", src)
        # interleaved by timestamp in the same flush as the recovery note, as a normal assistant bubble
        self.assertIn('events.append({"kind": "assistant", "md": _o["text"], "orphaned": True,', src)
        self.assertIn('"uuid": "orphan:%s" % (_o["uuid"] or _o["t"]), "ts": iso(_o["t"])})', src)

    def test_the_orphan_is_deduped_against_what_the_disk_kept(self):
        src = inspect.getsource(km.build_session)
        # a disk-text set built from THIS session's assistant atoms (skipping the error record)
        self.assertIn('if _a.get("type") == "assistant" and not _a.get("isApiError"):', src)
        self.assertIn("_disk_texts.add(_tx)", src)
        # exact OR either-way prefix match → a retry that re-replied (full text, or the partial's completion) skips
        self.assertIn("if _ot in _disk_texts or any(dt.startswith(_ot) or _ot.startswith(dt) for dt in _disk_texts):", src)


if __name__ == "__main__":
    unittest.main()
