// romp kernel — the standalone host for the romp web UI. Serves the SAME
// webview bundles the VS Code extension uses (chat + feed) over HTTP, bridges
// their postMessage protocol over WebSocket, reads the romp record files, and
// drives sessions through a SessionBackend (tmux today).
//
//   romp-serve [--port N] [--host 127.0.0.1]
//
// The browser pages load an acquireVsCodeApi() shim (see pageHtml) that backs
// postMessage with the WebSocket — the 3,400-line webview bundles run
// unchanged. Message types and semantics are identical to extension.ts; where
// the extension showed a native VS Code dialog, the kernel picks the safe
// default (close-tab never kills the session, multi-card dot clicks open the
// first card).
import * as fs from "fs";
import * as http from "http";
import * as os from "os";
import * as path from "path";
import { spawn } from "child_process";
import { WebSocketServer, WebSocket } from "ws";
import { TmuxBackend } from "./tmux-backend";
import { HeadlessBackend } from "./headless-backend";
import type { SessionBackend, SessionState } from "./backend";
import {
  Session, ChipState, chipState, statusPayload, sig, firstSeenOf,
  readParsedSession, liveTranscriptOf, customTitleOf, AskDriver,
  metaSigOf, filterInterrupted, RESTED,
} from "./chat";
import {
  ROMP_STATE, PROJECTS, rompIds, rompMeta, rompDir, rewriteName, scanTranscripts,
  resolveSessionRef, digestOf, ledgerSigOf, lastSummary, readSessionOrder,
  writeSessionOrder, writeChatActive, focusTimeline, hoverTimeline,
  appendLocateDiag, appendCleared, undoLastClear, appendFollowup, appendCorrection,
  appendRelevanceCorrection, appendReport, readReqRows, readFeedDetail, isEventId,
  turnEvent, relTime, ChipColor,
} from "./state";
import {
  computeFeedItems, computeAskItems, workingNames, ageRgbTuple, lastReqBySid,
  missedHandoffSuspects, FeedItem, AskItem,
} from "./feed";

const POLL_MS = 800;
const FEED_LIMIT = 200;
// One-time floors (see extension.ts): pre-tagging backlog / pre-registry turns.
const FEED_FLOOR = 1780964820;
const REQUESTS_FLOOR = 1781036800;

const DIST = path.join(__dirname);                  // dist/ (kernel.js lives beside render.js)
const MEDIA = path.join(__dirname, "..", "media");

// ---- kernel persistence (the workspaceState/globalState replacement) ----
const KERNEL_STATE = () => path.join(ROMP_STATE(), "web-kernel.json");
interface KernelState { openSessions: string[]; dismissed: string[]; activeTab?: string | null; }
function loadKernelState(): KernelState {
  try {
    const o = JSON.parse(fs.readFileSync(KERNEL_STATE(), "utf8"));
    return {
      openSessions: Array.isArray(o.openSessions) ? o.openSessions.map(String) : [],
      dismissed: Array.isArray(o.dismissed) ? o.dismissed.map(String) : [],
      activeTab: typeof o.activeTab === "string" ? o.activeTab : null,
    };
  } catch { return { openSessions: [], dismissed: [] }; }
}
let kstate = loadKernelState();
let kstateTimer: NodeJS.Timeout | undefined;
function saveKernelState() {
  if (kstateTimer) return;
  kstateTimer = setTimeout(() => {
    kstateTimer = undefined;
    try {
      fs.mkdirSync(ROMP_STATE(), { recursive: true });
      const tmp = KERNEL_STATE() + ".tmp";
      fs.writeFileSync(tmp, JSON.stringify(kstate));
      fs.renameSync(tmp, KERNEL_STATE());
    } catch { /* ignore */ }
  }, 250);
}

// ---- backend + globals ----
// --backend tmux (default) | headless, or ROMP_SERVE_BACKEND. tmux hosts
// sessions in tmux panes (full TUI mirroring); headless runs turns through
// `claude -p` — no tmux required, no live picker mirroring.
function pickBackend(): SessionBackend {
  const i = process.argv.indexOf("--backend");
  const which = (i >= 0 ? process.argv[i + 1] : process.env.ROMP_SERVE_BACKEND) || "tmux";
  if (which === "headless") return new HeadlessBackend();
  return new TmuxBackend();
}
const backend: SessionBackend = pickBackend();
const asker = new AskDriver(backend);
const sessions = new Map<string, Session>();
let lastStates: Map<string, SessionState> | null = null;
let lastWorkingSig = "";
let lastOrderSig = "";
let feedSig = "";
let feedShowDismissed = false;
let lastAskItems: AskItem[] = [];
let lastFeedItems: any[] = [];
let focusOverlayItem: string | null = null;
let activeTab: { tid: string; name: string } | null = null;

// ---- WS clients ----
interface Client extends WebSocket { rompApp?: "chat" | "feed"; rompReady?: boolean; rompActiveTab?: string | null; }
const clients = new Set<Client>();
function post(msg: any) {
  const s = JSON.stringify(msg);
  for (const c of clients) if (c.rompApp === "chat" && c.rompReady && c.readyState === WebSocket.OPEN) c.send(s);
}

// Shared tabs, PER-CLIENT focus (the user's choice 2026-06-11): the open-tab set
// is one kernel-global thing — open/close anywhere applies everywhere — but
// which tab is FOCUSED is each client's own. A focus triggered by a client's
// request goes back to THAT client only; unprompted focuses (deep links, with
// no requesting client) still broadcast. reqClient is set for the duration of
// one message dispatch (handlers are synchronous; async paths capture it).
let reqClient: Client | null = null;
function postFocus(msg: any) {
  if (reqClient && reqClient.readyState === WebSocket.OPEN) reqClient.send(JSON.stringify(msg));
  else post(msg);
}
function feedPost(msg: any) {
  const s = JSON.stringify(msg);
  for (const c of clients) if (c.rompApp === "feed" && c.rompReady && c.readyState === WebSocket.OPEN) c.send(s);
}
function postTo(c: Client, msg: any) {
  if (c.readyState === WebSocket.OPEN) c.send(JSON.stringify(msg));
}
const hasChatClients = () => Array.from(clients).some((c) => c.rompApp === "chat" && c.rompReady);
const hasFeedClients = () => Array.from(clients).some((c) => c.rompApp === "feed" && c.rompReady);

function warn(text: string) {
  console.warn("romp-serve:", text);
  // Both surfaces: the thin client turns this into a status-bar message; the
  // webview bundles ignore the unknown type.
  post({ type: "kernelToast", text });
  feedPost({ type: "kernelToast", text });
}

// ---- session tabs (ported from extension.ts, dialogs removed) ----

function persistOpen() {
  kstate.openSessions = Array.from(sessions.keys());
  saveKernelState();
}

function sessionStatus(s: Session, states: Map<string, SessionState> | null) {
  return statusPayload(s, chipState(s.name, states, s.lastWorking), states, s.lastSince);
}

function postSession(s: Session, target?: Client) {
  const p = readParsedSession(s);
  if (!p) return;
  s.lastWorking = p.status.working;
  const states = lastStates ?? backend.liveSessions();
  const state = chipState(s.name, states, s.lastWorking);
  s.lastSig = sig(s.file);
  s.lastSince = p.status.sinceEpoch;
  s.lastState = state;
  s.lastMetaSig = metaSigOf(s.name, states);
  const ledger = digestOf(s.id, states.get(s.name)?.summary);
  s.ledgerSig = ledgerSigOf(ledger);
  const msg = {
    type: "session",
    id: s.id, name: s.name, color: s.color,
    events: filterInterrupted(p.events, state),
    status: statusPayload(s, state, states, p.status.sinceEpoch),
    ledger,
    firstSeen: firstSeenOf(s),
  };
  if (target) postTo(target, msg); else post(msg);
}

