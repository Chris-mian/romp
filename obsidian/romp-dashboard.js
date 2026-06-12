'use strict';

// romp dashboard — a workspace-leaf view that mirrors the terminal
// `romp dashboard`, showing every Claude Code tmux session and what it's
// doing (working / ready / awaiting), live.
//
// Data source is the same tmux session variables the `romp` launcher and
// the tmux-status.sh hook maintain:
//   @claude-state, @claude-state-since, @claude-dir, @identity-bg/-fg
// We poll `tmux list-sessions` once a second (only while the pane is
// actually visible) and re-render. Pure decision logic lives in
// romp-logic.js; this file is the Obsidian + tmux glue.
//
// Desktop-only in practice (shells out to tmux). On mobile, or when tmux
// isn't installed, it renders a graceful message instead of crashing.

const { ItemView } = require('obsidian');
const logic = require('./romp-logic.js');

const VIEW_TYPE = 'romp-dashboard';
const STYLE_ID = 'romp-dashboard-styles';

// [r,g,b] of the surface a node sits on (Obsidian theme bg), for the perceptual idle-fade blend.
// Walks up for the first non-transparent background; dark fallback if none/headless.
function surfaceBg(node) {
  try {
    let n = node;
    while (n) {
      const c = (getComputedStyle(n).backgroundColor) || '';
      const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
      if (m && (m[4] === undefined || parseFloat(m[4]) > 0.05)) return [+m[1], +m[2], +m[3]];
      n = n.parentElement;
    }
  } catch (e) {}
  return [24, 24, 24];
}
const POLL_MS = 1000;
// Typing-indicator: this many dots, animated entirely in CSS (a staggered
// wave). CSS keyframes are robust to the dashboard's once-a-second full
// re-render and need no JS timer.
const DOT_COUNT = 4;
// A "…" placeholder that lingers on a READY row past this long is treated as a
// stuck/dead summarizer job and surfaced as an error, not perpetual motion.
// Comfortably beyond the summarizer's worst case (Haiku call + one retry).
const PENDING_TIMEOUT_SECS = 150;
// A session whose state hasn't changed in this long (no hook events —
// the tmux-status hook stamps @claude-state-since on every event) is
// treated as idle/stale: its row fades toward black (name/badge/time).
const STALE_AFTER_SECS = 3600; // 1 hour

// Absolute candidates first: Obsidian launched from the Dock has a
// stripped GUI PATH that usually lacks Homebrew, so a bare `tmux` often
// won't resolve. Bare `tmux` is the last-ditch fallback.
const TMUX_CANDIDATES = [
  '/opt/homebrew/bin/tmux',
  '/usr/local/bin/tmux',
  '/usr/bin/tmux',
  '/bin/tmux',
];

const TMUX_FORMAT =
  '#{@romp}|#{session_name}|#{@claude-state}|#{@claude-state-since}|#{@claude-dir}|#{@identity-bg}|#{@identity-fg}|#{@claude-model}|#{@claude-effort}|#{@claude-summary}|#{@claude-summary-kind}|#{@claude-context}|#{session_created}|#{@romp-mail-from}|#{@romp-mail-bg}|#{@romp-mail-fg}';

let _tmuxPath; // resolved once, cached across views/reloads

function resolveTmux() {
  if (_tmuxPath !== undefined) return _tmuxPath;
  _tmuxPath = 'tmux';
  try {
    const fs = require('fs');
    for (const p of TMUX_CANDIDATES) {
      if (fs.existsSync(p)) { _tmuxPath = p; break; }
    }
  } catch (e) { /* no fs (mobile) — fall through to bare 'tmux' */ }
  return _tmuxPath;
}

