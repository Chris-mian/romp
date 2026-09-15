"""The file preview popover on a REMOTE host's session (T364): a hub kernel's /chat page shows a session that lives on a
second hermetic kernel checked in as host TESTHOST (the mobile handshake, no ssh; the shape tests/test_composer_placeholder_remote_served.py
boots). The session's chat mentions a markdown file and an image that exist on the REMOTE kernel's disk only. Before the
fix the popover fetched the LOCAL origin (/file on the hub) for the remote session's file and got the wrong kernel's
answer (a 403: the hub knows neither the session nor the path), so a laptop-hosted session's card never rendered; the
fetch rides the hub's /remote/<host>/file relay with the bare sid now, as the inline images always did (preview.ts).

Synthetic throughout: placeholder sids, TESTHOST, invented file names. Skips where Playwright or its browser is absent.
"""
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zlib
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID = "77777777-2222-3333-4444-555555555555"
COLOR = ("#9cd2ff", "#0c1a2e")
NOTES = "# Remote notes\n\nThe notes-api retry loop backs off with a jitter of ten percent.\n\n## Later\n\nA second section.\n"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _png(w=2, h=2, rgb=(60, 120, 200)):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 760 } });
const fileRequests = [];   // every /file request the page makes, by URL: the route is the claim
page.on("request", (r) => { if (/\/file\?/.test(r.url())) fileRequests.push(r.url().replace(/^https?:\/\/[^/]+/, "")); });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
// the remote host's tab appears once the hub reports the check-in up and the relay socket is open
const remoteTab = page.locator("#tabs .tab", { hasText: "TESTHOST" }).first();
try { await remoteTab.waitFor({ timeout: 45000 }); }
catch (e) { console.error("no remote tab: " + JSON.stringify(await page.evaluate(() => (document.getElementById("tabs") || {}).textContent))); process.exit(1); }
await remoteTab.click();
await page.waitForFunction(() => document.querySelectorAll("#content .file-uri-link").length >= 2, null, { timeout: 30000 });
await page.mouse.move(900, 720); await page.waitForTimeout(300);
const out = {};
out.active = await page.evaluate(() => { const t = document.querySelector("#tabs .tab.active[data-id]"); return t ? t.dataset.id : null; });
out.links = await page.evaluate(() => Array.from(document.querySelectorAll("#content .file-uri-link")).map((a) => ({ path: a.dataset.path, preview: a.dataset.preview || null, why: a.dataset.previewWhy || null })));
const sel = (path, frag) => '#content .file-uri-link[data-path="' + path + '"]' + (frag ? '[data-frag="' + frag + '"]' : ":not([data-frag])");
const card = () => page.evaluate(() => {
  const p = document.getElementById("file-preview-pop"); if (!p || getComputedStyle(p).display === "none") return null;
  const body = p.querySelector(".fp-body"); const img = p.querySelector(".fp-img");
  return { title: (p.querySelector(".fp-title") || {}).textContent ?? null, note: (p.querySelector(".fp-note") || {}).textContent ?? null,
           kind: body ? body.className : null, text: body ? body.textContent.trim().slice(0, 300) : null,
           img: img ? { src: img.getAttribute("src"), natural: img.naturalWidth } : null };
});
const hoverCard = async (path, frag) => {
  const n0 = fileRequests.length;
  await page.hover(sel(path, frag));
  await page.waitForFunction(() => { const p = document.getElementById("file-preview-pop"); return !!p && getComputedStyle(p).display !== "none" && !!p.querySelector(".fp-body") && !p.querySelector(".rl-in"); }, null, { timeout: 8000 });
  await page.waitForTimeout(300);
  const c = await card();
  await page.mouse.move(900, 720); await page.waitForTimeout(400);
  return { card: c, requests: fileRequests.slice(n0) };
};
out.md = await hoverCard("docs/remote-notes.md", null);
out.section = await hoverCard("docs/remote-notes.md", "later");
// the image card: the bytes ride the relay too; the img must have decoded (a natural width)
await page.hover(sel("plots/remote-figure.png", null));
await page.waitForFunction(() => { const i = document.querySelector("#file-preview-pop .fp-img"); return !!i && i.naturalWidth > 0; }, null, { timeout: 8000 }).catch(() => {});
out.img = { card: await card(), requests: fileRequests.slice(-3) };
if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/romp_chat-file-preview-remote.png" }); }
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


