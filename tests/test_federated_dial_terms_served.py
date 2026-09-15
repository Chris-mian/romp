"""A federated chat pane dials the remote with the PAGE'S OWN terms (the design in
plans/federated-pane-dial-terms.md; the code it decides). Two hermetic kernels on one box:
a hub that owns no session and a checked-in TESTHOST that owns two ("api" the watched tab, "worker" a cold
one). The hub's /chat page, in a skeleton posture (?skeleton=1) with the watched tab persisted as a REMOTE
session, dials TESTHOST's relay socket. Before this change the remote dial carried only app+wid, so the
remote built every tab whole, held no skeleton set, and filed an anonymous relay row: the cost the user's
long chat thread ran on. Now federation.ts reads the shim's __rompDialTerms and carries them to each remote
socket, so the remote is served the way the local pane is.

Red first at the base (the bare dial), green with the terms, on three observables:
  1. the relay dial URL (window.__dials) carries skeleton=1, delta=1, the watched tab's BARE sid as
     active=, and an iid namespaced by the hub's wid;
  2. the REMOTE kernel's /perf builds.chat.coldSkipped is >0 (it dieted the cold tab for the hub's
     skeleton client), 0 at the base;
  3. the REMOTE kernel's client-diag.jsonl carries a wsopen row of kind "relay" whose iid presence flag is
     true (the stored row records iid as present/absent, not the value: kernel.py _note_ws_open), where the
     bare dial left it the absent one that reads as an anonymous relay.

This lab boots subprocess kernels and drives Chromium; it loads no romp code in-process, so it carries no
in-process state-isolation preamble and is not scanned by tests/test_state_isolation_order.py (the same as
tests/test_chat_split_host_served.py, its two-kernel sibling). Synthetic only: placeholder uuids, hostname
TESTHOST, invented transcript text.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_R0 = "11111111-2222-4333-8444-000000000701"   # "api" on TESTHOST: the tab the page is watching
SID_R1 = "11111111-2222-4333-8444-000000000702"   # "worker" on TESTHOST: a cold tab the skeleton client diets
HOST = "TESTHOST"
REMOTE0 = HOST + ":" + SID_R0                      # …as the hub's dashboard carries it (federation.ts prefixId)
WID = "hublab"                                     # the hub pane's wid: the iid it sends is namespaced by this


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    """`pairs` CLOSED user/assistant turns for `sid` (an OPEN turn would invite the boot reconcile to resume it)."""
    out, parent = [], None
    filler = ["The ranking pass reads its weights from the notes-api config now.",
              "Tokenizer edge cases (hyphens, quotes) are covered by the new fixture set.",
              "Index rebuild time is dominated by the stemmer; caching its table halves it."]
    for i in range(pairs):
        u, a = "%s-u%02d" % (tag, i), "%s-a%02d" % (tag, i)
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "sessionId": sid, "cwd": cwd,
                    "timestamp": "2024-01-01T00:%02d:00Z" % (i % 60), "promptSource": "typed",
                    "message": {"role": "user", "content": "turn %d: what changed in the notes-api search?" % i}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "sessionId": sid, "cwd": cwd,
                    "timestamp": "2024-01-01T00:%02d:30Z" % (i % 60),
                    "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                "content": [{"type": "text", "text": filler[i % len(filler)]}]}})
        parent = a
    return "".join(json.dumps(r) + "\n" for r in out)


def _kernel(lab, name, port, token, sessions):
    """Boot one hermetic kernel: its own state root and dist, and `sessions` [(sid, name, tag)] with closed-turn transcripts."""
    state = os.path.join(lab, name, "xdg", "romp")
    claude = os.path.join(lab, name, "claude")
    cwd = os.path.join(lab, name, "proj")
    for d in ("names", "sdk", "states"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    os.makedirs(cwd, exist_ok=True)
    Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own hosts off (the conftest rule)
    Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
    proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
    os.makedirs(proj, exist_ok=True)
    for sid, sname, tag in sessions:
        Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (sname, cwd))
        Path(state, "sdk", sid + ".json").write_text(json.dumps(
            {"sid": sid, "name": sname, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
        Path(proj, sid + ".jsonl").write_text(_transcript(sid, tag, cwd, 6))
    env = _lab.kernel_env(os.path.join(lab, name), claude, os.path.join(lab, "dist"), port, token, ROMP_HOST_NAME=name.upper())
    log = os.path.join(lab, name + "-kernel.log")
    proc = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=1)
            return proc, log
        except Exception:
            time.sleep(0.5)
    proc.kill(); proc.wait()
    raise unittest.SkipTest("hermetic kernel %s never served /healthz here" % name)


# The Chromium driver: hook every socket URL the page dials (window.__dials), persist the watched tab as a
# REMOTE session before the page's scripts run (the shim's ?active= and __rompDialTerms read it), open the
# hub's /chat page in a skeleton posture, and wait for the relay socket to the remote. The kernel-side
# observables (the remote's /perf and client-diag) are read from Python after this returns.
DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const context = await browser.newContext({ viewport: { width: 1200, height: 700 } });
const page = await context.newPage();
const out = { dials: [], died: null, tabSeen: false };
page.on("pageerror", () => {});
await page.addInitScript(() => {
  window.__dials = []; const W = window.WebSocket;
  window.WebSocket = function (url, protos) { window.__dials.push(String(url)); return protos === undefined ? new W(url) : new W(url, protos); };
  window.WebSocket.prototype = W.prototype; window.WebSocket.CONNECTING = 0; window.WebSocket.OPEN = 1; window.WebSocket.CLOSING = 2; window.WebSocket.CLOSED = 3;
});
// the watched tab is a REMOTE session, host-prefixed as the dashboard carries it: __rompDialTerms carries it
// to the remote dial, where federation.ts strips the host to the bare sid the remote knows
await page.addInitScript((rid) => { try { localStorage.setItem("romp-vscode-state-chat", JSON.stringify({ activeId: rid })); } catch (e) {} }, cfg.remote0);
try {
  await page.goto(cfg.chat);
  // the FederationManager attaches every checked-in remote on load; wait for its relay socket to be dialed
  await page.waitForFunction(() => (window.__dials || []).some((u) => u.indexOf("/remote/TESTHOST/ws") !== -1), null, { timeout: 30000 });
  // the remote tab surfaces once the relay is open (best-effort confirmation; the assertions read __dials + the remote kernel)
  try { await page.locator("#tabs .tab", { hasText: "TESTHOST" }).first().waitFor({ timeout: 15000 }); out.tabSeen = true; } catch (e) {}
  // let the remote serve the skeleton client: the watched tab full, the cold tab skipped, the relay wsopen row filed
  await page.waitForTimeout(3000);
  out.dials = await page.evaluate(() => (window.__dials || []).slice());
} catch (e) {
  out.died = String(e).slice(0, 400);
  try { out.dials = await page.evaluate(() => (window.__dials || []).slice()); } catch (e2) {}
}
console.log("RESULT:" + JSON.stringify(out));
await browser.close();
"""


