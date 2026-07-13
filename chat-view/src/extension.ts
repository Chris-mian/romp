// The romp VS Code extension — a THIN CLIENT of the romp web kernel.
//
// All host logic (transcript parsing, session mirroring, the feed fold, tmux
// driving, record-file IO) lives in the kernel (bin/romp-kernel, spawned via
// bin/romp-serve). This extension only:
//   1. ensures a kernel is running (spawn-or-attach on the default port,
//      restarting a stale one once after a VSIX update),
//   2. hosts the four webview surfaces — chat + feed (editor panels) and
//      timeline + outline/fleet (native panel/sidebar views) — and pipes their
//      postMessage traffic over the kernel's WebSocket protocol verbatim,
//   3. supplies the few genuinely CLIENT-side capabilities: opening files in
//      the editor, the OS file picker, the clipboard, external links, and
//      panel reveal/focus orchestration.
//
// The browser pages the kernel serves are this same pipe minus VS Code — both
// front ends are clients of one kernel, sharing tabs with per-client focus.
import * as vscode from "vscode";
import * as http from "http";
import { execFile } from "child_process";
import WebSocket from "ws";
import { chatBody, FEED_BODY, FLEET_BODY, TIMELINE_BODY, ATTACH_TITLE_VSCODE } from "./page-skeleton";
import { ensureThenAttach } from "./kernel-attach";
import { routeViewMessage } from "./view-routing";
import { deriveStatus, freshNeedsYou, renderStatusBar, statusTooltipLines, FleetStatus } from "./fleet-status";
import { citeText, sessionsForWorkspace, SessionInfo } from "./workspace-sessions";
import { parsePorcelain } from "./session-diff";

const HOST = "127.0.0.1";

// Ports are CONFIGURABLE so different VS Code windows can attach to different kernels (each kernel
// scopes its own group of agents). Precedence: the VS Code setting (if set) → env var → default.
function cfgPort(key: "kernelPort" | "managerPort", env: string | undefined, dflt: number): number {
  const v = vscode.workspace.getConfiguration("romp").get<number>(key);
  if (typeof v === "number" && v > 0) return v;
  return Number(env) || dflt;
}
function kernelPort(): number { return cfgPort("kernelPort", process.env.ROMP_SERVE_PORT, 7433); }
function managerPort(): number { return cfgPort("managerPort", process.env.ROMP_MANAGER_PORT, 7432); }

let ctx: vscode.ExtensionContext;
let extUri: vscode.Uri;
let panel: vscode.WebviewPanel | undefined;
let feedPanel: vscode.WebviewPanel | undefined;
let chatPipe: KernelPipe | undefined;
let feedPipe: KernelPipe | undefined;
let timelinePipe: KernelPipe | undefined;
let fleetPipe: KernelPipe | undefined;
// Webview-cold replays: a deep link / picker-open that arrived before the chat
// webview signalled "ready" is re-sent when the ready flows past us.
let pendingToWebview: any[] = [];
// Resolver for an in-flight rompChat.pickSession() call (cross-extension picker).
type PickValue = { id: string; name: string } | { createNew: true };
let pendingPick: ((v: PickValue | undefined) => void) | null = null;

