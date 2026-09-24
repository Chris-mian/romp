#!/usr/bin/env python3
"""Reordering a tab by drag lands it where the cursor was released (the user 2026-09-11, who could drag a
tab to the FIRST slot of a row but nowhere else: every other release put the tab somewhere other than under
the cursor). Their strip wraps onto two rows, a tag group on the first and the untagged trail on the second,
and the trail's row is where the drop lands wrong; a drag within the group's row still works.

The strip's drag is HTML5 drag-and-drop (render.ts wireTabDrag: dragstart / the #tabs dragover / drop). The
dragover hit-tests the pointer against a VIRTUAL wrap layout of the non-dragged items (dragslot.ts
dragSlotIndex): widths snapshotted at dragstart, the strip's flex-wrap simulated, the pointer's row read as
floor(y / rowH), and the slot as the first simulated midpoint right of x. With the tab groups on, the
untagged trail sits behind a zero-height ROW BREAK (makeRowBreak, .tab-group-break.tab-group-sep), which the
dragover maps to a zero-width box that opens a virtual row (`br`, T264), and it marks the box AFTER any
break as a row opener too (`br: isBreak(t) || isBreak(before(t))`): the trail's first TAB wears `br`. The
simulation's guard against opening an empty row is `cx > 0` (dragslot.ts), where cx is the row's fill so
far, and a zero-width box still adds the strip's column gap to it. Under the yatharth theme the strip has a
3px column gap (styles.css `body.chat-theme-yatharth #tabs { gap: 0 3px }`), so after the break cx is 3, the
guard fails, and the trail's first tab opens a THIRD virtual row: the break sits alone on the row that
floor(y / rowH) resolves the trail's pointer to, with a single midpoint at 0, every x on the row is past it,
and the slot falls to the next row's head, the trail's first tab. Every drop on the untagged row lands at
its first position, which is why a drag to the first slot is the one that works. Under the classic theme
the gap is 0, cx stays 0 after the break, and the row holds the trail's tabs as the strip does, so the
classic strip (and T264's own tests) never showed it. Present since T264 (74412c04, one group per row, the
layout in which the trail has a row of its own); a fix in the simulation (a zero-width row opener adding no
gap) was tried and reverted here, and it lands every one of these drops under the cursor.

This lab drives the real /chat page of a hermetic kernel: twenty sessions, three under one tag (the group's
row), two under a second tag (its own row) and fifteen in no tag (the trail's row), REAL mouse drags (page.mouse
down, a run of moves across the strip, up over the target tab), the tab order read from the DOM and from the
persisted arrangement (romp:vieworder:shared, the kernel's arrangement as this browser caches it). The classic theme
is the control; the yatharth theme is set the way the
user sets it, the `theme` key of the romp:settings store (theme.ts and the kernel's inline reader turn it into
the body class).

FOLDED NEIGHBOURS SHARE A ROW (the user 2026-09-16): a folded group is one small header, yet each took a whole
row; now a folded header right after another folded header is PACKED onto its row (tab-groups.ts planStrip
`packed`: no row break ahead of it), while an open group and the trail keep rows of their own. The last phase
folds both groups by a click on each header and measures the layout: the two headers on one row (equal tops, no
break between them, the two boxes side by side and their chips apart), the trail on the row below; drags on the
trail's row still land under the cursor (the dragover marks a header `br` only when a break precedes it, so the
virtual layout has the packed row as ONE row, as the strip does; with a row per folded group the pointer's row
would read one too low and every trail drop would miss); a drop released between the two headers lands at the
trail's head in the global order, and (since the gesture below) JOINS the first of the two, whose row that slot
ends; a drop released ahead of the FIRST header is the strip's head, not the ungrouped row, and takes no tag off;
a header dragged across the shared row still reorders the groups; and with one of the two opened again the folded
one keeps a row of its own between the open group's row and the trail's. Then the same packed layout under the
classic theme (gap 0).

DRAGGING A TAB INTO AND OUT OF A GROUP (the user 2026-09-23): the place a tab is dropped states where it should
appear now. A group IS a tag, so a drop inside a group's row puts the session in it (that tag added, at the slot
the cursor named) and leaves its other tags alone; the ungrouped row is NOT a group but the sessions carrying no
tags, so a drop there clears EVERY tag. That asymmetry is the rule. The last phase drives the whole chain on the
real page: an untagged tab into an open group, a tab already in the group (position moves, nothing is written),
on into a second group (it renders under both), the two-tag session cleared by a drop on the ungrouped row,
dragged back into ONE group (which restores that tag alone — reversibility is one tag, not the set), cleared
again, the ungrouped row to itself, a group's tab released ahead of the first header (the strip's head: nothing
is cleared), and a drop on a folded group's bare header. Tags are read from the KERNEL'S OWN views store, never
the DOM alone. The cue is measured mid-gesture too: the group about to be joined wears the accent ring, a release
that would clear tags names them all before the release — the whole safety, since there is no undo stack — and a
drag that only reorders shows neither.

Each case records the row layout (every tab's left/top/width), the release point and the landing rect, and
expects the tab to sit where the pointer was released: after every other tab on the release row whose
midpoint is left of the cursor once the dragged tab is taken out of the row (the pre-drag layout, the strip's
own virtual model), before the rest. The log each case keeps (every drag event's target and acceptance, the
strip's rebuilds) says, when a case fails, whether a drop reached the strip at all. Skips LOUDLY without the
extension deps or a Playwright browser. SYNTHETIC fixtures only (the notes-api demo world, host TESTHOST,
placeholder sids). TAB_DRAG_DIST=<dir> serves another tree's UI bundle (the bisect's before);
TAB_DRAG_DUMP=<path> writes the whole measurement; TAB_DRAG_SHOTS=<prefix> writes strip screenshots of the packed layouts."""
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

# the notes-api demo world: twenty sessions, so the untagged trail is a long row of its own
NAMES = ["web", "api", "deploy", "tests", "docs", "auth", "search", "cache", "ingest", "export", "billing", "mailer",
         "worker", "scheduler", "metrics", "backup", "importer", "notifier", "gateway", "indexer"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]
TAGGED = ["web", "api", "deploy"]   # the infra group: the strip's first row
QA = ["tests", "docs"]              # the qa group: the second row; folded beside a folded infra, the two pack onto one row
TAGS = [{"id": "tag-infra", "name": "infra", "color": "#4EC9B0", "members": [SIDS[n] for n in TAGGED]},
        {"id": "tag-qa", "name": "qa", "color": "#c98cff", "members": [SIDS[n] for n in QA]}]