class FederatedDialTerms(unittest.TestCase):
    """Two kernels (a hub and a checked-in TESTHOST), one page, one driver run in setUpClass; each method asserts one observable."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        try:
            cls._boot()
        except BaseException:          # a skip OR a failure: never leave a kernel or a lab behind
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served lab needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served lab needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="federated-dial-terms-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))   # skips a concurrent build's staging files
        # the REMOTE owns both sessions (the watched tab + a cold one); the HUB owns none and shows them through the relay
        cls.rport, cls.rtoken = _free_port(), "testtok-remote-fed"
        cls.hport, cls.htoken = _free_port(), "testtok-hub-fed"
        rp, cls.rlog = _kernel(cls.lab, "testhost", cls.rport, cls.rtoken, [(SID_R0, "api", 1), (SID_R1, "worker", 2)])
        cls.procs.append(rp)
        hp, cls.hlog = _kernel(cls.lab, "hub", cls.hport, cls.htoken, [])
        cls.procs.append(hp)
        body = json.dumps({"host": HOST, "kernelPort": cls.rport, "busPort": _free_port(), "token": cls.rtoken}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/checkin?token=%s" % (cls.hport, cls.htoken), data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ans = json.loads(resp.read().decode())
        if not ans.get("ok"):
            raise unittest.SkipTest("the hub refused the check-in: %r" % ans)
        rows = []
        for _ in range(60):   # the hub's supervisor probes the peer and reports it up; the browser dials only then
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/tunnels?token=%s" % (cls.hport, cls.htoken), timeout=3) as r2:
                    rows = json.loads(r2.read().decode()).get("tunnels") or []
            except Exception:
                rows = []
            row = next((t for t in rows if t.get("host") == HOST), None)
            if row and row.get("status") == "up" and row.get("hasToken"):
                break
            time.sleep(0.5)
        else:
            raise unittest.SkipTest("the hub never reported the checked-in peer up: %r" % (rows,))
        cls.result, cls.driver_error = None, None
        cls._drive()
        cls.remote_chat_perf = cls._poll_remote_chat_perf()
        cls.remote_relay_rows = cls._read_relay_wsopen_rows()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?skeleton=1&wid=%s&token=%s" % (cls.hport, WID, cls.htoken),
                       "remote0": REMOTE0}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served leg needs one (CI installs none)")
        if p.returncode != 0:
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        if line is None:
            cls.driver_error = "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        cls.result = json.loads(line[len("RESULT:"):])

    @classmethod
    def _poll_remote_chat_perf(cls):
        """The remote's builds.chat counters, once its push cycle has served the hub's skeleton client (a bounded
        retry, as the /tunnels poll above: no busy loop). At the base the dial states no diet and coldSkipped stays 0."""
        chat = {}
        for _ in range(20):
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/perf?token=%s" % (cls.rport, cls.rtoken), timeout=3) as r:
                    perf = json.loads(r.read().decode())
                chat = (perf.get("builds") or {}).get("chat") or {}
            except Exception:
                chat = {}
            if chat.get("coldSkipped"):
                break
            time.sleep(0.5)
        return chat

    @classmethod
    def _read_relay_wsopen_rows(cls):
        """The remote kernel's wsopen rows of kind 'relay' (the hub's spliced dial). data.iid is a PRESENCE flag,
        not the value (kernel.py _note_ws_open): true names a per-pane iid, false is the anonymous relay."""
        path = os.path.join(cls.lab, "testhost", "xdg", "romp", "client-diag.jsonl")
        rows = []
        for _ in range(20):
            rows = []
            try:
                with open(path) as fh:
                    for ln in fh:
                        try:
                            rec = json.loads(ln)
                        except ValueError:
                            continue
                        if rec.get("what") == "wsopen" and (rec.get("data") or {}).get("kind") == "relay":
                            rows.append(rec)
            except OSError:
                rows = []
            if rows:
                break
            time.sleep(0.3)
        return rows

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _driver_ran(self):
        if getattr(type(self), "driver_error", None):
            self.fail(type(self).driver_error)
        if getattr(type(self), "result", None) is None:
            raise unittest.SkipTest("the driver produced no result")

    def _relay_dial(self):
        self._driver_ran()
        relay = [u for u in self.result["dials"] if "/remote/TESTHOST/ws" in u]
        self.assertTrue(relay, "the hub page dialed the remote's relay socket: %r" % self.result["dials"])
        return relay[0]

    def test_the_hub_dials_the_remote_relay_socket(self):
        self.assertTrue(self._relay_dial())

    def test_the_remote_dial_carries_the_pages_terms(self):
        qs = parse_qs(urlsplit(self._relay_dial()).query)
        self.assertEqual(qs.get("app"), ["chat"], "the pane's app")
        self.assertEqual(qs.get("delta"), ["1"], "delta rides every dial, as the local pane's does")
        self.assertEqual(qs.get("skeleton"), ["1"], "the page's skeleton posture rode the remote dial")
        self.assertEqual(qs.get("active"), [SID_R0], "the watched remote tab, stripped to its bare sid")

    def test_the_remote_iid_is_namespaced_by_the_hub_wid(self):
        qs = parse_qs(urlsplit(self._relay_dial()).query)
        iid = (qs.get("iid") or [""])[0]
        self.assertTrue(iid.startswith(WID + ":"),
                        "the iid a hub pane sends is namespaced by its wid so it cannot collide with the remote's own page: %r" % iid)
        self.assertGreater(len(iid), len(WID) + 1, "…and carries the page's own instance id after the prefix")

    def test_the_remote_diets_its_cold_tab_for_the_skeleton_client(self):
        self._driver_ran()
        self.assertGreater(self.remote_chat_perf.get("coldSkipped") or 0, 0,
                           "the remote skipped its cold tab for the hub's skeleton client: %r" % self.remote_chat_perf)

    def test_the_remote_relay_wsopen_row_names_a_per_pane_iid(self):
        self._driver_ran()
        rows = self.remote_relay_rows
        self.assertTrue(rows, "the remote filed a relay wsopen row for the hub's spliced dial")
        self.assertTrue(any((r.get("data") or {}).get("iid") for r in rows),
                        "a relay row names a per-pane iid (present), not the absent one that reads as an anonymous relay: %r"
                        % [r.get("data") for r in rows])


if __name__ == "__main__":
    unittest.main()
