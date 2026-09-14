#!/usr/bin/env python3
"""T414 folded into T416 (the user 2026-09-14): with the feed's focused-session section on, a click on a card's SUMMARY
line that jumps into another session switches the section and scrolls the feed's box to the TOP at once, on the click
itself, so the section, now showing that session's cards, is in view. Nothing waits on the kernel's activeChat frame:
the first cut recorded the jump and scrolled when the frame landed, and a click that changed no tab left the record
standing for the next hand switch (the review's medium); its per-handler note also missed the split summary's
paragraphs (the second medium). Now the jump is noted in the ONE place every jump passes (the host api's postMessage)
and the switch is local (ui/webview/feed.ts, noteOwnJump / applyLocalFocus / scrollFeedTop).

The served lab drives the real /feed page from a hermetic kernel with a SYNTHETIC payload (the notes-api demo world:
`web` with twenty-eight Working cards and a Completed one so the board alone scrolls more than 900 px, `api` with a Completed card
carrying a summary and its anchor and a second whose summary is two cited paragraphs, `tests` a CLOSED session with a
Completed card), the section switched on through the View menu, and walks these roads in one browser run:
  (a) row layout, web focused, the list scrolled 600 px down: a click on api's summary line posts the jump and, at once,
      the section shows api with the list at scrollTop 0 and the section's first block head in view; the kernel's
      frame for web that a push built before the switch carries (stale) flips nothing; the frame for api settles it; a
      later frame for web is a real switch;
  (k) a burst of three switches faster than the round trip (the shell's relays api, tests, web with their announcement
      numbers), then the kernel's frames in order: the section stays on web through all three (the round-two medium: a
      count of disagreeing frames used to let the second one land a stale session); and a burst back to the same
      session (api, web, api): the first frame for api is not the echo (its number differs), the frame for web yields,
      the numbered echo settles, and a frame with nothing pending is a real switch;
  (b) the reader scrolls after the jump: the kernel's frame lands and the list stays where they put it;
  (c) a summary click on the session already focused (api, scrolled down): the top at once;
  (d) the section OFF, a board of more than twenty cards with more than 900 px of room: the click and the frame move the
      list by nothing;
      and the section switched off before a jump then on again: nothing moved;
  (e) a summary click on a CLOSED session's card, then a hand switch (a frame for api) later: the click switches and
      scrolls nothing, the frame switches the section and scrolls nothing;
  (f) the split summary: a click on its second paragraph switches and scrolls at once (the one-place note);
  (g) the shell's relay of the chat's tab change ({romp:"activeChat"}) made by the reader (gesture true) switches the
      section at once with the pointer resting on a board card; a relay of a kernel-driven switch (gesture false) under
      that pointer waits for the release like a push (the round-two low), and so does the kernel's own frame;
  (h) a session name clicked in the feed (an openSession post) switches the section and scrolls nothing: the jump
      scroll rides the Summary and card jumps only (the round-two low);
  (i) a grouped card's modal opened (its title handler once posted its jump at paint time, braces missing): the
      section and the scroll stand, through a later push too (the round-two medium);
  (l) the kernel's frame beats the shell's relay for the same switch while a board card is held: the frame parks the
      paint, and the relay (the reader's gesture) paints it at once instead of leaving the section stale until the
      pointer moves (the round-three medium);
  (m) one throw inside render (a lookup made to fail once) leaves no mark behind: the next Summary click switches and
      scrolls (the round-three medium: a bare clearing once left the mark set);
  (n) the shell's revealCard for a card no longer on the board, marked with the reader's gesture (a bell click, a
      notification tap): its openSession switches the section at once and scrolls nothing (a round-three low);
  (o) a re-announce after a socket flap (an agreeing frame with a higher number) settles the record, so a later frame
      for another session is a real switch (a round-three low: the record used to stand for the page's life);
  (j) the single-column layout (a 520 px viewport): road (a)'s jump again.
Screenshots with FEED_FOCUS_SCROLL_SHOTS=<path-prefix>: -1-row-dark/-light and -2-stacked-dark/-light. Optional, never a
skip. Skips LOUDLY without the extension deps or a Playwright browser, and for nothing else; a build or kernel failure
is a failure. Source pins ride ui/webview/feed-focus-local-switch.test.ts. All fixtures synthetic.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment

SID_WEB = "aaaaaaaa-1111-2222-3333-777777777777"
SID_API = "aaaaaaaa-1111-2222-3333-888888888888"
SID_TESTS = "aaaaaaaa-1111-2222-3333-999999999999"
WEB_DONE = "cccccccc-1111-2222-3333-000000000009"
API_DONE = "cccccccc-1111-2222-3333-000000000021"
API_SPLIT = "cccccccc-1111-2222-3333-000000000022"
TESTS_DONE = "cccccccc-1111-2222-3333-000000000031"
API_GRP1 = "cccccccc-1111-2222-3333-000000000041"
API_GRP2 = "cccccccc-1111-2222-3333-000000000042"
API_ANCHOR = "dddddddd-1111-2222-3333-000000000001"
WEB_ANCHOR = "dddddddd-1111-2222-3333-000000000002"
TESTS_ANCHOR = "dddddddd-1111-2222-3333-000000000003"
PARA_ANCHORS = ["dddddddd-1111-2222-3333-000000000011", "dddddddd-1111-2222-3333-000000000012"]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 2 });
const errors = [];
page.on("pageerror", (e) => { const t = String(e && e.stack || e); if (!t.includes("lab: one-shot throw inside render")) errors.push(t.slice(0, 400)); });   // road (m)'s own throw is expected
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text().slice(0, 300)); });
// capture what the page posts to its host (a jump is a showOnTimeline message)
await page.addInitScript(() => {
  window.__posted = [];
  let real;
  Object.defineProperty(window, "acquireVsCodeApi", {
    configurable: true,
    get() { return function () { const api = real ? real() : {}; const post = api.postMessage ? api.postMessage.bind(api) : () => {};
      api.postMessage = (m) => { window.__posted.push(m); return post(m); }; return api; }; },
    set(fn) { real = fn; },
  });
});
const ready = async () => {
  await page.waitForFunction(() => document.readyState === "complete" && typeof window.acquireVsCodeApi === "function", null, { timeout: 20000 });
  await page.waitForTimeout(600);
};
const now = Math.floor(Date.now() / 1000);
const ask = (itemId, sid, name, column, text, t, extra) => Object.assign({ itemId, sid, name, color: cfg.colors[name], text, t, live: true,
  turnId: "turn-" + itemId.slice(-2), trgb: [30, 161, 235], column, tree: [] }, extra || {});
const asks = [];
for (let i = 0; i < 28; i++) asks.push(ask("cccccccc-1111-2222-3333-0000000000" + String(10 + i), cfg.web, "web", "working", "notes-api: working step " + (i + 1), now - 60 * (i + 1)));
asks.push(ask(cfg.webDone, cfg.web, "web", "completed", "notes-api: write the index schema", now - 900,
  { summary: "The index schema is written; every note carries its tags as a sorted list.", summaryAnchorUuid: cfg.webAnchor }));
asks.push(ask(cfg.apiDone, cfg.api, "api", "completed", "notes-api: wire the tag filter", now - 120,
  { summary: "The tag filter is wired end to end; the list endpoint accepts a tag and returns only matching notes.", summaryAnchorUuid: cfg.apiAnchor }));
asks.push(ask(cfg.apiSplit, cfg.api, "api", "completed", "notes-api: name the tag routes", now - 400,
  { summary: "The tag routes are named after the resource they filter.\n\nThe old query-string form still answers, with a deprecation header.",
    summaryAnchorUuid: cfg.apiAnchor, summaryAnchorsPara: [{ u: cfg.paraAnchors[0], q: "named after the resource" }, { u: cfg.paraAnchors[1], q: "deprecation header" }] }));
// two sibling asks of one typed turn: the board folds them into a GROUP card whose modal titles once posted at paint time
asks.push(ask(cfg.apiGrp1, cfg.api, "api", "working", "notes-api: list the tag routes", now - 200, { turnId: "turn-grp", groupTitle: "notes-api: the tag work" }));
asks.push(ask(cfg.apiGrp2, cfg.api, "api", "working", "notes-api: test the tag routes", now - 190, { turnId: "turn-grp", groupTitle: "notes-api: the tag work" }));
asks.push(ask(cfg.testsDone, cfg.tests, "tests", "completed", "notes-api: cover the tag filter", now - 3000,
  { live: false, summary: "The tag filter has a test per operator, and one for an unknown tag.", summaryAnchorUuid: cfg.testsAnchor }));
const payload = { type: "feed", asks, sessions: [{ sid: cfg.web, name: "web" }, { sid: cfg.api, name: "api" }, { sid: cfg.tests, name: "tests" }],
  order: [cfg.web, cfg.api, cfg.tests] };
const deliver = (m) => page.evaluate((m) => new Promise((res) => { window.dispatchEvent(new MessageEvent("message", { data: m })); requestAnimationFrame(() => res(null)); }), m);
const frame = () => page.evaluate(() => new Promise((res) => requestAnimationFrame(() => res(null))));
const park = async () => { await page.mouse.move(2, 2); await page.waitForTimeout(150); };
const state = () => page.evaluate(() => {
  const list = document.getElementById("feed-list"), sec = document.getElementById("feed-focus");
  const lr = list.getBoundingClientRect();
  const head = sec ? sec.querySelector(".feed-focus-cols .feed-col:not(.col-empty) .feed-col-head") : null;
  const hr = head ? head.getBoundingClientRect() : null;
  return { scrollTop: list.scrollTop, scrollHeight: list.scrollHeight, clientHeight: list.clientHeight,
           section: !!sec, name: sec ? (sec.querySelector(".feed-focus-head .fname") || {}).textContent || null : null,
           headInView: hr ? (hr.top >= lr.top - 0.5 && hr.bottom <= lr.bottom + 0.5) : null, headTop: hr ? hr.top - lr.top : null,
           hovered: !!document.querySelector(".fitem:hover"),
           posted: (window.__posted || []).filter((m) => m && m.type === "showOnTimeline").map((m) => m.sid),
           postedOpen: (window.__posted || []).filter((m) => m && m.type === "openSession").map((m) => m.id),
           modal: !!document.getElementById("feed-modal") };
});
const scrollList = (top) => page.evaluate((top) => { const l = document.getElementById("feed-list"); l.scrollTop = top; return l.scrollTop; }, top);
const light = async (on) => { await page.evaluate((on) => { document.body.classList[on ? "add" : "remove"]("chat-theme-yatharth", "theme-light"); }, on); await page.waitForTimeout(250); };
const shotBoth = async (name) => { if (!cfg.shots) return; await page.screenshot({ path: `${cfg.shots}-${name}-dark.png` }); await light(true); await page.screenshot({ path: `${cfg.shots}-${name}-light.png` }); await light(false); };
// a click dispatched on the element itself: Playwright's own click first scrolls an off-screen card into view, which would
// move the list before the handler runs and mask what the handler does to the scroll (the roads scroll the list 600 px down
// with the summary cards at the top of the board); the hover roads use the real pointer
const clickOn = async (sel) => { const ok = await page.evaluate((sel) => { const el = document.querySelector(sel); if (!el) return false; el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); return true; }, sel); if (!ok) throw new Error("no element for " + sel); await frame(); };
const clickSummary = (id) => clickOn(`#feed-cols [data-key="a:${id}"] .fask-distill`);
const toggleSection = async () => {
  await page.click("#feed-viewbtn");
  await page.waitForSelector(".feed-viewmenu .ctx-item", { timeout: 10000 });
  await page.locator(".feed-viewmenu .ctx-item", { hasText: "Show focused session" }).click();
  await page.waitForSelector(".feed-viewmenu", { state: "detached", timeout: 10000 });
  await park();
};
const kernel = async (sid, nonce) => { await deliver(Object.assign({ type: "activeChat", id: sid }, nonce == null ? {} : { nonce })); await frame(); };   // the kernel's relay frame, numbered when the chat numbered its announcement
const relay = async (sid, nonce, gesture) => { await deliver({ romp: "activeChat", id: sid, nonce, gesture: gesture !== false }); await frame(); };   // the shell's relay of the chat's tab change
const clickHeaderName = async (name) => { const ok = await page.evaluate((name) => { const el = Array.from(document.querySelectorAll(".feed-sess-head .fname")).find((n) => n.textContent === name); if (!el) return false; el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); return true; }, name); if (!ok) throw new Error("no session header named " + name); await frame(); };
const out = {};
await page.goto(cfg.feed);
await ready();
await deliver(payload);
await page.waitForSelector(`#feed-cols [data-key="a:${cfg.testsDone}"]`, { timeout: 10000 });
await park();
await toggleSection();   // the section on
await kernel(cfg.web); await park();
out.start = await state();
// (a) scrolled 600 px down, api's summary: the switch and the top at once; a stale frame flips nothing; the frame for api settles it
out.scrolledA = await scrollList(600);
await clickSummary(cfg.apiDone);
out.a1 = await state();
await kernel(cfg.web);   // built before the kernel took the switch: stale
out.a2 = await state();
await kernel(cfg.api);   // the echo
out.a3 = await state();
await park();
await shotBoth("1-row");
await kernel(cfg.web);   // no record pending: a real switch
out.a4 = await state();
// (k) a burst of three switches faster than the round trip, then the kernel's frames in order: the section stays on the last
await relay(cfg.api, 1); await relay(cfg.tests, 2); await relay(cfg.web, 3);
out.k0 = await state();
await kernel(cfg.api, 1);
out.k1 = await state();
await kernel(cfg.tests, 2);
out.k2 = await state();
await kernel(cfg.web, 3);
out.k3 = await state();
// …and a burst back to the same session: only the numbered echo settles the record
await relay(cfg.api, 4); await relay(cfg.web, 5); await relay(cfg.api, 6);
out.k4 = await state();
await kernel(cfg.api, 4);   // the same session, an earlier announcement: not the echo
out.k5 = await state();
await kernel(cfg.web, 5);   // a stale frame: yields (it would have landed had the frame before cleared the record)
out.k6 = await state();
await kernel(cfg.api, 6);   // the echo
out.k7 = await state();
await kernel(cfg.web, 7);   // nothing pending: a real switch
out.k8 = await state();
await park();
// (b) the reader scrolls after the jump, before the kernel's frame: the list stays where they put it
await scrollList(600);
await clickSummary(cfg.apiDone);
out.b0 = await state();
await park();
out.scrolledB = await scrollList(300);   // the reader's own scroll (clamped by the browser when api's section is shorter)
await frame();
await kernel(cfg.api);
out.b1 = await state();
// (c) api already focused: a summary click on its own card scrolls to the top at once
await scrollList(600);
await clickSummary(cfg.apiDone);
out.c = await state();
await park();
// (d) the section OFF: a 20-card board with room; the click and the frame move the list by nothing
await toggleSection();
await kernel(cfg.web);
out.scrolledD = await scrollList(400);
out.d0 = await state();
await clickSummary(cfg.apiDone);
await park();
out.d1 = await state();
await kernel(cfg.api);
out.d2 = await state();
// …and the section switched off before a jump, then on again: nothing moved
out.scrolledD2 = await scrollList(500);
await clickSummary(cfg.webDone);
await park();
await kernel(cfg.web);
await toggleSection();   // on again
out.d3 = await state();
// (e) a CLOSED session's summary: the click switches and scrolls nothing; the hand switch later scrolls nothing
out.scrolledE = await scrollList(600);
await clickSummary(cfg.testsDone);
await park();
out.e1 = await state();
await kernel(cfg.api);   // the hand switch, minutes later
out.e2 = await state();
// (f) the split summary's second paragraph: the one-place note covers it
await kernel(cfg.web); await park();
out.scrolledF = await scrollList(600);
await clickOn(`#feed-cols [data-key="a:${cfg.apiSplit}"] .fask-para-link:nth-of-type(2)`);
out.f = await state();
await park();
await kernel(cfg.api);
// (g) the shell's relay with the pointer resting on a board card: at once; the kernel's frame under the pointer waits
await kernel(cfg.web); await park();
await scrollList(0);
await page.hover(`#feed-cols [data-key="a:cccccccc-1111-2222-3333-000000000010"]`);
await page.waitForTimeout(120);
out.g0 = await state();
await relay(cfg.tests, 11, true);   // the reader's own switch in the chat
out.g1 = await state();
await kernel(cfg.tests, 11);        // the echo
out.g2 = await state();
await relay(cfg.api, 12, false);    // a kernel-driven switch (a focus frame, a re-activation) under the pointer: deferred
out.g3 = await state();
await kernel(cfg.api, 12);          // its echo: still deferred
out.g4 = await state();
await park();
out.g5 = await state();
// (h) a session name clicked in the feed: the section switches, the list stands
await kernel(cfg.web); await park();
out.scrolledH = await scrollList(600);
await clickHeaderName("api");
out.h = await state();
await park();
await kernel(cfg.api);
// (i) a grouped card's modal opened: the section and the scroll stand, through a later push too
await kernel(cfg.web); await park();
out.scrolledI = await scrollList(600);
await clickOn(`#feed-cols .fitem.fgroup[data-key="g:turn-grp"]`);
await page.waitForTimeout(450);   // the card's single-click opens the modal after its double-click debounce
out.i1 = await state();
await deliver(payload);   // a later push repaints the open modal
await frame();
out.i2 = await state();
await clickOn("#feed-modal");   // the backdrop closes it
await frame();
out.i3 = await state();
// (l) the frame first, then the relay, with a board card held: the relay's gesture paints the parked switch
await kernel(cfg.web); await park();
await scrollList(0);
await page.hover(`#feed-cols [data-key="a:cccccccc-1111-2222-3333-000000000010"]`);
await page.waitForTimeout(120);
await kernel(cfg.tests, 31);          // the kernel's frame lands first: parked under the held card
out.l1 = await state();
await relay(cfg.tests, 31, true);     // the shell's relay of the same switch, the reader's gesture
out.l2 = await state();
await park();
out.l3 = await state();
// (m) one throw inside render leaves no mark: the next Summary click still switches and scrolls
await kernel(cfg.web); await park();
out.scrolledM = await scrollList(600);
await page.evaluate(() => {
  const orig = document.getElementById.bind(document);
  document.getElementById = function (id) { if (id === "feed-foot") { document.getElementById = orig; throw new Error("lab: one-shot throw inside render"); } return orig(id); };
});
await deliver(payload);   // this push's render throws once, inside the body
await frame();
out.m0 = await state();
await clickSummary(cfg.apiDone);
out.m1 = await state();
await park();
await kernel(cfg.api);
// (n) the shell's revealCard for a card gone from the board, carrying the reader's gesture: the fallback's openSession switches at once
await kernel(cfg.web); await park();
out.scrolledN = await scrollList(600);
await deliver({ romp: "revealCard", itemId: "cccccccc-1111-2222-3333-0000000000ff", sid: cfg.api, gesture: true });
await frame();
out.n = await state();
await park();
await kernel(cfg.api);
// (o) a re-announce with a higher number settles the record: the next frame for another session is a real switch
await kernel(cfg.web); await park();
await relay(cfg.api, 40, true);
out.o1 = await state();
await kernel(cfg.api, 41);   // the chat re-announced after a socket flap: the same session, a new number
out.o2 = await state();
await kernel(cfg.web, 42);   // nothing pending any more: a real switch
out.o3 = await state();
await park();
// (j) single column: road (a)'s jump again
await page.setViewportSize({ width: 520, height: 760 });
await kernel(cfg.web); await park();
out.scrolledJ = await scrollList(600);
await clickSummary(cfg.apiDone);
out.j = await state();
await park();
await kernel(cfg.api);
await shotBoth("2-stacked");
out.errors = errors;
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
process.exit(0);
"""