TRAIL = [n for n in NAMES if n not in TAGGED and n not in QA]


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
const page = await browser.newPage({ viewport: { width: 1900, height: 760 } });   // wide: the trail's seventeen tabs on one row
// the gesture's log: every drag event with its target and whether the page accepted it (defaultPrevented, read on the
// window, after the strip's own listener), plus every wholesale rebuild of #tabs (a burst of child removals), so a case
// that moved nothing says whether a drag happened, whether a drop reached the strip, and what stood under the pointer
await page.addInitScript(() => {
  window.__log = [];
  const L = (k, e) => window.__log.push({ k, t: Math.round(performance.now()), x: e ? Math.round(e.clientX) : null, y: e ? Math.round(e.clientY) : null,
    tgt: e && e.target ? String(e.target.className || e.target.nodeName) + (e.target.dataset && e.target.dataset.id ? "#" + e.target.dataset.id.slice(0, 8) : "") : null,
    prevented: e ? e.defaultPrevented : null });
  for (const k of ["dragstart", "dragover", "dragenter", "dragleave", "drop", "dragend", "pointercancel"]) window.addEventListener(k, (e) => L(k, e));
  // the kernel's frames, watched for a marker (a renamed session's new name): the event that says a push has LANDED on the
  // page, whatever the strip does with it
  window.__wsMarker = null; window.__wsMarkerSeen = false;
  const OrigWS = window.WebSocket;
  window.WebSocket = function (...a) { const ws = new OrigWS(...a);
    ws.addEventListener("message", (m) => { if (window.__wsMarker && typeof m.data === "string" && m.data.includes(window.__wsMarker)) { window.__wsMarkerSeen = true; L("push:" + window.__wsMarker, null); } });
    return ws; };
  window.WebSocket.prototype = OrigWS.prototype; Object.assign(window.WebSocket, OrigWS);
  const watch = () => { const bar = document.getElementById("tabs"); if (!bar) { setTimeout(watch, 50); return; }
    new MutationObserver((muts) => { const removed = muts.reduce((n, m) => n + m.removedNodes.length, 0);
      if (removed > 2) L("rebuild:-" + removed, null); }).observe(bar, { childList: true }); };
  watch();
});
const settle = async (n = cfg.count) => {   // n: the tabs the strip shows (a folded group's members have none)
  await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
  await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, n, { timeout: 30000 });
  await page.waitForTimeout(800);
};
await page.goto(cfg.chat);
await settle();
const r1 = (v) => Math.round(v * 10) / 10;
// THE KERNEL'S OWN VIEWS STORE, read per gesture: which tag holds which session. The drag's tag writes (drag
// into a group adds the tag, a drop on the ungrouped row takes the dragged copy's off) are asserted from here,
// not from the DOM alone — the store is the authority the strip only renders.
// a stored member is the canonical {host, sid} pair (kernel.py _member_pair); the legacy plain sid and the
// viewer-relative "host:sid" string read the same way
const memberSid = (m) => (m && typeof m === "object" ? String(m.sid || "") : String(m == null ? "" : m));
const tagsOf = () => {
  try { const v = JSON.parse(fs.readFileSync(cfg.views, "utf8"));
        return Object.fromEntries((v.tags || []).map((t) => [t.name, (t.members || []).map(memberSid)])); }
  catch (e) { return null; }
};
const tagsIn = (m, sid) => Object.keys(m || {}).filter((n) => m[n].some((x) => x.endsWith(sid))).sort();
const tagsFor = (sid) => tagsIn(tagsOf(), sid);
// …and the wait for one: a tag write lands in the store before its ack, so the event to wait on is the store
// answering differently. Bounded, and the caller records whether it ever did.
const waitTags = async (sid, before) => {
  for (let i = 0; i < 60; i++) {
    if (JSON.stringify(tagsFor(sid)) !== JSON.stringify(before)) return true;
    await page.waitForTimeout(100);
  }
  return false;
};
// the strip's layout: every #tabs child with its rect in the bar's own space, the tabs grouped into rows by top
const layout = async () => { const L = await pageLayout(); L.tags = tagsOf(); return L; };
const pageLayout = () => page.evaluate(() => {
  const bar = document.getElementById("tabs"); const b = bar.getBoundingClientRect();
  const r1 = (v) => Math.round(v * 10) / 10;
  const items = Array.from(bar.children).map((el) => { const r = el.getBoundingClientRect();
    const chip = el.querySelector(".tab-group-chip"), c = chip ? chip.getBoundingClientRect() : null;   // a header's tag chip: how far apart two packed headers' labels sit
    return { cls: el.className, id: el.dataset.id || null, group: el.dataset.group || null,
             copy: el.dataset.copy === undefined ? null : el.dataset.copy,   // T264b: which group's row this COPY sits in ("" = the untagged trail)
             name: el.dataset.id ? (el.querySelector(".tab-label") || el).textContent.trim() : el.className,
             top: r1(r.top - b.top), left: r1(r.left - b.left), w: r1(r.width), h: r1(r.height), draggable: !!el.draggable,
             chip: c ? { left: r1(c.left - b.left), right: r1(c.right - b.left) } : null }; });
  const tabs = items.filter((i) => i.id);
  const tops = [...new Set(tabs.map((t) => t.top))].sort((a, b) => a - b);
  const rows = tops.map((top) => tabs.filter((t) => t.top === top));
  let stored = null; try { stored = JSON.parse(localStorage.getItem("romp:vieworder:shared")); } catch (e) {}
  return { bar: { left: b.left, top: b.top, w: r1(b.width), h: r1(b.height), clientWidth: bar.clientWidth, gap: getComputedStyle(bar).columnGap },
           theme: document.body.classList.contains("chat-theme-yatharth") ? "yatharth" : "classic",
           items, tabs, rows, order: tabs.map((t) => t.id), stored };
});
const cases = [];
const fmt = (rows) => rows.map((r) => r.map((t) => t.name + "@" + t.left + "," + t.top + "+" + t.w + "x" + t.h));
// measure a finished gesture: where the cursor is, by the strip's own rule, is after every other tab whose midpoint is
// left of the cursor on the cursor's row, and after every tab on the rows above it — the other tabs as they stand with
// the dragged one taken out of its row (the PRE-drag layout, each tab right of it on its row moved left by its width and
// the gap: the strip's own virtual model). Never the settled layout: a wrong landing reshapes that, and an expectation
// read from it moves with the mistake.
async function record(label, pre, src, tgt, tx, ty, extra) {
  const log = await page.evaluate(() => window.__log);
  const post = await layout();
  const nameOf = (id) => (pre.tabs.find((t) => t.id === id) || { name: id }).name;
  post.tabs.forEach((t) => { t.name = nameOf(t.id); });   // one name per tab across the gesture, by id (a push may have renamed one)
  const cx = r1(tx - pre.bar.left), cy = r1(ty - pre.bar.top);
  const gap = parseFloat(pre.bar.gap) || 0;
  const others = pre.tabs.filter((t) => t.id !== src.id);
  const onRow = (t) => t.top <= cy && cy < t.top + t.h;
  const leftOf = (t) => (t.top === src.top && t.left > src.left) ? t.left - src.w - gap : t.left;
  const expected = others.filter((t) => t.top + t.h <= cy || (onRow(t) && leftOf(t) + t.w / 2 < cx)).length;
  const actual = post.order.indexOf(src.id);
  const landed = post.tabs.find((t) => t.id === src.id);
  const count = (k) => log.filter((e) => e.k === k).length;
  cases.push({ label, theme: post.theme, gap: post.bar.gap,
               from: { name: src.name, index: pre.order.indexOf(src.id), draggable: src.draggable },
               over: tgt ? { name: tgt.name, left: tgt.left, w: tgt.w, top: tgt.top } : null,
               release: { x: cx, y: cy }, expected, actual, ok: expected === actual,
               landed: landed ? { left: landed.left, right: r1(landed.left + landed.w), top: landed.top,
                                  cursorInside: landed.left <= cx && cx <= landed.left + landed.w && landed.top <= cy && cy < landed.top + landed.h } : null,
               preRows: fmt(pre.rows), postRows: fmt(post.rows), preOrder: pre.order.map(nameOf), postOrder: post.order.map(nameOf),
               stored: Array.isArray(post.stored) ? post.stored.map(nameOf) : post.stored,
               // the TAG evidence, from the kernel's own store: what the dragged session held before and after,
               // which copies the strip draws for it now (T264b: one per tag, "" = the untagged trail), and where
               // the copy that matters sits among its group's members
               tags: { before: pre.tags && tagsIn(pre.tags, src.id), after: tagsFor(src.id) },
               copies: post.tabs.filter((t) => t.id === src.id).map((t) => t.copy),
               inGroups: Object.fromEntries([...new Set(post.tabs.map((t) => t.copy))].map((c) =>
                 [c === null ? "flat" : c, post.tabs.filter((t) => t.copy === c).map((t) => t.name)])),
               ...(extra || {}),
               ev: { dragstart: count("dragstart"), dragover: count("dragover"), drop: count("drop"), dragend: count("dragend") },
               // every drag tick the page actually SAW, in order, as "kind@x" — Chromium coalesces drag events to one
               // per frame, so which positions got a tick is the first thing to read when a drop landed off the cursor
               ticks: log.filter((e) => e.k === "dragover" || e.k === "dragenter" || e.k === "drop").map((e) => e.k[4] + "@" + e.x),
               tail: log.filter((e) => e.k !== "dragenter" && e.k !== "dragleave" && e.k !== "pointercancel").slice(-6).map((e) => e.k + "@" + e.x + (e.tgt ? " on " + e.tgt : "") + (e.prevented ? " accepted" : "")),
               items: post.items.map((i) => (i.id ? i.name : "[" + i.cls + "]") + "@" + i.left + "," + i.top + "+" + i.w + "x" + i.h) });
}
// The hand comes to rest at a point and STAYS until the strip has re-slotted for it. One move is not enough: the
// tick a pointer jump produces is a dragENTER (Chromium fires it instead of dragover when the element under the
// pointer changes), which the strip accepts as a drop target but does not hit-test — only the dragover after it
// re-slots. So each rest is a move plus a few still ticks a frame apart, which is what a real hand delivers.
const settleAt = async (x, y) => {
  await page.mouse.move(x, y);
  for (let i = 0; i < 3; i++) { await page.mouse.move(x, y); await page.waitForTimeout(25); }
};
// THE GESTURE, shared by every drag below: `src` is the item to grab, the release is at `frac` of `tgt`'s width
// (0.25 = its left part, so the dragged tab should land BEFORE it; 0.75 = its right part, AFTER it). A run of
// moves across the strip, a rest over the target, the release — plus the DRAG CUE sampled while the hand rests
// (the drag into / out of a group change, 2026-09-23: the group about to be joined wears the accent ring, a tag
// about to come off says so in the floating line), and, when the gesture writes a tag, the wait for the kernel's
// store to answer. `opts.tagWrite` = this gesture is expected to write a tag, so wait for the store to change.
async function runDrag(label, pre, src, tgt, frac, opts) {
  const o = opts || {};
  const sx = pre.bar.left + src.left + src.w / 2, sy = pre.bar.top + src.top + src.h / 2;
  const tx = pre.bar.left + tgt.left + tgt.w * frac, ty = pre.bar.top + tgt.top + tgt.h / 2;
  const before = pre.tags ? tagsIn(pre.tags, src.id) : null;
  await page.evaluate(() => { window.__log = []; });
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + 4, sy + 1, { steps: 2 });   // the drag starts on the first moves after the press
  await page.mouse.move(tx, ty, { steps: 16 });          // a run of dragover ticks across the strip
  // THE RELEASE POINT'S OWN HIT-TEST, MADE CERTAIN: park at the grab point until the strip has really re-slotted
  // there, then come to the release point and rest until it re-slots again (settleAt). Two things conspire without
  // this. Chromium coalesces drag events to one per frame, so the sweep's last delivered tick can be a step or two
  // short of where the hand stopped — and if that tick's hop slides the dragged tab under the cursor, every later
  // tick is refused by the strip's own native-feel guard (a pointer inside the dragged tab's box moves nothing), so
  // the gesture ends one slot short. A real hand, moving continuously, always gets a tick at its resting place.
  // The park takes the tab out from under the cursor; the hit-test that follows runs against the same virtual
  // layout either way (the dragged tab is never part of it), so the slot is this test's pre-drag `expected` by
  // construction. Nothing about the strip changes here; the synthetic hand is catching up with a real one.
  await settleAt(sx, sy);
  await settleAt(tx, ty);
  // a rest over the target: the hand stops before it lets go. THREE still ticks, not one: the last moving tick's hop slides
  // a new element under the pointer, Chromium answers the next tick with dragenter (which the strip does not cancel: no
  // dragenter listener, so that tick's drop operation is none) and only the tick after with an accepted dragover; a release
  // straight after the hop is refused by the browser (no drop, dragend cancels, the tab snaps home). That refusal is a
  // hazard of its own, seen here as the intermittent drop=0; this test is about where an ACCEPTED drop lands.
  for (let i = 0; i < 3; i++) await page.mouse.move(tx, ty);
  // the cue as the hand sees it, mid-gesture: the ringed header(s), and the leave line's words when it is up
  const cue = await page.evaluate(() => {
    const c = document.querySelector(".tab-drag-cue");
    return { ring: Array.from(document.querySelectorAll("#tabs .tab-group-head.join-target")).map((h) => h.dataset.group),
             leave: c && c.style.display !== "none" ? c.textContent.replace(/\s+/g, " ").trim() : "",
             cueBox: c && c.style.display !== "none" ? (() => { const r = c.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })() : null };
  });
  await page.mouse.up();
  const wrote = o.tagWrite ? await waitTags(src.id, before) : null;
  await page.waitForTimeout(500);
  await page.mouse.move(900, 700);                        // off the strip: no hover tip in the next measurement
  // the cue belongs to the gesture: nothing of it may survive dragend
  const cueAfter = await page.evaluate(() => {
    const c = document.querySelector(".tab-drag-cue");
    return { ring: Array.from(document.querySelectorAll("#tabs .tab-group-head.join-target")).map((h) => h.dataset.group),
             leave: c && c.style.display !== "none" ? c.textContent.trim() : "" };
  });
  await record(label, pre, src, tgt, tx, ty, { cue, cueAfter, wrote });
}
// the tab at rows[fromRow][fromIdx] dragged onto rows[toRow][toIdx]
async function drag(label, fromRow, fromIdx, toRow, toIdx, frac, opts) {
  const pre = await layout();
  const src = pre.rows[fromRow] && pre.rows[fromRow][fromIdx], tgt = pre.rows[toRow] && pre.rows[toRow][toIdx];
  if (!src || !tgt) { cases.push({ label, skipped: "no such tab: rows=" + JSON.stringify(pre.rows.map((r) => r.map((t) => t.name))) }); return; }
  await runDrag(label, pre, src, tgt, frac, opts);
}
// A session's COPY, named by the session and the group whose row it sits in (T264b: a session under N tags has N
// tabs, and which copy is dragged is what a drop on the ungrouped row takes off), dragged onto another copy or
// onto a section HEADER (`to.head`). This is how the join/leave phase addresses the strip: by name, never by a
// row index, since a tag write reshapes the rows under it.
const copyOf = (L, name, copy) => L.tabs.find((t) => t.name === name && t.copy === copy);
async function dragCopy(label, srcName, srcCopy, to, frac, opts) {
  const pre = await layout();
  const src = copyOf(pre, srcName, srcCopy);
  const tgt = to.head !== undefined ? pre.items.find((i) => i.group === to.head)
            : to.row !== undefined ? (pre.rows[to.row === "trail" ? pre.rows.length - 1 : to.row] || [])[to.idx]
            : copyOf(pre, to.name, to.copy);
  if (!src || !tgt) { cases.push({ label, skipped: "no such tab: " + JSON.stringify({ srcName, srcCopy, to, tabs: pre.tabs.map((t) => t.name + "/" + t.copy) }) }); return; }
  await runDrag(label, pre, src, tgt.group ? { ...tgt, name: "#" + tgt.group } : tgt, frac, opts);
}
// the tab at rows[fromRow][fromIdx] dragged to rows[toRow][toIdx] with a REAL kernel push landing mid-drag: partway across,
// the driver renames another session through the kernel's headless POST /rename (the names file is what the pusher
// watches, so the new name re-pushes to the page), waits for the frame carrying the new name to reach the page, then
// finishes the gesture. The browser fires pointercancel at dragstart (a drag cancels the pointer); the strip's click-safe
// hold used to release on it, so the push rebuilt #tabs under the drag, detached the dragged node, and the drop moved
// nothing. Held through the drag, the push's render waits for dragend: no rebuild between dragstart and drop, the drop
// lands under the cursor, and the new name shows once the gesture is over.
async function dragAcrossPush(label, fromRow, fromIdx, toRow, toIdx, frac, renameFrom, renameTo) {
  const pre = await layout();
  const src = pre.rows[fromRow] && pre.rows[fromRow][fromIdx], tgt = pre.rows[toRow] && pre.rows[toRow][toIdx];
  if (!src || !tgt) { cases.push({ label, skipped: "no such tab: rows=" + JSON.stringify(pre.rows.map((r) => r.map((t) => t.name))) }); return; }
  const sx = pre.bar.left + src.left + src.w / 2, sy = pre.bar.top + src.top + src.h / 2;
  const tx = pre.bar.left + tgt.left + tgt.w * frac, ty = pre.bar.top + tgt.top + tgt.h / 2;
  const mx = (sx + tx) / 2;
  await page.evaluate((m) => { window.__log = []; window.__wsMarker = m; window.__wsMarkerSeen = false; }, renameTo);
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + 4, sy + 1, { steps: 2 });
  await page.mouse.move(mx, ty, { steps: 8 });            // halfway: the drag is live
  const resp = await fetch(cfg.rename, { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: JSON.stringify({ target: renameFrom, name: renameTo }) });
  const ans = await resp.json();
  const pushed = await page.waitForFunction(() => window.__wsMarkerSeen, null, { timeout: 15000 }).then(() => true).catch(() => false);
  await page.waitForTimeout(300);                          // whatever the page does with the frame has had its turn
  const shownDuring = await page.evaluate((n) => Array.from(document.querySelectorAll("#tabs .tab-label")).some((l) => l.textContent.trim() === n), renameTo).catch(() => null);
  await page.mouse.move(tx, ty, { steps: 8 });            // …and the gesture goes on to the target
  await settleAt(sx, sy);                                 // the park and the rest at the release point (runDrag's
  await settleAt(tx, ty);                                 // account): the drop's slot is the pre-drag model's
  for (let i = 0; i < 3; i++) await page.mouse.move(tx, ty);
  await page.mouse.up();
  await page.waitForTimeout(500);
  await page.mouse.move(900, 700);
  const shownAfter = await page.waitForFunction((n) => Array.from(document.querySelectorAll("#tabs .tab-label")).some((l) => l.textContent.trim() === n), renameTo, { timeout: 10000 })
    .then(() => true).catch(() => false);
  await record(label, pre, src, tgt, tx, ty);
  const log = await page.evaluate(() => window.__log);
  const t0 = (log.find((e) => e.k === "dragstart") || {}).t, t1 = (log.find((e) => e.k === "drop" || e.k === "dragend") || {}).t;
  const rebuiltMidDrag = log.some((e) => e.k.startsWith("rebuild") && e.t > t0 && e.t < t1);
  Object.assign(cases[cases.length - 1], { rename: ans, pushed, shownDuring, shownAfter, rebuiltMidDrag });
}
const out = { grouped: null, yatharth: null };
// 1. the CLASSIC theme, the control: row 0 = the infra group, the last row = the untagged trail
let L = await layout();
out.grouped = { theme: L.theme, gap: L.bar.gap, rows: L.rows.map((r) => r.map((t) => t.name)), bar: L.bar,
                items: L.items.map((i) => (i.id ? i.name : "[" + i.cls + "]") + "@" + i.left + "," + i.top + "+" + i.w + "x" + i.h) };
