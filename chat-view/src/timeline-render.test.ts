// Headless draw() smoke test (2026-06-12 regression): the timeline view's draw() runs only in a
// browser, so the unit tests for its pure helpers never executed the render path — and a `const hit`
// name collision (a membership helper shadowing the bar loop's local `const hit` rect) TDZ-crashed
// draw() on the first in-window bar, blanking the whole timeline while every test stayed green. This
// test stands up a minimal DOM shim, feeds the view a synthetic payload with IN-WINDOW turns (the
// exact path that crashed), and asserts draw() completes and emits lanes. It is the guard that any
// future draw()-level crash trips.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as path from "node:path";
import { createRequire } from "node:module";

// ---- minimal DOM shim (only what the view touches: SVG/HTML nodes, canvas measureText, localStorage) ----
function makeNode(tag: string): any {
  const n: any = {
    tag, _attrs: {}, children: [] as any[], style: {}, dataset: {}, textContent: "", parentNode: null,
    classList: { _s: new Set<string>(), add(...a: string[]) { a.forEach((c) => this._s.add(c)); },
      remove(...a: string[]) { a.forEach((c) => this._s.delete(c)); },
      toggle(c: string, f?: boolean) { f ? this._s.add(c) : this._s.delete(c); }, contains(c: string) { return this._s.has(c); } },
    setAttribute(k: string, v: any) { this._attrs[k] = v; }, getAttribute(k: string) { return this._attrs[k]; },
    setAttributeNS(_n: any, k: string, v: any) { this._attrs[k] = v; }, removeAttribute(k: string) { delete this._attrs[k]; },
    appendChild(c: any) { c.parentNode = n; this.children.push(c); return c; },
    insertBefore(c: any, ref: any) { c.parentNode = n; const i = this.children.indexOf(ref); i < 0 ? this.children.push(c) : this.children.splice(i, 0, c); return c; },
    removeChild(c: any) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    get firstChild() { return this.children[0] || null; },
    addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { width: 1400, height: 420, left: 0, top: 0, right: 1400, bottom: 420 }; },
    closest() { return null; }, focus() {},
    createEl(t: string, o: any) { const e = makeNode(t); if (o && o.cls) e.classList.add(o.cls); if (o && o.text) e.textContent = o.text; this.appendChild(e); return e; },
    createDiv(o: any) { return this.createEl("div", o); }, createSpan(o: any) { return this.createEl("span", o); },
  };
  return n;
}
const g: any = global;
g.document = {
  createElement(t: string) { return t === "canvas" ? { getContext() { return { font: "", measureText(s: string) { return { width: (s ? s.length : 0) * 6 }; } }; } } : makeNode(t); },
  createElementNS(_n: any, t: string) { return makeNode(t); },
  body: makeNode("body"), documentElement: makeNode("html"), head: makeNode("head"),
  addEventListener() {}, removeEventListener() {},
};
g.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
g.getComputedStyle = () => ({ backgroundColor: "rgb(30,30,30)" });
g.requestAnimationFrame = () => 0;
g.addEventListener = () => {}; g.removeEventListener = () => {};
g.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
g.window = g;   // the view reads window.* (event listeners / globals) in its constructor
g.innerWidth = 1400; g.innerHeight = 800;   // moveTip() clamps the tooltip to the viewport

const viewPath = path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js");
const { TimelinePanel, fmtSpan } = createRequire(__filename)(viewPath);

