#!/usr/bin/env python3
"""The phone's session picker lists the sessions in the desktop strip's order, under the same tag
headings (the user 2026-09-16, whose phone picker ran the sessions in another order than the strip on
their desktop once the tabs were grouped by tag).

The desktop strip is painted from planStrip (ui/webview/tab-groups.ts): one section per tag in tagOrder,
each holding every visible member it carries (a session under two tags has a copy in each), then the
untagged trail behind a separator. The phone's picker (kernel.py _CHAT_MOBILE_JS, #mlist) is built by
scraping the page's own hidden #tabs strip, so it lists whatever the strip renders in DOM order — and on
the phone layout the plan used to FLATTEN: planStrip(phone=true) returned the visible ids in their raw
view order with no headings, since a folded section there would have hidden its members from the
phone's only switcher. The two surfaces therefore read the same ids in two orders. Now the phone plan
sections like the desktop's (nothing folds there: the picker's heading is a label, not a fold control,
so every session stays reachable), and the picker mirrors the strip's children one for one: a heading
row per group header (the tag's chip and the count, cloned from the header), a row per tab copy, a
divider where the trail begins.

This lab drives a hermetic kernel's real /chat page twice: a desktop context reads the strip's children,
a phone context (a coarse pointer under 1024 px, the kernel's own media rule) opens the picker and reads
its rows; the two sequences must be identical. It also taps a copy under its second tag (the session
opens), taps a heading (nothing opens, the list stays), and folds a group in the phone's own store (the
phone lists its members regardless, where the desktop hides them). The arrangement is the kernel's since
2026-09-23 (view-order.ts), so the trail matrix resets the kernel's arrangement along with both browsers'
keys, and a desktop's arrangement reaches the phone. Skips LOUDLY without the extension deps or a
Playwright browser. The lab kernel never reaches the machine's user manager: a `systemctl` and a
`systemd-run` of the lab's own shadow the real ones on its PATH. SYNTHETIC fixtures only (the notes-api
demo world, host TESTHOST, placeholder sids). MOBILE_ORDER_DUMP=<path> writes the whole measurement."""
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

# the notes-api demo world, in an order that interleaves the groups: grouped the strip reads qa (tests,
# docs, deploy), infra (web, api, deploy), solo (mailer), then the untagged trail (auth, search, cache,
# worker). deploy is under BOTH qa and infra (a copy in each); solo holds exactly one member (a
# single-member tag sections like any other); `empty` holds none (a tag in the view with no visible
# member yields no section); the trail is four deep, so its ORDER is measurable and not just its set.
NAMES = ["web", "tests", "api", "docs", "deploy", "auth", "search", "cache", "mailer", "worker"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
NAME_OF = {v: k for k, v in SIDS.items()}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]
TAGS = [{"id": "tag-qa", "name": "qa", "color": "#DD42FF", "members": [SIDS[n] for n in ("tests", "docs", "deploy")]},
        {"id": "tag-infra", "name": "infra", "color": "#4EC9B0", "members": [SIDS[n] for n in ("web", "api", "deploy")]},
        {"id": "tag-solo", "name": "solo", "color": "#e0af68", "members": [SIDS["mailer"]]},
        {"id": "tag-empty", "name": "empty", "color": "#7aa2f7", "members": []}]
TAG_ORDER = ["qa", "infra", "solo", "empty"]
MEMBERS = {"qa": {"tests", "docs", "deploy"}, "infra": {"web", "api", "deploy"}, "solo": {"mailer"},
           None: {"auth", "search", "cache", "worker"}}
