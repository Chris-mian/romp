#!/usr/bin/env python3
"""Record the two front-page clips over a hermetic kernel in the notes-api demo world (synthetic only: placeholder ids,
invented text, hostname TESTHOST), so the pictures follow the product's words and colours instead of a screen recording
of somebody's real sessions (the first clips were live captures and still said Blocked after the Needs you change,
plans/needs-you.md).

    every-session-timeline: the Sessions pane with three lanes (api and tests ready, web needing you), the pointer
                            resting on api's first turn dot (its hover card) and then on web's striped stretch (the
                            Needs you hover); 2702x300, about 8 s.
    task-cards:             the chat page beside the feed: a typed request arrives, the session runs a command and
                            answers, and its card lands in Working and then Completed with its Summary open; 2742x800,
                            about 17 s.

Everything on screen is the served product over the kernel's own build of the world, with ONE patch at the page's
boundary: a dormant SDK session (no thread running, as every session in a hermetic kernel is) reports its in-flight
state as waiting on purpose (sdk_backend._live_row: a dead prompt must not read as a live block), so the timeline clip
rewrites web's lane to the live permission state as the lanes frame enters the view, and the stripe, the hover and the
chip then draw as they do for a session blocked right now.

The frames are page screenshots at device scale two (the pointer drawn in afterwards, since a screenshot carries none),
assembled into an MP4 by the ffmpeg imageio-ffmpeg bundles and a GIF by Pillow. Run from the repo root with the extension
built (node vscode-extension/esbuild.js) and its node_modules present:

    uv run --with pillow --with imageio-ffmpeg python docs/assets/guide/src/record-clips.py [--only timeline|cards] [--out DIR]

The kernel, the state root and the browser live under a temporary directory removed at the end (--keep --lab DIR keeps
the frames and the kernel log somewhere of yours)."""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BIN = ROOT / "bin"
EXT = ROOT / "vscode-extension"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from tests.dist_copy import copy_dist  # noqa: E402
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment

WEB = "aaaaaaaa-1111-2222-3333-444444444444"
API = "bbbbbbbb-1111-2222-3333-444444444444"
TESTS = "cccccccc-1111-2222-3333-444444444444"
FPS = 15
SCALE = 2
CHAT_W, GUTTER, FEED_W, CARDS_H = 500, 2, 869, 400      # the cards clip's two pages, side by side: 1371 CSS px, 2742 device px


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def user(sid, u, parent, t, content):
    return {"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "sessionId": sid, "promptSource": "typed",
            "message": {"role": "user", "content": content}}


def asst(sid, u, parent, t, content, model, stop="end_turn"):
    return {"type": "assistant", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "sessionId": sid,
            "message": {"role": "assistant", "model": model, "stop_reason": stop, "content": content}}


