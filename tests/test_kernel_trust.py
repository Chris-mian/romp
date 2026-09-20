#!/usr/bin/env python3
"""Per-host trust model, kernel side: the remotes registry stores a trust level (trusted|directed|
isolated), defaulting to directed; set_trust validates + persists it; _remote_public/_tunnels expose it
(the channel the bus reads); the /tunnels/trust route drives it; and the held-mail backfill surfaces a held
message from a directed peer as a needs-you NOTICE card whose Approve and Deny are actions of the quarantine kind.

Synthetic only — hermetic temp STATE, placeholder hostnames/mids, invented notes-domain sessions.
"""
import http.client
import io
import json
import sys
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))


def _row(host, **extra):
    r = {"host": host, "kernel_port": 29855, "local_port": 5000, "bus_port": 5001, "token": "t",
         "proc": None, "status": "up", "detail": "", "sids": [], "trust": "directed"}
    r.update(extra)
    return r


class SetTrust(unittest.TestCase):
    def setUp(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")

    def test_default_is_directed_in_public_view(self):
        pub = km._remote_public(km._remotes["TESTHOST"])
        self.assertEqual(pub["trust"], "directed")

    def test_set_trust_updates_and_persists(self):
        pub, err = km.set_trust("TESTHOST", "trusted")
        self.assertIsNone(err)
        self.assertEqual(pub["trust"], "trusted")
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")
        # persistence: reload from remotes.json and confirm the level survived
        km._remotes_save()
        km._remotes.clear()
        km._remotes_load()
        self.assertEqual(km._remotes["TESTHOST"]["trust"], "trusted")

    def test_set_trust_rejects_bad_level(self):
        pub, err = km.set_trust("TESTHOST", "whatever")
        self.assertIsNone(pub)
        self.assertIn("trust must be one of", err)

    def test_set_trust_unattached_host_is_origin_only(self):
        # Trust is judged BY ORIGIN at delivery (the user 2026-07-25): a host with no tunnel here —
        # its mail arrives relayed through a hub — can carry a tier. The level lands in the
        # remembered-hosts table and reaches the bus as an origin-only row.
        calls = []
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: calls.append((h, t)) or True
        try:
            pub, err = km.set_trust("FARBOX", "trusted")
        finally:
            km._notify_bus_origin_trust = saved
        self.assertIsNone(err)
        self.assertEqual(pub, {"host": "FARBOX", "trust": "trusted", "originOnly": True})
        self.assertEqual(km.known_trust("FARBOX"), "trusted", "the remembered table IS the store")
        self.assertEqual(calls, [("FARBOX", "trusted")], "the bus learns the origin row now")

    def test_push_origin_trust_rows_covers_only_unattached(self):
        # The supervisor pushes remembered-but-unattached tiers once per (host, level); attached
        # hosts stay the (up, trust)-keyed full notify's job.
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        km._known.clear()                         # order-independent: other tests seed this table
        km._known_note("TESTHOST", "trusted")     # attached → not this path's job
        km._known_note("FARBOX", "isolated")      # unattached → pushed
        km._origin_trust_pushed.clear()
        calls = []
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: calls.append((h, t)) or True
        try:
            km._push_origin_trust_rows()
            km._push_origin_trust_rows()          # memoized: no duplicate push
            km._known_note("FARBOX", "directed")  # a level CHANGE re-pushes
            km._push_origin_trust_rows()
        finally:
            km._notify_bus_origin_trust = saved
        self.assertEqual(calls, [("FARBOX", "isolated"), ("FARBOX", "directed")])

    def test_load_defaults_missing_trust_to_directed(self):
        # a pre-trust remotes.json row (no "trust" key) reads back as directed
        km._remotes.clear()
        km._remotes["OLD"] = {k: v for k, v in _row("OLD").items() if k != "trust"}
        km._remotes_save()
        km._remotes.clear()
        km._remotes_load()
        self.assertEqual(km._remotes["OLD"]["trust"], "directed")


class TrustRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", path, json.dumps(body),
                  {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
        r = c.getresponse()
        data = json.loads(r.read().decode() or "{}")
        c.close()
        return r.status, data

    def test_route_sets_trust(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        code, data = self._post("/tunnels/trust", {"host": "TESTHOST", "trust": "isolated"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tunnel"]["trust"], "isolated")

    def test_route_rejects_bad_level(self):
        km._remotes.clear()
        km._remotes["TESTHOST"] = _row("TESTHOST")
        code, data = self._post("/tunnels/trust", {"host": "TESTHOST", "trust": "bogus"})
        self.assertEqual(code, 400)
        self.assertFalse(data["ok"])

    def test_route_unattached_host_sets_origin_trust(self):
        km._remotes.clear()
        saved = km._notify_bus_origin_trust
        km._notify_bus_origin_trust = lambda h, t: True
        try:
            code, data = self._post("/tunnels/trust", {"host": "GHOST", "trust": "trusted"})
        finally:
            km._notify_bus_origin_trust = saved
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tunnel"], {"host": "GHOST", "trust": "trusted", "originOnly": True})


WEB = "11111111-2222-3333-4444-000000000901"     # the recipient session the names registry knows: a PRIVATE synthetic sid (the
#                                                  suite runs every module in one process over one state root, and a names entry
#                                                  left under the shared placeholder sid made a later module's rename of that sid
#                                                  to "web" its own-name no-op, 2026-09-19); _HeldMailFixture removes what these write, nothing else


OTHER = "11111111-2222-3333-4444-000000000903"   # a second session: the recipient of a message another card must not decide
LATE = "11111111-2222-3333-4444-000000000904"    # a recipient the names registry learns only after its hold was posted owner-less
_HELD_SIDS = (WEB, OTHER, LATE)
_HELD_MIDS = set()                               # every held file these tests write, removed at their end


class _HeldMailFixture:
    """The held-mail tests write into the run's SHARED state root (every kernel test module runs in one process over one root):
    they must remove only what they wrote (the manager's review of PR 1885, low 3). Their own sids' files (names, notices,
    archive, index) and their held files go; the shared files they append to (the owner-less home, its archive and index,
    the cleared ledger) are restored to the bytes they had before the test."""

    @staticmethod
    def _shared():
        out = {}
        f = km.jd.STATE / "cleared.jsonl"
        out["cleared.jsonl"] = f.read_bytes() if f.exists() else None
        for d in ("notices", "notices-archive"):
            dd = km.jd.STATE / d
            if dd.exists():
                for f in dd.iterdir():
                    if f.name.startswith("notes"):
                        out[d + "/" + f.name] = f.read_bytes()
        return out

    @staticmethod
    def begin(tc):
        tc._held_before = _HeldMailFixture._shared()
        km.jd.NAMES.mkdir(parents=True, exist_ok=True)
        km.NAMES = km.jd.NAMES                          # the direct registry read, off any cycle's names snapshot an earlier class left
        km._live_scope.names = None
        _HeldMailFixture.memos()

    @staticmethod
    def memos():
        getattr(km, "_HELD_MAIL_MEMO", {})["slot"] = None; getattr(km, "_HELD_MAIL_SAID", set()).clear()
        km._NOTICE_MEMO.clear(); km._CLEARED_MEMO["slot"] = None

    @staticmethod
    def end(tc):
        for sid in _HELD_SIDS:
            for f in (km.jd.NAMES / sid, km.jd.STATE / "notices" / (sid + ".jsonl"), km.jd.STATE / "notices-archive" / (sid + ".jsonl"),
                      km.jd.STATE / "notices-archive" / (sid + ".revs.json")):
                if f.exists():
                    f.unlink()
        qdir = km.jd.STATE / "postal" / "quarantine"
        for mid in list(_HELD_MIDS):
            f = qdir / (mid + ".json")
            if f.exists():
                f.unlink()
        _HELD_MIDS.clear()
        after = _HeldMailFixture._shared()
        for rel in set(after) | set(tc._held_before):
            f = km.jd.STATE / rel
            before = tc._held_before.get(rel)
            if before is None:
                if f.exists():
                    f.unlink()                          # the test created it
            elif after.get(rel) != before:
                f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(before)
        _HeldMailFixture.memos()


class HeldMailCards(unittest.TestCase):
    """A message held from a DIRECTED peer is a NOTICE CARD (plans/notice-cards.md, "Action kinds and the held-mail card",
    2026-09-19): the kernel's backfill posts one under the RECIPIENT for every held file the notice store has no row for,
    key = the message id, producer postal, Approve and Deny of the quarantine kind, dismissed on the decision. Idempotent over
    the live rows and the archive, memoized on the directory's stat; a recipient the kernel does not know files owner-less
    with no actions. Synthetic: a placeholder recipient sid, invented session names and text."""

    def _write_held(self, mid, frm="api", to="web", to_id=WEB, origin="TESTHOST", body="ship the parser fix", at=1000):
        qdir = km.jd.STATE / "postal" / "quarantine"
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / (mid + ".json")).write_text(json.dumps(
            {"mid": mid, "to": to, "toId": to_id, "frm": frm, "frmId": "id-api", "body": body, "kind": "coordinate", "origin": origin, "at": at}))
        _HELD_MIDS.add(mid)

    def _name(self, sid, name):
        (km.jd.NAMES / sid).write_text("%s\t%s\t#1EA1EB\t#ffffff\n" % (name, km.jd.STATE / "notes-api"))

    def setUp(self):
        _HeldMailFixture.begin(self)
        HeldMailCards._name(self, WEB, "web")           # by the class: HeldMailDecision and BusPortRecord borrow this setUp

    def tearDown(self):
        _HeldMailFixture.end(self)

    def _cards(self, alive=()):
        return km._notice_cards(2000, km._cleared_ids(), set(alive))

    def test_a_held_message_is_a_needs_you_notice_card_under_the_recipient_with_approve_and_deny_of_the_quarantine_kind(self):
        self._write_held("qc-1")
        cards = self._cards()
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual((c["itemId"], c["sid"], c["name"]), ("notice:%s:qc-1:1" % WEB, WEB, "web"), "keyed by the message id, under the recipient")
        self.assertEqual((c["column"], c["category"], c["board"]), ("needs_input", "needs_input", "feed"))
        self.assertEqual(c["text"], "New message from api")
        self.assertEqual(c["t"], 1000, "the card's time is the hold's, never the build's clock")
        n = c["notice"]
        self.assertEqual(n["producer"], "postal")
        self.assertEqual(n["body"], "from TESTHOST:api to web, held because peer TESTHOST is DIRECTED\n\nship the parser fix", "the route line, then the message text")
        self.assertEqual(n["actions"], [{"label": "Approve", "kind": "quarantine", "body": {"mid": "qc-1", "verdict": "approve"}},
                                        {"label": "Deny", "kind": "quarantine", "body": {"mid": "qc-1", "verdict": "deny"}}], "two actions of the KIND, no Edit")
        self.assertTrue(n["dismissOnAction"]); self.assertIsNone(c["blocked"], "no hand-built blocked flavour")

    def test_live_is_the_recipients_from_the_alive_roster(self):
        # 2026-09-19: every notice card said live False, so the card modal struck the recipient's name through as a dead session's
        self._write_held("qc-2")
        self.assertEqual([c["live"] for c in self._cards()], [False])
        self.assertEqual([c["live"] for c in self._cards(alive={WEB})], [True])

    def test_the_backfill_is_idempotent_and_memoized_on_the_directory(self):
        self._write_held("qc-3")
        self.assertEqual(km._held_mail_backfill(), 1)
        self.assertEqual(km._held_mail_backfill(), 0, "the memo: an unmoved directory posts nothing")
        km._HELD_MAIL_MEMO["slot"] = None
        self.assertEqual(km._held_mail_backfill(), 0, "a live post row for the key: never a second card")
        self._write_held("qc-4", body="another")
        self.assertEqual(km._held_mail_backfill(), 1, "a moved directory: only the new hold is posted")
        self.assertEqual(sorted(c["itemId"] for c in self._cards()), ["notice:%s:qc-3:1" % WEB, "notice:%s:qc-4:1" % WEB])
        self.assertEqual([r["op"] for r in km._notice_rows(WEB)], ["post", "post"], "two rows, one per hold")

    def test_a_decided_or_dismissed_message_is_never_re_posted_even_after_the_archive_pass(self):
        self._write_held("qc-5"); self._write_held("qc-6")
        km._held_mail_backfill()
        iid5 = "notice:%s:qc-5:1" % WEB
        with km._notice_lock:                          # the decision's retirement, as the runner writes it
            km._notice_append(WEB, {"op": "expire", "t": 1500, "key": "qc-5", "rev": 1, "sid": WEB})
        km._clear_ask("notice:%s:qc-6:1" % WEB)        # the user's Clear on the other
        self.assertEqual([c["itemId"] for c in self._cards()], [], "the decided card and the dismissed card are both off the board")
        km._HELD_MAIL_MEMO["slot"] = None
        self.assertEqual(km._held_mail_backfill(), 0, "the live rows hold both keys")
        moved = km._compact_notices(now=5000)          # the retention pass moves the expired and the dismissed rows to the archive
        self.assertGreater(moved, 0)
        km._HELD_MAIL_MEMO["slot"] = None; km._NOTICE_MEMO.clear()
        self.assertEqual(km._held_mail_backfill(), 0, "the archive's revision index holds both keys: a decided card stays decided")
        self.assertEqual([c["itemId"] for c in self._cards()], [])
        self.assertNotIn(iid5, [c["itemId"] for c in self._cards()])

    def test_an_unknown_recipient_files_owner_less_with_no_actions(self):
        self._write_held("qc-7", to="gone", to_id="11111111-2222-3333-4444-999999999999")
        cards = self._cards()
        self.assertEqual(len(cards), 1); c = cards[0]
        self.assertEqual((c["sid"], c["name"], c["column"]), (km.NOTICE_OWNERLESS_SID, km.NOTICE_OWNERLESS_NAME, "completed"), "no session to route the decision: the owner-less run, informational")
        self.assertEqual(c["text"], "New message from api for gone"); self.assertEqual(c["notice"]["actions"], [])

    def test_a_held_file_whose_id_is_no_key_is_skipped_and_an_empty_directory_posts_nothing(self):
        self._write_held("bad id!")
        self.assertEqual(km._held_mail_backfill(), 0); self.assertEqual(self._cards(), [])
        qdir = km.jd.STATE / "postal" / "quarantine"
        for f in qdir.iterdir():
            f.unlink()
        km._HELD_MAIL_MEMO["slot"] = None
        self.assertEqual(km._held_mail_backfill(), 0)
        import shutil
        shutil.rmtree(qdir)
        km._HELD_MAIL_MEMO["slot"] = None
        self.assertEqual(km._held_mail_backfill(), 0, "no directory: nothing held, no crash")

    def test_a_hold_posted_owner_less_is_re_homed_once_its_recipient_is_known_and_a_dismissed_one_is_not(self):
        # the manager's review of PR 1885, low 1 (executed: three cards for two holds): the recipient unknown at the first build,
        # the card files owner-less; the names entry lands and another hold moves the directory: the first hold must not gain a
        # second card beside the first, it moves home (the actionable card under the recipient, the informational one expired)
        self._write_held("rh-1", to="late", to_id=LATE)
        self.assertEqual(km._held_mail_backfill(), 1)
        self.assertEqual([(c["sid"], len(c["notice"]["actions"])) for c in self._cards() if c["notice"]["key"] == "rh-1"], [(km.NOTICE_OWNERLESS_SID, 0)], "owner-less, informational")
        self._name(LATE, "late"); km._live_scope.names = None
        self._write_held("rh-2", to="late", to_id=LATE, body="a second hold")
        self.assertEqual(km._held_mail_backfill(), 2, "the second hold and the first, re-homed")
        mine = [c for c in self._cards() if c["notice"]["key"] in ("rh-1", "rh-2")]
        self.assertEqual(sorted((c["sid"], c["notice"]["key"], len(c["notice"]["actions"])) for c in mine),
                         [(LATE, "rh-1", 2), (LATE, "rh-2", 2)], "two holds, two cards, both under the recipient with their decisions")
        self.assertIn(("expire", "rh-1"), [(r["op"], r["key"]) for r in km._notice_rows(km.NOTICE_OWNERLESS_SID)], "the owner-less card was expired, not left beside")
        km._HELD_MAIL_MEMO["slot"] = None
        self.assertEqual(km._held_mail_backfill(), 0, "and nothing posts again")
        # a hold dismissed while owner-less stays dismissed: the user's Clear is a decision about that message's card
        (km.jd.NAMES / LATE).unlink(); km._live_scope.names = None
        self._write_held("rh-3", to="late", to_id=LATE, body="a third hold")
        self.assertEqual(km._held_mail_backfill(), 1)
        km._clear_ask("notice:%s:rh-3:1" % km.NOTICE_OWNERLESS_SID)
        self.assertGreater(km._compact_notices(now=10**9), 0, "the pass archived the dismissed row")
        self._name(LATE, "late"); km._live_scope.names = None; km._HELD_MAIL_MEMO["slot"] = None; km._NOTICE_MEMO.clear()
        self.assertEqual(km._held_mail_backfill(), 0, "an archived (dismissed) owner-less card is not re-posted under the recipient")
        self.assertNotIn("rh-3", [c["notice"]["key"] for c in self._cards()])

    def test_a_quarantine_action_naming_a_message_held_for_another_session_is_refused_at_the_post(self):
        # the manager's review of PR 1885, medium: a producer's card under one session's name and colour must not route the
        # user's click at another session's mail; the held file's recipient must be the card's owner (a mid with no file is the
        # bus's to refuse at the click)
        self._name(OTHER, "api")
        self._write_held("xo-1", to="api", to_id=OTHER)
        row, err = km.post_notice(WEB, "xo-1", "New message from api", producer="postal", actions=km._held_mail_actions("xo-1"), needs_you=True, now=100)
        self.assertEqual((row, err), (None, "a quarantine action's message is held for another session, not this card's owner"))
        row, err = km.post_notice(OTHER, "xo-1", "New message from api", producer="postal", actions=km._held_mail_actions("xo-1"), needs_you=True, now=100)
        self.assertIsNone(err, "the recipient's own card is accepted")
        row, err = km.post_notice(WEB, "nofile", "t", producer="postal", actions=km._held_mail_actions("nofile-1"), needs_you=True, now=100)
        self.assertIsNone(err, "no held file to consult: the click's bus answers")

    def test_the_feed_payload_names_this_machine(self):
        import inspect
        self.assertIn('"selfHost": _self_host(),', inspect.getsource(km.build_feed))

    def test_build_feed_lists_no_hand_built_quarantine_family(self):
        import inspect
        src = inspect.getsource(km.build_feed)
        self.assertNotIn("_quarantine_cards(", src, "the family is gone: the held message rides _notice_cards")
        self.assertIn("_notice_cards(now, cleared, {s[\"sid\"] for s in alive})", src, "the notice cards take the build's alive roster")
        self.assertFalse(hasattr(km, "_quarantine_cards"))


class HeldMailDecision(unittest.TestCase):
    """The decision is a notice ACTION of the quarantine kind over the noticeAction op: the kernel runs the STORED action
    through the bus's act road with the card's owner as the recipient, a deny's note as the bus's feedback, and answers the
    asking pane by the card's id (noticeActionDone), so a refusal re-arms that card's buttons alone and says why. The
    quarantineDecision and quarantineRefused ops left with the hand-built family (2026-09-19)."""

    def setUp(self):
        HeldMailCards.setUp(self)
        self._saved = km._bus_quarantine_act, km._mark_views_dirty
        self.sent, self.dirtied, self.acts = [], [], []
        km._mark_views_dirty = lambda: self.dirtied.append(True)
        self.client = {"app": "feed", "wid": "w1", "alive": True, "send": lambda raw: self.sent.append(json.loads(raw))}
        HeldMailCards._write_held(self, "qc-7"); getattr(km, "_held_mail_backfill", lambda: 0)()
        self.dirtied.clear()                            # the backfill's post dirtied the views; the decisions below are what is measured
        self.iid = "notice:%s:qc-7:1" % WEB

    def tearDown(self):
        km._bus_quarantine_act, km._mark_views_dirty = self._saved
        HeldMailCards.tearDown(self)

    def _op(self, body, inp=None, kind="quarantine"):
        msg = {"type": "noticeAction", "itemId": self.iid, "sid": WEB, "kind": kind, "body": body}
        if inp is not None:
            msg["input"] = inp
        km.Handler._dispatch_ws(None, msg, self.client)

    def test_a_refused_verdict_answers_the_card_by_its_id_and_changes_no_view(self):
        km._bus_quarantine_act = lambda body: (self.acts.append(body) or (False, "the recipient is no longer live"))
        self._op({"mid": "qc-7", "verdict": "approve"})
        self.assertEqual(self.acts, [{"mid": "qc-7", "action": "approve", "sid": WEB}], "the stored body as the bus's act, the card's owner as the recipient")
        self.assertEqual(self.sent, [{"type": "noticeActionDone", "itemId": self.iid, "ok": False, "error": "the recipient is no longer live"}],
                         "the reply names the card, so the feed re-arms that card's buttons alone")
        self.assertEqual(self.dirtied, [], "a refused verdict changes no view")
        self.assertEqual([r["op"] for r in km._notice_rows(WEB)], ["post"], "no retirement on a refusal")
        self.assertEqual([c["itemId"] for c in km._notice_cards(2000, km._cleared_ids())], [self.iid], "the card stays")

    def test_an_accepted_verdict_retires_the_card_and_rebuilds_the_views(self):
        km._bus_quarantine_act = lambda body: (self.acts.append(body) or (True, ""))
        self._op({"mid": "qc-7", "verdict": "deny"}, {"note": "  not now,   ask after the release "})
        self.assertEqual(self.acts, [{"mid": "qc-7", "action": "deny", "sid": WEB, "feedback": "not now, ask after the release"}], "a deny's note rides as the bus's feedback, whitespace collapsed")
        self.assertEqual(self.sent, [{"type": "noticeActionDone", "itemId": self.iid, "ok": True, "error": ""}])
        self.assertEqual([r["op"] for r in km._notice_rows(WEB)], ["post", "expire", "acted"], "the decision expires the card and marks the action spent")
        self.assertIn(self.iid, km._cleared_ids(), "dismissOnAction: the card is off the board at once")
        self.assertEqual(km._notice_cards(2000, km._cleared_ids()), [])
        self.assertTrue(self.dirtied)
        # a second click on the same card: the bus is never asked again
        self._op({"mid": "qc-7", "verdict": "approve"})
        self.assertEqual(len(self.acts), 1); self.assertEqual(self.sent[-1]["ok"], False)

    def test_the_click_may_add_only_the_input_the_kind_names(self):
        km._bus_quarantine_act = lambda body: (self.acts.append(body) or (True, ""))
        self._op({"mid": "qc-7", "verdict": "approve"}, {"note": "why"})
        self.assertEqual((self.sent[-1]["ok"], self.sent[-1]["error"]), (False, "the action takes no 'note' from the click"), "an approve carries no note")
        self._op({"mid": "qc-7", "verdict": "deny"}, {"text": "edited words"})
        self.assertEqual((self.sent[-1]["ok"], self.sent[-1]["error"]), (False, "the action takes no 'text' from the click"), "nobody edits held mail")
        self._op({"mid": "qc-7", "verdict": "edit"})
        self.assertEqual((self.sent[-1]["ok"], self.sent[-1]["error"]), (False, "no such action on that card"), "a verdict the card never stored")
        self._op({"mid": "other", "verdict": "approve"})
        self.assertEqual(self.sent[-1]["error"], "no such action on that card", "another message's id is not this card's action")
        self.assertEqual(self.acts, [], "the bus never heard of any of it")

    def test_a_verdict_on_a_message_held_for_another_session_is_refused_before_the_bus(self):
        # the manager's review of PR 1885, medium (executed at 178a61af: the click on a card under api delivered web's held
        # message): a row that names another session's held message, written before the post-time check or by hand, is
        # refused at the click; the bus is never asked
        HeldMailCards._name(self, OTHER, "api")
        HeldMailCards._write_held(self, "xo-7", to="api", to_id=OTHER)
        with km._notice_lock:
            km._notice_append(WEB, {"op": "post", "t": 100, "key": "xo-7", "rev": 1, "sid": WEB, "title": "New message from api", "body": "", "producer": "postal",
                                    "needsYou": True, "dismissOnAction": True, "actions": km._held_mail_actions("xo-7")})
        km._bus_quarantine_act = lambda body: (self.acts.append(body) or (True, ""))
        iid = "notice:%s:xo-7:1" % WEB
        km.Handler._dispatch_ws(None, {"type": "noticeAction", "itemId": iid, "sid": WEB, "kind": "quarantine", "body": {"mid": "xo-7", "verdict": "approve"}}, self.client)
        self.assertEqual(self.sent[-1], {"type": "noticeActionDone", "itemId": iid, "ok": False, "error": "that message is held for another session, not this card's owner"})
        self.assertEqual(self.acts, [], "the bus was never asked")
        self.assertEqual([r["op"] for r in km._notice_rows(WEB) if r.get("key") == "xo-7"], ["post"], "the card stands, undecided")
        self.assertTrue((km.jd.STATE / "postal" / "quarantine" / "xo-7.json").exists(), "the message is still held")

    def test_the_older_ops_are_gone(self):
        km._bus_quarantine_act = lambda body: (self.acts.append(body) or (True, ""))
        km.Handler._dispatch_ws(None, {"type": "quarantineDecision", "mid": "qc-7", "action": "approve", "sid": WEB}, self.client)
        self.assertEqual((self.acts, self.sent), ([], [{"type": "unknownOp", "op": "quarantineDecision"}]), "quarantineDecision is an op the kernel no longer knows; the bus is never asked")
        import inspect
        self.assertNotIn("quarantineRefused", inspect.getsource(km.Handler._dispatch_ws))


class MirrorTrust(unittest.TestCase):
    """mirror_trust (the user 2026-07-26): sets OUR level for a host as ITS level for US, through the
    tunnel forward + that machine's serve token — the human with both tokens acting on both kernels.
    Deliberately the ONLY reciprocity: a peer can never open our gate by declaring trust."""

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.pop("boxa", None)

    def _stub_remote(self, seen):
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path
                seen["token"] = self.headers.get("X-Romp-Token")
                seen["body"] = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                out = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return srv.server_address[1]

    def test_mirror_posts_our_level_through_the_tunnel_with_the_remote_token(self):
        seen = {}
        port = self._stub_remote(seen)
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=port, token="remote-tok", trust="trusted")
        res, err = km.mirror_trust("boxa")
        self.assertIsNone(err)
        self.assertEqual(res, {"host": "boxa", "trust": "trusted"})
        self.assertEqual(seen["path"], "/tunnels/trust", "the remote's own persisting route does the write")
        self.assertEqual(seen["token"], "remote-tok", "authorized with THAT machine's serve token")
        self.assertEqual(seen["body"], {"host": km._self_host(), "trust": "trusted"},
                         "the remote is told to hold THIS machine at our current level")

    def test_mirror_without_a_tunnel_errors_plainly(self):
        res, err = km.mirror_trust("nosuchhost")
        self.assertIsNone(res)
        self.assertTrue(err.startswith("no attached"), err)

    def test_mirror_without_a_token_errors_plainly(self):
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=1, token="", trust="trusted")
        res, err = km.mirror_trust("boxa")
        self.assertIsNone(res)
        self.assertIn("no admin path", err)


def _stub_kernel(cleanup_with, seen=None, tunnels=None):
    """A pretend remote kernel on a loopback port: records any POST into `seen` (mirror/remote-trust
    tests) and answers GET /tunnels with `tunnels` (pairs tests)."""
    from http.server import BaseHTTPRequestHandler

    class H(BaseHTTPRequestHandler):
        def _out(self, payload):
            out = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def do_POST(self):
            if seen is not None:
                seen["path"] = self.path
                seen["token"] = self.headers.get("X-Romp-Token")
                seen["body"] = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self._out({"ok": True})

        def do_GET(self):
            self._out(tunnels or {})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cleanup_with(srv.shutdown)
    return srv.server_address[1]


class RemoteTrust(unittest.TestCase):
    """remote_trust (the user 2026-08-11): the hub sets ON one attached machine ITS trust level for
    another host — the popover's 'Between your machines' rows. Same boundary as mirror_trust: the
    write crosses the on-host tunnel with that machine's own serve token, and that machine's own
    /tunnels/trust route persists it; a peer can never raise its own standing."""

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.pop("boxa", None)

    def test_writes_the_pair_level_through_the_holders_tunnel(self):
        seen = {}
        port = _stub_kernel(self.addCleanup, seen=seen)
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=port, token="remote-tok", trust="directed")
        res, err = km.remote_trust("boxa", "boxb", "trusted")
        self.assertIsNone(err)
        self.assertEqual(res, {"onHost": "boxa", "host": "boxb", "trust": "trusted"})
        self.assertEqual(seen["path"], "/tunnels/trust", "the holder's own persisting route does the write")
        self.assertEqual(seen["token"], "remote-tok", "authorized with the HOLDING machine's serve token")
        self.assertEqual(seen["body"], {"host": "boxb", "trust": "trusted"},
                         "boxa is told to hold boxb at the chosen level")

    def test_bad_level_refused_before_any_dial(self):
        res, err = km.remote_trust("boxa", "boxb", "bogus")
        self.assertIsNone(res)
        self.assertIn("trust must be one of", err)

    def test_without_a_tunnel_errors_plainly(self):
        res, err = km.remote_trust("nosuchhost", "boxb", "trusted")
        self.assertIsNone(res)
        self.assertTrue(err.startswith("no attached"), err)

    def test_a_machine_never_tiers_its_own_mail(self):
        res, err = km.remote_trust("boxa", "boxa", "trusted")
        self.assertIsNone(res)
        self.assertIn("own mail", err)


class PairsSnapshot(unittest.TestCase):
    """pairs_snapshot: the hub reads each attached machine's own trust table over its tunnel and
    assembles per-pair directions. '' = the holder has no explicit row (the bus treats a relayed
    origin as directed); None + a named per-host error = that machine was unreadable this pass —
    surfaced, never silently dropped (fail loudly)."""

    def setUp(self):
        # these tests assert the WHOLE hosts map, and the kernel module is ONE object per process for
        # every test file that loads it under this name — so start from an empty map and put back
        # exactly what was there (under xdist another file's leftover row landed in the snapshot,
        # 2026-09-02); popping only this class's own hosts left any other file's row in place
        with km._remotes_lock:
            self._saved = dict(km._remotes)
            km._remotes.clear()

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.clear()
            km._remotes.update(self._saved)

    def test_pairs_read_both_directions_from_each_machines_own_table(self):
        # boxa holds boxb via an attached-tunnel row; boxb holds boxa via a relay (viaReach) row —
        # the three row kinds a tier can live on are all consulted.
        pa = _stub_kernel(self.addCleanup, tunnels={"tunnels": [{"host": "boxb", "trust": "trusted"}],
                                                    "known": [], "viaReach": []})
        pb = _stub_kernel(self.addCleanup, tunnels={"tunnels": [], "known": [],
                                                    "viaReach": [{"host": "boxa", "trust": "isolated"}]})
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=pa, token="ta")
            km._remotes["boxb"] = _row("boxb", local_port=pb, token="tb")
        snap = km.pairs_snapshot()
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["hosts"], {"boxa": {"ok": True}, "boxb": {"ok": True}})
        self.assertEqual(snap["pairs"], [{"a": "boxa", "b": "boxb", "ab": "trusted", "ba": "isolated"}])

    def test_no_explicit_row_reads_empty_never_an_invented_level(self):
        pa = _stub_kernel(self.addCleanup, tunnels={"tunnels": [], "known": [], "viaReach": []})
        pb = _stub_kernel(self.addCleanup, tunnels={"tunnels": [],
                                                    "known": [{"host": "boxa", "trust": "trusted"}],
                                                    "viaReach": []})
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=pa, token="ta")
            km._remotes["boxb"] = _row("boxb", local_port=pb, token="tb")
        snap = km.pairs_snapshot()
        self.assertEqual(snap["pairs"], [{"a": "boxa", "b": "boxb", "ab": "", "ba": "trusted"}])

    def test_an_unreadable_machine_carries_its_error_not_a_guess(self):
        pa = _stub_kernel(self.addCleanup, tunnels={"tunnels": [{"host": "boxb", "trust": "directed"}]})
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=pa, token="ta")
            km._remotes["boxb"] = _row("boxb", status="down")
        snap = km.pairs_snapshot()
        self.assertEqual(snap["hosts"]["boxb"], {"ok": False, "error": "not connected"})
        self.assertEqual(snap["pairs"], [{"a": "boxa", "b": "boxb", "ab": "directed", "ba": None}])