TRAIL_ARRIVAL = ["auth", "search", "cache", "worker"]   # the order the four loose sessions were created in
TRAIL_RENDERED = ["worker", "cache", "search", "auth"]  # …and the order a viewer that never dragged shows: the
#   kernel lists newest first, and an empty arrangement is view-order.ts's identity transform over that seed
# ONE VIEWER'S ARRANGEMENT: the whole rendered order as a drag writes it (commitTabOrder is dense), with the
# TRAIL reversed — what a desktop that has dragged its loose tabs holds. Seeded as the pre-move key
# (romp:vieworder), which a browser publishes when the kernel keeps no arrangement (view-order.ts, 2026-09-23),
# so it reaches a phone that never dragged
DRAG_NAMES = ["web", "tests", "api", "docs", "deploy", "mailer", "search", "worker", "auth", "cache"]
TRAIL_DRAGGED = ["search", "worker", "auth", "cache"]   # neither the arrival nor the rendered order: unmistakably a drag
# THE LATE ARRIVALS: two untagged sessions that land while the desktop is open and the phone is not — the
# trail is where a new session goes, so this is the pair the user compares
LATE = ["hotfix", "review"]
LATE_SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("k") + i) * 8) for i, n in enumerate(LATE)}
NAME_OF.update({v: k for k, v in LATE_SIDS.items()})
# tab NODES on a full strip: every group's members (3 + 3 + 1) plus the trail's four — deploy counted
# twice, once per group, as the strip draws a copy per tag
FULL_NODES = 3 + 3 + 1 + 4
FOLDED_DESK_NODES = FULL_NODES - 3        # qa folded on the desktop hides its three members
LENS_NODES = 3 + 3 + 1                    # the lens narrowed to the tags: no trail at all
HEADS = 3                                 # qa, infra, solo (`empty` holds nothing, so it yields no section)


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
const MEDIA = "(pointer:coarse) and (max-width:1024px)";
// the strip's children and the picker's, one token each: a group heading (g:<tag>), a tab or row (t:<sid>/<copy>;
// the copy is the group the tab sits in, "" for the untagged trail, "-" on a flat strip), the trail's divider (sep)
const SEQ = `(root, k) => Array.from(root ? root.children : []).map((el) => {
  if (el.matches(k.head)) return "g:" + el.dataset.group;
  if (el.matches(k.sep)) return "sep";
  if (el.matches(k.tab)) return "t:" + el.dataset.id + "/" + (el.dataset.copy === undefined ? "-" : el.dataset.copy);
  return null; }).filter(Boolean)`;
const STRIP = { head: ".tab-group-head[data-group]", sep: ".tab-group-sep", tab: ".tab[data-id]" };
const PICKER = { head: ".mhead[data-group]", sep: ".msep", tab: ".mrow[data-id]" };
const readStrip = (page) => page.evaluate(([seq, k]) => (0, eval)(seq)(document.getElementById("tabs"), k), [SEQ, STRIP]);
const readPicker = (page) => page.evaluate(([seq, k]) => (0, eval)(seq)(document.getElementById("mlist"), k), [SEQ, PICKER]);
// EXACT counts, not floors: a case that changes the strip (a fold, a narrowed lens) waits for the change
// rather than passing on the strip the case before it left. `heads` bounded with a catch, so a strip that
// never sections still reaches the assertion, which then says what was there.
const FULL_NODES = cfg.nodes.full, HEADS = cfg.heads;
const settle = async (page, nodes = FULL_NODES, heads = HEADS) => {
  // attached, not visible: the phone page hides #tabs (display:none) and still renders every tab into it
  await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length === n, nodes, { timeout: 30000 });
  await page.waitForFunction((h) => document.querySelectorAll("#tabs .tab-group-head[data-group]").length === h, heads, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(300);
};
// the picker built from that strip: a row per tab (a copy each), read once the rows are there
const pickerReady = (page, nodes = FULL_NODES) =>
  page.waitForFunction((n) => document.querySelectorAll("#mlist .mrow[data-id]").length === n, nodes, { timeout: 10000 }).catch(() => {});