class World:
    """The notes-api demo world: api, tests and web, each with a morning of turns, web stopped on a permission prompt."""

    SESSIONS = (  # sid, name, colour, ink, model id, model label, context fill
        (API, "api", "#1EA1EB", "#ffffff", "claude-opus-5", "Opus 5", 9),
        (TESTS, "tests", "#54B204", "#ffffff", "claude-sonnet-5", "Sonnet 5", 3),
        (WEB, "web", "#4EA8A9", "#ffffff", "claude-sonnet-5", "Sonnet 5", 4),
    )

    def __init__(self, lab):
        self.lab = Path(lab)
        self.state = self.lab / "xdg" / "romp"
        self.claude = self.lab / "claude"
        self.cwd = self.lab / "notes-api"
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.proj = self.claude / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.cwd.resolve()))
        self.proj.mkdir(parents=True, exist_ok=True)
        for d in ("names", "sdk", "states", "goals"):
            (self.state / d).mkdir(parents=True, exist_ok=True)
        (self.state / "session-hosts").write_text("off\n")
        self.now = int(time.time())
        self.blocked_since = self.now - 25 * 60
        self.models = {}

    def transcript(self, sid):
        return self.proj / (sid + ".jsonl")

    def append(self, sid, recs):
        with self.transcript(sid).open("a") as f:
            f.write("".join(json.dumps(r) + "\n" for r in recs))

    def states(self, sid, rows):
        (self.state / "states" / (sid + ".jsonl")).write_text("".join(json.dumps(s) + "\n" for s in rows))

    def build(self, quiet_peers=False):
        """The three sessions; with `quiet_peers` (the cards clip) api and web have said nothing yet and own no card, so the
        board shows the one card the story files, as the first clip did."""
        t_start = self.now - 130 * 60                      # the lanes span the last two hours
        for sid, name, bg, fg, model, label, ctx in self.SESSIONS:
            self.models[sid] = model
            (self.state / "names" / sid).write_text("%s\t%s\t%s\t%s\n" % (name, self.cwd, bg, fg))
            (self.state / "sdk" / (sid + ".json")).write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": self.cwd.as_posix(), "mode": "auto", "effort": "high", "lastSid": sid,
                 "alive": True, "model": model, "liveModel": label, "liveCtx": ctx}))
            self.transcript(sid).write_text("")
        if quiet_peers:
            # nobody has said anything yet: the board opens empty and the story's request is the first turn (a turn the planner has not
            # placed draws a provisional card, and this recorder files no placements, so an earlier turn would sit in Working as one)
            for sid in (API, TESTS, WEB):
                self.states(sid, [{"t": self.now - 45, "state": "idle"}])   # idle since just before the clip: the card's working time reads from here
            (self.state / "session-order.json").write_text(json.dumps([API, TESTS, WEB]))
            return
        # api: three turns over the morning, then a fresh one a few minutes ago
        api_turns = [("Add PUT, DELETE and PATCH endpoints to the notes API, with tests", "Added the three handlers and their tests; the suite is green."),
                     ("Now the pagination on GET /notes", "Cursor pagination in, with a limit of 50 and a next cursor in the body."),
                     ("Rate limit the write endpoints", "A token bucket per key, 60 writes a minute; the limits are covered by tests.")]
        t, n, rows = t_start, 0, []
        for prompt, reply in api_turns:
            n += 1
            self.append(API, [user(API, "u%d" % n, "a%d" % (n - 1) if n > 1 else None, t, prompt),
                              asst(API, "a%d" % n, "u%d" % n, t + 480, [{"type": "text", "text": reply}], self.models[API])])
            rows += [{"t": t, "state": "working"}, {"t": t + 480, "state": "idle"}]
            t += 30 * 60
        self.append(API, [user(API, "u9", "a3", self.now - 240, "Document the new endpoints in the README"),
                          asst(API, "a9", "u9", self.now - 60, [{"type": "text", "text": "The README lists every endpoint with an example call."}], self.models[API])])
        rows += [{"t": self.now - 240, "state": "working"}, {"t": self.now - 60, "state": "idle"}]
        self.states(API, rows)
        # tests: one turn, a quarter of an hour ago
        self.append(TESTS, [user(TESTS, "u1", None, self.now - 22 * 60, "Run the integration suite against the fixtures"),
                            asst(TESTS, "a1", "u1", self.now - 16 * 60, [{"type": "text", "text": "All 84 pass; two are slow and marked."}], self.models[TESTS])])
        self.states(TESTS, [{"t": self.now - 22 * 60, "state": "working"}, {"t": self.now - 16 * 60, "state": "idle"}])
        # web: a turn, then a permission prompt the user has not answered: its stretch is striped (the states log's needs-input
        # states are "permission" and "picker", the kernel's _NEEDS_INPUT_STATES) and its chip says Needs you
        tb = self.blocked_since
        self.append(WEB, [user(WEB, "u1", None, t_start + 70 * 60, "Wire the fixtures directory into the integration suite"),
                          asst(WEB, "a1", "u1", tb, [{"type": "text", "text": "Which database should the suite target, the SQLite file or the Postgres service?"}], self.models[WEB])])
        self.states(WEB, [{"t": t_start + 70 * 60, "state": "working"}, {"t": tb, "state": "permission"}])
        g = WEB + ":gw"
        (self.state / "goals" / (WEB + ".json")).write_text(json.dumps(
            {"rompUuid": WEB, "seq": 2, "lastNode": g, "closedTurns": [],
             "nodes": {g: {"id": g, "text": "wire the fixtures directory into the integration suite", "parentId": None, "nodeComplete": False,
                           "blocked": True, "blockWhy": "which database does the suite target?", "cleared": False, "trail": [], "t": t_start + 70 * 60,
                           "log": [{"ev_t": tb + 1, "src": "planner", "kind": "block", "why": "asked which database the suite targets", "at": tb + 1}]}},
             "placements": {}, "status": {g: "blocked"}}))
        (self.state / "session-order.json").write_text(json.dumps([API, TESTS, WEB]))

    def _upsert(self, sid, gid, node, status, turn=None):
        """Add or replace one node in the session's goal store (the store is the authority here; no judge runs). `turn` is the
        user record's uuid the card answers: placed on the store, so the feed does not draw a provisional card beside it."""
        p = self.state / "goals" / (sid + ".json")
        store = json.loads(p.read_text()) if p.exists() else {"rompUuid": sid, "seq": 0, "lastNode": None, "closedTurns": [], "nodes": {}, "placements": {}, "status": {}}
        store["seq"] = int(store.get("seq") or 0) + 1
        store["lastNode"] = gid
        store["nodes"][gid] = node
        store["status"][gid] = status
        if turn:
            store["placements"][turn] = gid
            if turn not in store["closedTurns"]:
                store["closedTurns"].append(turn)
        p.write_text(json.dumps(store))

    def card_working(self, sid, gid, text, t, turn=None):
        """A card in Working: an open goal with no verdict yet."""
        self._upsert(sid, gid, {"id": gid, "text": text, "parentId": None, "nodeComplete": False, "blocked": False, "cleared": False, "trail": [], "t": t, "log": []},
                     "working", turn)

    def card_completed(self, sid, gid, text, t, summary, background, turn=None):
        self._upsert(sid, gid, {"id": gid, "text": text, "parentId": None, "nodeComplete": True, "blocked": False, "cleared": False, "trail": [], "t": t,
                                "summary": summary, "background": background,
                                "log": [{"ev_t": t + 8, "src": "closer", "kind": "done", "why": "the turn answered the request", "at": t + 8}]},
                     "completed", turn)


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
const browser = await chromium.launch({});
const frames = [];   // one record per frame: the file(s) and the pointer's CSS position on the page named
let n = 0;
const tick = async (page) => { await page.waitForTimeout(1000 / cfg.fps); };
const ease = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
const signal = (what) => { fs.writeFileSync(cfg.signal, what); };
const waitCue = async (page, cue) => { for (let i = 0; i < 600; i++) { if (fs.existsSync(cfg.cue) && fs.readFileSync(cfg.cue, "utf8") === cue) return; await page.waitForTimeout(50); } };

