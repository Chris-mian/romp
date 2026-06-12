import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { execSync, execFileSync, execFile, spawn } from "child_process";
import { newIncParser, feed, buildParsed, type IncParser, type ChatEvent } from "./transcript";
import { hydratePostal } from "./postal-spec";
import { parseAskPane } from "./askparse";

const PROJECTS = path.join(os.homedir(), ".claude", "projects");
const ROMP_STATE = path.join(
  process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
  "romp",
);
const ROMP_NAMES = path.join(ROMP_STATE, "names");
const ROMP_SUMMARIES = path.join(ROMP_STATE, "summaries");
// Shared, persisted tab/lane order (SID array, first = left-most tab) — the romp
// timeline (db_timeline) reads/writes the SAME file so tabs ↔ lanes stay in sync.
const SESSION_ORDER = path.join(ROMP_STATE, "session-order.json");
const POLL_MS = 800;

type ChipState = "working" | "ready" | "awaiting" | "idle" | "closed" | "compacting";
interface ChipColor { bg: string; fg: string; }
interface TmuxInfo { state: string; effort: string; model: string; ctx: string; since: string; summary: string; }
interface Session {
  id: string;
  file: string;
  name: string;
  color: ChipColor | null;
  lastSig: string;
  lastSince: number | null;
  lastState: ChipState | "";
  lastWorking: boolean;
  watcher?: fs.FSWatcher;
  debounce?: NodeJS.Timeout;
  closedTicks?: number;
  keepOpen?: boolean;           // deliberately-opened read-only tab — exempt from auto-close
  addedAt?: number;             // when the tab was opened (grace before auto-close eligibility)
  workingSince?: number | null; // frozen start (ms) of the current working burst
  parser?: IncParser;           // incremental transcript parser (accumulated DAG)
  offset?: number;              // bytes of the transcript already fed to parser
  askSig?: string;              // signature of the live picker last pushed (dedupes re-posts)
  ledgerSig?: string;           // signature of the digest/ledger last pushed (dedupes re-posts)
  firstSeen?: number;           // launch/earliest-activity epoch (transcript first line) — cached; tab sort key
  lastMetaSig?: string;         // model|effort|ctx|faded last pushed — a reopened/revived session's
                                // tmux vars land AFTER the tab opens, with no state change to ride on
  askComposerTicks?: number;    // consecutive composer-screen ticks while awaiting — heals a hookless
                                // picker's stranded "permission" state after it's answered
}

let extUri: vscode.Uri;
let ctx: vscode.ExtensionContext;
let panel: vscode.WebviewPanel | undefined;
// The "romp feed" panel — a sibling webview (separate viewType) opened beside the
// chat panel; a fleet-wide stream of deliverables. State lives near the feed code.
let feedPanel: vscode.WebviewPanel | undefined;
let feedReady = false;
let feedShowDismissed = false;
let feedSig = "";
let lastAskItems: AskItem[] = [];   // last computed fold, for the showAskPath handler
let focusOverlayItem: string | null = null;   // itemId whose DAG overlay is currently painted on the timeline (hover or double-click pin) — so clearing THAT card also clears the overlay
let timer: NodeJS.Timeout | undefined;
let lastStates: Map<string, TmuxInfo> | null = null;
const sessions = new Map<string, Session>();
// A deep-link focus (+scroll anchor) waiting for the webview to signal ready —
// set on a cold open, where messages posted before ready would be dropped.
let pendingFocus: { id: string; anchor?: string; anchorT?: number; anchorKind?: string; compose?: boolean } | null = null;
// Picker open requested before the webview was ready (cold open) — replayed in
// onReady. `pick` = "return the selection" mode (cross-extension) vs open-a-tab.
let pendingPickerOpen: { pick: boolean; prompt?: string; allowNew?: boolean } | null = null;
let webviewReady = false;
// Resolver for an in-flight rompChat.pickSession() call (cross-extension picker).
type PickValue = { id: string; name: string } | { createNew: true };
let pendingPick: ((v: PickValue | undefined) => void) | null = null;
// The chat's currently-open tab, published to ROMP_STATE/chat-active so the romp
// timeline can outline the matching lane.
let activeTab: { tid: string; name: string } | null = null;

export function activate(context: vscode.ExtensionContext) {
  extUri = context.extensionUri;
  ctx = context;
  // Restore the romp pane after a VS Code restart (otherwise it comes back black).
  context.subscriptions.push(
    vscode.window.registerWebviewPanelSerializer("rompChat", {
      async deserializeWebviewPanel(webviewPanel) {
        wirePanel(webviewPanel);
        restoreSessions();
      },
    }),
  );
  // Restore the romp feed pane after a restart, same as the chat pane.
  context.subscriptions.push(
    vscode.window.registerWebviewPanelSerializer("rompFeed", {
      async deserializeWebviewPanel(webviewPanel) {
        wireFeedPanel(webviewPanel);
      },
    }),
  );
  // External deep-link entry — the romp dashboard fires vscode://…/open?session=&anchor=.
  context.subscriptions.push(
    vscode.window.registerUriHandler({ handleUri: onDeepLink }),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("rompChat.open", async () => {
      const had = !!panel;
      openPanel();
      // The icon opens the whole romp surface: feed beside the chat (next
      // editor group over, created if needed) and the timeline in the bottom
      // panel (vscode-trackchanges' view; silently skipped if not installed).
      const chatCol = panel?.viewColumn;
      openFeedPanel(true, chatCol !== undefined ? ((chatCol as number) + 1) as vscode.ViewColumn : undefined);
      try { await vscode.commands.executeCommand("trackchanges.timeline.focus"); } catch { /* not installed */ }
      panel?.reveal(panel.viewColumn ?? vscode.ViewColumn.Beside, false); // focus ends on the chat
      if (had) post({ type: "openPicker" }); // re-click while open -> pick another
    }),
    vscode.commands.registerCommand("rompChat.openFeed", () => openFeedPanel()),
    vscode.commands.registerCommand("rompChat.addSession", () => openCustomPicker()),
    // Cross-extension: open the colored picker and resolve with the chosen
    // {id,name} (undefined if cancelled). Used by vscode-trackchanges' Cmd+M.
    vscode.commands.registerCommand("rompChat.pickSession", (arg?: unknown) =>
      pickSessionExternal(
        typeof arg === "string" ? { prompt: arg }
          : arg && typeof arg === "object" ? (arg as { prompt?: string; allowNew?: boolean })
          : {})),
    vscode.commands.registerCommand("rompChat.openAll", () => openAllRunning()),
    vscode.commands.registerCommand("rompChat.nextTab", () => post({ type: "nextTab" })),
    vscode.commands.registerCommand("rompChat.prevTab", () => post({ type: "prevTab" })),
    vscode.commands.registerCommand("rompChat.openCurrent", () => {
      const ed = vscode.window.activeTextEditor;
      if (ed && ed.document.fileName.endsWith(".jsonl")) {
        openPanel();
        addSession(ed.document.fileName);
      } else {
        vscode.window.showWarningMessage("romp: open a .jsonl transcript first.");
      }
    }),
  );
  timer = setInterval(tick, POLL_MS);
  context.subscriptions.push({ dispose: () => timer && clearInterval(timer) });
}

// One webview editor pane (with internal session sub-tabs), opened beside the
// current group and locked so files never push into it.
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
      localResourceRoots: [
        vscode.Uri.joinPath(extUri, "dist"),
        vscode.Uri.joinPath(extUri, "media"),
      ],
    },
  );
  wirePanel(p);
  vscode.commands.executeCommand("workbench.action.lockEditorGroup");
}

// Wire a panel — freshly created or restored after a restart — with its html,
// webview options, icon, and message handlers.
function wirePanel(p: vscode.WebviewPanel) {
  panel = p;
  webviewReady = false;
  p.webview.options = {
    enableScripts: true,
    localResourceRoots: [
      vscode.Uri.joinPath(extUri, "dist"),
      vscode.Uri.joinPath(extUri, "media"),
    ],
  };
  p.iconPath = vscode.Uri.joinPath(extUri, "media", "romp-swirl.svg");
  p.webview.html = buildHtml(p.webview);
  p.webview.onDidReceiveMessage((m) => {
    if (!m) return;
    if (m.type === "ready") onReady();
    else if (m.type === "addSession") openCustomPicker();
    else if (m.type === "createSession") createNewSession(String(m.name ?? ""));
    else if (m.type === "closeSession" && m.id) requestCloseTab(String(m.id));
    else if (m.type === "renameSession" && m.id && typeof m.name === "string") renameSession(String(m.id), String(m.name));
    else if (m.type === "requestSessions") post({ type: "sessionList", items: sessionPayload() });
    else if (m.type === "openSession" && m.id) openSessionById(m.id);
    else if (m.type === "openByName" && m.name) openByName(String(m.name));
    else if (m.type === "openAll") openAllRunning();
    else if (m.type === "openFile" && m.path) openFileInEditor(m.path, m.line);
    else if (m.type === "openLink" && typeof m.href === "string") openLink(String(m.href));
    // rail-dot fleet links: hover → timeline + feed highlight; click → feed card modal
    else if (m.type === "dotHover") onDotHover(m.sid ? String(m.sid) : null, m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
    else if (m.type === "dotOpen" && m.sid) onDotOpen(String(m.sid), m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
    else if (m.type === "dropFile" && typeof m.name === "string" && typeof m.b64 === "string") saveDroppedFile(String(m.name), String(m.b64));
    else if (m.type === "pickFile") pickFileForComposer();
    else if (m.type === "activeTab") setActiveTab(m.id ?? null);
    else if (m.type === "pickResult") resolvePick(m.createNew ? { createNew: true } : m.id ? { id: String(m.id), name: String(m.name ?? "") } : undefined);
    else if (m.type === "sendMessage" && m.id && m.text) sendMessageToTab(String(m.id), String(m.text));
    else if (m.type === "interrupt" && m.id) interruptSession(String(m.id));
    else if (m.type === "answerAsk" && m.id && typeof m.target === "number") answerAskPrompt(String(m.id), m.target);
    else if (m.type === "toggleAsk" && m.id && typeof m.target === "number") toggleAskOption(String(m.id), m.target);
    else if (m.type === "submitAsk" && m.id) submitMultiAsk(String(m.id));
    else if (m.type === "addCustomAsk" && m.id && typeof m.text === "string") addCustomAsk(String(m.id), m.text);
    else if (m.type === "cancelAsk" && m.id) cancelAsk(String(m.id));
    else if (m.type === "askText" && m.id && typeof m.text === "string") askSendText(String(m.id), m.text);
    // paste fallback for webview <input> fields: native Cmd+V never reaches
    // them (typing does) — the webview asks for the clipboard text instead.
    else if (m.type === "readClipboard") vscode.env.clipboard.readText().then((text) => post({ type: "clipboardText", text }), () => post({ type: "clipboardText", text: "" }));
    else if (m.type === "setModel" && m.id && typeof m.value === "string") setSessionMeta(String(m.id), "model", String(m.value));
    else if (m.type === "setEffort" && m.id && typeof m.value === "string") setSessionMeta(String(m.id), "effort", String(m.value));
    else if (m.type === "compactSession" && m.id) compactSession(String(m.id));
    else if (m.type === "reorderTabs" && Array.isArray(m.order)) writeSessionOrder(m.order.map(String));
    // ledger bullets drive the timeline like feed rows: hover → transient highlight,
    // click → locate (pan + openChat). The bullet id is the reply's romp-events id.
    else if (m.type === "ledgerHover") hoverTimeline(m.id ? [String(m.id)] : null);
    else if (m.type === "ledgerLocate" && m.id) focusTimeline(String(m.id), String(m.sid ?? ""), Number(m.t) || 0, undefined, "work");
    // a path-source pasted image: read it off disk → dataURL (cached) so the webview
    // can show a real thumbnail; null → it keeps the filename chip.
    else if (m.type === "imgRequest" && typeof m.path === "string") post({ type: "imgData", path: m.path, url: imgDataUrl(String(m.path)) });
    // landing diagnostics: the webview reports how every deep-link landing
    // resolved (exact pointer / refused wrong-kind pointer / time-near / gave
    // up) → locate-diag.jsonl, so "that click landed weird" is diagnosable
    // after the fact instead of unreproducible (the user's ask, 2026-06-10).
    else if (m.type === "locateDiag") appendLocateDiag(m);
  });
  p.onDidChangeViewState((e) => { if (e.webviewPanel.active) writeChatActive(); });
  p.onDidDispose(() => { panel = undefined; webviewReady = false; resolvePick(undefined); activeTab = null; writeChatActive(); });
}

function post(msg: any) { panel?.webview.postMessage(msg); }

// Pasted-image hydration. A user turn can carry a "path:<abs path>" image — Claude
// Code writes pastes to ~/.claude/image-cache/… and screenshots are pasted straight
// from disk (~/Downloads/…). The webview can't read arbitrary files, so it asks the
// host on demand; we read the file once, base64-encode it, and cache by path+mtime+
// size. Oversized / unknown-type / missing → null, and the webview keeps its compact
// "🖼 filename" chip as the fallback.
const IMG_MAX_BYTES = 8_000_000;            // ~8 MB raw cap (a Retina screenshot is well under this)
const IMG_MIME: { [ext: string]: string } = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".svg": "image/svg+xml",
};
const imgCache = new Map<string, string | null>();   // "<path>:<mtimeMs>:<size>" → dataURL | null
function imgDataUrl(p0: string): string | null {
  try {
    let p = p0;
    if (p.startsWith("~/")) p = path.join(os.homedir(), p.slice(2));
    if (!path.isAbsolute(p)) return null;             // a relative paste can't be resolved safely
    const mime = IMG_MIME[path.extname(p).toLowerCase()];
    if (!mime) return null;
    const st = fs.statSync(p);
    if (!st.isFile()) return null;
    const key = `${p}:${st.mtimeMs}:${st.size}`;
    if (imgCache.has(key)) return imgCache.get(key)!;
    if (st.size > IMG_MAX_BYTES) { imgCache.set(key, null); return null; }
    const url = `data:${mime};base64,${fs.readFileSync(p).toString("base64")}`;
    imgCache.set(key, url);
    return url;
  } catch { return null; }
}

// Open a file (that a tool touched) in the real editor — the shared
// open/navigate surface. Webview message shape: {type:"openFile", path, line?}
// (line is 1-based, optional). Opens in the main group, NOT the locked romp
// group beside it. vs_chat's transcript deep-link is layered on this surface.
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
  } catch {
    /* ignore */
  }
}

function onReady() {
  webviewReady = true;
  if (sessions.size === 0) {
    const recent = listSessions()[0];
    if (recent) addSession(recent.file);
  } else {
    for (const s of sessions.values()) postSession(s);
    // Restore focus to the tab the user was last on (if it survived the dead-prune).
    try {
      const active = ctx.workspaceState.get<string>("rompActiveTab");
      if (active && sessions.has(active)) post({ type: "focus", id: active });
    } catch { /* ignore */ }
  }
  // Apply the shared tab order (synced with the timeline) on (re)load.
  const ord = readSessionOrder();
  lastOrderSig = ord.join(",");
  post({ type: "tabOrder", order: ord });
  // Re-deliver a deep-link focus that was posted before the webview was ready.
  if (pendingFocus) {
    post({ type: "focus", id: pendingFocus.id, anchor: pendingFocus.anchor, anchorT: pendingFocus.anchorT, anchorKind: pendingFocus.anchorKind });
    if (pendingFocus.compose) post({ type: "focusComposer" });
    pendingFocus = null;
  }
  // Open the picker if it was requested while the panel was still cold.
  if (pendingPickerOpen) {
    post({ type: "openPicker", pick: pendingPickerOpen.pick, prompt: pendingPickerOpen.prompt, allowNew: pendingPickerOpen.allowNew });
    pendingPickerOpen = null;
  }
}

// Open the custom, identity-coloured in-webview session picker (the same "+"
// overlay), instead of the plain VS Code quick-pick.
function openCustomPicker() {
  openPanel();
  if (webviewReady) post({ type: "openPicker", pick: false });
  else pendingPickerOpen = { pick: false }; // show once the webview signals ready
}

// Cross-extension picker: open the colored session picker in "return the
// selection" mode and resolve with the chosen {id,name} (undefined if
// dismissed). Lets other extensions (vscode-trackchanges' Cmd+M) reuse the exact
// picker instead of a native quick-pick.
function pickSessionExternal(opts: { prompt?: string; allowNew?: boolean } = {}): Promise<PickValue | undefined> {
  if (pendingPick) { pendingPick(undefined); pendingPick = null; } // cancel any prior pick
  openPanel();
  return new Promise((resolve) => {
    pendingPick = resolve;
    if (webviewReady) post({ type: "openPicker", pick: true, prompt: opts.prompt, allowNew: !!opts.allowNew });
    else pendingPickerOpen = { pick: true, prompt: opts.prompt, allowNew: !!opts.allowNew };
  });
}

function resolvePick(v: PickValue | undefined) {
  if (pendingPick) { pendingPick(v); pendingPick = null; }
}

// The real login-shell PATH (cached). The romp launcher lives in a dir that's on the
// interactive shell's PATH but NOT on tmuxEnv()'s minimal one, so we probe it once.
let loginPath: string | null = null;
function loginShellPath(): string {
  if (loginPath !== null) return loginPath;
  const shell = process.env.SHELL || "/bin/zsh";
  try {
    loginPath = (execFileSync(shell, ["-lic", 'printf %s "$PATH"'], { timeout: 4000, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }) || "").trim();
  } catch { loginPath = ""; }
  return loginPath;
}
// env for launching `romp`: the tmux env (TMUX_TMPDIR → same server we read) with the
// login PATH prepended so the romp launcher itself is resolvable.
function launchEnv(): NodeJS.ProcessEnv {
  const env = tmuxEnv();
  const login = loginShellPath();
  if (login) env.PATH = login + ":" + (env.PATH || "");
  return env;
}

// "✛ New session" from the + picker: create a fresh detached romp session and open
// it as a tab here. The name comes from the picker's search box (validated there —
// no native input dialog). Mirrors vscode-trackchanges' createSession
// (romp --detach <name>), then waits for Claude to boot (its hook sets
// @claude-state) before opening the tab.
async function createNewSession(rawName: string) {
  openPanel();
  const name = rawName.trim();
  if (!name || !/^[A-Za-z0-9._-]+$/.test(name)) {
    vscode.window.showWarningMessage("romp: session names use letters, digits, . _ - only.");
    return;
  }
  const states0 = rompTmuxState();
  if (states0 && states0.has(name)) { vscode.window.showWarningMessage(`romp: a session named "${name}" already exists.`); openByName(name); return; }
  const folders = vscode.workspace.workspaceFolders || [];
  let cwd = folders.length ? folders[0].uri.fsPath : os.homedir();
  if (folders.length > 1) {
    const pick = await vscode.window.showWorkspaceFolderPick({ placeHolder: "Working directory for the new session" });
    if (!pick) return;
    cwd = pick.uri.fsPath;
  }
  vscode.window.setStatusBarMessage(`romp: creating "${name}"…`, 8000);
  const made = await new Promise<boolean>((resolve) => {
    execFile("romp", ["--detach", name], { cwd, env: launchEnv(), timeout: 20000 }, (err) => resolve(!err));
  });
  if (!made) { vscode.window.showWarningMessage(`romp: couldn't create session "${name}" — is the romp launcher on your PATH?`); return; }
  // wait for it to boot (hook sets @claude-state) and become resolvable, then open it
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 800));
    const states = rompTmuxState();
    if (states && states.has(name) && resolveDeepLink(name)) { openByName(name); return; }
  }
  vscode.window.showInformationMessage(`romp: "${name}" is starting — open it from the + picker once it appears.`);
}

// Publish the chat's active tab to ROMP_STATE/chat-active so the romp timeline
// can outline the open lane. Matched by tid (fork-safe); name is the fallback.
function setActiveTab(id: string | null) {
  if (id) {
    const name = sessions.get(id)?.name ?? rompMeta(id).name ?? id.slice(0, 8);
    activeTab = { tid: id, name };
  } else {
    activeTab = null;
  }
  try { ctx.workspaceState.update("rompActiveTab", id || undefined); } catch { /* ignore */ } // remember the focused tab across reloads
  writeChatActive();
}

function writeChatActive() {
  try {
    fs.writeFileSync(path.join(ROMP_STATE, "chat-active"), activeTab ? JSON.stringify(activeTab) : "");
  } catch { /* ignore */ }
}

// Deliver the composer's text to a session as its NEXT PROMPT (tmux paste, like
// trackchanges' "Message a Session"): the message becomes a turn in that
// session's conversation — which is what a chat composer should do.
function sendMessageToTab(id: string, text: string) {
  const body = text.trim();
  if (!body) return;
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) { vscode.window.showWarningMessage("romp: no session name to deliver to."); return; }
  sendToSession(name, body);
}

// The statusline's model/effort dropdowns: inject the matching slash command into
// the pane (Claude Code parses a pasted "/model …" / "/effort …" on submit, same
// as a typed one). Values are allowlisted — the webview only ever sends these, so
// anything else means a confused message, not a command to forward. Refused while
// a prompt is pending: the pane's keyboard belongs to the picker, and the pasted
// text + Enter would answer it instead.
const META_VALUES: Record<"model" | "effort", Set<string>> = {
  model: new Set(["fable", "opus", "sonnet", "haiku", "opusplan", "best", "default"]),
  effort: new Set(["low", "medium", "high", "xhigh", "max", "auto"]),
};
function setSessionMeta(id: string, kind: "model" | "effort", value: string) {
  if (!META_VALUES[kind].has(value)) return;
  const s = sessions.get(id);
  const name = s?.name ?? rompMeta(id).name;
  if (!name) return;
  if (s && chipState(s.name, lastStates, s.lastWorking) === "awaiting") {
    vscode.window.showWarningMessage(`romp: answer "${name}"'s pending prompt before changing the ${kind}.`);
    return;
  }
  sendToSession(name, `/${kind === "model" ? "model" : "effort"} ${value}`);
}