// the picker open, whatever the page's last case left it as (a reload closes it)
const openPicker = async (page, nodes = FULL_NODES) => {
  if (!(await page.$("#mlist.open"))) await page.tap("#mcur");
  await page.waitForSelector("#mlist.open", { timeout: 10000 });
  await pickerReady(page, nodes);
  await page.waitForTimeout(200);
};
const setLS = (page, k, v) => page.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [k, v]);
const state = (page) => page.evaluate((m) => {
  const vis = (el) => !!el && getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
  const act = document.querySelector("#tabs .tab.active[data-id]");
  const cur = document.querySelector("#mcur .nm");
  return { phoneLayout: window.matchMedia(m).matches, stripVisible: vis(document.getElementById("tabs")),
           headerVisible: vis(document.getElementById("mhdr")), listOpen: !!document.querySelector("#mlist.open"),
           active: act ? act.dataset.id : null, current: cur ? cur.textContent.trim() : null,
           activeRows: Array.from(document.querySelectorAll("#mlist .mrow.active")).map((r) => r.dataset.id),
           rowNames: Array.from(document.querySelectorAll("#mlist .mrow[data-id]")).map((r) => (r.querySelector(".nm") || r).textContent.trim()),
           headTexts: Array.from(document.querySelectorAll("#mlist .mhead")).map((h) => h.textContent.trim()) };
}, MEDIA);
const out = {};
// 1. the DESKTOP strip: a mouse, a wide window — the order the user sees on their desktop
const desk = await browser.newContext({ viewport: { width: 1400, height: 800 } });
const dpage = await desk.newPage();
await dpage.goto(cfg.chat);
await settle(dpage);
out.desktop = { strip: await readStrip(dpage), ...(await state(dpage)) };
// 2. the PHONE: a coarse pointer under 1024 px (the kernel's own media rule), the picker in the strip's place
const phoneCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 });
const page = await phoneCtx.newPage();
await page.goto(cfg.chat);
await settle(page);
await page.tap("#mcur");
await page.waitForSelector("#mlist.open", { timeout: 10000 });
await pickerReady(page);
await page.waitForTimeout(300);
out.phone = { strip: await readStrip(page), picker: await readPicker(page), ...(await state(page)) };
// 3. a copy under its SECOND tag is a row of its own and opens the session: the deploy row under infra (the
//    last deploy row), tapped
const copies = await page.$$('#mlist .mrow[data-id="' + cfg.deploy + '"]');
out.tapCopy = { copies: copies.length };
if (copies.length) {
  await copies[copies.length - 1].tap();
  await page.waitForFunction((id) => { const a = document.querySelector("#tabs .tab.active[data-id]"); return !!a && a.dataset.id === id; }, cfg.deploy, { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(300);
  Object.assign(out.tapCopy, await state(page));
}
// 4. a heading is a label, not a pick: tapped, the list stays open and nothing opens
await page.evaluate(() => { const l = document.getElementById("mlist"); if (l && !l.classList.contains("open")) document.getElementById("mcur").click(); });
await page.waitForTimeout(200);
const before = await state(page);
const head = await page.$("#mlist .mhead[data-group]");
out.tapHead = { present: !!head, before: before.active };
if (head) {
  await head.tap();
  await page.waitForTimeout(400);
  Object.assign(out.tapHead, await state(page));
}
// 5. a FOLD in the phone's own store: qa folded. The desktop hides qa's members under its header; the phone lists
//    them regardless — its heading is a label, the picker its only switcher, so nothing may fold out of reach
const FOLD = JSON.stringify({ on: true, collapsed: ["qa"], expanded: [], pinned: [] });
await page.evaluate((v) => localStorage.setItem("romp:tabgroups", v), FOLD);
await page.reload();
await settle(page);
await page.tap("#mcur");
await page.waitForSelector("#mlist.open", { timeout: 10000 });
await pickerReady(page);
await page.waitForTimeout(300);
out.phoneFolded = { strip: await readStrip(page), picker: await readPicker(page), ...(await state(page)) };
await dpage.evaluate((v) => localStorage.setItem("romp:tabgroups", v), FOLD);
await dpage.reload();
await dpage.waitForFunction(() => document.querySelectorAll("#tabs .tab[data-id]").length >= 5, null, { timeout: 30000 });   // qa's three folded away
await dpage.waitForFunction(() => document.querySelectorAll("#tabs .tab-group-head[data-group]").length >= 2, null, { timeout: 15000 }).catch(() => {});
await dpage.waitForTimeout(300);
out.desktopFolded = { strip: await readStrip(dpage), ...(await state(dpage)) };
// ── THE TRAIL MATRIX (2026-09-23): every case that can move a session between a group and the trail, or
// reorder the trail, read on BOTH surfaces side by side. Each case sets the two viewers' own stores, reloads
// both, and records the desktop strip, the phone strip and the phone picker.
const cases = [];
async function probe(label, deskNodes = FULL_NODES, phoneNodes = FULL_NODES, heads = HEADS) {
  await settle(dpage, deskNodes, heads);
  const desktop = await readStrip(dpage);
  await settle(page, phoneNodes, heads);
  await openPicker(page, phoneNodes);
  cases.push({ label, desktop, phoneStrip: await readStrip(page), picker: await readPicker(page), order: await orders() });
}
// the arrangement each viewer SHOWS (view-order.ts readViewOrder: the kernel's copy once held, else the pre-move key)
const shown = (p) => p.evaluate(() => { const s = localStorage.getItem("romp:vieworder:shared"); return s !== null ? s : localStorage.getItem("romp:vieworder"); });
async function orders() { return { desk: await shown(dpage), phone: await shown(page) }; }
const both = [dpage, page];
// A RESET clears both browsers' keys AND the kernel's viewer store: the arrangement is the kernel's since 2026-09-23
// (view-order.json), served to a browser on every reload, so clearing a browser alone resets nothing
const KEYS = ["romp:vieworder", "romp:vieworder:shared", "romp:tabgroups", "romp:settings"];
const reset = async (p) => { for (const f of cfg.viewerStore) { try { fs.unlinkSync(f); } catch (e) { /* absent */ } } for (const k of KEYS) await setLS(p, k, null); };
// 1. BASELINE: neither viewer has arranged anything — the identity transform on both, so any difference
//    here is structural
for (const p of both) { await reset(p); await p.reload(); }
await probe("baseline: neither viewer has dragged");
// 2. THE REAL PAIR: the desktop has dragged its loose tabs, the phone never has. The desktop writes the dense arrangement a drag
//    writes, through the page's one write (federation.ts __rompWriteOrder, view-order.ts writeViewOrder): cached, published to
//    the kernel, which keeps it and pushes it to the phone (2026-09-23). The phone is reloaded after, as a device opened later
await dpage.evaluate((o) => window.__rompWriteOrder(o), cfg.drag);
await page.waitForFunction((o) => localStorage.getItem("romp:vieworder:shared") === JSON.stringify(o), cfg.drag, { timeout: 15000 }).catch(() => {});
await page.reload();
await probe("the desktop has dragged its tabs; the phone has not");
// 3. …and the same arrangement written on both viewers (an unchanged republish: nothing moves)
await page.evaluate((o) => window.__rompWriteOrder(o), cfg.drag); await page.reload();
await probe("both viewers carry the same arrangement");
// 4. a FOLDED group in both stores: the desktop hides qa's members, the phone shows them (#1770, deliberate)
for (const p of both) { await reset(p); await setLS(p, "romp:tabgroups", JSON.stringify({ on: true, collapsed: ["qa"], expanded: [], pinned: [] })); await p.reload(); }
await probe("qa folded in both stores", cfg.nodes.foldedDesk, FULL_NODES);
// 5. ONE TAG GROUP PER ROW off in both: the trail stands behind its visible divider instead of a row break
for (const p of both) { await reset(p); await setLS(p, "romp:settings", JSON.stringify({ stripGroupRows: false })); await p.reload(); }
await probe("one tag group per row off in both");
// 6. the chat LENS narrowed to the tagged sessions (kernel-persisted, so the same for both viewers): every
//    untagged session loses its tab. The picker is the phone's only switcher — does it still list them?
for (const p of both) { await reset(p); }
fs.writeFileSync(cfg.viewsFile, JSON.stringify(cfg.lensViews));
for (const p of both) { await p.reload(); }
await probe("the chat lens narrowed to the tagged sessions (shared)", cfg.nodes.lens, cfg.nodes.lens);
fs.writeFileSync(cfg.viewsFile, JSON.stringify(cfg.baseViews));
for (const p of both) { await p.reload(); }
await settle(dpage); await settle(page);
// 7. THE LATE ARRIVALS, the decisive case: neither viewer has ever dragged, and two untagged sessions land
//    WHILE THE DESKTOP IS OPEN and the phone is not. The desktop adopts each as its frame lands (one at a
//    time, in arrival order); a phone opened afterwards meets them all at once, in the kernel's list order.
//    Both arrangements are "never dragged", so any difference here is romp:vieworder's adoption, not a drag.
for (const p of both) { await reset(p); await p.reload(); }
await settle(dpage); await settle(page);
let grown = FULL_NODES;
for (const s of cfg.late) {
  for (const f of s.files) fs.writeFileSync(f[0], f[1]);
  grown += 1;
  await dpage.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length === n, grown, { timeout: 30000 });
  // the adoption writes the arrangement synchronously on the frame it renders (to the kernel's cached copy since 2026-09-23),
  // so the entry is the event (a local id sits in that store bare: federation prefixes remote ids only)
  await dpage.waitForFunction((sid) => JSON.parse(localStorage.getItem("romp:vieworder:shared") || "[]").includes(sid), s.sid, { timeout: 10000 });
}
await settle(dpage, grown, HEADS);
// a phone that opens only NOW, having never seen these sessions: its own fresh profile, never dragged
const freshCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 });
const freshPhone = await freshCtx.newPage();
await freshPhone.goto(cfg.chat);
await settle(freshPhone, grown, HEADS);
await openPicker(freshPhone, grown);
cases.push({ label: "two untagged sessions arrive while only the desktop is open", desktop: await readStrip(dpage),
             phoneStrip: await readStrip(freshPhone), picker: await readPicker(freshPhone),
             order: { desk: await shown(dpage), phone: await shown(freshPhone) } });
