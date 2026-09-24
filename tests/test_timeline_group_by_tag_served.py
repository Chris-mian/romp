#!/usr/bin/env python3
"""T399 (the user 2026-09-12): GROUP BY TAG in the Sessions pane, on the real /timeline page of a hermetic kernel over a
SYNTHETIC world (the notes-api demo: web, api, tests, docs, infra, old-notes; host TESTHOST) with tags backend {api, web},
frontend {web, docs} and archived {old-notes}, tests and infra untagged, and one message from api to web.

Asserted on the page: with the switch on (romp:tabgroups.timeline, the strip's own blob), one section per tag in the tag
order, each head ONE chip (the tag's name in its colour, tagChip's mirror), the caret and the count; web under BOTH
backend and frontend, and the api-to-web connector landing on web's FIRST lane; archived folded by default to its head
alone; the untagged trail behind a divider; a click on a head folds and opens its section and writes the fold into the
strip's blob in the strip's shape. With the switch OFF the pane is as it was: no heads, no divider, the lanes in the
pane's order at the pane's row pitch, the SVG the pane's own height. Every read waits on the pane's own draw (the
lanes, heads and connector in the DOM; a click's fold state after it), never a fixed pause: a loaded CI runner drew the
pane after a pause had run out (2026-09-13). With T399_SHOTS=<dir> the driver writes
sessions-group-by-tag-dark.png and sessions-group-by-tag-light.png (a lab copies them to the drops folder under the
task's name). Skips LOUDLY without the extension deps or a Playwright browser."""
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
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the port is chosen below, never read from the env)

WEB, API, TESTS = "11111111-2222-3333-4444-000000000001", "11111111-2222-3333-4444-000000000002", "11111111-2222-3333-4444-000000000003"
DOCS, INFRA, OLD = "11111111-2222-3333-4444-000000000004", "11111111-2222-3333-4444-000000000005", "11111111-2222-3333-4444-000000000006"
SESSIONS = [("web", WEB, "#9cd2ff", "#0c1a2e"), ("api", API, "#1EA1EB", "#ffffff"), ("tests", TESTS, "#54B204", "#ffffff"),
            ("docs", DOCS, "#e0a54a", "#1a1200"), ("infra", INFRA, "#c47ad4", "#ffffff"), ("old-notes", OLD, "#8a8a8a", "#ffffff")]
NAMES = [s[0] for s in SESSIONS]


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def turns(sid, t0, n):
    out, parent = [], None
    for k in range(n):
        t = t0 + k * 900
        u, a = "%s-u%d" % (sid[-4:], k), "%s-a%d" % (sid[-4:], k)
        out.append({"type": "user", "timestamp": iso(t), "uuid": u, "parentUuid": parent, "promptSource": "sdk", "sessionId": sid,
                    "message": {"role": "user", "content": "Synthetic prompt %d." % k}})
        out.append({"type": "assistant", "timestamp": iso(t + 120 + 60 * k), "uuid": a, "parentUuid": u, "sessionId": sid,
                    "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                "content": [{"type": "text", "text": "Synthetic reply %d." % k}]}})
        parent = a
    return out


def send_pair(t, uuid, parent, sid, to, body):
    tu = "tu_" + uuid
    return [{"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": sid,
             "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "tool_use",
                         "content": [{"type": "tool_use", "id": tu, "name": "mcp__romp-postal-service__send_message",
                                      "input": {"to": to, "body": body, "kind": "coordinate"}}]}},
            {"type": "user", "timestamp": iso(t + 1), "uuid": uuid + "r", "parentUuid": uuid, "sessionId": sid,
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu, "content": "Delivered to '%s'." % to}]}}]


