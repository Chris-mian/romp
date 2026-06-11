'use strict';

// Pure helpers for the romp dashboard view. No `obsidian` / DOM / Node
// dependencies so they can be unit-tested directly (see
// tests/romp-dashboard.test.mjs). The view layer (romp-dashboard.js)
// shells out to tmux and renders; everything decision-shaped lives here.
//
// Mirrors the terminal `scripts/romp-dashboard`: same tmux session vars,
// same state→label mapping, same duration formatting, same xterm-256
// identity colors (rendered as CSS hex instead of ANSI escapes).

// Basic 16-color xterm palette (indices 0–15).
const BASIC_16 = [
  '#000000', '#800000', '#008000', '#808000',
  '#000080', '#800080', '#008080', '#c0c0c0',
  '#808080', '#ff0000', '#00ff00', '#ffff00',
  '#0000ff', '#ff00ff', '#00ffff', '#ffffff',
];

// 6×6×6 color-cube level steps.
const CUBE_STEPS = [0, 95, 135, 175, 215, 255];

function toHex2(n) {
  const s = Math.max(0, Math.min(255, n)).toString(16);
  return s.length === 1 ? '0' + s : s;
}

// Map an xterm-256 color index to a CSS hex string.
function xterm256ToHex(n) {
  n = Number(n);
  if (!Number.isFinite(n) || n < 0 || n > 255) return null;
  if (n < 16) return BASIC_16[n];
  if (n < 232) {
    const c = n - 16;
    const r = CUBE_STEPS[Math.floor(c / 36)];
    const g = CUBE_STEPS[Math.floor((c % 36) / 6)];
    const b = CUBE_STEPS[c % 6];
    return '#' + toHex2(r) + toHex2(g) + toHex2(b);
  }
  const v = 8 + 10 * (n - 232); // grayscale ramp
  return '#' + toHex2(v) + toHex2(v) + toHex2(v);
}