const DAY = 86400, WEEK = 7 * DAY, MONTH = 30 * DAY;
test("fmtSpan: concise day/week/month label for long collapsed gaps", () => {
  assert.equal(fmtSpan(DAY), "1 day");
  assert.equal(fmtSpan(2 * DAY), "2 days");
  assert.equal(fmtSpan(2.4 * DAY), "2 days");           // rounds to nearest day
  assert.equal(fmtSpan(6 * DAY), "6 days");
  assert.equal(fmtSpan(WEEK), "1 week");
  assert.equal(fmtSpan(3 * WEEK), "3 weeks");
  assert.equal(fmtSpan(MONTH), "1 month");
  assert.equal(fmtSpan(2 * MONTH), "2 months");
});
test("fmtSpan: never reads '7 days' or '5 weeks' — each unit clamps below the next threshold", () => {
  assert.equal(fmtSpan(WEEK - 1), "6 days");            // just under a week stays "6 days", not "7 days"
  assert.equal(fmtSpan(MONTH - 1), "4 weeks");          // just under a month stays "4 weeks", not "5 weeks"
});

// A synthetic payload with TWO live lanes, each with an IN-WINDOW turn carrying the atom ids — the
// precise shape that exercises barLit/dotLit (where the TDZ crash lived).
function synthData() {
  const now = 1_781_000_000;
  const turn = (id: string, dt0: number, dt1: number) => ({
    id, promptId: id + "#p", workId: id + "#w",
    start: now - dt0, end: now - dt1, prompt: "do the thing", src: "typed", mids: [],
    pending: false, summary: "did the thing", reply: "did it", tid: "fork-" + id, uuid: "u-" + id,
    workUuid: "w-" + id, replyUuid: "r-" + id,
  });
  const sess = (id: string, name: string) => ({
    id, name, color: "#7aa2f7", state: "working", live: true, model: "Opus 4.8", effort: "xhigh",
    context: 40, since: now - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false,
  });
  return {
    now,
    sessions: [sess("S1", "alpha"), sess("S2", "beta")],
    turns: { S1: [turn("S1:1:aa", 300, 60), turn("S1:2:bb", 50, 5)], S2: [turn("S2:1:cc", 200, 30)] },
    messages: [], activeChat: null, focus: null, hover: null, usage: null,
  };
}

test("draw() renders multiple lanes without throwing (no const-hit TDZ crash)", () => {
  const host = makeNode("div");
  const panel = new TimelinePanel(host);
  panel.data = synthData();
  assert.doesNotThrow(() => panel.draw(), "draw() must not throw on in-window bars");
  assert.ok(panel.svg.children.length > 10, "draw() should emit a populated SVG (lanes/bars/dots)");
  assert.equal(panel._vis.length, 2, "both live lanes must survive the render");
});

// Dead lanes strike their name (the user 2026-06-13: a dead agent's name should be struck through
// wherever it appears — timeline + feed). Keys on the data-model `live` field, NOT a render heuristic.
function findText(node: any, txt: string): any {
  if (node.tag === "text" && node.textContent === txt) return node;
  for (const c of node.children || []) { const r = findText(c, txt); if (r) return r; }
  return null;
}
test("a dead lane's name is struck through; a live lane's is not", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const data: any = synthData();
  // turn lane "beta" into an ended (dead) session — its in-window turn keeps it on screen
  Object.assign(data.sessions[1], { live: false, faded: true, state: "idle" });
  panel.data = data;
  assert.doesNotThrow(() => panel.draw());
  const live = findText(panel.svg, "alpha");
  const dead = findText(panel.svg, "beta");
  assert.ok(live && dead, "both lane names must render");
  assert.equal(dead.getAttribute("text-decoration"), "line-through", "the dead lane's name is struck through");
  assert.ok(!live.getAttribute("text-decoration"), "the live lane's name is NOT struck");
});

test("a compacting lane's badge shows the live compaction % (the user 2026-06-15)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const data: any = synthData();
  Object.assign(data.sessions[0], { state: "compacting", compactPct: 74 });
  panel.data = data;
  assert.doesNotThrow(() => panel.draw());
  assert.ok(findText(panel.svg, "COMPACTING 74%"), "the COMPACTING badge includes the %");
});

