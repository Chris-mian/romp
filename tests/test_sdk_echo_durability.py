#!/usr/bin/env python3
"""An SDK input echo is the ONLY visible record of a send the transcript hasn't caught up on — since
queued sends forward into the CLI mid-turn (2026-07-17) there is a window where a message is neither
queued nor landed, and the echo must own it (the user 2026-07-20: a reply sat invisible in the chat,
and one message was silently LOST across a kernel restart with no trace anywhere). Four durability
guarantees, each pinned here:
  1. the live-tail overflow cap never evicts an echo (work atoms are disposable; echoes aren't),
  2. the genuine-human-turn floor retires only PATH-BEARING echoes (the image-extraction case whose
     text-match structurally fails) — a plain-text echo prunes only by its own text landing, and a
     dropped send's echo PERSISTS so the loss shows (the tmux echo's semantics),
  3. unlanded echoes mirror to the registry (reg['echoes']) and reseed on backend construction, so a
     kernel restart cannot wipe the only evidence of an in-flight send,
  4. an echo that survives its holder is MARKED dropped at the event that orphaned it (boot reseed /
     fresh CLI spawn), so persistence reads as "never delivered", not as delivered history (the user
     2026-07-29: a two-day-old lost send kept resurfacing mid-chat, posing as an ordinary bubble).
SYNTHETIC fixtures only."""
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
sb = SourceFileLoader("romp_sdk_backend_echo", os.path.join(BIN, "romp_sdk_backend.py")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _echo(text, t=1000, key="echo:k1"):
    return key, {"type": "user", "uuid": key, "session_id": SID, "t": t, "parentUuid": None,
                 "author": "human", "_echo_text": text,
                 "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _work(i):
    return "w%d" % i, {"type": "assistant", "uuid": "w%d" % i, "session_id": SID, "t": 2000 + i,
                       "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}}


class OverflowCapSparesEchoes(unittest.TestCase):
    def test_echo_survives_a_work_atom_flood(self):
        d = {}
        k, e = _echo("the in-flight reply")
        d[k] = e
        for i in range(sb.LIVE_TAIL_CAP + 60):
            wk, w = _work(i)
            d[wk] = w
            sb._evict_live_overflow(d)
        self.assertIn(k, d, "the echo must survive the cap — it is the send's only record")
        self.assertLessEqual(len(d), sb.LIVE_TAIL_CAP)

    def test_all_echo_pathology_still_bounds_memory(self):
        d = {}
        for i in range(sb.LIVE_TAIL_CAP + 20):
            k, e = _echo("msg %d" % i, t=1000 + i, key="echo:%d" % i)
            d[k] = e
        sb._evict_live_overflow(d)
        self.assertLessEqual(len(d), sb.LIVE_TAIL_CAP)


class FloorOnlyRetiresPathBearingEchoes(unittest.TestCase):
    def _backend(self):
        return sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)

    def test_plain_text_echo_survives_a_later_human_turn(self):
        be = self._backend()
        k, e = _echo("please refactor the parser")
        be._live[SID] = dict([(k, e)])
        be.prune_live(SID, tx_uuids=set(), tx_user_texts=set(), human_floor=e["t"] + 100)
        self.assertIn(k, be._live.get(SID, {}),
                      "a plain echo must not be floored away — its message may still be inside the CLI")

    def test_path_bearing_echo_retires_on_the_floor(self):
        # the image-extraction case: the landed record's text can never match, so the floor is the
        # only retire — exactly the 2026-06-25 screenshots-piling-up semantics, now scoped to it
        be = self._backend()
        k, e = _echo("look at ~/Screenshots/shot.png please")
        be._live[SID] = dict([(k, e)])
        be.prune_live(SID, tx_uuids=set(), tx_user_texts=set(), human_floor=e["t"] + 100)
        self.assertNotIn(SID, be._live, "path-bearing echo floors away once a human turn postdates it")

    def test_text_landing_still_prunes_any_echo(self):
        be = self._backend()
        k, e = _echo("please refactor the parser")
        be._live[SID] = dict([(k, e)])
        be.prune_live(SID, tx_uuids=set(), tx_user_texts={"please refactor the parser"}, human_floor=0)
        self.assertNotIn(SID, be._live)

    def test_path_bearing_predicate(self):
        self.assertTrue(sb._path_bearing("see /tmp/x.png"))
        self.assertTrue(sb._path_bearing("~/notes/todo.md is stale"))
        self.assertFalse(sb._path_bearing("just a plain reply, and/or nothing else"))
        self.assertFalse(sb._path_bearing(""))


class EchoesSurviveARestart(unittest.TestCase):
    def test_persist_then_reseed_round_trip(self):
        state = tempfile.mkdtemp()
        be = sb.SdkBackend(state, "/bin/true", lambda *a, **k: None)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("message in flight across the restart")
        be._live[SID] = dict([(k, e)])
        be._persist_echoes(SID)
        reg = sb.read_reg(be.state_dir, SID)
        self.assertEqual([x["text"] for x in reg.get("echoes") or []],
                         ["message in flight across the restart"])
        # "kernel restart": a fresh backend over the same state dir reseeds the echo into its live tail
        be2 = sb.SdkBackend(state, "/bin/true", lambda *a, **k: None)
        atoms = be2.live_atoms(SID)
        self.assertEqual([a.get("_echo_text") for a in atoms],
                         ["message in flight across the restart"])
        self.assertEqual(atoms[0].get("author"), "human")

    def test_landing_empties_the_mirror(self):
        state = tempfile.mkdtemp()
        be = sb.SdkBackend(state, "/bin/true", lambda *a, **k: None)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("lands soon")
        be._live[SID] = dict([(k, e)])
        be._persist_echoes(SID)
        be.prune_live(SID, tx_uuids=set(), tx_user_texts={"lands soon"}, human_floor=0)
        self.assertEqual(sb.read_reg(be.state_dir, SID).get("echoes"), [],
                         "a landed echo leaves the restart mirror too")

    def test_command_feedback_is_never_mirrored(self):
        state = tempfile.mkdtemp()
        be = sb.SdkBackend(state, "/bin/true", lambda *a, **k: None)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        be._live[SID] = {"cmd:1": {"type": "user", "uuid": "cmd:1", "t": 5, "command": "/model",
                                   "_echo_text": "/model opus", "author": "human",
                                   "message": {"role": "user", "content": [{"type": "text", "text": "/model opus"}]}}}
        be._persist_echoes(SID)
        self.assertEqual(sb.read_reg(be.state_dir, SID).get("echoes"), [],
                         "a stale /model confirmation must not replay after a restart")


class DroppedSendsAnnounceThemselves(unittest.TestCase):
    """Guarantee 4 (the user 2026-07-29): an echo that survives its holder is marked `dropped` at the
    exact event that orphaned it — the boot reseed, or a fresh CLI spawning — so the chat can render
    "never delivered" instead of a sent-looking bubble posing as history. A two-day-old lost send kept
    resurfacing mid-chat, hopping turns as new ones landed, its stale timestamp reading as a glitch:
    durable BY DESIGN, but illegible. The marking is self-correcting (a landed text still prunes the
    echo, flag and all) and rides the registry mirror across further restarts."""

    def _backend(self, state=None):
        return sb.SdkBackend(state or tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)

    def test_boot_reseed_marks_an_unqueued_echo_dropped(self):
        state = tempfile.mkdtemp()
        be = self._backend(state)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("the send the dead CLI was holding")
        be._live[SID] = dict([(k, e)])
        be._persist_echoes(SID)
        be2 = self._backend(state)               # "kernel restart": nothing re-delivers this text
        atoms = be2.live_atoms(SID)
        self.assertTrue(atoms and atoms[0].get("dropped"),
                        "a reseeded echo with no queue entry has provably lost its message")
        self.assertTrue((sb.read_reg(state, SID).get("echoes") or [{}])[0].get("dropped"),
                        "the flag rides the mirror, so the NEXT restart keeps the verdict")

    def test_boot_reseed_spares_an_echo_still_in_the_queue(self):
        state = tempfile.mkdtemp()
        be = self._backend(state)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True,
                                         "queue": ["still queued across the restart"]})
        k, e = _echo("still queued across the restart")
        be._live[SID] = dict([(k, e)])
        be._persist_echoes(SID)
        be2 = self._backend(state)               # boot reconcile will re-deliver the queue → not lost
        atoms = be2.live_atoms(SID)
        self.assertTrue(atoms and not atoms[0].get("dropped"),
                        "a queued send is in flight, not lost — it must not read as never-delivered")

    def test_spawn_marking_spares_the_pending_queue(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k1, e1 = _echo("orphaned by the respawn", key="echo:a")
        k2, e2 = _echo("delivered to the fresh CLI", t=1001, key="echo:b")
        be._live[SID] = {k1: e1, k2: e2}
        be._mark_dropped_echoes(SID, ["delivered to the fresh CLI"])
        d = be._live[SID]
        self.assertTrue(d[k1].get("dropped"))
        self.assertFalse(d[k2].get("dropped"))

    def test_spawn_marking_ignores_command_feedback(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        be._live[SID] = {"cmd:1": {"type": "user", "uuid": "cmd:1", "t": 5, "command": "/model",
                                   "_echo_text": "/model opus", "author": "human",
                                   "message": {"role": "user", "content": [{"type": "text", "text": "/model opus"}]}}}
        be._mark_dropped_echoes(SID, [])
        self.assertFalse(be._live[SID]["cmd:1"].get("dropped"),
                         "command feedback is not a lost message; it retires via the command floor")

    def test_a_fresh_cli_spawn_runs_the_marking(self):
        # the spawn half is a call inside Session._run (spawning a real CLI in a unit test is not
        # practical) — pin it the way error-visibility's NoSilentSwallows pins handlers: read the source
        import ast
        import inspect
        run = next(n for n in ast.walk(ast.parse(inspect.getsource(sb)))
                   if isinstance(n, ast.FunctionDef) and n.name == "_run")
        calls = [n.func.attr for n in ast.walk(run)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertIn("_mark_dropped_echoes", calls,
                      "_run no longer marks orphaned echoes when a fresh CLI spawns")

    def test_landing_still_prunes_a_dropped_echo(self):
        # the self-correcting guarantee: a premature mark can never stick to a delivered message
        state = tempfile.mkdtemp()
        be = self._backend(state)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("actually landed after all")
        e["dropped"] = True
        be._live[SID] = dict([(k, e)])
        be._persist_echoes(SID)
        be.prune_live(SID, tx_uuids=set(), tx_user_texts={"actually landed after all"}, human_floor=0)
        self.assertNotIn(SID, be._live)
        self.assertEqual(sb.read_reg(state, SID).get("echoes"), [])

    def test_dismiss_retires_by_key_and_by_send_time(self):
        state = tempfile.mkdtemp()
        be = self._backend(state)
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("seen and dismissed")
        e["dropped"] = True
        be._live[SID] = dict([(k, e)])
        self.assertEqual(be.dismiss_echo(SID, uuid=k), "seen and dismissed")
        self.assertNotIn(SID, be._live)
        self.assertEqual(sb.read_reg(state, SID).get("echoes"), [], "dismissal empties the mirror")
        # by send time: the uuid regenerates at every boot reseed, but t survives it
        k2, e2 = _echo("dismissed after a restart", t=4242, key="echo:regen")
        e2["dropped"] = True
        be._live[SID] = dict([(k2, e2)])
        self.assertEqual(be.dismiss_echo(SID, uuid="echo:stale-painted-key", t=4242),
                         "dismissed after a restart")
        self.assertIsNone(be.dismiss_echo(SID, uuid="echo:stale-painted-key", t=4242),
                          "a second click is an idempotent miss, not an error")

    def test_dismiss_never_touches_a_pending_echo(self):
        be = self._backend()
        sb.write_reg(be.state_dir, SID, {"sid": SID, "alive": True})
        k, e = _echo("still in flight")
        be._live[SID] = dict([(k, e)])
        self.assertIsNone(be.dismiss_echo(SID, uuid=k, t=e["t"]),
                          "an undropped echo is the send's only record — undismissable")
        self.assertIn(k, be._live[SID])


if __name__ == "__main__":
    unittest.main()
