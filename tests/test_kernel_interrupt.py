#!/usr/bin/env python3
"""Stop/interrupt → the chat chip should flip to 'ready' (the user 2026-06-20). The chip is driven by the
event-model open-turn signal (open turn AND no idle atom). A normal turn flips it via the transcript's
end_turn; an Esc INTERRUPT writes no end_turn and the Stop hook doesn't fire, so the kernel records a
state:"idle" transition itself (_record_idle) → an idle atom lands in the open turn → the chip reads ready.
Isolated from test_kernel.py (a peer is churning it). Synthetic fixtures only."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_intr", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(t, text, uuid, parent, stop):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": stop}}


class RecordIdle(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved = jd.STATE
        jd.STATE = Path(self.td.name)

    def tearDown(self):
        jd.STATE = self.saved
        self.td.cleanup()

    def test_appends_a_backdated_idle_state_record(self):
        km._record_idle(SID, NOW)
        rows = [json.loads(l) for l in (jd.STATE / "states" / (SID + ".jsonl")).read_text().splitlines() if l]
        self.assertEqual(rows, [{"t": NOW - 1, "state": "idle"}],
                         "one idle transition, backdated 1s so its [start,end] span is non-empty immediately")

    def test_no_sid_is_a_noop(self):
        km._record_idle("", NOW)
        self.assertFalse((jd.STATE / "states").exists(), "no sid → nothing written, no crash")


class IdleAtomFlipsTheOpenTurn(unittest.TestCase):
    """The mechanism: an idle state record (what _record_idle writes) becomes an idle atom inside the OPEN
    turn, so the chip's open_now (= not ended AND no idle atom) goes False → 'ready'."""

    def _open_session(self, states):
        # an OPEN turn: the last assistant stops on tool_use (no end_turn), so the turn never 'ends'
        recs = [uline(T0, "do the thing", "u1"),
                aline(T0 + 10, "working on it", "a1", "u1", "tool_use")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / (SID + ".jsonl")
            p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
            return em.parse_session(str(p), rompuuid=SID, candidate_files=[str(p)], states=states, now=NOW)

    def test_open_turn_is_working_without_an_idle_record(self):
        lt = self._open_session(states=[])["turns"][-1]
        self.assertFalse(lt["ended"], "a tool_use stop leaves the turn open")
        self.assertFalse(any(a["type"] == "idle" for a in lt["atoms"]), "no idle record → no idle atom → still working")

    def test_idle_record_lands_an_idle_atom_in_the_open_turn(self):
        # the interrupt's idle record (backdated 1s, like _record_idle)
        lt = self._open_session(states=[{"t": NOW - 1, "state": "idle"}])["turns"][-1]
        self.assertFalse(lt["ended"], "the turn still never got end_turn")
        self.assertTrue(any(a["type"] == "idle" for a in lt["atoms"]),
                        "the idle transition becomes an idle atom in the open turn → the chip flips to ready")


if __name__ == "__main__":
    unittest.main()


class InterruptingChip(unittest.TestCase):
    """The INTERRUPTING chip (the user 2026-07-02): a just-sent stop flips the chip AT ONCE — the stop can
    take seconds to reach a stream boundary and land on disk, and the UI used to sit on 'working' (button
    still pressable, timer counting) the whole time. Event-cleared the moment the turn settles."""

    def setUp(self):
        km._interrupt_clicked.clear()

    def tearDown(self):
        km._interrupt_clicked.clear()

    def test_stamp_reads_interrupting_while_the_turn_is_still_open(self):
        km._interrupt_clicked[SID] = NOW - 2
        self.assertTrue(km._interrupting(SID, True, NOW), "stop sent + turn still open → interrupting")

    def test_clears_the_instant_the_turn_settles(self):
        km._interrupt_clicked[SID] = NOW - 2
        self.assertFalse(km._interrupting(SID, False, NOW), "turn no longer open → the stop landed")
        self.assertNotIn(SID, km._interrupt_clicked, "stamp consumed — never sticks")

    def test_wedged_turn_falls_back_after_the_safety_cap(self):
        km._interrupt_clicked[SID] = NOW - 121
        self.assertFalse(km._interrupting(SID, True, NOW), "a wedged turn falls back to honest 'working'")
        self.assertNotIn(SID, km._interrupt_clicked)

    def test_the_ws_interrupt_handler_stamps_and_pushes(self):
        with open(os.path.join(BIN, "romp-kernel")) as f:
            src = f.read()
        self.assertIn('_interrupt_clicked[str(sid)] = time.time()', src,
                      "the interrupt op stamps the optimistic state")
        self.assertIn('"interrupting" if _interrupting(sid, open_now, now,', src,
                      "the chip formula reads the stamp (with the open turn's start), right under compacting")


class InterruptMarker(unittest.TestCase):
    """The CLI's '[Request interrupted by user]' stop record is an EVENT, not typed input (the user
    2026-07-02): build_session flags it so the chat renders a slim rail marker, never a blue bubble."""

    def test_build_session_flags_the_stop_record(self):
        import inspect
        src = inspect.getsource(km.build_session)
        self.assertIn('if prompt.strip().startswith("[Request interrupted by user"):', src)
        self.assertIn('ev["interruptMarker"] = True', src)


class InterruptRecordEndsTurn(unittest.TestCase):
    """The CLI's stop record ENDS its turn in the event model (the user 2026-07-05). An interrupt writes
    no end_turn, so the dangling user record read as an OPEN turn in any STATES-LESS parse — which is what
    the kernel's _parse is: the chip latched 'Interrupting…' to its 120s cap and _ops_gate parked a /model
    pick against an idle session, while auto-nudge (whose judge parse folds states) simultaneously read the
    same session as stopped and fired into it. The record is the interrupt event itself, so the turn ends
    on it — no states overlay required."""

    def setUp(self):
        km._downtime[:] = []

    def _turns(self, recs, states=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / (SID + ".jsonl")
            p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
            return em.parse_session(str(p), rompuuid=SID, candidate_files=[str(p)],
                                    states=states or [], now=NOW)["turns"]

    def _interrupted(self, marker="[Request interrupted by user]"):
        return [uline(T0, "do the thing", "u1"),
                aline(T0 + 10, "working on it", "a1", "u1", "tool_use"),
                uline(T0 + 60, marker, "u2", "a1")]

    def test_interrupt_record_ends_the_turn_in_a_states_less_parse(self):
        turns = self._turns(self._interrupted())
        self.assertEqual(len(turns), 1, "the stop record folds into the turn it stopped")
        self.assertTrue(turns[-1]["ended"], "the CLI's stop record IS the turn end — no end_turn is coming")
        self.assertFalse(km._session_working(turns), "an interrupted session is not working")

    def test_tool_use_variant_ends_the_turn_too(self):
        turns = self._turns(self._interrupted("[Request interrupted by user for tool use]"))
        self.assertTrue(turns[-1]["ended"], "a permission-prompt dismissal is the same stop event")

    def test_next_prompt_opens_a_fresh_turn(self):
        recs = self._interrupted() + [uline(T0 + 120, "take another angle", "u3", "u2")]
        turns = self._turns(recs)
        self.assertEqual(len(turns), 2, "a prompt after the stop opens fresh, never absorbs into the dead turn")
        self.assertEqual(turns[0]["ended"], True)
        self.assertEqual((turns[1]["trigger"] or {}).get("uuid"), "u3")

    def test_plain_dangling_prompt_still_reads_open(self):
        # regression guard: a NORMAL not-yet-answered prompt (no stop record) is optimistic working
        turns = self._turns([uline(T0, "do the thing", "u1"),
                             aline(T0 + 10, "working on it", "a1", "u1", "tool_use")])
        self.assertFalse(turns[-1]["ended"])
        self.assertTrue(km._session_working(turns), "an open turn without a stop record still reads working")

    def test_suppression_holds_through_trailing_idle_atoms(self):
        # the judge-side parse folds a states idle atom AFTER the stop record — the scan must not care
        turns = self._turns(self._interrupted(), states=[{"t": T0 + 61, "state": "idle"}])
        self.assertTrue(km._interrupt_suppresses_nudge(turns),
                        "interrupt behind an idle span still reads as the user's last action")
        normal = self._turns([uline(T0, "ask", "u1"), aline(T0 + 10, "done", "a1", "u1", "end_turn")])
        self.assertFalse(km._interrupt_suppresses_nudge(normal), "a normally-ended turn is not user-stopped")

    def test_a_peer_message_does_not_lift_suppression(self):
        # requirement (the user 2026-07-05 via ui): suppressed until the USER's next message — a peer
        # postal turn (author {"peer": …} via the romp-msg-id marker) ending in between must not re-arm
        recs = self._interrupted() + [
            uline(T0 + 200, "QUESTION: which port?\nromp-msg-id: 1111.2_3.TESTHOST", "u3", "u2"),
            aline(T0 + 220, "answered the peer", "a2", "u3", "end_turn")]
        self.assertTrue(km._interrupt_suppresses_nudge(self._turns(recs)),
                        "a peer's postal message is not the user speaking — still suppressed")

    def test_the_users_next_message_lifts_suppression(self):
        recs = self._interrupted() + [uline(T0 + 200, "ok, take the other approach", "u3", "u2"),
                                      aline(T0 + 220, "on it", "a2", "u3", "end_turn")]
        self.assertFalse(km._interrupt_suppresses_nudge(self._turns(recs)),
                         "the user spoke after the interrupt → the user-message event re-arms the nudge")


class InterruptStampNoRelatch(unittest.TestCase):
    """The 'Interrupting…' stamp belongs to the turn the user STOPPED, not to whatever turn happens to be
    open (the user 2026-07-05): an auto-nudge opened a new turn 37s after their stop and the chip wore
    'Interrupting…' for work nobody tried to stop. A turn that STARTED after the click clears the stamp."""

    def setUp(self):
        km._interrupt_clicked.clear()

    def tearDown(self):
        km._interrupt_clicked.clear()

    def test_a_turn_opened_after_the_click_clears_the_stamp(self):
        km._interrupt_clicked[SID] = NOW - 30
        self.assertFalse(km._interrupting(SID, True, NOW, NOW - 10),
                         "the open turn began AFTER the stop click → it is not the interrupted turn")
        self.assertNotIn(SID, km._interrupt_clicked, "stamp consumed, never re-latches")

    def test_the_interrupted_turn_itself_keeps_the_stamp(self):
        km._interrupt_clicked[SID] = NOW - 30
        self.assertTrue(km._interrupting(SID, True, NOW, NOW - 100),
                        "the turn that was running at the click still wears the stamp until it settles")


class AutoNudgeInterruptGate(unittest.TestCase):
    """Auto-nudge NEVER fires off a turn the user interrupted (the user 2026-07-05): the stop record means
    the human is at the controls — a nudge then steals the session (their case: a 2-minute turn on the old
    model) and holds parked drive ops behind it. Likewise a session with PARKED ops (a queued send / model
    pick) is being driven — a nudge would jump the user's queue. Both gates are event-based: the CLI's stop
    record, and the _pending_ops FIFO itself."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        self.tpath = pdir / (SID + ".jsonl")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self.saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATE, km.NAMES, jd.CLOSER_ON)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATE = names, proj, td / "goals", td
        km.NAMES = names
        jd.CLOSER_ON = False              # closer-verdict gate idles → the new gates are what's exercised
        jd.GOALDIR.mkdir(parents=True)
        km._downtime[:] = []
        km._parse_cache.clear()
        km._autonudge_cache.clear()
        km._pending_ops.clear()
        self.tmux = {SID: {"state": "idle", "since": NOW - 100, "model": "", "effort": "",
                           "context": None, "compactPct": None, "color": None}}
        km._set_auto_nudge(True)

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATE, km.NAMES, jd.CLOSER_ON) = self.saved
        km._pending_ops.clear()
        km._parse_cache.clear()
        self.td.cleanup()

    def _transcript(self, interrupted):
        recs = [uline(T0, "first ask", "u1"),
                aline(T0 + 20, "Done.", "a1", "u1", "end_turn"),
                uline(T0 + 100, "second ask", "u2", "a1"),
                aline(T0 + 120, "digging in", "a2", "u2", "tool_use")]
        if interrupted:
            recs.append(uline(T0 + 130, "[Request interrupted by user]", "u3", "a2"))
        else:
            recs.append(aline(T0 + 130, "Finished the second ask.", "a3", "a2", "end_turn"))
        self.tpath.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

    def _goal(self):
        g = SID + ":gw"
        (jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 1, "lastNode": g, "closedTurns": [],
            "nodes": {g: {"id": g, "text": "wire up the thing", "parentId": None, "nodeComplete": False,
                          "blocked": False, "cleared": False, "trail": [], "t": T0}},
            "placements": {}, "status": {g: "working"}}))
        return g

    def _stub(self):
        sent = []
        saved = km._tmux_send, jd.optimistic_followup
        km._tmux_send = lambda name, body, **kw: sent.append((name, body))
        jd.optimistic_followup = lambda sid, gid: True

        def restore():
            km._tmux_send, jd.optimistic_followup = saved
        return sent, restore

    def test_control_a_normally_ended_stall_still_nudges(self):
        # fixture validity: without a stop record or parked ops, this exact setup DOES nudge — so the
        # no-fire asserts below test the gates, not a broken fixture.
        self._transcript(interrupted=False)
        g = self._goal()
        sent, restore = self._stub()
        try:
            km._auto_nudge_tick(NOW, self.tmux)
            self.assertEqual(len(sent), 1, "the orphaned working goal is nudged")
            self.assertIn("romp-goal-id: " + g, sent[0][1])
        finally:
            restore()

    def test_no_nudge_after_a_user_interrupt(self):
        self._transcript(interrupted=True)
        self._goal()
        sent, restore = self._stub()
        try:
            km._auto_nudge_tick(NOW, self.tmux)
            self.assertEqual(sent, [], "the user stopped this turn themselves — they're driving, not stalled")
        finally:
            restore()

    def test_no_nudge_while_drive_ops_are_parked(self):
        self._transcript(interrupted=False)
        self._goal()
        km._pending_ops[SID] = [("model", "fable")]
        sent, restore = self._stub()
        try:
            km._auto_nudge_tick(NOW, self.tmux)
            self.assertEqual(sent, [], "queued user intent outranks a nudge — never jump the user's queue")
        finally:
            restore()

    def _append(self, recs):
        with open(self.tpath, "a") as f:
            f.write("\n".join(json.dumps(r) for r in recs) + "\n")

    def test_a_peer_turn_after_the_interrupt_stays_suppressed(self):
        # requirement (the user 2026-07-05 via ui): suppression lifts on the USER-message event only — a
        # peer postal exchange ending after the interrupt used to make the latest turn read 'genuine' and
        # re-arm the nudge.
        self._transcript(interrupted=True)
        self._append([uline(T0 + 200, "COORDINATE: heads-up\nromp-msg-id: 1111.2_3.TESTHOST", "u4", "u3"),
                      aline(T0 + 220, "acknowledged", "a4", "u4", "end_turn")])
        self._goal()
        sent, restore = self._stub()
        try:
            km._auto_nudge_tick(NOW, self.tmux)
            self.assertEqual(sent, [], "a peer spoke, the user didn't — still their pause, still suppressed")
        finally:
            restore()

    def test_the_users_message_after_the_interrupt_rearms_the_nudge(self):
        self._transcript(interrupted=True)
        self._append([uline(T0 + 200, "keep going with plan B", "u4", "u3"),
                      aline(T0 + 220, "resuming with plan B", "a4", "u4", "end_turn")])
        self._goal()
        sent, restore = self._stub()
        try:
            km._auto_nudge_tick(NOW, self.tmux)
            self.assertEqual(len(sent), 1, "the user re-engaged and the goal re-stalled → nudging resumes")
        finally:
            restore()

    def test_feed_card_wears_the_interrupted_badge(self):
        # the floated badge (the user 2026-07-05): a working card whose session the user stopped says
        # "interrupted" instead of sitting silent like an orphaned goal. Cache-only like the working dot.
        self._transcript(interrupted=True)
        self._goal()
        km._parse(str(self.tpath), SID, NOW)                       # warm the cache (stands in for _warm_fleet_bg)
        card = next(a for a in km.build_feed(NOW, self.tmux)["asks"] if a["itemId"] == SID + ":gw")
        self.assertTrue(card.get("interrupted"), "user-stopped + no message since → interrupted badge")

    def test_feed_badge_clears_once_the_user_re_engages(self):
        self._transcript(interrupted=True)
        self._append([uline(T0 + 200, "keep going with plan B", "u4", "u3")])   # user spoke; turn back open
        self._goal()
        km._parse(str(self.tpath), SID, NOW)
        card = next(a for a in km.build_feed(NOW, self.tmux)["asks"] if a["itemId"] == SID + ":gw")
        self.assertFalse(card.get("interrupted"), "the user's next message retires the badge")