await freshCtx.close();
// 8. A PICKER ROW REUSED ACROSS A STRIP RE-RENDER (CI, 2026-09-23): the row key collapses a missing copy attribute and the
//    trail's empty one, so a row made while the strip was flat is reused once the strip sections; its copy attribute must follow
//    the tab's. Driven on the DOM the picker scrapes: a trail tab leaves (its row goes), returns without its copy (its row is
//    MADE without one), then gains the trail's copy under a child-list poke (the observer's filter ignores attribute changes;
//    the strip's own re-render moves children too): the REUSED row must carry it. Each step waits on the row's state, never a clock.
out.copyRefresh = await page.evaluate(async () => {
  const tabs = document.getElementById("tabs"), list = document.getElementById("mlist");
  const tab = tabs.querySelector('.tab[data-id][data-copy=""]');
  if (!tab) return { tab: false };
  const id = tab.dataset.id, next = tab.nextSibling;
  const rowCopy = () => { const r = list.querySelector('.mrow[data-id="' + id + '"]'); return r ? (r.hasAttribute("data-copy") ? r.getAttribute("data-copy") : null) : "no-row"; };
  const until = async (f) => { for (let i = 0; i < 200; i++) { if (f()) return true; await new Promise((r) => setTimeout(r, 25)); } return false; };   // loop-ok: bounded, on the DOM's state
  tab.remove();
  const gone = await until(() => rowCopy() === "no-row");
  tab.removeAttribute("data-copy"); tabs.insertBefore(tab, next);
  const made = await until(() => rowCopy() === null);
  tab.setAttribute("data-copy", ""); const poke = document.createElement("i"); tabs.appendChild(poke); poke.remove();
  const refreshed = await until(() => rowCopy() === "");
  return { tab: true, id, gone, made, refreshed, rowCopy: rowCopy(), stripCopy: tab.getAttribute("data-copy") };
});
out.matrix = cases;
fs.writeFileSync(cfg.out, JSON.stringify(out));
fs.writeSync(1, "RESULT:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


def names(seq):
    """A sequence with the sids replaced by the demo names, for readable diffs."""
    def one(tok):
        if tok.startswith("t:"):
            sid, _, copy = tok[2:].partition("/")
            return "t:%s/%s" % (NAME_OF.get(sid, sid), copy)
        return tok
    return [one(t) for t in seq]


def sections(seq):
    """A strip or picker as (group, {member names}) in order: a heading opens a group, the divider opens
    the untagged trail (None), and a sequence with no heading at all is one flat run ("-")."""
    out, cur = [], None
    for tok in names(seq):
        if tok.startswith("g:"):
            cur = (tok[2:], set()); out.append(cur)
        elif tok == "sep":
            cur = (None, set()); out.append(cur)
        elif tok.startswith("t:"):
            if cur is None:
                cur = ("-", set()); out.append(cur)
            cur[1].add(tok[2:].partition("/")[0])
    return out


def trail(seq):
    """The UNGROUPED trail as a surface renders it: the session names after the untagged divider, in order.
    None when the surface draws no trail at all — a flat strip (no divider) or no loose session left."""
    toks = names(seq)
    if "sep" not in toks:
        return None
    return [t[2:].partition("/")[0] for t in toks[toks.index("sep") + 1:] if t.startswith("t:")]


def full_rows(seq):
    """Every row with its session name, headings and divider included — the whole sequence, for the table."""
    return names(seq)


class ServedMobilePickerOrder(unittest.TestCase):
    maxDiff = None
    result = None

    def _matrix(self):
        return self._run()["matrix"]

    @staticmethod
    def _trail_table(cases):
        """The per-case table the follow-up asks for: each case's trail on the desktop strip and in the phone
        picker, in order, with the membership sets and the two viewers' arrangements."""
        out = ["", "%-52s %-34s %-34s %s" % ("case", "desktop trail", "phone picker trail", "same?")]
        for c in cases:
            d, p = trail(c["desktop"]), trail(c["picker"])
            out.append("%-52s %-34s %-34s %s" % (c["label"][:52], d, p, "yes" if d == p else "NO"))
            if d != p:
                dm, pm = (set(d) if d else set()), (set(p) if p else set())
                out.append("%-52s   order %s / membership %s%s" % (
                    "", "differs" if (d and p and sorted(d) == sorted(p)) else "n/a", "same" if dm == pm else "differs",
                    "" if dm == pm else "  desktop-only %s phone-only %s" % (sorted(dm - pm), sorted(pm - dm))))
        return "\n".join(out)

    @staticmethod
    def _rows_table(c):
        return "\n  desktop: %s\n  phone strip: %s\n  phone picker: %s\n  arrangements: %s" % (
            full_rows(c["desktop"]), full_rows(c["phoneStrip"]), full_rows(c["picker"]), c["order"])

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
        cls.lab = tempfile.mkdtemp(prefix="mobile-order-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)   # tests/dist_copy: skips the bundler's staging files
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root of its own: no per-session host process (CLAUDE.md, 2026-09-11)
        # the machine's user manager is not the lab's: these shadow systemctl and systemd-run on the lab kernel's PATH, so
        # the boot reconcile's scope listing (it lists for every session it finds alive) sees an empty manager
        cls.fakebin = os.path.join(cls.lab, "fakebin")
        os.makedirs(cls.fakebin)
        for tool, body in (("systemctl", "exit 0\n"), ("systemd-run", "echo 'no user manager in this lab' >&2\nexit 1\n")):
            Path(cls.fakebin, tool).write_text("#!/bin/sh\n" + body)
            os.chmod(os.path.join(cls.fakebin, tool), 0o755)
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
            # mtime rises with the arrival index: discovery lists transcripts newest first and mtime TIES fall to lexical
            # sid order (arrival order here), so TRAIL_RENDERED pins the code's newest-first order, not the runner's clock
            os.utime(Path(proj, sid + ".jsonl"), (t0 + i, t0 + i))
        cls.state, cls.cwd = state, cwd   # the late arrivals' files are written mid-run, by the driver
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "tags": TAGS, "tagOrder": TAG_ORDER}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-mobileorder"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST", ROMP_CLI_SCOPE="0")
        env["PATH"] = cls.fakebin + os.pathsep + env.get("PATH", os.environ.get("PATH", ""))
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
        """One driver run for every case (the taps are sequential on one page); its result, or its failure, is shared."""
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
            late = []
            for i, name in enumerate(LATE):
                sid = LATE_SIDS[name]
                bg, fg = PALETTE[i % len(PALETTE)]
                late.append({"sid": sid, "name": name, "files": [
                    [os.path.join(cls.state, "names", sid), "%s\t%s\t%s\t%s\n" % (name, cls.cwd, bg, fg)],
                    [os.path.join(cls.state, "sdk", sid + ".json"), json.dumps(
                        {"sid": sid, "name": name, "cwd": cls.cwd, "mode": "auto", "effort": "high", "lastSid": sid,
                         "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"})]]})
            base_views = {"active": "all", "tags": TAGS, "tagOrder": TAG_ORDER}
            # the chat lens narrowed to the three tags that hold members: every UNTAGGED session loses its tab
            lens_views = dict(base_views, actives={"chat": {"tags": ["qa", "infra", "solo"]}})
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": out,
                       "deploy": SIDS["deploy"], "heads": HEADS,
                       "nodes": {"full": FULL_NODES, "foldedDesk": FOLDED_DESK_NODES, "lens": LENS_NODES},
                       "drag": [SIDS[n] for n in DRAG_NAMES],
                       "viewsFile": os.path.join(cls.lab, "xdg", "romp", "timeline-views.json"),
                       # the kernel's viewer store (2026-09-23): the arrangement every device reads
                       "viewerStore": [os.path.join(cls.lab, "xdg", "romp", "view-order.json")],
                       "baseViews": base_views, "lensViews": lens_views, "late": late}, f)
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
        if os.environ.get("MOBILE_ORDER_DUMP"):
            Path(os.environ["MOBILE_ORDER_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    # ── the layouts the lab drove are the ones it meant to ──
    def test_the_two_contexts_land_on_the_two_layouts(self):
        r = self._run()
        self.assertFalse(r["desktop"]["phoneLayout"], "a mouse and 1400 px: the desktop layout")
        self.assertTrue(r["desktop"]["stripVisible"])
        self.assertTrue(r["phone"]["phoneLayout"], "a coarse pointer at 390 px: the kernel's phone rule holds")
        self.assertFalse(r["phone"]["stripVisible"], "the phone page hides the strip…")
        self.assertTrue(r["phone"]["headerVisible"], "…and shows the picker's header in its place")
        self.assertTrue(r["phone"]["listOpen"], "the tap on the current-session chip opened the list")

    # ── the bug: the picker's order is the desktop strip's, headings included ──
    def test_the_desktop_strip_groups_by_tag_in_tag_order_with_the_trail_last(self):
        # the fixture's shape (the kernel lists the newest session first, so the order inside a group is its own):
        # qa then infra, in tag order, deploy under both, the three untagged behind the divider
        r = self._run()
        self.assertEqual(sections(r["desktop"]["strip"]),
                         [("qa", MEMBERS["qa"]), ("infra", MEMBERS["infra"]), ("solo", MEMBERS["solo"]), (None, MEMBERS[None])],
                         names(r["desktop"]["strip"]))

    def test_the_phone_picker_reads_the_same_as_the_desktop_strip(self):
        r = self._run()
        self.assertEqual(names(r["phone"]["picker"]), names(r["desktop"]["strip"]),
                         "the phone picker (left) lists the sessions in another order, or without the strip's headings, "
                         "than the desktop strip (right)")
        self.assertEqual(names(r["phone"]["picker"]), names(r["phone"]["strip"]),
                         "…and mirrors its own page's strip one for one: the strip is the picker's one source")

    def test_the_rows_keep_their_state_cues(self):
        r = self._run()
        p = r["phone"]
        self.assertIsNotNone(p["active"], "an active tab")
        self.assertEqual(sorted(set(p["activeRows"])), [p["active"]], "every row of the active session wears .active (its copies too)")
        self.assertEqual(p["rowNames"], [t.split("/")[0][2:] for t in names(p["picker"]) if t.startswith("t:")],
                         "each row names its session")
        self.assertEqual(p["headTexts"], ["qa3", "infra3", "solo1"],
                         "a heading is the tag's chip and the member count, nothing else (no caret: it folds nothing)")
        self.assertEqual(p["current"], NAME_OF[p["active"]], "the current-session chip names the active session")

    # ── the copies: a session under two tags is a row under each, and either opens it ──
    def test_a_copy_under_its_second_tag_is_a_row_of_its_own_that_opens_the_session(self):
        r = self._run()
        t = r["tapCopy"]
        self.assertEqual(t["copies"], 2, "deploy is under qa and under infra: two rows")
        self.assertEqual(t["active"], SIDS["deploy"], "the tap on the infra copy opened deploy")
        self.assertEqual(t["current"], "deploy")
        self.assertFalse(t["listOpen"], "a pick closes the list")

    # ── a heading is a label ──
    def test_a_heading_is_a_label_not_a_pick(self):
        r = self._run()
        t = r["tapHead"]
        self.assertTrue(t["present"], "the picker has headings")
        self.assertEqual(t["active"], t["before"], "tapping a heading opens nothing")
        self.assertTrue(t["listOpen"], "…and the list stays open for the pick")

    # ── folds are the desktop's: the phone hides no session from its only switcher ──
    def test_a_fold_hides_nothing_on_the_phone_where_the_desktop_folds(self):
        r = self._run()
        self.assertEqual(names(r["phoneFolded"]["picker"]), names(r["desktop"]["strip"]),
                         "qa folded in the phone's store: the phone lists qa's members regardless, in the strip's order")
        self.assertEqual(sections(r["desktopFolded"]["strip"]),
                         [("qa", set()), ("infra", MEMBERS["infra"]), ("solo", MEMBERS["solo"]), (None, MEMBERS[None])],
                         "the same store on the desktop folds qa: its header alone, no member tab")

    # ── THE TRAIL (the user 2026-09-23: the groups match now, the ungrouped tabs do not) ──
    # The measured answer (the table this class prints): the trail's MEMBERSHIP never diverges, and since the kernel keeps
    # the viewer's arrangement (view-order.ts, 2026-09-23) neither does its ORDER: the one case that used to differ, a
    # desktop that had dragged and a phone that had not, now reads alike (pinned on its own below).
    DRAGGED = "the desktop has dragged its tabs; the phone has not"

    def test_the_trail_reads_the_same_on_both_surfaces_in_every_case(self):
        """Whatever moves a session between a group and the trail, or reorders the trail, the phone picker's
        trail and the desktop strip's read alike — same members, same order, in every case."""
        cases = self._matrix()
        bad = [c for c in cases if trail(c["desktop"]) != trail(c["picker"])]
        self.assertEqual([c["label"] for c in bad], [],
                         self._trail_table(cases) + "".join(self._rows_table(c) for c in bad))

    def test_the_trails_MEMBERSHIP_never_diverges_not_even_in_the_deliberate_case(self):
        """The set is the part that is never a matter of taste: a session loose on one surface is loose on the
        other, whatever either viewer has dragged, folded or set."""
        cases = self._matrix()
        bad = [(c["label"], set(trail(c["desktop"]) or []), set(trail(c["picker"]) or []))
               for c in cases if set(trail(c["desktop"]) or []) != set(trail(c["picker"]) or [])]
        self.assertEqual(bad, [], self._trail_table(cases))

    def test_a_desktops_arrangement_reaches_the_phone_that_never_dragged(self):
        """The difference that used to be deliberate, gone: until 2026-09-23 the arrangement was each browser's own (the
        2026-07-31 ruling), so a desktop that had dragged its loose tabs read in its order and a phone that never had read
        the kernel's. The kernel keeps the viewer's arrangement now, so the desktop's reaches the phone: the same sessions,
        under the same headings, in the one sequence the desktop dragged them into."""
        c = next(c for c in self._matrix() if c["label"] == self.DRAGGED)
        d, p = trail(c["desktop"]), trail(c["picker"])
        self.assertEqual(d, TRAIL_DRAGGED, "the desktop renders its arrangement: %s" % self._rows_table(c))
        self.assertEqual(p, TRAIL_DRAGGED, "and so does the phone, which never dragged: %s" % self._rows_table(c))
        self.assertEqual(c["order"]["desk"], c["order"]["phone"], "the two viewers hold the one arrangement")
        self.assertEqual([n for n, _ in sections(c["desktop"])], [n for n, _ in sections(c["picker"])],
                         "the groups read alike too: their order is the kernel's tagOrder")

    def test_every_case_the_phone_picker_mirrors_its_own_pages_strip(self):
        """The picker is built from the strip it sits on, so these can never differ — a case where they do
        is a picker bug, not a plan one, and says so separately from the surface-to-surface comparison."""
        cases = self._matrix()
        bad = [c for c in cases if c["picker"] != c["phoneStrip"]]
        self.assertEqual(bad, [], "".join(self._rows_table(c) for c in bad))

    def test_a_picker_row_reused_across_a_strip_re_render_follows_the_tabs_copy(self):
        """CI, 2026-09-23 (main, the served-labs step): the mirror case 'qa folded in both stores' read the phone's first trail row as a
        flat-strip row (no copy attribute) against its own strip's tab, which carried the trail's empty copy. The picker keys rows so that a
        missing copy and the empty one collide, and its in-place update never refreshed the attribute, so a row made while the strip was flat
        kept the stale attribute once the strip sectioned. Driven on the DOM: the row goes with its tab, is made without a copy when the tab
        returns flat, and follows the tab's copy once it is back (before: the reused row kept the missing attribute)."""
        r = self._run()["copyRefresh"]
        self.assertTrue(r.get("tab"), "premise: a trail tab with the empty copy on the phone's strip: %r" % r)
        self.assertTrue(r["gone"], "premise: the row leaves with its tab: %r" % r)
        self.assertTrue(r["made"], "premise: the tab back on a flat strip makes a row without a copy attribute: %r" % r)
        self.assertEqual((r["refreshed"], r["rowCopy"], r["stripCopy"]), (True, "", ""), "the reused row follows the tab's copy (before: it kept the missing attribute and read as a flat-strip row): %r" % r)

    def test_a_single_member_tag_sections_on_both_surfaces_and_stays_out_of_the_trail(self):
        """`solo` holds exactly one session: no minimum-size rule may leave it grouped on one surface and
        loose on the other."""
        for c in self._matrix():
            for surface in ("desktop", "picker"):
                secs = dict((n, m) for n, m in sections(c[surface]))
                self.assertIn("solo", secs, "%s / %s: no solo section: %s" % (c["label"], surface, self._rows_table(c)))
                self.assertEqual(secs["solo"], {"mailer"}, "%s / %s: %s" % (c["label"], surface, self._rows_table(c)))
                self.assertNotIn("mailer", set(trail(c[surface]) or []), "%s / %s" % (c["label"], surface))

    def test_a_tag_holding_no_visible_member_yields_no_section_on_either_surface(self):
        for c in self._matrix():
            for surface in ("desktop", "picker"):
                self.assertNotIn("empty", [n for n, _ in sections(c[surface])], "%s / %s" % (c["label"], surface))

    def test_the_double_tagged_session_has_a_copy_per_group_and_is_never_in_the_trail(self):
        for c in self._matrix():
            for surface in ("desktop", "picker"):
                self.assertNotIn("deploy", set(trail(c[surface]) or []), "%s / %s: %s" % (c["label"], surface, self._rows_table(c)))

    def test_a_view_hidden_session_is_listed_by_neither_surface(self):
        """The narrowed chat lens is the kernel's, shared by both viewers: an untagged session it hides has no
        tab on the desktop and no row on the phone. The picker is the phone's only switcher, but a lens the
        user set on this session's behalf is not a fold — it is what they asked to see."""
        c = next(c for c in self._matrix() if c["label"].startswith("the chat lens narrowed"))
        self.assertIsNone(trail(c["desktop"]), self._rows_table(c))
        self.assertIsNone(trail(c["picker"]), self._rows_table(c))
        for surface in ("desktop", "picker"):
            named = {t[2:].partition("/")[0] for t in names(c[surface]) if t.startswith("t:")}
            self.assertEqual(named & MEMBERS[None], set(), "%s lists a view-hidden session: %s" % (surface, self._rows_table(c)))


if __name__ == "__main__":
    unittest.main()
