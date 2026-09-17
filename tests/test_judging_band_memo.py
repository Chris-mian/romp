#!/usr/bin/env python3
"""The judging band reuses its entry objects across builds and scans only the horizon (2026-09-16).

_run_judging rebuilt the whole band from the retained judge-usage rows on every bars build: every retained
row (~62k under the 31-day retention) was tested against the 48 h horizon, and every completed run in the
horizon (~8.7k) became a FRESH entry dict, which _compact_judging turned into a fresh compact dict. Every
object being new, the bars fill's identity memo (_delta_split's, which hands back a reused bar's pair
since 2026-09-16) never hit on the band, and every entry was re-encoded each build. Now the band keeps a
per-row memo validated on the gloss it borrowed, so an entry whose row and gloss are unchanged is the
SAME object across builds, _compact_judging keeps an identity memo over those entries, and a cursor skips
the leading rows each verified to end before the horizon.

Self-contained, on test_kernel_runspans.py's harness: a synthetic judge-usage.jsonl under a temp state
root, placeholder sids, jd._active cleared per test, the memo slots cleared per test."""
import inspect
import io
import json
import os
import random
import tempfile
import unittest
from contextlib import redirect_stderr
from romp_load import load_source
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_judging_band_memo", os.path.join(BIN, "romp-kernel"))
jd = km.jd

SID = "11111111-2222-3333-4444-555555555555"
SID2 = "22222222-3333-4444-5555-666666666666"
NOW = 1_800_000_000


def _row(judge, sid, t, dur=5, **kw):
    r = {"judge": judge, "fsid": sid, "t": t, "sent": t - dur, "recv": t, "ms": 1000 * dur, "in": 50, "out": 20}
    r.update(kw)
    return r


def _mark(judge, sid, t, text, kind="mint"):
    return {"judge": judge, "sid": sid, "t": t, "kind": kind, "text": text}


class _Counting(dict):
    """A row that counts its reads: the cursor's proof is that a leading pre-horizon row is read by no later build."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.reads = 0

    def get(self, *a):
        self.reads += 1
        return super().get(*a)


class _Pruning(dict):
    """A row whose FIRST read prunes `n` rows off the left of the list it sits in: the shape of the reader's left prune
    landing from another thread in the middle of a scan (an analytics request or a cold connect push reads the log too).
    `counted` is the production reader's prune, which also moves the cumulative count; uncounted is a mutation the
    cursor's premise does not cover, held here to pin the identity backstop."""
    def __init__(self, rows, n, *a, counted=False, **kw):
        super().__init__(*a, **kw)
        self._rows, self._n, self._counted, self.fired = rows, n, counted, False

    def get(self, *a):
        if not self.fired:
            self.fired = True
            del self._rows[:self._n]
            if self._counted:
                km._JUDGE_USAGE_CACHE["pruned"] = km._JUDGE_USAGE_CACHE.get("pruned", 0) + self._n
        return super().get(*a)