let trail = L.rows.length - 1;
await drag("classic: trail, 3rd tab to the FIRST slot (left part of the 1st)", trail, 2, trail, 0, 0.25);
await drag("classic: trail, 1st tab to the 3rd slot (right part of the 3rd)", trail, 0, trail, 2, 0.75);
await drag("classic: trail, 4th tab to the 2nd slot (left part of the 2nd)", trail, 3, trail, 1, 0.25);
await drag("classic: group row, 1st tab to the 3rd slot (right part of the 3rd)", 0, 0, 0, 2, 0.75);
// 2. the YATHARTH theme, set as the user sets it: the theme key of this browser's settings store, read at boot
await page.evaluate(() => { let s = {}; try { s = JSON.parse(localStorage.getItem("romp:settings") || "{}") || {}; } catch (e) {}
                            s.theme = "yatharth"; localStorage.setItem("romp:settings", JSON.stringify(s)); });
await page.reload();
await settle();
L = await layout();
out.yatharth = { theme: L.theme, gap: L.bar.gap, rows: L.rows.map((r) => r.map((t) => t.name)), bar: L.bar,
                 items: L.items.map((i) => (i.id ? i.name : "[" + i.cls + "]") + "@" + i.left + "," + i.top + "+" + i.w + "x" + i.h) };