// The ctx battery's click → /compact, mirroring the timeline's battery click
// (same awaiting guard as setSessionMeta — a pending prompt owns the keyboard).
function compactSession(id: string) {
  const s = sessions.get(id);
  const name = s?.name ?? rompMeta(id).name;
  if (!name) return;
  if (s && chipState(s.name, lastStates, s.lastWorking) === "awaiting") {
    vscode.window.showWarningMessage(`romp: answer "${name}"'s pending prompt before compacting.`);
    return;
  }
  sendToSession(name, "/compact");
}

function tmuxArgs(extra: string[]): string[] {
  const sock = tmuxSocket();
  return sock ? ["-S", sock, ...extra] : extra;
}

// Ctrl+C from the prompt box → send ESC (not a literal C-c) into the session's pane.
// In Claude Code, Esc INTERRUPTS the current response (no kill); Ctrl+C is the EXIT
// key (twice = quits the program) — the user wants interrupt-only, so we send Esc.
function interruptSession(id: string) {
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) return;
  try { execFileSync("tmux", tmuxArgs(["send-keys", "-t", name, "Escape"]), { env: tmuxEnv(), timeout: 4000, encoding: "utf8" }); }
  catch { /* pane gone / not a live session */ return; }
  // Claude Code fires NO hook on an Esc interrupt, so the tmux @claude-state set by
  // ~/.claude/hooks/tmux-status.sh stays "working" until the next prompt — stranding
  // the chip, the feed working-dots, AND the timeline as if the session were still
  // running (the user saw a 10-min "work period" long after stopping it). We reset the
  // pane to idle ourselves once the interrupt settles. Re-assert at two delays to ride
  // out a late PostToolUse from the cancelled tool, then refresh the chip immediately.
  const tInt = Math.floor(Date.now() / 1000);
  for (const ms of [600, 2000]) setTimeout(() => { markPaneIdle(name, tInt); refreshStatusFor(id); }, ms);
  // A pre-first-token interrupt restores the prompt into the TUI's composer and
  // hides the turn; filterInterrupted mirrors that, but its just-sent age guard
  // (2.5s) can outlast the refreshes above when Ctrl+C follows the send almost
  // immediately. One more re-post after the guard expires catches that window.
  setTimeout(() => {
    const s = sessions.get(id);
    if (!s) return;
    const state = chipState(s.name, lastStates, s.lastWorking);
    if (RESTED.has(state)) repostEventsFor(s, state);
  }, 3200);
}

// Force a pane's @claude-state to idle (mirrors the Stop branch of tmux-status.sh:
// state + since + emoji, plus the transition the timeline reads for its intervals).
// Guarded: only clears a working/compacting state, and never clobbers a NEWER hook
// event (e.g. a fresh prompt sent right after the interrupt — since > the interrupt).
function markPaneIdle(name: string, notAfter: number) {
  const env = tmuxEnv();
  const T = (args: string[]): string => execFileSync("tmux", tmuxArgs(args), { env, timeout: 4000, encoding: "utf8" });
  try {
    const prev = T(["show", "-t", name, "-v", "@claude-state"]).trim();
    if (prev !== "working" && prev !== "compacting") return;
    const since = parseInt(T(["show", "-t", name, "-v", "@claude-state-since"]).trim(), 10);
    if (since && since > notAfter) return;   // a newer event fired → leave it alone
    const now = Math.floor(Date.now() / 1000);
    T(["set", "-t", name, "@claude-state", "waiting"]);
    T(["set", "-t", name, "@claude-state-since", String(now)]);
    T(["set", "-t", name, "@romp-emoji", "🔵"]);
    const sid = T(["show", "-t", name, "-v", "@romp-session-id"]).trim();
    if (sid) {
      const dir = path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"), "romp", "states");
      try { fs.mkdirSync(dir, { recursive: true }); fs.appendFileSync(path.join(dir, `${sid}.jsonl`), JSON.stringify({ t: now, state: "waiting" }) + "\n"); } catch { /* ignore */ }
    }
  } catch { /* pane gone */ }
}

// The displayed-meta dedupe key (pairs with Session.lastMetaSig): every status
// post carries these four, so every post site should stamp it.
function metaSigOf(name: string, states: Map<string, TmuxInfo> | null): string {
  return [modelOf(name, states), effortOf(name, states), ctxOf(name, states), fadedFor(name, states)].join("|");
}

// Re-read tmux state and push a status update for one session if its chip changed.
// Used to make an interrupt feel immediate without waiting for the next poll tick.
function refreshStatusFor(id: string) {
  const s = sessions.get(id);
  if (!s || !panel) return;
  lastStates = rompTmuxState();
  const state = chipState(s.name, lastStates, s.lastWorking);
  if (state === s.lastState) return;
  const wasBusy = s.lastState === "working" || s.lastState === "compacting";
  s.lastState = state;
  s.lastMetaSig = metaSigOf(s.name, lastStates);
  // an interrupt settling the session = the trailing turn may have been
  // restored to the composer — re-post events so its bubble disappears too
  if (wasBusy && RESTED.has(state)) { repostEventsFor(s, state); return; }
  post({ type: "status", id: s.id, status: { state, sinceEpoch: workingSinceMs(s, state, lastStates, s.lastSince), effort: effortOf(s.name, lastStates), model: modelOf(s.name, lastStates), ctx: ctxOf(s.name, lastStates), faded: fadedFor(s.name, lastStates) } });
}

function sendToSession(name: string, text: string) {
  const env = tmuxEnv();
  const T = (args: string[]): string =>
    execFileSync("tmux", tmuxArgs(args), { env, timeout: 4000, encoding: "utf8" });
  const BUF = "romp-chat-view";
  try {
    // exit copy-mode if the pane is scrolled, so the paste + Enter actually land
    try { if (T(["display-message", "-p", "-t", name, "#{pane_in_mode}"]).trim() === "1") T(["send-keys", "-t", name, "-X", "cancel"]); } catch { /* not in copy-mode */ }
    T(["set-buffer", "-b", BUF, text]);
    T(["paste-buffer", "-b", BUF, "-d", "-p", "-t", name]); // -p bracketed paste, -d delete buffer after
    // brief gap so the bracketed paste is fully received before Enter submits it
    setTimeout(() => { try { T(["send-keys", "-t", name, "Enter"]); } catch { /* ignore */ } }, 250);
  } catch {
    vscode.window.showWarningMessage(`romp: couldn't deliver to "${name}" — is it a live romp session?`);
  }
}

// Capture a session's visible tmux pane as plain text — used to read a pending
// picker that Claude Code hasn't written to the transcript yet.
function capturePane(name: string): string {
  try {
    return execFileSync("tmux", tmuxArgs(["capture-pane", "-p", "-t", name]), { env: tmuxEnv(), timeout: 3000, encoding: "utf8" });
  } catch { return ""; }
}

// The Claude Code composer (idle/working), NOT a pending prompt: its auto-mode /
// ctx status line. A real picker/permission screen REPLACES this footer, so its
// presence means "no structured prompt, just the message box".
function isComposerScreen(pane: string): boolean {
  return /⏵⏵|shift\s*\+\s*tab to cycle|auto mode (on|off)|\bctx:\s*\d+%/.test(pane);
}

// Capture + parse a session's pane and push the structured prompt to the webview
// (the webview renders the right widget per kind). A null parse while awaiting CAN
// mean a genuinely-unreadable prompt (→ show the ⚠ safeguard card) — but it also
// happens transiently when `@claude-state` lags behind a decline/cancel and the
// pane is just BLANK or the normal composer (verified: selecting "Chat about this"
// leaves state=permission for ~3s while the pane is empty). In that case DON'T
// raise the scary "answer in the terminal" warning — clear the live-ask so the
// normal composer shows. Deduped by sig.
function postLiveAskFor(s: Session) {
  const pane = capturePane(s.name);
  const parsed = parseAskPane(pane);
  if (!parsed && (!pane.trim() || isComposerScreen(pane))) {
    if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
    // HOOKLESS prompt answered: a picker that fired no hook (e.g. the /model
    // switch confirmation) fires none on dismissal either, so the "permission"
    // we painted below would strand the red chip forever. After the composer
    // has been back for a few consecutive ticks (riding out the ~3s transient
    // lag noted above, which real prompts' own hooks heal), reset the state.
    s.askComposerTicks = (s.askComposerTicks ?? 0) + 1;
    if (s.askComposerTicks >= 4) markPaneState(s.name, "waiting", ["permission"]);
    return;
  }
  s.askComposerTicks = 0;
  const sig = parsed ? parsed.sig : "TEXT";
  if (sig !== s.askSig) { s.askSig = sig; post({ type: "askLive", id: s.id, ask: parsed }); }
}

// HOOKLESS pickers. @claude-state only learns "permission" from the Notification
// hook, and Claude Code fires NO hook for TUI confirmations like the /model
// switch prompt — so such a session keeps its old chip and the chat view never
// even looked at its pane (the user's report, 2026-06-11). Probe live panes for
// a structured picker; on a hit, paint the pane awaiting in tmux — which heals
// EVERY consumer (chip, dashboard, timeline, feed) — and post the live ask now.
// Only a real parse counts (the footer/submit-row requirement in parseAskPane
// keeps ordinary numbered output from matching); the TEXT fallback card stays
// exclusive to hook-confirmed awaiting states.
let probeTick = 0;
function probeHooklessAsk(s: Session): boolean {
  const pane = capturePane(s.name);
  const parsed = parseAskPane(pane);
  if (!parsed) return false;
  s.askComposerTicks = 0;
  if (parsed.sig !== s.askSig) { s.askSig = parsed.sig; post({ type: "askLive", id: s.id, ask: parsed }); }
  markPaneState(s.name, "permission", ["waiting", "working", "idle", ""]);
  return true;
}

// For every awaiting session, push its pending prompt to the webview; clear it
// the moment the session stops awaiting. Non-awaiting live sessions get probed
// for hookless pickers — the active tab every tick, the rest every 4th tick
// (and any tick while their ask card is up, so it clears promptly).
function refreshLiveAsks() {
  probeTick++;
  for (const s of sessions.values()) {
    const st = chipState(s.name, lastStates, s.lastWorking);
    if (st === "awaiting") { postLiveAskFor(s); continue; }
    // Probe ONLY quiet sessions (2026-06-11 timeline_window incident): a WORKING
    // session cannot have a picker up — Claude is running — but its pane is full
    // of arbitrary output, and a parser false-positive here painted "permission"
    // over a live turn (then flapped against PostToolUse for minutes). Hookless
    // pickers only ever appear on a session that looks ready/idle.
    if ((st === "ready" || st === "idle") && (s.id === activeTab?.tid || s.askSig || probeTick % 4 === 0)) {
      if (probeHooklessAsk(s)) continue;
    }
    if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
  }
}

// Set a pane's @claude-state (with emoji + since + the states-log line the
// timeline reads), but ONLY from one of the expected prior states — never
// clobbering a newer hook-set value. Mirrors markPaneIdle's guards.
function markPaneState(name: string, to: string, fromStates: string[]) {
  const env = tmuxEnv();
  const T = (args: string[]): string => execFileSync("tmux", tmuxArgs(args), { env, timeout: 4000, encoding: "utf8" });
  try {
    const prev = T(["show", "-t", name, "-v", "@claude-state"]).trim();
    if (prev === to || !fromStates.includes(prev)) return;
    const now = Math.floor(Date.now() / 1000);
    T(["set", "-t", name, "@claude-state", to]);
    T(["set", "-t", name, "@claude-state-since", String(now)]);
    T(["set", "-t", name, "@romp-emoji", to === "permission" ? "🔴" : "🔵"]);
    const sid = T(["show", "-t", name, "-v", "@romp-session-id"]).trim();
    if (sid) {
      const dir = path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"), "romp", "states");
      try { fs.mkdirSync(dir, { recursive: true }); fs.appendFileSync(path.join(dir, `${sid}.jsonl`), JSON.stringify({ t: now, state: to }) + "\n"); } catch { /* ignore */ }
    }
  } catch { /* pane gone */ }
}

// Send a key/text sequence into a session's pane (exits copy-mode first so the
// keys land). The callback gets the tmux runner + session name.
function sendToPane(id: string, fn: (T: (args: string[]) => string, name: string) => void): void {
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) return;
  const env = tmuxEnv();
  const T = (args: string[]): string => execFileSync("tmux", tmuxArgs(args), { env, timeout: 4000, encoding: "utf8" });
  try {
    try { if (T(["display-message", "-p", "-t", name, "#{pane_in_mode}"]).trim() === "1") T(["send-keys", "-t", name, "-X", "cancel"]); } catch { /* not in copy-mode */ }
    fn(T, name);
  } catch {
    vscode.window.showWarningMessage(`romp: couldn't drive "${name}" — is it a live romp session?`);
  }
}
// Re-mirror a session shortly after we drive it, so the panel reflects the new
// screen/checkbox state without waiting for the next 800ms tick.
function remirrorSoon(id: string, ms = 220) {
  const s = sessions.get(id);
  if (s) setTimeout(() => { try { postLiveAskFor(s); } catch { /* ignore */ } }, ms);
}

type ParsedAskResult = ReturnType<typeof parseAskPane>;
// Send a key sequence into the pane (one atomic send-keys). NOTE: only ever batch
// NAVIGATION keys — batching nav + an action key (Space/Enter) makes the action
// apply to the PRE-nav cursor (verified against the TUI). So nav and the action
// key are always separate, gated by whenReady below.
function keySeq(id: string, keys: string[]) {
  if (keys.length) sendToPane(id, (T, name) => T(["send-keys", "-t", name, ...keys]));
}
// Poll the pane (up to tries × gap ms) until `ready(parsed)`, then run `act`. This
// confirms the cursor/screen actually landed before we fire the action key, so we
// never toggle the wrong row or hit Enter on a screen still mid-transition.
function whenReady(id: string, ready: (p: ParsedAskResult) => boolean, act: () => void, tries = 8, gap = 80) {
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) return;
  const step = (left: number) => {
    let p: ParsedAskResult = null;
    try { p = parseAskPane(capturePane(name)); } catch { /* ignore */ }
    if (ready(p)) { act(); return; }
    if (left > 0) setTimeout(() => step(left - 1), gap);
  };
  step(tries);
}

// Navigate the picker cursor to `target` ONE arrow key at a time, re-confirming
// the cursor after each press before sending the next. The TUI DROPS rapidly-
// batched arrow keys (verified empirically: 4 Downs in a single send-keys move
// the cursor only ONE row), so the old batched navKeysFor() never reached a far
// option — most visibly "Chat about this", the LAST option, which needs the most
// steps and so failed every time. Each iteration re-captures, so a dropped key is
// simply re-sent on the next tick (self-correcting). Aborts (without acting) if
// the screen changes kind or the budget runs out; waits out a transient
// unreadable cursor rather than pressing blind. Runs `act` once cursor === target.
function stepNavTo(id: string, target: number, kindOk: (p: ParsedAskResult) => boolean, act: () => void, budget = 16) {
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) return;
  let p: ParsedAskResult = null;
  try { p = parseAskPane(capturePane(name)); } catch { /* ignore */ }
  if (!p || !kindOk(p)) return;                    // wrong/changed screen → abort
  if (budget <= 0) return;
  if (!p.cursorFound) { setTimeout(() => stepNavTo(id, target, kindOk, act, budget - 1), 110); return; } // unreadable → wait, don't press blind
  if (p.cursor === target) { act(); return; }
  keySeq(id, [p.cursor < target ? "Down" : "Up"]); // one step toward target (numbers track display order)
  setTimeout(() => stepNavTo(id, target, kindOk, act, budget - 1), 110);
}

// Single-select pick (and the submit-review screen's Submit/Cancel choice):
// navigate to the target row, CONFIRM the cursor landed, then Enter. Aborts on a
// multi-select selection screen (those toggle) or an unreadable cursor.
function answerAskPrompt(id: string, target: number) {
  const parsed = parseAskPane(capturePane(sessions.get(id)?.name ?? rompMeta(id).name ?? ""));
  if (!parsed || parsed.kind === "multi" || !parsed.cursorFound) return;
  // step to the target one key at a time (single-select OR the submit-review
  // screen's Submit/Cancel rows — kind stays non-"multi" throughout), then Enter.
  stepNavTo(id, target, (p) => !!p && p.kind !== "multi", () => keySeq(id, ["Enter"]));
  remirrorSoon(id, 450);
}

// Multi-select: toggle the target option (navigate to it, CONFIRM the cursor
// landed on that row, then Space).
function toggleAskOption(id: string, target: number) {
  const parsed = parseAskPane(capturePane(sessions.get(id)?.name ?? rompMeta(id).name ?? ""));
  if (!parsed || parsed.kind !== "multi" || !parsed.cursorFound) return;
  stepNavTo(id, target, (p) => !!p && p.kind === "multi", () => keySeq(id, ["Space"]));
  remirrorSoon(id, 450);
}

// Multi-select submit: from the selection screen → cross to the Submit tab (→),
// WAIT until the review screen is actually showing, land the cursor on "Submit
// answers", then Enter; from the review screen → straight to that.
function submitMultiAsk(id: string) {
  const name = sessions.get(id)?.name ?? rompMeta(id).name ?? "";
  const parsed = parseAskPane(capturePane(name));
  if (!parsed) return;
  const commit = () => {
    const p = parseAskPane(capturePane(name));
    if (!p || p.kind !== "submit") return;
    const sub = p.options.find((o) => /submit\b/i.test(o.label)) || p.options[0];
    stepNavTo(id, sub.n, (q) => !!q && q.kind === "submit", () => keySeq(id, ["Enter"]));
  };
  if (parsed.kind === "multi") {
    // Park the cursor on the FIRST option (a plain checkbox row) before crossing
    // tabs — if it's on the "Type something" text row, Right edits text instead of
    // navigating (the exact reason Submit failed after a custom answer).
    const first = parsed.options[0]?.n ?? 1;
    stepNavTo(id, first, (p) => !!p && p.kind === "multi", () => {
      keySeq(id, ["Right"]);                                 // cross to the Submit tab
      whenReady(id, (p) => !!p && p.kind === "submit", commit); // commit once the review screen is up
    });
  } else if (parsed.kind === "submit") {
    commit();
  }
  remirrorSoon(id, 700);
}

// Custom answer: drive the TUI's "Type something" slot. Navigate to it, confirm
// the cursor landed, then type. VERIFIED sequences:
//  • multi-select: typing alone is only a PROVISIONAL edit (discarded if you
//    navigate away); Enter COMMITS the text as a real option but toggles it OFF;
//    Space re-checks it — so it lands committed AND selected.
//  • single-select (incl. each tab of the multi-QUESTION wizard): typing on the
//    slot replaces its label inline; Enter commits it as this question's answer
//    (and advances to the next tab). No Space — Enter already picked.
function addCustomAsk(id: string, text: string) {
  if (!text.trim()) return;
  const name = sessions.get(id)?.name ?? rompMeta(id).name ?? "";
  const parsed = parseAskPane(capturePane(name));
  if (!parsed || parsed.kind === "submit") return;
  const slot = parsed.options.find((o) => /^\s*type something/i.test(o.label));
  if (!slot) return;
  const kind = parsed.kind;
  stepNavTo(id, slot.n, (p) => !!p && p.kind === kind, () => {
    sendToPane(id, (T, nm) => T(["send-keys", "-t", nm, "-l", text])); // type the text
    setTimeout(() => keySeq(id, ["Enter"]), 170);                       // commit (multi: toggles OFF; single: answers)
    if (kind === "multi") setTimeout(() => keySeq(id, ["Space"]), 350); // multi only: re-check it so it's selected
  });
  remirrorSoon(id, 650);
}

// Cancel the whole prompt (Esc).
function cancelAsk(id: string) {
  sendToPane(id, (T, name) => T(["send-keys", "-t", name, "Escape"]));
  remirrorSoon(id, 260);
}

// Free-text answer ("Type something."): type the text, then Enter.
function askSendText(id: string, text: string) {
  if (!text) return;
  sendToPane(id, (T, name) => {
    T(["send-keys", "-t", name, "-l", text]);
    setTimeout(() => { try { T(["send-keys", "-t", name, "Enter"]); } catch { /* ignore */ } }, 120);
  });
  remirrorSoon(id, 260);
}

// Open a tab for every currently-running (live tmux @romp) session.
function openAllRunning() {
  openPanel();
  const states = rompTmuxState();
  const runningNames = new Set(states ? Array.from(states.keys()) : []);
  const transcripts = scanTranscripts();
  // One tab per running NAME (the most recent transcript for it), not every
  // historical id that ever used that name.
  const best = new Map<string, { file: string; mtime: number }>();
  for (const id of rompIds()) {
    const name = rompMeta(id).name;
    if (!name || !/[A-Za-z0-9]/.test(name) || !runningNames.has(name)) continue;
    const tr = transcripts.get(id);
    if (!tr) continue;
    const prev = best.get(name);
    if (!prev || tr.mtime > prev.mtime) best.set(name, tr);
  }
  for (const tr of best.values()) addSession(tr.file);
}

function addSession(file: string, anchor?: string, keepOpen?: boolean) {
  const id = path.basename(file, ".jsonl");
  if (sessions.has(id)) {
    post({ type: "focus", id, anchor });
    return;
  }
  const meta = rompMeta(id);
  const sess: Session = {
    id, file,
    name: meta.name ?? id.slice(0, 8),
    color: meta.color,
    lastSig: "",
    lastSince: null,
    lastState: "",
    lastWorking: false,
    keepOpen: keepOpen || undefined,
    addedAt: Date.now(),
  };
  sessions.set(id, sess);
  postSession(sess);
  post({ type: "focus", id, anchor });
  watch(sess);
  persistOpen();
}

function persistOpen() {
  try { ctx.workspaceState.update("rompOpenSessions", Array.from(sessions.keys())); }
  catch { /* ignore */ }
}