test("draw() also survives with an active hover set (atom-id highlight path)", () => {
  const host = makeNode("div");
  const panel = new TimelinePanel(host);
  const data: any = synthData();
  panel.data = data;
  // a work-atom hover + a prompt-atom hover → exercises barLit/dotLit membership inside the loops
  panel._hover = { ids: ["S1:1:aa#w", "S2:1:cc#p"] };
  assert.doesNotThrow(() => panel.draw(), "draw() must not throw while a hover highlight is active");
  assert.equal(panel._vis.length, 2);
});

// Direct hover push (setHover) + nonce gate — the fast path that skips the file→watch→rebuild.
test("setHover applies by atom ids and gates on nonce (stale push ignored, clear works)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.data = synthData();
  panel.setHover({ ids: ["S1:1:aa#w"], nonce: 5 });
  assert.deepEqual(panel._hover && panel._hover.ids, ["S1:1:aa#w"]);
  assert.equal(panel._hoverNonce, 5);
  panel.setHover({ ids: ["S2:1:cc#p"], nonce: 4 });          // older → ignored
  assert.deepEqual(panel._hover.ids, ["S1:1:aa#w"]);
  panel.setHover({ ids: ["S2:1:cc#p"], nonce: 6 });          // newer → applied
  assert.deepEqual(panel._hover.ids, ["S2:1:cc#p"]);
  panel.setHover({ ids: null, nonce: 7 });                   // clear
  assert.equal(panel._hover, null);
  assert.equal(panel._hoverNonce, 7);
});

test("a file-poll hover cannot revert a fresher direct push (nonce gate in update)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const data: any = synthData();
  panel.update(data);                                        // no hover yet
  panel.setHover({ ids: ["S1:1:aa#w"], nonce: 9 });          // fresh push
  panel.update({ ...data, hover: { ids: ["S2:1:cc#p"], nonce: 8 } });   // OLDER poll → ignored
  assert.deepEqual(panel._hover.ids, ["S1:1:aa#w"]);
  panel.update({ ...data, hover: { ids: ["S2:1:cc#p"], nonce: 10 } });  // NEWER poll → wins
  assert.deepEqual(panel._hover.ids, ["S2:1:cc#p"]);
});

// Freeze-on-hover: a tooltip pauses live-follow only when we were pinned (following now).
const fakeEv = () => ({ clientX: 100, clientY: 100, currentTarget: makeNode("rect") });

test("freeze-on-hover: showTip pauses live-follow when pinned; hideTip resumes (deferred)", async () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  assert.equal(panel._pinned, true, "starts pinned (following now)");
  panel.showTip("<div>tip</div>", fakeEv());
  assert.equal(panel._frozeFromPin, true);
  assert.equal(panel._pinned, false, "live-follow paused while hovering");
  assert.equal(panel._holdReal, panel.data.now, "held at the now-edge captured at hover-start");
  panel.hideTip();
  assert.equal(panel._frozeFromPin, true, "resume is DEFERRED — still frozen right after hideTip");
  await new Promise((r) => setTimeout(r, 60));   // let the grace-window timer fire
  assert.equal(panel._frozeFromPin, false);
  assert.equal(panel._pinned, true, "live-follow resumed after the grace window");
});

test("freeze-on-hover: a quick glyph→glyph handoff keeps the freeze (no mid-handoff jump)", async () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  panel.showTip("<div>bar</div>", fakeEv());
  assert.equal(panel._frozeFromPin, true);
  panel.hideTip();                              // leaving the bar — resume is SCHEDULED
  panel.showTip("<div>dot</div>", fakeEv());    // …but the dot grabs it before the grace elapses
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(panel._frozeFromPin, true, "still frozen — the handoff cancelled the resume");
  assert.equal(panel._pinned, false, "timeline did not resume/jump mid-handoff");
});

test("freeze-on-hover does NOT fire (or snap to now) when the user has panned into history", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  panel._pinned = false;                                     // user panned back
  panel.showTip("<div>tip</div>", fakeEv());
  assert.equal(panel._frozeFromPin, false, "no freeze when already unpinned");
  panel.hideTip();
  assert.equal(panel._pinned, false, "un-hover must NOT yank a history-browsing user to now");
});

