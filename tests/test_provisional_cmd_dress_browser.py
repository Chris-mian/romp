#!/usr/bin/env python3
"""T403 (the user 2026-09-13, a chat-page screenshot): a provisional /compact (the kernel's echo of a command send, captioned
"sending…") wore a thick blue dashed ring, while the queued /model row under it wore the standard provisional dress (a thin
muted dashed border, dim caption, the pill inside). The ring's source is the sheet's cascade: the landed command row sheds its
bubble with `border: none`, which leaves the border WIDTH at the initial `medium` (3px) with no style, and the echo dress set the
style alone to dashed. The fix names the echo of a command in the queued bubble's own rule (one provisional vocabulary, T302).

The served lab drives the real /chat page over the queued lab's boot (a hermetic kernel, a session mid-turn) and injects one
update frame the way the provisional-rows lab does (this boot's kernel has no Agent SDK, which is what mints an echo atom): a
LANDED /compact record, the ECHO of a /compact send (an "echo:" uuid, as the backend mints them) and the kernel's queued copy of a
/model. It reads the computed styles of the three rows in both themes and shoots the tail (CMD_DRESS_SHOTS=<prefix> writes
<prefix>-dark.png and <prefix>-light.png; CMD_DRESS_DUMP=<path> writes the whole measurement). Red before the fix on the echo's
border (3px against the queued bubble's 1px) and on its chip and ✦ (the landed row's dress on a provisional row). The landed row
is a ratchet: unchanged. Skips LOUDLY without the extension deps or a browser (a failure under ROMP_SERVED_TESTS_REQUIRE=1, the
file name being a served module's). SYNTHETIC fixtures only.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_queued_rescind_browser import QueuedLab, SID   # noqa: E402  the shared boot: a session mid-turn that parks every send

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 760 } });
// every kernel frame from the first byte (the FULL session frame is the base for the synthetic push); while the synthetic state
// stands the kernel's own frames are held back at the shim's socket handler, so a push cannot overwrite the injected rows
await page.addInitScript(() => {
  window.__frames = []; window.__quiet = false;
  window.addEventListener("message", (e) => { const m = e.data; if (m && (m.type === "session" || m.type === "update" || m.type === "chatTail")) window.__frames.push(m); });
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, "onmessage");
  Object.defineProperty(WebSocket.prototype, "onmessage", { configurable: true, get() { return desc.get.call(this); },
    set(fn) { desc.set.call(this, (ev) => { if (window.__quiet) { try { const m = JSON.parse(ev.data); if (m && (m.type === "chatTail" || m.type === "update" || m.type === "session" || m.type === "status")) return; } catch (e) {} } fn(ev); }); } });
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForSelector(".turn.turn-user", { timeout: 20000 });
await page.waitForFunction(() => window.__frames.some((m) => m.type === "session" && Array.isArray(m.events) && m.events.length > 3), null, { timeout: 20000 });
await page.waitForTimeout(400);
const base = await page.evaluate(() => { const fr = window.__frames.filter((m) => m.type === "session" && Array.isArray(m.events)); return fr[fr.length - 1]; });
base.events = base.events.filter((e) => !(e.uuid || "").startsWith("optimistic:") && e.kind !== "queued" && e.kind !== "todo");
const now = new Date().toISOString();
const landedCmd = { kind: "user", md: "/compact", uuid: "la-cmd-1", ts: now, human: true };                       // a LANDED slash command: the ✦ row
const echoCmd = { kind: "user", md: "/compact", uuid: "echo:" + "e".repeat(32), ts: now, human: true };           // the kernel's echo of a send not yet read: provisional
const queuedModel = { kind: "queued", uuid: "queued", texts: [{ md: "/model", qid: "echo:" + "f".repeat(32), qts: Date.now(), cancelable: true, idx: 0 }] };   // the standard provisional dress
await page.evaluate(() => { window.__quiet = true; });
await page.evaluate((f) => { window.postMessage(f, "*"); }, { ...base, type: "update", events: [...base.events, landedCmd, echoCmd, queuedModel] });
await page.waitForSelector("#content .turn.echo .user-bubble.cmd-row.echo-bubble", { timeout: 10000 });
await page.waitForSelector("#content .turn-queued .queued-bubble", { timeout: 10000 });
const read = () => page.evaluate(() => {
  const cs = (el, ps) => { const c = getComputedStyle(el); const o = {}; for (const p of ps) o[p] = c[p]; return o; };
  const BORDER = ["borderTopWidth", "borderTopStyle", "borderTopColor", "borderRadius", "paddingTop", "paddingLeft", "backgroundColor", "outlineWidth", "outlineStyle", "opacity", "color"];
  const CHIP = ["backgroundColor", "color", "borderTopColor", "borderTopStyle", "borderTopWidth"];
  const echo = document.querySelector("#content .turn.echo .user-bubble.cmd-row.echo-bubble");
  const queued = Array.from(document.querySelectorAll("#content .turn-queued .queued-bubble")).find((b) => (b.textContent || "").includes("/model"));
  const landed = Array.from(document.querySelectorAll("#content .turn.turn-user:not(.echo) .user-bubble.cmd-row")).find((b) => (b.textContent || "").includes("/compact"));
  // the token the queued bubble's border names, resolved by the page itself
  const probe = document.createElement("div"); probe.style.cssText = "position:absolute;visibility:hidden;border:1px dashed color-mix(in srgb, var(--you) 55%, transparent)"; document.body.appendChild(probe);
  const token = getComputedStyle(probe).borderTopColor; probe.remove();
  const row = (b) => b ? Object.assign(cs(b, BORDER), { before: getComputedStyle(b, "::before").content, chip: b.querySelector(".slash-cmd-chip") ? cs(b.querySelector(".slash-cmd-chip"), CHIP) : null,
    rect: (() => { const r = b.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })() }) : null;
  const note = echo ? echo.parentElement.querySelector(".echo-note") : null;
  return { theme: document.body.classList.contains("theme-light") ? "light" : "dark", token, echo: row(echo), queued: row(queued), landed: row(landed),
           note: note ? note.textContent : null, noteColor: note ? getComputedStyle(note).color : null, queuedHead: (document.querySelector("#content .turn-queued .queued-head") || {}).textContent || null };
});
const shot = async (theme) => { if (!cfg.shots) return; const tail = await page.$("#content"); const box = await tail.boundingBox(); const h = Math.min(box.height, 420);
  await page.screenshot({ path: cfg.shots + "-" + theme + ".png", clip: { x: box.x, y: box.y + box.height - h, width: box.width, height: h } }); };
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
await page.waitForTimeout(200);
const dark = await read(); await shot("dark");
await page.evaluate(() => document.body.classList.add("theme-light")); await page.waitForTimeout(200);
const light = await read(); await shot("light");
await page.evaluate(() => document.body.classList.remove("theme-light"));
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify({ dark, light }) + "\n", () => process.exit(0));
"""