function pushUpdate(s: Session) {
  if (!hasChatClients()) return;
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
  post({ type: "update", id: s.id, events: filterInterrupted(p.events, state), status: statusPayload(s, state, lastStates, s.lastSince) });
}

// Re-post a session's (filtered) events without a transcript change — used when
// a working→rest transition means the trailing turn may have just been
// interrupt-restored and should disappear, mirroring the TUI.
function repostEventsFor(s: Session, state: ChipState) {
  const p = readParsedSession(s);
  if (!p) return;
  post({ type: "update", id: s.id, events: filterInterrupted(p.events, state), status: statusPayload(s, state, lastStates, s.lastSince) });
}

function watch(s: Session) {
  try {
    s.watcher = fs.watch(s.file, () => {
      if (s.debounce) clearTimeout(s.debounce);
      s.debounce = setTimeout(() => pushUpdate(s), 50);
    });
  } catch { /* best-effort; poll covers it */ }
}

function addSession(file: string, anchor?: string, keepOpen?: boolean) {
  const id = path.basename(file, ".jsonl");
  if (sessions.has(id)) {
    postFocus({ type: "focus", id, anchor });
    return;
  }
  const meta = rompMeta(id);
  const sess: Session = {
    id, file,
    name: meta.name ?? id.slice(0, 8),
    color: meta.color,
    lastSig: "", lastSince: null, lastState: "", lastWorking: false,
    keepOpen: keepOpen || undefined,
    addedAt: Date.now(),
  };
  sessions.set(id, sess);
  postSession(sess);
  postFocus({ type: "focus", id, anchor });
  watch(sess);
  persistOpen();
}

// Follow a transcript fork (/clear, resume): swap the tab's file and reset the
// incremental parser, but KEEP the anchor identity — s.id stays the anchor sid
// (names/, digest/, ledger all key on it) and firstSeen stays cached from the
// anchor. Re-post the full session so the webview rebuilds from the new file.
function repointSession(s: Session, file: string) {
  try { s.watcher?.close(); } catch { /* ignore */ }
  s.watcher = undefined;
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
  persistOpen();
  post({ type: "closed", id });
}

function restoreSessions() {
  const ids = kstate.openSessions || [];
  if (!ids.length) return;
  const states = backend.liveSessions();
  const reliable = states.size > 0;
  const alive = new Set(states.keys());
  const transcripts = scanTranscripts();
  for (const id of ids) {
    if (sessions.has(id)) continue;
    const tr = transcripts.get(id);
    if (!tr) continue;
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (reliable && !alive.has(name)) continue;   // prune dead
    const sess: Session = {
      id, file: tr.file, name, color: meta.color,
      lastSig: "", lastSince: null, lastState: "", lastWorking: false,
    };
    sessions.set(id, sess);
    watch(sess);
  }
}

function applyRename(s: Session, name: string) {
  s.name = name;
  post({ type: "renamed", id: s.id, name });
  if (activeTab?.tid === s.id) { activeTab = { tid: s.id, name }; writeChatActive(activeTab); }
}

function renameSession(id: string, newName: string) {
  const s = sessions.get(id);
  const name = newName.trim();
  if (!s || !name || name === s.name) return;
  if (!/^[A-Za-z0-9._-]+$/.test(name)) { warn("session names are letters, digits, . _ - only."); return; }
  const states = backend.liveSessions();
  if (!states.has(s.name)) { warn(`"${s.name}" isn't running — only a live session can be renamed.`); return; }
  if (states.has(name)) { warn(`a session named "${name}" already exists.`); return; }
  if (!backend.rename(s.name, name)) { warn("rename failed"); return; }
  rewriteName(s.id, name);
  applyRename(s, name);
}

async function createNewSession(rawName: string) {
  const name = rawName.trim();
  if (!name || !/^[A-Za-z0-9._-]+$/.test(name)) { warn("session names use letters, digits, . _ - only."); return; }
  const states0 = backend.liveSessions();
  if (states0.has(name)) { warn(`a session named "${name}" already exists.`); openByName(name); return; }
  const rc = reqClient;   // survives the awaits below, so the new tab focuses the asker
  const cwd = process.env.ROMP_SERVE_CWD || os.homedir();
  const made = await backend.spawn(name, cwd);
  if (!made) { warn(`couldn't create session "${name}" — is the romp launcher on your PATH?`); return; }
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 800));
    const states = backend.liveSessions();
    if (states.has(name) && resolveSessionRef(name)) {
      reqClient = rc;
      try { openByName(name); } finally { reqClient = null; }
      return;
    }
  }
  warn(`"${name}" is starting — open it from the + picker once it appears.`);
}

function openSessionById(id: string) {
  // Fork/incarnation-aware: live under its customTitle (even when the clicked
  // fsid is an old fork) → focus the running session by name; otherwise offer
  // to revive the MOST RECENT incarnation (in-webview dialog).
  const t = resolveSession(id);
  if (!t) return;
  if (t.liveName) { openByName(t.liveName); return; }
  const name = customTitleOf(t.file) ?? rompMeta(t.id).name ?? t.id.slice(0, 8);
  postFocus({ type: "confirmRevive", id: t.id, name });
}

function openByName(name: string) {
  const r = resolveSessionRef(name);
  if (!r) { warn(`no session named "${name}".`); return; }
  if (sessions.has(r.id)) { postFocus({ type: "focus", id: r.id }); return; }
  const states = backend.liveSessions();
  if (states.size > 0 && states.has(name)) addSession(r.file);
  else postFocus({ type: "confirmRevive", id: r.id, name });
}

// External deep-link (vscode://…/open?session=&anchor= forwarded by the thin
// client, or a future /open route): focus the session's tab, opening it first
// if needed. Fork/incarnation-aware like openSessionById; a dead session gets
// the in-page revive dialog.
function deepLink(session: string, m: any) {
  const anchor = m.anchor ? String(m.anchor) : undefined;
  const anchorT = Number(m.anchorT) || undefined;
  const anchorKind = m.anchorKind ? String(m.anchorKind) : undefined;
  const compose = !!m.compose;
  const r = resolveSessionRef(session);
  if (!r) { warn(`no transcript found for "${session}".`); return; }
  if (sessions.has(r.id)) {
    postFocus({ type: "focus", id: r.id, anchor, anchorT, anchorKind });
    if (compose) postFocus({ type: "focusComposer" });
    return;
  }
  const t = resolveSession(session) ?? { id: r.id, file: r.file, liveName: null };
  if (t.liveName) {
    const lr = resolveSessionRef(t.liveName) ?? t;
    if (sessions.has(lr.id)) postFocus({ type: "focus", id: lr.id, anchor, anchorT, anchorKind });
    else addSession(lr.file, anchor);
    if (compose) postFocus({ type: "focusComposer" });
    return;
  }
  const name = customTitleOf(t.file) ?? rompMeta(t.id).name ?? t.id.slice(0, 8);
  postFocus({ type: "confirmRevive", id: t.id, name });
}

// The × on a live session's tab: confirm in-page before anything irreversible.
// A dead session's tab just closes (nothing to end). The tick's AUTO-close
// calls closeSession directly, so it never prompts.
function requestCloseTab(id: string) {
  const s = sessions.get(id);
  if (!s) return;
  const states = backend.liveSessions();
  const running = states.size > 0 && states.has(s.name);
  if (!running) { closeSession(id); return; }
  postFocus({ type: "confirmClose", id, name: s.name });
}

// Revive a dead session (the in-webview dialog's "Revive"): relaunch detached
// under its original name + dir, wait for it to register live, then open the
// now-current transcript. Ported from the extension's reopenSession.
function reviveSession(id: string) {
  const name = rompMeta(id).name ?? customTitleOf(scanTranscripts().get(id)?.file || "") ?? id.slice(0, 8);
  const rc = reqClient;
  if (!backend.resume(name, id, rompDir(id))) { warn(`failed to reopen "${name}".`); return; }
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
      reqClient = rc;
      try { addSession(best.file); } finally { reqClient = null; }
    }
  };
  const poll = () => {
    const states = backend.liveSessions();
    const live = states.size > 0 && states.has(name);
    if (live || tries++ >= 20) openLatest();
    else setTimeout(poll, 1000);
  };
  setTimeout(poll, 800);
}

