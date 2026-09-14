#!/usr/bin/env python3
"""THE STRIP'S TAGS MENU AND ITS BUTTON (T413, the user 2026-09-14) on the served chat page: a hermetic kernel serves six synthetic
notes-api sessions (TESTHOST) and THIRTY tags (the many-tags fixture of the 2026-09-09 rule), each session under several. (1) In
the tags menu every tag row is the house switch: role menuitemcheckbox with aria-checked, a two-state mark at its right (the
check-in-circle when selected, an empty ring when not) beside the lit or faded chip. (2) With the strip NOT grouping tabs by tag,
every selected tag shows as the standard chip just LEFT of the tags button: two tags, two chips; thirty, three chips and one
plain "+27 more" chip that opens the menu; a chip's cross drops its tag; the run never adds a row (the rows with the chips equal
the rows without them, in a wide window and a narrow one where the run yields) and never pushes the button or the gear off the
strip's right end. Grouping, the tags are the section headings and nothing sits beside the button. Both themes, screenshots.

STRIP_TAGS_DIST=<dir> serves another tree's UI bundle (the red run's before); STRIP_TAGS_SHOTS=<prefix> writes
<prefix>-<scene>-<theme>.png; STRIP_TAGS_DUMP=<path> writes the whole measurement. Skips LOUDLY without the extension deps or a
Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip there is a failure). Synthetic throughout:
placeholder sids, TESTHOST, invented tag names.
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
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

NAMES = ["web", "api", "deploy", "tests", "docs", "auth"]
TAGS = ["infra", "web", "api", "docs", "tests", "auth", "deploy", "data", "ops", "ui", "db", "cache", "queue", "mail", "search",
        "billing", "export", "import", "sync", "alerts", "logs", "metrics", "backup", "perf", "access", "locale", "mobile", "desktop", "cli", "sdk"]   # thirty
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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 700 } });
const page = await ctx.newPage();
const errors = [];   // page errors and console errors, kept in the result
page.on("pageerror", (e) => errors.push("pageerror: " + String(e)));
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.type() + ": " + m.text()); });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
await page.waitForTimeout(600);
const out = {};
// the strip: its rows (distinct tops of the visible items, the hairlines aside), the right end's places, the chips host
const readStrip = () => page.evaluate(() => {
  const bar = document.getElementById("tabs"); const b = bar.getBoundingClientRect(); const r1 = (v) => Math.round(v * 10) / 10;
  const items = () => Array.from(bar.children).filter((c) => !c.classList.contains("tab-row-line") && c.getClientRects().length);
  const rowsNow = () => new Set(items().map((c) => Math.round(c.getBoundingClientRect().top))).size;
  const end = bar.querySelector(".tab-strip-end"), gear = bar.querySelector(".tab-widgets-gear"), btn = bar.querySelector(".tab-tagfilter"), host = bar.querySelector(".tab-tagbox .tab-tagchips");
  let rowsSansChips = null;
  if (host) { const was = host.hidden; host.hidden = true; rowsSansChips = rowsNow(); host.hidden = was; }
  const chips = host ? Array.from(host.children).map((c) => ({ text: c.textContent.replace("✕", "").trim(), cls: c.className, title: c.title, color: getComputedStyle(c).color, w: r1(c.getBoundingClientRect().width) })) : null;
  return { rows: rowsNow(), rowsSansChips, heads: bar.querySelectorAll(".tab-group-head").length, tabs: bar.querySelectorAll(".tab[data-id]").length,
           endRightGap: end ? r1(b.right - end.getBoundingClientRect().right) : null, gearRightGap: gear ? r1(b.right - gear.getBoundingClientRect().right) : null,
           btnToGear: btn && gear ? r1(gear.getBoundingClientRect().left - btn.getBoundingClientRect().right) : null,
           pressed: btn ? btn.getAttribute("aria-pressed") : null, btnColor: btn ? getComputedStyle(btn).color : null,
           hostPresent: !!host, hostHidden: host ? host.hidden : null, hostVisible: !!host && host.getClientRects().length > 0 && !host.hidden, chips,
           chipsLeftOfBtn: host && btn && host.getClientRects().length ? r1(btn.getBoundingClientRect().left - host.getBoundingClientRect().right) : null,
           stripW: r1(b.width), groups: (() => { try { return JSON.parse(localStorage.getItem("romp:tabgroups") || "null"); } catch (e) { return null; } })() };
});
const readMenu = () => page.evaluate(() => { const m = document.querySelector('[data-tag-menu="1"]'); if (!m) return null;
  return Array.from(m.children).map((r) => { const mark = r.querySelector("[data-check]"); const chip = Array.from(r.children).find((k) => /border:1px solid/.test(k.getAttribute("style") || ""));
    return { label: r.textContent.replace("✓", "").trim(), role: r.getAttribute("role"), checked: r.getAttribute("aria-checked"),
             mark: mark ? { check: mark.getAttribute("data-check"), text: mark.textContent, bg: getComputedStyle(mark).backgroundColor, border: getComputedStyle(mark).borderTopColor, w: mark.getBoundingClientRect().width } : null,
             chipOpacity: chip ? getComputedStyle(chip).opacity : null }; }); });
// the menu opens on the press and the release's click is the button's to swallow: the press is held while the rows are
// clicked by script and released at the end (at the base a thirty-tag menu stood over its own button, so the release landed
// on the menu and the click, fired at the common ancestor, closed it; the head caps the menu to the room on its side)
const openMenu = async () => {
  const r = await page.evaluate(() => { const btn = document.querySelector("#tabs .tab-tagfilter"); btn.scrollIntoView({ block: "nearest" }); const b = btn.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; });   // a thirty-heading strip scrolls inside its bar: the button into view first
  await page.mouse.move(r.x, r.y); await page.mouse.down();
  await page.waitForSelector('[data-tag-menu="1"]', { timeout: 5000 }); await page.waitForTimeout(150);
};
const readMenuBox = () => page.evaluate(() => { const m = document.querySelector('[data-tag-menu="1"]'); if (!m) return null; const r = m.getBoundingClientRect(); const b = document.querySelector("#tabs .tab-tagfilter").getBoundingClientRect();
  return { top: r.top, bottom: r.bottom, h: r.height, rows: m.children.length, scrolls: m.scrollHeight > m.clientHeight + 1, overflowY: getComputedStyle(m).overflowY, vh: window.innerHeight,
           coversButton: r.top < b.bottom && r.bottom > b.top && r.left < b.right && r.right > b.left, belowButton: r.top >= b.bottom, btnBottom: b.bottom }; });
const clickRow = async (label) => { await page.evaluate((label) => { const m = document.querySelector('[data-tag-menu="1"]'); const r = Array.from(m.children).find((x) => x.textContent.replace("✓", "").trim() === label); if (!r) throw new Error("no row " + label); r.click(); }, label); await page.waitForTimeout(220); };
// a click on the page body closes the menu (the document's click closer); an Escape with the keyboard on the body is recorded once below, not relied on
const closeMenu = async () => { await page.mouse.up(); await page.waitForTimeout(150); await page.evaluate(() => document.body.click()); await page.waitForTimeout(200); };
const shot = async (name, theme) => { if (!cfg.shots) return; const bar = await page.evaluate(() => { const b = document.getElementById("tabbar").getBoundingClientRect(); const m = document.querySelector('[data-tag-menu="1"]'); const extra = m ? m.getBoundingClientRect().bottom - b.bottom + 8 : 60;   // the menu, when open, in the frame
  return { x: 0, y: Math.max(0, b.top - 4), width: window.innerWidth, height: Math.min(window.innerHeight - b.top, b.height + extra) }; });
  await page.screenshot({ path: cfg.shots + "-" + name + "-" + theme + ".png", clip: bar }); };
const themed = async (name, fn) => { for (const theme of ["dark", "light"]) { await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme); await page.waitForTimeout(200); if (fn) out[name + "_" + theme] = await fn(); await shot(name, theme); } await page.evaluate(() => document.body.classList.remove("theme-light")); await page.waitForTimeout(150); };
// 1. boot: grouping is the default with tags present: the headings carry the tags, nothing beside the button
out.boot = await readStrip();
await openMenu(); out.menuBoot = await readMenu(); out.menuBox = await readMenuBox();
await page.mouse.up(); await page.waitForTimeout(200); out.menuAfterRelease = !!(await page.$('[data-tag-menu="1"]'));
await page.keyboard.press("Escape"); await page.waitForTimeout(200); out.escapeClosed = !(await page.$('[data-tag-menu="1"]'));   // an observation for the read
await page.evaluate(() => document.body.click()); await page.waitForTimeout(200);
// 2. grouping off through the menu's own switch; All as the baseline for the rows
await openMenu(); await clickRow("Group tabs by tag"); await page.waitForTimeout(300); await clickRow("All"); await page.waitForTimeout(300); await closeMenu();
out.flatNone = await readStrip();
// 3. two tags selected: two chips left of the button
await openMenu(); await clickRow("infra"); await clickRow("web"); out.menuTwo = await readMenu(); await closeMenu();
out.flatTwo = await readStrip();
await themed("few", null);
// 4. every tag selected (thirty): a bounded run, the rest as one count
await openMenu(); for (const t of cfg.tags.slice(2)) await clickRow(t); out.menuMany = await readMenu();
await themed("menu", readMenu);
await closeMenu();
out.flatMany = await readStrip();
await themed("many", null);
// 5. the more chip opens the menu; a chip's cross drops its tag
// (guarded: at the base neither chip exists, and the run must finish for every test to read its own red)
if (await page.$("#tabs .tab-tagchips .tag-chip-more")) { await page.click("#tabs .tab-tagchips .tag-chip-more"); await page.waitForTimeout(200); out.moreOpens = !!(await page.$('[data-tag-menu="1"]')); await page.evaluate(() => document.body.click()); await page.waitForTimeout(200); }
else out.moreOpens = null;
await page.evaluate(() => { const host = document.querySelector("#tabs .tab-tagbox .tab-tagchips"); const x = host && host.children[0] && host.children[0].lastElementChild; if (x) x.click(); }); await page.waitForTimeout(400);
out.afterRemove = await readStrip();
// 6. a narrow window: the run yields rather than add a row (the rows with the chips equal the rows without them)
await page.setViewportSize({ width: 560, height: 700 }); await page.waitForTimeout(500);
out.narrowMany = await readStrip();
await page.setViewportSize({ width: 1400, height: 700 }); await page.waitForTimeout(500);
// 7. grouping on again: the headings, no chips
await openMenu(); await clickRow("Group tabs by tag"); await page.waitForTimeout(300); await closeMenu();
out.groupedMany = await readStrip();
await themed("grouped", null);
out.errors = errors;
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
"""


