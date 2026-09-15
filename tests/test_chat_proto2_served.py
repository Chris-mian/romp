#!/usr/bin/env python3
"""T323 stage 4b (2026-09-11): the proto-2 chat wire over a real hermetic kernel. A first kernel parses a compacted
synthetic session whole and leaves its assembly document at exit; a second kernel boots from it. A proto-2 tab's
session frame is the post-boundary tail with headKnown false and headTotal null and hydrates nothing (the
flattening step: no pre-cut body is read at a first open); loadOlder by uuid walks page by page to the head, where
the count appears, and the pages plus the tail equal what an index (proto-1) client on the same kernel assembles
from today's frames; loadAround lands a deep anchor in one reply as a run by its span; loadTurns pages the gap to the
window back to the live tail and re-attaches, so the next transcript append reaches it as a chatTail; every leaf
byte is the tail, the guards and the pages asked for. Synthetic transcript (the stage 4a fixture); TESTHOST."""
import json
import os
import sys
import time
import unittest
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import test_asm_checkpoint_served as A                      # noqa: E402  the lab, the fixture, the kernel boot helpers
from test_fold_checkpoints_served import ChatClient, iso    # noqa: E402

WEB = A.WEB
MAX_PAGES = 400                                             # the walks are bounded: a fixture this size takes a few dozen


class Proto2LongLastTurn(A.RestartOverACheckpointedSession):
    """The tail run at a turn boundary over a real hermetic kernel (the snap of 2026-09-15, kernel.py _tail_run_start): a LAST
    turn longer than the wire tail (an opening reply, 300 tool calls, a closing reply). The proto-2 frame begins at that turn's
    first record and carries the opening reply, so the page holds the turn whole from its start; before the snap the frame
    began at the cut inside the turn and the turn's head was in neither the run nor the head gap."""
    test_the_second_kernel_restores_the_assembly_from_the_first_kernels_document = None   # the parent's own test: not re-run here

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        t0 = int(time.time()) - 86400
        recs = A.transcript(t0, turns=60, compact_every=25)
        t, parent = t0 + 60 * 60 + 100, recs[-1]["uuid"]
        recs.append({"type": "user", "uuid": "uL", "parentUuid": parent, "timestamp": iso(t), "promptSource": "typed", "cwd": "/w/notes-api",
                     "message": {"role": "user", "content": "run the whole sweep and report 0"}})
        recs.append({"type": "assistant", "uuid": "aL0", "parentUuid": "uL", "timestamp": iso(t + 5), "cwd": "/w/notes-api",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "Starting the sweep; the figures land as each stage finishes."}], "stop_reason": "tool_use"}})
        parent = "aL0"
        for i in range(300):
            tu, tr = "tL%d" % i, "rL%d" % i
            recs.append({"type": "assistant", "uuid": tu, "parentUuid": parent, "timestamp": iso(t + 10 + 2 * i), "cwd": "/w/notes-api",
                         "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tuL%d" % i, "name": "Bash", "input": {"command": "uv run python stage.py %d" % i}}], "stop_reason": "tool_use"}})
            recs.append({"type": "user", "uuid": tr, "parentUuid": tu, "timestamp": iso(t + 11 + 2 * i),
                         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tuL%d" % i, "content": "ok %d" % i}]}})
            parent = tr
        recs.append({"type": "assistant", "uuid": "aL1", "parentUuid": parent, "timestamp": iso(t + 620), "cwd": "/w/notes-api",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "Sweep done; every stage reported."}], "stop_reason": "end_turn"}})
        with open(cls.leaf, "w") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in recs))

    def _open(self, port):
        client = ChatClient(port, self.token, WEB)
        client.send({"type": "ready", "proto": 2})
        for fr in client.frames(60):
            if fr.get("type") == "session" and fr.get("id") == WEB:
                return client, fr
        self.fail("no session frame for web within 60 s")

    def test_a_long_last_turn_is_held_whole_from_its_first_record(self):
        k, port, log = self._boot()
        try:
            client, frame = self._open(port)
            try:
                uuids = [e.get("uuid") for e in frame["events"]]
                self.assertEqual(frame.get("proto"), 2)
                self.assertEqual(uuids[0], "uL", "the run begins at the long turn's first record, not at the cut 250 events from the end: %r" % uuids[:3])
                self.assertIn("aL0", uuids, "the turn's opening reply, before the cut, is in the run")
                self.assertGreater(len(uuids), 300, "the frame carries the whole turn: its 300 tool calls and both replies")
                self.assertIsInstance(frame.get("tailLo"), int, "the frame names the tail run's first turn")
                records = [e.get("uuid") for e in frame["events"] if e.get("kind") in ("user", "assistant", "tool", "thinking", "compact")]
                self.assertEqual(records[-1], "aL1", "…through the closing reply (the overlay cards after it ride the suffix, and are not records)")
            finally:
                client.close()
        finally:
            self._stop(k)