export function activate(context: vscode.ExtensionContext) {
  ctx = context;
  extUri = context.extensionUri;
  context.subscriptions.push(
    vscode.window.registerWebviewPanelSerializer("rompChat", {
      async deserializeWebviewPanel(webviewPanel) { wirePanel(webviewPanel); },
    }),
    vscode.window.registerWebviewPanelSerializer("rompFeed", {
      async deserializeWebviewPanel(webviewPanel) { wireFeedPanel(webviewPanel); },
    }),
    // Timeline + Outline are native VIEWS (bottom panel / sidebar by default —
    // the user can drag them anywhere), resolved lazily when first shown.
    vscode.window.registerWebviewViewProvider("rompTimeline",
      { resolveWebviewView: (v) => wireTimelineView(v) },
      { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.window.registerWebviewViewProvider("rompFleet",
      { resolveWebviewView: (v) => wireFleetView(v) },
      { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.window.registerUriHandler({ handleUri: onDeepLink }),
    vscode.commands.registerCommand("rompChat.open", async () => {
      const had = !!panel;
      openPanel();
      const chatCol = panel?.viewColumn;
      openFeedPanel(true, chatCol !== undefined ? ((chatCol as number) + 1) as vscode.ViewColumn : undefined);
      // Bring the timeline up without stealing focus from the chat panel.
      try { await vscode.commands.executeCommand("rompTimeline.focus", { preserveFocus: true }); } catch { /* view unavailable */ }
      panel?.reveal(panel.viewColumn ?? vscode.ViewColumn.Beside, false);
      if (had) toWebview({ type: "openPicker" });
    }),
    vscode.commands.registerCommand("rompChat.openFeed", () => openFeedPanel()),
    vscode.commands.registerCommand("rompChat.openTimeline", () => vscode.commands.executeCommand("rompTimeline.focus")),
    vscode.commands.registerCommand("rompChat.openFleet", () => vscode.commands.executeCommand("rompFleet.focus")),
    vscode.commands.registerCommand("rompChat.addSession", () => { openPanel(); toWebview({ type: "openPicker", pick: false }); }),
    vscode.commands.registerCommand("rompChat.pickSession", (arg?: unknown) =>
      pickSessionExternal(
        typeof arg === "string" ? { prompt: arg }
          : arg && typeof arg === "object" ? (arg as { prompt?: string; allowNew?: boolean })
          : {})),
    vscode.commands.registerCommand("rompChat.openAll", () => { openPanel(); chatPipe?.send({ type: "openAll" }); }),
    vscode.commands.registerCommand("rompChat.nextTab", () => panel?.webview.postMessage({ type: "nextTab" })),
    vscode.commands.registerCommand("rompChat.prevTab", () => panel?.webview.postMessage({ type: "prevTab" })),
    vscode.commands.registerCommand("rompChat.openCurrent", () => {
      const ed = vscode.window.activeTextEditor;
      if (ed && ed.document.fileName.endsWith(".jsonl")) {
        openPanel();
        chatPipe?.send({ type: "openTranscript", file: ed.document.fileName });
      } else {
        vscode.window.showWarningMessage("romp: open a .jsonl transcript first.");
      }
    }),
    vscode.commands.registerCommand("rompChat.citeInComposer", citeInComposer),
    vscode.commands.registerCommand("rompChat.openSessionWorktree", openSessionWorktree),
    vscode.commands.registerCommand("rompChat.diffSessionChanges", diffSessionChanges),
    // HEAD side of the session-diff editor: romp-git:/<rel>?<json {dir,rel}>
    vscode.workspace.registerTextDocumentContentProvider("romp-git", {
      provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
        try {
          const q = JSON.parse(uri.query);
          if (!q.rel) return Promise.resolve("");   // untracked: no HEAD side
          return gitIn(String(q.dir), ["show", `HEAD:${String(q.rel)}`]).catch(() => "");
        } catch { return Promise.resolve(""); }
      },
    }),
  );
  startFleetStatus(context);
}

export function deactivate() {
  // Attach-only: VS Code does NOT own the kernel (the `romp --on` manager does), so there's nothing to
  // reap here — closing/reloading VS Code just drops our attach; the kernel keeps running.
  chatPipe?.dispose();
  feedPipe?.dispose();
  timelinePipe?.dispose();
  fleetPipe?.dispose();
  statusPipe?.dispose();
}

// Post into the chat webview, deferring until its "ready" if it's still cold
// (a freshly-created webview silently drops postMessage).
function toWebview(msg: any) {
  if (!panel) return;
  if (chatPipe?.webviewReady) panel.webview.postMessage(msg);
  else pendingToWebview.push(msg);
}

// ---- the kernel: ENSURE-THEN-ATTACH (the manager owns it; we never spawn) ----
// VS Code does NOT spawn the kernel. It attaches to a manager-owned kernel on romp.kernelPort; if none
// is there, it asks the `romp --on` manager to ENSURE one (the manager spawns + owns it), waits for it,
// and attaches. A second front-end spawner would fight the manager for the port and re-create the
// invisible-orphan problem — so the only spawner is ever the manager (the user's 2026-06-13 ruling).
// The decision sequence lives in ./kernel-attach (headless-testable); ensureKernel just supplies the
// VS Code-flavoured deps (real healthz, a manager POST, real sleep) and turns failures into a toast.

function healthz(): Promise<{ ok: boolean; version?: string }> {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port: kernelPort(), path: "/healthz", timeout: 1500 }, (res) => {
      let body = "";
      res.on("data", (d) => (body += d));
      res.on("end", () => {
        try { const j = JSON.parse(body); resolve({ ok: !!j.ok, version: j.version ? String(j.version) : undefined }); }
        catch { resolve({ ok: false }); }
      });
    });
    req.on("timeout", () => { req.destroy(); resolve({ ok: false }); });
    req.on("error", () => resolve({ ok: false }));
  });
}

