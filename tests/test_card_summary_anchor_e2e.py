#!/usr/bin/env python3
"""The card's brief click, end to end through build_feed (T388): a blocked card whose brief has no validated
citation, whose newest trail segment holds only a tool call, and whose wrap-up sits in the same turn's second
segment. The base landed on the tool call (the segment's first landable atom, a collapsed tool group); the head
lands on the text atom that carries the brief's opening sentence, with the span the chat highlights. The same
harness shows a body read that raises leaving build_feed whole, and (the verifier's second round) that the card
and its modal row resolve one brief to ONE landing: a blocked top whose child worked later in a second turn, and a
completed top holding a valid citation; a handoff row carries no landing of its own. SYNTHETIC fixtures only; a
private synthetic sid."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
from romp_load import load_source
km = load_source("romp_kernel_anche2e", os.path.join(BIN, "romp-kernel"))
jd = km.jd

NOW = 1_788_300_000
T0 = NOW - 3600
SID = "f11e0002-1111-4222-8333-000000000002"    # private synthetic sid, never the shared placeholder
PEER = "f11e0003-1111-4222-8333-000000000003"
WRAP = ("Four questions before I go on. Should the history budget follow the device or the setting? "
        "Which client do the tests target? Do we keep the old exporter? Who owns the glossary file?")
WRAP2 = ("Picking this up in the child step. Should the history budget follow the device or the setting? "
         "The exporter now keeps both clients while the tests run against the old one, and the glossary file is mine.")
BRIEF = "Should the history budget follow the device or the setting? The session asks four things it cannot decide alone."
SUMMARY = "The history budget follows the device now. Both clients stay while the tests run against the old one."


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def tline(t, uuid, parent):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tu-" + uuid, "name": "Bash",
                                                          "input": {"command": "true"}}],
                        "stop_reason": "tool_use"}}


def aline(t, text, uuid, parent):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


def node(nid, text, parent=None, t=T0, **kw):
    d = {"id": nid, "text": text, "parentId": parent, "nodeComplete": False, "blocked": False, "cleared": False,
         "trail": [], "t": t, "mt": t, "log": []}
    d.update(kw)
    return d


class TheBriefClickEndToEnd(unittest.TestCase):
    G1 = SID + ":g1"
    G2 = SID + ":g2"

    def setUp(self):
        km._downtime[:] = []
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"
        cdir.mkdir()
        proj = td / "projects"
        import re as _re
        pdir = proj / _re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        # turn one, two segments: the typed opener and a shell call, then a typed prompt absorbed mid-turn and the
        # wrap-up that carries the four questions, thirteen minutes after the call; turn two, twenty minutes later:
        # the child step's own reply, carrying the same opening sentence
        recs = [uline(T0, "land the history gaps change", "u1"),
                tline(T0 + 60, "a1", "u1"),
                uline(T0 + 120, "keep going", "u2", "a1"),
                aline(T0 + 840, WRAP, "t9", "u2"),
                uline(T0 + 1200, "now the child step", "u3", "t9"),
                aline(T0 + 1260, WRAP2, "t20", "u3")]
        self.tpath = pdir / (SID + ".jsonl")
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        names = td / "names"
        names.mkdir()
        (names / SID).write_text("web\t%s\t#abcdef\n" % str(cdir))
        (names / PEER).write_text("api\t%s\t#abcdef\n" % str(cdir))
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km._live_map, km._GLOBAL_CLAUDE_MD, jd.gist_llm)
        jd.gist_llm = lambda p: ""
        km._autonudge_cache.clear()
        km._GLOBAL_CLAUDE_MD = td / "no-global-claude.md"
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        jd.STATE = td
        km.NAMES = names
        km._live_map = lambda: {SID: {"state": "idle", "since": NOW - 100, "model": "", "effort": "",
                                     "context": None, "compactPct": None, "color": None}}
        jd.GOALDIR.mkdir(parents=True, exist_ok=True)
        s = jd.parsed_session(SID, [str(self.tpath)], NOW)
        st0 = {"rompUuid": SID, "nodes": {}, "placements": {}, "status": {}}
        self.segs = [sg["id"] for turn in s["turns"] for sg in jd._segs(turn, st0)]
        km._SUMMARY_ANCHOR_MEMO.clear()

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km._live_map, km._GLOBAL_CLAUDE_MD, jd.gist_llm) = self.saved
        km._autonudge_cache.clear()
        self.td.cleanup()

    def _write(self, nodes, status):
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": len(nodes), "lastNode": self.G1, "nodes": nodes, "placements": {}, "status": status}))

    def _blocked_top(self, trail):
        # the block lands AFTER the last user turn (u3 at T0 + 1200), so no plain reply follows it and the card
        # stays in needs-input, where the client shows the brief and wires its click; a block with a later plain
        # turn sits in the re-judging window, where no distiller line renders (the verifier's fourth round)
        return node(self.G1, "Land the history gaps change", trail=trail, mt=T0 + 1300, blocked=True,
                    blockWhy="four questions the user must answer", blockSummary=BRIEF, summaryAnchor=None,
                    briefedMt=T0 + 1300,
                    log=[{"ev_t": T0 + 1300, "src": "closer", "kind": "block", "at": T0 + 1300,
                          "why": "four questions the user must answer"}])

    def _card(self, g=None):
        km._parse(str(self.tpath), SID, NOW)           # warm the kernel parse cache: the anchor tiers read it
        return next(a for a in km.build_feed(NOW)["asks"] if a.get("itemId") == (g or self.G1))

    def _row(self, card, nid):
        return next(r for r in card["tree"] if r["id"] == nid)

    def test_the_turns_hold_three_segments_the_first_a_tool_call_only(self):
        self.assertEqual(len(self.segs), 3, self.segs)

    def test_the_brief_click_lands_on_the_wrap_up_text_atom_not_the_tool_call(self):
        self._write({self.G1: self._blocked_top([self.segs[0]])}, {self.G1: "blocked"})   # the newest trail segment: the tool call only
        card = self._card()
        self.assertEqual((card["column"], card["distillState"]), ("needs_input", "blocked"), "a displaying state: the brief shows and its click is wired")
        self.assertEqual(card["summaryAnchorUuid"], "t9", "the text atom that carries the brief's opening sentence (the base: a1, the tool call)")
        self.assertEqual(card["summaryAnchorQuote"], "Should the history budget follow the device or the setting?")
        row = self._row(card, self.G1)
        self.assertEqual((row["summaryAnchorUuid"], row["summaryAnchorQuote"]), ("t9", card["summaryAnchorQuote"]),
                         "the modal's row carries the same landing")
        self.assertEqual(row["anchorUuid"], "a1", "the work anchor stays the segment's landable atom for the mark and time zones")

    def test_a_body_read_that_raises_leaves_build_feed_whole(self):
        self._write({self.G1: self._blocked_top([self.segs[0]])}, {self.G1: "blocked"})
        real = km.jd._atom_text
        def boom(a):                                   # the wrap-up's body cannot be read; every other read is real
            if a.get("uuid") == "t9":
                raise km.em.LazyBodyRead("no record at the offset")
            return real(a)
        km.jd._atom_text = boom
        try:
            try:
                card = self._card()
            except Exception as ex:
                self.fail("build_feed raised on one unreadable body, so no session got a feed this cycle: %r" % (ex,))
        finally:
            km.jd._atom_text = real
        self.assertEqual(card["summaryAnchorUuid"], "t9", "no quote could be located, so the tier falls to the substantive text atom, never a raise")
        self.assertIsNone(card["summaryAnchorQuote"])
        self.assertGreaterEqual(km._SUMMARY_ANCHOR_STATS["fault"], 1)

    def test_a_blocked_top_with_a_child_that_worked_later_lands_the_card_and_its_row_in_one_place(self):
        # the top's own trail names the tool-only first segment; its child worked later, in the second turn, whose
        # reply carries the brief's opening sentence too: the card reads the subtree (t20) and so must the row
        top = self._blocked_top([self.segs[0]])
        child = node(self.G2, "The child step", parent=self.G1, t=T0 + 1200, mt=T0 + 1260, trail=[self.segs[2]])
        self._write({self.G1: top, self.G2: child}, {self.G1: "blocked"})
        card = self._card()
        row = self._row(card, self.G1)
        self.assertEqual(card["summaryAnchorUuid"], "t20", "the newest subtree segment's text atom carrying the opening sentence")
        self.assertEqual(row["summaryAnchorUuid"], card["summaryAnchorUuid"], "one brief, one landing, whichever surface is clicked")
        self.assertEqual(row["summaryAnchorQuote"], card["summaryAnchorQuote"])

    def test_a_completed_top_with_a_citation_lands_the_card_and_its_row_on_the_same_recap(self):
        # a completed top pins its summary click to the newest substantive tail across the subtree (the completion
        # recap); the citation on t9 stands valid, and the row must follow the card's pin rather than the citation
        top = node(self.G1, "Land the history gaps change", trail=[self.segs[1]], mt=T0 + 1300, nodeComplete=True,
                   summary=SUMMARY, summaryAnchor="t9", summaryQuote="Should the history budget follow the device or the setting?",
                   distilledMt=NOW - 10, settledAt=T0 + 1300,
                   log=[{"ev_t": T0 + 1290, "src": "closer", "kind": "done", "at": T0 + 1290, "why": "landed"}])
        child = node(self.G2, "The child step", parent=self.G1, t=T0 + 1200, mt=T0 + 1260, trail=[self.segs[2]], nodeComplete=True,
                     log=[{"ev_t": T0 + 1270, "src": "closer", "kind": "done", "at": T0 + 1270, "why": "done"}])
        self._write({self.G1: top, self.G2: child}, {self.G1: "completed"})
        card = self._card()
        row = self._row(card, self.G1)
        self.assertEqual(card["column"], "completed")
        self.assertEqual(card["summaryAnchorUuid"], "t20", "the completed pin: the newest substantive tail across the subtree")
        self.assertEqual(row["summaryAnchorUuid"], card["summaryAnchorUuid"], "the row follows the card's pin, not the citation")

    def test_a_working_top_floored_to_needs_input_lands_on_the_brief_it_shows(self):
        # a live permission prompt floors a WORKING top to needs-input: the card shows its decision brief (the
        # distill state is blocked), so the click must land on the brief's sentence (t20), never the takeaway's (t9)
        # that the column's rule would name (the verifier's third round)
        km._live_map = lambda: {SID: {"state": "permission", "since": NOW - 100, "model": "", "effort": "",
                                     "context": None, "compactPct": None, "color": None}}
        top = node(self.G1, "Land the history gaps change", trail=[self.segs[0]], mt=T0 + 900,
                   summary="Four questions before I go on. The earlier completion left these standing.",   # its sentence: t9 only
                   summaryAnchor=None, distilledMt=T0 + 700,
                   blockSummary=BRIEF, briefedMt=T0 + 900)                                              # its sentence: t9 and t20
        child = node(self.G2, "The child step", parent=self.G1, t=T0 + 1200, mt=T0 + 1260, trail=[self.segs[2]])
        self._write({self.G1: top, self.G2: child}, {self.G1: "working"})
        card = self._card()
        self.assertEqual(card["column"], "needs_input", "the live prompt floors the working top")
        self.assertEqual(card["distillState"], "blocked", "…and the card shows the decision brief")
        self.assertEqual(card["summaryAnchorUuid"], "t20", "the landing follows the shown brief (its sentence in the newest segment), not the takeaway")
        self.assertEqual(card["summaryAnchorQuote"], "Should the history budget follow the device or the setting?",
                         "the located span is the SHOWN brief's sentence; resolved from the takeaway's line (the column's rule) no span is found")

    def test_a_faulted_build_is_served_but_not_memoized_so_the_next_build_recovers(self):
        self._write({self.G1: self._blocked_top([self.segs[0]])}, {self.G1: "blocked"})
        real = km.jd._atom_text
        def boom(a):
            if a.get("uuid") == "t9":
                raise km.em.LazyBodyRead("no record at the offset")
            return real(a)
        km.jd._atom_text = boom
        try:
            first = self._card()
        finally:
            km.jd._atom_text = real
        self.assertEqual((first["summaryAnchorUuid"], first["summaryAnchorQuote"]), ("t9", None), "the faulted build lands without the span")
        second = self._card()                          # nothing on disk moved: only a non-memoized entry re-derives
        self.assertEqual(second["summaryAnchorQuote"], "Should the history budget follow the device or the setting?",
                         "the next build recovers the span: the faulted entry was not memoized")

    def test_the_landing_is_resolved_once_per_node_and_line_within_a_build(self):
        self._write({self.G1: self._blocked_top([self.segs[0]])}, {self.G1: "blocked"})
        real, calls = km._summary_text_anchor, []
        def counting(*a, **kw):
            calls.append(a[2] if len(a) > 2 else kw.get("memo_key"))
            return real(*a, **kw)
        km._summary_text_anchor = counting
        try:
            card = self._card()
        finally:
            km._summary_text_anchor = real
        row = self._row(card, self.G1)
        self.assertEqual(row["summaryAnchorUuid"], card["summaryAnchorUuid"], "the card and its row carry the landing")
        self.assertEqual(len(calls), 1, "…from ONE resolve of the tier for the node and its line, not one per surface")

    def test_a_stall_floored_card_lands_on_the_brief_it_shows_not_the_tool_call(self):
        # romp's nudge gate holds an idle working top (a stall record, no block verdict): the column floors to
        # needs-input (the user's 2026-08-13 rule) while the distill state stays None, so the client shows the
        # staller's brief through the column fallback; the kernel must resolve the landing from that same brief,
        # else the newest tool-only segment hands the click the tool call (the defect this change opens with)
        real = km._stalled_goals
        km._stalled_goals = lambda: {self.G1: {"why": "the reviver is not retiring", "since": NOW - 100}}
        try:
            top = node(self.G1, "Land the history gaps change", trail=[self.segs[0]], mt=T0 + 900,
                       blockSummary=BRIEF, summaryAnchor=None, briefedMt=T0 + 900)
            self._write({self.G1: top}, {self.G1: "working"})
            card = self._card()
        finally:
            km._stalled_goals = real
        self.assertEqual((card["column"], card["distillState"]), ("needs_input", None), "the stall floor: needs-input with no distill state")
        self.assertEqual(card["summaryAnchorUuid"], "t9", "the brief the client shows lands on its own sentence (the base: a1, the tool call)")
        self.assertEqual(card["summaryAnchorQuote"], "Should the history budget follow the device or the setting?")

    def test_a_handoff_row_carries_no_landing_of_its_own(self):
        # a handoff row's session is the peer's; an anchor resolved in this session's parse would be a foreign atom
        # to the peer's chat, so the row ships none and its line falls to the work anchor's click
        top = self._blocked_top([self.segs[0]])
        tracker = node(self.G2, "delegated to api", parent=self.G1, t=T0 + 1200, mt=T0 + 1260, trail=[self.segs[2]],
                       handoff={"peer": PEER, "goalId": PEER + ":g3"}, blockSummary=BRIEF)
        own = node(SID + ":g3", "The local step", parent=self.G1, t=T0 + 900, mt=T0 + 900, trail=[self.segs[1]])   # a top whose
        self._write({self.G1: top, self.G2: tracker, SID + ":g3": own}, {self.G1: "blocked"})   # only leaf is a handoff renders no card
        card = self._card()
        row = self._row(card, self.G2)
        self.assertEqual(row["kind"], "handoff")
        self.assertIsNone(row["summaryAnchorUuid"], "a handoff row's brief line falls to goWork")
        self.assertIsNone(row["summaryAnchorQuote"])


if __name__ == "__main__":
    unittest.main()