// After a reload, re-open EXACTLY the tabs that were open — minus any whose
// session has since died. Restored = (remembered open set) ∩ (alive in tmux). We
// never auto-open sessions the user didn't have open. Safety: if the tmux probe is
// unreliable (empty), restore the full remembered set rather than nuke everything.
function restoreSessions() {
  let ids: string[] = [];
  try { ids = ctx.workspaceState.get<string[]>("rompOpenSessions", []) || []; }
  catch { /* ignore */ }
  if (!ids.length) return;
  const states = rompTmuxState();
  const reliable = !!states && states.size > 0;             // empty probe → don't prune (would lose all tabs)
  const alive = new Set(states ? Array.from(states.keys()) : []);
  const transcripts = scanTranscripts();
  for (const id of ids) {
    if (sessions.has(id)) continue;
    const tr = transcripts.get(id);
    if (!tr) continue;
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (reliable && !alive.has(name)) continue;             // PRUNE DEAD: its session is gone → don't reopen
    const sess: Session = {
      id, file: tr.file, name, color: meta.color,
      lastSig: "", lastSince: null, lastState: "", lastWorking: false,
    };
    sessions.set(id, sess);
    watch(sess);
  }
}

function watch(s: Session) {
  try {
    s.watcher = fs.watch(s.file, () => {
      if (s.debounce) clearTimeout(s.debounce);
      s.debounce = setTimeout(() => pushUpdate(s), 50);
    });
  } catch { /* best-effort; poll covers it */ }
}

function pushUpdate(s: Session) {
  if (!panel) return;
  const cur = sig(s.file);
  if (!cur || cur === s.lastSig) return;
  s.lastSig = cur;
  const p = readParsedSession(s);
  if (!p) return;
  s.lastSince = p.status.sinceEpoch;
  s.lastWorking = p.status.working;
  const state = chipState(s.name, lastStates, s.lastWorking);
  s.lastState = state;
  s.lastMetaSig = metaSigOf(s.name, lastStates);
  post({ type: "update", id: s.id, events: filterInterrupted(p.events, state), status: { state, sinceEpoch: workingSinceMs(s, state, lastStates, s.lastSince), effort: effortOf(s.name, lastStates), model: modelOf(s.name, lastStates), ctx: ctxOf(s.name, lastStates), faded: fadedFor(s.name, lastStates) } });
}

// ---- transcript-fork following (/clear, /ide, resume, skill) ----
// Claude Code forks a session onto a NEW transcript fsid on /clear (and /ide,
// resume, a skill) while romp's anchor (@romp-session-id, the names-dir key, and
// this tab's id) stays put — so the live conversation moves to a DIFFERENT .jsonl
// in the SAME project dir, carrying the SAME customTitle. A tab pinned to one
// fsid would tail the now-static old file forever: frozen chat, new prompts
// invisible (the user's report, 2026-06-11). We follow the fork by re-pointing
// the watcher to the newest same-title transcript — the exact fork-grouping the
// daemon uses (romp-summarize-backfill custom_title()/sessions()).
const titleCache = new Map<string, { key: string; title: string | null }>();
// The romp NAME stamped into a transcript's `custom-title` line — read from a
// bounded 64KB head and cached by (mtime,size). KEEP THIS IDENTICAL to the
// daemon's custom_title() (type=="custom-title", first 64KB) so the hosts never
// disagree on which transcripts belong to one session.
function readCustomTitle(file: string): string | null {
  let st: fs.Stats;
  try { st = fs.statSync(file); } catch { return null; }
  const key = `${st.mtimeMs}:${st.size}`;
  const hit = titleCache.get(file);
  if (hit && hit.key === key) return hit.title;
  let title: string | null = null;
  try {
    const fd = fs.openSync(file, "r");
    const buf = Buffer.alloc(65536);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    for (const line of buf.toString("utf8", 0, n).split("\n")) {
      if (!line || !line.includes("custom-title")) continue;
      try {
        const o = JSON.parse(line);
        if (o.type === "custom-title" && o.customTitle) { title = String(o.customTitle); break; }
      } catch { /* a partial / non-JSON head line */ }
    }
  } catch { /* unreadable */ }
  titleCache.set(file, { key, title });
  return title;
}

// The tab's CURRENT live transcript: the newest *.jsonl in its project dir whose
// customTitle matches its romp name. Returns null (→ never repoint) for a tab
// with no real romp name (an 8-char fsid fallback can't match a customTitle) or a
// keepOpen tab — a read-only / deep-link view is pinned to a specific fsid on
// purpose and must NOT chase forks. Steady-state the current (growing) file IS
// the newest, so this only differs from s.file right after a fork.
function currentTranscriptFor(s: Session): string | null {
  if (s.keepOpen) return null;
  if (!s.name || s.name === s.id.slice(0, 8)) return null;
  const dir = path.dirname(s.file);
  let files: string[];
  try { files = fs.readdirSync(dir); } catch { return null; }
  // Seed the bar with the CURRENTLY-watched file's own mtime: only a STRICTLY
  // newer same-title sibling can win, so a tab only ever re-points FORWARD onto a
  // fresher fork — never backwards onto an abandoned one, and never flaps on an
  // mtime tie (parity with the kernel host's fork-follow). Returns null when
  // nothing newer exists (the steady state — the live file is its own newest).
  let bestM = -1;
  try { bestM = fs.statSync(s.file).mtimeMs; } catch { /* current file gone → any match wins */ }
  let best: string | null = null;
  for (const f of files) {
    if (!f.endsWith(".jsonl") || f.startsWith("agent-")) continue;
    const fp = path.join(dir, f);
    let st: fs.Stats;
    try { st = fs.statSync(fp); } catch { continue; }
    if (st.mtimeMs <= bestM) continue;
    if (readCustomTitle(fp) !== s.name) continue;
    bestM = st.mtimeMs; best = fp;
  }
  return best;
}

// Follow a fork: swap the tab onto a new transcript file IN PLACE, preserving the
// tab's identity (id = anchor, name, colour, firstSeen) so it stays the same tab
// in the same sort slot — only the watched bytes change. A fresh parser + offset
// re-read the new file from the top; postSession re-posts a full "session", which
// the webview rebuilds from scratch (the upsert() view-reset) — so the post-fork
// conversation replaces the old thread instead of appending onto it.
function repointSession(s: Session, file: string) {
  try { s.watcher?.close(); } catch { /* ignore */ }
  if (s.debounce) { clearTimeout(s.debounce); s.debounce = undefined; }
  s.file = file;
  s.parser = undefined;
  s.offset = 0;
  s.lastSig = "";
  watch(s);
  postSession(s);
}

function closeSession(id: string) {
  const s = sessions.get(id);
  if (!s) return;
  s.watcher?.close();
  if (s.debounce) clearTimeout(s.debounce);
  sessions.delete(id);
  persistOpen(); // CRITICAL: drop the closed tab from the persisted open-set so a
                 // reload doesn't re-open it — closing a tab must survive reload
                 // even though the session itself is still alive.
  post({ type: "closed", id });
}

// The × on a tab. Normally closing a tab just drops it from this panel and leaves
// the session running. the user (2026-06-10): on close, offer to END the session
// entirely. Only a LIVE session prompts; a dead one closes silently (nothing to
// end). The tick's AUTO-close calls closeSession directly, so it never prompts.
async function requestCloseTab(id: string) {
  const s = sessions.get(id);
  if (!s) return;
  const states = rompTmuxState();
  const running = !!(states && states.size > 0 && states.has(s.name));
  if (!running) { closeSession(id); return; }
  const choice = await vscode.window.showWarningMessage(
    `End “${s.name}”?`,
    { modal: true, detail: "“Close tab” just removes it from this panel and leaves it running.\n“End session” shuts the session down." },
    "End session", "Close tab",
  );
  if (choice === "End session") { endSession(s.name); closeSession(id); }
  else if (choice === "Close tab") closeSession(id);
  // dismissed (Esc/Cancel) → leave the tab open, untouched
}

// Inline rename from a tab (right-click → edit in place). Renames the tmux
// session itself; the after-rename-session hook (`romp _renamed`) then resyncs
// the name map and pushes /rename to Claude's pill, so the timeline, feed, and
// postal addressing all follow. The webview label only updates when we post
// "renamed" back — on any failure we just warn and the tab keeps its old name.
function renameSession(id: string, newName: string) {
  const s = sessions.get(id);
  const name = newName.trim();
  if (!s || !name || name === s.name) return;
  if (!/^[A-Za-z0-9._-]+$/.test(name)) { vscode.window.showWarningMessage("romp: session names are letters, digits, . _ - only."); return; }
  const states = rompTmuxState();
  if (!states || !states.has(s.name)) { vscode.window.showWarningMessage(`romp: "${s.name}" isn't running — only a live session can be renamed.`); return; }
  if (states.has(name)) { vscode.window.showWarningMessage(`romp: a session named "${name}" already exists.`); return; }
  try { execFileSync("tmux", tmuxArgs(["rename-session", "-t", "=" + s.name, name]), { env: tmuxEnv(), timeout: 4000, encoding: "utf8" }); }
  catch (e) { vscode.window.showWarningMessage(`romp: rename failed — ${(e as Error).message ?? e}`); return; }
  // Update the name map ourselves too (same record `romp _renamed` rewrites):
  // the hook is async — and if it's ever broken, the map would stay stale and
  // pickers/restores would keep resolving the dead old name.
  try {
    const f = path.join(ROMP_NAMES, s.id);
    const parts = fs.readFileSync(f, "utf8").replace(/\n$/, "").split("\t");
    parts[0] = name;
    fs.writeFileSync(f, parts.join("\t") + "\n");
  } catch { /* no record for this id — the hook covers it */ }
  applyRename(s, name);
}

// Adopt a session's new name everywhere the extension holds it: the Session
// record, the webview tab, and the published chat-active file (the timeline
// matches lanes by it).
function applyRename(s: Session, name: string) {
  s.name = name;
  post({ type: "renamed", id: s.id, name });
  if (activeTab?.tid === s.id) { activeTab = { tid: s.id, name }; writeChatActive(); }
}

// End a session for good: kill its tmux session (the pane closes → Claude exits).
// The transcript stays on disk, so `romp resume` can still bring the conversation
// back later. Exact target (=name) so we never kill a prefix-matched neighbor.
function endSession(name: string) {
  try { execFileSync("tmux", tmuxArgs(["kill-session", "-t", "=" + name]), { env: tmuxEnv(), timeout: 4000, encoding: "utf8" }); }
  catch { /* already gone */ }
}

// Incremental read: keep a per-session parser + byte offset and feed only the
// bytes appended since last time, instead of re-reading and re-JSON-parsing the
// whole transcript on every change. A multi-MB live session no longer re-parses
// megabytes per keystroke-sized update — only the new tail. Falls back to a full
// re-read when the file shrank or was replaced (offset past EOF), and on any
// parse error (which also resets state so the next attempt re-reads cleanly).
//
// parse/postal-hydration are wrapped: a throw here used to bubble up through
// postSession/addSession AFTER the tab was registered, leaving the panel
// permanently blank (re-open just re-focused the empty tab; reload re-threw).
// Returning null lets callers (which all null-check) skip this update and retry.
function readParsedSession(s: Session) {
  let size: number;
  try { size = fs.statSync(s.file).size; } catch { return null; }
  if (size === 0) return null;
  try {
    // Fresh parser on first read, truncation, or replacement (file got shorter).
    if (!s.parser || (s.offset ?? 0) > size) {
      s.parser = newIncParser();
      s.offset = 0;
    }
    const from = s.offset ?? 0;
    if (size > from) {
      const fd = fs.openSync(s.file, "r");
      try {
        const len = size - from;
        const buf = Buffer.allocUnsafe(len);
        let got = 0;
        while (got < len) {
          const n = fs.readSync(fd, buf, got, len - got, from + got);
          if (n <= 0) break;
          got += n;
        }
        feed(s.parser, got === len ? buf : buf.subarray(0, got));
        s.offset = from + got;
      } finally { fs.closeSync(fd); }
    }
    const p = buildParsed(s.parser);
    // Fold romp postal traffic into structured, identity-coloured cards.
    p.events = hydratePostal(p.events, ROMP_STATE, {
      byId: (id) => rompMeta(id).color,
      byName: colorForName,
    });
    return p;
  } catch (e) {
    console.error("romp-chat-view: failed to parse transcript", s.file, e);
    s.parser = undefined;
    s.offset = 0;
    return null;
  }
}

function sig(file: string): string {
  try { const st = fs.statSync(file); return `${st.size}:${st.mtimeMs}`; }
  catch { return ""; }
}

// Launch / earliest-activity time: the transcript's first-line `timestamp`
// (falls back to the file's birth/mtime). Immutable per session → cached. Used as
// the within-tier tab sort key so tab order matches the romp timeline's lanes.
function firstSeenOf(s: Session): number {
  if (s.firstSeen != null) return s.firstSeen;
  let ms = 0;
  try {
    const fd = fs.openSync(s.file, "r");
    const buf = Buffer.alloc(65536);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    const firstLine = buf.toString("utf8", 0, n).split("\n").find((l) => l.trim());
    const ts = firstLine ? JSON.parse(firstLine)?.timestamp : null;
    const parsed = ts ? Date.parse(ts) : NaN;
    if (!isNaN(parsed)) ms = parsed;
  } catch { /* fall back to file time */ }
  if (!ms) { try { const st = fs.statSync(s.file); ms = st.birthtimeMs || st.mtimeMs || 0; } catch { /* 0 */ } }
  s.firstSeen = ms;
  return ms;
}

// An interrupt that lands BEFORE the first response token makes the TUI pop the
// prompt back into the composer and drop the turn from its conversation — but
// the user line already hit the transcript, and NOTHING marks the restore
// (verified 2026-06-11: the line just sits as the leaf until the next submit
// orphans it). Mirror the TUI: hide a trailing typed user turn once the session
// is back at rest. Not for working/compacting (a reply is coming), and not for
// closed (history should stand whole). The age guard rides out the
// submit→UserPromptSubmit-hook lag, so a just-sent prompt whose state still
// reads "waiting" is never hidden.
const RESTED = new Set<ChipState>(["ready", "idle", "awaiting"]);
function filterInterrupted(events: ChatEvent[], state: ChipState): ChatEvent[] {
  if (!RESTED.has(state)) return events;
  for (let i = events.length - 1; i >= 0; i--) {
    const e: any = events[i];
    if (e.kind === "queued" || e.kind === "todo") continue;   // trailing fixtures, not the turn itself
    if (e.kind === "user" && e.human && e.md && e.ts && Date.now() - Date.parse(e.ts) > 2500)
      return events.slice(0, i).concat(events.slice(i + 1));
    break;
  }
  return events;
}

// Re-post a session's (filtered) events without a transcript change — used when
// a working→rest transition means the trailing turn may have just been
// interrupt-restored and should disappear, mirroring the TUI.
function repostEventsFor(s: Session, state: ChipState) {
  const p = readParsedSession(s);
  if (!p) return;
  post({ type: "update", id: s.id, events: filterInterrupted(p.events, state), status: { state, sinceEpoch: workingSinceMs(s, state, lastStates, s.lastSince), effort: effortOf(s.name, lastStates), model: modelOf(s.name, lastStates), ctx: ctxOf(s.name, lastStates), faded: fadedFor(s.name, lastStates) } });
}

function postSession(s: Session) {
  const p = readParsedSession(s);
  if (!p) return;
  s.lastWorking = p.status.working;
  const states = rompTmuxState();
  const state = chipState(s.name, states, s.lastWorking);
  s.lastSig = sig(s.file);
  s.lastSince = p.status.sinceEpoch;
  s.lastState = state;
  s.lastMetaSig = metaSigOf(s.name, states);
  const ledger = digestOf(s);
  s.ledgerSig = ledgerSigOf(ledger);
  post({
    type: "session",
    id: s.id,
    name: s.name,
    color: s.color,
    events: filterInterrupted(p.events, state),
    status: { state, sinceEpoch: workingSinceMs(s, state, states, p.status.sinceEpoch), effort: effortOf(s.name, states), model: modelOf(s.name, states), ctx: ctxOf(s.name, states), faded: fadedFor(s.name, states) },
    ledger,
    firstSeen: firstSeenOf(s),
  });
}

function tick() {
  const chatActive = !!panel && sessions.size > 0;
  if (!chatActive && !feedPanel) return;
  lastStates = rompTmuxState();
  if (feedPanel) refreshFeed();
  if (!chatActive) return;
  for (const s of Array.from(sessions.values())) {
    // Follow renames made anywhere (this panel, tmux prefix-$, :rename-session):
    // the after-rename hook resyncs the name map, so re-read it. Without this the
    // tab keeps the old name, which tmux no longer knows → chipState says
    // "closed" → the tab auto-closes two ticks after a rename. CRITICAL: only
    // adopt a map name tmux actually knows — the hook is async (and can be
    // broken entirely, e.g. a stale path), so blindly adopting a lagging map
    // entry would revert a just-renamed session to its dead old name and the
    // auto-close below would eat the tab.
    const nm = rompMeta(s.id).name;
    if (nm && nm !== s.name && lastStates?.has(nm)) applyRename(s, nm);
    // Follow a /clear (or /ide / resume / skill) fork: if this session's live
    // conversation has moved to a new fsid transcript, re-point the tab onto it
    // BEFORE the freshness check below — else the tab tails the now-static old
    // file forever (frozen chat; new prompts land in the unwatched new file).
    const live = currentTranscriptFor(s);
    if (live && live !== s.file) { repointSession(s, live); continue; }
    const cur = sig(s.file);
    if (cur && cur !== s.lastSig) { pushUpdate(s); continue; }
    const state = chipState(s.name, lastStates, s.lastWorking);
    // Auto-close a tab whose session has closed (after 2 ticks, to ride out a blip).
    const settled = Date.now() - (s.addedAt ?? 0) > 6000; // grace: don't auto-close a just-opened tab
    if (state === "closed" && !s.keepOpen && settled) {
      s.closedTicks = (s.closedTicks ?? 0) + 1;
      if (s.closedTicks >= 2) { closeSession(s.id); continue; }
    } else {
      s.closedTicks = 0;
    }
    // Re-post on a state change OR a model/effort/ctx/faded change. The meta
    // check matters for a reopened/revived session: its tab opens before the
    // TUI's statusline republishes the tmux vars, so the values arrive a few
    // seconds later with NO chip-state change to carry them (the user's report,
    // 2026-06-11). Also keeps an idle session's display fresh after /model//effort.
    const metaSig = metaSigOf(s.name, lastStates);
    if (state !== s.lastState || metaSig !== s.lastMetaSig) {
      const wasBusy = s.lastState === "working" || s.lastState === "compacting";
      s.lastState = state;
      s.lastMetaSig = metaSig;
      // settling out of work with no transcript change = a possible interrupt-
      // restore: re-post events so the trailing turn is (un)hidden to match
      if (wasBusy && RESTED.has(state)) repostEventsFor(s, state);
      else post({ type: "status", id: s.id, status: { state, sinceEpoch: workingSinceMs(s, state, lastStates, s.lastSince), effort: effortOf(s.name, lastStates), model: modelOf(s.name, lastStates), ctx: ctxOf(s.name, lastStates), faded: fadedFor(s.name, lastStates) } });
    }
  }
  refreshLiveAsks();
  refreshLedgers();
  refreshTabOrder();
  // broadcast the working-name set to the chat-view (postal recipient dots); deduped
  const wsig = workingNames(lastStates).join(",");
  if (wsig !== lastWorkingSig) { lastWorkingSig = wsig; post({ type: "working", names: workingNames(lastStates) }); }
}
let lastWorkingSig = "";

// ---- romp / tmux state ----

function chipState(name: string, states: Map<string, TmuxInfo> | null, working: boolean): ChipState {
  // Only trust tmux when it actually returned sessions (size > 0) — an empty
  // map means the probe is unreliable, so don't mass-mark everything closed.
  if (states && states.size > 0) {
    const info = states.get(name);
    if (!info) return "closed"; // genuinely not running
    if (info.state === "working") return "working";
    if (info.state === "permission") return "awaiting";
    if (info.state === "compacting") return "compacting";
    return "ready"; // waiting / idle
  }
  // tmux unreliable -> fall back to the JSONL working flag.
  return working ? "working" : "ready";
}

// Fade a tab when its session is closed, or running-but-idle for over an hour
// (mirrors the romp timeline's staleness fade).
// Names of sessions currently WORKING (tmux @claude-state) — broadcast to both
// webviews so EVERY render site of a session name (feed card/modal titles, postal
// recipients, tree handoff names) can show a leading working dot.
function workingNames(states: Map<string, TmuxInfo> | null): string[] {
  if (!states) return [];
  const out: string[] = [];
  for (const [name, info] of states) if (info.state === "working") out.push(name);
  return out;
}

function fadedFor(name: string, states: Map<string, TmuxInfo> | null): boolean {
  if (!states || states.size === 0) return false; // unreliable -> don't fade
  const info = states.get(name);
  if (!info) return true; // closed
  if (info.state === "working" || info.state === "permission" || info.state === "compacting") return false;
  const since = parseInt(info.since, 10);
  if (!since) return false;
  return Date.now() / 1000 - since > 3600; // idle > 1h
}

// Raw start timestamp (ms) from tmux @claude-state-since, or the fallback (last
// human prompt) when tmux is absent. romp REWRITES @claude-state-since on tool
// boundaries, so this is sampled only ONCE at the start of a working burst (see
// workingSinceMs) — reading it live would reset the spinner on every tool.
function sinceMsOf(name: string, states: Map<string, TmuxInfo> | null, fallback: number | null): number | null {
  const raw = states ? states.get(name)?.since : undefined;
  const s = raw ? parseInt(raw, 10) : 0;
  return s ? s * 1000 : fallback;
}

// The spinner's elapsed runs from the START of the current working burst and
// keeps climbing through tool uses until the turn is done: capture the start
// once when the session enters "working" and FREEZE it; clear it only when the
// turn finishes (ready/idle/closed). "awaiting" (permission) keeps the clock.
function workingSinceMs(s: Session, state: ChipState, states: Map<string, TmuxInfo> | null, fallback: number | null): number | null {
  if (state === "working") {
    if (s.workingSince == null) s.workingSince = sinceMsOf(s.name, states, fallback);
    return s.workingSince;
  }
  if (state !== "awaiting" && state !== "compacting") s.workingSince = null;
  return s.workingSince ?? null;
}