trail = L.rows.length - 1;
await drag("yatharth: trail, 3rd tab to the FIRST slot (left part of the 1st)", trail, 2, trail, 0, 0.25);
await drag("yatharth: trail, 1st tab to the 3rd slot (right part of the 3rd)", trail, 0, trail, 2, 0.75);
await drag("yatharth: trail, 4th tab to the 2nd slot (left part of the 2nd)", trail, 3, trail, 1, 0.25);
await drag("yatharth: trail, 2nd tab to the 5th slot (right part of the 5th)", trail, 1, trail, 4, 0.75);
await drag("yatharth: group row, 1st tab to the 3rd slot (right part of the 3rd)", 0, 0, 0, 2, 0.75);
// 3. a kernel push mid-drag (the trail's last tab is renamed while the trail's 2nd tab is on its way to the 6th slot)
L = await layout();
const lastName = L.rows[trail][L.rows[trail].length - 1].name;
await dragAcrossPush("push mid-drag: trail, 2nd tab to the 6th slot (right part of the 6th)", trail, 1, trail, 5, 0.75, lastName, lastName + "-renamed");
// …and its name back, so the phases below read the fixture's names again
await fetch(cfg.rename, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: lastName + "-renamed", name: lastName }) });
await page.waitForFunction((n) => { const names = Array.from(document.querySelectorAll("#tabs .tab-label")).map((l) => l.textContent.trim()); return names.includes(n) && !names.includes(n + "-renamed"); }, lastName, { timeout: 15000 });
// 4. FOLDED NEIGHBOURS SHARE A ROW (the user 2026-09-16): both groups folded by a click on each header. The two bare
//    headers pack onto ONE row and the trail is the row below; the trail's drags still land under the cursor (the
//    virtual layout has the packed row as one row, as the strip does), a drop between the two headers lands at the
//    trail's head, a header dragged across the shared row still reorders the groups, and with one group opened again
//    the folded one keeps a row of its own. Then the same under the classic theme.
const foldGroup = async (name, folded) => {   // a real click on the header; the wait is for the fold's own render (its members' tabs gone, or back)
  await page.click(`#tabs .tab-group-head[data-group="${name}"]`);
  await page.waitForFunction(([n, f]) => { const h = document.querySelector(`#tabs .tab-group-head[data-group="${n}"]`);
    return !!h && h.classList.contains("collapsed") === f && (document.querySelector(`#tabs .tab[data-copy="${n}"]`) === null) === f; }, [name, folded], { timeout: 10000 });
  await page.waitForTimeout(400);
};
const stripShot = async (tag) => { if (cfg.shots) { const b = await page.evaluate(() => { const r = document.getElementById("tabbar").getBoundingClientRect(); return { x: r.left, y: r.top, width: r.width, height: r.height }; });
  await page.screenshot({ path: cfg.shots + "-" + tag + ".png", clip: b }); } };
// the strip's shape for the layout assertions: the headers (row, box, chip, fold), the breaks, the rows of tabs
const shape = (Lx) => ({ theme: Lx.theme, gap: Lx.bar.gap, rows: Lx.rows.map((r) => r.map((t) => t.name)),
  heads: Lx.items.filter((i) => i.group).map((h) => ({ group: h.group, top: h.top, left: h.left, right: r1(h.left + h.w), h: h.h, chip: h.chip,
                                                        collapsed: h.cls.includes("collapsed"), shown: h.cls.includes("snap-shown") })),
  breaks: Lx.items.filter((i) => i.cls.includes("tab-group-break")).map((i) => ({ top: i.top, sep: i.cls.includes("tab-group-sep") })),
  // who the strip shows in each row's group RIGHT NOW (T264b's data-copy, "" = the untagged trail): the layout
  // assertions read membership from here rather than from the fixture's opening arrangement, since the drag into
  // and out of a group (2026-09-23) moves sessions between the trail and the groups before these phases run
  members: Object.fromEntries([...new Set(Lx.tabs.map((t) => t.copy))].map((c) =>
    [c === null ? "flat" : c === "" ? "trail" : c, Lx.tabs.filter((t) => t.copy === c).map((t) => t.name)])),
  items: Lx.items.map((i) => (i.id ? i.name : "[" + i.cls + "]") + "@" + i.left + "," + i.top + "+" + i.w + "x" + i.h) });
