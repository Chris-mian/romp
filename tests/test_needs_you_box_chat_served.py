"""The chat page's NEEDS YOU BOX (plans/needs-you.md, phase three): a hermetic kernel over one synthetic live session in the
notes-api demo world, the real /chat page served from a copy of the built bundle, driven by Playwright, the feed pane closed.
The session's goal store holds three judge questions (diary block events in the fold's shape) and a fourth, working focus goal;
the transcript ends on an API error record only the user can clear (isApiErrorMessage, "prompt is too long"), so the fourth
card is a HARD STOP the kernel floors with a live-block object (state apiError) and the tab wears the red Blocked ring; a message
from a DIRECTED peer is held under STATE/postal/quarantine before boot and becomes a needs-you notice card at the first build.
The box lists the three questions (Reply, Clear) and the held message (Approve, Deny) under a "Needs you · 4" header, collapsed to that header by default and opened in steps,
wears the Needs you token on its edge, and lists no row for the hard stop. Clear
takes its row off the box with the next frame; Continue posts the card's own Continue wire and its row leaves once the kernel
files the reply; Reply points the composer at the card (the chip with the card's title) and the row leaves once the typed reply
is filed. The gear's Needs you box switch (a romp:settings save) hides the box and leaves the ring; back on, the box returns.
Synthetic only: placeholder ids, invented text, hostname TESTHOST.

After the 2026-09-23 default flip the badge is the default; this lab opts into RING mode (it seeds tabStateBadge:false) because its subject is the ring, and the dot's default is covered by the badge lab (test_tab_badge_browser) and the gear-preview test (test 5)."""
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

SID = "cccccccc-1111-2222-3333-444444444444"
API = "dddddddd-1111-2222-3333-444444444444"     # a second session with a question and NO hard stop: its tab wears the Needs you ring
API_Q = "which port should the api listen on in the fixtures?"
BRIEF = "the suite targets Postgres in CI and SQLite locally; which should the fixtures load into?"
LONG_BRIEF = " ".join("The fixtures load into one database and the suite has two: Postgres in CI and SQLite on a laptop, with different "
                      "date handling, so a fixture written for one fails on the other." for _ in range(30))   # past four lines at any width the lab runs at (CI's browser fit five repetitions in four; the round-fifteen CI red)
MID = "aaaaaaaa-bbbb-cccc-dddd-000000000301"
TOKEN_RGB = "rgb(217, 70, 239)"          # --st-needs-bg, the dark theme (styles.css)
QUESTIONS = ["which database does the suite target?", "should the parser keep the legacy header?", "is the fixtures directory versioned?"]

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
await page.addInitScript(() => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.tabStateBadge = false; localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {} });   // RING mode: this lab's subject is the ring, not the badge (the 2026-09-23 default flip; the dot is the badge lab's + test 5's)
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
const out = { errors };
const mark = () => process.stdout.write("PARTIAL:" + JSON.stringify(out) + "\n");   // the record so far, after every scene: what a run that hits the driver's budget still reports
const rowSel = (id) => '#notices .ntc-row[data-item="' + id + '"]';
const readBox = () => page.evaluate(() => {
  const box = document.getElementById("notices"); const cs = box ? getComputedStyle(box) : null;
  const rows = box ? Array.from(box.querySelectorAll(".ntc-row")) : [];
  const tab = document.querySelector('#tabs .tab[data-id]');
  const tabs = Object.fromEntries(Array.from(document.querySelectorAll('#tabs .tab[data-id]')).map((t) => [t.getAttribute("data-id"), t.className]));   // every tab's classes by sid: the rings
  const vis = (el) => !!el && getComputedStyle(el).display !== "none";
  const level = box ? ["ntc-l0", "ntc-l1", "ntc-l2"].findIndex((c) => box.classList.contains(c)) : null;   // the box's level class (-1: none)
  return { shown: !!box && box.style.display !== "none" && !!cs && cs.display !== "none", border: cs ? cs.borderTopColor : null, borderLeft: cs ? cs.borderLeftWidth : null,
           head: box ? ((box.querySelector(".ntc-head .ntc-label") || {}).textContent || null) : null,
           dot: box && box.querySelector(".ntc-head .ntc-dot") ? getComputedStyle(box.querySelector(".ntc-head .ntc-dot")).backgroundColor : null,
           level, caret: box && box.querySelector(".ntc-head .ntc-caret") ? box.querySelector(".ntc-head .ntc-caret").textContent : null,
           headVisible: box ? vis(box.querySelector(".ntc-head")) : null, rowsVisible: rows.map((r) => vis(r)), bodiesVisible: rows.map((r) => vis(r.querySelector(".ntc-body"))),
           theme: document.body.classList.contains("theme-light") ? "light" : "dark",
           rows: rows.map((r) => ({ id: r.getAttribute("data-item"), title: (r.querySelector(".ntc-title") || {}).textContent, body: (r.querySelector(".ntc-body") || {}).textContent,
                                   buttons: Array.from(r.querySelectorAll(".ntc-actions button")).map((b) => b.textContent), disabled: Array.from(r.querySelectorAll(".ntc-actions button")).map((b) => b.disabled) })),
           tabClasses: tab ? tab.className : null, tabs };
});
const waitRows = (n, ms) => page.waitForFunction((n) => document.querySelectorAll("#notices .ntc-row").length === n, n, { timeout: ms }).then(() => true).catch(() => false);
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab", { timeout: 30000 }).catch(() => {});
// 1. the box: four rows (the three questions and the held message), the header, the token edge, no row for the hard stop, the red ring on the tab
out.fourRows = await waitRows(4, 60000);
out.first = await readBox();
// 0. COLLAPSED BY DEFAULT and opened in steps (the user 2026-09-23): the header line alone, one click the items (titles and buttons), a second the
// full context (the background under each title); read in both themes at each level (the theme is the body's class, as the colour lab sets it)
const setTheme = (t) => page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), t);
const foldTo = (level) => openNeedsBox(page, level);   // the shared fold helper (test_ship_reship_served NEEDS_BOX_OPEN_JS): a click per step, each waited on the level class, fail-soft at the base
out.levels = {};
for (const t of ["dark", "light"]) {
  await setTheme(t); await foldTo(0); out.levels[t + "0"] = await readBox();
  await foldTo(1); out.levels[t + "1"] = await readBox();
  await foldTo(2); out.levels[t + "2"] = await readBox();
}
await setTheme("dark"); await foldTo(2);   // the rest of the scenes read the bodies and their disclosures: the full context open
mark();
// the hard stop as the feed pane shows it from the same kernel's pushed frame: the focus goal's card under Needs you with the on-you API error badge
const feed = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await feed.goto(cfg.feed);
const g4Sel = '[data-key="a:' + cfg.g4 + '"]';
out.hardStop = await feed.waitForSelector(g4Sel, { state: "attached", timeout: 60000 }).then(() => feed.evaluate((sel) => { const c = document.querySelector(sel);
  const badge = c ? c.querySelector(".fask-api") : null; const badges = c ? Array.from(c.querySelectorAll("a, span")).map((x) => x.textContent || "").filter((t) => t.startsWith("⚠")) : [];
  return { col: c ? c.parentElement.id : null, badges }; }, g4Sel)).catch(() => ({ col: null, badges: [] }));
