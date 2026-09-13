"""A card's brief or summary click lands on the text that carries it, never on a tool call (T388).

The manager's finding, 2026-09-12: a blocked card whose brief had no validated citation sent its summary click to
the node's WORK anchor, the newest trail segment's first assistant atom, a shell call inside a collapsed tool group,
while the quoted questions were the same turn's last text atom thirteen minutes later; four landings filed
pointer-exact on the wrong atom. The kernel now resolves such a click to the assistant text atom of that segment's
turn that carries the line's opening sentence (else the turn's last text atom), never a tool_use or thinking atom,
and ships the located span as the click's quote. Synthetic atoms only."""
import os
import tempfile
import unittest

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
from romp_load import load_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
em = load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))

T0 = 1781300000


def tool(uuid, t):
    return {"type": "assistant", "uuid": uuid, "t": t, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu-" + uuid, "name": "Bash", "input": {"command": "true"}}]}}


def think(uuid, t):
    return {"type": "assistant", "uuid": uuid, "t": t, "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "hm"}]}}


def text(uuid, t, body):
    return {"type": "assistant", "uuid": uuid, "t": t, "message": {"role": "assistant", "content": [{"type": "text", "text": body}]}}


QUESTIONS = ("Four questions before I go on. Should the history budget follow the device or the setting? "
             "Which client do the tests target? Do we keep the old exporter? Who owns the glossary file?")
BRIEF = "Should the history budget follow the device or the setting? The session asks four things it cannot decide alone."


class TheTextAtom(unittest.TestCase):
    def test_a_segment_of_tool_calls_lands_on_the_turns_text_atom_not_the_first_tool_call(self):
        seg = [tool("a1", T0), tool("a2", T0 + 1), tool("a3", T0 + 2), tool("a4", T0 + 3)]   # the newest trail segment: shell calls only
        turn = {"t": T0, "end": T0 + 800, "atoms": seg + [text("t9", T0 + 780, QUESTIONS)]}    # the turn's last text atom, later
        self.assertEqual(km._seg_jump(seg), "a1", "the WORK anchor: the first landable atom, a tool call (the collapsed group)")
        u, q = km._summary_text_anchor((turn, seg), BRIEF)
        self.assertEqual(u, "t9", "the brief click lands on the text atom that carries its opening sentence")
        self.assertEqual(q, "Should the history budget follow the device or the setting?", "the located span rides as the quote")

    def test_the_atom_carrying_the_opening_sentence_wins_over_a_later_text_atom(self):
        seg = [tool("a1", T0), text("t5", T0 + 10, QUESTIONS), text("t6", T0 + 20, "Done for now.")]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        u, q = km._summary_text_anchor((turn, seg), BRIEF)
        self.assertEqual((u, q), ("t5", "Should the history budget follow the device or the setting?"))

    def test_no_sentence_match_lands_on_the_newest_substantive_text_atom_never_a_stub(self):
        # a paraphrased brief (the common case): the analysis before the stub, not the stub, the walk's own rule
        analysis = "The exporter keeps both clients while the history budget follows the device, and the tests target the old one " * 2
        seg = [tool("a1", T0), text("t5", T0 + 10, analysis), text("t6", T0 + 20, "Done for now.")]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        self.assertEqual(km._summary_text_anchor((turn, seg), "Decide the retry policy for the exporter."), ("t5", None))
        # the stub newest with the analysis older, the same answer
        seg2 = [tool("a1", T0), text("t5", T0 + 10, analysis), text("t6", T0 + 20, "Done for now.")]
        turn2 = {"t": T0, "end": T0 + 30, "atoms": seg2}
        self.assertEqual(km._summary_text_anchor((turn2, seg2), "The paraphrase names no sentence of the reply.")[0], "t5")

    def test_only_stubs_answer_nothing_unless_the_call_is_the_last_resort(self):
        seg = [tool("a1", T0), text("t5", T0 + 10, "first note"), text("t6", T0 + 20, "second note")]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        self.assertEqual(km._summary_text_anchor((turn, seg), "Decide the retry policy for the exporter."), (None, None),
                         "no quote and no substantive atom: the chain falls through to the walk")
        self.assertEqual(km._summary_text_anchor((turn, seg), "Decide the retry policy for the exporter.", stub_ok=True), ("t6", None),
                         "the last resort takes the last text atom, still ahead of a tool group")

    def test_a_segment_without_text_falls_to_the_turns_newest_substantive_text_atom(self):
        seg = [tool("a1", T0), think("th", T0 + 1)]
        wrap = "The wrap-up here is the reply the user reads, long enough to count as prose by the walk's own floor."
        turn = {"t": T0, "end": T0 + 60, "atoms": seg + [text("t7", T0 + 50, wrap), text("t8", T0 + 55, "ok")]}
        self.assertEqual(km._summary_text_anchor((turn, seg), "Nothing that matches."), ("t7", None))

    def test_a_body_that_cannot_be_read_is_skipped_and_counted_never_raised(self):
        seg = [tool("a1", T0), text("t5", T0 + 10, QUESTIONS), text("t6", T0 + 20, "Done for now.")]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        real = km.jd._atom_text
        def boom(a):                                   # the body read raises, as a LazyBodyRead or a rotated file would
            raise km.em.LazyBodyRead("no record at the offset")
        km.jd._atom_text = boom
        km._SUMMARY_ANCHOR_MEMO.clear()
        before = km._SUMMARY_ANCHOR_STATS.get("fault", 0)
        try:
            try:
                out = km._summary_text_anchor((turn, seg), BRIEF, memo_key=("11111111-2222-3333-4444-555555555555", "gf", "kf"))
            except Exception as e:
                self.fail("the tier raised on an unreadable body instead of skipping it: %r" % (e,))
        finally:
            km.jd._atom_text = real
        self.assertIn("fault", km._SUMMARY_ANCHOR_STATS, "the fault counter exists beside hit, miss and evict")
        self.assertEqual(len(km._SUMMARY_ANCHOR_MEMO), 0, "a faulted search is not memoized: a transient fault never pins a degraded landing")
        self.assertEqual(km._SUMMARY_ANCHOR_STATS["fault"], before + 2, "every unreadable candidate is counted (two text atoms)")
        self.assertEqual(out, ("t5", None), "…and the tier goes on without a body: the substantive fallback, never a raise")

    def test_thinking_and_tool_calls_alone_resolve_to_nothing(self):
        seg = [tool("a1", T0), think("th", T0 + 1)]
        turn = {"t": T0, "end": T0 + 5, "atoms": seg}
        self.assertEqual(km._summary_text_anchor((turn, seg), BRIEF), (None, None))
        self.assertEqual(km._summary_text_anchor(None, BRIEF), (None, None))

    def test_an_api_error_and_the_null_settle_are_never_the_landing(self):
        err = dict(text("e1", T0 + 5, "API Error: overloaded, please retry the request in a while and check the status page for the outage"), isApiError=True)
        reply = "The real reply the user reads, long enough to pass the walk's prose floor, names the outcome of the work."
        seg = [tool("a1", T0), err, text("t2", T0 + 6, reply)]
        turn = {"t": T0, "end": T0 + 10, "atoms": seg}
        self.assertEqual(km._summary_text_anchor((turn, seg), "Nothing matches."), ("t2", None))
        self.assertEqual(km._summary_text_anchor((turn, [tool("a1", T0), err]), "Nothing matches.", stub_ok=True), ("t2", None),
                         "the API error is never the landing, even as the last resort")

    def test_the_opening_sentence_drops_a_list_number_and_stops_at_the_first_sentence_end(self):
        self.assertEqual(km._opening_sentence("1. Decide the retry policy. Then the rest."), "Decide the retry policy.")
        self.assertEqual(km._opening_sentence("\n\nShort? Yes it is."), "Short? Yes it is.", "a sentence end inside the first twelve characters is not the cut")
        self.assertEqual(km._opening_sentence(""), "")

    def test_the_memo_answers_a_repeat_without_reading_again(self):
        seg = [tool("a1", T0), text("t5", T0 + 10, QUESTIONS)]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        km._SUMMARY_ANCHOR_MEMO.clear()
        first = km._summary_text_anchor((turn, seg), BRIEF, memo_key=("11111111-2222-3333-4444-555555555555", "g1", "k1"))
        seg[1]["message"]["content"][0]["text"] = "changed under the memo"      # the same key: the memo answers, no re-read
        again = km._summary_text_anchor((turn, seg), BRIEF, memo_key=("11111111-2222-3333-4444-555555555555", "g1", "k1"))
        self.assertEqual(first, again)
        self.assertEqual(first[0], "t5")


# The states the verifier executed plus the one producible pair they left out, one row each: (name, distillState, column, completed, blocked). The webview
# test ui/webview/distiller-line.test.ts carries the SAME rows for distillInputs; TheLineRuleTable pins both sides.
LINE_RULE_TABLE = [
    ("stall floor", None, "needs_input", False, True),
    ("permission floor", "blocked", "needs_input", False, True),
    ("real block in recheck", "blocked", "working", False, False),
    ("done confirming", None, "working", False, False),
    ("completed", "completed", "completed", True, False),
    ("plain working", None, "working", False, False),
    ("completed under a needs-input column", "completed", "needs_input", True, False),   # the producible pair the six named states left untabled
]


class TheLineRuleTable(unittest.TestCase):
    def test_the_kernel_mirrors_the_clients_distill_inputs_over_the_six_states(self):
        nd = {"summary": "the takeaway", "blockSummary": "the brief"}
        for name, state, column, completed, blocked in LINE_RULE_TABLE:
            with self.subTest(name):
                got_completed, line = km._landing_inputs(state, column, nd)
                self.assertEqual(got_completed, completed, name)
                self.assertEqual(line, "the brief" if blocked else ("the takeaway" if completed else None), name)

    def test_the_webview_test_carries_the_same_table_and_executes_it(self):
        ts = open(os.path.join(ROOT, "ui", "webview", "distiller-line.test.ts"), encoding="utf-8").read()
        table = ts.index("const LINE_RULE_TABLE:")
        for name, state, column, completed, blocked in LINE_RULE_TABLE:
            row = '["%s", %s, "%s", %s, %s]' % (name, "null" if state is None else '"%s"' % state, column,
                                                str(completed).lower(), str(blocked).lower())
            self.assertIn(row, ts, "the webview pins the same row: %s" % row)
        # PRESENT is not EXECUTED (the manager's read of the merge): the rows must be driven through distillInputs by a
        # test that stands beside them, or a deleted test block with the array kept would leave this pin green
        head = 'test("distillInputs over the states the kernel\'s landing rule mirrors", () => {'
        self.assertIn(head, ts, "the webview TEST that drives the table exists (present rows are not executed rows)")
        call = ts.index(head)
        self.assertGreater(call, table, "the test stands beside the table it drives")
        block = ts[call:]
        self.assertIn("for (const [name, state, column, completed, blocked] of LINE_RULE_TABLE)", block, "the test walks the table")
        self.assertIn("assert.deepEqual(distillInputs(state, column), { completed, blocked }, name);", block, "…and asserts each row through distillInputs")


class TheWiring(unittest.TestCase):
    def test_the_card_chain_tries_the_text_atom_before_the_latest_prose_walk_and_the_tree_rows_carry_it(self):
        src = open(os.path.join(ROOT, "kernel", "kernel.py"), encoding="utf-8").read()
        land = src.index("    def _brief_landing(nid, completed, line):")
        flat = src.index("    def flatten(nid, out, ancestor_done=False, boundary=None):")
        self.assertLess(land, flat, "one landing function, defined before the flatten, serves the card and every row")
        body = src[land:flat]
        tier = body.index("u, q = _summary_text_anchor(seg_turn.get(sk), line, memo_key=(fsid, nid, sk))")
        walk = body.index("best = None                                  # (substantive, seg_t): prefer substantive, then latest")
        stub = body.index("stub_ok=True)")
        work = body.index("wu = seg_uuid.get(_seg_key(s))")
        self.assertLess(tier, walk, "the text-atom tier runs before the latest-prose walk")
        self.assertLess(walk, stub, "…the stub only after the walk")
        self.assertLess(stub, work, "…and the work anchor last")
        self.assertIn("_completed, _line = _landing_inputs(distill_state, column, nodes[nid])", src,
                      "the card's line and completed bit come from distillInputs' terms: the state AND the column")
        self.assertIn("_sa_u, _sa_q = _brief_landing(nid, _completed, _line)", src, "the card takes the one resolve")
        self.assertIn('_ncompleted, _nline = _landing_inputs("completed" if st == "done" else "blocked" if st == "question" else None, "", nd)', src,
                      "…and each row's from its own shown status, through the same function, with no column term")
        self.assertIn("_nsa_u, _nsa_q = (None, None) if (_ho_sid or not _nline) else _brief_landing(nid, _ncompleted, _nline)", src)
        self.assertIn('"summaryAnchorUuid": _nsa_u,', src, "every tree row carries the brief line's own landing")
        self.assertIn('"summaryAnchorQuote": _nsa_q,', src)
        self.assertIn("else (_sa_q or None)),", src, "the card's quote falls to the text-atom tier's span")
        ts = open(os.path.join(ROOT, "ui", "webview", "feed.ts"), encoding="utf-8").read()
        self.assertIn("if (!repeat && node.summaryAnchorUuid) {", ts, "the modal's brief line prefers the brief's own landing")
        self.assertIn("anchorUuid: su, quote: sq", ts, "…and sends its span as the click's quote")
        self.assertIn("ss = navSidOf(it, node);", ts, "the click names the ROW's session (a serving-folded worker row), never the card's")
        self.assertIn("focusEcho(ss); vscodeApi?.postMessage({ type: \"showOnTimeline\", itemId: node.id || it.turnId, sid: ss,", ts)
        self.assertIn("and not _summary_outrun(nd, [nodes[x].get(\"trail\") for x in sub], seg_best):", src,
                      "the cited tier applies the outrun rule over the whole subtree, once, for the card and the row alike")
        self.assertIn("_land_memo[mk] = (u, (q or None))", src, "one resolve per node, bit and line within a build")
        self.assertIn("got = _sub_memo[root] = acc", src, "one subtree walk per root within a build")
        self.assertIn('if not (entry or {}).get("faults"):', src, "a derivation that met a body-read fault is not memoized as an entry")
        self.assertIn("summaryAnchorUuid?: string | null;                            // the brief/summary line's own landing", ts)


class TheMemoIsBoundedByBytes(unittest.TestCase):
    """The summary-anchor memo follows the user's caches rule (2026-09-11): a byte bound as a fraction of machine memory
    with an environment override, oldest-first eviction that sheds only the deficit, counters under /perf; never a
    count literal with a wholesale clear (the manager's fold on T388)."""
    def setUp(self):
        self._bound = km.SUMMARY_ANCHOR_MEMO_BYTES
        km._SUMMARY_ANCHOR_MEMO.clear()
        for k in ("hit", "miss", "evict", "bytes"):
            km._SUMMARY_ANCHOR_STATS[k] = 0

    def tearDown(self):
        km.SUMMARY_ANCHOR_MEMO_BYTES = self._bound
        km._SUMMARY_ANCHOR_MEMO.clear()

    def test_the_bound_is_a_fraction_of_memory_with_an_override_and_no_count_literal(self):
        from unittest import mock
        self.assertEqual(km._summary_anchor_memo_bound(), km._mem_total_bytes() // 256)
        with mock.patch.dict(os.environ, {"ROMP_SUMMARY_ANCHOR_MEMO_BYTES": "8192"}):
            self.assertEqual(km._summary_anchor_memo_bound(), 8192)
        with mock.patch.dict(os.environ, {"ROMP_SUMMARY_ANCHOR_MEMO_BYTES": "lots"}):
            self.assertEqual(km._summary_anchor_memo_bound(), km._mem_total_bytes() // 256, "an unreadable override falls back to the fraction")
        self.assertEqual(km.SUMMARY_ANCHOR_MEMO_BYTES, km._summary_anchor_memo_bound(), "the module constant IS the fraction, no literal")
        self.assertFalse(hasattr(km, "_SUMMARY_ANCHOR_MEMO_MAX"), "no count cap")
        src = open(os.path.join(ROOT, "kernel", "kernel.py"), encoding="utf-8").read()
        self.assertNotIn("_SUMMARY_ANCHOR_MEMO.clear()", src, "no wholesale clear on the cap")
        self.assertIn('("summaryAnchor", _summary_anchor_memo_report)', src, "reported under /perf beside the other memos")

    def test_a_hit_survives_an_eviction_of_a_colder_entry_and_the_counters_say_so(self):
        seg = [tool("a1", T0), text("t5", T0 + 10, QUESTIONS)]
        turn = {"t": T0, "end": T0 + 30, "atoms": seg}
        sid = "11111111-2222-3333-4444-555555555555"
        km.SUMMARY_ANCHOR_MEMO_BYTES = 1      # any second entry is over the bound: the put sheds the coldest, keeps the newest
        km._summary_text_anchor((turn, seg), BRIEF, memo_key=(sid, "g1", "k1"))      # A: a miss, stored
        km._summary_text_anchor((turn, seg), BRIEF, memo_key=(sid, "g2", "k2"))      # B: a miss, stored; A is the colder
        self.assertEqual(km._SUMMARY_ANCHOR_STATS["evict"], 1, "over the bound: one eviction, the oldest")
        self.assertEqual(len(km._SUMMARY_ANCHOR_MEMO), 1)
        self.assertIn((sid, "g2", "k2", hash(BRIEF), T0 + 30, False), km._SUMMARY_ANCHOR_MEMO, "the newest survives, the coldest went")
        km.SUMMARY_ANCHOR_MEMO_BYTES = 10 ** 6
        km._summary_text_anchor((turn, seg), BRIEF, memo_key=(sid, "g3", "k3"))      # C stored beside B
        before = km._SUMMARY_ANCHOR_STATS["hit"]
        km._summary_text_anchor((turn, seg), BRIEF, memo_key=(sid, "g2", "k2"))      # a HIT on B: B is now the newest
        self.assertEqual(km._SUMMARY_ANCHOR_STATS["hit"], before + 1)
        km.SUMMARY_ANCHOR_MEMO_BYTES = 1
        km._summary_text_anchor((turn, seg), BRIEF, memo_key=(sid, "g4", "k4"))      # D: sheds the coldest, C, never the hit B
        keys = list(km._SUMMARY_ANCHOR_MEMO)
        self.assertNotIn((sid, "g3", "k3", hash(BRIEF), T0 + 30, False), keys, "the colder entry went")
        self.assertIn((sid, "g4", "k4", hash(BRIEF), T0 + 30, False), keys)
        rep = km._summary_anchor_memo_report()
        for k in ("entries", "bytes", "bound", "hit", "miss", "evict", "fault"):
            self.assertIn(k, rep)
        self.assertEqual(rep["entries"], len(km._SUMMARY_ANCHOR_MEMO))
        self.assertEqual(rep["bound"], km.SUMMARY_ANCHOR_MEMO_BYTES)
        self.assertGreater(rep["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
