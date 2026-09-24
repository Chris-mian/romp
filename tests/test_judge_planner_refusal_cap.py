#!/usr/bin/env python3
"""A content refusal on a planner call stops being retried at the cap instead of looping (the user 2026-09-23).

The incident, reproduced here SYNTHETICALLY (the real one is described by shape only): one work-run
segment's planner call came back as the CLI's classifier-stop envelope — "<model> can't help with this.
Start a new session to continue." — the API's `refusal` stop reason, which is the FILTER ruling on that
segment's text, so the same call returned the same envelope on every pass. It fell through BOTH give-up
guards. The planner's call-failure branch (`not ops and not raw`) counted no strike and had no horizon, by
design: a rate-limit window must not burn PLAN_PARSE_RETRIES and drop a segment — right for a transient
failure, exactly wrong for a refusal. And the model-scoped health latch counts CONSECUTIVE failures per
model, reset by every served reply on that model, which every other segment supplied constantly. Measured:
~42,600 doomed calls on one segment over five days at ~300 an hour. The envelope also latched a serving
model degraded, since only the safeguards wording was exempted from the health latch, by a bare substring
test in one place.

Under test:
  - _REFUSAL_ENVELOPE_RE names the class ONCE: the safeguards flag and the classifier stop match; a 529, a
    usage limit, an auth error, a dead CLI and prose that merely says "refuse" do not (narrow, anchored on
    the envelope text);
  - _judge_run stamps `refusal` on its failure stash and exempts a refusal from the model-health latch
    whichever wording it wears, while a 529 still latches exactly as before;
  - the planner strikes a refused work-run against the SAME item-scoped counter the parse path uses and,
    at PLAN_PARSE_RETRIES, takes the SAME give-up: one loud "give-up" row that says refusal (not parse
    reject) and carries the envelope, the user message hard-placed, and no further call;
  - a TRANSIENT envelope keeps today's contract exactly — no strike, retry every pass — and a stale
    refusal stash never charges a unit whose own call was skipped (the pre-call reset).
All fixtures are SYNTHETIC: a private placeholder UUID, invented text, no hostnames. The envelope strings
are the API's and the CLI's own wording, not session content."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = load_source("romp_judge_planner_refusal_cap", os.path.join(BIN, "romp-judge"))

NOW = 1781100000
# a PRIVATE synthetic sid (the goal-store fixtures rule, 2026-08-24): this module mints a goal, and the
# shared 11111111-2222-… placeholder can be re-flagged by other modules' journaled overrides
SID = "12121212-3434-4565-8787-909090909090"
T0 = NOW - 3600
ASK = "please tidy the notes-api release checklist before the tag"

# the two refusal envelopes as the CLI renders them, and one transient envelope for contrast
REFUSAL = "API Error: Sonnet 5 can't help with this. Start a new session to continue."
REFUSAL_CURLY = REFUSAL.replace("'", "’")
SAFEGUARDS = "API Error: the model's safeguards flagged this message."
OVERLOAD = "API Error: Repeated 529 Overloaded errors."


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent=None, stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": stop}}


def _drain_health():
    while jd.consume_judge_recovery():
        pass
    with jd._health_lock:
        jd._CALL_HEALTH["degraded"] = set()
        jd._CALL_HEALTH["stats"] = {}


class _Harness(unittest.TestCase):
    """A private state root (ERRORS and GOALDIR move with it), the rate gate held open, the process-global
    health latch snapshotted and restored (a later test must not inherit a degraded model), and a fake
    `subprocess.run` so the envelope travels through _judge_run's REAL error-envelope branch — the stash
    and the matcher are the code under test, so no stub above them may stand in."""

    def setUp(self):
        self._saved_state = jd.STATE
        self._td = tempfile.mkdtemp()
        jd._rebind_state(Path(self._td))   # GOALDIR, ERRORS and every derived dir move too
        jd.STATE.mkdir(parents=True, exist_ok=True)
        (jd.STATE / "usage.json").write_text(json.dumps(
            {"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))   # the rate gate stays open
        jd._judge_ctx.last_call_fail = None
        jd._judge_ctx.paused = False
        with jd._health_lock:
            self._health = (set(jd._CALL_HEALTH["degraded"]), jd._CALL_HEALTH["recovered"],
                            {m: dict(s) for m, s in jd._CALL_HEALTH["stats"].items()})
        _drain_health()
        self._saved_fns = (jd.subprocess.run, jd._group_store, jd.plan_llm)
        jd._group_store = lambda *a, **k: None   # never fire the grouper model after a placement
        self.calls = []

    def tearDown(self):
        jd.subprocess.run, jd._group_store, jd.plan_llm = self._saved_fns
        with jd._health_lock:
            jd._CALL_HEALTH["degraded"].clear()
            jd._CALL_HEALTH["degraded"].update(self._health[0])
            jd._CALL_HEALTH["recovered"] = self._health[1]
            jd._CALL_HEALTH["stats"].clear()
            jd._CALL_HEALTH["stats"].update(self._health[2])
        jd._judge_ctx.last_call_fail = None
        jd._rebind_state(self._saved_state)
        shutil.rmtree(self._td, ignore_errors=True)

    def _fake_envelope(self, envelope):
        """Every judge subprocess answers with this CLI envelope; the prompt each call carried is kept."""
        def fake_run(cmd, input=None, capture_output=None, text=None, cwd=None, env=None, timeout=None):
            self.calls.append(input or "")
            return SimpleNamespace(stdout=json.dumps(envelope), stderr="", returncode=0)
        jd.subprocess.run = fake_run

    def _errors(self):
        try:
            return [json.loads(l) for l in Path(jd.ERRORS).read_text().splitlines()]
        except OSError:
            return []

    def _passes(self, n):
        """Run the planner `n` times over ONE ended human turn — exactly one work-run unit, so one planner
        call per pass until something resolves it. Returns each pass's placement count."""
        tpath = Path(self._td) / (SID + ".jsonl")
        records = [uline(T0, ASK, "u1"),
                   aline(T0 + 30, "Tidied the checklist and pushed it.", "a1", "u1")]
        tpath.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return [jd._plan_session(SID, str(tpath), NOW) for _ in range(n)]