mark();
await feed.close();
// 1b. a brief lands on the first question's card (the judge's blockSummary, written to the store): the row's body follows within the
// next frames with no gesture (the second review of PR 1967: the box repainted only when a row came or went)
// the kernel's own build event for a store write (the disclosure scene's second CI red, 2026-09-22: sixty seconds with no frame and no word
// from the kernel): GET /feed.json serves the pusher's warmed feed while a pane is attached, so its buildId advancing past the one read
// before the write, with the card's brief as written, is the kernel's word that its feed rebuilt over the new store; the box row follows by
// one chat build (_feed_needs_rows, the chat signature's `notices`). The order touch moves a file the view signature stats, so the rebuild
// follows at once rather than at the signature's 5 s clock bucket (the second contributor's read of PR 2031: the touch makes the rebuild
// prompt, it does not enable it). A miss records the kernel's pusher and build counters (GET /perf) beside the brief the kernel's last feed
// carries, so the failure names the link that did not fire: the write unseen, the feed not rebuilt, or the frame not shipped.
// The wait is polled from the DRIVER: an async predicate under page.waitForFunction resolves at once, since the Promise it returns is truthy
// (Playwright fulfils on the first truthy return; the second contributor's read of PR 2031: every scene's wait returned at once with False)
const kernelFeed = () => page.evaluate(async (u) => { try { const r = await fetch(u); return r.ok ? await r.json() : null; } catch (e) { return null; } }, cfg.feedJson);
const kernelPerf = () => page.evaluate(async (u) => { try { const r = await fetch(u); const p = await r.json(); return { pusher: p.pusher, builds: p.builds, stages_ms: p.stages_ms }; } catch (e) { return String(e); } }, cfg.perf);
const briefOf = (f, id) => (((f || {}).asks || []).find((a) => a.itemId === id) || {}).blockSummary;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const feedBuiltPast = async (floor, id, brief, ms) => {   // the kernel's feed build past `floor` carrying `brief` on the card: its build id, else null at the deadline
  if (typeof floor !== "number") return null;   // a null floor is the pre-write read's own miss (the floor pin names it): no poll, no counters pointing at the kernel (the second contributor's read of PR 2038)
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {   // loop-ok: bounded by the deadline, one fetch per 500 ms (the cadence the polling option asked for)
    const f = await kernelFeed();
    if (f && typeof f.buildId === "number" && typeof floor === "number" && f.buildId > floor && briefOf(f, id) === brief) return f.buildId;
    await sleep(500);
  }
  return null;
};
const writeStore = async (mutate) => {   // the feed build id before the write (null when that read fails: its own miss, never a floor of -1), the write (seq bumped), the order touch
  // The write is a PUBLICATION the kernel's own writers must see: `rev` advances as save_goals advances it, so a judge pass whose store predates
  // this write rebases onto it (the kernel's compare-and-swap keys on rev and, since the CI red of 2026-09-23, on the file's identity; before,
  // an in-place rewrite that left rev alone was invisible to a save holding an older base, and the pass's save erased the node just written)
  const b0 = ((await kernelFeed()) || {}).buildId; const st = JSON.parse(fs.readFileSync(cfg.store, "utf8")); mutate(st); st.seq = (st.seq || 0) + 1; st.rev = (st.rev || 0) + 1;
  fs.writeFileSync(cfg.store, JSON.stringify(st));
  fs.utimesSync(cfg.order, new Date(), new Date()); return typeof b0 === "number" ? b0 : null;
};
const onMiss = async (o) => {   // the counters, the kernel's own view of the card, and the FILE: a write the kernel published over reads as a node gone and rev moved
  o.perf = await kernelPerf(); o.kernelBrief = briefOf(await kernelFeed(), o.id);
  try { const st = JSON.parse(fs.readFileSync(cfg.store, "utf8")); o.store = { rev: st.rev, seq: st.seq, hasNode: !!(st.nodes || {})[o.id], brief: ((st.nodes || {})[o.id] || {}).blockSummary }; } catch (e) { o.store = String(e); }
  return o;
};
const builtRecord = async (id, floor, brief) => { const o = { id, floor, built: await feedBuiltPast(floor, id, brief, 90000) }; if (o.built === null) await onMiss(o); return o; };   // { id, floor, built }, the counters on a miss
// a brief is a FAMILY field (the store's distill families): the rebase adopts a family as a unit by its stamp, so an in-place edit of a
// brief stamps its family (briefedMt, as every kernel writer of a brief does) or a judge pass's save keeps its own (2026-09-23)
const briefNow = () => Math.floor(Date.now() / 1000);
const w1 = await writeStore((st) => { st.nodes[cfg.g1].blockSummary = cfg.brief; st.nodes[cfg.g1].briefedMt = briefNow(); });
out.brief = await builtRecord(cfg.g1, w1, cfg.brief);
out.brief.landed = await page.waitForFunction((a) => { const r = document.querySelector(a.sel); const b = r && r.querySelector(".ntc-body"); return !!b && (b.textContent || "").trim() === a.brief; }, { sel: rowSel(cfg.g1), brief: cfg.brief }, { timeout: 30000 }).then(() => true).catch(() => false);   // the row follows the kernel's word by one chat build
if (!out.brief.landed) await onMiss(out.brief);
mark();
out.brief.box = await readBox();
// 1c. a brief past the four-line clamp gets a disclosure on its row (the second contributor's review of PR 1967): the More button shows
// only once the body overflows, opens the row (the clamp lifted, the whole brief on screen), reads Less, and folds the row back
const w2 = await writeStore((st) => { st.nodes[cfg.g1].blockSummary = cfg.longBrief; st.nodes[cfg.g1].briefedMt = briefNow() + 1; });
const moreSel = rowSel(cfg.g1) + " .ntc-more";
// held on the kernel's build event, then the page's own events (the round-fifteen CI red read too early; the second red saw no frame for sixty
// seconds with no word from the kernel): the feed rebuilt past the write with the brief, the body carries it, its layout clips it, then the button
const landedAt = (sel, brief) => page.waitForFunction((a) => { const r = document.querySelector(a.sel); const b = r && r.querySelector(".ntc-body"); return !!b && (b.textContent || "").trim() === a.brief; }, { sel, brief }, { timeout: 30000 }).then(() => true).catch(() => false);
const clippedAt = (sel) => page.waitForFunction((s) => { const r = document.querySelector(s); const b = r && r.querySelector(".ntc-body"); return !!b && b.scrollHeight > b.clientHeight + 1; }, sel, { timeout: 15000 }).then(() => true).catch(() => false);
out.more = await builtRecord(cfg.g1, w2, cfg.longBrief);
out.more.landed = await landedAt(rowSel(cfg.g1), cfg.longBrief); if (!out.more.landed) await onMiss(out.more);
out.more.clipped = await clippedAt(rowSel(cfg.g1));
out.more.shown = await page.waitForSelector(moreSel, { timeout: 15000 }).then(() => true).catch(() => false);
out.more.before = await page.evaluate((s) => { const r = document.querySelector(s); const b = r && r.querySelector(".ntc-body"); const m = r && r.querySelector(".ntc-more");
  return b ? { open: r.classList.contains("ntc-open"), clamp: getComputedStyle(b).webkitLineClamp, clipped: b.scrollHeight > b.clientHeight + 1, label: m ? m.textContent : null, chars: (b.textContent || "").length, width: b.clientWidth } : null; }, rowSel(cfg.g1));