function effortOf(name: string, states: Map<string, TmuxInfo> | null): string | undefined {
  return states?.get(name)?.effort || undefined;
}

function modelOf(name: string, states: Map<string, TmuxInfo> | null): string | undefined {
  return states?.get(name)?.model || undefined;
}

function ctxOf(name: string, states: Map<string, TmuxInfo> | null): string | undefined {
  return states?.get(name)?.ctx || undefined;
}

// Find the actual tmux server socket file (default server). Passing it with
// `-S` bypasses any inherited $TMUX / TMUX_TMPDIR entirely.
function tmuxSocket(): string | null {
  const uid = typeof process.getuid === "function" ? process.getuid() : 0;
  for (const dir of ["/tmp", process.env.TMUX_TMPDIR, process.env.TMPDIR, os.tmpdir()]) {
    if (!dir) continue;
    const s = path.join(dir, `tmux-${uid}`, "default");
    try { if (fs.existsSync(s)) return s; } catch { /* ignore */ }
  }
  return null;
}

const TMUX_FMT = "'#{session_name}|#{@romp}|#{@claude-state}|#{@claude-effort}|#{@claude-model}|#{@claude-context}|#{@claude-state-since}|#{@claude-summary}'";

function runShell(cmd: string): string {
  try {
    return execSync(cmd, { env: tmuxEnv(), encoding: "utf8", timeout: 2500, stdio: ["ignore", "pipe", "pipe"] });
  } catch (e: any) {
    return String(e?.stdout || "");
  }
}

function parseTmux(out: string): Map<string, TmuxInfo> {
  const map = new Map<string, TmuxInfo>();
  for (const line of out.split("\n")) {
    const p = line.split("|");
    if (p.length < 2 || p[1].trim() !== "1") continue;
    // @claude-summary may itself contain '|', so it's the last field — rejoin the tail.
    map.set(p[0].trim(), { state: (p[2] || "").trim(), effort: (p[3] || "").trim(), model: (p[4] || "").trim(), ctx: (p[5] || "").trim(), since: (p[6] || "").trim(), summary: p.slice(7).join("|").trim() });
  }
  return map;
}

function rompTmuxState(): Map<string, TmuxInfo> | null {
  const sock = tmuxSocket();
  const direct = (sock ? `tmux -S ${JSON.stringify(sock)}` : "tmux") + ` list-sessions -F ${TMUX_FMT}`;
  let map = parseTmux(runShell(direct));
  if (map.size === 0) {
    // Fallback through a login+interactive shell, which reproduces the terminal
    // env where tmux can reach the server.
    const viaLogin = parseTmux(runShell(`zsh -ilc ${JSON.stringify(`tmux list-sessions -F ${TMUX_FMT}`)}`));
    if (viaLogin.size > 0) map = viaLogin;
  }
  return map;
}

function tmuxEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PATH: `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${process.env.PATH || ""}`,
  };
  // VS Code may have inherited a $TMUX client socket that points at the wrong
  // server (empty result). Clear it so we use the TMUX_TMPDIR socket below.
  delete env.TMUX;
  const uid = typeof process.getuid === "function" ? process.getuid() : 0;
  for (const dir of ["/tmp", process.env.TMUX_TMPDIR, process.env.TMPDIR, os.tmpdir()]) {
    if (!dir) continue;
    try {
      if (fs.existsSync(path.join(dir, `tmux-${uid}`, "default"))) { env.TMUX_TMPDIR = dir; break; }
    } catch { /* ignore */ }
  }
  return env;
}

// ---- session listing (mirrors `romp -r`) ----

interface SessionItem extends vscode.QuickPickItem { file: string; }

// One row per session NAME (most-recent transcript), skipping malformed names —
// dedupes forks/resumes that share a name, and filters stray entries like "\".
function sessionRows(): Array<{ id: string; name: string; color: ChipColor | null; running: boolean; mtime: number; file: string }> {
  const transcripts = scanTranscripts();
  const st0 = rompTmuxState();
  const running = new Set<string>(st0 ? Array.from(st0.keys()) : []);
  const best = new Map<string, { id: string; name: string; color: ChipColor | null; running: boolean; mtime: number; file: string }>();
  for (const id of rompIds()) {
    const tr = transcripts.get(id);
    if (!tr) continue;
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (!/[A-Za-z0-9]/.test(name)) continue; // skip garbage names (e.g. a stray "\")
    const prev = best.get(name);
    if (!prev || tr.mtime > prev.mtime) best.set(name, { id, name, color: meta.color, running: running.has(name), mtime: tr.mtime, file: tr.file });
  }
  return Array.from(best.values()).sort((a, b) => Number(b.running) - Number(a.running) || b.mtime - a.mtime);
}

function listSessions(): SessionItem[] {
  return sessionRows().slice(0, 150).map((r) => ({
    label: (r.running ? "● " : "") + r.name,
    description: r.running ? "running" : relTime(r.mtime),
    detail: lastSummary(r.id),
    file: r.file,
  }));
}

// Rich payload for the custom webview picker (includes identity color).
function sessionPayload(): Array<{ id: string; name: string; color: ChipColor | null; running: boolean; time: string; summary: string }> {
  return sessionRows().slice(0, 150).map((r) => ({
    id: r.id, name: r.name, color: r.color, running: r.running,
    time: r.running ? "running" : relTime(r.mtime),
    summary: lastSummary(r.id) || "",
  }));
}

function openSessionById(id: string) {
  const t = resolveSession(id);
  if (!t) return;
  // Live under its customTitle (even when the clicked fsid is an old/forked
  // incarnation) → focus the running session by name. Otherwise revive/open the
  // MOST RECENT incarnation, named by its customTitle — never the stale fork's
  // fsid or a garbage fallback name (the user's "go to the most recent one").
  if (t.liveName) { openByName(t.liveName); return; }
  const name = readCustomTitle(t.file) ?? rompMeta(t.id).name ?? t.id.slice(0, 8);
  promptReopen(t.id, name);
}

// Navigate to a session by its romp NAME (the clickable sender/recipient chip in
// a postal card). Resolve name → most-recent transcript: already open → focus it;
// live → open silently; dead → offer revive / read-only (same UX as a deep-link).
function openByName(name: string) {
  const r = resolveDeepLink(name);
  if (!r) { vscode.window.showWarningMessage(`romp: no session named "${name}".`); return; }
  if (sessions.has(r.id)) { post({ type: "focus", id: r.id }); return; }
  const states = rompTmuxState();
  const running = !!(states && states.size > 0 && states.has(name));
  if (running) addSession(r.file);
  else promptReviveDeepLink(r.id, name, r.file);
}

// External deep-link: vscode://romp.romp-chat-view/open?session=<id>&anchor=<uuid>.
// The romp dashboard fires this on click. Reveal the panel, open the session's
// tab (read-only — render straight from the on-disk JSONL even if it's closed,
// bypassing the reopen prompt), and scroll the webview to the event with <uuid>.
// A file dropped on the composer from the OS carries NO filesystem path in a
// sandboxed webview — only its bytes. Save them under the romp state dir and
// hand the path back ("droppedPath") so the prompt references a real, readable
// file. Drops that DO expose a path never reach here (inserted in-webview).
const ROMP_DROPS = path.join(ROMP_STATE, "drops");
function saveDroppedFile(name: string, b64: string) {
  try {
    fs.mkdirSync(ROMP_DROPS, { recursive: true });
    const safe = name.replace(/[^\w.-]+/g, "_").slice(-80) || "drop";
    const file = path.join(ROMP_DROPS, `${Date.now()}-${safe}`);
    fs.writeFileSync(file, Buffer.from(b64, "base64"));
    post({ type: "droppedPath", path: file });
  } catch (e) {
    vscode.window.showWarningMessage(`romp: couldn't save the dropped file — ${(e as Error).message ?? e}`);
  }
}

// The reliable way to get a file path into the composer. OS file drags onto the
// webview are swallowed by the workbench's editor drop overlay ("drop to open"),
// so instead of fighting it the 📎 button asks the host to run a native open
// dialog and inserts each picked file's real fsPath via the same droppedPath
// pipeline as an in-webview drop.
async function pickFileForComposer() {
  const picks = await vscode.window.showOpenDialog({
    canSelectMany: true,
    canSelectFiles: true,
    canSelectFolders: false,
    openLabel: "Insert path",
    title: "Attach file — inserts its path into the message",
  });
  if (!picks?.length) return;
  for (const uri of picks) post({ type: "droppedPath", path: uri.fsPath });
}

// A link clicked inside a chat webview (the webview sandbox swallows anything
// that isn't http(s)). Deep links addressed to THIS extension skip the OS
// round-trip and go straight to the URI handler — so a vscode://… chat anchor
// pasted into a conversation is clickable right in the transcript. Everything
// else goes to the OS (browser, mail, other apps' schemes).
function openLink(href: string) {
  let uri: vscode.Uri;
  try { uri = vscode.Uri.parse(href, true); } catch { return; }
  if (uri.scheme === "vscode" && uri.authority.toLowerCase() === "romp.romp-chat-view") { onDeepLink(uri); return; }
  vscode.env.openExternal(uri);
}

function onDeepLink(uri: vscode.Uri) {
  const q = new URLSearchParams(uri.query);
  const session = (q.get("session") || "").trim();
  const anchor = (q.get("anchor") || "").trim() || undefined;
  // time fallback (epoch s): used when `anchor` is absent or its uuid can't be
  // found in the rendered thread — the chat lands on the nearest turn instead
  // of silently scrolling to the bottom
  const anchorT = Number(q.get("anchorT") || "") || undefined;
  // intent for the time fallback: "user" = a prompt click; land on the user's
  // own turn, never substitute an assistant answer
  const anchorKind = (q.get("anchorKind") || "").trim() || undefined;
  const preserveFocus = q.get("focus") === "0"; // timeline arrow-preview: reveal without stealing focus
  const compose = q.get("compose") === "1";     // Enter on the timeline → drop the cursor into the composer
  if (!session) {
    vscode.window.showWarningMessage("romp: deep-link is missing ?session=");
    return;
  }
  const r = resolveDeepLink(session);
  if (!r) {
    vscode.window.showWarningMessage(`romp: no transcript found for "${session}".`);
    return;
  }
  // Already open as a tab (by this exact fsid) → just focus it (+ scroll/compose).
  if (sessions.has(r.id)) {
    openPanel(preserveFocus);
    post({ type: "focus", id: r.id, anchor, anchorT, anchorKind });
    if (compose) post({ type: "focusComposer" });
    return;
  }
  // Fork/incarnation-aware: the clicked fsid may be an old or forked incarnation
  // while the session runs NOW under its customTitle (a DIFFERENT anchor sid). Open
  // the session that's live so a stale-stamped deep-link focuses it instead of
  // offering to revive a fork — and when nothing's live, target the MOST RECENT
  // incarnation, not the clicked stale fork.
  const t = resolveSession(session) ?? { id: r.id, file: r.file, liveName: null };
  if (t.liveName) {
    const lr = resolveDeepLink(t.liveName) ?? t;   // the live session's tab/anchor
    if (sessions.has(lr.id)) {
      openPanel(preserveFocus);
      post({ type: "focus", id: lr.id, anchor, anchorT, anchorKind });
      if (compose) post({ type: "focusComposer" });
      return;
    }
    const cold = !panel; // a freshly-created webview isn't listening yet
    openPanel(preserveFocus);
    addSession(lr.file, anchor);
    if (compose) post({ type: "focusComposer" });
    if (cold) pendingFocus = { id: lr.id, anchor, anchorT, anchorKind, compose };
    return;
  }
  // Genuinely not live under any name → revive / view the most recent incarnation.
  const name = readCustomTitle(t.file) ?? rompMeta(t.id).name ?? t.id.slice(0, 8);
  promptReviveDeepLink(t.id, name, t.file, anchor, compose);
}

// Resolve a deep-link `session` (a transcript id; falls back to a romp name →
// most-recent transcript) to {id, file} on disk, or null if none exists.
function resolveDeepLink(session: string): { id: string; file: string } | null {
  const transcripts = scanTranscripts();
  const direct = transcripts.get(session);
  if (direct) return { id: session, file: direct.file };
  let best: { id: string; file: string; mtime: number } | undefined;
  for (const tid of rompIds()) {
    if (rompMeta(tid).name !== session) continue;
    const t = transcripts.get(tid);
    if (t && (!best || t.mtime > best.mtime)) best = { id: tid, file: t.file, mtime: t.mtime };
  }
  return best ? { id: best.id, file: best.file } : null;
}

// Resolve a clicked / deep-linked transcript fsid to the SESSION it belongs to,
// accounting for a session that has lived across several fsids over its life
// (/clear forks, kill+relaunch, revive — each a fresh fsid, but the transcript's
// customTitle stays the session's name). Returns the session's CURRENT
// incarnation — the newest same-customTitle transcript in the project dir — plus
// the live tmux name if it's running now. So a stamp carrying an OLD or forked
// fsid resolves to the session that's live now (focus it), or, when nothing's
// live, to the MOST RECENT incarnation (revive/open that) — never the specific
// stale fork that happened to be clicked. This is why a deliverable produced under
// timeline_window's former anchor (dc1291fb) must NOT offer to revive "dc1291fb":
// its customTitle is "timeline_window", which is live (the user's report,
// 2026-06-11). Falls back to the clicked fsid when it has no customTitle.
function resolveSession(fsid: string): { id: string; file: string; liveName: string | null } | null {
  const tr = scanTranscripts().get(fsid);
  if (!tr) return null;
  const title = readCustomTitle(tr.file);
  let id = fsid, file = tr.file;
  if (title) {
    const dir = path.dirname(tr.file);
    let bestM = -1;
    try {
      for (const f of fs.readdirSync(dir)) {
        if (!f.endsWith(".jsonl") || f.startsWith("agent-")) continue;
        const fp = path.join(dir, f);
        let st: fs.Stats;
        try { st = fs.statSync(fp); } catch { continue; }
        if (st.mtimeMs <= bestM) continue;
        if (readCustomTitle(fp) !== title) continue;
        bestM = st.mtimeMs; file = fp; id = f.replace(/\.jsonl$/, "");
      }
    } catch { /* unreadable dir → keep the clicked transcript */ }
  }
  const states = rompTmuxState();
  let liveName: string | null = null;
  if (states && states.size > 0) {
    if (title && states.has(title)) liveName = title;   // customTitle is authoritative over a stale names entry
    else { const nm = rompMeta(id).name; if (nm && states.has(nm)) liveName = nm; }
  }
  return { id, file, liveName };
}

async function promptReopen(id: string, name: string) {
  const choice = await vscode.window.showWarningMessage(
    `"${name}" is closed. Reopen this session?`,
    { modal: true },
    "Reopen",
  );
  if (choice === "Reopen") reopenSession(id, name);
}

// A deep-link landed on a DEAD session: ask whether to revive rather than
// silently opening a read-only tab that the auto-close would then kill.
async function promptReviveDeepLink(id: string, name: string, file: string, anchor?: string, compose?: boolean) {
  const choice = await vscode.window.showWarningMessage(
    `"${name}" is closed — revive it?`,
    { modal: true },
    "Revive",
    "View read-only",
  );
  if (choice === "Revive") {
    reopenSession(id, name, anchor, compose);
  } else if (choice === "View read-only") {
    const cold = !panel;
    openPanel();
    addSession(file, anchor, true); // keepOpen: exempt from auto-close so it stays readable
    if (compose) post({ type: "focusComposer" });
    if (cold) pendingFocus = { id, anchor, compose };
  }
  // Cancel → do nothing (no silent read-only tab).
}

function rompBin(): string {
  const local = path.join(os.homedir(), "GitRepos", "romp", "bin", "romp");
  try { if (fs.existsSync(local)) return local; } catch { /* ignore */ }
  return "romp";
}

// Restart a closed romp session detached, then open the now-running one.
function reopenSession(id: string, name: string, anchor?: string, compose?: boolean) {
  try {
    // Pass the NAME positionally (+ the original dir) so the revived session is
    // named `name` and runs in the right place. Without the name, romp names the
    // resumed session after the extension host's CWD (a garbage/"\" name), so it
    // never comes back as `name` → looks dead → the tab gets auto-closed.
    execSync(`${JSON.stringify(rompBin())} ${JSON.stringify(name)} --resume ${JSON.stringify(id)} --detach`, {
      env: tmuxEnv(),
      cwd: rompDir(id) || undefined,
      timeout: 12000,
      stdio: ["ignore", "ignore", "ignore"],
    });
  } catch {
    vscode.window.showErrorMessage(`romp: failed to reopen "${name}".`);
    return;
  }
  // Resume boots asynchronously — wait until the session registers as a live
  // tmux @romp session BEFORE opening the tab, so it doesn't open "closed" and
  // get auto-closed. Poll up to ~20s, then open whatever's most-recent.
  let tries = 0;
  const openLatest = () => {
    const transcripts = scanTranscripts();
    let best: { file: string; mtime: number } | undefined;
    for (const tid of rompIds()) {
      if (rompMeta(tid).name !== name) continue;
      const t = transcripts.get(tid);
      if (t && (!best || t.mtime > best.mtime)) best = t;
    }
    if (best) {
      addSession(best.file, anchor);
      if (compose) post({ type: "focusComposer" });
    }
  };
  const poll = () => {
    const states = rompTmuxState();
    const live = !!(states && states.size > 0 && states.has(name));
    if (live || tries++ >= 20) openLatest();
    else setTimeout(poll, 1000);
  };
  setTimeout(poll, 800);
}

function scanTranscripts(): Map<string, { file: string; mtime: number }> {
  const map = new Map<string, { file: string; mtime: number }>();
  let dirs: string[] = [];
  try { dirs = fs.readdirSync(PROJECTS); } catch { return map; }
  for (const d of dirs) {
    const full = path.join(PROJECTS, d);
    let files: string[];
    try { files = fs.readdirSync(full); } catch { continue; }
    for (const f of files) {
      if (!f.endsWith(".jsonl") || f.startsWith("agent-")) continue;
      const id = f.replace(/\.jsonl$/, "");
      const fp = path.join(full, f);
      let st: fs.Stats;
      try { st = fs.statSync(fp); } catch { continue; }
      const prev = map.get(id);
      if (!prev || st.mtimeMs > prev.mtime) map.set(id, { file: fp, mtime: st.mtimeMs });
    }
  }
  return map;
}

function rompIds(): string[] {
  try { return fs.readdirSync(ROMP_NAMES); } catch { return []; }
}

// ---- per-session ledger (rolling digest shown at the top of the chat) ----

interface LedgerBullet { text: string; t?: number; id?: string; sid?: string; }   // id = the reply's romp-events id → timeline hover/locate anchor
interface Ledger { summary: string; bullets: LedgerBullet[]; }

// The rolling digest the romp-summarize Stop hook regenerates each turn, with the
// documented fallback chain so a live session's box is rarely blank: digest →
// latest `reply` phrase in the summaries log → the live @claude-summary tmux var.
function digestOf(s: Session): Ledger | null {
  // BULLETS come from the LIVE summaries log (the haiku-summaries daemon appends a
  // `reply` per turn, age 0-4s) — re-read every tick so the box stays fresh. The
  // digest/<id>.json is only regenerated occasionally (often stale), so we use it
  // ONLY for the curated purpose/summary line, not the bullets.
  const bullets = recentReplyBullets(s.id, 8);
  let summary = "";
  try {
    const raw = fs.readFileSync(path.join(ROMP_STATE, "digest", `${s.id}.json`), "utf8").trim();
    if (raw) { const d = JSON.parse(raw); if (typeof d.summary === "string") summary = d.summary.trim(); }
  } catch { /* no digest */ }
  if (!summary) summary = lastReplySummary(s.id) || lastStates?.get(s.name)?.summary || "";
  if (!summary && !bullets.length) return null;
  return { summary, bullets };
}

// The most-recent `reply` summaries from the live summaries log — the per-turn
// "done" items the ledger shows as bullets. The log is NOT guaranteed to be in
// timestamp order (backfilled entries land out of order), so we collect all
// replies, SORT by timestamp descending, then take the top k.
function recentReplyBullets(id: string, k: number): LedgerBullet[] {
  try {
    const lines = fs.readFileSync(path.join(ROMP_SUMMARIES, `${id}.jsonl`), "utf8").trim().split("\n");
    const all: LedgerBullet[] = [];
    for (const ln of lines) {
      if (!ln) continue;
      try {
        const e = JSON.parse(ln);
        // attach the reply's romp-events id (+ this session as sid) so the bullet
        // can drive timeline hover/locate, exactly like a feed row
        if (e.kind === "reply" && e.text) all.push({ text: String(e.text).trim(), t: typeof e.t === "number" ? e.t : undefined, id: typeof e.id === "string" ? e.id : undefined, sid: id });
      } catch { /* skip */ }
    }
    all.sort((a, b) => (b.t ?? 0) - (a.t ?? 0)); // newest first
    return all.slice(0, k);
  } catch { return []; }
}

// Latest assistant-`reply` phrase (else the last entry) from the summaries log —
// the digest's fallback before a session has been digested. NOTE the file is
// `<id>.jsonl` (the older lastSummary() reads `<id>` without the extension).
function lastReplySummary(id: string): string {
  try {
    const lines = fs.readFileSync(path.join(ROMP_SUMMARIES, `${id}.jsonl`), "utf8").trim().split("\n").filter(Boolean);
    const tail = lines.slice(-12).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) as any[];
    for (let i = tail.length - 1; i >= 0; i--) if (tail[i].kind === "reply" && tail[i].text) return String(tail[i].text).trim();
    const last = tail[tail.length - 1];
    return last && last.text ? String(last.text).trim() : "";
  } catch { return ""; }
}

function ledgerSigOf(l: Ledger | null): string {
  if (!l) return "";
  return l.summary + "§" + l.bullets.map((b) => `${b.t ?? ""}:${b.text}`).join("|");
}