class RefusalMatcher(unittest.TestCase):
    """One definition of a content refusal, shared by the health exemption and the planner's strike."""

    def test_names_both_refusal_envelopes(self):
        for text in (SAFEGUARDS, REFUSAL, REFUSAL_CURLY,
                     "stop_reason: refusal", '{"stop_reason":"refusal"}'):
            with self.subTest(text=text):
                self.assertTrue(jd._REFUSAL_ENVELOPE_RE.search(text), "a content refusal, whichever wording")

    def test_stays_narrow(self):
        for text in (OVERLOAD,
                     "Claude AI usage limit reached — resets 12:00",
                     "rate limit reached, try again shortly",
                     "API Error: 401 authentication_error",
                     "the proxy refused the connection",
                     "I refuse to answer that",
                     "the model CLI died with no output (exit 1)"):
            with self.subTest(text=text):
                self.assertFalse(jd._REFUSAL_ENVELOPE_RE.search(text),
                                 "anchored on the envelope text — never a generic word")


class RefusalIsNotModelHealth(_Harness):
    """_judge_run's error-envelope branch: the stash says WHY the call failed, and a refusal — either
    wording — never latches the model degraded, while a 529 still does exactly as before."""

    def test_refusal_stamps_the_stash_and_never_latches_health(self):
        for text in (REFUSAL, REFUSAL_CURLY, SAFEGUARDS):
            with self.subTest(text=text):
                _drain_health()
                self._fake_envelope({"is_error": True, "result": text})
                out = jd._judge_run("sonnet", "SYS", "u", judge="planner", tier="triage")
                self.assertEqual(out, "", "an error envelope is a failed call to the caller")
                st = jd._judge_ctx.last_call_fail
                self.assertIs(st.get("refusal"), True,
                              "the stash names the class: a content refusal, deterministic per prompt")
                self.assertIn("API Error", st["note"], "the evidence still reaches the warn")
                jd._mark_call_served("sonnet")
                self.assertFalse(jd.consume_judge_recovery(),
                                 "a content refusal is not API degradation — no degraded→serving edge")

    def test_transient_envelope_is_not_a_refusal_and_still_latches(self):
        self._fake_envelope({"is_error": True, "result": OVERLOAD})
        jd._judge_run("sonnet", "SYS", "u", judge="planner", tier="triage")
        st = jd._judge_ctx.last_call_fail
        self.assertFalse(st.get("refusal"), "a 529 is the API answering, not a ruling on the content")
        jd._mark_call_served("sonnet")
        self.assertTrue(jd.consume_judge_recovery(), "a 529 IS model health: the latch is unchanged")