await page.click(moreSel).catch(() => {});
out.more.open = await page.waitForFunction((s) => { const r = document.querySelector(s); return !!r && r.classList.contains("ntc-open"); }, rowSel(cfg.g1), { timeout: 10000 }).then(() => true).catch(() => false);
out.more.after = await page.evaluate((s) => { const r = document.querySelector(s); const b = r && r.querySelector(".ntc-body"); const m = r && r.querySelector(".ntc-more");
  return b ? { clamp: getComputedStyle(b).webkitLineClamp, clipped: b.scrollHeight > b.clientHeight + 1, label: m ? m.textContent : null, text: (b.textContent || "").trim() } : null; }, rowSel(cfg.g1));
await page.click(moreSel).catch(() => {});
out.more.closed = await page.waitForFunction((s) => { const r = document.querySelector(s); return !!r && !r.classList.contains("ntc-open"); }, rowSel(cfg.g1), { timeout: 10000 }).then(() => true).catch(() => false);
out.more.box = await readBox();
mark();
// 2a. a Clear the clears log REFUSES (the log made read-only): the dialog says nothing changed, the row stays and its buttons let go
fs.chmodSync(cfg.ledger, 0o444);
await page.click(rowSel(cfg.g3) + ' [data-act="ntc-clear"]');
out.refused = { dialog: await page.waitForSelector("#confirm", { timeout: 30000 }).then(() => page.evaluate(() => (document.getElementById("confirm") || {}).textContent || "")).catch(() => null) };
out.refused.rearmed = await page.waitForFunction((s) => { const r = document.querySelector(s); return !!r && Array.from(r.querySelectorAll(".ntc-actions button")).every((b) => !b.disabled); }, rowSel(cfg.g3), { timeout: 30000 }).then(() => true).catch(() => false);
out.refused.box = await readBox();
out.refused.rowErr = await page.evaluate((s) => { const r = document.querySelector(s); const e = r && r.querySelector(".ntc-err"); return e && e.style.display !== "none" ? e.textContent : null; }, rowSel(cfg.g3));
await page.evaluate(() => { const b = Array.from(document.querySelectorAll("#confirm button")).find((x) => /Dismiss/.test(x.textContent || "")); if (b) b.click(); });
await page.waitForSelector("#confirm", { state: "detached", timeout: 10000 }).catch(() => {});
fs.chmodSync(cfg.ledger, 0o644);
mark();
// 2. Clear on the third question: the card's own askClear wire; the row leaves with the next frame
await page.click(rowSel(cfg.g3) + ' [data-act="ntc-clear"]');
out.clearLatched = await page.evaluate((s) => { const r = document.querySelector(s); return r ? Array.from(r.querySelectorAll("button")).every((b) => b.disabled) : null; }, rowSel(cfg.g3));
out.afterClear = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g3), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterClear.box = await readBox();
mark();
// 3. Continue is NOT offered on the row (the user 2026-09-23: Reply and Clear only for now; the stored offer and its wire stay for a later
//    return): the second question shows Reply and Clear alone, and its Clear takes the row off like the first's
out.contButtons = await page.evaluate((s) => { const r = document.querySelector(s); return r ? Array.from(r.querySelectorAll(".ntc-actions button")).map((b) => b.textContent) : null; }, rowSel(cfg.g2));
out.contAct = await page.evaluate((s) => !!document.querySelector(s + ' [data-act="ntc-cont"]'), rowSel(cfg.g2));
await page.click(rowSel(cfg.g2) + ' [data-act="ntc-clear"]');
out.contLatched = await page.evaluate((s) => { const r = document.querySelector(s); return r ? Array.from(r.querySelectorAll("button")).every((b) => b.disabled) : null; }, rowSel(cfg.g2));
out.afterCont = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g2), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterCont.box = await readBox();
mark();
// 4. Reply on the first question: the composer takes the card (the chip with its title); the typed reply is a follow-up on the card and the row leaves once filed
await page.click(rowSel(cfg.g1) + ' [data-act="ntc-reply"]');
out.chip = await page.waitForFunction(() => { const c = document.querySelector("#composer .composer-chip .composer-chip-label"); return c ? c.textContent : null; }, null, { timeout: 15000 }).then((h) => h.jsonValue()).catch(() => null);
out.rowStaysOnReply = await page.evaluate((s) => !!document.querySelector(s), rowSel(cfg.g1));
await page.fill("#composer-input", cfg.reply);
await page.press("#composer-input", "Enter");
out.afterReply = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g1), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterReply.box = await readBox();
mark();
// 4b. a BRAND-NEW card with a long brief (the round-thirteen verifier): its row is built detached and joined after, so the disclosure must be
// measured once the row stands in the box; the button shows with no gesture
const w3 = await writeStore((st) => {
  st.nodes[cfg.g5] = { id: cfg.g5, text: cfg.g5q, parentId: null, nodeComplete: false, blocked: true, blockWhy: cfg.g5q, blockSummary: cfg.longBrief, cleared: false, trail: [],
    t: Math.floor(Date.now() / 1000), log: [{ ev_t: Math.floor(Date.now() / 1000), src: "planner", kind: "block", why: "asked: " + cfg.g5q, at: Math.floor(Date.now() / 1000) }] };
  st.status[cfg.g5] = "blocked"; });
