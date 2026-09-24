#!/usr/bin/env python3
"""Every client-diag row says which page build wrote it and which kernel boot that page loaded against (2026-09-23).

The user reloads often, and client-diag.jsonl rows carried no word of the page that filed them: reading a row after a
deploy, nobody could tell whether it came from the old page code or the new, so every attribution of a symptom to a
change was a guess. Now the page's one diag door stamps each row as it leaves:
- the pane shim's send() (every pane row takes it: the bundle's posts through acquireVsCodeApi, the reload core's
  __rompDiag, federation's own rows through __rompLocalSend), with LOADEDV, the dist token the page was served with,
  and BOOTID, the serving kernel's boot id baked beside it;
- the shell's shellDiag, its twin, reading the landing's reload core (loaded, boot) at the moment the row leaves;
and the kernel's clientDiag branch keeps both, `build` an int and `boot` a string, null for a page that sent none (a page
that predates the stamp, the VS Code webview), which itself says old code.

Legs: the handler alone; the REAL shim core under node (each door, a queued row flushed on the redial, a non-diag
message untouched, the caller's object untouched); the shell's stamp executed; the reload core's baked boot kept
through a restart re-latch; and the two joined (the shim's own stamped row through the real dispatch, read back from
the file). Synthetic only: placeholder UUIDs, TESTHOST. Never run raw: a raw run skips conftest's floor.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_cdiag_build_boot", os.path.join(BIN, "romp-kernel"))

WID = "11111111-2222-3333-4444-555555555571"

# The browser the shim thinks it runs in (the tests/test_client_diag_reconnect_stamp.py harness, no federation): `var`
# at module scope shadows node's own WebSocket / setTimeout / MessageChannel for the core that follows in the same file.
_SHIM_HARNESS = r"""
var NOW=1000000;Date.now=function(){return NOW;};
var timers=[];var setTimeout=function(fn,ms){timers.push({fn:fn,ms:ms,live:true});return timers.length;};
var clearTimeout=function(id){if(id&&timers[id-1])timers[id-1].live=false;};
var setInterval=function(fn,ms){return 1;};
var docL={};var document={visibilityState:"visible",wasDiscarded:false,
addEventListener:function(t,f){(docL[t]=docL[t]||[]).push(f);},getElementById:function(){return null;}};
var window={innerWidth:800,innerHeight:600,parent:{postMessage:function(m){}},
dispatchEvent:function(e){return true;},sessionStorage:{getItem:function(){return "";}}};
var location={protocol:"http:",host:"TESTHOST",search:""};
var localStorage={getItem:function(){return null;},setItem:function(){}};
var sockets=[];function WebSocket(url){this.url=url;this.readyState=0;this.sent=[];sockets.push(this);}
WebSocket.prototype.send=function(s){this.sent.push(s);};WebSocket.prototype.close=function(){this.readyState=3;};
function MessageChannel(){this.port1={onmessage:null};this.port2={postMessage:function(d){}};}
function sock(){return sockets[sockets.length-1];}
function open(){var s=sock();s.readyState=1;s.onopen();return s;}
function redial(){var live=timers.filter(function(t){return t.live&&t.fn.name==="connect";});live[live.length-1].fn();}
"""

_SCENARIO = r"""
var first=open();
window.__rompLocalSend({type:"clientDiag",surface:"chat",what:"via-local",data:{n:1}});
var api=window.acquireVsCodeApi();var orig={type:"clientDiag",surface:"chat",what:"via-api",data:{n:2}};api.postMessage(orig);
window.__rompDiag("held",{reason:"build"});
api.postMessage({type:"activeTab",id:"11111111-2222-3333-4444-555555555572"});
var onFirst=first.sent.map(function(x){return JSON.parse(x);});
first.readyState=3;first.onclose();                                   // the drop: its wsclose row queues for the redial
window.__rompLocalSend({type:"clientDiag",surface:"chat",what:"while-down",data:{}});
redial();var second=open();
var onSecond=second.sent.map(function(x){return JSON.parse(x);});
process.stdout.write(JSON.stringify({first:onFirst,second:onSecond,origKeys:Object.keys(orig).sort()}));
"""


def _run_shim(v=123):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not installed")
    with tempfile.TemporaryDirectory() as fx:
        path = os.path.join(fx, "run.js")
        with open(path, "w") as f:
            f.write(_SHIM_HARNESS + km._shim_core_js(app="chat", v=v) + "\n" + _SCENARIO)
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("node failed:\n" + r.stderr)
    return json.loads(r.stdout)


def _node(js):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not installed")
    with tempfile.TemporaryDirectory() as fx:
        path = os.path.join(fx, "run.js")
        with open(path, "w") as f:
            f.write(js)
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("node failed:\n" + r.stderr)
    return json.loads(r.stdout)


class _State(unittest.TestCase):
    """A private state root per test (km.jd.STATE is shared by every module that loads the judge)."""
    def setUp(self):
        self._saved_state = km.jd.STATE
        self._td = tempfile.TemporaryDirectory()
        km.jd._rebind_state(pathlib.Path(self._td.name))
        self.fp = km.jd.STATE / "client-diag.jsonl"

    def tearDown(self):
        km.jd._rebind_state(self._saved_state)
        self._td.cleanup()

    def rows(self):
        return [json.loads(line) for line in self.fp.read_text(encoding="utf-8").splitlines() if line.strip()]

    def post(self, msg, client=None):
        km.Handler._dispatch_ws(None, dict({"type": "clientDiag", "surface": "chat", "what": "probe", "data": {}}, **msg), client or {"wid": WID})


class TheKernelKeepsTheStamp(_State):
    def test_build_and_boot_ride_every_row_in_the_row_order(self):
        self.post({"build": 4321, "boot": "12345.1700000000"})
        row = self.rows()[0]
        self.assertEqual(row["build"], 4321)
        self.assertEqual(row["boot"], "12345.1700000000")
        self.assertEqual(list(row), ["t", "wid", "surface", "what", "reconnect", "build", "boot", "data"], "the stamp sits beside the socket's, ahead of the data")

    def test_a_row_without_a_stamp_reads_null_for_both(self):
        # a page that predates the stamp, or a host that sends none (the VS Code webview): null is the statement
        self.post({})
        row = self.rows()[0]
        self.assertIsNone(row["build"])
        self.assertIsNone(row["boot"])

    def test_the_stamp_is_typed_like_the_page_sends_it(self):
        for bad_build, bad_boot in ((True, 7), ("123", ""), (1.5, None), (None, ["x"])):
            self.post({"build": bad_build, "boot": bad_boot})
        for row in self.rows():
            self.assertIsNone(row["build"], row)   # assertIsNone: True is an int in Python, and a bool is not a build
            self.assertIsNone(row["boot"], row)
        self.post({"build": 0, "boot": "x" * 200})
        row = self.rows()[-1]
        self.assertEqual(row["build"], 0, "a page served without a token files 0, which is a token")
        self.assertEqual(len(row["boot"]), 40, "bounded")


class TheShimStampsEveryDoor(unittest.TestCase):
    def test_every_diag_row_leaves_the_shim_with_the_pages_build_and_boot(self):
        out = _run_shim(v=123)
        diag = [m for m in out["first"] if m.get("type") == "clientDiag"]
        self.assertEqual([m["what"] for m in diag], ["via-local", "via-api", "held"], "the bundle's door, the page API's and the reload core's")
        for m in diag:
            self.assertEqual(m["build"], 123, m)
            self.assertEqual(m["boot"], km._BOOT_ID, m)
        self.assertEqual(diag[2]["surface"], "reload-core")
        other = [m for m in out["first"] if m.get("type") == "activeTab"]
        self.assertEqual(len(other), 1)
        self.assertNotIn("build", other[0], "only diag rows are stamped")
        self.assertNotIn("boot", other[0])
        self.assertEqual(out["origKeys"], ["data", "surface", "type", "what"], "the caller's object is untouched: the stamp rides a copy")

    def test_a_row_queued_while_the_socket_was_down_is_stamped_on_the_redial(self):
        out = _run_shim(v=123)
        diag = {m["what"]: m for m in out["second"] if m.get("type") == "clientDiag"}
        self.assertIn("wsclose", diag, "the drop's own row rides the redial")
        self.assertIn("while-down", diag)
        for what in ("wsclose", "while-down"):
            self.assertEqual(diag[what]["build"], 123)
            self.assertEqual(diag[what]["boot"], km._BOOT_ID)

    def test_the_shim_bakes_the_serving_kernels_boot_beside_its_build(self):
        js = km._shim("feed", 77)
        self.assertIn("var LOADEDV=77;var BOOTID=%s;" % json.dumps(km._BOOT_ID), js)
        self.assertIn('function send(m){if(m&&m.type==="clientDiag")m=diagStamp(m);var s=JSON.stringify(m);', js,
                      "stamped in the one door, before the string is made (queued or sent)")


class TheShellStampsAsTheRowLeaves(unittest.TestCase):
    def test_both_of_the_shells_send_points_stamp(self):
        js = km._LANDING_MOBILE_JS
        self.assertIn("if(shellSock&&shellSock.readyState===1){try{shellSock.send(JSON.stringify(diagStamp(m)));}catch(e){}}", js)
        self.assertIn("shellSock=ws;var q=diagQ;diagQ=[];q.forEach(function(m){try{ws.send(JSON.stringify(diagStamp(m)));}catch(e){}});", js)
        self.assertIn("else if(diagQ.length<DIAGQ_MAX)diagQ.push(m);", js, "a queued row waits unstamped: the core parses after this script")

    def test_the_shells_stamp_reads_the_landings_reload_core(self):
        fn = re.search(r"function diagStamp\(m\)\{var R=window\.__rompReload.*?return c;\}", km._LANDING_MOBILE_JS)
        self.assertIsNotNone(fn)
        out = _node("var window={};" + fn.group(0) + r"""