class PlannerRefusalCap(_Harness):
    """The planner's work-run under a deterministic refusal: strike, cap, loud give-up, no further call."""

    def test_refusal_gives_up_at_the_cap_instead_of_looping(self):
        self._fake_envelope({"is_error": True, "result": REFUSAL})
        cap = jd.PLAN_PARSE_RETRIES
        placed = self._passes(cap + 3)
        self.assertEqual(len(self.calls), cap,
                         "one doomed call per pass UNTIL the cap, then none — the segment is parked, not "
                         "retried forever (the 42,600-call loop)")
        self.assertEqual(placed, [0] * (cap - 1) + [1] + [0] * 3,
                         "nothing placed under the cap; the capping pass hard-places the user message ONCE; "
                         "the passes after it have nothing left to do")
        store = jd.load_goals(SID)
        tops = [nd for nd in store["nodes"].values() if nd.get("parentId") is None]
        self.assertEqual(len(tops), 1, "the user message is hard-placed — never lost to the refusal")
        self.assertEqual(store.get("parseFails", {}), {}, "the shared item-scoped counter is cleared once resolved")
        give = [r for r in self._errors() if r.get("err") == "give-up"]
        self.assertEqual(len(give), 1, "one loud give-up row: an operator can see the segment parked")
        self.assertEqual((give[0]["judge"], give[0]["fsid"]), ("planner", SID))
        self.assertTrue(give[0].get("seg"), "the row names the segment it parked")
        note = give[0]["note"]
        self.assertTrue(note.startswith("%d content refusals" % cap), note)
        self.assertIn("can't help with this", note, "the envelope that parked it is readable from the row")
        self.assertIn("hard-placed", note, "…and so is the resolution")
        self.assertEqual([r for r in self._errors() if r.get("err") == "parse"], [],
                         "a refusal is never logged as a parse reject — the model wrote nothing")
        self.assertEqual(len([r for r in self._errors() if r.get("err") == "call"]), cap,
                         "each doomed call was logged as what it was, and there were exactly cap of them")

    def test_transient_envelope_keeps_retrying_without_a_strike(self):
        # the exemption the refusal path carves out of STAYS for everything else: a 529's recovery is the
        # storm ending, and striking it would drop a segment for good off a thirty-second outage
        self._fake_envelope({"is_error": True, "result": OVERLOAD})
        cap = jd.PLAN_PARSE_RETRIES
        placed = self._passes(cap + 2)
        self.assertEqual(len(self.calls), cap + 2, "a transient failure retries every pass — no horizon here, on purpose")
        self.assertEqual(placed, [0] * (cap + 2), "nothing placed off a failed call")
        store = jd.load_goals(SID)
        self.assertEqual(store.get("parseFails", {}), {}, "no strike: a rate-limit window must never burn PLAN_PARSE_RETRIES")
        self.assertEqual(store["nodes"], {}, "no goal invented off a failed call")
        self.assertEqual([r for r in self._errors() if r.get("err") in ("give-up", "parse")], [],
                         "no give-up and no phantom parse row for a transient failure")

    def test_a_stale_refusal_stash_never_charges_a_unit_whose_call_was_skipped(self):
        # a pause-skip or a rate-gate skip returns "" and writes NO stash: without the pre-call reset the
        # PREVIOUS unit's refusal would strike a unit whose call never went out
        jd._judge_ctx.last_call_fail = {"note": REFUSAL[:160], "model": "sonnet", "refusal": True}
        jd.plan_llm = lambda *a, **k: ""   # the call was skipped upstream; nothing to parse, no stash written
        cap = jd.PLAN_PARSE_RETRIES
        placed = self._passes(cap + 1)
        self.assertEqual(placed, [0] * (cap + 1))
        self.assertEqual(jd.load_goals(SID).get("parseFails", {}), {},
                         "a skipped call is not a refusal of THIS unit — no strike")
        self.assertEqual([r for r in self._errors() if r.get("err") == "give-up"], [])


if __name__ == "__main__":
    unittest.main()