out.fresh = await builtRecord(cfg.g5, w3, cfg.longBrief);
out.fresh.row = await page.waitForSelector(rowSel(cfg.g5), { timeout: 30000 }).then(() => true).catch(() => false);   // after the kernel's word
out.fresh.landed = await landedAt(rowSel(cfg.g5), cfg.longBrief); if (!out.fresh.landed) await onMiss(out.fresh); out.fresh.clipped = await clippedAt(rowSel(cfg.g5));   // the same holds: the brief on the row, its layout clipping it
out.fresh.more = await page.waitForSelector(rowSel(cfg.g5) + " .ntc-more", { timeout: 15000 }).then(() => true).catch(() => false);
out.fresh.box = await readBox();
mark();
// 5. the switch, through the settings card's OWN ROW (the user 2026-09-23, who did not find it): the kernel's settings page (the card the
//    shell's gear opens; the chat page hosts none and relays) in the same browser context, its Chat tab, the row under the head named for
//    where the box sits, visible; its click saves, the chat page hears the store change and the box hides, leaving the ring; a second click
//    brings the box back
const [sp] = await Promise.all([page.waitForEvent("popup"), page.evaluate((u) => { window.open(u, "_blank"); }, cfg.chat.replace("/chat?token=", "/settings?token="))]);   // a popup of the chat page: the SAME
//   context and store, so the chat page hears the save as a storage event (a page in another context is another store, and the default context spawns none by the API)
await sp.waitForLoadState("domcontentloaded").catch(() => {});
await sp.waitForSelector("#rs-needsbox", { state: "attached", timeout: 30000 }).catch(() => {});
await sp.evaluate(() => { const t = document.querySelector('#rs-tabs [data-tab="chat"]'); if (t) t.click(); });
out.switchRow = await sp.waitForFunction(() => { const cb = document.getElementById("rs-needsbox"); const pane = cb && cb.closest(".rs-pane"); return !!cb && !!pane && !pane.hidden && getComputedStyle(cb.closest("label")).display !== "none"; }, null, { timeout: 10000 }).then(() => sp.evaluate(() => {
  const cb = document.getElementById("rs-needsbox"); const lab = cb.closest("label"); let head = lab.previousElementSibling; while (head && !head.classList.contains("rs-sec")) head = head.previousElementSibling;   // loop-ok: walks up to the section head
  return { present: true, checked: cb.checked, label: (lab.querySelector("b") || {}).textContent, head: head ? head.textContent : null, headSection: head ? head.getAttribute("data-section") : null, pane: cb.closest(".rs-pane").getAttribute("data-pane") };
})).catch(() => ({ present: false }));
const setBox = async (on) => { await sp.evaluate((on) => { const cb = document.getElementById("rs-needsbox"); if (cb && cb.checked !== on) cb.click(); }, on); };
await setBox(false);
out.off = { hidden: await page.waitForFunction(() => { const b = document.getElementById("notices"); return !!b && b.style.display === "none"; }, null, { timeout: 10000 }).then(() => true).catch(() => false) };
out.off.box = await readBox();
await setBox(true);
await sp.close();
await foldTo(2);   // the rebuilt box (the switch's off-then-on) keeps the page's level for the session
out.on = { shown: await page.waitForFunction(() => { const b = document.getElementById("notices"); return !!b && b.style.display !== "none" && b.querySelectorAll(".ntc-row").length >= 1; }, null, { timeout: 10000 }).then(() => true).catch(() => false) };
out.on.moreAfterRebuild = await page.waitForSelector(rowSel(cfg.g5) + " .ntc-more", { timeout: 15000 }).then(() => true).catch(() => false);   // the rebuilt row (host.replaceChildren, then the rows built anew) wears the disclosure too
out.on.box = await readBox();
mark();
// 6. a HIDDEN pane (the first contributor's post-merge review of PR 1967): the chat page inside a display:none iframe lays nothing out, so a
// fresh long-brief row measured there reads zero by zero; a zero measure is no information, and the pane's return re-runs the pass
const shell = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await shell.goto(cfg.landing);                                                                     // the kernel's own shell: the chat pane is one of its iframes
let fr = null; for (let i = 0; i < 150 && !fr; i++) { fr = shell.frames().find((f) => /\/chat(\?|$)/.test(f.url())) || null; if (!fr) await shell.waitForTimeout(200); }   // loop-ok: bounded
out.hiddenPane = { frame: !!fr };
if (fr) {
  out.hiddenPane.loaded = await fr.waitForSelector("#notices .ntc-head", { timeout: 60000 }).then(() => true).catch(() => false);   // the box on screen once, collapsed to its header line (a fresh page)
  out.hiddenPane.collapsedFresh = await fr.evaluate(() => document.getElementById("notices").classList.contains("ntc-l0") && Array.from(document.querySelectorAll("#notices .ntc-row")).every((r) => getComputedStyle(r).display === "none"));   // collapsed by default: the rows attached and hidden
  await openNeedsBox(fr, 2);   // to the full context; a page without the levels (the base) shows everything already
  out.hiddenPane.rowsShown = await fr.waitForSelector("#notices .ntc-row", { timeout: 15000 }).then(() => true).catch(() => false);   // the rows visible at the full context
  out.hiddenPane.g5MoreBefore = await fr.waitForSelector(rowSel(cfg.g5) + " .ntc-more", { timeout: 15000 }).then(() => true).catch(() => false);   // the long-brief row's button stands before the hide
  await shell.evaluate(() => { window.__rompPaneToggle("chat", false); });                                                    // the rail hides the pane (display:none on its wrapper): the observer's word
  out.hiddenPane.hidden = await shell.waitForFunction(() => !document.body.classList.contains("po-chat"), null, { timeout: 10000 }).then(() => true).catch(() => false);
  const w4 = await writeStore((st) => {
    st.nodes[cfg.g6] = { id: cfg.g6, text: cfg.g6q, parentId: null, nodeComplete: false, blocked: true, blockWhy: cfg.g6q, blockSummary: cfg.longBrief, cleared: false, trail: [],
      t: Math.floor(Date.now() / 1000), log: [{ ev_t: Math.floor(Date.now() / 1000), src: "planner", kind: "block", why: "asked: " + cfg.g6q, at: Math.floor(Date.now() / 1000) }] };
    st.status[cfg.g6] = "blocked"; });
  Object.assign(out.hiddenPane, await builtRecord(cfg.g6, w4, cfg.longBrief));   // { id, floor, built }: the kernel's build event, read from the chat page's own fetch
  out.hiddenPane.row = await fr.waitForSelector(rowSel(cfg.g6), { state: "attached", timeout: 30000 }).then(() => true).catch(() => false);   // after the kernel's word
  out.hiddenPane.landed = await fr.waitForFunction((a) => { const r = document.querySelector(a.sel); const b = r && r.querySelector(".ntc-body"); return !!b && (b.textContent || "").trim() === a.brief; }, { sel: rowSel(cfg.g6), brief: cfg.longBrief }, { timeout: 30000 }).then(() => true).catch(() => false);
  if (!out.hiddenPane.landed) await onMiss(out.hiddenPane);
  out.hiddenPane.whileHidden = await fr.evaluate((a) => { const r = document.querySelector(a.g6); const b = r && r.querySelector(".ntc-body"); const g5 = document.querySelector(a.g5);
    return b ? { h: b.clientHeight, sh: b.scrollHeight, more: !!r.querySelector(".ntc-more"), g5More: !!(g5 && g5.querySelector(".ntc-more")) } : null; }, { g6: rowSel(cfg.g6), g5: rowSel(cfg.g5) });   // g5's button must stand: a zero measure removes nothing (the second contributor's post-merge note on PR 2018)
  await shell.evaluate(() => { window.__rompPaneToggle("chat", true); });                                                     // shown again
  out.hiddenPane.moreAfterShow = await fr.waitForSelector(rowSel(cfg.g6) + " .ntc-more", { timeout: 15000 }).then(() => true).catch(() => false);
  out.hiddenPane.clipped = await fr.evaluate((s) => { const r = document.querySelector(s); const b = r && r.querySelector(".ntc-body"); return !!b && b.scrollHeight > b.clientHeight + 1; }, rowSel(cfg.g6));
}
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


