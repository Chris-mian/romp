"""A session that enters a Claude Code worktree relocates its transcript to the WORKTREE cwd's
projects dir — the launch-dir walk then finds nothing, and every surface read a WORKING session as
'opening' / dropped it from the list (the user 2026-08-20). The CLI itself reports where it writes
(every hook payload carries transcript_path); the Stop hook records it and discovery prefers it.
Re-ported onto v0.15 2026-09-15. Synthetic fixtures only (placeholder sids)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
KDIR = os.path.join(os.path.dirname(HERE), "kernel")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the load — judge.py resolves its state root at import time, and only pytest
# runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = load_source("romp_judge_wtt", os.path.join(KDIR, "judge.py"))

SID = "11111111-2222-3333-4444-555555555555"


class DiscoverFollowsTheRecordedPath(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        base = Path(self.td.name)
        self._saved = (jd.NAMES, jd.SDKDIR)
        jd.NAMES = base / "names"; jd.NAMES.mkdir()
        jd.SDKDIR = base / "sdk"; jd.SDKDIR.mkdir()
        # the LAUNCH dir's project folder — EMPTY (the CLI moved the transcript away)
        self.launch_proj = base / "projects" / "-repo"
        self.launch_proj.mkdir(parents=True)
        # the WORKTREE dir's project folder — where the transcript actually lives
        self.wt_proj = base / "projects" / "-repo--claude-worktrees-syn"
        self.wt_proj.mkdir(parents=True)
        self.moved = self.wt_proj / (SID + ".jsonl")
        self.moved.write_text(json.dumps({"type": "user", "uuid": "u1",
                                          "message": {"role": "user", "content": "hi"}}) + "\n")
        (jd.NAMES / SID).write_text("web\t/repo\t#888888\tblack")
        self._saved_pd = jd._proj_dir
        jd._proj_dir = lambda cdir: str(self.launch_proj)   # launch cwd → the EMPTY dir
        for memo in (jd._lastsid_memo, jd._recpath_memo, jd._namefp_memo):
            memo.clear()
        jd._discover_cache.clear()

    def tearDown(self):
        jd.NAMES, jd.SDKDIR = self._saved
        jd._proj_dir = self._saved_pd
        for memo in (jd._lastsid_memo, jd._recpath_memo, jd._namefp_memo):
            memo.clear()
        jd._discover_cache.clear()
        self.td.cleanup()

    def _reg(self, **extra):
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"sid": SID, "alive": True, **extra}))

    def test_without_the_record_the_session_is_lost(self):
        self._reg()
        got = jd._discover_impl(int(self.moved.stat().st_mtime) + 10, window=3600)
        self.assertEqual(got, [], "the launch-dir walk cannot see a relocated transcript (the bug)")

    def test_the_recorded_path_resolves_the_relocated_transcript(self):
        self._reg(transcriptPath=str(self.moved))
        got = jd._discover_impl(int(self.moved.stat().st_mtime) + 10, window=3600)
        self.assertEqual(len(got), 1)
        fsid, path, anchor, name = got[0]
        self.assertEqual((fsid, str(path), name), (SID, str(self.moved), "web"))

    def test_a_clear_fork_after_relocation_follows_lastSid_in_the_new_dir(self):
        fork = self.wt_proj / "22222222-3333-4444-5555-666666666666.jsonl"
        fork.write_text(self.moved.read_text())
        self._reg(transcriptPath=str(self.moved), lastSid="22222222-3333-4444-5555-666666666666")
        got = jd._discover_impl(int(fork.stat().st_mtime) + 10, window=3600)
        self.assertEqual(str(got[0][1]), str(fork), "the fork resolves in the RECORDED file's dir")

    def test_a_stale_record_falls_back_to_the_walk(self):
        anchor = self.launch_proj / (SID + ".jsonl")
        anchor.write_text(self.moved.read_text())
        self._reg(transcriptPath=str(self.wt_proj / "gone.jsonl"))   # recorded but deleted
        got = jd._discover_impl(int(anchor.stat().st_mtime) + 10, window=3600)
        self.assertEqual(str(got[0][1]), str(anchor), "a dead record never hides the launch-dir file")

    def test_the_fingerprint_signs_the_record(self):
        src = open(os.path.join(KDIR, "judge.py")).read()
        self.assertIn('_sdk_transcript_path(f.name) or ""', src,
                      "a relocation must bust the discover cache the moment it lands")
        sb = open(os.path.join(KDIR, "sdk_backend.py")).read()
        self.assertIn('self.backend._update_reg(self.sid, transcriptPath=str(tp))', sb,
                      "the Stop hook records the CLI-reported path")


if __name__ == "__main__":
    unittest.main()