let ensuring: Promise<boolean> | null = null;
let notRunningWarned = false;
function ensureKernel(): Promise<boolean> {
  if (ensuring) return ensuring;
  ensuring = (async () => {
    const res = await ensureThenAttach({
      healthz: async () => (await healthz()).ok,
      ensureViaManager: () => askManagerEnsure(kernelPort()),
      delay: (ms) => new Promise((r) => setTimeout(r, ms)),
    });
    if (res.ok) { notRunningWarned = false; return true; }
    // Point the user at the fix, once (not on every panel mount / reconnect poll).
    if (!notRunningWarned) {
      notRunningWarned = true;
      const port = kernelPort();
      vscode.window.showErrorMessage(
        res.reason === "no-manager"
          ? `romp: no kernel on port ${port} and no manager on :${managerPort()} — start it with \`romp --on\` in a terminal.`
          : `romp: the manager couldn't bring up a kernel on port ${port} — is that port already in use? Check \`romp --status\`.`,
      );
    }
    return false;
  })();
  const p = ensuring;
  void p.finally(() => { if (ensuring === p) ensuring = null; });
  return p;
}

// POST the manager's /ensure?port=N so it spawns+owns a kernel there. Resolves true iff a manager
// answered (i.e. one is running) — we never spawn the kernel ourselves.
function askManagerEnsure(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.request(
      { host: HOST, port: managerPort(), path: `/ensure?port=${port}`, method: "POST", timeout: 4000 },
      (res) => { res.resume(); resolve((res.statusCode ?? 500) < 400); });
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.on("error", () => resolve(false));
    req.end();
  });
}

// ---- the pipe: one WebSocket per panel, postMessage in both directions ----

class KernelPipe {
  private ws: WebSocket | null = null;
  private queue: string[] = [];
  private alive = true;
  private everConnected = false;
  webviewReady = false;
  constructor(
    private app: "chat" | "feed" | "timeline" | "fleet",
    private onDown: (m: any) => void,
    private onReconnect: () => void,
    private onState?: (up: boolean) => void,
    // A passive pipe OBSERVES: it polls healthz and attaches when a kernel is
    // there, but never asks the manager to spawn one and never toasts — the
    // ambient status bar must not resurrect a kernel the user turned off.
    private passive = false,
  ) {
    void this.connect();
  }
  send(m: any) {
    const s = JSON.stringify(m);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(s);
    else this.queue.push(s);
  }
  private async connect() {
    if (!this.alive) return;
    const ok = this.passive ? (await healthz()).ok : await ensureKernel();
    if (!this.alive) return;
    if (!ok) { this.onState?.(false); setTimeout(() => void this.connect(), 5000); return; }
    // One window-group id per VS Code window: the kernel routes a feed click's
    // focus to THIS window's chat panel (same mechanism as the combined
    // browser page's panes).
    const ws = new WebSocket(`ws://${HOST}:${kernelPort()}/ws?app=${this.app}&wid=${encodeURIComponent(vscode.env.sessionId)}`);
    this.ws = ws;
    ws.on("open", () => {
      if (!this.alive) { ws.close(); return; }
      this.onState?.(true);
      if (this.everConnected) {
        // A reconnect after a kernel restart: the kernel lost this client's
        // state, so reload the webview — its fresh "ready" resyncs everything.
        this.queue = [];
        this.webviewReady = false;
        this.onReconnect();
      } else {
        this.everConnected = true;
        for (const s of this.queue) ws.send(s);
        this.queue = [];
      }
    });
    ws.on("message", (data) => {
      if (!this.alive) return;
      let m: any;
      try { m = JSON.parse(String(data)); } catch { return; }
      this.onDown(m);
    });
    const reconnect = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.onState?.(false);
      if (this.alive) setTimeout(() => void this.connect(), 1500);
    };
    ws.on("close", reconnect);
    ws.on("error", reconnect);
  }
  dispose() {
    this.alive = false;
    try { this.ws?.close(); } catch { /* ignore */ }
    this.ws = null;
  }
}