// The restart ↻ button MOVED to the feed's top-right next to the ⛭ gear (the user 2026-06-17) — off the
// timeline's bottom-left. So the timeline controls no longer embed it (the feed gear holds it now).
test("the timeline controls no longer embed a kernel-restart button (it moved to the feed gear)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const kids = panel.controls.children;
  const btn = kids.find((c: any) => c.tag === "button" && c.getAttribute("title") === "Restart the romp kernel");
  assert.equal(btn, undefined, "the restart button moved to the feed's top-right, beside the ⛭ gear");
});

// The settings gear was MERGED into the feed's top-right ⛭ (the user 2026-06-16): one gear now holds the
// compact toggle + version info. So the timeline controls NO LONGER embed a settings gear — only the
// restart button + usage bars remain at the bottom-left.
test("the timeline controls no longer embed a settings gear (merged into the feed's ⛭)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const kids = panel.controls.children;
  const gear = kids.find((c: any) => c.tag === "button" && c.getAttribute("title") === "Settings");
  assert.equal(gear, undefined, "the timeline's settings gear moved to the feed's top-right ⛭");
});

// Freeze-on-hover must actually STOP the edge (the user 2026-06-13: "timeline doesn't stop when I hover").
test("freeze-on-hover also fires under 🔒 lock-to-now, and never marks offDirty", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  panel._lockNow = true; panel._pinned = true;
  panel.showTip("<div>tip</div>", fakeEv());
  assert.equal(panel._frozeFromPin, true, "lock must NOT block the hover-freeze");
  assert.equal(panel._offDirty, false, "freeze must not mark offDirty, or the next poll jumps the edge to the new now");
});

test("freeze-on-hover: _liveNow holds at the hover instant so open bars + pending stop advancing", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.data = { now: 5000 } as any;
  panel._frozeFromPin = true; panel._holdReal = 4000;
  assert.equal(panel._liveNow(), 4000, "frozen → _holdReal (the hover instant), not the advancing data.now");
});

// Round 2: holding the EDGE wasn't enough — update() re-laid-out the SVG every poll (new events +
// recompressed gaps shift x), which read as an intermittent jump. While a tooltip is up, update() must
// buffer the data but skip the redraw; hideTip paints the catch-up. (the user 2026-06-13)
test("update() keeps a still snapshot while a tooltip is up; hideTip paints the catch-up (deferred)", async () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());                       // initial real layout
  let draws = 0; panel.draw = () => { draws++; };  // count further redraws
  panel.tip.classList.add("show");                 // a tooltip is showing
  const d2 = synthData();
  panel.update(d2);
  assert.equal(draws, 0, "a poll while a tooltip is up must NOT redraw (the re-layout was the jump)");
  assert.equal(panel.data, d2, "the fresh data is still buffered for the catch-up");
  assert.equal(panel._dirtyWhileTip, true);
  panel.hideTip();
  await new Promise((r) => setTimeout(r, 60));      // the catch-up repaint is deferred with the unfreeze
  assert.ok(draws >= 1, "hideTip paints the buffered data (one catch-up)");
  assert.equal(panel._dirtyWhileTip, false);
});

// Mouse model (the user 2026-06-13): wheel=zoom (honors 🔒lock), click-drag=pan (breaks 🔒lock),
// vertical drag=reorder. These drive the real handlers through the DOM shim and assert the state moves.
function wheelEv(over: any) { return { deltaX: 0, deltaY: 0, ctrlKey: false, clientX: 700, clientY: 200, preventDefault() {}, ...over }; }
function mouseEv(over: any) { return { button: 0, clientX: 500, clientY: 200, preventDefault() {}, ...over }; }

