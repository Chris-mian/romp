#!/usr/bin/env python3
"""Golden contract tests for the romp-events extractor.

Each scenario builds a synthetic transcript, runs the REAL extract_events on
it with a fixed clock, and compares the FULL output (events, pending,
compactions — every field) against a checked-in golden JSON file. Together the
scenarios pin the extractor's external contract: boundary kinds (typed,
queued, absorbed, drain, decision), stable event ids, peer gating, banner
stripping, idle-gap clipping, active-path uuid anchoring, and pending dots.

This is the contract any future session backend must reproduce: if a refactor
changes a golden file, that diff IS the contract change and must be reviewed
as one (and CACHE_VERSION in bin/romp-events bumped).

Run:    python3 tests/test_romp_events_golden.py
Regen:  python3 tests/test_romp_events_golden.py --regen   (then REVIEW the diff)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
GOLDEN = Path(HERE) / "fixtures" / "events-golden"

ev = SourceFileLoader("romp_events_g", os.path.join(SCRIPTS, "romp-events")).load_module()

NOW = 1781100000                      # fixed test clock — goldens depend on it; never change casually
SID = "11111111-2222-3333-4444-555555555555"


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, ps="typed", uuid=None, parent=None):
    return {"type": "user", "timestamp": iso(t), "promptSource": ps,
            "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": text}}


def aline(t, text, tools=(), uuid=None, parent=None, extra_content=None):
    content = [{"type": "text", "text": text}]
    content += [{"type": "tool_use", "id": "tu_%d" % i, "name": n, "input": {}}
                for i, n in enumerate(tools)]
    if extra_content:
        content += extra_content
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": content}}


def qop(t, op, content=None):
    # real queue-operation records carry NO uuid/parentUuid (verified against live
    # transcripts) — giving them one would corrupt the active-path leaf in fixtures
    return {"type": "queue-operation", "timestamp": iso(t), "operation": op,
            "content": content}


def tool_result_line(t, tool_use_id, content="", uuid=None, parent=None,
                     tool_use_result=None, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    r = {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
         "message": {"role": "user", "content": [block]}}
    if tool_use_result is not None:
        r["toolUseResult"] = tool_use_result
    return r


BANNER = ("############################################\n"
          "## \U0001F4EC from feed_design · 16:52\n"
          "############################################\n"
          "ASK: bump the colormap alpha on the recency tint.\n"
          "<!-- romp-msg-id: 1781051207.67474_57710.TESTHOST -->\n"
          "############################################")

T0 = NOW - 3600                       # base time for most scenarios


def scenario_typed_two_turns():
    """Two typed prompts, replies with tools; last period open, end = last assistant ts."""
    return [
        uline(T0, "fix the flicker in the feed panel", uuid="u1"),
        aline(T0 + 30, "Found the cause in feed.css.", tools=("Read", "Edit"),
              uuid="a1", parent="u1"),
        aline(T0 + 90, "Fixed: debounced the repaint.", uuid="a2", parent="a1"),
        uline(T0 + 600, "now add some color to the cards", uuid="u2", parent="a2"),
        aline(T0 + 660, "Tinted cards by recency.", tools=("Edit",), uuid="a3", parent="u2"),
    ]


def scenario_queued_and_absorbed():
    """enqueue→dequeue = its own `queued` turn; enqueue→remove = `absorbed` boundary at fold ts."""
    return [
        uline(T0, "refactor the ledger", uuid="u1"),
        aline(T0 + 20, "Working through romp-ledger.", tools=("Read",), uuid="a1", parent="u1"),
        qop(T0 + 40, "enqueue", "also rename the digest file"),
        qop(T0 + 60, "remove"),                       # folded mid-turn → absorbed @ T0+60
        aline(T0 + 80, "Folded the rename in too.", uuid="a2", parent="a1"),
        qop(T0 + 100, "enqueue", "and check the tests pass"),
        qop(T0 + 200, "dequeue"),                     # re-surfaced as the queued user line below
        uline(T0 + 200, "and check the tests pass", ps="queued", uuid="u2", parent="a2"),
        aline(T0 + 230, "Tests pass.", tools=("Bash",), uuid="a3", parent="u2"),
    ]


def scenario_pending_and_skips():
    """Still-queued enqueue → pending dot; banner + task-notification enqueues → no dot."""
    return [
        uline(T0, "start the migration", uuid="u1"),
        aline(T0 + 30, "Migrating.", uuid="a1", parent="u1"),
        qop(T0 + 60, "enqueue", "remember to update the docs"),  # unresolved → pending
        qop(T0 + 70, "enqueue", BANNER),                          # peer banner → skipped
        qop(T0 + 80, "enqueue", "<task-notification>bg task done</task-notification>"),  # harness → skipped
    ]


def scenario_drain():
    """A Stop-hook-drained inbound message: kind=drain, peer, mids, banner-stripped display."""
    drain = ("Stop hook feedback: \U0001F4EC New message(s) while you worked — "
             "from feed_design (2026-06-10T16:52:07Z): Q: which alpha did you pick? "
             "<!-- romp-msg-id: 1781051207.67474_57710.TESTHOST --> (to reply: send_message)")
    return [
        uline(T0, "tune the recency colormap", uuid="u1"),
        aline(T0 + 30, "Lowered tint alpha to 0.18.", tools=("Edit",), uuid="a1", parent="u1"),
        uline(T0 + 120, drain, ps=None, uuid="u2", parent="a1"),
        aline(T0 + 150, "Replied with the alpha value.", uuid="a2", parent="u2"),
    ]


def scenario_decision_ask_user():
    """AskUserQuestion mid-turn: the tool_result splits the turn into a `decision` boundary."""
    ask = [{"type": "tool_use", "id": "tu_ask", "name": "AskUserQuestion",
            "input": {"questions": [{"question": "Stack or scroll when narrow?",
                                     "header": "Layout"}]}}]
    tur = {"questions": [{"question": "Stack or scroll when narrow?", "header": "Layout"}],
           "answers": {"Stack or scroll when narrow?": "Stack"}}
    return [
        uline(T0, "make the feed responsive", uuid="u1"),
        aline(T0 + 30, "Two options for narrow widths.", uuid="a1", parent="u1",
              extra_content=ask),
        tool_result_line(T0 + 300, "tu_ask", uuid="u2", parent="a1", tool_use_result=tur),
        aline(T0 + 330, "Stacking columns under 700px.", tools=("Edit",), uuid="a2", parent="u2"),
    ]


def scenario_decision_plan():
    """ExitPlanMode approve (plan headline) and reject (the user's redirect words)."""
    plan_use = [{"type": "tool_use", "id": "tu_plan", "name": "ExitPlanMode",
                 "input": {"plan": "# Port the nag plugin\n\nSteps..."}}]
    plan_use2 = [{"type": "tool_use", "id": "tu_plan2", "name": "ExitPlanMode",
                  "input": {"plan": "# Rewrite everything in Rust"}}]
    return [
        uline(T0, "plan the nag plugin port", uuid="u1"),
        aline(T0 + 30, "Here is a plan.", uuid="a1", parent="u1", extra_content=plan_use),
        tool_result_line(T0 + 120, "tu_plan", uuid="u2", parent="a1",
                         content="User approved the plan."),
        aline(T0 + 150, "Porting now.", tools=("Edit",), uuid="a2", parent="u2"),
        aline(T0 + 200, "Proposing a second plan.", uuid="a3", parent="a2",
              extra_content=plan_use2),
        tool_result_line(T0 + 400, "tu_plan2", uuid="u3", parent="a3", is_error=True,
                         content="Plan rejected; the user said: too risky, just patch it"),
        aline(T0 + 430, "Patching instead.", uuid="a4", parent="u3"),
    ]


def scenario_idle_gap_clip():
    """A >IDLE_GAP silence between assistant lines clips the period: later lines belong
    to a later turn (revive), so the bar must not span the dead gap."""
    t0 = NOW - 2 * 3600
    return [
        uline(t0, "investigate the crash", uuid="u1"),
        aline(t0 + 60, "Reproduced it.", tools=("Bash",), uuid="a1", parent="u1"),
        # session dies; revived much later — this line is NOT part of the turn above
        aline(t0 + 60 + ev.IDLE_GAP + 300, "Back after revive.", uuid="a2", parent="a1"),
    ]


def scenario_compaction_marker():
    """isCompactSummary lines are point markers in `compactions`, never boundaries."""
    return [
        uline(T0, "long running refactor", uuid="u1"),
        aline(T0 + 30, "Working.", uuid="a1", parent="u1"),
        {"type": "system", "timestamp": iso(T0 + 500), "uuid": "c1", "parentUuid": None,
         "logicalParentUuid": "a1", "isCompactSummary": True,
         "compactMetadata": {"trigger": "auto"},
         "message": {"role": "user", "content": "summary of the conversation"}},
        aline(T0 + 530, "Continuing post-compaction.", uuid="a2", parent="c1"),
    ]


def scenario_peer_banner_typed():
    """A pushed-mail banner arriving as a typed line: peer=True (from RAW text), display
    stripped to the body, id minted from the RAW text so summaries stay bound."""
    return [
        uline(T0, BANNER, uuid="u1"),
        aline(T0 + 30, "On it — bumping the alpha.", tools=("Edit",), uuid="a1", parent="u1"),
    ]


def scenario_rewind_off_path():
    """A rewound branch: the abandoned turn's uuids are off the active path, so its
    event anchors fall back (uuid=None) instead of pointing at unreachable lines."""
    return [
        uline(T0, "first attempt", uuid="u1"),
        aline(T0 + 30, "Did it one way.", uuid="a1", parent="u1"),
        uline(T0 + 300, "abandoned follow-up", uuid="u2", parent="a1"),
        aline(T0 + 330, "Going down a dead end.", uuid="a2", parent="u2"),
        # the user rewinds to a1 and takes a different branch — leaf chain skips u2/a2
        uline(T0 + 600, "second attempt instead", uuid="u3", parent="a1"),
        aline(T0 + 630, "Better approach done.", uuid="a3", parent="u3"),
    ]


SCENARIOS = {
    "typed_two_turns": scenario_typed_two_turns,
    "queued_and_absorbed": scenario_queued_and_absorbed,
    "pending_and_skips": scenario_pending_and_skips,
    "drain": scenario_drain,
    "decision_ask_user": scenario_decision_ask_user,
    "decision_plan": scenario_decision_plan,
    "idle_gap_clip": scenario_idle_gap_clip,
    "compaction_marker": scenario_compaction_marker,
    "peer_banner_typed": scenario_peer_banner_typed,
    "rewind_off_path": scenario_rewind_off_path,
}


def run_scenario(name):
    records = SCENARIOS[name]()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / (SID + ".jsonl")
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return ev.extract_events(SID, str(path), NOW)


class GoldenTests(unittest.TestCase):
    maxDiff = None


def _add_case(name):
    def test(self):
        golden_path = GOLDEN / (name + ".json")
        self.assertTrue(golden_path.exists(),
                        "missing golden %s — run with --regen and review" % golden_path)
        expected = json.loads(golden_path.read_text())
        actual = json.loads(json.dumps(run_scenario(name)))   # normalize tuples etc.
        self.assertEqual(expected, actual,
                         "extract_events contract changed for %r — if intended, --regen, "
                         "review the diff, and bump CACHE_VERSION in bin/romp-events" % name)
    setattr(GoldenTests, "test_" + name, test)


for _n in SCENARIOS:
    _add_case(_n)


class IdStability(unittest.TestCase):
    """The id is the join key for every summary ever written — pin its derivation."""

    def test_same_input_same_id(self):
        a = run_scenario("typed_two_turns")
        b = run_scenario("typed_two_turns")
        self.assertEqual([e["id"] for e in a["events"]], [e["id"] for e in b["events"]])

    def test_id_shape(self):
        for e in run_scenario("typed_two_turns")["events"]:
            sid, t, h = e["id"].rsplit(":", 2)
            self.assertEqual(sid, SID)
            self.assertEqual(int(t), e["t"])
            self.assertEqual(len(h), 8)

    def test_id_from_raw_not_stripped_text(self):
        """Banner turns mint their id from the RAW text; cosmetic stripping must not move it."""
        out = run_scenario("peer_banner_typed")
        e = out["events"][0]
        flat = " ".join(BANNER.split())[:140]
        self.assertEqual(e["id"], ev._eid(SID, e["t"], flat))
        self.assertNotIn("####", e["text"])               # display IS stripped


def regen():
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in sorted(SCENARIOS):
        out = run_scenario(name)
        p = GOLDEN / (name + ".json")
        p.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print("wrote %s  (%d events, %d pending, %d compactions)"
              % (p, len(out["events"]), len(out["pending"]), len(out["compactions"])))


if __name__ == "__main__":
    if "--regen" in sys.argv:
        regen()
    else:
        unittest.main(verbosity=2)
