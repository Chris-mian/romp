"""The settings-proposal card on the served feed page (plans/settings-across-machines.md, phase one B): a hermetic kernel over
one synthetic session in the notes-api demo world, the real /feed page served from a copy of the built bundle, driven by
Playwright. Another machine's push (POST /mesh-settings with the serve token, naming itself TESTHOST) lands on this kernel as
two PROPOSAL records, task tracking and Suggest /compact, each the opposite of this machine's value under a newer stamp; each
record is a needs-you NOTICE card on the owner-less Notes run (producer settings, the title in the user's terms, Apply, Keep
mine and Keep mine and pin this machine as actions of the setting-proposal kind). Apply on the task-tracking card reaches the
kernel's noticeAction op, applies the value under the other machine's stamp through the store's own setter and takes the card
off; Keep mine on the Suggest /compact card drops the record, remembers the stamp as answered and takes its card off; the kernel's
/version shows what holds. Nothing changed on this kernel until the click. The unit road (the kind's gates, the runner, the
card's life) is tests/test_mesh_settings_adopt.py TheCard. Synthetic only: placeholder ids, invented text, hostname TESTHOST."""
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

SID = "11111111-2222-3333-4444-555555555555"
PEER = "TESTHOST"

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
// every noticeActionDone the pane receives (recorded at the federation manager's inbound, or the window for a page without it)
await page.addInitScript(() => {
  window.__nad = [];
  const record = (m) => { if (m && m.type === "noticeActionDone") window.__nad.push(m); };
  let fed = null;
  Object.defineProperty(window, "__rompFed", { configurable: true, get() { return fed; },
    set(v) { fed = v; if (v && typeof v.inbound === "function" && !v.__labWrapped) { const inb = v.inbound; v.__labWrapped = true; v.inbound = (h, m) => { record(m); return inb(h, m); }; } } });
  window.addEventListener("message", (e) => { if (!fed) record(e.data); });
});
const idOf = (key) => "notice:notes:" + key + ":1";
const selOf = (key) => '[data-key="a:' + idOf(key) + '"]';
const facts = (key) => page.evaluate((s) => { const c = document.querySelector(s); if (!c) return null;
  const q = (x) => c.querySelector(x);
  return { col: c.parentElement && c.parentElement.id, vis: c.offsetHeight > 0, prod: (q(".fask-nprod") || {}).textContent || "",
    title: (q(".fcard-title") || {}).textContent || "", name: (q(".fname") || {}).textContent || "", bodyText: (q(".fask-nbody") || {}).textContent || "",
    actions: Array.from(c.querySelectorAll(".fask-nactions button")).map((b) => ({ label: b.textContent, disabled: b.disabled, vis: b.offsetHeight > 0 })) }; }, selOf(key));
