#!/usr/bin/env python3
"""The chat page's approval box, kernel side (plans/notice-cards.md, "Action kinds and the held-mail card", 2026-09-19): the
session frame's status carries `notices`, this session's standing needs-you notices that carry actions (a held peer message's
Approve and Deny), read from the same projection the feed card reads with the cleared ledger applied; a decision (the expire
row) or a Clear drops the row; an informational notice or one without actions is not a decision and stays off the box. The
chat signature carries the rows' ids so the box and the ring move in one frame, and the chat page's markup places the box
between the transcript and the background box. Synthetic: a placeholder sid, invented names and text."""
import inspect
import json
import os
import sys
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))

SID = "11111111-2222-3333-4444-000000000902"   # a PRIVATE synthetic sid: the suite shares one state root across modules, and a names
#                                                entry left under the shared placeholder poisons a later module's route test (2026-09-19)
KSRC = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py")).read()


def _held(mid):
    return [{"label": "Approve", "kind": "quarantine", "body": {"mid": mid, "verdict": "approve"}},
            {"label": "Deny", "kind": "quarantine", "body": {"mid": mid, "verdict": "deny"}}]


class ChatNotices(unittest.TestCase):
    def setUp(self):
        for d in (km.jd.STATE / "notices", km.jd.STATE / "notices-archive"):
            if d.exists():
                for f in d.iterdir():
                    f.unlink()
        ledger = km.jd.STATE / "cleared.jsonl"
        if ledger.exists():
            ledger.unlink()
        km.jd.NAMES.mkdir(parents=True, exist_ok=True)
        (km.jd.NAMES / SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % (km.jd.STATE / "notes-api"))
        km.NAMES = km.jd.NAMES
        km._live_scope.names = None
        km._NOTICE_MEMO.clear(); km._CLEARED_MEMO["slot"] = None

    def tearDown(self):
        # remove what the tests wrote into the shared root: the names entry, the notice files, the ledger
        for f in (km.jd.NAMES / SID, km.jd.STATE / "cleared.jsonl"):
            if f.exists():
                f.unlink()
        for d in (km.jd.STATE / "notices", km.jd.STATE / "notices-archive"):
            if d.exists():
                for f in d.iterdir():
                    f.unlink()
        km._NOTICE_MEMO.clear(); km._CLEARED_MEMO["slot"] = None

    def test_the_box_lists_needs_you_notices_with_actions_each_action_with_its_kind(self):
        # getattr: at the base before the box the helper is absent, and the test reds on its behaviour
        rows = getattr(km, "_chat_notices", lambda sid: None)(SID)
        self.assertEqual(rows, [], "a session with no notice file has an empty box")
        km.post_notice(SID, "m1", "New message from api", "from TESTHOST:api to web, held because peer TESTHOST is DIRECTED\n\nhello",
                       producer="postal", actions=_held("m1"), needs_you=True, dismiss_on_action=True, now=100, t=100)
        km.post_notice(SID, "fig", "A new figure is ready", producer="figure", now=101, t=101)                       # informational: no decision
        km.post_notice(SID, "dropped", "1 message was not re-sent", producer="dropped-sends", needs_you=True, now=102, t=102)   # needs you, no action to take here
        with km._notice_lock:                                                          # an OLDER row, written before the kinds: its action carries a route
            km._notice_append(SID, {"op": "post", "t": 103, "key": "again", "rev": 1, "sid": SID, "title": "Send it again?", "body": "", "producer": "cli",
                                    "needsYou": True, "actions": [{"label": "Send again", "route": "/send", "body": {"text": "please retry"}}]})
        rows = km._chat_notices(SID)
        self.assertEqual([r["itemId"] for r in rows], ["notice:%s:m1:1" % SID, "notice:%s:again:1" % SID], "the two decisions, in post order")
        r = rows[0]
        self.assertEqual((r["key"], r["rev"], r["title"], r["producer"]), ("m1", 1, "New message from api", "postal"))
        self.assertEqual(r["body"], "from TESTHOST:api to web, held because peer TESTHOST is DIRECTED\n\nhello", "the message text is the body")
        self.assertEqual(r["actions"], _held("m1"), "the stored actions with their kind")
        self.assertEqual(rows[1]["actions"], [{"label": "Send again", "kind": "send", "route": "/send", "body": {"text": "please retry"}}], "an older row's route reads as its kind beside it")

    def test_a_decision_a_clear_and_an_expiry_drop_the_row(self):
        km.post_notice(SID, "m1", "t", producer="postal", actions=_held("m1"), needs_you=True, dismiss_on_action=True, now=100, t=100)
        km.post_notice(SID, "m2", "t", producer="postal", actions=_held("m2"), needs_you=True, dismiss_on_action=True, now=100, t=100)
        soon = int(km.time.time()) + 3600
        km.post_notice(SID, "m3", "t", producer="postal", actions=_held("m3"), needs_you=True, dismiss_on_action=True, now=100, t=100, expires_at=soon)
        self.assertEqual(len(km._chat_notices(SID)), 3)
        with km._notice_lock:                                                          # the runner's retirement on a decision
            km._notice_append(SID, {"op": "expire", "t": 200, "key": "m1", "rev": 1, "sid": SID})
        km._clear_ask("notice:%s:m2:1" % SID)                                           # the user's Clear on the feed card
        self.assertEqual([r["key"] for r in km._chat_notices(SID)], ["m3"], "the decided and the dismissed rows are off the box")
        saved = km.time.time
        try:
            km.time.time = lambda: soon + 1                                                # past m3's expiry
            self.assertEqual(km._chat_notices(SID), [], "an expired notice is off the box at the next read")
        finally:
            km.time.time = saved

    def test_the_owner_less_run_and_a_fault_give_an_empty_box(self):
        km.post_notice("", "k", "Remember the standup moved", producer="cli", needs_you=True, now=100, t=100)
        self.assertEqual(km._chat_notices(km.NOTICE_OWNERLESS_SID), [], "an owner-less card carries no actions: nothing to decide")
        saved = km._notice_projection
        try:
            def boom(*a, **k): raise OSError("unreadable")
            km._notice_projection = boom
            self.assertEqual(km._chat_notices(SID), [], "best-effort: a fault is an empty box, never a dead frame")
        finally:
            km._notice_projection = saved

    def test_the_session_frame_carries_the_rows_on_its_status_and_the_signature_carries_their_ids(self):
        src = inspect.getsource(km.build_session)
        self.assertIn('"needsYou": needs_you,', src)
        self.assertIn('"notices": _chat_notices(sid),', src, "beside needsYou on the STATUS, so a status-only delta carries a decision")
        self.assertIn("sig.append(_feed_needs_input_of(sid) is True)\n", KSRC)
        self.assertIn('sig.append(tuple(n["itemId"] for n in _chat_notices(sid)))', KSRC, "the chat signature: a hold posted or a decision taken brings a frame forward")
        labels = km._CHAT_SIG_LABELS
        self.assertEqual(labels[labels.index("needs") + 1], "notices", "one label per signature position, the new one right after needs (the builder appends them in that order)")

    def test_the_chat_page_places_the_box_between_the_transcript_and_the_background_box(self):
        body = km._chat_body()
        self.assertIn('<div id="notices" style="display:none"></div>', body)
        self.assertLess(body.index('id="content"'), body.index('id="notices"'), "after the transcript")
        self.assertLess(body.index('id="notices"'), body.index('id="bg-tasks"'), "above the background box (the user: a decision sits nearest the composer's eye line, above the agents)")
        self.assertLess(body.index('id="bg-tasks"'), body.index('id="composer"'))


if __name__ == "__main__":
    unittest.main()
