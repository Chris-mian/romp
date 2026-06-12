// The romp VS Code extension — a THIN CLIENT of the romp web kernel.
//
// All host logic (transcript parsing, session mirroring, the feed fold, tmux
// driving, record-file IO) lives in the kernel (src/kernel/, run by
// bin/romp-serve). This extension only:
//   1. ensures a kernel is running (spawn-or-attach on the default port,
//      restarting a stale one once after a VSIX update),
//   2. hosts the two webview panels (chat + feed) and pipes their postMessage
//      traffic over the kernel's WebSocket protocol verbatim,
//   3. supplies the few genuinely CLIENT-side capabilities: opening files in
//      the editor, the OS file picker, the clipboard, external links, and
//      panel reveal/focus orchestration.
//
// The browser pages romp-serve serves are this same pipe minus VS Code — both
// front ends are clients of one kernel, sharing tabs with per-client focus.
import * as vscode from "vscode";
import * as fs from "fs";
import * as http from "http";
import * as os from "os";
import * as path from "path";
import { execFileSync, spawn } from "child_process";
import WebSocket from "ws";

const HOST = "127.0.0.1";
function kernelPort(): number {
  return Number(process.env.ROMP_SERVE_PORT) || 7433;
}

let ctx: vscode.ExtensionContext;
let extUri: vscode.Uri;
let panel: vscode.WebviewPanel | undefined;
let feedPanel: vscode.WebviewPanel | undefined;
let chatPipe: KernelPipe | undefined;
let feedPipe: KernelPipe | undefined;
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
    vscode.window.registerUriHandler({ handleUri: onDeepLink }),
    vscode.commands.registerCommand("rompChat.open", async () => {
      const had = !!panel;
      openPanel();
      const chatCol = panel?.viewColumn;
      openFeedPanel(true, chatCol !== undefined ? ((chatCol as number) + 1) as vscode.ViewColumn : undefined);
      try { await vscode.commands.executeCommand("trackchanges.timeline.focus"); } catch { /* not installed */ }
      panel?.reveal(panel.viewColumn ?? vscode.ViewColumn.Beside, false);
      if (had) toWebview({ type: "openPicker" });
    }),
    vscode.commands.registerCommand("rompChat.openFeed", () => openFeedPanel()),
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
  );
}

export function deactivate() {
  chatPipe?.dispose();
  feedPipe?.dispose();
}

// Post into the chat webview, deferring until its "ready" if it's still cold
// (a freshly-created webview silently drops postMessage).
function toWebview(msg: any) {
  if (!panel) return;
  if (chatPipe?.webviewReady) panel.webview.postMessage(msg);
  else pendingToWebview.push(msg);
}

// ---- the kernel: spawn-or-attach ----