// A file dropped on the composer from the OS carries NO filesystem path in a
// sandboxed webview — only its bytes. Save them under the romp state dir and
// hand the path back ("droppedPath") so the prompt references a real, readable
// file. Drops that DO expose a path never reach here (inserted in-webview).
function saveDroppedFile(name: string, b64: string) {
  try {
    const drops = path.join(ROMP_STATE(), "drops");
    fs.mkdirSync(drops, { recursive: true });
    const safe = name.replace(/[^\w.-]+/g, "_").slice(-80) || "drop";
    const file = path.join(drops, `${Date.now()}-${safe}`);
    fs.writeFileSync(file, Buffer.from(b64, "base64"));
    post({ type: "droppedPath", path: file });
  } catch (e) {
    warn(`couldn't save the dropped file — ${(e as Error).message ?? e}`);
  }
}

function openAllRunning() {
  const states = backend.liveSessions();
  const runningNames = new Set(states.keys());
  const transcripts = scanTranscripts();
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

function sessionRows() {
  const transcripts = scanTranscripts();
  const st0 = backend.liveSessions();
  const running = new Set<string>(st0.keys());
  const best = new Map<string, { id: string; name: string; color: ChipColor | null; running: boolean; mtime: number; file: string }>();
  for (const id of rompIds()) {
    const tr = transcripts.get(id);
    if (!tr) continue;
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (!/[A-Za-z0-9]/.test(name)) continue;
    const prev = best.get(name);
    if (!prev || tr.mtime > prev.mtime) best.set(name, { id, name, color: meta.color, running: running.has(name), mtime: tr.mtime, file: tr.file });
  }
  return Array.from(best.values()).sort((a, b) => Number(b.running) - Number(a.running) || b.mtime - a.mtime);
}

function sessionPayload() {
  return sessionRows().slice(0, 150).map((r) => ({
    id: r.id, name: r.name, color: r.color, running: r.running,
    time: r.running ? "running" : relTime(r.mtime),
    summary: lastSummary(r.id) || "",
  }));
}

function setActiveTab(id: string | null) {
  if (reqClient) reqClient.rompActiveTab = id;   // each client keeps its own focus
  // The kernel-global active tab (probe priority, the timeline's lane outline,
  // and the restore default for a fresh page) follows the most recent client
  // to change focus — last-writer-wins, same as two hosts sharing a file.
  if (id) {
    const name = sessions.get(id)?.name ?? rompMeta(id).name ?? id.slice(0, 8);
    activeTab = { tid: id, name };
  } else {
    activeTab = null;
  }
  kstate.activeTab = id || null;
  saveKernelState();
  writeChatActive(activeTab);
}

function sendMessageToTab(id: string, text: string) {
  const body = text.trim();
  if (!body) return;
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) { warn("no session name to deliver to."); return; }
  if (!backend.send(name, body)) warn(`couldn't deliver to "${name}" — is it a live romp session?`);
}

function interruptSession(id: string) {
  const name = sessions.get(id)?.name ?? rompMeta(id).name;
  if (!name) return;
  if (!backend.interrupt(name)) return;
  // Claude Code fires no hook on Esc — reset the published state ourselves
  // (re-asserted at two delays to ride out a late PostToolUse).
  const tInt = Math.floor(Date.now() / 1000);
  for (const ms of [600, 2000]) setTimeout(() => { backend.markIdle(name, tInt); refreshStatusFor(id); }, ms);
  // A pre-first-token interrupt restores the prompt into the TUI's composer and
  // hides the turn; filterInterrupted mirrors that, but its just-sent age guard
  // (2.5s) can outlast the refreshes above when the interrupt follows the send
  // almost immediately. One more re-post after the guard expires catches that.
  setTimeout(() => {
    const s = sessions.get(id);
    if (!s) return;
    const state = chipState(s.name, lastStates, s.lastWorking);
    if (RESTED.has(state)) repostEventsFor(s, state);
  }, 3200);
}

// Re-read live state and push a status update for one session if its chip
// changed — makes an interrupt feel immediate without waiting for the poll tick.
function refreshStatusFor(id: string) {
  const s = sessions.get(id);
  if (!s || !hasChatClients()) return;
  lastStates = backend.liveSessions();
  const state = chipState(s.name, lastStates, s.lastWorking);
  if (state === s.lastState) return;
  const wasBusy = s.lastState === "working" || s.lastState === "compacting";
  s.lastState = state;
  s.lastMetaSig = metaSigOf(s.name, lastStates);
  // an interrupt settling the session = the trailing turn may have been
  // restored to the composer — re-post events so its bubble disappears too
  if (wasBusy && RESTED.has(state)) { repostEventsFor(s, state); return; }
  post({ type: "status", id: s.id, status: statusPayload(s, state, lastStates, s.lastSince) });
}

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
    warn(`answer "${name}"'s pending prompt before changing the ${kind}.`);
    return;
  }
  backend.send(name, `/${kind === "model" ? "model" : "effort"} ${value}`);
}

function compactSession(id: string) {
  const s = sessions.get(id);
  const name = s?.name ?? rompMeta(id).name;
  if (!name) return;
  if (s && chipState(s.name, lastStates, s.lastWorking) === "awaiting") {
    warn(`answer "${name}"'s pending prompt before compacting.`);
    return;
  }
  backend.send(name, "/compact");
}

// ---- live asks ----

function postLiveAskFor(s: Session) {
  if (!backend.tui) return;
  const live = asker.liveAsk(s.name);
  if (!live) {
    if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
    // HOOKLESS prompt answered: a picker that fired no hook (e.g. the /model
    // switch confirmation) fires none on dismissal either, so the "permission"
    // we painted below would strand the red chip forever. After the composer
    // has been back for a few consecutive ticks (riding out the ~3s transient
    // lag of a decline/cancel, which real prompts' own hooks heal), reset.
    s.askComposerTicks = (s.askComposerTicks ?? 0) + 1;
    if (s.askComposerTicks >= 4) backend.tui.markState(s.name, "waiting", ["permission"]);
    return;
  }
  s.askComposerTicks = 0;
  if (live.sig !== s.askSig) { s.askSig = live.sig; post({ type: "askLive", id: s.id, ask: live.ask }); }
}

// HOOKLESS pickers. The published state only learns "permission" from the
// Notification hook, and Claude Code fires NO hook for TUI confirmations like
// the /model switch prompt — so such a session keeps its old chip and the chat
// view never even looked at its pane (the user's report, 2026-06-11). Probe live
// panes for a structured picker; on a hit, paint the pane awaiting — which
// heals EVERY consumer (chip, dashboard, timeline, feed) — and post the live
// ask now. Only a real parse counts; the TEXT fallback card stays exclusive to
// hook-confirmed awaiting states.
let probeTick = 0;
function probeHooklessAsk(s: Session): boolean {
  if (!backend.tui) return false;
  const parsed = asker.parse(s.name);
  if (!parsed) return false;
  s.askComposerTicks = 0;
  if (parsed.sig !== s.askSig) { s.askSig = parsed.sig; post({ type: "askLive", id: s.id, ask: parsed }); }
  backend.tui.markState(s.name, "permission", ["waiting", "working", "idle", ""]);
  return true;
}

