#!/usr/bin/env python3
"""Pipeline-side unit tests: the romp-events extractor boundary + the
romp-summarize-backfill parsers, registry writers, and gates.

Run:  python3 tests/test_romp_pipeline_side.py

Sibling of test_romp_read_side.py, born from the same 2026-06-09 incident day.
Priority mirrors what actually escaped:

  a. TRANSCRIPT FIXTURES — synthetic .jsonl transcripts through the REAL
     extractor (the banner-gate bug lived exactly where mocked internals would
     have lied): peer flag, truncation/text_full, drains, task-notifications.
  b. PARSER GUARDS — junk-tail matrix for 'TAG :: phrase :: LINK :: DONE',
     REQ/PARENTS, the deterministic ball-in-court override + its peer gating.
  c. REGISTRY SEMANTICS — idempotent internal nodes, floor, candidate builder
     (cap/eviction), and the two-wave same-pass ordering with a scripted llm.
  d. ANCHOR-SID fork resolution in sessions().

NO model calls anywhere: the judgment layer stays covered by decision-log
replay + requests/corrections.jsonl. Structural corrections entries from
2026-06-09 are encoded here as permanent fixtures: peer-minted asks
(banner + parked/revive), the 140-char truncation, and the trailing-offer
ball-in-court override.

Discipline: run this suite before every daemon restart (selftest gate).
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
sys.path.insert(0, SCRIPTS)

ev = SourceFileLoader("romp_events_t", os.path.join(SCRIPTS, "romp-events")).load_module()
bf = SourceFileLoader("romp_backfill_t", os.path.join(SCRIPTS, "romp-summarize-backfill")).load_module()

NOW = 1781100000                      # fixed test clock, comfortably past REQUESTS_FLOOR
FLOOR = bf.REQUESTS_FLOOR


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, ps="typed", uuid=None, parent=None):
    return {"type": "user", "timestamp": iso(t), "promptSource": ps,
            "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": text}}


def aline(t, text, tools=(), uuid=None, parent=None):
    content = [{"type": "text", "text": text}]
    content += [{"type": "tool_use", "id": "tu_%d" % i, "name": n, "input": {}}
                for i, n in enumerate(tools)]
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": content}}


def qop(t, op, content=None, uuid=None):
    return {"type": "queue-operation", "timestamp": iso(t), "operation": op,
            "content": content, "uuid": uuid}


BANNER = ("############################################\n"
          "## \U0001F4EC from feed_design · 16:52\n"
          "############################################\n"
          "ASK: promote the deferred classify-completion item — the user just hit its "
          "symptom and it is the top quality gap now. Reply with the format you choose.\n"
          "<!-- romp-msg-id: 1781051207.67474_57710.TESTHOST -->\n"
          "############################################")

PARKED = ("\U0001F4EC New message(s) from your romp peers:\n\n"
          "· ⏸ parked (you were offline)\n"
          "— from vs_chat (2026-06-09T16:39:44-0700):\n"
          "ASK: diagnose the ask-extraction miss on the dashboard turn.\n"
          "<!-- romp-msg-id: 1781048384.66206_27591.TESTHOST -->\n"
          "— from feed_design (2026-06-09T16:45:40-0700):\n"
          "FYI: spec frozen.\n"
          "<!-- romp-msg-id: 1781048740.66206_79978.TESTHOST -->")

LONG_TYPED = ("Now I want you to thoroughly go through everything that displays on the "
              "dashboard and various things should be able to link to stuff. For example "
              "clicking one of the linked work things should jump to that point in the "
              "timeline where the thing happened and then select it and in doing so also "
              "select it in the chat or in the tabs. Also add a color legend to the "
              "deliverable output so the meaning of each color is obvious at a glance.")


def extract(lines, sid="S", now=NOW):
    """Write a transcript fixture and run the REAL extractor on it."""
    d = tempfile.mkdtemp(prefix="romp-ptest-")
    try:
        p = os.path.join(d, sid + ".jsonl")
        with open(p, "w") as f:
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
        return ev.extract_events(sid, p, now)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def typed_turn(t, text, ps="typed"):
    """A minimal closed work period: prompt + assistant reply."""
    return [uline(t, text, ps=ps, uuid="u%d" % t),
            aline(t + 10, "did the work", tools=("Edit",), uuid="a%d" % t, parent="u%d" % t)]


# ───────────────────────── a. transcript fixtures ─────────────────────────

class PeerGate(unittest.TestCase):
    """The 2026-06-09 inversion: peer-prompted turns must never mint user-asks.
    The gate must key on RAW-text markers (banner frame / 📬 / romp-msg-id) computed
    BEFORE the cosmetic strip — e['text'] has them removed, which is why the original
    text-based gate was dead from day one."""

    def test_live_banner_turn_is_peer(self):
        events = extract(typed_turn(NOW - 1000, BANNER) + typed_turn(NOW - 500, "closer"))
        e = events["events"][0]
        self.assertTrue(e["peer"])
        self.assertFalse(bf._is_real_ask(e))

    def test_parked_revive_drain_is_peer(self):
        events = extract(typed_turn(NOW - 1000, PARKED) + typed_turn(NOW - 500, "closer"))
        e = events["events"][0]
        self.assertTrue(e["peer"])
        self.assertEqual(len(e["mids"]), 2)          # parked mail carries msg-ids
        self.assertFalse(bf._is_real_ask(e))

    def test_genuine_typed_turn_extracts(self):
        events = extract(typed_turn(NOW - 1000, LONG_TYPED) + typed_turn(NOW - 500, "closer"))
        e = events["events"][0]
        self.assertFalse(e["peer"])
        self.assertTrue(bf._is_real_ask(e))

    def test_stop_hook_drain_excluded(self):
        lines = typed_turn(NOW - 1000, "real ask")
        lines.append(uline(NOW - 900, "Stop hook feedback: \U0001F4EC New message(s) — "
                           "from vs_chat (x): hello", ps=None, uuid="d1"))
        lines += [aline(NOW - 890, "handled", uuid="a2", parent="d1")]
        events = extract(lines)
        drains = [e for e in events["events"] if e["kind"] == "drain"]
        self.assertEqual(len(drains), 1)
        self.assertFalse(bf._is_real_ask(drains[0]))

    def test_absorbed_peer_message_is_peer(self):
        lines = typed_turn(NOW - 1000, "real ask")
        lines.append(qop(NOW - 995, "enqueue", BANNER, uuid="q1"))
        lines.append(qop(NOW - 992, "remove"))
        lines += typed_turn(NOW - 500, "closer")
        events = extract(lines)
        absorbed = [e for e in events["events"] if e["kind"] == "absorbed"]
        self.assertEqual(len(absorbed), 1)
        self.assertTrue(absorbed[0]["peer"])
        self.assertFalse(bf._is_real_ask(absorbed[0]))

    def test_absorbed_typed_message_extracts(self):
        lines = typed_turn(NOW - 1000, "real ask")
        lines.append(qop(NOW - 995, "enqueue", "also please fix the flaky test", uuid="q1"))
        lines.append(qop(NOW - 992, "remove"))
        lines += typed_turn(NOW - 500, "closer")
        events = extract(lines)
        absorbed = [e for e in events["events"] if e["kind"] == "absorbed"]
        self.assertEqual(len(absorbed), 1)
        self.assertFalse(absorbed[0]["peer"])
        self.assertTrue(bf._is_real_ask(absorbed[0]))

    def test_task_notification_never_an_event(self):
        lines = typed_turn(NOW - 1000, "real ask")
        lines.append(qop(NOW - 995, "enqueue", "<task-notification>done</task-notification>", uuid="q1"))
        lines.append(qop(NOW - 992, "remove"))
        events = extract(lines)
        self.assertEqual([e["kind"] for e in events["events"]], ["typed"])
        self.assertEqual(events["pending"], [])


class Truncation(unittest.TestCase):
    """The original miss: 140-char display cut amputating ask content. text_full must
    carry the full prose; the id hash must stay bound to the 140-cut FOREVER."""

    def test_text_full_carries_past_140(self):
        e = extract(typed_turn(NOW - 1000, LONG_TYPED))["events"][0]
        self.assertEqual(len(e["text"]), 140)
        self.assertGreater(len(e["text_full"]), 400)
        self.assertIn("color legend", e["text_full"])     # the tail that used to vanish
        self.assertNotIn("color legend", e["text"])

    def test_event_id_hashes_the_140_cut(self):
        e = extract(typed_turn(NOW - 1000, LONG_TYPED))["events"][0]
        flat = " ".join(LONG_TYPED.split())
        want = hashlib.sha1(flat[:140].encode()).hexdigest()[:8]
        self.assertTrue(e["id"].endswith(want))
        # and NOT the full-text hash — changing this orphans every summary/link/feed-detail
        self.assertFalse(e["id"].endswith(hashlib.sha1(flat.encode()).hexdigest()[:8]))

    def test_emit_strip_removes_bulk_fields(self):
        e = extract(typed_turn(NOW - 1000, LONG_TYPED))["events"][0]
        self.assertIn("text_full", e)                     # present at extract level
        # the --emit merge layer pops rec/text_full; emulate its contract here
        e.pop("rec", None); e.pop("text_full", None)
        self.assertNotIn("text_full", e)


# ───────────────────────── b. parser guards ─────────────────────────

class ReplyParser(unittest.TestCase):
    def test_full_line(self):
        self.assertEqual(bf._split_reply("DONE :: Shipped the fix :: LINK 1,3 :: DONE 1"),
                         ("DONE", "Shipped the fix", [1, 3], [1], {}))

    def test_done_none(self):
        tag, phrase, links, dones, did = bf._split_reply("DETAILS :: Refactored :: LINK 2 :: DONE none")
        self.assertEqual((links, dones), ([2], []))

    def test_done_omitted(self):
        tag, phrase, links, dones, did = bf._split_reply("DETAILS :: Partial :: LINK 1")
        self.assertEqual((links, dones), ([1], None))

    def test_junk_done_degrades_done_only(self):
        tag, phrase, links, dones, did = bf._split_reply("DETAILS :: Work :: LINK 1 :: DONE banana")
        self.assertEqual((tag, phrase, links, dones), ("DETAILS", "Work", [1], None))

    def test_junk_link_degrades_link_phrase_intact(self):
        tag, phrase, links, dones, did = bf._split_reply("DETAILS :: Work :: LINK banana")
        self.assertEqual((phrase, links), ("Work", None))
        self.assertNotIn("LINK", phrase)

    def test_link_none(self):
        self.assertEqual(bf._split_reply("DETAILS :: Work :: LINK none")[2], [])

    def test_no_tails_at_all(self):
        tag, phrase, links, dones, did = bf._split_reply("DONE :: Just the work")
        self.assertEqual((tag, phrase, links, dones, did), ("DONE", "Just the work", None, None, {}))

    # ── DID tail (per-request scoped phrases, incident dde32f03 2026-06-10) ──
    def test_did_full_line(self):
        tag, phrase, links, dones, did = bf._split_reply(
            "DONE :: Confirmed three fixes live :: LINK 1,2,3 :: DONE 1,2,3 "
            ":: DID 1=verified the jump fix | 2=confirmed diagnostic logging | 3=wired double-click open")
        self.assertEqual(links, [1, 2, 3])
        self.assertEqual(dones, [1, 2, 3])
        self.assertEqual(did, {1: "verified the jump fix", 2: "confirmed diagnostic logging",
                               3: "wired double-click open"})

    def test_did_stripped_before_done(self):
        # DID's numbers must never feed the DONE parse — strip order is the guarantee
        tag, phrase, links, dones, did = bf._split_reply(
            "DETAILS :: Work :: LINK 1,2 :: DONE none :: DID 1=did a thing | 2=did another")
        self.assertEqual(dones, [])                       # NOT polluted by DID's 1,2
        self.assertEqual(did, {1: "did a thing", 2: "did another"})

    def test_junk_did_degrades_did_only(self):
        tag, phrase, links, dones, did = bf._split_reply(
            "DETAILS :: Work :: LINK 1,2 :: DONE 1 :: DID banana")
        self.assertEqual((links, dones, did), ([1, 2], [1], {}))

    def test_did_colon_separator_tolerated(self):
        _t, _p, _l, _d, did = bf._split_reply("DONE :: W :: LINK 1,2 :: DONE 1,2 :: DID 1: alpha | 2: beta")
        self.assertEqual(did, {1: "alpha", 2: "beta"})

    def test_done_subset_guard_at_write(self):
        # numbers outside the LINK set must be ignored by the write layer
        cand = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        rids = bf._picks_to_ids([1], cand)
        dids = set(bf._picks_to_ids([1, 3], cand)) & set(rids)
        self.assertEqual(dids, {"a"})

    def test_picks_bounds_checked(self):
        cand = [{"id": "a"}]
        self.assertEqual(bf._picks_to_ids([0, 1, 2, 99], cand), ["a"])
        self.assertEqual(bf._picks_to_ids(None, cand), [])


class MsgParser(unittest.TestCase):
    def test_req_yes_with_parents(self):
        phrase, is_req, parents = bf._parse_msg("Fix the gate :: REQ yes :: PARENTS 1,2")
        self.assertEqual((phrase, is_req, parents), ("Fix the gate", True, [1, 2]))

    def test_req_no(self):
        phrase, is_req, parents = bf._parse_msg("Status update :: REQ no :: PARENTS none")
        self.assertEqual((is_req, parents), (False, []))

    def test_req_missing(self):
        phrase, is_req, parents = bf._parse_msg("Just a phrase")
        self.assertIsNone(is_req)


class RequestParser(unittest.TestCase):
    def test_phrase_plus_asks_and_amend(self):
        out = ("PHRASE :: wants dashboard linking\n"
               "ASK :: linked-work clicks jump to timeline\n"
               "AMEND 2 :: also select in chat tabs\n"
               "ASK :: add color legend")
        phrase, asks, amends, answers, verdict = bf._parse_request(out)
        self.assertEqual(phrase, "wants dashboard linking")
        self.assertEqual(asks, ["linked-work clicks jump to timeline", "add color legend"])
        self.assertEqual(amends, [(2, "also select in chat tabs")])
        self.assertEqual(verdict, "ask")

    def test_phrase_only_is_unclassified(self):
        # a bare PHRASE is a capture FAILURE (verdict None), not a 'no ask' judgment —
        # the f752575d misses (2026-06-11) were exactly this shape
        phrase, asks, amends, answers, verdict = bf._parse_request("PHRASE :: small talk")
        self.assertEqual((asks, amends, verdict), ([], [], None))

    def test_explicit_ack(self):
        _, asks, _, _, verdict = bf._parse_request("PHRASE :: thanks, looks good\nACK")
        self.assertEqual((asks, verdict), ([], "ack"))

    def test_explicit_answer(self):
        _, asks, _, answers, verdict = bf._parse_request("PHRASE :: picks the second option\nANSWER 2 :: chose stacking when narrow")
        self.assertEqual((asks, verdict, answers), ([], "answer", [(2, "chose stacking when narrow")]))

    def test_asks_win_over_stray_ack(self):
        _, asks, _, _, verdict = bf._parse_request("PHRASE :: fix and thanks\nASK :: fix the gate\nACK")
        self.assertEqual((asks, verdict), (["fix the gate"], "ask"))


class CaptureBackstop(unittest.TestCase):
    """Deterministic under-fire guard (mystery's handoff, 2026-06-11): zero-ask captures
    must be EXPLICIT to stand; bare or suspicious ones auto-mint from the phrase."""

    def test_unclassified_always_mints(self):
        self.assertEqual(bf._capture_backstop(None, [], [], "short note"), "unclassified")

    def test_explicit_ack_short_respected(self):
        self.assertIsNone(bf._capture_backstop("ack", [], [], "sounds good, thanks"))

    def test_ack_with_question_mark_mints(self):
        self.assertEqual(bf._capture_backstop("ack", [], [], "why is this popping up?"),
                         "suspicious-ack")

    def test_ack_long_turn_mints(self):
        long_txt = " ".join(["word"] * 31)
        self.assertEqual(bf._capture_backstop("ack", [], [], long_txt), "suspicious-ack")

    def test_explicit_answer_trusted_even_long(self):
        long_answer = " ".join(["detail"] * 40)
        self.assertIsNone(bf._capture_backstop("answer", [], [], long_answer))

    def test_no_backstop_when_asks_exist(self):
        self.assertIsNone(bf._capture_backstop("ask", ["do x"], [], "do x please?"))


class BallInCourt(unittest.TestCase):
    """The user's ruling (corrections t=1781053800): ball-in-court is reply-TAIL-sensitive.
    Deterministic in code because the tag model would not hold the rule."""

    def test_tail_question_detected(self):
        rec = "USER ASKED: x\nASSISTANT SAID: Wrote the doc. Want me to draft the next one?\nTOOLS USED: Write"
        self.assertTrue(bf._tail_question(rec))

    def test_plain_close_not_detected(self):
        rec = "USER ASKED: x\nASSISTANT SAID: Wrote the doc. Nothing pending.\nTOOLS USED: Write"
        self.assertFalse(bf._tail_question(rec))

    def test_mid_prose_question_not_detected(self):
        rec = "USER ASKED: x\nASSISTANT SAID: Fixed the 'why does X fail?' handler and shipped it.\nTOOLS USED: Edit"
        self.assertFalse(bf._tail_question(rec))

    def test_none_rec(self):
        self.assertFalse(bf._tail_question(None))

    # ── review-offer carve-out (the user's refinement, decision_ref 0045ccce, 2026-06-10):
    # a closing review offer is politeness, not pending input — must NOT force DECISION.
    def test_review_offer_two_sided_fixture(self):
        # the 0045ccce shape: review offer (ignore) + concrete alternative (model's IDEA stands)
        rec = ("USER ASKED: x\nASSISTANT SAID: Implemented the status chip and installed v2.1. "
               "If you'd rather have it bottom-right, just say so. Do you want to review the "
               "implementation, or does the summary cover it?\nTOOLS USED: Edit")
        self.assertFalse(bf._tail_question(rec))

    def test_looks_off_carved_out(self):
        rec = "USER ASKED: x\nASSISTANT SAID: Shipped the fix. Let me know if anything looks off?\nTOOLS USED: Edit"
        self.assertFalse(bf._tail_question(rec))

    def test_sound_good_carved_out(self):
        rec = "USER ASKED: x\nASSISTANT SAID: Renamed the column as planned. Sound good?\nTOOLS USED: Edit"
        self.assertFalse(bf._tail_question(rec))

    def test_genuine_question_after_review_word_in_body(self):
        # 'review' earlier in the prose must not bleed into the closing-sentence judgment
        rec = ("USER ASKED: x\nASSISTANT SAID: I reviewed both options and shipped a draft. "
               "Should I keep the legacy path or delete it?\nTOOLS USED: Edit")
        self.assertTrue(bf._tail_question(rec))

    def test_reply_sys_teaches_review_offer_boundary(self):
        self.assertIn("REVIEW OFFER", bf.REPLY_SYS)             # review offer → DONE
        self.assertIn("NEVER an ACTION", bf.REPLY_SYS)          # optional review ≠ ACTION
        self.assertIn("ALTERNATIVE that would change the artifact", bf.REPLY_SYS)  # closer alternative → IDEA

    # inverted ball-in-court (decision_ref 3d7afe17, 2026-06-10): the USER's question in
    # the record misread as pending input — answered question is the deliverable (DONE),
    # and the phrase must describe what the reply delivered, never the user's state.
    def test_reply_sys_teaches_answered_question_is_done(self):
        self.assertIn("ANSWERS the user's question", bf.REPLY_SYS)
        self.assertIn("DELIVERED", bf.REPLY_SYS)

    def test_reply_sys_phrase_never_describes_user_state(self):
        self.assertIn("Never describe the USER's state", bf.REPLY_SYS)

    def test_users_own_question_does_not_trip_tail_override(self):
        # deterministic side of the same lesson: _tail_question reads ASSISTANT prose only —
        # The user's question in the record must never trigger the DECISION flip
        rec = ("USER ASKED: is batch-marking better than careful tracing?\n"
               "ASSISTANT SAID: Batch-marking is safe here because completion is verified downstream.\n"
               "TOOLS USED: Read")
        self.assertFalse(bf._tail_question(rec))


class OverrideFlow(unittest.TestCase):
    """_handle_rep with writes stubbed: the override must flip tag AND link relevance to
    DECISION, suppress the completion upgrade, and decision-log itself."""

    def setUp(self):
        self.log = {"sum": [], "links": [], "dec": []}
        self._saved = (bf.append_summary, bf._append_req, bf._declog)
        bf.append_summary = lambda sid, eid, kind, text, t, rel=None: self.log["sum"].append((eid, rel))
        bf._append_req = lambda path, rec: self.log["links"].append(rec)
        bf._declog = lambda rec: self.log["dec"].append(rec)
        self.cand = [{"id": "ask#0", "text": "Document router instructions"}]
        self.out = "DONE :: Documented and committed :: LINK 1 :: DONE 1"

    def tearDown(self):
        bf.append_summary, bf._append_req, bf._declog = self._saved

    def test_tailq_overrides_everything(self):
        bf._handle_rep(("rep", "anc", "sid", "E1", NOW, self.cand, True), self.out)
        self.assertEqual(self.log["sum"][0][1], "DECISION")
        self.assertEqual(self.log["links"][0]["relevance"], "DECISION")     # completion suppressed
        self.assertEqual([d["kind"] for d in self.log["dec"] if d["kind"] == "tag-override"],
                         ["tag-override"])

    def test_no_tailq_keeps_model_output(self):
        bf._handle_rep(("rep", "anc", "sid", "E2", NOW, self.cand, False), self.out)
        self.assertEqual(self.log["sum"][0][1], "DONE")
        self.assertEqual(self.log["links"][0]["relevance"], "DONE")
        self.assertEqual([d for d in self.log["dec"] if d["kind"] == "tag-override"], [])

    def test_already_decision_no_override_record(self):
        bf._handle_rep(("rep", "anc", "sid", "E3", NOW, self.cand, True),
                       "DECISION :: Asked which version to pin :: LINK 1")
        self.assertEqual([d for d in self.log["dec"] if d["kind"] == "tag-override"], [])

    def test_own_turn_ask_linked_structurally(self):
        # the user 2026-06-11: the reply of the turn that minted an ask can never float
        # free of it — even when the model says LINK none, the own-turn ask attaches
        cand = [{"id": "OTHER#0", "text": "Unrelated ask"},
                {"id": "E5#0", "text": "This turn's own ask"}]
        bf._handle_rep(("rep", "anc", "sid", "E5", NOW, cand, False),
                       "DETAILS :: Investigated the flag :: LINK none :: DONE none")
        self.assertEqual(self.log["links"][0]["request_ids"], ["E5#0"])
        self.assertEqual(self.log["links"][0]["relevance"], "DETAILS")

    def test_wait_tag_parses_and_carries(self):
        # WAIT = paused on an external event (not the user): valid tag, link carries it,
        # no completion marks, no needs-user routing
        bf._handle_rep(("rep", "anc", "sid", "E6", NOW, self.cand, False),
                       "WAIT :: Kicked off CI run, awaiting result :: LINK 1 :: DONE none")
        self.assertEqual(self.log["sum"][0][1], "WAIT")
        self.assertEqual(self.log["links"][0]["relevance"], "WAIT")

    def test_review_carved_idea_survives_with_suppressed_completion(self):
        # 0045ccce end-to-end: review-offer tail carved upstream (tailq=False); the model's
        # IDEA (bottom-right alternative) stands un-flipped, completion marks suppressed
        # (NEEDS_USER_TAGS) so the node waits for the user's next typed turn.
        bf._handle_rep(("rep", "anc", "sid", "E4", NOW, self.cand, False),
                       "IDEA :: Added status chip, offered bottom-right placement :: LINK 1 :: DONE 1")
        self.assertEqual(self.log["sum"][0][1], "IDEA")
        self.assertEqual(self.log["links"][0]["relevance"], "IDEA")          # not DONE
        self.assertEqual([d for d in self.log["dec"] if d["kind"] == "tag-override"], [])

    def test_review_carved_done_completion_flows(self):
        # review-offer-only closer: model DONE stands and the discharge actually lands
        bf._handle_rep(("rep", "anc", "sid", "E5", NOW, self.cand, False), self.out)
        self.assertEqual(self.log["links"][0]["relevance"], "DONE")

    def test_mixed_completion_splits_relevance_groups(self):
        # the 136a33d9 shape (corrections decision_ref 2eadbd3f, 2026-06-10): a two-topic
        # closer discharges request 1 while request 2 from the SAME turn stays in flight —
        # the DONE subset must land as relevance=DONE for #1 and the turn tag for #2,
        # never collapse to 'DONE none' because the turn as a whole isn't finished.
        cand = [{"id": "ask#0", "text": "Sort timeline chronologically"},
                {"id": "ask#1", "text": "Investigate duplicate cards"}]
        bf._handle_rep(("rep", "anc", "sid", "E6", NOW, cand, False),
                       "DONE :: Shipped sort fix, debugging dup cards :: LINK 1,2 :: DONE 1")
        rel = {tuple(l["request_ids"]): l["relevance"] for l in self.log["links"]}
        self.assertEqual(rel[("ask#0",)], "DONE")
        # the in-flight topic must NOT inherit the turn's DONE tag (false-complete trap):
        # a DONE-tagged turn's non-discharged links demote to DETAILS
        self.assertEqual(rel[("ask#1",)], "DETAILS")

    def test_reply_sys_teaches_mixed_completion(self):
        self.assertIn("MIXED TURNS ARE THE NORM", bf.REPLY_SYS)
        self.assertIn("doubt about one request must not blank the others", bf.REPLY_SYS)
        self.assertIn("MANDATORY", bf.REPLY_SYS)   # the DONE segment may never be silently omitted (2026-06-11)

    # ── per-request scoped phrases (incident dde32f03: one whole-turn phrase rendered
    # under 3 cards spanning 2 workstreams, leaking material across them) ──
    def test_multi_request_link_carries_did_by_request(self):
        cand = [{"id": "jump#0", "text": "Investigate timeline jump"},
                {"id": "log#0", "text": "Add diagnostic logging"},
                {"id": "dbl#0", "text": "Wire double-click open"}]
        bf._handle_rep(("rep", "anc", "sid", "E7", NOW, cand, False),
                       "DONE :: Confirmed jump fix, log, and double-click live :: LINK 1,2,3 :: DONE 1,2,3 "
                       ":: DID 1=verified the jump fix | 2=confirmed diagnostic logging | 3=wired double-click")
        row = self.log["links"][0]
        self.assertEqual(sorted(row["request_ids"]), ["dbl#0", "jump#0", "log#0"])
        self.assertEqual(row["did_by_request"], {"jump#0": "verified the jump fix",
                                                 "log#0": "confirmed diagnostic logging",
                                                 "dbl#0": "wired double-click"})

    def test_did_split_across_relevance_groups(self):
        # mixed turn: each relevance group's row carries only ITS requests' phrases
        cand = [{"id": "a#0", "text": "Ship sort"}, {"id": "b#0", "text": "Find dup cards"}]
        bf._handle_rep(("rep", "anc", "sid", "E8", NOW, cand, False),
                       "DONE :: Shipped sort, debugging dups :: LINK 1,2 :: DONE 1 "
                       ":: DID 1=shipped the sort fix | 2=added dup-card logging")
        by_rel = {l["relevance"]: l for l in self.log["links"]}
        self.assertEqual(by_rel["DONE"]["did_by_request"], {"a#0": "shipped the sort fix"})
        self.assertEqual(by_rel["DETAILS"]["did_by_request"], {"b#0": "added dup-card logging"})

    def test_single_request_link_has_no_did(self):
        # global phrase is already correctly scoped — and a stray DID must not attach
        bf._handle_rep(("rep", "anc", "sid", "E9", NOW, self.cand, False),
                       "DONE :: Documented and committed :: LINK 1 :: DONE 1 :: DID 1=documented it")
        self.assertNotIn("did_by_request", self.log["links"][0])

    def test_reply_sys_teaches_did(self):
        self.assertIn(":: DID", bf.REPLY_SYS)
        self.assertIn("FOR THAT request", bf.REPLY_SYS)


# ───────────────────────── c. registry semantics ─────────────────────────

class RegistryDir(unittest.TestCase):
    """Real registry writers against a temp requests/ dir."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-req-")
        self._saved = (bf.REQDIR, bf.NODESF, bf.LINKSF, bf.CLEARF, bf.DECLOG)
        bf.REQDIR = Path(self.dir)
        bf.NODESF = bf.REQDIR / "nodes.jsonl"
        bf.LINKSF = bf.REQDIR / "links.jsonl"
        bf.CLEARF = bf.REQDIR / "cleared.jsonl"
        bf.DECLOG = bf.REQDIR / "decision-log.jsonl"
        self._sum = bf.append_summary
        bf.append_summary = lambda *a, **k: None
        self._wm, self._pm = bf._write_msg, bf._push_msg_to_statusbar
        bf._write_msg = lambda *a: None
        bf._push_msg_to_statusbar = lambda *a: None

    def tearDown(self):
        bf.REQDIR, bf.NODESF, bf.LINKSF, bf.CLEARF, bf.DECLOG = self._saved
        bf.append_summary = self._sum
        bf._write_msg, bf._push_msg_to_statusbar = self._wm, self._pm
        shutil.rmtree(self.dir, ignore_errors=True)

    def read(self, p):
        try:
            return [json.loads(l) for l in p.read_text().splitlines()]
        except OSError:
            return []

    def msg_meta(self, mid="m1", t=NOW, cand=()):
        return ("msg", mid, "sender-sid", "recip-sid", t, list(cand), "ASK: do the thing")

    def test_internal_node_created_and_idempotent(self):
        nodes = {}
        out = "Do the thing :: REQ yes :: PARENTS none"
        bf._handle_msg(self.msg_meta(), out, nodes)
        bf._handle_msg(self.msg_meta(), out, nodes)       # either side may run first; second is a no-op
        recs = [r for r in self.read(bf.NODESF) if r["kind"] == "internal"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], "m1")
        self.assertEqual(recs[0]["from_sid"], "sender-sid")

    def test_parents_edge_lands_after_node(self):
        nodes = {}
        cand = [{"id": "ask#0", "text": "the parent ask"}]
        bf._handle_msg(self.msg_meta(cand=cand), "Delegate :: REQ yes :: PARENTS 1", nodes)
        recs = self.read(bf.NODESF)
        self.assertEqual([r["kind"] for r in recs], ["internal", "parents"])
        self.assertEqual(recs[1]["parent_ids"], ["ask#0"])

    def test_req_no_logs_negative_decision(self):
        bf._handle_msg(self.msg_meta(), "Status only :: REQ no :: PARENTS none", {})
        self.assertEqual(self.read(bf.NODESF), [])
        dec = self.read(bf.DECLOG)
        self.assertEqual(dec[0]["kind"], "req-decision")
        self.assertIn("snippet", dec[0])

    def test_floor_blocks_node_creation(self):
        bf._handle_msg(self.msg_meta(t=FLOOR - 100), "Old ask :: REQ yes :: PARENTS none", {})
        self.assertEqual(self.read(bf.NODESF), [])

    def test_ask_capture_always_logged_with_raw(self):
        out = "PHRASE :: small talk\nACK"                  # EXPLICIT zero-ask (the new convention)
        bf._handle_req(("req", "anc", "sid", "T1", NOW, [], None, "thanks"), out, {})
        dec = self.read(bf.DECLOG)
        self.assertEqual(dec[0]["kind"], "ask-capture")
        self.assertEqual(dec[0]["asks"], [])
        self.assertEqual(dec[0]["verdict"], "ack")
        self.assertIsNone(dec[0]["backstop"])
        self.assertIn("PHRASE", dec[0]["raw"])

    def test_anchored_answer_writes_child_event(self):
        # the user's ruling (2026-06-11): an ANSWER with a number lands as an explicit
        # 'answer' node row on that card — recorded, never inferred from later typing
        cand = [{"id": "ROOT#0", "text": "fix the gate"}]
        out = "PHRASE :: picks option two\nANSWER 1 :: use the stricter gate"
        bf._handle_req(("req", "anc", "sid", "T9", NOW, cand, None, "use the stricter gate"), out, {})
        rows = self.read(bf.NODESF)
        self.assertEqual([r["kind"] for r in rows], ["answer"])
        self.assertEqual(rows[0]["id"], "ROOT#0")
        self.assertEqual(rows[0]["turn_id"], "T9")
        self.assertEqual(rows[0]["text"], "use the stricter gate")
        dec = self.read(bf.DECLOG)
        self.assertEqual(dec[0]["answers"], [[1, "use the stricter gate"]])
        self.assertIsNone(dec[0]["backstop"])             # explicit answer: no mint

    def test_unanchored_answer_writes_nothing(self):
        out = "PHRASE :: answers the question\nANSWER :: just context, no entry fits"
        bf._handle_req(("req", "anc", "sid", "T10", NOW, [], None, "some short answer"), out, {})
        self.assertEqual(self.read(bf.NODESF), [])        # verdict-only; logged, not anchored
        self.assertEqual(self.read(bf.DECLOG)[0]["verdict"], "answer")

    def test_bare_phrase_backstop_mints_and_logs(self):
        # the f752575d silent-drop class: bare PHRASE → auto-mint from the phrase,
        # node written, and the declog row says WHY (backstop: unclassified)
        out = "PHRASE :: identify recurring notification source"
        bf._handle_req(("req", "anc", "sid", "T1", NOW, [], None, "where does this keep coming from?"), out, {})
        nodes = self.read(bf.NODESF)
        self.assertEqual([n["kind"] for n in nodes], ["ask"])
        self.assertEqual(nodes[0]["text"], "identify recurring notification source")
        dec = self.read(bf.DECLOG)
        self.assertEqual(dec[0]["backstop"], "unclassified")
        self.assertEqual(dec[0]["asks"], ["identify recurring notification source"])

    def test_asks_minted_with_indexed_ids(self):
        out = "PHRASE :: two things\nASK :: first thing\nASK :: second thing"
        bf._handle_req(("req", "anc", "sid", "T2", NOW, []), out, {})
        asks = [r for r in self.read(bf.NODESF) if r["kind"] == "ask"]
        self.assertEqual([a["id"] for a in asks], ["T2#0", "T2#1"])
        self.assertEqual(asks[0]["sid"], "anc")            # anchor sid, not transcript fsid

    # ── _load_registry discharged fold (amend-of-completed regression set) ──
    def w(self, path, *rows):
        with open(path, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_fold_corrections_done_discharges(self):
        self.w(bf.NODESF, {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "x"})
        self.w(bf.LINKSF, {"kind": "link", "request_ids": ["a1"], "relevance": "DETAILS", "t": 100})
        self.w(bf.REQDIR / "corrections.jsonl",
               {"kind": "link", "t": 200, "should_have": {"request_ids": ["a1"], "relevance": "DONE"}})
        _n, _c, done = bf._load_registry()
        self.assertIn("a1", done)                          # rejudge flips must reach the palette

    def test_fold_newest_wins_downgrade_reopens(self):
        self.w(bf.NODESF, {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "x"})
        self.w(bf.LINKSF,
               {"kind": "link", "request_ids": ["a1"], "relevance": "DONE", "t": 100},
               {"kind": "link", "request_ids": ["a1"], "relevance": "DETAILS", "t": 200})
        _n, _c, done = bf._load_registry()
        self.assertNotIn("a1", done)                       # newest verdict wins, matching the UI

    def test_fold_path_completion_discharges_delegation_ask(self):
        # the 2026-06-10 re-title incident shape: the ask completed via its handoff child
        # (child DONE-linked by the delegate's batch close); the ask itself only ever got
        # DETAILS links, so the old direct-DONE fold left it unmarked in the amend palette.
        self.w(bf.NODESF,
               {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "fix timeline dots"},
               {"kind": "internal", "id": "h1", "from_sid": "S", "to_sid": "X", "t": 110, "text": "handoff"},
               {"kind": "parents", "id": "h1", "parent_ids": ["a1"], "t": 110})
        self.w(bf.LINKSF,
               {"kind": "link", "request_ids": ["a1"], "relevance": "DETAILS", "t": 120},
               {"kind": "link", "request_ids": ["h1"], "relevance": "DONE", "t": 500})
        _n, _c, done = bf._load_registry()
        self.assertIn("h1", done)
        self.assertIn("a1", done)

    def test_fold_open_child_blocks_path_completion(self):
        self.w(bf.NODESF,
               {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "x"},
               {"kind": "internal", "id": "h1", "from_sid": "S", "to_sid": "X", "t": 110, "text": "h1"},
               {"kind": "internal", "id": "h2", "from_sid": "S", "to_sid": "Y", "t": 111, "text": "h2"},
               {"kind": "parents", "id": "h1", "parent_ids": ["a1"], "t": 110},
               {"kind": "parents", "id": "h2", "parent_ids": ["a1"], "t": 111})
        self.w(bf.LINKSF, {"kind": "link", "request_ids": ["h1"], "relevance": "DONE", "t": 500})
        _n, _c, done = bf._load_registry()
        self.assertNotIn("a1", done)                       # h2 still open — paths not terminated

    def test_fold_cleared_child_counts_as_terminated(self):
        self.w(bf.NODESF,
               {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "x"},
               {"kind": "internal", "id": "h1", "from_sid": "S", "to_sid": "X", "t": 110, "text": "h1"},
               {"kind": "parents", "id": "h1", "parent_ids": ["a1"], "t": 110})
        self.w(bf.CLEARF, {"id": "h1", "t": 500})
        _n, _c, done = bf._load_registry()
        self.assertIn("a1", done)                          # a cleared path can't block forever

    def test_demo_nodes_invisible_to_write_side(self):
        # feed-written display fixtures (2026-06-10): "demo:" ids have no transcript turns —
        # the registry fold drops them, so palette/linker/rejudge/briefs can never touch them
        self.w(bf.NODESF,
               {"kind": "ask", "id": "demo:ask1", "sid": "S", "t": 100, "text": "demo root"},
               {"kind": "internal", "id": "demo:h1", "from_sid": "S", "to_sid": "S", "t": 110, "text": "demo hop"},
               {"kind": "parents", "id": "demo:h1", "parent_ids": ["demo:ask1"], "t": 110},
               {"kind": "ask", "id": "real#0", "sid": "S", "t": 120, "text": "real ask"})
        nodes, cleared, done = bf._load_registry()
        self.assertEqual(set(nodes), {"real#0"})
        cand = bf._candidates(nodes, cleared, done, "S")
        self.assertEqual([c["id"] for c in cand], ["real#0"])

    def test_corrective_amend_restores_title(self):
        # the re-title repair mechanism itself: a later amend row wins the fold in file order
        self.w(bf.NODESF,
               {"kind": "ask", "id": "a1", "sid": "S", "t": 100, "text": "original title"},
               {"kind": "amend", "id": "a1", "t": 200, "text": "hijacked by new wording"},
               {"kind": "amend", "id": "a1", "t": 300, "text": "original title",
                "note": "corrective re-title"})
        n, _c, _d = bf._load_registry()
        self.assertEqual(n["a1"]["text"], "original title")

    # ── follow-up filing (feed 'Follow up' box, 2026-06-10): follow-up turns file UNDER
    # their root — parents row to the followups.jsonl root, NEVER an amend/re-title. ──
    FU = {"id": "root#0", "sid": "anc", "t": NOW - 30, "text": "make the legend clickable"}

    def test_followup_root_matches(self):
        txt = 'Follow-up on "Add color legend": make the legend clickable too'
        self.assertEqual(bf._followup_root("anc", NOW, txt, [self.FU]), "root#0")

    def test_followup_root_window_and_sid(self):
        txt = 'Follow-up on "Add color legend": make the legend clickable too'
        self.assertIsNone(bf._followup_root("anc", NOW + 5000, txt, [self.FU]))   # stale row
        self.assertIsNone(bf._followup_root("other", NOW, txt, [self.FU]))        # wrong session

    def test_followup_root_text_discriminates_two_cards(self):
        rows = [self.FU, {"id": "root#9", "sid": "anc", "t": NOW - 20, "text": "sort the rows"}]
        txt = 'Follow-up on "Sort timeline": sort the rows by age instead'
        self.assertEqual(bf._followup_root("anc", NOW, txt, rows), "root#9")      # closer t loses to text

    def test_followup_asks_get_parents_row(self):
        self.w(bf.NODESF, {"kind": "ask", "id": "root#0", "sid": "anc", "t": NOW - 60, "text": "Add color legend"})
        nodes, _c, _d = bf._load_registry()
        bf._handle_req(("req", "anc", "sid", "T9", NOW, [], "root#0"),
                       "PHRASE :: follow-up tweak\nASK :: make the legend clickable", nodes)
        recs = self.read(bf.NODESF)
        parents = [r for r in recs if r["kind"] == "parents"]
        self.assertEqual(parents, [{"kind": "parents", "id": "T9#0", "parent_ids": ["root#0"], "t": NOW}])
        self.assertEqual(nodes["T9#0"]["parent_ids"], ["root#0"])                 # same-pass mirror

    def test_followup_amend_becomes_child_ask(self):
        # the user's ruling: a follow-up NEVER re-titles the root — AMEND converts to child ASK
        self.w(bf.NODESF, {"kind": "ask", "id": "root#0", "sid": "anc", "t": NOW - 60, "text": "Add color legend"})
        nodes, _c, _d = bf._load_registry()
        cand = [{"id": "root#0", "text": "Add color legend"}]
        bf._handle_req(("req", "anc", "sid", "TA", NOW, cand, "root#0"),
                       "PHRASE :: follow-up tweak\nAMEND 1 :: clickable color legend", nodes)
        recs = self.read(bf.NODESF)
        self.assertEqual([r for r in recs if r["kind"] == "amend"], [])           # no re-title
        self.assertEqual(nodes["root#0"]["text"], "Add color legend")
        self.assertEqual(nodes["TA#0"]["text"], "clickable color legend")         # intent kept as child
        self.assertEqual(nodes["TA#0"]["parent_ids"], ["root#0"])

    def test_followup_unknown_root_degrades_to_plain_ask(self):
        nodes = {}
        bf._handle_req(("req", "anc", "sid", "TB", NOW, [], "ghost#0"),
                       "PHRASE :: follow-up tweak\nASK :: do the thing", nodes)
        recs = self.read(bf.NODESF)
        self.assertEqual([r["kind"] for r in recs], ["ask"])                      # ask survives, no orphan edge

    def test_amend_targets_candidate(self):
        nodes = {"ask#0": {"kind": "ask", "id": "ask#0", "text": "old"}}
        cand = [{"id": "ask#0", "text": "old"}]
        bf._handle_req(("req", "anc", "sid", "T3", NOW, cand),
                       "PHRASE :: refine\nAMEND 1 :: new text", nodes)
        amends = [r for r in self.read(bf.NODESF) if r["kind"] == "amend"]
        self.assertEqual(amends[0]["id"], "ask#0")
        self.assertEqual(nodes["ask#0"]["text"], "new text")


class Candidates(unittest.TestCase):
    """_candidates: cap 12; eviction order DONE-linked-first then oldest (a TIEBREAKER,
    not a hard filter — multi-deliverable handoffs are the norm)."""

    def n_ask(self, i, t, sid="S"):
        return {"kind": "ask", "id": "a%d" % i, "sid": sid, "t": t, "text": "ask %d" % i}

    def n_int(self, i, t, to="S"):
        return {"kind": "internal", "id": "i%d" % i, "from_sid": "X", "to_sid": to,
                "t": t, "text": "handoff %d" % i}

    def test_cleared_and_foreign_excluded(self):
        nodes = {"a1": self.n_ask(1, 100), "a2": self.n_ask(2, 200),
                 "a3": self.n_ask(3, 300, sid="OTHER")}
        out = bf._candidates(nodes, {"a2"}, set(), "S")
        self.assertEqual([c["id"] for c in out], ["a1"])

    def test_asks_only_excludes_internal(self):
        nodes = {"a1": self.n_ask(1, 100), "i1": self.n_int(1, 200)}
        out = bf._candidates(nodes, set(), set(), "S", asks_only=True)
        self.assertEqual([c["id"] for c in out], ["a1"])

    def test_before_excludes_future(self):
        nodes = {"a1": self.n_ask(1, 100), "a2": self.n_ask(2, 900)}
        out = bf._candidates(nodes, set(), set(), "S", before=500)
        self.assertEqual([c["id"] for c in out], ["a1"])

    def test_cap_evicts_done_linked_first_then_oldest(self):
        nodes = {}
        for i in range(14):
            nodes["a%d" % i] = self.n_ask(i, 1000 + i)
        done_linked = {"a13"}                              # newest, but DONE-linked
        out = bf._candidates(nodes, set(), done_linked, "S")
        ids = [c["id"] for c in out]
        self.assertEqual(len(ids), 12)
        self.assertNotIn("a13", ids)                       # evicted first despite recency
        self.assertNotIn("a0", ids)                        # then the oldest
        self.assertIn("a1", ids)

    def test_numbered_newest_first(self):
        nodes = {"a1": self.n_ask(1, 100), "a2": self.n_ask(2, 200)}
        out = bf._candidates(nodes, set(), set(), "S")
        self.assertEqual([c["id"] for c in out], ["a2", "a1"])

    def test_done_flag_rides_candidates(self):
        nodes = {"a1": self.n_ask(1, 100), "a2": self.n_ask(2, 200)}
        out = bf._candidates(nodes, set(), {"a1"}, "S")
        flags = {c["id"]: c["_done"] for c in out}
        self.assertEqual(flags, {"a1": True, "a2": False})


class CompletedMarking(unittest.TestCase):
    """Amend-of-completed regression (the user, 2026-06-10): their new message amended a
    12h-finished ask because <open-asks> showed nothing marking it discharged — the old
    card got re-titled to today's wording. Discharged entries must render '(completed)'
    in the request/amend palette ONLY; the reply <candidates> block stays unmarked so
    batch closes can still link finished entries."""

    CAND = [{"id": "a2", "t": 200, "text": "new open ask", "_done": False},
            {"id": "a1", "t": 100, "text": "old finished ask", "_done": True}]

    def test_open_asks_marks_completed(self):
        block = bf._cand_block(self.CAND, "open-asks", mark_done=True)
        self.assertIn("1. new open ask", block)
        self.assertIn("2 (completed): old finished ask", block)

    def test_reply_candidates_stay_unmarked(self):
        block = bf._cand_block(self.CAND, "candidates")
        self.assertIn("2. old finished ask", block)
        self.assertNotIn("completed", block)

    def test_request_prompt_carries_marking(self):
        p = bf._request_prompt("fix the thing again", None, self.CAND)
        self.assertIn("2 (completed): old finished ask", p)

    def test_request_sys_forbids_amending_completed(self):
        self.assertIn("NEVER amend an entry marked", bf.REQUEST_SYS)
        self.assertIn("NEW ASK", bf.REQUEST_SYS)

    def test_request_sys_requires_topical_continuity(self):
        # chimera-amend fixture (decision_ref 021517ca, 2026-06-10): a different-subject turn
        # amended onto a recent ask fused two workstreams into a title nobody requested
        self.assertIn("TOPICAL CONTINUITY", bf.REQUEST_SYS)
        self.assertIn("when unsure between AMEND and ASK, choose ASK", bf.REQUEST_SYS)


class TwoWavePass(unittest.TestCase):
    """The same-pass hard requirement: an ask typed and answered within ONE catch-up pass
    must be visible to the reply linker (wave 1 lands before wave 2 prompts are built).
    Scripted llm — no model calls."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-2w-")
        req = os.path.join(self.dir, "requests")
        self._saved = {}
        for k, v in {"REQDIR": Path(req), "NODESF": Path(req) / "nodes.jsonl",
                     "LINKSF": Path(req) / "links.jsonl", "CLEARF": Path(req) / "cleared.jsonl",
                     "DECLOG": Path(req) / "decision-log.jsonl",
                     "SUMDIR": Path(self.dir) / "summaries"}.items():
            self._saved[k] = getattr(bf, k)
            setattr(bf, k, v)
        # one fixture transcript: the user asks (post-floor), turn closes, session idle
        self.tp = os.path.join(self.dir, "F.jsonl")
        lines = (typed_turn(NOW - 600, "Please build the widget for the dashboard")
                 + typed_turn(NOW - 300, "thanks, looks good"))
        with open(self.tp, "w") as f:
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
        self._fn = {n: getattr(bf, n) for n in
                    ("sessions", "session_states", "_reconcile_statusbars", "_msg_pending",
                     "events_for", "llm", "time")}
        bf.sessions = lambda now: [("F", Path(self.tp), "ANCHOR")]
        bf.session_states = lambda: {"F": "idle"}
        bf._reconcile_statusbars = lambda: None
        bf._msg_pending = lambda *a, **k: []
        bf.events_for = lambda sid, tp, now: ev.extract_events(sid, tp, now)
        # backfill_pass stamps its own time.time() into events_for/before= — pin it to the
        # fixture clock or the extractor's end=min(end, now) clamp collapses `before` to real
        # wall-clock and silently empties every candidate set (found the hard way).
        import types
        bf.time = types.SimpleNamespace(time=lambda: float(NOW))

        def fake_llm(sysp, txt, raw=False, model=None):
            # discriminate on the right PROMPT SECTION: the ask text also appears in
            # <open-asks>/<candidates>/<preceding> blocks of OTHER turns' prompts.
            if sysp is bf.REQUEST_SYS:
                if "widget" in txt.split("</request>")[0]:
                    return "PHRASE :: build dashboard widget\nASK :: build the dashboard widget"
                return "PHRASE :: acknowledged result\nACK"   # explicit zero-ask (closed classification)
            if sysp is bf.REPLY_SYS:
                turn = txt.split("<candidates>")[0]
                if "<candidates>" in txt and "Please build the widget" in turn:
                    return "DONE :: Built the widget :: LINK 1 :: DONE 1"
                return "DETAILS :: routine work"
            return ""
        bf.llm = fake_llm

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(bf, k, v)
        for n, fn in self._fn.items():
            setattr(bf, n, fn)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_same_pass_ask_visible_to_linker(self):
        bf.backfill_pass(50)
        nodes = [json.loads(l) for l in bf.NODESF.read_text().splitlines()]
        links = [json.loads(l) for l in bf.LINKSF.read_text().splitlines()]
        asks = [n for n in nodes if n["kind"] == "ask"]
        self.assertEqual(len(asks), 1)
        self.assertEqual(asks[0]["sid"], "ANCHOR")
        done = [l for l in links if l["relevance"] == "DONE"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["request_ids"], [asks[0]["id"]])   # linked IN THE SAME PASS


class RunAwareLink(unittest.TestCase):
    """Run-aware structural link (2026-06-12): a queued prompt folds into the SAME
    physical turn (an `absorbed` slice), and its work routinely ships under that
    later slice's reply. The reply must attach to the still-open asks of EVERY
    earlier slice in its run even when the model links none of them — before
    this, the earlier card kept no anchor to the shipping reply and was free to
    auto-file as looks-done (the tab-rename and compaction-% incidents)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-run-")
        req = os.path.join(self.dir, "requests")
        self._saved = {}
        for k, v in {"REQDIR": Path(req), "NODESF": Path(req) / "nodes.jsonl",
                     "LINKSF": Path(req) / "links.jsonl", "CLEARF": Path(req) / "cleared.jsonl",
                     "DECLOG": Path(req) / "decision-log.jsonl",
                     "SUMDIR": Path(self.dir) / "summaries"}.items():
            self._saved[k] = getattr(bf, k)
            setattr(bf, k, v)
        # one physical turn, two prompts: a typed ask, then a second ask queued
        # mid-turn (enqueue->remove = absorbed slice); the work for BOTH ships in
        # the absorbed slice's reply; a final typed ack closes that period.
        self.tp = os.path.join(self.dir, "R.jsonl")
        lines = [
            uline(NOW - 900, "Add a duration footer to finished cards", uuid="u1"),
            aline(NOW - 870, "Mapping the layout.", tools=("Read",), uuid="a1", parent="u1"),
            qop(NOW - 860, "enqueue", "Also recolor the working chip yellow"),
            qop(NOW - 855, "remove"),
            aline(NOW - 850, "Recolored the chip and added the duration footer.",
                  tools=("Edit",), uuid="a2", parent="a1"),
            uline(NOW - 300, "thanks, looks good", uuid="u2", parent="a2"),
            aline(NOW - 290, "ack", uuid="a3", parent="u2"),
        ]
        with open(self.tp, "w") as f:
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
        self._fn = {n: getattr(bf, n) for n in
                    ("sessions", "session_states", "_reconcile_statusbars", "_msg_pending",
                     "events_for", "llm", "time")}
        bf.sessions = lambda now: [("R", Path(self.tp), "ANCHOR")]
        bf.session_states = lambda: {"R": "idle"}
        bf._reconcile_statusbars = lambda: None
        bf._msg_pending = lambda *a, **k: []
        bf.events_for = lambda sid, tp, now: ev.extract_events(sid, tp, now)
        import types
        bf.time = types.SimpleNamespace(time=lambda: float(NOW))

        def fake_llm(sysp, txt, raw=False, model=None):
            if sysp is bf.REQUEST_SYS:
                req = txt.split("</request>")[0]
                if "duration footer" in req:
                    return "PHRASE :: add duration footer\nASK :: add a duration footer to finished cards"
                if "recolor" in req:
                    return "PHRASE :: recolor working chip\nASK :: recolor the working chip yellow"
                return "PHRASE :: acknowledged\nACK"
            if sysp is bf.REPLY_SYS:
                turn = txt.split("<candidates>")[0]
                if "Recolored the chip" in turn:
                    # the model misses BOTH links — the structural layers must cover
                    return "DONE :: Recolored chip and added footer :: LINK none :: DONE none"
                return "DETAILS :: routine work"
            return ""
        bf.llm = fake_llm

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(bf, k, v)
        for n, fn in self._fn.items():
            setattr(bf, n, fn)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_absorbed_slice_reply_attaches_to_earlier_slice_asks(self):
        bf.backfill_pass(50)
        nodes = [json.loads(l) for l in bf.NODESF.read_text().splitlines()]
        links = [json.loads(l) for l in bf.LINKSF.read_text().splitlines()]
        asks = [n for n in nodes if n["kind"] == "ask"]
        a_ask = next(n for n in asks if "duration" in n["text"])          # slice1 (typed)
        b_ask = next(n for n in asks if "recolor" in n["text"].lower())   # slice2 (absorbed)
        rep_eid = b_ask["id"].rsplit("#", 1)[0]                           # the absorbed slice's reply
        linked = {r for l in links if l["reply_id"] == rep_eid for r in l["request_ids"]}
        self.assertIn(b_ask["id"], linked, "own-turn structural link (pre-existing)")
        self.assertIn(a_ask["id"], linked, "RUN-AWARE link to the earlier slice's ask (the fix)")


# ───────────────────────── decision briefs ─────────────────────────

class BriefParser(unittest.TestCase):
    def test_full_output(self):
        out = ("CONTEXT :: You asked for X. The agent built most of it.\n"
               "QUESTION :: You're being asked to pick a scope.\n"
               "OPTION :: contained afternoon build\n"
               "OPTION :: full VS Code client")
        ctx, q, opts, needed = bf._parse_brief(out)
        self.assertTrue(ctx.startswith("You asked"))
        self.assertEqual(len(opts), 2)

    def test_no_options(self):
        ctx, q, opts, needed = bf._parse_brief("CONTEXT :: a\nQUESTION :: b")
        self.assertEqual((ctx, q, opts), ("a", "b", []))

    def test_junk_tolerated(self):
        ctx, q, opts, needed = bf._parse_brief("noise\nCONTEXT :: a\ngarbage line\nQUESTION :: b\n")
        self.assertEqual((ctx, q), ("a", "b"))
    def test_needed_no_parsed(self):
        # the second-opinion demotion (2026-06-11): NEEDED no must parse explicitly
        ctx, q, opts, needed = bf._parse_brief(
            "NEEDED :: no\nCONTEXT :: work done\nQUESTION :: nothing to decide")
        self.assertIs(needed, False)

    def test_needed_missing_is_none(self):
        ctx, q, opts, needed = bf._parse_brief("CONTEXT :: a\nQUESTION :: b")
        self.assertIsNone(needed)   # fail open: treated as yes downstream



class BriefChain(unittest.TestCase):
    def test_walks_parents_to_root(self):
        nodes = {
            "ask#0": {"kind": "ask", "id": "ask#0", "text": "the root ask"},
            "msg1": {"kind": "internal", "id": "msg1", "text": "the handoff",
                     "parent_ids": ["ask#0"]},
        }
        lines = bf._brief_chain(nodes, ["msg1"])
        self.assertEqual(lines, ["USER'S ASK: the root ask", "HANDOFF: the handoff"])

    def test_missing_node_tolerated(self):
        self.assertEqual(bf._brief_chain({}, ["ghost"]), [])


class BriefGenerate(unittest.TestCase):
    """_generate_brief end-to-end against temp dirs with a scripted llm."""

    SID = "S1"
    RID = "S1:100:aaaaaaaa"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-brief-")
        self._saved = {}
        for k, v in {"REQDIR": Path(self.dir) / "requests",
                     "BRIEF_DIR": Path(self.dir) / "decision-brief",
                     "SUMDIR": Path(self.dir) / "summaries",
                     "FEED_DETAIL_DIR": Path(self.dir) / "feed-detail"}.items():
            self._saved[k] = getattr(bf, k)
            setattr(bf, k, v)
        for k in ("NODESF", "LINKSF", "CLEARF", "DECLOG"):
            self._saved[k] = getattr(bf, k)
            setattr(bf, k, bf.REQDIR / (k[:-1].lower() + "s.jsonl"))
        bf.NODESF = bf.REQDIR / "nodes.jsonl"
        bf.LINKSF = bf.REQDIR / "links.jsonl"
        bf.CLEARF = bf.REQDIR / "cleared.jsonl"
        bf.DECLOG = bf.REQDIR / "decision-log.jsonl"
        bf.REQDIR.mkdir(parents=True)
        bf.SUMDIR.mkdir(parents=True)
        nodes = [{"kind": "ask", "id": "ask#0", "sid": self.SID, "t": 50, "text": "build the feature"},
                 {"kind": "internal", "id": "m1", "from_sid": "X", "to_sid": self.SID, "t": 60,
                  "text": "implement the feature core"},
                 {"kind": "parents", "id": "m1", "parent_ids": ["ask#0"], "t": 60}]
        bf.NODESF.write_text("".join(json.dumps(n) + "\n" for n in nodes))
        links = [{"kind": "link", "reply_id": self.RID, "request_ids": ["m1"],
                  "relevance": "DECISION", "sid": self.SID, "t": 100},
                 {"kind": "link", "reply_id": "S1:90:bbbbbbbb", "request_ids": ["m1"],
                  "relevance": "DONE", "sid": self.SID, "t": 90}]
        bf.LINKSF.write_text("".join(json.dumps(l) + "\n" for l in links))
        summaries = [{"id": self.RID, "t": 100, "kind": "reply",
                      "text": "Asked which storage backend to use", "relevance": "DECISION"},
                     {"id": "S1:90:bbbbbbbb", "t": 90, "kind": "reply",
                      "text": "Built the core module", "relevance": "DONE"}]
        (bf.SUMDIR / (self.SID + ".jsonl")).write_text(
            "".join(json.dumps(s) + "\n" for s in summaries))
        self.calls = []
        self._llm = bf.llm

        def fake_llm(sysp, txt, raw=False, model=None):
            self.calls.append(txt)
            return ("CONTEXT :: You asked to build the feature; the core is done.\n"
                    "QUESTION :: You're being asked to choose the storage backend.\n"
                    "OPTION :: sqlite\nOPTION :: flat files")
        bf.llm = fake_llm

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(bf, k, v)
        bf.llm = self._llm
        shutil.rmtree(self.dir, ignore_errors=True)

    def read_brief(self):
        return json.loads((bf.BRIEF_DIR / (self.RID + ".json")).read_text())

    def test_brief_written_with_chain_and_options(self):
        self.assertTrue(bf._generate_brief(self.RID))
        b = self.read_brief()
        self.assertEqual(b["options"], ["sqlite", "flat files"])
        self.assertEqual((b["sid"], b["t"]), (self.SID, 100))
        # the prompt saw the full lineage + delivered work + the asking reply
        self.assertIn("USER'S ASK: build the feature", self.calls[0])
        self.assertIn("DELIVERED: Built the core module", self.calls[0])
        self.assertIn("Asked which storage backend", self.calls[0])

    def test_idempotent_no_second_model_call(self):
        bf._generate_brief(self.RID)
        n = len(self.calls)
        self.assertTrue(bf._generate_brief(self.RID))
        self.assertEqual(len(self.calls), n)

    def test_options_null_when_absent(self):
        bf.llm = lambda *a, **k: "CONTEXT :: a\nQUESTION :: b"
        bf._generate_brief(self.RID)
        self.assertIsNone(self.read_brief()["options"])

    def test_missing_question_withholds_file(self):
        bf.llm = lambda *a, **k: "CONTEXT :: context only, model under-fired"
        self.assertFalse(bf._generate_brief(self.RID))
        self.assertFalse((bf.BRIEF_DIR / (self.RID + ".json")).exists())   # retried by the sweep

    def test_no_decision_link_no_brief(self):
        self.assertFalse(bf._generate_brief("S1:90:bbbbbbbb"))              # DONE-linked reply

    # ── voice + permission-ceremony polish (brief 1742ab48, 2026-06-10) ──
    def test_session_name_injected_for_voice(self):
        names = Path(self.dir) / "names"
        names.mkdir()
        (names / self.SID).write_text("db_timeline\t/x\n")
        saved = bf.NAMES
        bf.NAMES = names
        try:
            self.assertTrue(bf._generate_brief(self.RID))
        finally:
            bf.NAMES = saved
        self.assertIn("<session>db_timeline</session>", self.calls[0])

    def test_missing_name_omits_session_block(self):
        saved = bf.NAMES
        bf.NAMES = Path(self.dir) / "no-such-dir"
        try:
            self.assertTrue(bf._generate_brief(self.RID))
        finally:
            bf.NAMES = saved
        self.assertNotIn("<session>", self.calls[0])

    def test_brief_sys_voice_and_permission_ceremony(self):
        self.assertIn("NEVER 'a coding assistant'", bf.BRIEF_SYS)          # session-voice rule
        self.assertIn("already requested", bf.BRIEF_SYS)                   # permission-ceremony note

    # ── contradiction guardrail (01efe65e, 2026-06-10): a brief concluding nothing-is-
    # needed contradicts the ACTION/DECISION link that triggered it — must be declogged ──
    def test_no_action_brief_logs_contradiction(self):
        bf.llm = lambda *a, **k: ("CONTEXT :: All three fixes were implemented and shipped.\n"
                                  "QUESTION :: No decision or action is needed from you.")
        self.assertTrue(bf._generate_brief(self.RID))                      # file still lands
        dec = [json.loads(l) for l in bf.DECLOG.read_text().splitlines()]
        rows = [d for d in dec if d["kind"] == "brief-contradiction"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reply_id"], self.RID)

    def test_genuine_question_no_contradiction_row(self):
        bf._generate_brief(self.RID)                                       # default fake: real question
        try:
            dec = [json.loads(l) for l in bf.DECLOG.read_text().splitlines()]
        except OSError:
            dec = []
        self.assertEqual([d for d in dec if d["kind"] == "brief-contradiction"], [])

    def test_reply_sys_imperative_review_is_done(self):
        # 01efe65e: 'review the delivered changes and let me know…' tagged ACTION across
        # 3 requests, flipping an already-DONE handoff back open
        self.assertIn("even phrased as an instruction", bf.REPLY_SYS)
        self.assertIn("review the delivered changes", bf.REPLY_SYS)


class BriefSpawn(unittest.TestCase):
    """Spawn gating + the write-time trigger in _handle_rep."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-spawn-")
        self._saved = (bf.BRIEF_DIR, dict(bf._brief_spawned), list(bf._brief_procs),
                       bf.append_summary, bf._append_req, bf._declog)
        bf.BRIEF_DIR = Path(self.dir)
        bf._brief_spawned.clear()
        bf._brief_procs[:] = []
        self.spawncalls = []
        self._popen = bf.subprocess.Popen

        class FakeProc:
            def poll(self):
                return None
        bf.subprocess.Popen = lambda *a, **k: (self.spawncalls.append(a[0]), FakeProc())[1]

    def tearDown(self):
        (bf.BRIEF_DIR, spawned, procs, bf.append_summary, bf._append_req, bf._declog) = self._saved
        bf._brief_spawned.clear(); bf._brief_spawned.update(spawned)
        bf._brief_procs[:] = procs
        bf.subprocess.Popen = self._popen
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_spawn_then_cooldown(self):
        self.assertTrue(bf._spawn_brief("R1", 1000))
        self.assertFalse(bf._spawn_brief("R1", 1010))          # cooled down
        self.assertEqual(len(self.spawncalls), 1)
        self.assertIn("--brief", self.spawncalls[0])

    def test_existing_file_skipped(self):
        (bf.BRIEF_DIR / "R2.json").parent.mkdir(parents=True, exist_ok=True)
        (bf.BRIEF_DIR / "R2.json").write_text("{}")
        self.assertFalse(bf._spawn_brief("R2", 1000))

    def test_handle_rep_triggers_on_decision_only(self):
        bf.append_summary = lambda *a, **k: None
        bf._append_req = lambda *a, **k: None
        bf._declog = lambda *a, **k: None
        cand = [{"id": "a#0", "text": "the ask"}]
        bf._handle_rep(("rep", "anc", "sid", "RD", NOW, cand, False),
                       "DECISION :: Needs a choice :: LINK 1")
        bf._handle_rep(("rep", "anc", "sid", "RK", NOW, cand, False),
                       "DONE :: Shipped :: LINK 1 :: DONE 1")
        ids = [c[c.index("--brief") + 1] for c in self.spawncalls if "--brief" in c]
        self.assertEqual(ids, ["RD"])

    def test_tag_override_also_triggers(self):
        bf.append_summary = lambda *a, **k: None
        bf._append_req = lambda *a, **k: None
        bf._declog = lambda *a, **k: None
        cand = [{"id": "a#0", "text": "the ask"}]
        bf._handle_rep(("rep", "anc", "sid", "RT", NOW, cand, True),   # tailq=True forces DECISION
                       "DONE :: Shipped the fix and offered a next step :: LINK 1 :: DONE 1")
        ids = [c[c.index("--brief") + 1] for c in self.spawncalls if "--brief" in c]
        self.assertEqual(ids, ["RT"])


# ───────────────────────── needs-input taxonomy ─────────────────────────

class Taxonomy(unittest.TestCase):
    """{DONE, DECISION, ACTION, IDEA, DETAILS}: ACTION/IDEA/DECISION suppress completion
    marks (node stays open until the user's cross) and trigger brief prewarm."""

    def setUp(self):
        self.log = {"sum": [], "links": [], "dec": [], "briefs": []}
        self._saved = (bf.append_summary, bf._append_req, bf._declog, bf._spawn_brief)
        bf.append_summary = lambda sid, eid, kind, text, t, rel=None: self.log["sum"].append((eid, rel))
        bf._append_req = lambda path, rec: self.log["links"].append(rec)
        bf._declog = lambda rec: self.log["dec"].append(rec)
        bf._spawn_brief = lambda rid, now: self.log["briefs"].append(rid)
        self.cand = [{"id": "a#0", "text": "the ask"}]

    def tearDown(self):
        bf.append_summary, bf._append_req, bf._declog, bf._spawn_brief = self._saved

    def test_new_tags_parse(self):
        self.assertEqual(bf._split_relevance("ACTION :: Installed, reload to pick up")[0], "ACTION")
        self.assertEqual(bf._split_relevance("IDEA :: Proposed side panel instead")[0], "IDEA")
        self.assertEqual(bf._split_relevance("BANANA :: junk")[0], "DETAILS")   # unknown → default

    def test_action_suppresses_completion_and_briefs(self):
        bf._handle_rep(("rep", "anc", "sid", "RA", NOW, self.cand, False),
                       "ACTION :: Installed the panel update :: LINK 1 :: DONE 1")
        self.assertEqual(self.log["links"][0]["relevance"], "ACTION")     # not upgraded to DONE
        self.assertEqual(self.log["briefs"], ["RA"])                      # prewarmed

    def test_idea_suppresses_and_briefs(self):
        bf._handle_rep(("rep", "anc", "sid", "RI", NOW, self.cand, False),
                       "IDEA :: Proposed side panel alternative :: LINK 1 :: DONE 1")
        self.assertEqual(self.log["links"][0]["relevance"], "IDEA")
        self.assertEqual(self.log["briefs"], ["RI"])

    def test_done_still_upgrades_no_brief(self):
        bf._handle_rep(("rep", "anc", "sid", "RD", NOW, self.cand, False),
                       "DONE :: Shipped it live :: LINK 1 :: DONE 1")
        self.assertEqual(self.log["links"][0]["relevance"], "DONE")
        self.assertEqual(self.log["briefs"], [])


# ───────────────────────── re-judgment backfill ─────────────────────────

class Rejudge(unittest.TestCase):
    """--rejudge: open leaves re-verdicted under the upgraded prompt; DONE flips become
    corrections rows (links.jsonl untouched); corrected leaves are skipped on re-run."""

    SID = "S1"
    RID = "S1:100:aaaaaaaa"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-rj-")
        self._saved = {}
        for k in ("REQDIR", "NODESF", "LINKSF", "CLEARF", "DECLOG"):
            self._saved[k] = getattr(bf, k)
        bf.REQDIR = Path(self.dir) / "requests"
        bf.NODESF = bf.REQDIR / "nodes.jsonl"
        bf.LINKSF = bf.REQDIR / "links.jsonl"
        bf.CLEARF = bf.REQDIR / "cleared.jsonl"
        bf.DECLOG = bf.REQDIR / "decision-log.jsonl"
        bf.REQDIR.mkdir(parents=True)
        bf.NODESF.write_text(json.dumps(
            {"kind": "ask", "id": "ask#0", "sid": self.SID, "t": 50, "text": "build the widget"}) + "\n")
        bf.LINKSF.write_text(json.dumps(                       # old-prompt DETAILS verdict → open leaf
            {"kind": "link", "reply_id": self.RID, "request_ids": ["ask#0"],
             "relevance": "DETAILS", "sid": self.SID, "t": 100}) + "\n")
        bf.DECLOG.write_text(json.dumps(
            {"kind": "link", "reply_id": self.RID, "sid": self.SID, "t": 100,
             "candidates": [{"id": "ask#0", "text": "build the widget"}],
             "chosen": ["ask#0"], "raw": "1"}) + "\n")
        self._fn = {n: getattr(bf, n) for n in ("sessions", "events_for", "llm")}
        bf.sessions = lambda now: [(self.SID, Path("/fake"), self.SID)]
        bf.events_for = lambda sid, tp, now: {"events": [
            {"id": self.RID, "t": 100, "end": 110, "peer": False,
             "rec": "USER ASKED: build the widget\nASSISTANT SAID: Widget built, "
                    "tested and shipped. Nothing pending.\nTOOLS USED: Edit"}]}
        self.calls = []
        def fake_llm(sysp, txt, raw=False, model=None):
            self.calls.append(txt)
            return "DONE :: Built and shipped the widget :: LINK 1 :: DONE 1"
        bf.llm = fake_llm

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(bf, k, v)
        for n, fn in self._fn.items():
            setattr(bf, n, fn)
        shutil.rmtree(self.dir, ignore_errors=True)

    def corr(self):
        p = bf.REQDIR / "corrections.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def test_flip_writes_corrections_row(self):
        self.assertEqual(bf._rejudge_pass(), 1)
        rows = self.corr()
        self.assertEqual(rows[0]["should_have"], {"request_ids": ["ask#0"], "relevance": "DONE"})
        self.assertEqual(rows[0]["decision_ref"], self.RID)     # merge-compatible synthetic reply
        # links.jsonl untouched
        self.assertEqual(len(bf.LINKSF.read_text().splitlines()), 1)

    def test_rerun_skips_corrected_leaf(self):
        bf._rejudge_pass()
        n = len(self.calls)
        self.assertEqual(bf._rejudge_pass(), 0)                  # corrected → no longer open
        self.assertEqual(len(self.calls), n)                     # and no model spend

    def test_non_done_verdict_no_row(self):
        bf.llm = lambda *a, **k: "DECISION :: Asked which widget variant to keep :: LINK 1"
        self.assertEqual(bf._rejudge_pass(), 0)
        self.assertEqual(self.corr(), [])

    def test_cleared_leaf_skipped(self):
        bf.CLEARF.write_text(json.dumps({"id": "ask#0", "t": 200}) + "\n")
        self.assertEqual(bf._rejudge_pass(), 0)
        self.assertEqual(self.calls, [])


# ───────────────────────── d. anchor-sid fork resolution ─────────────────────────

class ForkResolution(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-ptest-fork-")
        # sessions() resolves project dirs via _proj_dir, re-exported from the daemon's
        # PRIVATE romp_events module copy — patch PROJECTS there too, or the patch is silent
        self._saved = (bf.NAMES, bf.PROJECTS, bf.romp_events.PROJECTS)
        bf.NAMES = Path(self.dir) / "names"
        bf.PROJECTS = bf.romp_events.PROJECTS = Path(self.dir) / "projects"
        bf.NAMES.mkdir(parents=True)
        cdir = "/Users/test/proj"
        (bf.NAMES / "anchor-sid").write_text("my_session\t%s\n" % cdir)
        proj = bf.PROJECTS / re.sub(r"[/.]", "-", cdir)
        proj.mkdir(parents=True)
        (proj / "anchor-sid.jsonl").write_text(json.dumps(uline(NOW - 100, "hi")) + "\n")
        fork = [{"type": "custom-title", "customTitle": "my_session"}, uline(NOW - 50, "post-clear")]
        (proj / "fork-sid.jsonl").write_text("".join(json.dumps(l) + "\n" for l in fork))
        (proj / "stranger.jsonl").write_text(json.dumps(uline(NOW - 50, "other")) + "\n")
        now = NOW
        for p in proj.iterdir():
            os.utime(p, (now, now))

    def tearDown(self):
        bf.NAMES, bf.PROJECTS, bf.romp_events.PROJECTS = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_fork_resolves_to_anchor(self):
        # pin now=NOW (the fixture's mtime stamp): real wall clock walks past WINDOW and
        # silently empties the result — same time-bomb family as the extract_events clamp
        got = bf.sessions(NOW)
        by_stem = {sid: anchor for sid, tp, anchor in got}
        self.assertEqual(by_stem.get("anchor-sid"), "anchor-sid")
        self.assertEqual(by_stem.get("fork-sid"), "anchor-sid")     # fork keys to the anchor
        self.assertNotIn("stranger", by_stem)                       # no title match → not ours


if __name__ == "__main__":
    unittest.main(verbosity=2)
