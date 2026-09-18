#!/usr/bin/env python3
"""The card boards, phase two (plans/card-boards.md): the kernel's board table (_CODE_BOARDS) holds the feed in the one schema
the renderer's ui/webview/board-def.ts holds, checked by _board_check at import; every card the kernel builds carries its
board and its category beside its column; the bell, the phone and the badge read the board's notification set and badge
category instead of a literal. Synthetic fixtures only (the notes-api demo world)."""
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
_XDG = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _XDG
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(_XDG, "romp"), exist_ok=True)
open(os.path.join(_XDG, "romp", "session-hosts"), "w").write("off\n")
km = load_source("romp_kernel_card_boards", os.path.join(BIN, "romp-kernel"))
KSRC = open(os.path.join(BIN, "romp-kernel")).read()
TSRC = open(os.path.join(ROOT, "ui", "webview", "board-def.ts")).read()

SID = "11111111-2222-3333-4444-555555555555"     # web


def _feed_def():
    return km._CODE_BOARDS["feed"]


class BoardTable(unittest.TestCase):
    def test_the_feed_entry_is_in_the_schema_and_carries_todays_literals(self):
        d, err = km._board_check(_feed_def(), allow_reserved=True)
        self.assertIsNone(err)
        self.assertEqual([c["id"] for c in d["categories"]], ["working", "needs_input", "completed"])
        self.assertEqual([(c["title"], c["chip"]) for c in d["categories"]], [("Working", "working"), ("Blocked", "blocked"), ("Completed", "completed")])
        self.assertEqual((d["defaultCategory"], d["sort"], d["groupBy"], d["needsYou"]), ("working", {"key": "t", "dir": "asc"}, "session", "needs_input"))
        self.assertEqual(d["notify"], ["needs_input", "completed"])
        self.assertEqual(km._NOTIFY_COLUMNS, ("needs_input", "completed"), "the notify set the snapshot entries are checked against is the table's")
        self.assertIn('_NOTIFY_COLUMNS = tuple(_CODE_BOARDS["feed"]["notify"])', KSRC)

    def test_the_renderer_constant_and_the_kernel_table_name_the_same_feed(self):
        # ui/webview/board-def.ts FEED_BOARD, field for field, read from the source (no TypeScript runtime here)
        ts = TSRC[TSRC.index("export const FEED_BOARD: Board = {"):]
        ts = ts[:ts.index("\n};") + 3]
        cats = re.findall(r'\{ id: "([^"]+)", title: "([^"]+)", chip: "([^"]+)" \}', ts)
        self.assertEqual(cats, [(c["id"], c["title"], c["chip"]) for c in _feed_def()["categories"]])
        for key, want in (("defaultCategory", '"working"'), ("groupBy", '"session"'), ("needsYou", '"needs_input"')):
            self.assertRegex(ts, r'\b%s: %s' % (key, re.escape(want)), key)
        self.assertRegex(ts, r'notify: \["needs_input", "completed"\]')
        self.assertRegex(ts, r'sort: \{ key: "t", dir: "asc" \}')
        self.assertRegex(ts, r'kinds: \["goal", "placeholder", "parked", "quarantine", "notice"\]')
        self.assertEqual(_feed_def()["kinds"], ["goal", "placeholder", "parked", "quarantine", "notice"])

    def test_the_check_refuses_a_copy_with_one_member_changed_naming_it(self):
        def refused(mut, want):
            d = json.loads(json.dumps(_feed_def()))
            mut(d)
            _, err = km._board_check(d, allow_reserved=True)
            self.assertIsNotNone(err, want)
            self.assertRegex(err, want)
        refused(lambda d: d["categories"][1].__setitem__("chip", "red"), r"chip must be one of working, blocked, completed, neutral")
        refused(lambda d: d["categories"].extend({"id": "c%d" % i, "title": "C", "chip": "neutral"} for i in range(6)), r"1 to 8")
        refused(lambda d: d["categories"][2].__setitem__("id", "working"), r"repeats")
        refused(lambda d: d.__setitem__("defaultCategory", "done"), r"defaultCategory must name")
        refused(lambda d: d.__setitem__("rules", [{"when": {"needsYou": True}, "category": "done"}]), r"rule's category must name")
        refused(lambda d: d.__setitem__("rules", [{"when": {"owner": "x"}, "category": "working"}]), r"predicate has an unknown member 'owner'")
        refused(lambda d: d.__setitem__("sort", {"key": "age", "dir": "asc"}), r"sort\.key must be one of t, session, owner, title")
        refused(lambda d: d.__setitem__("groupBy", "owner"), r'groupBy must be "session" or null')
        refused(lambda d: d.__setitem__("order", ["newestPinned"]), r"order rules must be from ownerRank")
        refused(lambda d: d.__setitem__("notify", ["done"]), r"notify names a category the board does not have")
        refused(lambda d: d.__setitem__("needsYou", "done"), r"needsYou must be one of")
        refused(lambda d: d.__setitem__("kinds", ["card"]), r"kinds must be from")
        refused(lambda d: d.__setitem__("colour", "blue"), r"unknown member 'colour'")
        refused(lambda d: d.__setitem__("id", "Feed"), r"id must match")
        self.assertEqual(km._board_check("feed"), (None, "a board definition must be a JSON object"))
        # the door refuses the reserved id; the constants pass it
        self.assertRegex(km._board_check(_feed_def())[1], r"code-defined board")
        self.assertIn("raise RuntimeError(\"code-defined board", KSRC, "a drifted constant fails at import")

    def test_the_helpers_read_the_board_a_card_names_and_fall_to_the_feed(self):
        self.assertEqual(km._board_notify("feed"), ("needs_input", "completed"))
        self.assertEqual(km._board_notify(None), ("needs_input", "completed"), "a card naming no board is the feed's")
        self.assertEqual(km._board_notify("notes"), ("needs_input", "completed"), "an id this kernel does not know reads as the feed's until phase three's store")
        self.assertEqual(km._board_needs_you("feed"), "needs_input")