// Resolve a tmux @identity-bg token to a CSS hex. Accepts:
//   - truecolor hex ("#179EE8") — the current romp palette is the exact
//     Obsidian colors, stored as hex; passed straight through.
//   - xterm-256 tokens ("colour33" / "color33" / "33") — the legacy
//     format, for any session not yet recolored; mapped via the cube.
// Returns null for empty / named / unrecognized tokens.
function identityHex(token) {
  if (!token) return null;
  const t = String(token).trim();
  if (/^#[0-9a-fA-F]{6}$/.test(t)) return t;
  const m = /^(?:colour|color)?(\d+)$/.exec(t);
  if (!m) return null;
  return xterm256ToHex(Number(m[1]));
}

// Perceptual idle fade: blend a color toward the surface bg until its LUMINANCE hits a uniform low
// target (bg luminance + FADE_TARGET), so every hue lands at the same perceived dimness — plain opacity
// leaves bright hues looking brighter. Shared algorithm with the timeline view + romp-chat-view; keep
// FADE_TARGET in sync across all three. bg = [r,g,b] of the surface.
const FADE_TARGET = 38;
function fadeHex(hex, bg) {
  if (!hex || hex[0] !== '#' || hex.length < 7) return hex;
  const n = parseInt(hex.slice(1, 7), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const lum = (x, y, z) => 0.2126 * x + 0.7152 * y + 0.0722 * z;
  const Lc = lum(r, g, b), Lb = lum(bg[0], bg[1], bg[2]), Lt = Lb + FADE_TARGET;
  if (Lc <= Lt) return hex;
  const t = Math.min(0.85, (Lc - Lt) / (Lc - Lb));
  const hx = (a, c) => Math.round(a * (1 - t) + c * t).toString(16).padStart(2, '0');
  return '#' + hx(r, bg[0]) + hx(g, bg[1]) + hx(b, bg[2]);
}

// Trim a trailing parenthetical from a model display name so the dashboard
// shows just the base name — "Opus 4.8 (1M context)" → "Opus 4.8".
// statusline.sh already strips this where it publishes @claude-model, but an
// idle session keeps its last-published value (its status line stops
// re-rendering), so we strip again here at display time to be safe.
function shortModel(name) {
  return String(name || '').replace(/\s*\([^)]*\)\s*$/, '').trim();
}

// Parse the raw stdout of:
//   tmux list-sessions -F '#{@romp}|#{session_name}|#{@claude-state}|...'
// into objects, keeping only romp-tagged sessions (@romp == "1") — the
// session name no longer carries a prefix, so the @romp flag is the marker.
//
// `model` / `effort` are published by the statusline script (the only
// place Claude exposes the live model display name + effort level); they
// stay '' for a session that hasn't rendered a status line yet, and
// effort stays '' for models that don't support the effort parameter.
// `summary` is a <=8-word phrase the romp-summarize.sh hook writes — your
// REQUEST while working, then the assistant's REPLY when done (empty until the
// first turn, or if disabled). `summaryKind` ('request' | 'reply' | '') drives
// its color in the view: turquoise for a request, gray for a reply.
// `contextPct` is the context-window fill % (also from statusline.sh); it's
// null until the session renders its first status line.
function parseSessions(raw) {
  const out = [];
  for (const line of String(raw || '').split('\n')) {
    if (!line.trim()) continue;
    const f = line.split('|');
    if (f[0] !== '1') continue;
    const name = f[1] || '';
    if (!name) continue;
    const sinceRaw = (f[3] || '').trim();
    const since = /^\d+$/.test(sinceRaw) ? Number(sinceRaw) : null;
    const ctxRaw = (f[11] || '').trim();
    const contextPct = /^\d+$/.test(ctxRaw) ? Number(ctxRaw) : null;
    // @session_created — epoch seconds when the tmux session was started.
    // Drives the dashboard's stable oldest-first ordering (see sortByCreated).
    const createdRaw = (f[12] || '').trim();
    const created = /^\d+$/.test(createdRaw) ? Number(createdRaw) : null;
    out.push({
      name,
      state: (f[2] || '').trim(),
      since,
      dir: (f[4] || '').trim(),
      idBg: (f[5] || '').trim(),
      idFg: (f[6] || '').trim(),
      model: shortModel(f[7]),
      effort: (f[8] || '').trim(),
      summary: (f[9] || '').trim(),
      summaryKind: (f[10] || '').trim(),
      contextPct,
      created,
      // Incoming peer-message badge (set by romp-postal _set_mail_badge); empty
      // when there's no pending/recent mail.
      mailFrom: (f[13] || '').trim(),
      mailBg: (f[14] || '').trim(),
      mailFg: (f[15] || '').trim(),
    });
  }
  return out;
}

// Context-window fill % → severity class for the dashboard's ctx cell,
// mirroring statusline.sh's green/yellow/red thresholds (<50 / 50–79 / ≥80).
// Anything non-numeric is treated as low.
function contextLevel(pct) {
  const n = Number(pct);
  if (!Number.isFinite(n)) return 'low';
  if (n >= 80) return 'high';
  if (n >= 50) return 'mid';
  return 'low';
}

// Classify what the summary cell should show, so "…" means ONLY "actively
// generating" and a real failure reads as an error (not perpetual motion):
//   'pending' → the hook's "…" placeholder, job still plausibly running.
//   'error'   → the hook flagged a failure (kind='error'), OR a "…" that has
//               lingered on a READY row well past the summarizer's worst case
//               (timeoutSecs) — i.e. a stuck/dead job.
//   'request' → your prompt (turquoise, while working).
//   'reply'   → what the assistant did (gray).
//   'empty'   → no summary (trivial turn / not started).
// `elapsedSecs` is the time since the session's state last changed.
function summaryState(summary, kind, state, elapsedSecs, timeoutSecs) {
  if (kind === 'error') return 'error';
  // "pending" is the hook's ASCII generating-signal (kind field). We also accept
  // a literal "…" summary as a legacy fallback. Either way: a generating row
  // that's been READY past the timeout is a stuck job → surface it as an error.
  if (kind === 'pending' || summary === '…') {
    const ready = state === 'waiting' || state === 'idle';
    if (ready && elapsedSecs != null && elapsedSecs > timeoutSecs) return 'error';
    return 'pending';
  }
  if (!summary) return 'empty';
  return kind === 'request' ? 'request' : 'reply';
}

// Sort rows by when each session was STARTED — oldest first (smallest
// @session_created on top, newest at the bottom). This is a stable order
// that doesn't reshuffle as sessions go active/idle (the old behavior sorted
// by @claude-state-since, so any activity jumped a row to the top). Rows with
// no creation time sink to the bottom. Returns a new array; input not mutated.
function sortByCreated(rows) {
  return [...rows].sort((a, b) => {
    const ac = a.created;
    const bc = b.created;
    if (ac == null && bc == null) return 0;
    if (ac == null) return 1;
    if (bc == null) return -1;
    return ac - bc;
  });
}

// Like sortByCreated, but STALE sessions (the grayed-out ones — no state change
// for longer than staleAfterSecs) sink to the bottom, with the active sessions
// kept on top in stable oldest-first order. A session with no `since` is treated
// as not-stale (we can't tell it's idle). Returns a new array; input not mutated.
function sortByActivity(rows, nowSecs, staleAfterSecs) {
  const isStale = (s) => (s.since != null && (nowSecs - s.since) > staleAfterSecs) ? 1 : 0;
  return [...rows].sort((a, b) => {
    const sa = isStale(a), sb = isStale(b);
    if (sa !== sb) return sa - sb;                 // active first, grayed-out to the bottom
    const ac = a.created, bc = b.created;          // within a group: stable oldest-first
    if (ac == null && bc == null) return 0;
    if (ac == null) return 1;
    if (bc == null) return -1;
    return ac - bc;
  });
}

// Claude lifecycle state → { label, kind }. `kind` drives the badge
// color class. Mirrors the terminal `scripts/romp-dashboard` case
// statement — keep the two in sync (idle is shown as READY too). The
// underlying tmux @claude-state values are unchanged ('waiting'/'idle');
// only the display label/color differs.
function mapState(state) {
  switch (state) {
    case 'working':    return { label: 'WORKING',  kind: 'working' };
    case 'waiting':    return { label: 'READY',    kind: 'ready' };
    case 'idle':       return { label: 'READY',    kind: 'ready' };
    case 'permission': return { label: 'AWAITING', kind: 'attention' };
    case 'compacting': return { label: 'COMPACTING', kind: 'compacting' };
    default:           return { label: '—',        kind: 'unknown' };
  }
}

// Compact elapsed-time string (45s / 12m / 3h / 2d). Null/negative → '—'.
function formatDuration(secs) {
  if (secs == null || !Number.isFinite(secs) || secs < 0) return '—';
  secs = Math.floor(secs);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

// Roll up the rows into the footer summary counts.
function summarize(rows) {
  let working = 0;
  let attention = 0;
  for (const r of rows) {
    const kind = mapState(r.state).kind;
    if (kind === 'working') working++;
    else if (kind === 'attention') attention++;
  }
  return { total: rows.length, working, attention };
}

// Abbreviate a leading home dir to '~'.
function shortenDir(dir, home) {
  if (!dir) return '';
  if (home && dir.startsWith(home)) return '~' + dir.slice(home.length);
  return dir;
}

module.exports = {
  xterm256ToHex,
  identityHex,
  fadeHex,
  shortModel,
  parseSessions,
  contextLevel,
  summaryState,
  sortByCreated,
  sortByActivity,
  mapState,
  formatDuration,
  summarize,
  shortenDir,
};