// Resolves to { rows, fatal }. Never rejects. `fatal` is a user-facing
// string when the dashboard genuinely can't run (no tmux binary / no
// child_process); null otherwise — an empty `rows` just means "no
// sessions" (e.g. no tmux server running yet).
function listSessions() {
  return new Promise((resolve) => {
    let execFile;
    try { ({ execFile } = require('child_process')); }
    catch (e) { resolve({ rows: [], fatal: 'romp dashboard needs a desktop Obsidian (no shell access here).' }); return; }

    execFile(
      resolveTmux(),
      ['list-sessions', '-F', TMUX_FORMAT],
      // Force a UTF-8 locale: Obsidian launched from the Dock inherits no LANG,
      // so the spawned tmux mangles multibyte chars (em-dashes, etc.) down to
      // "_". Pin UTF-8 + utf8 decoding so summaries come through intact.
      {
        timeout: 2000,
        windowsHide: true,
        encoding: 'utf8',
        env: Object.assign({}, process.env, {
          LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', LC_CTYPE: 'en_US.UTF-8',
        }),
      },
      (err, stdout) => {
        if (err) {
          if (err.code === 'ENOENT') {
            resolve({ rows: [], fatal: 'tmux not found. Install it (brew install tmux) to use the dashboard.' });
          } else {
            // Almost always "no server running on ..." — treat as empty.
            resolve({ rows: [], fatal: null });
          }
          return;
        }
        resolve({ rows: logic.parseSessions(stdout || ''), fatal: null });
      },
    );
  });
}

