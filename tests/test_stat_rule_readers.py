#!/usr/bin/env python3
"""One stat rule on both sides of the mail door and in the fail-closed readers (2026-09-14): the bus and the kernel tell a
MISSING record (ENOENT, ENOTDIR, EBADF, ELOOP) from an UNREADABLE one (any other stat error) by the same errno tuple, never by
Path.exists(), whose ignored set CPython 3.14 widened to every error; a directory that cannot be read is never empty; a task
directory that exists but cannot be listed raises to its caller. Each fault staged for real (a mode-000 directory, a symlink
loop), never a stub of the call that would raise. Hermetic: temp roots; synthetic sids."""
import os
import tempfile
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_ROOT = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _ROOT
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.makedirs(os.path.join(_ROOT, "romp"), exist_ok=True)
Path(_ROOT, "romp", "session-hosts").write_text("off\n")
km = load_source("romp_kernel_stat_rule", os.path.join(BIN, "romp-kernel"))
jd = km.jd
pm = load_source("romp_postal_stat_rule", os.path.join(BIN, "romp-postal-service"))

SID = "11111111-2222-4333-8444-0000000000e1"
ROOT_ONLY = hasattr(os, "geteuid") and os.geteuid() == 0


class OneRuleOnBothSides(unittest.TestCase):
    def test_the_bus_and_the_kernel_share_the_missing_errno_tuple(self):
        self.assertEqual(tuple(pm.REG_MISSING_ERRNOS), tuple(km._REG_MISSING_ERRNOS), "the two sides must agree, or the bus holds mail while the tab paints mail on")

    def test_a_symlink_loop_reg_is_missing_on_both_sides(self):
        d = pm.SESSION_FLAGS.parent / "sdk"; d.mkdir(parents=True, exist_ok=True)
        p = d / (SID + ".json")
        os.symlink(p.name, p)
        try:
            self.assertEqual(pm._thread_of(SID), "", "the bus: an ordinary session")
            saved = jd.STATE; jd._rebind_state(pm.SESSION_FLAGS.parent)
            try:
                self.assertEqual(km._thread_reg_read(SID)[0], "missing", "the kernel: the same word")
            finally:
                jd._rebind_state(saved)
        finally:
            p.unlink()

    def test_an_unreadable_sdk_directory_is_unreadable_on_both_sides(self):
        if ROOT_ONLY:
            self.skipTest("root reads through chmod 000")
        d = pm.SESSION_FLAGS.parent / "sdk"; d.mkdir(parents=True, exist_ok=True)
        (d / (SID + ".json")).write_text("{}")
        os.chmod(d, 0)
        try:
            self.assertEqual(pm._thread_of(SID), pm.THREAD_REG_UNREADABLE)
            saved = jd.STATE; jd._rebind_state(pm.SESSION_FLAGS.parent)
            try:
                km._thread_reg_memo.pop(SID, None)
                self.assertEqual(km._thread_reg_read(SID)[0], "unreadable")
            finally:
                jd._rebind_state(saved)
        finally:
            os.chmod(d, 0o755); (d / (SID + ".json")).unlink()


