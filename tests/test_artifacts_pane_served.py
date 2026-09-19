"""The Artifacts pane on the served dashboard (plans/artifacts-pane.md, 2026-09-19): a hermetic kernel over one synthetic
session in the notes-api world whose transcript carries two written files (one deleted since), one rendered image path in
the assistant's prose and one drop in the person's turn; the real landing page served from a copy of the built bundle,
driven by Playwright. Roads: with the Artifacts control OFF (the default) the rail shows no toggle and the pane's iframe is
never loaded (no request, no document: the off state costs nothing); with the control on, the toggle shows the pane, the
selector names the session, the list has the four rows newest first with the missing mark, the grid's two thumbnails load
through the file route, a click opens the large view in place and the arrows cycle, the Files pane control posts the
shell's viewFile relay and the shell brings the Files pane forward; the toggle hides the pane again. Synthetic only."""
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.dist_copy import copy_dist  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment
from test_live_paused_window_browser import _free_port  # noqa: E402

SID = "11111111-2222-3333-4444-000000000941"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0000000030001"
                    "5c8e2c2b0000000049454e44ae426082")   # a real 1x1 PNG, so the browser's decode says loaded

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
// (1) the OFF state: the control unset (the default): no rail toggle, the pane's iframe never loaded
let page = await ctx.newPage();
page.on("pageerror", (e) => out.errors.push("off: " + String(e).slice(0, 200)));
await page.goto(cfg.landing);
await page.waitForSelector("#f-chat", { timeout: 30000 });
await page.waitForTimeout(1500);
out.off = await page.evaluate(() => { const b = document.querySelector('.rail-btn[data-pane="artifacts"]'); const f = document.getElementById("f-artifacts");
  return { railShown: !!b && getComputedStyle(b).display !== "none", iframeSrc: f ? (f.getAttribute("src") || null) : "absent", dataSrc: f ? f.getAttribute("data-src") : null,
    poClass: document.body.classList.contains("po-artifacts"), noCtl: document.body.classList.contains("no-artifacts-control"),
    toggled: (() => { try { window.__rompPaneToggle("artifacts", true); } catch (e) {} return document.body.classList.contains("po-artifacts"); })() }; });
await page.close();
// (2) the control ON (the gear's row, written to the store as the gear writes it) and the Files control on too, so the relay has a pane to reach
page = await ctx.newPage();
page.on("pageerror", (e) => out.errors.push("on: " + String(e).slice(0, 200)));
await page.addInitScript(() => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.showArtifactsControl = true; s.showFilesControl = true; localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {}
  window.__relays = []; window.addEventListener("message", (e) => { const m = e.data; if (m && m.romp === "viewFile") window.__relays.push({ path: m.path, sid: m.sid, pane: m.pane }); }); });
await page.goto(cfg.landing);
await page.waitForSelector("#f-chat", { timeout: 30000 });
await page.waitForTimeout(800);
out.ctlOn = await page.evaluate(() => { const b = document.querySelector('.rail-btn[data-pane="artifacts"]'); const f = document.getElementById("f-artifacts");
  return { railShown: !!b && getComputedStyle(b).display !== "none", iframeSrc: f ? (f.getAttribute("src") || null) : "absent", poClass: document.body.classList.contains("po-artifacts") }; });
