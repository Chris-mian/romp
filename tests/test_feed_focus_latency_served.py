"""T416 (the user 2026-09-14, whose chat tab moved at once on a feed click while the feed's current-session section
took a long time to follow): THE SECTION FOLLOWS A TAB CHANGE AT ONCE, whatever surface the change came from.

Measured first on the served dashboard page (the shell with its chat and feed panes over a hermetic kernel), hop by
hop, from each of the switch's sources: a session name clicked in the feed (an openSession post), a card title
clicked in the feed (a showOnTimeline post), a tab clicked in the chat's strip, and a hot key in the chat (ArrowRight).
The hops are stamped on one clock across the frames (performance.timeOrigin + performance.now(), the same renderer):
the gesture, the feed's post, the chat's focus frame, the chat's activeTab post, the feed's activeChat frame, the
section head's name change, and the animation frame after it. The measurement at the merge base: the chat posts
within 3 ms of the gesture, the kernel relays within 4 to 22 ms of the post, the feed's rebuild takes 2 to 6 ms, and
a feed click's repaint waits for the pointer to LEAVE the clicked header or card (the hover-freeze parking the frame
as focusStale), 2.5 s in the lab and unbounded in use. The fix moves the section on the local signal: the feed's own
post (noted in the one place every jump passes) and the chat's tab change handed across the page by the shell; the
kernel's frame reconciles under a pending record.

Roads, on one landing page, in BOTH layouts (a wide viewport where the section's blocks sit in a row, a narrower one
where they stack):
  a. a session name clicked in the feed, the pointer left on the header (the natural gesture): the section repaints
     within one frame of the click, ahead of the kernel's frame, and the frame flips nothing back;
  b. the same click, the pointer leaving the header at once;
  c. a card title clicked in the feed (the timeline jump), the pointer left on the card: as (a);
  d. a tab clicked in the chat's strip: the shell's relay of the tab reaches the feed and the section repaints within
     two frames of the tab's own paint (the three panes share one main thread, so nothing paints before the chat's
     switch handler and its post-switch frame return: locally the kernel's frame and the relay land in the same idle
     gap; the relay's worth is a link the frame crosses slowly);
  e. ArrowRight in the chat (a hot key): as (d);
  d2, e2. the same two with the kernel's activeChat frames withheld from the feed's handler (a slow link stood in
     for): the shell's relay alone moves the section, within two frames of the tab's paint;
  f. a card of a CLOSED session (the kernel knows it dead) clicked: the feed's card says closed, so the section stays;
     the chat gets its confirmRevive prompt (dismissed);
  g. the same click on a card the feed still marks live (its word stale by a moment): the section moves on the click
     and comes back on the kernel's answer (the chat's re-announce through the shell, the kernel's marked reaffirm
     frame), so the chat and the section agree again without a hand switch.
Red first at the merge base on (a), (b), (c), (d), (e), (d2) and (e2) in both layouts ((d) and (e) on the relay's
arrival; their frame bound held at the base too); (f) and (g) guard the closed-session path. All
fixtures synthetic (the notes-api world: web, api, tests, and a closed `old`). Skips loudly without the extension deps
or a browser.
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
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_WEB = "aaaaaaaa-4160-2222-3333-777777777777"
SID_API = "aaaaaaaa-4160-2222-3333-888888888888"
SID_TESTS = "aaaaaaaa-4160-2222-3333-999999999999"
SID_OLD = "aaaaaaaa-4160-2222-3333-000000000000"
WEB_WORKING = "cccccccc-4160-2222-3333-000000000001"
WEB_DONE = "cccccccc-4160-2222-3333-000000000002"
API_WORKING = "cccccccc-4160-2222-3333-000000000011"
API_DONE = "cccccccc-4160-2222-3333-000000000012"
TESTS_WORKING = "cccccccc-4160-2222-3333-000000000021"
OLD_DONE = "cccccccc-4160-2222-3333-000000000031"
WEB_ANCHOR = "dddddddd-4160-2222-3333-000000000001"
API_ANCHOR = "dddddddd-4160-2222-3333-000000000002"
OLD_ANCHOR = "dddddddd-4160-2222-3333-000000000003"
FRAME_MS = 17.0   # one frame at 60 Hz, rounded up
# a tab change made in the chat: the feed's repaint queues behind the chat's own post-switch frame on the shared main
# thread (measured 8 to 19 ms after the tab's paint), so two frames is the bound there; the feed's own click paints in
# the click handler itself, within one
CHAT_SIDE_FRAMES = 2


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    """`pairs` CLOSED user/assistant turns for `sid` (an open turn would invite the boot reconcile to resume it)."""
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "11111111-2222-4333-8444-%02x00004a%04x" % (tag, i)
        a = "11111111-2222-4333-8444-%02x00004b%04x" % (tag, i)
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": sid, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep going with the notes-api search module (part %d)" % (i + 1)}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": sid, "cwd": cwd,
                    "message": {"id": "msg_lab_%d_%04d" % (tag, i), "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": "Note %d. The ranking pass reads its weights from the config now." % (i + 1)}],
                                "stop_reason": "end_turn"}})
        parent = a
    return "\n".join(json.dumps(r) for r in out) + "\n"


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); } catch (e) { fs.writeSync(2, "no browser: " + e + "\n"); process.exit(3); }
const out = { layouts: {}, errors: [] };
const finish = async () => { fs.writeFileSync(cfg.out, JSON.stringify(out)); await browser.close(); process.exit(0); };
const die = async (why) => { out.died = why; await finish(); };
process.on("unhandledRejection", async (e) => { await die("unhandled: " + String(e).split("\n")[0]); });

const runLayout = async (tag, width) => {
  const L = { roads: {}, tag, width };
  out.layouts[tag] = L;
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  page.on("pageerror", (e) => out.errors.push(tag + ": " + String(e)));
  // every frame: the hop clock (one clock across the frames), gesture capture, and the feed's section switched ON
  // before its first load (the view state's `focused`, the T347 switch)
  await page.addInitScript(() => {
    const abs = () => performance.timeOrigin + performance.now();
    const hops = (window.__hops = []);
    const tag = location.pathname;
    const note = (ev, extra) => hops.push(Object.assign({ f: tag, ev, t: abs() }, extra || {}));
    const S = WebSocket.prototype.send;
    WebSocket.prototype.send = function (d) {
      try { const m = JSON.parse(d); if (m && ["activeTab", "openSession", "showOnTimeline"].includes(m.type)) note("send:" + m.type, { id: m.id || m.sid || null }); } catch (e) {}
      return S.call(this, d);
    };
    const wrapIn = (fn) => function (ev) {
      try {
        const m = JSON.parse(ev.data);
        if (m && ["activeChat", "focus", "confirmRevive"].includes(m.type)) {
          if (m.type === "activeChat" && window.__dropActiveChat) { note("dropped:activeChat", { id: m.id || null }); return; }   // the socket's frame held back: a slow link
          note("recv:" + m.type, { id: m.id || null, reaffirm: !!m.reaffirm });
        }
      } catch (e) {}
      return fn.call(this, ev);
    };
    const AEL = WebSocket.prototype.addEventListener;
    WebSocket.prototype.addEventListener = function (type, fn, opts) { return AEL.call(this, type, type === "message" && typeof fn === "function" ? wrapIn(fn) : fn, opts); };
    const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, "onmessage");
    Object.defineProperty(WebSocket.prototype, "onmessage", { configurable: true, get() { return desc.get.call(this); },
      set(fn) { desc.set.call(this, typeof fn === "function" ? wrapIn(fn) : fn); } });
    document.addEventListener("click", (e) => note("click", { tgt: String((e.target && (e.target.className || e.target.tagName)) || "").slice(0, 40) }), true);
    window.addEventListener("message", (e) => { const d = e && e.data; if (d && typeof d.romp === "string" && (d.romp === "activeTab" || d.romp === "activeChat")) note("msg:" + d.romp, { id: d.id || null }); }, true);
    document.addEventListener("keydown", (e) => note("key", { key: e.key }), true);
    if (tag === "/feed" && !localStorage.getItem("romp:feedview")) localStorage.setItem("romp:feedview", JSON.stringify({ v: 1, focused: true }));
  });
  const T = 20000;
  const waitFn = async (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(tag + ": " + why + " (" + String(e).split("\n")[0] + ")"); });
  const waitTabs = (sids) => waitFn((sids) => {
    const f = document.getElementById("f-chat"); const d = f && f.contentDocument; if (!d) return false;
    const ids = Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id);
    return sids.every((s) => ids.includes(s));
  }, sids, "the chat never showed the tabs");
  const waitActive = (sid) => waitFn((sid) => {
    const f = document.getElementById("f-chat"); const d = f && f.contentDocument;
    const t = d && d.querySelector("#tabs .tab.active[data-id]"); return !!t && t.dataset.id === sid;
  }, sid, "the chat never activated " + sid);
  const chatFrame = async () => (await page.$("#f-chat")).contentFrame();
  const feedFrame = async () => (await page.$("#f-feed")).contentFrame();
  const clickTab = async (sid) => { const fr = await chatFrame(); await fr.locator('#tabs .tab[data-id="' + sid + '"]').first().click(); };
  const rectIn = (fid, sel) => page.evaluate(([fid, sel]) => {
    const f = document.getElementById(fid); const fr = f.getBoundingClientRect(); const el = f.contentDocument.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect(); return { x: fr.left + r.left, y: fr.top + r.top, w: r.width, h: r.height };
  }, [fid, sel]);
  const clickIn = async (fid, sel) => { const r = await rectIn(fid, sel); if (!r) await die("no " + sel + " in " + fid); await page.mouse.click(r.x + r.w / 2, r.y + Math.min(r.h / 2, 120)); };
  const headName = () => page.evaluate(() => { const f = document.getElementById("f-feed"); const d = f && f.contentDocument; const n = d && d.querySelector("#feed-focus .feed-focus-head .fname"); return n ? n.textContent : null; });
  const waitHead = (name, ms) => page.waitForFunction((name) => { const f = document.getElementById("f-feed"); const d = f && f.contentDocument; const n = d && d.querySelector("#feed-focus .feed-focus-head .fname"); return !!n && n.textContent === name; }, name, { timeout: ms }).then(() => true).catch(() => false);
  const clock = () => page.evaluate(() => performance.timeOrigin + performance.now());
  const hopsAll = () => page.evaluate(() => {
    const g = (id) => { const f = document.getElementById(id); return f && f.contentWindow && f.contentWindow.__hops ? f.contentWindow.__hops.slice() : []; };
    return [].concat(window.__hops || [], g("f-chat"), g("f-feed")).sort((a, b) => a.t - b.t);
  });
  const clearHops = () => page.evaluate(() => { for (const w of [window, document.getElementById("f-chat").contentWindow, document.getElementById("f-feed").contentWindow]) if (w && w.__hops) w.__hops.length = 0; });
  // the section head's name change, and the animation frame after it, stamped from inside the feed frame
  const observeHead = () => page.evaluate(() => {
    const w = document.getElementById("f-feed").contentWindow, d = w.document;
    const abs = () => w.performance.timeOrigin + w.performance.now();
    const read = () => { const n = d.querySelector("#feed-focus .feed-focus-head .fname"); return n ? n.textContent : null; };
    let last = read();
    new w.MutationObserver(() => {
      const nm = read();
      if (nm === last) return;
      last = nm;
      w.__hops.push({ f: "/feed", ev: "head", name: nm, t: abs() });
      w.requestAnimationFrame(() => w.__hops.push({ f: "/feed", ev: "head-frame", name: nm, t: abs() }));
    }).observe(d.body, { subtree: true, childList: true, characterData: true });
    return last;
  });
  // the chat's tab paint: the active tab's id changing on the strip, and the animation frame after it, from inside the chat frame
  const observeTabs = () => page.evaluate(() => {
    const w = document.getElementById("f-chat").contentWindow, d = w.document;
    const abs = () => w.performance.timeOrigin + w.performance.now();
    const read = () => { const t = d.querySelector("#tabs .tab.active[data-id]"); return t ? t.dataset.id : null; };
    let last = read();
    new w.MutationObserver(() => {
      const id = read();
      if (id === last) return;
      last = id;
      w.__hops.push({ f: "/chat", ev: "tab", id, t: abs() });
      w.requestAnimationFrame(() => w.__hops.push({ f: "/chat", ev: "tab-frame", id, t: abs() }));
    }).observe(d.getElementById("tabs") || d.body, { subtree: true, attributes: true, attributeFilter: ["class"], childList: true });
    return last;
  });
  const setDrop = (on) => page.evaluate((on) => { document.getElementById("f-feed").contentWindow.__dropActiveChat = on; }, on);
  // the section's block layout: a row (the visible blocks side by side) or stacked (the container query's column direction)
  const layout = () => page.evaluate(() => {
    const f = document.getElementById("f-feed"); const d = f.contentDocument;
    const blocks = Array.from(d.querySelectorAll("#feed-focus .feed-focus-cols .feed-col")).filter((c) => { const r = c.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    const lefts = blocks.map((c) => Math.round(c.getBoundingClientRect().left));
    const all = Array.from(d.querySelectorAll("#feed-focus .feed-focus-cols .feed-col")).map((c) => { const r = c.getBoundingClientRect(); return { cls: c.className, w: Math.round(r.width), h: Math.round(r.height), l: Math.round(r.left), t: Math.round(r.top), cards: c.querySelectorAll(".fitem").length }; });
    const cols = d.querySelector("#feed-focus .feed-focus-cols");
    const dir = cols ? getComputedStyle(cols).flexDirection : null;   // the stacked container query turns the row into a column
    const keys = (root) => root ? Array.from(root.querySelectorAll(".fitem[data-key]")).map((c) => c.dataset.key) : [];
    return { feedW: f.getBoundingClientRect().width, blocks: blocks.length, lefts, all, dir, stacked: dir === "column",
             secKeys: keys(d.getElementById("feed-focus")), boardKeys: keys(d.getElementById("feed-cols")).length };
  });
  // the synthetic board, delivered on the feed frame's own message path (the shim dispatches a socket frame the same way)
  const now = Math.floor(Date.now() / 1000);
  const ask = (itemId, sid, name, column, text, t, extra) => Object.assign({ itemId, sid, name, color: { bg: "#3a86ff", fg: "#ffffff" }, text, t, live: true,
    turnId: "turn-" + itemId.slice(-2), trgb: [30, 161, 235], column, tree: [] }, extra || {});
  const payloadOf = (oldLive) => ({ type: "feed", asks: [
      ask(cfg.webWorking, cfg.web, "web", "working", "notes-api: draft the search index", now - 60),
      ask(cfg.webDone, cfg.web, "web", "completed", "notes-api: write the index schema", now - 240, { summary: "The index schema is written; every note carries its tags as a sorted list.", summaryAnchorUuid: cfg.webAnchor }),
      ask(cfg.apiWorking, cfg.api, "api", "working", "notes-api: wire the tag filter", now - 120),
      ask(cfg.apiDone, cfg.api, "api", "completed", "notes-api: name the tag routes", now - 400, { summary: "The tag routes are named after the resource they filter.", summaryAnchorUuid: cfg.apiAnchor }),
      ask(cfg.testsWorking, cfg.tests, "tests", "working", "notes-api: cover the tag filter", now - 30),
      ask(cfg.oldDone, cfg.old, "old", "completed", "notes-api: the first index prototype", now - 9000, { live: oldLive, summary: "The first prototype indexed titles only.", summaryAnchorUuid: cfg.oldAnchor })],
    sessions: [{ sid: cfg.web, name: "web" }, { sid: cfg.api, name: "api" }, { sid: cfg.tests, name: "tests" }, { sid: cfg.old, name: "old" }],
    order: [cfg.web, cfg.api, cfg.tests, cfg.old] });
  const deliver = (m) => page.evaluate((m) => new Promise((res) => {
    const w = document.getElementById("f-feed").contentWindow;
    w.dispatchEvent(new w.MessageEvent("message", { data: m }));
    w.requestAnimationFrame(() => res(null));
  }), m);
  const park = async () => { await page.mouse.move(2, 2); await page.waitForTimeout(150); };
  const feedCard = (itemId) => '.fitem[data-key="a:' + itemId + '"]';
  // the reader's "session name in the feed": the session header's name
  const clickName = async (name) => { const fr = await feedFrame(); await fr.locator(".feed-sess-head .fname", { hasText: name }).first().click({ timeout: 8000 }); };
  const clickTitle = async (itemId) => { const fr = await feedFrame(); await fr.locator(feedCard(itemId) + " .fcard-title").first().click({ timeout: 8000 }); };
  // after a switch: the kernel's frame for `sid` has landed (or 3 s passed), then a beat; what the head says then
  const settled = async (sid) => {
    await page.waitForFunction((sid) => (document.getElementById("f-feed").contentWindow.__hops || []).some((h) => h.ev === "recv:activeChat" && h.id === sid), sid, { timeout: 3000 }).catch(() => null);
    await page.waitForTimeout(200);
    return headName();
  };
  const confirmShown = () => page.evaluate(() => { const d = document.getElementById("f-chat").contentDocument; const o = d && d.querySelector(".picker-overlay"); return o ? (o.textContent || "").slice(0, 120) : null; });
  const dismissConfirm = async () => {
    const fr = await chatFrame();
    await fr.getByRole("button", { name: "Cancel" }).first().click({ timeout: 8000 });
    await waitFn(() => { const d = document.getElementById("f-chat").contentDocument; return !(d && d.querySelector(".picker-overlay")); }, null, "the confirm never closed");
  };

  // ---- load: every live session a tab in the chat, the feed pane up with its section on ----
  await page.goto(cfg.url);
  await waitTabs([cfg.web, cfg.api, cfg.tests]);
  await waitFn(() => { const f = document.getElementById("f-feed"); const d = f && f.contentDocument; return !!(d && d.getElementById("feed-list") && f.contentWindow.acquireVsCodeApi); }, null, "the feed pane never loaded");
  await page.waitForTimeout(800);   // the feed's first payload and the activeChat frame of its ready
  await deliver(payloadOf(false));
  await waitFn((sel) => { const f = document.getElementById("f-feed"); const d = f && f.contentDocument; return !!(d && d.querySelector(sel)); }, feedCard(cfg.oldDone), "the board never showed the injected cards");
  L.sectionAtBoot = await page.evaluate(() => !!document.getElementById("f-feed").contentDocument.getElementById("feed-focus"));
  if (!L.sectionAtBoot) await die("the section is not on (the seeded view state did not take)");
  L.oldTab = await page.evaluate((old) => !!document.getElementById("f-chat").contentDocument.querySelector('#tabs .tab[data-id="' + old + '"]'), cfg.old);
  await clickTab(cfg.web); await waitActive(cfg.web); await park();
  L.headAfterBoot = await waitHead("web", 5000);
  L.headAtStart = await observeHead();
  L.tabAtStart = await observeTabs();
  L.layout = await layout();

  const road = async (key, run) => { await clearHops(); const r = await run(); r.hops = await hopsAll(); L.roads[key] = r; };
  // the section on `sid` through a real tab change: by way of another tab first when the chat already shows `sid` (after a
  // road whose section did not follow, at the merge base), so a kernel frame for `sid` always comes
  const settle = async (sid, name) => {
    const other = sid === cfg.api ? cfg.tests : cfg.api;
    await clickTab(other); await waitActive(other);
    await clickTab(sid); await waitActive(sid); await park();
    if (!(await waitHead(name, 5000))) await die("the section never settled on " + name);
    await deliver(payloadOf(false)); await park(); await clearHops();
  };

  // a. a session name clicked in the feed; the pointer stays on the header, as a click leaves it
  await settle(cfg.web, "web");
  await road("a_feed_name_pointer_stays", async () => {
    await clickName("api");
    const within = await waitHead("api", 2500);
    const tMove = await clock();
    const settledName = await settled(cfg.api);
    await page.mouse.move(2, 2);
    const afterLeave = await waitHead("api", 5000);
    return { within, tMove, settled: settledName, afterLeave, headNow: await headName() };
  });
  // b. the same click, the pointer leaving the header at once
  await settle(cfg.web, "web");
  await road("b_feed_name_pointer_leaves", async () => {
    await clickName("api");
    await page.mouse.move(2, 2);
    const within = await waitHead("api", 5000);
    return { within, settled: await settled(cfg.api), headNow: await headName() };
  });
  // c. a card title clicked in the feed (the timeline jump: showOnTimeline), the pointer left on the card
  await settle(cfg.web, "web");
  await road("c_feed_title_pointer_stays", async () => {
    await clickTitle(cfg.apiDone);
    const within = await waitHead("api", 2500);
    const tMove = await clock();
    const settledName = await settled(cfg.api);
    await page.mouse.move(2, 2);
    const afterLeave = await waitHead("api", 5000);
    return { within, tMove, settled: settledName, afterLeave, headNow: await headName() };
  });
  // d. a tab clicked in the chat's strip
  await settle(cfg.api, "api");
  await road("d_strip_click", async () => {
    await clickTab(cfg.web);
    const within = await waitHead("web", 5000);
    return { within, settled: await settled(cfg.web), headNow: await headName() };
  });
  // e. a hot key in the chat: ArrowRight steps to the next tab
  await settle(cfg.web, "web");
  await clickIn("f-chat", "#content");
  await page.waitForTimeout(200);
  await clearHops();
  await road("e_hot_key", async () => {
    const before = await headName();
    await page.keyboard.press("ArrowRight");
    const within = await page.waitForFunction((before) => { const d = document.getElementById("f-feed").contentDocument; const n = d && d.querySelector("#feed-focus .feed-focus-head .fname"); return !!n && n.textContent !== before; }, before, { timeout: 5000 }).then(() => true).catch(() => false);
    const to = await page.evaluate(() => { const d = document.getElementById("f-chat").contentDocument; const t = d.querySelector("#tabs .tab.active[data-id]"); return t ? t.dataset.id : null; });
    return { within, before, to, settled: await settled(to), headNow: await headName() };
  });
  // d2/e2. the same two with the kernel's activeChat frames withheld from the feed (a slow link): the shell's relay alone
  await settle(cfg.api, "api");
  await setDrop(true);
  await road("d2_strip_click_frame_withheld", async () => {
    await clickTab(cfg.web);
    const within = await waitHead("web", 1500);
    await page.waitForTimeout(300);
    return { within, headNow: await headName() };
  });
  await setDrop(false);
  await settle(cfg.web, "web");
  await clickIn("f-chat", "#content");
  await page.waitForTimeout(200);
  await setDrop(true);
  await clearHops();
  await road("e2_hot_key_frame_withheld", async () => {
    const before = await headName();
    await page.keyboard.press("ArrowRight");
    const within = await page.waitForFunction((before) => { const d = document.getElementById("f-feed").contentDocument; const n = d && d.querySelector("#feed-focus .feed-focus-head .fname"); return !!n && n.textContent !== before; }, before, { timeout: 1500 }).then(() => true).catch(() => false);
    const to = await page.evaluate(() => { const d = document.getElementById("f-chat").contentDocument; const t = d.querySelector("#tabs .tab.active[data-id]"); return t ? t.dataset.id : null; });
    await page.waitForTimeout(300);
    return { within, before, to, headNow: await headName() };
  });
  await setDrop(false);
  // f. a closed session's card, the feed's card saying closed: the section stays; the chat gets its confirmRevive
  await settle(cfg.web, "web");
  await road("f_closed_card_says_closed", async () => {
    await clickTitle(cfg.oldDone);
    const moved = await waitHead("old", 800);
    await waitFn(() => !!document.getElementById("f-chat").contentDocument.querySelector(".picker-overlay"), null, "the chat never showed the confirmRevive prompt");
    const confirm = await confirmShown();
    await page.mouse.move(2, 2);
    await page.waitForTimeout(300);
    const r = { moved, confirm, headNow: await headName() };
    await dismissConfirm();
    return r;
  });
  // g. the same card while the feed still marks it live (stale by a moment): the section moves on the click and comes back on the kernel's answer
  await settle(cfg.web, "web");
  await deliver(payloadOf(true)); await park(); await clearHops();
  await road("g_closed_card_marked_live", async () => {
    await clickTitle(cfg.oldDone);
    const moved = await waitHead("old", 800);
    const back = await waitHead("web", 3000);
    await waitFn(() => !!document.getElementById("f-chat").contentDocument.querySelector(".picker-overlay"), null, "the chat never showed the confirmRevive prompt");
    await page.mouse.move(2, 2);
    await page.waitForTimeout(300);
    const r = { moved, back, headNow: await headName() };
    await dismissConfirm();
    return r;
  });
  await deliver(payloadOf(false));
  await page.close();
};

await runLayout("row", cfg.rowWidth);
await runLayout("stacked", cfg.stackedWidth);
await finish();
"""