// ---- panels ----

function openPanel(preserveFocus = false) {
  if (panel) {
    panel.reveal(panel.viewColumn ?? vscode.ViewColumn.Beside, preserveFocus);
    return;
  }
  const p = vscode.window.createWebviewPanel(
    "rompChat",
    "romp chat",
    { viewColumn: vscode.ViewColumn.Beside, preserveFocus },
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
    },
  );
  wirePanel(p);
  vscode.commands.executeCommand("workbench.action.lockEditorGroup");
}

function wirePanel(p: vscode.WebviewPanel) {
  panel = p;
  p.webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
  };
  p.iconPath = vscode.Uri.joinPath(extUri, "media", "romp-swirl.svg");
  p.webview.html = buildHtml(p.webview);
  const pipe = new KernelPipe(
    "chat",
    (m) => {
      if (m.type === "kernelToast") { vscode.window.setStatusBarMessage(`romp: ${m.text}`, 5000); return; }
      p.webview.postMessage(m);
    },
    () => { pendingToWebview = []; p.webview.html = buildHtml(p.webview); },
  );
  chatPipe = pipe;
  p.webview.onDidReceiveMessage((m) => {
    if (!m) return;
    // CLIENT capabilities — VS Code does these locally; the browser shim has
    // its own versions. Everything else goes to the kernel verbatim.
    if (m.type === "openFile" && m.path) { openFileInEditor(String(m.path), m.line); return; }
    if (m.type === "openLink" && typeof m.href === "string") { openLink(String(m.href)); return; }
    if (m.type === "pickFile") { void pickFileForComposer(p); return; }
    if (m.type === "readClipboard") {
      vscode.env.clipboard.readText().then(
        (text) => p.webview.postMessage({ type: "clipboardText", text }),
        () => p.webview.postMessage({ type: "clipboardText", text: "" }));
      return;
    }
    if (m.type === "pickResult") { resolvePick(m.createNew ? { createNew: true } : m.id ? { id: String(m.id), name: String(m.name ?? "") } : undefined); return; }
    if (m.type === "ready") {
      pipe.webviewReady = true;
      pipe.send(m);
      for (const q of pendingToWebview.splice(0)) p.webview.postMessage(q);
      return;
    }
    const r = routeViewMessage("chat", m);
    if (r.revealFeed) openFeedPanel(r.revealFeed.preserveFocus);
    pipe.send(m);
  });
  p.onDidDispose(() => {
    pipe.dispose();
    if (chatPipe === pipe) chatPipe = undefined;
    panel = undefined;
    pendingToWebview = [];
    resolvePick(undefined);
  });
}

function openFeedPanel(preserveFocus = false, column?: vscode.ViewColumn) {
  if (feedPanel) {
    let col = feedPanel.viewColumn ?? vscode.ViewColumn.Beside;
    if (column !== undefined && feedPanel.viewColumn !== undefined && feedPanel.viewColumn === panel?.viewColumn)
      col = column;
    feedPanel.reveal(col, preserveFocus);
    return;
  }
  const p = vscode.window.createWebviewPanel(
    "rompFeed",
    "romp feed",
    { viewColumn: column ?? vscode.ViewColumn.Beside, preserveFocus },
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
    },
  );
  wireFeedPanel(p);
}