// a header dragged onto another: the dragged group takes the target's slot in tagOrder (a kernel write, acked back as a
// frame), so the headers' DOM order changes; measured once the order has changed, or after the wait gives up
async function dragHead(label, fromGroup, toGroup) {
  const pre = await layout();
  const hs = pre.items.filter((i) => i.group);
  const src = hs.find((h) => h.group === fromGroup), tgt = hs.find((h) => h.group === toGroup);
  if (!src || !tgt) { cases.push({ label, skipped: "no such header: " + JSON.stringify(hs.map((h) => h.group)) }); return; }
  const sx = pre.bar.left + src.left + src.w / 2, sy = pre.bar.top + src.top + src.h / 2;
  const tx = pre.bar.left + tgt.left + tgt.w / 2, ty = pre.bar.top + tgt.top + tgt.h / 2;
  const before = hs.map((h) => h.group);
  await page.evaluate(() => { window.__log = []; });
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + 4, sy + 1, { steps: 2 });
  await page.mouse.move(tx, ty, { steps: 12 });
  for (let i = 0; i < 3; i++) await page.mouse.move(tx, ty);
  await page.mouse.up();
  const reordered = await page.waitForFunction((b) => JSON.stringify(Array.from(document.querySelectorAll("#tabs .tab-group-head")).map((h) => h.dataset.group)) !== JSON.stringify(b), before, { timeout: 10000 })
    .then(() => true).catch(() => false);
  await page.waitForTimeout(500);
  await page.mouse.move(900, 700);
  const post = await layout(), log = await page.evaluate(() => window.__log);
  const count = (k) => log.filter((e) => e.k === k).length;
  cases.push({ label, theme: post.theme, gap: post.bar.gap, headDrag: true, from: { name: fromGroup, draggable: src.draggable }, before, reordered,
               after: post.items.filter((i) => i.group).map((h) => h.group), shape: shape(post),
               // a HEADER drag reorders the groups and touches no membership: the whole store, before and after
               // (the two gestures are told apart by what is being dragged, so a header on a header never joins)
               tagsBefore: pre.tags, tagsAfter: tagsOf(),
               cueAfter: await page.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab-group-head.join-target")).map((h) => h.dataset.group)),
               ev: { dragstart: count("dragstart"), dragover: count("dragover"), drop: count("drop"), dragend: count("dragend") },
               tail: log.filter((e) => e.k !== "dragenter" && e.k !== "dragleave" && e.k !== "pointercancel").slice(-6).map((e) => e.k + "@" + e.x + (e.tgt ? " on " + e.tgt : "") + (e.prevented ? " accepted" : "")) });
}
// a tab dragged to a HEADER's slot: released over `frac` of the header's width (0.25: its left part, so the slot before it)
async function dragToHead(label, fromRow, fromIdx, group, frac, opts) {
  const pre = await layout();
  const src = pre.rows[fromRow] && pre.rows[fromRow][fromIdx], tgt = pre.items.find((i) => i.group === group);
  if (!src || !tgt) { cases.push({ label, skipped: "no such tab or header: rows=" + JSON.stringify(pre.rows.map((r) => r.map((t) => t.name))) }); return; }
  await runDrag(label, pre, src, { name: "#" + group, left: tgt.left, w: tgt.w, top: tgt.top, h: tgt.h }, frac, opts);
}
const groups = L.items.filter((i) => i.group).map((h) => h.group);   // in strip order (tagOrder)
await foldGroup(groups[0], true);
await foldGroup(groups[1], true);
L = await layout();
out.packed = shape(L);
await stripShot("packed-yatharth");
trail = L.rows.length - 1;   // the only row of tabs
await drag("packed: trail, 1st tab to the 3rd slot (right part of the 3rd)", trail, 0, trail, 2, 0.75);
await drag("packed: trail, 4th tab to the 2nd slot (left part of the 2nd)", trail, 3, trail, 1, 0.25);
// the slot between the two packed heads is the END of the first group's row — the provisional tab sits right after
// that header — so since 2026-09-23 the release JOINS the first group (and the tab, now a member of a folded group,
// goes off the strip with the rest of its members). The landing is unchanged: the global order still puts it at the
// trail's head, which is what the next phases' rows read.
await dragToHead("packed: trail, 3rd tab to the slot BETWEEN the two folded headers (left part of the second)", trail, 2, groups[1], 0.25, { tagWrite: true });
// …and the slot ahead of the FIRST head is the head of the strip, not the ungrouped row: no tag comes off, the drop
// is the plain reorder it has always been (the guard against a mis-aimed drop stripping a tag)
await dragToHead("packed: trail, 3rd tab to the slot BEFORE the first folded header (the strip's head)", trail, 2, groups[0], 0.25);
await dragHead("packed: the second header dragged onto the first (the groups swap)", groups[1], groups[0]);
// one of the two opened again: the open group's row, the folded one's own row, the trail's
L = await layout();
const order = L.items.filter((i) => i.group).map((h) => h.group);
await foldGroup(order[0], false);
L = await layout();
out.unfolded = shape(L);
await stripShot("unfolded-neighbour-yatharth");
await foldGroup(order[0], true);   // back to the packed row: the fold state is per browser, so the classic reload below keeps it
// 5. the CLASSIC theme over the same folds (gap 0): the packed row again, and its drags
await page.evaluate(() => { let s = {}; try { s = JSON.parse(localStorage.getItem("romp:settings") || "{}") || {}; } catch (e) {}
                            s.theme = "classic"; localStorage.setItem("romp:settings", JSON.stringify(s)); });
const shownBeforeReload = (await layout()).tabs.length;   // the strip's own count, not the fixture's: a join above moved a tab into a folded group
await page.reload();
await settle(shownBeforeReload);
L = await layout();
out.packedClassic = shape(L);
await stripShot("packed-classic");
trail = L.rows.length - 1;
const groupsC = L.items.filter((i) => i.group).map((h) => h.group);
await drag("classic packed: trail, 1st tab to the 3rd slot (right part of the 3rd)", trail, 0, trail, 2, 0.75);
await drag("classic packed: trail, 4th tab to the 2nd slot (left part of the 2nd)", trail, 3, trail, 1, 0.25);
await dragToHead("classic packed: trail, 3rd tab to the slot BETWEEN the two folded headers (left part of the second)", trail, 2, groupsC[1], 0.25, { tagWrite: true });

// 6. DRAGGING A TAB INTO AND OUT OF A GROUP (the user 2026-09-23). Last, so nothing above depends on the
//    membership these gestures rewrite. Both groups open; every drag names its tab by SESSION and COPY, since a
//    tag write reshapes the rows under it. The place a tab is dropped states where it should appear: a group is a
//    tag, so a drop in its row ADDS that tag and leaves the others alone; the ungrouped row is not a group but the
//    sessions with NO tags, so a drop there CLEARS every tag. 6d…6f is the round trip that asymmetry allows:
//    cleared, dragged back into ONE group (which restores that tag alone), cleared again.
for (const g of L.items.filter((i) => i.group).map((h) => h.group)) await foldGroup(g, false);
L = await layout();
const open0 = L.items.filter((i) => i.group).map((h) => h.group);   // [first, second] in tagOrder
out.joinStart = { groups: open0, tags: tagsOf(), rows: L.rows.map((r) => r.map((t) => t.name)) };
const trailRow = () => L.rows.length - 1;
// 6a. an UNTAGGED tab dragged into an open group's row, released on the right part of its 2nd member: the session
//     gains exactly that tag and its tab renders inside the group, after the member it was dropped past
const joiner = L.rows[trailRow()][2].name;
const firstMembers = L.tabs.filter((t) => t.copy === open0[0]).map((t) => t.name);
out.joinStart.joiner = joiner;
out.joinStart.firstMembers = firstMembers;
await dragCopy("join: an untagged tab into the first group, past its 2nd member", joiner, "",
               { name: firstMembers[1], copy: open0[0] }, 0.75, { tagWrite: true });
// 6b. a tab ALREADY in the group, dragged within its row: the position moves, nothing is written, nothing lights up
await dragCopy("join: a tab that already carries the tag, dragged within its group", firstMembers[0], open0[0],
               { name: firstMembers[2], copy: open0[0] }, 0.75);
// 6c. …and the same session dragged on into the SECOND group: it gains that tag too and renders under BOTH
L = await layout();
const secondMembers = L.tabs.filter((t) => t.copy === open0[1]).map((t) => t.name);
await dragCopy("join: a tab that carries another tag joins a second group and renders under both", joiner, open0[0],
               { name: secondMembers[0], copy: open0[1] }, 0.75, { tagWrite: true });
// 6d. the LEAVE half: one of its two copies dragged onto the ungrouped row. EVERY tag comes off — that row is the
//     sessions carrying none — so the session renders once, there, at the drop index, under no group
await dragCopy("leave: a two-tag session dragged to the ungrouped row is cleared of both", joiner, open0[1],
               { row: "trail", idx: 2 }, 0.25, { tagWrite: true });
// 6e. …and dragged back into ONE group it holds exactly that tag: the gesture reverses one tag, never the set
await dragCopy("leave: dragged back into one group it holds exactly that tag", joiner, "",
               { name: secondMembers[1] || secondMembers[0], copy: open0[1] }, 0.75, { tagWrite: true });
// 6f. out again, from one tag this time: cleared, and the store is back where this phase started
await dragCopy("leave: a one-tag session dragged to the ungrouped row is cleared", joiner, open0[1],
               { row: "trail", idx: 3 }, 0.25, { tagWrite: true });
// 6g. the ungrouped row to itself: a plain reorder, no tag write, no cue
L = await layout();
await dragCopy("leave: the ungrouped row to itself is a plain reorder", L.rows[trailRow()][1].name, "",
               { row: "trail", idx: 5 }, 0.75);
// 6h. a GROUP's tab released ahead of the strip's first header: that is the head of the strip, not the ungrouped
//     row, so nothing is cleared (the mis-aimed drop guard)
L = await layout();
const keeper = L.tabs.filter((t) => t.copy === open0[0]).map((t) => t.name)[0];
await dragCopy("leave: a group's tab released ahead of the first header keeps its tag", keeper, open0[0],
               { head: open0[0] }, 0.25);