// For every awaiting session, push its pending prompt to the webview; clear it
// the moment the session stops awaiting. Non-awaiting live sessions get probed
// for hookless pickers — the active tab every tick, the rest every 4th tick
// (and any tick while their ask card is up, so it clears promptly).
function refreshLiveAsks() {
  probeTick++;
  // a tab focused in ANY client gets the every-tick probe (per-client focus)
  const activeIds = new Set<string>();
  if (activeTab) activeIds.add(activeTab.tid);
  for (const c of clients) if (c.rompApp === "chat" && c.rompActiveTab) activeIds.add(c.rompActiveTab);
  for (const s of sessions.values()) {
    const st = chipState(s.name, lastStates, s.lastWorking);
    if (st === "awaiting") { postLiveAskFor(s); continue; }
    // Probe ONLY quiet sessions (2026-06-11 timeline_window incident): a WORKING
    // session cannot have a picker up — Claude is running — but its pane is full
    // of arbitrary output, and a parser false-positive here painted "permission"
    // over a live turn. Hookless pickers only ever appear on a ready/idle session.
    if ((st === "ready" || st === "idle") && (activeIds.has(s.id) || s.askSig || probeTick % 4 === 0)) {
      if (probeHooklessAsk(s)) continue;
    }
    if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
  }
}

function remirrorSoon(id: string, ms = 220) {
  const s = sessions.get(id);
  if (s) setTimeout(() => { try { postLiveAskFor(s); } catch { /* ignore */ } }, ms);
}

// ---- ledgers / tab order ----

function refreshLedgers() {
  for (const s of sessions.values()) {
    const ledger = digestOf(s.id, lastStates?.get(s.name)?.summary);
    const sg = ledgerSigOf(ledger);
    if (sg !== s.ledgerSig) { s.ledgerSig = sg; post({ type: "ledger", id: s.id, ledger }); }
  }
}

function refreshTabOrder() {
  const order = readSessionOrder();
  const sg = order.join(",");
  if (sg !== lastOrderSig) { lastOrderSig = sg; post({ type: "tabOrder", order }); }
}

// ---- the poll tick ----

function tick() {
  const chatActive = hasChatClients() && sessions.size > 0;
  if (!chatActive && !hasFeedClients()) return;
  lastStates = backend.liveSessions();
  if (hasFeedClients()) refreshFeed();
  if (!chatActive) return;
  for (const s of Array.from(sessions.values())) {
    const nm = rompMeta(s.id).name;
    if (nm && nm !== s.name && lastStates?.has(nm)) applyRename(s, nm);
    // /clear forks to a new transcript file (same customTitle) and the pinned
    // one stops growing — follow the fork. Live tabs only: read-only/deep-link
    // tabs (keepOpen) stay pinned to the file they were opened on.
    if (!s.keepOpen && lastStates && lastStates.size > 0 && lastStates.has(s.name)) {
      const live = liveTranscriptOf(s);
      if (live !== s.file) { repointSession(s, live); continue; }
    }
    const cur = sig(s.file);
    if (cur && cur !== s.lastSig) { pushUpdate(s); continue; }
    const state = chipState(s.name, lastStates, s.lastWorking);
    const settled = Date.now() - (s.addedAt ?? 0) > 6000;
    if (state === "closed" && !s.keepOpen && settled) {
      s.closedTicks = (s.closedTicks ?? 0) + 1;
      if (s.closedTicks >= 2) { closeSession(s.id); continue; }
    } else {
      s.closedTicks = 0;
    }
    // Re-post on a state change OR a model/effort/ctx/faded change. The meta
    // check matters for a reopened/revived session: its tab opens before the
    // TUI's statusline republishes the live vars, so the values arrive a few
    // seconds later with NO chip-state change to carry them.
    const mSig = metaSigOf(s.name, lastStates);
    if (state !== s.lastState || mSig !== s.lastMetaSig) {
      const wasBusy = s.lastState === "working" || s.lastState === "compacting";
      s.lastState = state;
      s.lastMetaSig = mSig;
      // settling out of work with no transcript change = a possible interrupt-
      // restore: re-post events so the trailing turn is (un)hidden to match
      if (wasBusy && RESTED.has(state)) repostEventsFor(s, state);
      else post({ type: "status", id: s.id, status: statusPayload(s, state, lastStates, s.lastSince) });
    }
  }
  refreshLiveAsks();
  refreshLedgers();
  refreshTabOrder();
  const wsig = workingNames(lastStates).join(",");
  if (wsig !== lastWorkingSig) { lastWorkingSig = wsig; post({ type: "working", names: workingNames(lastStates) }); }
}

// ---- the feed ----

function feedDismissed(): Set<string> { return new Set(kstate.dismissed); }
function setFeedDismissed(s: Set<string>) { kstate.dismissed = Array.from(s); saveKernelState(); }

function refreshFeed(force = false) {
  if (!hasFeedClients()) return;
  const dismissed = feedDismissed();
  const linkedReplies = new Set<string>(
    readReqRows("links.jsonl").filter((l) => l.kind === "link" && l.reply_id).map((l) => String(l.reply_id)));
  const clearedRows = readReqRows("cleared.jsonl");
  const clearedIds = new Set<string>(clearedRows.map((c) => String(c.id)));
  const all = computeFeedItems(lastStates).filter((i) => i.t >= FEED_FLOOR)
    .map((i) => ({
      ...i,
      inAsk: linkedReplies.has(i.itemId),
      standalone: linkedReplies.has(i.itemId) === false && i.origin === "user"
        && (i.relevance === "DONE"
          || (i.relevance === "DECISION" && (lastReqBySid.get(i.sid) || 0) <= i.t))
        && i.t >= REQUESTS_FLOOR,
    }));
  const filtered = all.filter((i) => !clearedIds.has(i.itemId))
    .filter((i) => (feedShowDismissed ? dismissed.has(i.itemId) : !dismissed.has(i.itemId)));
  const now = Math.floor(Date.now() / 1000);
  const userItems = filtered.filter((i) => i.origin === "user").slice(0, FEED_LIMIT);
  const agentItems = filtered.filter((i) => i.origin === "agent").slice(0, FEED_LIMIT);
  const items = [...userItems, ...agentItems].sort((a, b) => b.t - a.t)
    .map((i) => ({ ...i, trgb: ageRgbTuple(now - i.t) }));
  const didById = new Map<string, FeedItem>(all.map((i) => [i.itemId, i] as const));
  const asks = computeAskItems(lastStates, didById).map((a) => ({
    ...a,
    trgb: ageRgbTuple(now - a.t),
    tree: a.tree.map((n) => ({
      ...n,
      trgb: ageRgbTuple(now - n.last),
      rows: n.rows.map((r) => ({ ...r, trgb: ageRgbTuple(now - r.t) })),
    })),
  }));
  lastAskItems = asks;
  // NEEDS INPUT is a UNION: text-DECISION links + sessions LIVE-blocked on the
  // user (permission prompt / resume picker). Ephemeral session states, not
  // registry objects: no Clear button, the card's click opens the session.
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
      // The user's ruling (2026-06-11): a blocked session is NOT its own card —
      // the ask the session is blocked ON moves to BLOCKED itself. Resolve the
      // live turn to its card(s); the synthetic session card below is an ERROR
      // FLAG for an unclaimed live turn (capture/linking missed), kept so a
      // block is never invisible.
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
  const sg = `${feedShowDismissed ? "D" : "L"}:${dismissed.size}:${clearedRows.length}:`
    + items.map((i) => `${i.itemId}:${i.live ? 1 : 0}:${i.relevance}:${i.origin === "user" ? "u" : "a"}:${i.inAsk ? 1 : 0}:${Math.floor((now - i.t) / 60)}`).join("|")
    + "‖A:" + asks.map((a) => `${a.itemId}:${a.live ? 1 : 0}:${a.done}:${a.needsYou}:${a.linked.length}:${Math.floor((now - a.t) / 60)}:${a.text.length}:${a.column}:${a.reopened ? "R" : ""}:${a.liveness}:${a.blocked ? "B" : ""}:${a.autoFiled ? "AF" : ""}:${a.explicitDone ? "X" : ""}:${a.waiting ? "W" : ""}:${(a as any).suspects ? (a as any).suspects.length : 0}:${a.openPaths.length}:${a.tree.map((n) => n.status[0] + (n.whoWorking ? "W" : "")).join("")}:${a.openQuestions.map((q) => q.reply_id + q.qtype[0] + (q.brief ? "+b" : "")).join(",")}`).join("|")
    + "‖B:" + blocked.map((b) => `${b.name}:${b.state}:${Math.floor((now - b.since) / 60)}`).join("|")
    + "‖W:" + workingNames(lastStates).join(",");
  lastFeedItems = items;
  if (!force && sg === feedSig) return;
  feedSig = sg;
  feedPost({ type: "feed", items, asks, blocked, now, working: workingNames(lastStates), dismissedCount: dismissed.size, showDismissed: feedShowDismissed, canUndoClear: clearedRows.length > 0 });
}

