#!/usr/bin/env python3
"""TWO BROWSERS OF ONE KERNEL SHOW ONE ARRANGEMENT (the user 2026-09-23, whose phone's session list did not
match the desktop strip they had dragged).

The order is still COMPUTED in the browser — it spans every attached machine, and no kernel can order sids
belonging to one it has never heard of (the 2026-07-31 ruling, commit e9870995). What moved is where the
finished list is KEPT: the kernel this browser talks to persists it, serves it on connect and pushes it when
it changes, as opaque data. This drives that end to end in a real browser, with two independent contexts —
separate localStorage, so they are two devices, not two tabs sharing a store — against one hermetic kernel.

Four phases in one run:
  0. a browser carrying a pre-move arrangement meets a kernel with none: it PUBLISHES its own, so nobody's
     existing order is lost in the move.
  1. a second browser opens and is served that arrangement on connect, with no drag of its own; then it
     drags, and the FIRST browser's strip follows — no reload, no poll, the kernel's push is the event.
  2. the pre-move local key in the first browser is exactly where it was: reverting is harmless.
  3. the first browser drags the order AWAY from the kernel's seed, and then a freshly CLEARED browser opens
     (review find on #2062, 2026-09-23). The connect push serves the strip before the viewOrder frame, and a
     page that spoke for the arrangement from boot answered it with the seed order it had adopted into an empty
     copy, putting that over the user's arrangement on every device. The arrangement must survive: on the new
     page, on the two open ones, and in the kernel's file.

The kernel's seed is pinned (session-order.json, web then api) so phase 3's arrangement is known to differ from it.

Skips LOUDLY without the extension deps or a Playwright browser. The lab kernel's environment is
kernel_env's list of names, never a copy of the runner's. SYNTHETIC sessions and text only (the notes-api
demo world: web, api).
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    from tests.dist_copy import copy_dist
except ImportError:   # an older tree without the staging-aware copy: a plain copy serves the same
    copy_dist = shutil.copytree

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's
# Hermetic state for a bare unittest or script run, which has no conftest floor.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)   # a live kernel's export outranks the XDG floor

SID_A = "11111111-2222-4333-8444-000000000901"
SID_B = "11111111-2222-4333-8444-000000000902"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, cwd, pairs):
    """`pairs` closed user/assistant turns (an OPEN turn would invite the boot reconcile to resume it)."""
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "%s-a%04x" % (sid[:23], i)
        a = "%s-b%04x" % (sid[:23], i)
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))   # noqa: E731
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": sid, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep going with the notes-api search module (part %d)" % (i + 1)}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": sid, "cwd": cwd,
                    "message": {"id": "msg_lab_%s_%04d" % (sid[-3:], i), "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": "Note %d: the tokenizer fixture set covers the hyphen cases now." % (i + 1)}],
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
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = {};
const die = async (why) => { fs.writeSync(1, "RESULT:" + JSON.stringify({ ...out, died: why }) + "\n"); await browser.close(); process.exit(0); };
const T = 20000;

// One "device": its own browser context, so its own localStorage. Two tabs of one context share a store
// and would converge through the `storage` event alone, which is what this test must NOT be measuring.
// `standalone`: the chat page on its own (/chat) rather than the dashboard around it. There the chat pane's socket is
// the only one, so nothing else on the page can hear the kernel's arrangement before the strip lands; inside the
// dashboard another pane often hears first and hides the race phase 3 is about.
const device = async (seedLocalOrder, standalone = false) => {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  if (seedLocalOrder) await ctx.addInitScript((o) => { try { localStorage.setItem("romp:vieworder", JSON.stringify(o)); } catch (e) {} }, seedLocalOrder);
  const page = await ctx.newPage();
  const sa = standalone;
  const d = {
    page,
    open: async () => {
      await page.goto(sa ? cfg.url.replace("/?token=", "/chat?token=") : cfg.url);
      await d.waitFn(([sids, sa]) => { const f = document.getElementById("f-chat"); const doc = sa ? document : f && f.contentDocument;
        if (!doc) return false; const ids = Array.from(doc.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id);
        return sids.every((s) => ids.includes(s)); }, [cfg.sids, sa], "the chat never showed both tabs");
      await d.waitFn((sa) => { const f = document.getElementById("f-chat"); const w = sa ? window : f && f.contentWindow; return !!(w && w.__rompFed); }, sa, "the pane never got its federation manager");
      // the no-reload witness: a property on the chat's own window, gone if anything reloads it
      await page.evaluate((sa) => { (sa ? window : document.getElementById("f-chat").contentWindow).__rompConvergeMark = 1; }, sa);
    },
    waitFn: (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(why + " (" + String(e).split("\n")[0] + ")"); }),
    strip: () => page.evaluate((sa) => Array.from((sa ? document : document.getElementById("f-chat").contentDocument).querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id), sa),
    keys: () => page.evaluate(() => ({ shared: JSON.parse(localStorage.getItem("romp:vieworder:shared") || "null"),
                                       local: JSON.parse(localStorage.getItem("romp:vieworder") || "null") })),
    fresh: () => page.evaluate((sa) => (sa ? window : document.getElementById("f-chat").contentWindow).__rompConvergeMark === 1, sa),
    waitStrip: (want, why) => d.waitFn(([want, sa]) => { const f = document.getElementById("f-chat"); const doc = sa ? document : f && f.contentDocument;
      if (!doc) return false; const ids = Array.from(doc.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id);
      return JSON.stringify(ids) === JSON.stringify(want); }, [want, sa], why),
    // the strip's own dragstart / dragover / drop / dragend on the tab nodes, with one DataTransfer:
    // a tab dropped on another lands AFTER it, so the first onto the second reverses the pair
    drag: (from, to) => page.evaluate(([from, to, sa]) => {
      const w = sa ? window : document.getElementById("f-chat").contentWindow, doc = w.document;
      const src = doc.querySelector('#tabs .tab[data-id="' + from + '"]'), dst = doc.querySelector('#tabs .tab[data-id="' + to + '"]');
      const dt = new w.DataTransfer(), r = dst.getBoundingClientRect();
      const fire = (type, target, x) => target.dispatchEvent(new w.DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt, clientX: x, clientY: r.top + r.height / 2 }));
      const started = fire("dragstart", src, src.getBoundingClientRect().left + 4);
      fire("dragover", dst, r.right - 2); fire("drop", dst, r.right - 2); fire("dragend", src, r.right - 2);
      return { started, strip: Array.from(doc.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id) };
    }, [from, to, sa]),
  };
  return d;
};

// ---- 0. a browser carrying a pre-move arrangement meets a kernel with none ----
// The kernel's arrival order is whatever it lists; this device's pre-move local key names the REVERSE of
// the ids, so whichever way the kernel seeds them the published arrangement is distinguishable from it.
const desktop = await device(cfg.sids.slice().reverse());
await desktop.open();
await desktop.waitStrip(cfg.sids.slice().reverse(), "the upgrading browser's own arrangement never applied");
out.desktopAfterMigration = { strip: await desktop.strip(), keys: await desktop.keys() };

// ---- 1. a second device opens, is served that arrangement, and its drag reaches the first ----
const phone = await device(null);
await phone.open();
out.phoneOnConnect = { strip: await phone.strip(), keys: await phone.keys() };
const K = await phone.strip();
out.phoneDrag = await phone.drag(K[0], K[1]);           // reverses the pair again
await phone.waitStrip(K.slice().reverse(), "the dragging device's own strip never took the drag");
await desktop.waitStrip(K.slice().reverse(), "the OTHER device never took the arrangement from the kernel");
out.converged = { desktopStrip: await desktop.strip(), phoneStrip: await phone.strip(),
                  desktopKeys: await desktop.keys(), desktopNeverReloaded: await desktop.fresh() };

// ---- 3. an arrangement that is NOT the seed survives a freshly cleared browser opening ----
const K2 = await desktop.strip();                          // the seed order again (phase 1 reversed the reversal)
out.desktopDrag2 = await desktop.drag(K2[0], K2[1]);
const ARR = K2.slice().reverse();
await desktop.waitStrip(ARR, "the desktop's second drag never took");
await phone.waitStrip(ARR, "the phone never took the desktop's second drag");
const cleared = await device(null, true);                  // a new context: nothing cached, no pre-move key; the chat page alone
await cleared.open();
await cleared.waitFn(() => localStorage.getItem("romp:vieworder:shared") !== null, null, "the cleared browser never heard the kernel's arrangement");
// whatever the cleared browser did, let it reach the other device before reading it: wait until the desktop shows
// the same order as the cleared page (both the arrangement when it survives; both the seed when it was overwritten)
const t0 = Date.now();
let same = false;
while (Date.now() - t0 < T) {
  const [a, b] = [await desktop.strip(), await cleared.strip()];
  if (JSON.stringify(a) === JSON.stringify(b)) { same = true; break; }
  await new Promise((r) => setTimeout(r, 100));
}
if (!same) await die("the desktop and the cleared browser never showed the same order");
out.afterCleared = { arrangement: ARR, clearedStrip: await cleared.strip(), clearedKeys: await cleared.keys(),
                     desktopStrip: await desktop.strip(), phoneStrip: await phone.strip(), desktopNeverReloaded: await desktop.fresh() };

fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class SharedOrderServed(unittest.TestCase):
    """One kernel, two browser contexts, one driver run in setUpClass; each method asserts one part."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="shared-order-")
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
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root of its own: no per-session host process (CLAUDE.md, 2026-09-11)
        Path(state, "session-order.json").write_text(json.dumps([SID_A, SID_B]))   # the seed, pinned: web, then api
        # the machine's user manager is not the lab's: these shadow systemctl and systemd-run on the lab kernel's PATH
        fakebin = os.path.join(cls.lab, "fakebin")
        os.makedirs(fakebin)
        for tool, body in (("systemctl", "exit 0\n"), ("systemd-run", "echo 'no user manager in this lab' >&2\nexit 1\n")):
            Path(fakebin, tool).write_text("#!/bin/sh\n" + body)
            os.chmod(os.path.join(fakebin, tool), 0o755)
        for sid, name in ((SID_A, "web"), (SID_B, "api")):
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
            Path(proj, sid + ".jsonl").write_text(_transcript(sid, cwd, 3))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        cls.state = state
        cls.port = _free_port()
        cls.token = "testtok-sharedorder"
        cls.env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.env["PATH"] = fakebin + os.pathsep + cls.env.get("PATH", os.environ.get("PATH", ""))
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")],
                                      stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=cls.env)
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
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "sids": [SID_A, SID_B]}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so[-3000:]
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served leg needs one (CI installs none)")
        if p.returncode != 0:
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        if line is None:
            cls.driver_error = "driver printed no result:\n" + p.stdout[-3000:]
            return
        r = json.loads(line[len("RESULT:"):])
        if "died" in r:
            cls.driver_error = "driver aborted early: %s\n%s" % (r["died"], json.dumps(r, indent=1)[-2500:])
            return
        cls.result = r

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            try:
                os.kill(k.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _r(self):
        if self.driver_error:
            tail = ""
            try:
                with open(self.klog) as fh:
                    tail = "\nkernel log tail:\n" + fh.read()[-2000:]
            except OSError:
                pass
            self.fail(self.driver_error + tail)
        return self.result

    def _kernel_file(self):
        p = Path(self.state, "view-order.json")
        return json.loads(p.read_text()) if p.exists() else None

    def test_1_a_browser_carrying_a_pre_move_arrangement_publishes_it_to_a_kernel_that_has_none(self):
        m = self._r()["desktopAfterMigration"]
        want = [SID_B, SID_A]
        self.assertEqual(m["strip"], want, "the upgrading browser shows the order it had: %r" % m["strip"])
        self.assertEqual(m["keys"]["shared"], want,
                         "…adopted back off the kernel's own push, so the kernel took it: %r" % m["keys"])
        # that the kernel KEPT it is what the next case proves, from a device that has no local key to show

    def test_2_a_second_device_is_served_the_arrangement_on_connect_with_no_drag_of_its_own(self):
        # …which is also the proof that the first device's publish landed in the kernel's store: this
        # context has an empty localStorage, so [B, A] can only have come off the wire
        p = self._r()["phoneOnConnect"]
        self.assertEqual(p["strip"], [SID_B, SID_A], "the arrangement, not this kernel's arrival order: %r" % p["strip"])
        self.assertIsNone(p["keys"]["local"], "this device never had a pre-move key of its own: %r" % p["keys"])
        self.assertEqual(p["keys"]["shared"], [SID_B, SID_A], "it came off the connect push")

    def test_3_a_drag_on_one_device_moves_the_other_without_a_reload(self):
        r = self._r()
        self.assertTrue(r["phoneDrag"]["started"], "the drag was not refused: %r" % r["phoneDrag"])
        want = [SID_A, SID_B]
        c = r["converged"]
        self.assertEqual(c["phoneStrip"], want, "the dragging device: %r" % c["phoneStrip"])
        self.assertEqual(c["desktopStrip"], want, "the OTHER device followed: %r" % c["desktopStrip"])
        self.assertEqual(c["desktopKeys"]["shared"], want, "…off the kernel's push, not a reload")
        self.assertTrue(c["desktopNeverReloaded"],
                        "the other device's chat frame is the same document it was: nothing reloaded, nothing polled")
        # (the kernel's file after the LAST drag, phase 3's, is what test_5 reads — last write wins)

    def test_5_a_freshly_cleared_browser_opening_does_not_overwrite_the_arrangement(self):
        r = self._r()
        self.assertTrue(r["desktopDrag2"]["started"], "the second drag was not refused: %r" % r["desktopDrag2"])
        a = r["afterCleared"]
        want = [SID_B, SID_A]
        self.assertEqual(a["arrangement"], want, "phase 3 arranged the sessions AWAY from the pinned seed (web, api)")
        self.assertIsNone(a["clearedKeys"]["local"], "the new browser carried no arrangement of its own: %r" % a["clearedKeys"])
        self.assertEqual(a["clearedStrip"], want, "the cleared browser shows the user's arrangement, not the seed: %r" % a["clearedStrip"])
        self.assertEqual(a["desktopStrip"], want, "the desktop's arrangement survived a new device connecting: %r" % a["desktopStrip"])
        self.assertEqual(a["phoneStrip"], want, "…and the phone's: %r" % a["phoneStrip"])
        self.assertTrue(a["desktopNeverReloaded"])
        self.assertEqual(self._kernel_file(), want, "the kernel still holds the user's arrangement")

    def test_4_the_pre_move_local_key_is_left_exactly_where_it_was(self):
        # the migration is lossless in both directions: reverting this change hands the viewer back the
        # order they had before it, rather than whatever some other device last dragged
        self.assertEqual(self._r()["converged"]["desktopKeys"]["local"], [SID_B, SID_A])


if __name__ == "__main__":
    unittest.main()
