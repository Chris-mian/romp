#!/usr/bin/env python3
"""T323 stage 4b (2026-09-11): the chat build's RENDER FLOOR and PAGE renderer. A restored parse's pre-cut turns are
lazy (stage 4a); the chat build renders from the turn holding the assembly cut (the floor) and the older history is
rendered on demand, a page of turns at a time, for a proto-2 client's loadOlder / loadAround / loadNewer. Pinned here:
the pages from turn 0 to the floor, concatenated with the floor'd list, equal the WHOLE build's events byte for byte,
at every page size (so at every page boundary), with notes interleaved between the turns; a page hydrates its own
turns only and the floor'd build hydrates the tail's; the floor drops to 0 while a proto-1 client is connected and
climbs back when it leaves (the fold entry rebuilt, the prefix released); every event's uuid is unique within a
list. The proto-2 base never ends on one of the kernel's transient live-tail keys (an input echo, the command chip;
2026-09-19): the landing that replaces such a key is a delta after the record before it, and a full frame sent to a
client holding a base is counted by reason and filed as a client-diag row. Synthetic transcripts only (the stage 4a served fixture's builder and the golden compaction scenarios)."""
import contextlib
import io
import json
from unittest import mock
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from romp_load import load_source
HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_t323s4b", os.path.join(BIN, "romp-kernel"))
jd, em = km.jd, km.em
sys.path.insert(0, HERE)
import test_event_model_golden as G                                  # noqa: E402  the synthetic scenario builders
from test_asm_checkpoint_served import transcript                    # noqa: E402  the 4a served fixture's transcript builder

SID = "aaaaaaaa-4444-4222-8333-444444444444"
NOW = 1781200000


def _last_uuid(recs):
    return next((r["uuid"] for r in reversed(recs) if r.get("uuid")), None)


def compacting_variant(recs, tag):
    """A golden scenario's records followed by a compaction and two more turns (the stage 4a harness's shape, copied here:
    importing that module re-executes the event model into this process and resets its registries)."""
    t1 = max((em.parse_z(r.get("timestamp")) or 0) for r in recs if r.get("timestamp")) + 600
    b, sm = "b_%s" % tag, "s_%s" % tag
    more = [G.compact_line(t1, b, _last_uuid(recs)),
            G.compact_summary_line(t1 + 1, sm, b),
            G.uline(t1 + 10, "after the compaction, what remains?", "u_%s_1" % tag, sm),
            G.aline(t1 + 20, "the cap and the retry budget remain", "a_%s_1" % tag, "u_%s_1" % tag, stop="end_turn"),
            G.uline(t1 + 30, "then close them out", "u_%s_2" % tag, "a_%s_1" % tag),
            G.aline(t1 + 40, "closing both", "a_%s_2" % tag, "u_%s_2" % tag, stop="end_turn")]
    return list(recs) + more


def _strip(events):
    return json.loads(json.dumps(events, default=lambda o: "<unserializable>"))