function wireFeedPanel(p: vscode.WebviewPanel) {
  feedPanel = p;
  p.webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
  };
  p.iconPath = vscode.Uri.joinPath(extUri, "media", "romp-swirl.svg");
  p.webview.html = buildFeedHtml(p.webview);
  const pipe = new KernelPipe(
    "feed",
    (m) => {
      if (m.type === "kernelToast") { vscode.window.setStatusBarMessage(`romp: ${m.text}`, 5000); return; }
      p.webview.postMessage(m);
    },
    () => { p.webview.html = buildFeedHtml(p.webview); },
  );
  feedPipe = pipe;
  p.webview.onDidReceiveMessage((m) => {
    if (!m) return;
    if (m.type === "ready") pipe.webviewReady = true;
    // Clicking into a session (or locating a card's chat turn) should bring
    // the CHAT panel forward — panel reveal is this host's job; the kernel
    // opens/focuses the tab itself. The rules live in view-routing.ts.
    const r = routeViewMessage("feed", m);
    if (r.revealChat) openPanel(r.revealChat.preserveFocus);
    pipe.send(m);
  });
  p.onDidDispose(() => {
    pipe.dispose();
    if (feedPipe === pipe) feedPipe = undefined;
    feedPanel = undefined;
  });
}

// ---- fleet status: the ambient status bar item + needs-you notifications ----
// One host-held feed pipe (independent of the feed panel, which may be closed)
// keeps the status bar live in every window: working / needs-you counts from
// the kernel's authoritative feed frames, "offline" while the socket is down.
// A needs-you card APPEARING is the one event worth a native notification —
// "interrupt only when the human is the bottleneck"; existing cards on
// (re)connect are status, not news, and never notify.

let statusPipe: KernelPipe | undefined;
let statusItem: vscode.StatusBarItem | undefined;
let statusSeen: Set<string> | null = null;   // needs-you itemIds already seen (null = baseline pending)
let statusOffline = true;
let lastStatus: FleetStatus | null = null;
let lastFrame: any = null;                   // last feed frame (tooltip detail)
let sessionDirs: SessionInfo[] = [];         // /sessions cache for the "this window" tooltip line
let statusCompKey = "";                      // fleet composition key: refetch dirs only when it changes

function startFleetStatus(context: vscode.ExtensionContext) {
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusItem.name = "romp";
  statusItem.command = "rompChat.open";
  context.subscriptions.push(statusItem);
  paintStatus();
  statusItem.show();
  statusPipe = new KernelPipe(
    "feed",
    (m) => onStatusFrame(m),
    () => { statusSeen = null; },              // kernel restarted: re-baseline, don't replay old asks
    (up) => {
      statusOffline = !up;
      if (!up) statusSeen = null;
      // No webview behind this pipe, so announce readiness ourselves — the
      // kernel pushes the full feed state in response.
      else statusPipe?.send({ type: "ready" });
      paintStatus();
    },
    true,                                      // passive: observe only, never spawn/toast
  );
}

function onStatusFrame(m: any) {
  const st = deriveStatus(m);
  if (!st) return;                             // ka frames and other chatter
  lastStatus = st;
  lastFrame = m;
  const { seen, fresh } = freshNeedsYou(statusSeen, m);
  statusSeen = seen;
  paintStatus();
  notifyNeedsYou(fresh);
  // Refresh the session→dir map only when the fleet's composition changes
  // (each frame is already an event; composition is the part the tooltip's
  // "this window" line depends on).
  const key = JSON.stringify([m.working || [], (m.asks || []).map((a: any) => a.itemId)]);
  if (key !== statusCompKey) {
    statusCompKey = key;
    void fetchSessions().then((s) => { sessionDirs = s; paintStatus(); });
  }
}

function paintStatus() {
  if (!statusItem) return;
  const r = renderStatusBar(statusOffline, lastStatus);
  statusItem.text = r.text;
  statusItem.backgroundColor = r.warn ? new vscode.ThemeColor("statusBarItem.warningBackground") : undefined;
  if (statusOffline) {
    statusItem.tooltip = "The romp kernel is unreachable — start it with `romp --on`.";
    return;
  }
  const lines = lastFrame ? statusTooltipLines(lastFrame) : [];
  const here = sessionsForWorkspace(sessionDirs, workspaceFolderPaths()).map((s) => s.name);
  if (here.length) lines.unshift(`This window: ${here.join(", ")}`);
  statusItem.tooltip = lines.join("\n") || "romp fleet";
}

