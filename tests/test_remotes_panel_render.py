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
        "host": "TESTHOST", "kernelPort": 29855, "localPort": 51000, "busPort": 51001,
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
  return {id:id, hidden:true, textContent:'', title:'', style:{}, value:'', className:'',
    children:[], _listeners:{}, _html:'',
    // Assigning innerHTML replaces an element's contents, so it must drop appended children too. Without
    // that, render()'s opening `list.innerHTML=''` left the previous pass's rows in place and every
    // refresh doubled the list.
    get innerHTML(){return this._html;}, set innerHTML(v){this._html=v; this.children=[];},
    classList:{_s:new Set(), add(){}, remove(){}, toggle(){}, contains(){return false;}},
    appendChild(c){this.children.push(c); return c;},
    querySelector(){return null;}, querySelectorAll(){return [];},
    addEventListener(k,f){this._listeners[k]=f;}, removeEventListener(){},
    setAttribute(){}, getAttribute(){return null;}, focus(){}, select(){}, remove(){},
    click(){ if(this.onclick) this.onclick({stopPropagation(){}, preventDefault(){}}); },
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
const POSTS = [];               // every write the panel makes, so a test can assert what Attach sent
function fetch(url, opts){
  if (opts && opts.method === 'POST') {
    POSTS.push({url:url, body:JSON.parse(opts.body || '{}')});
    return Promise.resolve({ ok:true, json(){ return Promise.resolve({ok:true}); } });
  }
  const body = url.indexOf('/ssh-hosts') >= 0 ? {hosts:['TESTHOST']} : TUNNELS;
  return Promise.resolve({ ok:true, json(){ return Promise.resolve(body); } });
}
const ALERTS = [];
function alert(m){ ALERTS.push(String(m)); }
const setTimeout_ = setTimeout;
const window = { addEventListener(){}, location:{reload(){}} };
const console_err = [];
const console = { error(...a){ console_err.push(a.map(String).join(' ')); }, log(){}, warn(){} };

__PANEL_JS__

// drive it: open the panel (sets hidden=false, loads hosts, refreshes) and let the promises settle
ELS['rnet-back'].hidden = false;
window.__rompOpenNet && window.__rompOpenNet();
// A host is an ITEM of two lines, so the markup lives on the item's children rather than on the node
// appended to the list. Walk the whole subtree so this stays true of whatever shape the rows take next.
function collect(el){
  let s = String(el.className || '') + ' ' + String(el.innerHTML || el.textContent || '');
  (el.children || []).forEach(c => { s += ' ' + collect(c); });
  return s;
}
setTimeout_(() => {
  __DRIVE__                    // a test may click things here; then we let its promises settle too
  setTimeout_(() => {
    const list = ELS['rnet-list'];
    const rows = list.children.length;
    const html = list.children.map(collect).join(' | ');
    const add = ELS['rnet-add'], plus = ELS['rnet-plus'], dl = ELS['rnet-hosts'];
    process.stdout.write(JSON.stringify({rows:rows, html:html, errors:console_err,
      addHidden:!!add.hidden, plusHidden:!!plus.hidden, hostsHtml:String(dl.innerHTML||''),
      posts:POSTS, alerts:ALERTS}));
    process.exit(0);   // the panel re-arms its own poll timer forever, so exit once measured
  }, 40);
}, 60);
"""


class RemotesPanelRender(unittest.TestCase):
    def _run(self, drive="", tunnels=None):
        js = (HARNESS.replace("__PANEL_JS__", km._LANDING_REMOTES_JS)
                     .replace("__TUNNELS__", json.dumps(tunnels if tunnels is not None else TUNNELS))
                     .replace("__DRIVE__", drive))
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
        self.assertIn("function render(ts,known,pmode,via,rholds)", js)
        self.assertIn("render(ts,(d&&d.known)||[],pmode,(d&&d.viaReach)||[],(d&&d.remoteHolds)||[])", js)

    def test_the_per_host_settings_sit_on_their_own_line(self):
        # Trust and check-in are set once and left; Detach is an act. Splitting them off line 1 is what
        # stops a phone-width row from pushing Detach past the right edge.
        out = self._run()
        self.assertIn("rnet-row2", out.get("html", ""))
        self.assertIn("rnet-trust", out.get("html", ""))

    def test_the_trust_options_say_what_they_mean(self):
        # A dropdown reading trusted/directed/isolated makes you hover each one to find out what it does.
        out = self._run()
        html = out.get("html", "")
        self.assertIn("directed (held for you)", html)
        self.assertIn("trusted (auto-accept)", html)
        self.assertIn("isolated (no mail)", html)

    def test_the_checkin_box_is_named_for_what_it_does(self):
        # It publishes THIS machine to the remote. Its old label, "keep connected", read as the reconnect
        # setting, so the tooltip had to spend a sentence denying that.
        out = self._run()
        self.assertIn("Share my sessions there", out.get("html", ""))
        self.assertNotIn("keep connected", out.get("html", ""))

    def test_the_add_form_is_closed_until_the_plus_is_clicked(self):
        # Progressive disclosure: the panel's subject is the hosts you have, not the act of adding one.
        shut = self._run()
        self.assertTrue(shut.get("addHidden"), "the add form must start collapsed")
        self.assertFalse(shut.get("plusHidden"), "+ Add a host must be the visible affordance")
        opened = self._run(drive="ELS['rnet-plus'].click();")
        self.assertFalse(opened.get("addHidden"), "+ must open the add form")
        self.assertTrue(opened.get("plusHidden"), "+ gives way to the form it opened")

    def test_a_host_absent_from_ssh_config_can_be_typed_and_attached(self):
        # The point of the free-text box: ssh takes any target you could type after `ssh`, so ~/.ssh/config
        # is a source of completions, not the set of machines you can reach.
        out = self._run(drive="ELS['rnet-plus'].click();"
                              "ELS['rnet-host'].value='someone@198.51.100.7';"
                              "ELS['rnet-attach'].click();")
        posts = [p for p in out.get("posts", []) if p["url"] == "/tunnels"]
        self.assertEqual([p["body"]["host"] for p in posts], ["someone@198.51.100.7"])
        self.assertEqual(out.get("alerts"), [], "a good host must not report a failure")

    def test_a_rejected_host_is_reported_rather_than_swallowed(self):
        # Typos are newly possible now that the host is typed. Fail loudly (CLAUDE.md).
        out = self._run(drive="ELS['rnet-plus'].click();"
                              "ELS['rnet-host'].value='nope';"
                              "fetch=function(u,o){if(o&&o.method==='POST')"
                              "return Promise.resolve({json(){return Promise.resolve({ok:false,error:'invalid host'});}});"
                              "return Promise.resolve({json(){return Promise.resolve(TUNNELS);}});};"
                              "ELS['rnet-attach'].click();")
        self.assertTrue(any("invalid host" in a for a in out.get("alerts", [])),
                        "a refused attach must say so: %r" % (out.get("alerts"),))

    def test_known_and_attached_hosts_both_feed_the_completions(self):
        # What makes a typed-in host stick: attaching records it, so it completes from then on.
        tun = json.loads(json.dumps(TUNNELS))
        tun["known"] = [{"host": "otherbox", "trust": "trusted", "lastAttachedAt": 1}]
        out = self._run(tunnels=tun)
        self.assertIn("TESTHOST", out.get("hostsHtml", ""))
        self.assertIn("otherbox", out.get("hostsHtml", ""))

    def test_a_host_that_gave_up_offers_the_way_back_in(self):
        # It is no longer being dialed, and the attach control now lives behind +, so the row itself has
        # to carry the retry. The label used to point at a control that would no longer be on screen.
        tun = json.loads(json.dumps(TUNNELS))
        tun["tunnels"][0].update({"status": "gave-up", "gaveUp": True, "fails": 5})
        out = self._run(tunnels=tun)
        self.assertIn("Retry", out.get("html", ""))
        self.assertIn("stopped trying", out.get("html", ""))


if __name__ == "__main__":
    unittest.main()