class CardsCarryTheirBoard(unittest.TestCase):
    def test_every_card_family_stamps_board_and_category_beside_column(self):
        # the seven builders, by their source: each carries "board": "feed" and a category equal to its column literal
        fams = {"_feed_session_entry": '"board": "feed", "category": column,',
                "_provisional_card": '"column": "working", "board": "feed", "category": "working",',
                "_awaiting_card": '"column": "working", "board": "feed", "category": "working",',
                "_blocked_placeholder": '"column": "needs_input", "board": "feed", "category": "needs_input",',
                "build_feed": '"column": "needs_input", "board": "feed", "category": "needs_input",',   # the parked handoff
                "_quarantine_cards": '"column": "needs_input", "board": "feed", "category": "needs_input",',
                "_notice_cards": '"board": "feed", "category": "needs_input" if r.get("needsYou") else "completed",'}
        for fn, lit in fams.items():
            self.assertIn(lit, inspect.getsource(getattr(km, fn)), fn)
        self.assertEqual(KSRC.count('"board": "feed"'), 7, "seven families, no eighth card built by hand without its board")
        # the column expression itself is untouched: the record of the 2026-06-29 and 2026-07-07 rulings its pins hold
        self.assertIn('column = ("needs_input" if (api_block or nid == jauth_top or nid == perm_top', inspect.getsource(km._feed_session_entry))

    def test_a_notice_card_carries_the_feed_board_and_its_category_executed(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        cwd = root / "notes-api"; cwd.mkdir()
        orig_state, orig_names = km.jd.STATE, km.NAMES
        km.jd._rebind_state(root / "state")
        (km.jd.STATE / "session-hosts").parent.mkdir(parents=True, exist_ok=True)
        (km.jd.STATE / "session-hosts").write_text("off\n")
        km.jd.NAMES.mkdir(parents=True, exist_ok=True)
        (km.jd.NAMES / SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        km.NAMES = km.jd.NAMES
        saved = (km._live_map, km._cwd_of, km._mark_views_dirty, km._push_soon)
        km._live_map = lambda: {}
        km._cwd_of = lambda sid: str(cwd) if sid == SID else None
        km._mark_views_dirty = lambda: None
        km._push_soon = lambda: None
        km._NOTICE_MEMO.clear(); km._NOTICE_SWEPT.clear()
        try:
            _, err = km.post_notice(SID, "figure", "A new version of the accuracy figure is ready", producer="figure", now=100)
            self.assertIsNone(err)
            _, err = km.post_notice(SID, "ask", "Pick the retry policy", producer="cli", needs_you=True, now=200)
            self.assertIsNone(err)
            cards = {c["notice"]["key"]: c for c in km._notice_cards(300, set())}
            self.assertEqual((cards["figure"]["board"], cards["figure"]["category"], cards["figure"]["column"]), ("feed", "completed", "completed"))
            self.assertEqual((cards["ask"]["board"], cards["ask"]["category"], cards["ask"]["column"]), ("feed", "needs_input", "needs_input"))
        finally:
            (km._live_map, km._cwd_of, km._mark_views_dirty, km._push_soon) = saved
            km.jd._rebind_state(orig_state); km.NAMES = orig_names
            km._NOTICE_MEMO.clear(); km._NOTICE_SWEPT.clear()
            td.cleanup()


class BellAndBadgeReadTheBoard(unittest.TestCase):
    def test_the_badge_counts_the_boards_needs_you_category_and_falls_to_column_for_an_older_card(self):
        feed = {"asks": [
            {"itemId": "a", "board": "feed", "category": "needs_input", "column": "needs_input"},
            {"itemId": "b", "board": "feed", "category": "needs_input", "column": "needs_input", "provisional": True},   # placeholder churn
            {"itemId": "c", "board": "feed", "category": "working", "column": "working"},
            {"itemId": "d", "board": "feed", "category": "completed", "column": "completed"},
            {"itemId": "e", "column": "needs_input"},                                                                     # an older card: column alone
        ]}
        self.assertEqual(km._needs_you_count(feed), 2)
        self.assertIn('a.get("category", a.get("column")) == _board_needs_you(a.get("board"))', inspect.getsource(km._needs_you_count))

    def test_the_notifications_diff_reads_the_boards_notify_set(self):
        src = inspect.getsource(km._feed_notifications_diff)
        self.assertIn('if col in _board_notify(a.get("board")):', src)
        self.assertNotIn("col in _NOTIFY_COLUMNS", src, "no literal set in the diff; the snapshot's entry check keeps _NOTIFY_COLUMNS")
        self.assertIn("_NOTIFY_COLUMNS", inspect.getsource(km._notify_prev_entry), "the stored snapshot's entries are still checked against the feed's set")


if __name__ == "__main__":
    unittest.main()