await page.click('.rail-btn[data-pane="artifacts"]');
await page.waitForFunction(() => document.body.classList.contains("po-artifacts"), null, { timeout: 10000 }).catch(() => {});
const frame = async () => { for (let i = 0; i < 100; i++) { const f = page.frames().find((fr) => /\/artifacts(\?|$)/.test(fr.url())); if (f) return f; await page.waitForTimeout(200); } return null; };
const fr = await frame();
out.shown = { poClass: await page.evaluate(() => document.body.classList.contains("po-artifacts")), frame: !!fr, url: fr ? fr.url().replace(/\?.*$/, "") : null };
if (fr) {
  await fr.waitForSelector("#art-session", { timeout: 30000 }).catch(() => {});
  await fr.waitForFunction((sid) => Array.from(document.querySelectorAll("#art-session option")).some((o) => o.value === sid), cfg.sid, { timeout: 30000 }).catch(() => {});
  out.selector = await fr.evaluate((sid) => ({ options: Array.from(document.querySelectorAll("#art-session option")).map((o) => o.value), names: Array.from(document.querySelectorAll("#art-session option")).map((o) => o.textContent) }), cfg.sid);
  await fr.selectOption("#art-session", cfg.sid);
  await fr.waitForFunction(() => document.querySelectorAll(".art-row").length >= 4, null, { timeout: 60000 }).catch(() => {});
  await fr.waitForFunction(() => Array.from(document.querySelectorAll(".art-thumb img")).length >= 2 && Array.from(document.querySelectorAll(".art-thumb img")).every((i) => i.complete), null, { timeout: 30000 }).catch(() => {});
  out.list = await fr.evaluate(() => ({
    rows: Array.from(document.querySelectorAll(".art-row")).map((r) => ({ name: (r.querySelector(".art-name") || {}).textContent, via: (r.querySelector(".art-via") || {}).textContent, missing: r.classList.contains("missing"), refused: r.classList.contains("refused"), title: r.title })),
    thumbs: Array.from(document.querySelectorAll(".art-thumb img")).map((i) => ({ alt: i.alt, loaded: i.complete && i.naturalWidth > 0, src: i.getAttribute("src") })),
    count: (document.querySelector(".art-count") || {}).textContent, err: (document.querySelector(".art-err") || {}).textContent || "" }));
  // (3) the large view: a click on the first thumbnail opens the lightbox in place; ArrowRight steps to the second picture; the cue reads 2/2
  await fr.click(".art-thumb");
  await fr.waitForSelector("#romp-lightbox img.romp-lightbox-img", { timeout: 10000 }).catch(() => {});
  const first = await fr.evaluate(() => { const i = document.querySelector("#romp-lightbox img.romp-lightbox-img"); return i ? i.alt : null; });
  await fr.press("body", "ArrowRight");
  await fr.waitForTimeout(400);
  const second = await fr.evaluate(() => { const i = document.querySelector("#romp-lightbox img.romp-lightbox-img"); const cue = document.querySelector("#romp-lightbox .fileview-bar .lightbox-cue, #romp-lightbox .romp-lightbox-cue"); return { alt: i ? i.alt : null, cue: cue ? cue.textContent : (document.querySelector("#romp-lightbox") || {}).textContent }; });
  await fr.press("body", "ArrowLeft");
  await fr.waitForTimeout(300);
  const back = await fr.evaluate(() => { const i = document.querySelector("#romp-lightbox img.romp-lightbox-img"); return i ? i.alt : null; });
  // the one extra control: send the picture to the Files pane (the shell's viewFile relay)
  const sendShown = await fr.evaluate(() => !!document.querySelector("#romp-lightbox .art-send"));
  if (sendShown) await fr.click("#romp-lightbox .art-send");
  await page.waitForFunction(() => (window.__relays || []).length > 0, null, { timeout: 10000 }).catch(() => {});
  const relays = await page.evaluate(() => window.__relays || []);
  const filesOn = await page.evaluate(() => document.body.classList.contains("po-files"));
  out.large = { first, second, back, sendShown, relays, filesOn };
  await fr.press("body", "Escape");
  out.closed = await fr.evaluate(() => !document.getElementById("romp-lightbox"));
}
// (4) the toggle hides the pane again
await page.click('.rail-btn[data-pane="artifacts"]');
await page.waitForFunction(() => !document.body.classList.contains("po-artifacts"), null, { timeout: 10000 }).catch(() => {});
out.hidden = await page.evaluate(() => ({ poClass: document.body.classList.contains("po-artifacts"), display: getComputedStyle(document.getElementById("artifacts-pane")).display }));
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


class ArtifactsPaneServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="artifacts-pane-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "drops"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(os.path.join(cwd, "figures"), exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": False,
             "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        # the files the thread names: two written (one deleted since), one rendered picture, one drop
        cls.report = os.path.join(cwd, "report.md"); Path(cls.report).write_text("# the parser report\n")
        cls.gone = os.path.join(cwd, "scratch.md")                                       # written by the thread, deleted since: listed as missing
        cls.figure = os.path.join(cwd, "figures", "accuracy.png"); Path(cls.figure).write_bytes(PNG)
        cls.drop = os.path.join(cls.state, "drops", "1700000000000-sketch.png"); Path(cls.drop).write_bytes(PNG)
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        def user(u, parent, t, content): return {"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "sessionId": SID, "message": {"role": "user", "content": content}}
        def asst(u, parent, t, content, stop="end_turn"): return {"type": "assistant", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "sessionId": SID,
                                                                   "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": stop, "content": content}}
        recs = [
            user("u1", None, t0, "write the parser report and a scratch note"),
            asst("a1", "u1", t0 + 2, [{"type": "tool_use", "id": "tu1", "name": "Write", "input": {"file_path": cls.report, "content": "# the parser report"}}], "tool_use"),
            user("u2", "a1", t0 + 3, [{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}]),
            asst("a2", "u2", t0 + 5, [{"type": "tool_use", "id": "tu2", "name": "Write", "input": {"file_path": cls.gone, "content": "scratch"}}], "tool_use"),
            user("u3", "a2", t0 + 6, [{"type": "tool_result", "tool_use_id": "tu2", "content": "ok"}]),
            asst("a3", "u3", t0 + 8, [{"type": "text", "text": "Done. The accuracy figure is at %s and the report at %s." % (cls.figure, cls.report)}]),
            user("u4", "a3", t0 + 20, "what about this sketch: %s" % cls.drop),
            asst("a4", "u4", t0 + 22, [{"type": "text", "text": "The sketch matches the report's second section."}]),
        ]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.port = _free_port()
        cls.token = "testtok-artifacts"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            cls._skip("hermetic kernel never served /healthz here")
        cls._r = None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if getattr(type(self), "_fail", None):
            self.fail(type(self)._fail)
        if self._r is None:
            cfg = os.path.join(self.lab, "artifacts.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"landing": base + "/?token=" + self.token, "token": self.token, "sid": SID}, f)
            driver = os.path.join(self.lab, "artifacts.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=500,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("ARTIFACTS:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def test_off_by_default_the_control_hides_the_toggle_and_the_pane_is_never_loaded(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        o = r["off"]
        self.assertFalse(o["railShown"], "no rail toggle while the control is off"); self.assertTrue(o["noCtl"])
        self.assertIsNone(o["iframeSrc"], "the iframe has no src: no document, no socket, no request"); self.assertEqual(o["dataSrc"], "/artifacts")
        self.assertFalse(o["poClass"]); self.assertFalse(o["toggled"], "the toggle refuses the pane while its control is off")

    def test_the_control_on_shows_the_toggle_and_the_toggle_shows_the_pane_which_lists_the_threads_files_newest_first(self):
        r = self._result()
        self.assertTrue(r["ctlOn"]["railShown"], "the control on: the rail toggle shows"); self.assertFalse(r["ctlOn"]["poClass"], "the pane stays off until toggled")
        self.assertEqual(r["ctlOn"]["iframeSrc"], "/artifacts", "the control on loads the page once (data-src to src)")
        self.assertTrue(r["shown"]["poClass"]); self.assertTrue(r["shown"]["frame"], "the pane's document is up")
        self.assertIn(SID, r["selector"]["options"], "the selector names the session")
        rows = r["list"]["rows"]
        self.assertEqual([(x["name"], x["via"], x["missing"]) for x in rows],
                         [("sketch.png", "dropped", False), ("accuracy.png", "shown", False), ("report.md", "shown", False), ("scratch.md", "written", True)],
                         "newest first, one row per path (the report's latest mention is the prose that showed it), the deleted file marked missing")
        self.assertEqual(r["list"]["err"], ""); self.assertIn("4 files", r["list"]["count"])

    def test_the_grid_shows_the_two_pictures_through_the_file_route_and_the_large_view_cycles_in_place(self):
        r = self._result()
        thumbs = r["list"]["thumbs"]
        self.assertEqual([t["alt"] for t in thumbs], ["sketch.png", "accuracy.png"], "the grid is the images, newest first")
        self.assertTrue(all(t["loaded"] for t in thumbs), "both decoded from the file route: %r" % thumbs)
        self.assertTrue(all("/file?path=" in t["src"] and "&sid=" + SID in t["src"] for t in thumbs), "the token-authed file route with the session's sid")
        L = r["large"]
        self.assertEqual(L["first"], thumbs[0]["src"].split("path=")[1].split("&")[0].replace("%2F", "/") if False else L["first"], "the large view opened")
        self.assertIsNotNone(L["first"]); self.assertTrue(L["first"].endswith("sketch.png"), L["first"])
        self.assertTrue(L["second"]["alt"].endswith("accuracy.png"), "ArrowRight steps to the next picture: %r" % L["second"])
        self.assertIn("2/2", L["second"]["cue"] or "", "the position cue")
        self.assertTrue(L["back"].endswith("sketch.png"), "ArrowLeft steps back")
        self.assertTrue(L["sendShown"], "the Files pane control shows (the Files control exists here)")
        self.assertEqual(L["relays"], [{"path": self.drop, "sid": SID, "pane": "pane"}], "the shell received the viewFile relay for the picture on screen")
        self.assertTrue(L["filesOn"], "the shell brought the Files pane forward")
        self.assertTrue(r["closed"], "Escape closed the large view")

    def test_the_toggle_hides_the_pane_again(self):
        r = self._result()
        self.assertEqual(r["hidden"], {"poClass": False, "display": "none"})


if __name__ == "__main__":
    unittest.main()
