'use strict';

// romp-timeline-view — the Timeline tab's panel: a reversed-log window slider +
// an SVG timeline (lanes per session, activity bars, prompt dots, message
// connectors, Obsidian-style status chips). A native DOM port of the standalone
// prototypes/romp-timeline.html render, fed by romp-timeline-data.buildTimelineData().
//
// TimelinePanel owns the DOM under a host element: build it once, then call
// update(data) each poll to redraw the SVG (the slider persists across redraws).

const SVGNS = 'http://www.w3.org/2000/svg';
const MIN_W = 60, MAX_W = 172800;                  // 1 min … 48 h window (NICE has 60 → 1-min ticks render)
const MAX_OFFSET = 72 * 3600;                      // pan slider: right edge from now (0) back to −72 h (linear)
// Compact metrics: rows collapse to the minimum height a bar+dots+label need.
const LANE_GAP = 26, BAR_H = 8, CORNER = 6, MSG_DROP = 10, DOT_R = 6, CLEAR = DOT_R + 4, COINCIDE = 45;
// Each directed flow (A→B) is ONE line; its thickness = MSG_W0 + (count-1)*MSG_GROW
// — linear in message count, no max cap (BAR_H=8 is the work-bar reference: a flow
// passes that around ~5-6 messages and keeps growing). Drawn at alpha .5 so
// overlapping flows stay legible.
const MSG_W0 = 2, MSG_GROW = 1.3;
const GAP_MIN = 20 * 60;   // broken-axis: collapse idle gaps (no work on ANY lane) longer than this. Each
                           // collapses to GAP_FRAC of the window — a CONTINUOUS function of zoom (not the
                           // discrete niceStep), so the break width changes smoothly while zooming (no
                           // jumps), at a ~constant pixel width. (See _buildCompressMap.)
const GAP_FRAC = 0.11;     // collapsed-gap compressed width = GAP_FRAC * winSec ≈ GAP_FRAC * plotW pixels
const DAG_HL = '#ffffff';   // request-DAG "journey" highlight: thick white border/outline → reads as "focused" (matches the feed card's white focus border)
const DAG_W = 3;            // its stroke width; outlines are offset by DAG_W/2 so the INNER edge hugs the element (no dark gap)
// idle >1h fade: blend the color toward the surface bg until its LUMINANCE hits a uniform low target,
// so every hue lands at the same perceived dimness (plain opacity leaves bright hues looking brighter).
// Shared algorithm with romp-chat-view so all surfaces match — keep FADE_TARGET in sync with it.
const FADE_TARGET = 38;   // faded luminance = bg luminance + this; lower → more fade
function fadeHex(hex, bg) {
  if (!hex || hex[0] !== '#' || hex.length < 7) return hex;
  const n = parseInt(hex.slice(1, 7), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const lum = (x, y, z) => 0.2126 * x + 0.7152 * y + 0.0722 * z;
  const Lc = lum(r, g, b), Lb = lum(bg[0], bg[1], bg[2]), Lt = Lb + FADE_TARGET;
  if (Lc <= Lt) return hex;                                   // already dim enough → leave it
  const t = Math.min(0.85, (Lc - Lt) / (Lc - Lb));
  const hx = (a, c) => Math.round(a * (1 - t) + c * t).toString(16).padStart(2, '0');
  return '#' + hx(r, bg[0]) + hx(g, bg[1]) + hx(b, bg[2]);
}
const PADL = 8, COLGAP = 10;                        // gutter: name col | chip col
const BADGE_FS = 9;
const NICE = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800];
const BADGE = { working: { bg: '#E0B020', fg: '#332600' }, ready: { bg: '#2B7FB8', fg: '#ffffff' },
                attention: { bg: '#C0392B', fg: '#ffffff' }, compacting: { bg: '#11808f', fg: '#ffffff' } };
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
// Judging band: a compact second timeline UNDER the session lanes, on the SAME axis — one row per
// summarizer judge (design/judge.md). Each mark is FILLED with the colour of the SESSION it acted on and
// OUTLINED in the judge's OWN colour (so a bar reads as "judge X on session Y"). Fed by
// data.judging = [{judge, sid, t, kind, text}]. Each judge's colour is a distinct hue from the romp palette.
const JUDGES = [
  { key: 'captioner', color: '#1EA1EB' }, { key: 'archiver', color: '#54B204' },
  { key: 'planner', color: '#E0B020' }, { key: 'grouper', color: '#4EA8A9' },
  { key: 'closer', color: '#C0392B' }, { key: 'distiller', color: '#D26EA8' },
  { key: 'courier', color: '#9088F0' },
];
const JROW = 14, JBAR_H = 9, JB_TOPGAP = 17, JB_BOTGAP = 5, JMARK_MINW = 6, JMERGE_GAP = 110;
const JUDGE_KIND = { segment: 'caption', turn: 'turn caption', index: 'archived', mint: 'new goal',
  sub: 'filed a step', done: 'completed', block: 'needs you', group: 'regrouped', plant: 'handoff in',
  distill: 'key takeaway', brief: 'decision brief' };

function el(t, a) { const n = document.createElementNS(SVGNS, t); for (const k in a) n.setAttribute(k, a[k]); return n; }
function esc(s) { return (s || '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function clock(t) { const d = new Date(t * 1000); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
function clockS(t) { const d = new Date(t * 1000); return clock(t) + ':' + String(d.getSeconds()).padStart(2, '0'); }   // seconds precision for API call times
function fmtWin(s) { return s < 3600 ? Math.round(s / 60) + 'm' : (s / 3600 < 10 ? (s / 3600).toFixed(1) : Math.round(s / 3600)) + 'h'; }
function fmtTokens(n) { n = Math.round(n || 0); return n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n); }
function fmtDur(ms) { ms = Math.round(ms || 0); return ms < 1000 ? ms + 'ms' : ms < 60000 ? (ms / 1000).toFixed(1) + 's' : Math.round(ms / 60000) + 'm'; }
// Pure (exported for tests): a long idle gap's SPAN as a concise day/week/month label ("2 days", "1 week",
// "3 weeks", "2 months") so a multi-day broken-axis break isn't ambiguous between its two HH:MM boundary
// clocks ("23:40 → 08:50" could be 9h or 2 days). Day-scale only — callers gate on span ≥ 1 day (the user
// 2026-06-17). Each unit's count is clamped below the next unit's threshold so it never reads "7 days".
function fmtSpan(s) {
  const DAY = 86400, WEEK = 7 * DAY, MONTH = 30 * DAY;
  const u = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
  if (s < WEEK)  return u(Math.min(6, Math.max(1, Math.round(s / DAY))),  'day');
  if (s < MONTH) return u(Math.min(4, Math.max(1, Math.round(s / WEEK))), 'week');
  return u(Math.max(1, Math.round(s / MONTH)), 'month');
}
function niceStep(W) { for (const s of NICE) if (W / s <= 8) return s; return 172800; }
// Smooth live-edge advance (the user 2026-06-13): between data polls, advance the effective `now` by the
// wall-clock elapsed since the current data.now was observed, so the live edge GLIDES instead of jumping
// each poll (most visible zoomed in). Pure + exported so the clamp is unit-tested.
//   baseSec — the data's `now` (epoch sec)      live  — are we live-following right now?
//   baseMs  — monotonic ms when baseSec observed  nowMs — monotonic ms now
// Clamp the advance to [0, maxAheadSec]: never run backward (a clock hiccup), and never fling the edge
// far ahead if the tab was backgrounded (rAF paused → huge elapsed) or the kernel went quiet.
const MAX_INTERP_AHEAD = 30;   // seconds the edge may glide past the last data.now before it just waits
const LIVE_MIN_PX = 0.15;      // live-tick repaints once the edge would move ≥ this many px — small so the
                               // glide stays smooth at high zoom (effectively native rAF), but >0 so a
                               // near-static (zoomed-out) edge idles instead of repainting for nothing
function perfNow() { return (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now(); }
function interpNow(baseSec, baseMs, nowMs, live, maxAheadSec) {
  if (!live || baseMs == null) return baseSec;
  const cap = maxAheadSec == null ? MAX_INTERP_AHEAD : maxAheadSec;
  return baseSec + Math.max(0, Math.min((nowMs - baseMs) / 1000, cap));
}

// Re-anchor decision for the live edge's time-baseline (pure + exported for unit tests). The edge
// FREE-RUNS on the local clock between re-anchors (interpNow off a FIXED baseSec/baseMs); we re-snap the
// baseline onto a fresh data.now only on a genuine STEP — never for the few-ms poll-ARRIVAL jitter which,
// snapped every poll, made the live edge hiccup ~1-2px while otherwise gliding smoothly (the user
// 2026-06-15; worse zoomed in, where a px is fewer ms). Re-anchor when:
//   • no anchor yet (first poll), or we're not live-following (held/frozen: nowS doesn't drive the window
//     position — `off` cancels it — so keeping data.now fresh is jump-free AND keeps off-screen pending
//     items advancing), or we just (re)entered live-following (adopt the current now), or
//   • the free-running edge has drifted from data.now past REANCHOR_SEC — a backgrounded-tab resume
//     (interpNow's clamp left us behind), a seek, or real client↔kernel clock skew → one clean catch-up.
// Same physical machine → data.now and the local clock share a rate, so a live edge re-anchored once then
// free-run stays locked to data.now (drift ~0); the constant transport-latency offset is invisible.
const REANCHOR_SEC = 0.5;   // s of edge↔data.now drift tolerated before a single corrective snap
function shouldReanchorEdge(baseSec, baseMs, nowMs, dataNow, live, wasLive) {
  if (baseSec == null || baseMs == null || !live || !wasLive) return true;
  const displayed = interpNow(baseSec, baseMs, nowMs, true, MAX_INTERP_AHEAD);
  return Math.abs(dataNow - displayed) > REANCHOR_SEC;
}

// Right edge a work bar is DRAWN to. An OPEN ("still working") bar has its `end` baked to data.now at
// emit, so between polls it would sit at the stale now while the axis glides past — then jump forward on
// the next re-emit (the user saw this 2026-06-13). So draw an open bar to the interpolated live edge
// (nowS) instead, so it advances WITH the axis; a closed bar keeps its real end. "open" = the data's
// flag if present, else (robust) its end reached the emit-time now (open intervals ride `now`).
function barEndT(t, nowS, dataNow) {
  const liveBar = t.open === true || (typeof t.end === 'number' && t.end >= dataNow);
  return liveBar ? Math.max(nowS, t.start) : t.end;
}

// Which axis a click-drag commits to once it passes the threshold (the user 2026-06-13's mouse model):
// horizontal-dominant → PAN the plot, vertical-dominant → REORDER the lane (mirrors onWheel's horiz/vert
// split). null until it moves enough to decide, so a plain click still selects/opens the lane.
function dragAxis(dx, dy, threshold) {
  const t = threshold == null ? 4 : threshold;
  if (Math.abs(dx) < t && Math.abs(dy) < t) return null;
  return Math.abs(dx) > Math.abs(dy) ? 'pan' : 'row';
}
// The uuid anchor a WORK-intent click opens in the chat: the period's READABLE
// reply line (replyUuid = last assistant line with text, NOT the first which is
// usually a thinking block), then workUuid (first reply line), then the boundary
// uuid (an interrupted period has no reply at all). Shared by the focus handler
// and the work-bar click so the two landings can never drift apart again.
function workAnchorOf(t) { return (t && (t.replyUuid || t.workUuid || t.uuid)) || null; }

// Which ATOM of a turn a highlight set covers — `hit(id)` = membership in the active DAG-journey
// ∪ hover set. A turn renders two glyphs: the prompt DOT and the work-period BAR. The DOT lights
// for the whole-turn id (a DAG journey / a coarse card hover wants the whole turn) OR the PROMPT
// atom id; the BAR for the whole-turn id OR the WORK atom id. Because the two atom ids are minted
// distinctly by romp-events (t.promptId / t.workId), a chat 'message' hover (emitting promptId)
// rings ONLY the dot and an 'action' hover (emitting workId) ONLY the bar — the split is read from
// the data model, never guessed at render time. Exported for tests.
function dotLit(t, hit) { return hit(t.id) || hit(t.promptId); }
function barLit(t, hit) { return hit(t.id) || hit(t.workId); }

// Pure (exported for tests): from MERGED activity intervals [[a,b],…] (sorted, non-overlapping)
// the list of idle stretches worth collapsing on the broken axis — each ≥GAP_MIN AND wider than the
// collapsed width gapCT. Two sources: gaps BETWEEN activity, plus — when `now` is given — the TRAILING
// gap from the last activity's end up to now (the user 2026-06-12), so a quiet period before the
// present collapses too. Returns [{ ra, rb, trailing }] in ascending order; the trailing gap (if any)
// is last and flagged so its right boundary (now) draws no "resumed" clock.
function idleGaps(merged, gapCT, now) {
  const gaps = [];
  for (let i = 1; i < merged.length; i++) {
    const ga = merged[i - 1][1], gb = merged[i][0], D = gb - ga;
    if (D >= GAP_MIN && D > gapCT) gaps.push({ ra: ga, rb: gb, trailing: false });
  }
  if (now != null && merged.length) {
    const ga = merged[merged.length - 1][1], D = now - ga;
    if (D >= GAP_MIN && D > gapCT) gaps.push({ ra: ga, rb: now, trailing: true });
  }
  return gaps;
}

function badgeFor(s) {
  if (!s || !s.live) return null;
  let m = null;
  if (s.state === 'working') m = { label: 'WORKING', kind: 'working' };
  else if (s.state === 'permission' || s.state === 'awaiting') m = { label: 'BLOCKED', kind: 'attention' };
  else if (s.state === 'waiting' || s.state === 'idle') m = { label: 'READY', kind: 'ready' };
  if (!m) return null;
  return { label: m.label, bg: BADGE[m.kind].bg, fg: BADGE[m.kind].fg };
}

// context-window fill % → a battery bar (matches romp-chat-view's context indicator, v0.4.115): the
// fill WIDTH = pct, recolored by level (green <60, amber 60–84, red ≥85). null for historical sessions
// / before first report. BAT_W×BAT_H is the bar box.
const BAT_W = 48, BAT_H = 14;
function ctxInfo(s) {
  if (!s || s.context == null) return null;
  const p = s.context;
  return { label: p + '%', pct: p, color: p >= 85 ? '#c0392b' : (p >= 60 ? '#e0b020' : '#54B204') };
}

// Model + effort, e.g. "Opus 4.8 xhigh" — the SAME string the Claude status bar shows.
// statusline.sh publishes @claude-model/@claude-effort to tmux; the data layer reads them onto the
// session. Rendered as muted secondary text between the name and the state chip. '' when unknown
// (historical/dead lanes never reported it, and some models carry no effort level).
const MODEL_FG = '#9aa0a6';
function modelLabel(s) {
  if (!s || !s.model) return '';
  return s.effort ? s.model + ' ' + s.effort : s.model;
}

// The model + effort labels are little drop-down pickers (mirror of the chat-view statusline's): on a
// LIVE lane, clicking the model or effort word opens a menu whose pick injects the matching /model or
// /effort slash command into that session's pane (see _sendCommand → tmux, like _compactSession). The
// label refreshes on the next poll when the TUI republishes @claude-model/@claude-effort; _metaPending
// dims the word in the gap. Values mirror chat-view's allowlist (extension.ts META_VALUES) verbatim.
const META_HOVER_FG = '#e6edf3';   // brighten the word + reveal its caret on hover
const META_CARET = ' ▾';           // appended (hair-spaced) after each clickable word
// Per-lane feed show/hide EYE (the user 2026-06-22, replacing the old settings gear + flag menu): sits
// between the name and the model. ON the feed (default) = a normal gray eye, its prompts mint feed cards;
// OFF the feed = the SAME gray eye struck through + DIMMER (de-emphasised — NOT a highlight colour; we don't
// spotlight the disabled state, the user 2026-06-22), its prompts won't make cards though the lane stays on
// the timeline (re-opening only affects NEW prompts; it doesn't resurface past ones to clear). One click
// toggles it directly — no menu.
// Drawn (not an emoji) so it stays crisp + monochrome everywhere: an almond outline + pupil; `off`=true adds
// a strike-through slash so the muted state is obvious. One gray throughout — the caller dims the off state.
function eyeIcon(off, cx, cy, color) {
  const g = el('g', { 'pointer-events': 'none' });
  g.appendChild(el('path', { d: 'M' + (cx - 6) + ' ' + cy + ' C' + (cx - 3) + ' ' + (cy - 3.6) + ' ' + (cx + 3) + ' ' + (cy - 3.6) + ' ' + (cx + 6) + ' ' + cy + ' C' + (cx + 3) + ' ' + (cy + 3.6) + ' ' + (cx - 3) + ' ' + (cy + 3.6) + ' ' + (cx - 6) + ' ' + cy + ' Z', fill: 'none', stroke: color, 'stroke-width': 1.2 }));
  g.appendChild(el('circle', { cx: cx, cy: cy, r: 1.5, fill: color }));
  if (off) g.appendChild(el('line', { x1: cx - 6.5, y1: cy + 4.5, x2: cx + 6.5, y2: cy - 4.5, stroke: color, 'stroke-width': 1.4, 'stroke-linecap': 'round' }));
  return g;
}
const MODEL_CHOICES = [
  { label: 'Fable', value: 'fable' },
  { label: 'Opus', value: 'opus' },
  { label: 'Sonnet', value: 'sonnet' },
  { label: 'Haiku', value: 'haiku' },
  { label: 'Default', value: 'default' },
];
const EFFORT_CHOICES = ['low', 'medium', 'high', 'xhigh', 'max'].map((v) => ({ label: v, value: v }));
// Is this menu entry the lane's CURRENT value? Effort matches exactly; the model var holds a display
// name ("Opus 4.8"), so match on the leading word — same rule as the chat-view's isCurrentMeta.
function isCurrentMeta(kind, s, value) {
  const cur = ((kind === 'model' ? s.model : s.effort) || '').toLowerCase();
  return kind === 'effort' ? cur === value : cur.startsWith(value);
}

// rounded orthogonal path through waypoints (message connectors)
function roundedPath(pts, r) {
  const p = pts.filter((q, i) => i === 0 || q.x !== pts[i - 1].x || q.y !== pts[i - 1].y);
  if (p.length < 2) return '';
  let d = 'M ' + p[0].x + ' ' + p[0].y;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], c = p[i], b = p[i + 1];
    const inL = Math.hypot(c.x - a.x, c.y - a.y), outL = Math.hypot(b.x - c.x, b.y - c.y);
    const rr = Math.max(0, Math.min(r, inL / 2, outL / 2));
    const i1 = { x: c.x - Math.sign(c.x - a.x) * rr, y: c.y - Math.sign(c.y - a.y) * rr };
    const o1 = { x: c.x + Math.sign(b.x - c.x) * rr, y: c.y + Math.sign(b.y - c.y) * rr };
    d += ' L ' + i1.x + ' ' + i1.y + ' Q ' + c.x + ' ' + c.y + ' ' + o1.x + ' ' + o1.y;
  }
  const L = p[p.length - 1]; d += ' L ' + L.x + ' ' + L.y; return d;
}
function crossX(lo0, hi0, xs, xe, obstacles) {
  const lo = Math.min(lo0, hi0), hi = Math.max(lo0, hi0);
  const between = obstacles.filter((o) => o.lane > lo && o.lane < hi && o.x >= xs - CLEAR && o.x <= xe + CLEAR);
  let xc = xs, changed = true, g = 0;
  while (changed && g++ < 60) { changed = false; for (const o of between) if (Math.abs(o.x - xc) < CLEAR) { xc = o.x + CLEAR; changed = true; } }
  return xc > xe ? xs : xc;
}