class ServedStripTagChips(unittest.TestCase):
    maxDiff = None
    result = None

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
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="strip-tags-")
        before = os.environ.get("STRIP_TAGS_DIST", "")
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
        Path(state, "session-hosts").write_text("off\n")   # this lab mints its own state root: no session host (repo rule)
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i % len(PALETTE)]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        # thirty tags, each session under several (tag i holds sessions i and i+1 round the six): the many-tags fixture; the chat lens open (All)
        tags = [{"id": "tag-" + t, "name": t, "color": PALETTE[i % len(PALETTE)][0], "members": [SIDS[NAMES[i % len(NAMES)]], SIDS[NAMES[(i + 1) % len(NAMES)]]]} for i, t in enumerate(TAGS)]
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "actives": {"chat": {"all": True}}, "tags": tags}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-striptags"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
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
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

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
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "landing": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token),
                       "count": len(NAMES), "names": NAMES, "tags": TAGS, "out": out, "shots": os.environ.get("STRIP_TAGS_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        if not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        result = json.loads(Path(out).read_text())
        if os.environ.get("STRIP_TAGS_DUMP"):
            Path(os.environ["STRIP_TAGS_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def test_the_tags_menu_rows_are_checkboxes_with_a_two_state_mark_beside_the_lit_or_faded_chip(self):
        r = self._run()
        rows = {x["label"]: x for x in r["menuBoot"]}; t = "\n  " + json.dumps(r["menuBoot"][:4])
        for tag in ("infra", "web", "sdk"):
            row = rows[tag]
            self.assertEqual((row["role"], row["checked"]), ("menuitemcheckbox", "false"), tag + ": an unselected tag row is the house switch, unchecked" + t)
            self.assertEqual((row["mark"]["check"], row["mark"]["text"]), ("false", ""), tag + ": the mark is an empty ring when unselected" + t)
            self.assertEqual(row["chipOpacity"], "0.45", tag + ": the chip faded when unselected (the lit state kept)" + t)
        many = {x["label"]: x for x in r["menuMany"]}; tm = "\n  " + json.dumps(r["menuMany"][:4])
        self.assertEqual((many["infra"]["role"], many["infra"]["checked"], many["infra"]["mark"]["check"], many["infra"]["mark"]["text"]), ("menuitemcheckbox", "true", "true", "✓"), "selected: checked, the check-in-circle" + tm)
        self.assertEqual(many["infra"]["mark"]["bg"], "rgb(30, 161, 235)", "the dark theme's check token behind the mark" + tm)
        self.assertEqual(many["infra"]["chipOpacity"], "1", "and the chip lit" + tm)
        light = {x["label"]: x for x in r["menu_light"]}
        self.assertEqual(light["infra"]["mark"]["bg"], "rgb(194, 65, 12)", "the light theme's clay check behind the mark: " + json.dumps(light["infra"]))
        self.assertEqual((rows["All"]["role"], rows["All"]["mark"]["text"], rows["(no tags)"]["role"]), (None, "✓", "menuitemcheckbox"), "at boot the lens is All: its ✓ alone, no checkbox role (the exclusive pick's grammar); (no tags) is a checkbox row" + t)
        self.assertIsNone(many["All"]["mark"], "with tags selected All is not current and shows no mark at all, no ring: the exclusive pick's grammar" + tm)

    def test_the_menu_with_thirty_tags_caps_its_height_scrolls_within_itself_and_never_covers_its_button(self):
        r = self._run(); m = r["menuBox"]; t = "\n  " + json.dumps(m)
        self.assertEqual(m["rows"], 35, "All, (no tags), thirty tags, the separator, the group switch and Configure" + t)
        self.assertFalse(m["coversButton"], "the menu never stands over its own button: the release must reach the button, whose click swallow keeps the menu (the many-tags case)" + t)
        self.assertTrue(m["belowButton"], "it opens below the button and caps its height to the room there" + t)
        self.assertLessEqual(m["bottom"], m["vh"] - 8 + 0.5, "inside the window" + t)
        self.assertTrue(m["scrolls"] and m["overflowY"] == "auto", "and scrolls within itself" + t)
        self.assertTrue(r["menuAfterRelease"], "the press released over the button leaves the menu standing" + t)

    def test_outside_group_mode_two_selected_tags_are_two_chips_left_of_the_button_adding_no_row(self):
        r = self._run(); s = r["flatTwo"]; base = r["flatNone"]; t = "\n  " + json.dumps(s) + "\n  base=" + json.dumps(base)
        self.assertFalse(s["groups"] and s["groups"].get("on"), "grouping off" + t)
        self.assertTrue(s["hostPresent"] and s["hostVisible"], "the chips host shows beside the button" + t)
        self.assertEqual([c["text"] for c in s["chips"]], ["infra", "web"], "the two selected tags, as chips, in the unions' order" + t)
        self.assertGreaterEqual(s["chipsLeftOfBtn"], 0, "the chips sit LEFT of the button" + t)
        self.assertEqual(s["rows"], base["rows"], "the selection added no row" + t)
        self.assertEqual(s["rows"], s["rowsSansChips"], "the rows with the chips equal the rows without them" + t)
        self.assertLessEqual(s["endRightGap"], 2.0, "the right end flush with the strip" + t); self.assertLessEqual(abs(s["gearRightGap"] - 4), 0.6, "the gear at its 4px" + t)
        self.assertEqual(s["pressed"], "true", "the button wears the accent: narrowed" + t)
        self.assertEqual(base["chips"], [], "the baseline, All: no chip" + t)

    def test_thirty_selected_tags_are_a_bounded_run_three_chips_and_the_rest_as_one_count_that_opens_the_menu(self):
        r = self._run(); s = r["flatMany"]; base = r["flatNone"]; t = "\n  " + json.dumps(s)
        self.assertEqual([c["text"] for c in s["chips"]], ["infra", "web", "api", "+27 more"], "three chips then the count, in the user's terms" + t)
        self.assertEqual(s["chips"][3]["cls"], "tag-chip-more", "the more chip is the plain chip" + t)
        for name in ("docs", "sdk", "cli"): self.assertIn(name, s["chips"][3]["title"], "its title names the rest" + t)
        self.assertEqual(s["rows"], base["rows"], "thirty tags added no row" + t); self.assertEqual(s["rows"], s["rowsSansChips"], t)
        self.assertLessEqual(s["endRightGap"], 2.0, t); self.assertLessEqual(abs(s["gearRightGap"] - 4), 0.6, "the gear and the button stay on the strip's end" + t)
        self.assertTrue(r["moreOpens"], "the more chip opens the menu")
        a = r["afterRemove"]; ta = "\n  " + json.dumps(a)
        self.assertEqual([c["text"] for c in a["chips"]], ["web", "api", "docs", "+26 more"], "the first chip's cross dropped its tag: the run shifts, the count follows" + ta)

    def test_a_narrow_window_the_run_yields_rather_than_add_a_row(self):
        r = self._run(); s = r["narrowMany"]; t = "\n  " + json.dumps(s)
        self.assertTrue(s["hostPresent"], t)
        self.assertEqual(s["rows"], s["rowsSansChips"], "the rows with the chips equal the rows without them: the run yields (hidden) when it alone would wrap the right end" + t)
        self.assertLessEqual(s["endRightGap"], 2.0, "the right end still flush" + t); self.assertLessEqual(abs(s["gearRightGap"] - 4), 0.6, "the gear on the strip's end" + t)
        self.assertEqual(s["pressed"], "true", "the accent still says narrowed, chips or not" + t)

    def test_in_group_mode_the_headings_carry_the_tags_and_nothing_sits_beside_the_button(self):
        r = self._run()
        for name in ("boot", "groupedMany"):
            s = r[name]; t = "\n  " + name + "=" + json.dumps(s)
            self.assertTrue(s["groups"] is None or s["groups"].get("on"), "grouping on" + t)
            self.assertGreaterEqual(s["heads"], 1, "the tags are the section headings" + t)
            self.assertTrue(s["hostPresent"], "the host exists" + t)
            self.assertFalse(s["hostVisible"], "and shows nothing beside the button" + t)
            self.assertEqual(s["chips"], [], t)
        self.assertEqual(r["groupedMany"]["pressed"], "true", "narrowed to thirty tags, the button says so in group mode too")


if __name__ == "__main__":
    unittest.main()