def _clamped(want, st):
    return min(want, st["scrollHeight"] - st["clientHeight"])


class ServedFocusedSectionJumpScroll(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="feedfocusscroll-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise AssertionError("esbuild failed here: " + (b.stderr or b.stdout)[-400:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "session-hosts"), "w") as fh:   # a lab root of its own pins the hosts OFF (CLAUDE.md 2026-09-11)
            fh.write("off\n")
        cls.port = _free_port()
        cls.token = "testtok-feedfocusscroll"
        env = _lab.kernel_env(cls.lab, os.path.join(cls.lab, "claude"), dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(120):   # bounded: 60 s of half-second probes
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            cls.kernel.wait()
            raise AssertionError("hermetic kernel never served /healthz here; log tail:\n" + open(cls.klog).read()[-1500:])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def test_a_summary_click_switches_the_section_and_scrolls_the_feed_to_the_top_at_once(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"feed": "http://127.0.0.1:%d/feed?token=%s" % (self.port, self.token),
                       "web": SID_WEB, "api": SID_API, "tests": SID_TESTS, "webDone": WEB_DONE, "apiDone": API_DONE, "apiSplit": API_SPLIT,
                       "testsDone": TESTS_DONE, "apiGrp1": API_GRP1, "apiGrp2": API_GRP2, "apiAnchor": API_ANCHOR, "webAnchor": WEB_ANCHOR, "testsAnchor": TESTS_ANCHOR, "paraAnchors": PARA_ANCHORS,
                       "colors": {"web": {"bg": "#1EA1EB", "fg": "#ffffff"}, "api": {"bg": "#E0A526", "fg": "#000000"}, "tests": {"bg": "#7A5CFF", "fg": "#ffffff"}},
                       "out": os.path.join(self.lab, "result.json"),
                       "shots": os.environ.get("FEED_FOCUS_SCROLL_SHOTS", "")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:])
        out_path = os.path.join(self.lab, "result.json")
        self.assertTrue(os.path.exists(out_path), "driver wrote no result file:\n" + p.stdout[-3000:] + p.stderr[-3000:])
        with open(out_path) as fh:
            r = json.load(fh)
        # the roads' outcomes in one line each, for the record a base run leaves (pytest -s): a red assertion below stops
        # at the first road, the print shows every road's state
        summary = []
        for k in ("a1", "a2", "a3", "a4", "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "b0", "b1", "c", "d1", "d2", "d3", "e1", "e2", "f", "g1", "g3", "g4", "g5", "h", "i1", "i2", "i3", "l1", "l2", "l3", "m0", "m1", "n", "o1", "o2", "o3", "j"):
            st_ = r.get(k) or {}
            summary.append("%s: name=%s scrollTop=%s%s%s" % (k, st_.get("name"), st_.get("scrollTop"),
                                                          " hovered" if st_.get("hovered") else "", " modal" if st_.get("modal") else ""))
        print("\n" + "\n".join(summary))
        self.assertEqual(r.get("errors"), [], "the page threw nothing: %r" % r.get("errors"))
        st = r["start"]
        self.assertTrue(st["section"] and st["name"] == "web", "the section is on and web is focused: %r" % st)
        self.assertGreater(st["scrollHeight"], st["clientHeight"] + 600, "the world is tall enough for a 600 px scroll: %r" % st)
        # (a) the click itself: the section shows api, the list is at the top, the block head in view, the jump posted
        self.assertEqual(r["scrolledA"], 600, "the list was scrolled 600 px down")
        a1 = r["a1"]
        self.assertEqual((a1["name"], a1["scrollTop"], a1["headInView"], a1["posted"]), ("api", 0, True, [SID_API]),
                         "the click switches the section and scrolls to the top AT ONCE, before any frame: %r" % a1)
        self.assertEqual((r["a2"]["name"], r["a2"]["scrollTop"]), ("api", 0), "a frame for web built before the switch flips nothing: %r" % r["a2"])
        self.assertEqual((r["a3"]["name"], r["a3"]["scrollTop"]), ("api", 0), "the frame for api settles the record and changes nothing: %r" % r["a3"])
        self.assertEqual(r["a4"]["name"], "web", "with nothing pending a frame for web is a real switch: %r" % r["a4"])
        # (k) the burst: an event, never a count
        self.assertEqual([r[k]["name"] for k in ("k0", "k1", "k2", "k3")], ["web"] * 4,
                         "three switches faster than the round trip, then the kernel's three frames in order: the section stays on the last, never lands a stale one: %r" % [r[k]["name"] for k in ("k0", "k1", "k2", "k3")])
        self.assertEqual([r[k]["name"] for k in ("k4", "k5", "k6", "k7", "k8")], ["api", "api", "api", "api", "web"],
                         "a burst back to the same session: an earlier announcement's frame is no echo, the stale frame yields, the numbered echo settles, the next frame is a real switch: %r" % [r[k]["name"] for k in ("k4", "k5", "k6", "k7", "k8")])
        # (b) the reader scrolls after the jump: the frame lands and the list stays where they put it (clamped to api's shorter document)
        self.assertEqual((r["b0"]["name"], r["b0"]["scrollTop"]), ("api", 0), "the jump scrolled to the top: %r" % r["b0"])
        self.assertGreater(r["scrolledB"], 0, "the reader scrolled back down (the browser clamps 300 to the shorter document): %r" % r["scrolledB"])
        self.assertEqual(r["b1"]["scrollTop"], r["scrolledB"], "the kernel's frame moves nothing: the reader's scroll stands: %r" % r["b1"])
        # (c) the session already focused: the top at once
        self.assertEqual((r["c"]["name"], r["c"]["scrollTop"]), ("api", 0), "a summary click on the focused session's own card scrolls to the top at once: %r" % r["c"])
        # (d) the section off: a 20-card board with more than 900 px of room; nothing moves, no clamp in play
        d0, d1, d2 = r["d0"], r["d1"], r["d2"]
        self.assertFalse(d0["section"])
        self.assertGreaterEqual(d0["scrollHeight"] - d0["clientHeight"], 900, "the board alone leaves more than 900 px of room: %r" % d0)
        self.assertEqual(r["scrolledD"], 400)
        self.assertEqual((d1["section"], d1["scrollTop"]), (False, 400), "with the section off the click moves the list by nothing: %r" % d1)
        self.assertEqual((d2["section"], d2["scrollTop"]), (False, 400), "…and neither does the frame: %r" % d2)
        d3 = r["d3"]
        self.assertEqual(r["scrolledD2"], 500)
        self.assertEqual((d3["section"], d3["name"], d3["scrollTop"]), (True, "web", 500), "off before the jump, then on again: the list did not move: %r" % d3)
        # (e) a closed session's summary: the click switches and scrolls nothing; the hand switch later scrolls nothing
        e1, e2 = r["e1"], r["e2"]
        self.assertEqual(r["scrolledE"], 600)
        self.assertEqual(e1["posted"][-1], SID_TESTS, "the click posted the jump (the kernel answers the chat's confirmRevive): %r" % e1["posted"])
        self.assertEqual((e1["name"], e1["scrollTop"]), ("web", 600), "a closed session's jump moves nothing here: %r" % e1)
        self.assertEqual((e2["name"], e2["scrollTop"]), ("api", _clamped(600, e2)), "the hand switch shows api and scrolls nothing: %r" % e2)
        # (f) the split summary's paragraph: the one place every jump passes covers it
        f = r["f"]
        self.assertEqual(r["scrolledF"], 600)
        self.assertEqual((f["name"], f["scrollTop"], f["headInView"], f["posted"][-1]), ("api", 0, True, SID_API), "a paragraph's click switches and scrolls at once: %r" % f)
        # (g) the shell's relay through the hover-freeze; the kernel's frame still waits under the pointer
        self.assertTrue(r["g0"]["hovered"] and r["g0"]["name"] == "web", "the pointer rests on a board card: %r" % r["g0"])
        self.assertEqual((r["g1"]["hovered"], r["g1"]["name"]), (True, "tests"), "the reader's own switch, relayed by the shell, passes the hover-freeze: %r" % r["g1"])
        self.assertEqual(r["g2"]["name"], "tests", "the kernel's echo changes nothing: %r" % r["g2"])
        self.assertEqual((r["g3"]["hovered"], r["g3"]["name"]), (True, "tests"), "a kernel-driven switch relayed under the pointer waits for the release like a push (the round-two low): %r" % r["g3"])
        self.assertEqual((r["g4"]["hovered"], r["g4"]["name"]), (True, "tests"), "…and so does its echo: %r" % r["g4"])
        self.assertEqual((r["g5"]["hovered"], r["g5"]["name"]), (False, "api"), "…which paints on the release: %r" % r["g5"])
        # (h) a session name: the switch without the scroll
        h = r["h"]
        self.assertEqual(r["scrolledH"], 600)
        self.assertEqual((h["name"], h["scrollTop"], h["postedOpen"][-1]), ("api", _clamped(600, h), SID_API),
                         "a session name's openSession switches the section and scrolls nothing (the round-two low): %r" % h)
        # (i) the grouped modal: nothing moves at paint time
        i1, i2, i3 = r["i1"], r["i2"], r["i3"]
        self.assertEqual(r["scrolledI"], 600)
        self.assertTrue(i1["modal"], "the group card's modal opened: %r" % i1)
        self.assertEqual((i1["name"], i1["scrollTop"]), ("web", 600), "opening the modal switches and scrolls nothing (the round-two medium: its title once posted at paint time): %r" % i1)
        self.assertEqual((i2["name"], i2["scrollTop"]), ("web", 600), "…and a later push repainting the open modal moves nothing either: %r" % i2)
        self.assertEqual((i3["modal"], i3["name"], i3["scrollTop"]), (False, "web", 600), "the backdrop closes it, nothing moved: %r" % i3)
        self.assertNotIn(SID_API, i3["posted"][len(r["f"]["posted"]):], "no jump was posted by the modal's paint: %r" % i3["posted"][len(r["f"]["posted"]):])
        # (l) the frame first under a held card, then the relay: the gesture paints the parked switch
        self.assertEqual((r["l1"]["hovered"], r["l1"]["name"]), (True, "web"), "the kernel's frame under the held card parks the paint: %r" % r["l1"])
        self.assertEqual((r["l2"]["hovered"], r["l2"]["name"]), (True, "tests"), "the relay of the same switch is the reader's gesture: it paints now (the round-three medium): %r" % r["l2"])
        self.assertEqual(r["l3"]["name"], "tests", "…and the release changes nothing: %r" % r["l3"])
        # (m) a throw inside render leaves no mark
        self.assertEqual(r["scrolledM"], 600)
        self.assertEqual((r["m0"]["name"], r["m0"]["scrollTop"]), ("web", 600), "the throwing push moved nothing: %r" % r["m0"])
        self.assertEqual((r["m1"]["name"], r["m1"]["scrollTop"]), ("api", 0), "the next Summary click switches and scrolls: the mark did not stay set (the round-three medium): %r" % r["m1"])
        # (n) the shell's revealCard with the reader's gesture: the fallback's openSession switches at once, scrolls nothing
        n = r["n"]
        self.assertEqual(r["scrolledN"], 600)
        self.assertEqual((n["name"], n["scrollTop"], n["postedOpen"][-1]), ("api", _clamped(600, n), SID_API), "a gesture arriving through the shell's frame is honoured (a round-three low): %r" % n)
        # (o) the watermark: a re-announce with a higher number settles the record
        self.assertEqual([r[k]["name"] for k in ("o1", "o2", "o3")], ["api", "api", "web"],
                         "the chat's re-announce after a flap (a higher number, the same session) settles the record and the next frame is a real switch (a round-three low): %r" % [r[k]["name"] for k in ("o1", "o2", "o3")])
        # (j) single column
        self.assertEqual(r["scrolledJ"], 600)
        j = r["j"]
        self.assertEqual((j["name"], j["scrollTop"], j["headInView"]), ("api", 0, True), "single column: the same switch and scroll at once: %r" % j)


if __name__ == "__main__":
    unittest.main()
