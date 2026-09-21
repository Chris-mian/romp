"""build_feed is CACHE-ONLY on a cold start, and its background parse-warmer must NOT compete with the chat.

The feed's CARDS come from the goal store (cheap); the working-dots / deep-link anchors / API-error+awaiting
badges / provisional card read the transcript parse ONLY if it's already cached (_parse_cached), so the cards
paint at once on a cold kernel start (the user 2026-06-26). The dedicated warmer (_warm_fleet_bg) fills the
cache for a FEED-ONLY window — but a chat or timeline client already parses the same fleet into the same
cache, so the warmer must skip then, or it steals GIL from the chat's active-tab reshape on a cold restart.
The one exception to cache-only (2026-09-18): a session the memo already holds warm is re-read in place when its
files moved, so its entry never falls cold for a build; a session never parsed still costs the first paint nothing.
The re-read runs only while the transcript can be stat'ed (2026-09-21): a leaf gone from disk has no store slot to
re-read into, so that entry falls cold instead and asks the warmer for nothing. The warmer's own loop skips such a
leaf too (the post-merge review of that gate, 2026-09-21), so a warm another cold session kicked never parses it.
"""
import inspect
import os
import unittest
from romp_load import load_source
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))


class FeedCacheOnly(unittest.TestCase):
    def test_build_feed_reads_the_parse_cache_only_never_a_cold_parse(self):
        src = (inspect.getsource(km.build_feed) + inspect.getsource(km._feed_session_key)
               + inspect.getsource(km._feed_session_entry))   # T368: the loop body and its key builder
        self.assertIn("ps = _parse_cached(s[\"path\"])", src, "the working-dot reads the CACHED parse, no cold parse")
        self.assertIn("cold_parse = True", src)
        # A LOCATOR, not the proof (the post-merge review, 2026-09-21): the literal pins the spelling of the gate line,
        # so a rewording trips it while a behavior change under the same spelling does not; the gated behavior is
        # executed by the tests the message names, and a change to the gate is owed a change there.
        self.assertIn("if _feed_key_was_warm(prev_key) and transcript[0] is not None:", src,
                      "the re-read's gate moved or was reworded: this literal only LOCATES it (a WARM memoized key, "
                      "2026-09-18, whose leaf stats, 2026-09-21). The behavior is proved in "
                      "tests/test_feed_session_memo.py, class AWarmEntryIsNeverDerivedCold: the warm-key clause by "
                      "test_an_append_after_the_chats_parse_derives_the_session_warm_once_and_the_chats_next_parse_hits"
                      " and "
                      "test_an_emptied_parse_store_under_a_warm_entry_re_reads_in_place_and_asks_for_no_background_warm"
                      ", the stat clause by "
                      "test_a_warm_entry_whose_transcript_is_gone_derives_cold_once_and_re_reads_nothing, the body's "
                      "warm ask by test_a_warm_entry_whose_transcript_is_gone_asks_the_warmer_for_nothing, and the "
                      "warmer's own loop gate by test_a_warm_that_another_cold_session_kicked_skips_the_gone_leaf; "
                      "re-point this message if those move")
        self.assertIn("ps = _parse(path, fsid, now)", src, "...and only then does the key parse in place")
        self.assertIn("_warm_fleet_bg(now)", src, "an unparsed living session kicks the background warmer")
        # the parse-derived enrichments are all gated on `ps` (cached) so the cold first paint is just cards
        # API-error floor — gated on awaiting too since 2026-07-05 (yields to live background agents)
        self.assertIn("if (ps and not who_working and not sess_awaiting_why) else None", src)
        self.assertIn("if ps else None", src)                              # awaiting badge
        self.assertIn("if not had_working and perm_top is None and ps:", src)   # provisional card (still gated on the cached parse)


class WarmerDoesNotCompeteWithChat(unittest.TestCase):
    def setUp(self):
        self._saved = list(km._clients)
        km._warming[0] = False

    def tearDown(self):
        with km._clients_lock:
            km._clients[:] = self._saved
        km._warming[0] = False

    def _set_clients(self, apps):
        with km._clients_lock:
            km._clients[:] = [{"app": a, "send": lambda s: None, "sent": {}, "alive": True} for a in apps]

    def test_has_parsing_client_is_true_for_chat_or_timeline_only(self):
        self._set_clients(["feed"])
        self.assertFalse(km._has_parsing_client(), "a feed-only window has no parser of the fleet")
        self._set_clients(["feed", "chat"])
        self.assertTrue(km._has_parsing_client())
        self._set_clients(["timeline"])
        self.assertTrue(km._has_parsing_client())

    def test_warmer_is_a_no_op_when_a_chat_client_is_connected(self):
        self._set_clients(["feed", "chat"])
        km._warm_fleet_bg(0)
        self.assertFalse(km._warming[0], "the warmer must NOT start while the chat parses the fleet itself")

    def test_warmer_is_a_no_op_with_no_clients(self):
        self._set_clients([])
        km._warm_fleet_bg(0)
        self.assertFalse(km._warming[0])


if __name__ == "__main__":
    unittest.main()