var m={type:"clientDiag",surface:"shell",what:"deeplink",data:{}};
var before=diagStamp(m);
window.__rompReload={loaded:88,boot:"555.1700000001"};
var after=diagStamp(m);
process.stdout.write(JSON.stringify({before:before,after:after,m:Object.keys(m).sort()}));""")
        self.assertIsNone(out["before"]["build"], "no core yet: null, never a guess")
        self.assertIsNone(out["before"]["boot"])
        self.assertEqual(out["after"]["build"], 88)
        self.assertEqual(out["after"]["boot"], "555.1700000001")
        self.assertEqual(out["m"], ["data", "surface", "type", "what"], "the queued row itself is untouched")
        # the landing carries the core the stamp reads, and the core exposes the two baked values
        html = km._landing()
        self.assertIn("window.__rompReload=R;", html)
        self.assertIn("loaded:LOADED,boot:BOOT};", km._RELOAD_CORE_JS)

    def test_the_cores_boot_is_the_one_the_page_loaded_against_even_after_a_restart(self):
        # R.boot is read by the shell's stamp; a restart re-latches the core's private BOOT (noteVersion), and the stamp
        # must still name the boot the page LOADED against, which is what says old code from new
        harness = r"""
var document={addEventListener:function(){},getSelection:function(){return null;},hasFocus:function(){return true;},getElementById:function(){return null;},
activeElement:null,body:{classList:{remove:function(){}}},querySelectorAll:function(){return [];}};
var window={addEventListener:function(){}};window.parent=window;
var location={pathname:"/",reload:function(){}};
var sessionStorage={setItem:function(){},getItem:function(){return null;},removeItem:function(){}};
var localStorage={setItem:function(){},getItem:function(){return null;},removeItem:function(){}};
function fetch(){return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(null);}});}
"""
        out = _node(harness + km._reload_core_js(9, "100.1700000000", "abc") + r"""
var R=window.__rompReload;var at={loaded:R.loaded,boot:R.boot};
R.noteVersion({boot:"200.1700000099",dist_ver:9,code_ident:"abc"});
process.stdout.write(JSON.stringify({at:at,after:{loaded:R.loaded,boot:R.boot},restarted:R.restarted()}));""")
        self.assertEqual(out["at"], {"loaded": 9, "boot": "100.1700000000"})
        self.assertEqual(out["restarted"], 1, "the restart was seen")
        self.assertEqual(out["after"], {"loaded": 9, "boot": "100.1700000000"}, "…and the page's own boot still reads the load-time one")


class ThePairInTheLog(_State):
    def test_the_shims_own_stamped_row_lands_in_the_file_with_the_stamp(self):
        out = _run_shim(v=321)
        row = next(m for m in out["first"] if m.get("what") == "via-api")
        km.Handler._dispatch_ws(None, row, {"wid": WID, "redial": True})
        got = self.rows()[0]
        self.assertEqual((got["what"], got["build"], got["boot"], got["reconnect"]), ("via-api", 321, km._BOOT_ID, True))
        self.assertEqual(got["data"], {"n": 2})


if __name__ == "__main__":
    unittest.main()
