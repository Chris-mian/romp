#!/usr/bin/env python3
"""POST /deliver — the postal bus's ONE door for live-delivering a mail banner: it
hands the banner to the kernel, which routes it through the owning backend's deliver() (the SDK
enqueues it; see SessionBackend.deliver). The bus never touches a session's transport directly."""

import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_deliver", os.path.join(BIN, "romp-kernel")).load_module()


class SdkDeliverSourcePin(unittest.TestCase):
    def test_sdk_backend_defines_deliver_as_a_no_echo_enqueue(self):
        src = open(os.path.join(BIN, "romp_sdk_backend.py"), encoding="utf-8").read()
        body = src.split("def deliver(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("s.enqueue(text)", body, "SDK deliver enqueues the banner (the deliver-time wake)")
        self.assertNotIn("_echo_text", body, "no optimistic human echo — it's a peer's mail, not the user's input")

    def test_post_deliver_routes_through_backend_for(self):
        src = open(os.path.join(BIN, "romp-kernel"), encoding="utf-8").read()
        self.assertIn('u.path == "/deliver"', src)
        self.assertIn("Sessions.backend_for(sid).deliver(sid, text)", src)


