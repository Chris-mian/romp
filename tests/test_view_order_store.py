#!/usr/bin/env python3
"""The kernel keeps the VIEWER'S arrangement, as opaque data (the user 2026-09-23).

The order sessions are shown in is computed in the browser and always will be: it spans every kernel the
dashboard has attached, and no kernel can ORDER sids belonging to a machine it has never heard of (the
2026-07-31 ruling, commit e9870995). What moved here is where the finished list is KEPT, so a phone and a
desktop looking at the same sessions read the same order instead of two unreconcilable ones.

Storing is not ordering, and that is what these pin: an arrangement naming hosts this kernel does not own
round-trips through view-order.json byte for byte, in the viewer's order, with no prefix parsed, no entry
matched against a live session and nothing pruned or re-sorted; the frame that serves it says whether this
kernel has an arrangement AT ALL (the browser's migration turns on exactly that); and a write reports
whether it CHANGED, because the change is the only thing worth pushing to the viewer's other devices.

Synthetic ids and hostnames only (the notes-api demo world, hosts TESTHOST / TESTHOST2).
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the load — the kernel resolves its state root at import time, and only pytest runs
# conftest's floor (a bare unittest or script run would otherwise write REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)   # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_view_order", os.path.join(BIN, "romp-kernel"))

# Sessions on THIS kernel, and sessions on two machines it has never heard of — the ids arrive already
# prefixed by the browser's federation layer, which is the only party that knows what a prefix means.
LOCAL_A = "11111111-2222-4333-8444-000000000001"
LOCAL_B = "11111111-2222-4333-8444-000000000002"
FAR_WEB = "TESTHOST:11111111-2222-4333-8444-000000000003"
FAR_API = "TESTHOST2:11111111-2222-4333-8444-000000000004"


class ViewOrderStore(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self._state = km.jd.STATE
        km.jd.STATE = Path(self.td.name)
        # Per-session hosts are ON by default over a state root with no file (T348); this root mints none
        # and this test starts no backend, so it pins the switch off rather than leaving a host to spawn.
        (km.jd.STATE / "session-hosts").write_text("off")
        km._view_order_lkg[0] = None
        km._view_folds_lkg[0] = None

    def tearDown(self):
        km.jd.STATE = self._state
        km._view_order_lkg[0] = None
        km._view_folds_lkg[0] = None
        self.td.cleanup()

    def stored_file(self):
        return json.loads((km.jd.STATE / "view-order.json").read_text())

    # ── the round trip ────────────────────────────────────────────────────────────────────────────
    def test_an_arrangement_over_hosts_this_kernel_does_not_own_round_trips_verbatim(self):
        # the crux: two of these ids name machines this kernel has never heard of, and one interleaves
        # them with its own — the arrangement no kernel could have computed
        arrangement = [FAR_WEB, LOCAL_A, FAR_API, LOCAL_B]
        self.assertTrue(km._write_view_order(arrangement))
        self.assertEqual(self.stored_file(), arrangement, "written whole, in the viewer's order")
        self.assertEqual(km._view_order_served(), (arrangement, True), "served back the same way")

    def test_nothing_is_parsed_pruned_or_re_sorted(self):
        # an entry for a session that is long gone, one for a host that is detached, and one whose prefix
        # is not a host this kernel could resolve: all opaque, all kept exactly where the viewer put them
        arrangement = [FAR_API, "ghost:not-a-uuid", LOCAL_B, FAR_WEB]
        km._write_view_order(arrangement)
        self.assertEqual(km._view_order_served()[0], arrangement)

    def test_non_strings_are_dropped_and_the_list_is_bounded(self):
        km._write_view_order([LOCAL_A, 7, None, {"sid": LOCAL_B}, FAR_WEB])
        self.assertEqual(km._view_order_served()[0], [LOCAL_A, FAR_WEB])
        # the backstop mirrors the browser's own (view-order.ts VIEW_ORDER_CAP): the viewer's prune is the
        # real bound, this only stops a client bug growing the file without limit — and it keeps the TAIL,
        # the most recent arrangement, as the browser's cap does
        km._write_view_order(["s%d" % i for i in range(km._VIEW_ORDER_CAP + 10)])
        kept = km._view_order_served()[0]
        self.assertEqual(len(kept), km._VIEW_ORDER_CAP)
        self.assertEqual(kept[-1], "s%d" % (km._VIEW_ORDER_CAP + 9))

    # ── what the frame says ───────────────────────────────────────────────────────────────────────
    def test_a_kernel_with_no_arrangement_says_so_and_one_with_an_empty_one_says_otherwise(self):
        # the browser's migration turns on exactly this: with no arrangement here, a browser carrying one
        # publishes it; with an EMPTY arrangement here, it does not (the emptiness is somebody's answer)
        self.assertEqual(km._view_order_frame(), {"type": "viewOrder", "order": [], "stored": False, "folds": None})
        km._write_view_order([])
        self.assertEqual(km._view_order_frame(), {"type": "viewOrder", "order": [], "stored": True, "folds": None})

    def test_the_frame_serves_what_was_written(self):
        km._write_view_order([FAR_WEB, LOCAL_A])
        self.assertEqual(km._view_order_frame(),
                         {"type": "viewOrder", "order": [FAR_WEB, LOCAL_A], "stored": True, "folds": None})

    # ── the change event ──────────────────────────────────────────────────────────────────────────
    def test_a_write_reports_whether_it_changed_anything(self):
        self.assertTrue(km._write_view_order([LOCAL_A, FAR_WEB]), "a first arrangement is a change")
        self.assertFalse(km._write_view_order([LOCAL_A, FAR_WEB]),
                         "a viewer republishing the list it was served pushes nothing")
        self.assertTrue(km._write_view_order([FAR_WEB, LOCAL_A]), "a drag is a change")

    def test_the_change_is_pushed_to_every_connected_client_on_one_dedup_slot(self):
        # the send itself is _send_client's (per-client dedup: a client already holding this arrangement
        # byte for byte is sent nothing, so the connect push and the change push never double up)
        seen = []
        saved_send, saved_clients = km._send_client, list(km._clients)
        km._send_client = lambda c, key, msg, *a, **kw: seen.append((c["cid"], key, msg))
        km._clients[:] = [{"cid": "phone"}, {"cid": "desktop"}]
        try:
            km._write_view_order([FAR_WEB, LOCAL_A])
            km._broadcast_view_order()
        finally:
            km._send_client, km._clients[:] = saved_send, saved_clients
        frame = {"type": "viewOrder", "order": [FAR_WEB, LOCAL_A], "stored": True, "folds": None}
        self.assertEqual(seen, [("phone", ("vieworder",), frame), ("desktop", ("vieworder",), frame)],
                         "every viewer of this kernel hears the change, on the one slot")

    # ── the store survives a kernel that cannot read it ───────────────────────────────────────────
    def _raise_on_read(self):
        saved = km._read_state_json
        km._read_state_json = lambda *a, **kw: (_ for _ in ()).throw(
            km._StateUnreadable(km._view_order_path(), "read failed: EIO"))
        self.addCleanup(lambda: setattr(km, "_read_state_json", saved))

    def test_an_unreadable_store_serves_the_last_known_good_and_still_says_stored(self):
        # A file we could not read is not a file that is MISSING. Answering "no arrangement" under an EIO
        # would invite the next browser to publish its own over an order that is still sitting there.
        km._write_view_order([LOCAL_A, FAR_WEB])
        self._raise_on_read()
        self.assertEqual(km._view_order_served(), ([LOCAL_A, FAR_WEB], True))
        # (the folds half reads through the same patched reader and has no known-good copy: it is left out)
        self.assertEqual(km._view_order_frame(), {"type": "viewOrder", "order": [LOCAL_A, FAR_WEB], "stored": True})

    def test_an_unreadable_store_with_nothing_known_good_says_NOTHING_rather_than_a_guess(self):
        # The fail-loudly rule, applied to a push: [] would have every viewer adopt an empty arrangement
        # over the one they are showing, and "stored" would be a claim about a file we have not read. No
        # frame goes; every page keeps what it has, and the read fault is filed once per episode.
        self._raise_on_read()
        self.assertIsNone(km._view_order_served())
        self.assertIsNone(km._view_order_frame())
        seen = []
        saved_send, saved_clients = km._send_client, list(km._clients)
        km._send_client = lambda c, key, msg, *a, **kw: seen.append(msg)
        km._clients[:] = [{"cid": "phone"}]
        try:
            km._send_view_order(km._clients[0])
            km._broadcast_view_order()
        finally:
            km._send_client, km._clients[:] = saved_send, saved_clients
        self.assertEqual(seen, [])

    def test_corrupt_bytes_read_as_no_arrangement_so_the_next_viewer_refills_it(self):
        # _read_state_json quarantines the bad bytes aside (they survive for forensics) and the store
        # starts empty — which says "no arrangement", and the first browser to connect publishes its own.
        km._write_view_order([LOCAL_A, FAR_WEB])
        km._view_order_lkg[0] = None                 # a kernel that restarted onto the bad file
        (km.jd.STATE / "view-order.json").write_text("{ not json")
        self.assertEqual(km._view_order_served(), ([], False))


# The fold state the browser keeps beside the arrangement (tab-groups.ts TabFolds): tag names folded, a
# default-folded one opened, a member pinned through its fold, and the rename memory those pins rest on.
FOLDS = {"collapsed": ["api"], "expanded": ["archived"],
         "pinned": [{"sid": FAR_WEB, "name": "api", "id": "g2"}], "followed": {"g2": "api"}}


class ViewFoldsStore(ViewOrderStore):
    """The viewer's FOLDS, kept beside the arrangement (the user 2026-09-23, who wanted the phone to fold too
    and the folded groups shared across devices like the order). Same store, same frame, same push: the
    viewOrder frame carries `folds` beside `order`, and a change to either is a push of that one frame. The
    object is opaque here as the list is: a round trip returns it as written, with nothing inside it read.

    Inherits the store's setUp (a private state root, session-hosts off) and so reruns its tests too, which
    is the point: the arrangement's behaviour is unchanged by the half riding beside it."""

    def stored_folds(self):
        return json.loads((km.jd.STATE / "view-folds.json").read_text())

    def test_folds_round_trip_verbatim_and_ride_the_arrangements_frame(self):
        self.assertTrue(km._write_view_folds(FOLDS))
        self.assertEqual(self.stored_folds(), FOLDS, "written whole")
        self.assertEqual(km._view_folds_served(), FOLDS)
        km._write_view_order([FAR_WEB, LOCAL_A])
        self.assertEqual(km._view_order_frame(),
                         {"type": "viewOrder", "order": [FAR_WEB, LOCAL_A], "stored": True, "folds": FOLDS},
                         "one frame: the arrangement and the folds side by side")

    def test_no_folds_is_null_and_an_empty_fold_state_is_not(self):
        # the browser's migration turns on this, as it does on `stored`: with nothing here, a browser that
        # has folds of its own publishes them; with an emptied state here (every group opened), it must not
        # refill it from its own old key
        self.assertIsNone(km._view_order_frame()["folds"])
        empty = {"collapsed": [], "expanded": [], "pinned": []}
        km._write_view_folds(empty)
        self.assertEqual(km._view_order_frame()["folds"], empty)

    def test_a_fold_write_reports_whether_it_changed(self):
        self.assertTrue(km._write_view_folds(FOLDS), "a first fold state is a change")
        self.assertFalse(km._write_view_folds(json.loads(json.dumps(FOLDS))),
                         "a viewer republishing the state it was served pushes nothing")
        self.assertTrue(km._write_view_folds(dict(FOLDS, collapsed=[])), "opening a group is a change")

    def test_a_non_object_or_an_oversized_one_is_refused_whole(self):
        with self.assertRaises(km._StateUnwritable):
            km._write_view_folds(["api"])
        with self.assertRaises(km._StateUnwritable):
            km._write_view_folds({"collapsed": ["x" * 64] * (km._VIEW_FOLDS_CAP // 64)})
        self.assertFalse((km.jd.STATE / "view-folds.json").exists(), "nothing written: a cut object is a different state")

    def test_the_socket_message_writes_and_pushes_one_frame_to_every_viewer(self):
        # through the real dispatcher: setViewFolds stores the object and pushes the one viewOrder frame on
        # its slot to every connected client; an unchanged republish pushes nothing
        seen = []
        saved_send, saved_clients = km._send_client, list(km._clients)
        km._send_client = lambda c, key, msg, *a, **kw: seen.append((c["cid"], key, msg))
        km._clients[:] = [{"cid": "phone"}, {"cid": "desktop"}]
        handler = object.__new__(km.Handler)
        poster = {"cid": "desktop", "app": "chat", "alive": True, "send": lambda s: seen.append(("reply", json.loads(s)))}
        try:
            km.Handler._dispatch_ws(handler, {"type": "setViewFolds", "folds": FOLDS}, poster)
            first = list(seen)
            del seen[:]
            km.Handler._dispatch_ws(handler, {"type": "setViewFolds", "folds": FOLDS}, poster)
            again = list(seen)
        finally:
            km._send_client, km._clients[:] = saved_send, saved_clients
        frame = {"type": "viewOrder", "order": [], "stored": False, "folds": FOLDS}
        self.assertEqual(first, [("phone", ("vieworder",), frame), ("desktop", ("vieworder",), frame)])
        self.assertEqual(again, [], "the same folds again: no change, no push")
        self.assertEqual(self.stored_folds(), FOLDS)

    def test_a_refused_fold_write_is_said_to_the_viewer_who_folded(self):
        seen = []
        handler = object.__new__(km.Handler)
        poster = {"cid": "desktop", "app": "chat", "alive": True, "send": lambda s: seen.append(json.loads(s))}
        saved = km._write_state_json
        km._write_state_json = lambda *a, **kw: (_ for _ in ()).throw(km._StateUnwritable(km._view_folds_path(), "[Errno 28] No space left on device"))
        try:
            km.Handler._dispatch_ws(handler, {"type": "setViewFolds", "folds": FOLDS}, poster)
        finally:
            km._write_state_json = saved
        self.assertEqual([m["type"] for m in seen], ["warn"])
        self.assertIn("folded groups", seen[0]["text"])

    def test_an_unreadable_fold_store_serves_its_last_known_good_else_leaves_the_half_out(self):
        km._write_view_folds(FOLDS)
        km._write_view_order([LOCAL_A])
        saved = km._read_state_json

        def flaky(path, *a, **kw):
            if Path(path).name == "view-folds.json":
                raise km._StateUnreadable(path, "read failed: EIO")
            return saved(path, *a, **kw)
        km._read_state_json = flaky
        self.addCleanup(lambda: setattr(km, "_read_state_json", saved))
        self.assertEqual(km._view_order_frame()["folds"], FOLDS, "a file we could not read is not a missing one")
        km._view_folds_lkg[0] = None                 # a kernel that has never read it
        self.assertEqual(km._view_order_frame(), {"type": "viewOrder", "order": [LOCAL_A], "stored": True},
                         "no folds half at all: every page keeps the folds it shows rather than adopting a guess, "
                         "and the arrangement still goes")


if __name__ == "__main__":
    unittest.main()