test("onWheel: vertical scroll zooms; horizontal scroll pans", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  const w0 = panel.winSec();
  panel.onWheel(wheelEv({ deltaY: 20 }));                 // vertical → zoom (window widens, deltaY>0)
  assert.notEqual(panel.winSec(), w0, "vertical wheel changes the zoom window");
  const off0 = panel.offSec();
  panel.onWheel(wheelEv({ deltaX: -40, deltaY: 0 }));     // horizontal → pan into history (offset grows)
  assert.ok(panel.offSec() > off0, "horizontal wheel pans (offset moves off now)");
});

test("onWheel: zoom HONORS 🔒 lock (right edge stays at now)", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  panel._setLock(true);
  panel.onWheel(wheelEv({ deltaY: 20 }));
  assert.equal(panel.offSec(), 0, "locked zoom keeps offset 0 — edge pinned at now");
});

test("click-drag pan BREAKS 🔒 lock and unpins", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  panel._setLock(true); panel._pinned = true;
  const sid = panel._vis[0].id;
  panel._beginDrag(sid, mouseEv({ clientX: 500, clientY: 200 }));
  panel._dragMove(mouseEv({ clientX: 440, clientY: 202 }));   // horizontal-dominant → pan
  assert.equal(panel._lockNow, false, "a pan-drag turns OFF the lock");
  assert.equal(panel._pinned, false, "a pan-drag unpins (edge leaves now)");
  panel._dragUp(mouseEv({ clientX: 440, clientY: 202 }));
});

test("vertical click-drag reorders the lane (not pan), leaving the lock alone", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.update(synthData());
  const lockBefore = panel._lockNow;
  const sid = panel._vis[0].id;
  panel._beginDrag(sid, mouseEv({ clientX: 500, clientY: 200 }));
  panel._dragMove(mouseEv({ clientX: 502, clientY: 270 }));   // vertical-dominant → reorder
  assert.equal(panel._drag.mode, "row", "vertical drag → reorder mode");
  assert.equal(panel._lockNow, lockBefore, "reorder must not touch the lock");
  panel._dragUp(mouseEv({ clientX: 502, clientY: 270 }));
});

// ── judging band (2026-06-17): a compact second timeline under the lanes, one row per summarizer
// judge, each mark coloured by the SESSION it acted on. Fed by data.judging = [{judge,sid,t,kind,text}].
function findAll(node: any, pred: (n: any) => boolean, acc: any[] = []): any[] {
  if (pred(node)) acc.push(node);
  for (const c of node.children || []) findAll(c, pred, acc);
  return acc;
}
// The band is gated on the GLOBAL Debug setting (romp:settings.debug, toggled in the feed gear). Drive
// it through the same localStorage key the view reads.
function setDebug(on: boolean) {
  g.localStorage.getItem = (k: string) => (k === "romp:settings" && on ? JSON.stringify({ debug: true }) : null);
}
test("judging band: with Debug mode on, data.judging renders a compact, labelled row per judge", () => {
  setDebug(true);
  const panel = new TimelinePanel(makeNode("div"));
  const base: any = synthData();
  const now = base.now;
  panel.data = { ...base, judging: [
    { judge: "captioner", sid: "S1", t: now - 200, kind: "segment", text: "did a thing" },
    { judge: "captioner", sid: "S1", t: now - 150, kind: "turn", text: "wrapped the turn" },  // merges with the above (same session, <gap)
    { judge: "planner", sid: "S2", t: now - 120, kind: "mint", text: "new goal" },
    { judge: "courier", sid: "S2", t: now - 80, kind: "plant", text: "handoff in" },
    { judge: "closer", sid: "S1", t: now - 30, kind: "close", text: "shipped it" },
  ] };
  assert.doesNotThrow(() => panel.draw(), "draw() must not throw with a judging band");
  for (const j of ["captioner", "archiver", "planner", "grouper", "closer", "distiller", "courier"])
    assert.ok(findText(panel.svg, j), `judge row '${j}' must be labelled in the gutter`);
  assert.ok(findText(panel.svg, "judges"), "the band carries a gutter heading");
  const cap = findAll(panel.svg, (n) => n.getAttribute && n.getAttribute("data-judge") === "captioner");
  assert.equal(cap.length, 1, "two adjacent same-session captions merge into ONE attention mark");
  assert.equal(cap[0].getAttribute("fill"), "#7aa2f7", "a mark is FILLED with the session it judged");
  // no per-bar outline (the user 2026-06-18) — the judge's colour lives on the row rail, not a redundant stroke
  assert.equal(cap[0].getAttribute("stroke"), undefined, "a mark has NO stroke (solid session-colour fill only)");
  assert.equal(findAll(panel.svg, (n) => n.getAttribute && n.getAttribute("data-judge") === "courier").length, 1);
});
test("judging band is gated on Debug mode: OFF by default hides it; Debug on draws it and grows the SVG", () => {
  setDebug(false);
  const panel = new TimelinePanel(makeNode("div"));
  const base: any = synthData();
  panel.data = { ...base, judging: [{ judge: "planner", sid: "S1", t: base.now - 50, kind: "mint", text: "g" }] };
  panel.draw();                                               // Debug off (default)
  assert.ok(!findText(panel.svg, "judges"), "no band heading while Debug is off");
  assert.equal(findAll(panel.svg, (n) => n.getAttribute && n.getAttribute("data-judge")).length, 0, "no judge marks drawn while off");
  const hOff = Number(panel.svg.getAttribute("height"));
  setDebug(true);
  panel.draw();                                               // a storage event from the gear would trigger this in the browser
  assert.ok(findText(panel.svg, "judges"), "Debug on reveals the band");
  assert.ok(Number(panel.svg.getAttribute("height")) > hOff, "the band adds height below the lanes");
  g.localStorage.getItem = () => null;                        // reset the shared mock
});