class TimelinePanel {
  constructor(host) {
    this.host = host;
    this.data = null;
    this.fitted = false;
    this.M = { left: 130, right: 16, top: 8, bottom: 22 };   // axis labels live in the bottom margin
    this._mc = document.createElement('canvas').getContext('2d');

    // No on-screen controls: window width + offset are driven entirely by trackpad gestures
    // (horizontal scroll = pan, pinch = zoom). They live as continuous SECONDS in _winSec/_offSec,
    // persisted directly to localStorage. winSec()/offSec() read them; fitWindow seeds _winSec.
    this.WSTORE = 'romp-tl-winsec';
    this.OSTORE = 'romp-tl-offsec';
    this.CSTORE = 'romp-tl-collapse';
    this.LSTORE = 'romp-tl-locknow';
    this._winSec = null; this._offSec = 0; this._drawRAF = null;
    // broken-axis: collapse long idle gaps (no work on any lane — e.g. overnight) into a thin squiggle
    // break, so the active periods get the width. ON by default; the checkbox below the axis toggles it.
    this._collapseGaps = true;
    // 🔒 lock-to-now (the user 2026-06-11): the live edge is pinned PERMANENTLY — pan gestures can't
    // leave it, and a focus that's off-screen ZOOMS OUT (window widens leftward, right edge stays at
    // now, target lands ~mid-window) instead of panning away. OFF by default; checkbox far right.
    this._lockNow = false;
    this._compactClicked = {};   // sid → click ts: show the compacting cue OPTIMISTICALLY until the real state catches up
    this._pendingFlags = {};     // sid → {flag: value}: an optimistic eye-toggle held STICKY across pushes until the kernel's data confirms it (no flicker-back)
    try { if (localStorage.getItem(this.CSTORE) === '0') this._collapseGaps = false; } catch (e) {}
    try { if (localStorage.getItem(this.LSTORE) === '1') this._lockNow = true; } catch (e) {}
    try { const v = localStorage.getItem(this.WSTORE); if (v != null && /^\d+(\.\d+)?$/.test(v)) { this._winSec = +v; this.fitted = true; } } catch (e) {}
    try { const v = localStorage.getItem(this.OSTORE); if (v != null && /^\d+(\.\d+)?$/.test(v)) this._offSec = +v; } catch (e) {}
    if (this._lockNow) this._offSec = 0;   // a restored mid-pan offset never overrides the lock
    // Live-follow vs hold-position. PINNED (default) = the window's right edge tracks `now`, so it
    // auto-scrolls. The instant the user pans/zooms off the now-edge it UNPINS and HOLDS its absolute
    // real-time position (no creep as `now` advances); a far-right ⟩⟩ button re-pins + resumes follow.
    // _holdReal = the absolute right-edge time held while unpinned; _offDirty = a gesture just wrote
    // _offSec, so draw() honors it verbatim this frame before resuming the hold. Restored mid-pan stays
    // unpinned (loaded off>0). [[contract with vs_chat]] is unaffected — this is pan state only.
    this._offDirty = true; this._holdReal = null; this._pinned = !(this._offSec > 0);
    // Smooth live-edge advance (see interpNow): while live-following, a rAF loop (_liveRAF) advances the
    // effective `now` by wall-clock between polls so the window glides. _nowBaseSec/_nowBaseMs = the edge's
    // time-baseline (epoch sec + the monotonic ms when it was observed); the edge FREE-RUNS off this fixed
    // pair and shouldReanchorEdge re-snaps it only on a genuine step, so per-poll arrival jitter no longer
    // hiccups the edge. _wasLive = were we live-following at the last poll (→ re-anchor on re-entry).
    // _lastLiveNow = effective-now of the last live repaint (sub-pixel guard so we only repaint when the
    // edge would actually move). Re-armed each poll; self-stops when not live.
    this._nowBaseSec = null; this._nowBaseMs = null; this._wasLive = false;
    this._liveRAF = null; this._lastLiveNow = null;

    this.wrap = host.createDiv({ cls: 'romp-tl-wrap' });
    this.svg = document.createElementNS(SVGNS, 'svg');
    this.svg.setAttribute('xmlns', SVGNS); this.wrap.appendChild(this.svg);

    // controls row BELOW the time axis. Layout (the user 2026-06-11): usage bars LEFT-justified,
    // then a flexible spacer, then RIGHT-justified "collapse idle gaps" with the 🔒 lock-to-now
    // toggle at the far right, under the lanes.
    this.controls = this.wrap.createDiv({ cls: 'romp-tl-controls' });
    this.controls.setAttribute('style', 'display:flex;align-items:center;gap:16px;padding:4px 8px;font-size:11px;color:#9aa0a6;user-select:none;');

    // (The restart-kernel ↻ button moved UP to the feed's top-right, next to the ⛭ settings gear (the
    // user 2026-06-17) — off the timeline's bottom-left, which now carries only the usage bars + the
    // right-justified gap/lock toggles. The gear was already there; the ↻ now sits beside it. The
    // 'romp:settings' contract still lives in ui/webview/settings.ts.)

    // Claude usage bars (the /usage rate-limit %: 5-hour + weekly), LEFT-justified. Hidden until
    // statusline.sh reports usage (Pro/Max only); _updateUsage() fills them each
    // poll from data.usage. The pct bar is color-coded green/amber/red; the reset countdown is in the
    // hover title.
    this._usageWrap = this.controls.createDiv();
    this._usageWrap.setAttribute('style', 'display:none;align-items:center;gap:14px;');
    this._usageBars = {};
    // Each window = a label + a column of TWO stacked mini-bars: the USAGE % (colored) over a
    // TIME-THROUGH-WINDOW bar (neutral slate — how far between the window's start = resets_at−winSec and
    // its reset). Comparing the two fill widths is the BURN-RATE cue: usage ahead of time = spending
    // faster than the window refills. Only the two account-wide windows (5h + weekly); no model-specific.
    const mkUsageBar = (key, label, winSec) => {
      const g = this._usageWrap.createDiv();
      g.setAttribute('style', 'display:inline-flex;align-items:center;gap:6px;');
      const lab = g.createSpan({ text: label }); lab.setAttribute('style', 'opacity:0.85;');
      const col = g.createDiv(); col.setAttribute('style', 'display:flex;flex-direction:column;gap:3px;');
      const mkRow = (kindLabel, fillColor, txtOpacity) => {
        const row = col.createDiv(); row.setAttribute('style', 'display:inline-flex;align-items:center;gap:4px;');
        const kl = row.createSpan({ text: kindLabel }); kl.setAttribute('style', 'opacity:0.55;min-width:42px;');
        const track = row.createDiv();
        track.setAttribute('style', 'width:64px;height:6px;border-radius:3px;background:rgba(255,255,255,0.10);overflow:hidden;');
        const fill = track.createDiv();
        fill.setAttribute('style', 'height:100%;width:0%;border-radius:3px;background:' + fillColor + ';transition:width .3s ease;');
        const txt = row.createSpan({ text: '–' }); txt.setAttribute('style', 'min-width:30px;font-variant-numeric:tabular-nums;opacity:' + txtOpacity + ';');
        return { row, fill, txt };
      };
      const usage = mkRow('used', '#54B204', '0.9');       // % of the limit consumed — color set per-poll
      const time = mkRow('elapsed', '#6b7a8c', '0.55');    // % of the window elapsed — neutral slate (pace)
      this._usageBars[key] = { group: g, winSec, usage, time };
    };
    mkUsageBar('fiveHour', 'session', 5 * 3600);
    mkUsageBar('sevenDay', 'week', 7 * 86400);

    // (The per-window token grid that used to sit here was removed at the user's request 2026-06-18 — only
    // the /usage rate-limit bars above remain. The kernel still ships data.tokens; nothing reads it now.)

    // spacer: everything after it sits flush right
    const ctlSpacer = this.controls.createDiv();
    ctlSpacer.setAttribute('style', 'flex:1 1 auto;');

    const cbWrap = this.controls.createEl('label');
    cbWrap.setAttribute('style', 'display:inline-flex;align-items:center;gap:5px;cursor:pointer;');
    this._collapseBox = cbWrap.createEl('input');
    this._collapseBox.type = 'checkbox';   // set as a property (the VS Code createEl shim ignores {type})
    this._collapseBox.checked = this._collapseGaps;
    cbWrap.createSpan({ text: 'collapse gaps' });
    this._collapseBox.addEventListener('change', () => {
      this._collapseGaps = this._collapseBox.checked;
      try { localStorage.setItem(this.CSTORE, this._collapseGaps ? '1' : '0'); } catch (e) {}
      this.draw();
    });

    // Lock-to-now, far right: while checked the live edge can't be left — pans snap back,
    // and an off-screen focus ZOOMS OUT (right edge stays at now) instead of panning away.
    // The icon is an inline SVG padlock (not the emoji): locked = shackle seated on the body;
    // unlocked = shackle hinged at the top-right, swung clearly out to the SIDE (the user 2026-06-11).
    const LOCK_CLOSED = '<svg viewBox="0 0 15 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" style="display:block">'
      + '<rect x="3" y="6.2" width="8" height="5.6" rx="1.2"/>'
      + '<path d="M4.8 6.2 V4.4 a2.2 2.2 0 0 1 4.4 0 V6.2"/></svg>';
    const LOCK_OPEN = '<svg viewBox="0 0 15 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" style="display:block">'
      + '<rect x="3" y="6.2" width="8" height="5.6" rx="1.2"/>'
      + '<path d="M9.4 6.2 V5.3 A2.4 2.4 0 0 1 13.6 3.7"/></svg>';
    const lockWrap = this.controls.createEl('label');
    lockWrap.setAttribute('style', 'display:inline-flex;align-items:center;gap:5px;cursor:pointer;');
    lockWrap.title = 'keep the timeline at the present: focus jumps zoom out instead of panning away';
    this._lockBox = lockWrap.createEl('input');
    this._lockBox.type = 'checkbox';
    this._lockBox.checked = this._lockNow;
    this._lockIcon = lockWrap.createSpan();
    this._LOCK_CLOSED = LOCK_CLOSED; this._LOCK_OPEN = LOCK_OPEN;   // stashed so _setLock can repaint the icon (e.g. a drag unlocks)
    this._lockIcon.setAttribute('style', 'display:inline-flex;align-items:center;opacity:' + (this._lockNow ? '1' : '0.7') + ';');
    this._lockIcon.innerHTML = this._lockNow ? LOCK_CLOSED : LOCK_OPEN;
    lockWrap.createSpan({ text: 'now' });
    this._lockBox.addEventListener('change', () => {
      this._setLock(this._lockBox.checked);
      if (this._lockNow) this._jumpToNow();   // snap to the live edge the moment it locks
      this.draw();
    });

    this.tip = document.body.createDiv({ cls: 'romp-tl-tip' });
    this._tipOwner = null;   // the hit element that opened the current tip (see _onTipSweep)
    // The judging band is gated on the global Debug setting (romp:settings.debug), which the feed-gear ⛭
    // toggles in another same-origin iframe. React to that toggle via the storage event so the band
    // appears/disappears live (no reload). draw() reads the flag fresh, so we just repaint.
    try { window.addEventListener('storage', (e) => { if (e && e.key === 'romp:settings') this.draw(); }); } catch (e) {}

    // model/effort drop-down pickers: the open menu element + per-lane optimistic "pending" cues
    // ('sid:kind' → {was, until}) that dim a word until the tmux var actually flips (or 20s elapses).
    this._metaMenu = null; this._metaPending = {};
    this._onDocClick = () => this._closeMetaMenu();
    this._onDocKey = (e) => { if (e.key === 'Escape') this._closeMetaMenu(); };
    document.addEventListener('click', this._onDocClick);
    document.addEventListener('keydown', this._onDocKey);

    this._onResize = () => this.draw();
    this._onWheel = (e) => this.onWheel(e);
    window.addEventListener('resize', this._onResize);
    // Trackpad gestures over the plot: two-finger horizontal scroll pans the offset, pinch/expand
    // zooms the window width (anchored at the cursor). Pinch reaches us as a ctrlKey wheel event in
    // Chromium/Electron. Non-passive so we can preventDefault.
    this.wrap.addEventListener('wheel', this._onWheel, { passive: false });
    // Touchscreen equivalents (phones/tablets, where there are no wheel events): one finger PANS — or,
    // when 🔒locked, ZOOMS with the right edge pinned at now; two fingers PINCH-zoom anchored at the
    // midpoint. Mirrors onWheel's math. touch-action:pan-y keeps vertical lane-scroll native while we own
    // horizontal + pinch and stop the browser from page-zooming the whole view. Touch never breaks 🔒.
    this._touch = null;
    this.wrap.style.touchAction = 'pan-y';
    this._onTouchStart = (e) => this.onTouchStart(e);
    this._onTouchMove = (e) => this.onTouchMove(e);
    this._onTouchEnd = (e) => this.onTouchEnd(e);
    this.wrap.addEventListener('touchstart', this._onTouchStart, { passive: false });
    this.wrap.addEventListener('touchmove', this._onTouchMove, { passive: false });
    this.wrap.addEventListener('touchend', this._onTouchEnd, { passive: false });
    this.wrap.addEventListener('touchcancel', this._onTouchEnd, { passive: false });
    // keyboard: ↑/↓ move a SELECTED lane cursor, Enter opens it in the chat. Scoped to the timeline
    // (wrap is focusable + focused on click) so arrows act only when the timeline has focus, not globally.
    this.selectedSid = null; this._vis = [];
    // vertical drag-to-reorder lanes: _drag holds the in-flight gesture, _dragOrder is the live
    // (transient) sid order draw() honors while dragging; on drop we write the full SID order to the
    // shared session-order.json (the chat tabs read+write the same file). _suppressClick stops the
    // mouseup-click from also firing a select after a real drag.
    this._drag = null; this._dragOrder = null; this._suppressClick = false;
    this._dag = null;   // request-DAG journey overlay (set by focusEvent when the feed supplies a dag)
    this._hover = null; // feed→timeline hover highlight {ids,...} (set by update from data.hover OR setHover; null = none)
    this._hoverNonce = null;  // highest hover nonce applied — gates the direct push vs the file poll so neither clobbers the other (the same monotonic nonce rides both; see setHover)
    this._frozeFromPin = false;  // freeze-on-hover: true while a tooltip has paused live-follow that WAS pinned (so hideTip knows to resume)
    this._dirtyWhileTip = false; // a data poll arrived while a tooltip was up (draw was skipped) → hideTip repaints the catch-up
    this._unfreezeTimer = null;  // deferred hideTip resume — cancelled by a quick glyph→glyph hover handoff
    this.wrap.tabIndex = 0; this.wrap.style.outline = 'none';
    this._onKey = (e) => this.onKey(e);
    this._focusWrap = () => this.wrap.focus();
    this.wrap.addEventListener('keydown', this._onKey);
    this.wrap.addEventListener('mousedown', this._focusWrap);
    // SAFETY NET for a stuck tooltip: a hit's own mouseleave never fires if a redraw
    // (expand/collapse, a live update) pulls the element out from under a stationary
    // cursor — so the tip stays shown over empty timeline. On any move over the plot,
    // drop the tip once the cursor is no longer over the element that opened it (or
    // that element is gone). hideTip() on the owner's mouseleave still handles the
    // normal case; this only catches the orphaned ones.
    this._onTipSweep = (e) => {
      if (!this.tip || !this.tip.classList.contains('show')) return;
      const o = this._tipOwner;
      if (!o || !o.isConnected) { this.hideTip(); return; }   // owner removed by a redraw
      const r = o.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) this.hideTip();
    };
    this.wrap.addEventListener('mousemove', this._onTipSweep);
  }

  destroy() {
    window.removeEventListener('resize', this._onResize);
    if (this.wrap) { this.wrap.removeEventListener('wheel', this._onWheel); this.wrap.removeEventListener('keydown', this._onKey); this.wrap.removeEventListener('mousedown', this._focusWrap); this.wrap.removeEventListener('mousemove', this._onTipSweep);
      this.wrap.removeEventListener('touchstart', this._onTouchStart); this.wrap.removeEventListener('touchmove', this._onTouchMove); this.wrap.removeEventListener('touchend', this._onTouchEnd); this.wrap.removeEventListener('touchcancel', this._onTouchEnd); }
    if (this._drawRAF) cancelAnimationFrame(this._drawRAF);
    this._stopLiveTick();
    if (this._autoOpenT) clearTimeout(this._autoOpenT);
    if (this._unfreezeTimer) clearTimeout(this._unfreezeTimer);
    if (this._onDragMove) window.removeEventListener('mousemove', this._onDragMove, true);
    if (this._onDragUp) window.removeEventListener('mouseup', this._onDragUp, true);
    document.removeEventListener('click', this._onDocClick);
    document.removeEventListener('keydown', this._onDocKey);
    this._closeMetaMenu();
    if (this.tip) this.tip.remove();
  }

  // [r,g,b] of the surface the timeline sits on (Obsidian theme / VS Code panel bg), so the perceptual
  // fade blends toward the real background. Walks up for the first non-transparent bg; dark fallback.
  _surfaceBg() {
    try {
      let node = this.wrap;
      while (node) {
        const c = getComputedStyle(node).backgroundColor || '';
        const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
        if (m && (m[4] === undefined || parseFloat(m[4]) > 0.05)) return [+m[1], +m[2], +m[3]];
        node = node.parentElement;
      }
    } catch (e) {}
    return [24, 24, 24];
  }

  _font(b) { this._mc.font = (b ? '700 ' + BADGE_FS + 'px ' : '650 12px ') + FONT; }
  labelWidth(s) { this._font(false); return this._mc.measureText(s || '').width; }
  badgeWidth(s) { this._font(true); return this._mc.measureText(s || '').width; }
  ctxWidth(s) { this._mc.font = '600 11px ' + FONT; return this._mc.measureText(s || '').width; }

  winSec() { const w = this._winSec != null ? this._winSec : Math.sqrt(MIN_W * MAX_W); return Math.round(Math.max(MIN_W, Math.min(MAX_W, w))); }
  offSec() { return Math.round(Math.max(0, Math.min(MAX_OFFSET, this._offSec || 0))); }   // 0 at right (now) … 72h at left

  // keyboard lane selection: ↑/↓ move the cursor AND auto-open that session in the chat WITHOUT
  // stealing focus (so you can keep arrowing through and previewing). Enter commits + focuses the chat.
  onKey(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); this.moveSelection(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.moveSelection(-1); }
    else if (e.key === 'Enter') { e.preventDefault(); this.composeSelected(); }    // Enter → cursor into the prompt box
  }
  moveSelection(dir) {
    const vis = this._vis || [];
    if (!vis.length) return;
    let idx = vis.findIndex((s) => s.id === this.selectedSid);
    if (idx < 0) idx = dir > 0 ? -1 : vis.length;            // first press lands on the first/last lane
    idx = Math.max(0, Math.min(vis.length - 1, idx + dir));
    this.selectedSid = vis[idx].id;
    this.draw();
    // debounce the auto-open so holding/rapid arrows settle on the lane you land on (not every one
    // in between) — preview-only, focus stays on the timeline.
    if (this._autoOpenT) clearTimeout(this._autoOpenT);
    this._autoOpenT = setTimeout(() => { this._autoOpenT = null; this.openSelected(true); }, 120);
  }
  // a lane's LIVE transcript id = its most recent turn's tid (the current fork), falling back to the
  // lane sid. Opening with no anchor → the chat scrolls to the bottom (latest) of that transcript.
  _laneTid(s) {
    const turns = (this.data && this.data.turns && this.data.turns[s.id]) || [];
    const t = turns.length ? turns[turns.length - 1] : null;
    return (t && t.tid) || s.id;
  }
  openSelected(preserveFocus) {
    const s = (this._vis || []).find((x) => x.id === this.selectedSid);
    if (!s) return;
    this.openChat(this._laneTid(s), null, preserveFocus);   // switch → bottom (latest), no specific anchor
  }
  // Enter on the selected lane → open its tab (at bottom) and drop the cursor into the chat's message
  // box so you can type a message to that session. (Needs the chat-view composer enabled — vs_chat.)
  composeSelected() {
    const s = (this._vis || []).find((x) => x.id === this.selectedSid);
    if (!s) return;
    this.openChat(this._laneTid(s), null, false, true);
  }

  _scheduleDraw() {
    if (this._drawRAF) return;
    this._drawRAF = requestAnimationFrame(() => { this._drawRAF = null; this.draw(); });
  }

  // Trackpad gestures: horizontal two-finger scroll → pan (offset); pinch/expand → zoom the
  // window width, anchored at the time under the cursor. Both write the continuous window/
  // offset state and re-seat the slider thumbs, so the result persists + redraws like a drag.
  onWheel(e) {
    const g = this._geom; if (!g || !this.data || !this.data.sessions) return;
    const pinch = e.ctrlKey;                                   // Chromium maps trackpad pinch → ctrl+wheel
    const horiz = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    // wheel model (the user 2026-06-22): a plain VERTICAL wheel SCROLLS the panel up/down NATIVELY — we no
    // longer hijack it to zoom (that "expanded" the timeline, which the user didn't want). So zoom is now
    // PINCH (ctrl+wheel — trackpad pinch, or ctrl+wheel on a mouse), and a HORIZONTAL wheel (two-finger /
    // shift-wheel) PANS the time axis — EXCEPT when 🔒locked to now, where there's nowhere to pan, so the
    // horizontal wheel ZOOMS with the right edge pinned at now instead (the user 2026-06-22; mirrors the
    // locked touch-drag). Click-drag also pans — and BREAKS the lock; the wheel keeps it.
    if (!pinch && !horiz) return;                             // plain vertical → don't preventDefault, let it scroll
    e.preventDefault();
    const rect = this.svg.getBoundingClientRect();
    const scaleX = rect.width ? g.W / rect.width : 1;          // svg user-units per client px
    const curWin = this.winSec(), curOff = this.offSec();
    // Work in COMPRESSED time (the geom's mapping is LINEAR there). cT0 = window's left edge in
    // compressed seconds. Pan = translate at a CONSTANT compressed-sec-per-px scale → smooth, no rescale.
    const compress = g.compress || ((t) => t);
    const cNow = compress(this.data.now), cT1 = cNow - curOff, cT0 = cT1 - curWin;
    if (pinch) {
      const factor = Math.exp(e.deltaY * 0.01);                // deltaY>0 → wider window (zoom out); pinch is smooth
      const newWin = Math.max(MIN_W, Math.min(MAX_W, curWin * factor));
      const svgX = (e.clientX - rect.left) * scaleX;
      const frac = Math.max(0, Math.min(1, (svgX - g.ml) / g.plotW));   // cursor position across the plot
      const cc = cT0 + frac * curWin;                         // compressed time under the cursor — pin it
      this._winSec = newWin;
      this._offSec = Math.max(0, Math.min(MAX_OFFSET, cNow - (cc + (1 - frac) * newWin)));
    } else if (this._lockNow) {
      // 🔒 horizontal wheel → ZOOM (no pan possible — the right edge is pinned at now). Rightward (toward
      // now) zooms IN, leftward (toward the past) zooms OUT — same direction as the locked touch-drag.
      const factor = Math.exp(-e.deltaX * 0.01);               // deltaX<0 (toward past) → wider window (zoom out)
      this._winSec = Math.max(MIN_W, Math.min(MAX_W, curWin * factor));
    } else {
      const dt = e.deltaX * scaleX * (curWin / g.plotW);       // compressed-sec per px (CONSTANT → smooth pan)
      this._offSec = Math.max(0, Math.min(MAX_OFFSET, curOff - dt));
    }
    if (this._lockNow) this._offSec = 0;   // 🔒 the wheel HONORS the lock: zoom keeps the right edge at now (a DRAG breaks it)
    this._markOffsetGesture();   // honor this _offSec verbatim next frame; re-pin if it lands at the now-edge
    try { localStorage.setItem(this.WSTORE, String(this.winSec())); } catch (e2) {}
    try { localStorage.setItem(this.OSTORE, String(Math.round(this._offSec))); } catch (e2) {}
    this._scheduleDraw();
    this._startLiveTick();   // a pan back to the now-edge re-pins → resume smooth advance (no-op otherwise)
  }

  _touchDist(a, b) { return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY); }

  // Touchscreen pan/zoom (phones — no wheel events). ONE finger, horizontal: PAN the window (free, breaks
  // 🔒 like a mouse drag) — content tracks the finger (drag right → earlier time slides in). When 🔒locked
  // a horizontal drag ZOOMS instead (the right edge stays pinned at now, so there's nowhere to pan) — this
  // is the user's "locked-to-now drag does a zoom." ONE finger, vertical: falls through to native lane
  // scroll (touch-action:pan-y), and a tap with no movement falls through to the lane's click/select. TWO
  // fingers: PINCH-zoom the window width, anchored at the midpoint. Math mirrors onWheel/_panDragMove in
  // COMPRESSED time (linear there). _winSec/_offSec are the same continuous state the wheel + sliders write.
  onTouchStart(e) {
    const g = this._geom; if (!g || !this.data || !this.data.sessions) return;
    if (e.touches.length >= 2) {
      const a = e.touches[0], b = e.touches[1];
      const rect = this.svg.getBoundingClientRect();
      const scaleX = rect.width ? g.W / rect.width : 1;            // svg user-units per client px
      const curWin = this.winSec(), curOff = this.offSec();
      const compress = g.compress || ((t) => t);
      const cNow = compress(this.data.now), cT1 = cNow - curOff, cT0 = cT1 - curWin;
      const svgX = ((a.clientX + b.clientX) / 2 - rect.left) * scaleX;   // midpoint across the plot
      const frac = Math.max(0, Math.min(1, (svgX - g.ml) / g.plotW));
      this._touch = { mode: 'pinch', startDist: Math.max(1, this._touchDist(a, b)), frac,
        cc: cT0 + frac * curWin, cNow, startWin: curWin };          // pin the compressed time under the midpoint
      e.preventDefault();
    } else if (e.touches.length === 1) {
      const t = e.touches[0];
      this._touch = { mode: 'drag', axis: null, startX: t.clientX, startY: t.clientY,
        startOff: this.offSec(), startWin: this.winSec(), locked: this._lockNow };
      // no preventDefault yet — the first real move decides ours (horizontal) vs. native (vertical scroll)
    }
  }
  onTouchMove(e) {
    const d = this._touch, g = this._geom; if (!d || !g || !g.plotW || !this.data) return;
    const rect = this.svg.getBoundingClientRect();
    const scaleX = rect.width ? g.W / rect.width : 1;
    if (d.mode === 'pinch') {
      if (e.touches.length < 2) return;
      const dist = Math.max(1, this._touchDist(e.touches[0], e.touches[1]));
      const newWin = Math.max(MIN_W, Math.min(MAX_W, d.startWin * (d.startDist / dist)));   // spread → narrower window (zoom in)
      this._winSec = newWin;
      this._offSec = Math.max(0, Math.min(MAX_OFFSET, d.cNow - (d.cc + (1 - d.frac) * newWin)));
      e.preventDefault();
    } else if (d.mode === 'drag') {
      const dx = e.touches[0].clientX - d.startX, dy = e.touches[0].clientY - d.startY;
      if (d.axis == null) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 6) return;        // below threshold → still undecided (could be a tap)
        d.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
      }
      if (d.axis === 'y') return;                                     // vertical → leave it to native lane scroll
      const dxc = dx * scaleX;                                        // client px → svg user-units
      if (d.locked) {                                                 // 🔒 → a horizontal drag ZOOMS, right edge stays at now
        this._winSec = Math.max(MIN_W, Math.min(MAX_W, d.startWin * Math.exp(-dxc / g.plotW)));   // drag right → zoom in
        this._offSec = 0;
      } else {                                                        // free PAN — content tracks the finger; breaks 🔒
        const dt = dxc * (d.startWin / g.plotW);
        this._offSec = Math.max(0, Math.min(MAX_OFFSET, d.startOff + dt));   // drag right → window slides to earlier time
        this._setLock(false);
        this._pinned = false;
      }
      this._offDirty = true;
      this._scheduleDraw();
      e.preventDefault();
    }
  }
  onTouchEnd(e) {
    const d = this._touch; if (!d) return;
    if (e.touches && e.touches.length >= 1) {                         // a finger lifted but one remains (pinch→drag): rebaseline
      const t = e.touches[0];
      this._touch = { mode: 'drag', axis: null, startX: t.clientX, startY: t.clientY,
        startOff: this.offSec(), startWin: this.winSec(), locked: this._lockNow };
      return;
    }
    this._touch = null;
    if (d.mode === 'drag' && d.axis !== 'x') return;                  // a native scroll or a tap — nothing of ours to persist
    if (this._lockNow) this._offSec = 0;                              // a 🔒locked zoom keeps the right edge at now
    this._markOffsetGesture();                                        // honor _offSec next frame; re-pin if it landed at the now-edge
    try { localStorage.setItem(this.WSTORE, String(this.winSec())); } catch (e2) {}
    try { localStorage.setItem(this.OSTORE, String(Math.round(this._offSec))); } catch (e2) {}
    this._scheduleDraw();
    this._startLiveTick();
  }

  // A user gesture/nav just wrote _offSec → draw() honors it verbatim this frame (_offDirty), then
  // resumes holding the absolute position. RE-PIN (resume live-follow) when the right edge lands within
  // ~6px of the now-edge, so panning the whole way back to the right turns auto-scroll back on.
  _markOffsetGesture() {
    const g = this._geom;
    const pinEps = (g && g.plotW) ? Math.max(2, 6 * this.winSec() / g.plotW) : 2;   // ~6px of the right edge, in compressed sec
    this._pinned = this.offSec() <= pinEps;
    this._offDirty = true;
  }

  // Programmatically toggle 🔒 lock-to-now, keeping the checkbox + icon + persisted state in sync. A
  // click-drag uses this to BREAK the lock (the user 2026-06-13: drag away from now = free pan).
  _setLock(on) {
    on = !!on;
    if (this._lockNow === on) return;
    this._lockNow = on;
    if (this._lockBox) this._lockBox.checked = on;
    if (this._lockIcon) { this._lockIcon.innerHTML = on ? this._LOCK_CLOSED : this._LOCK_OPEN; this._lockIcon.style.opacity = on ? '1' : '0.7'; }
    try { localStorage.setItem(this.LSTORE, on ? '1' : '0'); } catch (e) {}
  }

  // Far-right ⟩⟩ button (see _drawNowButton): snap the window all the way to the live edge and resume
  // auto-scroll. Only reachable while unpinned (the button hides at the edge).
  _jumpToNow() {
    this._pinned = true; this._offSec = 0; this._offDirty = true;
    this._holdReal = this.data ? this.data.now : null;
    try { localStorage.setItem(this.OSTORE, '0'); } catch (e) {}
    this.draw();
    this._startLiveTick();   // resume the smooth-advance loop now that we're following the edge again
  }

  // --- smooth live-edge advance (see interpNow + the constructor field comment) ---
  // Are we auto-scrolling the live edge right now? (lock forces follow; a hover-freeze or a pan stops it.)
  _liveFollowing() { return (this._pinned || this._lockNow) && !this._frozeFromPin; }
  // On-screen? rAF already pauses for a hidden TAB; this also catches a hidden Obsidian leaf / detached
  // node (no offsetParent) so the loop doesn't spin for an invisible pane. False-negative just degrades
  // to per-poll redraw (no interpolation), never breaks.
  _isVisible() {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return false;
    const w = this.wrap;
    return !!(w && w.offsetParent !== null);
  }
  // The effective `now` draw() renders the right edge at: data.now plus wall-clock since that poll while
  // live-following, else the raw data.now (a held/frozen view must NOT creep as time passes).
  _liveNow() {
    const base = (this._nowBaseSec != null) ? this._nowBaseSec : (this.data ? this.data.now : 0);
    // Frozen on hover → hold EVERYTHING at the hover instant (_holdReal): the axis edge AND, via barEndT /
    // execAt / startAt which read this, the open work bars + pending items. Otherwise they keep advancing
    // per poll while the edge sits still — the "doesn't stop on hover" bug. Not frozen → glide, or data.now.
    if (this._frozeFromPin && this._holdReal != null) return this._holdReal;
    return interpNow(base, this._nowBaseMs, perfNow(), this._liveFollowing(), MAX_INTERP_AHEAD);
  }
  // Arm the rAF loop (no-op if already running or not currently live+visible). Re-armed each poll by
  // update(), so even after the loop self-stops it returns within one poll once we're live again. NOT
  // called from draw() — draw() runs inside the tick, and re-arming there would double the loop.
  _startLiveTick() {
    if (this._liveRAF != null || !this._liveFollowing() || !this._isVisible()) return;
    this._liveRAF = requestAnimationFrame(() => this._tickLive());
  }
  _tickLive() {
    this._liveRAF = null;
    if (!this._liveFollowing() || !this._isVisible() || !this.data) return;   // gate closed → stop the loop
    const g = this._geom;
    // Only repaint when the edge would actually move ≥ LIVE_MIN_PX since the last live draw — a wide
    // (zoomed-out) window where the edge barely creeps costs ~nothing, a zoomed-in one repaints every
    // native frame. Keep looping either way so we catch the moment it does move.
    if (!g || this._lastLiveNow == null || ((this._liveNow() - this._lastLiveNow) / g.winSec * g.plotW) >= LIVE_MIN_PX) {
      this.draw();
    }
    this._liveRAF = requestAnimationFrame(() => this._tickLive());
  }
  _stopLiveTick() { if (this._liveRAF != null) { cancelAnimationFrame(this._liveRAF); this._liveRAF = null; } }

  // (The restart ↻ handler moved to the feed's top-right gear (the kernel's _GEAR_JS) along with the
  // button — the user 2026-06-17. It POSTs the same /restart, polls /healthz, and reloads, as before.)

  // (The settings gear + its modal moved to the feed's top-right ⛭ — the user 2026-06-16. The timeline
  // no longer hosts settings; ui/webview/settings.ts still owns the 'romp:settings' contract
  // and the chat applies it live via the storage event the feed gear fires.)

  // A small vertical ⟩⟩ button hugging the far-right edge, shown ONLY when the view is held back off the
  // live edge (unpinned). Click → _jumpToNow (snap to `now` + resume live-follow). Drawn last so it sits
  // on top; pointer-events on the group only (the rest of the row stays clickable underneath elsewhere).
  _drawNowButton(svg) {
    const g = this._geom; if (!g) return;
    const bw = 16, bh = 46;
    const bx = g.W - this.M.right - bw + 5;            // hug the right edge, slight overhang into the margin
    const axisY = g.H - this.M.bottom;
    const by = g.top + ((axisY - g.top) - bh) / 2;     // vertically centered in the plot band
    const grp = el('g', {}); grp.style.cursor = 'pointer';
    grp.appendChild(el('rect', { x: bx, y: by, width: bw, height: bh, rx: 5, fill: '#1b1d22', 'fill-opacity': 0.82, stroke: '#ffffff', 'stroke-opacity': 0.45, 'stroke-width': 1 }));
    const cx = bx + bw / 2, cy = by + bh / 2;
    const chev = (ox) => 'M ' + (cx - 3 + ox) + ' ' + (cy - 5) + ' L ' + (cx + 3 + ox) + ' ' + cy + ' L ' + (cx - 3 + ox) + ' ' + (cy + 5);
    grp.appendChild(el('path', { d: chev(-2.5) + ' ' + chev(2.5), fill: 'none', stroke: '#ffffff', 'stroke-opacity': 0.9, 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    const ttl = el('title', {}); ttl.textContent = 'Jump to now · resume live'; grp.appendChild(ttl);
    grp.addEventListener('click', (ev) => { ev.stopPropagation(); this._jumpToNow(); });
    svg.appendChild(grp);
  }

  // Fill the usage bars from data.usage (Claude /usage rate-limit %). Hidden when absent (not Pro/Max,
  // or nothing reported yet). A window past its resets_at has rolled over → show 0 until the next write.
  _updateUsage(usage) {
    if (!this._usageWrap) return;
    if (!usage || (!usage.fiveHour && !usage.sevenDay)) { this._usageWrap.style.display = 'none'; return; }
    this._usageWrap.style.display = 'flex';
    const nowS = (typeof Date !== 'undefined' && Date.now) ? Math.floor(Date.now() / 1000) : 0;
    const apply = (key, seg, name) => {
      const b = this._usageBars[key]; if (!b) return;
      if (!seg) { b.group.style.display = 'none'; return; }
      b.group.style.display = 'inline-flex';
      const rolled = seg.resetsAt && nowS > seg.resetsAt;            // window reset since the last report
      const pct = rolled ? 0 : seg.pct;
      b.usage.fill.style.width = pct + '%';
      b.usage.fill.style.background = pct >= 90 ? '#c0392b' : (pct >= 70 ? '#e0b020' : '#54B204');
      b.usage.txt.textContent = pct + '%';
      // TIME through the window: 0% at the window start (resets_at − winSec), 100% at the reset.
      let timePct = null;
      if (seg.resetsAt && b.winSec) timePct = Math.max(0, Math.min(100, Math.round((nowS - (seg.resetsAt - b.winSec)) / b.winSec * 100)));
      b.time.row.style.display = (timePct == null) ? 'none' : 'inline-flex';
      if (timePct != null) { b.time.fill.style.width = timePct + '%'; b.time.txt.textContent = timePct + '%'; }
      b.group.setAttribute('title', name + ' — usage ' + pct + '%' + (timePct != null ? ' · ' + timePct + '% through the window' : '') + (seg.resetsAt ? ' · resets in ' + this._fmtReset(seg.resetsAt) : ''));
    };
    apply('fiveHour', usage.fiveHour, 'Session (5h)');
    apply('sevenDay', usage.sevenDay, 'Weekly');
  }
  // Compact "2d 3h 14m" countdown to a reset epoch, for the usage-bar hover title.
  _fmtReset(epoch) {
    const nowS = (typeof Date !== 'undefined' && Date.now) ? Math.floor(Date.now() / 1000) : 0;
    let dt = epoch - nowS; if (dt <= 0) return 'soon';
    const d = Math.floor(dt / 86400); dt -= d * 86400;
    const h = Math.floor(dt / 3600); dt -= h * 3600;
    const m = Math.floor(dt / 60);
    return (d ? d + 'd ' : '') + (h || d ? h + 'h ' : '') + m + 'm';
  }


  fitWindow() {
    let e = this.data.now;
    this.data.messages.forEach((m) => { if (m.sent) e = Math.min(e, m.sent); });
    Object.values(this.data.turns).forEach((ts) => ts.forEach((t) => { if (t.start) e = Math.min(e, t.start); }));
    this._winSec = Math.min(12 * 3600, Math.max(3600, Math.round((this.data.now - e) * 1.15)));
  }

  update(data) {
    if (!data || data.unavailable || !data.sessions) { this.data = data; this.drawMessage(data && data.unavailable ? 'Timeline needs a desktop Obsidian with tmux.' : 'No romp activity.'); return; }
    this.data = data;
    this._reconcilePendingFlags();   // hold an optimistic eye-toggle sticky until THIS push (or a later one) confirms it
    // Live-edge baseline: free-run off a FIXED anchor and re-snap only on a genuine step, so the few-ms
    // poll-arrival jitter no longer hiccups the gliding edge ~1-2px (the user 2026-06-15). See shouldReanchorEdge.
    const _live = this._liveFollowing(), _tMs = perfNow();
    if (shouldReanchorEdge(this._nowBaseSec, this._nowBaseMs, _tMs, data.now, _live, this._wasLive)) {
      this._nowBaseSec = data.now; this._nowBaseMs = _tMs;   // monotonic ms when this data.now was observed
    }
    this._wasLive = _live;
    if (!this.fitted) { this.fitWindow(); this.fitted = true; }
    // first paint with a chat already open → seed the highlight from it (don't override a later local pick)
    if (this.selectedSid == null) { const sid = this._sidForActiveChat(data.activeChat); if (sid) this.selectedSid = sid; }
    // Feed→timeline HOVER from the FILE (timeline-hover.json — the cross-front-end broadcast channel,
    // also read by VS Code trackchanges + the Obsidian vault). data.hover.ids = the subtree's events +
    // delegation messages ([] = cleared). The SAME monotonic nonce rides both this file and the direct
    // setHover push (server.ts pushHover), so gate on it: apply only when it's not OLDER than the last
    // hover we showed — a poll that races a fresh push ties (same nonce, no-op) instead of reverting it,
    // and a stale read (lower nonce) is ignored. nonce absent (old writer) → always apply (today's
    // behavior). A separate transient channel from the click focus (no pan/pulse/open). [[contract with vs_chat]]
    const _hvN = (data.hover && typeof data.hover.nonce === 'number') ? data.hover.nonce : null;
    if (_hvN == null || this._hoverNonce == null || _hvN >= this._hoverNonce) {
      this._hover = (data.hover && data.hover.ids && data.hover.ids.length) ? data.hover : null;
      if (_hvN != null) this._hoverNonce = _hvN;
    }
    // DAG overlay is DERIVED state: re-synced from the current focus file on EVERY poll, so it clears
    // the instant the feed clears/replaces the focus's dag — even when no fresh focusEvent fires (e.g.
    // the double-clicked card is un-highlighted). The nonce-gated focusEvent below only does the JUMP.
    this._dag = this._dagFromFocus(data.focus);
    this._updateUsage(data.usage);   // Claude /usage rate-limit bars in the controls row (HTML, outside the SVG)
    // STILL SNAPSHOT while a tooltip is up (the user 2026-06-13): the data + derived state above are
    // buffered, but DON'T re-lay-out the SVG — a fresh layout (new events, recompressed idle gaps) shifts
    // every x-position = the jump the user saw under the held edge. Keep the last frame; hideTip repaints
    // the buffered data as ONE catch-up. (Also skips the focus-jump + live-tick below — both move the view.)
    if (this.tip && this.tip.classList && this.tip.classList.contains('show')) { this._dirtyWhileTip = true; return; }
    this.draw();
    // feed→timeline locate: a NEW focus nonce (update_feed wrote timeline-focus.json on a card click)
    // → pan/scroll/pulse to that event. Adopt the nonce silently on first load (don't jump to a stale
    // file); only a CHANGE fires. Guarded so the 1s/3s poll re-reading the same file never re-fires.
    if (data.focus && data.focus.nonce != null) {
      if (this._focusNonce === undefined) this._focusNonce = data.focus.nonce;
      else if (data.focus.nonce !== this._focusNonce) { this._focusNonce = data.focus.nonce; this.focusEvent(data.focus); }
    }
    this._startLiveTick();   // re-arm the smooth-advance loop each poll (no-op unless live-following + visible)
  }

  // Direct hover push from the kernel (server.ts pushHover) — the FAST path that skips the
  // timeline-hover.json write → fs.watch → full rebuild that otherwise made modal/chat hover lag
  // behind the (instant, ws-pushed) chat glow. m = {ids: string[]|null, nonce}. The SAME hover also
  // lands in the file (the cross-front-end broadcast), carrying the SAME monotonic nonce — so honor
  // max-nonce: a following data-poll reading the file ties (same nonce, no-op) and any stale/out-of-
  // order push (lower nonce) is ignored. Redraws ONLY (no update()/rebuild). nonce absent → always apply.
  setHover(m) {
    if (!m) return;
    const nonce = (typeof m.nonce === 'number') ? m.nonce : null;
    if (nonce != null && this._hoverNonce != null && nonce < this._hoverNonce) return;   // stale → ignore
    if (nonce != null) this._hoverNonce = nonce;
    this._hover = (m.ids && m.ids.length) ? { ids: m.ids } : null;
    this._scheduleDraw();
  }

  // resolve the chat's active tab {tid,name} to a lane sid: precise by transcript id (a lane's turn
  // carries that tid), else by name. null if no lane matches.
  _sidForActiveChat(ac) {
    if (!ac || !this.data || !this.data.sessions) return null;
    const turns = this.data.turns || {};
    if (ac.tid) {
      for (const s of this.data.sessions) { if ((turns[s.id] || []).some((t) => t.tid === ac.tid)) return s.id; }
    }
    if (ac.name) { const s = this.data.sessions.find((x) => x.name === ac.name); if (s) return s.id; }
    return null;
  }

  // set the single selection highlight + redraw only on a real change.
  _select(sid) { if (sid && this.selectedSid !== sid) { this.selectedSid = sid; this.draw(); } }

  // Reverse hover: a glyph hover tells the host to light the matching feed card + glow the chat turns
  // in [t0,t1] (the host has the receivers; web kernel only — no-op in Obsidian). sid null → clear.
  _emitHover(sid, segIds, t0, t1) {
    try { if (typeof window !== 'undefined' && typeof window.__rompTimelineHover === 'function') window.__rompTimelineHover(sid, segIds, t0, t1); } catch (e) {}
  }

  // The chat published a new active tab (host fs-watches chat-active and pushes this instantly on tab
  // switch). Move the highlight to follow it — but DON'T fire openChat back (that would loop).
  setActiveChat(ac) {
    if (!this.data || !this.data.sessions) return;
    this.data.activeChat = ac || null;
    const sid = this._sidForActiveChat(ac);
    if (sid) this.selectedSid = sid;
    this.draw();
  }

  // ── vertical drag-to-reorder ─────────────────────────────────────────────
  // A row drag reorders the lanes AND writes the new full SID order to the shared session-order.json,
  // which the chat-view tabs read+write too — so dragging a row reorders the tabs and vice-versa.
  // Distinguished from a plain click by a small movement threshold; the lanes shuffle live under the
  // cursor, and the order is persisted on drop (optimistically applied so there's no snap-back).
  _svgY(e) {
    const g = this._geom; if (!g) return 0;
    const rect = this.svg.getBoundingClientRect();
    const scaleY = rect.height ? g.H / rect.height : 1;   // svg user-units per client px
    return (e.clientY - rect.top) * scaleY;
  }
  // One mousedown on a lane; the first real movement decides via dragAxis: horizontal → PAN the plot,
  // vertical → REORDER the lane. A plain click (no movement) falls through to the row's select handler.
  _beginDrag(sid, e) {
    if (e.button !== 0 || !this._geom) return;                 // left button, need geometry
    const order = (this._vis || []).map((s) => s.id);
    const fromIdx = order.indexOf(sid);
    if (fromIdx < 0) return;
    this._suppressClick = false;
    this._drag = {
      sid, fromIdx, order, toIdx: fromIdx, moved: false, mode: null,
      startX: e.clientX, startY: e.clientY,                    // client coords → axis decision
      panOff: this.offSec(), panWin: this.winSec(),           // pan baseline (constant scale from gesture start)
    };
    this._onDragMove = (ev) => this._dragMove(ev);
    this._onDragUp = (ev) => this._dragUp(ev);
    window.addEventListener('mousemove', this._onDragMove, true);
    window.addEventListener('mouseup', this._onDragUp, true);
    e.preventDefault();
  }
  _dragMove(ev) {
    const d = this._drag; if (!d) return;
    if (d.mode == null) {
      d.mode = dragAxis(ev.clientX - d.startX, ev.clientY - d.startY);
      if (d.mode == null) return;                              // below threshold → still a potential click
      d.moved = true; this.svg.style.cursor = 'grabbing';
      if (d.mode === 'row') this.selectedSid = d.sid;
    }
    if (d.mode === 'pan') this._panDragMove(ev); else this._rowDragMove(ev);
  }
  // Horizontal click-drag → pan at a CONSTANT compressed-sec-per-px scale (same as onWheel's pan branch),
  // measured from the gesture start. BREAKS pin + 🔒lock so you can drag away from now freely.
  _panDragMove(ev) {
    const d = this._drag, g = this._geom; if (!d || !g || !g.plotW) return;
    const rect = this.svg.getBoundingClientRect();
    const scaleX = rect.width ? g.W / rect.width : 1;
    const dt = (ev.clientX - d.startX) * scaleX * (d.panWin / g.plotW);
    this._offSec = Math.max(0, Math.min(MAX_OFFSET, d.panOff - dt));
    this._setLock(false);                                      // a drag turns OFF 🔒 — no snap-back to now
    this._pinned = false;
    this._offDirty = true;
    this._suppressClick = true;
    this._scheduleDraw();
    ev.preventDefault();
  }
  _rowDragMove(ev) {
    const d = this._drag; if (!d) return;
    const n = d.order.length, y = this._svgY(ev);
    let toIdx = Math.round((y - this._geom.top - LANE_GAP / 2) / LANE_GAP);
    toIdx = Math.max(0, Math.min(n - 1, toIdx));
    d.toIdx = toIdx;
    // rebuild from the ORIGINAL order each move (no drift): pull the dragged sid, splice at the target band.
    const base = d.order.filter((id) => id !== d.sid);
    base.splice(toIdx, 0, d.sid);
    this._dragOrder = base;
    this._scheduleDraw();
    ev.preventDefault();
  }
  _dragUp(ev) {
    const d = this._drag;
    window.removeEventListener('mousemove', this._onDragMove, true);
    window.removeEventListener('mouseup', this._onDragUp, true);
    this._onDragMove = this._onDragUp = null;
    this._drag = null; this.svg.style.cursor = '';
    if (!d || !d.moved) { this._dragOrder = null; return; }    // no movement → a click; let select fire
    if (d.mode === 'pan') {
      this._markOffsetGesture();                               // re-pin if dragged back to the now-edge
      try { localStorage.setItem(this.OSTORE, String(Math.round(this._offSec))); } catch (e) {}
      this.draw();
      this._startLiveTick();                                   // re-pinned at the edge → resume smooth advance
      ev.preventDefault();
      return;
    }
    this._suppressClick = true;
    const visOrder = this._dragOrder || d.order;
    this._dragOrder = null;
    const full = this._mergeVisibleOrder(visOrder);            // full SID list with only the visible lanes permuted
    this._applyOrderToData(full);                              // optimistic in-place reorder → no snap-back pre-poll
    this._persistOrder(full);                                  // write the shared file (tabs watch it)
    this.draw();
    ev.preventDefault();
  }
  // Map the new VISIBLE order back onto the full session list, keeping non-visible (out-of-window/idle)
  // sessions in their existing absolute slots — only the visible lanes get permuted into their new order.
  _mergeVisibleOrder(visOrder) {
    const oldIds = (this.data && this.data.sessions || []).map((s) => s.id);
    const visSet = new Set(visOrder);
    let vi = 0;
    return oldIds.map((id) => visSet.has(id) ? visOrder[vi++] : id);
  }
  _applyOrderToData(full) {
    if (!this.data || !this.data.sessions) return;
    const oidx = new Map(full.map((id, i) => [id, i]));
    this.data.sessions.sort((a, b) => ((oidx.has(a.id) ? oidx.get(a.id) : Infinity) - (oidx.has(b.id) ? oidx.get(b.id) : Infinity)));
  }
  // Persist the full SID order to ~/.local/state/romp/session-order.json. VS Code webview has no Node →
  // hand it to the extension host (which writes atomically); Obsidian desktop writes directly (tmp+rename).
  _persistOrder(order) {
    try {
      if (typeof window !== 'undefined' && typeof window.__rompTimelineWriteOrder === 'function') {
        window.__rompTimelineWriteOrder(order); return;
      }
      const fs = require('fs'), path = require('path'), os = require('os');
      const base = process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state');
      const f = path.join(base, 'romp', 'session-order.json'), tmp = f + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(order));
      fs.renameSync(tmp, f);
    } catch (e) { /* no host hook + no Node → can't persist; the drag still reordered visually until next poll */ }
  }

  // ── feed→timeline locate ────────────────────────────────────────────────
  // Driven by timeline-focus.json (update_feed writes {id,sid,t,nonce} on a feed-card click; the data
  // builder surfaces it as data.focus). Pan the time window to the event (if off-screen), highlight +
  // scroll its lane into view, and pulse a ring at (time, lane).
  // Resolve the focus `sid` (update_feed writes the event's transcript fsid) to the lane that actually
  // draws it. Usually fsid === the lane's romp SID; but a FORKED session is merged into ONE lane keyed
  // by the root SID, with the fork's fsid surfacing as a turn's `tid` — so fall back to a tid match.
  _laneForFocusSid(sid) {
    if (!sid || !this.data || !this.data.sessions) return sid;
    if (this.data.sessions.some((s) => s.id === sid)) return sid;            // direct lane id
    const turns = this.data.turns || {};
    for (const s of this.data.sessions) { if ((turns[s.id] || []).some((t) => t.tid === sid)) return s.id; }  // fork fsid → merged lane
    return sid;
  }
  // Exact event id-join (the canonical key — romp-events `e.id` == the feed itemId, now on each turn):
  // find the turn whose id matches and return its lane + exact start. Beats sid+t (no time drift, and
  // it lands on whatever lane actually draws it, so the fork-merge case is handled for free).
  _focusTargetById(id) {
    if (!id || !this.data || !this.data.sessions) return null;
    const turns = this.data.turns || {};
    for (const s of this.data.sessions) {
      for (const t of (turns[s.id] || [])) { if (t.id === id) return { sid: s.id, t: t.start, end: t.end, tid: t.tid, uuid: t.uuid, workUuid: t.workUuid, replyUuid: t.replyUuid, src: t.src }; }
    }
    return null;
  }
  // Broken-axis: a GLOBAL real→compressed time map. Long idle gaps (≥GAP_MIN, no work on any lane)
  // each collapse to `gapCT` compressed-seconds (one tick interval); active time maps 1:1. Because the
  // gap set is GLOBAL (not window-clipped) and gapCT is fixed for a given zoom, the map is STABLE while
  // panning — so x() only rescales on zoom, never on pan (no edge-snap jank). Returns {compress(t),
  // decompress(c), gaps:[{ra,rb}]} or null (no qualifying gaps → caller uses identity).
  _buildCompressMap(turns, gapCT, now) {
    const iv = [];
    for (const sid in turns) for (const t of (turns[sid] || [])) {
      const s0 = (t.proc != null ? t.proc : t.start), a = s0, b = Math.max(t.end || s0, s0);
      if (b > a) iv.push([a, b]);
    }
    if (!iv.length) return null;
    iv.sort((p, q) => p[0] - q[0]);
    const merged = [];
    for (const [a, b] of iv) { const last = merged[merged.length - 1]; if (last && a <= last[1] + 1) last[1] = Math.max(last[1], b); else merged.push([a, b]); }
    const gaps = idleGaps(merged, gapCT, now);                // [{ra, rb, trailing}], collapse-worthy idle stretches
    if (!gaps.length) return null;
    const segs = [];                                          // real [ra,rb] → compressed [ca,cb]
    let curC = gaps[0].ra;
    for (let i = 0; i < gaps.length; i++) {
      const ga = gaps[i].ra, gb = gaps[i].rb, D = gb - ga, ct = Math.min(D, gapCT);
      segs.push({ ra: ga, rb: gb, ca: curC, cb: curC + ct }); curC += ct;
      if (i + 1 < gaps.length) { const nga = gaps[i + 1].ra, len = nga - gb; segs.push({ ra: gb, rb: nga, ca: curC, cb: curC + len }); curC += len; }
    }
    const first = segs[0], last = segs[segs.length - 1];
    const compress = (t) => {                                 // identity outside the gap range, slope 1
      if (t <= first.ra) return first.ca + (t - first.ra);
      if (t >= last.rb) return last.cb + (t - last.rb);
      for (const s of segs) if (t <= s.rb) { const f = s.rb > s.ra ? (t - s.ra) / (s.rb - s.ra) : 0; return s.ca + f * (s.cb - s.ca); }
      return last.cb + (t - last.rb);
    };
    const decompress = (c) => {
      if (c <= first.ca) return first.ra + (c - first.ca);
      if (c >= last.cb) return last.rb + (c - last.cb);
      for (const s of segs) if (c <= s.cb) { const f = s.cb > s.ca ? (c - s.ca) / (s.cb - s.ca) : 0; return s.ra + f * (s.rb - s.ra); }
      return last.rb + (c - last.cb);
    };
    return { compress, decompress, gaps };
  }
  // broken-axis marker for one collapsed gap: just a vertical zigzag squiggle (no band), framed by two
  // boundary gridlines labelled with the time work STOPPED (left) and RESUMED (right).
  // showLeft/showRight (default true) gate each boundary gridline+clock: a gap that STRADDLES a window
  // edge (its start before t0, or end past t1) has that boundary clamped to the plot edge, so we suppress
  // its label/gridline rather than draw it into the gutter (over the battery column) or off the plot.
  // placeLabel (the caller's axis-row occupancy fn) gates each boundary CLOCK: when it would overlap a
  // label already on the row (a regular tick, or another gap's clock) the text is dropped — the
  // gridline and squiggle still draw, so the break stays visible without doubled-up labels.
  _drawGapBreak(svg, x0, x1, ra, rb, top, axisY, showLeft, showRight, placeLabel) {
    const ends = [];
    if (showLeft !== false) ends.push([x0, ra, 'end', -2]);
    if (showRight !== false) ends.push([x1, rb, 'start', 2]);
    for (const e of ends) {
      svg.appendChild(el('line', { x1: e[0], y1: top, x2: e[0], y2: axisY, stroke: '#ffffff20', 'stroke-width': 1, 'pointer-events': 'none' }));
      const s = clock(e[1]), lx = e[0] + e[3];
      this._mc.font = '9px ' + FONT;
      const w = this._mc.measureText(s).width;
      if (placeLabel && !placeLabel(e[2] === 'end' ? lx - w : lx, e[2] === 'end' ? lx : lx + w)) continue;
      const tx = el('text', { x: lx, y: axisY + 14, 'text-anchor': e[2], fill: 'var(--text-muted)', 'font-size': 9, 'pointer-events': 'none' }); tx.textContent = s; svg.appendChild(tx);
    }
    const cx = (x0 + x1) / 2, amp = 3, seg = 7;
    // SPAN label (the user 2026-06-17): a multi-day collapsed gap shows its concise duration ("2 days",
    // "1 week") centered at the TOP of the break — a different row from the boundary clocks below the axis,
    // so it never collides — making clear how long the gap is. Sub-day gaps draw the squiggle full-height.
    const span = rb - ra, hasSpan = span >= 86400, sqTop = top + (hasSpan ? 14 : 0);
    if (hasSpan) {
      const tx = el('text', { x: cx, y: top + 10, 'text-anchor': 'middle', fill: 'var(--text-muted)', 'font-size': 9, 'font-weight': 600, 'pointer-events': 'none' });
      tx.textContent = fmtSpan(span); svg.appendChild(tx);
    }
    let d = 'M ' + cx + ' ' + sqTop, yy = sqTop, k = 0;
    while (yy < axisY) { const ny = Math.min(yy + seg, axisY); d += ' L ' + (cx + (k % 2 ? amp : -amp)) + ' ' + ny; yy = ny; k++; }
    svg.appendChild(el('path', { d, fill: 'none', stroke: '#ffffff', 'stroke-width': 1.4, opacity: 0.5, 'pointer-events': 'none' }));
  }
  // Build the DAG overlay sets from a focus payload's dag (or null when absent/empty). The overlay is
  // synced from this in update() every poll, so it tracks the focus file's CURRENT dag (clears on
  // clear/replace) without needing a fresh focusEvent.
  _dagFromFocus(f) {
    if (!f || !f.dag) return null;
    const ev = f.dag.events || [], ms = f.dag.msgs || [];
    if (!ev.length && !ms.length) return null;
    return { events: new Set(ev), msgs: new Set(ms) };
  }
  // Pan (ONLY) so the focus time `t` sits ~mid-window when it's currently off-screen (compressed-time
  // check, gap-aware). No pulse/open — shared by the full focusEvent jump and the paint-only dag focus.
  // Returns true if it actually panned (caller redraws).
  _panToTime(t) {
    if (t == null) return false;
    const g = this._geom, compress = (g && g.compress) ? g.compress : ((x) => x);
    const win = this.winSec(), cNow = compress(this.data.now), ct = compress(t);
    const cT1 = cNow - this.offSec(), cT0 = cT1 - win;
    // 🔒 locked to now: never pan off the live edge — ZOOM OUT instead. Widen the window (right
    // edge stays at now) until the target is on-screen, sitting ~mid-window, so the right half
    // spans target → now. Already-visible targets change nothing.
    if (this._lockNow) {
      if (ct >= cT0 && ct <= cT1 && this.offSec() === 0) return false;
      this._winSec = Math.max(MIN_W, Math.min(MAX_W, 2 * Math.max(1, cNow - ct)));
      this._offSec = 0; this._offDirty = true; this._pinned = true;
      try { localStorage.setItem(this.WSTORE, String(this.winSec())); } catch (e) {}
      try { localStorage.setItem(this.OSTORE, '0'); } catch (e) {}
      return true;
    }
    if (ct < cT0 || ct > cT1) {                        // off-screen in time → pan so t sits ~mid-window
      this._offSec = Math.max(0, Math.min(MAX_OFFSET, cNow - ct - win * 0.5));
      this._markOffsetGesture();                       // hold at the navigated target (don't creep)
      try { localStorage.setItem(this.OSTORE, String(Math.round(this._offSec))); } catch (e) {}
      return true;
    }
    return false;
  }
  focusEvent(f) {
    if (!f || !this.data || !this.data.sessions) return;
    // The DAG overlay (this._dag) is synced every poll in update() from the focus file — so a clear or
    // replace takes effect even without a fresh focusEvent. focusEvent only does the one-shot JUMP.
    // locate:false is a PAINT-only signal. the user's ruling (2026-06-10): a feed-card HOVER (or single click)
    // must only HIGHLIGHT the journey on the timeline (paint, already done by update()) and NEVER jump/pan
    // — only a DOUBLE-CLICK jumps. The double-click carries jump:true, so even on a paint focus we PAN to
    // bring the DAG on-screen (pan only — no chat-open, that's first-party in romp-chat-view ≥v0.4.171; no
    // pulse). Plain hover/single-click omit jump → just paint, no pan.
    if (f.locate === false) {
      if (f.jump) {
        const tb = f.id ? this._focusTargetById(f.id) : null;
        if (this._panToTime(tb ? tb.t : f.t)) this.draw();
      }
      return;
    }
    const byId = f.id ? this._focusTargetById(f.id) : null;     // prefer the exact id-join
    // Each work period has TWO anchors: the prompt START DOT (uuid, the boundary line) and the WORK BAR
    // (workUuid, the period's reply/response). The feed now sends an explicit CLICK-INTENT hint, because
    // kind-inference can't see intent: a reply filed under a direct ask lands ON the typed turn, so a
    // work-row click can carry a typed-turn id. anchor='work' → flash the BAR + open workUuid (even on a
    // typed turn); anchor='prompt' → the start dot. Absent (old payloads) → fall back to kind-inference:
    // typed/queued/enqueue = the user's prompt (dot); drain/absorbed/decision = peer/queue work (bar). This
    // is the fix for the user landing on "an edit" or "my own message" (the start glyph of a drain turn is a
    // tool-use boundary or the coincident message-arrival dot), never the work.
    const kindWork = !!(byId && byId.src && byId.src !== 'typed' && byId.src !== 'queued' && byId.src !== 'enqueue');
    const onWork = !!byId && (f.anchor === 'work' ? true : (f.anchor === 'prompt' ? false : kindWork));
    const sid = byId ? byId.sid : this._laneForFocusSid(f.sid);  // else fall back to sid (fork-aware)
    const t = byId ? byId.t : f.t;                               // else the written time (turn START)
    this._panToTime(t);                                          // pan so the target sits ~mid-window if off-screen
    if (sid) this.selectedSid = sid;
    this.draw();                                     // redraw with the new pan + selection (refreshes _geom/_vis)
    this._pulseFocus(sid, t, onWork ? byId : null);  // reply event → flash the BAR; prompt → ring on the dot
    // Land the chat half too. A reply event opens its READABLE reply line (replyUuid = last assistant
    // line with text, NOT the first which is usually a thinking block → workUuid/uuid fallbacks); a typed
    // prompt opens its prompt line (uuid). anchorT (the turn/event time) rides along belt-and-braces so
    // the chat scrolls by time if the uuid anchor misses. On a _focusTargetById MISS (event outside the
    // loaded window) we STILL open the lane by time (anchorT=f.t) rather than silently doing nothing.
    if (byId && byId.tid) {
      const a = onWork ? workAnchorOf(byId) : byId.uuid;
      // !onWork = we resolved to the boundary uuid = PROMPT-intent → anchorKind=user (kind-safe fallback)
      this.openChat(byId.tid, a, false, false, byId.t, onWork ? undefined : 'user');
    } else if (sid && f.t != null) {
      const lane = this.data.sessions.find((x) => x.id === sid);
      // byId missed → pure time fallback; a 'prompt'-anchored focus is still prompt-intent
      this.openChat((lane && this._laneTid(lane)) || sid, undefined, false, false, f.t, f.anchor === 'prompt' ? 'user' : undefined);
    }
  }
  // Flash the focused event + scroll it into view. Called AFTER draw() so _geom (time→x) and _vis
  // (lane index) are current. Two shapes: a prompt focus pulses a RING on its start dot; a reply/work
  // focus (workTurn given) pulses an OUTLINE over the whole work BAR (start→end) — so the confirm lands
  // on the work, not on a prompt/message glyph. (A poll redraw may clear it early — that's fine.)
  _pulseFocus(sid, t, workTurn) {
    const g = this._geom; if (!g) return;
    const i = (this._vis || []).findIndex((s) => s.id === sid);
    if (i < 0) return;
    const y = g.top + i * LANE_GAP + LANE_GAP * 0.5;
    const X = (tt) => g.ml + ((g.compress ? g.compress(tt) : tt) - g.cT0) / g.winSec * g.plotW;   // compressed-time x
    const startMs = (typeof performance !== 'undefined' && performance.now) ? performance.now() : null;
    const DUR = 1400;
    if (workTurn) {
      // bar outline: span the work period, pulse stroke-width + fade
      const xs = X(workTurn.t), xe = X(workTurn.end != null && workTurn.end > workTurn.t ? workTurn.end : workTurn.t);
      const bw = Math.max(6, xe - xs), h = BAR_H + 6;
      const box = el('rect', { x: xs - 3, y: y - h / 2, width: bw + 6, height: h, rx: h / 2, fill: 'none', stroke: '#ffd166', 'stroke-width': 2.5, opacity: 0.95 });
      this.svg.appendChild(box);
      try { box.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) {}
      const step = (nowMs) => {
        if (!box.parentNode) return;
        const p = startMs != null ? Math.min(1, (nowMs - startMs) / DUR) : 1;
        const ph = (p * 2) % 1;                        // two pulses
        box.setAttribute('stroke-width', String(2.5 + ph * 2.5));
        box.setAttribute('opacity', String(0.95 * (1 - ph)));
        if (p >= 1) { box.remove(); return; }
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      return;
    }
    const cx = X(t);
    const ring = el('circle', { cx, cy: y, r: 5, fill: 'none', stroke: '#ffd166', 'stroke-width': 2.5, opacity: 0.95 });
    this.svg.appendChild(ring);
    try { ring.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) {}
    const step = (nowMs) => {
      if (!ring.parentNode) return;                  // a poll redraw cleared it → stop
      const p = startMs != null ? Math.min(1, (nowMs - startMs) / DUR) : 1;
      const ph = (p * 2) % 1;                         // two expanding pulses
      ring.setAttribute('r', String(5 + ph * 16));
      ring.setAttribute('opacity', String(0.95 * (1 - ph)));
      if (p >= 1) { ring.remove(); return; }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  drawMessage(msg) {
    while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
    this.svg.setAttribute('height', '60');
    const t = el('text', { x: 14, y: 34, fill: 'var(--text-muted)', 'font-size': 13 }); t.textContent = msg; this.svg.appendChild(t);
  }

  // FREEZE-ON-HOVER (the user 2026-06-12): while a glyph tooltip is shown, pause live-follow so the
  // content stops sliding out from under the cursor. Only when we were PINNED (following now) and not
  // 🔒-locked — a user who has panned into history is already frozen, and the lock means "always now".
  // We hold at the current now (unpin to a fixed _holdReal); hideTip resumes. The poll redraws against
  // the hold, so the now-edge stops advancing — no continuous slide to fight.
  showTip(html, ev) {
    // bridge a glyph→glyph hover handoff (e.g. work-bar → its prompt dot): cancel any pending unfreeze
    // so the now-edge doesn't resume in the gap and slip the next glyph out from under the cursor (the
    // user 2026-06-15). An already-frozen state carries straight into the new tooltip.
    if (this._unfreezeTimer) { clearTimeout(this._unfreezeTimer); this._unfreezeTimer = null; }
    this.tip.innerHTML = html; this.tip.classList.add('show'); this._tipOwner = (ev && ev.currentTarget) || null; this.moveTip(ev);
    // Freeze the live edge while hovering, so the user can actually read a bar (the user 2026-06-13).
    // Freeze whenever we're following the live edge — pinned OR 🔒locked (lock no longer blocks it).
    // Do NOT mark _offDirty: that makes the next poll take the offset verbatim (off=0 → edge jumps to the
    // new now); leaving it false lets draw()'s hold branch pin the edge at _holdReal (the hover instant).
    if ((this._pinned || this._lockNow) && this.data) {
      this._frozeFromPin = true; this._pinned = false; this._holdReal = this.data.now; this._offDirty = false;
    }
  }
  moveTip(ev) { const pad = 14; let lx = ev.clientX + pad, ly = ev.clientY + pad; const r = this.tip.getBoundingClientRect();
    if (lx + r.width > innerWidth) lx = ev.clientX - r.width - pad; if (ly + r.height > innerHeight) ly = ev.clientY - r.height - pad;
    this.tip.style.left = lx + 'px'; this.tip.style.top = ly + 'px'; }
  hideTip() {
    this.tip.classList.remove('show'); this._tipOwner = null;   // tooltip hides at once…
    // …but DEFER the live-follow resume a beat: a quick move onto another glyph (bar→dot) fires its
    // showTip, which cancels this timer, so the now-edge never resumes/jumps mid-handoff. If nothing
    // grabs it within the grace window, the timer resumes live-follow + snaps to now (the catch-up).
    if (this._unfreezeTimer) return;
    this._unfreezeTimer = setTimeout(() => {
      this._unfreezeTimer = null;
      const dirty = this._dirtyWhileTip; this._dirtyWhileTip = false;
      if (this._frozeFromPin) { this._frozeFromPin = false; this._jumpToNow(); }
      else if (dirty && this.data) this.draw();
    }, 40);
  }

  // Deep-link a click on a timeline item into the romp Chat View VS Code extension,
  // focusing that session's tab and scrolling to the EXACT transcript line. Contract
  // (agreed with vs_chat): open vscode://romp.romp-chat-view/open?session=<TRANSCRIPT_ID>&anchor=<LINE_UUID>.
  //   session = the PER-EVENT source transcript basename (a lane can span multiple
  //             transcripts over resume/fork, so this is the clicked item's tid, NOT the lane id).
  //   anchor  = the uuid of the conversational JSONL line to scroll to; OMITTED → the chat opens the
  //             tab and scrolls to the BOTTOM (latest). Lane-level selects (row/bar/awaiting/↑↓) omit it.
  //   preserveFocus = true → append &focus=0 so the chat reveals WITHOUT stealing focus (used by lane
  //                   selects/↑↓ preview so you can keep arrowing); a dot/line click omits it → focus the chat.
  openChat(session, anchor, preserveFocus, compose, anchorT, anchorKind) {
    if (!session) return;                       // need a transcript/session to open
    let url = 'vscode://romp.romp-chat-view/open?session=' + encodeURIComponent(session);
    if (anchor) url += '&anchor=' + encodeURIComponent(anchor);   // uuid anchor (wins); omit → use anchorT / bottom
    // anchorT (epoch seconds): the chat view scrolls to the nearest turn by time (skipping thinking
    // blocks) when the uuid anchor misses — so a click NEVER silently no-ops. Sent belt-and-braces.
    if (anchorT != null && isFinite(anchorT)) url += '&anchorT=' + Math.round(anchorT);
    // anchorKind=user (PROMPT-intent opens only): when the uuid anchor misses and the open falls back
    // to time, the chat-view (≥v0.4.157) restricts the nearest-readable-turn search to the USER's own
    // turns — so a prompt-intent click can degrade in PRECISION but never land on an assistant answer
    // (the user's rule: a fallback may degrade landing precision, never landing KIND). Omitted = any turn.
    if (anchorKind) url += '&anchorKind=' + encodeURIComponent(anchorKind);
    if (preserveFocus) url += '&focus=0';
    if (compose) url += '&compose=1';           // Enter → put the cursor in the chat's message box for this session
    try {
      // VS Code webview surface (vscode-trackchanges): no Node here, so hand the uri to the
      // extension host, which opens it via vscode.env.openExternal. Host injects this hook.
      if (typeof window !== 'undefined' && typeof window.__rompTimelineOpenExternal === 'function') {
        window.__rompTimelineOpenExternal(url); return;
      }
      // Obsidian desktop surface: shell out via Node.
      require('child_process').execFile('open', [url]);
    } catch (e) { /* no host hook + no shell → silently ignore */ }
  }

  // Click the context battery → send `/compact` to that session's terminal. VS Code: hand the session
  // name to the extension host (no Node in the webview); Obsidian: shell tmux directly. Types the slash
  // command literally then submits it. (Targets the tmux session by name, like romp-postal's inject.)
  _compactSession(name) {
    if (!name) return;
    try {
      if (typeof window !== 'undefined' && typeof window.__rompTimelineCompact === 'function') {
        window.__rompTimelineCompact(name); return;
      }
      const cp = require('child_process'), tmux = this._tmuxPath();
      cp.execFile(tmux, ['send-keys', '-t', name, '-l', '/compact'], (err) => {
        if (!err) cp.execFile(tmux, ['send-keys', '-t', name, 'Enter']);
      });
    } catch (e) { /* no host hook + no Node → can't send */ }
  }
  // Inject a slash command into a session's pane (the model/effort pickers). VS Code surface: hand it
  // to the host hook if present; Obsidian: shell tmux. We BRACKETED-PASTE the command (set-buffer +
  // paste-buffer -p) rather than send-keys -l, then submit with a delayed Enter — mirroring the
  // chat-view's sendToSession. A literal type would feed "/model …" to Claude Code's slash-command
  // AUTOCOMPLETE char-by-char and an immediate Enter would race the TUI; a bracketed paste lands the
  // whole string atomically (no autocomplete), and the 250ms gap lets the paste arrive before Enter.
  //
  // confirm=true → send a SECOND Enter after the submit. /model doesn't switch on submit: it opens a
  // "Switch model?" picker (cursor pre-seated on "Yes, switch …") that fires no hook and waits — so the
  // one Enter only OPENS the dialog and the model never changes. The extra Enter accepts the default
  // "Yes". /effort and /compact apply directly (no cache-invalidation confirmation), so they don't pass
  // it. The extra Enter is harmless even if a build skips the dialog (an empty composer submit is a no-op).
  _sendCommand(name, cmd, confirm) {
    if (!name || !cmd) return;
    try {
      if (typeof window !== 'undefined' && typeof window.__rompTimelineSendCommand === 'function') {
        window.__rompTimelineSendCommand(name, cmd); return;
      }
      const cp = require('child_process'), tmux = this._tmuxPath();
      const env = Object.assign({}, process.env, { LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', LC_CTYPE: 'en_US.UTF-8' });
      const run = (args, cb) => cp.execFile(tmux, args, { timeout: 4000, encoding: 'utf8', env }, (err, out) => { if (cb) cb(err, out); });
      const enter = () => run(['send-keys', '-t', name, 'Enter']);
      const BUF = 'romp-timeline';
      const submit = () => { enter(); if (confirm) setTimeout(enter, 600); };   // 2nd Enter → accept "Switch model? Yes"
      const paste = () => run(['set-buffer', '-b', BUF, cmd], () =>
        run(['paste-buffer', '-b', BUF, '-d', '-p', '-t', name], () => setTimeout(submit, 250)));
      // exit copy-mode first if the pane is scrolled, so the paste + Enter actually land
      run(['display-message', '-p', '-t', name, '#{pane_in_mode}'], (err, out) => {
        if (!err && String(out || '').trim() === '1') run(['send-keys', '-t', name, '-X', 'cancel'], paste);
        else paste();
      });
    } catch (e) { /* no host hook + no Node → can't send */ }
  }

  _closeMetaMenu() { if (this._metaMenu) { this._metaMenu.remove(); this._metaMenu = null; } }

  // Open the model/effort drop-down anchored under the clicked label. Re-clicking the same word's
  // caret toggles it shut. Refused while the lane is AWAITING a prompt — the pane's keyboard belongs to
  // the picker, so a pasted "/model …" + Enter would answer it instead (chat-view guards the same way).
  _openMetaMenu(kind, s, anchorEl) {
    const reopen = this._metaMenu && this._metaMenu._kind === kind && this._metaMenu._sid === s.id;
    this._closeMetaMenu();
    if (reopen) return;
    if (s.state === 'awaiting' || s.state === 'permission') return;
    // Styled inline (NOT via a CSS class): injectStyles() guards on an existing <style> id, so a CSS
    // rule added later never lands after a plugin reload — only a full restart. Inline always applies.
    const menu = document.body.createDiv();
    menu.setAttribute('style', 'position:fixed;z-index:1001;min-width:96px;padding:4px;background:#1c2430;border:1px solid #ffffff1f;border-radius:8px;box-shadow:0 8px 24px #00000066;font-size:12px;color:#e6edf3;user-select:none;');
    menu._kind = kind; menu._sid = s.id;
    for (const c of (kind === 'model' ? MODEL_CHOICES : EFFORT_CHOICES)) {
      const cur = isCurrentMeta(kind, s, c.value);
      const item = menu.createDiv({ text: c.label });
      item.setAttribute('style', 'padding:4px 22px 4px 9px;border-radius:5px;cursor:pointer;position:relative;white-space:nowrap;' + (cur ? 'color:#54B204;' : ''));
      if (cur) { const ck = item.createSpan({ text: '✓' }); ck.setAttribute('style', 'position:absolute;right:8px;'); }
      item.addEventListener('mouseenter', () => { item.style.background = '#ffffff14'; });
      item.addEventListener('mouseleave', () => { item.style.background = 'transparent'; });
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this._sendCommand(s.name, '/' + kind + ' ' + c.value, kind === 'model');
        const now = (typeof Date !== 'undefined' && Date.now) ? Date.now() : 0;
        this._metaPending[s.id + ':' + kind] = { was: (kind === 'model' ? s.model : s.effort) || '', until: now + 20000 };
        this._closeMetaMenu();
        this.draw();
      });
    }
    const r = anchorEl.getBoundingClientRect();
    // clamp to the viewport so a right-edge lane's menu stays on-screen
    const left = Math.min(Math.round(r.left), (window.innerWidth || 9999) - 140);
    menu.style.left = Math.max(6, left) + 'px';
    menu.style.top = Math.round(r.bottom + 4) + 'px';
    this._metaMenu = menu;
  }

  // (The old per-lane settings drop-down + its flag list were removed (the user 2026-06-22): with a single
  // flag, the lane EYE toggles hideFromFeed DIRECTLY on click — no menu. See the render below; the flag is
  // still persisted by _setSessionFlag.)

  // Optimistic per-session view flags (the eye → hideFromFeed). A click flips the flag locally AND fires
  // _setSessionFlag, but the kernel's confirming rebuild takes ~1s and ANY routine push that lands in that
  // window carries the OLD value — wholesale-replacing this.data would REVERT the eye (a visible flicker, the
  // session "un-hiding" for a beat before settling — the user 2026-06-22). So hold each clicked value in
  // _pendingFlags and re-apply it onto every incoming push until the kernel's value MATCHES (confirmed → drop
  // it). Net: click → it changes → it stays, never bounces. Called from update() right after this.data = data.
  _reconcilePendingFlags() {
    const pend = this._pendingFlags; if (!pend) return;
    for (const s of (this.data && this.data.sessions) || []) {
      const p = pend[s.id]; if (!p) continue;
      for (const flag of Object.keys(p)) {
        if (s[flag] === p[flag]) delete p[flag];   // the kernel now agrees → stop overriding this flag
        else s[flag] = p[flag];                    // not yet confirmed → keep the optimistic value sticky
      }
      if (!Object.keys(p).length) delete pend[s.id];
    }
  }

  // Persist a per-session flag. Web dashboard: the host WS hook (→ kernel setSessionFlag → rebuild feed).
  // Obsidian/headless fallback: write the same session-flags.json the kernel's build_feed reads.
  _setSessionFlag(s, flag, value) {
    try {
      if (typeof window !== 'undefined' && typeof window.__rompTimelineSetFlag === 'function') {
        window.__rompTimelineSetFlag(s.id, flag, value); return;
      }
      const fs = require('fs'), os = require('os'), path = require('path');
      const dir = path.join(os.homedir(), '.local', 'state', 'romp');
      const fp = path.join(dir, 'session-flags.json');
      let cur = {};
      try { cur = JSON.parse(fs.readFileSync(fp, 'utf8')) || {}; } catch (e) {}
      const f = (cur[s.id] && typeof cur[s.id] === 'object') ? cur[s.id] : {};
      if (value) f[flag] = true; else delete f[flag];
      if (Object.keys(f).length) cur[s.id] = f; else delete cur[s.id];
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(fp, JSON.stringify(cur));
    } catch (e) { /* no host hook + no Node fs → can't persist */ }
  }

  _tmuxPath() {
    if (this._tmux) return this._tmux;
    this._tmux = 'tmux';
    try { const fs = require('fs'); for (const p of ['/opt/homebrew/bin/tmux', '/usr/local/bin/tmux', '/usr/bin/tmux', '/bin/tmux']) if (fs.existsSync(p)) { this._tmux = p; break; } } catch (e) {}
    return this._tmux;
  }

  // Items that aren't themselves a conversational line (awaiting/compaction spans, message
  // connectors) borrow the deep-link anchor of the session's nearest work period to `t`.
  nearestTurnAnchor(sid, t) {
    const ts = (this.data && this.data.turns && this.data.turns[sid]) || [];
    let best = null, bestd = Infinity;
    for (const x of ts) {
      if (x.src === 'enqueue') continue;
      const d = (t >= x.start && t <= x.end) ? 0 : Math.min(Math.abs(t - x.start), Math.abs(t - x.end));
      if (d < bestd) { bestd = d; best = x; }
    }
    return best;   // {tid,uuid,...} or null → openChat no-ops on a null anchor
  }

  draw() {
    const data = this.data; if (!data || !data.sessions) return;
    const svg = this.svg, M = this.M;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    // candy-cane hatch for AWAITING spans: diagonal white stripes overlaid on the bar
    const defs = el('defs', {});
    const pat = el('pattern', { id: 'vault-await-hatch', patternUnits: 'userSpaceOnUse', width: 7, height: 7, patternTransform: 'rotate(45)' });
    pat.appendChild(el('line', { x1: 0, y1: 0, x2: 0, y2: 7, stroke: '#ffffff', 'stroke-width': 4, opacity: 0.78 }));
    defs.appendChild(pat);
    // CROSS-hatch (X-weave) for CONTEXT COMPACTION spans — distinct from the single-diagonal candy-cane;
    // a cool cyan reads as "compressed". Two perpendicular line sets.
    const cpat = el('pattern', { id: 'vault-compact-hatch', patternUnits: 'userSpaceOnUse', width: 6, height: 6, patternTransform: 'rotate(45)' });
    cpat.appendChild(el('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: '#86e1ff', 'stroke-width': 2, opacity: 0.9 }));
    cpat.appendChild(el('line', { x1: 0, y1: 0, x2: 6, y2: 0, stroke: '#86e1ff', 'stroke-width': 2, opacity: 0.9 }));
    defs.appendChild(cpat);
    // WORKING-chip color-pulse mirrors romp-chat-view's `.chip-pulse`: the letters are ONE solid color
    // that breathes between two tones on a sine ease. That's a per-<text> SMIL `<animate fill>` (added
    // where the chip is drawn below), so no gradient def is needed here.
    svg.appendChild(defs);
    // Pan: the window's RIGHT edge is `now` minus the offset slider; the actual live `now` (nowS)
    // is separate, so pending events still ride the true now (off-screen to the right when panned back).
    const nowS = this._liveNow(), winSec = this.winSec();   // effective now: glides between polls while live-following
    this._lastLiveNow = nowS;                               // baseline for the live-tick's sub-pixel guard
    // Broken-axis (see _buildCompressMap): the window (winSec/off) is in COMPRESSED seconds; each long
    // idle gap collapses to one tick interval (step). The map is GLOBAL + stable, so panning is a pure
    // translate (x only rescales on zoom). When collapse is off, compress is identity = plain linear.
    const step = niceStep(winSec);                            // axis tick interval (discrete nice value)
    const gapCT = winSec * GAP_FRAC;                          // gap compressed width — CONTINUOUS → smooth zoom
    const cmap = this._collapseGaps ? this._buildCompressMap(data.turns, gapCT, nowS) : null;
    const compress = cmap ? cmap.compress : (t) => t;
    const decompress = cmap ? cmap.decompress : (c) => c;
    const cNow = compress(nowS);
    // FOLLOW-NOW vs HOLD-POSITION (see constructor). Pinned → right edge = now (live auto-scroll).
    // Unpinned → re-derive `off` each POLL so the right edge stays at `_holdReal` (absolute → no creep);
    // a fresh gesture/nav (_offDirty) is taken verbatim this frame, then we resume holding.
    let off;
    if (this._lockNow && !this._frozeFromPin) this._pinned = true;   // 🔒 lock pins to now — but a hover-freeze still wins (hold at the hovered instant)
    if (this._pinned) off = 0;
    else if (!this._offDirty && this._holdReal != null) off = Math.max(0, Math.min(MAX_OFFSET, cNow - compress(this._holdReal)));
    else off = this.offSec();
    this._offSec = off; this._offDirty = false;
    const cT1 = cNow - off, cT0 = cT1 - winSec;
    const t1 = decompress(cT1), t0 = decompress(cT0);         // real-time window edges (for clip filters)
    this._holdReal = t1;                                      // remember the absolute right edge for the next poll's hold

    const inWin = (t) => t >= t0 && t <= t1;
    const overlaps = (a, b) => b >= t0 && a <= t1;
    // An event is positioned at its PROCESS-START (when it began affecting the workflow). While still
    // pending (queued / in-flight, not yet worked) it rides the live `now` edge (nowS); once processed
    // the data carries a FIXED past time so it can never equal now again (anti-"perpetual-just-landing").
    // A resolved enqueue snaps to its resolution time (t.proc), not submission.
    const execAt = (mm) => mm.pending ? nowS : mm.exec;
    const startAt = (t) => t.pending ? nowS : (t.proc != null ? t.proc : t.start);
    // LANE IDENTITY IS THE SID (data.turns + vidx + connectors all key by session.id, since two
    // live sessions can share a name and a rename keeps the id). `name` is display-only.
    const turnsOf = (sid) => data.turns[sid] || [];
    const colorOf = (sid) => { const s = data.sessions.find((x) => x.id === sid); return s ? s.color : '#888'; };

    // live sessions ALWAYS get a lane (even with no activity in this window);
    // closed sessions appear only when the window covers their past activity
    const active = (s) => s.live ||
      turnsOf(s.id).some((t) => overlaps(t.start, t.end)) ||
      data.messages.some((m) => (m.fromId === s.id || m.toId === s.id) && overlaps(Math.min(m.sent, m.exec), Math.max(m.sent, m.exec)));
    let vis = data.sessions.filter(active);
    // while a row is being dragged, honor the transient drag order so the lanes shuffle live under
    // the cursor (data.sessions still holds the persisted order; _dragOrder overrides until drop).
    if (this._dragOrder) {
      const oidx = new Map(this._dragOrder.map((id, i) => [id, i]));
      vis = vis.slice().sort((a, b) => ((oidx.has(a.id) ? oidx.get(a.id) : Infinity) - (oidx.has(b.id) ? oidx.get(b.id) : Infinity)));
    }
    this._vis = vis;   // visible lanes in order → keyboard ↑/↓ selection
    const vidx = {}; vis.forEach((s, i) => { vidx[s.id] = i; });


    // "compacting" = the real @claude-state OR an OPTIMISTIC click not yet confirmed (≤6s) — so the cue
    // appears the instant the user clicks the battery, not after the next state poll.
    const nowMs = (typeof Date !== 'undefined' && Date.now) ? Date.now() : 0;
    const compactingNow = (s) => s.state === 'compacting' || (this._compactClicked[s.id] != null && (nowMs - this._compactClicked[s.id]) < 6000);
    // gutter = name column (left-aligned) + chip column (every chip shares an x,
    // like the dashboard's badge column). Names left-aligned, chips follow.
    const visB = vis.map((s) => compactingNow(s)
      ? { label: 'COMPACTING' + (s.compactPct != null ? ' ' + s.compactPct + '%' : ''), bg: BADGE.compacting.bg, fg: BADGE.compacting.fg }   // live % from @claude-compact-pct
      : badgeFor(s));
    const visC = vis.map((s) => ctxInfo(s));
    const maxName = Math.max(40, ...(vis.length ? vis : data.sessions).map((s) => this.labelWidth(s.name)));
    // model+effort column: each word is a clickable picker drawn as [model ▾] [effort ▾], so reserve the
    // word + caret widths (+ a gap between the two pickers). Same 11px font as ctx (ctxWidth).
    const META_GAP = 6, caretW = this.ctxWidth(META_CARET);
    const metaWidth = (s) => { if (!s.model) return 0; let w = this.ctxWidth(s.model) + caretW; if (s.effort) w += META_GAP + this.ctxWidth(s.effort) + caretW; return w; };
    const maxModel = Math.max(0, ...vis.map(metaWidth));
    const maxChip = Math.max(0, ...visB.map((b) => (b ? this.badgeWidth(b.label) + 12 : 0)));
    const maxCtx = (visC.some((c) => c) || vis.some((s) => compactingNow(s))) ? BAT_W : 0;   // ctx column = battery bar
    // gear column: a per-session settings gear between the name and the model, on LIVE lanes (the user
    // 2026-06-19). Reserve its width only when there IS a live lane, so an all-historical view keeps the
    // tight [name][model] layout.
    const EYE_W = 13, EYE_GAP = 6, anyLive = vis.some((s) => s.live);
    const eyeColX = PADL + Math.ceil(maxName) + COLGAP;                              // [name] [👁] [model+effort] [chip] [ctx]
    const modelColX = eyeColX + (anyLive ? EYE_W + EYE_GAP : 0);
    const chipColX = modelColX + (maxModel > 0 ? Math.ceil(maxModel) + COLGAP : 0);
    const ctxColX = chipColX + (maxChip > 0 ? Math.ceil(maxChip) + COLGAP : 0);
    M.left = ctxColX + (maxCtx > 0 ? Math.ceil(maxCtx) + COLGAP : 4);
    // (the compacting cue is now a solid teal "compression" rect drawn per-lane below — no shared gradient)

    // judging band height: a compact judge row per JUDGES entry, shown only when there's judging
    // activity inside the current window. Folded into H so the shared axis (axisY = H - M.bottom)
    // and its gridlines span BOTH bands, with the time labels at the very bottom.
    // the global Debug setting (romp:settings.debug, set in the feed gear) gates the whole band; read fresh
    let debugOn = false; try { debugOn = !!JSON.parse(localStorage.getItem('romp:settings') || '{}').debug; } catch (e) {}
    // the band shows when there are judge run-spans in window (auto-nudge ⚡ marks were removed from the band
    // entirely — the user 2026-06-23; an auto-nudge still shows as a romp-logo dot on its lane)
    const jShow = !!(debugOn && data.judging && data.judging.some((e) => inWin(e.t)));
    const bandH = jShow ? (JB_TOPGAP + JUDGES.length * JROW + JB_BOTGAP) : 0;
    const W = Math.max(640, this.wrap.clientWidth || 900);
    const plotW = W - M.left - M.right, H = M.top + Math.max(1, vis.length) * LANE_GAP + bandH + M.bottom;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('height', H); svg.setAttribute('width', W);
    // x is LINEAR in compressed time → smooth pan (only zoom rescales). Identity compress = plain linear.
    const x = (t) => M.left + (compress(t) - cT0) / winSec * plotW;
    const laneY = (i) => M.top + i * LANE_GAP + LANE_GAP * 0.5;
    this._geom = { ml: M.left, plotW, W, H, top: M.top, t0, t1, cT0, winSec, compress, decompress };

    // axis — gridlines + time labels. Ticks at real nice intervals, drawn at their compressed x (evenly
    // spaced in active regions, squished across gaps). A tick inside a collapsed gap is skipped — the
    // squiggle break + its two boundary-time labels stand in for that span.
    const inGap = (t) => cmap && cmap.gaps.some((g) => t > g.ra && t < g.rb);
    const axisY = H - M.bottom;
    // axis-label collision guard: every clock on the label row claims its x-extent; a label that
    // would overlap an already-placed one is dropped (its gridline still draws). Regular interval
    // ticks draw first so they always win — the gap-break boundary clocks (drawn after) yield.
    const placedLabels = [];
    const placeLabel = (a, b) => { for (const p of placedLabels) if (a < p[1] + 6 && b > p[0] - 6) return false; placedLabels.push([a, b]); return true; };
    for (let tk = Math.ceil(t0 / step) * step; tk <= t1; tk += step) {
      if (inGap(tk)) continue;
      svg.appendChild(el('line', { x1: x(tk), y1: M.top, x2: x(tk), y2: axisY, stroke: '#ffffff10', 'stroke-width': 1 }));
      this._mc.font = '10px ' + FONT;
      const hw = this._mc.measureText(clock(tk)).width / 2;
      if (!placeLabel(x(tk) - hw, x(tk) + hw)) continue;
      const tx = el('text', { x: x(tk), y: axisY + 14, 'text-anchor': 'middle', fill: 'var(--text-muted)', 'font-size': 10 }); tx.textContent = clock(tk); svg.appendChild(tx);
    }
    svg.appendChild(el('line', { x1: x(t1), y1: M.top, x2: x(t1), y2: axisY, stroke: '#ffffff22', 'stroke-width': 1 }));
    // broken-axis squiggle(s): one per collapsed gap visible in the window (real edges → compressed x).
    // CLAMP to the plot [M.left, plotRight]: a gap straddling a window edge would otherwise map x(g.ra)
    // LEFT of M.left → the squiggle + its label render in the gutter, over the battery column (the bug).
    if (cmap) {
      const plotR = W - M.right;
      for (const g of cmap.gaps) if (g.rb > t0 && g.ra < t1) {
        const rx0 = x(g.ra), rx1 = x(g.rb);
        const gx0 = Math.max(M.left, rx0), gx1 = Math.min(plotR, rx1);
        if (gx1 > gx0 + 0.5) this._drawGapBreak(svg, gx0, gx1, g.ra, g.rb, M.top, axisY, rx0 >= M.left - 0.5, !g.trailing && rx1 <= plotR + 0.5, placeLabel);
      }
    }
    if (!vis.length) { const tx = el('text', { x: M.left, y: M.top + 16, fill: 'var(--text-muted)', 'font-size': 12 }); tx.textContent = 'no romp activity in this window'; svg.appendChild(tx); }

    // lanes + activity bars + status chip + label
    const bgRGB = this._surfaceBg();   // surface color for the perceptual idle-fade blend
    const dag = this._dag || null;     // request-DAG journey overlay: {events:Set, msgs:Set} or null
    // feed-modal hover: a SET of ids (a parent line covers its whole subtree — union of reply events +
    // delegation messages). Each id matches either an event (turn → bar/dot) or a postal message
    // (connector/arrival dot), so the hover set feeds BOTH match helpers below.
    const hoverSet = (this._hover && this._hover.ids && this._hover.ids.length) ? new Set(this._hover.ids) : null;
    // An event glyph (bar + start dot) / a message glyph (connector + arrival dot) gets the SAME white
    // focus border whether it's part of the DAG journey (card hover) OR is in the hovered set — the user
    // wants line-hover and card-hover identical (no separate faint glow). `dagOrHover(id)` = membership
    // in either; dotLit/barLit then split the event glyph by ATOM id, so a hover that carries the PROMPT
    // atom (promptId) lights only the start dot and one that carries the WORK atom (workId) lights only
    // the bar — the whole-turn id (DAG journey, coarse card hover) still lights both halves. (NB: name it
    // dagOrHover, NOT `hit` — the bar/connector loops use a LOCAL `const hit` rect; a `const hit` here
    // would put those blocks in a TDZ and crash draw() on the first in-window bar.)
    const dagOrHover = (id) => !!id && ((dag && dag.events.has(id)) || (hoverSet && hoverSet.has(id)));
    const dagOrHoverMsg = (id) => !!id && ((dag && dag.msgs.has(id)) || (hoverSet && hoverSet.has(id)));
    vis.forEach((s, i) => {
      const y = laneY(i);
      // perceptual idle fade: faded lanes blend their colors toward bgRGB to a uniform low luminance.
      const F = (hex) => s.faded ? fadeHex(hex, bgRGB) : hex;
      const fadedEls = [];   // {el, full, faded} for a faded lane → un-faded to full color while hovered
      // ONE highlight: a soft filled block (light gray, NO border) on the SELECTED lane. Selection is
      // set by clicking a lane/item, by ↑/↓, and by the chat's active tab — all the same highlight.
      // Drawn first → bars/dots sit on top.
      if (this.selectedSid === s.id) {
        svg.appendChild(el('rect', { x: 2, y: y - LANE_GAP / 2 + 1, width: W - 4, height: LANE_GAP - 2, rx: 4,
          fill: '#d6dbe2', 'fill-opacity': 0.1 }));
      }
      // full-row click target (low z): clicking ANY empty part of the row selects the lane + previews
      // it at the bottom (latest) — same as a bar, just no anchor. Non-interactive lane elements below
      // are pointer-events:none so their area falls through here; bars/dots keep their handlers on top.
      const rowHit = el('rect', { x: 0, y: y - LANE_GAP / 2, width: W, height: LANE_GAP, fill: 'transparent' });
      rowHit.style.cursor = 'grab';   // grab = drag to PAN (horizontal) or REORDER (vertical); a plain click still selects/opens
      rowHit.addEventListener('mousedown', (e) => this._beginDrag(s.id, e));
      rowHit.addEventListener('click', () => {
        if (this._suppressClick) { this._suppressClick = false; return; }   // just finished a drag → not a select
        this._select(s.id); this.openChat(this._laneTid(s), null, true);
      });
      // ever-so-slight hover tint on the row (much fainter than the selected block) + un-fade a faded
      // lane's colors to full while hovered, so an idle row is readable when you point at it.
      rowHit.addEventListener('mouseenter', () => { rowHit.setAttribute('fill', '#ffffff'); rowHit.setAttribute('fill-opacity', '0.035'); for (const f of fadedEls) f.el.setAttribute('fill', f.full); });
      rowHit.addEventListener('mouseleave', () => { rowHit.setAttribute('fill', 'transparent'); rowHit.removeAttribute('fill-opacity'); for (const f of fadedEls) f.el.setAttribute('fill', f.faded); });
      svg.appendChild(rowHit);
      svg.appendChild(el('line', { x1: M.left, y1: y, x2: x(t1), y2: y, stroke: '#ffffff14', 'stroke-width': 2, 'stroke-linecap': 'round', 'pointer-events': 'none' }));
      turnsOf(s.id).forEach((t) => {
        const a = Math.max(t.start, t0), b = Math.min(barEndT(t, nowS, data.now), t1); if (b <= a) return;
        // ONE bar per work period = ONE hover/summary. A permission pause is a gate WITHIN one task
        // (same ask before & after), so it does NOT split the work — it's an overlay (candy-stripe
        // below). Only a new ASK (typed/queued/absorbed/drain) starts a new period. The bar's color
        // also backs the candy-stripe.
        const bx = x(a), bw = Math.max(2, x(b) - x(a)), eh = BAR_H + 5;
        // White focus border HUGGING this work period — drawn for a DAG journey event (card hover) OR
        // the single event hovered in the feed modal (same style for both, per the user). Offset by DAG_W/2
        // so the stroke's inner edge sits exactly on the bar's edge (entirely outside, no dark gap).
        if (barLit(t, dagOrHover)) {
          svg.appendChild(el('rect', { x: bx - DAG_W / 2, y: y - BAR_H / 2 - DAG_W / 2, width: bw + DAG_W, height: BAR_H + DAG_W, rx: (BAR_H + DAG_W) / 2, fill: 'none', stroke: DAG_HL, 'stroke-width': DAG_W, 'pointer-events': 'none' }));
        }
        const bar = el('rect', { x: bx, y: y - BAR_H / 2, width: bw, height: BAR_H, rx: BAR_H / 2, fill: s.color, opacity: 0.9 });
        svg.appendChild(bar);
        const act = s.state === 'working' || s.state === 'permission' || s.state === 'awaiting' || s.state === 'compacting';
        const ongoing = s.live && act && t.end > t.start && (data.now - t.end) <= 5;
        const hit = el('rect', { x: bx, y: y - 7, width: bw, height: 14, fill: 'transparent' }); hit.style.cursor = 'pointer';
        const html = () => '<div class="r"><span class="chip" style="background:' + s.color + '"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="t">' + clock(t.start) + '–' + clock(t.end) + '</span></div>' + this.barBody(t, ongoing);
        const grow = (h) => { bar.setAttribute('y', y - h / 2); bar.setAttribute('height', h); bar.setAttribute('rx', h / 2); };
        hit.addEventListener('mouseenter', (e) => { grow(eh); bar.setAttribute('opacity', '1'); this.showTip(html(), e); this._emitHover(s.id, [t.id], t.start, t.end); });
        hit.addEventListener('mousemove', (e) => this.moveTip(e));
        hit.addEventListener('mouseleave', () => { grow(BAR_H); bar.setAttribute('opacity', '0.9'); this.hideTip(); this._emitHover(null); });
        // the BAR = the work/response: open the period's readable reply (workAnchorOf), with the
        // period's start as the by-time fallback. This was a bare lane-open with NO anchor, so every
        // work-bar click visibly did nothing while prompt-dot clicks worked (the user, 2026-06-12).
        // The prompt dot keeps the prompt-line uuid.
        hit.addEventListener('click', () => { this._select(s.id); this.openChat(t.tid || this._laneTid(s), workAnchorOf(t), false, false, t.start); });
        svg.appendChild(hit);
      });
      // AWAITING (permission) → candy-stripe every span the session sat blocked on your
      // input (historical, from the state-transition log), plus the current open one. The
      // dashed white overlay reads as a distinct texture vs a solid "still working" bar.
      const aw = (s.awaiting && s.awaiting.length) ? s.awaiting
                 : ((s.live && (s.state === 'permission' || s.state === 'awaiting') && s.since != null) ? [[s.since, t1]] : []);
      for (const span of aw) {
        const a0 = span[0], b0 = span[1];
        const sa = Math.max(a0, t0), sb = Math.min(b0, t1); if (sb <= sa) continue;
        // The awaiting interval (state log) and the work bars (transcript) come from different
        // sources, so a bar can end a few seconds BEFORE the permission prompt → a gap (made worse by
        // rounded caps). Bridge the colored backing to the adjacent work bars (within BRIDGE) and overlap
        // their rounded caps so the candy-cane reads as one continuous lane, not a floating segment.
        const BRIDGE = 180;
        let pe = null, ns = null;
        for (const t of turnsOf(s.id)) {
          if (t.src === 'enqueue' || t.end <= t.start) continue;
          if (t.end <= a0 + 1 && (pe == null || t.end > pe)) pe = t.end;
          if (t.start >= b0 - 1 && (ns == null || t.start < ns)) ns = t.start;
        }
        let bx0 = x(sa), bx1 = x(sb);
        if (pe != null && a0 - pe <= BRIDGE) bx0 = Math.min(bx0, x(Math.max(pe, t0)) - BAR_H / 2);
        if (ns != null && ns - b0 <= BRIDGE) bx1 = Math.max(bx1, x(Math.min(ns, t1)) + BAR_H / 2);
        const eh = BAR_H + 5;
        // colored backing bridges the gap (square caps so it merges with the rounded bars on either side)
        const back = el('rect', { x: bx0, y: y - BAR_H / 2, width: Math.max(2, bx1 - bx0), height: BAR_H, fill: s.color, opacity: 0.9 });
        svg.appendChild(back);
        // candy-cane stripes over the ACTUAL awaiting span (shows the session color THROUGH the stripes)
        const stripe = el('rect', { x: x(sa), y: y - BAR_H / 2, width: Math.max(2, x(sb) - x(sa)), height: BAR_H, fill: 'url(#vault-await-hatch)' });
        svg.appendChild(stripe);
        const sh = el('rect', { x: bx0, y: y - 7, width: Math.max(2, bx1 - bx0), height: 14, fill: 'transparent' }); sh.style.cursor = 'pointer';
        const end = b0 >= data.now - 2 ? 'now' : clock(b0);
        const shtml = () => '<div class="r"><span class="chip" style="background:' + BADGE.attention.bg + '"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="k">blocked</span></div><div class="b">blocked on your input · ' + clock(a0) + '–' + end + '</div>';
        const grow = (h) => { for (const r of [back, stripe]) { r.setAttribute('y', y - h / 2); r.setAttribute('height', h); } };
        sh.addEventListener('mouseenter', (e) => { grow(eh); this.showTip(shtml(), e); });
        sh.addEventListener('mousemove', (e) => this.moveTip(e));
        sh.addEventListener('mouseleave', () => { grow(BAR_H); this.hideTip(); });
        sh.addEventListener('click', () => { this._select(s.id); this.openChat(this._laneTid(s), null, true); });
        svg.appendChild(sh);
      }
      // CONTEXT COMPACTING (LIVE) → cyan cross-hatch over the session color for every span the session
      // sat compacting (PreCompact→PostCompact from the state log), plus the current open one if it's
      // compacting RIGHT NOW. This is the in-progress indicator; the isCompactSummary marker below is the
      // after-the-fact one. Same figure-ground as the awaiting candy-cane.
      const comp = (s.compacting && s.compacting.length) ? s.compacting
                   : ((s.live && s.state === 'compacting' && s.since != null) ? [[s.since, t1]] : []);
      for (const span of comp) {
        const a0 = span[0], b0 = span[1];
        const sa = Math.max(a0, t0), sb = Math.min(b0, t1); if (sb <= sa) continue;
        const eh = BAR_H + 5, cx = x(sa), cw = Math.max(2, x(sb) - x(sa));
        const cback = el('rect', { x: cx, y: y - BAR_H / 2, width: cw, height: BAR_H, rx: 2, fill: s.color, opacity: 0.9 });
        svg.appendChild(cback);
        const chx = el('rect', { x: cx, y: y - BAR_H / 2, width: cw, height: BAR_H, rx: 2, fill: 'url(#vault-compact-hatch)' });
        svg.appendChild(chx);
        const ch = el('rect', { x: cx, y: y - 7, width: cw, height: 14, fill: 'transparent' }); ch.style.cursor = 'pointer';
        const live = b0 >= data.now - 2;
        const cw2 = live ? 'compacting' : 'compacted';
        const chtml = () => '<div class="r"><span class="chip" style="background:#86e1ff"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="k">' + cw2 + '</span></div><div class="b">context ' + cw2 + ' · ' + clock(a0) + '–' + (live ? 'now' : clock(b0)) + '</div>';
        const cgrow = (h) => { for (const r of [cback, chx]) { r.setAttribute('y', y - h / 2); r.setAttribute('height', h); } };
        ch.addEventListener('mouseenter', (e) => { cgrow(eh); this.showTip(chtml(), e); });
        ch.addEventListener('mousemove', (e) => this.moveTip(e));
        ch.addEventListener('mouseleave', () => { cgrow(BAR_H); this.hideTip(); });
        ch.addEventListener('click', () => { this._select(s.id); this.openChat(this._laneTid(s), null, true); });
        svg.appendChild(ch);
      }
      // CONTEXT COMPACTION → a cyan cross-hatch SPAN over the session color (same figure-ground as the
      // awaiting candy-cane: identity color behind, texture in front). The span runs from compaction
      // START (prev real event) to completion (cp.t), CLAMPED to the last CCAP seconds so a long
      // idle-then-/compact gap doesn't stretch the bar — the compaction itself is at most a minute or two.
      const CCAP = 300;
      for (const cp of (s.compactions || [])) {
        if (cp.t < t0 || cp.t > t1) continue;
        const cs = Math.max(cp.prev != null ? cp.prev : cp.t, cp.t - CCAP, t0);
        const ce = Math.min(cp.t, t1);
        const cx = x(cs), cw = Math.max(6, x(ce) - cx), eh = BAR_H + 5;
        const cback = el('rect', { x: cx, y: y - BAR_H / 2, width: cw, height: BAR_H, rx: 2, fill: s.color, opacity: 0.9 });
        svg.appendChild(cback);
        const chx = el('rect', { x: cx, y: y - BAR_H / 2, width: cw, height: BAR_H, rx: 2, fill: 'url(#vault-compact-hatch)' });
        svg.appendChild(chx);
        const ch = el('rect', { x: cx, y: y - 7, width: cw, height: 14, fill: 'transparent' }); ch.style.cursor = 'pointer';
        const chtml = () => '<div class="r"><span class="chip" style="background:#86e1ff"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="k">compacted</span></div><div class="b">context compacted · ' + clock(cp.t) + '</div>';
        const cgrow = (h) => { for (const r of [cback, chx]) { r.setAttribute('y', y - h / 2); r.setAttribute('height', h); } };
        ch.addEventListener('mouseenter', (e) => { cgrow(eh); this.showTip(chtml(), e); });
        ch.addEventListener('mousemove', (e) => this.moveTip(e));
        ch.addEventListener('mouseleave', () => { cgrow(BAR_H); this.hideTip(); });
        ch.addEventListener('click', () => { this._select(s.id); this.openChat(this._laneTid(s), null, true); });
        svg.appendChild(ch);
      }
      // name left-aligned; status chip in the shared chip column to its right. ENDED or idle >1h
      // (s.faded) → name/chip/ctx blended toward the surface bg to a uniform low luminance (perceptual
      // fade via F(), consistent across hues + with the chat tabs), instead of a flat opacity.
      const lblA = { x: PADL, y: y + 3.5, 'text-anchor': 'start', 'font-weight': 650, 'font-size': 12, fill: F(s.color), 'pointer-events': 'none' };
      if (!s.live) lblA['text-decoration'] = 'line-through';   // dead lane → strike the name (mirrors the feed)
      const lbl = el('text', lblA); lbl.textContent = s.name; svg.appendChild(lbl);
      if (s.faded) fadedEls.push({ el: lbl, full: s.color, faded: F(s.color) });
      // per-session feed show/hide EYE (live lanes only): one click toggles hideFromFeed directly — eye =
      // on the feed (default), struck-through + dimmer = off it. Always GRAY; the OFF state is de-emphasised
      // (dimmer), never highlighted (the user 2026-06-22). No menu.
      if (s.live) {
        const off = !!s.hideFromFeed;
        const cx = eyeColX + 5, cy = y + 0.5;
        // The drawn eye is PURELY VISUAL (pointer-events:none): thin strokes are nearly unhittable, so a
        // generous transparent <rect> over it is the real hit target (same trick the work bars use). The
        // tooltip uses the shared showTip/hideTip (a native SVG <title> never shows — a redraw kills the
        // hover before it appears; showTip freezes live-follow so it stays — the user 2026-06-22).
        const dim = off ? '0.4' : '0.62';              // off = darker/dimmer; on = the normal gray
        const eye = eyeIcon(off, cx, cy, MODEL_FG);
        eye.setAttribute('opacity', dim);
        svg.appendChild(eye);
        const hit = el('rect', { x: eyeColX - 4, y: y - 9, width: EYE_W + 8, height: 18, fill: 'transparent', 'pointer-events': 'all' });
        hit.style.cursor = 'pointer';
        hit.setAttribute('aria-label', off ? 'session off the feed' : 'session on the feed'); svg.appendChild(hit);
        const tip = off
          ? "Off the feed — click to put it back on<div style='opacity:.65;margin-top:2px'>only new prompts make cards; past ones won’t reappear</div>"
          : "On the feed — click to take it off<div style='opacity:.65;margin-top:2px'>its prompts stop making cards; it stays on the timeline</div>";
        hit.addEventListener('mouseenter', (e) => { eye.setAttribute('opacity', '1'); this.showTip(tip, e); });
        hit.addEventListener('mousemove', (e) => this.moveTip(e));
        hit.addEventListener('mouseleave', () => { eye.setAttribute('opacity', dim); this.hideTip(); });
        hit.addEventListener('click', (e) => {
          e.stopPropagation();
          const next = !s.hideFromFeed;
          s.hideFromFeed = next;                       // optimistic …
          (this._pendingFlags[s.id] = this._pendingFlags[s.id] || {}).hideFromFeed = next;   // … and held STICKY across pushes until the kernel confirms (no flicker-back)
          this._setSessionFlag(s, 'hideFromFeed', next);
          this.hideTip();
          this.draw();
        });
      }
      // model + effort, muted, between the name and the state chip (left-aligned in its column). On a
      // LIVE lane each word is a drop-down picker — hover reveals a ▾ caret, click opens a menu whose
      // pick injects /model or /effort into that pane. Dead/historical lanes render it as static text.
      if (s.model) {
        if (!s.live) {
          const mt = el('text', { x: modelColX, y: y + 3.5, 'text-anchor': 'start', 'font-size': 11, 'font-weight': 600, fill: F(MODEL_FG), 'pointer-events': 'none' });
          mt.textContent = modelLabel(s); svg.appendChild(mt);
          if (s.faded) fadedEls.push({ el: mt, full: MODEL_FG, faded: F(MODEL_FG) });
        } else {
          const pendingOf = (kind) => {
            const p = this._metaPending[s.id + ':' + kind]; if (!p) return false;
            const cur = (kind === 'model' ? s.model : s.effort) || '';
            if (cur !== p.was || nowMs > p.until) { delete this._metaPending[s.id + ':' + kind]; return false; }
            return true;
          };
          let px = modelColX;
          const drawPiece = (kind, word) => {
            const pend = pendingOf(kind), ww = this.ctxWidth(word);
            const wt = el('text', { x: px, y: y + 3.5, 'text-anchor': 'start', 'font-size': 11, 'font-weight': 600, fill: MODEL_FG, 'pointer-events': 'auto' });
            wt.textContent = word; wt.style.cursor = 'pointer'; if (pend) wt.setAttribute('opacity', '0.45'); svg.appendChild(wt);
            const ct = el('text', { x: px + ww, y: y + 3.5, 'text-anchor': 'start', 'font-size': 11, 'font-weight': 600, fill: MODEL_FG, opacity: pend ? '0.45' : '0', 'pointer-events': 'none' });
            ct.textContent = META_CARET; svg.appendChild(ct);
            wt.addEventListener('mouseenter', () => { wt.setAttribute('fill', META_HOVER_FG); ct.setAttribute('fill', META_HOVER_FG); ct.setAttribute('opacity', '1'); });
            wt.addEventListener('mouseleave', () => { wt.setAttribute('fill', MODEL_FG); ct.setAttribute('fill', MODEL_FG); ct.setAttribute('opacity', pendingOf(kind) ? '0.45' : '0'); });
            wt.addEventListener('click', (e) => { e.stopPropagation(); this._openMetaMenu(kind, s, wt); });
            px += ww + caretW;
          };
          drawPiece('model', s.model);
          if (s.effort) { px += META_GAP; drawPiece('effort', s.effort); }
        }
      }
      const bdg = visB[i];
      if (bdg) {
        const h = 14, padX = 6, w = Math.ceil(this.badgeWidth(bdg.label)) + padX * 2, by = y - h / 2;
        const chipBg = el('rect', { x: chipColX, y: by, width: w, height: h, rx: h / 2, fill: F(bdg.bg), 'pointer-events': 'none' }); svg.appendChild(chipBg);
        // WORKING chip letters are a SOLID color that breathes between two tones on a sine ease (mirrors
        // romp-chat-view's .chip-pulse); other chips keep their solid fg. Working sessions are never faded.
        const WK_A = '#1a1a1a', WK_B = '#0d9488';   // near-black ↔ teal, both contrast the yellow pill
        const chipFill = s.state === 'working' ? WK_A : F(bdg.fg);
        const bt = el('text', { x: chipColX + w / 2, y: y + 3, 'text-anchor': 'middle', fill: chipFill, 'font-size': BADGE_FS, 'font-weight': 700, 'pointer-events': 'none' });
        bt.setAttribute('letter-spacing', '0.03em'); bt.textContent = bdg.label;
        if (s.state === 'working') {
          // calcMode=spline keySplines 0.37 0 0.63 1 = ease-in-out-sine; begin='0s' rides the persistent
          // SVG doc-time phase so the ~1s poll rebuild resumes mid-cycle, seamless.
          bt.appendChild(el('animate', { attributeName: 'fill', values: WK_A + ';' + WK_B + ';' + WK_A, keyTimes: '0;0.5;1', calcMode: 'spline', keySplines: '0.37 0 0.63 1;0.37 0 0.63 1', dur: '1.5s', begin: '0s', repeatCount: 'indefinite' }));   // 1.5s = 2× the old 3s, matches the chat chip-pulse (the user 2026-06-16)
        }
        svg.appendChild(bt);
        if (s.faded) { fadedEls.push({ el: chipBg, full: bdg.bg, faded: F(bdg.bg) }); fadedEls.push({ el: bt, full: bdg.fg, faded: F(bdg.fg) }); }
      }
      // context-window battery bar (matches the chat-view): faint box + level-colored fill (width ∝ pct)
      // + "N%" inside. While COMPACTING it instead shows a rainbow scan-bar (no %), the live cue.
      const cinfo = visC[i], isComp = compactingNow(s);
      if (cinfo || isComp) {
        const byTop = y - BAT_H / 2;
        svg.appendChild(el('rect', { x: ctxColX, y: byTop, width: BAT_W, height: BAT_H, rx: 3, fill: 'rgba(255,255,255,0.07)', stroke: 'rgba(255,255,255,0.35)', 'stroke-width': 1, 'pointer-events': 'none' }));
        if (isComp) {
          // a solid TEAL rectangle fills the battery, then its RIGHT edge slides left (width shrinks from a
          // fixed left x) — a "compression" cue. It fades in at full width and out when compressed so the
          // loop never snaps. No % while compacting. draw() recreates this <rect> every ~1s poll, but
          // `this.svg` — and thus its SMIL document timeline — PERSISTS, so begin='0s' lands each freshly-
          // created rect at the current phase (docTime % DUR) → the per-poll rebuild is seamless.
          const ix0 = ctxColX + 1, innerW = BAT_W - 2, minW = 1, DUR = 3.2, TEAL = '#14b8a6';
          const bar = el('rect', { x: ix0, y: byTop + 1, width: innerW, height: BAT_H - 2, rx: 1, fill: TEAL, 'pointer-events': 'none' });
          bar.appendChild(el('animate', { attributeName: 'width', values: innerW + ';' + innerW + ';' + minW + ';' + minW, keyTimes: '0;0.1;0.9;1', dur: DUR + 's', begin: '0s', repeatCount: 'indefinite' }));
          bar.appendChild(el('animate', { attributeName: 'opacity', values: '0;1;1;0', keyTimes: '0;0.1;0.9;1', dur: DUR + 's', begin: '0s', repeatCount: 'indefinite' }));
          svg.appendChild(bar);
        } else {
          const innerW = BAT_W - 2, fillW = Math.max(0, Math.min(1, cinfo.pct / 100)) * innerW, fillCol = F(cinfo.color);
          if (fillW > 0.5) {
            const fr = el('rect', { x: ctxColX + 1, y: byTop + 1, width: fillW, height: BAT_H - 2, rx: 2, fill: fillCol, 'pointer-events': 'none' });
            svg.appendChild(fr);
            if (s.faded) fadedEls.push({ el: fr, full: cinfo.color, faded: fillCol });
          }
          const ct = el('text', { x: ctxColX + BAT_W / 2, y: y + 3, 'text-anchor': 'middle', fill: '#ffffff', 'font-size': 9, 'font-weight': 700, 'font-family': 'ui-monospace, SFMono-Regular, Menlo, monospace', 'pointer-events': 'none' });
          ct.setAttribute('style', 'text-shadow: 0 0 2px rgba(0,0,0,.75)');
          ct.textContent = cinfo.label; svg.appendChild(ct);
        }
        // CLICK the battery → send /compact to that live session; optimistically show the cue at once.
        if (s.live) {
          const hit = el('rect', { x: ctxColX, y: byTop, width: BAT_W, height: BAT_H, rx: 3, fill: 'transparent' });
          hit.style.cursor = 'pointer';
          const cmt = () => '<div class="r"><span class="chip" style="background:' + s.color + '"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="k">' + (isComp ? 'compacting' : ((cinfo ? cinfo.label : '') + ' context')) + '</span></div><div class="b">' + (isComp ? 'compaction in progress' : 'click to /compact this session') + '</div>';
          hit.addEventListener('mouseenter', (e) => this.showTip(cmt(), e));
          hit.addEventListener('mousemove', (e) => this.moveTip(e));
          hit.addEventListener('mouseleave', () => this.hideTip());
          hit.addEventListener('click', (e) => { e.stopPropagation(); this.hideTip(); this._compactClicked[s.id] = (Date.now ? Date.now() : 0); this._compactSession(s.name); this.draw(); });
          svg.appendChild(hit);
        }
      }
      // 📬 unread/parked mail flag — esp. meaningful on a DEAD lane (the mail delivers on its revival).
      // Full-opacity attention glyph at the lane's right (now) edge; hover shows the count.
      if (s.pendingMail > 0) {
        const mx = x(t1) - 12, n = s.pendingMail;
        const mb = el('text', { x: mx, y: y + 4, 'font-size': 12, 'text-anchor': 'middle' }); mb.textContent = '📬'; svg.appendChild(mb);
        const mhit = el('rect', { x: mx - 10, y: y - 8, width: 20, height: 16, fill: 'transparent' }); mhit.style.cursor = 'pointer';
        const mhtml = () => '<div class="r"><span class="chip" style="background:' + s.color + '"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="k">mail</span></div><div class="b">' + n + ' unread message' + (n === 1 ? '' : 's') + ' waiting' + (s.live ? '' : ' (delivers on revival)') + '</div>';
        mhit.addEventListener('mouseenter', (e) => this.showTip(mhtml(), e));
        mhit.addEventListener('mousemove', (e) => this.moveTip(e));
        mhit.addEventListener('mouseleave', () => this.hideTip());
        mhit.addEventListener('click', () => { this._select(s.id); this.openChat(this._laneTid(s), null, true); });
        svg.appendChild(mhit);
      }
    });

    // obstacles for routing — at each event's process-start (a pending event rides `now` via execAt/startAt)
    const obstacles = [];
    data.messages.forEach((mm) => { if (inWin(execAt(mm)) && vidx[mm.toId] != null) obstacles.push({ x: x(execAt(mm)), lane: vidx[mm.toId] }); });
    vis.forEach((s, i) => turnsOf(s.id).forEach((t) => { if (inWin(startAt(t))) obstacles.push({ x: x(startAt(t)), lane: i }); }));

    // one connector per directed FLOW (A→B): a single line spanning the flow's first
    // send → last delivery, whose THICKNESS grows linearly with the message count
    // (no cap). Drawn at alpha .5 and colored by sender, so the two directions (which
    // sit at slightly different tracks) read even where they overlap. The per-message
    // arrival dots below still mark each individual message.
    const flows = {};
    data.messages.forEach((mm) => {
      if (vidx[mm.fromId] == null || vidx[mm.toId] == null) return;
      if (execAt(mm) < t0 || mm.sent > t1) return;
      const k = mm.fromId + '|' + mm.toId;
      const f = flows[k] || (flows[k] = { from: mm.fromId, to: mm.toId, n: 0, sent: Infinity, exec: -Infinity, last: null });
      f.n++; if (mm.sent < f.sent) f.sent = mm.sent; if (mm.exec > f.exec) f.exec = mm.exec;
      if (!f.last || mm.exec > f.last.exec) f.last = mm;
    });
    // base flow lines (thickness ∝ message count) — the visual band per directed flow
    const flowW = {};
    Object.keys(flows).forEach((k) => {
      const f = flows[k];
      const sLane = vidx[f.from], rLane = vidx[f.to];
      const xs = x(Math.max(f.sent, t0)), ys = laneY(sLane), xe = x(f.exec), ye = laneY(rLane), col = colorOf(f.from);
      const dir = (ys < ye) ? 1 : -1;
      const track = ye - dir * MSG_DROP;
      const xc = crossX(sLane, rLane, xs, xe, obstacles);
      const pts = (xc > xs + 0.5) ? [{ x: xs, y: ys }, { x: xc, y: ys }, { x: xc, y: track }, { x: xe, y: track }, { x: xe, y: ye }]
                                  : [{ x: xs, y: ys }, { x: xs, y: track }, { x: xe, y: track }, { x: xe, y: ye }];
      const d = roundedPath(pts, CORNER);
      const w = MSG_W0 + (f.n - 1) * MSG_GROW;   // thickness ∝ message count, no max cap
      flowW[k] = w;   // band no longer drawn — per-message connectors below draw each message's own line
    });
    // Per-message connector + arrival dot are ONE interactive unit: hovering the line OR the dot
    // co-highlights both and shows the tooltip; clicking either jumps to where the message LANDED
    // (the recipient's transcript at exec). No longer separate hover/click targets.
    const msgUI = {};   // message index → { hl, dot }, shared across the line + dot passes
    const msgHtml = (mm) => () => { const col = colorOf(mm.fromId); return '<div class="r"><span class="chip" style="background:' + col + '"></span><span class="who" style="color:' + col + '">' + esc(mm.from) + '</span><span class="ar">→</span><span class="who" style="color:' + colorOf(mm.toId) + '">' + esc(mm.to) + '</span>' + (mm.pending ? ' <span class="k">pending</span>' : '') + '<span class="t">' + clock(mm.sent) + (mm.pending ? ' → …' : ' → ' + clock(mm.exec)) + '</span></div>' + this.body(esc(mm.summary || mm.text || '')); };
    const msgNav = (mm) => () => { const an = this.nearestTurnAnchor(mm.toId, execAt(mm)); this._select(mm.toId); this.openChat((an && an.tid) || mm.toId, mm.id || (an && (an.uuid || an.replyUuid)), false, false, execAt(mm)); };   // land on the message's OWN postal card BY ID — the chat matches mm.id to the card's data-mid (the user 2026-06-20); nearest-turn uuid / time only as fallback
    // PASS 1: connector line + highlight (drawn first so the dots sit on top).
    data.messages.forEach((mm, i) => {
      if (vidx[mm.fromId] == null || vidx[mm.toId] == null) return;
      if (execAt(mm) < t0 || mm.sent > t1) return;
      const sLane = vidx[mm.fromId], rLane = vidx[mm.toId];
      const xs = x(Math.max(mm.sent, t0)), ys = laneY(sLane), xe = x(execAt(mm)), ye = laneY(rLane), col = colorOf(mm.fromId);
      const dir = (ys < ye) ? 1 : -1, track = ye - dir * MSG_DROP;
      const xc = crossX(sLane, rLane, xs, xe, obstacles);
      const pts = (xc > xs + 0.5) ? [{ x: xs, y: ys }, { x: xc, y: ys }, { x: xc, y: track }, { x: xe, y: track }, { x: xe, y: ye }]
                                  : [{ x: xs, y: ys }, { x: xs, y: track }, { x: xe, y: track }, { x: xe, y: ye }];
      const d = roundedPath(pts, CORNER);
      // White casing under a handoff connector that's part of the focused journey (DAG card hover) OR the
      // hovered subtree's delegation messages — same style for both. Drawn first → the colored line sits
      // centered on top, leaving a DAG_W-wide white border each edge.
      if (dagOrHoverMsg(mm.id)) {
        svg.appendChild(el('path', { d, fill: 'none', stroke: DAG_HL, 'stroke-width': MSG_W0 + 2 * DAG_W, opacity: 1, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'pointer-events': 'none' }));
      }
      const lineAttr = { d, fill: 'none', stroke: col, 'stroke-width': MSG_W0, opacity: mm.pending ? 0.4 : 0.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
      if (mm.pending) lineAttr['stroke-dasharray'] = '1 4';
      svg.appendChild(el('path', lineAttr));
      const hl = el('path', { d, fill: 'none', stroke: col, 'stroke-width': MSG_W0 + 3, opacity: 0, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
      svg.appendChild(hl);
      const u = (msgUI[i] = { hl, dot: null });
      const hit = el('path', { d, fill: 'none', stroke: 'transparent', 'stroke-width': Math.max(14, MSG_W0 + 6) }); hit.style.cursor = 'pointer';
      hit.addEventListener('mouseenter', (e) => { hl.setAttribute('opacity', '0.95'); if (u.dot) u.dot.setAttribute('r', DOT_R + 2); this.showTip(msgHtml(mm)(), e); });
      hit.addEventListener('mousemove', (e) => this.moveTip(e));
      hit.addEventListener('mouseleave', () => { hl.setAttribute('opacity', '0'); if (u.dot) u.dot.setAttribute('r', DOT_R); this.hideTip(); });
      hit.addEventListener('click', msgNav(mm));
      svg.appendChild(hit);
    });

    // dot helper: optional onClick (deep-link) + optional linkedHl (co-light a connector on hover).
    const dot = (cx, cy, color, html, onClick, linkedHl) => {
      const c = el('circle', { cx, cy, r: DOT_R, fill: color, stroke: '#e8eef5', 'stroke-width': 1.5 }); c.style.cursor = onClick ? 'pointer' : 'default';
      c.addEventListener('mouseenter', (e) => { c.setAttribute('r', DOT_R + 2); if (linkedHl) linkedHl.setAttribute('opacity', '0.95'); this.showTip(html(), e); });
      c.addEventListener('mousemove', (e) => this.moveTip(e));
      c.addEventListener('mouseleave', () => { c.setAttribute('r', DOT_R); if (linkedHl) linkedHl.setAttribute('opacity', '0'); this.hideTip(); });
      if (onClick) c.addEventListener('click', onClick);
      svg.appendChild(c);
      return c;
    };

    // PASS 2: message arrival dots (on top of the lines), linked to their connector so the two
    // co-highlight and share the click. A dot whose sender lane is off-screen has no connector but
    // is still its own hoverable/clickable target.
    data.messages.forEach((mm, i) => {
      if (vidx[mm.toId] == null || !inWin(execAt(mm))) return;
      const col = colorOf(mm.fromId), cy = laneY(vidx[mm.toId]);
      const u = msgUI[i];
      if (dagOrHoverMsg(mm.id)) svg.appendChild(el('circle', { cx: x(execAt(mm)), cy, r: DOT_R + DAG_W / 2, fill: 'none', stroke: DAG_HL, 'stroke-width': DAG_W, 'pointer-events': 'none' }));   // white ring: DAG journey node OR hovered delegation message → hugging the arrival dot
      const c = dot(x(execAt(mm)), cy, col, msgHtml(mm), msgNav(mm), u && u.hl);
      if (u) u.dot = c;
    });

    // turn process-start (prompt) dots — at startAt; CLICKABLE → jump to the prompt that started
    // the period. Skipped where a PROCESSED message dot coincides (the message dot stands in).
    vis.forEach((s, i) => {
      const y = laneY(i);
      turnsOf(s.id).forEach((t) => {
        if (t.cont) return;                  // a post-sleep continuation piece of one segment: its prompt dot belongs to the FIRST piece, not here
        if (!inWin(startAt(t))) return;
        if (data.messages.some((mm) => mm.toId === s.id && !mm.pending && Math.abs(execAt(mm) - startAt(t)) <= 1)) return;
        const dx = x(startAt(t));
        if (dotLit(t, dagOrHover)) svg.appendChild(el('circle', { cx: dx, cy: y, r: DOT_R + DAG_W / 2, fill: 'none', stroke: DAG_HL, 'stroke-width': DAG_W, 'pointer-events': 'none' }));   // white focus ring: DAG journey node, a coarse card hover (whole-turn id), OR a prompt-atom hover (promptId) — never a work-only (workId) hover
        // a romp NUDGE prompt (auto-nudge / Nudge / retry — author 'romp', the user 2026-06-22): caption it
        // 'romp · nudge' with the swirl logo, not the session name, and stamp a ⚡ INSIDE its dot below.
        const tip = t.nudge
          ? () => '<div class="r"><img src="/media/romp-swirl-glyph.svg" width="13" height="13" style="vertical-align:-2px;margin-right:5px;border-radius:2px"><span class="who" style="color:' + s.color + '">romp · nudge</span><span class="t">' + clock(startAt(t)) + '</span></div>' + this.body(this.req(t))
          : () => '<div class="r"><span class="chip" style="background:' + s.color + '"></span><span class="who" style="color:' + s.color + '">' + esc(s.name) + '</span><span class="t">' + clock(startAt(t)) + '</span>' + (t.src === 'enqueue' ? (t.pending ? '<span class="k">queued</span>' : '') : '') + '</div>' + this.body(this.req(t));
        dot(dx, y, s.color, tip, () => { this._select(s.id); this.openChat(t.tid || s.id, t.uuid, false, false, startAt(t), 'user'); });   // prompt dot = prompt-intent → time fallback restricted to user turns
        if (t.nudge) {                                   // ⚡ inside the circle: a white bolt path so it reads on any lane colour (pointer-events:none → the dot keeps its hover/click)
          svg.appendChild(el('path', { d: 'M' + (dx + 1) + ' ' + (y - 3.2) + 'L' + (dx - 2.2) + ' ' + (y + 0.5) + 'L' + (dx - 0.2) + ' ' + (y + 0.5) + 'L' + (dx - 1) + ' ' + (y + 3.2) + 'L' + (dx + 2.2) + ' ' + (y - 0.6) + 'L' + (dx + 0.2) + ' ' + (y - 0.6) + 'Z', fill: '#ffffff', 'pointer-events': 'none' }));
        }
      });
    });

    // ── judging band: the summarizer judges on the same axis, under the lanes. Each mark is coloured
    // by the SESSION it acted on; adjacent same-session marks merge into a stretch of attention. A mark
    // within ~8s of the live edge is "running now" (white-outlined). (design/judge.md; data.judging.)
    if (jShow) {
      const jb0 = M.top + vis.length * LANE_GAP + JB_TOPGAP;     // top of the first judge row
      const jY = (i) => jb0 + i * JROW + JROW * 0.5;
      const nameOf = (sid) => { const s = data.sessions.find((z) => z.id === sid); return s ? s.name : sid; };
      const sepY = jb0 - JB_TOPGAP * 0.5;
      svg.appendChild(el('line', { x1: M.left, y1: sepY, x2: x(t1), y2: sepY, stroke: '#ffffff14', 'stroke-width': 1, 'pointer-events': 'none' }));
      // vertical "judges" section label in the freed gutter space, just left of the right-justified judge names
      const jcx = Math.max(12, M.left - 72), jcy = (jY(0) + jY(JUDGES.length - 1)) / 2;
      const hd = el('text', { x: jcx, y: jcy, fill: 'var(--text-faint)', 'font-size': 9, 'font-weight': 700, 'letter-spacing': '.08em', 'text-anchor': 'middle', transform: 'rotate(-90 ' + jcx + ' ' + jcy + ')' }); hd.textContent = 'judges'; svg.appendChild(hd);
      JUDGES.forEach((J, ji) => {
        const y = jY(ji);
        // baseline rail through the row, faintly tinted in the judge's colour so each row is identifiable
        svg.appendChild(el('line', { x1: M.left, y1: y, x2: x(t1), y2: y, stroke: J.color, 'stroke-opacity': 0.28, 'stroke-width': 2, 'stroke-linecap': 'round', 'pointer-events': 'none' }));
        // judge name right-justified so it sits right beside the start of its rail
        const lbl = el('text', { x: M.left - 6, y: y + 3, 'text-anchor': 'end', fill: J.color, 'font-size': 10, 'font-weight': 600 }); lbl.textContent = J.key; svg.appendChild(lbl);
        // merge this judge's in-window marks into same-session blocks (a stretch of attention)
        // each mark is a RUN SPAN [t, t1] = [sent, recv] (g70): the real wall-clock the judge call ran, not
        // a point back-placed onto the work. Merge adjacent same-session spans into a stretch of attention.
        const evs = data.judging.filter((e) => e.judge === J.key && inWin(e.t)).sort((a, b) => a.t - b.t);
        const blocks = [];
        for (const e of evs) { const es = e.t, ee = (e.t1 != null ? e.t1 : e.t); const last = blocks[blocks.length - 1];
          if (last && last.sid === e.sid && es - last.end <= JMERGE_GAP) { last.end = Math.max(last.end, ee); last.members.push(e); }
          else blocks.push({ sid: e.sid, start: es, end: ee, members: [e] }); }
        for (const b of blocks) {
          let x1 = x(b.start), x2 = x(b.end);
          if (x2 - x1 < JMARK_MINW) { const c = (x1 + x2) / 2; x1 = c - JMARK_MINW / 2; x2 = c + JMARK_MINW / 2; }
          const col = colorOf(b.sid), active = (nowS - b.end) >= 0 && (nowS - b.end) < 8;
          // fill = the SESSION being judged; outline = THIS judge's own colour
          // SOLID session colour, NO border (the user 2026-06-18): the judge's own colour already lives on
          // the row's horizontal rail, so a per-bar outline just repeated it. "Running now" reads as a fully
          // opaque bar; a settled one is slightly dimmed — that's the only cue, no stroke.
          const r = el('rect', { x: x1, y: y - JBAR_H / 2, width: x2 - x1, height: JBAR_H, rx: 2.5,
            fill: col, 'fill-opacity': active ? 1 : 0.82, 'data-judge': J.key });
          svg.appendChild(r);
          const html = () => {
            const span = b.start === b.end ? clock(b.start) : clock(b.start) + '–' + clock(b.end);
            // elapsed (total judge compute) + tokens for this stretch, summed from each mark's matched run
            const ms = b.members.reduce((a, m) => a + (m.ms || 0), 0);
            const tin = b.members.reduce((a, m) => a + (m['in'] || 0), 0), tout = b.members.reduce((a, m) => a + (m['out'] || 0), 0);
            const usage = (ms || tin || tout) ? '<div style="opacity:.7;margin-top:3px">⏱ ' + fmtDur(ms) + ' · ' + fmtTokens(tin + tout) + ' tok</div>' : '';
            // the LITERAL API call window: when the prompt went out → when the response came back (seconds
            // precision; judge calls are seconds-scale), the earliest send and latest recv across this block.
            const sents = b.members.map((m) => m.sent).filter((x) => x != null), recvs = b.members.map((m) => m.recv).filter((x) => x != null);
            const api = (sents.length && recvs.length) ? '<div style="opacity:.7;margin-top:2px">API ' + clockS(Math.min.apply(null, sents)) + ' → ' + clockS(Math.max.apply(null, recvs)) + '</div>' : '';
            const rows = b.members.slice(-5).map((m) => '<div class="b" style="opacity:.85"><span class="k">' + esc(JUDGE_KIND[m.kind] || m.kind) + '</span> ' + esc((m.text || '').slice(0, 90)) + '</div>').join('');
            return '<div class="r"><span class="who" style="color:' + J.color + '">' + esc(J.key) + '</span><span class="ar">▸</span><span style="color:' + col + '">' + esc(nameOf(b.sid)) + '</span><span class="t">' + span + (b.members.length > 1 ? ' · ' + b.members.length : '') + '</span></div>' + usage + api + rows;
          };
          const hit = el('rect', { x: x1 - 2, y: y - JROW / 2, width: (x2 - x1) + 4, height: JROW, fill: 'transparent' }); hit.style.cursor = 'default';
          hit.addEventListener('mouseenter', (e) => this.showTip(html(), e));
          hit.addEventListener('mousemove', (e) => this.moveTip(e));
          hit.addEventListener('mouseleave', () => this.hideTip());
          svg.appendChild(hit);
        }
      });
      // (auto-nudge ⚡ marks were removed from the judge band entirely — the user 2026-06-23. An auto-nudge
      // still surfaces as a romp-logo dot on its own lane; the band is now judge run-spans only.)
    }

    // far-right ⟩⟩ jump-to-now button — only when held back off the live edge (unpinned)
    if (!this._pinned) this._drawNowButton(svg);
  }

  // hover bodies: the prompt DOT shows the MESSAGE caption — a gist of what the user ASKED — once the
  // captioner produces it (ready early, the moment the message lands), and falls back to the raw prompt
  // only in the intermediate before that caption exists (the user 2026-06-19). The activity BAR is the
  // WORK (t.summary — what the agent DID); the two are now separate captions, dot vs line.
  req(t) { return t.msgCaption ? esc(t.msgCaption) : (t.prompt ? esc(t.prompt.slice(0, 120)) : ''); }
  // activity-bar hover = what the agent DID: the work period's own caption (t.summary), or a readable
  // reply line (t.reply) if the kernel supplied one. Only when there's NO work caption yet do we fall
  // back to the request (the prompt) — "working on… <prompt>" in progress, else "request: <prompt>"
  // muted — so we never invent a result the summarizer hasn't produced.
  barBody(t, ongoing) {
    const work = t.reply ? esc(t.reply) : (t.summary ? esc(t.summary) : '');
    if (work) return '<div class="b">' + work + '</div>';
    const reqp = t.prompt ? esc(t.prompt.slice(0, 120)) : '';
    if (ongoing) return '<div class="b"><span style="opacity:.55;font-style:italic">working on: </span>' + (reqp || 'awaiting summary') + '</div>';
    return '<div class="b"><span style="opacity:.55;font-style:italic">request: </span>' + (reqp || '(no summary)') + '</div>';
  }
  body(s) { return s ? '<div class="b">' + s + '</div>' : ''; }
}

module.exports = { TimelinePanel, badgeFor, roundedPath, crossX, workAnchorOf, idleGaps, fmtSpan, dotLit, barLit, interpNow, shouldReanchorEdge, barEndT, dragAxis };