class Harness(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.saved_state = jd.STATE
        jd._rebind_state(self.td / "state")
        for d in ("states", "goals", "sdk", "checkpoints"):
            (jd.STATE / d).mkdir(parents=True, exist_ok=True)
        em.set_checkpoint_dir(lambda: jd.STATE / "checkpoints")
        self.proj = self.td / "proj"; self.proj.mkdir()
        self.leaf = str(self.proj / (SID + ".jsonl"))
        self.rows = [{"sid": SID, "name": "web", "path": self.leaf, "mtime": NOW, "anchor": SID}]
        self.saved = (km._sessions, km._live_map)
        km._sessions = lambda now, **kw: list(self.rows)
        km._live_map = lambda: {}
        self.fresh()

    def tearDown(self):
        km._sessions, km._live_map = self.saved
        km._live_scope.chat_floor0 = None
        em.set_checkpoint_dir(None)
        jd._rebind_state(self.saved_state)
        shutil.rmtree(self.td, ignore_errors=True)

    def fresh(self):
        """A kernel restart's in-memory side."""
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.clear()
        with em._ASM_LOCK:
            em._ASM_CACHE.clear()
        em._TRAILING_CACHE.clear()
        with em._ASM_CKPT_LOCK:
            em._HYDRATED.clear(); em._HYDRATED_BYTES[0] = 0
        em._LAZY_FILES.clear()
        with em._READ_BYTES_LOCK:
            em._READ_BYTES.clear()
        em._ASM_CKPT_STATS.update(written=0, restored=0, fallbacks={}, skipped={}, hydratedBytes=0, hydratedAtoms=0, hydratedBy={})
        with km._chat_fold_lock:
            km._chat_fold.clear()
        for name in ("_PARSE_CACHE",):                                    # the one parse store (stage 2): a restart empties it
            getattr(jd, name).clear()
        km._parse_mode.clear()
        km._built_chat.clear() if hasattr(km, "_built_chat") else None
        km._prev_chat_events.clear()
        km._RENDER_FLOOR.clear()
        with km._page_lock:
            km._PAGE_CACHE.clear(); km._PAGE_STATS.update(hits=0, misses=0, evictions=0, pages=0, bytes=0, renderMs=0.0)
        km._live_scope.chat_floor0 = None
        with em._MAT_LOCK:                                                # the lazy index's LRU and counters (stage 4c)
            em._MAT_LRU.clear()
            em._ASM_INDEX_STATS.update(materialized=0, materializedBy={}, resident=0, evictions=0, restoredTurns=0)

    def write(self, recs):
        Path(self.leaf).write_text("".join(json.dumps(r) + "\n" for r in recs))

    def whole(self):
        """The fully hydrated build (a proto-1 client's), from a fresh process with no document."""
        self.fresh(); saved = em._CKPT_DIR_FN; em._CKPT_DIR_FN = None
        try:
            m = km.build_session(SID, NOW, {}, floor=0)
        finally:
            em._CKPT_DIR_FN = saved
        self.head_cards = _strip(m.get("headCards") or [])
        return _strip(m["events"])[len(self.head_cards):]                # the transcript's events: the head cards ride top-level

    def document(self):
        self.fresh()
        km.build_session(SID, NOW, {}, floor=0)                          # a whole parse, then its document
        self.assertTrue(em.asm_checkpoint_write(self.leaf, SID, tree=km._parse(self.leaf, SID, NOW)), em.asm_checkpoint_stats())   # the
        #                                                                  store's tree gives the turns section (stage 4c)

    def restored(self):
        """A fresh process with the document: the floor'd build (the pusher's, no proto-1 client)."""
        self.fresh(); modes = []
        km._live_scope.chat_floor0 = False
        try:
            m = km.build_session(SID, NOW, {})
        finally:
            km._live_scope.chat_floor0 = None
        return m

    def pages(self, floor, size):
        out = []
        for lo in range(0, floor, size):
            out += km._chat_history_page(SID, lo, min(lo + size, floor), NOW)
        return _strip(out)


class PagesEqualTheWhole(Harness):
    def test_pages_and_the_floored_list_equal_the_whole_build_at_every_page_size(self):
        recs = transcript(NOW - 86400, turns=120, compact_every=25)
        self.write(recs)
        whole = self.whole()
        self.assertGreater(len(whole), 200)
        self.document()
        m = self.restored()
        floor = m["floor"]
        self.assertGreater(floor, 0, "a restored parse renders from the cut")
        tail = _strip(m["events"])
        self.assertLess(len(tail), len(whole))
        self.assertEqual(tail, whole[len(whole) - len(tail):], "the floor'd list is the whole build's tail")
        for size in (1, 3, 7, 16, 64):
            with self.subTest(page_turns=size):
                self.assertEqual(self.pages(floor, size) + tail, whole, "pages of %d turns plus the tail equal the whole" % size)
        self.assertGreater(km._PAGE_STATS["misses"], 0)

    def _with_notes(self, turns=120, compact_every=25):
        """The fixture with a model stamp on every reply and a states log of romp's notes between the turns: a retry
        recovered, a give-up, an effort change, a command gesture and two orphan replies (one the transcript kept: deduped;
        one it did not: rendered), several stamped one second before a page boundary's first atom."""
        recs = transcript(NOW - 86400, turns=turns, compact_every=compact_every)
        for r in recs:
            if r.get("type") == "assistant":
                r["message"]["model"] = "claude-test-1"
        self.write(recs)
        t_of = {}                                                          # turn index (typed prompts in order) -> its t
        k = 0
        for r in recs:
            if r.get("type") == "user" and not r.get("isCompactSummary") and r.get("promptSource") == "typed":
                t_of[k] = em.parse_z(r["timestamp"]); k += 1
        kept_text = next(r for r in recs if r.get("type") == "assistant")["message"]["content"][0]["text"]
        # a page boundary of the PARSE's turns (each compact boundary record is its own turn, so prompt 96 is not turn 96):
        # the first multiple of 16 whose turn starts a clean second after the turn before ends
        pturns = km._parse(self.leaf, SID, NOW)["turns"]
        self.boundary = next(b for b in (96, 80, 112, 64) if (pturns[b - 1].get("end") or 0) < int(pturns[b]["t"]) - 1)
        rows = [{"t": int(t_of[3]) + 30, "retriesRecovered": 2},
                {"t": int(t_of[16]) - 1, "retriesGaveUp": 5, "errorKind": "overloaded"},     # a page boundary (16-turn pages)
                {"t": int(t_of[32]) - 1, "effortApplied": "high"},
                {"t": int(t_of[48]) - 1, "cmdGesture": "/compact"},
                {"t": int(t_of[64]) - 1, "orphanReply": {"uuid": "orph-1", "text": "a reply the transcript never kept"}},
                {"t": int(t_of[7]) + 5, "orphanReply": {"uuid": "orph-2", "text": kept_text}},
                {"t": int(t_of[80]) - 1, "effortApplied": "low"},
                {"t": int(pturns[self.boundary]["t"]) - 1, "orphanReply": {"uuid": "orph-3", "text": kept_text}}]   # RENDERED, at a page boundary
        (jd.STATE / "states" / (SID + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in rows))
        return recs

    def test_pages_with_notes_between_the_turns_equal_the_whole_and_the_walks_cross_them(self):
        """Review find N: the fixtures carried no notes, so the cursors, the note ordinals and the orphan dedup ran on empty
        inputs. Notes at page boundaries are a page's first event; the uuid walks resolve them (review find B)."""
        self._with_notes()
        whole = self.whole()
        kinds = [e.get("kind") for e in whole]
        for k in ("retried", "retryGaveUp", "effortApplied", "cmdGesture"):
            self.assertIn(k, kinds, k)
        # the parse synthesizes an orphan reply's atom from the same row when the transcript lacks the text
        # (event_model.synthesize_orphans), so orph-1's note is deduped against that atom, which sits at the note's time;
        # orph-2's text is turn 0's reply, far from the note's time, so under the near-window rule the note renders
        orphaned = [e for e in whole if e.get("orphaned")]
        self.assertEqual([e.get("orphanOf") for e in orphaned], ["orph-2", "orph-3"], "near texts dedup; a copy far in time does not")
        self.assertRegex(orphaned[1]["uuid"], r"^orphan:\d+:\d+$", "a rendered note's key: orphan:<t>:<n>, the record uuid on orphanOf")
        self.assertTrue(any(e.get("kind") == "assistant" and not e.get("orphaned") and (e.get("md") or "").startswith("a reply the transcript never kept") for e in whole))
        self.document()
        m = self.restored()
        floor = m["floor"]; tail = _strip(m["events"])
        for size in (1, 3, 7, 16, 64):
            with self.subTest(page_turns=size):
                self.assertEqual(self.pages(floor, size) + tail, whole, "notes interleaved the same way in pages of %d turns" % size)
        # the uuid walks cross the notes: older to the head from the tail, then around a note and forward to the tail
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        resident = list(sent[-1]["events"]); oldest = resident[0]["uuid"]
        for _ in range(100):
            r = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": oldest}, NOW)
            self.assertNotIn("missing", r, "a page's first event is a note here: it resolves by its second")
            resident = r["events"] + resident
            if not r["more"]:
                break
            oldest = resident[0].get("key") or resident[0]["uuid"]
        self.assertEqual(_strip(resident), self.head_cards + whole)
        note = next(e for e in whole if e.get("kind") == "retryGaveUp")
        w = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": note["uuid"]}, NOW)
        self.assertNotIn("missing", w); self.assertIn(note["uuid"], [e["uuid"] for e in w["events"]])
        # the rendered orphan note at the boundary of the 96th turn: a page's FIRST event; a window lands on it by its key,
        # the pages around it equal the whole, and a walk older from it crosses the boundary (round 2, item 6)
        onote = orphaned[1]
        ow = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": onote["uuid"]}, NOW)
        self.assertNotIn("missing", ow); self.assertIn(onote["uuid"], [e["uuid"] for e in ow["events"]])
        wu = [e["uuid"] for e in whole]
        full_index = wu.index(onote["uuid"])
        b16 = self.boundary
        self.assertEqual(self.pages(m["floor"], 16)[full_index]["uuid"], onote["uuid"])
        page_at = km._chat_history_page(SID, b16, b16 + 16, NOW)
        self.assertEqual(page_at[0]["uuid"], onote["uuid"], "the note is the boundary page's FIRST event")
        before = km._chat_history_page(SID, b16 - 16, b16, NOW)
        self.assertFalse(before[-1].get("orphaned"), "the page before it ends clean")
        turns_b = km._parse(self.leaf, SID, NOW)["turns"]
        first_atom = next(a["uuid"] for a in turns_b[b16]["atoms"] if a.get("uuid"))
        ob0 = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": first_atom}, NOW)
        self.assertNotIn(onote["uuid"], [e["uuid"] for e in ob0["events"]], "older than the boundary turn's first atom excludes the note")
        ob = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": onote["uuid"]}, NOW)
        self.assertNotIn("missing", ob); self.assertTrue(ob["events"], "older than the note: the pages before its boundary")
        older = [e["uuid"] for e in ob["events"]]
        self.assertEqual(older[len(self.head_cards):] + [onote["uuid"]], wu[:full_index + 1], "one contiguous run across the boundary, from the head")
        self.assertFalse(ob["more"])
        held = list(w["events"])
        # the rest of the transcript below the window, asked by TURN SPAN in one loadTurns (T386 stage 2: the walk retired)
        self.assertEqual(len(w["span"]), 2)
        n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": w["span"][1], "hi": len(turns_b)}, NOW)
        self.assertNotIn("missing", n)
        held = held + n["events"]
        full = [e["uuid"] for e in self.head_cards + whole]
        self.assertEqual([e["uuid"] for e in held], full[full.index(held[0]["uuid"]):])

    def test_a_page_hydrates_its_own_turns_and_the_floored_build_the_tails(self):
        recs = transcript(NOW - 86400, turns=120, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["hydratedAtoms"], 0, "the floor'd build reads no pre-cut body: %s" % st["hydratedBy"])
        floor = m["floor"]
        page = km._chat_history_page(SID, 0, 5, NOW)
        st = em.asm_checkpoint_stats()
        atoms_in = sum(len(t["atoms"]) for t in em.parse_session(self.leaf, rompuuid=SID, candidate_files=[self.leaf], states=None, postal_log=[], now=NOW)["turns"][0:5])
        self.assertGreater(st["hydratedAtoms"], 0)
        self.assertLessEqual(st["hydratedAtoms"], atoms_in + km._PAGE_FILL_TURNS * 4, "the page's turns and its fill turns, no more: %s" % st["hydratedBy"])
        self.assertLessEqual(set(st["hydratedBy"]), {"build_session", "_atom_md"}, "the page's reshape and its own text set: %s" % st["hydratedBy"])
        self.assertGreater(len(page), 0)
        self.assertLess(floor, len(em.parse_session(self.leaf, rompuuid=SID, candidate_files=[self.leaf], states=None, postal_log=[], now=NOW)["turns"]))

    def test_every_golden_compaction_scenario_pages_equal_its_whole(self):
        for name in sorted(G.SINGLE_FILE):                                 # every single-file scenario made to compact (stage 4a)
            with self.subTest(scenario=name):
                records, _ = G.SINGLE_FILE[name]
                self.write(compacting_variant(records(), name[:6]) if name not in ("compaction_atom", "compaction_broken_stitch", "manual_compact_detached") else records())
                whole = self.whole()
                self.document()
                m = self.restored()
                floor = m["floor"]
                tail = _strip(m["events"])
                for size in (1, 2, 16):
                    self.assertEqual(self.pages(floor, size) + tail, whole, "%s at %d turns per page" % (name, size))


def restart_seam_records():
    """A machine-cut seam in the pre-cut history: a prompt, a reply cut by a kernel restart (the CLI's stop record, its null
    settle, romp's resume notice), then the resumed reply; more turns; then a compaction and two turns after it, so the
    seam lies in the pages. The notice is what stamps the marker's cause and drops the settle (_stamp_interrupt_causes),
    and it lands turns after the marker: a page ending at the marker's turn reads it through its fill turns."""
    t0 = NOW - 86400
    recs, parent = [], None
    for i in range(12):
        t = t0 + i * 120
        recs.append(G.uline(t, "step %d, please" % i, "u_seam_%d" % i, parent))
        recs.append(G.aline(t + 30, "step %d done" % i, "a_seam_%d" % i, "u_seam_%d" % i, stop="end_turn"))
        parent = "a_seam_%d" % i
    t = t0 + 12 * 120
    recs.append(G.uline(t, "now the long step", "u_cut", parent))
    recs.append(G.aline(t + 20, "starting the long step", "a_cut", "u_cut", stop="end_turn"))
    recs.append(G.uline(t + 40, "[Request interrupted by user]", "u_stop", "a_cut", ps=None))
    recs.append(G.aline(t + 41, "No response requested.", "a_settle", "u_stop", stop="end_turn"))
    recs.append(G.uline(t + 60, "[romp] The romp kernel " + km.INTR_RESTART_SIG + " this session's in-flight turn; pick it up where it "
                        "stopped.<!-- romp-injected --><!-- romp-system -->", "u_notice", "a_settle", ps=None))
    recs.append(G.aline(t + 90, "resuming the long step", "a_resume", "u_notice", stop="end_turn"))
    parent = "a_resume"
    for i in range(12, 20):
        t = t0 + (i + 1) * 120
        recs.append(G.uline(t, "step %d, please" % i, "u_seam_%d" % i, parent))
        recs.append(G.aline(t + 30, "step %d done" % i, "a_seam_%d" % i, "u_seam_%d" % i, stop="end_turn"))
        parent = "a_seam_%d" % i
    return compacting_variant(recs, "seamcut")   # a tag whose minted uuids (u_seamcut_1, ...) cannot collide with the seam's own
    #                                                u_seam_N: a collision rebinds a pre-cut record and makes the resolved graph
    #                                                cyclic, which the writer now refuses (T402 follow-up)


class RestartSeam(Harness):
    def test_a_machine_cut_seam_in_the_pages_keeps_its_cause_and_no_page_repeats_an_event(self):
        """Round 2, item 5: the settle a restart seam drops shifted every index after it, so a page kept its fill turn's first
        event and the next page repeated it; and no golden carried an interrupt marker."""
        self.write(restart_seam_records())
        whole = self.whole()
        marker = [e for e in whole if e.get("interruptMarker")]
        self.assertEqual(len(marker), 1); self.assertEqual(marker[0].get("interruptCause"), "restart", "the notice names the cause")
        self.assertEqual([e for e in whole if e.get("interruptSettle")], [], "a machine cut shows no settle line")
        self.assertIn("a_settle", marker[0].get("settleUuids") or [], "the dropped settle's uuid still answers on the seam")
        self.document()
        m = self.restored()
        floor = m["floor"]; self.assertGreater(floor, 0)
        tail = _strip(m["events"])
        for size in (1, 2, 16):
            with self.subTest(page_turns=size):
                paged = self.pages(floor, size)
                self.assertEqual(paged + tail, whole, "the seam through pages of %d turns" % size)
                keys = [e.get("key") or e["uuid"] for e in paged + tail]
                self.assertEqual(len(keys), len(set(keys)), "no event twice on the wire")


def _fake_self(path):
    """A connect handler whose peer speaks through the stubbed _ws_recv (tests/test_chat_skeleton_reconnect.py's shape)."""
    class FakeSelf:
        headers = {"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
        rfile = io.BytesIO(); wfile = io.BytesIO()
        connection = type("FakeSock", (), {"sendall": lambda self, b: None, "shutdown": lambda self, how: None})()
        close_connection = False
        def send_response(self, *a): pass
        def send_header(self, *a): pass
        def end_headers(self): pass
    FakeSelf.path = path
    for name in ("_dispatch_ws", "_push_one"):                            # the handler's own arms, on the fake
        setattr(FakeSelf, name, getattr(km.Handler, name))
    return FakeSelf()


class RealArm(Harness):
    """The socket handler's own arms driven with frames (the ready, the history requests, needFull): the base the kernel
    keeps for the client is the real arm's, not a re-implementation's (round 3, D)."""

    def _drive(self, path, next_frame, alive_rows=True):
        got, sent = [], []
        real = (km._register_ws_client, km._ws_recv, km._mk_ws_send, km._alive_sessions)
        km._register_ws_client = lambda c: (got.append(c), km._clients.append(c))
        km._ws_recv = lambda rfile: next_frame(sent)
        km._mk_ws_send = lambda q, sock, client: (lambda s: sent.append(json.loads(s)))
        if alive_rows:
            km._alive_sessions = lambda now, tmux: list(self.rows)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                km.Handler._ws(_fake_self(path))
        finally:
            km._register_ws_client, km._ws_recv, km._mk_ws_send, km._alive_sessions = real
            with km._clients_lock:
                for c in got:
                    if c in km._clients:
                        km._clients.remove(c)
        self.assertEqual(len(got), 1)
        return got[0], sent

    @staticmethod
    def _frame(msg):
        return (0x1, json.dumps(msg).encode("utf-8"), True)

    def test_the_registration_reads_the_redials_protocol(self):
        """Round 2 item 4 / round 3 D: the dial term's proto lands on the client at the handshake."""
        for path, want in (("/ws?app=chat&delta=1&iid=p1&active=%s&reconnect=1&proto=2" % SID, 2),
                           ("/ws?app=chat&delta=1&iid=p1&active=%s&reconnect=1&proto=1" % SID, 1),
                           ("/ws?app=chat&delta=1&iid=p1&active=%s&reconnect=1" % SID, None),
                           ("/ws?app=chat&delta=1&iid=p1&active=%s&proto=2" % SID, None)):   # not a redial: the ready says
            c, _ = self._drive(path, lambda sent: (0x8, b"", True), alive_rows=False)
            self.assertEqual(c.get("proto"), want, path)
            self.assertIsInstance(c.get("t0"), (int, float), "the registration is stamped for the ready wait")

    def test_a_deep_link_then_a_span_to_the_tail_grows_the_tail_run_and_every_tail_change_is_a_delta(self):
        """T386 stage 2: a deep link (a window with its turn span), then the gap between the window and the tail asked as one
        span (loadTurns), whose reply moves the kernel's base to the filled span's first event since it reaches the tail's first
        turn; a deep link into the filled part changes nothing; a tail change reaches the client as a chatTail. No client is ever
        detached and no re-attach exists."""
        recs = transcript(NOW - 86400, turns=600, compact_every=150)      # ~300 events after the cut: longer than the wire tail
        self.write(recs)
        whole = self.whole()
        self.write(_head_past_the_last_compaction(recs)); self.document()   # documented before the tail landed (stage one b cuts at
        self.write(recs)                                                     #  the last settled turn, so a whole-file document has a
        m = self.restored()                                                  #  short tail)
        evs = m["events"]
        deep = whole[10]["uuid"]
        run = []                                                          # what the page holds, as the frames build it
        state = {"step": "ready", "fulls": 0}

        def next_frame(sent):
            fresh = sent[state.get("seen", 0):]
            state["seen"] = len(sent)

            def newest(kind):
                return next((f for f in reversed(fresh) if f.get("type") == kind and f.get("id") == SID), None)
            if state["step"] == "ready":
                state["step"] = "window"; return self._frame({"type": "ready", "proto": 2})
            if state["step"] == "window":
                f = newest("session")
                if f is not None:
                    state["fulls"] += 1; state["tailLo"] = f["tailLo"]; state["step"] = "turns"
                    self.assertIsInstance(f["tailLo"], int, "the full frame names the tail run's first turn")
                    return self._frame({"type": "loadAround", "id": SID, "uuid": deep})
            elif state["step"] == "turns":
                w = newest("chatWindow")
                if w is not None:
                    run[:] = list(w["events"]); state["window"] = w
                    self.assertEqual(w["span"][0], 0, "the window reached the head"); self.assertTrue(w["moreAfter"])
                    self.assertLess(w["span"][1], state["tailLo"], "…and ends before the tail run")
                    state["step"] = "filled"
                    return self._frame({"type": "loadTurns", "id": SID, "lo": w["span"][1], "hi": state["tailLo"]})
            elif state["step"] == "filled":
                n = newest("chatTurns")
                if n is not None:
                    run.extend(n["events"]); state["turns"] = n; state["step"] = "walked"
                    self.assertEqual(n["span"], [state["window"]["span"][1], state["tailLo"]])
                    inside = run[len(run) // 3]["uuid"]                 # into the filled part, far from the tail
                    return self._frame({"type": "loadAround", "id": SID, "uuid": inside})
            elif state["step"] == "walked":
                w = newest("chatWindow")
                if w is not None:
                    state["window2"] = w; state["step"] = "done"
            return (0x8, b"", True)
        c, sent = self._drive("/ws?app=chat&delta=1&iid=p2&active=%s" % SID, next_frame)
        self.assertEqual(state["step"], "done", "the sequence ran to its end: %s" % state)
        self.assertEqual(state["fulls"], 1, "one full frame: no re-attach frame exists")
        base = c["echat"][SID]
        self.assertEqual(set(base), {"first", "last"}, "the tail-only base: no detached flag")
        filled_first = state["turns"]["events"][0]
        self.assertEqual(base["first"], filled_first.get("key") or filled_first["uuid"], "the base's first moved to the filled span's first event: it reached the tail")
        w2 = state["window2"]
        self.assertNotIn("connected", w2); self.assertEqual(len(w2["span"]), 2)
        n = len(sent)
        km._send_chat_locked(c, m, None, len(evs) - 1, False)             # the next tail change
        self.assertEqual(len(sent), n + 1); self.assertEqual(sent[-1]["type"], "chatTail", "a delta, not silence")

    def test_a_window_reaching_the_head_carries_the_head_cards_and_a_span_to_the_tail_keys_the_base_on_an_event(self):
        """T386 stage 2 (from round 3, B): the head cards ride a window whose span starts at turn 0; a window that does not reach
        the tail leaves the base alone; the span up to the tail's first turn moves the base's first to its first EVENT (a key
        that places in a turn), and the next tail change is a delta."""
        recs = transcript(NOW - 86400, turns=200, compact_every=25)
        self.write(recs)
        whole = self.whole()
        self.document()
        m = self.restored()
        self.assertTrue(self.head_cards, "the fixture has head cards")
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        f = sent[-1]; tail_lo = f["tailLo"]
        self.assertIsInstance(tail_lo, int); self.assertGreater(tail_lo, 0)
        w = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": whole[0]["uuid"]}, NOW, base=c["echat"][SID])
        self.assertFalse(w["moreBefore"]); self.assertEqual(w["events"][0]["uuid"], self.head_cards[0]["uuid"], "the head cards ride first")
        self.assertEqual(w["span"][0], 0)
        self.assertIsNone(w["_base"], "a window short of the tail leaves the base alone")
        n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": w["span"][1], "hi": tail_lo}, NOW, base=c["echat"][SID])
        self.assertEqual(n["span"], [w["span"][1], tail_lo]); self.assertFalse(n["head"])
        self.assertEqual(n["_base"]["first"], n["events"][0].get("key") or n["events"][0]["uuid"], "the base's first is the span's first EVENT")
        c["echat"][SID] = {"first": n["_base"]["first"], "last": c["echat"][SID]["last"]}
        held = list(w["events"]) + n["events"] + list(f["events"])
        self.assertEqual(_strip(held), self.head_cards + whole, "the window, the span and the tail make the whole, the head cards first")
        n0 = len(sent)
        km._send_chat_locked(c, m, None, len(m["events"]) - 1, False)
        self.assertEqual(sent[-1]["type"], "chatTail"); self.assertEqual(len(sent), n0 + 1)
        w2 = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": whole[4]["uuid"]}, NOW, base=c["echat"][SID])
        self.assertNotIn("connected", w2); self.assertEqual(w2["span"][0], 0)


class NotesAndFloor(Harness):
    def _sealed_note(self):
        """A rendered orphan note in the (soon sealed) last turn of a 200-turn transcript, its text turn 0's reply: the parse
        keeps the text far away, so the near-window rule renders the note; then a typed prompt opens turn 200, which seals
        turn 199 with the note into the fold's prefix. Returns (records, kept_text, the open prompt's uuid)."""
        recs = transcript(NOW - 86400, turns=200, compact_every=1000)     # no compaction: one fold over the whole list
        self.write(recs)
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        kept_text = next(r for r in recs if r.get("type") == "assistant")["message"]["content"][0]["text"]
        rows = [{"t": int(turns[199]["t"]) - 1, "orphanReply": {"uuid": "orph-g", "text": kept_text}}]
        (jd.STATE / "states" / (SID + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in rows))
        last = next(r for r in reversed(recs) if r.get("uuid"))
        t_last = em.parse_z(last["timestamp"])
        recs2 = recs + [G.uline(t_last + 60, "one more, please", "u_g200", last["uuid"])]
        self.write(recs2)
        m = km.build_session(SID, NOW, {}, floor=0)                       # turn 199 sealed, the note in it
        self.assertTrue(any(e.get("orphanOf") == "orph-g" for e in m["events"]), "the note rendered")
        fe = km._chat_fold_get(SID)
        self.assertIsNotNone(fe)
        self.assertTrue(any(isinstance(x, (list, tuple)) and x[1] == kept_text for x in fe["orphan_texts"]), "sealed as (t, text)")
        return recs2, kept_text, t_last

    def test_a_reply_landing_in_the_notes_window_retires_it_and_one_far_from_it_does_not(self):
        recs2, kept_text, t_last = self._sealed_note()
        # the far case: the open turn's reply says something else, then a later turn repeats the salvaged text
        far = recs2 + [G.aline(t_last + 90, "quite another reply", "a_g200", "u_g200", stop="end_turn"),
                       G.uline(t_last + 120, "and again", "u_g201", "a_g200"),
                       G.aline(t_last + 150, kept_text, "a_g201", "u_g201", stop="end_turn")]
        self.write(far)
        km.build_session(SID, NOW + 1, {}, floor=0)
        info = km._chat_fold_last_info()
        self.assertNotEqual(info.get("why"), "orphan", "a match two turns past the note's window is not its reply: %s" % info)
        self.assertEqual(info.get("fold"), 1, "the fold stands")
        # the near case: the reply landing in the turn right after the note's (its window) retires it
        self.fresh(); (jd.STATE / "states" / (SID + ".jsonl")).unlink()
        recs2, kept_text, t_last = self._sealed_note()
        near = recs2 + [G.aline(t_last + 90, kept_text, "a_g200", "u_g200", stop="end_turn")]
        self.write(near)
        km.build_session(SID, NOW + 1, {}, floor=0)
        self.assertEqual(km._chat_fold_last_info().get("why"), "orphan", "a new reply in the note's window retires it: a refold")


class KeyCounts(unittest.TestCase):
    """Round 2 item 13, executed: the sealed part is keyed before its key counts are memoized, else a uuid-less event in a
    just-sealed turn is missing from the next build's seen map and a later event of its kind gets the same key."""

    def test_counts_taken_after_the_pass_carry_the_uuid_less_events_key(self):
        prefix = [{"kind": "user", "uuid": "u0"}]
        sealed = [{"kind": "assistant", "uuid": "a0"}, {"kind": "todo"}]          # the overlay card has no uuid: the pass names it
        tail = [{"kind": "todo"}]
        events = prefix + sealed + tail
        p, b = len(prefix), len(prefix) + len(sealed)
        stale = km._key_counts(events[:b])                                       # the pre-fix order: counts before the pass
        self.assertNotIn("todo", stale)
        km._uniq_event_uuids(events[p:b], events[:p])                            # the commit's order now
        counts = km._key_counts(events[:b])
        self.assertEqual(counts.get("todo"), 1, "the sealed card's key is in the seen map")
        km._uniq_event_uuids(events[b:], events[:b], seen=counts)
        self.assertEqual(events[b:][0].get("key"), "todo#2", "the tail's card is a second of its kind")
        stale_tail = [{"kind": "todo"}]
        km._uniq_event_uuids(stale_tail, [], seen=stale)
        self.assertIsNone(stale_tail[0].get("key"), "with the stale counts the same key would have been minted twice")
        src = open(os.path.join(BIN, "romp-kernel")).read()
        i = src.index('"keyCounts": _key_counts(events[:_b])')
        self.assertIn("_uniq_event_uuids(events[_pref_len:_b], events[:_pref_len],", src[i - 1200:i], "the pass precedes the commit")


class ZeroMaterialization(Harness):
    """T323 stage 4c: the chat's first open of a restored session builds no pre-cut atom. The floor'd build reads the turns
    before the floor through their own scalars (_cursors_before, _turn_index_of_events, _fold_tasks, the cut) and hydrates
    the tail's atoms only; a page then builds exactly its own turns' atoms."""

    def test_the_floored_build_builds_no_pre_cut_atom_and_a_page_builds_its_own_turns(self):
        recs = transcript(NOW - 86400, turns=120, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()                                               # fresh() zeroed the index's counters
        self.assertGreater(m["floor"], 0)
        tree = km._parse(self.leaf, SID, NOW)
        self.assertTrue(all(isinstance(tree["turns"][i], em.PreTurn) for i in range(m["floor"])), "the pre-cut turns are the index's")
        st = em.asm_index_stats()
        self.assertEqual(st["materialized"], 0, "the first open built no pre-cut atom: %s" % st["materializedBy"])
        page = km._chat_history_page(SID, 16, 32, NOW)
        self.assertTrue(page)
        st = em.asm_index_stats()
        built = sum(len(tree["turns"][i]["uuids"]) for i in range(16, 32 + km._PAGE_FILL_TURNS))
        self.assertLessEqual(st["materialized"], built, "a page builds its turns and its fill turns, no more: %s" % st["materializedBy"])
        self.assertGreater(st["materialized"], 0)
        r = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": m["events"][0]["uuid"]}, NOW)
        self.assertTrue(r["events"])


class EchoPlacement(Harness):
    """Review low 3: a stale echo stamped in the pre-cut history goes into the first post-cut turn, never into a restored
    pre-cut turn (its atoms are the document's, its spans written, and a synthetic turn among them would move the floor)."""

    def test_an_echo_before_the_cut_joins_the_first_tail_turn_and_the_pre_turns_stand(self):
        recs = transcript(NOW - 86400, turns=60, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()
        tree = km._parse(self.leaf, SID, NOW)
        cut = tree["cutTurn"]; turns = tree["turns"]
        early = turns[3]["t"] + 1                                          # inside a pre-cut turn's window
        gap = turns[cut - 1]["end"] + 1 if turns[cut]["t"] - turns[cut - 1]["end"] > 2 else turns[2]["end"] + 1   # a gap among pre-turns
        echoes = [{"type": "user", "uuid": "echo-1", "session_id": SID, "t": early, "_echo_text": "a note sent yesterday", "message": {"role": "user", "content": "a note sent yesterday"}},
                  {"type": "user", "uuid": "echo-2", "session_id": SID, "t": gap, "_echo_text": "another", "message": {"role": "user", "content": "another"}},
                  {"type": "user", "uuid": "echo-0", "session_id": SID, "t": turns[0]["t"] - 60, "_echo_text": "before everything", "message": {"role": "user", "content": "before everything"}}]
        out, placed = km._place_stale_echoes(turns, echoes)
        self.assertEqual(len(out), len(turns), "no synthetic turn among the pre-cut turns")
        for i in range(cut):
            self.assertIs(out[i], turns[i], "a pre-cut turn is untouched")
        self.assertEqual({p[0] for p in placed}, {cut}, "both echoes joined the first post-cut turn")
        self.assertEqual(sorted(a["uuid"] for a in out[cut]["atoms"] if a.get("_echo_text")), ["echo-0", "echo-1", "echo-2"], "the one ahead of every turn too")
        self.assertEqual(em.asm_index_stats()["materialized"], 0, "…and no pre-cut atom was built for it")


class UniqueUuids(Harness):
    def test_every_event_carries_a_uuid_unique_within_the_list(self):
        recs = transcript(NOW - 86400, turns=60, compact_every=25)
        self.write(recs)
        whole = self.whole()
        uuids = [e.get("uuid") for e in whole]
        self.assertTrue(all(uuids), "every event carries a uuid")
        keys = [e.get("key") or e.get("uuid") for e in whole]
        self.assertEqual(len(keys), len(set(keys)), "the wire's keys are unique within the list")
        self.document(); m = self.restored()
        got = self.pages(m["floor"], 16) + _strip(m["events"])
        kk = [e.get("key") or e.get("uuid") for e in got]
        self.assertEqual(len(kk), len(set(kk)))
        # a record whose text and tool call are two events keeps its uuid on both (deep links land on the record) and
        # the second carries the key
        t0 = NOW - 7200
        recs = [G.uline(t0, "run it", "u1", None), G.aline(t0 + 10, "running", "a1", "u1", tools=("Bash",), stop="tool_use"),
                G.trline(t0 + 11, "tu_a1_0", "r1", "a1", content="ok"), G.aline(t0 + 20, "done", "a2", "r1", stop="end_turn")]
        self.write(recs)
        whole = self.whole()
        same = [e for e in whole if e.get("uuid") == "a1"]
        self.assertEqual(len(same), 2, [e.get("kind") for e in whole])
        self.assertEqual([e.get("key") for e in same], [None, "a1#2"])


class RenderFloor(Harness):
    def test_the_floor_outlives_the_hydration_of_every_pre_cut_atom(self):
        """The judges' first pass over a fresh store hydrates every pre-cut atom (their unit text); the lazy markers go
        with the bodies. The floor is the parse's cutTurn, recorded before that, so the next build still renders from
        the cut (a scan of the markers would have found none and dropped to turn 0: every proto-2 client re-based)."""
        recs = transcript(NOW - 86400, turns=120, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()
        cut = m["floor"]; self.assertGreater(cut, 0)
        tree = km._parse(self.leaf, SID, NOW)                            # the STORE's tree, the one build_session reads
        self.assertEqual(tree.get("cutTurn"), cut)
        em.hydrate(tree, SID)                                             # what the judges' first pass does, to that tree
        self.assertEqual(sum(1 for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None), 0, "no marker left")
        km._live_scope.chat_floor0 = False
        try:
            m2 = km.build_session(SID, NOW + 1, {})
        finally:
            km._live_scope.chat_floor0 = None
        self.assertEqual(m2["floor"], cut, "the floor stands after the hydration")
        self.assertEqual([e["uuid"] for e in m2["events"]], [e["uuid"] for e in m["events"]])
        saved = tree.pop("cutTurn")                                       # cutTurn is load-bearing: without it the markers, now gone,
        try:                                                              #  would put the floor at turn 0
            km._live_scope.chat_floor0 = False
            m3 = km.build_session(SID, NOW + 2, {})
        finally:
            km._live_scope.chat_floor0 = None; tree["cutTurn"] = saved
        self.assertEqual(m3["floor"], 0, "the parse's cutTurn is what holds the floor")


    def test_the_floor_drops_while_a_proto1_client_is_connected_and_climbs_back_when_it_leaves(self):
        recs = transcript(NOW - 86400, turns=90, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()
        cut = m["floor"]; self.assertGreater(cut, 0)
        km._live_scope.chat_floor0 = True                                  # a proto-1 client is connected
        try:
            m0 = km.build_session(SID, NOW, {})
        finally:
            km._live_scope.chat_floor0 = None
        self.assertEqual(m0["floor"], 0, "the whole transcript for the index client")
        self.assertGreater(len(m0["events"]), len(m["events"]))
        self.assertEqual(km._RENDER_FLOOR[SID], 0)
        self.assertEqual(km._chat_fold_last_info().get("why"), "floor", "the fold demoted on the floor moving")
        km._live_scope.chat_floor0 = False                                 # it left
        try:
            m1 = km.build_session(SID, NOW, {})
        finally:
            km._live_scope.chat_floor0 = None
        self.assertEqual(m1["floor"], cut, "the floor climbs back at the next build")
        self.assertEqual(_strip(m1["events"]), _strip(m["events"]))
        self.assertEqual(km._chat_fold_last_info().get("why"), "floor")
        fe = km._chat_fold_get(SID)
        self.assertIsNotNone(fe)
        self.assertEqual(fe["rf"], cut, "the fold entry holds the prefix from the floor: the turn-0 prefix is released")
        self.assertLess(len(fe["events"]), len(m0["events"]))


class FloorDecision(Harness):
    def test_which_clients_move_the_floor(self):
        """Round 2, item 4: a socket before its ready has no protocol and moves no floor; a redial carries the page's protocol
        on its dial term; a client stamped ready with none (an older shim's redial) is an index client."""
        f = km._chat_floor0_of
        self.assertFalse(f([]))
        self.assertFalse(f([{"proto": 2, "ready": True}]))
        self.assertFalse(f([{"proto": None, "ready": False}, {"proto": 2}]), "a socket whose ready has not arrived is not counted")
        self.assertTrue(f([{"proto": 1, "ready": True}]))
        self.assertTrue(f([{"proto": None, "ready": True}]), "ready with no protocol: an index client")
        self.assertTrue(f([{"proto": 2}, {"proto": 1}]))
        t = km._ws_clock()
        self.assertFalse(f([{"proto": None, "ready": False, "t0": t - 5}], now=t), "a socket five seconds old waits for its ready")
        self.assertTrue(f([{"proto": None, "ready": False, "t0": t - km.READY_WAIT_S - 1}], now=t),
                        "no protocol and no ready past the wait: an index client (a page whose ready was never answered)")
        # the follow-up after PR 1584, low 3: a socket the accept marked as not yet handshaken is served no chat frame, so it moves no
        # floor either, stamped ready by its redial's pop (a reconnect=1 dial with no proto term) or old past the wait
        self.assertFalse(f([{"handshake": False, "proto": None, "ready": True}]), "a never-handshaken socket stamped ready by its redial's pop moves no floor: it is served nothing")
        self.assertFalse(f([{"handshake": False, "proto": None, "ready": False, "t0": t - km.READY_WAIT_S - 1}], now=t), "…nor past the wait")
        self.assertTrue(f([{"handshake": False, "proto": None, "ready": True}, {"proto": 1, "ready": True}]), "an index client beside it still floors")
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn('_live_scope.chat_floor0 = _chat_floor0_of(_all_chat)', src)
        reg = src[src.index('            client["reconnect"] = True'):src.index('        _register_ws_client(client)')]
        self.assertIn('_rp = (q.get("proto") or [""])[0]', reg, "the redial's registration reads the protocol from its dial term")
        self.assertIn('client["proto"] = int(_rp)', reg)
        self.assertIn('?"&reconnect=1&proto="+readyProto:""', src, "the shim's dial term carries the protocol the bundle's ready declared")
        self.assertIn('if(m&&m.type==="ready"){bundleReady=true;readyProto=(m.proto===2?2:1);readyMsg=s;}', src)

    def test_a_connect_push_counts_every_connected_client_and_a_pre_ready_socket_moves_nothing(self):
        """Review find E, executed through _push: the decision reads km._clients, not the push's targets."""
        recs = transcript(NOW - 86400, turns=90, compact_every=25)
        self.write(recs)
        self.document()
        m = self.restored()
        cut = m["floor"]; self.assertGreater(cut, 0)
        saved_alive, saved_clients = km._alive_sessions, km._clients
        km._alive_sessions = lambda now, tmux: list(self.rows)
        try:
            c2, s2 = _client(proto=2); c2.update(app="chat", alive=True, ready=True, active=SID)
            c1, s1 = _client(proto=1); c1.update(app="chat", alive=True, ready=True)
            c0, s0 = _client(proto=None); c0.update(app="chat", alive=True, ready=False)   # a socket before its ready
            with km._clients_lock:
                km._clients = [c2, c0]
            km._push([c2], connect=True, live_map={})
            self.assertEqual(km._RENDER_FLOOR[SID], cut, "a proto-2 page and a pre-ready socket: the floor stands")
            f2 = next(x for x in s2 if x.get("type") == "session" and x.get("id") == SID)
            self.assertEqual(f2.get("proto"), 2)
            with km._clients_lock:
                km._clients = [c2, c1]                                    # an index client connects elsewhere
            km._push([c2], connect=False, live_map={})
            self.assertEqual(km._RENDER_FLOOR[SID], 0, "every connected client decides: the index client drops the floor")
            self.assertEqual(km._chat_fold_last_info().get("why"), "floor")
            with km._clients_lock:
                km._clients = [c2]
            km._push([c2], connect=False, live_map={})
            self.assertEqual(km._RENDER_FLOOR[SID], cut, "…and it climbs back when the index client leaves")
        finally:
            km._alive_sessions = saved_alive
            with km._clients_lock:
                km._clients = saved_clients


def _head_past_the_last_compaction(recs):
    """The records up to and including two turns after the last compaction boundary: a document written over them has its cut
    near that boundary, and the rest of `recs`, appended after, is the tail the restore reads (stage one b, 2026-09-15: the cut
    is the turn before the last settled turn, so a document written over the whole file would leave a tail of one turn)."""
    bi = max(i for i, r in enumerate(recs) if r.get("subtype") == "compact_boundary")
    users = [i for i, r in enumerate(recs) if i > bi and r.get("type") == "user" and not r.get("isCompactSummary")]
    end = users[2] if len(users) > 2 else len(recs)
    return recs[:end]


def _client(proto=2):
    sent = []
    return {"send": lambda s: sent.append(json.loads(s)), "sent": {}, "proto": proto, "echat": {}}, sent


class Proto2Wire(Harness):
    """The uuid-anchored send path and the history requests, over a restored session."""

    def _restored_tail(self):
        recs = transcript(NOW - 86400, turns=200, compact_every=25)     # ~400 events, the cut near turn 175
        self.write(recs)
        whole = self.whole()
        self.document()
        m = self.restored()
        return whole, m

    def test_a_first_send_is_the_tail_with_head_unknown_and_a_later_send_a_uuid_anchored_delta(self):
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        self.assertEqual(sent[-1]["type"], "session")
        f = sent[-1]
        self.assertEqual((f["proto"], f["headKnown"], f["headTotal"]), (2, False, None), "the head is not reached: no count")
        self.assertNotIn("headFrom", f)
        self.assertEqual(f["events"], m["events"][-km.WIRE_TAIL:])
        self.assertEqual((f["firstUuid"], f["lastUuid"]), (f["events"][0]["uuid"], f["events"][-1]["uuid"]))
        self.assertEqual(c["echat"][SID], {"first": f["firstUuid"], "last": f["lastUuid"]}, "the tail-only base (T386 stage 2)")
        self.assertIsInstance(f["tailLo"], int); self.assertGreater(f["tailLo"], 0, "the full frame names the tail run's first turn; the head is not reached")
        # an append: the list grows by two events, the diff finds the old length
        m2 = dict(m); m2["events"] = list(m["events"]) + [{"kind": "user", "md": "more", "uuid": "u_new"}, {"kind": "assistant", "md": "ok", "uuid": "a_new"}]
        km._send_chat_locked(c, m2, None, len(m["events"]), False)
        d = sent[-1]
        self.assertEqual(d["type"], "chatTail")
        self.assertEqual((d["afterUuid"], [e["uuid"] for e in d["events"]]), (f["lastUuid"], ["u_new", "a_new"]))
        self.assertEqual(c["echat"][SID]["last"], "a_new")
        # a change inside the held window: from the event two before the end
        m3 = dict(m2); evs3 = list(m2["events"]); evs3[-2] = dict(evs3[-2], md="edited"); m3["events"] = evs3
        km._send_chat_locked(c, m3, None, len(evs3) - 2, False)
        d = sent[-1]
        self.assertEqual((d["type"], d["afterUuid"], len(d["events"])), ("chatTail", evs3[-3]["uuid"], 2))
        # a change AT the client's first resident event (the floor'd list fits the tail whole: index 0): a full frame again
        km._send_chat_locked(c, m3, None, 0, False)
        self.assertEqual(sent[-1]["type"], "session")
        self.assertEqual(sent[-1]["firstUuid"], evs3[0]["uuid"])
        # a fork: the held uuids are gone from the new list
        m4 = dict(m); m4["events"] = [{"kind": "user", "md": "x", "uuid": "z1"}, {"kind": "assistant", "md": "y", "uuid": "z2"}]
        km._send_chat_locked(c, m4, None, 0, False)
        self.assertEqual((sent[-1]["type"], sent[-1]["headKnown"], sent[-1]["headTotal"]), ("session", False, None))

    def test_a_client_holding_pages_before_the_floor_still_gets_deltas(self):
        whole, m = self._restored_tail()
        c, sent = _client()
        c["echat"][SID] = {"first": whole[3]["uuid"], "last": m["events"][-1]["uuid"], "detached": False}   # pages walked to the head
        m2 = dict(m); m2["events"] = list(m["events"]) + [{"kind": "user", "md": "more", "uuid": "u_new2"}]
        km._send_chat_locked(c, m2, None, len(m["events"]), False)
        self.assertEqual((sent[-1]["type"], sent[-1]["afterUuid"], [e["uuid"] for e in sent[-1]["events"]]),
                         ("chatTail", m["events"][-1]["uuid"], ["u_new2"]), "a run that begins before the floor'd list is caught up from its last")

    def test_a_trailing_overlay_card_that_vanishes_does_not_break_the_base(self):
        whole, m = self._restored_tail()
        c, sent = _client()
        m1 = dict(m); m1["events"] = list(m["events"]) + [{"kind": "apiError", "uuid": "apiError", "text": "x", "status": 500}]
        km._send_chat_locked(c, m1, None, 0, False)
        self.assertEqual(c["echat"][SID]["last"], m["events"][-1]["uuid"], "the base ends on the last transcript event, not the notice")
        km._send_chat_locked(c, m1, None, len(m1["events"]), False)                  # nothing changed: an empty suffix
        self.assertEqual((sent[-1]["type"], sent[-1]["events"]), ("chatTail", []))
        m2 = dict(m); m2["events"] = list(m["events"]) + [{"kind": "user", "md": "next", "uuid": "u_next"}]   # the notice gone, a record appended
        km._send_chat_locked(c, m2, None, len(m["events"]), False)
        d = sent[-1]
        self.assertEqual((d["type"], d["afterUuid"], [e["uuid"] for e in d["events"]]), ("chatTail", m["events"][-1]["uuid"], ["u_next"]))

    # ── the kernel's transient live-tail keys at the tail (2026-09-19) ──
    # An SDK input echo ("echo:<hex>"), a Codex echo ("echo-<hex>") or the /model chip ("cmd:<t>:<name>") is an ordinary
    # {"kind": "user"} event of the built list, sorted after every atom of the last turn, and its key is in no later list
    # once the CLI's record (or the chip's cmdGesture note) lands: the record carries its own uuid, and the live atom
    # leaves the merge (_merge_live_atoms's `fresh` filter, its text in `hide`). A base whose `last` was such a key could
    # not be mapped by the next push, and the pusher sent a whole session frame to every caught-up client on every send
    # into an idle session. The lists here are hand-built on the restored tail, so the key vanishes because the next list
    # omits it, the way the landing build omits it; tests/test_queued_copy_identity.py drives the real road.
    ECHO = "echo:" + "a" * 32
    REC = {"kind": "user", "md": "please continue", "uuid": "11111111-2222-4333-8444-555555555501", "human": True}
    REPLY = {"kind": "assistant", "md": "on it", "uuid": "11111111-2222-4333-8444-555555555502"}

    def _with(self, m, extra):
        m1 = dict(m); m1["events"] = list(m["events"]) + list(extra)
        return m1

    def _frame(self, d):
        return (d["type"], d.get("afterUuid"), [e["uuid"] for e in d.get("events") or []]) if d["type"] == "chatTail" else (d["type"],)

    def _diag_rows(self):
        fp = jd.STATE / "client-diag.jsonl"
        rows = [json.loads(l) for l in fp.read_text().splitlines() if l.strip()] if fp.exists() else []
        return [r for r in rows if r.get("surface") == "kernel" and r.get("what") == "chatFull"]

    def _diag_reasons(self):
        return [r["data"]["reason"] for r in self._diag_rows()]

    def _echo_then_landing(self, echo_uuid):
        """A caught-up client; the echo appended as a delta; then the list with the CLI's record and a reply in the echo's
        place, sent with the pusher's own change_from (_chat_diff finds the echo's slot). Returns what the sends produced."""
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat(c, m, None, 0, False)               # the locked entry: the chatFull rows the counter test reads are filed
        last_rec = km._event_key(m["events"][-1])         # after its lock block, so a row test drives it, never _send_chat_locked
        echo = {"kind": "user", "md": "please continue", "uuid": echo_uuid, "human": True}
        m1 = self._with(m, [echo])
        km._send_chat(c, m1, None, len(m["events"]), False)
        d1, base1 = sent[-1], dict(c["echat"][SID])
        m2 = self._with(m, [self.REC, self.REPLY])
        cf = km._chat_diff(m1["events"], m2["events"])
        self.assertEqual(cf, len(m["events"]), "the pusher's diff finds the echo's slot")
        km._send_chat(c, m2, None, cf, False)
        return m, c, sent, last_rec, echo, d1, base1, sent[-1]

    def test_a_pending_input_echo_that_lands_does_not_break_the_base(self):
        m, c, sent, last_rec, echo, d1, base1, d2 = self._echo_then_landing(self.ECHO)
        self.assertEqual(self._frame(d1), ("chatTail", last_rec, [echo["uuid"]]), "the echo itself rides a delta")
        self.assertEqual(base1["last"], last_rec, "the base ends on the record before the echo, never on the echo")
        self.assertEqual(self._frame(d2), ("chatTail", last_rec, [self.REC["uuid"], self.REPLY["uuid"]]), "the landing rides the suffix")
        self.assertEqual(c["echat"][SID]["last"], self.REPLY["uuid"])
        # a status-only send while the echo is pending: the empty suffix is anchored on the echo, which the client holds
        c2, sent2 = _client()
        m1 = self._with(m, [echo])
        km._send_chat_locked(c2, m, None, 0, False)
        km._send_chat_locked(c2, m1, None, len(m["events"]), False)
        km._send_chat_locked(c2, m1, None, len(m1["events"]), False)
        self.assertEqual(self._frame(sent2[-1]), ("chatTail", echo["uuid"], []))
        self.assertEqual(c2["echat"][SID]["last"], last_rec)

    def test_a_codex_echo_that_lands_does_not_break_the_base(self):
        m, c, sent, last_rec, echo, d1, base1, d2 = self._echo_then_landing("echo-0123abcd")   # CodexBackend.send's form: "echo-" + 8 hex
        self.assertEqual(self._frame(d1), ("chatTail", last_rec, [echo["uuid"]]))
        self.assertEqual(base1["last"], last_rec, "the Codex form is a transient key too")
        self.assertEqual(self._frame(d2), ("chatTail", last_rec, [self.REC["uuid"], self.REPLY["uuid"]]))

    def test_a_dropped_echo_dismissed_is_an_empty_suffix_after_the_record(self):
        # a never-delivered echo (undelivered, echoT) the user dismissed with its cross (SdkBackend.dismiss_echo): the list
        # shrinks back to the record, and the delta is an empty suffix after it, not a full frame
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        last_rec = km._event_key(m["events"][-1])
        dropped = {"kind": "user", "md": "lost one", "uuid": self.ECHO, "human": True, "undelivered": True, "echoT": NOW - 30}
        m1 = self._with(m, [dropped])
        km._send_chat_locked(c, m1, None, len(m["events"]), False)
        self.assertEqual(c["echat"][SID]["last"], last_rec)
        cf = km._chat_diff(m1["events"], m["events"])
        self.assertEqual(cf, len(m["events"]))
        km._send_chat_locked(c, m, None, cf, False)
        self.assertEqual(self._frame(sent[-1]), ("chatTail", last_rec, []), "the dismissal: an empty suffix after the record")

    def test_the_command_chip_replaced_by_its_durable_note_rides_the_suffix(self):
        # _ack_cmd_chip's "cmd:<t>:<name>" chip is retired (prune_live's stale_cmd at the next human turn, or by text) for the
        # durable cmdGesture note "cmdg:<t>:<n>" build_session emits in its slot, a different key: the echo's road again
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        last_rec = km._event_key(m["events"][-1])
        chip = {"kind": "user", "md": "/model sonnet", "uuid": "cmd:%d:model" % (NOW - 20), "human": True}
        note = {"kind": "cmdGesture", "cmd": "/model sonnet", "uuid": "cmdg:%d:1" % (NOW - 20)}
        mc = self._with(m, [chip])
        km._send_chat_locked(c, mc, None, len(m["events"]), False)
        self.assertEqual(c["echat"][SID]["last"], last_rec, "the chip is never the anchor")
        mn = self._with(m, [note, self.REC, self.REPLY])
        km._send_chat_locked(c, mn, None, km._chat_diff(mc["events"], mn["events"]), False)
        self.assertEqual(self._frame(sent[-1]), ("chatTail", last_rec, [note["uuid"], self.REC["uuid"], self.REPLY["uuid"]]))
        self.assertEqual(c["echat"][SID]["last"], self.REPLY["uuid"])

    def test_two_echoes_then_a_queued_overlay_keep_the_base_on_the_record(self):
        # two pending sends and then a queued card after them: the base stays on the record before the first echo, and the
        # card's arrival re-sends the echoes on the suffix (the client truncates after the record and re-applies them; its
        # pending reconcile re-hides the sender's own), the way an overlay card rides every later delta
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        last_rec = km._event_key(m["events"][-1])
        e1 = {"kind": "user", "md": "one", "uuid": "echo:" + "b" * 32, "human": True}
        e2 = {"kind": "user", "md": "two", "uuid": "echo:" + "c" * 32, "human": True}
        q = {"kind": "queued", "uuid": "queued", "texts": [{"md": "three"}]}
        m5 = self._with(m, [e1, e2])
        km._send_chat_locked(c, m5, None, len(m["events"]), False)
        self.assertEqual(c["echat"][SID]["last"], last_rec)
        m6 = self._with(m, [e1, e2, q])
        km._send_chat_locked(c, m6, None, km._chat_diff(m5["events"], m6["events"]), False)
        self.assertEqual(self._frame(sent[-1]), ("chatTail", last_rec, [e1["uuid"], e2["uuid"], "queued"]))
        self.assertEqual(c["echat"][SID]["last"], last_rec)
        # a list of nothing else falls back to its last event (a transcript-less session's first echo): the known residue,
        # one full at that first landing, once per session creation
        self.assertEqual(km._last_anchor([e1, e2, q]), "queued")
        self.assertEqual(km._last_anchor([e1, e2]), e2["uuid"])

    def test_the_transient_key_rule_and_the_gone_key_label(self):
        # None-safe (a hand-built event with no uuid gives _event_key None); a uuid#n key of a transient matches by its
        # prefix; the kernel's durable synthesized keys and the overlay kinds are not transient
        self.assertFalse(km._transient_key(None))
        self.assertEqual(km._last_anchor([{"kind": "user", "uuid": "x"}, {"kind": "user"}]), None)
        for k in (self.ECHO, "echo-0123abcd", "cmd:1781199000:model", self.ECHO + "#2"):
            self.assertTrue(km._transient_key(k), k)
        for k in ("cmdg:1:1", "orphan:1:1", "retried:1:1", "gaveup:1:1", "effort:1:1", "branch:x", "clear:x", "system:x", "ev:abc",
                  "queued", "apiError", self.REC["uuid"], self.REC["uuid"] + "#2"):
            self.assertFalse(km._transient_key(k), k)
        # the lastGone label is a bounded vocabulary: a transient key names its prefix, a colon-keyed note its family, an
        # overlay kind `overlay`, a record uuid (with or without its #n) `record`, never a label per uuid
        self.assertEqual([km._gone_key_label(k) for k in (self.ECHO, "echo-0123abcd", "cmd:1:model", "cmd:1:model#2")],
                         ["echo", "echo-", "cmd", "cmd"])
        self.assertEqual([km._gone_key_label(k) for k in ("cmdg:1:1", "orphan:1:1", "ev:abc")], ["cmdg", "orphan", "ev"])
        self.assertEqual([km._gone_key_label(k) for k in (self.REC["uuid"], self.REC["uuid"] + "#2", "u_new", "queued", None, "")],
                         ["record", "record", "record", "overlay", "none", "none"])
        # the two comparison labels, asserted on the rule itself (the 2026-09-19 review: no test read them, so a dropped branch
        # or a loosened comparison landed the full under another label with every module green): a base whose last edge
        # sits before its first is `inverted`; a change at or before the held first edge is `changeBelowFirst`; a change
        # past it that still reached the full frame is `other`
        base = {"first": "f", "last": "l"}
        self.assertEqual(km._chat_full_reason(base, 5, 2, 7, 10), "inverted")
        self.assertEqual(km._chat_full_reason(base, 3, 8, 2, 10), "changeBelowFirst")
        self.assertEqual(km._chat_full_reason(base, 3, 8, 3, 10), "changeBelowFirst", "at the held first edge itself")
        self.assertEqual(km._chat_full_reason(base, 3, 8, 4, 10), "other")

    def test_a_full_to_a_base_holder_is_counted_by_reason_and_filed_once(self):
        # the meter (2026-09-19): every proto-2 full is counted under pusher.chatFullWhy by the reason the sender had, and a
        # full to a client that HOLDS a base files one chatFull client-diag row; the deltas count and file nothing. The
        # collector is process-global and the harness never resets it (the other tests here send fulls too), so reset first
        km._PERF_STATS.reset()
        why = lambda: km._PERF_STATS.snapshot()["pusher"]["chatFullWhy"]
        m, c, sent, last_rec, echo, d1, base1, d2 = self._echo_then_landing(self.ECHO)
        self.assertEqual(why(), {"noBase": 1}, "the first send: no base held, counted, not filed")
        self.assertEqual(self._diag_reasons(), [], "the two deltas filed nothing")
        m4 = dict(m); m4["events"] = [{"kind": "user", "md": "x", "uuid": "z1"}, {"kind": "assistant", "md": "y", "uuid": "z2"}]   # a fork
        km._send_chat(c, m4, None, 0, False)
        self.assertEqual(sent[-1]["type"], "session")
        self.assertEqual(why(), {"noBase": 1, "baseGone": 1})
        self.assertEqual(self._diag_reasons(), ["baseGone"])
        m5 = self._with(m4, [{"kind": "assistant", "md": "z", "uuid": "z3"}])   # the fork grew by a reply: unlike the last frame sent
        km._send_chat(c, m5, None, 0, False)                           # a change at the list's first event against a held base: a
        self.assertEqual(sent[-1]["type"], "session")                  # genuine first-event change or a no-baseline send, by whichever sender
        self.assertEqual(why(), {"noBase": 1, "baseGone": 1, "changeAt0": 1})
        self.assertEqual(self._diag_reasons(), ["baseGone", "changeAt0"])
        row = self._diag_rows()[-1]
        self.assertEqual((row["surface"], set(row)), ("kernel", {"t", "wid", "surface", "what", "data"}))
        self.assertEqual(row["data"], {"cid": None, "kind": None, "sid": SID, "reason": "changeAt0", "changeFrom": 0, "total": 3,
                                       "firstHeld": True, "lastHeld": True})
        # the same full again inside the dedup window (the 2026-09-19 review): _send_client finds the client already holds the
        # frame byte for byte and hands it nothing, counting it under sends.deduped. The meter and the row follow the frame
        # that LEFT, not the decision to send one, so neither gains anything
        n_sent, before = len(sent), km._PERF_STATS.snapshot()["sends"]
        km._send_chat(c, m5, None, 0, False)
        after = km._PERF_STATS.snapshot()["sends"]
        self.assertEqual(len(sent), n_sent, "no frame left the client's send")
        self.assertEqual(after["deduped"]["chat"]["count"], before["deduped"].get("chat", {}).get("count", 0) + 1, "the dedup happened")
        self.assertEqual(why(), {"noBase": 1, "baseGone": 1, "changeAt0": 1}, "a deduped full is not counted")
        self.assertEqual(self._diag_reasons(), ["baseGone", "changeAt0"], "nor filed")
        # a base whose last edge is gone while the first is held: the label names the vanished key's family (the defect's own
        # shape, and how a fourth transient prefix minted outside the tuple would read on /perf). This client wears a real
        # socket's identity, and the row is read whole (the 2026-09-19 review: with a bare client and both edges held, swapped
        # or constant flags, swapped identity fields and a wid taken from the cid field all stayed green)
        n = len(m["events"])
        c3, sent3 = _client()
        c3.update(cid="11111111-2222-3333-4444-5555555555c3", kind="page", wid="W3")
        c3["echat"][SID] = {"first": km._event_key(m["events"][0]), "last": self.ECHO}
        km._send_chat(c3, m, None, n, False)
        self.assertEqual(sent3[-1]["type"], "session")
        self.assertEqual((why()["lastGone:echo"], self._diag_reasons()[-1]), (1, "lastGone:echo"))
        row = self._diag_rows()[-1]
        self.assertEqual(row["wid"], "W3", "the row names the window, from the client's own wid")
        self.assertEqual(row["data"], {"cid": "11111111-2222-3333-4444-5555555555c3", "kind": "page", "sid": SID, "reason": "lastGone:echo",
                                       "changeFrom": n, "total": n, "firstHeld": True, "lastHeld": False})
        c4, sent4 = _client()
        c4["echat"][SID] = {"first": km._event_key(m["events"][0]), "last": "11111111-2222-4333-8444-555555555599"}
        km._send_chat(c4, m, None, 1, False)
        self.assertEqual(why()["lastGone:record"], 1, "a vanished record uuid is one label, not one per uuid")
        # the two comparison labels through the sender, a fresh client each (a byte-identical repost inside the window is
        # deduped and counts nothing): a base whose last edge sits before its first, and a change below the held first edge
        self.assertGreaterEqual(n, 4, "the restored tail has the events the two arms index")
        c5, sent5 = _client()
        c5["echat"][SID] = {"first": km._event_key(m["events"][-1]), "last": km._event_key(m["events"][-3])}
        km._send_chat(c5, m, None, n, False)
        self.assertEqual((sent5[-1]["type"], why()["inverted"], self._diag_reasons()[-1]), ("session", 1, "inverted"))
        c6, sent6 = _client()
        c6["echat"][SID] = {"first": km._event_key(m["events"][-2]), "last": km._event_key(m["events"][-1])}
        km._send_chat(c6, m, None, n - 3, False)
        self.assertEqual((sent6[-1]["type"], why()["changeBelowFirst"], self._diag_reasons()[-1]), ("session", 1, "changeBelowFirst"))
        # an empty list to a client that holds a base: `empty`, and a row, since the client was owed deltas
        m0 = dict(m); m0["events"] = []
        km._send_chat(c4, m0, None, 0, False)
        self.assertEqual((why()["empty"], self._diag_reasons()[-1]), (1, "empty"))
        self.assertEqual(why(), {"noBase": 1, "baseGone": 1, "changeAt0": 1, "lastGone:echo": 1, "lastGone:record": 1,
                                 "inverted": 1, "changeBelowFirst": 1, "empty": 1})
        self.assertEqual(sum(why().values()), km._PERF_STATS.snapshot()["sends"]["full"]["chat"]["count"],
                         "the meter's total is the whole chat frames that went, no more")
        snap = why(); snap["planted"] = 1
        self.assertNotIn("planted", why(), "the snapshot hands out a copy")

    def test_an_empty_list_records_no_base_so_its_repost_and_the_first_content_frame_are_no_base_fulls_filed_nowhere(self):
        # A session whose built list is empty (a just-created SDK session: registered before any first send, built with zero
        # events, not skeletoned for want of a transcript) used to leave a base with both edges None (the 2026-09-19 review of
        # the meter): every later send to that client then read as one to a base holder, so the pusher's repost of the
        # identical empty full, once per client per repost window, was counted `empty` and filed a chatFull row with no event
        # behind it (180 rows an hour for one idle fresh session with three tabs open), and the first content frame found
        # neither edge in the list and was counted `baseGone` with a row. An empty list records no base: the repost and the
        # first content frame are noBase fulls, filed nowhere, and the frame after that is a delta
        km._PERF_STATS.reset()
        why = lambda: km._PERF_STATS.snapshot()["pusher"]["chatFullWhy"]
        whole, m = self._restored_tail()
        m0 = dict(m); m0["events"] = []
        c, sent = _client()
        km._send_chat(c, m0, None, 0, False)
        self.assertEqual((sent[-1]["type"], sent[-1]["events"], sent[-1]["lastUuid"]), ("session", [], None), "the empty full")
        self.assertNotIn(SID, c["echat"], "an empty list records no base")
        self.assertEqual((why(), self._diag_reasons()), ({"noBase": 1}, []))
        sig, t = c["sent"][("chat", SID)]
        c["sent"][("chat", SID)] = (sig, t - km._DEDUP_REPOST_S - 1)  # the pusher's next cycle past the dedup window
        km._send_chat(c, m0, None, 0, False)
        self.assertEqual(len(sent), 2, "the repost left")
        self.assertEqual((why(), self._diag_reasons()), ({"noBase": 2}, []),
                         "a re-sent empty list past the dedup slot: noBase, no row, no empty label")
        km._send_chat(c, m, None, 0, False)                            # the first content frame
        self.assertEqual(sent[-1]["type"], "session")
        self.assertEqual((why(), self._diag_reasons()), ({"noBase": 3}, []), "the first content frame is noBase, and files no row")
        self.assertEqual(c["echat"][SID], {"first": sent[-1]["firstUuid"], "last": km._last_anchor(m["events"])})
        m2 = self._with(m, [{"kind": "user", "md": "more", "uuid": "u_after_empty"}])
        km._send_chat(c, m2, None, len(m["events"]), False)
        self.assertEqual(self._frame(sent[-1]), ("chatTail", km._event_key(m["events"][-1]), ["u_after_empty"]), "and the frame after it is a delta")
        self.assertEqual(sum(why().values()), km._PERF_STATS.snapshot()["sends"]["full"]["chat"]["count"])

    def test_the_chat_full_row_is_appended_once_the_locked_entry_has_released_the_clients_lock(self):
        # The row's decision is made under the client's slot lock, with the send; the disk append is not (the 2026-09-19
        # review: a 0.6 s stall in the append under the lock held a handler thread's needFull reset for 0.55 s). Both
        # locked entries, the pusher's and the targeted push's road (_send_chat_or_status) and the test-facing one
        # (_send_chat), append after their lock block: a spy on the diag append reads who holds the lock at the write
        whole, m = self._restored_tail()
        seen, real = [], km._client_diag_append
        for entry in (km._send_chat, km._send_chat_or_status):
            c, sent = _client()
            entry(c, m, None, 0, False)                                     # the base
            m4 = dict(m); m4["events"] = [{"kind": "user", "md": "x", "uuid": "z1"}]   # a fork: a full to a base holder
            spy = lambda fp, line, c=c: (seen.append((json.loads(line)["what"], c["dlock"]._is_owned())), real(fp, line))
            with mock.patch.object(km, "_client_diag_append", spy):
                entry(c, m4, None, 0, False)
            self.assertEqual(sent[-1]["type"], "session")
            self.assertEqual(seen, [("chatFull", False)], entry.__name__ + ": one row, appended with the client's lock released")
            del seen[:]

    def test_the_whole_chat_frames_switch_builds_a_documented_session_from_turn_0_for_a_protocol_2_client_and_flips_live(self):
        """The Whole chat frames switch (2026-09-15, the night stage one b landed): a protocol-2 client over a documented
        session gets the FLOORED frame (the turns past the document's cut) with the switch off, the WHOLE frame (every turn
        from 0) with it on, and a flip mid-life changes the very next push: the pusher's floor decision reads the store live."""
        recs = transcript(NOW - 86400, turns=600, compact_every=150)
        self.write(_head_past_the_last_compaction(recs)); self.document()
        self.write(recs)
        whole = self.whole()
        c, _sent = _client(proto=2)
        saved = km._live_scope.chat_floor0
        self.addCleanup(lambda: setattr(km._live_scope, "chat_floor0", saved))
        self.addCleanup(lambda: (km.jd.STATE / km.WHOLE_CHAT_FRAMES_FILE).unlink(missing_ok=True))
        def push_build():
            self.fresh()
            km._live_scope.chat_floor0 = km._chat_floor0_of([c])          # the pusher's decision for this cycle, over this client
            try:
                return km.build_session(SID, NOW, {})
            finally:
                km._live_scope.chat_floor0 = None
        self.assertFalse(km._whole_chat_frames_on(), "off by default: absent file")
        m0 = push_build()
        self.assertGreater(m0.get("floor", 0), 0, "a protocol-2 client over a documented session: the frame is floored at the cut")
        self.assertLess(len(m0["events"]), len(whole), "…and carries the turns past the cut only")
        self.assertIsNotNone(km._set_whole_chat_frames(True), "the flip applies")
        self.assertTrue(km._whole_chat_frames_on())
        m1 = push_build()
        self.assertEqual(m1.get("floor", 0), 0, "the switch on: the next push builds from turn 0 for the same client")
        self.assertGreaterEqual(len(m1["events"]), len(whole), "…the whole frame: at least every event of the proto-1 whole build")
        stamp = km._set_whole_chat_frames(False)
        self.assertIsNotNone(stamp)
        m2 = push_build()
        self.assertEqual((m2.get("floor", 0) > 0, len(m2["events"])), (True, len(m0["events"])), "off again: floored on the next push")
        self.assertIsNone(km._set_whole_chat_frames(False, gt=stamp), "the same value under the same stamp is the gesture's own echo: nothing applied")
        self.assertIsNone(km._set_whole_chat_frames(True, gt=stamp - 1), "an older gesture stands down")
        self.assertFalse(km._whole_chat_frames_on())

    def test_a_non_boolean_store_reads_off_and_says_so_once(self):
        """The 1704 read, low 2: a hand-edited store with the string "false" read ON silently (a truthy non-boolean). Only a real
        true or false is a proved answer; anything else reads OFF and is said once per value on stderr, as the task-tracking
        switch does; the next write repairs it."""
        store = km.jd.STATE / km.WHOLE_CHAT_FRAMES_FILE
        self.addCleanup(lambda: store.unlink(missing_ok=True))
        getattr(km, "_wcf_read_fault_said", set()).clear()               # reached with a default: the base red is the read below, not a name
        err = io.StringIO()
        store.write_text(json.dumps({"enabled": "false", "gt": 1}))
        with contextlib.redirect_stderr(err):
            self.assertFalse(km._whole_chat_frames_on(), "the string false is not a proved ON (the base read it as True)")
            self.assertFalse(km._whole_chat_frames_on())
        self.assertEqual(err.getvalue().count("not a boolean"), 1, "said once per value")
        store.write_text(json.dumps({"enabled": "true", "gt": 2}))
        with contextlib.redirect_stderr(err):
            self.assertFalse(km._whole_chat_frames_on(), "the string true is not a proved ON either")
        self.assertEqual(err.getvalue().count("not a boolean"), 2, "a new value: said again, once")
        for k, v in enumerate(("yes", 1, 2.5, [True], {"on": True}, "TRUE")):   # six more distinct values: six lines, keyed by value, not by the
            store.write_text(json.dumps({"enabled": v, "gt": 3 + k}))          #  last value seen (1721 round two, low 3)
            with contextlib.redirect_stderr(err):
                self.assertFalse(km._whole_chat_frames_on())
        self.assertEqual(err.getvalue().count("not a boolean"), 8, "one line per distinct value")
        store.write_text(json.dumps({"enabled": "false", "gt": 9}))            # a value said before: no new line
        with contextlib.redirect_stderr(err):
            self.assertFalse(km._whole_chat_frames_on())
        self.assertEqual(err.getvalue().count("not a boolean"), 8, "a repeat of an earlier value says nothing")
        store.write_text(json.dumps({"enabled": None, "gt": 10}))              # a JSON null reads as absent: off, silently (the docstring says so)
        with contextlib.redirect_stderr(err):
            self.assertFalse(km._whole_chat_frames_on())
        self.assertEqual(err.getvalue().count("not a boolean"), 8, "null is absent, not a fault")
        self.assertIsNotNone(km._set_whole_chat_frames(True)); self.assertTrue(km._whole_chat_frames_on(), "a real write repairs it")

    def test_the_boot_seed_of_the_whole_chat_frames_switch_runs_after_every_definition_it_reaches_and_seeds_once(self):
        """The 1704 read, low 1: the ROMP_CHAT_FLOOR0 seed sat in a module-level try beside the boot sweep, where the setter's
        _mark_views_dirty call raised NameError (defined far below), swallowed by the bare except: the store write landed and
        nothing after it ran. The seed is a function main() calls once the module is loaded: with the env set and no store it
        seeds ON and dirties the views; a standing store is never overwritten (a later flip survives a second boot with the
        env set); without the env nothing happens."""
        store = km.jd.STATE / km.WHOLE_CHAT_FRAMES_FILE
        self.addCleanup(lambda: store.unlink(missing_ok=True))
        # the 1717 read, low 3: the base's red must be the BEHAVIOUR, not a missing name. At the base the seed ran at import
        # (writing the store, never dirtying the views: the setter raised NameError at _mark_views_dirty, swallowed), so a fresh
        # interpreter importing the kernel with the env set and no store shows a store and a dirty mark of 0.0; at the head the
        # import seeds nothing (main does) and the seed function, reached through getattr, dirties the views
        child = subprocess.run([sys.executable, "-c", "\n".join([
            "import os, sys, tempfile, json",
            "root = tempfile.mkdtemp(); os.environ['XDG_STATE_HOME'] = root; os.environ.pop('ROMP_STATE_DIR', None)",
            "os.makedirs(os.path.join(root, 'romp'), exist_ok=True); open(os.path.join(root, 'romp', 'session-hosts'), 'w').write('off')",   # its own root: hosts off
            "os.environ['ROMP_KERNEL_NO_OPEN'] = '1'; os.environ.setdefault('ROMP_SERVE_TOKEN', 'testtok'); os.environ['ROMP_CHAT_FLOOR0'] = '1'",
            "sys.path.insert(0, %r)" % HERE, "from romp_load import load_source",
            "km = load_source('romp_kernel_seedprobe', %r)" % os.path.join(BIN, "romp-kernel"),
            "store = km.jd.STATE / km.WHOLE_CHAT_FRAMES_FILE",
            "print(json.dumps({'storeAfterImport': store.exists(), 'dirtyAfterImport': km._views_dirty[0]}))"])],
            capture_output=True, text=True, timeout=600,
            env=dict(os.environ, ROMP_CHAT_FLOOR0="1",                    # the postal trio: the child's bus is its own and never started
                     ROMP_POSTAL_PORT=str(20000 + os.getpid() % 20000), ROMP_POSTAL_PEERS="0", ROMP_POSTAL_CLIENT_ONLY="1"))
        self.assertEqual(child.returncode, 0, child.stderr[-2000:])
        probe = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual(probe, {"storeAfterImport": False, "dirtyAfterImport": 0.0},
                         "the import seeds nothing: the base wrote the store at import with the views never dirtied")
        seed = getattr(km, "_seed_whole_chat_frames", None)
        self.assertIsNotNone(seed, "the seed is a function main() calls once the module is loaded")
        with mock.patch.dict(os.environ, {"ROMP_CHAT_FLOOR0": "1"}):
            d0 = km._views_dirty[0]
            self.assertTrue(seed(), "no store, the env set: seeded")
            self.assertTrue(km._whole_chat_frames_on()); self.assertGreater(km._views_dirty[0], d0, "the flip dirties the views: no NameError")
            self.assertIsNotNone(km._set_whole_chat_frames(False), "the user flips it off later")
            self.assertFalse(km._seed_whole_chat_frames(), "a second boot with the env set leaves the flip alone")
            self.assertFalse(km._whole_chat_frames_on())
        store.unlink(missing_ok=True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROMP_CHAT_FLOOR0", None)
            self.assertFalse(km._seed_whole_chat_frames(), "no env: nothing seeded"); self.assertFalse(store.exists())
        src = Path(os.path.join(BIN, "romp-kernel")).read_text()
        self.assertIn("    _seed_whole_chat_frames()", inspect.getsource(km.main), "main calls the seed after every definition is loaded")
        sweep_at = src.index("em.checkpoint_sweep()")
        self.assertNotIn("_set_whole_chat_frames", src[sweep_at - 200: sweep_at + 400], "no seed inside the module-level try beside the boot sweep")

    def test_the_base_rule_over_a_list_longer_than_the_wire_tail_and_a_floor_move(self):
        """Review find N: the earlier fixture's floor'd list fit the wire tail whole (pf 0). Here the tail is longer: a change
        just before the held first is a full frame, just after it a delta from the change; a floor move (an index client
        connecting) rebuilds the list from turn 0 and is a full frame."""
        recs = transcript(NOW - 86400, turns=600, compact_every=150)
        self.write(_head_past_the_last_compaction(recs)); self.document()   # the document's cut near turn 450 (stage one b cuts at the
        self.write(recs); m = self.restored()                                #  last settled turn: documented before the ~300-event tail)
        evs = m["events"]; self.assertGreater(len(evs), km.WIRE_TAIL)
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        f = sent[-1]; pf = len(evs) - km.WIRE_TAIL
        self.assertEqual(f["firstUuid"], evs[pf].get("key") or evs[pf]["uuid"])
        m2 = dict(m); e2 = list(evs); e2[pf - 1] = dict(e2[pf - 1], md="edited before the held first"); m2["events"] = e2
        km._send_chat_locked(c, m2, None, pf - 1, False)
        self.assertEqual(sent[-1]["type"], "session", "a change before the held first: a full tail frame")
        m3 = dict(m); e3 = list(evs); e3[pf + 1] = dict(e3[pf + 1], md="edited inside"); m3["events"] = e3
        km._send_chat_locked(c, m3, None, pf + 1, False)
        d = sent[-1]
        self.assertEqual((d["type"], d["afterUuid"]), ("chatTail", evs[pf].get("key") or evs[pf]["uuid"]), "a change inside: a delta from it")
        self.assertEqual(len(d["events"]), len(evs) - pf - 1)
        km._live_scope.chat_floor0 = True                                  # an index client connected: the floor drops to 0
        try:
            m0 = km.build_session(SID, NOW + 1, {})
        finally:
            km._live_scope.chat_floor0 = None
        km._send_chat_locked(c, m0, None, 0, False)
        self.assertEqual((sent[-1]["type"], sent[-1]["floor"]), ("session", 0), "a floor move is a full frame")

    def test_a_window_whose_span_reaches_the_tail_run_moves_the_bases_first_to_its_first_event(self):
        """From review find G (T386 stage 2): a window that reaches the tail run's first turn merges into the tail on the page,
        so the kernel's base takes its first event as the tail's older edge; the last stands."""
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        base = dict(c["echat"][SID])
        anchor = whole[-len(m["events"]) - 3]["uuid"]                        # just before the floor'd list: the window reaches it
        r = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW, base=base)
        self.assertNotIn("connected", r); self.assertNotIn("detached", r.get("_base") or {})
        hc = {h["uuid"] for h in self.head_cards}
        first_event = next(e for e in r["events"] if e["uuid"] not in hc)
        self.assertEqual(r["_base"], {"first": first_event.get("key") or first_event["uuid"]}, "the span reaches the tail: the base's first is the window's first event")
        self.assertEqual(len(r["span"]), 2)

    def test_in_list_windows_are_turn_aligned_at_floor_zero_and_the_walks_meet_the_whole(self):
        """Review find J: slices of the floor'd list snap to turn boundaries, at floor 0 too (a whole parse, no document)."""
        recs = transcript(NOW - 86400, turns=300, compact_every=1000)     # no compaction: floor 0, ~600 events in the list
        self.write(recs)
        self.fresh(); km._live_scope.chat_floor0 = False
        try:
            m = km.build_session(SID, NOW, {})
        finally:
            km._live_scope.chat_floor0 = None
        self.assertEqual(m["floor"], 0)
        evs = m["events"]
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        tix = km._turn_index_of_events(evs, turns)
        pos = {e["uuid"]: i for i, e in enumerate(evs)}
        for d in (0, 1, 2, 3):                                            # both parities: the fixture's turns are two events each,
            anchor = evs[len(evs) // 2 + d]["uuid"]                       #  so one parity lands on a turn start by accident (round 2)
            r = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW)
            first, last = r["events"][0]["uuid"], r["events"][-1]["uuid"]
            a, b = pos[first], pos[last]
            self.assertTrue(a == 0 or tix[a - 1] != tix[a], "the window starts at a turn's first event (anchor +%d)" % d)
            self.assertTrue(b == len(evs) - 1 or tix[b + 1] != tix[b], "and ends at a turn's last event (anchor +%d)" % d)
            self.assertIn(anchor, [e["uuid"] for e in r["events"]])
        anchor = evs[len(evs) // 2]["uuid"]
        r = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW)
        held = list(r["events"])
        for _ in range(50):
            o = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": held[0].get("key") or held[0]["uuid"]}, NOW)
            held = o["events"] + held
            if not o["more"]:
                break
        n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": r["span"][1], "hi": len(turns)}, NOW)
        held = held + n["events"]
        self.assertEqual(_strip(held), _strip(evs), "the older walk and one span below the window meet the whole list")

    @staticmethod
    def _apply_base(c, reply):
        """What the handler does with a reply's _base (kernel.py, the history requests' arm): the tail run's first edge advances,
        the last stands (T386 stage 2)."""
        base = reply.pop("_base", None)
        old = c["echat"].get(SID)
        if isinstance(base, dict) and base.get("first") and isinstance(old, dict):
            c["echat"][SID] = {"first": base["first"], "last": old.get("last")}

    def test_load_older_advances_the_runs_first_edge_and_a_window_inside_the_walked_run_stays_attached(self):
        """Round 2, item 1: the base's first never moved with loadOlder, so loadAround's `connected` tested a STALE first: a
        window inside the walked run (holding neither the stale first nor the live tail) left the kernel detached while the
        page, holding the live tail, believed itself live: no deltas, ever."""
        recs = transcript(NOW - 86400, turns=600, compact_every=150)      # ~300 events after the cut: longer than the wire tail
        self.write(recs)
        whole = self.whole()
        self.write(_head_past_the_last_compaction(recs)); self.document()   # documented before the tail landed (stage one b cuts at
        self.write(recs)                                                     #  the last settled turn, so a whole-file document has a
        m = self.restored()                                                  #  short tail)
        evs = m["events"]
        self.assertGreater(len(evs), km.WIRE_TAIL)
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        base0 = dict(c["echat"][SID])
        self.assertEqual(base0["first"], evs[len(evs) - km.WIRE_TAIL]["uuid"], "the first frame's base: the wire tail's first")
        self.assertNotEqual(base0["first"], evs[0]["uuid"])
        o1 = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": base0["first"]}, NOW, base=c["echat"][SID])
        self.assertEqual(set(o1["_base"]), {"first"}, "an older chunk from the TAIL's first edge moves the base's first, nothing else")
        self._apply_base(c, o1)
        b1 = c["echat"][SID]
        self.assertEqual(b1["first"], evs[0]["uuid"], "the run's first edge advanced to the list's head")
        self.assertEqual(b1["last"], base0["last"], "its last unchanged")
        self.assertEqual(o1["span"][1], km._turn_index_of_events(evs, km._parse(self.leaf, SID, NOW)["turns"])[len(evs) - km.WIRE_TAIL], "the chunk's span ends at the tail's first turn")
        o2 = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": b1["first"]}, NOW, base=c["echat"][SID])
        self._apply_base(c, o2)
        b2 = c["echat"][SID]
        pages = o2["events"]
        self.assertEqual(b2["first"], pages[0].get("key") or pages[0]["uuid"], "…and into the pages")
        run = pages + evs                                                 # what the page holds: one run through the live tail
        anchor = run[len(pages) // 2]["uuid"]                             # inside the walked pages: neither edge is in its window
        w = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW, base=c["echat"][SID])
        keys = {e.get("key") or e["uuid"] for e in w["events"]}
        self.assertNotIn(b2["first"], keys); self.assertNotIn(base0["first"], keys); self.assertNotIn(b2["last"], keys)
        self.assertTrue(w["moreAfter"], "the window ends before the tail")
        self.assertIsNone(w["_base"], "a window inside the held history changes no base: the tail is always resident (T386 stage 2)")
        n = len(sent)
        km._send_chat_locked(c, m, None, len(evs) - 1, False)             # a change at the tail: a delta, not silence
        self.assertEqual(len(sent), n + 1); self.assertEqual(sent[-1]["type"], "chatTail")
        far = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": whole[2]["uuid"]}, NOW, base=c["echat"][SID])
        self.assertIsNone(far["_base"]); self.assertNotIn("connected", far)
        o3 = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": far["events"][-1]["uuid"]}, NOW, base=c["echat"][SID])
        self.assertIsNone(o3.get("_base"), "an older chunk from a history run's edge, not the tail's, leaves the base alone")
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn('if isinstance(base, dict) and base.get("first"):', src, "the handler applies a first-edge advance and keeps the last")

    def test_the_fold_entry_carries_the_prefixs_key_counts(self):
        whole, m = self._restored_tail()
        km._live_scope.chat_floor0 = False
        try:
            km.build_session(SID, NOW + 1, {})                             # a second build seals a prefix
        finally:
            km._live_scope.chat_floor0 = None
        fe = km._chat_fold_get(SID)
        self.assertIsNotNone(fe); self.assertIn("keyCounts", fe)
        self.assertEqual(fe["keyCounts"], km._key_counts(fe["events"]))

    def test_a_client_whose_first_edge_lies_in_the_pages_still_gets_the_tails_delta(self):
        """T386 stage 2: no client is detached; a base whose first sits before the floor'd list (history the client loaded) and
        whose last is the tail's gets the tail's changes as deltas like any other."""
        whole, m = self._restored_tail()
        c, sent = _client()
        c["echat"][SID] = {"first": whole[10]["uuid"], "last": m["events"][-1].get("key") or m["events"][-1]["uuid"]}
        km._send_chat_locked(c, m, None, len(m["events"]) - 1, False)
        self.assertEqual(sent[-1]["type"], "chatTail", "a delta reaches a client holding history above the tail")
        c["echat"].pop(SID)                                              # needFull's reset, or a reconnect's ready
        km._send_chat_locked(c, m, None, len(m["events"]) - 1, False)
        self.assertEqual(sent[-1]["type"], "session")
        self.assertEqual(set(c["echat"][SID]), {"first", "last"})

    def test_a_proto1_client_keeps_the_index_frames(self):
        whole, m = self._restored_tail()
        c, sent = _client(proto=1)
        km._live_scope.chat_floor0 = True
        try:
            m0 = km.build_session(SID, NOW, {})
        finally:
            km._live_scope.chat_floor0 = None
        km._send_chat_locked(c, m0, None, 0, False)
        f = sent[-1]
        self.assertEqual(f["type"], "session"); self.assertNotIn("proto", f)
        self.assertGreater(len(m0["events"]), km.WIRE_TAIL, "the whole list is longer than the wire tail")
        self.assertEqual((f["headFrom"], f["headTotal"]), (len(m0["events"]) - km.WIRE_TAIL, len(m0["events"])))
        self.assertIsInstance(c["echat"][SID], tuple)

    def test_load_older_by_uuid_walks_to_the_head_and_the_pages_equal_the_whole(self):
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        resident = list(sent[-1]["events"])
        oldest = resident[0]["uuid"]
        steps = 0
        while True:
            r = km._chat_history_reply(SID, {"type": "loadOlder", "id": SID, "before": oldest}, NOW)
            self.assertEqual((r["type"], r["beforeUuid"]), ("chatHead", oldest))
            self.assertNotIn("missing", r)
            resident = r["events"] + resident
            steps += 1
            if not r["more"]:
                break
            oldest = resident[0]["uuid"]
            self.assertLess(steps, 50)
        self.assertEqual(_strip(resident), self.head_cards + whole, "the pages walked back to the head, the head cards first, concatenate to the whole build")
        self.assertGreaterEqual(steps, 2)

    def test_load_around_lands_a_deep_anchor_in_one_reply_and_a_span_fills_the_gap_to_the_tail(self):
        whole, m = self._restored_tail()
        c, sent = _client()
        km._send_chat_locked(c, m, None, 0, False)
        f = sent[-1]
        anchor = whole[7]["uuid"]                                        # deep in the pre-cut history
        self.assertNotIn(anchor, {e["uuid"] for e in f["events"]})
        r = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": anchor}, NOW, base=c["echat"][SID])
        self.assertEqual((r["type"], r["anchor"]), ("chatWindow", anchor))
        uu = [e["uuid"] for e in r["events"]]
        self.assertIn(anchor, uu)
        self.assertEqual(r["moreBefore"], False, "the window reached the head"); self.assertEqual(r["span"][0], 0)
        self.assertTrue(r["moreAfter"], "and not the tail")
        self.assertIsNone(r["_base"], "a window short of the tail leaves the base alone: the client is not detached")
        km._send_chat_locked(c, m, None, len(m["events"]) - 1, False)
        self.assertEqual(sent[-1]["type"], "chatTail", "the delta reaches the client with a window above the tail")
        turns = km._parse(self.leaf, SID, NOW)["turns"]
        n = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": r["span"][1], "hi": f["tailLo"]}, NOW, base=c["echat"][SID])
        self.assertEqual((n["type"], n["span"], n["head"]), ("chatTurns", [r["span"][1], f["tailLo"]], False))
        self.assertEqual(n["_base"]["first"], n["events"][0].get("key") or n["events"][0]["uuid"], "the span reaches the tail's first turn: the base's first moves")
        held = list(r["events"]) + n["events"] + list(f["events"])
        self.assertEqual(_strip(held), self.head_cards + whole, "the window, the span and the tail equal the whole, the head cards first")
        past = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": f["tailLo"], "hi": len(turns) + 5}, NOW, base=c["echat"][SID])
        self.assertEqual(_strip(past["events"]), _strip(f["events"]), "a span over the tail run itself is the tail's events, clipped to the transcript")
        empty = km._chat_history_reply(SID, {"type": "loadTurns", "id": SID, "lo": len(turns), "hi": len(turns) + 5}, NOW)
        self.assertTrue(empty.get("missing"))
        retired = km._chat_history_reply(SID, {"type": "loadNewer", "id": SID, "after": uu[-1]}, NOW)
        self.assertTrue(retired.get("missing") and retired.get("retired"), "the walk toward the tail is retired: answered, never served")
        r = km._chat_history_reply(SID, {"type": "loadAround", "id": SID, "uuid": "no-such-uuid"}, NOW)
        self.assertTrue(r.get("missing")); self.assertEqual(r["events"], [])

    def test_the_pages_cache_counts_and_bounds(self):
        whole, m = self._restored_tail()
        floor = m["floor"]
        km._chat_history_page(SID, 0, min(16, floor), NOW)
        km._chat_history_page(SID, 0, min(16, floor), NOW)
        st = km._PAGE_STATS
        self.assertEqual((st["misses"], st["hits"]), (1, 1))
        self.assertGreater(st["bytes"], 0); self.assertEqual(st["pages"], 1)
        saved = km._PAGE_CACHE_MAX
        km._PAGE_CACHE_MAX = 2
        try:
            for lo in range(0, min(floor, 48), 16):
                km._chat_history_page(SID, lo, min(lo + 16, floor), NOW)
            self.assertLessEqual(km._PAGE_STATS["pages"], 2)
            self.assertGreaterEqual(km._PAGE_STATS["evictions"], 1)
        finally:
            km._PAGE_CACHE_MAX = saved


class HydrationRace(Harness):
    def test_an_atom_another_thread_finished_between_the_filter_and_the_read_is_skipped(self):
        """Review find C: the disk loop was guarded, the memo-hit path and _hydrate_one were not."""
        class Flaky(dict):                                                # answers the marker once (the filter), then none
            def __init__(self, *a, **k):
                super().__init__(*a, **k); self.n = 0
            def get(self, k, d=None):
                if k == "lazy":
                    self.n += 1
                    if self.n == 2:
                        super().pop("lazy", None)                         # another thread finished it: the marker is GONE, so a
                    return super().get(k, d) if self.n <= 1 else None    #  re-introduced a["lazy"] subscript raises (round 2)
                return super().get(k, d)
        a = Flaky({"uuid": "x1", "type": "user", "lazy": {"k": "u", "at": (0, 10)}, "session_id": SID})
        with em._ASM_CKPT_LOCK:
            em._HYDRATED["x1"] = ({"uuid": "x1", "message": {"role": "user", "content": "hi"}}, 10)   # a warm memo
        try:
            self.assertEqual(em.hydrate([a], SID), 1, "counted as filled, nothing raised")
        finally:
            with em._ASM_CKPT_LOCK:
                em._HYDRATED.pop("x1", None)
        em._hydrate_one({"uuid": "x2"}, {"uuid": "x2"})                   # a finished atom: a no-op, not a KeyError


if __name__ == "__main__":
    unittest.main()