// ---- feed detail (lazy, cached per deliverable) ----

const feedDetailPending = new Set<string>();
function feedDetailBin(): string {
  return process.env.ROMP_FEED_DETAIL_BIN || "romp-feed-detail";
}
function requestFeedDetail(id: string, generate: boolean) {
  const cached = readFeedDetail(id);
  if (cached) { feedPost({ type: "detail", itemId: id, detail: cached }); return; }
  if (!generate) { feedPost({ type: "detailFailed", itemId: id, reason: "none" }); return; }
  if (!isEventId(id)) { feedPost({ type: "detailFailed", itemId: id, reason: "legacy" }); return; }
  feedPost({ type: "detailPending", itemId: id });
  if (feedDetailPending.has(id)) return;
  feedDetailPending.add(id);
  try {
    const child = spawn(feedDetailBin(), [id], { detached: true, stdio: "ignore" });
    child.on("error", () => { /* producer not installed */ });
    child.unref();
  } catch { /* unavailable; poll still covers a file written elsewhere */ }
  pollFeedDetail(id, 0);
}
function pollFeedDetail(id: string, tries: number) {
  if (!hasFeedClients()) { feedDetailPending.delete(id); return; }
  const d = readFeedDetail(id);
  if (d) { feedDetailPending.delete(id); feedPost({ type: "detail", itemId: id, detail: d }); return; }
  if (tries >= 30) { feedDetailPending.delete(id); feedPost({ type: "detailFailed", itemId: id, reason: "timeout" }); return; }
  setTimeout(() => pollFeedDetail(id, tries + 1), 500);
}

// ---- rail-dot ↔ timeline/feed links ----

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

// Fan the modal-row hover out to the CHAT panel too (the user 2026-06-11):
// white-ring the rail dots of every chat turn inside the hovered event's span,
// and any postal card carrying a hovered message id. An event id self-describes
// its session and start (`<sid>:<turn-start>:<hash>`); the matching feed row's
// t (the period end) bounds the span. Ids without the event shape are postal
// message ids. null/empty → clear.
function chatGlow(ids: string[] | null) {
  if (!hasChatClients()) return;
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

// hoverTimeline + the chat glow fan, debounced together (rides the same ~40ms
// cadence the timeline-hover file write uses).
let glowTimer: NodeJS.Timeout | undefined;
let glowPending: string[] | null = null;
function hoverFan(ids: string[] | string | null) {
  hoverTimeline(ids);
  glowPending = ids == null ? null : Array.isArray(ids) ? ids : [ids];
  if (glowTimer) return;
  glowTimer = setTimeout(() => { glowTimer = undefined; chatGlow(glowPending); }, 40);
}

function onDotHover(sid: string | null, uuid: string | null, t: number) {
  const ev = sid ? turnEvent(sid, uuid, t) : null;
  if (!ev) { hoverTimeline(null); feedPost({ type: "hoverCards", keys: [], eid: null }); return; }
  hoverTimeline(String(ev.id));
  // eid → the feed also white-rings the matching ROWS inside an open modal
  feedPost({ type: "hoverCards", keys: cardsForEvent(String(ev.id)).flatMap((c) => c.dom), eid: String(ev.id) });
}

function onDotOpen(sid: string, uuid: string | null, t: number) {
  const ev = turnEvent(sid, uuid, t);
  const cards = ev ? cardsForEvent(String(ev.id)) : [];
  if (!cards.length) { warn("this turn has no open feed card"); return; }
  // multi-card: open the first (no native picker here); hl white-rings the
  // clicked turn's row(s) inside the opened modal
  feedPost({ type: "openCard", key: cards[0].open, hl: ev ? String(ev.id) : null });
}

// Resolve a clicked / deep-linked transcript fsid to the SESSION it belongs to,
// accounting for a session that has lived across several fsids (/clear forks,
// kill+relaunch, revive — each a fresh fsid, but the transcript's customTitle
// stays the session's name). Returns the session's CURRENT incarnation — the
// newest same-customTitle transcript — plus the live name if it's running now.
function resolveSession(fsid: string): { id: string; file: string; liveName: string | null } | null {
  const tr = scanTranscripts().get(fsid);
  if (!tr) return null;
  const title = customTitleOf(tr.file);
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
        if (customTitleOf(fp) !== title) continue;
        bestM = st.mtimeMs; file = fp; id = f.replace(/\.jsonl$/, "");
      }
    } catch { /* unreadable dir → keep the clicked transcript */ }
  }
  const states = backend.liveSessions();
  let liveName: string | null = null;
  if (states.size > 0) {
    if (title && states.has(title)) liveName = title;   // customTitle is authoritative over a stale names entry
    else { const nm = rompMeta(id).name; if (nm && states.has(nm)) liveName = nm; }
  }
  return { id, file, liveName };
}

// Jump the CHAT panel to the user's instruction behind a feed card, from
// first-party data only (the card's session + mint epoch). Fork/incarnation-
// aware: a card stamped with an old fsid still belongs to a live session under
// its customTitle. A passive locate never offers revive — dead just highlights.
function locateInChat(sid: string, t: number) {
  if (!sid || !t) return;
  const direct = resolveSessionRef(sid);
  if (direct && sessions.has(direct.id)) {
    postFocus({ type: "focus", id: direct.id, anchorT: t, anchorKind: "user" });
    return;
  }
  const target = resolveSession(sid);
  if (!target || !target.liveName) return;   // dead + unopened: highlight only
  const lr = resolveSessionRef(target.liveName) ?? target;
  if (sessions.has(lr.id)) {
    postFocus({ type: "focus", id: lr.id, anchorT: t, anchorKind: "user" });
    return;
  }
  addSession(lr.file);
  postFocus({ type: "focus", id: lr.id, anchorT: t, anchorKind: "user" });
}

// ---- open-in-editor (the one genuinely editor-bound feature) ----
// Best effort: ROMP_SERVE_OPEN_CMD (e.g. "cursor -g {file}:{line}"), else try
// `cursor -g`, then `code -g`. Silently a no-op when neither exists.
function openFileInEditor(file: string, line?: number) {
  const target = typeof line === "number" && line > 0 ? `${file}:${line}` : file;
  const custom = process.env.ROMP_SERVE_OPEN_CMD;
  const attempts = custom
    ? [custom.replace("{file}:{line}", target).replace("{file}", file).split(/\s+/)]
    : [["cursor", "-g", target], ["code", "-g", target]];
  const tryNext = (i: number) => {
    if (i >= attempts.length) return;
    const [cmd, ...args] = attempts[i];
    const child = spawn(cmd, args, { detached: true, stdio: "ignore" });
    child.on("error", () => tryNext(i + 1));
    child.unref();
  };
  tryNext(0);
}

function openLink(href: string) {
  // The browser page can open http(s) links itself; this handler only fires for
  // schemes the webview bundle forwards (it can't know it's in a real browser).
  try {
    const child = spawn(process.platform === "darwin" ? "open" : "xdg-open", [href], { detached: true, stdio: "ignore" });
    child.on("error", () => { /* ignore */ });
    child.unref();
  } catch { /* ignore */ }
}