function notifyNeedsYou(fresh: any[]) {
  if (!fresh.length) return;
  if (panel?.active) return;                   // already looking at the romp chat — the card is on screen
  const first = fresh[0];
  const msg = fresh.length === 1
    ? `romp: ${first.name} needs you — ${String(first.text || "").slice(0, 120)}`
    : `romp: ${fresh.length} sessions need you (${[...new Set(fresh.map((a) => a.name))].join(", ")})`;
  void vscode.window.showInformationMessage(msg, "Open").then((choice) => {
    if (choice !== "Open") return;
    openPanel(false);
    chatPipe?.send({ type: "openSession", id: String(first.sid) });
  });
}

// ---- native views (timeline + fleet/outline) ----
// WebviewViews resolve lazily when first shown and are re-resolved if the user
// drags them to another container — wire a fresh pipe each time. Same relay as
// the panels: the host holds the kernel WS, the webview never opens a socket.

function wireTimelineView(v: vscode.WebviewView) {
  timelinePipe?.dispose();
  timelinePipe = wireView(v, "timeline", buildTimelineHtml, (p) => { if (timelinePipe === p) timelinePipe = undefined; });
}

function wireFleetView(v: vscode.WebviewView) {
  fleetPipe?.dispose();
  fleetPipe = wireView(v, "fleet", buildFleetHtml, (p) => { if (fleetPipe === p) fleetPipe = undefined; });
}

function wireView(
  v: vscode.WebviewView,
  app: "timeline" | "fleet",
  build: (w: vscode.Webview) => string,
  onGone: (p: KernelPipe) => void,
): KernelPipe {
  v.webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
  };
  v.webview.html = build(v.webview);
  const pipe = new KernelPipe(
    app,
    (m) => {
      if (m.type === "kernelToast") { vscode.window.setStatusBarMessage(`romp: ${m.text}`, 5000); return; }
      v.webview.postMessage(m);
    },
    () => { v.webview.html = build(v.webview); },
  );
  v.webview.onDidReceiveMessage((m) => {
    if (!m) return;
    if (m.type === "ready") pipe.webviewReady = true;
    const r = routeViewMessage(app, m);
    if (r.revealChat) openPanel(r.revealChat.preserveFocus);
    if (r.openLinkLocally) openLink(r.openLinkLocally);
    if (r.forward) pipe.send(m);
  });
  v.onDidDispose(() => { pipe.dispose(); onGone(pipe); });
  return pipe;
}

// ---- workspace integration: sessions ↔ the folders this window has open ----

// The kernel's /sessions endpoint — the authoritative unified session list
// (id, name, dir per session). Empty on any failure; callers surface that.
function fetchSessions(): Promise<SessionInfo[]> {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port: kernelPort(), path: "/sessions", timeout: 2000 }, (res) => {
      let body = "";
      res.on("data", (d) => (body += d));
      res.on("end", () => {
        try {
          const j = JSON.parse(body);
          resolve(Array.isArray(j)
            ? j.map((s: any) => ({ id: String(s.id), name: String(s.name), dir: String(s.dir || "") }))
            : []);
        } catch { resolve([]); }
      });
    });
    req.on("timeout", () => { req.destroy(); resolve([]); });
    req.on("error", () => resolve([]));
  });
}

function workspaceFolderPaths(): string[] {
  return (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath);
}

function gitIn(dir: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile("git", ["-C", dir, ...args], { maxBuffer: 16 * 1024 * 1024 }, (err, stdout) => {
      if (err) reject(err);
      else resolve(stdout);
    });
  });
}

async function pickKernelSession(placeHolder: string): Promise<SessionInfo | undefined> {
  const sessions = await fetchSessions();
  if (!sessions.length) {
    vscode.window.showWarningMessage("romp: no sessions (is the kernel running? `romp --on`).");
    return undefined;
  }
  const folders = workspaceFolderPaths();
  const here = new Set(sessionsForWorkspace(sessions, folders).map((s) => s.id));
  const pick = await vscode.window.showQuickPick(
    sessions.map((s) => ({
      label: s.name,
      description: s.dir + (here.has(s.id) ? "  (this window)" : ""),
      session: s,
    })),
    { placeHolder },
  );
  return pick?.session;
}

