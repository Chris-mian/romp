"""The Needs you colour and word on every surface (plans/needs-you.md, phase two): a hermetic kernel over two synthetic sessions
(web, under one tag, with a judge's question and a blocked sub-goal under it; api idle) in the notes-api demo world, the real
pages served from a copy of the built bundle, driven by Playwright in BOTH themes. What it reads, computed, never as source:
the feed's column header chip (its word and its colours), the card face's checklist mark for the blocked sub-goal, the modal's
question label and mark; the landing page's chat tab ring (class and outline), the folded tag header's pip for the hidden web,
the section's overview row for web (the shared status chip's word and fill), the settings frame's three ring rows (their
labels, in precedence order) and the Needs you ring's demo tab; the outline page's row mark for the question; the phone
picker's current-session border and its row's bar. Not read here: the bar under the transcript, whose chip says Needs you only
for a live prompt (the kernel's _session_chip; status-chip.test.ts and tab-snapshot.test.ts pin the word), and the sessions
pane's lane chip (drawn on a canvas, pinned by timeline-awaiting.test.ts). Synthetic only: placeholder ids, invented text,
hostname TESTHOST."""
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.dist_copy import copy_dist  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment

WEB = "aaaaaaaa-1111-2222-3333-444444444444"
API = "bbbbbbbb-1111-2222-3333-444444444444"
TOKEN = {"dark": "rgb(217, 70, 239)", "light": "rgb(162, 28, 175)"}   # --st-needs-bg: #d946ef and #a21caf


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
try { browser = await chromium.launch({}); } catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const errors = [];
const out = { feed: {}, strip: {}, settings: {}, phone: {} };
const themes = ["dark", "light"];
const setTheme = (frameOrPage, t) => frameOrPage.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), t);
// ── the feed page: the column header chip, the card's modal (the question label and mark) ──
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const feed = await ctx.newPage(); feed.on("pageerror", (e) => errors.push("feed: " + String(e).slice(0, 200)));
await feed.goto(cfg.feed);
const cardSel = '[data-key="a:' + cfg.web + ':gw"]';
await feed.waitForSelector(cardSel, { state: "attached", timeout: 60000 });
// the card face's sub-goal checklist shows under its Sub-goals section: open it (the button's own click(), inside the card) before the modal
await feed.evaluate((sel) => { const b = Array.from(document.querySelector(sel).querySelectorAll(".fask-secbtn")).find((x) => /sub-goal/.test(x.textContent || "")); if (b) b.click(); }, cardSel);   // the button counts its sub-goals ("1 sub-goal")
await feed.waitForSelector(cardSel + " .fcheck.question .fcheck-mark", { timeout: 20000 }).catch(async () => { errors.push("card: no sub-goal checklist mark on the card face: " + (await feed.evaluate((sel) => { const c = document.querySelector(sel); if (!c) return "no card"; const secs = c.querySelector(".fask-secs"); const cl = c.querySelector(".fask-checklist, .fcheck"); const it = c._it || {}; return "btns=" + JSON.stringify(Array.from(c.querySelectorAll(".fask-secbtn")).map((b) => [b.textContent, b.style.display, b.className])) + " turnId=" + it.turnId + " tree=" + JSON.stringify((it.tree || []).map((n) => [n.id.slice(-3), n.status, n.children, n.kind, n.reviewedEarlier])) + " checklist=" + (cl ? cl.outerHTML.slice(0, 200) : "none"); }, cardSel))); });
await feed.evaluate((sel) => document.querySelector(sel).click(), cardSel);   // the card element itself: a click on the title would open the session instead
await feed.waitForSelector("#feed-modal-body .st-question .ftree-meta", { state: "attached", timeout: 20000 }).catch(async () => {
  errors.push("modal: " + (await feed.evaluate(() => { const b = document.getElementById("feed-modal-body"); return b ? b.innerHTML.slice(0, 600) : "no modal body; modal=" + !!document.getElementById("feed-modal"); })));
});
for (const t of themes) {
  await setTheme(feed, t); await feed.waitForTimeout(200);
  out.feed[t] = await feed.evaluate((sel) => {
    const chip = document.querySelector(".feed-col.col-needsInput .fcol-chip"); const card = document.querySelector(sel);
    const meta = document.querySelector("#feed-modal-body .st-question .ftree-meta"), mark = document.querySelector("#feed-modal-body .st-question .ftree-mark");
    const cmark = card ? card.querySelector(".fcheck.question .fcheck-mark") : null;   // the card face's checklist mark for the blocked sub-goal
    const cs = (e) => e ? getComputedStyle(e) : null;
    return { headText: chip ? chip.textContent : null, headBg: chip ? cs(chip).backgroundColor : null, headFg: chip ? cs(chip).color : null,
             cardCol: card ? card.parentElement.id : null, metaText: meta ? meta.textContent : null, metaBg: meta ? cs(meta).backgroundColor : null,
             markBorder: mark ? cs(mark).borderTopColor : null, markColor: mark ? cs(mark).color : null,
             cardMarkBorder: cmark ? cs(cmark).borderTopColor : null, cardMarkColor: cmark ? cs(cmark).color : null };
  }, cardSel);
}
// ── the landing: the chat frame's tab ring and the settings frame's ring rows and demo ──
const page = await ctx.newPage(); page.on("pageerror", (e) => errors.push("landing: " + String(e).slice(0, 200)));
await page.goto(cfg.landing);
await page.waitForSelector("#rail-gear", { timeout: 20000 });
const frameBy = async (part) => { let f = page.frames().find((x) => x.url().includes(part)); for (let i = 0; i < 100 && !f; i++) { await page.waitForTimeout(100); f = page.frames().find((x) => x.url().includes(part)); } return f; };
const chatF = await frameBy("/chat");
// the settings frame opens through the strip's gear glyph (T415: one click, the Chat tab at its Tab widgets section)
await chatF.waitForSelector("#tabs .tab-strip-end .tab-widgets-gear", { timeout: 20000 });
await chatF.click("#tabs .tab-strip-end .tab-widgets-gear");
await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
const setF = await frameBy("/settings");
if (!setF) errors.push("settings: no frame opened");
await chatF.waitForFunction((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return !!t && t.classList.contains("ring-waiting-on-you"); }, cfg.web, { timeout: 30000 }).catch(async () => {
  errors.push("strip: " + (await chatF.evaluate((id) => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id.slice(0, 8) + ":" + t.className).join(" | "), cfg.web)));
});
// the outline page's tree row for the question wears the mark in the token
const outline = await ctx.newPage(); outline.on("pageerror", (e) => errors.push("outline: " + String(e).slice(0, 200)));
await outline.goto(cfg.outline);
await outline.waitForSelector(".ledger-tnode.blocked .ledger-tmark", { timeout: 30000 }).catch(() => { errors.push("outline: no blocked row mark"); });
out.pip = {}; out.overview = {}; out.outline = {};
for (const t of themes) {
  await setTheme(chatF, t); if (setF) await setTheme(setF, t); await setTheme(page, t); await setTheme(outline, t); await page.waitForTimeout(200);
  out.strip[t] = await chatF.evaluate((id) => { const tab = document.querySelector('#tabs .tab[data-id="' + id + '"]'); const cs = getComputedStyle(tab);
    return { cls: tab.className, outlineColor: cs.outlineColor, outlineStyle: cs.outlineStyle }; }, cfg.web);
  out.outline[t] = await outline.evaluate(() => { const m = document.querySelector(".ledger-tnode.blocked .ledger-tmark"); const cs = m ? getComputedStyle(m) : null;
    return { color: cs ? cs.color : null, border: cs ? cs.borderTopColor : null }; });
  out.settings[t] = !setF ? { rows: [] } : await setF.evaluate(() => {
    const rows = Array.from(document.querySelectorAll("#rs-rings .rs-widget[data-widget]")).map((r) => { const d = r.querySelector(".rs-widget-demo .tab"); const cs = d ? getComputedStyle(d) : null;
      return { id: r.dataset.widget, label: r.querySelector(".rs-widget-name b").textContent, demoOutline: cs ? cs.outlineColor : null, demoStyle: cs ? cs.outlineStyle : null }; });
    return { rows };
  });
}
// the folded group pip and the overview row: web sits alone under one tag; a click on its header (by the element's own click(), since the
// settings frame intercepts pointer events once open) folds the section, so the header's pip reads web's ring, and shows the section's
// overview in the transcript's place, whose row wears the shared status chip with the category's word
await chatF.waitForSelector('#tabs .tab-group-head[data-group="notes"]', { timeout: 30000 }).catch(() => { errors.push("strip: no tag section header"); });
await chatF.evaluate(() => { const h = document.querySelector('#tabs .tab-group-head[data-group="notes"]'); if (h) h.click(); });
await chatF.waitForSelector('#tabs .tab-group-head[data-group="notes"] .tab-group-pip.ask', { timeout: 20000 }).catch(() => { errors.push("pip: the folded header shows no ask pip"); });
await chatF.waitForSelector('.snap-row .chip.chip-needsInput', { timeout: 20000 }).catch(() => { errors.push("overview: no Needs you chip on the section's row"); });
for (const t of themes) {
  await setTheme(chatF, t); await page.waitForTimeout(200);
  out.pip[t] = await chatF.evaluate(() => { const p = document.querySelector('#tabs .tab-group-head[data-group="notes"] .tab-group-pip'); return p ? { cls: p.className, bg: getComputedStyle(p).backgroundColor } : null; });
  out.overview[t] = await chatF.evaluate((id) => { const row = Array.from(document.querySelectorAll(".snap-row")).find((r) => (r.querySelector(".snap-sess") || {}).textContent === "web");
    const c = row ? row.querySelector(".chip") : null; const cs = c ? getComputedStyle(c) : null; return { text: c ? c.textContent : null, bg: cs ? cs.backgroundColor : null, cls: c ? c.className : null }; }, cfg.web);
}
await setTheme(chatF, "dark"); if (setF) await setTheme(setF, "dark"); await setTheme(page, "dark");
// ── the phone: the picker's current-session border and the row's bar ──
const phoneCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 });
const phone = await phoneCtx.newPage(); phone.on("pageerror", (e) => errors.push("phone: " + String(e).slice(0, 200)));
await phone.goto(cfg.chat);
await phone.waitForFunction((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return !!t && t.classList.contains("ring-waiting-on-you"); }, cfg.web, { timeout: 30000 }).catch(() => { errors.push("phone: no ring on the tab"); });
await phone.tap("#mcur");
await phone.waitForSelector("#mlist.open", { timeout: 10000 });
await phone.waitForFunction((id) => !!document.querySelector('#mlist .mrow[data-id="' + id + '"].ask'), cfg.web, { timeout: 10000 }).catch(() => { errors.push("phone: web's row never took the ask class"); });
// the picker's current box wears the ring only for the CURRENT session: pick web (the row tap clicks its desktop tab and closes the list), then reopen the list so both read at once
await phone.tap('#mlist .mrow[data-id="' + cfg.web + '"]');
await phone.waitForFunction(() => { const c = document.getElementById("mcur"); return !!c && c.classList.contains("ask"); }, null, { timeout: 10000 }).catch(() => { errors.push("phone: #mcur never took the ask class after picking web"); });
await phone.tap("#mcur");
await phone.waitForSelector("#mlist.open", { timeout: 10000 });
for (const t of themes) {
  await setTheme(phone, t); await phone.waitForTimeout(200);
  out.phone[t] = await phone.evaluate((id) => { const cur = document.querySelector("#mcur"), row = document.querySelector('#mlist .mrow[data-id="' + id + '"]');
    const cs = (e) => e ? getComputedStyle(e) : null;
    return { curAsk: !!cur && cur.classList.contains("ask"), curBorder: cur ? cs(cur).borderTopColor : null, curStyle: cur ? cs(cur).borderTopStyle : null,
             rowAsk: !!row && row.classList.contains("ask"), rowBar: row ? cs(row).borderLeftColor : null }; }, cfg.web);
}
process.stdout.write("RESULT:" + JSON.stringify({ ...out, errors }) + "\n");
await browser.close();
"""


class NeedsYouColourServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="needs-you-colour-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 3600
        for sid, name, bg, fg in ((WEB, "web", "#9cd2ff", "#0c1a2e"), (API, "api", "#1EA1EB", "#ffffff")):
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            Path(state, "states", sid + ".jsonl").write_text(json.dumps({"t": t0 + 70, "state": "idle"}) + "\n")
            recs = [{"type": "user", "timestamp": iso(t0), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        # web's goal is BLOCKED on the user (a judge's question): its card files under Needs you, its tab wears the ring.
        # The diary entry is in the fold's shape (ev_t/src/kind/at): the rollup rederives every flag from the log at
        # boot, so a bare `blocked` flag with no diary event behind it is cleared before the first frame.
        g = WEB + ":gw"
        gc = WEB + ":gc"   # the blocked sub-goal: the card face's checklist mark (.fcheck.question), the modal's second question row
        Path(state, "goals", WEB + ".json").write_text(json.dumps(
            {"rompUuid": WEB, "seq": 3, "lastNode": g, "closedTurns": [],
             "nodes": {gc: {"id": gc, "text": "pick the database the fixtures load into", "parentId": g, "nodeComplete": False, "blocked": True,
                            "blockWhy": "which database?", "cleared": False, "trail": [], "t": t0 + 5,
                            "log": [{"ev_t": t0 + 62, "src": "planner", "kind": "block", "why": "asked which database", "at": t0 + 62}]},
                       g: {"id": g, "text": "wire the fixtures directory into the integration suite", "parentId": None,
                           "nodeComplete": False, "blocked": True, "blockWhy": "which database does the suite target?", "cleared": False, "trail": [], "t": t0,
                           "log": [{"ev_t": t0 + 61, "src": "planner", "kind": "block", "why": "asked which database the suite targets", "at": t0 + 61}]}},
             "placements": {}, "status": {g: "blocked", gc: "blocked"}}))
        # one tag holding web: the strip groups by tag, so its header can be folded (the pip) and clicked (the overview row)
        Path(state, "timeline-views.json").write_text(json.dumps(
            {"tags": [{"id": "t-notes", "name": "notes", "color": "#9088F0", "members": [WEB]}], "tagOrder": ["notes"]}))
        cls.port, cls.token = _free_port(), "testtok-needsyou"
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
            cfg = os.path.join(self.lab, "needsyou.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"outline": base + "/fleet?token=" + self.token, "feed": base + "/feed?token=" + self.token, "landing": base + "/?token=" + self.token, "chat": base + "/chat?token=" + self.token,
                           "token": self.token, "web": WEB, "api": API}, f)
            driver = os.path.join(self.lab, "needsyou.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if not line:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        return self._r

    def test_the_feed_says_needs_you_in_the_token_on_the_column_chip_and_the_modals_question_label_and_mark_in_both_themes(self):
        r = self._result()
        for t in ("dark", "light"):
            f = r["feed"][t]
            self.assertEqual(f["cardCol"], "col-needsInput-list", "%s: the blocked goal's card files under Needs you: %r (errors: %r)" % (t, f, [e[:160] for e in r["errors"]]))
        self.assertEqual(r["errors"], [], "no page error")
        for t in ("dark", "light"):
            f = r["feed"][t]
            self.assertEqual(f["headText"], "Needs you", "%s: the column header's word" % t)
            self.assertEqual(f["headBg"], TOKEN[t], "%s: the column chip wears the Needs you token: %r" % (t, f))
            self.assertEqual(f["metaText"], "Needs you", "%s: the modal's question label reads the category's word" % t)
            self.assertEqual((f["cardMarkBorder"], f["cardMarkColor"]), (TOKEN[t], TOKEN[t]), "%s: the card face's checklist mark for the blocked sub-goal wears the token: %r" % (t, f))
            self.assertEqual(f["metaBg"], TOKEN[t], "%s: the label's chip wears the token: %r" % (t, f))
            self.assertEqual((f["markBorder"], f["markColor"]), (TOKEN[t], TOKEN[t]), "%s: the question mark's ring and glyph wear the token, never red: %r" % (t, f))

    def test_the_tab_ring_and_the_settings_demo_wear_the_token_and_the_ring_rows_read_blocked_needs_you_retrying(self):
        r = self._result()
        for t in ("dark", "light"):
            self.assertEqual(r["pip"][t], {"cls": "tab-group-pip ask", "bg": TOKEN[t]}, "%s: the folded header's pip for the hidden web wears the token" % t)
            self.assertEqual(r["overview"][t], {"text": "Needs you", "bg": TOKEN[t], "cls": "chip chip-needsInput"}, "%s: the section's overview row for web wears the shared chip with the category's word in the token" % t)
            self.assertEqual(r["outline"][t], {"color": TOKEN[t], "border": TOKEN[t]}, "%s: the outline page's row mark for the question wears the token" % t)
        for t in ("dark", "light"):
            s = r["strip"][t]
            self.assertIn("ring-waiting-on-you", s["cls"].split(), "%s: the tab wears the Needs you ring: %r" % (t, s))
            self.assertEqual((s["outlineStyle"], s["outlineColor"]), ("dashed", TOKEN[t]), "%s: the ring is dashed in the token: %r" % (t, s))
            rows = r["settings"][t]["rows"]
            self.assertEqual([x["label"] for x in rows], ["Blocked", "Needs you", "Retrying"], "%s: the ring rows' labels in precedence order: %r" % (t, rows))
            demo = next(x for x in rows if x["id"] == "ring-waiting-on-you")
            self.assertEqual((demo["demoStyle"], demo["demoOutline"]), ("dashed", TOKEN[t]), "%s: the Needs you demo tab's ring wears the token: %r" % (t, demo))

    def test_the_phone_pickers_current_session_border_and_row_bar_wear_the_token(self):
        r = self._result()
        for t in ("dark", "light"):
            p = r["phone"][t]
            self.assertTrue(p["curAsk"] and p["rowAsk"], "%s: the current session and its row carry the ring's class: %r" % (t, p))
            self.assertEqual((p["curStyle"], p["curBorder"]), ("dashed", TOKEN[t]), "%s: the current-session chip's dashed border in the token: %r" % (t, p))
            self.assertEqual(p["rowBar"], TOKEN[t], "%s: the row's left bar in the token: %r" % (t, p))


if __name__ == "__main__":
    unittest.main()