# the driver's budget. Its bounded waits sum to about 1170 s serially (every helper counted per call: the kernel's four 90 s deadlines, the
# 60 s row and card waits of the first scenes, the 30 s row waits that follow the kernel's word, the shorter button, dialog and frame waits, the
# 30 s frame loop), more than any per-test ceiling the runner gives (CI's served-page step runs pytest with --timeout=600, thread method), so
# the cap cannot be the sum: it is the ceiling less the SETUP the same per-test timer wraps (pytest-timeout's thread method times the first
# test's setUpClass too: the esbuild run and the healthz boot loop, bounded at about 60 to 120 s here), so a kernel that boots late and then
# stalls still hits this cap before the runner's, with the record below and the kernel's tail in hand rather than a bare per-test timeout
# that also skips every later served test in the process (the second contributor's read of PR 2038). A driver that runs past it has hit
# several deadlines in a row; the driver prints a PARTIAL line after every scene, and _result reports the last one with the kernel's tail.
DRIVER_TIMEOUT_S = 480


def _block(t, why):
    return {"ev_t": t, "src": "planner", "kind": "block", "why": why, "at": t}


class NeedsYouBoxChatServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="needs-you-box-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "goals", os.path.join("postal", "quarantine")):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "names", SID).write_text("web\t%s\t#9cd2ff\t#0c1a2e\n" % cwd)
        # alive: the box's Continue button needs a LIVE session (_needs_you_rows: `cont` is the card's live bit), so the Continue and Reply legs
        # reach the SDK backend for web, which on a box without the SDK logs "sdk session web crashed: ModuleNotFoundError" once per send and the
        # leg still passes (the reply is filed as the card's follow-up). The briefs' landing never depends on the backend: the box rows come from
        # the feed build of the store and ride the chat signature by value. Session hosts stay off (below), so no romp-session-host starts.
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        # api: one question and no hard stop, so its tab wears the Needs you ring (the switch leg reads it: web's red ring is painted
        # first and alone, so a regression dropping the magenta ring would pass on web's tab); web stays first, the active tab
        Path(state, "names", API).write_text("api\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(state, "sdk", API + ".json").write_text(json.dumps(
            {"sid": API, "name": "api", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": API, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        Path(state, "session-order.json").write_text(json.dumps([SID, API]))
        Path(state, "cleared.jsonl").write_text("")      # present, so the refused-clear leg can take its write bit away and give it back
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs, parent = [], None
        for i in range(6):
            u, a = "u%d" % i, "a%d" % i
            recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t0 + 10 * i), "sessionId": SID, "promptSource": "typed",
                         "message": {"role": "user", "content": "question %d about the notes api" % i}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": iso(t0 + 10 * i + 4), "sessionId": SID,
                         "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": "answer %d: the notes api keeps its shape." % i}]}})
            parent = a
        # the session is STOPPED on an API error only the user can clear (the transcript's last record, Claude Code's
        # isApiErrorMessage shape, "prompt is too long"): its focus goal (the store's lastNode) floors as a live block, the hard stop
        recs.append({"type": "user", "uuid": "u6", "parentUuid": parent, "timestamp": iso(t0 + 60), "sessionId": SID, "promptSource": "typed",
                     "message": {"role": "user", "content": "wire the fixtures directory into the integration suite"}})
        recs.append({"type": "assistant", "uuid": "e6", "parentUuid": "u6", "timestamp": iso(t0 + 62), "sessionId": SID, "isApiErrorMessage": True,
                     "apiErrorStatus": 400, "error": "invalid_request",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "API Error: 400 prompt is too long"}]}})
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "states", SID + ".jsonl").write_text(json.dumps({"t": t0 + 70, "state": "idle"}) + "\n")
        # three questions the judges filed (diary events in the fold's shape, so the rollup keeps the flags), and the working focus goal
        cls.g = [SID + ":g%d" % i for i in range(1, 5)]
        nodes, status = {}, {}
        for i, q in enumerate(QUESTIONS):
            g = cls.g[i]
            nodes[g] = {"id": g, "text": q, "parentId": None, "nodeComplete": False, "blocked": True, "blockWhy": q, "cleared": False, "trail": [],
                        "t": t0 + 100 + i, "log": [_block(t0 + 200 + i, "asked: " + q)]}
            status[g] = "blocked"
        g4 = cls.g[3]
        nodes[g4] = {"id": g4, "text": "wire the fixtures directory into the integration suite", "parentId": None, "nodeComplete": False, "blocked": False,
                     "cleared": False, "trail": [], "t": t0 + 300, "log": []}
        status[g4] = "working"
        cls.store = os.path.join(state, "goals", SID + ".json")
        Path(cls.store).write_text(json.dumps(
            {"rompUuid": SID, "seq": 5, "lastNode": g4, "closedTurns": [], "nodes": nodes, "placements": {}, "status": status}))
        cls.ledger = os.path.join(state, "cleared.jsonl")
        cls.order = os.path.join(state, "session-order.json")
        Path(proj, API + ".jsonl").write_text(json.dumps(
            {"type": "user", "uuid": "p1", "parentUuid": None, "timestamp": iso(t0 + 20), "sessionId": API, "promptSource": "typed",
             "message": {"role": "user", "content": "set up the api fixtures"}}) + "\n" + json.dumps(
            {"type": "assistant", "uuid": "q1", "parentUuid": "p1", "timestamp": iso(t0 + 24), "sessionId": API,
             "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": API_Q}]}}) + "\n")
        Path(state, "states", API + ".jsonl").write_text(json.dumps({"t": t0 + 30, "state": "idle"}) + "\n")
        ga = API + ":g1"
        Path(state, "goals", API + ".json").write_text(json.dumps(
            {"rompUuid": API, "seq": 1, "lastNode": ga, "closedTurns": [], "placements": {}, "status": {ga: "blocked"},
             "nodes": {ga: {"id": ga, "text": "set up the api fixtures", "parentId": None, "nodeComplete": False, "blocked": True, "blockWhy": API_Q,
                            "cleared": False, "trail": [], "t": t0 + 20, "log": [_block(t0 + 25, "asked: " + API_Q)]}}}))
        # a message from a DIRECTED peer, held for the user's decision: a needs-you notice with Approve and Deny at the first build
        Path(state, "postal", "quarantine", MID + ".json").write_text(json.dumps(
            {"mid": MID, "to": "web", "toId": SID, "frm": "api", "frmId": "11111111-2222-3333-4444-666666666666",
             "body": "the README draft is ready for a look, could you check the parser section before the release?",
             "kind": "coordinate", "origin": "TESTHOST", "via": "peer", "at": int(time.time()) - 600}))
        cls.port = _free_port()
        cls.token = "testtok-needsbox"
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
            cfg = os.path.join(self.lab, "needsbox.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"chat": base + "/chat?token=" + self.token, "feed": base + "/feed?token=" + self.token, "feedJson": base + "/feed.json?token=" + self.token, "perf": base + "/perf?token=" + self.token, "sid": SID, "api": API, "g1": self.g[0], "g2": self.g[1], "g3": self.g[2], "g4": self.g[3],
                           "reply": "Postgres, the same as production", "store": self.store, "brief": BRIEF, "longBrief": LONG_BRIEF, "g5": SID + ":g5", "g5q": "should the fixtures use the production database name or a scratch one?", "g6": SID + ":g6", "g6q": "which of the two fixture loaders should the CI job run first?", "landing": base + "/?token=" + self.token, "ledger": self.ledger, "order": self.order}, f)
            driver = os.path.join(self.lab, "needsbox.mjs")
            Path(driver).write_text(_lab.NEEDS_BOX_OPEN_JS + DRIVER)   # the fold helper the held-mail lab shares
            try:
                p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=DRIVER_TIMEOUT_S,
                                   env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            except subprocess.TimeoutExpired as e:
                # the driver ran past its budget (several deadlines in a row): say the record it had reached and what the kernel's tail says, instead
                # of a bare traceback in every test (the second contributor's read of PR 2031)
                out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
                partial = next((ln for ln in reversed(out.splitlines()) if ln.startswith("PARTIAL:")), "(no scene completed)")
                type(self)._fail = "the driver ran past its %d s budget; its record so far: %s; kernel: %s" % (DRIVER_TIMEOUT_S, partial[-3000:], self._kernel_tail())
                self.fail(type(self)._fail)
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        return self._r

    def _built(self, rec, what):
        """The kernel's own build event for a store write, as the driver recorded it: the floor an int of at least 0 (a null floor is the
        pre-write read's own miss), the build id past it (never None, never the floor; a bool passed the old not-None check, since the async
        predicate under waitForFunction resolved at once with False: the second contributor's read of PR 2031). The message prints the record."""
        rec = {k: v for k, v in rec.items() if k != "box"}
        self.assertIsInstance(rec.get("floor"), int, "%s: the feed build id before the write was read (a null floor is its own miss): %r (kernel: %s)" % (what, rec, self._kernel_tail()))
        self.assertGreaterEqual(rec["floor"], 0)
        self.assertIsNotNone(rec.get("built"), "%s: the kernel's feed rebuilt past the write with the brief on the card, polled from the driver (GET /feed.json; a miss carries the pusher's counters): %r (kernel: %s)" % (what, rec, self._kernel_tail()))
        self.assertGreater(rec["built"], rec["floor"], "%s: the build id is past the floor: %r" % (what, rec))

    def _kernel_tail(self):
        try:
            return open(self.klog).read()[-1200:]
        except OSError:
            return ""

    def test_the_box_lists_the_questions_and_the_held_message_under_the_header_in_the_token_and_no_row_for_the_hard_stop(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertTrue(r["fourRows"], "four rows within a minute: %r (kernel: %s)" % (r["first"], self._kernel_tail()))
        b = r["first"]
        self.assertTrue(b["shown"], "the box shows")
        self.assertEqual(b["head"], "Needs you · 4", "the header: the title with the count")
        self.assertEqual((b["border"], b["borderLeft"], b["dot"]), (TOKEN_RGB, "1px", TOKEN_RGB), "one thin edge and the dot in the Needs you token: %r" % b)
        ids = [x["id"] for x in b["rows"]]
        self.assertEqual(ids[:3], self.g[:3], "the three questions first, in the frame's order: %r" % ids)
        self.assertEqual(ids[3], "notice:%s:%s:1" % (SID, MID), "then the held message")
        self.assertNotIn(self.g[3], ids, "the hard stop (the focus goal under the on-you API error) has no row")
        hard = r["hardStop"]
        self.assertEqual(hard["col"], "col-needsInput-list", "the feed pane files the focus goal's card under Needs you from the same pushed frame: %r" % hard)
        self.assertTrue(any("Prompt too long" in t for t in hard["badges"]), "wearing the on-you API error badge, the hard stop the box leaves out: %r" % hard)
        self.assertTrue(any(x["id"] == self.g[0] for x in b["rows"]), "the questions are on the box while the hard stop is not")
        for row, q in zip(b["rows"][:3], QUESTIONS):
            self.assertEqual(row["title"], q, "the card's text is the row's title")
            self.assertEqual(row["buttons"], ["Reply", "Clear"], "a live session's question: Reply and Clear (the user 2026-09-23: no Continue button for now)")
            self.assertEqual(row["disabled"], [False, False], "two buttons, both live")
        self.assertEqual(b["rows"][3]["buttons"], ["Approve", "Deny"], "the held message keeps its stored actions")
        self.assertIn("ring-needs-you", b["tabClasses"] or "", "the tab wears the red Blocked ring for the hard stop (it outranks the Needs you ring): %r" % b["tabClasses"])
        self.assertIn("ring-waiting-on-you", (b["tabs"] or {}).get(API) or "", "api's tab, a question and no hard stop, wears the Needs you ring: %r" % b["tabs"])

    def test_a_brief_landing_on_a_card_reaches_its_row_with_no_gesture(self):
        r = self._result()
        self._built(r["brief"], "the short brief")
        self.assertTrue(r["brief"]["landed"], "the row's body follows the brief written to the store within the next frames: %r (kernel: %s)" % (r["brief"], self._kernel_tail()))
        row = next((x for x in r["brief"]["box"]["rows"] if x["id"] == self.g[0]), None)
        self.assertEqual(row and row["body"].strip(), BRIEF, "the brief is the row's body (the face renders it as markdown, with its trailing newline)")
        self.assertEqual(r["brief"]["box"]["head"], "Needs you · 4", "and nothing else moved")

    def test_a_long_brief_gets_a_disclosure_on_its_row_that_lifts_the_clamp_and_folds_back(self):
        """The second contributor's review (2026-09-22): the row clamped the brief to four lines with no way to the rest. A More button
        shows once the body overflows, opens the row (the clamp lifted, the whole brief on screen), reads Less, and folds the row back."""
        r = self._result()
        m = r["more"]
        self._built(m, "the long brief")
        self.assertTrue(m["landed"], "the long brief reaches the row after the kernel's build (the read waits for it): %r (kernel: %s)" % ({k: v for k, v in m.items() if k != "box"}, self._kernel_tail()))
        self.assertTrue(m["clipped"], "and the layout clips it at four lines (the brief is long enough for any width): %r" % m["before"])
        self.assertTrue(m["shown"], "the More button shows on a brief past the clamp: %r" % m)
        self.assertEqual((m["before"] or {}).get("label"), "More"); self.assertEqual((m["before"] or {}).get("open"), False)
        self.assertTrue((m["before"] or {}).get("clipped"), "the body hides lines before the click: %r" % m["before"])
        self.assertEqual((m["before"] or {}).get("clamp"), "4", "the clamp stands on a closed row")
        self.assertTrue(m["open"], "the click opens the row")
        self.assertEqual((m["after"] or {}).get("clamp"), "none", "the clamp lifted: %r" % m["after"])
        self.assertFalse((m["after"] or {}).get("clipped"), "the whole brief is on screen")
        self.assertEqual((m["after"] or {}).get("label"), "Less"); self.assertEqual((m["after"] or {}).get("text"), LONG_BRIEF)
        self.assertTrue(m["closed"], "the second click folds the row back")
        self.assertEqual(m["box"]["head"], "Needs you · 4", "a disclosure is not a decision: nothing else moved")

    def test_a_brand_new_long_brief_row_and_a_rebuilt_row_both_get_the_disclosure(self):
        """The round-thirteen verifier (2026-09-22): the disclosure was measured while the row was still detached (built, then joined), so a
        fresh row with a long brief never got its button, nor did the rows the switch's off-then-on rebuilt; the first scene passed because it
        mutated a row already in the document. The measure runs over the rows once they stand in the box."""
        r = self._result()
        self._built(r["fresh"], "the fresh row")
        self.assertTrue(r["fresh"]["row"], "the new card's row arrives: %r (kernel: %s)" % ({k: v for k, v in r["fresh"].items() if k != "box"}, self._kernel_tail()))
        self.assertTrue(r["fresh"]["landed"] and r["fresh"]["clipped"], "with its long brief, clipped: %r" % r["fresh"])
        self.assertTrue(r["fresh"]["more"], "and wears the More button with no gesture (before: measured detached, 0 by 0, no button): %r" % r["fresh"]["box"])
        self.assertTrue(r["on"]["shown"]); self.assertTrue(r["on"]["moreAfterRebuild"], "the rebuilt row wears it too (before: none after the switch's off-then-on)")

    def test_a_pane_hidden_while_a_long_brief_row_arrives_gets_its_disclosure_when_shown(self):
        """The first contributor's post-merge review of PR 1967 (low 1): a disclosure measured in a display:none pane read zero by zero and
        removed a closed row's button or left a fresh row without one until the next repaint. A zero measure is no information, and the
        chat visibility watcher's return edge (hidden, then visible) re-runs the pass, so the button appears when the pane is shown."""
        r = self._result(); h = r["hiddenPane"]
        self._built(h, "the hidden pane's row")   # the fourth scene's record, asserted (the second contributor's read of PR 2031: recorded and read by nothing)
        self.assertTrue(h["frame"] and h["loaded"] and h["hidden"] and h["row"] and h["landed"], "the shell's chat pane, shown once then hidden by the rail, builds the fresh row with its brief while hidden: %r (kernel: %s)" % (h, self._kernel_tail()))
        self.assertEqual((h["whileHidden"] or {}).get("h"), 0, "hidden, the body measures zero: %r" % h["whileHidden"])
        self.assertTrue(h["g5MoreBefore"], "the earlier long-brief row's button stood before the hide")
        self.assertTrue((h["whileHidden"] or {}).get("g5More"), "and stands while hidden: a zero measure is no information (with the guard deleted the pass removes it): %r" % h["whileHidden"])
        self.assertTrue(h["moreAfterShow"], "shown, the pane's return re-measures and the button appears (before: none until the next repaint): %r" % h)
        self.assertTrue(h["clipped"], "and the brief is clipped at four lines once laid out")

    def test_a_clear_the_clears_log_refuses_leaves_the_row_and_re_arms_its_buttons_and_says_so(self):
        r = self._result()
        d = r["refused"]
        self.assertIn("That clear did not land", d["dialog"] or "", "the dialog says so: %r" % d["dialog"])
        self.assertIn("nothing was cleared", d["dialog"] or "")
        self.assertTrue(d["rearmed"], "the row's buttons let go on the kernel's reply (they latched on the press): %r" % d["box"])
        self.assertIn(self.g[2], [x["id"] for x in d["box"]["rows"]], "the row stays")
        self.assertEqual(d["box"]["head"], "Needs you · 4")
        self.assertEqual(d["rowErr"], "That clear did not land", "and the row says why, the frame's title alone (the verifier's low: no doubled refusal): %r" % d["rowErr"])

    def test_clear_takes_its_row_off_the_box_with_the_next_frame(self):
        r = self._result()
        self.assertTrue(r["clearLatched"], "the row's buttons latch on the press")
        self.assertTrue(r["afterClear"]["left"], "the cleared question's row left: %r (kernel: %s)" % (r["afterClear"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterClear"]["box"]["head"], "Needs you · 3")

    def test_continue_is_not_offered_and_the_second_question_clears_like_the_first(self):
        """The user 2026-09-23: Reply and Clear only for now. The stored offer (the row's cont) and the card's Continue wire stay for a later
        return; the button is gone from the row, and the row's Clear works as the first question's did."""
        r = self._result()
        self.assertEqual(r["contButtons"], ["Reply", "Clear"], "the live question offers Reply and Clear alone")
        self.assertFalse(r["contAct"], "no Continue control on the row")
        self.assertTrue(r["contLatched"], "the row's buttons latch on the press")
        self.assertTrue(r["afterCont"]["left"], "the cleared question's row left: %r (kernel: %s)" % (r["afterCont"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterCont"]["box"]["head"], "Needs you · 2")

    def test_the_box_is_collapsed_by_default_and_opens_in_two_steps_in_both_themes(self):
        """The user 2026-09-23: collapsed by default like the awaiting box, and successively expandable. Level 0: the header line alone (the label
        with the count), the rows hidden. One click: the items (each title with its buttons), the background paragraphs hidden. A second: the
        full context, the background under each title. The level is the page's state for the session, never a timer; a fresh page starts
        collapsed. Read at each level in the dark theme and the light one."""
        r = self._result()
        for t in ("dark", "light"):
            l0, l1, l2 = r["levels"][t + "0"], r["levels"][t + "1"], r["levels"][t + "2"]
            self.assertEqual((l0["theme"], l1["theme"], l2["theme"]), (t, t, t))
            self.assertEqual((l0["level"], l0["head"], l0["headVisible"]), (0, "Needs you · 4", True), "%s: collapsed, the header line alone: %r" % (t, l0))
            self.assertEqual((set(l0["rowsVisible"]), l0["caret"]), ({False}, "\u25b8"), "%s: level 0 shows no row, the caret pointing right: %r" % (t, l0))
            self.assertEqual((l1["level"], set(l1["rowsVisible"]), set(l1["bodiesVisible"])), (1, {True}, {False}), "%s: one click shows the items and no background: %r" % (t, l1))
            self.assertEqual([row["buttons"] for row in l1["rows"]], [["Reply", "Clear"]] * 3 + [["Approve", "Deny"]], "%s: the buttons stand at level 1" % t)
            self.assertEqual((l2["level"], set(l2["rowsVisible"]), l2["caret"]), (2, {True}, "\u25be"), "%s: a second click shows the full context, the caret down: %r" % (t, l2))
            self.assertTrue(any(l2["bodiesVisible"]), "%s: at level 2 a background paragraph shows where the row has one: %r" % (t, l2))
        self.assertTrue(r["hiddenPane"].get("collapsedFresh"), "a fresh page starts collapsed: %r" % r["hiddenPane"])

    def test_reply_points_the_composer_at_the_card_and_the_typed_reply_takes_the_row_off(self):
        r = self._result()
        self.assertEqual(r["chip"], QUESTIONS[0], "the composer's chip names the card, as a feed card click that lands in the chat does")
        self.assertTrue(r["rowStaysOnReply"], "Reply alone leaves the row: the reply is not written yet")
        self.assertTrue(r["afterReply"]["left"], "the typed reply is a follow-up on the card and its row left: %r (kernel: %s)" % (r["afterReply"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterReply"]["box"]["head"], "Needs you · 1", "the held message alone remains")

    def test_the_switch_hides_the_box_and_leaves_the_ring_and_back_on_the_box_returns(self):
        """The user 2026-09-23, who looked for the switch and did not find it: the settings card's own row, under a head named for where the
        box sits, on the Chat tab; its click saves and hides the box, a second brings it back."""
        r = self._result()
        sw = r["switchRow"]
        self.assertTrue(sw.get("present"), "the row renders on the Chat tab: %r" % sw)
        self.assertEqual((sw["pane"], sw["label"], sw["head"], sw["headSection"], sw["checked"]), ("chat", "Needs you box", "Boxes below the transcript", "boxes", True), "a plainly labelled row under its own head, on by default: %r" % sw)
        self.assertTrue(r["off"]["hidden"], "the box hides on the row's save: %r" % r["off"]["box"])
        self.assertIn("ring-needs-you", r["off"]["box"]["tabClasses"] or "", "the red ring stays: the switch is the box's alone")
        self.assertIn("ring-waiting-on-you", (r["off"]["box"]["tabs"] or {}).get(API) or "", "and the Needs you ring on api's tab stays too: %r" % r["off"]["box"]["tabs"])
        self.assertTrue(r["on"]["shown"], "back on, the box returns with its rows: %r" % r["on"]["box"])
        self.assertIn("ring-waiting-on-you", (r["on"]["box"]["tabs"] or {}).get(API) or "")


if __name__ == "__main__":
    unittest.main()
