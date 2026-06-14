'use strict';

// romp-kernel-views — the romp chat / feed / timeline as INDEPENDENT Obsidian
// leaves, each an iframe onto the romp web kernel (bin/romp-serve, port 7433).
// No in-process rendering or data plumbing here: the kernel is the single UI
// host (same bundles + WebSocket protocol the VS Code thin client and the
// browser pages use), and Obsidian is just a third front end. The module
// ensure-then-attaches (asks the `romp on` manager to bring the kernel up if
// needed) exactly like the VS Code extension does.
//
// All three panes in one Obsidian window share a window-group id (?wid=), so
// cross-pane links work: a session-name click in the feed focuses the chat
// leaf beside it (the kernel routes focus by wid; the iframe posts a reveal
// hint this module turns into revealLeaf).

const { ItemView, Plugin } = require('obsidian');
const http = require('http');
// No child_process/fs/os/path: Obsidian never LAUNCHES the kernel itself — it asks the manager to (see ensureKernel).

const HOST = '127.0.0.1';
const PORT = Number(process.env.ROMP_SERVE_PORT) || 7433;
const MANAGER_PORT = Number(process.env.ROMP_MANAGER_PORT) || 7432;

const CHAT_VIEW_TYPE = 'romp-chat';
const FEED_VIEW_TYPE = 'romp-feed';
// Same type id the retired in-process timeline used, so saved layouts restore
// straight into the kernel-backed view.
const TIMELINE_VIEW_TYPE = 'romp-timeline';

const PANES = {
  chat: { type: CHAT_VIEW_TYPE, page: '/chat', title: 'romp chat', icon: 'message-square' },
  feed: { type: FEED_VIEW_TYPE, page: '/feed', title: 'romp feed', icon: 'list-todo' },
  timeline: { type: TIMELINE_VIEW_TYPE, page: '/timeline', title: 'romp timeline', icon: 'gantt-chart' },
};

// one window-group id per Obsidian session — every romp pane in this app
// instance links to the others
const WID = 'obs-' + Math.random().toString(36).slice(2, 10);

// ---- ensure-then-attach (the user 2026-06-13) ----
// Obsidian must NEVER spawn the kernel itself: a kernel it spawned would be an invisible orphan, and
// two front ends both spawning would fight over its lifetime. Instead it attaches to a manager-owned
// kernel on PORT; if none is there it asks the `romp on` manager to ENSURE one (the manager spawns +
// owns it), waits, and attaches — same model as the VS Code extension. If neither a kernel nor a
// manager is reachable, onOpen shows an error pointing at `romp on`.

function healthz() {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port: PORT, path: '/healthz', timeout: 1500 }, (res) => {
      let body = '';
      res.on('data', (d) => (body += d));
      res.on('end', () => { try { resolve(!!JSON.parse(body).ok); } catch (e) { resolve(false); } });
    });
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

// POST the `romp on` manager's /ensure?port=N so it spawns+owns a kernel there. Resolves true iff a
// manager answered (i.e. one is running) — Obsidian never spawns the kernel itself.
function ensureViaManager() {
  return new Promise((resolve) => {
    const req = http.request(
      { host: HOST, port: MANAGER_PORT, path: '/ensure?port=' + PORT, method: 'POST', timeout: 4000 },
      (res) => { res.resume(); resolve((res.statusCode || 500) < 400); });
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
    req.end();
  });
}

let ensuring = null;
function ensureKernel() {
  if (ensuring) return ensuring;
  ensuring = (async () => {
    // 1. Already serving on PORT? attach straight away (the common case once `romp on` is up).
    if (await healthz()) return true;
    // 2. None there — ask the manager to bring one up (it owns it). No manager → give up (onOpen errors).
    if (!(await ensureViaManager())) return false;
    // 3. Poll until the freshly-ensured kernel is serving (~5s), then attach.
    for (let i = 0; i < 25; i++) {
      await new Promise((r) => setTimeout(r, 200));
      if (await healthz()) return true;
    }
    return false;
  })();
  const p = ensuring;
  p.finally(() => { if (ensuring === p) ensuring = null; });
  return p;
}

// ---- the view: one class, parameterized by pane ----

class RompKernelView extends ItemView {
  constructor(leaf, pane) {
    super(leaf);
    this.pane = pane;   // one of PANES
  }

  getViewType() { return this.pane.type; }
  getDisplayText() { return this.pane.title; }
  getIcon() { return this.pane.icon; }

  async onOpen() {
    const el = this.contentEl;
    el.empty();
    el.setAttribute('style', 'padding:0;overflow:hidden;');
    const note = el.createDiv();
    note.setAttribute('style', 'padding:12px;color:var(--text-muted);font-size:12px;');
    note.textContent = 'connecting to the romp kernel…';
    const ok = await ensureKernel();
    note.remove();
    if (!ok) {
      const err = el.createDiv();
      err.setAttribute('style', 'padding:12px;color:var(--text-error);font-size:12px;');
      err.textContent = 'romp kernel not running — start it with `romp on` in a terminal, then reopen this pane. (Obsidian attaches to a kernel; it doesn’t launch one — only `romp on` does.)';
      return;
    }
    this._frame = el.createEl('iframe');
    this._frame.setAttribute('style', 'width:100%;height:100%;border:0;display:block;background:#1e1e1e;');
    this._frame.src = `http://${HOST}:${PORT}${this.pane.page}?wid=${WID}`;
  }

  async onClose() {
    this._frame = null;
    this.contentEl.empty();
  }
}

// ---- open/reveal helpers ----

async function openPane(plugin, key) {
  const pane = PANES[key];
  const ws = plugin.app.workspace;
  let leaf = ws.getLeavesOfType(pane.type)[0];
  if (!leaf) {
    // timeline keeps its old bottom-strip habit; chat/feed open as normal tabs
    // the user places with Obsidian's own windowing (drag out, split, pop out)
    leaf = key === 'timeline' ? ws.getLeaf('split', 'horizontal') : ws.getLeaf(true);
    await leaf.setViewState({ type: pane.type, active: true });
  }
  ws.revealLeaf(leaf);
}

function register(plugin) {
  for (const key of Object.keys(PANES)) {
    const pane = PANES[key];
    plugin.registerView(pane.type, (leaf) => new RompKernelView(leaf, pane));
    plugin.addCommand({
      id: 'vault-launch-romp-' + key,
      name: 'Launch romp ' + key,
      callback: () => { openPane(plugin, key).catch((e) => console.error('[vault-code] openPane failed:', e)); },
    });
  }
  // cross-pane reveal: an iframe whose page received a focus/openCard posts
  // {romp:'reveal', pane} to its parent window — surface that leaf.
  plugin.registerDomEvent(window, 'message', (e) => {
    const m = e && e.data;
    if (!m || m.romp !== 'reveal' || !PANES[m.pane]) return;
    const leaf = plugin.app.workspace.getLeavesOfType(PANES[m.pane].type)[0];
    if (leaf) plugin.app.workspace.revealLeaf(leaf);
  });
}

module.exports = { register, openPane, RompKernelView, CHAT_VIEW_TYPE, FEED_VIEW_TYPE, TIMELINE_VIEW_TYPE };