class PairRoutes(unittest.TestCase):
    """Route wiring for the pair section: GET /tunnels/pairs answers the snapshot; POST
    /tunnels/trust-remote proxies the write and maps errors to honest statuses."""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        with km._remotes_lock:
            km._remotes.clear()

    def _call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, None if body is None else json.dumps(body),
                  {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
        r = c.getresponse()
        data = json.loads(r.read().decode() or "{}")
        c.close()
        return r.status, data

    def test_pairs_route_answers_empty_world(self):
        code, data = self._call("GET", "/tunnels/pairs")
        self.assertEqual(code, 200)
        self.assertEqual(data, {"ok": True, "hosts": {}, "pairs": []})

    def test_trust_remote_route_round_trips_to_the_stub(self):
        seen = {}
        port = _stub_kernel(self.addCleanup, seen=seen)
        with km._remotes_lock:
            km._remotes["boxa"] = _row("boxa", local_port=port, token="remote-tok")
        code, data = self._call("POST", "/tunnels/trust-remote",
                                {"onHost": "boxa", "host": "boxb", "trust": "trusted"})
        self.assertEqual(code, 200)
        self.assertEqual(data, {"ok": True, "set": {"onHost": "boxa", "host": "boxb", "trust": "trusted"}})
        self.assertEqual(seen["body"], {"host": "boxb", "trust": "trusted"})

    def test_trust_remote_route_maps_errors_to_statuses(self):
        code, data = self._call("POST", "/tunnels/trust-remote",
                                {"onHost": "boxa", "host": "boxb", "trust": "bogus"})
        self.assertEqual((code, data["ok"]), (400, False))
        code, data = self._call("POST", "/tunnels/trust-remote",
                                {"onHost": "ghost", "host": "boxb", "trust": "trusted"})
        self.assertEqual((code, data["ok"]), (404, False))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class BusPortRecord(unittest.TestCase):
    """The kernel's loopback dials of the bus read the bus's own port record ahead of the environment (2026-09-18): a kernel
    and a bus that read ROMP_POSTAL_PORT from different environments dialed different ports, and a held message's approve
    reached a bus that never held it ("no held message"). Hermetic: the record under this test's state root, a stub bus on a
    free port standing for the bus that holds the file."""

    def setUp(self):
        self.rec = km.jd.STATE / "postal" / "postal-port"
        self.rec.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.rec.unlink()
        except FileNotFoundError:
            pass
        km._BUS_PORT_SAID[0] = None
        self._saved_ens = km._BUS_ENSURED[0]; km._BUS_ENSURED[0] = True   # this kernel ensured its bus: the record may be trusted
        self._err, self._saved_bp = io.StringIO(), km.BUS_PORT
        self._saved_stderr = sys.stderr; sys.stderr = self._err

    def tearDown(self):
        sys.stderr = self._saved_stderr
        km.BUS_PORT = self._saved_bp
        km._BUS_ENSURED[0] = self._saved_ens
        km._BUS_PORT_SAID[0] = None
        try:
            self.rec.unlink()
        except FileNotFoundError:
            pass

    def _rec(self, port, pid=None, tok=None):
        """A record as the bus writes it: this kernel's token mark unless a foreign one is asked for."""
        return json.dumps({"port": port, "pid": os.getpid() if pid is None else pid, "tok": km._bus_token_mark() if tok is None else tok})

    def _stub_bus(self, seen):
        from http.server import BaseHTTPRequestHandler   # the module's own idiom: imported where the stub is built
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
                out = json.dumps({"ok": True}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return srv.server_address[1]

    def test_the_record_wins_over_the_environment_and_the_environment_is_the_fallback(self):
        km.BUS_PORT = 1                                            # the environment's word: a port nothing answers on
        self.assertEqual(km._bus_port(), 1, "no record: the environment")
        self.rec.write_text(self._rec(45678))
        self.assertEqual(km._bus_port(), 45678, "the record names the bound port, a live pid and this kernel's token mark: it wins")
        self.rec.write_text(self._rec(45679, pid=2 ** 22 + 12345))   # a pid that does not run: a stale record
        self.assertEqual(km._bus_port(), 1, "a stale record (its pid gone) is ignored: the environment")
        self.rec.write_text(self._rec(45680, tok="0123456789abcdef"))   # another bus's record: a token mark that is not ours
        self.assertEqual(km._bus_port(), 1, "a foreign record (another bus, another world, a reused pid) is ignored: the environment")
        self.rec.write_text(json.dumps({"port": 45681, "pid": os.getpid()}))   # a record with no mark (an older bus): never trusted
        self.assertEqual(km._bus_port(), 1)
        # a kernel that ensured NO bus (client-only, a lab's, an in-process test's) dials the environment whatever the record says
        self.rec.write_text(self._rec(45682))
        km._BUS_ENSURED[0] = False
        self.assertEqual(km._bus_port(), 1, "no ensure, no record: the environment")
        km._BUS_ENSURED[0] = True
        self.assertEqual(km._bus_port(), 45682, "the ensure is the event that makes the bus this kernel's")
        self.rec.write_text("torn")
        self.assertEqual(km._bus_port(), 1, "a torn record: the environment, never a raise")
        self.rec.write_text(self._rec(0))
        self.assertEqual(km._bus_port(), 1, "a record with no port: the environment")

    def test_the_census_line_says_the_port_and_its_source_once_and_names_a_mismatch_with_the_environment(self):
        km.BUS_PORT = 25302
        km._bus_port(); km._bus_port()
        lines = [l for l in self._err.getvalue().splitlines() if "postal bus dialed" in l]
        self.assertEqual(lines, ["romp-kernel: postal bus dialed on 127.0.0.1:25302 from the environment"], "said once, no mismatch when the environment is the source")
        self.rec.write_text(self._rec(45678))
        km._bus_port(); km._bus_port()
        lines = [l for l in self._err.getvalue().splitlines() if "postal bus dialed" in l]
        self.assertEqual(len(lines), 2, "a change is said again, once")
        self.assertIn("127.0.0.1:45678 from the record (ROMP_POSTAL_PORT says 25302: the environment and the bus disagree; the record wins)", lines[1])

    def test_a_kernel_on_one_port_and_a_bus_bound_on_another_still_reach_the_bus_that_holds_the_file(self):
        # the fault of 2026-09-18, red at main: the kernel's environment names a port nothing answers on while the bus that holds
        # the message is bound elsewhere and says so in its record; the approve reaches the record's bus
        seen = []
        bus_port = self._stub_bus(seen)
        km.BUS_PORT = 1
        self.rec.write_text(self._rec(bus_port))
        ok, err = km._bus_quarantine_act({"mid": "px-1.2_abc.TESTHOST", "action": "approve", "sid": "11111111-2222-3333-4444-555555555555"})
        self.assertEqual((ok, err), (True, ""), "the record's bus answered ok: an empty error on a success (the review of PR 1885, low 2): %r" % err)
        self.assertEqual(seen[0][0], "/quarantine/act"); self.assertEqual(seen[0][1]["mid"], "px-1.2_abc.TESTHOST"); self.assertEqual(seen[0][1]["sid"], "11111111-2222-3333-4444-555555555555")

    def test_a_record_another_world_left_cannot_redirect_a_dial_a_test_or_an_operator_pointed_elsewhere(self):
        # the suite found it first (2026-09-18): every kernel test module shares one event-model state root, so a record one
        # world wrote outlived it, and a module that pointed BUS_PORT at its own stub bus reached the machine's real bus
        # instead ("token required"). The mark closes it: a record is trusted only when its token mark is this kernel's own.
        seen = []
        stub = self._stub_bus(seen)
        km.BUS_PORT = stub
        self.rec.write_text(json.dumps({"port": 25302, "pid": os.getpid(), "tok": "not-this-kernels-mark"}))
        ok, err = km._bus_quarantine_act({"mid": "px-1.2_abc.TESTHOST", "action": "approve"})
        self.assertEqual((ok, err), (True, ""), "the dial followed the override to the stub, not the foreign record")
        self.assertEqual(seen[0][0], "/quarantine/act")

    def test_the_ensure_exiting_zero_is_what_arms_the_record(self):
        # the flag is set by _ensure_postal_bus on a zero exit and by nothing else; a refused ensure (the fixed port under a test)
        # leaves it off, so a hermetic kernel never trusts a record
        saved = km.subprocess.run
        class R:
            def __init__(self, code): self.returncode, self.stderr = code, "refused"
        try:
            km._BUS_ENSURED[0] = False
            km.subprocess.run = lambda *a, **kw: R(1)
            km._ensure_postal_bus()
            self.assertFalse(km._BUS_ENSURED[0], "a refused ensure arms nothing")
            km.subprocess.run = lambda *a, **kw: R(0)
            km._ensure_postal_bus()
            self.assertTrue(km._BUS_ENSURED[0], "the ensure that answered arms the record")
        finally:
            km.subprocess.run = saved

    def test_the_decision_carries_the_recipient_sid_to_the_bus(self):
        # the decision is a notice action of the quarantine kind since 2026-09-19: the recipient the bus is told is the CARD's
        # owner, read from the stored row, never a word the pane sent; a deny's note from the click is the bus's feedback
        HeldMailCards.setUp(self); self.addCleanup(HeldMailCards.tearDown, self)
        HeldMailCards._write_held(self, "px-1.2_abc.TESTHOST"); getattr(km, "_held_mail_backfill", lambda: 0)()
        bodies = []
        saved = km._bus_quarantine_act, km._mark_views_dirty
        km._bus_quarantine_act = lambda body: (bodies.append(body), (True, ""))[1]
        km._mark_views_dirty = lambda: None
        try:
            sent = []
            client = {"app": "feed", "wid": "w1", "alive": True, "send": lambda raw: sent.append(json.loads(raw))}
            km.Handler._dispatch_ws(None, {"type": "noticeAction", "itemId": "notice:%s:px-1.2_abc.TESTHOST:1" % WEB, "sid": "TESTHOST:" + WEB, "kind": "quarantine",
                                           "body": {"mid": "px-1.2_abc.TESTHOST", "verdict": "deny"}, "input": {"note": "not now"}}, client)
        finally:
            km._bus_quarantine_act, km._mark_views_dirty = saved
        self.assertEqual(bodies, [{"mid": "px-1.2_abc.TESTHOST", "action": "deny", "sid": WEB, "feedback": "not now"}],
                         "the bus is told which session the decision is for: the card's owner, bare (the pane's prefixed word is not read)")
        self.assertEqual(sent, [{"type": "noticeActionDone", "itemId": "notice:%s:px-1.2_abc.TESTHOST:1" % WEB, "ok": True, "error": ""}])


if __name__ == "__main__":
    unittest.main()
