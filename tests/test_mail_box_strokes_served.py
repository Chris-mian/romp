"""A chat mail row's bordered box must show nothing at its left but its OWN neutral border and its content (the user
2026-09-19, a screenshot: an outgoing mail box wore extra identity-colour vertical strokes at its left edge). The
defect, diagnosed: an OUTGOING boxed postal .notice drew its 2px `border-left` in the RECIPIENT's identity colour
(styles.css `.notice { border-left: 2px solid var(--notice-rail) }`, --notice-rail <- ev.color.bg <- the `to` name's
colour), a duplicate identity stroke beside the session's own gutter rail (.turn::before). This lab renders an outgoing
boxed mail row between an expanded tool group (the "Ran N commands" detour, whose connectors share the box's left
column) and a plain paragraph, with the viewed session AND the recipient set to the SAME vivid magenta so any
identity stroke on the box shows, and asserts the outgoing box's border-left is the NEUTRAL box border, not the
recipient identity colour (so the box wears no duplicate identity stroke beside the session's gutter rail). Screenshots
in both themes go to drops.

Synthetic only: placeholder uuids, the notes-api world, invented body text. Hermetic kernel, never the live one.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
from tests.dist_copy import copy_dist                 # noqa: E402
import test_ship_reship_served as _lab                # noqa: E402
from test_postal_cards_served import send_pair        # noqa: E402  the exact outgoing send_message pair shape

WEB = "aaaaaaaa-1111-2222-3333-444444444444"
API = "bbbbbbbb-1111-2222-3333-444444444444"
MAGENTA = "#d6249f"     # BOTH the viewed session and the recipient: the box border (recipient) and the gutter rail (session) go the same vivid hue
DROPS = os.path.expanduser("~/.local/state/romp/drops")   # the shared surface the manager and a verifier read pictures from

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
const browser = await chromium.launch({});
const out = { themes: {}, err: null };
try {
  for (const theme of ["dark", "light"]) {
    const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(cfg.chat);
    await page.waitForSelector("#tabs .tab", { timeout: 60000 });
    if (theme === "light") { await page.evaluate(() => document.body.classList.add("theme-light")); await page.waitForTimeout(200); }
    await page.waitForSelector(".turn-postal-service.postal-service-out .notice", { timeout: 60000 });
    // expand the tool group above (the "Ran N commands" fold) so its detour connectors, if any, are drawn
    await page.evaluate(() => { const tg = document.querySelector(".turn-toolgroup .notice-head, .turn-toolgroup .tg-head, .turn-toolgroup"); if (tg) tg.click && tg.click(); });
    await page.waitForTimeout(400);
    const box = await page.$(".turn-postal-service.postal-service-out .notice");
    await box.scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    const m = await page.evaluate(() => {
      const turn = document.querySelector(".turn-postal-service.postal-service-out");
      const n = turn.querySelector(".notice");
      const cs = getComputedStyle(n);
      const bb = document.createElement("div"); bb.style.background = "var(--box-border)"; document.body.appendChild(bb);
      const boxBorder = getComputedStyle(bb).backgroundColor; bb.remove();
      const rail = getComputedStyle(turn, "::before");
      const r = n.getBoundingClientRect();
      return {
        borderLeftColor: cs.borderLeftColor, borderLeftWidth: cs.borderLeftWidth, boxBorder,
        paddingLeft: cs.paddingLeft, boxLeft: r.left, boxTop: r.top, boxHeight: r.height, boxWidth: r.width,
        railLeft: rail.left, railWidth: rail.width, railBg: rail.backgroundColor,
        dpr: window.devicePixelRatio,
      };
    });
    // a full-page screenshot for the eye + the drops, plus a tight clip of the box for the pixel scan
    const shotAll = cfg.lab + "/mailbox-" + theme + ".png";
    await page.screenshot({ path: shotAll });
    const clip = { x: Math.max(0, m.boxLeft - 4), y: m.boxTop, width: Math.min(60, m.boxWidth), height: m.boxHeight };
    const clipPath = cfg.lab + "/mailbox-" + theme + "-clip.png";
    await page.screenshot({ path: clipPath, clip });
    out.themes[theme] = { m, shot: shotAll, clip: clipPath, clipOx: clip.x };
    await ctx.close();
  }
} catch (e) { out.err = String(e && e.stack || e).slice(0, 800); }
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
"""


def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); n = s.getsockname()[1]; s.close(); return n


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def _tool_pair(t, uuid, parent, tu, cmd):
    return [
        {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": WEB,
         "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "tool_use",
                     "content": [{"type": "tool_use", "id": tu, "name": "Bash", "input": {"command": cmd}}]}},
        {"type": "user", "timestamp": iso(t + 1), "uuid": uuid + "r", "parentUuid": uuid, "sessionId": WEB,
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu, "content": "ok"}]}},
    ]