class _Band(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = (jd.STATE, km._judge_usage_rows, jd.active_runs)
        self.saved_pruned = km._JUDGE_USAGE_CACHE.get("pruned", 0)
        jd.STATE = Path(self.td.name)
        jd.active_runs = lambda: []
        km._judging_band = None
        km._judging_compact_memo = None
        km._delta_entry_memo.clear()

    def tearDown(self):
        jd.STATE, km._judge_usage_rows, jd.active_runs = self.saved
        km._JUDGE_USAGE_CACHE["pruned"] = self.saved_pruned
        jd._active.clear()
        km._judging_band = None
        km._judging_compact_memo = None
        self.td.cleanup()

    def _usage(self, rows, mode="w"):
        with open(jd.STATE / "judge-usage.jsonl", mode) as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def _cold(self, t0, alive, semantic):
        """What a memo-less call yields: the slot cleared, the same reader, fresh objects."""
        held = km._judging_band
        km._judging_band = None
        try:
            return km._run_judging(t0, alive, semantic)
        finally:
            km._judging_band = held


class EntryIdentity(_Band):
    """(a) An unchanged band yields identical entry objects across two builds; a change reaches exactly its entry."""

    def _band(self):
        rows = [_row("planner", SID, NOW - 90000),           # before the horizon: never an entry
                _row("captioner", SID, NOW - 3000), _row("planner", SID, NOW - 2000),
                _row("closer", SID, NOW - 1000), _row("captioner", SID, NOW - 500)]
        self._usage(rows)
        semantic = [_mark("captioner", SID, NOW - 3100, "first caption"), _mark("planner", SID, NOW - 2500, "the plan"),
                    _mark("captioner", SID, NOW - 600, "second caption")]
        return rows, semantic

    def test_an_unchanged_band_yields_the_same_entry_objects_across_two_builds(self):
        _, semantic = self._band()
        t0 = NOW - 86400
        first = km._run_judging(t0, {SID}, semantic)
        second = km._run_judging(t0 + 1, {SID}, semantic)      # the next build: a second later, as the pusher's is
        self.assertEqual(len(first), 4)
        self.assertEqual(second, first, "the band's content is unchanged")
        for a, b in zip(first, second):
            self.assertIs(a, b, "an unchanged row with an unchanged gloss: the SAME entry object, not an equal one")
        self.assertEqual([e["text"] for e in first], ["first caption", "the plan", "", "second caption"])

    def test_a_changed_gloss_re_mints_only_the_entries_it_is_newest_for(self):
        _, semantic = self._band()
        t0 = NOW - 86400
        first = km._run_judging(t0, {SID}, semantic)
        # a newer captioner mark, newest for the last captioner run only: that entry is new with the new text,
        # the three others keep their identity (the memo validates on the gloss it borrowed, by value)
        semantic.append(_mark("captioner", SID, NOW - 520, "third caption"))
        second = km._run_judging(t0 + 1, {SID}, semantic)
        self.assertEqual(second, self._cold(t0 + 1, {SID}, semantic), "equal to a memo-less build")
        self.assertIs(second[0], first[0]); self.assertIs(second[1], first[1]); self.assertIs(second[2], first[2])
        self.assertIsNot(second[3], first[3], "the re-glossed run is a new object")
        self.assertEqual(second[3]["text"], "third caption")

    def test_an_appended_row_adds_one_new_entry_and_keeps_the_rest(self):
        _, semantic = self._band()
        t0 = NOW - 86400
        first = km._run_judging(t0, {SID}, semantic)
        self._usage([_row("grouper", SID, NOW - 100)], mode="a")
        second = km._run_judging(t0 + 1, {SID}, semantic)
        self.assertEqual(len(second), 5)
        for a, b in zip(first, second[:4]):
            self.assertIs(a, b)
        self.assertEqual(second[4]["judge"], "grouper")
        self.assertEqual(second, self._cold(t0 + 1, {SID}, semantic))

    def test_an_alive_set_change_reads_the_memo_exactly(self):
        rows, semantic = self._band()
        self._usage([_row("planner", SID2, NOW - 1500)], mode="a")
        t0 = NOW - 86400
        both = km._run_judging(t0, {SID, SID2}, semantic)
        self.assertEqual([e["sid"] for e in both].count(SID2), 1)
        one = km._run_judging(t0 + 1, {SID}, semantic)
        self.assertEqual(one, self._cold(t0 + 1, {SID}, semantic), "the alive set only gates which rows yield an entry")
        self.assertEqual(len(one), 4)
        for e in one:
            self.assertIn(e, both)
            self.assertTrue(any(e is b for b in both), "a row alive in both builds keeps its entry object")
        back = km._run_judging(t0 + 2, {SID, SID2}, semantic)
        self.assertEqual(back, both)

    def test_an_open_run_stays_fresh_every_build(self):
        _, semantic = self._band()
        rid = jd._active_begin("grouper", SID, NOW - 50)
        jd.active_runs = self.saved[2]
        try:
            first = km._run_judging(NOW - 86400, {SID}, semantic)
            second = km._run_judging(NOW - 86400, {SID}, semantic)
        finally:
            jd._active_end(rid)
        self.assertTrue(first[-1].get("open") and second[-1].get("open"))
        self.assertIsNot(first[-1], second[-1], "an in-flight run's t1 is the build clock: minted per build by design")


class MemoTuple(_Band):
    """(b) The memo holds ONE tuple per row and hands the same tuple back on a hit (the split memo's precedent: a tuple
    holding a dict is tracked by the collector for life, so a fresh one per row per build is the stream the memo exists
    to remove); the slot is one tuple, rebound whole."""

    def test_a_hit_hands_back_the_memo_tuple_itself(self):
        self._usage([_row("planner", SID, NOW - 2000), _row("closer", SID, NOW - 1000)])
        km._run_judging(NOW - 86400, {SID}, [])
        rows = km._judge_usage_rows()
        slot1 = km._judging_band
        self.assertIsInstance(slot1, tuple, "one tuple in one slot, read once and rebound whole")
        memo1 = slot1[-1]
        self.assertEqual(set(memo1), {id(r) for r in rows})
        km._run_judging(NOW - 86400 + 1, {SID}, [])
        slot2 = km._judging_band
        self.assertIsNot(slot2, slot1, "the slot is rebound to a new tuple per call")
        for r in rows:
            self.assertIs(slot2[-1][id(r)], memo1[id(r)], "a hit: the previous build's tuple itself, no new tuple")
            self.assertIs(slot2[-1][id(r)][0], r, "the tuple holds the row it was validated against")

    def test_the_compact_memo_hands_back_the_same_compact_dict_and_the_same_tuple(self):
        entries = [{"judge": "planner", "sid": SID, "t": 10, "t1": 12, "kind": "plan", "text": "the plan", "ms": 5, "in": 1, "out": 1, "sent": 10, "recv": 12},
                   {"judge": "closer", "sid": SID, "t": 20, "t1": 21, "kind": "run", "text": "", "ms": 0, "in": 0, "out": 0, "sent": 20, "recv": 21}]
        c1 = km._compact_judging(entries)
        memo1 = km._judging_compact_memo
        self.assertIs(memo1[id(entries[0])][1], c1[SID][0])
        c2 = km._compact_judging(entries)
        self.assertIs(c2[SID][0], c1[SID][0], "the same entry object: the same compact dict")
        self.assertIs(c2[SID][1], c1[SID][1])
        self.assertIs(km._judging_compact_memo[id(entries[0])], memo1[id(entries[0])], "and the memo's tuple is reused")
        self.assertIsNot(km._judging_compact_memo, memo1, "the memo is rebuilt per call and the global rebound")
        fresh = [dict(entries[0]), entries[1]]                     # equal content, a NEW object: a miss for that entry only
        c3 = km._compact_judging(fresh)
        self.assertIsNot(c3[SID][0], c1[SID][0]); self.assertEqual(c3[SID][0], c1[SID][0])
        self.assertIs(c3[SID][1], c1[SID][1])
        self.assertNotIn(id(entries[0]), km._judging_compact_memo, "rebuilt from THIS call's entries: no growth")
        self.assertEqual(c3, c1, "the wire is unchanged")

    def test_the_bars_fill_reuses_the_pair_of_an_unchanged_entry(self):
        self._usage([_row("planner", SID, NOW - 2000), _row("closer", SID, NOW - 1000)])
        semantic = [_mark("planner", SID, NOW - 2500, "the plan")]
        c1 = km._compact_judging(km._run_judging(NOW - 86400, {SID}, semantic))
        e1, _ = km._delta_split("dictlist:k", c1, memo_key=("bars", "judging"))
        c2 = km._compact_judging(km._run_judging(NOW - 86400 + 1, {SID}, semantic))
        e2, _ = km._delta_split("dictlist:k", c2, memo_key=("bars", "judging"))
        self.assertEqual(set(e1), set(e2))
        for k in e1:
            self.assertIs(e2[k], e1[k], "the split's identity memo hits: the previous (object, json) pair, nothing re-encoded")


class Cursor(_Band):
    """(c) The scan covers the horizon, not every retained row: the leading rows each verified to end before the
    horizon are not read again, and the cursor drops whenever its premise does (a horizon moved back, a left prune
    it cannot account for, a new list)."""

    def _stable(self, n_old, n_new):
        rows = [_Counting(_row("captioner", SID, NOW - 200000 - i)) for i in range(n_old)]
        rows += [_Counting(_row("captioner", SID, NOW - 1000 + i)) for i in range(n_new)]
        km._judge_usage_rows = lambda: rows
        return rows

    def test_rows_before_the_horizon_are_not_read_again(self):
        rows = self._stable(50, 5)
        t0 = NOW - 86400
        s0 = dict(km._JUDGING_BAND_STATS)
        first = km._run_judging(t0, {SID}, [])
        self.assertEqual(len(first), 5)
        for r in rows[:50]:
            r.reads = 0
        second = km._run_judging(t0 + 1, {SID}, [])
        self.assertEqual(second, first)
        self.assertEqual(sum(r.reads for r in rows[:50]), 0, "a leading pre-horizon row is read by no later build")
        self.assertTrue(all(r.reads > 0 for r in rows[50:]), "the horizon's rows are re-verified")
        s = km._JUDGING_BAND_STATS
        self.assertEqual(s["builds"] - s0["builds"], 2)
        self.assertEqual(s["rows_visited"] - s0["rows_visited"], 55 + 5, "every row once, then the horizon's")
        self.assertEqual(s["rows_skipped"] - s0["rows_skipped"], 50)
        self.assertEqual(s["entries_reused"] - s0["entries_reused"], 5)
        self.assertEqual(s["entries_minted"] - s0["entries_minted"], 5)

    def test_a_horizon_moved_back_re_verifies_and_the_earlier_rows_reappear(self):
        rows = self._stable(50, 5)
        km._run_judging(NOW - 86400, {SID}, [])
        km._run_judging(NOW - 86400, {SID}, [])
        for r in rows:
            r.reads = 0
        back = km._run_judging(NOW - 300000, {SID}, [])
        self.assertEqual(len(back), 55, "the horizon now covers every row")
        self.assertTrue(all(r.reads > 0 for r in rows), "t0 moved back: every row is verified again")
        self.assertEqual(back, self._cold(NOW - 300000, {SID}, []))

    def test_a_left_prune_the_reader_did_not_account_for_and_a_rotation_reset_the_cursor(self):
        rows = self._stable(50, 5)
        t0 = NOW - 86400
        km._run_judging(t0, {SID}, [])
        del rows[:10]                                            # the same list, its left edge gone: every index moved
        for r in rows:
            r.reads = 0
        out = km._run_judging(t0 + 1, {SID}, [])
        self.assertEqual(out, self._cold(t0 + 1, {SID}, []))
        self.assertTrue(all(r.reads > 0 for r in rows), "the object at the cursor moved: a full re-verification")
        fresh = [_Counting(dict(r)) for r in rows]               # a new list (a rotated log): the memo's premise is gone
        km._judge_usage_rows = lambda: fresh
        out2 = km._run_judging(t0 + 2, {SID}, [])
        self.assertEqual(out2, out)
        self.assertTrue(all(r.reads > 0 for r in fresh))
        self.assertFalse(any(a is b for a, b in zip(out2, out)), "new row objects: new entries (identity, never equality)")

    def test_a_prune_landing_mid_scan_ends_the_scan_cleanly_and_the_next_build_resets(self):
        """The reader's left prune runs on whichever thread reads the log, so it can shrink the list UNDER a scan. An
        index loop over a length taken before it raised IndexError then, and the caller's guard blanked the whole band
        for a frame where the old iterator had merely run off the shortened end. The scan walks a snapshot, the memo
        records the boundary OBJECT the scan verified (never an index into the live list), and the next build finds it
        moved and verifies every row again."""
        rows = [_Counting(_row("captioner", SID, NOW - 200000 - i)) for i in range(50)]
        rows.append(_Pruning(rows, 3, _row("captioner", SID, NOW - 1000)))   # the first horizon row's read prunes three
        rows += [_Counting(_row("captioner", SID, NOW - 900 + i)) for i in range(4)]
        km._judge_usage_rows = lambda: rows
        boundary = rows[49]
        t0 = NOW - 86400
        s0 = dict(km._JUDGING_BAND_STATS)
        out = km._run_judging(t0, {SID}, [])
        self.assertEqual(len(rows), 52, "the prune landed during the scan")
        self.assertEqual(len(out), 5, "every horizon row is drawn: no exception, no blanked band")
        self.assertEqual(out, self._cold(t0, {SID}, []), "and the frame equals a build over the rows still present")
        mb = km._judging_band
        self.assertEqual(mb[1], 50)
        self.assertIs(mb[2], boundary, "the memo holds the object the scan verified as its boundary, not the live list's index")
        nxt = km._run_judging(t0 + 1, {SID}, [])
        self.assertEqual(nxt, out)
        self.assertEqual(km._JUDGING_BAND_STATS["resets"] - s0["resets"], 1, "the boundary moved: the cursor is dropped and re-found")
        self.assertEqual(km._judging_band[1], 47, "at the shifted edge")
        for a, b in zip(out, nxt):
            self.assertIs(a, b, "the entries themselves are reused: their rows and glosses stand")

    def _mid_scan(self, counted):
        rows = [_Counting(_row("captioner", SID, NOW - 200000 - i)) for i in range(50)]
        rows.append(_Pruning(rows, 3, _row("captioner", SID, NOW - 1000), counted=counted))   # the first horizon row's read prunes three
        rows += [_Counting(_row("captioner", SID, NOW - 900 + i)) for i in range(4)]
        km._judge_usage_rows = lambda: rows
        return rows

    def _build(self, t0, alive):
        """One build and the stats it moved: (entries, resets, rows visited)."""
        s = dict(km._JUDGING_BAND_STATS)
        out = km._run_judging(t0, alive, [])
        st = km._JUDGING_BAND_STATS
        return out, st["resets"] - s["resets"], st["rows_visited"] - s["rows_visited"]

    def test_a_counted_prune_landing_mid_scan_is_continued_by_the_next_build(self):
        """The production reader's prune landing from another thread while the scan runs: the list loses its first
        rows AND the count moves. The memo records the boundary object the scan verified and the count it read before
        the scan, so the next build shifts by the count, finds the object in place and continues: no reset, only the
        horizon's rows visited, every entry reused. A boundary read from the live list at rebind time would have been
        the row that slid into that index, and this build would have reset."""
        rows = self._mid_scan(counted=True)
        boundary = rows[49]
        t0 = NOW - 86400
        out, _, _ = self._build(t0, {SID})
        self.assertEqual(len(rows), 52)
        self.assertEqual(out, self._cold(t0, {SID}, []))
        mb = km._judging_band
        self.assertEqual(mb[1], 50); self.assertIs(mb[2], boundary)
        self.assertEqual(km._JUDGE_USAGE_CACHE["pruned"] - mb[3], 3, "the count moved after the memo read it")
        self.assertIsNot(rows[49], boundary, "the live list's index holds another row now")
        nxt, resets, visited = self._build(t0 + 1, {SID})
        self.assertEqual(resets, 0, "the count accounts for the shift: the boundary is found in place")
        self.assertEqual(km._judging_band[1], 47)
        self.assertEqual(visited, 5, "only the horizon's rows")
        self.assertEqual(nxt, self._cold(t0 + 1, {SID}, []))
        self.assertEqual(len(nxt), 5)
        for a, b in zip(out, nxt):
            self.assertIs(a, b, "every entry reused")

    def test_a_prune_whose_count_has_not_landed_yet_resets_rather_than_losing_rows(self):
        """The double race: a counted prune lands mid-scan, and at the next build another reader has deleted the left
        rows but not yet moved the count. The count says the list shifted by three; it shifted by six. The memo's
        boundary is the object the scan verified, so the row now at the shifted index is not it and the build resets:
        every row verified, nothing lost. A boundary read from the live list at rebind time would have been the row
        that slid into the index, the shifted index would hold that same row again, and the build would have skipped
        three horizon rows it never verified. Once the count lands the cursor is re-found and the band is stable."""
        rows = self._mid_scan(counted=True)
        t0 = NOW - 86400
        first, _, _ = self._build(t0, {SID})
        self.assertEqual(len(first), 5)
        slid = rows[49]                                          # what a live-list boundary would have recorded
        del rows[:3]                                             # the second prune's del has landed; its count is pending
        self.assertIs(rows[46], slid, "the shifted index holds the row that slid in: a live-list boundary would pass here")
        second, resets, visited = self._build(t0 + 1, {SID})
        self.assertEqual(resets, 1, "the verified boundary is not at the shifted index: a reset")
        self.assertEqual(visited, 49, "every row verified")
        self.assertEqual(len(second), 5, "no row lost")
        self.assertEqual(second, self._cold(t0 + 1, {SID}, []))
        for a, b in zip(first, second):
            self.assertIs(a, b, "the entries are reused across the reset: their rows and glosses stand")
        km._JUDGE_USAGE_CACHE["pruned"] += 3                     # the pending count lands
        third, resets, visited = self._build(t0 + 2, {SID})
        self.assertEqual(third, self._cold(t0 + 2, {SID}, []))
        self.assertEqual((resets, visited), (1, 49), "the count caught up to a shift the last scan had already absorbed: one more reset, exact")
        fourth, resets, visited = self._build(t0 + 3, {SID})
        self.assertEqual((resets, visited), (0, 5), "stable: the cursor is re-found and only the horizon's rows are visited")
        self.assertEqual(km._judging_band[1], 44)
        self.assertEqual(fourth, self._cold(t0 + 3, {SID}, []))

    def test_a_prune_through_the_reader_shifts_the_cursor_instead_of_resetting_it(self):
        """The live log spans its retention window, so most appends prune the left edge in place and move every
        index: an identity-only cursor would rescan every retained row on a third of live builds. The reader counts
        what it pruned, the band shifts by that count, and the identity check stays as the exactness backstop."""
        R = km._JUDGE_USAGE_RETAIN
        base = NOW - R - 100                                    # two rows that the next append pushes out of retention
        self._usage([_row("captioner", SID, base), _row("captioner", SID, base + 1)]
                    + [_row("captioner", SID, base + 50 + i) for i in range(40)]
                    + [_row("captioner", SID, NOW - 1000 + i) for i in range(5)])
        t0 = NOW - 86400
        first = km._run_judging(t0, {SID}, [])
        self.assertEqual(len(first), 5)
        before = list(km._judge_usage_rows())
        s0 = dict(km._JUDGING_BAND_STATS)
        self._usage([_row("captioner", SID, base + 1 + R + 1)], mode="a")    # newest - RETAIN passes the first two rows
        rows = km._judge_usage_rows()
        self.assertEqual(len(rows), len(before) - 2 + 1, "the reader pruned two rows and appended one")
        self.assertIs(rows[0], before[2])
        second = km._run_judging(t0 + 1, {SID}, [])
        s = dict(km._JUDGING_BAND_STATS)                        # before the cold comparison, itself a counted call
        self.assertEqual(s["rows_visited"] - s0["rows_visited"], 5 + 1, "the horizon's rows and the appended one: no leading row revisited")
        self.assertEqual(s["rows_skipped"] - s0["rows_skipped"], 40, "the cursor shifted by the two pruned rows")
        self.assertEqual(s["resets"] - s0["resets"], 0)
        self.assertEqual(second, self._cold(t0 + 1, {SID}, []))
        for a, b in zip(first, second):
            self.assertIs(a, b)


class Bound(_Band):
    """The band memo holds only the entries that reach the frame: the wire cap trims the oldest entries off every build,
    so holding theirs buys no reuse, and the memo's occupancy is bounded by the cap rather than by the horizon's row
    count (a judge storm's 147k), which the /perf block reports beside the occupancy."""

    def test_the_memo_holds_only_the_entries_that_survive_the_trim(self):
        n = km._JUDGING_ROW_CAP + 50
        rows = [_row("captioner", SID, NOW - n - 10 + i, dur=1) for i in range(n)]
        km._judge_usage_rows = lambda: rows
        km._JUDGING_TRIMMED.clear()
        t0 = NOW - (n + 3600)
        with redirect_stderr(io.StringIO()):
            out = km._run_judging(t0, {SID}, [])
        self.assertEqual(len(out), km._JUDGING_ROW_CAP)
        held = km._judging_band[5]
        self.assertEqual(len(held), km._JUDGING_ROW_CAP, "the trimmed entries' tuples are dropped with them")
        kept = {id(e) for e in out}
        self.assertTrue(all(id(t[3]) in kept for t in held.values()), "what is held is what the frame carries")
        rep = km._judging_band_report()
        self.assertEqual((rep["entries"], rep["bound"]), (km._JUDGING_ROW_CAP, km._JUDGING_ROW_CAP))
        self.assertGreater(rep["bytes"], 0)
        with redirect_stderr(io.StringIO()):
            out2 = km._run_judging(t0 + 1, {SID}, [])
        self.assertEqual(sum(1 for a, b in zip(out, out2) if a is b), km._JUDGING_ROW_CAP, "the surviving entries are reused")


class Interleaving(_Band):
    """(d) Two calls that overlap (a connect push builds the timeline outside the pusher's lock) read one slot each
    and rebind it whole: whichever writes last, the next build reads a consistent snapshot and yields the cold
    result. The race is driven deterministically: the slot is restored to what the second call would have read
    had it started before the first finished."""

    def _log(self):
        self._usage([_row("planner", SID, NOW - 200000), _row("planner", SID2, NOW - 150000),
                     _row("captioner", SID, NOW - 5000), _row("captioner", SID2, NOW - 4000),
                     _row("closer", SID, NOW - 3000), _row("grouper", SID2, NOW - 2000)])

    def test_interleaved_calls_with_different_horizons_and_alive_sets_yield_the_cold_result(self):
        self._log()
        semantic = [_mark("captioner", SID, NOW - 5500, "cap one"), _mark("captioner", SID2, NOW - 4500, "cap two")]
        a_args = (NOW - 86400, {SID}, semantic)
        b_args = (NOW - 300000, {SID, SID2}, semantic)
        km._run_judging(NOW - 90000, {SID, SID2}, semantic)      # a prior build: the slot both overlapping calls read
        s0 = km._judging_band
        a = km._run_judging(*a_args)
        self.assertEqual(a, self._cold(*a_args))
        km._judging_band = s0                                    # B read the slot before A rebound it
        b = km._run_judging(*b_args)
        self.assertEqual(b, self._cold(*b_args), "a horizon moved back against the snapshot it read: every row verified")
        c = km._run_judging(*a_args)                             # the next build reads whichever wrote last (B here)
        self.assertEqual(c, a)
        km._judging_band = s0
        d = km._run_judging(NOW - 3500, {SID2}, semantic)        # and the other order: a later horizon, a smaller set
        self.assertEqual(d, self._cold(NOW - 3500, {SID2}, semantic))
        e = km._run_judging(*b_args)
        self.assertEqual(e, b)

    def test_an_interleaving_across_a_rotation_yields_the_cold_result(self):
        self._log()
        km._run_judging(NOW - 86400, {SID, SID2}, [])
        s0 = km._judging_band
        self._usage([_row("closer", SID2, NOW - 100)])          # a rewrite: the reader's list is a new object
        rot = km._run_judging(NOW - 86400, {SID, SID2}, [])
        self.assertEqual(len(rot), 1)
        km._judging_band = s0                                    # the overlapping call read the pre-rotation slot
        late = km._run_judging(NOW - 86400 + 1, {SID, SID2}, [])
        self.assertEqual(late, rot)
        nxt = km._run_judging(NOW - 86400 + 2, {SID2}, [])
        self.assertEqual(nxt, self._cold(NOW - 86400 + 2, {SID2}, []))


class Equivalence(_Band):
    """(e) Guards, green before and after: the gloss by bisect is the comprehension's pick (the newest same-judge mark
    at or before the run's end), including equal mark times; the band's stats block reaches /perf."""

    def test_the_gloss_is_the_newest_same_judge_mark_at_or_before_the_end(self):
        rnd = random.Random(7)
        rows, semantic = [], []
        for i in range(120):
            rows.append(_row(rnd.choice(["captioner", "planner", "closer"]), rnd.choice([SID, SID2]), NOW - rnd.randint(0, 5000), dur=rnd.randint(1, 30)))
        for i in range(60):
            t = NOW - rnd.choice([100, 500, 1000, 2500, 4000, 4001, 5030])   # repeated times: equal-t marks
            semantic.append(_mark(rnd.choice(["captioner", "planner", "closer"]), rnd.choice([SID, SID2]), t, "mark %d" % i))
        self._usage(rows)
        by = {}
        for mk in semantic:
            by.setdefault((mk["sid"], mk["judge"]), []).append(mk)
        for v in by.values():
            v.sort(key=lambda m: m["t"])
        out = km._run_judging(NOW - 86400, {SID, SID2}, semantic)
        self.assertEqual(len(out), 120)
        for e in out:
            cands = [m for m in by.get((e["sid"], e["judge"]), []) if m["t"] <= e["t1"] + 1]
            src = cands[-1] if cands else None
            self.assertEqual((e["kind"], e["text"]), ((src or {}).get("kind", "run"), (src or {}).get("text", "")))
        self.assertEqual(out, km._run_judging(NOW - 86400 + 1, {SID, SID2}, semantic))

    def test_the_source_still_reads_the_shared_reader_and_perf_carries_the_block(self):
        src = inspect.getsource(km._run_judging)
        self.assertIn("_judge_usage_rows()", src)
        self.assertNotIn(".read_text(", src)
        self._usage([_row("planner", SID, NOW - 2000)])
        km._run_judging(NOW - 86400, {SID}, [])
        rep = km._PERF_STATS.snapshot()["memos"]["judgingBand"]
        self.assertEqual(set(rep), set(km._JUDGING_BAND_STATS) | {"entries", "compact", "bytes", "bound"})
        self.assertEqual((rep["entries"], rep["bound"]), (1, km._JUDGING_ROW_CAP), "the memo's occupancy, one held row, against its bound")


if __name__ == "__main__":
    unittest.main()