// Insert the active file (with the selected line range) into the chat
// composer — the cheapest editor → agent handoff. Rides the same droppedPath
// message a file drop uses, so the composer treats both identically.
function citeInComposer() {
  const ed = vscode.window.activeTextEditor;
  if (!ed || ed.document.uri.scheme !== "file") {
    vscode.window.showWarningMessage("romp: open a file to cite it.");
    return;
  }
  const sel = ed.selection;
  // A selection ending at column 0 visually excludes that line.
  const endLine = sel.end.character === 0 && sel.end.line > sel.start.line ? sel.end.line : sel.end.line + 1;
  const text = citeText(ed.document.uri.fsPath, sel.start.line + 1, endLine, !sel.isEmpty);
  openPanel(true);
  toWebview({ type: "droppedPath", path: text });
}

async function openSessionWorktree() {
  const s = await pickKernelSession("Open a session's working directory");
  if (!s || !s.dir) return;
  if (sessionsForWorkspace([s], workspaceFolderPaths()).length) {
    vscode.window.showInformationMessage(`romp: ${s.name}'s directory is already open in this window (${s.dir}).`);
    return;
  }
  await vscode.commands.executeCommand("vscode.openFolder", vscode.Uri.file(s.dir), { forceNewWindow: true });
}

// Review what a session changed without leaving this window: pick a session,
// pick one of its uncommitted files, open the native diff (HEAD vs working).
async function diffSessionChanges() {
  const s = await pickKernelSession("Diff a session's uncommitted changes");
  if (!s || !s.dir) return;
  let files;
  try {
    files = parsePorcelain(await gitIn(s.dir, ["status", "--porcelain"]));
  } catch {
    vscode.window.showWarningMessage(`romp: ${s.dir} is not a git repository (or git failed).`);
    return;
  }
  if (!files.length) {
    vscode.window.showInformationMessage(`romp: ${s.name} has no uncommitted changes in ${s.dir}.`);
    return;
  }
  const pick = await vscode.window.showQuickPick(
    files.map((f) => ({ label: f.path, description: f.status, file: f })),
    { placeHolder: `${s.name}: uncommitted changes in ${s.dir}` },
  );
  if (!pick) return;
  const f = pick.file;
  const right = vscode.Uri.file(`${s.dir}/${f.path}`);
  const left = vscode.Uri.from({
    scheme: "romp-git",
    path: "/" + f.path,
    query: JSON.stringify({ dir: s.dir, rel: f.untracked ? null : f.renamedFrom || f.path }),
  });
  await vscode.commands.executeCommand("vscode.diff", left, right, `${f.path} — HEAD vs working (${s.name})`);
}

// ---- client capabilities ----

// Open a file (that a tool touched) in the real editor — in the main group,
// NOT the locked romp group beside it. {type:"openFile", path, line?} (1-based).
function openFileInEditor(file: string, line?: number) {
  try {
    const uri = vscode.Uri.file(file);
    const opts: vscode.TextDocumentShowOptions = { preview: true, viewColumn: vscode.ViewColumn.One };
    if (typeof line === "number" && line > 0) {
      const pos = new vscode.Position(line - 1, 0);
      opts.selection = new vscode.Range(pos, pos);
    }
    vscode.window.showTextDocument(uri, opts).then(undefined, () => {
      vscode.window.showWarningMessage(`romp: couldn't open ${file}`);
    });
  } catch { /* ignore */ }
}

// A link clicked inside a chat webview. Deep links addressed to THIS extension
// skip the OS round-trip; everything else goes to the OS.
function openLink(href: string) {
  let uri: vscode.Uri;
  try { uri = vscode.Uri.parse(href, true); } catch { return; }
  if (uri.scheme === "vscode" && uri.authority.toLowerCase() === "romp.romp-chat-view") { onDeepLink(uri); return; }
  vscode.env.openExternal(uri);
}

