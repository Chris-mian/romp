#!/usr/bin/env python3
"""Kernel-side settings across attached machines (T248b, and since 2026-09-18 plans/settings-across-machines.md, phase one A).

The seam is the tunnel supervisor's poll: it lifts each up peer's /version "settings", "settingsGt" and (one A) "settingsPinned"
onto the peer's /tunnels row and hands them to _propose_peer_settings. Until one A the leg ADOPTED: a peer's stamp newer than
the local store's applied the peer's value through the setting's own gt-gated setter (the user's task tracking turned off when
a new machine attached with it off). Now a newer stamp with a DIFFERENT value raises a PROPOSAL record (settings-proposals.json:
the host, the value, the peer's stamp, the local value at the time) and applies NOTHING; the same value under a newer stamp still
lifts the local stamp only (it shows the user nothing, and it keeps a later local click from being proposed back); a store this
machine PINNED (settings-pins.json) raises none; a stamp the user KEPT against is not proposed again; the record drops when the
values come to equal or the peer's stamp is no longer newer. The user answers through /setting-proposal (apply: the setter under
the peer's stamp; keep; pin). A remote-origin gear click on a pinned store stands down with a settingStale frame, why pinned.

Two hermetic "kernels" here are two state roots served by one loaded module (jd.STATE swapped per call), which is exactly what
the seam sees: a peer is its /version dict, nothing more, and one class drives that dict through the REAL poll. Synthetic host
names, loopback only, no live state.
"""
import contextlib
import inspect
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from romp_load import load_source
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_mesh_adopt", os.path.join(BIN, "romp-kernel"))
jd = km.jd

KERNEL_SRC = open(os.path.join(BIN, "romp-kernel")).read()
SETTERS = {"compact-suggest": km._set_compact_suggest, "auto-nudge": km._set_auto_nudge, "file-editing": km._set_file_editing,
           "task-tracking": km._set_task_tracking}   # the Task tracking switch joined the road with T404 round two
READERS = {"compact-suggest": km._compact_suggest_on, "auto-nudge": km._auto_nudge_on, "file-editing": km._file_editing_on,
           "task-tracking": km._task_tracking_on}
KEYS = {"compact-suggest": "compactSuggest", "auto-nudge": "autoNudge", "file-editing": "fileEditing", "task-tracking": "taskTracking"}


class _Kernel:
    """One hermetic state root; `with k:` makes the loaded module act as that kernel."""

    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._saved = []   # a STACK: `with k:` nests (a helper called inside a block re-enters the same
        #                    kernel), and a single slot left jd.STATE on this root after the outer exit — the
        #                    next module then wrote under a deleted temp dir (CI + the full run, 2026-09-08)

    def __enter__(self):
        self._saved.append(jd.STATE)
        jd.STATE = self.root
        km._autonudge_cache.clear()
        return self

    def __exit__(self, *a):
        km._autonudge_cache.clear()
        jd.STATE = self._saved.pop()

    def version(self):
        """What this kernel's /version says to a polling peer: the settings dict + every store's stamp."""
        with self:
            return {"settings": {KEYS[n]: READERS[n]() for n in KEYS}, "settingsGt": km._settings_gt(),
                    "settingsPinned": self._opt("_settings_pinned_map", dict)()}   # one A: the pins ride /version too

    def set(self, store, value, gt):
        with self:
            return SETTERS[store](value, gt=gt)

    def read(self, store):
        with self:
            return READERS[store](), km._setting_stored_gt(store)

    def propose(self, host, rver):
        """The poll's inbound leg: the stores with a PENDING proposal after the pass, and what was said. Reached through
        getattr with the base's adopter as the fallback, so a copy of this file at the base runs the base's road and reds on
        what it DID (the store moved), not on a name."""
        with self:
            err = io.StringIO()
            leg = getattr(km, "_propose_peer_settings", None) or getattr(km, "_adopt_peer_settings")
            with contextlib.redirect_stderr(err):
                out = leg(host, rver)
            return out, err.getvalue()

    @staticmethod
    def _opt(name, default):
        return getattr(km, name, None) or default

    def proposals(self):
        with self:
            return self._opt("_settings_proposals_map", dict)()

    def records(self):
        with self:
            return km._settings_proposals()

    def pins(self):
        with self:
            return self._opt("_settings_pinned_map", dict)()

    def pin(self, store, pinned, gt):
        with self:
            try:
                return km._set_setting_pin(store, pinned, gt=gt, origin="local")   # round two: a pin takes the local origin alone
            except TypeError:                                                      # the first cut's pin knew no origin: its road
                return km._set_setting_pin(store, pinned, gt=gt)

    def push(self, host, store, value, gt):
        """A peer's push landing here: /mesh-settings' applier, the body naming the pusher as it names itself."""
        key = [k for k, s, _f in km._MESH_ADOPTED_SETTINGS if s == store][0]
        with self:
            with contextlib.redirect_stderr(io.StringIO()):
                return km._apply_mesh_settings({key: value, "gt": gt, "host": host})

    def answer(self, body):
        with self:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                return km._answer_setting_proposal(body)

    def notices(self):
        with self:
            return [r["text"] for r in km._sync_notice_rows(limit=50)]

    def close(self):
        self.td.cleanup()