class UnknownIsNeverEmpty(unittest.TestCase):
    def test_dir_empty_answers_true_false_and_none(self):
        base = Path(tempfile.mkdtemp())
        self.assertTrue(pm._dir_empty(base / "absent"), "an absent directory holds nothing")
        (base / "e").mkdir(); self.assertTrue(pm._dir_empty(base / "e"))
        (base / "f").mkdir(); (base / "f" / "x").write_text(""); self.assertFalse(pm._dir_empty(base / "f"))
        (base / "file").write_text(""); self.assertFalse(pm._dir_empty(base / "file"), "a file is not an empty directory")
        if ROOT_ONLY:
            return
        os.chmod(base / "f", 0)
        try:
            self.assertIsNone(pm._dir_empty(base / "f"), "unreadable: unknown, never empty")
        finally:
            os.chmod(base / "f", 0o755)

    def _box_with_unread_mail(self, sid):
        newd = pm.MAILROOT / sid / "new"; newd.mkdir(parents=True, exist_ok=True)
        (pm.MAILROOT / sid / "cur").mkdir(exist_ok=True); (pm.MAILROOT / sid / "tmp").mkdir(exist_ok=True)
        (newd / "m1").write_text("From: alice\n\nhi\n")
        return newd

    def test_an_unsearchable_inbox_with_unread_mail_keeps_its_marker_through_every_writer(self):
        """The medium of round two's read: _mark_pending read an unlistable new/ as no mail and UNLINKED the marker the retry
        arm had just kept, and serve() drives _reconcile_markers over every box at each bus start; the unread mail stranded
        with no wake. Executed on the real fault: the marker stands after _mark_pending, _reconcile_markers and _retry_pending."""
        if ROOT_ONLY:
            self.skipTest("root reads through chmod 000")
        sid = "33333333-2222-4333-8444-0000000000e3"
        newd = self._box_with_unread_mail(sid)
        pm._mark_pending(sid)
        self.assertTrue((pm.MAILPENDING / sid).exists(), "unread mail: the marker stands")
        os.chmod(newd, 0)
        try:
            pm._mark_pending(sid)
            self.assertTrue((pm.MAILPENDING / sid).exists(), "unknown inbox: the marker stands after _mark_pending")
            pm._reconcile_markers()
            self.assertTrue((pm.MAILPENDING / sid).exists(), "and after the bus start's reconcile")
            pm._retry_pending()
            self.assertTrue((pm.MAILPENDING / sid).exists(), "and after the retry arm")
        finally:
            os.chmod(newd, 0o755)
        pm._mark_pending(sid)
        self.assertTrue((pm.MAILPENDING / sid).exists(), "readable again with mail: still standing")
        (newd / "m1").unlink(); pm._mark_pending(sid)
        self.assertFalse((pm.MAILPENDING / sid).exists(), "drained: the marker goes")

    def test_an_unsearchable_inbox_without_a_marker_gets_none(self):
        """The absent arm: unknown keeps the marker as it stands, so no marker is minted on an inbox that cannot be read."""
        if ROOT_ONLY:
            self.skipTest("root reads through chmod 000")
        sid = "44444444-2222-4333-8444-0000000000e4"
        newd = self._box_with_unread_mail(sid)
        (pm.MAILPENDING / sid).unlink(missing_ok=True)
        os.chmod(newd, 0)
        try:
            pm._mark_pending(sid); pm._reconcile_markers()
            self.assertFalse((pm.MAILPENDING / sid).exists(), "absent stays absent on an unknown inbox")
        finally:
            os.chmod(newd, 0o755)


class TaskPlanLoudOnUnreadable(unittest.TestCase):
    def test_a_task_directory_that_cannot_be_listed_raises_and_a_missing_one_is_no_plan(self):
        cfg = tempfile.mkdtemp(); saved = os.environ.get("CLAUDE_CONFIG_DIR"); os.environ["CLAUDE_CONFIG_DIR"] = cfg
        try:
            self.assertIsNone(km._task_plan_cached(SID), "no directory: this session declared no plan")
            if ROOT_ONLY:
                return
            d = Path(cfg) / "tasks" / SID; d.mkdir(parents=True); (d / "1.json").write_text("{}")
            os.chmod(d, 0)
            try:
                with self.assertRaises(OSError):
                    km._task_plan_cached(SID)                    # exists but unreadable: loud, never "no plan"
            finally:
                os.chmod(d, 0o755)
            os.chmod(d.parent, 0)                                # the PARENT tasks/ unsearchable: the child's own stat fails
            try:                                                 #  with EACCES, and is_dir() read False there on 3.14 (a quiet
                with self.assertRaises(OSError):                 #  "no plan" at 1cfbae7d); by errno it is loud on every interpreter
                    km._task_plan_cached(SID)
            finally:
                os.chmod(d.parent, 0o755)
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = saved


if __name__ == "__main__":
    unittest.main()