class RompDashboardView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this._busy = false;
  }

  getViewType() { return VIEW_TYPE; }
  getDisplayText() { return 'romp dashboard'; }
  getIcon() { return 'activity'; }

  async onOpen() {
    this.contentEl.addClass('romp');
    this.tick();                       // paint immediately
    this.registerInterval(window.setInterval(() => this.tick(), POLL_MS));
  }

  async onClose() {
    this.contentEl.empty();
  }

  // offsetParent is null when this leaf sits in a background tab
  // (display:none) — don't spawn a tmux process behind a hidden pane.
  _isVisible() {
    return !!this.contentEl.offsetParent;
  }

  async tick() {
    if (this._busy || !this._isVisible()) return;
    this._busy = true;
    try {
      const { rows, fatal } = await listSessions();
      this._render(rows, fatal);
    } catch (e) {
      console.error('[vault-code] romp dashboard tick failed:', e);
    } finally {
      this._busy = false;
    }
  }

  _render(rows, fatal) {
    const root = this.contentEl;
    root.empty();

    const now = Date.now();
    const nowSecs = Math.floor(now / 1000);

    // Intentionally no in-view header row (title + clock) — this pane is
    // a deliberately minimal strip. The session list / empty message is
    // the first thing rendered. Re-add a `romp-header` div here if
    // a title or live clock is wanted again.

    if (fatal) {
      root.createDiv({ cls: 'romp-empty', text: fatal });
      return;
    }

    if (!rows.length) {
      root.createDiv({ cls: 'romp-empty', text: 'No romp sessions running' });
      root.createDiv({ cls: 'romp-hint', text: 'Start one with  romp <name>  in a terminal.' });
      return;
    }

    const table = root.createDiv({ cls: 'romp-table' });
    const sbg = surfaceBg(table);   // surface color for the perceptual idle-fade blend (matches the timeline)
    // Active sessions on top in stable oldest-first order; stale (grayed-out)
    // sessions sink to the bottom — same threshold as the .is-stale fade below.
    for (const s of logic.sortByActivity(rows, nowSecs, STALE_AFTER_SECS)) {
      const st = logic.mapState(s.state);
      const rowEl = table.createDiv({ cls: 'romp-row' });

      // Idle > 1h → fade the row. The COLORED bits (name, mail badge) blend perceptually toward the
      // surface bg (logic.fadeHex), matching the timeline + chat tabs; the gray cells keep `.is-stale`
      // opacity (see CSS — name is excluded there so it isn't double-faded).
      const elapsedSecs = (s.since != null) ? (nowSecs - s.since) : null;
      const stale = elapsedSecs != null && elapsedSecs > STALE_AFTER_SECS;
      if (stale) rowEl.addClass('is-stale');

      // The session name carries the identity color (bold) — the old
      // colored dot is gone. Falls back to the default text color when
      // the session has no parseable identity color.
      const nameEl = rowEl.createSpan({ cls: 'romp-name', text: s.name });
      const hex = logic.identityHex(s.idBg);
      if (hex) nameEl.style.color = stale ? logic.fadeHex(hex, sbg) : hex;

      rowEl.createSpan({ cls: 'romp-badge is-' + st.kind, text: st.label });

      const elapsed = (elapsedSecs != null) ? logic.formatDuration(elapsedSecs) : '—';
      rowEl.createSpan({ cls: 'romp-time', text: elapsed });

      // Context-window usage % (published by statusline.sh). Traffic-light
      // color on the same <50 / 50–80 / ≥80 thresholds as the terminal
      // statusline. Blank until the session renders its first status line.
      const ctxEl = rowEl.createSpan({ cls: 'romp-ctx' });
      if (s.contextPct != null) {
        ctxEl.addClass('is-' + logic.contextLevel(s.contextPct));
        ctxEl.setText(s.contextPct + '%');
      }

      // Model display name + effort level (published by statusline.sh).
      // Empty until the session renders its first status line.
      rowEl.createSpan({ cls: 'romp-model', text: s.model || '—' });
      rowEl.createSpan({ cls: 'romp-effort', text: s.effort || '' });

      // Summary cell, by state — "…" means ONLY "generating", failures read red:
      //   pending  → animated typing dots (job running)
      //   error    → red "⚠ …" (failed/stuck job — flag it, don't fake activity)
      //   request  → your prompt (turquoise, while working)
      //   reply    → what the assistant did (gray)
      //   empty    → nothing (trivial turn / not started)
      // Takes the remaining width and ellipsis-truncates (CSS).
      const sumEl = rowEl.createSpan({ cls: 'romp-summary' });
      // Incoming peer-message badge (📬 + sender), in the SENDER's identity colour,
      // shown the moment mail arrives — before/independent of the Haiku summary,
      // which then fills in (after the "…") in the text span beside it. It lives
      // INSIDE the summary cell because the table is a fixed 7-column grid.
      if (s.mailFrom) {
        const mb = sumEl.createSpan({ cls: 'romp-mail', text: '📬 ' + s.mailFrom + ' ' });
        const mhex = logic.identityHex(s.mailBg);
        if (mhex) mb.style.color = stale ? logic.fadeHex(mhex, sbg) : mhex;
      }
      const txt = sumEl.createSpan({ cls: 'romp-sumtext' });
      const stt = logic.summaryState(s.summary, s.summaryKind, s.state, elapsedSecs, PENDING_TIMEOUT_SECS);
      if (stt === 'pending') {
        const dots = txt.createSpan({ cls: 'romp-dots' });
        for (let i = 0; i < DOT_COUNT; i++) dots.createSpan(); // CSS animates them
      } else if (stt === 'error') {
        sumEl.addClass('is-error');
        const msg = (s.summaryKind === 'error') ? (s.summary || 'summarizer error') : 'summarizer timed out';
        txt.setText('⚠ ' + msg);
      } else {
        txt.setText(s.summary || '');
        if (stt === 'request') sumEl.addClass('is-request');
      }
    }
  }
}

// (The in-process timeline view that used to live here was retired 2026-06-12:
// the timeline now reaches Obsidian through the romp web kernel — see
// romp-kernel-views.js, which registers the same 'romp-timeline' view
// type as an iframe onto the kernel's /timeline page. One data path, no
// duplicated plumbing; romp-timeline-view.js itself remains the SHARED
// renderer the kernel serves.)