class ServedProvisionalCmdDress(QueuedLab):
    _r = None

    def _result(self):
        cls = type(self)
        if cls._r is None:
            cfg = os.path.join(self.lab, "cfg.json")
            with open(cfg, "w") as f:
                json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID,
                           "shots": os.environ.get("CMD_DRESS_SHOTS", "")}, f)
            driver = os.path.join(self.lab, "driver.mjs")
            with open(driver, "w") as f:
                f.write(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(self.EXT, "package.json"), CFG=cfg))
            if p.returncode == 3:
                raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
            self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(self.klog).read()[-1500:])
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
            cls._r = json.loads(line[len("RESULT:"):])
            if os.environ.get("CMD_DRESS_DUMP"):
                with open(os.environ["CMD_DRESS_DUMP"], "w") as f:
                    json.dump(cls._r, f, indent=1)
        print("RESULT:" + json.dumps(cls._r), file=sys.stderr)   # the whole measurement rides EVERY test's captured stderr
        return cls._r

    def test_the_provisional_command_wears_the_queued_bubbles_border_and_no_ring_in_both_themes(self):
        # the user's screenshot: a 3px blue dashed ring on the echo of /compact, a 1px muted dashed border on the queued /model
        r = self._result()
        for theme in ("dark", "light"):
            m = r[theme]; e, q = m["echo"], m["queued"]
            table = "\n  %s: echo=%s\n  queued=%s\n  token=%s" % (theme, json.dumps(e), json.dumps(q), m["token"])
            self.assertEqual(m["theme"], theme, table)
            self.assertIsNotNone(e, theme + ": the echo of the command rendered" + table)
            self.assertIsNotNone(q, theme + ": the queued /model rendered" + table)
            self.assertEqual((e["borderTopWidth"], e["borderTopStyle"], e["borderTopColor"]), (q["borderTopWidth"], q["borderTopStyle"], q["borderTopColor"]),
                             theme + ": the echo's border is the queued bubble's (width, style, colour)" + table)
            self.assertEqual((e["borderTopWidth"], e["borderTopStyle"]), ("1px", "dashed"), theme + ": the thin dashed provisional border" + table)
            self.assertEqual(e["borderTopColor"], m["token"], theme + ": the border colour is the queued bubble's token, 55 percent of the you blue" + table)
            self.assertTrue(e["outlineStyle"] == "none" or e["outlineWidth"] == "0px", theme + ": no outline stands on the row" + table)
            self.assertEqual((e["borderRadius"], e["paddingTop"], e["paddingLeft"], e["backgroundColor"]), (q["borderRadius"], q["paddingTop"], q["paddingLeft"], q["backgroundColor"]),
                             theme + ": the radius, padding and wash are the queued bubble's" + table)
            self.assertEqual(e["opacity"], q["opacity"], theme + ": the fade is in the colours, as the queued bubble's is" + table)
            self.assertEqual(m["note"], "sending…", theme + ": the dim caption under it" + table)

    def test_the_provisional_command_carries_the_queued_bubbles_chip_and_no_mark(self):
        # the pill inside, as the queued /compact draws it; the ✦ is the landed row's
        r = self._result()
        for theme in ("dark", "light"):
            m = r[theme]; e, q = m["echo"], m["queued"]
            table = "\n  %s: echo chip=%s before=%s\n  queued chip=%s" % (theme, json.dumps(e["chip"]), e["before"], json.dumps(q["chip"]))
            self.assertEqual(e["chip"], q["chip"], theme + ": the chip inside the echo is the queued bubble's chip" + table)
            self.assertIn(e["before"], ("none", '""'), theme + ": no ✦ on a provisional command" + table)

    def test_the_landed_command_row_is_unchanged(self):
        # the ratchet: the ✦ row, no bubble, no border, the blue chip on the page's ground
        r = self._result()
        for theme in ("dark", "light"):
            m = r[theme]; l = m["landed"]; table = "\n  %s: landed=%s" % (theme, json.dumps(l))
            self.assertIsNotNone(l, theme + ": the landed /compact rendered" + table)
            self.assertEqual((l["borderTopWidth"], l["borderTopStyle"]), ("0px", "none"), theme + ": no border on the landed row" + table)
            self.assertIn(l["backgroundColor"], ("rgba(0, 0, 0, 0)", "transparent"), theme + ": no bubble on the landed row" + table)
            self.assertEqual(l["before"], '"✦"', theme + ": the mark" + table)
            self.assertTrue(l["outlineStyle"] == "none" or l["outlineWidth"] == "0px", theme + ": no outline" + table)
            self.assertIsNotNone(l["chip"], table)
            self.assertNotEqual(l["chip"], m["queued"]["chip"], theme + ": the landed chip is the landed row's own (blue on the ground), not the queued bubble's" + table)


if __name__ == "__main__":
    unittest.main()
