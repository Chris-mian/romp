#!/usr/bin/env python3
"""The remotes popover's host list must actually RENDER.

`pmode` (peer-bus mode) is computed inside refresh()'s fetch callback, but render() read it as a FREE
variable — it is not in that scope. So every render threw ReferenceError right after `list.innerHTML=''`
had cleared the list and before any row was appended, and the bare `.catch(){}` swallowed it. The panel
showed an empty host list no matter how many remotes were attached, indistinguishable from "none
attached", and survived reloads and kernel restarts (the user 2026-07-22 — hours of misdiagnosis).

Source pins can't catch that class of bug, so this EXECUTES the real injected panel JS in node against a
DOM stub, drives the refresh with one attached host, and asserts a row lands in the list. Any
ReferenceError, typo, or scope slip in that path fails the test.

Synthetic only — placeholder host/token, no network (fetch is stubbed).
"""
import json
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_rpanel", os.path.join(BIN, "romp-kernel")).load_module()

TUNNELS = {
    "tunnels": [{
        "host": "TESTHOST", "kernelPort": 7433, "localPort": 51000, "busPort": 51001,
        "checkin": False, "checkinPeer": False, "token": "tok", "status": "up", "detail": "",
        "sids": ["11111111-2222-3333-4444-555555555555"], "trust": "directed",
        "kernelSha": "abc1234", "localSha": "abc1234", "outOfDate": False,
        "behindBy": 0, "aheadBy": 0, "kernelDate": "",
        "gaveUp": False, "fails": 0, "maxTries": 5,
    }],
    "known": [],
    "peersMode": True,
}

# Minimal DOM/browser stub: enough for the panel IIFE to wire itself up and run one refresh.
HARNESS = r"""
'use strict';
function mkEl(id){
  return {id:id, hidden:true, innerHTML:'', textContent:'', title:'', style:{},
    children:[], _listeners:{},
    classList:{_s:new Set(), add(){}, remove(){}, toggle(){}, contains(){return false;}},
    appendChild(c){this.children.push(c); return c;},
    querySelector(){return null;}, querySelectorAll(){return [];},
    addEventListener(k,f){this._listeners[k]=f;}, removeEventListener(){},
    setAttribute(){}, getAttribute(){return null;}, focus(){}, remove(){},
    get firstChild(){return this.children[0]||null;}};
}
const ELS = {};
const document = {
  getElementById(id){ if(!ELS[id]) ELS[id]=mkEl(id); return ELS[id]; },
  createElement(t){ return mkEl(t); },
  querySelector(){ return null; }, querySelectorAll(){ return []; },
  addEventListener(){}, body:mkEl('body'),
};
const localStorage = { getItem(){return null;}, setItem(){} };
const TUNNELS = __TUNNELS__;
function fetch(url){
  const body = url.indexOf('/ssh-hosts') >= 0 ? {hosts:['TESTHOST']} : TUNNELS;
  return Promise.resolve({ ok:true, json(){ return Promise.resolve(body); } });
}
const setTimeout_ = setTimeout;
const window = { addEventListener(){}, location:{reload(){}} };
const console_err = [];
const console = { error(...a){ console_err.push(a.map(String).join(' ')); }, log(){}, warn(){} };

__PANEL_JS__

// drive it: open the panel (sets hidden=false, loads hosts, refreshes) and let the promises settle
ELS['rnet-back'].hidden = false;
window.__rompOpenNet && window.__rompOpenNet();
setTimeout_(() => {
  const list = ELS['rnet-list'];
  const rows = list.children.length;
  const html = list.children.map(c => String(c.innerHTML || c.textContent || '')).join(' | ');
  process.stdout.write(JSON.stringify({rows:rows, html:html, errors:console_err}));
  process.exit(0);   // the panel re-arms its own poll timer forever, so exit once measured
}, 60);
"""


class RemotesPanelRender(unittest.TestCase):
    def _run(self):
        js = HARNESS.replace("__PANEL_JS__", km._LANDING_REMOTES_JS).replace("__TUNNELS__", json.dumps(TUNNELS))
        p = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, "panel JS crashed:\n%s" % p.stderr[-2000:])
        return json.loads(p.stdout or "{}")

    def test_an_attached_host_renders_a_row(self):
        out = self._run()
        self.assertEqual(out.get("errors"), [], "the refresh must not report a failure")
        self.assertGreaterEqual(out.get("rows", 0), 1,
                                "an attached host must render a row (this is the pmode ReferenceError bug)")

    def test_the_row_carries_the_detach_control(self):
        # Detach is the off switch for the reconnect relationship — the whole reason the list exists
        out = self._run()
        self.assertIn("Detach", out.get("html", ""))
        self.assertIn("TESTHOST", out.get("html", ""))

    def test_render_is_given_pmode_rather_than_reading_it_free(self):
        js = km._LANDING_REMOTES_JS
        self.assertIn("function render(ts,known,pmode)", js)
        self.assertIn("render(ts,(d&&d.known)||[],pmode)", js)


if __name__ == "__main__":
    unittest.main()