function myVersion(): string {
  try { return String(JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8")).version || ""); }
  catch { return ""; }
}

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

function postShutdown(): Promise<void> {
  return new Promise((resolve) => {
    const req = http.request({ host: HOST, port: kernelPort(), path: "/shutdown", method: "POST", timeout: 1500 }, (res) => {
      res.resume();
      res.on("end", () => resolve());
    });
    req.on("timeout", () => { req.destroy(); resolve(); });
    req.on("error", () => resolve());
    req.end();
  });
}

// The real login-shell PATH (cached): the romp launchers live on the
// interactive shell's PATH, not on the extension host's minimal one.
let loginPath: string | null = null;
function loginShellPath(): string {
  if (loginPath !== null) return loginPath;
  const shell = process.env.SHELL || "/bin/zsh";
  try {
    loginPath = (execFileSync(shell, ["-lic", 'printf %s "$PATH"'], { timeout: 4000, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }) || "").trim();
  } catch { loginPath = ""; }
  return loginPath;
}

// Launch the kernel detached, by preference: $ROMP_SERVE_BIN → the romp
// checkout's bin/romp-serve (rebuilds a stale dist/kernel.js itself) → a
// `romp-serve` on the login PATH → the kernel.js bundled in this VSIX (run
// with VS Code's own node via ELECTRON_RUN_AS_NODE).
function spawnKernel() {
  const env: NodeJS.ProcessEnv = { ...process.env };
  const login = loginShellPath();
  if (login) env.PATH = login + ":" + (env.PATH || "");
  const candidates: Array<{ cmd: string; args: string[]; env: NodeJS.ProcessEnv }> = [];
  if (process.env.ROMP_SERVE_BIN) candidates.push({ cmd: process.env.ROMP_SERVE_BIN, args: [], env });
  const local = path.join(os.homedir(), "GitRepos", "romp", "bin", "romp-serve");
  try { if (fs.existsSync(local)) candidates.push({ cmd: local, args: [], env }); } catch { /* ignore */ }
  candidates.push({ cmd: "romp-serve", args: [], env });
  candidates.push({
    cmd: process.execPath,
    args: [ctx.asAbsolutePath(path.join("dist", "kernel.js"))],
    env: { ...env, ELECTRON_RUN_AS_NODE: "1" },
  });
  const tryNext = (i: number) => {
    if (i >= candidates.length) return;
    const c = candidates[i];
    try {
      const child = spawn(c.cmd, c.args, { detached: true, stdio: "ignore", env: c.env });
      child.on("error", () => tryNext(i + 1));
      child.unref();
    } catch { tryNext(i + 1); }
  };
  tryNext(0);
}

let ensuring: Promise<boolean> | null = null;
let restartedOnce = false;
function ensureKernel(): Promise<boolean> {
  if (ensuring) return ensuring;
  ensuring = (async () => {
    let h = await healthz();
    if (h.ok) {
      // A kernel from before the last VSIX install would silently serve old
      // behavior (the classic stale-host trap) — restart it once per session.
      const mine = myVersion();
      if (!restartedOnce && h.version && mine && h.version !== mine) {
        restartedOnce = true;
        await postShutdown();
        await new Promise((r) => setTimeout(r, 500));
      } else {
        return true;
      }
    }
    spawnKernel();
    for (let i = 0; i < 25; i++) {
      await new Promise((r) => setTimeout(r, 400));
      h = await healthz();
      if (h.ok) return true;
    }
    vscode.window.showErrorMessage("romp: couldn't start the kernel (romp-serve) — is romp installed?");
    return false;
  })();
  const p = ensuring;
  void p.finally(() => { if (ensuring === p) ensuring = null; });
  return p;
}

// ---- the pipe: one WebSocket per panel, postMessage in both directions ----

class KernelPipe {
  private ws: WebSocket | null = null;
  private queue: string[] = [];
  private alive = true;
  private everConnected = false;
  webviewReady = false;
  constructor(
    private app: "chat" | "feed",
    private onDown: (m: any) => void,
    private onReconnect: () => void,
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
    const ok = await ensureKernel();
    if (!this.alive) return;
    if (!ok) { setTimeout(() => void this.connect(), 5000); return; }
    const ws = new WebSocket(`ws://${HOST}:${kernelPort()}/ws?app=${this.app}`);
    this.ws = ws;
    ws.on("open", () => {
      if (!this.alive) { ws.close(); return; }
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
    "romp",
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
    // reveal side-effects ride along; the kernel does the real work
    if (m.type === "dotOpen") openFeedPanel(true);
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
    // opens/focuses the tab itself.
    if (m.type === "openSession") openPanel(false);
    else if (m.type === "showOnTimeline" && m.anchor === "prompt") openPanel(true);
    else if (m.type === "showAskPath" && m.locate !== false && !m.jump && !m.off) openPanel(true);
    pipe.send(m);
  });
  p.onDidDispose(() => {
    pipe.dispose();
    if (feedPipe === pipe) feedPipe = undefined;
    feedPanel = undefined;
  });
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
  <div id="winframe"></div>
  <div id="tabbar"><span id="tabs"></span></div>
  <div id="ledger" style="display:none"></div>
  <div id="content"></div>
  <div id="live-ask" style="display:none"></div>
  <div id="footer">
    <div id="statusline" class="statusline"></div>
    <div id="composer"><textarea id="composer-input" rows="1" placeholder="Message this session…  (⏎ send · ⇧⏎ newline)"></textarea><button id="composer-attach" title="Attach a file — inserts its path (drag-and-drop is intercepted by VS Code; use this or paste instead)" aria-label="Attach file">📎</button></div>
  </div>
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
  <div id="feed-head"></div>
  <div id="feed-list"></div>
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
