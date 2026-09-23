#!/usr/bin/env python3
"""A send, its landing and the reply that follows APPEND to the chat's tail; nothing above the tail is rebuilt (2026-09-23).

On a long transcript the page holds only the kernel's tail, so the view's unit list starts with a gap unit for the turns it has
not loaded (the history regions, T386 stage 2), under a top spacer. Two defects lived there. The exact tail path trimmed and
tagged its nodes by EVENT index while the window build tags them by UNIT index, which the gap shifts by one, so the first
tail frame after a window build removed the node just above the changed point and never put it back: the landed message went
at the first frame of the reply, the previous reply blinked out at the send's first frame, and each came back only when a
later send rebuilt the window. And every send and every landing rebuilt the whole window (a stale mark where only the tail
changed), replacing every unit and re-estimating the top spacer, which moved the reader and the scroll height by tens of
thousands of pixels on a long transcript.

The lab: the real /chat page against a hermetic kernel whose one session holds a transcript longer than the kernel's tail (so
the page opens on a top spacer over a gap) and is MID-TURN, so the composer's send is queued by the kernel. The page is the
SENDER. It sends; the transcript then lands the message; then the reply arrives record by record, each its own tail frame.
Two cycles: a reader following the tail, and a reader scrolled up into the rendered window. At every step, and in every
mutation batch on the view between steps:
  1. the landed message's element never leaves the DOM once painted;
  2. no batch touches the top spacer or removes a node that was painted before the send (the tail's new units only);
  3. the top spacer's height and the position of every node painted before the send do not change, so the scroll height
     changes only by what the tail added;
  4. a reader following the tail is at the bottom after every step, a reader scrolled up stays exactly where they were, and
     the page files no scroll it did not write (`scrollgesture`).
SYNTHETIC fixtures only (a notes-api session named web); skips loudly without the extension deps or a Playwright browser.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_send_bubble_visible_browser as _sb    # noqa: E402  the hermetic kernel and its helpers (the module, never its classes)

SID = _sb.SID
EXCHANGES = 150          # 300 events and the open turn: past the kernel's 250-event tail, so the page holds a gap under a top spacer
LANDED = ["11111111-2222-3333-4444-000000000a01", "11111111-2222-3333-4444-000000000b01"]
DRIVER_TIMEOUT_S = 300


def _records(t0):
    """EXCHANGES answered asks, then an open turn: a prompt and a tool call whose result is still out (a send is queued)."""
    recs, parent = [], None
    for i in range(EXCHANGES):
        u, a = "u%03d" % i, "a%03d" % i
        recs.append({"type": "user", "timestamp": _sb.iso(t0 + i * 8), "uuid": u, "parentUuid": parent, "promptSource": "sdk",
                     "sessionId": SID, "message": {"role": "user", "content": "notes-api ask %d: tighten the search ranking" % i}})
        recs.append({"type": "assistant", "timestamp": _sb.iso(t0 + i * 8 + 4), "uuid": a, "parentUuid": u, "sessionId": SID,
                     "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "\n\n".join("Paragraph %d of reply %d." % (k, i) for k in range(3))}]}})
        parent = a
    t = t0 + EXCHANGES * 8
    recs.append({"type": "user", "timestamp": _sb.iso(t), "uuid": "uopen", "parentUuid": parent, "promptSource": "sdk", "sessionId": SID,
                 "message": {"role": "user", "content": "run the notes-api search tests"}})
    recs.append({"type": "assistant", "timestamp": _sb.iso(t + 2), "uuid": "aopen", "parentUuid": "uopen", "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                             "content": [{"type": "tool_use", "id": "tu_open", "name": "Bash", "input": {"command": "uv run pytest -q"}}]}})
    return recs


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
page.on("pageerror", (e) => fs.appendFileSync(cfg.consoleLog, "pageerror: " + e + "\n"));
await page.addInitScript(({ compact, hold }) => {
  try { localStorage.setItem("romp:scrollDiagCap", "100000"); } catch (e) {}   // every scroll row, never the per-minute cap
  try { localStorage.setItem("romp:settings", JSON.stringify({ compact })); } catch (e) {}   // the transcript mode under test (compact is the default)
  window.__frames = 0; window.__types = []; window.__diag = []; window.__tailLo = null; window.__lastTail = null; window.__tailSizes = [];
  window.addEventListener("message", (e) => { const m = e.data; if (!m || typeof m.type !== "string") return;
    if (m.__injected) return;   // the driver's own re-posts are not the kernel's frames
    if (m.type === "session" || m.type === "update" || m.type === "chatTail") { window.__frames++; window.__types.push(m.type); }
    if (m.type === "chatTail" && Array.isArray(m.events)) window.__tailSizes.push(m.events.length);
    if (m.type === "chatTail" && Array.isArray(m.events) && m.events.length) window.__lastTail = JSON.parse(JSON.stringify(m));
    if (m.type === "session" && Array.isArray(m.events) && typeof m.tailLo === "number") window.__tailLo = m.tailLo; });
  const origSend = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    try { const m = JSON.parse(d); if (m && m.type === "clientDiag") window.__diag.push({ what: m.what, data: m.data });
          if (hold && m && m.type === "sendMessage") return;   // the send stays the page's own: the transcript lands it (no kernel queue, no retry notice)
    } catch (e) {}
    return origSend.call(this, d);
  };
}, { compact: cfg.compact, hold: cfg.hold });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForSelector(".turn.turn-user", { timeout: 20000 });
await page.waitForTimeout(800);
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const settle = async () => { await painted(); await page.waitForTimeout(300); await painted(); };
const iso = (x) => new Date(x * 1000).toISOString().replace(/\.\d{3}Z$/, ".000Z");
let parent = "aopen", clock = cfg.t0 + 2000;
const append = (recs) => { for (const r of recs) fs.appendFileSync(cfg.transcript, JSON.stringify(r) + "\n"); };
const rec = (type, uuid, message, extra) => { clock += 3; const r = { type, timestamp: iso(clock), uuid, parentUuid: parent, sessionId: cfg.sid, message, ...(extra || {}) }; parent = uuid; return r; };
const asst = (content, stop) => ({ role: "assistant", model: "claude-fable-5-1", stop_reason: stop || "tool_use", content });
const waitFor = async (fn, arg, ms) => { try { await page.waitForFunction(fn, arg, { timeout: ms }); return true; } catch (e) { return false; } };
const frames = () => page.evaluate(() => window.__frames);

const out = { tailLo: null, spacerAtOpen: false, cycles: [] };
out.tailLo = await page.evaluate(() => window.__tailLo);
out.spacerAtOpen = await page.evaluate((sid) => !!document.querySelector('#content .thread[data-session="' + sid + '"] > .tx-spacer-top'), cfg.sid);

// arm a cycle: mark every node the view holds now, watch every mutation batch on the view from here on
const arm = (landed) => page.evaluate(({ sid, landed }) => {
  const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
  const c = document.getElementById("content");
  // every node painted before the send, less the live cards riding the very end (the kernel's queued copy and its notice, the
  // page's own pending bubble): those are tail units, repainted as the transcript grows above them
  const all = Array.from(th.children);
  while (all.length && /turn-queued|turn-notice/.test(String(all[all.length - 1].className))) all.pop();
  const kept = all.map((n) => ({ node: n, top: n.offsetTop, cls: String(n.className).slice(0, 40) }));
  const keptSet = new Set(kept.map((k) => k.node));
  const spacer = th.querySelector(":scope > .tx-spacer-top");
  // the reader's anchor: the first node whose bottom is below the viewport's top
  const cTop = c.getBoundingClientRect().top;
  const anchor = Array.from(th.children).find((n) => n.getBoundingClientRect().bottom > cTop + 1) || null;
  const w = { kept, spacerH: spacer ? spacer.offsetHeight : null, st: c.scrollTop, sh: c.scrollHeight, anchor, anchorTop: anchor ? anchor.getBoundingClientRect().top : null,
              batches: [], keptRemoved: [], spacerTouched: 0, landedLeft: 0, landedRerendered: 0, diag0: window.__diag.length, types0: window.__types.length };
  if (window.__w && window.__w.mo) window.__w.mo.disconnect();
  const isSpacer = (n) => n instanceof Element && n.classList.contains("tx-spacer-top");
  w.mo = new MutationObserver((records) => {
    const removed = [], added = [];
    for (const r of records) { r.removedNodes.forEach((n) => removed.push(n)); r.addedNodes.forEach((n) => added.push(n)); }
    const addedLanded = added.some((n) => n instanceof HTMLElement && n.dataset.uuid === landed);
    for (const n of removed) {
      if (keptSet.has(n)) w.keptRemoved.push(String(n.className).slice(0, 40) + "|" + ((n.dataset && n.dataset.uuid) || ""));
      if (n instanceof HTMLElement && n.dataset.uuid === landed) { if (addedLanded) w.landedRerendered++; else w.landedLeft++; }
    }
    if (removed.some(isSpacer) || added.some(isSpacer)) w.spacerTouched++;
    w.batches.push({ removed: removed.length, added: added.length, removedCls: removed.slice(0, 3).map((n) => String(n.className).slice(0, 30)), addedCls: added.slice(0, 3).map((n) => String(n.className).slice(0, 30)) });
  });
  w.mo.observe(th, { childList: true });
  window.__w = w;
  return { kept: kept.length, spacerH: w.spacerH, st: w.st, sh: w.sh, anchor: anchor ? String(anchor.className).slice(0, 40) : null };
}, { sid: cfg.sid, landed });

// one reading of the four criteria against the armed cycle
const probe = (step, landed) => page.evaluate(({ sid, step, landed }) => {
  const w = window.__w;
  const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
  const c = document.getElementById("content");
  const spacer = th.querySelector(":scope > .tx-spacer-top");
  const gone = [], moved = [];
  w.kept.forEach((k, i) => { if (!k.node.isConnected) gone.push(i + ":" + k.cls); else if (k.node.offsetTop !== k.top) moved.push(i + ":" + k.cls + ":" + (k.node.offsetTop - k.top)); });
  const diag = window.__diag.slice(w.diag0);
  return { step, landedShown: landed ? !!th.querySelector('[data-uuid="' + landed + '"]') : null,
           gone: gone.length, goneSample: gone.slice(-4), moved: moved.length, movedSample: moved.slice(0, 4), kept: w.kept.length,
           spacerH: spacer ? spacer.offsetHeight : null, spacerH0: w.spacerH, st: c.scrollTop, st0: w.st, sh: c.scrollHeight, sh0: w.sh, ch: c.clientHeight,
           dist: c.scrollHeight - c.scrollTop - c.clientHeight,
           anchorConnected: w.anchor ? w.anchor.isConnected : null, anchorDy: w.anchor && w.anchor.isConnected ? w.anchor.getBoundingClientRect().top - w.anchorTop : null,
           keptRemoved: w.keptRemoved.length, keptRemovedSample: w.keptRemoved.slice(0, 4), spacerTouched: w.spacerTouched, landedLeft: w.landedLeft, landedRerendered: w.landedRerendered,
           gestures: diag.filter((d) => d.what === "scrollgesture").length,
           rows: diag.filter((d) => /^(scrollgesture|scrollwrite|spacer|tailmut|tailchange)$/.test(d.what)).slice(0, 12).map((d) => d.what + ":" + JSON.stringify(d.data).slice(0, 160)),
           types: window.__types.slice(w.types0), batches: w.batches.slice(-6),
           tail: Array.from(th.children).slice(-6).map((n) => String(n.className).slice(0, 26) + "|" + ((n.dataset && n.dataset.uuid) || "").slice(-12) + "|" + ((n.dataset && n.dataset.unit) || "")) };
}, { sid: cfg.sid, step, landed });

const cycle = async (name, landed, text) => {
  const c = { name, arm: await arm(landed), steps: [] };
  // the send: the page's own bubble, then (unless the send is held back) the kernel's frame for its copy
  let f0 = await frames();
  await page.fill("#composer-input", text); await page.press("#composer-input", "Enter");
  if (cfg.hold) await waitFor((t) => Array.from(document.querySelectorAll("#content .turn-queued")).some((n) => (n.textContent || "").includes(t)), text, 5000);
  else await waitFor((b) => window.__frames > b, f0, 5000);
  await settle();
  c.steps.push(await probe("send", null));
  // the landing: the transcript takes the message
  append([{ type: "queue-operation", operation: "dequeue", timestamp: iso(clock + 1), sessionId: cfg.sid },
          rec("user", landed, { role: "user", content: [{ type: "text", text }] }, { promptSource: "sdk" })]);
  c.landedArrived = await waitFor((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), landed, 10000); await settle();
  c.steps.push(await probe("landing", landed));
  // the reply, record by record: each is its own tail frame
  const reply = [
    () => rec("assistant", landed.slice(0, -2) + "r1", asst([{ type: "thinking", thinking: "Weighing the " + name + " ranking change.", signature: "sig" }])),
    () => rec("assistant", landed.slice(0, -2) + "r2", asst([{ type: "text", text: "Reply marker " + name + ": the ranking now weighs recency." }])),
    () => rec("assistant", landed.slice(0, -2) + "r3", asst([{ type: "tool_use", id: "tu_" + name, name: "Bash", input: { command: "uv run pytest -q tests/test_search.py" } }])),
  ];
  for (let k = 0; k < reply.length; k++) {
    f0 = await frames();
    append([reply[k]()]);
    await waitFor((b) => window.__frames > b, f0, 8000); await settle();
    c.steps.push(await probe("reply" + (k + 1), landed));
  }
  await page.evaluate(() => { if (window.__w && window.__w.mo) window.__w.mo.disconnect(); });
  out.cycles.push(c);
};

// cycle 1: the reader follows the tail
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
await settle();
await cycle("follow", cfg.landed[0], "please rebuild the notes-api search index, round one");
// cycle 2: the reader is scrolled up inside the rendered window, reading
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = Math.max(0, c.scrollHeight - c.clientHeight - 2500); });
await settle(); await page.waitForTimeout(400); await settle();
await cycle("scrolled", cfg.landed[1], "please document the notes-api ranking, round two");

// the same tail again and again (a kernel repeating itself), then one whose LAST event changed: through the pane's own message
// channel, the frame the kernel last sent as the base
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
await settle();
const closing = cfg.landed[1].slice(0, -2) + "c1";
let f1 = await frames();
append([rec("assistant", closing, asst([{ type: "text", text: "Closing note: the ranking change is in." }]))]);
await waitFor((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), closing, 8000);
await waitFor((b) => window.__frames > b, f1, 4000); await settle(); await page.waitForTimeout(500); await settle();
out.repeat = await page.evaluate(async ({ sid, closing }) => {
  const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
  const c = document.getElementById("content");
  const base = window.__lastTail;
  const r = { baseOk: !!(base && base.events.some((e) => e && e.uuid === closing)), baseN: base ? base.events.length : 0 };
  if (!r.baseOk) return r;
  const frame = () => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(res, 0))));
  const batches = [];
  const mo = new MutationObserver((recs) => { const b = { removed: [], added: [] };
    for (const x of recs) { x.removedNodes.forEach((n) => b.removed.push({ cls: String(n.className || n.nodeName).slice(0, 30), uuid: (n.dataset && n.dataset.uuid) || "" }));
                            x.addedNodes.forEach((n) => b.added.push({ cls: String(n.className || n.nodeName).slice(0, 30), uuid: (n.dataset && n.dataset.uuid) || "" })); }
    batches.push(b); });
  mo.observe(th, { childList: true });
  const diag0 = window.__diag.length;
  for (let k = 0; k < 28; k++) { window.postMessage({ ...JSON.parse(JSON.stringify(base)), __injected: true }, "*"); await frame(); }
  await new Promise((res) => setTimeout(res, 300)); await frame();
  r.repeatBatches = batches.splice(0).map((b) => ({ removed: b.removed.slice(0, 4), added: b.added.slice(0, 4), nr: b.removed.length, na: b.added.length }));
  // one event changed: the closing reply's text grows by a line
  const unitH = () => Array.from(th.querySelectorAll(':scope > [data-uuid="' + closing + '"]')).reduce((h, n) => h + n.offsetHeight, 0);
  const spacer = th.querySelector(":scope > .tx-spacer-top");
  const h0 = unitH(), sh0 = c.scrollHeight, sp0 = spacer ? spacer.offsetHeight : null;
  const changed = JSON.parse(JSON.stringify(base));
  const ev = changed.events.find((e) => e && e.uuid === closing);
  for (const k of ["md", "text"]) if (typeof ev[k] === "string") ev[k] = ev[k] + "\n\nA second paragraph: recency now weighs twice as much.";
  window.postMessage({ ...changed, __injected: true }, "*");
  await frame(); await new Promise((res) => setTimeout(res, 300)); await frame();
  mo.disconnect();
  r.changedBatches = batches.map((b) => ({ removed: b.removed, added: b.added }));
  r.unitDh = unitH() - h0; r.shDh = c.scrollHeight - sh0; r.spacer = [sp0, spacer ? spacer.offsetHeight : null]; r.spacerConnected = spacer ? spacer.isConnected : null;
  r.fieldsChanged = ["md", "text"].filter((k) => typeof ev[k] === "string");
  r.rows = window.__diag.slice(diag0).filter((d) => /^(resync|frame-|scrollgesture)/.test(d.what)).slice(0, 8).map((d) => d.what);
  return r;
}, { sid: cfg.sid, closing });
out.closing = closing;

// one AGENT CARD changes mid-transcript with N unchanged events after it: the tool's result lands N records later, so the kernel
// re-sends the card and every event after it (the wire truncates after its anchor and re-appends). The card alone may change.
const cardPhase = async (name, n, scrolled) => {
  const base = "11111111-2222-3333-4444-" + (name === "card25" ? "d" : "e");
  const card = base + "00000000000", tuid = "tu_" + name;
  append([rec("assistant", card, asst([{ type: "tool_use", id: tuid, name: "Agent",
    input: { description: "Survey the notes-api ranking tests", prompt: "Read the ranking tests and list the slow ones.", subagent_type: "general-purpose" } }]))]);
  const rest = [];
  for (let k = 1; k <= n; k++) rest.push(rec("assistant", base + String(k).padStart(11, "0"), asst([{ type: "text", text: "Progress note " + k + " while the survey runs." }])));
  append(rest);
  const last = rest[rest.length - 1].uuid;
  const r = { name, n, arrived: await waitFor((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), last, 15000) };
  await settle(); await page.waitForTimeout(400); await settle();
  r.pre = await page.evaluate(({ sid, card, scrolled }) => {
    const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
    const c = document.getElementById("content");
    const node = th.querySelector('[data-uuid="' + card + '"]');
    if (!node) return { cardShown: false };
    if (scrolled) {   // the reader sits BELOW the card, reading the progress notes: the card is above the viewport
      const y = node.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop;
      c.scrollTop = y + node.offsetHeight + 400;
    } else c.scrollTop = c.scrollHeight;
    return { cardShown: true };
  }, { sid: cfg.sid, card, scrolled });
  await settle(); await page.waitForTimeout(300); await settle();
  await page.evaluate(({ sid, card }) => {
    const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
    const c = document.getElementById("content");
    const cTop = c.getBoundingClientRect().top;
    const anchor = Array.from(th.children).find((x) => x.getBoundingClientRect().bottom > cTop + 1) || null;
    const spacer = th.querySelector(":scope > .tx-spacer-top");
    const cardH = () => Array.from(th.querySelectorAll(':scope > [data-uuid="' + card + '"]')).reduce((h, x) => h + x.offsetHeight, 0);
    const w = { batches: [], sh: c.scrollHeight, st: c.scrollTop, dist: c.scrollHeight - c.scrollTop - c.clientHeight, cardH: cardH(), cardHf: cardH, spacer, spacerH: spacer ? spacer.offsetHeight : null,
                anchor, anchorTop: anchor ? anchor.getBoundingClientRect().top : null, diag0: window.__diag.length, frames0: window.__frames, sizes0: window.__tailSizes.length };
    w.mo = new MutationObserver((recs) => { const b = { removed: [], added: [] };
      for (const x of recs) { x.removedNodes.forEach((m) => b.removed.push({ cls: String(m.className || m.nodeName).slice(0, 30), uuid: (m.dataset && m.dataset.uuid) || "" }));
                              x.addedNodes.forEach((m) => b.added.push({ cls: String(m.className || m.nodeName).slice(0, 30), uuid: (m.dataset && m.dataset.uuid) || "" })); }
      w.batches.push(b); });
    w.mo.observe(th, { childList: true });
    window.__card = w;
  }, { sid: cfg.sid, card });
  const f0 = await frames();
  append([rec("user", base.slice(0, -1) + "f" + (name === "card25" ? "1" : "2") + "0000000000", { role: "user", content: [{ type: "tool_result", tool_use_id: tuid, content: "Three slow tests: ranking_recency, ranking_ties, ranking_stopwords." }] })]);
  r.frame = await waitFor((b) => window.__frames > b, f0, 8000);
  await settle(); await page.waitForTimeout(400); await settle();
  r.post = await page.evaluate(({ card }) => {
    const w = window.__card; w.mo.disconnect();
    const c = document.getElementById("content");
    const diag = window.__diag.slice(w.diag0);
    return { batches: w.batches.map((b) => ({ removed: b.removed.slice(0, 6), added: b.added.slice(0, 6), nr: b.removed.length, na: b.added.length })),
             shDh: c.scrollHeight - w.sh, stD: c.scrollTop - w.st, dist: c.scrollHeight - c.scrollTop - c.clientHeight, cardDh: w.cardHf() - w.cardH,
             spacer: [w.spacerH, w.spacer ? w.spacer.offsetHeight : null], spacerConnected: w.spacer ? w.spacer.isConnected : null,
             anchorConnected: w.anchor ? w.anchor.isConnected : null, anchorDy: w.anchor && w.anchor.isConnected ? w.anchor.getBoundingClientRect().top - w.anchorTop : null,
             gestures: diag.filter((d) => d.what === "scrollgesture").length, frames: window.__frames - w.frames0, tailSizes: window.__tailSizes.slice(w.sizes0),
             rows: diag.filter((d) => /^(resync|frame-|scrollgesture|scrollwrite|spacer)/.test(d.what)).slice(0, 8).map((d) => d.what + ":" + JSON.stringify(d.data).slice(0, 140)) };
  }, { card });
  r.card = card;
  return r;
};
out.cards = [await cardPhase("card25", 25, false), await cardPhase("card170", 170, true)];
fs.writeFileSync(cfg.out, JSON.stringify(out));
fs.writeSync(1, "RESULT-FILE:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


class ServedSendTailAppend(unittest.TestCase):
    """Compact mode, the default: tool runs folded, thinking hidden."""
    maxDiff = None
    COMPACT = True
    HOLD = False   # the send reaches the kernel, which queues it (the session is mid-turn) and lists its copy until the transcript lands it

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="send-tail-append-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.t0 = int(time.time()) - 3000
        cls.port, cls.token = _sb._free_port(), "testtok-tailappend"
        try:
            cls.kernel, cls.klog, cls.transcript = _sb._kernel(cls.lab, "k", cls.port, cls.token, records=_records(cls.t0))
        except unittest.SkipTest:
            shutil.rmtree(cls.lab, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _run(self):
        cfg = os.path.join(self.lab, "cfg.json")
        console_log = os.path.join(self.lab, "console.log")
        Path(console_log).write_text("")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID, "landed": LANDED, "compact": self.COMPACT, "hold": self.HOLD,
                       "transcript": self.transcript, "t0": self.t0, "consoleLog": console_log,
                       "out": os.path.join(self.lab, "result.json")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=DRIVER_TIMEOUT_S,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            self.fail("the driver ran past its %d s budget:\n%s\n%s" % (DRIVER_TIMEOUT_S, out[-3000:], _sb._kernel_tail(("kernel", self.klog))))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\n" + _sb._kernel_tail(("kernel", self.klog)))
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT-FILE:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        with open(line[len("RESULT-FILE:"):]) as f:
            r = json.load(f)
        self.assertEqual(open(console_log).read().strip(), "", "the page threw")
        return r

    def test_a_send_its_landing_and_its_reply_append_to_the_tail(self):
        r = self._run()
        mode = ("compact" if self.COMPACT else "normal") + ("/held" if self.HOLD else "/queued")
        print("TAIL-APPEND %s repeat=%s" % (mode, json.dumps({k: v for k, v in (r.get("repeat") or {}).items() if k != "changedBatches"})))
        print("TAIL-APPEND %s changed=%s" % (mode, json.dumps((r.get("repeat") or {}).get("changedBatches"))[:600]))
        for c in r["cycles"]:
            print("TAIL-APPEND %s %s arm=%s" % (mode, c["name"], json.dumps(c["arm"])))
            for s in c["steps"]:
                print("  %s" % json.dumps({k: s[k] for k in ("step", "landedShown", "gone", "moved", "keptRemoved", "spacerTouched", "landedLeft",
                                                              "spacerH0", "spacerH", "sh0", "sh", "st0", "st", "dist", "anchorDy", "gestures", "tail")}))
        # the lab's shape: the kernel's tail starts past turn 0, so the page opens on a gap under a top spacer
        self.assertIsInstance(r["tailLo"], int)
        self.assertGreater(r["tailLo"], 0, "the transcript is longer than the kernel's tail: %r" % r["tailLo"])
        self.assertTrue(r["spacerAtOpen"], "the view opens on a top spacer")
        self.assertEqual([c["name"] for c in r["cycles"]], ["follow", "scrolled"])
        for c in r["cycles"]:
            self.assertTrue(c["landedArrived"], "%s: the landing reached the page" % c["name"])
            steps = c["steps"]
            self.assertEqual([s["step"] for s in steps], ["send", "landing", "reply1", "reply2", "reply3"])
            last = steps[-1]
            # 1. the landed message never leaves the DOM once painted
            for s in steps[1:]:
                self.assertTrue(s["landedShown"], "%s/%s: the landed message is on the page: %s" % (c["name"], s["step"], json.dumps(s)))
            self.assertEqual(last["landedLeft"], 0, "%s: no batch removed the landed message: %s" % (c["name"], json.dumps(last)))
            # 2. no batch touched the top spacer or removed a node painted before the send
            self.assertEqual(last["spacerTouched"], 0, "%s: no batch touched the top spacer: %s" % (c["name"], json.dumps(last["batches"])))
            self.assertEqual(last["keptRemoved"], 0, "%s: no node painted before the send was removed: %s" % (c["name"], json.dumps(last)))
            for s in steps:
                self.assertEqual(s["gone"], 0, "%s/%s: every node painted before the send is still there: %s" % (c["name"], s["step"], json.dumps(s)))
            # 3. the top spacer and everything above the tail keep their geometry: the scroll height grows by the tail alone
            for s in steps:
                self.assertEqual(s["spacerH"], s["spacerH0"], "%s/%s: the top spacer kept its height: %s" % (c["name"], s["step"], json.dumps(s)))
                self.assertEqual(s["moved"], 0, "%s/%s: no node painted before the send moved: %s" % (c["name"], s["step"], json.dumps(s)))
            # 4. the reader: at the bottom when following, exactly where they were when scrolled up; no scroll the pane did not write
            for s in steps:
                if c["name"] == "follow":
                    self.assertLessEqual(s["dist"], 2, "follow/%s: the reader is at the bottom: %s" % (s["step"], json.dumps(s)))
                else:
                    self.assertEqual(s["st"], s["st0"], "scrolled/%s: the reader's scroll position did not move: %s" % (s["step"], json.dumps(s)))
                    self.assertTrue(s["anchorConnected"], "scrolled/%s: the node the reader was reading is still there" % s["step"])
                    self.assertLess(abs(s["anchorDy"]), 1, "scrolled/%s: the node the reader was reading did not move: %s" % (s["step"], json.dumps(s)))
                self.assertEqual(s["gestures"], 0, "%s/%s: no scroll the pane did not write: %s" % (c["name"], s["step"], json.dumps(s["rows"])))
        # the same tail 28 times mutates nothing; a tail whose last event changed touches that unit alone, by its own height
        rp = r["repeat"]
        self.assertTrue(rp["baseOk"], "the kernel's last tail carries the closing reply: %r" % rp)
        self.assertEqual(rp["repeatBatches"], [], "an identical tail, applied 28 times, mutated nothing: %s" % json.dumps(rp["repeatBatches"])[:1500])
        self.assertTrue(rp["fieldsChanged"], "the closing reply carries its text: %r" % rp)
        self.assertEqual(len(rp["changedBatches"]), 1, "one batch for one changed event: %s" % json.dumps(rp["changedBatches"])[:1500])
        b = rp["changedBatches"][0]
        self.assertTrue(b["removed"] and b["added"], "the changed unit was repainted: %r" % b)
        self.assertEqual({n["uuid"] for n in b["removed"] + b["added"]}, {r["closing"]}, "only the changed unit's nodes moved: %s" % json.dumps(b))
        self.assertEqual(rp["spacer"][0], rp["spacer"][1], "the top spacer kept its height: %r" % rp["spacer"])
        self.assertTrue(rp["spacerConnected"], "the top spacer is the same node")
        self.assertGreater(rp["unitDh"], 0, "the changed unit grew by its new paragraph: %r" % rp)
        self.assertLessEqual(abs(rp["shDh"] - rp["unitDh"]), 1, "the scroll height moved by the unit's change alone: %r" % rp)
        # an agent card changing N events up the tail (its result landing), the N events after it re-sent unchanged: the card alone
        for cd in r["cards"]:
            print("TAIL-APPEND %s %s %s" % (mode, cd["name"], json.dumps(cd)[:1600]))
            what = "%s (N=%d)" % (cd["name"], cd["n"])
            self.assertTrue(cd["arrived"] and cd["pre"]["cardShown"] and cd["frame"], "%s: the card and the events after it are on the page, and the result's frame came: %r" % (what, cd))
            post = cd["post"]
            self.assertGreaterEqual(max(post["tailSizes"] or [0]), cd["n"] + 1, "%s: the kernel re-sent the card and the %d events after it: %r" % (what, cd["n"], post["tailSizes"]))
            self.assertEqual(len(post["batches"]), 1, "%s: one batch for one changed card: %s" % (what, json.dumps(post["batches"])[:1500]))
            b = post["batches"][0]
            self.assertTrue(b["nr"] >= 1 and b["na"] >= 1, "%s: the card was repainted: %r" % (what, b))
            self.assertEqual({x["uuid"] for x in b["removed"] + b["added"]}, {cd["card"]}, "%s: only the card's nodes moved, none of the %d after it: %s" % (what, cd["n"], json.dumps(b)))
            self.assertEqual(b["nr"], b["na"], "%s: the card's nodes replaced one for one: %r" % (what, b))
            self.assertEqual(post["spacer"][0], post["spacer"][1], "%s: the top spacer kept its height" % what)
            self.assertTrue(post["spacerConnected"], "%s: the top spacer is the same node" % what)
            self.assertLessEqual(abs(post["shDh"] - post["cardDh"]), 1, "%s: the scroll height moved by the card's change alone: %r" % (what, post))
            if cd["name"] == "card25":
                self.assertLessEqual(post["dist"], 2, "%s: the reader following the tail is at the bottom: %r" % (what, post))
            else:
                self.assertTrue(post["anchorConnected"], "%s: the node the reader was reading is still there" % what)
                self.assertLess(abs(post["anchorDy"]), 1, "%s: the reader below the card did not move: %r" % (what, post))
            self.assertEqual(post["gestures"], 0, "%s: no scroll the pane did not write: %s" % (what, json.dumps(post["rows"])))


class ServedSendTailAppendNormal(ServedSendTailAppend):
    """Normal mode (compact off), every event its own unit: the mode where the exact tail path trimmed by event index."""
    COMPACT = False


class ServedSendTailAppendNormalHeld(ServedSendTailAppend):
    """Normal mode with the send held at the page: the transcript lands it with nothing after it, so the reply's first frame is
    the first tail frame after the landing's paint, the shape the user's page dropped the landed message at."""
    COMPACT = False
    HOLD = True


class ServedSendTailAppendCompactHeld(ServedSendTailAppend):
    COMPACT = True
    HOLD = True


if __name__ == "__main__":
    unittest.main()
