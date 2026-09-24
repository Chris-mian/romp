"""The Artifacts pane lists and serves a REMOTE session (plans/artifacts-pane.md section 9.1, 2026-09-20): a hub kernel and a
second hermetic kernel checked in as host TESTHOST (the mobile handshake, no ssh; the remote file-preview lab's shape), the
remote holding a session whose transcript names files that exist on the REMOTE disk only, the hub holding a local session of
its own. The hub's dashboard shows both tabs; the pane's picker lists both (the shell's union of the chat's open tabs), the
remote row wearing the strip's quiet host prefix and the name bold in its identity colour, in the menu tokens' card; picking
the remote lists its files, answered by the kernel that owns it (federation routes the listing by the sid, the answer comes
back under the host prefix), and its thumbnail loads through the hub's /remote/TESTHOST/file relay with the bare sid. Picking
the local session lists its own file. Synthetic throughout: placeholder sids, TESTHOST, invented file names.

The picker's mark (2026-09-23, a flake on main twice, the PR 2013 and PR 2061 merges): the card is a SNAPSHOT of the pane's
selection at the moment it opens, and the selection follows the chat's active tab over two roads that land in their own time,
the kernel's activeChat frame answering the pane's ready and the shell's relay of a switch; and at boot the chat's active tab is
itself a race: the chat ADOPTS the first session frame that lands (render.ts, the arrival adoption when nothing is active), the
hub's own over its socket or the remote's over the host relay, whichever comes first (both failing payloads read the REMOTE row
current, the hub's own row not).
The old read opened the card once the remote row was listed and read the mark at once, so it raced the selection's arrival and
the boot's adoption. Now the driver makes the hub's own tab the chat's active tab by a real switch (or confirms it), holds on
the pane's render of that selection (its button wearing the name, the page's own paint), opens the card and holds on the mark
(a synchronous predicate polled by the driver on a bounded cadence), and pins the holds' outcomes beside the read, never a
longer wall-clock cap. The race is reproduced on purpose: the FIRST activeChat frame each of the pane's sockets receives (the
ready answer, the frame the boot race is about; the reload leg's new socket delays its first again) is held for a second in
the artifacts frame (an init-script shim), so a read that does not hold reads no mark or the wrong one every time; every later
frame passes at once, since a delayed echo of a switch would widen the pane's echo window and flip a later pick back (the
second contributor's post-merge review of PR 2075). Two more holds make the leg exact: the boot state is made deterministic
by a REAL pre-switch to the remote tab before the switch to the hub's own, so the switch's outcome has one meaning (a confirmed
already-active tab would have been vacuous, and a broken switch green on hub-first boots); and after that switch the driver
waits for the kernel's echo of it, the frame carrying the nonce of the HUB'S OWN relay, which must be the LAST relay recorded
(both recorded by the init script; the last relay alone would be satisfied by the pre-switch's own pair on a hub-first boot, the
second contributor's post-merge review of PR 2086 at 12:40Z, and the last HUB relay alone by a hub re-announcement recorded
before the pre-switch, the same reviewer on PR 2091 at 15:02Z; the driver records such a re-announcement on purpose, so the
constant-true switch mutant reds on echoOk; and on a REMOTE-FIRST boot the pre-switch relays nothing, so a stand-in remote relay
follows the plant, the same reviewer on PR 2097 at 16:50Z, and a second short driver run boots remote-first on purpose so both
boots are checked in), before the
card opens, so no echo can move the selection under the read or the pick that follows."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment
from test_live_paused_window_browser import _free_port  # noqa: E402

SID_R = "11111111-2222-3333-4444-000000000951"   # the remote's session (api), files on the remote disk only
SID_L = "11111111-2222-3333-4444-000000000952"   # the hub's own session (web)
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0000000030001"
                    "5c8e2c2b0000000049454e44ae426082")   # a real 1x1 PNG, so the browser's decode says loaded
COLOR_R = ("#9cd2ff", "#0c1a2e")
COLOR_L = ("#1EA1EB", "#ffffff")

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = { errors: [] };
const ctx = await browser.newContext({ viewport: { width: 1500, height: 900 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => out.errors.push(String(e).slice(0, 200)));
// the pane enabled in the gear's Panes section (the experimental record's row), written as the gear writes it
await page.addInitScript(() => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.panes = Object.assign({}, s.panes || {}, { artifacts: true }); localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {} });
// every frame records its outbound frames by type and sid (the pane's watch and listing on the host relay: the frame-order pin of the
// reload leg) and counts the relay's opens; installed before any navigation, so the reload's boot is read whole
await page.addInitScript((delay) => { window.__sends = []; window.__relayUps = 0;
  window.addEventListener("romp:hostRelayUp", () => { window.__relayUps++; });
  // the delayed frame (the reproduction of the picker-mark race, see the module docstring): in the artifacts frame alone, the FIRST
  // kernel activeChat frame a socket receives reaches the page's listener a second late, so the pane's selection lands after a card
  // opened at once; every later frame passes at once (a delayed echo of a switch would widen the pane's echo window). The frames
  // delivered (the kernel's echoes) and the shell's relays are recorded per id and nonce for the echo hold
  window.__echoes = []; window.__relays = [];
  if (/\/artifacts(\?|$)/.test(location.pathname + location.search)) {
    window.addEventListener("message", (e) => { const m = e && e.data; if (m && m.romp === "activeChat") window.__relays.push({ id: m.id, nonce: m.nonce }); });
    const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, "onmessage");
    if (desc && desc.set) Object.defineProperty(WebSocket.prototype, "onmessage", { configurable: true, get() { return desc.get.call(this); },
      set(fn) { desc.set.call(this, (ev) => { let m = null; try { m = JSON.parse(ev.data); } catch (e) {}
        if (m && m.type === "activeChat") { const deliver = () => { window.__echoes.push({ id: m.id, nonce: m.nonce }); fn.call(this, ev); };
          if (delay > 0 && !this.__firstActiveChatSeen) { this.__firstActiveChatSeen = true; setTimeout(deliver, delay); return; } return deliver(); }
        return fn.call(this, ev); }); } });
  }
  const orig = WebSocket.prototype.send; WebSocket.prototype.send = function (d) { try { const m = JSON.parse(d); if (m && m.type) window.__sends.push({ type: m.type, sid: m.sid || null }); } catch (e) {} return orig.call(this, d); }; }, cfg.delayActiveChat || 0);
const waitFile = async (p, ms) => { for (let i = 0; i < ms / 250; i++) { if (fs.existsSync(p)) return true; await page.waitForTimeout(250); } return false; };
await page.goto(cfg.landing);
await page.waitForSelector("#f-chat", { timeout: 30000 });
const findFrame = async (re) => { for (let i = 0; i < 150; i++) { const f = page.frames().find((fr) => re.test(fr.url())); if (f) return f; await page.waitForTimeout(200); } return null; };
const cf = await findFrame(/\/chat(\?|$)/);
// the remote tab in the hub's strip: federation merges the checked-in host's tabs under its prefix
if (cf) await cf.waitForSelector('#tabs .tab[data-id="TESTHOST:' + cfg.rsid + '"]', { timeout: 90000 }).catch(() => {});
out.tabs = cf ? await cf.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.getAttribute("data-id"))) : null;
// a hold that ran out is false; any other failure of a hold (a detached frame, a thrown predicate) is a fault and surfaces
const timedOut = (e) => { if (e && e.name === "TimeoutError") return false; throw e; };
// a SWITCH is a click on a tab that is not the column's active one; the wait confirms the strip's own state
const switchTo = async (col, sid) => { await col.click('#tabs .tab[data-id="' + sid + '"] .tab-label', { timeout: 15000 }).catch(() => {}); return col.waitForFunction((t) => { const a = document.querySelector("#tabs .tab.active"); return !!a && a.getAttribute("data-id") === t; }, sid, { timeout: 15000 }).then(() => true).catch(timedOut); };
// the emulated REMOTE-FIRST boot (the second contributor's post-merge review of PR 2097 at 16:50Z): the remote tab made the chat's
// active tab before the pane exists, so the pane boots with the remote selected and the pre-switch below is a confirmation
if (cfg.bootRemoteFirst && cf) out.forcedRemoteFirst = await switchTo(cf, "TESTHOST:" + cfg.rsid);
await page.click('.rail-btn[data-pane="artifacts"]');
let fr = await findFrame(/\/artifacts(\?|$)/);
out.frame = !!fr;
if (fr) {
  await fr.waitForSelector("#art-pick", { timeout: 30000 }).catch(() => {});
  // the mark follows the pane's selection, the chat's active tab: make the boot state deterministic by a REAL pre-switch to the remote
  // tab, then make the hub's own the active tab by a real switch, wait for the kernel's echo of that switch (the frame carrying the
  // nonce of the hub's own relay, the last relay recorded), hold on the pane's render of the selection (the button wearing the name),
  // then open the card and hold on the mark (the module docstring)
  const t0 = Date.now();
  const bootActive = cf ? await cf.evaluate(() => { const a = document.querySelector("#tabs .tab.active"); return a ? a.getAttribute("data-id") : null; }) : null;   // which boot the run exercised: the hub's own first, or the remote's
  // the checked-in red-first (the review of PR 2091): a hub re-announcement, a relay of the hub's own tab and its echo, recorded in
  // the pane BEFORE the pre-switch, the pair a boot whose hub session frame is processed after the pane's document exists would
  // record; a wait that took the last hub relay would be satisfied by it, and the constant-true switch mutant would keep echoOk true
  await fr.evaluate((lsid) => { (window.__relays = window.__relays || []).push({ id: lsid, nonce: -1 }); (window.__echoes = window.__echoes || []).push({ id: lsid, nonce: -1 }); }, cfg.lsid);
  // on a boot that is not the hub's the pre-switch clicks the already active tab and relays nothing (setActive returns early), so the
  // plant would stay the last relay overall and satisfy the wait alone: a stand-in remote relay (no echo) stands where the real
  // pre-switch's relay would (the same review, executed: the constant-true switch mutant then reds on echoOk on both boots)
  if (bootActive !== cfg.lsid) await fr.evaluate((rid) => { (window.__relays = window.__relays || []).push({ id: rid, nonce: -2 }); }, "TESTHOST:" + cfg.rsid);
  const preSwitched = cf ? await switchTo(cf, "TESTHOST:" + cfg.rsid) : false;
  const switched = cf ? await switchTo(cf, cfg.lsid) : false;
  // the echo of THE switch to the hub's own tab: the LAST relay overall must carry the hub's id, and an echo its nonce. The last relay
  // alone would be the pre-switch's pair on a hub-first boot; the last HUB relay alone would be a hub relay recorded before the
  // pre-switch (a boot re-announcement, injected above on purpose), echoed long before the switch: either would certify nothing
  // about the switch (the second contributor's post-merge reviews of PR 2086 at 12:40Z and PR 2091 at 15:02Z)
  const echoOk = switched ? await fr.waitForFunction((lsid) => { const r = (window.__relays || []).slice(-1)[0]; return !!r && r.id === lsid && typeof r.nonce === "number" && (window.__echoes || []).some((e) => e.id === r.id && e.nonce === r.nonce); }, cfg.lsid, { timeout: 30000 }).then(() => true).catch(timedOut) : false;
  const buttonOk = await fr.waitForFunction(() => { const n = document.querySelector("#art-pick .session-name"); return !!n && n.textContent === "web"; }, null, { timeout: 30000 }).then(() => true).catch(timedOut);
  await fr.click("#art-pick", { timeout: 15000 }).catch(() => {});
  // the picker's rows are the shell's union of the open tabs, the shown one marked: hold for the remote row AND the mark on the hub's own
  const markOk = await fr.waitForFunction((a) => !!document.querySelector('#art-picker .ctx-item[data-sid="TESTHOST:' + a.rsid + '"]') && !!document.querySelector('#art-picker .ctx-item.current[data-sid="' + a.lsid + '"]'), { rsid: cfg.rsid, lsid: cfg.lsid }, { timeout: 30000 }).then(() => true).catch(timedOut);
  out.cardHolds = { bootActive: bootActive === cfg.lsid ? "hub" : (bootActive === "TESTHOST:" + cfg.rsid ? "remote" : bootActive), preSwitched, switched, echoOk, buttonOk, markOk, ms: Date.now() - t0 };
  out.card = await fr.evaluate(() => {
    const card = document.getElementById("art-picker"); if (!card) return null;
    const probe = document.createElement("div"); probe.style.background = "var(--menu-bg)"; probe.style.position = "absolute"; document.body.appendChild(probe);
    const menuBg = getComputedStyle(probe).backgroundColor; probe.remove();
    const rows = Array.from(card.querySelectorAll(".ctx-item[data-sid]")).map((r) => { const hp = r.querySelector(".host-prefix"); const nm = r.querySelector(".session-name");
      return { sid: r.getAttribute("data-sid"), prefix: hp ? hp.textContent : null, name: nm ? nm.textContent : null, current: r.classList.contains("current"),
        prefixStyle: hp ? { fontStyle: getComputedStyle(hp).fontStyle, fontWeight: getComputedStyle(hp).fontWeight, fontSize: parseFloat(getComputedStyle(hp).fontSize) } : null,
        nameStyle: nm ? { fontWeight: getComputedStyle(nm).fontWeight, fontSize: parseFloat(getComputedStyle(nm).fontSize), color: getComputedStyle(nm).color, chip: nm.style.getPropertyValue("--chip-bg") } : null }; });
    return { background: getComputedStyle(card).backgroundColor, menuBg, classes: Array.from(card.classList), rows, fg: getComputedStyle(document.body).color };
  });
  if (cfg.pickerOnly) { process.stdout.write("RESULT:" + JSON.stringify(out) + "\n"); await browser.close(); process.exit(0); }   // the remote-first run covers the picker leg alone
  // pick the remote session: the listing is answered by the kernel that owns it, the thumbnail rides the host relay
  await fr.click('#art-picker .ctx-item[data-sid="TESTHOST:' + cfg.rsid + '"]', { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => document.querySelectorAll(".art-row").length >= 2, null, { timeout: 90000 }).catch(() => {});
  await fr.waitForFunction(() => { const im = Array.from(document.querySelectorAll(".art-thumb img")); return im.length >= 1 && im.every((i) => i.complete); }, null, { timeout: 60000 }).catch(() => {});
  out.remote = await fr.evaluate(() => ({
    button: (document.getElementById("art-pick") || {}).textContent, buttonPrefix: (document.querySelector("#art-pick .host-prefix") || {}).textContent || null,
    rows: Array.from(document.querySelectorAll(".art-row")).map((r) => ({ name: (r.querySelector(".art-name") || {}).textContent, via: (r.querySelector(".art-via") || {}).textContent, missing: r.classList.contains("missing"), refused: r.classList.contains("refused") })),
    thumbs: Array.from(document.querySelectorAll(".art-thumb img")).map((i) => ({ alt: i.alt, src: i.getAttribute("src"), natural: i.naturalWidth, loaded: i.complete && i.naturalWidth > 0 })),
    count: (document.querySelector(".art-count") || {}).textContent, err: (document.querySelector(".art-err") || {}).textContent || "",
    lock: (() => { const l = document.getElementById("art-lock"); return l ? l.getAttribute("aria-pressed") : null; })() }));
  // …and the local session lists its own file when picked
  await fr.click("#art-pick", { timeout: 15000 }).catch(() => {});
  await fr.waitForSelector('#art-picker .ctx-item[data-sid="' + cfg.lsid + '"]', { timeout: 15000 }).catch(() => {});
  await fr.click('#art-picker .ctx-item[data-sid="' + cfg.lsid + '"]', { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => Array.from(document.querySelectorAll(".art-row .art-name")).some((n) => n.textContent === "report.md"), null, { timeout: 60000 }).catch(() => {});
  out.local = await fr.evaluate(() => ({ rows: Array.from(document.querySelectorAll(".art-row .art-name")).map((n) => n.textContent), prefix: (document.querySelector("#art-pick .host-prefix") || {}).textContent || null }));
  // (B) the owning host DOWN at selection time (the reviewers of PR 1925): the test stops the remote kernel on the stage file, the hub's
  // tunnel health marks the host down and federation publishes it; picking the remote then shows the disconnected note, never a wait
  // that nothing could end; the remote back (the test's second stage) lists with no click
  fs.writeFileSync(cfg.stage + "/stage-1", "");
  const acked1 = await waitFile(cfg.stage + "/ack-1", 60000);
  const down = await fr.waitForFunction(() => { const f = window.__rompFed; return !!f && typeof f.down === "function" && f.down().indexOf("TESTHOST") >= 0; }, null, { timeout: 120000 }).then(() => true).catch(timedOut);
  await fr.click("#art-pick", { timeout: 15000 }).catch(() => {});
  await fr.waitForSelector('#art-picker .ctx-item[data-sid="TESTHOST:' + cfg.rsid + '"]', { timeout: 15000 }).catch(() => {});
  await fr.click('#art-picker .ctx-item[data-sid="TESTHOST:' + cfg.rsid + '"]', { timeout: 15000 }).catch(() => {});
  const noted = await fr.waitForFunction(() => /disconnected/.test((document.querySelector(".art-err") || {}).textContent || ""), null, { timeout: 30000 }).then(() => true).catch(timedOut);
  out.hostDown = { acked1, down, noted, ...(await fr.evaluate(() => ({ err: (document.querySelector(".art-err") || {}).textContent || "", wait: (document.querySelector(".art-empty") || {}).textContent || "",
    spin: (() => { const o = document.getElementById("pane-spin"); return o ? !o.classList.contains("gone") : null; })(), rows: document.querySelectorAll(".art-row").length }))) };
  fs.writeFileSync(cfg.stage + "/stage-2", "");
  const acked2 = await waitFile(cfg.stage + "/ack-2", 120000);
  const relisted = await fr.waitForFunction(() => document.querySelectorAll(".art-row").length >= 2 && !document.querySelector(".art-err"), null, { timeout: 180000 }).then(() => true).catch(timedOut);
  out.hostBack = { acked2, relisted, ...(await fr.evaluate(() => ({ rows: Array.from(document.querySelectorAll(".art-row .art-name")).map((n) => n.textContent), err: (document.querySelector(".art-err") || {}).textContent || "", relayUps: window.__relayUps }))) };
  // (the re-arm, executed) the persisted remote selection and the lock survive a reload; the pane boots before federation holds a conn
  // for the host (its boot frames have nothing to ride: the ask is deferred to the relay's open), so on the host relay the open's re-arm
  // sends the watch and then the ONE listing, and nothing else follows
  await fr.click("#art-lock", { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => { const l = document.getElementById("art-lock"); return !!l && l.getAttribute("aria-pressed") === "true"; }, null, { timeout: 10000 }).catch(() => {});
  await page.reload(); await page.waitForSelector("#f-chat", { timeout: 30000 });
  fr = await findFrame(/\/artifacts(\?|$)/);
  if (fr) {
    await fr.waitForFunction(() => document.querySelectorAll(".art-row").length >= 2, null, { timeout: 120000 }).catch(() => {});
    await fr.waitForFunction(() => window.__relayUps > 0 && window.__sends.some((x) => x.type === "artifactsListing" || x.type === "listArtifacts"), null, { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(1500);   // a second ask that will not come cannot be awaited: the frames are read after the listing landed and a pause
    out.reloaded = await fr.evaluate((rid) => ({ prefix: (document.querySelector("#art-pick .host-prefix") || {}).textContent || null, name: (document.querySelector("#art-pick .session-name") || {}).textContent || null,
      lock: (document.getElementById("art-lock") || {}).getAttribute("aria-pressed"), rows: Array.from(document.querySelectorAll(".art-row .art-name")).map((n) => n.textContent), relayUps: window.__relayUps,
      frames: window.__sends.filter((x) => (x.type === "watchArtifacts" || x.type === "listArtifacts") && (x.sid === rid || x.sid === "TESTHOST:" + rid)).map((x) => x.type) }), cfg.rsid);
  }
}
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


def _kernel(lab, name, port, token, sid, session, color, records, files):
    """Boot one hermetic kernel: its own state root and dist, one session with a transcript and files under its cwd."""
    state = os.path.join(lab, name, "xdg", "romp")
    claude = os.path.join(lab, name, "claude")
    cwd = os.path.join(lab, name, "notes-api")
    for d in ("names", "sdk", "states"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    os.makedirs(cwd, exist_ok=True)
    Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own hosts off (the conftest rule)
    for rel, data in files.items():
        p = Path(cwd, rel); p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)
    Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (session, cwd, color[0], color[1]))
    Path(state, "sdk", sid + ".json").write_text(json.dumps(
        {"sid": sid, "name": session, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
         "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
    proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
    os.makedirs(proj, exist_ok=True)
    Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in records(cwd)))
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


def _records(sid, writes, prose):
    """A transcript: one Write per path in `writes`, then an assistant line of prose naming `prose` paths."""
    def build(cwd):
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs, parent, t, n = [], None, t0, 0
        for rel in writes:
            u, a = "u%d" % n, "a%d" % n
            recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "sessionId": sid, "message": {"role": "user", "content": "write %s" % rel}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": iso(t + 2), "sessionId": sid,
                         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                                     "content": [{"type": "tool_use", "id": "tu%d" % n, "name": "Write", "input": {"file_path": os.path.join(cwd, rel), "content": "x"}}]}})
            parent, t, n = a, t + 4, n + 1
        if prose:
            recs.append({"type": "assistant", "uuid": "p1", "parentUuid": parent, "timestamp": iso(t + 2), "sessionId": sid,
                         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": "The figure is at %s." % " and ".join(os.path.join(cwd, rel) for rel in prose)}]}})
        return recs
    return build


class ArtifactsRemoteServed(unittest.TestCase):
    _r = None
    _fail = None       # the main run's fault: read by every test, since a main-run fault after stage one leaves the remote kernel down
    _fail_rf = None    # the remote-first run's own fault (the second contributor's post-merge review of PR 2100 at 17:50Z): read by its one test alone,
    #                    so a fault in that short run no longer fails the four main-run tests sorted after it with a message about a run they never read

    @classmethod
    def _skip(cls, why):
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="artifacts-remote-")
        cls.procs = []
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.rport, cls.rtoken = _free_port(), "testtok-remote-art"
        cls.hport, cls.htoken = _free_port(), "testtok-hub-art"
        try:
            rp, cls.rlog = _kernel(cls.lab, "testhost", cls.rport, cls.rtoken, SID_R, "api", COLOR_R,
                                   _records(SID_R, ["docs/remote-notes.md"], ["plots/remote-figure.png"]),
                                   {"docs/remote-notes.md": "# notes on the remote\n", "plots/remote-figure.png": PNG})
            cls.procs.append(rp)
            cls.remote_args = (cls.lab, "testhost", cls.rport, cls.rtoken, SID_R, "api", COLOR_R,
                               _records(SID_R, ["docs/remote-notes.md"], ["plots/remote-figure.png"]),
                               {"docs/remote-notes.md": "# notes on the remote\n", "plots/remote-figure.png": PNG})   # the reboot of the down-host leg
            hp, cls.hlog = _kernel(cls.lab, "hub", cls.hport, cls.htoken, SID_L, "web", COLOR_L,
                                   _records(SID_L, ["report.md"], []), {"report.md": "# the report\n"})
            cls.procs.append(hp)
        except unittest.SkipTest:
            cls.tearDownClass()
            raise
        body = json.dumps({"host": "TESTHOST", "kernelPort": cls.rport, "busPort": _free_port(), "token": cls.rtoken}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/checkin?token=%s" % (cls.hport, cls.htoken), data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ans = json.loads(resp.read().decode())
        if not ans.get("ok"):
            cls.tearDownClass()
            cls._skip("the hub refused the check-in: %r" % ans)
        rows = []
        for _ in range(60):   # the hub's supervisor probes the peer and reports it up; the browser dials only then
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/tunnels?token=%s" % (cls.hport, cls.htoken), timeout=3) as r2:
                    rows = json.loads(r2.read().decode()).get("tunnels") or []
            except Exception:
                rows = []
            row = next((t for t in rows if t.get("host") == "TESTHOST"), None)
            if row and row.get("status") == "up" and row.get("hasToken"):
                break
            time.sleep(0.5)
        else:
            cls.tearDownClass()
            cls._skip("the hub never reported the checked-in peer up: %r" % (rows,))

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if type(self)._fail:
            self.fail(type(self)._fail)
        if type(self)._r is None:
            cfg = os.path.join(self.lab, "cfg.json")
            stage = os.path.join(self.lab, "stage"); os.makedirs(stage, exist_ok=True)
            with open(cfg, "w") as f:
                json.dump({"landing": "http://127.0.0.1:%d/?token=%s" % (self.hport, self.htoken), "rsid": SID_R, "lsid": SID_L, "stage": stage,
                           "delayActiveChat": 1000}, f)   # the reproduction of the picker-mark race (the module docstring): the first activeChat frame a pane socket receives lands a second late
            driver = os.path.join(self.lab, "driver.mjs")
            Path(driver).write_text(DRIVER)
            # the driver and this test meet on stage files: at stage-1 the remote kernel is stopped (the host down), at stage-2 it is
            # booted again on the same port (the host back); each wait is bounded and ends with the driver's exit too
            p = subprocess.Popen(["node", driver], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            def reached(name, secs):
                for _ in range(secs * 2):
                    if os.path.exists(os.path.join(stage, name)) or p.poll() is not None:
                        return p.poll() is None
                    time.sleep(0.5)
                return False
            if reached("stage-1", 420):
                rp = self.procs[0]; rp.kill(); rp.wait()
                Path(stage, "ack-1").write_text("")
            if reached("stage-2", 420):
                try:
                    rp2, self.rlog = _kernel(*self.remote_args)
                    self.procs.append(rp2)
                except unittest.SkipTest as e:
                    type(self)._fail = "the remote kernel did not come back: %s" % e
                Path(stage, "ack-2").write_text("")
            try:
                out, err = p.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                p.kill(); out, err = p.communicate()
            p.stdout, p.stderr = out, err
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; hub: %s; remote: %s)" % (p.stderr[-2000:], open(self.hlog).read()[-1200:], open(self.rlog).read()[-800:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("ARTREMOTE:", json.dumps(type(self)._r), file=sys.stderr)
        return type(self)._r

    def _result_remote_first(self):
        """The picker leg on an emulated REMOTE-FIRST boot (the second contributor's post-merge review of PR 2097 at 16:50Z): a second,
        short driver run on the same two kernels, the remote tab made active before the pane exists, ending after the card."""
        if type(self)._fail:               # the main run's fault first: after stage one it leaves the remote kernel down, and its message names that cause
            self.fail(type(self)._fail)
        if type(self)._fail_rf:
            self.fail(type(self)._fail_rf)
        if getattr(type(self), "_r2", None) is None:
            cfg = os.path.join(self.lab, "cfg-remote-first.json")
            with open(cfg, "w") as f:
                json.dump({"landing": "http://127.0.0.1:%d/?token=%s" % (self.hport, self.htoken), "rsid": SID_R, "lsid": SID_L,
                           "delayActiveChat": 1000, "bootRemoteFirst": True, "pickerOnly": True}, f)
            driver = os.path.join(self.lab, "driver-remote-first.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail_rf = "the remote-first driver produced no RESULT (stderr: %s)" % p.stderr[-2000:]
                self.fail(type(self)._fail_rf)
            type(self)._r2 = json.loads(line[len("RESULT:"):])
        print("ARTREMOTE-FIRST:", json.dumps(type(self)._r2), file=sys.stderr)
        return type(self)._r2

    def logs(self):
        return "\nhub: %s\nremote: %s" % (open(self.hlog).read()[-1000:], open(self.rlog).read()[-600:])

    def test_the_hubs_strip_shows_the_remote_tab_and_the_picker_lists_both_sessions_the_remote_under_its_host_prefix(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertIn("TESTHOST:" + SID_R, r["tabs"] or [], "the remote session's tab, under its host prefix, in the hub's strip%s" % self.logs())
        self.assertIn(SID_L, r["tabs"] or [], "the hub's own tab")
        self.assertTrue(r["frame"], "the pane's document is up")
        card = r["card"]
        self.assertIsNotNone(card, "the picker's card opened%s" % self.logs())
        by = {row["sid"]: row for row in card["rows"]}
        self.assertEqual(set(by), {SID_L, "TESTHOST:" + SID_R}, "exactly the open tabs, the remote under its host id: %r" % card["rows"])
        self.assertEqual((by["TESTHOST:" + SID_R]["prefix"], by["TESTHOST:" + SID_R]["name"]), ("TESTHOST:", "api"), "the remote row: the quiet prefix, then the name")
        self.assertEqual((by[SID_L]["prefix"], by[SID_L]["name"]), (None, "web"), "the local row: no prefix")
        h = r.get("cardHolds") or {}
        # one assertion per hold, in the order they ran, so a red names the hold that did not fire (never a longer wall-clock cap)
        self.assertTrue(h.get("preSwitched"), "the chat pre-switched to the remote tab (a confirmation on a remote-first boot): %r" % h)
        self.assertTrue(h.get("switched"), "then switched to the hub's own tab, a real switch: %r" % h)
        self.assertTrue(h.get("echoOk"), "the kernel's echo of THAT switch landed (the hub's own relay and an echo carrying its nonce): %r" % h)
        self.assertTrue(h.get("buttonOk"), "the pane's button wore the hub's name: %r" % h)
        self.assertTrue(h.get("markOk"), "the card's mark rendered on the hub's row: %r" % h)
        self.assertTrue(by[SID_L]["current"], "the shown session (the chat's active tab, the hub's own) wears the mark")
        self.assertFalse(by["TESTHOST:" + SID_R]["current"], "and the remote row does not")

    def test_on_a_remote_first_boot_the_pre_switch_confirms_and_the_wait_still_certifies_the_switch_to_the_hubs_own(self):
        # the emulated remote-first boot: the pre-switch is a confirmation (no relay), the stand-in remote relay keeps the plant from being
        # the last relay, and the wait is satisfied only by the switch's own hub relay and its echo
        r = self._result_remote_first()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertTrue(r.get("forcedRemoteFirst"), "the remote tab was the chat's active tab before the pane opened: %r" % r.get("forcedRemoteFirst"))
        h = r.get("cardHolds") or {}
        self.assertEqual(h.get("bootActive"), "remote", "the pane booted remote-first: %r" % h)
        for k, why in (("preSwitched", "the pre-switch confirmed the already active remote tab"), ("switched", "the switch to the hub's own tab was real"),
                       ("echoOk", "the kernel's echo of THAT switch landed (the hub's own relay, the last relay overall, and an echo carrying its nonce)"),
                       ("buttonOk", "the pane's button wore the hub's name"), ("markOk", "the card's mark rendered on the hub's row")):
            self.assertTrue(h.get(k), "%s: %r" % (why, h))
        by = {row["sid"]: row for row in (r.get("card") or {}).get("rows", [])}
        self.assertTrue(by.get(SID_L, {}).get("current"), "the hub's own row wears the mark: %r" % by)
        self.assertFalse(by.get("TESTHOST:" + SID_R, {}).get("current"), "and the remote row does not")

    def test_the_picker_wears_the_strips_dress_in_the_menu_tokens(self):
        card = self._result()["card"]
        self.assertIsNotNone(card)
        self.assertIn("ctx-menu", card["classes"], "the menu builder's card")
        self.assertEqual(card["background"], card["menuBg"], "the card's ground is the menu token's colour, resolved by the theme")
        remote = next(row for row in card["rows"] if row["sid"] == "TESTHOST:" + SID_R)
        self.assertEqual((remote["prefixStyle"]["fontStyle"], remote["prefixStyle"]["fontWeight"]), ("italic", "400"), "the host prefix: quiet, italic, weight 400: %r" % remote["prefixStyle"])
        self.assertLess(remote["prefixStyle"]["fontSize"], remote["nameStyle"]["fontSize"], "…and a step smaller than the name")
        self.assertEqual(remote["nameStyle"]["fontWeight"], "600", "the name bold: %r" % remote["nameStyle"])
        self.assertEqual(remote["nameStyle"]["chip"].lower(), COLOR_R[0].lower(), "the name inked through the strip's token, the session's identity colour")
        self.assertNotEqual(remote["nameStyle"]["color"], card["fg"], "…and not the body's text colour")

    def test_picking_the_remote_lists_its_files_from_the_owning_kernel_and_the_thumbnail_rides_the_hosts_relay(self):
        r = self._result()
        m = r["remote"]
        self.assertIsNotNone(m)
        self.assertEqual(m["err"], "", "the owning kernel answered: %r%s" % (m, self.logs()))
        self.assertEqual(sorted((x["name"], x["via"], x["missing"], x["refused"]) for x in m["rows"]),
                         [("remote-figure.png", "shown", False, False), ("remote-notes.md", "written", False, False)],
                         "the remote's two files, judged on the remote's disk: %r" % m["rows"])
        self.assertEqual(m["buttonPrefix"], "TESTHOST:", "the button wears the remote's prefix")
        self.assertEqual(len(m["thumbs"]), 1, "one picture in the grid: %r" % m["thumbs"])
        t = m["thumbs"][0]
        self.assertTrue(t["src"].startswith("/remote/TESTHOST/file?"), "the thumbnail rides the hub's relay to the host, not the local origin: %r" % t["src"])
        self.assertIn("sid=" + SID_L[:0] + SID_R, t["src"], "…with the bare sid the remote kernel knows")
        self.assertNotIn("TESTHOST%3A", t["src"]); self.assertNotIn("TESTHOST:", t["src"].split("sid=")[1])
        self.assertTrue(t["loaded"], "the bytes came through the relay and decoded: %r" % t)
        self.assertEqual(m["lock"], "false", "a fresh browser starts unlocked and following")

    def test_a_remote_picked_while_its_host_is_down_shows_the_note_in_place_of_the_wait_and_lists_when_the_host_is_back(self):
        # the reviewers of PR 1925 (B): the host down at selection time left "Reading the thread…" for good; the note (host-prefix.ts
        # hostDownNote) stands in its place, the loader is down, and the host's return lists with no click (the relay's reopen re-asks)
        r = self._result(); d, b = r.get("hostDown") or {}, r.get("hostBack") or {}
        self.assertTrue(d.get("acked1") and d.get("down"), "the remote was stopped and federation published the host down: %r%s" % (d, self.logs()))
        self.assertTrue(d.get("noted"), "the disconnected note in place of the wait: %r" % d)
        self.assertIn("TESTHOST is disconnected", d.get("err", "")); self.assertEqual((d.get("wait"), d.get("spin"), d.get("rows")), ("", False, 0), "no wait text, the loader down, no rows: %r" % d)
        self.assertTrue(b.get("acked2") and b.get("relisted"), "the host back: the listing came with no click: %r%s" % (b, self.logs()))
        self.assertEqual(sorted(b.get("rows") or []), ["remote-figure.png", "remote-notes.md"]); self.assertEqual(b.get("err"), "")

    def test_a_persisted_remote_selection_and_the_lock_survive_a_reload_and_the_relays_open_re_sends_the_watch_alone(self):
        # the re-arm executed (in place of two regexes): the pane boots before federation holds a conn for the host, so its boot frames
        # cannot ride anything and the ask is deferred; the relay's open re-arms the watch and asks the ONE listing, nothing follows
        r = self._result(); x = r.get("reloaded") or {}
        self.assertEqual((x.get("prefix"), x.get("name"), x.get("lock")), ("TESTHOST:", "api", "true"), "the remote selection and the lock survive the reload: %r" % x)
        self.assertEqual(sorted(x.get("rows") or []), ["remote-figure.png", "remote-notes.md"])
        self.assertGreaterEqual(x.get("relayUps") or 0, 1, "the relay opened after the pane booted: %r" % x)
        self.assertEqual(x.get("frames"), ["watchArtifacts", "listArtifacts"], "the frame order on the host relay: the re-arm's watch, the one listing: %r%s" % (x, self.logs()))

    def test_the_local_session_lists_its_own_file_when_picked(self):
        r = self._result()
        self.assertIsNotNone(r["local"])
        self.assertEqual(r["local"]["rows"], ["report.md"], "the hub's own session, from its own kernel: %r" % r["local"])
        self.assertIsNone(r["local"]["prefix"], "no host prefix on a local session")


if __name__ == "__main__":
    unittest.main()
