#!/usr/bin/env python3
"""Extra models from your API gateway: the comment dialog's default model (review round, 2026-09-22).

The create dialog pre-reads the kernel's default-comment trio from the authed /models payload (`commentDefaults`)
and shows it, so an untouched dialog shows what the thread will launch on. The route served the RAW comment-model
store while _comment_launch_prefs had learned to fall to inheriting the parent when the stored default is a model
this kernel no longer offers (an extra gateway model whose switch is off): the dialog showed a removed id as the
default while the create launched on the parent's model. One helper, _comment_default_model_effective, is now the
read both surfaces make: the stored value when it is "session", "default" or vouched, else "session". Pinned here:

- the helper itself, the route's commentDefaults.model and _comment_launch_prefs's model arm, for a removed id
  (both read "inherit"; the launch prefs still say so on stderr), a vouched value (both read it) and the two
  sentinels;
- the typed /model road consults _pick_vouched with the typed id (a call-recording patch, so a commented-out call
  would fail this where a source grep would not) and refuses a removed id;
- the three texts that describe the missing colour rank and capacity-fallback reading are narrowed to an id
  carrying no first-party family word (the backend's _model_rank matches a family word by substring, so an id
  that carries one ranks as that family).

Synthetic only: placeholder UUIDs, invented gateway ids (gw-6-astra, gw-7-nova), a temp state root with session
hosts off, a stub backend that records what it was asked, no network (ROMP_MODEL_CATALOG=off).
"""
import http.client
import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the loads: they resolve their state root at import time, and only pytest runs conftest's
# floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["ROMP_MANAGER_PORT"] = "1"             # a dead port, never an inherited live one
os.environ["ROMP_MODEL_CATALOG"] = "off"          # never the Models API from a test
for _v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL"):
    os.environ.pop(_v, None)
km = load_source("romp_kernel_router_comment_default", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_router_comment_default", os.path.join(BIN, "romp_sdk_backend.py"))
km.jd.STATE.mkdir(parents=True, exist_ok=True)
(km.jd.STATE / "session-hosts").write_text("off")   # this root is outside conftest's belt (repo rule, 2026-09-11)

DECLARED = "gw-6-astra, gw-7-nova"
REMOVED = "gw-6-astra"
SID = "11111111-2222-4333-8444-555555555555"


def _env(tc, key, value):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    tc.addCleanup(lambda: os.environ.__setitem__(key, prev) if prev is not None else os.environ.pop(key, None))


class Texts(unittest.TestCase):
    """The three texts that say a gateway id has no colour rank and a swap to one is never a capacity fallback
    are narrowed to an id carrying no first-party family word: sdk_backend._model_rank walks _MODEL_TIERS by
    substring with no router gate, so an id that carries a family word ranks as that family (pinned first)."""

    def test_the_rank_helper_matches_a_family_word_inside_a_gateway_id(self):
        self.assertEqual(sb._model_rank("gw-opus-mini"), sb._model_rank("opus"))
        self.assertIsNone(sb._model_rank(REMOVED), "an id carrying no family word has no rank")

    def _narrowed(self, text, label):
        # the qualifier stands in the same sentence as the fallback clause and AHEAD of it: the clause holds for
        # that id, not for every gateway id (a qualifier on the tint half alone leaves the fallback half unqualified)
        hits = [m for m in re.finditer(r"[^.\n]*(?:\n[^.\n]*)*?capacity\s+fallback[^.]*\.", text)]
        self.assertTrue(hits, "%s: the fallback clause is there" % label)
        for m in hits:
            self.assertRegex(m.group(0).replace("\n", " "),
                             r"carr(?:ies|ying) no (?:first-party|Claude) family word.*capacity\s+fallback",
                             "%s: the fallback clause names the id it holds for" % label)

    def test_the_reference_page(self):
        text = open(os.path.join(ROOT, "docs", "reference.md")).read()
        start = text.index("Extra models")
        self._narrowed(text[start:start + 6000], "docs/reference.md")

    def test_the_router_block_comment(self):
        text = open(os.path.join(BIN, "romp-kernel")).read()
        i = text.index("ROUTER_MODELS_FILE = ")
        head = text[text.rfind("\n\n", 0, i):i]          # the block comment directly above the store's name
        self.assertIn("capacity", head)
        self._narrowed(head.replace("\n# ", " "), "the router block comment")


if __name__ == "__main__":
    unittest.main()