// Push each session's digest to the webview whenever it changes — the box stays
// fresh as sessions work, since tick re-reads every 800ms. Deduped by ledgerSig.
function refreshLedgers() {
  for (const s of sessions.values()) {
    const ledger = digestOf(s);
    const sg = ledgerSigOf(ledger);
    if (sg !== s.ledgerSig) { s.ledgerSig = sg; post({ type: "ledger", id: s.id, ledger }); }
  }
}

// ---- shared tab/lane order (synced with the romp timeline) ----

let lastOrderSig = "";
function readSessionOrder(): string[] {
  try {
    const arr = JSON.parse(fs.readFileSync(SESSION_ORDER, "utf8"));
    return Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}
function writeSessionOrder(order: string[]) {
  try {
    const tmp = `${SESSION_ORDER}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(order));
    fs.renameSync(tmp, SESSION_ORDER);   // atomic
    lastOrderSig = order.join(",");      // so our own write doesn't bounce back via the poll
  } catch { /* ignore */ }
}
// Poll the shared order each tick; when it changes (e.g. the timeline reordered it)
// push it to the webview so the tabs re-render to match. Poll, not fs.watch (flaky
// on macOS).
function refreshTabOrder() {
  const order = readSessionOrder();
  const sig = order.join(",");
  if (sig !== lastOrderSig) { lastOrderSig = sig; post({ type: "tabOrder", order }); }
}

function lastSummary(id: string): string | undefined {
  try {
    const txt = fs.readFileSync(path.join(ROMP_SUMMARIES, id), "utf8").trim();
    const last = txt.split("\n").filter(Boolean).pop();
    if (!last) return undefined;
    try { return (JSON.parse(last).text || "").trim() || undefined; }
    catch { return last.slice(0, 140); }
  } catch { return undefined; }
}

// The working dir stored for a session (names file is `name\tdir\tbg\tfg`), so a
// revived session resumes where it lived rather than in the extension's CWD.
function rompDir(id: string): string | undefined {
  try {
    const dir = fs.readFileSync(path.join(ROMP_NAMES, id), "utf8").split("\t")[1]?.trim();
    return dir || undefined;
  } catch { return undefined; }
}

function rompMeta(id: string): { name?: string; color: ChipColor | null } {
  try {
    const txt = fs.readFileSync(path.join(ROMP_NAMES, id), "utf8");
    const [name, , bg, fg] = txt.split("\t");
    const color = bg && bg.trim() ? { bg: bg.trim(), fg: (fg || "white").trim() } : null;
    return { name: name?.trim() || undefined, color };
  } catch {
    return { color: null };
  }
}

// Resolve a session's identity colour by NAME (for outgoing sends, where we
// only know the recipient name). Names can be reused across sessions, so pick
// the most recently registered id carrying that name.
function colorForName(name: string): ChipColor | null {
  if (!name) return null;
  let best: { color: ChipColor; mtime: number } | null = null;
  for (const id of rompIds()) {
    const meta = rompMeta(id);
    if (meta.name !== name || !meta.color) continue;
    let mtime = 0;
    try { mtime = fs.statSync(path.join(ROMP_NAMES, id)).mtimeMs; } catch { /* ignore */ }
    if (!best || mtime > best.mtime) best = { color: meta.color, mtime };
  }
  return best?.color ?? null;
}

function relTime(ms: number): string {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

// ======================= romp feed =======================
// A fleet-wide stream of deliverables (each turn's `reply` phrase), newest-first,
// mirroring scripts/romp-feed but rendered as a webview list. Each item links to
// its session and can be dismissed; dismissals persist in globalState.

// Recency colormap — a manual port of scripts/romp_colormap.py (the canonical
// source; the webview can't import the Python module) so the feed's time labels
// match romp-feed / romp-ledger. Currently crameri "hawaii" (dark-magenta → pale
// cyan), recent -> bright, log scale. Re-sync BOTH STOPS and FADE_HI whenever the
// fleet swaps the colormap — terminal romp-feed/ledger move automatically, this
// static port does not.
const FEED_STOPS: Array<[number, number, number]> = [
  [140, 2, 115], [146, 46, 85], [151, 78, 62], [155, 111, 40], [156, 150, 28],
  [137, 189, 74], [107, 212, 142], [103, 233, 213], [179, 242, 253],
];
const FEED_FADE_LO = 120, FEED_FADE_HI = 345600;
function feedRamp(v: number): [number, number, number] {
  v = Math.max(0, Math.min(1, v));
  const x = v * (FEED_STOPS.length - 1);
  const i = Math.floor(x), fr = x - i;
  if (i >= FEED_STOPS.length - 1) return FEED_STOPS[FEED_STOPS.length - 1];
  const a = FEED_STOPS[i], b = FEED_STOPS[i + 1];
  return [Math.round(a[0] + (b[0] - a[0]) * fr), Math.round(a[1] + (b[1] - a[1]) * fr), Math.round(a[2] + (b[2] - a[2]) * fr)];
}
// Recency → [r,g,b] on the hawaii ramp (recent = bright). The webview composites
// this as the CARD BACKGROUND (a semi-transparent tint over black), so a card's
// color itself encodes how recent its deliverable is.
function ageRgbTuple(ageSec: number): [number, number, number] {
  const a = Math.max(FEED_FADE_LO, Math.min(FEED_FADE_HI, ageSec));
  const f = (Math.log(a) - Math.log(FEED_FADE_LO)) / (Math.log(FEED_FADE_HI) - Math.log(FEED_FADE_LO));
  return feedRamp(1 - f);
}

function djb2(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

type Relevance = "DONE" | "DECISION" | "ACTION" | "IDEA" | "WAIT" | "DETAILS" | "UNTAGGED";
interface FeedItem {
  itemId: string; sid: string; name: string; color: ChipColor | null;
  did: string; ask: string; t: number; live: boolean; relevance: Relevance;
  origin: "user" | "agent";   // who prompted the turn: the user typed vs a peer's postal message
  inAsk?: boolean;            // this reply is linked into some ask (renders there, not standalone)
}

// haiku_summaries tags each deliverable: DONE (finished), DECISION (needs the user),
// DETAILS (routine). Anything else — missing, legacy "MECHANICS", unrecognized —
// is UNTAGGED (kept VISIBLE by default with no label; only EXPLICIT DETAILS hides).
function normRelevance(v: any): Relevance {
  const s = String(v || "").toUpperCase();
  return s === "DONE" || s === "DECISION" || s === "ACTION" || s === "IDEA" || s === "WAIT" || s === "DETAILS" ? s : "UNTAGGED";
}

// the user's last typed-turn time per session (anchor sid) — rebuilt on every feed
// pass from the summaries' `request` lines. Used by the ask fold's
// answered-crossoff: a DECISION older than the user's next typed turn in that
// session has been answered and stops counting as "needs you".
const lastReqBySid = new Map<string, number>();
// turn_id → the typed turn's summary phrase. One prompt often mints SEVERAL
// asks (sub-parts of one request); the feed groups those under one card titled
// by this phrase — grouping is pure presentation, each ask keeps its own DAG.
const reqPhraseById = new Map<string, string>();

// One item per `reply` deliverable across every session's summaries log, each
// carrying the most recent preceding `request` as its prompting ask, newest-first.
function computeFeedItems(states: Map<string, TmuxInfo> | null): FeedItem[] {
  const liveNames = new Set<string>(states ? Array.from(states.keys()) : []);
  lastReqBySid.clear();
  reqPhraseById.clear();
  const out: FeedItem[] = [];
  for (const id of rompIds()) {
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (!/[A-Za-z0-9]/.test(name)) continue;   // skip garbage names (stray "\")
    let raw: string;
    try { raw = fs.readFileSync(path.join(ROMP_SUMMARIES, `${id}.jsonl`), "utf8"); }
    catch { continue; }
    const evs: any[] = [];
    for (const ln of raw.split("\n")) {
      const t = ln.trim();
      if (t) { try { evs.push(JSON.parse(t)); } catch { /* skip */ } }
    }
    evs.sort((a, b) => (a.t || 0) - (b.t || 0));
    // ORIGIN: the summarizer writes a `request` line ONLY for turns the user typed
    // (postal banners/drains/task-notifications get none), so a reply with a
    // SAME-ID request line is user-prompted; without one it's agent-prompted.
    // The same-id request is also the exact prompting ask when present (better
    // than the "most recent preceding request" fallback).
    const reqText = new Map<string, string>();
    for (const e of evs) {
      if (e.kind === "request" && typeof e.id === "string" && e.id) {
        reqText.set(e.id, String(e.text || ""));
        reqPhraseById.set(e.id, String(e.text || ""));
        // typed-turn time = the id's process-start (middle field), not the line's
        // late backfill write-time
        const start = Number(e.id.split(":")[1]);
        const rt = Number.isFinite(start) && start > 0 ? start : (e.t || 0);
        lastReqBySid.set(id, Math.max(lastReqBySid.get(id) || 0, rt));
      }
    }
    // The summarizer regenerates a turn's summary across passes, appending a NEW
    // reply line with the SAME id each time — so dedupe by id, last line wins (the
    // latest summary). Display time is the turn's PROCESS-START (the id's middle
    // field), not the line's write-time `t`, so a late backfill pass can't reorder
    // an old deliverable to the top. Older logs lack an id → synthesize a unique one.
    const byId = new Map<string, FeedItem>();
    let ask = "";
    let seq = 0;
    for (const e of evs) {
      if (e.kind === "request") { ask = String(e.text || ""); continue; }
      if (e.kind !== "reply") continue;
      const did = String(e.text || "");
      let itemId: string, t: number;
      if (typeof e.id === "string" && e.id) {
        itemId = e.id;
        const start = Number(e.id.split(":")[1]);
        t = Number.isFinite(start) && start > 0 ? start : (e.t || 0);
      } else {
        t = e.t || 0;
        itemId = `${id}:${t}:${seq}:${djb2(did)}`;
      }
      const own = typeof e.id === "string" ? reqText.get(e.id) : undefined;
      byId.set(itemId, {
        itemId, sid: id, name, color: meta.color, did, ask: own ?? ask, t,
        live: liveNames.has(name), relevance: normRelevance(e.relevance),
        origin: own !== undefined ? "user" : "agent",
      });
      seq++;
    }
    for (const it of byId.values()) out.push(it);
  }
  out.sort((a, b) => b.t - a.t);
  return out;
}

// ---- asks (the request registry; spec: ~/.local/state/romp/REQUESTS.md) ----
// One card per OPEN (uncleared) ask of the user's. Read-time fold: amend = latest
// text wins; cleared = drop; links roll up to root asks through the recorded
// `parents` edges (a deliverable can reach multiple roots).
//
// COLUMN = DAG path accounting (the user's model, 2026-06-09): each node's status
// comes from the newest link directly on it — DONE closes it, an UNANSWERED
// question (DECISION with no later the user turn in that session) flags it, anything
// else leaves it open. An ask is judged by where its paths END (2026-06-10):
// every leaf DONE → completed; any open question anywhere → needs_input; else
// asks, with a drop point per OPEN LEAF (the responsible session that owes
// either a completion or a question). Intermediate nodes whose newest direct
// row is a restatement or an answered question are transparent — the work
// continued downstream, and a fully delegated ask can complete even though
// nothing was ever filed directly on it. the user's adjudications land in
// corrections.jsonl and act as links at read time (see merge below), so
// "mark done" both completes the card and trains the linker. The system still
// never resolves anything on its own — Clear remains the only retirement.
const ROMP_REQUESTS = path.join(ROMP_STATE, "requests");

type RowStatus = "done" | "question" | "update";
type AskColumn = "asks" | "needs_input" | "completed";
interface AskLinked { did: string; relevance: Relevance; t: number; reply_id: string; status: RowStatus; sid: string; name: string; color: ChipColor | null; answer?: boolean }
// qtype: what kind of input the user owes — answer a question (decision), do
// something outside chat (action: closed only via "did it"), react to a
// suggestion (idea). Mirrors the linker's needs-user tag on the link.
interface AskQuestion { reply_id: string; sid: string; name: string; t: number; brief: any | null; qtype: "decision" | "action" | "idea"; nodeId: string }
interface AskPath { name: string; sid: string; color: ChipColor | null; since: number; lastPhrase: string }
// One node of the ask's request DAG, for tree-style card rendering: the ask
// root, then each handoff (delegation message) nested under what it serves,
// with the replies filed under each node as its leaf rows. A node serving two
// parents appears in both children lists (it's a DAG rendered as a tree).
interface AskTreeNode {
  id: string; kind: "ask" | "handoff";
  text: string;                        // ask text / handoff phrase
  who: string;                         // who owes this node a terminal: ask → its session, handoff → recipient
  whoSid: string;                      // …and its session id (the modal renders names as session links)
  whoColor: ChipColor | null;          // …in the agent's identity color
  whoWorking?: boolean;                // …is that agent currently WORKING (tmux @claude-state) → working dot
  status: "done" | "question" | "open";
  t: number; last: number;             // created / newest activity
  children: string[];                  // child node ids within this ask's subgraph
  rows: AskLinked[];                   // replies filed directly under THIS node, newest-first
}
interface AskItem {
  itemId: string; sid: string; name: string; color: ChipColor | null;
  text: string; t: number; created: number; live: boolean;
  done: number; needsYou: number; linked: AskLinked[]; turnId: string;
  column: AskColumn; openQuestions: AskQuestion[]; openPaths: AskPath[];
  reopened: boolean;                   // resurrected: a question arrived AFTER the user's clear
  // the full DAG for timeline highlighting: typed turn + every linked reply
  // (romp-events ids) and every handoff in the subgraph (postal message ids)
  path: { events: string[]; msgs: string[] };
  tree: AskTreeNode[];                 // flat node list, root first; nest via children
  // liveness reveal (2026-06-11): outline color in the feed — what an automated
  // "is this still being worked?" rule WOULD say. Colors only, decides nothing.
  liveness: AskLiveness; livenessWhy: string;
  // settled card moved out of WORKING by the read-time auto-filing rule — the
  // webview keeps its green ring in COMPLETED (verify before Clear)
  autoFiled?: boolean;
  // every path ends with an explicit DONE stamp (model or corrections) — the
  // OTHER door into COMPLETED; webview ring = blue (green+blue when the
  // settled detector agrees: the goal state where both systems intersect)
  explicitDone?: boolean;
  // newest link on some node is WAIT: paused on an EXTERNAL event — held in
  // WORKING, exempt from auto-filing and the green ring; ⏳ chip on the card
  waiting?: boolean;
  // every typed turn that touched this card (mint + amends) — joins a LIVE
  // blocked turn (permission/picker) to the card it's blocked on
  turnIds: string[];
  // set by refreshFeed when the owning session is blocked ON this card's work:
  // the card itself moves to BLOCKED (the user's ruling 2026-06-11 — a blocked
  // session is not its own card)
  blocked?: { state: string; since: number; what: string };
  // missed-handoff suspects attached by refreshFeed (deterministic sweep): a
  // dismissed-as-FYI message from this card's session followed by the
  // recipient's orphan work — ⚠ badge + modal section + Report box
  suspects?: Array<{ mid: string; to: string; t: number; snippet: string; why: string }>;
  // one typed prompt often mints SEVERAL asks: siblings share turnId and render
  // as ONE card (title = the turn's phrase) with a circle-line per member —
  // presentation only, each member keeps its own DAG/column/Clear
  groupTitle?: string; groupN?: number;
}
// The four liveness verdicts, session-level by construction (a busy owner MAY be
// working on something else — that coarseness is what the reveal is meant to
// expose before any auto-filing is built on it):
//   active    — the owning session is mid-turn
//   delegated — owner quiet, but a session holding an UNFINISHED handoff is mid-turn
//   stalled   — an unfinished handoff whose recipient is quiet or gone (that branch
//               owes a terminal and nobody is producing one)
//   settled   — no turn anywhere, no open handoff: nothing can change without the
//               user, so an auto-filing rule would move this card now
type AskLiveness = "active" | "delegated" | "stalled" | "settled";

// Decision briefs (haiku's pipeline): prewarmed on DECISION links — context from
// the upstream DAG walk + the concrete question. May lag or be absent; render
// falls back to the row phrase.
const ROMP_DECISION_BRIEF = path.join(ROMP_STATE, "decision-brief");
function readDecisionBrief(replyId: string): any | null {
  try {
    const d = JSON.parse(fs.readFileSync(path.join(ROMP_DECISION_BRIEF, `${replyId}.json`), "utf8"));
    return d && typeof d.question === "string" && d.question ? d : null;
  } catch { return null; }
}

function readReqRows(file: string): any[] {
  try {
    const raw = fs.readFileSync(path.join(ROMP_REQUESTS, file), "utf8");
    const out: any[] = [];
    for (const ln of raw.split("\n")) {
      const t = ln.trim();
      if (t) { try { out.push(JSON.parse(t)); } catch { /* skip */ } }
    }
    return out;
  } catch { return []; }
}

function computeAskItems(states: Map<string, TmuxInfo> | null, didById: Map<string, FeedItem>): AskItem[] {
  const liveNames = new Set<string>(states ? Array.from(states.keys()) : []);
  const asks = new Map<string, any>();
  const internals = new Map<string, any>();
  const parents = new Map<string, string[]>();
  const amendTurns = new Map<string, string[]>();   // ask id → turn ids that amended/answered it (joins a live turn to its card)
  const answerRows: any[] = [];                     // kind:"answer" rows — injected as pseudo-links below
  for (const n of readReqRows("nodes.jsonl")) {
    if (n.kind === "ask" && typeof n.id === "string") { if (!asks.has(n.id)) asks.set(n.id, { ...n }); }
    else if (n.kind === "internal" && typeof n.id === "string") { if (!internals.has(n.id)) internals.set(n.id, { ...n }); }
    else if (n.kind === "parents" && typeof n.id === "string") parents.set(n.id, Array.isArray(n.parent_ids) ? n.parent_ids : []);
    else if (n.kind === "amend" && asks.has(n.id)) {
      asks.get(n.id).text = String(n.text || asks.get(n.id).text || "");
      if (n.turn_id) { if (!amendTurns.has(n.id)) amendTurns.set(n.id, []); amendTurns.get(n.id)!.push(String(n.turn_id)); }
    }
    else if (n.kind === "answer" && typeof n.id === "string") {
      answerRows.push(n);
      if (n.turn_id) { if (!amendTurns.has(n.id)) amendTurns.set(n.id, []); amendTurns.get(n.id)!.push(String(n.turn_id)); }
    }
  }
  // newest clear per id (re-clears append; max-t wins). A clear hides the card
  // UNLESS an open question ARRIVES after it — then the card resurrects into
  // needs_input ("reopened"): a post-clear question must never be invisible,
  // while a question the user saw and deliberately cleared stays dismissed.
  // Pure read-time timestamp comparison — no writes, no daemon coordination,
  // so the in-flight-palette race resolves itself (late link = later t).
  const clearedAt = new Map<string, number>();
  for (const c of readReqRows("cleared.jsonl")) {
    const cid = String(c.id);
    clearedAt.set(cid, Math.max(clearedAt.get(cid) || 0, c.t || 0));
  }
  // Follow-ups (followups.jsonl — the feed's file, like cleared.jsonl): the
  // "Follow up" box on a completed card delivered a new instruction to the
  // session. The record deterministically reopens the card to ASKS until the
  // bookkeeper catches up — so the gap between sending and bookkeeping can
  // never show the card as still completed.
  const followupsById = new Map<string, any[]>();
  for (const f of readReqRows("followups.jsonl")) {
    const fid = String(f.id || "");
    if (!fid) continue;
    if (!followupsById.has(fid)) followupsById.set(fid, []);
    followupsById.get(fid)!.push(f);
  }
  // children = inverted parents edges (ask/internal → the internal nodes serving it)
  const children = new Map<string, string[]>();
  for (const [cid, pids] of parents) {
    for (const p of pids) {
      const key = String(p);
      if (!children.has(key)) children.set(key, []);
      children.get(key)!.push(cid);
    }
  }
  // links grouped per node, time-ascending — node status reads the newest.
  // PER-REQUEST PHRASES: one reply often discharges several requests across
  // unrelated workstreams, and the reply's whole-turn phrase then bleeds into
  // every card it's filed under (the user, 2026-06-10: double-click material
  // showing inside the investigate-jump card). When the link row carries a
  // phrase scoped to ONE request — did_by_request[rid], or did on a
  // single-request row — that node's copy of the link prefers it; the global
  // reply phrase remains the fallback for rows that don't carry one.
  const nodeLinks = new Map<string, any[]>();
  for (const l of readReqRows("links.jsonl")) {
    if (l.kind !== "link" || !Array.isArray(l.request_ids)) continue;
    const dbr = l.did_by_request && typeof l.did_by_request === "object" ? l.did_by_request : null;
    for (const rid of l.request_ids) {
      const key = String(rid);
      if (!asks.has(key) && !internals.has(key)) continue;   // unknown ids stay out of the user-level view
      if (!nodeLinks.has(key)) nodeLinks.set(key, []);
      const perReq = dbr && typeof dbr[key] === "string" && dbr[key].trim() ? dbr[key].trim()
        : typeof l.did === "string" && l.did.trim() ? l.did.trim() : null;
      nodeLinks.get(key)!.push(perReq ? { ...l, _didFor: perReq } : l);
    }
  }
  // the user's adjudications (corrections.jsonl — any session may append, spec'd in
  // REQUESTS.md): a row whose should_have names nodes × relevance acts as a link
  // on those nodes at its t. Newest-wins then applies as usual, so a "mark done"
  // closes a stale node the same way a real terminal reply would — and the same
  // row is the linker's training label.
  for (const c of readReqRows("corrections.jsonl")) {
    const sh = c && c.should_have;
    if (!sh || !Array.isArray(sh.request_ids) || !sh.relevance) continue;
    for (const rid of sh.request_ids) {
      const key = String(rid);
      if (!asks.has(key) && !internals.has(key)) continue;
      if (!nodeLinks.has(key)) nodeLinks.set(key, []);
      nodeLinks.get(key)!.push({
        kind: "link", reply_id: String(c.decision_ref || `corr:${key}:${c.t || 0}`),
        request_ids: [key], relevance: String(sh.relevance),
        sid: String(c.by_sid || ""), t: c.t || 0,
        _did: c.note ? String(c.note) : undefined,
        _corr: true,   // a re-verdict of an existing report, not new activity
      });
    }
  }
  // ANSWER rows (kind:"answer", the user 2026-06-11): the user's typed reply to an
  // agent question, recorded by the capture side as an explicit child event on
  // the card — never inferred. Injected as a pseudo-link so the newest-link
  // fold crosses the pending question off naturally (an ANSWER as newest link
  // reads "in flight again"), the row renders in the card's history (↩), and
  // recency/path joins pick the turn up. The next-typed-turn inference below
  // (`answered`) survives only as the fallback for UNANCHORED answers.
  for (const n of answerRows) {
    const key = String(n.id);
    if (!asks.has(key) && !internals.has(key)) continue;
    if (!nodeLinks.has(key)) nodeLinks.set(key, []);
    nodeLinks.get(key)!.push({
      kind: "link", reply_id: String(n.turn_id || `ans:${key}:${n.t || 0}`),
      request_ids: [key], relevance: "ANSWER",
      sid: String((asks.get(key) ?? internals.get(key))?.sid || ""), t: n.t || 0,
      _did: n.text ? String(n.text) : undefined, _answer: true,
    });
  }
  for (const ls of nodeLinks.values()) ls.sort((a, b) => (a.t || 0) - (b.t || 0));
  // A question is OPEN until the user's next typed turn in the asking session —
  // his answer crosses it off (the node reverts to open: in flight again).
  const answered = (l: any): boolean => (lastReqBySid.get(String(l.sid || "")) || 0) > (l.t || 0);
  // …or until the asking session demonstrably MOVED ON: a session blocked on a
  // question can only produce new filed work after the question was resolved.
  // This catches every answer channel that types nothing — plan-approval
  // dialogs, permission clicks, picker answers, peer-mail wake-ups — which the
  // typed-turn rule alone misses, stranding cards in AWAITING while the
  // session visibly works (db_timeline, 2026-06-10). DECISION only: ACTION is
  // the user's out-of-chat to-do (agent activity proves nothing about it), IDEA
  // is about HIS reaction, not the agent's progress.
  const lastLinkBySid = new Map<string, number>();
  for (const l of readReqRows("links.jsonl")) {
    if (l.kind !== "link" || !l.sid) continue;
    const s = String(l.sid);
    lastLinkBySid.set(s, Math.max(lastLinkBySid.get(s) || 0, l.t || 0));
  }
  const movedOn = (l: any): boolean => (lastLinkBySid.get(String(l.sid || "")) || 0) > (l.t || 0);
  type NodeStatus = { st: "done" | "question" | "open"; qlink?: any };
  const statusCache = new Map<string, NodeStatus>();
  const nodeStatus = (nid: string): NodeStatus => {
    const hit = statusCache.get(nid);
    if (hit) return hit;
    const ls = nodeLinks.get(nid) || [];
    let st: NodeStatus = { st: "open" };
    // DETAILS never re-opens a verdict (the user's latching rule applied to the
    // judged fold, 2026-06-11 evening): routine progress filed after a DONE stamp
    // is cleanup riding the same node — only a question, an answer, or a new
    // non-routine verdict changes state. Without this, any wrap-up DETAILS link
    // erased the judge's DONE and every Completed card rendered auto-filed green.
    let newest: any = null;
    for (let i = ls.length - 1; i >= 0; i--) {
      if (normRelevance(ls[i].relevance) === "DETAILS") continue;
      newest = ls[i]; break;
    }
    if (newest) {
      const rel = normRelevance(newest.relevance);
      if (rel === "DONE") st = { st: "done" };
      // ACTION = the user must DO something (reload, install, approve) — typing in
      // the session does NOT cross it off (he may have typed without acting);
      // only his explicit "did it" (a DONE correction, newest-wins) closes it.
      else if (rel === "ACTION") st = { st: "question", qlink: newest };
      // DECISION is answered by his next typed turn OR by the session moving on
      else if (rel === "DECISION" && !answered(newest) && !movedOn(newest)) st = { st: "question", qlink: newest };
      // IDEA is dismissed by his next typed turn alone (it asks for HIS reaction)
      else if (rel === "IDEA" && !answered(newest)) st = { st: "question", qlink: newest };
      // brief second-opinion gate (the user 2026-06-11): the brief sees the full
      // chain; when it judged NEEDED=no ("no decision needed — just a completion
      // report"), the needs-user verdict loses INSTANTLY here — the daemon's
      // demotion correction makes it durable for every other surface.
      if (st.st === "question") {
        const b: any = readDecisionBrief(String(newest.reply_id || ""));
        if (b && b.needed === false) st = { st: "open" };
      }
    }
    statusCache.set(nid, st);
    return st;
  };
  const nameOf = (sid: string): string => rompMeta(sid).name ?? sid.slice(0, 8);
  const out: AskItem[] = [];
  for (const [id, a] of asks) {
    // An ask minted UNDER another node (a follow-up turn the bookkeeper filed
    // as a child of the completed root) renders inside its root's card — the
    // card's title stays the root's, per the user. Never its own top-level card.
    if ((parents.get(id) || []).length) continue;
    // subgraph = the ask + every internal node whose parents-walk reaches it
    const subgraph: string[] = [];
    const seen = new Set<string>();
    const queue = [id];
    while (queue.length) {
      const nid = queue.shift()!;
      if (seen.has(nid)) continue;   // cycle guard
      seen.add(nid);
      subgraph.push(nid);
      for (const c of children.get(nid) || []) queue.push(c);
    }
    const stOf = new Map(subgraph.map((nid) => [nid, nodeStatus(nid)] as const));
    const kidsOf = (nid: string): string[] => (children.get(nid) || []).filter((c) => seen.has(c));
    // Rolled-up status: a node is judged by where its paths END. Leaves keep
    // their own status; an intermediate node is done when every path below it
    // ends DONE — its own restatement / answered question is transparent (the
    // work continued downstream). Questions bubble up from anywhere, so a
    // completed ask renders all-✓ and a buried question still flags the root.
    const rollCache = new Map<string, "done" | "question" | "open">();
    const rollup = (nid: string): "done" | "question" | "open" => {
      const hit = rollCache.get(nid);
      if (hit) return hit;
      rollCache.set(nid, "open");                      // cycle sentinel: a back-edge reads open
      const own = stOf.get(nid)?.st ?? "open";
      const kids = kidsOf(nid);
      let st: "done" | "question" | "open";
      if (!kids.length) st = own;
      else {
        const below = kids.map(rollup);
        st = own === "question" || below.includes("question") ? "question"
          : below.every((b) => b === "done") ? "done" : "open";
      }
      rollCache.set(nid, st);
      return st;
    };
    const openQuestions: AskQuestion[] = [];
    const openPaths: AskPath[] = [];
    for (const nid of subgraph) {
      const st = stOf.get(nid)!;
      if (st.st === "question") {
        const q = st.qlink;
        const qrel = normRelevance(q.relevance);
        openQuestions.push({
          reply_id: String(q.reply_id || ""), sid: String(q.sid || ""),
          name: nameOf(String(q.sid || "")), t: q.t || 0,
          brief: readDecisionBrief(String(q.reply_id || "")),
          qtype: qrel === "ACTION" ? "action" : qrel === "IDEA" ? "idea" : "decision",
          nodeId: nid,   // for "did it" — the action's node gets the DONE correction
        });
      } else if (st.st === "open" && !kidsOf(nid).length) {
        // drop point = an open LEAF: this path ended without a completion or a
        // question, and this node's responsible session owes the user one
        const node = asks.get(nid) ?? internals.get(nid);
        // an internal node's work is owed by its RECIPIENT; the root by the user's session
        const owner = String(node?.to_sid || node?.sid || "");
        const ls = nodeLinks.get(nid) || [];
        const newest = ls.length ? ls[ls.length - 1] : null;
        const fi = newest ? didById.get(String(newest.reply_id || "")) : undefined;
        openPaths.push({
          name: nameOf(owner), sid: owner, color: rompMeta(owner).color,
          since: newest ? (newest.t || 0) : (node?.t || 0),
          lastPhrase: newest?._didFor ? String(newest._didFor) : fi ? fi.did : String(node?.text || ""),
        });
      }
    }
    const allDone = rollup(id) === "done";
    // Open follow-ups on this root: each one holds the card in ASKS until the
    // bookkeeper mints the delivered turn as a child of the root, or any newer
    // verdict lands on the root itself — from then on the ordinary leaf-path
    // fold owns the card (fresh open leaf → ASKS; its DONE → completed again).
    const fuOpen = (followupsById.get(id) || []).filter((f) => {
      const ft = f.t || 0;
      const minted = (children.get(id) || []).some((c) => seen.has(c) && ((asks.get(c) ?? internals.get(c))?.t || 0) >= ft);
      const refiled = (nodeLinks.get(id) || []).some((l) => (l.t || 0) > ft);
      return !minted && !refiled;
    });
    // a sent follow-up is an owed answer: the worked session is the drop point
    for (const f of fuOpen) openPaths.push({
      name: nameOf(String(a.sid || "")), sid: String(a.sid || ""), color: rompMeta(String(a.sid || "")).color,
      since: f.t || 0,
      lastPhrase: `Follow-up sent: ${String(f.text || "")}`,
    });
    // cleared gate (post-question-fold so resurrection can see the questions)
    const clearedT = clearedAt.get(id);
    const reopened = clearedT !== undefined &&
      (openQuestions.some((q) => q.t > clearedT) || fuOpen.some((f) => (f.t || 0) > clearedT));
    if (clearedT !== undefined && !reopened) continue;
    let column: AskColumn = openQuestions.length ? "needs_input" : allDone && !fuOpen.length ? "completed" : "asks";
    // linked rows: every reply in the subgraph, one row per reply (a reply that
    // serves several nodes keeps its strongest status: question > done > update)
    const rowRank = { question: 2, done: 1, update: 0 } as const;
    const rowFor = (l: any, open: { qlink?: any }): AskLinked => {
      const rel = normRelevance(l.relevance);
      const rid = String(l.reply_id || "");
      const fi = didById.get(rid);
      return {
        // request-scoped phrase first (what this reply did FOR THIS request);
        // the whole-turn reply phrase only when no scoped one exists
        did: l._didFor ? String(l._didFor) : fi ? fi.did : (l._did ? String(l._did) : "(deliverable)"), relevance: rel, t: l.t || 0, reply_id: rid,
        status: rel === "DONE" ? "done" : (rel === "DECISION" || rel === "ACTION" || rel === "IDEA") && open.qlink === l ? "question" : "update",
        sid: String(l.sid || ""), name: nameOf(String(l.sid || "")),
        color: rompMeta(String(l.sid || "")).color,
        answer: l._answer ? true : undefined,    // the user's recorded answer → ↩ row
      };
    };
    // Display rows: ONE row per underlying report. A correction re-verdicts an
    // EXISTING reply (rejudge pass, mark-done, "did it") — it upgrades that
    // row's status but must not appear as a second row, bump its time, or
    // claim the corrector's identity (that combination made dead duplicate
    // rows: wrong session, wrong time, no timeline event to locate). A
    // correction on a node with no matching reply still gets its own row.
    const displayRows = (nid: string, open: NodeStatus): AskLinked[] => {
      const by = new Map<string, AskLinked>();
      for (const l of nodeLinks.get(nid) || []) {            // time-ascending
        const row = rowFor(l, open);
        const prev = by.get(row.reply_id);
        if (!prev) { by.set(row.reply_id, row); continue; }
        if (rowRank[row.status] > rowRank[prev.status]) prev.status = row.status;
        if (!l._corr) prev.t = Math.max(prev.t, row.t);      // a real later filing bumps time; a correction doesn't
      }
      // chronological, oldest first — the modal reads as a linear history
      return Array.from(by.values()).sort((x, y) => x.t - y.t);
    };
    const rowByReply = new Map<string, AskLinked>();
    const nodeRows = new Map<string, AskLinked[]>();
    let last = a.t || 0;
    for (const nid of subgraph) {
      const node = asks.get(nid) ?? internals.get(nid);
      if (node?.t) last = Math.max(last, node.t);            // a freshly-minted turn (e.g. a follow-up) bumps the clock even before its first reply row lands
      const rows = displayRows(nid, stOf.get(nid)!);
      nodeRows.set(nid, rows);
      for (const row of rows) {
        const prev = rowByReply.get(row.reply_id);
        if (!prev || rowRank[row.status] > rowRank[prev.status]) rowByReply.set(row.reply_id, row);
        last = Math.max(last, row.t);                        // corrections excluded: real activity only
      }
    }
    for (const f of fuOpen) last = Math.max(last, f.t || 0); // a fresh follow-up bumps the card
    const linked = Array.from(rowByReply.values()).sort((x, y) => y.t - x.t);
    // the same subgraph as a renderable tree (root first; nest via children)
    const tree: AskTreeNode[] = subgraph.map((nid) => {
      const node = asks.get(nid) ?? internals.get(nid);
      const isAsk = asks.has(nid);
      const rows = nodeRows.get(nid) || [];
      const whoSid = String((isAsk ? node?.sid : (node?.to_sid || node?.sid)) || "");
      return {
        id: nid, kind: isAsk ? "ask" as const : "handoff" as const,
        text: String(node?.text || ""),
        who: nameOf(whoSid), whoSid, whoColor: rompMeta(whoSid).color,
        whoWorking: !!(states && states.get(nameOf(whoSid))?.state === "working"),   // live working dot
        status: rollup(nid),                 // rolled-up: a completed ask shows all-✓
        t: node?.t || 0,
        last: rows.length ? rows[rows.length - 1].t : (node?.t || 0),   // newest REAL activity (rows sorted asc)
        // children chronological too: the whole tree reads oldest → newest
        children: (children.get(nid) || []).filter((c) => seen.has(c))
          .sort((x, y) => ((asks.get(x) ?? internals.get(x))?.t || 0) - ((asks.get(y) ?? internals.get(y))?.t || 0)),
        rows,
      };
    });
    const meta = rompMeta(String(a.sid || ""));
    const name = meta.name ?? String(a.sid || "").slice(0, 8);
    // ---- liveness (see AskLiveness): deterministic from live tmux state + the
    // tree's open handoffs. "Mid-turn" = working/compacting/permission — a
    // permission prompt is a paused turn, not a finished one.
    const busyOf = (nm: string): string => {
      const st = states?.get(nm)?.state || "";
      return st === "working" || st === "compacting" || st === "permission" ? st : "";
    };
    const stateOf = (nm: string): string => (liveNames.has(nm) ? states?.get(nm)?.state || "?" : "gone");
    const openHandoffs = tree.filter((n) => n.kind === "handoff" && n.status !== "done" && n.who !== name);
    const ownerBusy = busyOf(name);
    const delegates = openHandoffs.filter((n) => busyOf(n.who));
    // LATCHED looks-done (the user's ruling 2026-06-11): a busy owner counts as
    // "active" only when its CURRENT turn is CLAIMED by this card — the turn
    // minted/amended/answered it, or its work is linked into the graph. A turn
    // on something else leaves the settled verdict standing: a card that ever
    // looks done stays looking done until real work touches it (a new link or
    // amend refreshes the fold on its own).
    const tids = [String(a.turn_id || ""), ...(amendTurns.get(id) || [])].filter(Boolean);
    const curTurn = ownerBusy ? openTurnId(String(a.sid || "")) : null;
    // conservative claim: a busy owner whose open turn can't be resolved (no
    // events cache yet) HOLDS its cards — never auto-file blind
    const claimed = !!ownerBusy && (curTurn === null || tids.includes(curTurn) || linked.some((r) => r.reply_id === curTurn));
    let liveness: AskLiveness; let livenessWhy: string;
    if (ownerBusy && claimed) {
      liveness = "active";
      livenessWhy = `${name} is mid-turn on THIS card (${ownerBusy})`;
    } else if (delegates.length) {
      liveness = "delegated";
      livenessWhy = delegates.map((n) => `${n.who} is mid-turn (${busyOf(n.who)}) holding "${n.text}"`).join("; ");
    } else if (openHandoffs.length) {
      liveness = "stalled";
      livenessWhy = openHandoffs.map((n) => `handoff "${n.text}" unfinished, ${n.who} ${stateOf(n.who)}`).join("; ")
        + " — that branch owes an ending and nobody is working";
    } else {
      liveness = "settled";
      const owner = stateOf(name) === "gone" ? "is gone"
        : ownerBusy ? "is mid-turn on something ELSE (this card untouched)"
        : `is quiet (${stateOf(name)})`;
      livenessWhy = `${name} ${owner}, no open handoffs — nothing is moving this card without you`;
    }
    // AUTO-FILING (turned on 2026-06-11 after the user's green-ring sweep validated
    // every settled-in-WORKING card as genuinely done): a settled card never
    // sits in WORKING — nothing is moving it, so it rests in COMPLETED now and
    // pulls itself back the moment real work touches it (a new link freshens
    // the fold; liveness goes active when a turn claims it). autoFiled keeps
    // the green ring visible in COMPLETED during the trust-building period —
    // these are the cards to verify before Clear, vs model-stamped DONE.
    // WAIT exemption (the user 2026-06-11): a node whose newest link is WAIT ended
    // its turn on purpose pending an EXTERNAL event (CI, build, a peer's future
    // reply) — not the user. The card is settled but NOT done: it stays in
    // WORKING, no green ring, no auto-filing. New work landing lifts it naturally.
    const extWait = subgraph.some((nid) => {
      const ls = nodeLinks.get(nid) || [];
      const newest = ls.length ? ls[ls.length - 1] : null;
      return !!newest && normRelevance(newest.relevance) === "WAIT";
    });
    if (extWait && liveness === "settled") livenessWhy += " — but it is WAITING on an external event (exempt from auto-filing)";
    // fuOpen guard: a just-sent follow-up holds the card in WORKING until the
    // bookkeeper mints the delivered turn — auto-filing in that gap would show
    // the card as completed at the exact moment the user reopened it.
    // states empty = tmux unreachable: liveness is unknowable, NOT "everyone
    // quiet" — never mass-auto-file on a blind read.
    let autoFiled = false;
    if (states && states.size > 0 && column === "asks" && liveness === "settled" && !fuOpen.length && !extWait) {
      column = "completed";
      autoFiled = true;
      livenessWhy += " — auto-filed from WORKING; verify, then Clear";
    }
    out.push({
      itemId: id, sid: String(a.sid || ""), name, color: meta.color,
      text: String(a.text || ""), t: last, created: a.t || 0,
      live: liveNames.has(name),
      done: linked.filter((r) => r.status === "done").length,
      needsYou: openQuestions.length,
      linked, turnId: String(a.turn_id || ""),
      column, openQuestions, openPaths, reopened, liveness, livenessWhy, autoFiled,
      explicitDone: allDone, waiting: extWait,
      turnIds: tids,
      path: {
        events: [String(a.turn_id || ""), ...linked.map((r) => r.reply_id)].filter(Boolean),
        msgs: subgraph.filter((nid) => internals.has(nid)),
      },
      tree,
    });
  }
  // CLAIM-LAG hold (the user 2026-06-11 evening, timeline_window mis-file): while
  // a session is mid-turn and its open turn is claimed by NO card yet (the ask
  // capture for that prompt hasn't landed), the turn's true card is unknown —
  // one of this session's "settled" cards is probably being worked right now.
  // Hold the whole session's auto-filing until capture lands; the claimed card
  // then goes active and the rest file. Self-heals in seconds.
  const heldSids = new Set<string>();
  for (const a of out) {
    if (heldSids.has(a.sid)) continue;
    const stt = states?.get(a.name)?.state || "";
    if (!(stt === "working" || stt === "compacting" || stt === "permission")) continue;
    const cur = openTurnId(a.sid);
    if (cur && !out.some((b) => b.sid === a.sid
        && (b.turnIds.includes(cur) || b.path.events.includes(cur)))) heldSids.add(a.sid);
  }
  for (const a of out) {
    if (a.autoFiled && heldSids.has(a.sid)) {
      a.autoFiled = false;
      a.column = "asks";
      a.livenessWhy += " — HELD: the session is mid-turn on a not-yet-attributed prompt (it may be this card)";
    }
  }
  out.sort((x, y) => y.t - x.t);
  // group annotation: siblings = visible asks sharing a typed turn
  const byTurn = new Map<string, number>();
  for (const a of out) byTurn.set(a.turnId, (byTurn.get(a.turnId) || 0) + 1);
  for (const a of out) {
    const n = byTurn.get(a.turnId) || 1;
    if (n > 1) { a.groupN = n; a.groupTitle = reqPhraseById.get(a.turnId) || ""; }
  }
  return out;
}

// Exception report (the user's refinement loop, 2026-06-11): free-text + category
// from the modal's ⚠ Report box, with a snapshot of the card's computed state so
// the report is diagnosable later without replaying history. Own file (not
// corrections.jsonl — these carry no should_have verdict for the read-side fold);
// consumed by prompt-rework passes as labeled failure examples.
function appendReport(itemId: string, category: string, note: string, snapshot: any) {
  try {
    fs.mkdirSync(ROMP_REQUESTS, { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS, "reports.jsonl"),
      JSON.stringify({ kind: "report", id: itemId, t: Math.floor(Date.now() / 1000),
        category, note, snapshot }) + "\n");
  } catch { /* ignore */ }
}

// ---- missed-handoff suspect sweep (deterministic, the user 2026-06-11) ----
// A message the classifier judged "not a delegation" (req-decision, req=false)
// is SUSPECT when the recipient then produced work linked to NOTHING within the
// window — orphan work right after a dismissed message is the classic missed
// handoff. Read from the decision log (mtime-cached); surfaced as a ⚠ badge on
// the sender's most plausible open card, where the user confirms or rejects via
// the Report box. Pure joins, no model.
const SUSPECT_WINDOW = 45 * 60;        // recipient orphan work this soon after the message
const SUSPECT_HORIZON = 48 * 3600;     // ignore older history
let _suspectCache: { key: string; rows: any[] } | null = null;
function missedHandoffSuspects(now: number): Array<{ mid: string; fromSid: string; toSid: string; t: number; snippet: string; orphanT: number }> {
  const files = [path.join(ROMP_REQUESTS, "decision-log.jsonl"), path.join(ROMP_REQUESTS, "decision-log.jsonl.1")];
  const key = files.map((f) => { try { return String(fs.statSync(f).mtimeMs); } catch { return "0"; } }).join("|");
  if (_suspectCache && _suspectCache.key === key) return _suspectCache.rows;
  const dismissed: any[] = []; const orphanLinks: Array<{ sid: string; t: number }> = [];
  const audits = new Map<string, string>();   // msg_id → Opus verdict (handoff/fyi/unsure)
  for (const f of files) {
    let raw = "";
    try { raw = fs.readFileSync(f, "utf8"); } catch { continue; }
    for (const ln of raw.split("\n")) {
      if (!ln.trim()) continue;
      let o: any; try { o = JSON.parse(ln); } catch { continue; }
      if (o.kind === "suspect-audit" && o.msg_id) { audits.set(String(o.msg_id), String(o.verdict || "unsure")); continue; }
      if ((o.t || 0) < now - SUSPECT_HORIZON) continue;
      if (o.kind === "req-decision" && o.req === false && o.msg_id) dismissed.push(o);
      else if (o.kind === "link" && Array.isArray(o.chosen) && !o.chosen.length && o.sid) orphanLinks.push({ sid: String(o.sid), t: o.t || 0 });
    }
  }
  // Only UNSURE Opus audits reach the human (the user 2026-06-11: 41 raw
  // correlations in 48h, almost all FYIs). The daemon's auditor repairs real
  // handoffs automatically and suppresses coincidences; unaudited suspects just
  // wait their turn in the queue rather than nagging.
  const rows = dismissed.flatMap((d) => {
    if (audits.get(String(d.msg_id)) !== "unsure") return [];
    const orphan = orphanLinks.find((l) => l.sid === String(d.to_sid) && l.t > (d.t || 0) && l.t <= (d.t || 0) + SUSPECT_WINDOW);
    return orphan ? [{ mid: String(d.msg_id), fromSid: String(d.from_sid || ""), toSid: String(d.to_sid || ""),
      t: d.t || 0, snippet: String(d.snippet || "").slice(0, 160), orphanT: orphan.t }] : [];
  });
  _suspectCache = { key, rows };
  return rows;
}

// the user's Clear — the one human-asserted fact in the registry. cleared.jsonl is
// the UI's file (the daemon only reads it); single-writer holds because the feed
// is the only surface that clears today. Append-only, one JSON line per clear.
function appendCleared(id: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS, { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS, "cleared.jsonl"),
      JSON.stringify({ id, t: Math.floor(Date.now() / 1000) }) + "\n");
  } catch { /* ignore */ }
}

// UndoClear: pop the NEWEST cleared.jsonl row (single-writer + append-only, so
// the last line is always the most recent Clear) and the card comes back for
// every reader — daemon and pipeline included — with no schema change. The
// rewrite goes through tmp+rename so the read-only consumers never see a torn
// file. Note: a clear that came from "didn't need me" leaves its relevance
// correction in place — undo restores the card, it doesn't retract the label.
function undoLastClear(): boolean {
  try {
    const p = path.join(ROMP_REQUESTS, "cleared.jsonl");
    const lines = fs.readFileSync(p, "utf8").split("\n").filter((l) => l.trim());
    if (!lines.length) return false;
    const popped = lines.pop()!;
    const tmp = p + ".tmp";
    fs.writeFileSync(tmp, lines.length ? lines.join("\n") + "\n" : "");
    fs.renameSync(tmp, p);
    // An undone clear means "I didn't mean that" — so the cleared-as-done labels
    // that clear minted are wrong too. Retract exactly them (matched by the card
    // id stamped into their note), keeping the training data honest.
    try {
      const id = String(JSON.parse(popped).id || "");
      if (id) {
        const cp = path.join(ROMP_REQUESTS, "corrections.jsonl");
        const rows = fs.readFileSync(cp, "utf8").split("\n").filter((l) => l.trim());
        const kept = rows.filter((l) => !(l.includes(`(card ${id})`) && l.includes("cleared-as-done")));
        if (kept.length !== rows.length) {
          const ctmp = cp + ".tmp";
          fs.writeFileSync(ctmp, kept.length ? kept.join("\n") + "\n" : "");
          fs.renameSync(ctmp, cp);
        }
      }
    } catch { /* corrections file absent — nothing to retract */ }
    return true;
  } catch { return false; }
}

// the user's mark-done — an adjudication, not a dismissal. corrections.jsonl is
// spec'd any-session-append (REQUESTS.md): short atomic appends, ground truth
// attached to the decision it corrects. The fold merges these as links, so the
// card completes with credit; haiku's pipeline replays them as labels.
// "Follow up" on a COMPLETED card: the text was delivered to the session as a
// typed prompt; this record reopens the card to ASKS until the bookkeeper
// mints that turn under the root. followups.jsonl is the feed's file (the
// daemon only reads it), same single-writer rule as cleared.jsonl.
function appendFollowup(id: string, sid: string, text: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS, { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS, "followups.jsonl"),
      JSON.stringify({ id, sid, t: Math.floor(Date.now() / 1000), text }) + "\n");
  } catch { /* ignore */ }
}

function appendCorrection(nodeId: string, decisionRef: string | null, note: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS, { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS, "corrections.jsonl"),
      JSON.stringify({
        t: Math.floor(Date.now() / 1000), by_sid: "feed-panel", kind: "link",
        decision_ref: decisionRef,
        should_have: { request_ids: [nodeId], relevance: "DONE" }, note,
      }) + "\n");
  } catch { /* ignore */ }
}

// "didn't need me" on a STANDALONE awaiting item: no request node to re-verdict,
// so the correction carries only the relevance the tag should have had. The fold
// readers skip rows without request_ids (read-side merge rule), so this is purely
// a training label for the relevance classifier; the paired Clear retires the card.
function appendRelevanceCorrection(replyId: string, note: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS, { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS, "corrections.jsonl"),
      JSON.stringify({
        t: Math.floor(Date.now() / 1000), by_sid: "feed-panel", kind: "relevance",
        decision_ref: replyId,
        should_have: { relevance: "DONE" }, note,
      }) + "\n");
  } catch { /* ignore */ }
}

const FEED_LIMIT = 200;
// One-time backlog floor: relevance tagging went live ~2026-06-08 17:27 PDT, so
// everything before that is the pre-tagging backlog (~930 untagged/legacy items).
// Hiding it durably (a constant, no per-id dismissed-set bloat) makes the feed
// start fresh from the tagging era — only tagged-era + newer entries show.
const FEED_FLOOR = 1780964820;   // epoch seconds of the cutoff
// The request registry went live 2026-06-09 ~13:26 (haiku's REQUESTS_FLOOR). Turns
// before it can never be linked to an ask, so standalone-card logic starts here.
const REQUESTS_FLOOR = 1781036800;

function feedDismissed(): Set<string> {
  try { return new Set(ctx.globalState.get<string[]>("rompFeedDismissed", []) || []); }
  catch { return new Set(); }
}
function setFeedDismissed(s: Set<string>) {
  try { ctx.globalState.update("rompFeedDismissed", Array.from(s)); } catch { /* ignore */ }
}

// Recompute the feed and push it to the webview — but only when something the
// user would see changed (item set, liveness, or a per-item minute bucket so the
// "Xm ago" label + color fade stay fresh without churning every 800ms tick).
function refreshFeed(force = false) {
  if (!feedPanel || !feedReady) return;
  const dismissed = feedDismissed();
  // Registry overlays for the three-column view: which replies are linked into
  // some ask (they render inside the ask, never standalone), and which ids
  // the user has Cleared (ask ids and reply ids share cleared.jsonl).
  const linkedReplies = new Set<string>(
    readReqRows("links.jsonl").filter((l) => l.kind === "link" && l.reply_id).map((l) => String(l.reply_id)));
  const clearedRows = readReqRows("cleared.jsonl");
  const clearedIds = new Set<string>(clearedRows.map((c) => String(c.id)));
  const all = computeFeedItems(lastStates).filter((i) => i.t >= FEED_FLOOR)    // drop pre-tagging backlog
    .map((i) => ({
      ...i,
      inAsk: linkedReplies.has(i.itemId),
      // standalone-card eligibility: user-prompted finished/blocked work that no ask
      // claims. Gated at the REGISTRY floor — before it, no asks existed, so every
      // old turn would vacuously qualify and the pre-registry tail would flood in
      // (e.g. the 20h-old "phantom connector" card).
      // A standalone needs-you card gets the SAME crossoff as ask questions: once
      // the user types a later turn in that session, he has seen/answered it — it
      // must not sit in Awaiting forever (it has no DAG, so nothing else retires it).
      standalone: linkedReplies.has(i.itemId) === false && i.origin === "user"
        && (i.relevance === "DONE"
          || (i.relevance === "DECISION" && (lastReqBySid.get(i.sid) || 0) <= i.t))
        && i.t >= REQUESTS_FLOOR,
    }));
  const filtered = all.filter((i) => !clearedIds.has(i.itemId))
    .filter((i) => (feedShowDismissed ? dismissed.has(i.itemId) : !dismissed.has(i.itemId)));
  const now = Math.floor(Date.now() / 1000);
  // Cap PER ORIGIN class (newest N of each, re-merged by time): the webview's
  // "internal" toggle filters client-side, so on agent-heavy days a single cap
  // would let internal items crowd the user's out of the window (and vice versa).
  const userItems = filtered.filter((i) => i.origin === "user").slice(0, FEED_LIMIT);
  const agentItems = filtered.filter((i) => i.origin === "agent").slice(0, FEED_LIMIT);
  const items = [...userItems, ...agentItems].sort((a, b) => b.t - a.t)
    .map((i) => ({ ...i, trgb: ageRgbTuple(now - i.t) }));
  // asks ride the same push; the webview's "asks" toggle switches the list view
  const didById = new Map(all.map((i) => [i.itemId, i] as const));
  // recency tint (the Hawaii ramp) precomputed host-side for every timestamp the
  // modal renders: per ask, per tree node (last activity), per history row
  const asks = computeAskItems(lastStates, didById).map((a) => ({
    ...a,
    trgb: ageRgbTuple(now - a.t),
    tree: a.tree.map((n) => ({
      ...n,
      trgb: ageRgbTuple(now - n.last),
      rows: n.rows.map((r) => ({ ...r, trgb: ageRgbTuple(now - r.t) })),
    })),
  }));
  lastAskItems = asks;   // kept for the showAskPath handler (timeline DAG highlight)
  // NEEDS INPUT is a UNION: text-DECISION links (above) + sessions LIVE-blocked on
  // the user — a permission prompt or a modal picker (@claude-state from tmux; postal
  // emits "picker" on a stuck revive). These are ephemeral session states, not
  // registry objects: no Clear button (they self-resolve when the user acts), the
  // card's click opens the session. One card per blocked session.
  const BLOCKED_STATES = new Set(["permission", "picker"]);
  const blocked: any[] = [];
  if (lastStates) {
    for (const [name, info] of lastStates) {
      if (!BLOCKED_STATES.has(info.state)) continue;
      const id = rompIds().find((i) => (rompMeta(i).name ?? i.slice(0, 8)) === name);
      const sinceT = Number(info.since) || 0;
      // auto-mode debounce (2026-06-11): with auto mode on, every tool fires a
      // permission notification that the classifier allows seconds later — a
      // "permission" younger than this isn't blocked, it's mid-decision.
      if (info.state === "permission" && now - sinceT < 15) continue;
      const what = info.state === "permission" ? "waiting for your approval (permission prompt)"
        : "blocked on the resume picker";
      // The user's ruling (2026-06-11): a blocked session is NOT its own card — the
      // ask the session is blocked ON moves to BLOCKED itself. Resolve the live
      // turn to its card(s) via the turn ids that minted/amended each ask plus
      // its linked events. The synthetic session card below is an ERROR FLAG,
      // not a supported card type: under the every-prompt-mints rule an
      // unclaimed live turn means capture/linking missed (or the card was
      // cleared — the benign overlap), so the webview renders it with a ⚠
      // suspect badge whose modal explains the miss. It also keeps the block
      // visible — a block must never be invisible, even when bookkeeping failed.
      const ev = id ? turnEvent(id, null, sinceT || now) : null;
      const hit = ev ? asks.filter((a) => a.sid === id
        && (a.turnIds.includes(String(ev.id)) || (a.path?.events || []).includes(String(ev.id)))) : [];
      if (hit.length) {
        for (const a of hit) a.blocked = { state: info.state, since: sinceT, what };
        continue;
      }
      blocked.push({
        sid: id ?? "", name, color: id ? rompMeta(id).color : null,
        state: info.state, since: sinceT, what,
      });
    }
  }
  // missed-handoff suspects → ⚠ on the sender's most plausible open card (the
  // one with the newest activity at send time); confirm/reject via the Report box
  for (const s of missedHandoffSuspects(now)) {
    const cands = asks.filter((a) => a.sid === s.fromSid && a.created <= s.t);
    if (!cands.length) continue;
    const actAt = (a: any) => Math.max(a.created, ...(a.linked || []).filter((r: any) => (r.t || 0) <= s.t).map((r: any) => r.t || 0));
    const card: any = cands.reduce((x: any, y: any) => (actAt(y) > actAt(x) ? y : x));
    const toName = rompMeta(s.toSid).name ?? s.toSid.slice(0, 8);
    (card.suspects = card.suspects || []).push({
      mid: s.mid, to: toName, t: s.t, snippet: s.snippet,
      why: `a message to ${toName} was judged not-a-delegation, but ${toName} then did work linked to no card`,
    });
  }
  const sig = `${feedShowDismissed ? "D" : "L"}:${dismissed.size}:${clearedRows.length}:`
    + items.map((i) => `${i.itemId}:${i.live ? 1 : 0}:${i.relevance}:${i.origin === "user" ? "u" : "a"}:${i.inAsk ? 1 : 0}:${Math.floor((now - i.t) / 60)}`).join("|")
    + "‖A:" + asks.map((a) => `${a.itemId}:${a.live ? 1 : 0}:${a.done}:${a.needsYou}:${a.linked.length}:${Math.floor((now - a.t) / 60)}:${a.text.length}:${a.column}:${a.reopened ? "R" : ""}:${a.liveness}:${a.blocked ? "B" : ""}:${a.autoFiled ? "AF" : ""}:${a.explicitDone ? "X" : ""}:${a.waiting ? "W" : ""}:${(a as any).suspects ? (a as any).suspects.length : 0}:${a.openPaths.length}:${a.tree.map((n) => n.status[0] + (n.whoWorking ? "W" : "")).join("")}:${a.openQuestions.map((q) => q.reply_id + q.qtype[0] + (q.brief ? "+b" : "")).join(",")}`).join("|")
    + "‖B:" + blocked.map((b) => `${b.name}:${b.state}:${Math.floor((now - b.since) / 60)}`).join("|")
    + "‖W:" + workingNames(lastStates).join(",");   // working-name set → re-push so name dots update live
  lastFeedItems = items;   // kept for the rail-dot handlers (event → standalone card)
  if (!force && sig === feedSig) return;
  feedSig = sig;
  feedPost({ type: "feed", items, asks, blocked, now, working: workingNames(lastStates), dismissedCount: dismissed.size, showDismissed: feedShowDismissed, canUndoClear: clearedRows.length > 0 });
}

function feedPost(msg: any) { feedPanel?.webview.postMessage(msg); }

// ---- chat rail-dot ↔ timeline/feed links ----
// A dot on the chat's rail IS a turn; the turn (if work started there) IS a
// romp-events event; that event can be the root or a linked reply of feed
// cards. Hovering a dot fans out to both surfaces (timeline white highlight +
// feed card outline); clicking opens the matching feed card's modal.
let lastFeedItems: any[] = [];   // final standalone-item payload of the last feed push (cleared/dismissed already filtered)
let pendingDotOpen: { sid: string; uuid: string | null; t: number } | null = null; // dot click while the feed webview is cold — replayed on its ready

// Map a chat turn (anchor uuid + epoch) to its romp-events event via the
// events-cache snapshot romp-events maintains per session: uuid identity first
// (event.uuid = the prompt line, workUuid/replyUuid = its work/reply anchors),
// then containment in the event's [t, end) work period, then the last event
// started before t (reply tails past `end` still belong to that turn's work).
function turnEvent(sid: string, uuid: string | null, t: number): any | null {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(ROMP_STATE, "events-cache", `${sid}.json`), "utf8"));
    const evs: any[] = raw?.data?.events || [];
    if (uuid) {
      const byU = evs.find((e) => e.uuid === uuid || e.workUuid === uuid || e.replyUuid === uuid);
      if (byU) return byU;
    }
    if (t) {
      const inPeriod = evs.find((e) => t >= e.t && t < (e.end || e.t + 1));
      if (inPeriod) return inPeriod;
      const before = evs.filter((e) => e.t <= t);
      if (before.length) return before[before.length - 1];
    }
  } catch { /* no events cache for this session */ }
  return null;
}

// The session's currently-OPEN turn id, from the romp-events disk cache
// (mtime-cached). Drives the liveness claim-join: "active" requires the owner's
// current turn to be claimed by the card (latched looks-done, the user 2026-06-11).
const _openTurnCache = new Map<string, { m: number; id: string | null }>();
function openTurnId(sid: string): string | null {
  const f = path.join(ROMP_STATE, "events-cache", `${sid}.json`);
  let st: fs.Stats;
  try { st = fs.statSync(f); } catch { return null; }
  const hit = _openTurnCache.get(sid);
  if (hit && hit.m === st.mtimeMs) return hit.id;
  let id: string | null = null;
  try {
    const evs: any[] = JSON.parse(fs.readFileSync(f, "utf8"))?.data?.events || [];
    const last = evs[evs.length - 1];
    id = last && last.open ? String(last.id) : null;
  } catch { /* unreadable cache → claim unknown */ }
  _openTurnCache.set(sid, { m: st.mtimeMs, id });
  return id;
}

// The still-open feed cards built from an event: ask cards whose DAG contains
// it + standalone deliverable cards keyed by it. Both source lists come from
// the last feed compute, which already filters Cleared/dismissed — so "in the
// list" = "still open". `open` is the feed modal key (fullscreenAskId); `dom`
// lists the data-key candidates for the hover outline (an ask folded into a
// sibling group renders as the group card g:<turnId>, not its own card).
function cardsForEvent(eid: string): Array<{ open: string; dom: string[]; label: string; detail: string }> {
  const out: Array<{ open: string; dom: string[]; label: string; detail: string }> = [];
  for (const a of lastAskItems) {
    const hit = a.turnId === eid || (a.path?.events || []).includes(eid)
      || (a.linked || []).some((l: any) => String(l.reply_id) === eid);
    if (hit) out.push({ open: a.itemId, dom: ["a:" + a.itemId, "g:" + a.turnId], label: a.text, detail: `ask · ${a.name}` });
  }
  for (const i of lastFeedItems) {
    if (i.standalone && String(i.itemId) === eid)
      out.push({ open: "i:" + i.itemId, dom: ["i:" + i.itemId], label: i.did, detail: `deliverable · ${i.name}` });
  }
  return out;
}

function onDotHover(sid: string | null, uuid: string | null, t: number) {
  const ev = sid ? turnEvent(sid, uuid, t) : null;
  if (!ev) { hoverTimeline(null); feedPost({ type: "hoverCards", keys: [], eid: null }); return; }
  hoverTimeline(String(ev.id));
  // eid → the feed also white-rings the matching ROWS inside an open modal
  feedPost({ type: "hoverCards", keys: cardsForEvent(String(ev.id)).flatMap((c) => c.dom), eid: String(ev.id) });
}

async function onDotOpen(sid: string, uuid: string | null, t: number) {
  // Cold feed → card lists may be stale/empty. Open the panel and replay this
  // click from its ready handler, where refreshFeed has just recomputed them.
  if (!feedPanel || !feedReady) {
    pendingDotOpen = { sid, uuid, t };
    openFeedPanel(false);
    return;
  }
  const ev = turnEvent(sid, uuid, t);
  const cards = ev ? cardsForEvent(String(ev.id)) : [];
  if (!cards.length) { vscode.window.setStatusBarMessage("romp: this turn has no open feed card", 4000); return; }
  let chosen = cards[0];
  if (cards.length > 1) {
    const pick = await vscode.window.showQuickPick(
      cards.map((c) => ({ label: c.label, description: c.detail, card: c })),
      { placeHolder: "This turn appears in several feed cards — open which one?" });
    if (!pick) return;
    chosen = (pick as vscode.QuickPickItem & { card: typeof chosen }).card;
  }
  openFeedPanel(false); // reveal + focus the feed
  // hl → the modal opens with the clicked turn's row(s) white-ringed + scrolled to
  feedPost({ type: "openCard", key: chosen.open, hl: ev ? String(ev.id) : null });
}

// ---- expand → action paragraph (lazy, cached per deliverable) ----
// On expand the webview asks for feed-detail/<id>.json (produced by the separate
// `romp-feed-detail` generator, keyed by the entry's romp-events event id == our
// itemId). Cache hit → push it. Miss → spawn the producer detached and poll for
// the file (a generation failure writes NOTHING, so a lasting miss = unavailable).
const ROMP_FEED_DETAIL = path.join(ROMP_STATE, "feed-detail");
const feedDetailPending = new Set<string>();   // ids spawned + currently polled

// Feed → timeline linked projection: write a focus-request file that db_timeline's
// timeline fs.watches (symmetric with how we publish chat-active). Keyed by the
// event id (== our feed itemId); `nonce` makes a repeat-click on the same id
// re-fire the watch. Atomic tmp+rename so the watcher never reads a half file.
const ROMP_TIMELINE_FOCUS = path.join(ROMP_STATE, "timeline-focus.json");
// `dag` (optional) = an ask's full request subgraph for the timeline to outline
// as one path: typed-turn + reply event ids, and handoff postal-message ids
// (the timeline already keys its message connectors by those). Readers that
// don't know the field ignore it.
// `anchor` tells the timeline WHICH glyph of the turn the click means — the
// kind of the event can't disambiguate: a reply on a TYPED turn shares its id
// with the user's prompt dot. Work-row clicks mean the WORK (bar/response);
// ask-card locates mean the PROMPT dot. Absent → timeline's kind-inference.
// `locate:false` = paint the dag overlay but do NOT jump/select/open chat —
// card-body expand wants the journey visible without yanking the user's view;
// only an explicit title-click locate should move anything.
// Jump the CHAT panel to the user's instruction behind a feed card, from
// first-party data only: the card's session + the request's mint epoch (both
// stamped when the registry minted the ask from that typed turn). No uuid, no
// event-table hop — the webview lands on the user turn nearest the moment
// (data-t == mint t for a normal typed prompt, so this is exact), and the
// kind restriction means the worst case is a NEARBY prompt, never a reply.
function locateInChat(sid: string, t: number) {
  if (!sid || !t) return;
  // Exact-fsid tab already open → focus it.
  const direct = resolveDeepLink(sid);
  if (direct && sessions.has(direct.id)) {
    openPanel(false);
    post({ type: "focus", id: direct.id, anchorT: t, anchorKind: "user" });
    return;
  }
  // Fork/incarnation-aware: a card stamped with an old/forked fsid still belongs
  // to a live session under its customTitle — locate into THAT, not the stale
  // fork. A passive locate never offers revive, so a dead session just highlights.
  const target = resolveSession(sid);
  if (!target || !target.liveName) return;   // dead + unopened: highlight only
  const lr = resolveDeepLink(target.liveName) ?? target;
  if (sessions.has(lr.id)) {
    openPanel(false);
    post({ type: "focus", id: lr.id, anchorT: t, anchorKind: "user" });
    return;
  }
  const cold = !panel;          // a freshly-created webview isn't listening yet
  openPanel(false);
  addSession(lr.file);
  if (cold) pendingFocus = { id: lr.id, anchorT: t, anchorKind: "user" };
  else post({ type: "focus", id: lr.id, anchorT: t, anchorKind: "user" });
}

// Landing-diagnostics log: one JSON line per deep-link landing attempt, from
// the chat webview's locateDiag report. trail examples: ["pointer-exact"],
// ["pointer-wrong-kind", "time-near-3s"], ["pointer-not-rendered",
// "no-user-turns"]. Read it when the user reports a click that landed weird.
const ROMP_LOCATE_DIAG = path.join(ROMP_STATE, "locate-diag.jsonl");
function appendLocateDiag(m: any) {
  try {
    fs.appendFileSync(ROMP_LOCATE_DIAG, JSON.stringify({
      t: Math.floor(Date.now() / 1000), sid: String(m.id || ""), ok: !!m.ok,
      trail: Array.isArray(m.trail) ? m.trail.map(String) : [],
      ...(m.anchor ? { anchor: String(m.anchor) } : {}),
      ...(typeof m.anchorT === "number" ? { anchorT: m.anchorT } : {}),
      ...(m.kind ? { kind: String(m.kind) } : {}),
    }) + "\n");
  } catch { /* ignore */ }
}

// `jump` (only meaningful with locate:false): db_timeline PANS the timeline to
// bring the painted DAG on-screen — no pulse, no chat-open (the chat jump is
// first-party, locateInChat). The DOUBLE-CLICK pin sets it; hover never does.
function focusTimeline(id: string, sid: string, t: number, dag?: { ask: string; events: string[]; msgs: string[] }, anchor?: "prompt" | "work", locate?: boolean, jump?: boolean) {
  try {
    const tmp = ROMP_TIMELINE_FOCUS + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify({
      id, sid, t, nonce: Date.now(),
      ...(dag ? { dag } : {}), ...(anchor ? { anchor } : {}), ...(locate === false ? { locate: false } : {}),
      ...(jump ? { jump: true } : {}),
    }));
    fs.renameSync(tmp, ROMP_TIMELINE_FOCUS);
  } catch { /* ignore */ }
}

// Transient hover-highlight channel (db_timeline leads it; SEPARATE from the
// click pan/pulse focus above so fast hover never thrashes timeline-focus.json's
// nonce). Hovering a line in the ask modal writes {id, ids, nonce}; db_timeline
// draws a light transient outline on those events, cleared on null. `ids` is
// the full set (a parent line hovers the UNION of everything under it); `id`
// stays as the first entry for the pre-array reader. Debounced ~40ms, atomic
// tmp+rename — contract agreed with db_timeline 2026-06-09, ids added 06-10.
const ROMP_TIMELINE_HOVER = path.join(ROMP_STATE, "timeline-hover.json");
let hoverNonce = 0;
let hoverTimer: ReturnType<typeof setTimeout> | undefined;
let hoverPendingIds: string[] | null = null;
function hoverTimeline(ids: string[] | string | null) {
  hoverPendingIds = ids == null ? null : Array.isArray(ids) ? ids : [ids];
  if (hoverTimer) return;
  hoverTimer = setTimeout(() => {
    hoverTimer = undefined;
    try {
      const tmp = ROMP_TIMELINE_HOVER + ".tmp";
      fs.writeFileSync(tmp, JSON.stringify({
        id: hoverPendingIds ? hoverPendingIds[0] : null,
        ids: hoverPendingIds, nonce: ++hoverNonce,
      }));
      fs.renameSync(tmp, ROMP_TIMELINE_HOVER);
    } catch { /* ignore */ }
    chatGlow(hoverPendingIds);   // same transient hover, fanned to the chat panel
  }, 40);
}

// Fan the modal-row hover out to the CHAT panel too (the user 2026-06-11):
// white-ring the rail dots of every chat turn inside the hovered event's span,
// and any postal card carrying a hovered message id. An event id self-describes
// its session and start (`<sid>:<turn-start>:<hash>`); the matching feed row's
// t (the period end) bounds the span. Ids without the event shape are postal
// message ids. null/empty → clear. Rides hoverTimeline's 40ms debounce.
function chatGlow(ids: string[] | null) {
  if (!panel) return;
  const groups = new Map<string, Array<[number, number]>>();
  const mids: string[] = [];
  for (const id of ids || []) {
    const parts = id.split(":");
    if (parts.length >= 3 && /^\d+$/.test(parts[1])) {
      const sid = parts[0];
      const start = parseInt(parts[1], 10);
      let end = start;
      for (const a of lastAskItems) {
        for (const l of a.linked || []) if (String(l.reply_id) === id) end = Math.max(end, l.t || start);
        for (const n of a.tree || []) for (const r of n.rows || []) if (String(r.reply_id) === id) end = Math.max(end, r.t || start);
      }
      if (!groups.has(sid)) groups.set(sid, []);
      groups.get(sid)!.push([start, end]);
    } else if (id) mids.push(id);
  }
  post({ type: "glowTurns", groups: Array.from(groups, ([sid, ranges]) => ({ sid, ranges })), mids });
}

function readFeedDetail(id: string): any | null {
  try {
    const raw = fs.readFileSync(path.join(ROMP_FEED_DETAIL, `${id}.json`), "utf8").trim();
    if (!raw) return null;
    const d = JSON.parse(raw);
    return d && typeof d.paragraph === "string" && d.paragraph ? d : null;
  } catch { return null; }
}

function feedDetailBin(): string {
  const local = path.join(os.homedir(), "GitRepos", "romp", "bin", "romp-feed-detail");
  try { if (fs.existsSync(local)) return local; } catch { /* ignore */ }
  return "romp-feed-detail";
}

// A real romp-events id is exactly `<fsid>:<ts>:<hash>` (3 colon-parts, uuid head);
// our legacy/synthesized fallback ids have 4 parts and never bind to a producer.
function isEventId(id: string): boolean {
  const p = id.split(":");
  return p.length === 3 && /^[0-9a-f-]{16,}$/i.test(p[0]) && /^\d+$/.test(p[1]);
}

// `generate` is true only for DONE/DECISION items — those get a pre-warmed JLD
// paragraph. DETAILS/UNTAGGED intentionally have NO paragraph (haiku's cost cut),
// so we read the cache if present but never spawn-and-wait for them.
function requestFeedDetail(id: string, generate: boolean) {
  const cached = readFeedDetail(id);
  if (cached) { feedPost({ type: "detail", itemId: id, detail: cached }); return; }
  if (!generate) { feedPost({ type: "detailFailed", itemId: id, reason: "none" }); return; }
  if (!isEventId(id)) { feedPost({ type: "detailFailed", itemId: id, reason: "legacy" }); return; }
  feedPost({ type: "detailPending", itemId: id });
  if (feedDetailPending.has(id)) return;       // already generating + polling
  feedDetailPending.add(id);
  try {
    const child = spawn(feedDetailBin(), [id], { detached: true, stdio: "ignore", env: tmuxEnv() });
    // A missing producer emits an async 'error' (ENOENT) — swallow it (an unhandled
    // 'error' on a ChildProcess would otherwise crash the extension host). The poll
    // below reports the lasting cache miss as "unavailable".
    child.on("error", () => { /* producer not installed / failed to launch */ });
    child.unref();
  } catch { /* producer unavailable; poll still covers a file written elsewhere */ }
  pollFeedDetail(id, 0);
}

function pollFeedDetail(id: string, tries: number) {
  if (!feedPanel) { feedDetailPending.delete(id); return; }
  const d = readFeedDetail(id);
  if (d) { feedDetailPending.delete(id); feedPost({ type: "detail", itemId: id, detail: d }); return; }
  if (tries >= 30) { feedDetailPending.delete(id); feedPost({ type: "detailFailed", itemId: id, reason: "timeout" }); return; }
  setTimeout(() => pollFeedDetail(id, tries + 1), 500);   // ~15s budget
}

// ---- answering the resume picker from VS Code ----
// The picker lives in the tmux pane, invisible here. Clicking its needs-input
// card brings the CHOICE to the user instead of telling him to go find a terminal:
// read the live pane, show the same options as a QuickPick, forward his pick as
// keystrokes. the user decides; we only transport (the never-auto-answer rule holds).
const PICKER_OPTS = ["Resume from summary (recommended)", "Resume full session as-is"];
async function answerPicker(name: string) {
  const cap = await new Promise<string>((res) => {
    const p = spawn("tmux", ["capture-pane", "-p", "-t", name], { env: tmuxEnv() });
    let out = "";
    p.stdout?.on("data", (d) => (out += String(d)));
    p.on("close", () => res(out));
    p.on("error", () => res(""));
  });
  const lines = cap.split("\n");
  const opts = PICKER_OPTS.filter((o) => lines.some((l) => l.includes(o)));
  if (!opts.length) {
    vscode.window.showInformationMessage(`${name}: the picker is no longer on screen.`);
    refreshFeed(true);
    return;
  }
  const pick = await vscode.window.showQuickPick(opts, { placeHolder: `${name} is waiting on the resume picker — choose to answer it` });
  if (!pick) return;
  // Current highlight = the option line carrying the selector glyph (Ink uses ❯);
  // when not found, the picker default is the first option.
  let cur = 0;
  opts.forEach((o, i) => {
    const l = lines.find((x) => x.includes(o));
    if (l && l.includes("❯")) cur = i;
  });
  const want = opts.indexOf(pick);
  const keys: string[] = [];
  for (let i = 0; i < Math.abs(want - cur); i++) keys.push(want > cur ? "Down" : "Up");
  keys.push("Enter");
  spawn("tmux", ["send-keys", "-t", name, ...keys], { env: tmuxEnv() }).on("error", () => { /* session gone */ });
  setTimeout(() => refreshFeed(true), 1200);   // state hook flips picker→working shortly after
}

// Clicking a session in the feed should bring the romp CHAT panel forward and
// show that session — so reveal/create the chat panel (flips to its tab / focuses
// its group) FIRST, then open the session tab inside it.
function openSessionFromFeed(id: string) {
  openPanel();              // reveal existing chat panel (or create it), bringing it to the front
  openSessionById(id);      // add/focus the session's tab there (prompts to reopen if it's dead)
}

// One feed webview, opened beside the chat panel (its own viewType so the two are
// independent editor tabs side by side). `column` pins where it lands (the icon
// passes the group after the chat's); when the feed already exists it stays
// where the user put it, unless it's stacked as a tab in the chat's own group —
// then it's moved out so the two are actually side by side.
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
  feedReady = false;
  feedSig = "";
  p.webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extUri, "dist"), vscode.Uri.joinPath(extUri, "media")],
  };
  p.iconPath = vscode.Uri.joinPath(extUri, "media", "romp-swirl.svg");
  p.webview.html = buildFeedHtml(p.webview);
  p.webview.onDidReceiveMessage((m) => {
    if (!m) return;
    if (m.type === "ready") {
      feedReady = true;
      refreshFeed(true);
      // a rail-dot click arrived while this webview was cold — resolve it now,
      // against the card lists refreshFeed just recomputed
      if (pendingDotOpen) { const p = pendingDotOpen; pendingDotOpen = null; onDotOpen(p.sid, p.uuid, p.t); }
    }
    else if (m.type === "openSession" && m.id) openSessionFromFeed(String(m.id));
    else if (m.type === "expand" && m.itemId) requestFeedDetail(String(m.itemId), !!m.generate);
    // deliverable/work-row clicks always mean the WORK, even on a typed turn.
    // PROMPT-intent clicks locate the chat HERE (first-party time + kind, see
    // locateInChat) — the timeline only gets the paint, never the chat jump.
    else if (m.type === "showOnTimeline" && m.itemId) {
      const prompt = m.anchor === "prompt";
      focusTimeline(String(m.itemId), String(m.sid ?? ""), Number(m.t) || 0, undefined, prompt ? "prompt" : "work", prompt ? false : undefined);
      if (prompt) locateInChat(String(m.sid ?? ""), Number(m.t) || 0);
    }
    // ask-card click → outline the ask's WHOLE request DAG on the timeline.
    // m.locate===false (card-body expand) paints the journey only. A title
    // click (locate) jumps the CHAT directly from first-party data — the
    // ask's own session + mint time, landing restricted to the user's turns
    // — never via the timeline's event-pointer resolution. That pipeline
    // (turn id → event row → transcript uuid → DOM) substitutes neighboring
    // lines when a prompt is orphaned (compaction, rewinds), which is how
    // title clicks kept landing on assistant replies or, when every hop
    // missed, bottom-dumping to the newest turns. The timeline still paints
    // the DAG; it just never drives the chat scroll (locate stays false).
    // m.off (double-click toggle OFF) clears the overlay: a fresh focus with no
    // dag and no locate — the timeline drops the white outlines, view unmoved.
    // m.jump (double-click PIN) asks the timeline to PAN to the painted DAG
    // (the user's ruling: hover/single-click only highlight; only a double pans).
    else if (m.type === "showAskPath" && m.itemId) {
      const a = lastAskItems.find((x) => x.itemId === String(m.itemId));
      if (a && m.off) { focusTimeline(a.turnId, a.sid, a.created, undefined, undefined, false); focusOverlayItem = null; }
      else if (a) {
        focusTimeline(a.turnId, a.sid, a.created, { ask: a.itemId, events: a.path.events, msgs: a.path.msgs }, "prompt", false, m.jump === true);
        focusOverlayItem = String(m.itemId);   // this item's DAG overlay is now painted (covers both hover and the double-click pin)
        if (m.locate !== false && !m.jump) locateInChat(a.sid, a.created);
      }
    }
    // hover a line in the ask modal → transient timeline highlight (db_timeline
    // leads the read+render); id absent/null = clear. Separate channel from focus.
    else if (m.type === "hoverHighlight") hoverTimeline(
      Array.isArray(m.ids) && m.ids.length ? m.ids.map(String) : m.id ? String(m.id) : null);
    else if (m.type === "askClear" && m.itemId) {
      const id = String(m.itemId);
      // CLEAR-ON-GREEN implicit label (the user 2026-06-11: "I'm just clearing them
      // because they are done" — 57 manual mark-done clicks/day): clearing an
      // auto-filed card that the judge never stamped IS the user asserting it was
      // done, so file the done-corrections automatically. His one click now both
      // retires the card and labels the judge's miss. UndoClear leaves the labels
      // (a deliberate un-clear is about the card, not the verdicts).
      const ca: any = lastAskItems.find((x) => x.itemId === id);
      if (ca && ca.autoFiled && !ca.explicitDone) {
        for (const n of ca.tree || []) {
          if (n.status === "done") continue;
          const rows = n.rows || [];
          // note carries the card id so UndoClear can retract exactly these labels
          appendCorrection(String(n.id), rows.length ? String(rows[rows.length - 1].reply_id) : null,
            `cleared-as-done: the user cleared an auto-filed card (implicit done label) (card ${id})`);
        }
      }
      appendCleared(id);
      // if the cleared card is the one currently painted on the timeline (e.g. a
      // double-click PIN, whose white DAG overlay would otherwise survive the clear
      // until a hover replaces it), clear the overlay too — db_timeline re-syncs the
      // overlay from focus.json every poll, so a no-dag + locate:false focus drops it.
      if (id === focusOverlayItem) {
        const a = lastAskItems.find((x) => x.itemId === id);
        if (a) focusTimeline(a.turnId, a.sid, a.created, undefined, undefined, false);
        focusOverlayItem = null;
      }
      refreshFeed(true);
    }
    // UndoClear (header button): restore the most recently cleared card
    else if (m.type === "undoClear") {
      undoLastClear();
      refreshFeed(true);
    }
    // the user adjudicates a stale node done (modal "Mark done" on a drop point):
    // append a correction — the fold reads it as a DONE link on that node, and
    // the same row is the linker's training label. decisionRef = the newest
    // reply on the node (the filing the linker should have made terminal).
    // ⚠ Report box: category + free text + a snapshot of the card's computed
    // state, appended to requests/reports.jsonl as a labeled failure example
    else if (m.type === "askReport" && m.itemId) {
      const a: any = lastAskItems.find((x) => x.itemId === String(m.itemId));
      appendReport(String(m.itemId), String(m.category || "other"), String(m.text || ""),
        a ? { column: a.column, liveness: a.liveness, autoFiled: !!a.autoFiled, explicitDone: !!a.explicitDone,
              waiting: !!a.waiting, text: a.text, sid: a.sid, suspects: a.suspects || [] } : null);
      vscode.window.setStatusBarMessage("romp: exception report filed — thank you, it becomes a regression label", 5000);
    }
    else if (m.type === "askMarkDone" && m.nodeId) {
      appendCorrection(String(m.nodeId), m.decisionRef ? String(m.decisionRef) : null,
        typeof m.note === "string" && m.note.trim() ? m.note.trim() : "marked done by the user (feed panel)");
      refreshFeed(true);
    }
    // "didn't need me" on a standalone awaiting item: label the mis-tag for the
    // classifier AND clear the card (a standalone has no DAG node to mark done).
    else if (m.type === "itemNotNeeded" && m.itemId) {
      const id = String(m.itemId);
      appendRelevanceCorrection(id, "the user marked this as not needing input (false awaiting)");
      appendCleared(id);
      refreshFeed(true);
    }
    else if (m.type === "answerPicker" && m.name) void answerPicker(String(m.name));
    // Answer an open question from the panel: the user's text becomes that session's
    // next typed prompt (same delivery as the chat composer), which is also what
    // crosses the question off — the summarizer records it as a typed turn.
    // Prefixed with the question being answered (mirrors askFollowUp below) so
    // the session knows which of its questions this is — a bare "yes" or an
    // option label carries no context on its own.
    else if (m.type === "answerQuestion" && m.name && typeof m.text === "string" && m.text.trim()) {
      const q = typeof m.question === "string" ? m.question.trim() : "";
      const qShort = q.length > 200 ? q.slice(0, 200) + "…" : q;
      sendToSession(String(m.name), qShort ? `Answering your question "${qShort}": ${String(m.text).trim()}` : String(m.text));
      setTimeout(() => refreshFeed(true), 1500);
    }
    // Follow-up on a COMPLETED card: deliver to the session with the card's
    // title as the subject (the bookkeeper files the turn under that same
    // request — the title never changes), record it, card returns to ASKS.
    else if (m.type === "askFollowUp" && m.itemId && typeof m.text === "string" && m.text.trim()) {
      const a = lastAskItems.find((x) => x.itemId === String(m.itemId));
      if (a) {
        // m.title = a GROUP follow-up: prefix with the group's typed-turn phrase
        // (the whole prompt) rather than the single member ask it's filed under.
        const about = typeof m.title === "string" && m.title.trim() ? m.title.trim() : a.text;
        sendToSession(a.name, `Follow-up on "${about}": ${String(m.text).trim()}`);
        appendFollowup(a.itemId, a.sid, String(m.text).trim());
        // a follow-up on an AUTO-FILED card is the auto-filer's false-positive
        // label (the card was NOT done) — record it with a snapshot, automatically,
        // mirroring how Clear-on-green records the true-positive side.
        const af: any = a;
        if (af.autoFiled && !af.explicitDone) {
          appendReport(a.itemId, "premature-auto-file", `follow-up sent: ${String(m.text).trim().slice(0, 300)}`,
            { column: af.column, liveness: af.liveness, autoFiled: true, explicitDone: false,
              waiting: !!af.waiting, text: a.text, sid: a.sid });
        }
        setTimeout(() => refreshFeed(true), 1500);
      }
    }
    else if (m.type === "dismiss" && m.itemId) {
      const d = feedDismissed(); d.add(String(m.itemId)); setFeedDismissed(d); refreshFeed(true);
    } else if (m.type === "undismiss" && m.itemId) {
      const d = feedDismissed(); d.delete(String(m.itemId)); setFeedDismissed(d); refreshFeed(true);
    } else if (m.type === "feedRequest") {
      feedShowDismissed = !!m.showDismissed; refreshFeed(true);
    }
  });
  p.onDidDispose(() => { feedPanel = undefined; feedReady = false; });
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

function nonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let s = "";
  for (let i = 0; i < 24; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return s;
}

export function deactivate() {}