def _legs(hops):
    """The hop times relative to the gesture (ms), in order: the first click/key is the gesture."""
    g = next((h for h in hops if h["ev"] in ("click", "key")), None)
    if not g:
        return []
    return [(h["f"], h["ev"], h.get("id") or h.get("name") or h.get("key") or "", round(h["t"] - g["t"], 1), h.get("reaffirm")) for h in hops]


def _t(road, ev, **match):
    for h in road["hops"]:
        if h["ev"] == ev and all(h.get(k) == v for k, v in match.items()):
            return h["t"]
    return None


class FeedFocusLatencyServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="feedlat-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        os.makedirs(os.path.join(state, "names"), exist_ok=True)
        os.makedirs(os.path.join(state, "sdk"), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        with open(os.path.join(state, "session-hosts"), "w") as fh:   # a lab root of its own pins the hosts OFF (CLAUDE.md 2026-09-11)
            fh.write("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        # three synthetic live SDK sessions so the chat page has three tabs, and a CLOSED one (a name and a transcript, no
        # live record) for the confirmRevive roads; closed turns only, so nothing is ever resumed
        for sid, name, tag, live in [(SID_WEB, "web", 1, True), (SID_API, "api", 2, True), (SID_TESTS, "tests", 3, True), (SID_OLD, "old", 4, False)]:
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            if live:
                Path(state, "sdk", sid + ".json").write_text(json.dumps(
                    {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
            Path(proj, sid + ".jsonl").write_text(_transcript(sid, tag, cwd, 6))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        cls.port = _free_port()
        cls.token = "testtok-feedlat"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")],
                                      stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            raise unittest.SkipTest("hermetic kernel never served /healthz here")
        cls.result, cls.driver_error = None, None
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        res = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "out": res,
                       "web": SID_WEB, "api": SID_API, "tests": SID_TESTS, "old": SID_OLD,
                       "webWorking": WEB_WORKING, "webDone": WEB_DONE, "apiWorking": API_WORKING, "apiDone": API_DONE,
                       "testsWorking": TESTS_WORKING, "oldDone": OLD_DONE, "webAnchor": WEB_ANCHOR, "apiAnchor": API_ANCHOR, "oldAnchor": OLD_ANCHOR,
                       "rowWidth": 2600, "stackedWidth": 1250}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served leg needs one (CI installs none)")
        if p.returncode != 0 or not os.path.exists(res):
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        with open(res) as f:
            r = json.load(f)
        keep = os.environ.get("ROMP_T416_RESULT")
        if keep:
            shutil.copy(res, keep)
        if "died" in r:
            cls.driver_error = "driver aborted early: %s\n%s" % (r["died"], json.dumps(r, indent=1)[-3000:])
            return
        cls.result = r

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def setUp(self):
        if self.driver_error:
            self.fail(self.driver_error)

    def test_0_measurement(self):
        """The hop table, printed for the record (pytest -s); the assertions ride the roads below."""
        r = self.result
        lines = [""]
        for tag, L in r["layouts"].items():
            lines.append("== layout %s (viewport %d): feed pane %s px, %s; headAfterBoot=%r headAtStart=%r oldTab=%r" % (
                tag, L["width"], L["layout"]["feedW"], "stacked" if L["layout"]["stacked"] else "row", L.get("headAfterBoot"), L.get("headAtStart"), L.get("oldTab")))
            for key, road in L["roads"].items():
                lines.append("-- %s: within=%r settled=%r afterLeave=%r headNow=%r" % (key, road.get("within"), road.get("settled"), road.get("afterLeave"), road.get("headNow")))
                g = next((h for h in road["hops"] if h["ev"] in ("click", "key")), None)
                for f, ev, ident, dt, re_ in _legs(road["hops"]):
                    lines.append("   %+9.1f ms  %-6s %-18s %s%s" % (dt, f, ev, ident[-12:], " (reaffirm)" if re_ else ""))
                if g and road.get("tMove"):
                    lines.append("   %+9.1f ms  (pointer moved off the card)" % (road["tMove"] - g["t"]))
        print("\n".join(lines))
        self.assertEqual(r.get("errors"), [], "the pages threw nothing: %r" % r.get("errors"))

    def _layouts(self):
        r = self.result
        row, stacked = r["layouts"]["row"], r["layouts"]["stacked"]
        self.assertFalse(row["layout"]["stacked"], "the wide viewport lays the section's blocks in a row: %r" % row["layout"])
        self.assertTrue(stacked["layout"]["stacked"], "the narrower viewport stacks them: %r" % stacked["layout"])
        return [("row", row), ("stacked", stacked)]

    def _local(self, tag, key, road, target, gesture_ev, sent_id=None):
        """The section repainted to `target` within one frame of the tab change and AHEAD of the kernel's frame; the frame
        flipped nothing back. The tab change is the gesture for a feed-side source (the section moves on the click), and
        the chat's activeTab post for a chat-side one (the strip, a hot key)."""
        legs = "\n".join("%+9.1f ms %s %s %s%s" % (dt, f, ev, ident, " reaffirm" if re_ else "") for f, ev, ident, dt, re_ in _legs(road["hops"]))
        head = _t(road, "head", name=target)
        self.assertIsNotNone(head, "%s/%s: the section never repainted to %s while the pointer stayed put:\n%s" % (tag, key, target, legs))
        ref = _t(road, gesture_ev) if sent_id is None else _t(road, "send:activeTab", id=sent_id)
        self.assertIsNotNone(ref, "%s/%s: no %s hop:\n%s" % (tag, key, gesture_ev if sent_id is None else "activeTab post", legs))
        self.assertLessEqual(head - ref, FRAME_MS, "%s/%s: the repaint came %.1f ms after the tab change, more than one frame:\n%s" % (tag, key, head - ref, legs))
        recvs = [h["t"] for h in road["hops"] if h["ev"] == "recv:activeChat" and h["f"] == "/feed"]
        self.assertTrue(recvs, "%s/%s: the kernel's frame never arrived:\n%s" % (tag, key, legs))
        self.assertLess(head, min(recvs), "%s/%s: the section moved on the kernel's frame, not on the local signal:\n%s" % (tag, key, legs))
        self.assertEqual(road["settled"], target, "%s/%s: the kernel's frame flipped the section back: %r" % (tag, key, road["settled"]))

    def test_1_a_session_name_clicked_in_the_feed_moves_the_section_at_once_with_the_pointer_left_on_the_header(self):
        for tag, L in self._layouts():
            road = L["roads"]["a_feed_name_pointer_stays"]
            self.assertTrue(road["within"], "%s: the section repainted while the pointer stayed on the clicked header (it used to wait for the pointer to leave):\n%s" % (tag, _legs(road["hops"])))
            self._local(tag, "a", road, "api", "click")
            b = L["roads"]["b_feed_name_pointer_leaves"]
            self._local(tag, "b", b, "api", "click")

    def test_2_a_card_title_clicked_in_the_feed_moves_the_section_at_once_with_the_pointer_left_on_the_card(self):
        for tag, L in self._layouts():
            road = L["roads"]["c_feed_title_pointer_stays"]
            self.assertTrue(road["within"], "%s: the section repainted while the pointer stayed on the clicked card:\n%s" % (tag, _legs(road["hops"])))
            self._local(tag, "c", road, "api", "click")

    def _chat_side(self, tag, key, road, target, sid, withheld=False):
        """A tab change made in the chat: the shell's relay reached the feed with the new tab, and the section repainted within
        CHAT_SIDE_FRAMES of the tab's own paint. The three panes share one main thread, so nothing paints before the chat's
        switch handler and its post-switch frame return; the relay's worth is a link the kernel's frame crosses slowly,
        which `withheld` stands in for (the frame never reaches the feed's handler and the section must still follow)."""
        legs = "\n".join("%+9.1f ms %s %s %s%s" % (dt, f, ev, ident, " reaffirm" if re_ else "") for f, ev, ident, dt, re_ in _legs(road["hops"]))
        head = _t(road, "head", name=target)
        self.assertIsNotNone(head, "%s/%s: the section never repainted to %s:\n%s" % (tag, key, target, legs))
        self.assertIsNotNone(_t(road, "msg:activeChat", id=sid), "%s/%s: the shell's relay of the chat's tab never reached the feed:\n%s" % (tag, key, legs))
        paint = _t(road, "tab-frame", id=sid) or _t(road, "tab", id=sid)
        self.assertIsNotNone(paint, "%s/%s: the chat's strip never showed the new tab:\n%s" % (tag, key, legs))
        self.assertLessEqual(head - paint, FRAME_MS * CHAT_SIDE_FRAMES, "%s/%s: the section repainted %.1f ms after the tab's paint, more than %d frames:\n%s" % (tag, key, head - paint, CHAT_SIDE_FRAMES, legs))
        if withheld:
            self.assertIsNotNone(_t(road, "dropped:activeChat", id=sid), "%s/%s: the kernel's frame was withheld as the road meant:\n%s" % (tag, key, legs))
            self.assertIsNone(_t(road, "recv:activeChat", id=sid), "%s/%s: no kernel frame for the new tab reached the feed's handler:\n%s" % (tag, key, legs))
        else:
            self.assertEqual(road["settled"], target, "%s/%s: the kernel's frame flipped the section back: %r" % (tag, key, road["settled"]))

    def test_3_a_strip_click_and_a_hot_key_in_the_chat_move_the_section_within_one_frame_of_the_tab_change(self):
        for tag, L in self._layouts():
            d = L["roads"]["d_strip_click"]
            self._chat_side(tag, "d", d, "web", SID_WEB)
            e = L["roads"]["e_hot_key"]
            self.assertTrue(e["to"] and e["to"] != SID_WEB, "%s: ArrowRight stepped to another tab: %r" % (tag, e["to"]))
            self._chat_side(tag, "e", e, e["headNow"], e["to"])

    def test_3b_with_the_kernels_frame_withheld_the_shells_relay_alone_moves_the_section(self):
        for tag, L in self._layouts():
            d = L["roads"]["d2_strip_click_frame_withheld"]
            self.assertTrue(d["within"], "%s: the section followed the strip click with no kernel frame: %r" % (tag, d["headNow"]))
            self._chat_side(tag, "d2", d, "web", SID_WEB, withheld=True)
            e = L["roads"]["e2_hot_key_frame_withheld"]
            self.assertTrue(e["within"] and e["to"], "%s: the section followed the hot key with no kernel frame: %r" % (tag, e))
            self._chat_side(tag, "e2", e, e["headNow"], e["to"], withheld=True)

    def test_4_a_closed_sessions_card_switches_nothing_and_a_stale_live_mark_comes_back_on_the_kernels_answer(self):
        for tag, L in self._layouts():
            self.assertFalse(L["oldTab"], "%s: the closed session has no tab" % tag)
            f = L["roads"]["f_closed_card_says_closed"]
            self.assertEqual((f["moved"], f["headNow"]), (False, "web"), "%s: a card the feed knows closed moves the section by nothing: %r" % (tag, f))
            self.assertIn("closed", f["confirm"] or "", "%s: the chat got its confirmRevive prompt: %r" % (tag, f["confirm"]))
            self.assertIsNone(_t(f, "recv:activeChat", id=SID_OLD), "%s: no frame for the closed session" % tag)
            g = L["roads"]["g_closed_card_marked_live"]
            self.assertEqual((g["moved"], g["back"], g["headNow"]), (True, True, "web"),
                             "%s: a card still marked live moves the section on the click and the kernel's answer brings it back: %r" % (tag, g))
            self.assertTrue(any(h["ev"] == "recv:activeChat" and h.get("reaffirm") and h["id"] == SID_WEB for h in g["hops"]),
                            "%s: the kernel's marked reaffirm frame for the standing session arrived:\n%s" % (tag, _legs(g["hops"])))


if __name__ == "__main__":
    unittest.main()
