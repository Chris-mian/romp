"""The kernel must answer EVERY needFull (2026-09-19, round two MEDIUM). A page rejects a too-far-ahead delta with
one needFull; the page's awaitingFull clears only when a full frame arrives (or the socket re-opens). A kernel-side
dedup that answered a repeat within a short window with NOTHING therefore stranded the tab: a second gap ask inside
the window was dropped, awaitingFull stayed set, and every later delta was discarded as a gap until a reconnect. The
refused-frame loop is bounded on the PAGE (render.ts refusedFrameLatch stops after the second identical refusal), so
the kernel does not dedup: three gap asks for one sid each get the frame, and the reader catches up.

Drives the real WS dispatch against a hermetic kernel (the verifier's round-two harness). Synthetic sids/transcript.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# hermetic state BEFORE the loads (they resolve their state root at import time)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_nfnd", os.path.join(BIN, "romp-kernel"))

S1 = "11111111-2222-3333-4444-5555555550b1"
S2 = "11111111-2222-3333-4444-5555555550b2"
NAMES = {S1: "web", S2: "api"}
TAB_ORDER = [S1, S2]


def _sess(sid, n, state):
    return {"type": "session", "id": sid, "name": NAMES[sid],
            "events": [{"kind": "assistant", "uuid": "u%d" % i, "md": "m%d" % i} for i in range(n)],
            "status": {"state": state, "sinceEpoch": None}, "ledger": None}


class _Self:
    """A stand-in for the kernel whose _push_one runs the real push against the one client (a connect push, full frames)."""
    def __init__(self, push_one=None):
        self.calls = []
        self._po = push_one

    def _push_one(self, client):
        self.calls.append(client)
        if self._po:
            self._po(client)


class KernelAnswersEveryNeedFull(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {}
        for sid, n in {S1: 2000, S2: 3000}.items():
            p = os.path.join(self.tmp, sid + ".jsonl")
            with open(p, "w") as f:
                f.write("x" * n)
            self.paths[sid] = p
        self.SESS = {S1: _sess(S1, 5, "working"), S2: _sess(S2, 7, "working")}
        self._saved = (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
                       km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, list(km._clients))
        km._chat_tab_sessions = lambda now, live_map: [
            {"sid": sid, "name": NAMES[sid], "path": self.paths[sid], "anchor": sid} for sid in TAB_ORDER]
        km._live_map = lambda: {}
        km._cached_feed = lambda *a, **k: None
        km.build_session = lambda sid, now, live_map=None, **kw: json.loads(json.dumps(self.SESS[sid]))
        km._comments_frame = lambda sid, live_map: None
        km._push_subagents = lambda clients, now, live_map: None
        km.NAMES = Path(self.tmp) / "names"
        km.NAMES.mkdir()
        km.jd.STATE = Path(self.tmp) / "state"
        km.jd.STATE.mkdir(parents=True, exist_ok=True)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()
        del km._clients[:]
        km._pusher_wake.clear()

    def tearDown(self):
        (km._chat_tab_sessions, km._live_map, km._cached_feed, km.build_session,
         km._comments_frame, km._push_subagents, km.NAMES, km.jd.STATE, clients) = self._saved
        del km._clients[:]
        km._clients.extend(clients)
        km._built_chat.clear(); km._prev_chat_events.clear(); km._prev_chat_ledger.clear()

    def _client(self, **kw):
        frames = []
        c = {"app": "chat", "alive": True, "sent": {}, "send": lambda s: frames.append(json.loads(s)), "_frames": frames}
        c.update(kw)
        return c

    def _ask(self, c, sid):
        """One needFull through the real WS dispatch; returns the session ids the answering push sent for this client."""
        h = _Self(push_one=lambda cl: km._push([cl], connect=True))
        c["_frames"].clear()
        km.Handler._dispatch_ws(h, {"type": "needFull", "id": sid, "why": "gap"}, c)
        return [f["id"] for f in c["_frames"] if f["type"] == "session"]

    def test_three_gap_asks_for_one_sid_each_get_a_full_no_kernel_dedup(self):
        c = self._client(active=S1, reconnect=True)
        km._push([c])            # the reconnect's strip: S1 full, the rest skeleton
        c["_frames"].clear()
        # three gap asks in immediate succession (a parked reader whose deltas land ~0.5 s apart): each must be answered
        # with S1's full frame. A kernel dedup dropped the 2nd and 3rd, and awaitingFull then stranded the tab.
        got = [self._ask(c, S1), self._ask(c, S1), self._ask(c, S1)]
        self.assertEqual(got, [[S1], [S1], [S1]],
                         "every repeated needFull for the same sid is answered with the full frame (no kernel dedup): %r" % got)


if __name__ == "__main__":
    unittest.main()