if (cfg.clip === "timeline") {
  const ctx = await browser.newContext({ viewport: { width: 1351, height: 150 }, deviceScaleFactor: 2 });   // three lanes and their axis
  const page = await ctx.newPage();
  // the boundary patch (see the module docstring): web's lane reads as blocked right now
  await page.addInitScript(({ web, since }) => {
    const hook = () => {
      const P = window.TimelinePanel; if (!P || P.__clipPatched) return false;
      const orig = P.prototype.update;
      P.prototype.update = function (data) {
        for (const s of (data && data.sessions) || []) if (s.id === web) { s.state = "permission"; s.live = true; s.since = since; s.faded = false; }
        return orig.call(this, data);
      };
      P.__clipPatched = true; return true;
    };
    if (!hook()) { const iv = setInterval(() => { if (hook()) clearInterval(iv); }, 5); }
  }, { web: cfg.web, since: cfg.since });
  const shot = async (pointer) => { const file = cfg.frames + "/f" + String(n++).padStart(4, "0") + ".png"; await page.screenshot({ path: file }); frames.push({ files: [file], ...pointer }); };
  const hold = async (pointer, count) => { for (let i = 0; i < count; i++) { await tick(page); await shot(pointer); } };
  const glide = async (from, to, count) => { for (let i = 1; i <= count; i++) { const e = ease(i / count), x = from.x + (to.x - from.x) * e, y = from.y + (to.y - from.y) * e; await page.mouse.move(x, y); await tick(page); await shot({ x, y }); } };
  await page.goto(cfg.timeline);
  await page.waitForSelector(cfg.laneSel, { timeout: 60000 });                         // the view's wrap under #host
  await page.waitForSelector(cfg.laneSel + " circle", { timeout: 60000 });             // the bars frame landed: turn dots drawn
  await page.waitForFunction(() => Array.from(document.querySelectorAll("#host svg rect")).some((r) => (r.getAttribute("fill") || "").includes("await-hatch")), null, { timeout: 60000 });
  await page.waitForTimeout(1500);
  const dot = await page.evaluate(cfg.apiDotJs);          // {x, y} of api's first turn dot, in CSS pixels
  const stripe = await page.evaluate(cfg.webStripeJs);    // {x, y} of web's striped stretch
  const start = { x: dot.x - 160, y: dot.y + 90 };
  await page.mouse.move(start.x, start.y);
  await hold(start, Math.round(cfg.fps * 0.6));
  await glide(start, dot, Math.round(cfg.fps * 0.9));
  await hold(dot, Math.round(cfg.fps * 2.6));
  await glide(dot, stripe, Math.round(cfg.fps * 0.9));
  await hold(stripe, Math.round(cfg.fps * 2.6));
} else {
  // the chat page and the feed page side by side, each its own page at its own size; the recorder composes the frames
  const ctx = await browser.newContext({ viewport: { width: cfg.chatW, height: cfg.h }, deviceScaleFactor: 2 });
  const chat = await ctx.newPage();
  const fctx = await browser.newContext({ viewport: { width: cfg.feedW, height: cfg.h }, deviceScaleFactor: 2 });
  const feed = await fctx.newPage();
  const shot = async (pointer) => { const a = cfg.frames + "/c" + String(n).padStart(4, "0") + ".png", b = cfg.frames + "/f" + String(n++).padStart(4, "0") + ".png";
    await Promise.all([chat.screenshot({ path: a }), feed.screenshot({ path: b })]); frames.push({ files: [a, b], ...pointer }); };
  const hold = async (pointer, count) => { for (let i = 0; i < count; i++) { await tick(feed); await shot(pointer); } };
  const glide = async (from, to, count) => { for (let i = 1; i <= count; i++) { const e = ease(i / count), x = from.x + (to.x - from.x) * e, y = from.y + (to.y - from.y) * e; await feed.mouse.move(x, y); await tick(feed); await shot({ x, y, page: "feed" }); } };
  await Promise.all([chat.goto(cfg.chat), feed.goto(cfg.feed)]);
  await chat.waitForSelector("#composer", { timeout: 60000 });
  await chat.waitForSelector('#tabs .tab[data-id="' + cfg.tests + '"]', { timeout: 60000 });
  await chat.evaluate((id) => document.querySelector('#tabs .tab[data-id="' + id + '"]').click(), cfg.tests);   // tests is the session on screen
  await feed.waitForLoadState("networkidle");             // an empty board draws no column yet: the first card brings them
  await chat.waitForTimeout(2500);
  const nowhere = { x: -1, y: -1 };
  await hold(nowhere, Math.round(cfg.fps * 1.2));
  signal("typed");                                        // the request arrives (the recorder appends the turn's records)
  await waitCue(chat, "running");
  await hold(nowhere, Math.round(cfg.fps * 3.0));
  await waitCue(chat, "answered");
  await hold(nowhere, Math.round(cfg.fps * 3.5));
  await waitCue(chat, "completed");
  await hold(nowhere, Math.round(cfg.fps * 2.5));
  const tab = await feed.evaluate(cfg.summaryTabJs);       // the new card's Summary tab, open by default: the pointer comes to rest on it
  if (tab) { const from = { x: Math.max(20, tab.x - 260), y: Math.min(cfg.h - 20, tab.y + 140) }; await feed.mouse.move(from.x, from.y); await glide(from, tab, Math.round(cfg.fps * 0.8)); await hold({ ...tab, page: "feed" }, Math.round(cfg.fps * 4.0)); }
  else { console.error("no Summary tab on a card: " + (await feed.evaluate(() => document.body.innerText.slice(0, 300)))); await hold(nowhere, Math.round(cfg.fps * 4.0)); }
}
fs.writeFileSync(cfg.framesJson, JSON.stringify(frames));
await browser.close();
"""


FAKE_JUDGE = r'''
import json, os, sys
# The judges' child for a clip: it answers every pass at once and files nothing, so no judge ever calls a model (there is no
# credential here, and a refused call would badge every card "Can't analyze"); the goal stores the recorder writes are the cards.
sys.stdout.write(json.dumps({"op": "ready", "pid": os.getpid(), "judgeVersion": "clips", "protocolVersion": 1}) + "\n"); sys.stdout.flush()
while True:   # loop-ok: the protocol's request loop, one line in, one line out, until quit or EOF
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    if req.get("op") == "quit":
        break
    sys.stdout.write(json.dumps({"op": "done", "seq": req.get("seq"), "wallMs": 1.0, "tierStarts": 0, "tierCpuMs": 0.0, "workerCpuMs": 0.0,
                                 "failures": None, "recovered": False, "recordCache": {"entries": 0}, "asmCheckpoint": {}}) + "\n")
    sys.stdout.flush()
'''


def run_kernel(lab, dist, port, token):
    lab = Path(lab)
    # the judges run in a child that answers and files nothing (STATE/judges-process on + ROMP_JUDGE_SERVE_CMD, the seam
    # tests/test_judges_process.py uses), and a stub claude_agent_sdk package satisfies the backend's import probe so the
    # dormant sessions do not wear the "backend isn't installed" API-error card
    (lab / "xdg" / "romp" / "judges-process").write_text("on\n")
    (lab / "fake-judge.py").write_text(FAKE_JUDGE)
    stub = lab / "stub" / "claude_agent_sdk"
    stub.mkdir(parents=True, exist_ok=True)
    (stub / "__init__.py").write_text("# a stand-in for the clip recorder: importable, never used (no session runs here)\n")
    env = _lab.kernel_env(str(lab), str(lab / "claude"), str(dist), port, token, ROMP_HOST_NAME="TESTHOST",
                          ROMP_JUDGE_SERVE_CMD="%s %s" % (sys.executable, lab / "fake-judge.py"),
                          PYTHONPATH=str(lab / "stub") + ((os.pathsep + os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else ""))
    klog = Path(lab) / "kernel.log"
    proc = subprocess.Popen([str(BIN / "romp-kernel")], stdout=klog.open("w"), stderr=subprocess.STDOUT, env=env)
    for _ in range(120):   # loop-ok: a bounded wait for /healthz
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=1)
            return proc, klog
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("the hermetic kernel never served /healthz; see " + str(klog))


def draw_pointer(im, x, y):
    """A plain arrow pointer at the device position (x, y)."""
    from PIL import ImageDraw
    if x is None or x < 0:
        return im
    s = SCALE
    pts = [(x, y), (x, y + 17 * s), (x + 4.5 * s, y + 13 * s), (x + 7.5 * s, y + 19.5 * s), (x + 10 * s, y + 18.5 * s), (x + 7 * s, y + 12 * s), (x + 12.5 * s, y + 12 * s)]
    ImageDraw.Draw(im).polygon(pts, fill=(255, 255, 255), outline=(20, 20, 20))
    return im


def compose(fr):
    """One frame as an RGB image: the single page, or the chat and the feed side by side with a hairline gutter."""
    from PIL import Image
    ims = [Image.open(f).convert("RGB") for f in fr["files"]]
    if len(ims) == 1:
        im, ox = ims[0], 0
    else:
        chat, feed = ims
        im = Image.new("RGB", (chat.width + GUTTER * SCALE + feed.width, max(chat.height, feed.height)), (20, 20, 20))
        im.paste(chat, (0, 0))
        im.paste(feed, (chat.width + GUTTER * SCALE, 0))
        ox = chat.width + GUTTER * SCALE if fr.get("page") == "feed" else 0
    x = fr.get("x")
    if x is not None and x >= 0:
        draw_pointer(im, x * SCALE + ox, fr["y"] * SCALE)
    return im


def assemble(frames, out_mp4, out_gif, gif_width):
    from PIL import Image
    import imageio_ffmpeg
    work = Path(frames[0]["files"][0]).parent / "composed"
    work.mkdir(exist_ok=True)
    gif_frames = []
    for i, fr in enumerate(frames):
        im = compose(fr)
        im.save(work / ("p%04d.png" % i))
        g = im.resize((gif_width, round(im.height * gif_width / im.width)), Image.LANCZOS)
        gif_frames.append(g.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(work / "p%04d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "24", "-movflags", "+faststart", str(out_mp4)], check=True)
    gif_frames[0].save(out_gif, save_all=True, append_images=gif_frames[1:], duration=round(1000 / FPS), loop=0, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("timeline", "cards"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "assets" / "guide"))
    ap.add_argument("--keep", action="store_true", help="keep the lab directory (frames, kernel log)")
    ap.add_argument("--lab", default="", help="where the lab directory is made (default: a temporary directory; the lab module's own "
                                              "temporary root goes at exit, so --keep wants a place of yours)")
    args = ap.parse_args()
    if not (EXT / "node_modules" / "playwright").is_dir():
        raise SystemExit("the extension's node_modules (with playwright) are needed")
    lab = Path(tempfile.mkdtemp(prefix="romp-clips-", dir=args.lab or None))
    try:
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise SystemExit("esbuild failed: " + (b.stderr or b.stdout)[-400:])
        dist = lab / "dist"
        copy_dist(str(EXT / "dist"), str(dist))
        for clip in ([args.only] if args.only else ["timeline", "cards"]):
            world = World(lab / clip)
            world.build(quiet_peers=(clip == "cards"))
            port, token = free_port(), "clips-token"
            kernel, klog = run_kernel(lab / clip, dist, port, token)
            try:
                record(clip, world, lab / clip, port, token, Path(args.out))
            finally:
                kernel.kill()
                kernel.wait()
    finally:
        if not args.keep:
            shutil.rmtree(lab, ignore_errors=True)
        else:
            print("lab kept at", lab)


def record(clip, world, lab, port, token, out):
    base = "http://127.0.0.1:%d" % port
    frames_dir = lab / "frames"
    frames_dir.mkdir()
    cfg = {"clip": clip, "fps": FPS, "frames": str(frames_dir), "framesJson": str(lab / "frames.json"), "signal": str(lab / "signal"), "cue": str(lab / "cue"),
           "timeline": base + "/timeline?token=" + token, "chat": base + "/chat?token=" + token, "feed": base + "/feed?token=" + token,
           "web": WEB, "api": API, "tests": TESTS, "since": world.blocked_since,
           "chatW": CHAT_W, "feedW": FEED_W, "h": CARDS_H,
           "laneSel": "#host .romp-tl-wrap svg",        # the shared TimelinePanel mounted on the pane's #host
           # api's lane is the topmost (session-order.json): its leftmost turn dot (the plot's dots are the 12 px circles right of the labels;
           # the lane labels carry small icon svgs with circles of their own)
           "apiDotJs": "(() => { const cs = Array.from(document.querySelectorAll('#host svg circle')).map((c) => c.getBoundingClientRect()).filter((r) => r.width >= 11 && r.x > 320); const top = Math.min(...cs.map((r) => r.y)); const row = cs.filter((r) => Math.abs(r.y - top) < 6).sort((a, b) => a.x - b.x); const r = row[0]; return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()",
           "webStripeJs": "(() => { const s = Array.from(document.querySelectorAll('#host svg rect')).find((r) => (r.getAttribute('fill') || '').includes('await-hatch')); const b = s.getBoundingClientRect(); return { x: b.x + b.width * 0.35, y: b.y + b.height / 2 }; })()",
           "summaryTabJs": "(() => { const card = document.querySelector('[data-key=\"a:%s:g1\"]'); const b = card && Array.from(card.querySelectorAll('.fask-secbtn')).find((x) => x.textContent === 'Summary'); if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()" % TESTS}
    cfg_path = lab / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    driver = lab / "driver.mjs"
    driver.write_text(DRIVER)
    proc = subprocess.Popen(["node", str(driver)], env=dict(os.environ, EXT_PKG=str(EXT / "package.json"), CFG=str(cfg_path)),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if clip == "cards":
        story(world, lab, proc)
    out_, err = proc.communicate(timeout=600)
    if proc.returncode != 0:
        raise SystemExit("the driver failed:\n" + err[-3000:])
    if err.strip():
        print(err.strip()[-800:], file=sys.stderr)
    frames = json.loads((lab / "frames.json").read_text())
    name = "every-session-timeline" if clip == "timeline" else "task-cards"
    assemble(frames, out / (name + ".mp4"), out / (name + ".gif"), 1351 if clip == "timeline" else 1371)
    print(name, "recorded:", len(frames), "frames")


def story(world, lab, proc):
    """The task-cards story, told by the recorder as the driver films: the driver signals each beat, the recorder writes the
    world's next state and cues the driver on."""
    signal, cue = lab / "signal", lab / "cue"

    def wait_signal(what):
        for _ in range(1200):   # loop-ok: a bounded wait on the driver's signal file
            if signal.exists() and signal.read_text() == what:
                return True
            if proc.poll() is not None:
                return False
            time.sleep(0.05)
        return False

    t = world.now
    gid = TESTS + ":g1"
    if not wait_signal("typed"):
        return
    world.append(TESTS, [user(TESTS, "u2", None, t, "Check if any files need to be committed"),
                         asst(TESTS, "a2", "u2", t + 3, [{"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "git status --short && git diff --stat"}}], world.models[TESTS], "tool_use")])
    with (world.state / "states" / (TESTS + ".jsonl")).open("a") as f:
        f.write(json.dumps({"t": t, "state": "working"}) + "\n")
    world.card_working(TESTS, gid, "Check for uncommitted files", t, turn="u2")
    cue.write_text("running")
    time.sleep(3.2)
    world.append(TESTS, [user(TESTS, "u3", "a2", t + 6, [{"type": "tool_result", "tool_use_id": "tu1", "content": "\n"}]),
                         asst(TESTS, "a3", "u3", t + 8, [{"type": "text", "text": "Working tree is clean: nothing to commit."}], world.models[TESTS])])
    with (world.state / "states" / (TESTS + ".jsonl")).open("a") as f:
        f.write(json.dumps({"t": t + 8, "state": "idle"}) + "\n")
    cue.write_text("answered")
    time.sleep(3.6)
    world.card_completed(TESTS, gid, "Check for uncommitted files", t,
                         summary="Git status and diff stat confirmed the working tree was clean, with nothing needing to be committed.",
                         background="You asked whether anything in the notes-api checkout still needed committing after the fixtures work.", turn="u2")
    cue.write_text("completed")


if __name__ == "__main__":
    main()