const CSS = `
/* Maximally compact: collapse the whole in-leaf view-header for the romp
   pane — its title bar, nav arrows, and bookmark/⋯ actions — reclaiming
   ~30px. Scoped to this view type so other panes keep their header. The
   pane stays reachable via its "romp" tab in the strip above (right-click
   → Close, or the command palette); the green divider lives on the tab
   GROUP, not here, so it's unaffected. */
.workspace-leaf-content[data-type="${VIEW_TYPE}"] .view-header { display: none !important; }

/* Green divider along the very top of the romp bottom pane, so it reads
   as its own region (the default split divider is too dark to see). The
   border goes on the tab GROUP that holds the romp view (matched with
   :has), NOT the leaf content — the leaf content sits below the tab
   strip, so a border there draws under the "romp" tab. On the group it
   draws above the tab strip, at the true top edge. Uses the standard
   Vault section-palette green (--palette-2, #54B204), with a literal
   fallback in case the vault plugin isn't loaded to define it. */
.workspace-tabs:has(.workspace-leaf-content[data-type="${VIEW_TYPE}"]) {
  border-top: 2px solid var(--palette-2, #54B204) !important;
}

/* Tight padding so the pane is compact — Obsidian/theme default
   .view-content padding is ~12px top / 32px bottom, which left a big
   black band below the list. Scope to the view type + !important so it
   actually wins the cascade (a bare .romp rule lost to the theme). */
.workspace-leaf-content[data-type="${VIEW_TYPE}"] .view-content.romp {
  padding: 4px 10px 6px !important;
}
.romp { font-size: 15px; height: 100%; overflow: auto; }
/* The whole table is ONE grid so columns line up across every row. Each
   row is a subgrid spanning all 3 tracks, so the name column sizes to the
   LONGEST name across all rows and every badge starts at the same x (just
   right of it). (Per-row grids — the old approach — size each row's name
   column independently, so badges landed right after each own name.) */
.romp-table { display: grid; align-items: center; width: 100%;
  grid-template-columns: max-content max-content 48px max-content max-content max-content minmax(0, 1fr);
  column-gap: 10px; row-gap: 4px; }
.romp-row { display: grid; grid-template-columns: subgrid;
  grid-column: 1 / -1; align-items: center; }
/* Idle > 1h: dim the row's primary columns. The summary is deliberately
   EXCLUDED — it's already faded (--text-faint), so an extra 0.3 opacity on top
   makes it unreadable. */
/* .romp-name is NOT here — its identity color is perceptually faded inline (logic.fadeHex),
   so it must stay at full opacity to avoid double-fading. The gray/non-identity cells keep opacity. */
.romp-row.is-stale .romp-badge,
.romp-row.is-stale .romp-time,
.romp-row.is-stale .romp-ctx,
.romp-row.is-stale .romp-model,
.romp-row.is-stale .romp-effort { opacity: 0.3; }
/* Model display name + effort level — quieter than the session name so
   they read as trailing metadata. Effort is a tiny uppercase tag. */
/* Extra space before the model column so time and model read as separate
   groups (the grid's column-gap is otherwise uniform). ~two tabs' worth. */
.romp-model { color: var(--text-muted); white-space: nowrap;
  margin-left: 2rem; }
.romp-effort { color: var(--text-faint); font-size: 11px;
  font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
  white-space: nowrap; }
/* Summary phrase: takes the remaining width, single line, ellipsis-truncated
   when it doesn't fit (it's not critical info). Replies are faded gray; your
   requests are the faded dark-turquoise used throughout the vault (palette-4),
   so the two read apart at a glance. */
.romp-summary { color: var(--text-faint); min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* Incoming peer-message badge inside the summary cell: the sender's colour is
   applied inline; this keeps it on one line and bold so it reads as a tag, and
   (being first) it survives the cell's ellipsis truncation when the summary is long. */
.romp-mail { font-weight: 700; white-space: nowrap; }
.romp-summary.is-request { color: var(--palette-4, #4EA8A9); }
/* A failed/stuck summarizer reads as an error, not activity. */
.romp-summary.is-error { color: var(--text-error, #c0392b); font-size: 13px; }
/* Typing indicator (like a messaging app's "… is typing"): a row of dots that
   pulse in a staggered wave. Pure CSS @keyframes — robust to the once-a-second
   full re-render (each restart simply replays the wave, which reads as
   continuous) and needs no JS timer. vertical-align:middle keeps the dots on
   the text's centre line, not down at the baseline (which looked like "_"). */
.romp-dots { display: inline-flex; align-items: center; gap: 5px;
  vertical-align: middle; }
.romp-dots > span { width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-muted); display: inline-block;
  animation: romp-blink 1.1s infinite both ease-in-out; }
.romp-dots > span:nth-child(1) { animation-delay: 0s; }
.romp-dots > span:nth-child(2) { animation-delay: 0.18s; }
.romp-dots > span:nth-child(3) { animation-delay: 0.36s; }
.romp-dots > span:nth-child(4) { animation-delay: 0.54s; }
@keyframes romp-blink {
  0%, 70%, 100% { opacity: 0.25; transform: scale(0.8); }
  35%          { opacity: 1;    transform: scale(1.35); }
}
.romp-name { font-weight: 700; white-space: nowrap; }
/* justify-self: start keeps each badge shrunk to its text and pinned to
   the left edge of the (shared) badge column, so the labels read as a
   left-aligned column instead of stretching/centering. */
.romp-badge { font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
  padding: 1px 6px; border-radius: 4px; justify-self: start; white-space: nowrap; }
/* State semantics: working = yellow, ready = blue, awaiting = red. */
.romp-badge.is-working { color: #332600; background: #E0B020; }
.romp-badge.is-ready { color: #fff; background: #2b7fb8; }
.romp-badge.is-attention { color: #fff; background: #c0392b; }
.romp-badge.is-compacting { color: #fff; background: #c97a1e; }
.romp-badge.is-unknown { color: var(--text-muted); background: var(--background-modifier-border); }
.romp-time { color: var(--text-muted); text-align: right; font-variant-numeric: tabular-nums; }
/* Context-window usage %: traffic-light color on the same thresholds as
   statusline.sh — green <50, yellow 50–79, red ≥80. Empty cell until the
   session reports a percentage, so it just holds its column width then. */
.romp-ctx { font-size: 13px; white-space: nowrap; text-align: right;
  font-variant-numeric: tabular-nums; }
.romp-ctx.is-low { color: var(--palette-2, #54B204); }
.romp-ctx.is-mid { color: #e0b020; }
.romp-ctx.is-high { color: #c0392b; }
.romp-empty { color: var(--text-muted); padding: 8px 0 2px; }
.romp-hint { color: var(--text-faint); font-size: 13px; }
`;

