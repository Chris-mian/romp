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
  readParsedSession, liveTranscriptOf, AskDriver,
} from "./chat";
import {
  ROMP_STATE, rompIds, rompMeta, rompDir, rewriteName, scanTranscripts,
  resolveSessionRef, digestOf, ledgerSigOf, lastSummary, readSessionOrder,
  writeSessionOrder, writeChatActive, focusTimeline, hoverTimeline,
  appendLocateDiag, appendCleared, undoLastClear, appendFollowup, appendCorrection,
  appendRelevanceCorrection, readReqRows, readFeedDetail, isEventId, turnEvent,
  relTime, ChipColor,
} from "./state";
import {
  computeFeedItems, computeAskItems, workingNames, ageRgbTuple, lastReqBySid,
  FeedItem, AskItem,
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
interface Client extends WebSocket { rompApp?: "chat" | "feed"; rompReady?: boolean; }
const clients = new Set<Client>();
function post(msg: any) {
  const s = JSON.stringify(msg);
  for (const c of clients) if (c.rompApp === "chat" && c.rompReady && c.readyState === WebSocket.OPEN) c.send(s);
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
  post({ type: "kernelToast", text });        // unknown to render.ts today — harmless
}

// ---- session tabs (ported from extension.ts, dialogs removed) ----

function persistOpen() {
  kstate.openSessions = Array.from(sessions.keys());
  saveKernelState();
}

function sessionStatus(s: Session, states: Map<string, SessionState> | null) {
  return statusPayload(s, chipState(s.name, states, s.lastWorking), states, s.lastSince);
}

function postSession(s: Session) {
  const p = readParsedSession(s);
  if (!p) return;
  s.lastWorking = p.status.working;
  const states = lastStates ?? backend.liveSessions();
  const state = chipState(s.name, states, s.lastWorking);
  s.lastSig = sig(s.file);
  s.lastSince = p.status.sinceEpoch;
  s.lastState = state;
  const ledger = digestOf(s.id, states.get(s.name)?.summary);
  s.ledgerSig = ledgerSigOf(ledger);
  post({
    type: "session",
    id: s.id, name: s.name, color: s.color,
    events: p.events,
    status: statusPayload(s, state, states, p.status.sinceEpoch),
    ledger,
    firstSeen: firstSeenOf(s),
  });
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
  post({ type: "update", id: s.id, events: p.events, status: statusPayload(s, state, lastStates, s.lastSince) });
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
    post({ type: "focus", id, anchor });
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
  post({ type: "focus", id, anchor });
  watch(sess);
  persistOpen();
}

// Follow a transcript fork (/clear, resume): swap the tab's file and reset the
// incremental parser, but KEEP the anchor identity — s.id stays the anchor sid
// (names/, digest/, ledger all key on it) and firstSeen stays cached from the
// anchor. Re-post the full session so the webview rebuilds from the new file.
function repointSession(s: Session, file: string) {
  s.watcher?.close();
  s.watcher = undefined;
  if (s.debounce) { clearTimeout(s.debounce); s.debounce = undefined; }
  s.file = file;
  s.parser = undefined;
  s.offset = 0;
  s.lastSig = "";
  postSession(s);
  watch(s);
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
  const cwd = process.env.ROMP_SERVE_CWD || os.homedir();
  const made = await backend.spawn(name, cwd);
  if (!made) { warn(`couldn't create session "${name}" — is the romp launcher on your PATH?`); return; }
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 800));
    const states = backend.liveSessions();
    if (states.has(name) && resolveSessionRef(name)) { openByName(name); return; }
  }
  warn(`"${name}" is starting — open it from the + picker once it appears.`);
}

function openSessionById(id: string) {
  const tr = scanTranscripts().get(id);
  if (!tr) return;
  const name = rompMeta(id).name ?? id.slice(0, 8);
  const states = backend.liveSessions();
  if (states.size > 0 && states.has(name)) addSession(tr.file);
  else addSession(tr.file, undefined, true);   // dead → read-only tab (no native revive dialog here)
}