// ---- pasted-image hydration ----
const IMG_MAX_BYTES = 8_000_000;
const IMG_MIME: { [ext: string]: string } = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".svg": "image/svg+xml",
};
const imgCache = new Map<string, string | null>();
function imgDataUrl(p0: string): string | null {
  try {
    let p = p0;
    if (p.startsWith("~/")) p = path.join(os.homedir(), p.slice(2));
    if (!path.isAbsolute(p)) return null;
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

// ---- WS message handling (the postMessage protocol, verbatim) ----

function onChatReady(c: Client) {
  c.rompReady = true;
  if (sessions.size === 0) {
    restoreSessions();
    if (sessions.size === 0) {
      const recent = sessionRows()[0];
      if (recent) { addSession(recent.file); return; }
    }
  }
  // Replay the shared tab set to THIS client only — peers already have it.
  for (const s of sessions.values()) postSession(s, c);
  if (kstate.activeTab && sessions.has(kstate.activeTab)) postTo(c, { type: "focus", id: kstate.activeTab });
  c.rompActiveTab = kstate.activeTab && sessions.has(kstate.activeTab) ? kstate.activeTab : null;
  const ord = readSessionOrder();
  lastOrderSig = ord.join(",");
  postTo(c, { type: "tabOrder", order: ord });
}

function handleChatMessage(c: Client, m: any) {
  if (!m) return;
  if (m.type === "ready") onChatReady(c);
  else if (m.type === "addSession") post({ type: "openPicker", pick: false });
  else if (m.type === "createSession") void createNewSession(String(m.name ?? ""));
  else if (m.type === "closeSession" && m.id) requestCloseTab(String(m.id));   // live → in-page End/Close confirm
  else if (m.type === "closeTab" && m.id) closeSession(String(m.id));
  else if (m.type === "endSession" && m.id) {
    const s = sessions.get(String(m.id));
    if (s) { backend.kill(s.name); closeSession(String(m.id)); }
  }
  else if (m.type === "reviveSession" && m.id) reviveSession(String(m.id));
  else if (m.type === "viewReadOnly" && m.id) {
    const tr = scanTranscripts().get(String(m.id));
    if (tr) addSession(tr.file, undefined, true);   // keepOpen: exempt from auto-close
  }
  else if (m.type === "renameSession" && m.id && typeof m.name === "string") renameSession(String(m.id), String(m.name));
  else if (m.type === "requestSessions") postTo(c, { type: "sessionList", items: sessionPayload() });
  else if (m.type === "openSession" && m.id) openSessionById(String(m.id));
  else if (m.type === "openByName" && m.name) openByName(String(m.name));
  else if (m.type === "openAll") openAllRunning();
  else if (m.type === "deepLink" && m.session) deepLink(String(m.session), m);
  else if (m.type === "openTranscript" && typeof m.file === "string") {
    // a host asking to view a transcript file directly (rompChat.openCurrent)
    const file = path.resolve(String(m.file));
    if (file.startsWith(PROJECTS() + path.sep) && file.endsWith(".jsonl")) addSession(file);
  }
  else if (m.type === "openFile" && m.path) openFileInEditor(String(m.path), m.line);
  else if (m.type === "openLink" && typeof m.href === "string") openLink(String(m.href));
  else if (m.type === "dotHover") onDotHover(m.sid ? String(m.sid) : null, m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
  else if (m.type === "dotOpen" && m.sid) onDotOpen(String(m.sid), m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
  else if (m.type === "dropFile" && typeof m.name === "string" && typeof m.b64 === "string") saveDroppedFile(String(m.name), String(m.b64));
  // pickFile/readClipboard are CLIENT capabilities — the browser shim intercepts
  // them (file input / navigator.clipboard) before they ever reach this socket.
  // Reaching here means an old shim: answer with the empty fallback.
  else if (m.type === "readClipboard") postTo(c, { type: "clipboardText", text: "" });
  else if (m.type === "pickFile") { /* handled client-side by the shim */ }
  else if (m.type === "activeTab") setActiveTab(m.id ?? null);
  else if (m.type === "sendMessage" && m.id && m.text) sendMessageToTab(String(m.id), String(m.text));
  else if (m.type === "interrupt" && m.id) interruptSession(String(m.id));
  else if (m.type === "answerAsk" && m.id && typeof m.target === "number") { withName(m.id, (n) => asker.answer(n, m.target)); remirrorSoon(String(m.id), 450); }
  else if (m.type === "toggleAsk" && m.id && typeof m.target === "number") { withName(m.id, (n) => asker.toggle(n, m.target)); remirrorSoon(String(m.id), 450); }
  else if (m.type === "submitAsk" && m.id) { withName(m.id, (n) => asker.submit(n)); remirrorSoon(String(m.id), 700); }
  else if (m.type === "addCustomAsk" && m.id && typeof m.text === "string") { withName(m.id, (n) => asker.addCustom(n, String(m.text))); remirrorSoon(String(m.id), 650); }
  else if (m.type === "cancelAsk" && m.id) { withName(m.id, (n) => asker.cancel(n)); remirrorSoon(String(m.id), 260); }
  else if (m.type === "askText" && m.id && typeof m.text === "string") { withName(m.id, (n) => asker.sendText(n, String(m.text))); remirrorSoon(String(m.id), 260); }
  else if (m.type === "setModel" && m.id && typeof m.value === "string") setSessionMeta(String(m.id), "model", String(m.value));
  else if (m.type === "setEffort" && m.id && typeof m.value === "string") setSessionMeta(String(m.id), "effort", String(m.value));
  else if (m.type === "compactSession" && m.id) compactSession(String(m.id));
  else if (m.type === "reorderTabs" && Array.isArray(m.order)) { writeSessionOrder(m.order.map(String)); lastOrderSig = m.order.join(","); }
  else if (m.type === "ledgerHover") hoverFan(m.id ? [String(m.id)] : null);
  else if (m.type === "ledgerLocate" && m.id) focusTimeline(String(m.id), String(m.sid ?? ""), Number(m.t) || 0, undefined, "work");
  else if (m.type === "imgRequest" && typeof m.path === "string") postTo(c, { type: "imgData", path: m.path, url: imgDataUrl(String(m.path)) });
  else if (m.type === "locateDiag") appendLocateDiag(m);
}

function withName(id: any, fn: (name: string) => void) {
  const name = sessions.get(String(id))?.name ?? rompMeta(String(id)).name;
  if (name) fn(name);
}

// ---- answering the resume picker (in-page dialog instead of a QuickPick) ----
// The picker lives in the session's TUI, invisible here. Read the live screen,
// hand the SAME options to the asking feed client; its choice comes back as
// answerPickerChoice and we forward keystrokes. The user decides; we only
// transport (the never-auto-answer rule holds).
const PICKER_OPTS = ["Resume from summary (recommended)", "Resume full session as-is"];
function answerPicker(c: Client, name: string) {
  if (!backend.tui) { warn(`"${name}" is blocked on the resume picker — this backend can't drive it.`); return; }
  const lines = backend.tui.capturePane(name).split("\n");
  const opts = PICKER_OPTS.filter((o) => lines.some((l) => l.includes(o)));
  if (!opts.length) {
    warn(`${name}: the picker is no longer on screen.`);
    refreshFeed(true);
    return;
  }
  postTo(c, { type: "pickerOptions", name, options: opts });
}
function answerPickerChoice(name: string, want: number) {
  if (!backend.tui) return;
  const lines = backend.tui.capturePane(name).split("\n");
  const opts = PICKER_OPTS.filter((o) => lines.some((l) => l.includes(o)));
  if (want < 0 || want >= opts.length) return;
  // Current highlight = the option line carrying the selector glyph (Ink uses ❯);
  // when not found, the picker default is the first option.
  let cur = 0;
  opts.forEach((o, i) => {
    const l = lines.find((x) => x.includes(o));
    if (l && l.includes("❯")) cur = i;
  });
  const keys: string[] = [];
  for (let i = 0; i < Math.abs(want - cur); i++) keys.push(want > cur ? "Down" : "Up");
  keys.push("Enter");
  backend.tui.sendKeys(name, keys);
  setTimeout(() => refreshFeed(true), 1200);   // state hook flips picker→working shortly after
}

function handleFeedMessage(c: Client, m: any) {
  if (!m) return;
  if (m.type === "ready") { c.rompReady = true; refreshFeed(true); }
  else if (m.type === "openSession" && m.id) openSessionById(String(m.id));
  else if (m.type === "expand" && m.itemId) requestFeedDetail(String(m.itemId), !!m.generate);
  else if (m.type === "showOnTimeline" && m.itemId) {
    const prompt = m.anchor === "prompt";
    focusTimeline(String(m.itemId), String(m.sid ?? ""), Number(m.t) || 0, undefined, prompt ? "prompt" : "work", prompt ? false : undefined);
    if (prompt) locateInChat(String(m.sid ?? ""), Number(m.t) || 0);
  }
  else if (m.type === "showAskPath" && m.itemId) {
    const a = lastAskItems.find((x) => x.itemId === String(m.itemId));
    if (a && m.off) { focusTimeline(a.turnId, a.sid, a.created, undefined, undefined, false); focusOverlayItem = null; }
    else if (a) {
      focusTimeline(a.turnId, a.sid, a.created, { ask: a.itemId, events: a.path.events, msgs: a.path.msgs }, "prompt", false, m.jump === true);
      focusOverlayItem = String(m.itemId);
      if (m.locate !== false && !m.jump) locateInChat(a.sid, a.created);
    }
  }
  else if (m.type === "hoverHighlight") hoverFan(
    Array.isArray(m.ids) && m.ids.length ? m.ids.map(String) : m.id ? String(m.id) : null);
  else if (m.type === "askClear" && m.itemId) {
    const id = String(m.itemId);
    // CLEAR-ON-GREEN implicit label (the user 2026-06-11): clearing an
    // auto-filed card that the judge never stamped IS the user asserting it was
    // done, so file the done-corrections automatically — one click both retires
    // the card and labels the judge's miss. UndoClear leaves the labels.
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
  else if (m.type === "askMarkDone" && m.nodeId) {
    appendCorrection(String(m.nodeId), m.decisionRef ? String(m.decisionRef) : null,
      typeof m.note === "string" && m.note.trim() ? m.note.trim() : "marked done by the user (web kernel)");
    refreshFeed(true);
  }
  else if (m.type === "itemNotNeeded" && m.itemId) {
    const id = String(m.itemId);
    appendRelevanceCorrection(id, "the user marked this as not needing input (false awaiting)");
    appendCleared(id);
    refreshFeed(true);
  }
  // ⚠ Report box: category + free text + a snapshot of the card's computed
  // state, appended to requests/reports.jsonl as a labeled failure example
  else if (m.type === "askReport" && m.itemId) {
    const a: any = lastAskItems.find((x) => x.itemId === String(m.itemId));
    appendReport(String(m.itemId), String(m.category || "other"), String(m.text || ""),
      a ? { column: a.column, liveness: a.liveness, autoFiled: !!a.autoFiled, explicitDone: !!a.explicitDone,
            waiting: !!a.waiting, text: a.text, sid: a.sid, suspects: a.suspects || [] } : null);
    warn("exception report filed — it becomes a regression label");
  }
  else if (m.type === "answerPicker" && m.name) answerPicker(c, String(m.name));
  else if (m.type === "answerPickerChoice" && m.name && typeof m.n === "number") answerPickerChoice(String(m.name), m.n);
  else if (m.type === "answerQuestion" && m.name && typeof m.text === "string" && m.text.trim()) {
    const q = typeof m.question === "string" ? m.question.trim() : "";
    const qShort = q.length > 200 ? q.slice(0, 200) + "…" : q;
    backend.send(String(m.name), qShort ? `Answering your question "${qShort}": ${String(m.text).trim()}` : String(m.text));
    setTimeout(() => refreshFeed(true), 1500);
  }
  else if (m.type === "askFollowUp" && m.itemId && typeof m.text === "string" && m.text.trim()) {
    const a = lastAskItems.find((x) => x.itemId === String(m.itemId));
    if (a) {
      const about = typeof m.title === "string" && m.title.trim() ? m.title.trim() : a.text;
      backend.send(a.name, `Follow-up on "${about}": ${String(m.text).trim()}`);
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
}

// ---- HTTP ----

// The acquireVsCodeApi shim: postMessage ↔ WebSocket, state ↔ localStorage.
// Defined before the bundle script so the bundle picks it up at load. On a
// dropped connection the page reloads once the server is reachable again —
// simplest way to resync the webview's full state.
function shimJs(app: "chat" | "feed"): string {
  return `
(function () {
  var KEY = "romp-webview-state-${app}";
  var queue = [];
  var ws = null;
  function connect() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws?app=${app}");
    ws.onopen = function () { for (var i = 0; i < queue.length; i++) ws.send(queue[i]); queue = []; };
    ws.onmessage = function (ev) {
      var msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
      window.dispatchEvent(new MessageEvent("message", { data: msg }));
    };
    ws.onclose = function () { setTimeout(function () { location.reload(); }, 1500); };
  }
  function send(m) {
    var s = JSON.stringify(m);
    if (ws && ws.readyState === 1) ws.send(s); else queue.push(s);
  }
  function deliver(data) {
    window.dispatchEvent(new MessageEvent("message", { data: data }));
  }
  window.acquireVsCodeApi = function () {
    return {
      postMessage: function (m) {
        // CLIENT capabilities — things a real browser does better locally than
        // the kernel can remotely. Same protocol, intercepted before the wire.
        if (m && m.type === "readClipboard") {
          var done = function (text) { deliver({ type: "clipboardText", text: text || "" }); };
          if (navigator.clipboard && navigator.clipboard.readText) navigator.clipboard.readText().then(done, function () { done(""); });
          else done("");
          return;
        }
        if (m && m.type === "pickFile") {
          // The 📎 button: a real file input; picked bytes ride the same
          // dropFile→droppedPath pipeline as an in-page drop.
          var inp = document.createElement("input");
          inp.type = "file"; inp.multiple = true; inp.style.display = "none";
          inp.onchange = function () {
            var files = Array.prototype.slice.call(inp.files || []);
            files.forEach(function (f) {
              var r = new FileReader();
              r.onload = function () {
                var b64 = String(r.result || "").split(",")[1] || "";
                send({ type: "dropFile", name: f.name, b64: b64 });
              };
              r.readAsDataURL(f);
            });
            inp.remove();
          };
          document.body.appendChild(inp);
          inp.click();
          return;
        }
        send(m);
      },
      getState: function () {
        try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
      },
      setState: function (s) {
        try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* ignore */ }
      },
    };
  };
  connect();
})();
`;
}

// VS Code injects ~theme CSS variables into webviews; a plain browser has
// none, so the bundles' styles would all fall through to unset. This block is
// the Dark+ defaults for every --vscode-* var the stylesheets reference, plus
// the body baseline VS Code applies to webviews.
const THEME_CSS = `
:root {
  --vscode-font-family: -apple-system, BlinkMacSystemFont, "Segoe WPC", "Segoe UI", sans-serif;
  --vscode-editor-font-family: Menlo, Monaco, "Courier New", monospace;
  --vscode-chat-font-family: var(--vscode-font-family);
  --vscode-chat-font-size: 13px;
  --vscode-foreground: #cccccc;
  --vscode-descriptionForeground: rgba(204, 204, 204, 0.7);
  --vscode-errorForeground: #f48771;
  --vscode-editor-background: #1e1e1e;
  --vscode-editorWidget-background: #252526;
  --vscode-editorHoverWidget-border: #454545;
  --vscode-sideBar-background: #252526;
  --vscode-widget-border: #303031;
  --vscode-focusBorder: #007fd4;
  --vscode-input-background: #3c3c3c;
  --vscode-input-foreground: #cccccc;
  --vscode-input-border: #3c3c3c;
  --vscode-menu-background: #252526;
  --vscode-menu-foreground: #cccccc;
  --vscode-menu-selectionBackground: #094771;
  --vscode-menu-selectionForeground: #ffffff;
  --vscode-scrollbarSlider-background: rgba(121, 121, 121, 0.4);
  --vscode-textLink-foreground: #3794ff;
}
html, body { background: var(--vscode-editor-background); }
body {
  font-family: var(--vscode-font-family);
  font-size: 13px;
  color: var(--vscode-foreground);
  margin: 0;
  padding: 0;
}
`;

function chatHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="/dist/styles.css" rel="stylesheet" />
  <title>romp</title>
  <style>${THEME_CSS}</style>
</head>
<body>
  <div id="winframe"></div>
  <div id="tabbar"><span id="tabs"></span></div>
  <div id="ledger" style="display:none"></div>
  <div id="content"></div>
  <div id="live-ask" style="display:none"></div>
  <div id="footer">
    <div id="statusline" class="statusline"></div>
    <div id="composer"><textarea id="composer-input" rows="1" placeholder="Message this session…  (⏎ send · ⇧⏎ newline)"></textarea><button id="composer-attach" title="Attach a file — inserts its path" aria-label="Attach file">📎</button></div>
  </div>
  <script>${shimJs("chat")}</script>
  <script src="/dist/render.js"></script>
</body>
</html>`;
}

function feedHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="/dist/feed.css" rel="stylesheet" />
  <title>romp feed</title>
  <style>${THEME_CSS}</style>
</head>
<body>
  <div id="feed-head"></div>
  <div id="feed-list"></div>
  <script>${shimJs("feed")}</script>
  <script src="/dist/feed.js"></script>
</body>
</html>`;
}

// ---- auth (for serving beyond localhost) ----
// ROMP_SERVE_TOKEN (or --token) gates every route: pages accept ?token=… once
// and set a cookie; static/WS requests then ride the cookie. No token
// configured = open (fine on 127.0.0.1; tunnel or set a token for anything
// wider).
function serveToken(): string {
  const i = process.argv.indexOf("--token");
  return (i >= 0 ? process.argv[i + 1] : process.env.ROMP_SERVE_TOKEN) || "";
}
function authorized(req: http.IncomingMessage, url: URL): boolean {
  const token = serveToken();
  if (!token) return true;
  if (url.searchParams.get("token") === token) return true;
  const auth = req.headers.authorization || "";
  if (auth === `Bearer ${token}`) return true;
  const cookies = String(req.headers.cookie || "");
  return cookies.split(";").some((c) => c.trim() === `romp_token=${token}`);
}
function deny(res: http.ServerResponse) {
  res.writeHead(401, { "Content-Type": "text/plain" });
  res.end("unauthorized — open /?token=<ROMP_SERVE_TOKEN>");
}

// The package version (dist/kernel.js sits beside ../package.json) — surfaced
// on /healthz so an attaching host can detect a stale kernel and restart it.
let _kver: string | null = null;
function kernelVersion(): string {
  if (_kver !== null) return _kver;
  try { _kver = String(JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8")).version || ""); }
  catch { _kver = ""; }
  return _kver;
}

const STATIC_MIME: { [ext: string]: string } = {
  ".js": "text/javascript", ".css": "text/css", ".map": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2",
  ".html": "text/html",
};

function serveStatic(res: http.ServerResponse, root: string, rel: string) {
  const fp = path.join(root, path.normalize(rel).replace(/^(\.\.[/\\])+/, ""));
  if (!fp.startsWith(root)) { res.writeHead(403); res.end(); return; }
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404); res.end("not found"); return; }
    res.writeHead(200, { "Content-Type": STATIC_MIME[path.extname(fp)] || "application/octet-stream" });
    res.end(data);
  });
}

export function main() {
  const args = process.argv.slice(2);
  const argOf = (flag: string): string | undefined => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const port = Number(argOf("--port") || process.env.ROMP_SERVE_PORT || 7433);
  const host = argOf("--host") || process.env.ROMP_SERVE_HOST || "127.0.0.1";

  const server = http.createServer((req, res) => {
    const url = new URL(req.url || "/", "http://x");
    if (!authorized(req, url)) { deny(res); return; }
    // A page request carrying a valid ?token sets the cookie the static/WS
    // requests will ride (the shim's WebSocket can't add headers).
    const headers: http.OutgoingHttpHeaders = { "Content-Type": "text/html" };
    if (serveToken() && url.searchParams.get("token") === serveToken())
      headers["Set-Cookie"] = `romp_token=${serveToken()}; HttpOnly; SameSite=Strict; Path=/`;
    if (url.pathname === "/" || url.pathname === "/index.html") {
      res.writeHead(200, headers); res.end(chatHtml());
    } else if (url.pathname === "/feed") {
      res.writeHead(200, headers); res.end(feedHtml());
    } else if (url.pathname.startsWith("/dist/")) {
      serveStatic(res, DIST, url.pathname.slice("/dist/".length));
    } else if (url.pathname.startsWith("/media/")) {
      serveStatic(res, MEDIA, url.pathname.slice("/media/".length));
    } else if (url.pathname === "/healthz") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, sessions: sessions.size, clients: clients.size, version: kernelVersion() }));
    } else if (url.pathname === "/shutdown" && req.method === "POST") {
      // The thin client's stale-kernel restart (version mismatch after a VSIX
      // install): acknowledge, then exit — the requester respawns the new build.
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      console.log("romp-serve: shutdown requested (stale-kernel restart)");
      setTimeout(() => process.exit(0), 150);
    } else {
      res.writeHead(404); res.end("not found");
    }
  });

  const wss = new WebSocketServer({ server, path: "/ws" });
  // ws re-emits the http server's errors here; unhandled, they'd throw and
  // mask the EADDRINUSE handling below.
  wss.on("error", () => { /* handled on the http server */ });
  wss.on("connection", (socket: Client, req) => {
    const url = new URL(req.url || "/", "http://x");
    if (!authorized(req, url)) { socket.close(4401, "unauthorized"); return; }
    const app = url.searchParams.get("app") === "feed" ? "feed" : "chat";
    socket.rompApp = app;
    socket.rompReady = false;
    clients.add(socket);
    socket.on("message", (data) => {
      let m: any;
      try { m = JSON.parse(String(data)); } catch { return; }
      reqClient = socket;   // focus replies target the asking client (handlers are sync)
      try {
        if (app === "chat") handleChatMessage(socket, m);
        else handleFeedMessage(socket, m);
      } catch (e) {
        console.error("romp-serve: handler error for", m?.type, e);
      } finally {
        reqClient = null;
      }
    });
    socket.on("close", () => clients.delete(socket));
    socket.on("error", () => clients.delete(socket));
  });

  setInterval(tick, POLL_MS);
  // Single-instance by port: a second kernel on the same port is the
  // spawn-or-attach race (two hosts starting at once) — if the occupant is a
  // romp kernel, defer to it quietly so the spawner just attaches.
  server.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code !== "EADDRINUSE") { console.error("romp-serve:", err.message); process.exit(1); }
    http.get({ host, port, path: "/healthz", timeout: 2000 }, (res) => {
      let body = "";
      res.on("data", (d) => (body += d));
      res.on("end", () => {
        let ok = false;
        try { ok = !!JSON.parse(body).ok; } catch { /* not ours */ }
        if (ok) { console.log(`romp-serve: already running on ${host}:${port} — attaching to that one.`); process.exit(0); }
        console.error(`romp-serve: port ${port} is taken by something that isn't a romp kernel.`); process.exit(1);
      });
    }).on("error", () => { console.error(`romp-serve: port ${port} is taken and not answering /healthz.`); process.exit(1); });
  });
  server.listen(port, host, () => {
    console.log(`romp-serve: chat  http://${host}:${port}/`);
    console.log(`romp-serve: feed  http://${host}:${port}/feed`);
  });
}

main();