function injectStyles() {
  if (typeof document === 'undefined' || document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}

// Open (or reveal) the dashboard in a pane at the bottom of the window.
// `getLeaf('split', 'horizontal')` splits the active root leaf along a
// horizontal divider, so the new pane sits underneath it spanning the
// width — the "bottom strip" position. If one already exists we just
// reveal it instead of stacking duplicates. (The timeline used to be a
// sibling tab here; it's its own kernel-backed view now — romp-kernel-views.js.)
async function openRompPane(plugin) {
  const ws = plugin.app.workspace;
  let dash = ws.getLeavesOfType(VIEW_TYPE)[0];
  if (!dash) {
    dash = ws.getLeaf('split', 'horizontal');
    await dash.setViewState({ type: VIEW_TYPE, active: true });
  }
  ws.revealLeaf(dash);
}

function register(plugin) {
  injectStyles();
  // Register the view synchronously in onload so a saved bottom-pane tab is
  // restored on reload (Cmd+R) without us re-opening it.
  plugin.registerView(VIEW_TYPE, (leaf) => new RompDashboardView(leaf, plugin));
  plugin.addCommand({
    id: 'vault-launch-romp-dashboard',
    name: 'Launch romp dashboard',
    callback: () => {
      openRompPane(plugin).catch((e) =>
        console.error('[vault-code] openRompPane failed:', e));
    },
  });
}

module.exports = {
  RompDashboardView,
  VIEW_TYPE,
  register,
  openRompPane,
};
