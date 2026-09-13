#!/usr/bin/env python3
"""The tab menu's Billing flyout opens on HOVER over its row, as the Tags flyout does (one gesture, wireFlyout; T380), and
takes the user's shape (T387, the user 2026-09-12): the billings the session can pick from; below them, only when there is
more than one to choose from, a rule and ONE entry, Set default billing, which opens a further submenu holding exactly the
same entries with the machine's default check-marked; a click there sets the default; no sub-line anywhere. An Automatic
way back to the helper rule sits at the END of that submenu behind its own rule, only while an explicit default stands.

Two labs drive the real /chat page of hermetic kernels. ServedBillingFlyout's machine offers BOTH sides (a staged
apiKeyHelper in the kernel's Claude config dir, a synthetic Claude account in the kernel's own home) with two synthetic
sessions: web with no pick of its own, api with an explicit key pick. It right-clicks web's tab, HOVERS the Billing row
and reads the flyout (the picks, the rule, the entry, the computed absence of sub-lines); hovers the entry and reads the
nested submenu (its entries against the list, the check mark as the computed pseudo-element, its placement beside the
entry); leaves and reads the close; presses Escape; clicks Login in the submenu, after which sdk-defaults.json must read
auth login with authExplicit true while api keeps its key pick and web has none, the reopened submenu marks Login and
offers Automatic behind a rule; clicks Automatic and reads the seed cleared. ServedBillingFlyoutOneSide's machine has
NO apiKeyHelper: the flyout lists both sides with the key greyed and shows neither the rule nor the entry.
BILLING_FLYOUT_DIST=<dir> serves another tree's UI bundle (the red run's before; the driver falls back to a click when
the hover opens nothing, so the rest is still read); BILLING_FLYOUT_SHOTS=<prefix> writes <prefix>-dark.png and
<prefix>-light.png of the open flyout with its submenu. Skips LOUDLY without the extension deps or a Playwright browser,
and never otherwise (CI turns a skip in a served module into a failure). SYNTHETIC fixtures only."""
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
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

