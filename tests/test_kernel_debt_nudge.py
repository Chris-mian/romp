#!/usr/bin/env python3
"""The DEBT reminder (the user 2026-07-26): an unanswered postal question/delegate paints "Awaiting
<peer>" on the SENDER's cards and parks them (the auto-nudge deliberately skips peer-waiting cards) —
but nothing ever told the RECIPIENT it owed a reply, so a mis-declared kind (a "question" whose prose
said no reply was needed) parked its sender silently for a day. The fix: an idle session sitting on
unanswered inbound asks from LIVE peers gets ONE reminder in the asker's terms, deduped per ask event
(auto-nudge.json debtNudged) — either honest exit (an answer, or "nothing needed") is the reply that
releases the asker's wait. All fixtures SYNTHETIC (placeholder UUIDs, the notes-api demo names)."""
import json
import os
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_debt", os.path.join(BIN, "romp-kernel")).load_module()

DEBTOR = "11111111-2222-3333-4444-555555555555"     # the idle session that owes replies
ASKER = "66666666-7777-8888-9999-000000000000"      # the live peer parked on the wait
ASKER2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
NOW = 1781100000
T_ASK = NOW - 1800


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, sid, body):
        self.sent.append((sid, body))


class DebtBase(unittest.TestCase):
    def setUp(self):
        self._saved = (km._postal_wait_maps, km._name_of, km._auto_nudge_data,
                       km._write_auto_nudge, km.Sessions.backend_for)
        self._d = {"nudged": {}}
        km._auto_nudge_data = lambda: self._d
        km._write_auto_nudge = lambda d: self._d.update(d)
        km._name_of = lambda sid: {ASKER: "web", ASKER2: "api"}.get(sid)
        self.rec = _Recorder()
        km.Sessions.backend_for = lambda sid: self.rec
        self._maps = ({}, {})
        km._postal_wait_maps = lambda: self._maps

    def tearDown(self):
        (km._postal_wait_maps, km._name_of, km._auto_nudge_data,
         km._write_auto_nudge, km.Sessions.backend_for) = self._saved

    def _ask(self, kind="question", head="Which port should the staging server use?",
             ts=T_ASK, asker=ASKER, answered_at=None):
        last_any = {(asker, DEBTOR): ts}
        if answered_at is not None:
            last_any[(DEBTOR, asker)] = answered_at
        last_ask = {(asker, DEBTOR): (ts, kind, head)}
        self._maps = (last_any, last_ask)
        km._postal_wait_maps = lambda: self._maps


class DebtAsks(DebtBase):
    def test_an_unanswered_ask_from_a_live_peer_is_owed(self):
        self._ask()
        self.assertEqual(km._debt_asks(DEBTOR, {ASKER, DEBTOR}),
                         [(ASKER, "web", T_ASK, "question", "Which port should the staging server use?")])

    def test_any_later_message_back_settles_the_debt(self):
        # same rule as the sender's chip: a reply of ANY kind after the ask answers it
        self._ask(answered_at=T_ASK + 60)
        self.assertEqual(km._debt_asks(DEBTOR, {ASKER, DEBTOR}), [])

    def test_a_dead_asker_is_no_debt(self):
        # answering a dead session releases nobody — mirror the wait edge's alive gate
        self._ask()
        self.assertEqual(km._debt_asks(DEBTOR, {DEBTOR}), [])

    def test_legacy_two_tuple_records_still_read(self):
        # a cached (ts, kind) record from before the head rode along must not crash the scan
        self._maps = ({(ASKER, DEBTOR): T_ASK}, {(ASKER, DEBTOR): (T_ASK, "question")})
        km._postal_wait_maps = lambda: self._maps
        self.assertEqual(km._debt_asks(DEBTOR, {ASKER}),
                         [(ASKER, "web", T_ASK, "question", "")])


class DebtReminder(DebtBase):
    def test_the_reminder_names_the_asker_and_quotes_their_words(self):
        self._ask()
        self.assertTrue(km._fire_debt_reminder(DEBTOR, NOW, {ASKER, DEBTOR}))
        (sid, body), = self.rec.sent
        self.assertEqual(sid, DEBTOR)
        self.assertIn("web asked you something", body)
        self.assertIn("> Which port should the staging server use?", body,
                      "the asker's own first words are quoted back")
        self.assertIn("Reply to web now", body)
        self.assertIn("don't actually need anything", body, "the nothing-needed exit is offered")
        self.assertIn("<!-- romp-injected -->", body)
        self.assertIn("<!-- romp-system -->", body,
                      "the planner treats the response as housekeeping, never a fresh card")

    def test_a_handoff_reads_as_a_handoff(self):
        self._ask(kind="delegate", head="Take over the fixtures backfill.")
        km._fire_debt_reminder(DEBTOR, NOW, {ASKER, DEBTOR})
        (_sid, body), = self.rec.sent
        self.assertIn("web handed you some work", body)

    def test_one_reminder_per_ask_ever(self):
        self._ask()
        self.assertTrue(km._fire_debt_reminder(DEBTOR, NOW, {ASKER, DEBTOR}))
        self.assertFalse(km._fire_debt_reminder(DEBTOR, NOW + 60, {ASKER, DEBTOR}),
                         "an ignored reminder escalates on the SENDER's card, never by repeating")
        self.assertEqual(len(self.rec.sent), 1)
        key = "%s>%s:%d" % (ASKER, DEBTOR, T_ASK)
        self.assertEqual(self._d["debtNudged"][key], NOW, "the dedup record carries the fire time")

    def test_a_newer_ask_from_the_same_peer_re_arms(self):
        self._ask()
        km._fire_debt_reminder(DEBTOR, NOW, {ASKER, DEBTOR})
        self._ask(ts=T_ASK + 900, head="Second thing: which region?")
        self.assertTrue(km._fire_debt_reminder(DEBTOR, NOW + 60, {ASKER, DEBTOR}),
                        "a new ask is a new event with its own reminder")
        self.assertIn("which region", self.rec.sent[-1][1])

    def test_several_debts_ride_one_message(self):
        last_any = {(ASKER, DEBTOR): T_ASK, (ASKER2, DEBTOR): T_ASK + 5}
        last_ask = {(ASKER, DEBTOR): (T_ASK, "question", "Which port?"),
                    (ASKER2, DEBTOR): (T_ASK + 5, "delegate", "Take the backfill.")}
        self._maps = (last_any, last_ask)
        km._postal_wait_maps = lambda: self._maps
        self.assertTrue(km._fire_debt_reminder(DEBTOR, NOW, {ASKER, ASKER2, DEBTOR}))
        self.assertEqual(len(self.rec.sent), 1, "debts coalesce into one message")
        body = self.rec.sent[0][1]
        self.assertIn("web asked you", body)
        self.assertIn("api handed you", body)
        self.assertIn("Reply to each of them now", body)


if __name__ == "__main__":
    unittest.main()
