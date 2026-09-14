#!/usr/bin/env python3
"""The dashboard shell's browser-side reads check the answer's status before parsing its body.

A proxy in JSON-error mode answers a 5xx whose body parses, and a read that goes straight to r.json() takes that body
for the thing it asked for: the network rail's /tunnels poll painted no hosts and erased its was-up map (fixed with the
kernel /tunnels follow-up), and the same shape stood in four more readers, each writing a default from an unreadable
answer: the bell's two switches (painted OFF for the page's life from a one-shot read), the reload core's /version
(noteVersion's boot and dist latches), the stale banner's /version poll (its served/dismissed latches) and the update
banner's /update-check (waiting, bootNow, the failed and done words). Each now throws on a non-ok status into the catch
it already had; the bell's read retries a few times instead of standing. Source pins, one per reader, so a rewrite of
any block cannot drop the check quietly; the rail's own read is pinned beside its executed test in
tests/test_remotes_panel_render.py.
"""
import os
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the load: the kernel resolves its state root at import time
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)   # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_shell_reads", os.path.join(BIN, "romp-kernel"))


class ShellReadsCheckStatus(unittest.TestCase):
    def test_the_bell_switches_throw_on_a_non_ok_answer_and_retry_instead_of_painting_off(self):
        js = km._LANDING_PUSH_JS
        self.assertIn("function readSwitch(url,apply,tries){fetch(url).then(function(r){if(!r.ok)throw new Error(url+' answered HTTP '+r.status);return r.json();})", js)
        self.assertIn("readSwitch('/notify-all',function(on){isOn=on;},3);", js)
        self.assertIn("readSwitch('/notify-turns',function(on){turnsOn=on;},3);", js)
        self.assertIn("if(tries>0)setTimeout(function(){readSwitch(url,apply,tries-1);},5000);", js, "a bounded retry, never a default painted from the failure")
        self.assertNotIn("fetch('/notify-all').then(function(r){return r.json();})", js)

    def test_the_reload_cores_version_read_checks_the_status(self):
        self.assertIn("fetch('/version',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('/version answered HTTP '+r.status);return r.json();}).then(noteVersion)", km._RELOAD_CORE_JS)

    def test_the_stale_banners_version_poll_checks_the_status(self):
        self.assertIn("function check(){fetch('/version',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('/version answered HTTP '+r.status);return r.json();})", km._STALE_JS)

    def test_the_update_banners_two_reads_check_the_status(self):
        js = km._UPD_JS
        self.assertIn("function poll(){fetch('/update-check',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('/update-check answered HTTP '+r.status);return r.json();})", js)
        self.assertIn("fetch('/update-check',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('/update-check answered HTTP '+r.status);return r.json();}).then(function(d){bootNow=(d&&d.boot)||'';", js)
        self.assertNotIn("fetch('/update-check',{cache:'no-store'}).then(function(r){return r.json();})", js)


if __name__ == "__main__":
    unittest.main()