function openByName(name: string) {
  const r = resolveSessionRef(name);
  if (!r) { warn(`no session named "${name}".`); return; }
  if (sessions.has(r.id)) { post({ type: "focus", id: r.id }); return; }
  const states = backend.liveSessions();
  if (states.size > 0 && states.has(name)) addSession(r.file);
  else addSession(r.file, undefined, true);
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
}

function refreshStatusFor(id: string) {
  const s = sessions.get(id);
  if (!s || !hasChatClients()) return;
  lastStates = backend.liveSessions();
  const state = chipState(s.name, lastStates, s.lastWorking);
  if (state === s.lastState) return;
  s.lastState = state;
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
  const live = asker.liveAsk(s.name);
  if (!live) {
    if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
    return;
  }
  if (live.sig !== s.askSig) { s.askSig = live.sig; post({ type: "askLive", id: s.id, ask: live.ask }); }
}

function refreshLiveAsks() {
  for (const s of sessions.values()) {
    if (chipState(s.name, lastStates, s.lastWorking) === "awaiting") postLiveAskFor(s);
    else if (s.askSig) { s.askSig = undefined; post({ type: "askLiveClear", id: s.id }); }
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
      if (live !== s.file) repointSession(s, live);
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
    if (state !== s.lastState) {
      s.lastState = state;
      post({ type: "status", id: s.id, status: statusPayload(s, state, lastStates, s.lastSince) });
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
  const BLOCKED_STATES = new Set(["permission", "picker"]);
  const blocked: any[] = [];
  if (lastStates) {
    for (const [name, info] of lastStates) {
      if (!BLOCKED_STATES.has(info.state)) continue;
      const id = rompIds().find((i) => (rompMeta(i).name ?? i.slice(0, 8)) === name);
      const sinceT = Number(info.since) || 0;
      blocked.push({
        sid: id ?? "", name, color: id ? rompMeta(id).color : null,
        state: info.state, since: sinceT,
        what: info.state === "permission" ? "waiting for your approval (permission prompt)"
          : "blocked on the resume picker",
      });
    }
  }
  const sg = `${feedShowDismissed ? "D" : "L"}:${dismissed.size}:${clearedRows.length}:`
    + items.map((i) => `${i.itemId}:${i.live ? 1 : 0}:${i.relevance}:${i.origin === "user" ? "u" : "a"}:${i.inAsk ? 1 : 0}:${Math.floor((now - i.t) / 60)}`).join("|")
    + "‖A:" + asks.map((a) => `${a.itemId}:${a.live ? 1 : 0}:${a.done}:${a.needsYou}:${a.linked.length}:${Math.floor((now - a.t) / 60)}:${a.text.length}:${a.column}:${a.reopened ? "R" : ""}:${a.openPaths.length}:${a.tree.map((n) => n.status[0] + (n.whoWorking ? "W" : "")).join("")}:${a.openQuestions.map((q) => q.reply_id + q.qtype[0] + (q.brief ? "+b" : "")).join(",")}`).join("|")
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

function onDotHover(sid: string | null, uuid: string | null, t: number) {
  const ev = sid ? turnEvent(sid, uuid, t) : null;
  if (!ev) { hoverTimeline(null); feedPost({ type: "hoverCards", keys: [] }); return; }
  hoverTimeline(String(ev.id));
  feedPost({ type: "hoverCards", keys: cardsForEvent(String(ev.id)).flatMap((c) => c.dom) });
}

function onDotOpen(sid: string, uuid: string | null, t: number) {
  const ev = turnEvent(sid, uuid, t);
  const cards = ev ? cardsForEvent(String(ev.id)) : [];
  if (!cards.length) { warn("this turn has no open feed card"); return; }
  feedPost({ type: "openCard", key: cards[0].open });   // multi-card: open the first (no native picker)
}

function locateInChat(sid: string, t: number) {
  if (!sid || !t) return;
  const r = resolveSessionRef(sid);
  if (!r) return;
  if (sessions.has(r.id)) {
    post({ type: "focus", id: r.id, anchorT: t, anchorKind: "user" });
    return;
  }
  const name = rompMeta(r.id).name ?? r.id.slice(0, 8);
  const states = backend.liveSessions();
  if (!(states.size > 0 && states.has(name))) return;   // dead + unopened: highlight only
  addSession(r.file);
  post({ type: "focus", id: r.id, anchorT: t, anchorKind: "user" });
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
  for (const s of sessions.values()) postSession(s);
  if (kstate.activeTab && sessions.has(kstate.activeTab)) postTo(c, { type: "focus", id: kstate.activeTab });
  const ord = readSessionOrder();
  lastOrderSig = ord.join(",");
  postTo(c, { type: "tabOrder", order: ord });
}

function handleChatMessage(c: Client, m: any) {
  if (!m) return;
  if (m.type === "ready") onChatReady(c);
  else if (m.type === "addSession") post({ type: "openPicker", pick: false });
  else if (m.type === "createSession") void createNewSession(String(m.name ?? ""));
  else if (m.type === "closeSession" && m.id) closeSession(String(m.id));   // close tab only; never kills the session
  else if (m.type === "renameSession" && m.id && typeof m.name === "string") renameSession(String(m.id), String(m.name));
  else if (m.type === "requestSessions") postTo(c, { type: "sessionList", items: sessionPayload() });
  else if (m.type === "openSession" && m.id) openSessionById(String(m.id));
  else if (m.type === "openByName" && m.name) openByName(String(m.name));
  else if (m.type === "openAll") openAllRunning();
  else if (m.type === "openFile" && m.path) openFileInEditor(String(m.path), m.line);
  else if (m.type === "openLink" && typeof m.href === "string") openLink(String(m.href));
  else if (m.type === "dotHover") onDotHover(m.sid ? String(m.sid) : null, m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
  else if (m.type === "dotOpen" && m.sid) onDotOpen(String(m.sid), m.uuid ? String(m.uuid) : null, Number(m.t) || 0);
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
  else if (m.type === "ledgerHover") hoverTimeline(m.id ? [String(m.id)] : null);
  else if (m.type === "ledgerLocate" && m.id) focusTimeline(String(m.id), String(m.sid ?? ""), Number(m.t) || 0, undefined, "work");
  else if (m.type === "imgRequest" && typeof m.path === "string") postTo(c, { type: "imgData", path: m.path, url: imgDataUrl(String(m.path)) });
  else if (m.type === "locateDiag") appendLocateDiag(m);
}

function withName(id: any, fn: (name: string) => void) {
  const name = sessions.get(String(id))?.name ?? rompMeta(String(id)).name;
  if (name) fn(name);
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
  else if (m.type === "hoverHighlight") hoverTimeline(
    Array.isArray(m.ids) && m.ids.length ? m.ids.map(String) : m.id ? String(m.id) : null);
  else if (m.type === "askClear" && m.itemId) {
    const id = String(m.itemId);
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
  else if (m.type === "answerPicker" && m.name) warn(`"${m.name}" is blocked on the resume picker — answer it in the terminal (not supported here yet).`);
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
  window.acquireVsCodeApi = function () {
    return {
      postMessage: function (m) {
        var s = JSON.stringify(m);
        if (ws && ws.readyState === 1) ws.send(s); else queue.push(s);
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
    <div id="composer"><textarea id="composer-input" rows="1" placeholder="Message this session…  (⏎ send · ⇧⏎ newline)"></textarea></div>
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
      res.end(JSON.stringify({ ok: true, sessions: sessions.size, clients: clients.size }));
    } else {
      res.writeHead(404); res.end("not found");
    }
  });

  const wss = new WebSocketServer({ server, path: "/ws" });
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
      try {
        if (app === "chat") handleChatMessage(socket, m);
        else handleFeedMessage(socket, m);
      } catch (e) {
        console.error("romp-serve: handler error for", m?.type, e);
      }
    });
    socket.on("close", () => clients.delete(socket));
    socket.on("error", () => clients.delete(socket));
  });

  setInterval(tick, POLL_MS);
  server.listen(port, host, () => {
    console.log(`romp-serve: chat  http://${host}:${port}/`);
    console.log(`romp-serve: feed  http://${host}:${port}/feed`);
  });
}

main();