class ProposePeerSettings(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _Kernel(), _Kernel()
        with self.a:
            km._SYNC_NOTICES[:] = []

    def tearDown(self):
        self.a.close(); self.b.close()

    def test_a_newer_peer_pick_is_a_proposal_and_the_local_store_does_not_move(self):
        """The user's incident (2026-09-18): a new machine attached with task tracking off and the local switch went off too.
        One A: the newer remote value is a record the user answers, and the store is byte for byte what it was."""
        self.a.set("compact-suggest", False, 1_000)
        self.b.set("compact-suggest", True, 2_000)
        pending, err = self.a.propose("TESTHOST", self.b.version())
        self.assertEqual(pending, ["compact-suggest"])
        self.assertEqual(self.a.read("compact-suggest"), (False, 1_000), "nothing applied: the local value and stamp stand (the base adopted True under 2000)")
        self.assertEqual(self.a.proposals(), {"compact-suggest": [{"host": "TESTHOST", "value": True, "gt": 2_000, "current": False}]},
                         "the record: which machine, what value, under which stamp, against which local value")
        self.assertIn("TESTHOST", err); self.assertIn("nothing applied", err)
        self.assertEqual([n for n in self.a.notices() if "proposes" in n],
                         ["TESTHOST proposes turning Suggest /compact on (this machine has it off); Apply or Keep mine in Settings"],
                         "the interim alert: one sync notice, in the user's terms (one B replaces it with the card)")
        pending2, _ = self.a.propose("TESTHOST", self.b.version())
        self.assertEqual(pending2, ["compact-suggest"], "the second poll finds the record standing")
        self.assertEqual(len([n for n in self.a.notices() if "proposes" in n]), 1, "…and says nothing again for the same stamp")

    def test_a_moved_proposal_is_refreshed_and_said_once_more(self):
        self.a.set("compact-suggest", False, 1_000)
        self.b.set("compact-suggest", True, 2_000)
        self.a.propose("TESTHOST", self.b.version())
        self.b.set("compact-suggest", True, 2_500)              # the other machine clicked again
        self.a.propose("TESTHOST", self.b.version())
        self.assertEqual(self.a.proposals()["compact-suggest"][0]["gt"], 2_500, "the record follows the peer's stamp")
        self.assertEqual(len([n for n in self.a.notices() if "proposes" in n]), 2)
        self.assertIn("(the proposal moved)", self.a.notices()[-1])

    def test_an_older_or_equal_peer_stamp_raises_nothing(self):
        self.a.set("compact-suggest", True, 3_000)
        self.b.set("compact-suggest", False, 2_000)
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [])
        self.assertEqual(self.a.proposals(), {})
        rver = {"settings": {"compactSuggest": False}, "settingsGt": {"compact-suggest": 3_000}}   # equal stamp, other value
        self.assertEqual(self.a.propose("TESTHOST", rver)[0], [], "an equal stamp is not newer: no proposal (determinism)")
        self.assertEqual(self.a.read("compact-suggest"), (True, 3_000))
        with self.a:
            self.assertIsNone(km._pop_stale_notice(), "no delivering socket here: no verdict leaks to the next WS gesture")

    def test_the_same_value_under_a_newer_stamp_lifts_the_local_stamp_and_raises_nothing(self):
        # the value already agrees, but the STAMP is newer: lift it, or the local dashboard, which mints its next gesture
        # above the local kernel's stamps only, clicks below the peer's stamp and is proposed back one pass later
        self.a.set("compact-suggest", True, 5_000)
        self.b.set("compact-suggest", True, 7_000)
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [])
        self.assertEqual(self.a.read("compact-suggest"), (True, 7_000), "same value, the peer's stamp; nothing to show the user")
        self.assertEqual(self.a.proposals(), {})

    def test_a_pinned_store_raises_no_proposal(self):
        self.a.set("compact-suggest", False, 1_000)
        self.assertEqual(self.a.pin("compact-suggest", True, 1_500), 1_500)
        self.b.set("compact-suggest", True, 2_000)
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [])
        self.assertEqual(self.a.proposals(), {}); self.assertEqual(self.a.pins(), {"compact-suggest": True})
        self.assertEqual(self.a.read("compact-suggest"), (False, 1_000))

    def test_the_record_drops_when_the_divergence_ends(self):
        self.a.set("compact-suggest", False, 1_000)
        self.b.set("compact-suggest", True, 2_000)
        self.a.propose("TESTHOST", self.b.version())
        self.assertIn("compact-suggest", self.a.proposals())
        self.b.set("compact-suggest", False, 3_000)              # the other machine came back to ours
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [])
        self.assertEqual(self.a.proposals(), {}, "the values agree: nothing pending")
        self.assertEqual(self.a.read("compact-suggest"), (False, 3_000), "…and the same value lifted the stamp")

    def test_a_non_finite_stamp_skips_only_its_own_setting(self):
        self.b.set("file-editing", True, 2_000)
        rver = {"settings": {"compactSuggest": True, "fileEditing": True},
                "settingsGt": {"compact-suggest": float("nan"), "file-editing": 2_000}}
        self.assertEqual(self.a.propose("TESTHOST", rver)[0], ["file-editing"])
        rver["settingsGt"]["compact-suggest"] = float("inf")
        self.assertEqual(sorted(self.a.propose("TESTHOST", rver)[0]), ["file-editing"], "…and inf is not a stamp either")

    def test_an_older_kernel_or_a_junk_dict_proposes_nothing(self):
        self.a.set("compact-suggest", False, 1_000)
        for rver in (None, {}, {"settings": {"compactSuggest": True}},
                     {"settings": {"compactSuggest": True}, "settingsGt": {}},
                     {"settings": {"compactSuggest": "yes"}, "settingsGt": {"compact-suggest": 9_000}},
                     {"settings": {"compactSuggest": True}, "settingsGt": {"compact-suggest": "9000"}},
                     {"settings": "x", "settingsGt": {"compact-suggest": 9_000}}):
            self.assertEqual(self.a.propose("TESTHOST", rver)[0], [], repr(rver))
        self.assertEqual(self.a.proposals(), {})

    def test_two_machines_each_propose_to_the_other_and_one_apply_ends_it(self):
        self.a.set("compact-suggest", False, 1_000)
        self.b.set("compact-suggest", True, 2_000)
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], ["compact-suggest"])
        self.assertEqual(self.b.propose("TESTHOST2", self.a.version())[0], [], "b holds the newer stamp: a's older value is nothing to it")
        ack = self.a.answer({"store": "compact-suggest", "gt": 2_000, "answer": "apply"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual(self.a.read("compact-suggest"), (True, 2_000), "applied under the PEER's stamp: one value, one stamp")
        self.assertEqual(self.a.proposals(), {})
        self.assertEqual(self.b.propose("TESTHOST2", self.a.version())[0], [], "equal stamps: nothing proposed back, no ping-pong")

    def test_all_four_settings_propose_the_same_way(self):
        for store in ("auto-nudge", "file-editing", "task-tracking", "compact-suggest"):
            default = self.a.read(store)[0]
            self.b.set(store, not default, 2_000)
            pending, _ = self.a.propose("TESTHOST", self.b.version())
            self.assertIn(store, pending, store)
            self.assertEqual(self.a.read(store)[0], default, store + ": the local value stands")
            self.assertEqual(self.a.proposals()[store][0]["value"], not default, store)


class TheAnswers(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _Kernel(), _Kernel()
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000)
        self.a.propose("TESTHOST", self.b.version())

    def tearDown(self):
        self.a.close(); self.b.close()

    def test_apply_runs_the_setter_under_the_peers_stamp_and_drops_the_record(self):
        ack = self.a.answer({"store": "task-tracking", "gt": 2_000, "answer": "apply"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual(self.a.read("task-tracking"), (False, 2_000))
        self.assertEqual((ack["settings"]["taskTracking"], ack["settingsGt"]["task-tracking"], ack["settingsProposals"]), (False, 2_000, {}))

    def test_keep_drops_the_record_and_the_same_stamp_is_not_proposed_again(self):
        ack = self.a.answer({"store": "task-tracking", "gt": 2_000, "answer": "keep"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual(self.a.read("task-tracking"), (True, 1_000), "nothing applied")
        self.assertEqual(self.a.proposals(), {})
        self.assertEqual(self.a.records()["task-tracking"], {"hosts": {}, "answered": {"TESTHOST": 2_000}}, "the stamp is remembered as answered, per machine")
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [], "the next poll with the same stamp raises nothing")
        self.b.set("task-tracking", False, 3_000)               # a newer click on the other machine
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], ["task-tracking"], "…a newer stamp raises a fresh one")

    def test_pin_sets_the_pin_drops_the_record_and_the_next_poll_raises_nothing(self):
        ack = self.a.answer({"store": "task-tracking", "gt": 2_000, "answer": "pin"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual(ack["settingsPinned"], {"task-tracking": True}); self.assertEqual(ack["settingsProposals"], {})
        self.assertEqual(self.a.read("task-tracking"), (True, 1_000))
        self.b.set("task-tracking", False, 3_000)
        self.assertEqual(self.a.propose("TESTHOST", self.b.version())[0], [], "pinned: no proposal for any newer stamp")

    def test_a_stale_gt_an_unknown_store_and_a_bad_answer_are_refused_with_the_reason(self):
        for body, why in (({"store": "task-tracking", "gt": 1_999, "answer": "apply"}, "TESTHOST changed its mind since this line was drawn"),
                          ({"store": "task-tracking", "host": "TESTHOSTX", "gt": 2_000, "answer": "apply"}, "no proposal is pending for task-tracking from TESTHOSTX"),
                          ({"store": "judge-model", "gt": 2_000, "answer": "apply"}, "not a synchronized setting"),
                          ({"store": "task-tracking", "gt": 2_000, "answer": "later"}, "apply, keep or pin"),
                          ({"store": "auto-nudge", "gt": 2_000, "answer": "apply"}, "no proposal is pending"),
                          ("junk", "a JSON object")):
            ack = self.a.answer(body)
            self.assertFalse(ack["ok"], body); self.assertIn(why, ack["error"], body)
        self.assertEqual(self.a.read("task-tracking"), (True, 1_000), "nothing applied by any refusal")
        self.assertIn("task-tracking", self.a.proposals(), "the record stands")


class ThePinGate(unittest.TestCase):
    """A remote machine's gear click on a store this machine pinned stands down BEFORE the stale check, and only for a gesture
    whose origin is not this dashboard's own kernel; the delivering socket hears it as a settingStale frame, why pinned."""

    def setUp(self):
        self.a = _Kernel()
        self.a.set("task-tracking", True, 1_000)
        self.assertEqual(self.a.pin("task-tracking", True, 1_100), 1_100)

    def tearDown(self):
        self.a.close()

    def test_a_remote_origin_click_stands_down_and_the_refusal_names_the_pin(self):
        with self.a:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertIsNone(km._set_task_tracking(False, gt=5_000, origin="remote"))
            self.assertEqual(self.a.read("task-tracking"), (True, 1_000), "the pinned value stands against a NEWER remote stamp")
            rf = km._pop_refused_notice()
            self.assertEqual((rf["setting"], rf["gt"], rf["why"], rf["known"], rf["pinned"]), ("task-tracking", 5_000, "pinned on this machine", True, True), rf)
            self.assertIn("pinned on this machine", err.getvalue())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertIsNone(km._set_task_tracking(False, gt=5_001), "a message without an origin is read as remote")
            km._pop_refused_notice()

    def test_a_local_click_applies_as_ever(self):
        with self.a:
            self.assertEqual(km._set_task_tracking(False, gt=5_000, origin="local"), 5_000)
            self.assertEqual(self.a.read("task-tracking"), (False, 5_000))
            self.assertIsNone(km._pop_refused_notice(), "nothing refused")

    def test_the_gate_reads_the_pin_before_the_stale_check_in_every_setter(self):
        for fn, store in ((km._set_auto_nudge, "auto-nudge"), (km._set_compact_suggest, "compact-suggest"),
                          (km._set_file_editing, "file-editing"), (km._set_task_tracking, "task-tracking")):
            src = inspect.getsource(fn)
            self.assertIn('_pinned_stand_down("%s", gt, enabled, ' % store, src, store)
            self.assertLess(src.index("_pinned_stand_down("), src.index('_setting_stale("%s"' % store), store + ": the pin before the stale check")
            self.assertGreater(src.index("_pinned_stand_down("), src.index("_gesture_echo("), store + ": after the echo (an echo is nothing to refuse)")
        self.assertIn('if origin == "local" or not _setting_pinned(store):\n        return False', inspect.getsource(km._pinned_stand_down))

    def test_the_pin_itself_is_gt_gated_and_never_broadcast(self):
        with self.a:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertIsNone(km._set_setting_pin("task-tracking", True, gt=1_050, origin="local"), "a stale pin gesture stands down")
            self.assertIn("stale gesture stood down (gesture 1050 <= applied 1100)", err.getvalue())
            self.assertIsNone(km._pop_stale_notice(), "…and files NO settingStale frame: pin:<store> is outside the gear's vocabulary (round two)")
            self.assertIsNone(km._pop_refused_notice())
            self.assertIsNone(km._set_setting_pin("task-tracking", True, gt=1_100, origin="local"), "an equal stamp with the same state is an echo")
            self.assertEqual(km._set_setting_pin("task-tracking", False, gt=1_200, origin="local"), 1_200)
            self.assertEqual(km._settings_pinned_map(), {})
            with contextlib.redirect_stderr(err):
                self.assertIsNone(km._set_setting_pin("task-tracking", True, gt=1_250), "a pin without a local origin stands down (round two)")
                self.assertIsNone(km._set_setting_pin("task-tracking", True, gt=1_260, origin="remote"))
            self.assertEqual(km._settings_pinned_map(), {}, "…and nothing was pinned")
            self.assertIn("this machine's own dashboard alone", err.getvalue())
            self.assertIsNone(km._set_setting_pin("judge-model", True, gt=1_300, origin="local"), "only a synchronized store pins")
        self.assertIn('msg.get("type") == "setSettingPin"', KERNEL_SRC)
        self.assertIn('_set_setting_pin(str(msg.get("store")), pinned, gt=_gesture_ms(msg), origin=msg.get("origin"))', KERNEL_SRC, "the arm hands the origin over")
        self.assertIn('if (msg.type === "setSettingPin") return [{ host: LOCAL, msg: { ...msg, origin: "local" } }];',
                      open(os.path.join(os.path.dirname(BIN), "ui", "webview", "federation.ts")).read(), "federation stamps the pin local, to the local kernel alone")
        self.assertNotIn("setSettingPin", open(os.path.join(os.path.dirname(BIN), "ui", "webview", "federation.ts")).read().split("const KERNEL_SETTING")[1].split(");")[0],
                         "a pin is per machine: never a KERNEL_SETTING")


class RoundTwo(unittest.TestCase):
    """The verifier's finds on the first cut (2026-09-19): one record slot per store flapped between two proposing machines
    with a notice every pass and Keep mine never sticking; the poll and the push named one peer two ways; the pin's stand-down
    read as a file fault; Apply answered ok over a newer local click; the line printed a stale local value; the pin took any
    origin and filed a frame the gear cannot name; the exempt /version served another machine's name to a token-less caller."""

    def setUp(self):
        self.a, self.b, self.c = _Kernel(), _Kernel(), _Kernel()
        with self.a:
            km._SYNC_NOTICES[:] = []
        getattr(km, "_PEER_SELF_NAMES", {}).clear()   # round two's global map (gone in round three: the row carries the name)
        with km._remotes_lock:
            self._rows = dict(km._remotes); km._remotes.clear()

    def tearDown(self):
        getattr(km, "_PEER_SELF_NAMES", {}).clear()
        with km._remotes_lock:
            km._remotes.clear(); km._remotes.update(self._rows)
        self.a.close(); self.b.close(); self.c.close()

    def _said(self):
        return [n for n in self.a.notices() if "proposes" in n]

    def test_two_machines_proposing_one_store_hold_one_record_each_and_are_said_once_each(self):
        # the verifier's drive: A on@1000 polling B (off@2000) and C (off@3000) drew notices 2, 4, 6, 8 after four passes, the
        # record flapping B/C for ever; after Keep, B was re-proposed and re-notified on three consecutive passes
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000)
        self.c.set("task-tracking", False, 3_000)
        for _pass in range(4):
            self.assertEqual(self.a.propose("TESTHOSTB", self.b.version())[0], ["task-tracking"])
            self.assertEqual(self.a.propose("TESTHOSTC", self.c.version())[0], ["task-tracking"])
        self.assertEqual(len(self._said()), 2, "one notice per RECORD, two machines, four passes: %r" % self._said())
        self.assertEqual(self.a.proposals(), {"task-tracking": [{"host": "TESTHOSTC", "value": False, "gt": 3_000, "current": True},
                                                                {"host": "TESTHOSTB", "value": False, "gt": 2_000, "current": True}]},
                         "both records stand, newest stamp first")
        self.assertEqual(self.a.read("task-tracking"), (True, 1_000))
        ack = self.a.answer({"store": "task-tracking", "host": "TESTHOSTB", "gt": 2_000, "answer": "keep"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual([r["host"] for r in ack["settingsProposals"]["task-tracking"]], ["TESTHOSTC"], "Keep mine answers B's record alone")
        for _pass in range(3):
            self.a.propose("TESTHOSTB", self.b.version()); self.a.propose("TESTHOSTC", self.c.version())
        self.assertEqual([r["host"] for r in self.a.proposals()["task-tracking"]], ["TESTHOSTC"], "Keep sticks: B is not re-proposed under the kept stamp")
        self.assertEqual(len(self._said()), 2, "…and nothing more is said")
        ack = self.a.answer({"store": "task-tracking", "gt": 3_000, "answer": "keep"})
        self.assertTrue(ack["ok"], "with one record left the body need not name the machine: %r" % ack)
        self.assertEqual(self.a.proposals(), {})
        self.assertEqual(self.a.records()["task-tracking"], {"hosts": {}, "answered": {"TESTHOSTB": 2_000, "TESTHOSTC": 3_000}})
        self.assertFalse(self.a.answer({"store": "task-tracking", "gt": 3_000, "answer": "keep"})["ok"], "nothing pending now")

    def test_two_records_need_the_machine_named_and_one_apply_drops_every_record_holding_that_value(self):
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000); self.c.set("task-tracking", False, 3_000)
        self.a.propose("TESTHOSTB", self.b.version()); self.a.propose("TESTHOSTC", self.c.version())
        ack = self.a.answer({"store": "task-tracking", "gt": 2_000, "answer": "apply"})
        self.assertFalse(ack["ok"]); self.assertIn("name the machine", ack["error"])
        ack = self.a.answer({"store": "task-tracking", "host": "TESTHOSTB", "gt": 2_000, "answer": "apply"})
        self.assertTrue(ack["ok"], ack)
        self.assertEqual(self.a.read("task-tracking"), (False, 2_000), "applied under B's stamp")
        self.assertEqual(ack["settingsProposals"], {}, "C proposed the value now held: its record dropped with B's")

    def test_the_poll_and_the_push_name_one_peer_one_way(self):
        # the poll names the peer by its remotes-row key (the alias the user attached it under); the push names itself by its own
        # name; the token-gated /version carries that name, so the poll teaches the mapping and the push lands on the same record
        self.a.set("compact-suggest", False, 1_000)
        self.b.set("compact-suggest", True, 2_000)
        rver = dict(self.b.version(), host="TESTHOSTB")     # what the poll reads off B's /version with the token
        with km._remotes_lock:
            km._remotes["peer-alias"] = {"host": "peer-alias", "status": "up"}
        with self.a:
            km._learn_peer_name(km._remotes["peer-alias"], "TESTHOSTB")   # what _converge_peer_settings does with the answer
        self.assertEqual(self.a.propose("peer-alias", rver)[0], ["compact-suggest"])
        ack = self.a.push("TESTHOSTB", "compact-suggest", True, 2_000)   # B pushes the same pick, naming itself
        self.assertEqual([r["host"] for r in ack["settingsProposals"]["compact-suggest"]], ["peer-alias"], "one record, under the row's key")
        self.assertEqual(len(self._said()), 1, "said once: the push found the poll's record standing")
        self.b.set("compact-suggest", True, 2_500)
        self.a.push("TESTHOSTB", "compact-suggest", True, 2_500)          # B clicked again and pushes first
        self.assertEqual(self.a.proposals()["compact-suggest"], [{"host": "peer-alias", "value": True, "gt": 2_500, "current": False}])
        self.assertEqual(len(self._said()), 2, "the moved stamp is one more revision of the ONE record")
        self.a.propose("peer-alias", dict(self.b.version(), host="TESTHOSTB"))
        self.assertEqual(len(self._said()), 2, "…and the poll then finds it standing")
        with self.a:
            self.assertEqual(km._peer_key("TESTHOSTB"), "peer-alias"); self.assertEqual(km._peer_key("TESTHOSTZ"), "TESTHOSTZ")
            self.assertEqual(km._remotes["peer-alias"]["self_name"], "TESTHOSTB", "the lesson is on the ROW (round three)")
            self.assertIn("self_name", km._remotes_rows_for_save()[0], "…and persists with it")

    def test_apply_over_a_newer_local_click_is_refused_and_drops_the_record(self):
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000)
        self.a.propose("TESTHOSTB", self.b.version())
        self.a.set("task-tracking", True, 2_500)               # the user clicked here after the line was drawn (the same value)
        ack = self.a.answer({"store": "task-tracking", "gt": 2_000, "answer": "apply"})
        self.assertFalse(ack["ok"]); self.assertEqual(ack["error"], "your own newer choice stands; the proposal is dropped")
        self.assertEqual(self.a.read("task-tracking"), (True, 2_500), "nothing applied")
        self.assertEqual(ack["settingsProposals"], {}, "the record is gone")

    def test_the_line_reads_the_live_local_value_and_a_local_click_to_the_proposed_value_ends_it(self):
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000)
        self.a.propose("TESTHOSTB", self.b.version())
        self.assertEqual(self.a.proposals()["task-tracking"][0]["current"], True)
        self.a.set("task-tracking", False, 2_500)              # the user took the proposed value by their own click
        self.assertEqual(self.a.proposals()["task-tracking"][0]["current"], False, "the line says what the control shows, not the raise-time value")
        self.assertEqual(self.a.propose("TESTHOSTB", self.b.version())[0], [], "the next pass: the values agree, the record drops")
        self.assertEqual(self.a.proposals(), {})

    def test_the_pins_stand_down_rides_its_own_field_and_files_no_problem_row(self):
        self.a.set("task-tracking", True, 1_000); self.a.pin("task-tracking", True, 1_100)
        frames, problems = [], []
        with self.a:
            saved = km._reply, km._sdk_problem
            km._reply = lambda client, frame: frames.append(frame); km._sdk_problem = lambda text, **kw: problems.append(text)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertIsNone(km._set_task_tracking(False, gt=5_000, origin="remote"))
                    km._tell_stale_gesture(object(), {"type": "setTaskTracking", "enabled": False, "gt": 5_000, "origin": "remote"})
            finally:
                km._reply, km._sdk_problem = saved
        self.assertEqual(len(frames), 1, frames)
        f = frames[0]
        self.assertEqual((f["type"], f["setting"], f["pinned"], f["kept"], f["gt"]), ("settingStale", "task-tracking", True, True, 5_000), f)
        self.assertNotIn("why", f, "no `why`: the gear rendered any why as a file fault (the toast claimed the settings file could not be read)")
        self.assertEqual(f["gesture"], {"type": "setTaskTracking", "enabled": False, "origin": "remote"})
        self.assertEqual(problems, [], "a pin is not a fault: no error-center row")

    def test_version_serves_the_proposals_and_this_machines_name_to_the_token_alone(self):
        self.a.set("task-tracking", True, 1_000); self.b.set("task-tracking", False, 2_000)
        self.a.propose("TESTHOSTB", self.b.version())
        with self.a:
            bare, authed = km._version_info(), km._version_info(authed=True)
        self.assertNotIn("settingsProposals", bare, "a token-less caller of the exempt route learns no other machine's name")
        self.assertNotIn("host", bare)
        self.assertEqual(authed["settingsProposals"]["task-tracking"][0]["host"], "TESTHOSTB")
        self.assertEqual(authed["host"], km._self_host())
        self.assertEqual(bare["settingsPinned"], authed["settingsPinned"], "the pins ride both (no names in them)")


class RoundThree(unittest.TestCase):
    """The verifier's finds on round two (2026-09-19): the self-name mapping healed nothing already recorded and lived in memory,
    so a push that beat the first poll (first contact, a restart) left one machine two records and re-raised a kept stamp; the
    first cut's answered-only record migrated into a machine named gt; the gear drew the lines oldest first; a global map let
    a row attached under another machine's own name capture its records."""

    def setUp(self):
        self.a, self.b, self.c = _Kernel(), _Kernel(), _Kernel()
        with self.a:
            km._SYNC_NOTICES[:] = []
        with km._remotes_lock:
            self._rows = dict(km._remotes); km._remotes.clear()
            km._remotes["hostb"] = {"host": "hostb", "status": "up", "local_port": 51000, "token": "tok", "trust": "directed"}
        self.a.set("task-tracking", True, 1_000)
        self.b.set("task-tracking", False, 2_000)

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.clear(); km._remotes.update(self._rows)
        self.a.close(); self.b.close(); self.c.close()

    def _said(self):
        return [n for n in self.a.notices() if "proposes" in n]

    def _poll(self, row_key="hostb", peer=None, self_name="TESTHOSTB"):
        """A's supervisor step for the row: the answer B gives with the token (its own name beside its settings)."""
        peer = peer or self.b
        with self.a:
            with contextlib.redirect_stderr(io.StringIO()):
                return km._converge_peer_settings(km._remotes[row_key], dict(peer.version(), host=self_name), sync=True)

    def test_a_push_before_the_first_poll_is_re_keyed_onto_the_row_when_the_poll_learns_the_name(self):
        # first contact: B's push beats A's first poll of it, so the record is filed under B's own name; the poll then learns
        # the name and the record MOVES onto the row key; no second record, no second notice (round two left both standing)
        self.a.push("TESTHOSTB", "task-tracking", False, 2_000)
        self.assertEqual(sorted(self.a.records()["task-tracking"]["hosts"]), ["TESTHOSTB"], "no row knows the name yet: filed under it")
        for _pass in range(3):
            self._poll(); self.a.push("TESTHOSTB", "task-tracking", False, 2_000)
        self.assertEqual(sorted(self.a.records()["task-tracking"]["hosts"]), ["hostb"], "ONE record, under the row key")
        self.assertEqual([r["host"] for r in self.a.proposals()["task-tracking"]], ["hostb"], "the gear draws one line for one machine")
        self.assertEqual(len(self._said()), 1, "said once: %r" % self._said())
        self.assertEqual(km._remotes["hostb"]["self_name"], "TESTHOSTB")

    def test_keep_then_a_restart_then_the_push_wins_the_race_and_the_kept_stamp_holds(self):
        self._poll()
        ack = self.a.answer({"store": "task-tracking", "host": "hostb", "gt": 2_000, "answer": "keep"})
        self.assertTrue(ack["ok"], ack)
        said = len(self._said())
        # the restart: memory gone, the rows come back from remotes.json with the learned name, the file of records stays
        saved = km._remotes_rows_for_save()
        self.assertEqual(saved[0].get("self_name"), "TESTHOSTB", "the name persists with the row")
        with km._remotes_lock:
            km._remotes.clear(); km._remotes.update({r["host"]: dict(r) for r in saved})
        self.a.push("TESTHOSTB", "task-tracking", False, 2_000)      # B's push beats the first poll after the restart
        self.assertEqual(self.a.records()["task-tracking"], {"hosts": {}, "answered": {"hostb": 2_000}}, "the kept stamp holds: nothing raised")
        self._poll()
        self.assertEqual(self.a.proposals(), {}); self.assertEqual(len(self._said()), said, "nothing said again")
        self.assertFalse(hasattr(km, "_PEER_SELF_NAMES"), "no memory-only map remains")

    def test_a_row_attached_under_another_machines_own_name_keeps_its_own_records(self):
        # C is attached under the alias TESTHOSTB, which is B's own name; B's row is hostb. Round two's global map keyed by
        # the self-name sent C's poll to hostb and drew it as B
        self.c.set("task-tracking", False, 3_000)
        with km._remotes_lock:
            km._remotes["TESTHOSTB"] = {"host": "TESTHOSTB", "status": "up", "local_port": 51001, "token": "tok2", "trust": "directed"}
        self._poll()                                                  # B under hostb, self-name TESTHOSTB learned on hostb's row
        self._poll(row_key="TESTHOSTB", peer=self.c, self_name="TESTHOSTC")
        self.assertEqual(self.a.records()["task-tracking"]["hosts"]["TESTHOSTB"]["gt"], 3_000, "C's record under C's row key")
        self.assertEqual(self.a.records()["task-tracking"]["hosts"]["hostb"]["gt"], 2_000, "B's under B's")
        self.a.push("TESTHOSTB", "task-tracking", False, 2_000)      # B's push names itself: resolves to hostb, not to C's row
        self.assertEqual(self.a.records()["task-tracking"]["hosts"]["TESTHOSTB"]["gt"], 3_000, "C's record untouched by B's push")
        with self.a:
            self.assertEqual(km._peer_key("TESTHOSTB"), "hostb"); self.assertEqual(km._peer_key("TESTHOSTC"), "TESTHOSTB")

    def test_a_detached_row_takes_its_records_and_kept_stamps_with_it(self):
        self._poll()
        self.assertIn("hostb", self.a.records()["task-tracking"]["hosts"])
        with self.a:
            self.assertTrue(km._forget_peer_proposals("hostb"))
        self.assertEqual(self.a.records(), {}, "gone with the row")
        self.assertIn("_forget_peer_proposals(host)", inspect.getsource(km.detach_remote), "detach_remote forgets them")
        with self.a:
            self.assertFalse(km._forget_peer_proposals("hostb"), "nothing to forget twice")

    def test_the_first_cuts_answered_only_record_migrates_to_the_one_machine_or_to_nothing(self):
        with self.a:
            (self.a.root / km.SETTINGS_PROPOSALS_FILE).write_text(json.dumps({
                "task-tracking": {"answered": {"gt": 2_000}},
                "auto-nudge": {"hosts": {"hostb": {"value": True, "gt": 5_000, "seen": 1, "current": False}}, "answered": {"gt": 4_000}}}))
        recs = self.a.records()
        self.assertEqual(recs["task-tracking"], {"hosts": {}, "answered": {}}, "no machine named gt; a stamp no machine is named for is forgotten")
        self.assertEqual(recs["auto-nudge"]["answered"], {"hostb": 4_000}, "the one recorded machine takes the kept stamp")


class _FakePeer(BaseHTTPRequestHandler):
    """A stand-in peer kernel: /version answers with whatever PAYLOAD holds (the loopback shape
    tests/test_auto_nudge_every_kernel.py uses)."""
    PAYLOAD = {}

    def do_GET(self):
        body = json.dumps(self.PAYLOAD).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class ThroughTheRealPoll(unittest.TestCase):
    """The dict the supervisor hands to _propose_peer_settings is _poll_remote_version's return, not the
    peer's /version JSON: the poll must carry the stamps across, or nothing ever converges."""

    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakePeer)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.a = _Kernel()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.a.close()

    def _poll(self, payload):
        _FakePeer.PAYLOAD = payload
        return km._poll_remote_version({"local_port": self.port, "token": "tok"})

    def test_the_poll_carries_the_peers_stamps_beside_its_settings(self):
        got = self._poll({"kernel_sha": "abc1234", "settings": {"compactSuggest": True},
                          "settingsGt": {"compact-suggest": 2_000, "auto-nudge": 0}})
        self.assertEqual(got["settings"], {"compactSuggest": True})
        self.assertEqual(got["settingsGt"], {"compact-suggest": 2_000, "auto-nudge": 0})

    def test_an_older_kernel_or_junk_stamps_poll_as_none(self):
        self.assertIsNone(self._poll({"kernel_sha": "abc1234", "settings": {"compactSuggest": True}})["settingsGt"])
        self.assertIsNone(self._poll({"kernel_sha": "abc1234", "settingsGt": "2000"})["settingsGt"])

    def test_a_polled_peer_is_proposed_end_to_end(self):
        rver = self._poll({"kernel_sha": "abc1234", "settings": {"compactSuggest": True, "autoNudge": True, "fileEditing": True},
                           "settingsGt": {"compact-suggest": 2_000, "file-editing": 2_000}, "settingsPinned": {"file-editing": True}})
        self.assertEqual(rver["settingsPinned"], {"file-editing": True}, "the poll lifts the peer's pins")
        self.assertEqual(sorted(self.a.propose("TESTHOST", rver)[0]), ["compact-suggest", "file-editing"])
        self.assertEqual(self.a.read("compact-suggest")[0], False, "nothing applied (the base wrote True under 2000)")
        self.assertEqual(self.a.read("file-editing")[0], False)
        self.assertEqual(sorted(self.a.proposals()), ["compact-suggest", "file-editing"])
        self.assertEqual(self.a.read("auto-nudge")[1], 0, "no stamp for it in the peer's dict: untouched")


class TheEmitterIsOneSnapshotPerStore(unittest.TestCase):
    """The consumer takes a peer's (value, stamp) as one snapshot, so the peer's /version must read each
    store's value and stamp from ONE read: two reads with a click landing between them yield (old value,
    new stamp), which the adopter persists and the equal-stamp rule then freezes on both machines (the
    second review of this change)."""

    def setUp(self):
        self.k = _Kernel()

    def tearDown(self):
        self.k.close()

    def test_version_reports_a_value_and_stamp_from_the_same_read(self):
        # the blob reader is wrapped so that the settings sub-dict's VALUE readers see the pre-click blob while
        # the stamp reader sees the post-click one — exactly a click landing between two separate reads
        import inspect
        with self.k:
            km._set_compact_suggest(False, gt=5_000)
            old = dict(km._auto_nudge_data())
            km._set_compact_suggest(True, gt=9_000)
            new = dict(km._auto_nudge_data())
            real = km._auto_nudge_data
            def torn():
                caller = inspect.stack()[1].function
                return dict(old) if caller in ("_compact_suggest_on", "_auto_nudge_on") else dict(new)
            km._auto_nudge_data = torn
            try:
                v = km._version_info()
            finally:
                km._auto_nudge_data = real
        pair = (v["settings"]["compactSuggest"], v["settingsGt"]["compact-suggest"])
        self.assertIn(pair, [(False, 5_000), (True, 9_000)], "value and stamp come from one snapshot: %r" % (pair,))
        self.assertEqual(v["compactSuggest"], v["settings"]["compactSuggest"], "the top-level field rides the same snapshot")

    def test_the_snapshot_reads_the_blob_exactly_once(self):
        # the torn-read test above tears by CALLER, so a helper that read the blob twice (values, then stamps)
        # would still pass it; this counts the reads inside one snapshot (third review, nit)
        with self.k:
            km._set_compact_suggest(True, gt=9_000)
            real = km._auto_nudge_data
            calls = []
            km._auto_nudge_data = lambda: (calls.append(1), real())[1]
            try:
                values, stamps = km._mesh_settings_snapshot()
            finally:
                km._auto_nudge_data = real
        self.assertEqual(len(calls), 1, "one read of the auto-nudge blob for its two values and two stamps")
        self.assertEqual((values["compactSuggest"], stamps["compact-suggest"]), (True, 9_000))

    def test_version_builds_the_four_adopted_settings_from_the_snapshot_helper(self):
        src = KERNEL_SRC.split("def _version_info(")[1].split("\ndef ")[0]
        self.assertIn("_mesh_settings_snapshot()", src)
        with self.k:
            km._set_file_editing(True, gt=4_000)
            values, stamps = km._mesh_settings_snapshot()
        self.assertEqual(values["fileEditing"], True)
        self.assertEqual(stamps["file-editing"], 4_000)
        self.assertEqual(set(values), {"autoNudge", "compactSuggest", "fileEditing", "taskTracking"})
        self.assertEqual(set(stamps), {"auto-nudge", "compact-suggest", "file-editing", "task-tracking"})
        with self.k:
            km._set_task_tracking(False, gt=4_500)
            values, stamps = km._mesh_settings_snapshot()
        self.assertEqual((values["taskTracking"], stamps["task-tracking"]), (False, 4_500), "the switch's value and stamp from one read of its file")


class _Mesh:
    """Two kernels and a stubbed tunnel: A's pushes to B land in B's /mesh-settings applier under B's state root
    (the peer's gesture route, gt-gated like every setting). `refuse` makes B an older kernel with no such route."""

    def __init__(self, a, b, refuse=False):
        self.a, self.b, self.refuse, self.calls = a, b, refuse, []
        self._saved = km._remote_kernel_call

        def call(r, method, path, payload=None, timeout=8):
            self.calls.append((r.get("host"), method, path, payload))
            if self.refuse:   # the real shape: an older kernel's text 404 fails the transport's JSON parse
                return None, None, "could not reach TESTHOST's kernel: Expecting value: line 1 column 1 (char 0)"
            with self.b:
                return 200, km._apply_mesh_settings(payload if isinstance(payload, dict) else {}), None
        km._remote_kernel_call = call

    def close(self):
        km._remote_kernel_call = self._saved

    def row(self, trust="directed"):
        return {"host": "TESTHOST", "local_port": 51000, "token": "tok", "trust": trust, "status": "up"}

    def converge(self, trust="directed"):
        """A's supervisor step against B's /version — synchronously, so the test reads the outcome."""
        with self.a:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                out = km._converge_peer_settings(self.row(trust), self.b.version(), sync=True)
            return out, err.getvalue()


class VersionCarriesPinsAndProposals(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _Kernel(), _Kernel()

    def tearDown(self):
        self.a.close(); self.b.close()

    def test_version_reports_the_pins_and_the_pending_proposals_additively(self):
        with self.a:
            v0 = km._version_payload() if hasattr(km, "_version_payload") else None
        self.a.set("task-tracking", True, 1_000); self.a.pin("auto-nudge", True, 1_000)
        self.b.set("task-tracking", False, 2_000)
        self.a.propose("TESTHOST", self.b.version())
        with self.a:
            self.assertEqual(km._settings_pinned_map(), {"auto-nudge": True})
            self.assertEqual(km._settings_proposals_map(), {"task-tracking": [{"host": "TESTHOST", "value": False, "gt": 2_000, "current": True}]})
        self.assertIn('"settingsPinned": _settings_pinned_map(),', KERNEL_SRC, "/version carries the pins")
        self.assertIn('**({"settingsProposals": _settings_proposals_map(), "host": _self_host()} if authed else {}),', KERNEL_SRC,
                      "…and, to a caller with the token, the pending proposals (the gear's surface) and this machine's name")
        self.assertIn('_version_info(authed=self._authorize(q)[0])', KERNEL_SRC, "the handler says whether the caller presented the token")
        self.assertIn('"settingsPinned": j.get("settingsPinned") if isinstance(j.get("settingsPinned"), dict) else None', KERNEL_SRC,
                      "the poll lifts a peer's pins, so a pinned store is not pushed to")

    def test_a_proposal_never_writes_the_local_store(self):
        self.a.set("file-editing", False, 1_000)
        before = (self.a.root / "file-editing.json").read_bytes()
        self.b.set("file-editing", True, 2_000)
        self.a.propose("TESTHOST", self.b.version())
        self.assertEqual((self.a.root / "file-editing.json").read_bytes(), before, "byte for byte")
        self.assertTrue((self.a.root / "settings-proposals.json").exists(), "the record lives in its own file")


class OneDirectionalAttach(unittest.TestCase):
    """The default topology polls ONE way: the hub polls the machine it attached; that machine has no row for
    the hub until Share my sessions is on. Convergence therefore also PUSHES: a peer whose stamp is OLDER than
    ours receives our (value, stamp) through its gesture route, so latest-wins holds in both directions (the
    manager's review of the merged convergence, 2026-09-08)."""

    def setUp(self):
        self.a, self.b = _Kernel(), _Kernel()
        self.m = _Mesh(self.a, self.b)

    def tearDown(self):
        self.m.close(); self.a.close(); self.b.close()

    def test_the_hubs_newer_pick_reaches_a_peer_that_never_polls_it_as_a_proposal_within_one_pass(self):
        # the user's incident of 2026-09-08: the hub clicked compactSuggest OFF, then attached a machine whose copy was ON
        # under an older stamp; the machine never polled back, so the hub PUSHES. One A: the push lands on the peer as a
        # PROPOSAL (the peer's /mesh-settings proposes, never applies), so the peer's user answers there
        self.a.set("compact-suggest", False, 9_000)
        self.b.set("compact-suggest", True, 5_000)
        out, err = self.m.converge()
        self.assertEqual(out["pushed"], [], "the peer did not APPLY it (its ack shows its own stamp): not counted as pushed")
        self.assertEqual(out["adopted"], [])
        self.assertEqual(self.b.read("compact-suggest"), (True, 5_000), "b's store stands (the base wrote the hub's value under 9000)")
        self.assertEqual(self.b.proposals(), {"compact-suggest": [{"host": km._self_host(), "value": False, "gt": 9_000, "current": True}]},
                         "b holds the hub's pick as a proposal naming the hub")
        self.assertEqual([c[2] for c in self.m.calls], ["/mesh-settings"])
        self.assertEqual(self.m.calls[0][3].get("host"), km._self_host(), "the push names its machine for the peer's record")
        out, _ = self.m.converge()
        self.assertEqual(len(self.m.calls), 2, "the hub pushes again while the stamps differ; the peer's record is unchanged")
        self.assertEqual(self.b.proposals()["compact-suggest"][0]["gt"], 9_000)

    def test_a_newer_peer_is_proposed_here_and_nothing_is_pushed_to_it(self):
        self.a.set("compact-suggest", False, 5_000)
        self.b.set("compact-suggest", True, 9_000)
        out, _ = self.m.converge()
        self.assertEqual((out["adopted"], out["pushed"]), (["compact-suggest"], []), "the adopted list reads as the PENDING proposals")
        self.assertEqual(self.a.read("compact-suggest"), (False, 5_000), "the local store stands")
        self.assertEqual(self.a.proposals()["compact-suggest"][0]["value"], True)
        self.assertEqual(self.m.calls, [])

    def test_a_peers_pinned_store_is_not_pushed_to(self):
        self.a.set("compact-suggest", False, 9_000)
        self.b.set("compact-suggest", True, 5_000)
        self.b.pin("compact-suggest", True, 5_100)
        out, _ = self.m.converge()
        self.assertEqual((out["pushed"], self.m.calls), ([], []), "the peer's user pinned it: its value stands there by their word")
        self.assertEqual(self.b.proposals(), {})

    def test_an_older_kernel_that_has_no_route_is_said_once_and_skipped(self):
        self.m.refuse = True
        self.a.set("compact-suggest", False, 9_000)
        self.b.set("compact-suggest", True, 5_000)
        out1, err1 = self.m.converge()
        out2, err2 = self.m.converge()
        self.assertEqual((out1["pushed"], out2["pushed"]), ([], []))
        self.assertIn("TESTHOST", err1, "the refusal is said, naming the machine")
        self.assertIn("older kernel without the route, or unreachable", err1, "…and both likely causes, since the transport cannot tell them apart")
        self.assertEqual(err2.count("did not take"), 0, "…once per peer, not every pass")
        self.assertEqual(self.b.read("compact-suggest"), (True, 5_000), "the peer keeps its copy until it updates or the next click")

    def test_all_four_settings_push_the_same_way(self):
        for store in ("compact-suggest", "auto-nudge", "file-editing", "task-tracking"):
            default = self.b.read(store)[0]
            self.a.set(store, not default, 9_000)
            self.b.set(store, default, 5_000)
            self.m.converge()
            self.assertEqual(self.b.read(store), (default, 5_000), store + ": the peer's store stands")
            self.assertEqual(self.b.proposals()[store][0]["value"], not default, store + ": the push landed as a proposal")


class TrustGate(unittest.TestCase):
    """Adoption is an INBOUND leg — a peer's stored state, read off its auth-exempt /version, applied to this
    kernel's stores with no gesture — and the push is a new outbound one. Both gate on the peer's trust not being
    "isolated": for fileEditing an isolated peer could otherwise open this kernel's write-any-file save route."""

    def setUp(self):
        self.a, self.b = _Kernel(), _Kernel()
        self.m = _Mesh(self.a, self.b)

    def tearDown(self):
        self.m.close(); self.a.close(); self.b.close()

    def test_an_isolated_peers_newer_pick_is_neither_adopted_nor_pushed_to_and_that_is_said_once(self):
        self.b.set("file-editing", True, 9_000)
        self.a.set("compact-suggest", True, 9_000)
        self.b.set("compact-suggest", False, 5_000)
        out1, err1 = self.m.converge(trust="isolated")
        out2, err2 = self.m.converge(trust="isolated")
        self.assertEqual(out1, {"adopted": [], "pushed": []})
        self.assertEqual(out2, {"adopted": [], "pushed": []})
        self.assertEqual(self.a.read("file-editing"), (False, 0), "the gate on this kernel's save route stays shut")
        self.assertEqual(self.b.read("compact-suggest"), (False, 5_000), "nothing pushed either")
        self.assertEqual(self.m.calls, [])
        self.assertIn("isolated", err1); self.assertIn("TESTHOST", err1)
        self.assertEqual(err2.strip(), "", "said once per peer")

    def test_the_route_proposes_under_the_stamp_and_answers_the_current_snapshot(self):
        with self.b:
            self.b.set("compact-suggest", True, 5_000)
            ack = km._apply_mesh_settings({"compactSuggest": False, "gt": 9_000, "host": "TESTHOST2"})
            self.assertEqual(ack["ok"], True)
            self.assertEqual((ack["settings"]["compactSuggest"], ack["settingsGt"]["compact-suggest"]), (True, 5_000), "nothing applied (the base wrote False under 9000)")
            self.assertEqual(ack["settingsProposals"], {"compact-suggest": [{"host": "TESTHOST2", "value": False, "gt": 9_000, "current": True}]})
            stale = km._apply_mesh_settings({"compactSuggest": True, "gt": 4_000, "host": "TESTHOST2"})
            self.assertEqual(stale["settingsProposals"]["compact-suggest"][0]["gt"], 9_000, "an older stamp changes nothing; the ack shows what holds")
            self.assertIsNone(km._pop_stale_notice(), "no socket delivered this: no verdict left for the next gesture")
            junk = km._apply_mesh_settings({"compactSuggest": "yes", "gt": 9_500})
            self.assertEqual(junk["settings"]["compactSuggest"], True, "a non-bool is ignored")
            self.assertIn("settingsPinned", junk)


class ThePollSeam(unittest.TestCase):
    def test_the_supervisor_lifts_the_stamps_and_adopts_outside_the_lock(self):
        sup = KERNEL_SRC.split("def _tunnel_supervisor():")[1].split("\ndef ")[0]
        self.assertIn('r["settings"] = (rver or {}).get("settings")', sup)
        self.assertIn('r["settingsGt"] = (rver or {}).get("settingsGt")', sup, "the stamps ride the row beside the values")
        self.assertIn("_converge_peer_settings(r, rver)", sup, "the supervisor hands the ROW over, so trust is read at the seam")
        # the setters take their own locks and write files: they run in the OUTSIDE-the-lock block, like the auto update
        before_lock_exit = sup.split("if auto_check:")[0]
        self.assertNotIn("_converge_peer_settings(", before_lock_exit, "never under _remotes_lock")
        self.assertIn('if u.path == "/mesh-settings":', KERNEL_SRC, "the peer-side gesture route the push lands on")
        self.assertIn('if u.path == "/setting-proposal":', KERNEL_SRC, "the user's answer route (one A)")
        self.assertIn("adopted = _propose_peer_settings(host, rver)", KERNEL_SRC, "the inbound leg proposes")
        self.assertNotIn("def _adopt_peer_settings", KERNEL_SRC, "the adopter is gone: no road applies a remote value without the user")

    def test_the_table_names_exactly_the_four_broadcast_booleans(self):
        self.assertEqual([row[0] for row in km._MESH_ADOPTED_SETTINGS], ["compactSuggest", "autoNudge", "fileEditing", "taskTracking"])
        self.assertEqual([row[1] for row in km._MESH_ADOPTED_SETTINGS], ["compact-suggest", "auto-nudge", "file-editing", "task-tracking"])


if __name__ == "__main__":
    unittest.main()
