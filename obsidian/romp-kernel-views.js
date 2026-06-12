'use strict';

// romp-kernel-views — the romp chat / feed / timeline as INDEPENDENT Obsidian
// leaves, each an iframe onto the romp web kernel (bin/romp-serve, port 7433).
// No in-process rendering or data plumbing here: the kernel is the single UI
// host (same bundles + WebSocket protocol the VS Code thin client and the
// browser pages use), and Obsidian is just a third front end. The module
// spawn-or-attaches the kernel exactly like the VS Code extension does.
//
// All three panes in one Obsidian window share a window-group id (?wid=), so
// cross-pane links work: a session-name click in the feed focuses the chat
// leaf beside it (the kernel routes focus by wid; the iframe posts a reveal
// hint this module turns into revealLeaf).

const { ItemView, Plugin } = require('obsidian');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync, spawn } = require('child_process');

const HOST = '127.0.0.1';
const PORT = Number(process.env.ROMP_SERVE_PORT) || 7433;

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

// ---- spawn-or-attach (mirrors chat-view/src/extension.ts) ----

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

let loginPath = null;
function loginShellPath() {
  if (loginPath !== null) return loginPath;
  const shell = process.env.SHELL || '/bin/zsh';
  try {
    loginPath = (execFileSync(shell, ['-lic', 'printf %s "$PATH"'], { timeout: 4000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }) || '').trim();
  } catch (e) { loginPath = ''; }
  return loginPath;
}

function spawnKernel() {
  const env = Object.assign({}, process.env);
  const login = loginShellPath();
  if (login) env.PATH = login + ':' + (env.PATH || '');
  const candidates = [];
  if (process.env.ROMP_SERVE_BIN) candidates.push(process.env.ROMP_SERVE_BIN);
  if (process.env.ROMP_DIR) candidates.push(path.join(process.env.ROMP_DIR, 'bin', 'romp-serve'));
  candidates.push(path.join(os.homedir(), 'GitRepos', 'romp', 'bin', 'romp-serve'));
  candidates.push('romp-serve');
  const tryNext = (i) => {
    if (i >= candidates.length) return;
    if (i < candidates.length - 1 && candidates[i] !== 'romp-serve') {
      try { if (!fs.existsSync(candidates[i])) { tryNext(i + 1); return; } } catch (e) { tryNext(i + 1); return; }
    }
    try {
      const child = spawn(candidates[i], [], { detached: true, stdio: 'ignore', env });
      child.on('error', () => tryNext(i + 1));
      child.unref();
    } catch (e) { tryNext(i + 1); }
  };
  tryNext(0);
}

let ensuring = null;
function ensureKernel() {
  if (ensuring) return ensuring;
  ensuring = (async () => {
    if (await healthz()) return true;
    spawnKernel();
    for (let i = 0; i < 25; i++) {
      await new Promise((r) => setTimeout(r, 400));
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
    note.textContent = 'starting the romp kernel…';
    const ok = await ensureKernel();
    note.remove();
    if (!ok) {
      const err = el.createDiv();
      err.setAttribute('style', 'padding:12px;color:var(--text-error);font-size:12px;');
      err.textContent = 'romp kernel unreachable — run `romp-serve` (or check that the romp checkout is at ~/GitRepos/romp / $ROMP_DIR).';
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