// The reliable way to get a file path into the composer: OS drags onto the
// webview are swallowed by the workbench's editor drop overlay, so the 📎
// button runs a native open dialog and inserts each picked path via the same
// droppedPath message an in-webview drop uses.
async function pickFileForComposer(p: vscode.WebviewPanel) {
  const picks = await vscode.window.showOpenDialog({
    canSelectMany: true,
    canSelectFiles: true,
    canSelectFolders: false,
    openLabel: "Insert path",
    title: "Attach file — inserts its path into the message",
  });
  if (!picks?.length) return;
  for (const uri of picks) p.webview.postMessage({ type: "droppedPath", path: uri.fsPath });
}

// External deep-link: vscode://romp.romp-chat-view/open?session=<id>&anchor=<uuid>.
// Reveal the panel, then let the kernel resolve the session (fork-aware) and
// focus/scroll this client.
function onDeepLink(uri: vscode.Uri) {
  const q = new URLSearchParams(uri.query);
  const session = (q.get("session") || "").trim();
  if (!session) {
    vscode.window.showWarningMessage("romp: deep-link is missing ?session=");
    return;
  }
  const preserveFocus = q.get("focus") === "0";
  openPanel(preserveFocus);
  chatPipe?.send({
    type: "deepLink",
    session,
    anchor: (q.get("anchor") || "").trim() || undefined,
    anchorT: Number(q.get("anchorT") || "") || undefined,
    anchorKind: (q.get("anchorKind") || "").trim() || undefined,
    compose: q.get("compose") === "1",
  });
}

// Cross-extension picker (vscode-trackchanges' Cmd+M): open the colored
// in-webview picker in "return the selection" mode.
function pickSessionExternal(opts: { prompt?: string; allowNew?: boolean } = {}): Promise<PickValue | undefined> {
  if (pendingPick) { pendingPick(undefined); pendingPick = null; }
  openPanel();
  return new Promise((resolve) => {
    pendingPick = resolve;
    toWebview({ type: "openPicker", pick: true, prompt: opts.prompt, allowNew: !!opts.allowNew });
  });
}

function resolvePick(v: PickValue | undefined) {
  if (pendingPick) { pendingPick(v); pendingPick = null; }
}

// ---- webview HTML (the bundles ship in the VSIX; the kernel pipe replaces
// the host logic, not the rendering) ----

function buildHtml(webview: vscode.Webview): string {
  const js = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "render.js"));
  const css = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "styles.css"));
  const n = nonce();
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${n}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="${css}" rel="stylesheet" />
  <title>romp</title>
</head>
<body>
${chatBody(ATTACH_TITLE_VSCODE)}
  <script nonce="${n}" src="${js}"></script>
</body>
</html>`;
}

function buildFeedHtml(webview: vscode.Webview): string {
  const js = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "feed.js"));
  const css = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "feed.css"));
  const n = nonce();
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${n}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="${css}" rel="stylesheet" />
  <title>romp feed</title>
</head>
<body>
${FEED_BODY}
  <script nonce="${n}" src="${js}"></script>
</body>
</html>`;
}

function buildTimelineHtml(webview: vscode.Webview): string {
  const js = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "timeline-main.js"));
  const css = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "timeline-pane.css"));
  const n = nonce();
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${n}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="${css}" rel="stylesheet" />
  <title>romp timeline</title>
</head>
<body>
${TIMELINE_BODY}
  <script nonce="${n}" src="${js}"></script>
</body>
</html>`;
}

function buildFleetHtml(webview: vscode.Webview): string {
  const js = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "fleet.js"));
  // styles.css first (the .ledger-* goal-tree styling), fleet-pane.css after it
  // (the page layout) — same order as the kernel's /fleet page.
  const cssBase = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "styles.css"));
  const cssPane = webview.asWebviewUri(vscode.Uri.joinPath(extUri, "dist", "fleet-pane.css"));
  const n = nonce();
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${n}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="${cssBase}" rel="stylesheet" />
  <link href="${cssPane}" rel="stylesheet" />
  <title>romp outline</title>
</head>
<body>
${FLEET_BODY}
  <script nonce="${n}" src="${js}"></script>
</body>
</html>`;
}

function nonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let s = "";
  for (let i = 0; i < 24; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return s;
}