def _transcript(cwd):
    """A tool group of several Bash calls (the "Ran N commands" fold), then an outgoing boxed mail, then a paragraph."""
    recs, parent, t = [], None, int(time.time()) - 3600
    for i in range(8):
        r = _tool_pair(t, "cmd%02d" % i, parent, "tu_cmd%02d" % i, "python -c 'print(%d)'" % i)
        recs += r; parent = r[-1]["uuid"]; t += 2
    body = ("the README draft is ready for a look; could you check the parser section and the error table "
            "before the release, and confirm the notes-api examples still run end to end?")   # >90 chars -> a fold -> boxed
    mail = send_pair(t, "mail0001", parent, "api", "coordinate", body, "Delivered to 'api'.")
    recs += mail; parent = mail[-1]["uuid"]; t += 2
    recs.append({"type": "assistant", "timestamp": iso(t), "uuid": "para0001", "parentUuid": parent, "sessionId": WEB,
                 "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                             "content": [{"type": "text", "text": "Done: the ranking pass reads its weights from the config now."}]}})
    return "".join(json.dumps(r) + "\n" for r in recs)


class MailBoxStrokes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser here")
        cls.lab = tempfile.mkdtemp(prefix="mailbox-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states", "timeline"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        # BOTH web (viewed, the gutter rail) and api (recipient, the box border) the SAME vivid magenta
        Path(state, "names", WEB).write_text("web\t%s\t%s\t#ffffff\n" % (cwd, MAGENTA))
        Path(state, "names", API).write_text("api\t%s\t%s\t#ffffff\n" % (cwd, MAGENTA))
        Path(state, "sdk", WEB + ".json").write_text(json.dumps(
            {"sid": WEB, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": WEB, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(proj, WEB + ".jsonl").write_text(_transcript(cwd))
        cls.port, cls.token = _free_port(), "testtok-mailbox"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        up = False
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1); up = True; break
            except Exception:
                time.sleep(0.5)
        if not up:
            cls.tearDownClass(); raise unittest.SkipTest("kernel never served /healthz")
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?skeleton=1&wid=mb&token=%s" % (cls.port, cls.token), "lab": cls.lab}, f)
        drv = os.path.join(cls.lab, "driver.mjs")
        Path(drv).write_text(DRIVER)
        p = subprocess.run(["node", drv], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        cls.result = json.loads(line[len("RESULT:"):]) if line else None
        cls.driver_out = (p.stdout + p.stderr)[-2500:]
        # copy the screenshots to drops for the eye (both themes, full + the box clip)
        try:
            os.makedirs(DROPS, exist_ok=True)
            import shutil
            for theme, d in (cls.result or {}).get("themes", {}).items():
                for k in ("shot", "clip"):
                    if d.get(k) and os.path.exists(d[k]):
                        shutil.copy(d[k], os.path.join(DROPS, "mailbox-after-%s-%s.png" % (theme, k)))
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls):
        try:
            cls.kernel.kill(); cls.kernel.wait()
        except Exception:
            pass
        import shutil
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    @staticmethod
    def _rgb(css):
        n = [int(x) for x in re.findall(r"\d+", css)[:3]]
        return n if len(n) == 3 else None

    def _magentaish(self, rgb):
        r, g, b = rgb
        return r > 120 and b > 70 and g < r * 0.6   # the vivid magenta, not the near-grey box/page ground

    def test_outgoing_box_border_is_neutral_not_the_recipient_identity(self):
        self.assertIsNone((self.result or {}).get("err"), "driver: %r\n%s" % ((self.result or {}).get("err"), self.driver_out))
        self.assertTrue(self.result and self.result.get("themes"), "the driver produced theme results: %s" % self.driver_out)
        for theme, d in self.result["themes"].items():
            m = d["m"]
            blc = self._rgb(m["borderLeftColor"])
            self.assertIsNotNone(blc, "[%s] a border-left colour: %r" % (theme, m["borderLeftColor"]))
            # RED at the base: the outgoing box's border-left was the RECIPIENT's identity magenta; GREEN after: the
            # neutral box border, so the box wears no duplicate identity stroke beside the session's gutter rail.
            self.assertFalse(self._magentaish(blc),
                             "[%s] the outgoing mail box's border-left is the recipient identity colour %r, a duplicate identity stroke; it must be the neutral box border %r"
                             % (theme, m["borderLeftColor"], m["boxBorder"]))


if __name__ == "__main__":
    unittest.main()