// (The per-window token grid was removed from the timeline controls at the user's request 2026-06-18;
// only the /usage rate-limit bars remain. Its render tests went with it.)

// Hover bodies: the prompt DOT shows the REQUEST (prompt); the activity BAR shows the WORK (the
// segment's own caption). They must differ — the bar used to show its own work caption mislabeled
// "request:", reading as a duplicate of the dot (the user 2026-06-18).
test("work-bar hover shows the work caption (summary), not mislabeled 'request:'", () => {
  const panel: any = new TimelinePanel(makeNode("div"));
  const done = panel.barBody({ summary: "Fixed the off-by-one", prompt: "fix the bug", reply: "" }, false);
  assert.match(done, /Fixed the off-by-one/, "the bar shows its own work caption");
  assert.doesNotMatch(done, /request:/, "a work period WITH a caption is not labeled 'request:'");
  const noCap = panel.barBody({ summary: "", prompt: "fix the bug", reply: "" }, false);
  assert.match(noCap, /request: /);                           // no caption yet, finished → the request, muted
  assert.match(noCap, /fix the bug/);
  const live = panel.barBody({ summary: "", prompt: "fix the bug", reply: "" }, true);
  assert.match(live, /working on: /, "ongoing with no caption → 'working on: <prompt>'");
});

test("prompt-dot hover shows the MESSAGE caption once ready, falling back to the raw prompt (the user 2026-06-19)", () => {
  const panel: any = new TimelinePanel(makeNode("div"));
  // message caption available → show it (a gist of the ask), NOT the verbose prompt and NOT the work summary
  assert.equal(panel.req({ prompt: "please fix the pagination bug across the whole table view", msgCaption: "the pagination bug", summary: "Fixed pagination" }),
               "the pagination bug", "the dot shows the MESSAGE caption, distinct from the bar's work summary");
  // intermediate (no message caption yet) → the raw prompt is the fallback; the work summary is the BAR's, not the dot's
  assert.equal(panel.req({ prompt: "fix the pagination bug", summary: "Fixed pagination" }), "fix the pagination bug",
               "until the message caption lands, fall back to the raw prompt — never the work summary");
  assert.equal(panel.req({}), "", "neither → empty");
});