class Proto2Wire(A.RestartOverACheckpointedSession):
    test_the_second_kernel_restores_the_assembly_from_the_first_kernels_document = None   # the parent's own test: not re-run here

    def _open(self, port, proto):
        """A chat client on `port`: its ready frame (proto 2, or an index client's bare ready) and the session frame."""
        client = ChatClient(port, self.token, WEB)
        t0 = time.time()
        client.send({"type": "ready", "proto": 2} if proto == 2 else {"type": "ready"})
        for fr in client.frames(60):
            if fr.get("type") == "session" and fr.get("id") == WEB:
                return client, fr, time.time() - t0
        self.fail("no session frame for web within 60 s")

    def _reply(self, client, kind, seconds=60):
        for fr in client.frames(seconds):
            if fr.get("type") == kind and fr.get("id") == WEB:
                return fr
        self.fail("no %s frame within %d s" % (kind, seconds))

    def _walk_older(self, client, frame):
        """loadOlder by uuid to the head; returns the whole list and the number of pages."""
        evs = list(frame["events"])
        for pages in range(1, MAX_PAGES + 1):
            oldest = evs[0]["uuid"]
            client.send({"type": "loadOlder", "id": WEB, "before": oldest})
            r = self._reply(client, "chatHead")
            self.assertEqual(r["beforeUuid"], oldest)
            self.assertNotIn("missing", r)
            evs = r["events"] + evs
            if not r["more"]:
                return evs, pages
        self.fail("the head was not reached in %d pages" % MAX_PAGES)

    def _walk_older_index(self, client, frame):
        evs = list(frame["events"]); head_from = frame.get("headFrom", 0)
        for _ in range(MAX_PAGES):
            if head_from <= 0:
                return evs
            client.send({"type": "loadOlder", "id": WEB, "before": head_from})
            r = self._reply(client, "chatHead")
            self.assertEqual(r["before"], head_from)
            evs = r["events"] + evs; head_from = r["from"]
        self.fail("the index walk did not reach the head")

    def _fill_to_tail(self, client, window, frame):
        """The regions protocol (T386 stage 2): the tail run is always resident (the session frame), a window is a run by its turn span,
        and the gap between them is filled page by page with loadTurns by span (the frame names the tail run's first turn, tailLo, and
        the page size, pageTurns). Returns the window's events plus the pages' plus the tail's, and the number of pages."""
        lo, tail_lo, page = window["span"][1], frame["tailLo"], frame.get("pageTurns", 16)
        evs = list(window["events"]); pages = 0
        while lo < tail_lo:
            hi = min(lo + page, tail_lo)
            client.send({"type": "loadTurns", "id": WEB, "lo": lo, "hi": hi})
            r = self._reply(client, "chatTurns")
            self.assertEqual(r["span"], [lo, hi]); self.assertNotIn("missing", r)
            evs += r["events"]; lo = hi; pages += 1
            self.assertLessEqual(pages, MAX_PAGES, "the tail was not reached in %d pages" % MAX_PAGES)
        return evs + list(frame["events"]), pages

    def test_a_proto2_tab_over_a_restored_kernel(self):
        k1, p1, log1 = self._boot()
        try:
            c1, f1, dt1 = self._open(p1, 2)
            self.assertEqual((f1.get("proto"), f1["headKnown"], f1["headTotal"]), (2, False, None),
                             "a whole parse longer than the wire tail: the head not reached")
            # the tail run's law since the snap of 2026-09-15: the frame is at least the wire tail (250 events) and BEGINS at a
            # turn's first event (the cut moves up to it), never inside a turn; this replaces a 250 ceiling that held only while
            # the fixture's cut happened to land on a turn start (the builder at floor 0 gives a 251-event frame)
            self.assertGreaterEqual(len(f1["events"]), 250, "the frame carries at least the wire tail")
            self.assertIn(f1["events"][0]["uuid"].split(":")[0][0], ("u", "b", "s"),
                          "the run begins at a turn's first record (a prompt, or a compaction's boundary or summary), not at an assistant record: %r" % f1["events"][0].get("uuid"))
            c1.close()
            time.sleep(2.0)
        finally:
            self._stop(k1)
        size = os.path.getsize(self.leaf)
        k2, p2, log2 = self._boot()
        try:
            c2, f2, dt2 = self._open(p2, 2)
            perf = self._get(p2, "/perf"); asm = perf["asmCheckpoint"]
            self.assertEqual(asm["fallbacks"], {}); self.assertGreaterEqual(asm["restored"], 1)
            self.assertEqual((f2["proto"], f2["headKnown"], f2["headTotal"]), (2, False, None))
            self.assertEqual(f2["firstUuid"], f2["events"][0]["uuid"]); self.assertEqual(f2["lastUuid"], f2["events"][-1]["uuid"])
            # the frame's build read no pre-cut body (the judges' first pass over a fresh store reads the unjudged
            # segments' text through the same memo, under their own caller names; the chat's callers stay at zero)
            readers = {k.split("<-")[0] for k in asm["hydratedBy"]}   # a shared reader's key carries its caller (reader<-caller, T377)
            self.assertFalse({"build_session", "_atom_md"} & readers, "the first open hydrated for the chat: %s" % asm["hydratedBy"])
            self.assertLessEqual(readers, {"_unit_text", "_atom_text", "_seg_anchors", "_atom_user_text", "_human_prompt_record", "_has_asst_work", "_seg_launches"},
                                 "only the judges' readers: %s" % asm["hydratedBy"])
            by = perf["checkpoints"]["readByPath"]
            leaf_read0 = by.get(os.path.realpath(self.leaf), by.get(self.leaf, 0))
            self.assertLess(leaf_read0 - asm["hydratedBytes"], size / 4, "the leaf cost its tail and guards beyond the judges' hydration: %d read, %d hydrated, %d whole"
                            % (leaf_read0, asm["hydratedBytes"], size))
            self.assertLess(dt2, 10.0, "the first frame of a restored kernel: %.2fs" % dt2)
            # older history, page by page, to the head
            whole2, pages = self._walk_older(c2, f2)
            self.assertGreaterEqual(pages, 2)
            perf = self._get(p2, "/perf")
            self.assertGreater(perf["chatPages"]["misses"], 0, "the pages were rendered on demand: %s" % perf["chatPages"])
            # (the pages' own hydration is proven deterministically in tests/test_chat_pages.py: here the judges' first pass
            #  over a fresh store may already have filled the memo the pages read from)
            # the lazy index (T323 stage 4c): the restored kernel's pre-cut turns came from the document's turns section, and
            # the chat's first opens built no pre-cut atom; only a page render (the walk above) builds, and only its own turns
            idx = self._get(p2, "/perf")["asmIndex"]
            self.assertGreater(idx["restoredTurns"], 0, "the document carried a turns section: %s" % idx)
            for who in ("build_session", "_cursors_before", "_fold_tasks_turn", "_turn_index_of_events", "_turn_of_uuid"):
                self.assertNotIn(who, idx["materializedBy"], "the chat build reached for pre-cut atoms: %s" % idx["materializedBy"])
            self.assertLessEqual(idx["materialized"], idx["restoredTurns"] * 4, "the pages walked built their turns' atoms, no more: %s" % idx)
            # a deep anchor in one round trip: the window lands it and the client is detached
            anchor = whole2[5]["uuid"]
            c4, f4, _ = self._open(p2, 2)
            self.assertNotIn(anchor, {e["uuid"] for e in f4["events"]})
            t_win = time.time()
            c4.send({"type": "loadAround", "id": WEB, "uuid": anchor})
            w = self._reply(c4, "chatWindow")
            dt_win = time.time() - t_win                   # the user's click on a summary far in the past: one round trip
            self.assertLess(dt_win, 5.0, "a deep anchor's window landed in %.2fs" % dt_win)
            self.assertEqual(w["anchor"], anchor); self.assertIn(anchor, [e["uuid"] for e in w["events"]])
            t_win2 = time.time()
            c4.send({"type": "loadAround", "id": WEB, "uuid": anchor})
            self._reply(c4, "chatWindow")
            dt_win2 = time.time() - t_win2                 # the same window again: the pages cache serves it
            self.assertEqual(w["moreBefore"], False); self.assertTrue(w["moreAfter"])
            self.assertEqual(w["span"][0], 0, "the window reaches the head, so its span starts at turn 0")
            # to the live tail through the regions protocol: the gap between the window and the resident tail, page by page
            held, steps = self._fill_to_tail(c4, w, f4)
            self.assertEqual([e["uuid"] for e in held], [e["uuid"] for e in whole2], "the window, the pages and the tail are the whole")
            # a transcript append now reaches the re-attached client as a uuid-anchored delta (a record chained on the
            # last one: a parentless record would open a new conversation, a fork, and a full frame is right for that)
            time.sleep(4.0)                                # one pusher cycle: the shared diff baseline for the list stands
            last_ev = next(e for e in reversed(held) if e.get("kind") in ("user", "assistant"))   # the last RECORD (an overlay
            last_rec = last_ev["uuid"]                                                                #  card is no parent), and a stamp
            t_last = time.mktime(time.strptime(last_ev["ts"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone    #  after it (the fixture's
            with open(self.leaf, "a") as fh:                                                          #  clock runs past now)
                fh.write(json.dumps({"type": "user", "uuid": "u_after", "parentUuid": last_rec, "timestamp": iso(t_last + 60),
                                     "promptSource": "typed",
                                     "message": {"role": "user", "content": "one more prompt after the restart"}}) + "\n")
            d = None
            for fr in c4.frames(45):                       # status-only tails (empty suffixes) may precede the one carrying the append
                if fr.get("type") == "chatTail" and fr.get("id") == WEB:
                    self.assertIn("afterUuid", fr); self.assertNotIn("from", fr)
                    if "u_after" in [e.get("uuid") for e in fr.get("events") or []]:
                        d = fr; break
                if fr.get("type") == "session":
                    v = self._get(p2, "/version")
                    self.fail("no full frame: the re-attached client is caught up; got %s events, floor %s, headKnown %s, first %s; parse %s; chatfold %s; %s"
                              % (len(fr.get("events") or []), fr.get("floor"), fr.get("headKnown"), fr.get("firstUuid"), v.get("parse"), v.get("chatfold"),
                                 self._leaf_trace(log2)[-1500:]))
            self.assertIsNotNone(d, "the append reached the re-attached client as a uuid-anchored delta")
            self.assertEqual(d["afterUuid"], last_rec, "the delta starts after the client's newest transcript event (the trailing "
                                                    "notice card rides the suffix)")
            # an index client on the same kernel assembles the same list from today's frames (its connect drops the
            # render floor to turn 0 for every tab while it is connected, so it comes last: a floor move is a full
            # tail frame to every proto-2 client, by design)
            c3, f3, dt3 = self._open(p2, 1)
            self.assertNotIn("proto", f3); self.assertIsInstance(f3.get("headFrom"), int)
            whole1 = self._walk_older_index(c3, f3)
            OVERLAYS = ("system", "clear", "todo", "compacting", "clearing", "reconnecting", "retrying", "queued", "apiError")
            def records(lst):                              # the transcript's events: the head cards and the live notices aside
                return [e["uuid"] for e in lst if e.get("kind") not in OVERLAYS]
            self.assertEqual(records(whole1), records(whole2) + ["u_after"],
                             "the proto-2 pages plus the tail are the index client's transcript, the cards aside")
            c3.close()
            # the index client left: the next build's floor climbs back and every proto-2 client gets a full tail frame
            # from it (a floor move is a full frame by design; round 3)
            f4b = None                                     # (the floor-0 frame c3's connect caused may still be queued ahead of it)
            for fr in c4.frames(60):
                if fr.get("type") == "session" and fr.get("id") == WEB and (fr.get("floor") or 0) > 0:
                    f4b = fr; break
            self.assertIsNotNone(f4b, "the floor climbed back after the index client left and c4 got the frame")
            self.assertEqual(f4b.get("proto"), 2)
            self.assertFalse(f4b.get("headKnown"), "…and the head is unknown again to the proto-2 client")
            perf = self._get(p2, "/perf")
            by = perf["checkpoints"]["readByPath"]
            leaf_read = by.get(os.path.realpath(self.leaf), by.get(self.leaf, 0))
            hyd = perf["asmCheckpoint"]["hydratedBytes"]
            self.assertLess(leaf_read - hyd, size / 4 + 4096,
                            "the leaf: its tail, guards and the pages' bodies, never whole: read %d, hydrated %d, size %d; %s"
                            % (leaf_read, hyd, size, self._leaf_trace(log2)))
            log = open(log2).read()
            self.assertNotIn("LazyBodyRead", log); self.assertNotIn("Traceback", log)
            sys.stderr.write("t323s4b served: first frame %.2fs (kernel 1, whole), %.2fs (kernel 2, restored, %d events); %d pages to the head; "
                             "deep anchor window %.2fs cold, %.2fs from the cache; index client %.2fs; hydrated %d bytes; pages %s\n"
                             % (dt1, dt2, len(f2["events"]), pages, dt_win, dt_win2, dt3, hyd, perf["chatPages"]))
            c2.close(); c4.close()
        finally:
            self._stop(k2)


if __name__ == "__main__":
    unittest.main()