// 6i. a FOLDED group's bare header (its members hidden, its own row — not a packed one): a release on it joins
await foldGroup(open0[1], true);
L = await layout();
const folder = L.rows[trailRow()][4].name;
out.foldedJoin = { group: open0[1], joiner: folder };
await dragCopy("join: a tab dragged onto a FOLDED group's header joins it", folder, "", { head: open0[1] }, 0.75, { tagWrite: true });
out.joinEnd = { tags: tagsOf(), rows: (await layout()).rows.map((r) => r.map((t) => t.name)) };
out.cases = cases;
fs.writeFileSync(cfg.out, JSON.stringify(out));   // a file, not stdout: the per-case logs outgrow one pipe write
fs.writeSync(1, "RESULT:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


class ServedTabDragReorder(unittest.TestCase):
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
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="tab-drag-")
        # TAB_DRAG_DIST=<dir>: a UI bundle built from another tree, served by this kernel (the bisect's "before": the
        # strip is the bundle's, the kernel's wire the same); by default this tree's own build
        before = os.environ.get("TAB_DRAG_DIST", "")
        if before:
            src = before
        else:
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            if b.returncode != 0:
                raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
            src = os.path.join(EXT, "dist")
        dist = os.path.join(cls.lab, "dist")
        copy_dist(src, dist)   # tests/dist_copy: skips the bundler's staging files
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
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
        # two tags, three and two sessions: the strip groups by tag, a row per group, the other fifteen in the trail
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "tags": TAGS}))
        cls.state = state   # the kernel's own views store: what the drag's tag writes are asserted from (never the DOM alone)
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-tabdrag"
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
        """One driver run for every case (the drags are sequential on one page); its result, or its failure, is shared by
        the tests (a failed run is not repeated per test)."""
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
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "count": len(NAMES), "trail": len(TRAIL), "out": out,
                       "rename": "http://127.0.0.1:%d/rename?token=%s" % (cls.port, cls.token),
                       "views": os.path.join(cls.state, "timeline-views.json"), "sids": SIDS,
                       "shots": os.environ.get("TAB_DRAG_SHOTS", "")}, f)   # TAB_DRAG_SHOTS=<prefix>: strip screenshots of the packed layouts
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        if line is None or not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        result = json.loads(Path(out).read_text())
        if os.environ.get("TAB_DRAG_DUMP"):   # a path: the whole measurement, for reading the cases side by side
            Path(os.environ["TAB_DRAG_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def _case(self, prefix):
        r = self._run()
        c = next((c for c in r["cases"] if c["label"].startswith(prefix)), None)
        self.assertIsNotNone(c, "no such case %r among %r" % (prefix, [c["label"] for c in r["cases"]]))
        if c.get("skipped"):
            self.skipTest(c["skipped"])
        return c

    @staticmethod
    def _table(c):
        return ("\n  theme %(theme)s (column gap %(gap)s)\n  from %(from)s\n  released over %(over)s at strip x=%(rx)s y=%(ry)s"
                "\n  rows before %(pre)s\n  rows after  %(post)s\n  landed rect %(landed)s\n  order after %(order)s"
                "\n  stored (romp:vieworder:shared) %(stored)s\n  drag events %(ev)s\n  the gesture's tail %(tail)s\n  #tabs children %(items)s"
                % dict(c, rx=c["release"]["x"], ry=c["release"]["y"], pre=c["preRows"], post=c["postRows"], order=c["postOrder"]))

    def _assert_landed_under_cursor(self, c):
        table = self._table(c)
        self.assertTrue(c["from"]["draggable"], "the tab must be draggable (a page without its federation manager offers no drag)" + table)
        self.assertGreater(c["ev"]["dragstart"], 0, "no dragstart reached the strip: the mouse gesture began no drag" + table)
        self.assertGreater(c["ev"]["drop"], 0, "%s: no drop reached the strip; the browser refused the release and the drag was cancelled" % c["label"] + table)
        self.assertEqual(c["actual"], c["expected"],
                         "%s: the tab landed at index %d, the cursor was over slot %d" % (c["label"], c["actual"], c["expected"]) + table)
        # the persisted arrangement (the global order) carries the order the strip shows within every row: the strip
        # sections it by tag, so the rows are compared one by one
        self.assertIsInstance(c["stored"], list, "the drop persisted an arrangement" + table)
        for row in c["postRows"]:
            names = [t.split("@")[0] for t in row]
            self.assertEqual([n for n in c["stored"] if n in names], names, "the stored order and the strip's row disagree" + table)

    # ── the layouts ──
    def test_both_themes_show_the_group_row_above_the_trail_row(self):
        r = self._run()
        for key, theme, gap in (("grouped", "classic", "0px"), ("yatharth", "yatharth", "3px")):
            g = r[key]
            self.assertEqual(g["theme"], theme, "%s: the body wears the theme the settings store names: %r" % (key, g))
            self.assertEqual(g["gap"], gap, "%s: the strip's column gap under that theme: %r" % (key, g["bar"]))
            rows = g["rows"]
            self.assertGreaterEqual(len(rows), 3, "%s: the two groups and the trail wrap onto separate rows: %r" % (key, g))
            self.assertEqual(sorted(rows[0]), sorted(TAGGED), "%s: row 0 is the infra group: %r" % (key, rows))
            self.assertEqual(sorted(rows[1]), sorted(QA), "%s: row 1 is the qa group: %r" % (key, rows))
            self.assertEqual(sorted(rows[-1]), sorted(TRAIL), "%s: the last row is the trail: %r" % (key, rows))

    # ── the classic theme: the control ──
    def test_classic_trail_row_drag_to_the_first_slot(self):
        self._assert_landed_under_cursor(self._case("classic: trail, 3rd tab to the FIRST"))

    def test_classic_trail_row_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("classic: trail, 1st tab to the 3rd"))

    def test_classic_trail_row_drag_4th_to_2nd(self):
        self._assert_landed_under_cursor(self._case("classic: trail, 4th tab to the 2nd"))

    def test_classic_group_row_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("classic: group row, 1st tab to the 3rd"))

    # ── the yatharth theme (the user's): the trail's row lands wrong, its first slot and the group's row still right ──
    def test_yatharth_trail_row_drag_to_the_first_slot(self):
        self._assert_landed_under_cursor(self._case("yatharth: trail, 3rd tab to the FIRST"))

    def test_yatharth_trail_row_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("yatharth: trail, 1st tab to the 3rd"))

    def test_yatharth_trail_row_drag_4th_to_2nd(self):
        self._assert_landed_under_cursor(self._case("yatharth: trail, 4th tab to the 2nd"))

    def test_yatharth_trail_row_drag_2nd_to_5th(self):
        self._assert_landed_under_cursor(self._case("yatharth: trail, 2nd tab to the 5th"))

    def test_yatharth_group_row_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("yatharth: group row, 1st tab to the 3rd"))

    # ── a kernel push mid-drag: the strip's hold must outlive the browser's pointercancel at dragstart ──
    def test_a_drag_survives_a_kernel_push_that_lands_mid_drag(self):
        c = self._case("push mid-drag: trail, 2nd tab to the 6th")
        table = self._table(c)
        self.assertTrue(c["rename"].get("ok"), "the kernel accepted the headless rename: %r" % c["rename"])
        self.assertTrue(c["pushed"], "the frame carrying the new name reached the page while the drag was in flight" + table)
        self.assertFalse(c["rebuiltMidDrag"], "the strip was rebuilt under the drag: the hold did not outlive the browser's pointercancel" + table)
        self._assert_landed_under_cursor(c)
        self.assertTrue(c["shownAfter"], "the push's render, held through the drag, lands once the gesture is over: the new name shows" + table)

    # ── FOLDED NEIGHBOURS SHARE A ROW (the user 2026-09-16) ──
    @staticmethod
    def _tab_tops(g):
        """name → the row top of every TAB in a recorded shape (its items read `name@left,top+wxh`; a header or a break is `[cls]@…`)."""
        out = {}
        for it in g["items"]:
            if it.startswith("["):
                continue
            name, rect = it.split("@", 1)
            out[name] = float(rect.split(",")[1].split("+")[0])
        return out

    def _assert_packed(self, key):
        r = self._run()
        g = r[key]
        heads = g["heads"]
        detail = "\n  %s: heads %r\n  breaks %r\n  rows %r\n  items %r" % (key, heads, g["breaks"], g["rows"], g["items"])
        self.assertEqual([h["collapsed"] for h in heads], [True, True], "both groups folded" + detail)
        self.assertEqual(heads[0]["top"], heads[1]["top"], "the two folded headers share ONE row (equal tops)" + detail)
        self.assertEqual(len(g["breaks"]), 1, "one break in the strip, the trail's — none between the two folded headers" + detail)
        self.assertTrue(g["breaks"][0]["sep"], "…and it is the trail's (it wears the boundary class)" + detail)
        self.assertEqual(len(g["rows"]), 1, "the trail is the only row of tabs" + detail)
        # the trail as the strip itself reports it (the shape's own data-copy census), not the fixture's opening
        # arrangement: the drag into and out of a group (2026-09-23) moves sessions between the trail and the groups
        self.assertEqual(sorted(g["rows"][0]), sorted(g["members"].get("trail", [])), "…and every trail tab is on it" + detail)
        self.assertGreater(len(g["rows"][0]), 8, "the trail is still the long row this lab measures drags on" + detail)
        self.assertGreater(min(self._tab_tops(g).values()), heads[0]["top"] + heads[0]["h"] - 1, "the trail's row sits below the headers' row" + detail)
        self.assertEqual(sorted(g["members"]), ["trail"], "a folded group shows no member, so every tab on the strip is a trail tab" + detail)
        # the two headers sit side by side as two tabs do: the second's box starts where the first's ends (plus the strip's
        # column gap), the boxes never overlap, and the labels (the chips) stand clear of each other by both paddings
        gap = float(g["gap"].replace("px", "") or 0)
        self.assertGreaterEqual(heads[1]["left"], heads[0]["right"], "the second header's box starts after the first's" + detail)
        self.assertLessEqual(heads[1]["left"] - heads[0]["right"], gap + 1, "…right after it: the strip's column gap, nothing else" + detail)
        self.assertGreaterEqual(heads[1]["chip"]["left"] - heads[0]["right"], 6, "the second chip is at least its header's padding in from the first header's edge" + detail)
        self.assertGreaterEqual(heads[1]["chip"]["left"] - heads[0]["chip"]["right"], 24, "the two chips stand clear of each other (the count and caret between, plus both paddings)" + detail)

    def test_two_folded_groups_share_one_row_under_the_yatharth_theme(self):
        self._assert_packed("packed")

    def test_two_folded_groups_share_one_row_under_the_classic_theme(self):
        self._assert_packed("packedClassic")

    def test_an_open_neighbour_keeps_its_own_row_and_so_does_the_lone_folded_group(self):
        r = self._run()
        g = r["unfolded"]
        heads = g["heads"]
        detail = "\n  heads %r\n  breaks %r\n  rows %r\n  items %r" % (heads, g["breaks"], g["rows"], g["items"])
        self.assertEqual([h["collapsed"] for h in heads], [False, True], "the first group open, the second folded" + detail)
        self.assertLess(heads[0]["top"], heads[1]["top"], "the folded header is on a row BELOW the open group's header: nothing to pack with" + detail)
        self.assertEqual(len(g["breaks"]), 2, "a break ahead of the folded header and the trail's" + detail)
        self.assertEqual(len(g["rows"]), 2, "two rows of tabs: the open group's and the trail's" + detail)
        # membership as the strip reports it (see _assert_packed): the drag into and out of a group rewrites it
        open_members = g["members"].get(heads[0]["group"], [])
        self.assertEqual(sorted(g["rows"][0]), sorted(open_members), "the open group's row holds its members" + detail)
        self.assertEqual(sorted(g["rows"][1]), sorted(g["members"].get("trail", [])), "the trail's row holds the rest" + detail)
        tops = self._tab_tops(g)
        self.assertEqual({tops[n] for n in open_members}, {heads[0]["top"]}, "the open group's members sit on their header's own row" + detail)
        self.assertLess(heads[1]["top"], min(tops[n] for n in g["members"].get("trail", [])), "the folded header's row is above the trail's" + detail)
        self.assertEqual([n for n, t in tops.items() if t == heads[1]["top"]], [], "the lone folded header's row holds nothing else" + detail)

    def test_packed_row_trail_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("packed: trail, 1st tab to the 3rd"))

    def test_packed_row_trail_drag_4th_to_2nd(self):
        self._assert_landed_under_cursor(self._case("packed: trail, 4th tab to the 2nd"))

    def test_packed_row_drop_between_the_two_folded_headers_joins_the_first(self):
        # the slot between two packed heads is the END of the first group's row (no break stands between them), so
        # the provisional tab sits inside that group and the release joins it — the gesture of 2026-09-23 extended
        # to the packed layout. The landing in the global order is what it always was, the trail's head.
        c = self._case("packed: trail, 3rd tab to the slot BETWEEN")
        table = self._table(c)
        first = self._run()["packed"]["heads"][0]["group"]
        self.assertGreater(c["ev"]["drop"], 0, "the drop reached the strip" + table)
        self.assertTrue(c["wrote"], "the kernel's store answered the drag's tag write" + table)
        self.assertEqual(c["tags"]["before"], [], "an untagged trail tab was dragged" + table)
        self.assertEqual(c["tags"]["after"], [first], "…and it gained exactly the first group's tag" + table)
        self.assertEqual(c["cue"]["ring"], [first], "that group's header wore the accent ring before the release" + table)
        self.assertEqual(c["copies"], [], "its tab is off the strip with the rest of that folded group's members" + table)
        self.assertEqual([n for n in c["postRows"][0] if n.split("@")[0] == c["from"]["name"]], [],
                         "…so the trail no longer holds it" + table)

    def test_packed_row_drop_before_the_first_folded_header_takes_no_tag_off(self):
        # the slot ahead of the strip's FIRST header finds no section either, but it is the head of the strip, not
        # the ungrouped row: a drop aimed a little left of the first chip must never strip a tag
        c = self._case("packed: trail, 3rd tab to the slot BEFORE")
        self._assert_landed_under_cursor(c)
        self.assertEqual(c["actual"], 0, "the strip's head is the slot before the trail: the tab lands first" + self._table(c))
        self.assertEqual(c["tags"]["after"], c["tags"]["before"], "no tag written" + self._table(c))
        self.assertEqual(c["cue"]["ring"], [], "…and nothing lit up" + self._table(c))

    def test_packed_row_header_drag_reorders_the_groups(self):
        c = self._case("packed: the second header dragged onto the first")
        detail = "\n  before %r after %r reordered %r\n  events %r\n  tail %r\n  shape %r" % (c["before"], c["after"], c["reordered"], c["ev"], c["tail"], c["shape"])
        self.assertTrue(c["from"]["draggable"], "a header drags to reorder the groups" + detail)
        self.assertGreater(c["ev"]["drop"], 0, "the drop reached the strip" + detail)
        self.assertEqual(c["after"], list(reversed(c["before"])), "the dragged group took the target's slot: the two swapped" + detail)
        # a HEADER dropped on a header is the group-reorder gesture, told apart from a TAB dropped on a header by
        # what is being dragged: no membership moves, and the join cue never comes up
        self.assertEqual(c["tagsAfter"], c["tagsBefore"], "a header drag writes no membership" + detail)
        self.assertEqual(c["cueAfter"], [], "…and no group was ever marked as one to join" + detail)
        heads = c["shape"]["heads"]
        self.assertEqual(heads[0]["top"], heads[1]["top"], "…and the two still share one row" + detail)
        self.assertEqual([h["collapsed"] for h in heads], [True, True], "…both still folded" + detail)

    def test_classic_packed_row_trail_drag_1st_to_3rd(self):
        self._assert_landed_under_cursor(self._case("classic packed: trail, 1st tab to the 3rd"))

    def test_classic_packed_row_trail_drag_4th_to_2nd(self):
        self._assert_landed_under_cursor(self._case("classic packed: trail, 4th tab to the 2nd"))

    def test_classic_packed_row_drop_between_the_two_folded_headers_joins_the_first(self):
        c = self._case("classic packed: trail, 3rd tab to the slot BETWEEN")
        table = self._table(c)
        first = self._run()["packedClassic"]["heads"][0]["group"]
        self.assertTrue(c["wrote"], "the kernel's store answered the drag's tag write" + table)
        self.assertEqual(c["tags"]["after"], [first], "the packed row joins the same way under the classic theme" + table)
        self.assertEqual(c["cue"]["ring"], [first], "…and rings the same header" + table)

    # ── DRAGGING A TAB INTO AND OUT OF A GROUP (the user 2026-09-23) ──
    # The strip's sections are tags: a drop in a group's row puts the session in the group, a drop on the
    # ungrouped row takes the dragged copy's tag off. Tags are asserted from the KERNEL's own views store.
    def _joins(self):
        return self._run()["joinStart"]

    def _pos(self, names, who):
        self.assertIn(who, names, "%s is among %r" % (who, names))
        return names.index(who)

    def test_join_an_untagged_tab_into_an_open_group_gains_exactly_that_tag_at_the_drop_index(self):
        c = self._case("join: an untagged tab into the first group")
        table = self._table(c)
        st = self._joins()
        group, who, over = st["groups"][0], st["joiner"], c["over"]["name"]
        self.assertGreater(c["ev"]["drop"], 0, "the drop reached the strip" + table)
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(c["tags"]["before"], [], "an untagged tab was dragged" + table)
        self.assertEqual(c["tags"]["after"], [group], "it gained exactly the group's tag, in the kernel's own store" + table)
        self.assertEqual(c["copies"], [group], "…and the strip draws its one tab inside that group" + table)
        # the drop index: released on the right part of a member, so it sits immediately AFTER that member
        members = c["inGroups"][group]
        self.assertEqual(members[self._pos(members, over) + 1], who,
                         "the tab lands where the cursor was, among the group's members: %r" % (members,) + table)
        self.assertEqual(c["cue"]["ring"], [group], "the group about to be joined wore the accent ring before the release" + table)
        self.assertEqual(c["cue"]["leave"], "", "nothing is coming off, so the leave line stays down" + table)
        self.assertEqual(c["cueAfter"], {"ring": [], "leave": ""}, "the cue belongs to the gesture: dragend takes it all down" + table)

    def test_a_tab_that_already_carries_the_tag_only_reorders_and_flashes_nothing(self):
        c = self._case("join: a tab that already carries the tag")
        table = self._table(c)
        group = self._joins()["groups"][0]
        self._assert_landed_under_cursor(c)
        self.assertEqual(c["tags"]["after"], c["tags"]["before"], "no tag write at all" + table)
        self.assertEqual(c["tags"]["after"], [group], "…it was and is a member of the group it was dragged within" + table)
        self.assertEqual(c["cue"]["ring"], [], "nothing may flash on a drag that only reorders inside one group" + table)
        self.assertEqual(c["cue"]["leave"], "", "…and no tag is coming off either" + table)

    def test_a_tab_that_carries_another_tag_joins_a_second_group_and_renders_under_both(self):
        c = self._case("join: a tab that carries another tag joins a second group")
        table = self._table(c)
        st = self._joins()
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(c["tags"]["after"], sorted(st["groups"]),
                         "a group is a tag: 'appear here' adds this one and leaves the other alone" + table)
        self.assertEqual(sorted(c["copies"]), sorted(st["groups"]),
                         "…and the strip draws a copy under EACH, which is what makes the second tag evident" + table)
        self.assertEqual(c["cue"]["ring"], [st["groups"][1]], "only the group about to be joined is marked" + table)

    def test_a_multi_tag_session_dropped_on_the_ungrouped_row_is_cleared_of_every_tag(self):
        # the ungrouped row is not a group — it is the sessions carrying no tags — so "appear here" can only be
        # satisfied by clearing them all (the user 2026-09-23). The label says so before the release, which is the
        # whole safety: no undo stack, and one drag back restores one tag, not the set.
        c = self._case("leave: a two-tag session dragged to the ungrouped row")
        table = self._table(c)
        st = self._joins()
        who, over = st["joiner"], c["over"]["name"]
        self.assertGreater(c["ev"]["drop"], 0, "the drop reached the strip" + table)
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(sorted(c["tags"]["before"]), sorted(st["groups"]), "it carried both tags" + table)
        self.assertEqual(c["tags"]["after"], [], "and holds none at all in the kernel's own store" + table)
        self.assertEqual(c["copies"], [""], "one tab, in the ungrouped row, under no group" + table)
        for g in st["groups"]:
            self.assertNotIn(who, c["inGroups"].get(g, []), "%s no longer holds it" % g + table)
        trail = c["inGroups"][""]
        self.assertEqual(trail[self._pos(trail, over) - 1], who,
                         "released on the left part of a trail tab, so it lands immediately before it: %r" % (trail[:8],) + table)
        # the cue named EVERY tag the release would clear, while the hand could still move
        self.assertEqual(c["cue"]["ring"], [], "no group is being joined" + table)
        for g in st["groups"]:
            self.assertIn(g, c["cue"]["leave"], "the cue lists %s among the tags coming off" % g + table)
        self.assertTrue(c["cue"]["leave"].startswith("out of "), "…in the drag's own words: %r" % c["cue"]["leave"] + table)
        self.assertTrue(c["cue"]["cueBox"] and c["cue"]["cueBox"]["w"] > 0, "the cue was really on screen" + table)
        self.assertEqual(c["cueAfter"], {"ring": [], "leave": ""}, "and it goes at dragend" + table)

    def test_dragged_back_into_one_group_the_cleared_session_holds_exactly_that_tag(self):
        # reversibility is ONE tag, not the set: this is the cost of the asymmetry, asserted rather than assumed
        c = self._case("leave: dragged back into one group")
        table = self._table(c)
        st = self._joins()
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(c["tags"]["before"], [], "it was cleared by the previous drag" + table)
        self.assertEqual(c["tags"]["after"], [st["groups"][1]], "back in the group it was dragged into, and in no other" + table)
        self.assertEqual(c["copies"], [st["groups"][1]], "…so the strip draws it once, there" + table)

    def test_a_one_tag_session_dropped_on_the_ungrouped_row_is_cleared_and_lands_at_the_drop_index(self):
        c = self._case("leave: a one-tag session dragged to the ungrouped row")
        table = self._table(c)
        st = self._joins()
        who, over = st["joiner"], c["over"]["name"]
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(c["tags"]["before"], [st["groups"][1]], "one tag" + table)
        self.assertEqual(c["tags"]["after"], [], "…and none after" + table)
        self.assertEqual(c["copies"], [""], "one tab, in the ungrouped row" + table)
        trail = c["inGroups"][""]
        self.assertEqual(trail[self._pos(trail, over) - 1], who,
                         "it lands immediately before the tab it was released on the left part of: %r" % (trail[:8],) + table)
        self.assertEqual(c["cue"]["leave"], "out of " + st["groups"][1], "the cue named the one tag coming off" + table)

    def test_the_ungrouped_row_to_itself_is_a_plain_reorder(self):
        c = self._case("leave: the ungrouped row to itself")
        table = self._table(c)
        self._assert_landed_under_cursor(c)
        self.assertEqual(c["tags"]["before"], [], "an untagged tab" + table)
        self.assertEqual(c["tags"]["after"], [], "…and nothing was written, exactly as before this gesture existed" + table)
        self.assertEqual(c["cue"], dict(c["cue"], ring=[], leave="", cueBox=None),
                         "no cue on a plain reorder: there is nothing to warn about" + table)

    def test_a_group_tab_released_ahead_of_the_first_header_keeps_its_tag(self):
        c = self._case("leave: a group's tab released ahead of the first header")
        table = self._table(c)
        group = self._joins()["groups"][0]
        self.assertEqual(c["tags"]["after"], [group], "the head of the strip is not the ungrouped row: nothing is cleared" + table)
        self.assertEqual(c["cue"]["leave"], "", "…and the cue never promised otherwise" + table)

    def test_a_drop_on_a_folded_groups_bare_header_joins_it(self):
        c = self._case("join: a tab dragged onto a FOLDED group's header")
        table = self._table(c)
        fj = self._run()["foldedJoin"]
        self.assertGreater(c["ev"]["drop"], 0, "the drop reached the strip" + table)
        self.assertTrue(c["wrote"], "the kernel's store answered the write" + table)
        self.assertEqual(c["tags"]["before"], [], "an untagged trail tab was dragged" + table)
        self.assertEqual(c["tags"]["after"], [fj["group"]], "it gained the folded group's tag" + table)
        self.assertEqual(c["cue"]["ring"], [fj["group"]], "the folded header wore the ring before the release" + table)
        self.assertEqual(c["copies"], [], "its tab is hidden with the group's other members, which are folded away" + table)
        self.assertNotIn(fj["joiner"], c["inGroups"].get("", []), "…and it has left the ungrouped row" + table)

    def test_a_join_a_clear_and_a_join_back_leave_the_store_where_it_started(self):
        # 6a…6f take one session into a group, into a second, clear both, back into one, and clear again. The
        # kernel's store must end where this phase started for that session — asserted, not assumed. The only
        # difference in the whole store is the last case's deliberate join onto a folded header.
        r = self._run()
        start, end = r["joinStart"]["tags"], r["joinEnd"]["tags"]
        fj = r["foldedJoin"]
        detail = "\n  start %r\n  end   %r\n  folded join %r" % (start, end, fj)
        self.assertEqual(sorted(start), sorted(end), "the same tags exist" + detail)
        sid = SIDS[fj["joiner"]]
        norm = lambda ms: sorted(m.split(":")[-1] for m in ms)   # noqa: E731 — a member may be stored host-qualified
        for name in start:
            want = list(start[name]) + ([sid] if name == fj["group"] else [])
            self.assertEqual(norm(end[name]), norm(want),
                             "%s holds what it held, plus only the session the last case deliberately joined" % name + detail)


if __name__ == "__main__":
    unittest.main()