def _kernel(lab, name, port, token, records=None, sid=None, files=None):
    """Boot one hermetic kernel: its own state root, dist, and (optionally) one session with a transcript and files under its cwd."""
    state = os.path.join(lab, name, "xdg", "romp")
    claude = os.path.join(lab, name, "claude")
    cwd = os.path.join(lab, name, "proj")
    for d in ("names", "sdk", "states"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    os.makedirs(cwd, exist_ok=True)
    Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own hosts off (the conftest rule)
    Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
    for rel, data in (files or {}).items():
        p = Path(cwd, rel); p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)
    if records is not None:
        Path(state, "names", sid).write_text("api\t%s\t%s\t%s\n" % (cwd, COLOR[0], COLOR[1]))
        Path(state, "sdk", sid + ".json").write_text(json.dumps(
            {"sid": sid, "name": "api", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": sid, "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    env = _lab.kernel_env(os.path.join(lab, name), claude, os.path.join(lab, "dist"), port, token,
                          ROMP_HOST_NAME=name.upper())
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


class ServedRemoteFilePreview(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
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
        cls.lab = tempfile.mkdtemp(prefix="file-preview-remote-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.procs = []
        t0 = int(time.time()) - 900
        recs = [
            {"type": "user", "timestamp": iso(t0), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": SID,
             "message": {"role": "user", "content": "where are the retry notes?"}},
            {"type": "assistant", "timestamp": iso(t0 + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                         "content": [{"type": "text", "text": "The notes are in docs/remote-notes.md (the later part at docs/remote-notes.md#later) and the plot at plots/remote-figure.png."}]}},
        ]
        # the REMOTE kernel owns the session and its files; the HUB has neither and shows the session through the relay
        cls.rport, cls.rtoken = _free_port(), "testtok-remote-fp"
        cls.hport, cls.htoken = _free_port(), "testtok-hub-fp"
        try:
            rp, cls.rlog = _kernel(cls.lab, "testhost", cls.rport, cls.rtoken, records=recs, sid=SID,
                                   files={"docs/remote-notes.md": NOTES, "plots/remote-figure.png": _png()})
            cls.procs.append(rp)
            hp, cls.hlog = _kernel(cls.lab, "hub", cls.hport, cls.htoken)
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
            raise unittest.SkipTest("the hub refused the check-in: %r" % ans)
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
            raise unittest.SkipTest("the hub never reported the checked-in peer up: %r" % (rows,))

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def test_a_remote_sessions_links_preview_through_the_hosts_relay(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.hport, self.htoken), "shots": os.environ.get("PV_SHOTS", "")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
                         + "\nhub:\n" + open(self.hlog).read()[-1500:] + "\nremote:\n" + open(self.rlog).read()[-800:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        self.assertEqual(r["active"], "TESTHOST:" + SID, "the remote session's tab is active, under its host prefix")
        # the REMOTE kernel built the events and judged its own files: every link carries a preview kind
        by = {l["path"]: l for l in r["links"]}
        self.assertEqual(by["docs/remote-notes.md"]["preview"], "markdown", "judged on the remote's disk: %r" % r["links"])
        self.assertEqual(by["plots/remote-figure.png"]["preview"], "image")
        # the markdown card rendered from the relay, never from the hub's own /file
        md = r["md"]
        self.assertIn("fp-markdown", md["card"]["kind"] or "", "the remote file rendered: %r" % md)
        self.assertIn("jitter of ten percent", md["card"]["text"] or "")
        self.assertTrue(md["requests"], "the hover fetched the slice")
        for u in md["requests"]:
            self.assertTrue(u.startswith("/remote/TESTHOST/file?"), "the fetch rides the host relay, not the local origin: %r" % md["requests"])
            self.assertIn("sid=" + SID, u, "…with the bare sid the remote kernel knows (no host prefix): %r" % u)
        sec = r["section"]
        self.assertIn("A second section", sec["card"]["text"] or "", "the section road rides the relay too: %r" % sec)
        # the image card: the bytes came through the relay and decoded
        img = r["img"]["card"]
        self.assertIsNotNone(img and img["img"], "the image card: %r" % r["img"])
        self.assertTrue(img["img"]["src"].startswith("/remote/TESTHOST/file?"), "the img src is the relay's: %r" % img["img"])
        self.assertGreater(img["img"]["natural"], 0, "the image decoded (the relay served the bytes): %r" % img["img"])


if __name__ == "__main__":
    unittest.main()
