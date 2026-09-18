#!/usr/bin/env python3
"""_parked_handoffs (the user 2026-06-22): a send to a DEAD session parks in its maildir until the session
is revived — the kernel surfaces each as a needs-you 'revive to deliver, or dismiss' decision instead of
parking silently. DETERMINISTIC, no judging: a park:true 'sent' row in the postal log whose maildir file is
STILL in the recipient's new/ (unconsumed — the authoritative still-parked signal) AND whose recipient is
still dead. Self-contained: drives _parked_handoffs against a synthetic messages.jsonl + maildir. No real
session data.

ParkedHandoffFold (2026-09-18): the scan walked every row of the postal log on every feed build to find the handful of
park:true sends; a _fold_records fold now carries the parked candidates across builds (a recall or bounced row retires
one, an append steps only the new rows), and the maildir new/ check stays the sole authority for what is surfaced.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from romp_load import load_source
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_ph", os.path.join(BIN, "romp-kernel"))
jd = km.jd

A = "aaaaaaaa-0000-0000-0000-000000000001"   # sender (alive)
B = "bbbbbbbb-0000-0000-0000-000000000002"   # recipient (dead)
NOW = 1781100000


class ParkedHandoff(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = (jd.STATE, jd.MESSAGES, km._name_of)
        jd.STATE = Path(self.td.name)
        (jd.STATE / "timeline").mkdir(parents=True)
        jd.MESSAGES = jd.STATE / "timeline" / "messages.jsonl"
        km._name_of = lambda sid: {A: "alfa", B: "bravo"}.get(sid)

    def tearDown(self):
        (jd.STATE, jd.MESSAGES, km._name_of) = self.saved
        self.td.cleanup()

    def _log(self, rows):
        jd.MESSAGES.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def _maildir(self, to_id, mid, present=True):
        d = jd.STATE / "postal" / "mail" / to_id / "new"
        d.mkdir(parents=True, exist_ok=True)
        if present:
            (d / mid).write_text("From: alfa\n\nDELEGATE: do the thing")

    def _sent(self, mid, frm=A, to=B, park=True, body="DELEGATE: do the export"):
        r = {"ev": "sent", "id": mid, "from_id": frm, "to_id": to, "body": body, "t": NOW - 100}
        if park:
            r["park"] = True
        return r

    def test_parked_to_dead_with_pending_maildir_is_surfaced(self):
        self._log([self._sent("m1.1")])
        self._maildir(B, "m1.1", present=True)
        out = km._parked_handoffs(NOW, {A})              # B is NOT alive
        self.assertEqual(len(out), 1, "a parked-to-dead handoff with a pending maildir file surfaces")
        self.assertEqual(out[0]["toId"], B)
        self.assertEqual((out[0]["fromName"], out[0]["toName"]), ("alfa", "bravo"))
        self.assertEqual(out[0]["msgId"], "m1.1")

    def test_recipient_alive_means_already_delivered(self):
        self._log([self._sent("m1.1")])
        self._maildir(B, "m1.1", present=True)
        self.assertEqual(km._parked_handoffs(NOW, {A, B}), [], "B revived/alive → the parked mail already delivered")

    def test_consumed_maildir_is_resolved(self):
        self._log([self._sent("m1.1")])
        self._maildir(B, "m1.1", present=False)          # file gone = consumed / recalled
        self.assertEqual(km._parked_handoffs(NOW, {A}), [], "no maildir file → the handoff is resolved, not surfaced")

    def test_a_normal_delivered_send_is_not_a_parked_handoff(self):
        self._log([self._sent("m1.1", park=False)])      # delivered live, no park flag
        self._maildir(B, "m1.1", present=True)
        self.assertEqual(km._parked_handoffs(NOW, {A}), [], "only park:true sends are handoffs awaiting a decision")

    def test_oldest_first_and_multiple(self):
        self._log([self._sent("m2.2", body="DELEGATE: second"),
                   {"ev": "sent", "id": "m1.1", "from_id": A, "to_id": B, "body": "DELEGATE: first",
                    "t": NOW - 500, "park": True}])
        self._maildir(B, "m1.1", present=True)
        self._maildir(B, "m2.2", present=True)
        out = km._parked_handoffs(NOW, {A})
        self.assertEqual([h["msgId"] for h in out], ["m1.1", "m2.2"], "oldest-first by send time")


def _fold_stats():
    """The fold's counters, {} on a kernel without the fold: the tests below then FAIL at their assertions on the
    tree before it (the behavioral red), instead of erroring at setUp on the missing name."""
    return dict(getattr(km, "_parked_fold_stats", {}))


class ParkedHandoffFold(ParkedHandoff):
    """The fold behind _parked_handoffs (2026-09-18). The five behavioral tests above run again here, over a cleared
    fold cursor: the maildir authority still gates every surfaced row. The postal service writes its recall row after
    the unlink of new/<mid> and its bounced row after the move aside (and neither when the removal fails), so a
    terminal row is the later fact and retires the candidate; exec and unexec are NOT consulted, because restore()
    moves the file back to new/ before its unexec row lands and ignores a failed append, so the ledger cannot say
    whether a claim stands: the maildir alone decides. A log that exists and cannot be read answers no parked
    handoffs for the build, counted under fail and said once per episode on stderr, the awaiting overlay's shape."""

    def setUp(self):
        super().setUp()
        getattr(km, "_parked_fold_cache", {}).clear()       # the defaults keep the stock tree at its assertions, not here
        getattr(km, "_parked_fold_failed", set()).clear()
        km.em._JSONL_CACHE.pop(str(jd.MESSAGES), None)

    def _append(self, row):
        with open(jd.MESSAGES, "a") as fh:
            fh.write(json.dumps(row) + "\n")       # with its newline: a newline-less tail is provisional to the reader

    def test_a_terminal_row_retires_the_candidate(self):
        # the file is LEFT in new/ to isolate the row's verdict from the maildir's: the service unlinks before it
        # writes the row, so a recall row beside a standing file is a world it does not produce, and the row rules
        self._log([self._sent("m1.1"), {"ev": "recall", "id": "m1.1", "t": NOW - 50, "box": "new"}])
        self._maildir(B, "m1.1", present=True)
        self.assertEqual(km._parked_handoffs(NOW, {A}), [], "a recalled handoff is retired by its row")

    def test_b_a_claim_row_is_not_consulted_the_maildir_alone_decides(self):
        # green before the fold too: a guard on the semantics the fold keeps. read_box(consume=True) renames new/ to
        # cur/ and writes exec second; restore() renames back and writes unexec second, ignoring a failed append
        self._log([self._sent("m1.1"), {"ev": "exec", "id": "m1.1", "t": NOW - 60}])
        self._maildir(B, "m1.1", present=False)                    # claimed: the file sits in cur/
        self.assertEqual(km._parked_handoffs(NOW, {A}), [], "no file in new/: resolved, whatever the rows say")
        self._maildir(B, "m1.1", present=True)                     # restore() moved it back; its unexec row not yet landed
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1"],
                         "the file back in new/ surfaces it with the exec row standing")

    def test_c_an_append_steps_only_the_new_rows(self):
        self._log([self._sent("m1.1")])
        self._maildir(B, "m1.1", present=True)
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1"])
        before = _fold_stats()
        row = self._sent("m2.2", body="second"); row["t"] = NOW - 50
        self._append(row)
        self._maildir(B, "m2.2", present=True)
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1", "m2.2"])
        cursor = getattr(km, "_parked_fold_cache", {}).get(str(jd.MESSAGES), (0,))
        self.assertEqual(cursor[0], 2, "the cursor stands at the row count")
        self.assertEqual(_fold_stats()["append"], before["append"] + 1, "the appended row alone was stepped")
        after = _fold_stats()
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1", "m2.2"])
        self.assertEqual(_fold_stats()["hit"], after["hit"] + 1, "an unchanged log is one cursor check")
        self.assertEqual(_fold_stats()["append"], after["append"], "and nothing stepped")

    def test_d_an_unreadable_log_answers_none_and_is_said_once_per_episode(self):
        # the awaiting overlay's fail test, over this fold: a log that exists and cannot be read answers no parked
        # handoffs for the build (the fold's empty state), counts a fail per call, memoizes nothing, and is said ONCE
        # per episode on stderr; a later good read ends the episode, so a second failure is said again
        self._log([self._sent("m1.1")])
        self._maildir(B, "m1.1", present=True)
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1"])
        # the shared reader serves an UNCHANGED file's records on an identity hit without opening it, so a permission
        # flip alone is not a read attempt: the file grows first, then becomes unreadable
        row = self._sent("m2.2", body="second"); row["t"] = NOW - 50
        self._append(row)
        self._maildir(B, "m2.2", present=True)
        os.chmod(jd.MESSAGES, 0)
        try:
            if os.access(jd.MESSAGES, os.R_OK):
                self.skipTest("this user reads through mode 000 (root)")
            before, err = _fold_stats(), io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(km._parked_handoffs(NOW, {A}), [], "an unreadable log answers no parked handoffs for the build")
                self.assertEqual(km._parked_handoffs(NOW, {A}), [])
            self.assertEqual(_fold_stats().get("fail", 0), before.get("fail", 0) + 2, "counted per call, memoized never")
            self.assertEqual(err.getvalue().count("unreadable"), 1, "one stderr line per failure episode")
            self.assertIn(os.path.basename(str(jd.MESSAGES)), err.getvalue())
            self.assertIn("parked handoffs", err.getvalue(), "the line says what is answered as none")
        finally:
            os.chmod(jd.MESSAGES, 0o644)
        self.assertEqual([h["msgId"] for h in km._parked_handoffs(NOW, {A})], ["m1.1", "m2.2"], "readable again: folded whole")
        self.assertNotIn(str(jd.MESSAGES), getattr(km, "_parked_fold_failed", set()), "a good read ends the episode")
        row = self._sent("m3.3", body="third"); row["t"] = NOW - 40
        self._append(row)
        os.chmod(jd.MESSAGES, 0)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(km._parked_handoffs(NOW, {A}), [])
            self.assertEqual(err.getvalue().count("unreadable"), 1, "a new episode after a good read is said again")
        finally:
            os.chmod(jd.MESSAGES, 0o644)


if __name__ == "__main__":
    unittest.main()