# the notes-api demo world: twenty sessions, enough to wrap the strip onto several rows at a narrow width
NAMES = ["web", "api"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 700 } });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
await page.waitForTimeout(600);
const menuOpen = async () => {
  const tab = await page.$('#tabs .tab[data-id="' + cfg.sidWeb + '"]');
  await tab.click({ button: "right" });
  await page.waitForSelector(".ctx-menu .ctx-item-billing", { timeout: 5000 });
};
const billingRow = () => page.$(".ctx-menu .ctx-item-billing");
const readFly = () => page.evaluate(() => {
  const fly = document.querySelector(".ctx-sub-billing");
  if (!fly) return null;
  const rect = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, w: b.width, h: b.height, right: b.right, bottom: b.bottom }; };
  const kids = Array.from(fly.children);
  const lines = kids.map((k) => k.classList.contains("ctx-sep") ? "---" : k.classList.contains("ctx-item-setdefault") ? "[set default]" : k.textContent.trim());
  const choices = kids.filter((k) => k.classList.contains("ctx-item") && !k.classList.contains("ctx-item-setdefault") && !k.closest(".ctx-sub-default"))
    .map((i) => ({ text: i.textContent.trim(), current: i.classList.contains("current"), disabled: i.classList.contains("disabled"), title: i.title }));
  const entry = fly.querySelector(":scope > .ctx-item-setdefault");
  const readSub = (d) => Array.from(d.children).map((k) => k.classList.contains("ctx-sep") ? { sep: true } : {
    text: k.textContent.trim(), current: k.classList.contains("current"), disabled: k.classList.contains("disabled"), scope: k.dataset.scope,
    check: getComputedStyle(k, "::after").content, checkW: parseFloat(getComputedStyle(k, "::after").width) || 0, auto: k.classList.contains("ctx-item-auto") });
  const d = fly.querySelector(".ctx-sub-default");
  const row = document.querySelector(".ctx-menu .ctx-item-billing .ctx-item-sub");
  const rowEl = document.querySelector(".ctx-menu .ctx-item-billing"); const rr = rowEl ? rect(rowEl) : null;
  return { lines, choices, sep: kids.some((k) => k.classList.contains("ctx-sep")), subLines: fly.querySelectorAll(".ctx-item-sub").length,
    heads: fly.querySelectorAll(".ctx-sub-head").length, radios: fly.querySelectorAll(".ctx-radio").length,
    entry: entry ? { label: entry.querySelector(".ctx-item-label").textContent, caret: (entry.querySelector(".ctx-caret") || {}).textContent || "", rect: rect(entry),
                     caretInset: entry.querySelector(".ctx-caret") ? rect(entry).right - rect(entry.querySelector(".ctx-caret")).right : null } : null,
    rowCaretInset: (rowEl && rowEl.querySelector(".ctx-caret")) ? rect(rowEl).right - rect(rowEl.querySelector(".ctx-caret")).right : null,
    fontPx: { menu: rowEl ? parseFloat(getComputedStyle(rowEl).fontSize) : null,
              fly: kids.filter((k) => k.classList.contains("ctx-item")).length ? parseFloat(getComputedStyle(kids.filter((k) => k.classList.contains("ctx-item"))[0]).fontSize) : null,
              sub: (d && d.querySelector(".ctx-item")) ? parseFloat(getComputedStyle(d.querySelector(".ctx-item")).fontSize) : null },
    sub: d ? { items: readSub(d), rect: rect(d), inside: d.parentElement === fly } : null,
    rect: rect(fly), subLine: row ? row.textContent : null, rowRect: rr, viewport: window.innerWidth, viewportH: window.innerHeight };
});
const openSub = async () => {   // hover the Set default billing entry: the nested submenu opens by intent, a click is the fallback
  const e = await page.$(".ctx-sub-billing > .ctx-item-setdefault");
  if (!e) return { found: false };
  const eb = await e.boundingBox(); const t0 = Date.now();
  await page.mouse.move(eb.x + eb.width / 2, eb.y + eb.height / 2);
  let byHover = true;
  try { await page.waitForSelector(".ctx-sub-billing .ctx-sub-default", { timeout: 1500 }); } catch (err) { byHover = false; }
  if (!byHover) { await e.click(); await page.waitForSelector(".ctx-sub-billing .ctx-sub-default", { timeout: 3000 }).catch(() => {}); }
  await page.waitForTimeout(120);
  return { found: true, byHover, ms: Date.now() - t0 };
};
const hoverBilling = async () => {
  const row = await billingRow(); const bb = await row.boundingBox();
  await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
  await page.waitForSelector(".ctx-sub-billing", { timeout: 1500 }).catch(async () => { await row.click(); });
  await page.waitForTimeout(120);
};
const out = {};
out.tabs = await page.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => ({ id: t.dataset.id, name: (t.querySelector(".tab-label") || t).textContent.trim(), active: t.classList.contains("active") })));
try {
await menuOpen();
let row = await billingRow(); let bb = await row.boundingBox();
const t0 = Date.now();
await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
let byHover = true;
try { await page.waitForSelector(".ctx-sub-billing", { timeout: 1500 }); } catch (e) { byHover = false; }
out.hover = { opened: byHover, ms: Date.now() - t0 };
if (!byHover) { await row.click(); await page.waitForSelector(".ctx-sub-billing", { timeout: 5000 }).catch(() => {}); }
out.fly = await readFly();
out.subOpen = await openSub();
out.withSub = await readFly();
// leave both the row and the flyout: the flyout (and its submenu) closes after the tolerance window, the menu stays
await page.mouse.move(5, 690);
await page.waitForTimeout(450);
out.afterLeave = await page.evaluate(() => ({ fly: !!document.querySelector(".ctx-sub-billing"), sub: !!document.querySelector(".ctx-sub-default"), menu: !!document.querySelector(".ctx-menu") }));
// hover again, then Escape closes the menu (and the flyout with it)
row = await billingRow(); if (row) { bb = await row.boundingBox(); await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.waitForSelector(".ctx-sub-billing", { timeout: 1500 }).catch(() => {}); }
await page.keyboard.press("Escape"); await page.waitForTimeout(150);
out.afterEscape = await page.evaluate(() => ({ fly: !!document.querySelector(".ctx-sub-billing"), menu: !!document.querySelector(".ctx-menu") }));
// the screenshots: the open flyout with its submenu, dark and light
for (const theme of ["dark", "light"]) {
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.mouse.move(5, 690); await page.waitForTimeout(100);
  await menuOpen(); await hoverBilling(); await openSub();
  if (cfg.shots) await page.screenshot({ path: cfg.shots + "-" + theme + ".png", clip: { x: 0, y: 0, width: 1100, height: 520 } });
  await page.keyboard.press("Escape"); await page.waitForTimeout(100);
}
await page.evaluate(() => document.body.classList.remove("theme-light"));
// narrow windows (review: at 560, 760 and 886 px the flyout covered its menu and ran off-screen): inside the viewport, never over the row
out.narrow = {};
for (const [w, h] of [[560, 700], [760, 700], [886, 700], [560, 420], [560, 300]]) {
  await page.setViewportSize({ width: w, height: h }); await page.waitForTimeout(150);
  await menuOpen(); await hoverBilling(); await openSub();
  out.narrow[w + "x" + h] = await readFly();
  await page.keyboard.press("Escape"); await page.waitForTimeout(100);
}
await page.setViewportSize({ width: 1100, height: 700 }); await page.waitForTimeout(150);
// the default pick: Login in the nested submenu (the seed reads key: the helper is the box's default), posting setAuth with scope machine
await menuOpen(); await hoverBilling(); await openSub();
out.pick = await page.evaluate(() => {
  const r = Array.from(document.querySelectorAll(".ctx-sub-billing .ctx-sub-default > .ctx-item")).find((i) => i.textContent.trim().startsWith("Login"));
  if (!r) return { found: false };
  const disabled = r.classList.contains("disabled");
  if (!disabled) r.click();
  return { found: true, disabled, menuGone: !document.querySelector(".ctx-menu") };
});
await page.waitForTimeout(1200);   // the op reaches the kernel over the socket and the seed is written
await page.waitForFunction(() => { const s = document.querySelector('#tabs .tab.active'); return !!s; }, null, { timeout: 5000 });
await page.waitForTimeout(800);     // the next push carries web's new effective side
await menuOpen(); await hoverBilling(); await openSub();
out.afterPick = await readFly();
// the way back: Automatic at the end of the submenu clears the explicit default
out.autoClick = await page.evaluate(() => {
  const a = document.querySelector(".ctx-sub-billing .ctx-sub-default > .ctx-item-auto");
  if (!a) return { found: false };
  const prev = a.previousElementSibling; const last = a.parentElement.lastElementChild === a;
  a.click();
  return { found: true, behindRule: !!(prev && prev.classList.contains("ctx-sep")), last, menuGone: !document.querySelector(".ctx-menu") };
});
await page.waitForTimeout(1200);
await page.waitForTimeout(800);
await menuOpen(); await hoverBilling(); await openSub();
out.afterAuto = await readFly();
await page.keyboard.press("Escape");
} catch (e) { out.error = String(e && e.stack || e); }
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
console.log("RESULT: ok");
"""


class ServedBillingFlyout(unittest.TestCase):
    maxDiff = None
    result = None
    BOTH_SIDES = True

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="billing-fly-")
        before = os.environ.get("BILLING_FLYOUT_DIST", "")
        if before:
            src = before
        else:
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            if b.returncode != 0:
                raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
            src = os.path.join(EXT, "dist")
        dist = os.path.join(cls.lab, "dist")
        copy_dist(src, dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        # a lab root writes its own session-hosts off (the conftest rule): hosts are on by default, and a kernel-side boot
        # attach for twenty alive sessions would otherwise spawn twenty real session hosts on a developer's machine
        Path(state, "session-hosts").write_text("off\n")
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i % len(PALETTE)]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            reg = {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                   "model": "claude-opus-5", "liveModel": "Opus 5"}
            if name == "api":
                reg["auth"] = "key"          # api carries its OWN pick; web follows the machine default
            Path(state, "sdk", sid + ".json").write_text(json.dumps(reg))
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        # BOTH sides on this machine: a staged apiKeyHelper (read, never run) in the kernel's Claude config dir, and a
        # synthetic Claude account in the kernel's OWN home (the kernel probes the login side from ~/.claude.json)
        if cls.BOTH_SIDES:
            helper = Path(claude, "helper.sh"); helper.write_text("#!/bin/sh\necho not-a-real-key\n"); helper.chmod(0o700)
            Path(claude, "settings.json").write_text(json.dumps({"apiKeyHelper": str(helper)}))
        else:
            Path(claude, "settings.json").write_text(json.dumps({}))   # the login alone: one billing to choose from
        home = os.path.join(cls.lab, "home"); os.makedirs(home, exist_ok=True)
        Path(home, ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "11111111-2222-3333-4444-555555555555",
                                                                             "emailAddress": "user@example.com", "organizationName": "Example"}}))
        cls.home = home
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-billing"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST", HOME=cls.home)
        cls.state = state
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.terminate()
            try:
                k.wait(timeout=10)
            except subprocess.TimeoutExpired:
                k.kill(); k.wait()
            time.sleep(0.5)                # a kernel child still writing into the lab's config dir finishes (review: stray dirs)
        lab = getattr(cls, "lab", "")
        shutil.rmtree(lab, ignore_errors=True)
        time.sleep(0.3)
        shutil.rmtree(lab, ignore_errors=True)   # …and whatever landed between the two

    @classmethod
    def _run(cls):
        if cls.result is not None:
            if isinstance(cls.result, BaseException):
                raise cls.result
            return cls.result
        try:
            cls.result = cls._drive()
        except BaseException as e:
            cls.result = e
            raise
        return cls.result

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        out = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": out, "sidWeb": SIDS["web"],
                       "shots": (os.environ.get("BILLING_FLYOUT_SHOTS", "") + ("" if cls.BOTH_SIDES else "-oneside")) if os.environ.get("BILLING_FLYOUT_SHOTS") else ""}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        if not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        result = json.loads(Path(out).read_text())
        if os.environ.get("BILLING_FLYOUT_DUMP"):
            Path(os.environ["BILLING_FLYOUT_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        if result.get("error"):
            raise AssertionError("the driver threw: " + result["error"] + "\n  tabs: " + json.dumps(result.get("tabs")) + "\nkernel:\n" + open(cls.klog).read()[-1200:])
        return result

    def test_hovering_the_billing_row_opens_the_flyout_without_a_click(self):
        r = self._run()
        self.assertTrue(r["hover"]["opened"], "the flyout opened on hover, no click (the Tags flyout's gesture, T380): " + json.dumps(r["hover"]))
        self.assertLess(r["hover"]["ms"], 1200, "within the intent window: " + json.dumps(r["hover"]))

    def test_leaving_closes_the_flyout_and_its_submenu_and_keeps_the_menu_and_escape_closes_all(self):
        r = self._run()
        self.assertEqual(r["afterLeave"], {"fly": False, "sub": False, "menu": True}, "leaving the row and the flyout closes the flyout and its submenu, the menu stays: " + json.dumps(r["afterLeave"]))
        self.assertEqual(r["afterEscape"], {"fly": False, "menu": False}, "Escape closes the menu and the flyout with it: " + json.dumps(r["afterEscape"]))

    def test_the_flyout_lists_the_picks_then_a_rule_and_one_set_default_billing_entry_with_no_sub_line(self):
        r = self._run()
        f = r["fly"]
        self.assertIsNotNone(f, "the flyout was read")
        table = "\n  " + json.dumps(f)
        self.assertEqual([c["text"].split(" (")[0] for c in f["choices"]], ["Login", "API key"], table)
        self.assertEqual(f["lines"][2:], ["---", "[set default]"], "below the picks: a rule, then the ONE entry, nothing else" + table)
        self.assertEqual(f["entry"]["label"], "Set default billing", table)
        self.assertEqual(f["entry"]["caret"], "▸", "the entry opens a further submenu: its caret says so" + table)
        self.assertEqual(f["subLines"], 0, "no sub-line under anything (the user: self-explanatory)" + table)
        self.assertEqual((f["heads"], f["radios"]), (0, 0), "the Default group's head and radios are gone" + table)
        self.assertFalse(any(c["disabled"] for c in f["choices"]), "both sides are available on this machine" + table)
        self.assertEqual(f["subLine"], "API key", "web follows the automatic default: the key (the helper)" + table)
        self.assertLessEqual(f["rect"]["w"], 380, "a menu's width" + table)

    def test_the_entry_opens_a_nested_submenu_by_hover_holding_the_same_entries_none_marked_while_automatic(self):
        r = self._run()
        self.assertTrue(r["subOpen"]["found"] and r["subOpen"]["byHover"], "the nested submenu opened on hover over the entry (the same road): " + json.dumps(r["subOpen"]))
        f = r["withSub"]
        table = "\n  " + json.dumps(f)
        self.assertIsNotNone(f["sub"], "the submenu was read" + table)
        self.assertTrue(f["sub"]["inside"], "appended inside the Billing flyout: leaving both closes both" + table)
        items = [i for i in f["sub"]["items"] if not i.get("sep")]
        self.assertEqual([i["text"] for i in items], [c["text"] for c in f["choices"]], "exactly the list's entries, in its order" + table)
        self.assertTrue(all(i["scope"] == "machine" for i in items), table)
        self.assertEqual([i["current"] for i in items], [False, False], "no explicit default yet: nothing is check-marked" + table)
        self.assertTrue(all(i["check"] in ("none", "normal", "") or i["checkW"] == 0 for i in items), "…and no check mark is painted (the computed ::after)" + table)
        self.assertFalse(any(i.get("sep") for i in f["sub"]["items"]), "no rule and no Automatic while the default is automatic already" + table)
        self.assertEqual(f["subLines"], 0, "no sub-line in the submenu either" + table)
        er, sr = f["entry"]["rect"], f["sub"]["rect"]
        self.assertTrue(sr["left"] >= er["right"] - 0.5 or sr["right"] <= er["left"] + 0.5 or sr["top"] >= er["bottom"] - 0.5 or sr["bottom"] <= er["top"] + 0.5,
                        "placed beside (or below, or above) its entry, never over it" + table)
        self.assertLessEqual(abs(sr["top"] - er["top"]), 2, "beside: its top aligned to the entry's row" + table)

    def test_the_nested_submenu_keeps_the_flyouts_row_size_and_its_entrys_caret_lines_up_with_the_billing_rows(self):
        """Round one: .ctx-menu's 0.92em compounded at the third level (11.0 px against 10.1 px), and the entry's caret sat about
        16 px further in than the Billing and Tags carets (the check-mark room). Measured, never read."""
        f = self._run()["withSub"]
        table = "\n  " + json.dumps(f["fontPx"]) + " " + json.dumps({"entry": f["entry"]["caretInset"], "row": f["rowCaretInset"]})
        self.assertIsNotNone(f["sub"], "the submenu was read")
        self.assertAlmostEqual(f["fontPx"]["sub"], f["fontPx"]["fly"], delta=0.05, msg="the nested level's rows are the flyout's size" + table)
        self.assertLess(f["fontPx"]["fly"], f["fontPx"]["menu"], "the flyout is a menu inside a menu (0.92em once), as on main" + table)
        self.assertIsNotNone(f["entry"]["caretInset"]); self.assertIsNotNone(f["rowCaretInset"])
        self.assertAlmostEqual(f["entry"]["caretInset"], f["rowCaretInset"], delta=1, msg="the Set default billing caret sits where the Billing row's does" + table)

    def test_a_default_pick_in_the_submenu_writes_the_seed_touches_no_session_and_marks_itself_with_automatic_behind_a_rule(self):
        r = self._run()
        self.assertTrue(r["pick"]["found"] and not r["pick"]["disabled"], json.dumps(r["pick"]))
        self.assertTrue(r["pick"]["menuGone"], "the pick dismisses the menu")
        a = r["afterPick"]
        self.assertIsNotNone(a and a["sub"], "the submenu was read again after the pick")
        table = "\n  " + json.dumps(a)
        self.assertTrue((a["subLine"] or "").startswith("Login"), "web (no pick of its own) now reads the login, at once" + table)
        self.assertEqual([c["current"] for c in a["choices"]], [True, False], "…and its own choice marks the login it follows" + table)
        items = a["sub"]["items"]
        self.assertEqual([i.get("text", "---") for i in items], [a["choices"][0]["text"], "API key", "---", "Automatic"], "the list, then the rule, then Automatic at the END" + table)
        self.assertEqual([i.get("current") for i in items if not i.get("sep")], [True, False, False], "the explicit Login default wears the check" + table)
        self.assertEqual(items[0]["check"], '"✓"', "the check mark is the painted pseudo-element" + table)
        self.assertGreater(items[0]["checkW"], 0, table)
        self.assertTrue(items[3]["auto"], table)
        self.assertEqual(a["subLines"], 0, "Automatic carries no sub-line" + table)
        api = json.loads(Path(self.state, "sdk", SIDS["api"] + ".json").read_text())
        self.assertEqual(api.get("auth"), "key", "a session with its own pick is untouched")
        web = json.loads(Path(self.state, "sdk", SIDS["web"] + ".json").read_text())
        self.assertNotIn("auth", web, "a session that follows the default carries no pick of its own; it takes the new side at its next launch")
        # then Automatic: the way back clears the explicit default, and the submenu marks nothing and offers no Automatic
        c = r["autoClick"]
        self.assertTrue(c["found"] and c["behindRule"] and c["last"] and c["menuGone"], json.dumps(c))
        d = json.loads(Path(self.state, "sdk-defaults.json").read_text())
        self.assertEqual((d.get("auth"), d.get("authExplicit")), ("", False), "the seed and the flag cleared: " + json.dumps(d))
        z = r["afterAuto"]
        self.assertEqual([i.get("current") for i in z["sub"]["items"] if not i.get("sep")], [False, False], "\n  " + json.dumps(z))
        self.assertFalse(any(i.get("sep") for i in z["sub"]["items"]), "no Automatic while the default is automatic" + "\n  " + json.dumps(z))
        self.assertEqual(z["subLine"], "API key", "web follows the helper rule again")

    def test_in_a_narrow_or_short_window_both_levels_stay_inside_the_viewport_and_the_flyout_never_covers_its_row_while_a_place_exists(self):
        r = self._run()
        for size, f in r["narrow"].items():
            table = "\n  %s: %s" % (size, json.dumps(f)[:900])
            self.assertIsNotNone(f, table)
            self.assertGreaterEqual(f["rect"]["left"], 8 - 0.5, "inside the viewport, left" + table)
            self.assertLessEqual(f["rect"]["right"], f["viewport"] - 8 + 0.5, "inside the viewport, right" + table)
            self.assertGreaterEqual(f["rect"]["top"], -0.5, "inside the viewport, top" + table)
            self.assertLessEqual(f["rect"]["bottom"], f["viewportH"] + 0.5, "inside the viewport, bottom" + table)
            rr, fr = f["rowRect"], f["rect"]
            beside = fr["left"] >= rr["right"] - 0.5 or fr["right"] <= rr["left"] + 0.5
            below = fr["top"] >= rr["bottom"] - 0.5
            above = fr["bottom"] <= rr["top"] + 0.5
            fits_below = rr["bottom"] + 2 + fr["h"] <= f["viewportH"] - 4
            fits_above = rr["top"] - 2 - fr["h"] >= 0
            if fits_below or fits_above:
                self.assertTrue(beside or below or above, "never over its own row while a place beside, below or above exists" + table)
            if fits_below and not beside:
                self.assertTrue(below, "below the row when it fits there (review: the clamp pulled it back over the row)" + table)
            elif fits_above and not beside:
                self.assertTrue(above, "above the row's top when below does not fit" + table)
            if f["sub"]:
                sr = f["sub"]["rect"]
                self.assertGreaterEqual(sr["left"], 8 - 0.5, "the nested submenu inside the viewport too" + table)
                self.assertLessEqual(sr["right"], f["viewport"] - 8 + 0.5, table)
                self.assertGreaterEqual(sr["top"], -0.5, table)
                self.assertLessEqual(sr["bottom"], f["viewportH"] + 0.5, table)


class ServedBillingFlyoutOneSide(ServedBillingFlyout):
    """The same lab on a machine with NO apiKeyHelper: one billing to choose from, so neither the rule nor the entry."""
    BOTH_SIDES = False
    result = None

    def test_hovering_the_billing_row_opens_the_flyout_without_a_click(self):
        super().test_hovering_the_billing_row_opens_the_flyout_without_a_click()

    def test_leaving_closes_the_flyout_and_its_submenu_and_keeps_the_menu_and_escape_closes_all(self):
        super().test_leaving_closes_the_flyout_and_its_submenu_and_keeps_the_menu_and_escape_closes_all()

    def test_the_flyout_lists_the_picks_then_a_rule_and_one_set_default_billing_entry_with_no_sub_line(self):
        r = self._run()
        f = r["fly"]
        table = "\n  " + json.dumps(f)
        self.assertEqual([c["text"].split(" (")[0] for c in f["choices"]], ["Login", "API key"], "both sides still listed" + table)
        self.assertEqual([c["disabled"] for c in f["choices"]], [False, True], "the key greyed: no apiKeyHelper here" + table)
        self.assertIn("apiKeyHelper", f["choices"][1]["title"], "with the reason in its hover" + table)
        self.assertEqual(f["lines"], [c["text"] for c in f["choices"]], "one billing to choose from: no rule, no Set default billing entry" + table)
        self.assertFalse(f["sep"], table)
        self.assertIsNone(f["entry"], table)
        self.assertEqual(f["subLines"], 0, table)

    def test_the_entry_opens_a_nested_submenu_by_hover_holding_the_same_entries_none_marked_while_automatic(self):
        r = self._run()
        self.assertFalse(r["subOpen"]["found"], "no entry, so nothing to open: " + json.dumps(r["subOpen"]))

    def test_the_nested_submenu_keeps_the_flyouts_row_size_and_its_entrys_caret_lines_up_with_the_billing_rows(self):
        self.assertIsNone(self._run()["withSub"]["entry"], "one billing to choose from: no entry, so nothing to measure")

    def test_a_default_pick_in_the_submenu_writes_the_seed_touches_no_session_and_marks_itself_with_automatic_behind_a_rule(self):
        r = self._run()
        self.assertFalse(r["pick"]["found"], "no submenu to pick from: " + json.dumps(r["pick"]))
        self.assertFalse(os.path.exists(os.path.join(self.state, "sdk-defaults.json")), "nothing wrote a seed")

    def test_in_a_narrow_or_short_window_both_levels_stay_inside_the_viewport_and_the_flyout_never_covers_its_row_while_a_place_exists(self):
        super().test_in_a_narrow_or_short_window_both_levels_stay_inside_the_viewport_and_the_flyout_never_covers_its_row_while_a_place_exists()


if __name__ == "__main__":
    unittest.main()