DRIVER = r"""
import fs from "node:fs";
import { createRequire } from "node:module";
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const { chromium } = createRequire(import.meta.url)(cfg.pw);
const browser = await chromium.launch();
const NAMES = cfg.names;
const measure = ({ names, web }) => ({
  heads: Array.from(document.querySelectorAll(".tl-group-head")).map((g) => ({
    name: g.dataset.group, folded: g.dataset.folded === "1",
    chips: g.querySelectorAll("text").length - 2,              // the name, less the caret and the count texts: one chip = one name text
    chipFill: (g.querySelector("text") || {}).getAttribute ? g.querySelector("text").getAttribute("fill") : null,
    chipStroke: (g.querySelectorAll("rect")[1] || {}).getAttribute ? g.querySelectorAll("rect")[1].getAttribute("stroke") : null,
    chipBg: (g.querySelectorAll("rect")[1] || {}).getAttribute ? g.querySelectorAll("rect")[1].getAttribute("fill") : null,
    caret: g.querySelectorAll("text")[1] ? g.querySelectorAll("text")[1].textContent : null,
    count: g.querySelectorAll("text")[2] ? g.querySelectorAll("text")[2].textContent : null,
    y: g.querySelector("rect") ? +g.querySelector("rect").getAttribute("y") : null })),
  lanes: Array.from(document.querySelectorAll("svg text")).filter((t) => names.indexOf(t.textContent) >= 0 && t.getAttribute("font-weight") !== "400")
    .map((t) => ({ name: t.textContent, y: +t.getAttribute("y") })),
  dividers: document.querySelectorAll(".tl-trail-sep").length,
  svgH: +document.querySelector(".romp-tl-wrap svg").getAttribute("height"),
  connector: (() => { const p = document.querySelector('path[data-tl-to="' + web + '"]'); if (!p) return null;
    const nums = (p.getAttribute("d") || "").match(/-?[\d.]+/g).map(Number); return { endY: nums[nums.length - 1], from: p.getAttribute("data-tl-from") }; })(),
  blob: (() => { try { return JSON.parse(localStorage.getItem("romp:tabgroups") || "null"); } catch (e) { return "unparseable"; } })(),
  // the FOLDS, every device's since 2026-09-23: the kernel keeps them, and this browser's copy is here (tab-groups.ts TabFolds)
  folds: (() => { try { return JSON.parse(localStorage.getItem("romp:tabgroups:shared") || "null"); } catch (e) { return "unparseable"; } })(),
});
const results = {};
for (const pass of [{ name: "dark", theme: "dark", on: true }, { name: "light", theme: "light", on: true }, { name: "off", theme: "dark", on: false }]) {
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 560 }, deviceScaleFactor: 2 });
  await ctx.addInitScript(({ theme, on }) => {
    localStorage.setItem("romp:tabgroups", JSON.stringify(on ? { on: true, collapsed: [], expanded: [], pinned: [], timeline: true } : { on: true, collapsed: [], expanded: [], pinned: [] }));
    if (theme === "light") localStorage.setItem("romp:settings", JSON.stringify({ theme: "yatharth-light" }));
  }, pass);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("pageerror:", e.message));
  await page.goto(cfg.url);
  // every read waits on the pane's OWN draw (a CI runner under load drew the pane after a fixed pause had run out: the
  // driver read an empty SVG and the lab failed on another PR's run, 2026-09-13): the lanes and heads in the DOM, and on
  // the grouped passes the api-to-web connector too, which rides the deferred bars payload; never a fixed pause
  const drawn = ({ names, on, web }) => {
    const lanes = Array.from(document.querySelectorAll("svg text")).filter((t) => names.indexOf(t.textContent) >= 0).length;
    const heads = document.querySelectorAll(".tl-group-head").length;
    const connector = !!document.querySelector('path[data-tl-to="' + web + '"]');
    return on ? heads >= 3 && lanes >= 6 && connector : lanes >= 6 && connector;
  };
  try {
    await page.waitForFunction(drawn, { names: NAMES, on: pass.on, web: cfg.web }, { timeout: 90000 });   // the python side's cap covers three of these and three fold waits
  } catch (e) {
    const st = await page.evaluate(() => ({ heads: document.querySelectorAll(".tl-group-head").length, texts: Array.from(document.querySelectorAll("svg text")).map((t) => t.textContent).slice(0, 40) }));
    console.error("lanes missing (" + pass.name + "): " + JSON.stringify(st)); process.exit(1);
  }
  const r = { first: await page.evaluate(measure, { names: NAMES, web: cfg.web }) };
  if (pass.on) {
    if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/sessions-group-by-tag-" + pass.theme + ".png", fullPage: false }); }
    if (pass.name === "dark") {
      // fold backend by its head, read the blob, open it again, then open the default-folded archived
      // each click waits on the redraw it causes: the head's fold state in the DOM, never a fixed pause
      const foldedIs = ({ name, folded }) => { const g = document.querySelector('.tl-group-head[data-group="' + name + '"]'); return !!g && g.dataset.folded === (folded ? "1" : "0"); };
      await page.click('.tl-group-head[data-group="backend"] rect');
      await page.waitForFunction(foldedIs, { name: "backend", folded: true }, { timeout: 20000 });
      r.folded = await page.evaluate(measure, { names: NAMES, web: cfg.web });
      await page.click('.tl-group-head[data-group="backend"] rect');
      await page.waitForFunction(foldedIs, { name: "backend", folded: false }, { timeout: 20000 });
      r.reopened = await page.evaluate(measure, { names: NAMES, web: cfg.web });
      await page.click('.tl-group-head[data-group="archived"] rect');
      await page.waitForFunction(foldedIs, { name: "archived", folded: false }, { timeout: 20000 });
      r.archivedOpen = await page.evaluate(measure, { names: NAMES, web: cfg.web });
      // …and folded again: the folds are the kernel's since 2026-09-23, served to every later context, so the passes after
      // this one start from the defaults only if this one leaves them there
      await page.click('.tl-group-head[data-group="archived"] rect');
      await page.waitForFunction(foldedIs, { name: "archived", folded: true }, { timeout: 20000 });
    }
  }
  results[pass.name] = r;
  await ctx.close();
}
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify(results) + "\n", () => process.exit(0));
"""