const click = async (key, label) => {
  const id = idOf(key), sel = selOf(key);
  const before = await page.evaluate(() => (window.__nad || []).length);
  const latched = await page.evaluate(([s, l]) => { const c = document.querySelector(s); const b = c && Array.from(c.querySelectorAll(".fask-nactions button")).find((x) => x.textContent === l);
    if (!b) throw new Error("no button " + l); b.click();
    return Array.from(c.querySelectorAll(".fask-nactions button")).map((a) => ({ label: a.textContent, disabled: a.disabled })); }, [sel, label]);
  await page.waitForFunction(([i, n]) => (window.__nad || []).filter((m) => m.itemId === i).length > 0 && (window.__nad || []).length > n, [id, before], { timeout: 40000 }).catch(() => {});
  const done = await page.evaluate((i) => (window.__nad || []).filter((m) => m.itemId === i), id);
  await page.waitForSelector(sel, { state: "detached", timeout: 20000 }).catch(() => {});
  return { latched, done, gone: !(await page.$(sel)) };
};
await page.goto(cfg.feed);
// (1) both cards are on the board: the push landed before the page opened
await page.waitForSelector(selOf(cfg.keys.tt), { timeout: 60000 }).catch(() => {});
await page.waitForSelector(selOf(cfg.keys.cs), { timeout: 20000 }).catch(() => {});
const first = { tt: await facts(cfg.keys.tt), cs: await facts(cfg.keys.cs) };
// (2) Apply on the task-tracking card, then Keep mine on the Suggest /compact card
const apply = first.tt ? await click(cfg.keys.tt, "Apply") : null;
const keep = first.cs ? await click(cfg.keys.cs, "Keep mine") : null;
process.stdout.write("RESULT:" + JSON.stringify({ first, apply, keep, errors }) + "\n");
await browser.close();
"""


class SettingsProposalCardServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def _get(cls, path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s?token=%s" % (cls.port, path, cls.token), timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="proposal-card-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs = [{"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": iso(t0), "sessionId": SID,
                 "message": {"role": "user", "content": "a question about the notes api"}},
                {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": iso(t0 + 2), "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                             "content": [{"type": "text", "text": "the notes api keeps its shape."}]}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.port = _free_port()
        cls.token = "testtok-proposalcard"
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
        # the other machine's push: the opposite of this kernel's two values under a stamp newer than any it holds
        v0 = cls._get("/version")
        cls.before = {"taskTracking": v0["taskTracking"], "compactSuggest": v0["compactSuggest"]}
        cls.gt = int(time.time() * 1000)
        body = json.dumps({"taskTracking": not v0["taskTracking"], "compactSuggest": not v0["compactSuggest"], "gt": cls.gt, "host": PEER}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:%d/mesh-settings" % cls.port, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "X-Romp-Token": cls.token})
        with urllib.request.urlopen(req, timeout=10) as r:
            cls.pushed = json.loads(r.read().decode("utf-8"))
        cls.keys = {"tt": "proposal.task-tracking." + PEER, "cs": "proposal.compact-suggest." + PEER}
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
            cfg = os.path.join(self.lab, "card.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"feed": base + "/feed?token=" + self.token, "token": self.token, "keys": self.keys}, f)
            driver = os.path.join(self.lab, "card.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
            type(self)._after = self._get("/version")
        print("PROPOSALCARD:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def test_the_push_landed_as_two_proposals_and_nothing_changed_on_this_kernel(self):
        p = self.pushed
        self.assertTrue(p.get("ok"), p)
        self.assertEqual({"taskTracking": p["settings"]["taskTracking"], "compactSuggest": p["settings"]["compactSuggest"]}, self.before, "the push applied nothing")
        self.assertEqual(sorted(p["settingsProposals"]), ["compact-suggest", "task-tracking"], "two records, one per store")
        self.assertEqual([r["host"] for r in p["settingsProposals"]["task-tracking"]], [PEER])

    def test_each_proposal_is_a_needs_you_notice_card_on_the_notes_run_with_the_three_answers(self):
        r = self._result()
        for k, label in (("tt", "Task tracking"), ("cs", "Suggest /compact")):
            c = r["first"][k]
            self.assertIsNotNone(c, "the %s card drew (errors: %r)" % (label, r["errors"]))
            self.assertEqual(c["col"], "col-needsInput-list", "%s: a needs-you card" % label)
            self.assertTrue(c["vis"])
            self.assertEqual(c["prod"], "via settings", "the producer line, as the pane writes it")
            want = "%s: %s proposes %s; this machine is %s" % (label, PEER, "off" if self.before["taskTracking" if k == "tt" else "compactSuggest"] else "on",
                                                              "on" if self.before["taskTracking" if k == "tt" else "compactSuggest"] else "off")
            self.assertEqual(c["title"], want)
            self.assertEqual([a["label"] for a in c["actions"]], ["Apply", "Keep mine", "Keep mine and pin this machine"])
            self.assertTrue(all(a["vis"] and not a["disabled"] for a in c["actions"]), c["actions"])
            self.assertIn("Nothing changed here", c["bodyText"])

    def test_apply_on_the_card_applies_under_the_other_machines_stamp_and_takes_the_card_off(self):
        r = self._result()
        a = r["apply"]
        self.assertIsNotNone(a, "the click ran (errors: %r)" % r["errors"])
        self.assertTrue(all(x["disabled"] for x in a["latched"]), "every button latches on the click: %r" % a["latched"])
        self.assertEqual([(d["ok"], d["error"]) for d in a["done"]], [(True, "")], "the kernel's answer: %r" % a["done"])
        self.assertTrue(a["gone"], "the card left the board")
        v = type(self)._after
        self.assertEqual(v["taskTracking"], not self.before["taskTracking"], "the value applied on this kernel")
        self.assertEqual(v["settingsGt"]["task-tracking"], self.gt, "under the other machine's stamp: one value, one stamp")
        self.assertNotIn("task-tracking", v.get("settingsProposals") or {}, "the record is gone")

    def test_keep_mine_on_the_card_keeps_the_value_remembers_the_stamp_and_takes_the_card_off(self):
        r = self._result()
        k = r["keep"]
        self.assertIsNotNone(k, "the click ran (errors: %r)" % r["errors"])
        self.assertEqual([(d["ok"], d["error"]) for d in k["done"]], [(True, "")], k["done"])
        self.assertTrue(k["gone"])
        v = type(self)._after
        self.assertEqual(v["compactSuggest"], self.before["compactSuggest"], "nothing applied")
        self.assertNotIn("compact-suggest", v.get("settingsProposals") or {})
        recs = json.loads(Path(self.state, "settings-proposals.json").read_text())
        self.assertEqual(recs["compact-suggest"]["answered"], {PEER: self.gt}, "the stamp is remembered as answered for that machine")
        self.assertEqual(r["errors"], [], "no page errors")


if __name__ == "__main__":
    unittest.main()