class ServedGroupByTag(unittest.TestCase):
    maxDiff = None
    LANE_GAP, TOP, BOTTOM = 26, 8, 27          # romp-timeline-view.js LANE_GAP and this.M (top, bottom)

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
        cls.lab = tempfile.mkdtemp(prefix="t399-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states", "timeline"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        now = int(time.time())
        for i, (name, sid, bg, fg) in enumerate(SESSIONS):
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps({"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid,
                                                                       "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
            recs = turns(sid, now - 3300 + i * 200, 3)
            if sid == API:                                   # api mails web once, mid-window: the connector lands on web's lane
                recs += send_pair(now - 1500, "api-send-1", recs[-1]["uuid"], API, "web", "Synthetic heads-up for the lab.")
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "timeline", "messages.jsonl").write_text(
            json.dumps({"t": now - 1500, "ev": "sent", "id": "m-1", "from": "api", "from_id": API, "to_id": WEB, "body": "Synthetic heads-up for the lab.",
                        "kind": "coordinate", "from_host": ""}) + "\n" + json.dumps({"t": now - 1480, "ev": "exec", "id": "m-1"}) + "\n")
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "tagOrder": ["backend", "frontend", "archived"], "tags": [
            {"id": "t-backend", "name": "backend", "color": "#1EA1EB", "members": [API, WEB]},
            {"id": "t-frontend", "name": "frontend", "color": "#e0a54a", "members": [WEB, DOCS]},
            {"id": "t-archived", "name": "archived", "color": "#8a8a8a", "members": [OLD]}]}))
        cls.port, cls.token = _lab._free_port(), "testtok-t399"
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

    _r = None

    def _result(self):
        cls = type(self)
        if cls._r is not None:
            return cls._r
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/timeline?token=%s" % (self.port, self.token), "names": NAMES, "web": WEB,
                       "pw": os.path.join(EXT, "node_modules", "playwright"), "shots": os.environ.get("T399_SHOTS", "")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        Path(driver).write_text(DRIVER)
        # the cap covers the driver's own bounds (three first-read waits of 90 s and three fold waits of 20 s, 330 s) with room, so
        # on a loaded runner the driver dies by ITS bound and prints its lanes-missing diagnostic, never by this one in silence
        p = subprocess.run(["node", driver, cfg], capture_output=True, text=True, timeout=420)
        klog = Path(self.klog).read_text()[-3000:] if os.path.exists(self.klog) else ""
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + "\n" + p.stderr[-3000:] + "\nkernel:\n" + klog)
        line = [ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")][-1]
        cls._r = json.loads(line[len("RESULT:"):])
        return cls._r

    def _lane_y(self, i):
        return self.TOP + i * self.LANE_GAP + self.LANE_GAP * 0.5

    def test_the_sections_render_one_tag_per_row_with_the_shared_chip_and_the_copies_and_trail_the_strip_shows(self):
        r = self._result()
        for theme in ("dark", "light"):
            m = r[theme]["first"]
            self.assertEqual([(h["name"], h["folded"], h["count"]) for h in m["heads"]], [("backend", False, "2"), ("frontend", False, "2"), ("archived", True, "1")],
                             "%s: one section per tag in the tag order, archived folded by default: %r" % (theme, m["heads"]))
            for h in m["heads"]:
                self.assertEqual(h["chips"], 1, "%s: one tag per row: %r" % (theme, h))
                self.assertEqual(h["chipBg"], "transparent", "%s: tagChip's transparent ground, never a filled pill: %r" % (theme, h))
                self.assertEqual(h["chipStroke"], h["chipFill"], "%s: the 1px border and the name in the tag's own colour: %r" % (theme, h))
                self.assertEqual(h["caret"], "▸" if h["folded"] else "▾", "%s: the caret after the chip says the fold" % theme)
            self.assertEqual([h["chipFill"] for h in m["heads"]], ["#1EA1EB", "#e0a54a", "#8a8a8a"], "%s: the tags' colours" % theme)
            self.assertEqual([l["name"] for l in m["lanes"]], ["api", "web", "docs", "web", "infra", "tests"],
                             "%s: web under both backend and frontend; old-notes folded away; infra and tests trail: %r" % (theme, m["lanes"]))
            self.assertEqual(m["dividers"], 1, "%s: the untagged trail behind one divider" % theme)
            # the rows: head, api, web, head, docs, web, head(archived), divider, infra, tests = 10 rows
            self.assertEqual(m["svgH"], self.TOP + 10 * self.LANE_GAP + self.BOTTOM, "%s: the SVG counts heads and the divider as rows" % theme)
            ys = [l["y"] for l in m["lanes"]]
            # rows: head, api(1), web(2), head, docs(4), web(5), head, divider, infra(8), tests(9): the lanes' offsets from api's row
            self.assertEqual([round(y - ys[0]) for y in ys], [26 * (r - 1) for r in (1, 2, 4, 5, 8, 9)], "%s: the lanes sit on the row pitch with the heads and the divider between: %r" % (theme, ys))
            self.assertIsNotNone(m["connector"], "%s: the api-to-web connector drew" % theme)
            self.assertEqual(m["connector"]["from"], API)
            first_web = next(l for l in m["lanes"] if l["name"] == "web")
            # the connector ends at the lane's centre (row 2, under backend: laneY = TOP + 2 * LANE_GAP + LANE_GAP / 2); the
            # name text's y is that centre plus its baseline offset, so the centre is read back from the text
            self.assertLess(abs(first_web["y"] - 3.5 - self._lane_y(2)), 2, "%s: web's first lane is row 2: %r" % (theme, first_web))
            self.assertLess(abs(m["connector"]["endY"] - self._lane_y(2)), 6,
                            "%s: the connector lands on web's FIRST lane (row 1, under backend), not its frontend copy: end %r, web rows %r"
                            % (theme, m["connector"]["endY"], [l["y"] for l in m["lanes"] if l["name"] == "web"]))
            self.assertEqual(m["blob"].get("timeline"), True, "%s: the switch read from the strip's blob" % theme)

    def test_a_click_on_the_head_folds_and_opens_the_section_and_writes_the_fold_into_the_strips_blob_in_its_shape(self):
        r = self._result()["dark"]
        f = r["folded"]
        self.assertEqual([(h["name"], h["folded"]) for h in f["heads"]], [("backend", True), ("frontend", False), ("archived", True)])
        self.assertEqual([l["name"] for l in f["lanes"]], ["docs", "web", "infra", "tests"], "backend's lanes gone, web's frontend copy stays")
        self.assertEqual(f["folds"], {"collapsed": ["backend"], "expanded": [], "pinned": []},
                         "the strip's shape: collapsed names the fold, everything else carried (tab-groups.ts setSectionCollapsed), in the "
                         "folds every device shares (2026-09-23)")
        self.assertEqual((f["blob"]["on"], f["blob"]["timeline"]), (True, True), "the switches stay this browser's, in its own blob")
        o = r["reopened"]
        self.assertEqual([(h["name"], h["folded"]) for h in o["heads"]], [("backend", False), ("frontend", False), ("archived", True)])
        self.assertEqual(o["folds"]["collapsed"], [], "opening drops the name: minimal storage, as the strip")
        a = r["archivedOpen"]
        self.assertEqual([(h["name"], h["folded"]) for h in a["heads"]][2], ("archived", False))
        self.assertEqual(a["folds"]["expanded"], ["archived"], "a default-folded section opened is remembered under expanded")
        self.assertEqual([l["name"] for l in a["lanes"]], ["api", "web", "docs", "web", "old-notes", "infra", "tests"])

    def test_with_the_switch_off_the_pane_is_as_it_was(self):
        m = self._result()["off"]["first"]
        self.assertEqual(m["heads"], [], "no heads")
        self.assertEqual(m["dividers"], 0, "no divider")
        self.assertEqual(len(m["lanes"]), 6, "every session a lane, once: %r" % m["lanes"])
        ys = [l["y"] for l in m["lanes"]]
        self.assertEqual([round(y - ys[0]) for y in ys], [26 * i for i in range(6)], "the lanes at the pane's own pitch, nothing between them")
        self.assertEqual(m["svgH"], self.TOP + 6 * self.LANE_GAP + self.BOTTOM, "the SVG the pane's own height")
        self.assertNotIn("timeline", m["blob"], "the blob as before T399")


if __name__ == "__main__":
    unittest.main()
