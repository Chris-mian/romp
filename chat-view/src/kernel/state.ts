// Read/write helpers for the romp record files (~/.local/state/romp and
// ~/.claude/projects). Pure Node — no backend, no UI. Ported from
// chat-view/src/extension.ts; the file formats are the cross-tool contracts
// documented in docs/specs/.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// Resolved at CALL time, not module load: a test (or a long-lived kernel) may
// point XDG_STATE_HOME elsewhere after import — ESM hoists imports above any
// caller's env assignment, so module-load constants would silently bind to the
// real state dir. (Bit us once already; see backend-contract.test.ts.)
export const PROJECTS = () => path.join(os.homedir(), ".claude", "projects");
export const ROMP_STATE = () => path.join(
  process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
  "romp",
);
export const ROMP_NAMES = () => path.join(ROMP_STATE(), "names");
export const ROMP_SUMMARIES = () => path.join(ROMP_STATE(), "summaries");
export const ROMP_REQUESTS = () => path.join(ROMP_STATE(), "requests");
export const ROMP_DECISION_BRIEF = () => path.join(ROMP_STATE(), "decision-brief");
export const ROMP_FEED_DETAIL = () => path.join(ROMP_STATE(), "feed-detail");
export const SESSION_ORDER = () => path.join(ROMP_STATE(), "session-order.json");
export const ROMP_TIMELINE_FOCUS = () => path.join(ROMP_STATE(), "timeline-focus.json");
export const ROMP_TIMELINE_HOVER = () => path.join(ROMP_STATE(), "timeline-hover.json");
export const ROMP_LOCATE_DIAG = () => path.join(ROMP_STATE(), "locate-diag.jsonl");

export interface ChipColor { bg: string; fg: string; }

// ---- session identity (names/<sid> = name\tdir\tbg\tfg) ----

export function rompIds(): string[] {
  try { return fs.readdirSync(ROMP_NAMES()); } catch { return []; }
}

export function rompMeta(id: string): { name?: string; color: ChipColor | null } {
  try {
    const txt = fs.readFileSync(path.join(ROMP_NAMES(), id), "utf8");
    const [name, , bg, fg] = txt.split("\t");
    const color = bg && bg.trim() ? { bg: bg.trim(), fg: (fg || "white").trim() } : null;
    return { name: name?.trim() || undefined, color };
  } catch {
    return { color: null };
  }
}

// The working dir stored for a session, so a revive resumes where it lived.
export function rompDir(id: string): string | undefined {
  try {
    const dir = fs.readFileSync(path.join(ROMP_NAMES(), id), "utf8").split("\t")[1]?.trim();
    return dir || undefined;
  } catch { return undefined; }
}

// Rewrite the name field of a session's identity record (mirrors `romp _renamed`).
export function rewriteName(id: string, name: string): void {
  try {
    const f = path.join(ROMP_NAMES(), id);
    const parts = fs.readFileSync(f, "utf8").replace(/\n$/, "").split("\t");
    parts[0] = name;
    fs.writeFileSync(f, parts.join("\t") + "\n");
  } catch { /* no record for this id — the rename hook covers it */ }
}

// Identity colour by NAME (most recently registered id carrying it).
export function colorForName(name: string): ChipColor | null {
  if (!name) return null;
  let best: { color: ChipColor; mtime: number } | null = null;
  for (const id of rompIds()) {
    const meta = rompMeta(id);
    if (meta.name !== name || !meta.color) continue;
    let mtime = 0;
    try { mtime = fs.statSync(path.join(ROMP_NAMES(), id)).mtimeMs; } catch { /* ignore */ }
    if (!best || mtime > best.mtime) best = { color: meta.color, mtime };
  }
  return best?.color ?? null;
}

// ---- transcripts ----

export function scanTranscripts(): Map<string, { file: string; mtime: number }> {
  const map = new Map<string, { file: string; mtime: number }>();
  let dirs: string[] = [];
  try { dirs = fs.readdirSync(PROJECTS()); } catch { return map; }
  for (const d of dirs) {
    const full = path.join(PROJECTS(), d);
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

// Resolve a deep-link `session` (a transcript id; falls back to a romp name →
// most-recent transcript) to {id, file} on disk, or null.
export function resolveSessionRef(session: string): { id: string; file: string } | null {
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

// ---- summaries / ledger ----

export interface LedgerBullet { text: string; t?: number; id?: string; sid?: string; }
export interface Ledger { summary: string; bullets: LedgerBullet[]; }

export function recentReplyBullets(id: string, k: number): LedgerBullet[] {
  try {
    const lines = fs.readFileSync(path.join(ROMP_SUMMARIES(), `${id}.jsonl`), "utf8").trim().split("\n");
    const all: LedgerBullet[] = [];
    for (const ln of lines) {
      if (!ln) continue;
      try {
        const e = JSON.parse(ln);
        if (e.kind === "reply" && e.text) all.push({ text: String(e.text).trim(), t: typeof e.t === "number" ? e.t : undefined, id: typeof e.id === "string" ? e.id : undefined, sid: id });
      } catch { /* skip */ }
    }
    all.sort((a, b) => (b.t ?? 0) - (a.t ?? 0)); // newest first
    return all.slice(0, k);
  } catch { return []; }
}

export function lastReplySummary(id: string): string {
  try {
    const lines = fs.readFileSync(path.join(ROMP_SUMMARIES(), `${id}.jsonl`), "utf8").trim().split("\n").filter(Boolean);
    const tail = lines.slice(-12).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) as any[];
    for (let i = tail.length - 1; i >= 0; i--) if (tail[i].kind === "reply" && tail[i].text) return String(tail[i].text).trim();
    const last = tail[tail.length - 1];
    return last && last.text ? String(last.text).trim() : "";
  } catch { return ""; }
}

// digest summary + live bullets (fallback chain: digest → latest reply → live var)
export function digestOf(id: string, liveSummary?: string): Ledger | null {
  const bullets = recentReplyBullets(id, 30);   // the box is a scroll-pane (~6 visible); send a deep tail to scroll
  let summary = "";
  try {
    const raw = fs.readFileSync(path.join(ROMP_STATE(), "digest", `${id}.json`), "utf8").trim();
    if (raw) { const d = JSON.parse(raw); if (typeof d.summary === "string") summary = d.summary.trim(); }
  } catch { /* no digest */ }
  if (!summary) summary = lastReplySummary(id) || liveSummary || "";
  if (!summary && !bullets.length) return null;
  return { summary, bullets };
}

export function ledgerSigOf(l: Ledger | null): string {
  if (!l) return "";
  return l.summary + "§" + l.bullets.map((b) => `${b.t ?? ""}:${b.text}`).join("|");
}

export function lastSummary(id: string): string | undefined {
  try {
    const txt = fs.readFileSync(path.join(ROMP_SUMMARIES(), id), "utf8").trim();
    const last = txt.split("\n").filter(Boolean).pop();
    if (!last) return undefined;
    try { return (JSON.parse(last).text || "").trim() || undefined; }
    catch { return last.slice(0, 140); }
  } catch { return undefined; }
}

// ---- request registry ----

export function readReqRows(file: string): any[] {
  try {
    const raw = fs.readFileSync(path.join(ROMP_REQUESTS(), file), "utf8");
    const out: any[] = [];
    for (const ln of raw.split("\n")) {
      const t = ln.trim();
      if (t) { try { out.push(JSON.parse(t)); } catch { /* skip */ } }
    }
    return out;
  } catch { return []; }
}

export function readDecisionBrief(replyId: string): any | null {
  try {
    const d = JSON.parse(fs.readFileSync(path.join(ROMP_DECISION_BRIEF(), `${replyId}.json`), "utf8"));
    return d && typeof d.question === "string" && d.question ? d : null;
  } catch { return null; }
}

// The human-asserted registry files (single-writer: the UI).
export function appendCleared(id: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS(), { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS(), "cleared.jsonl"),
      JSON.stringify({ id, t: Math.floor(Date.now() / 1000) }) + "\n");
  } catch { /* ignore */ }
}

// UndoClear: pop the NEWEST cleared.jsonl row (single-writer + append-only, so
// the last line is always the most recent Clear); tmp+rename keeps the rewrite
// atomic for the read-only consumers (daemon, pipeline).
export function undoLastClear(): boolean {
  try {
    const p = path.join(ROMP_REQUESTS(), "cleared.jsonl");
    const lines = fs.readFileSync(p, "utf8").split("\n").filter((l) => l.trim());
    if (!lines.length) return false;
    lines.pop();
    const tmp = p + ".tmp";
    fs.writeFileSync(tmp, lines.length ? lines.join("\n") + "\n" : "");
    fs.renameSync(tmp, p);
    return true;
  } catch { return false; }
}

export function appendFollowup(id: string, sid: string, text: string) {
  try {
    fs.mkdirSync(ROMP_REQUESTS(), { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS(), "followups.jsonl"),
      JSON.stringify({ id, sid, t: Math.floor(Date.now() / 1000), text }) + "\n");
  } catch { /* ignore */ }
}

export function appendCorrection(nodeId: string, decisionRef: string | null, note: string, by = "web-kernel") {
  try {
    fs.mkdirSync(ROMP_REQUESTS(), { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS(), "corrections.jsonl"),
      JSON.stringify({
        t: Math.floor(Date.now() / 1000), by_sid: by, kind: "link",
        decision_ref: decisionRef,
        should_have: { request_ids: [nodeId], relevance: "DONE" }, note,
      }) + "\n");
  } catch { /* ignore */ }
}

export function appendRelevanceCorrection(replyId: string, note: string, by = "web-kernel") {
  try {
    fs.mkdirSync(ROMP_REQUESTS(), { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS(), "corrections.jsonl"),
      JSON.stringify({
        t: Math.floor(Date.now() / 1000), by_sid: by, kind: "relevance",
        decision_ref: replyId,
        should_have: { relevance: "DONE" }, note,
      }) + "\n");
  } catch { /* ignore */ }
}

// Exception report (the user's refinement loop, 2026-06-11): free-text + category
// from the modal's ⚠ Report box, with a snapshot of the card's computed state so
// the report is diagnosable later without replaying history. Own file (not
// corrections.jsonl — these carry no should_have verdict for the read-side fold);
// consumed by prompt-rework passes as labeled failure examples.
export function appendReport(itemId: string, category: string, note: string, snapshot: any) {
  try {
    fs.mkdirSync(ROMP_REQUESTS(), { recursive: true });
    fs.appendFileSync(path.join(ROMP_REQUESTS(), "reports.jsonl"),
      JSON.stringify({ kind: "report", id: itemId, t: Math.floor(Date.now() / 1000),
        category, note, snapshot }) + "\n");
  } catch { /* ignore */ }
}

// ---- shared tab/lane order ----

export function readSessionOrder(): string[] {
  try {
    const arr = JSON.parse(fs.readFileSync(SESSION_ORDER(), "utf8"));
    return Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}

export function writeSessionOrder(order: string[]) {
  try {
    const tmp = `${SESSION_ORDER()}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(order));
    fs.renameSync(tmp, SESSION_ORDER());   // atomic
  } catch { /* ignore */ }
}

// ---- timeline projection files (focus / hover / chat-active) ----

export function writeChatActive(active: { tid: string; name: string } | null) {
  try {
    fs.writeFileSync(path.join(ROMP_STATE(), "chat-active"), active ? JSON.stringify(active) : "");
  } catch { /* ignore */ }
}

export function focusTimeline(id: string, sid: string, t: number, dag?: { ask: string; events: string[]; msgs: string[] }, anchor?: "prompt" | "work", locate?: boolean, jump?: boolean) {
  try {
    const tmp = ROMP_TIMELINE_FOCUS() + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify({
      id, sid, t, nonce: Date.now(),
      ...(dag ? { dag } : {}), ...(anchor ? { anchor } : {}), ...(locate === false ? { locate: false } : {}),
      ...(jump ? { jump: true } : {}),
    }));
    fs.renameSync(tmp, ROMP_TIMELINE_FOCUS());
  } catch { /* ignore */ }
}

let hoverNonce = 0;
let hoverTimer: ReturnType<typeof setTimeout> | undefined;
let hoverPendingIds: string[] | null = null;
let hoverPendingNonce = 0;
// The ids are the highlight set written to timeline-hover.json. They may be whole-turn event ids
// (light the whole glyph — a DAG journey / a coarse card hover) OR per-ATOM ids minted by
// romp-events (promptId → the start dot only, workId → the work bar only): the dot/bar split lives
// in the id itself, so the timeline never needs an out-of-band "which half" flag to interpret it.
// Returns the monotonic NONCE this hover will carry into the file. It's assigned at CALL time (not
// at the debounced write) so the kernel can push the SAME nonce straight to its /timeline clients
// (server.ts pushHover) — a fast lane past the fs.watch→rebuild — and a trailing data-poll, reading
// the identical nonce from the file, ties instead of clobbering (setHover honors max-nonce).
export function hoverTimeline(ids: string[] | string | null): number {
  hoverPendingIds = ids == null ? null : Array.isArray(ids) ? ids : [ids];
  hoverPendingNonce = ++hoverNonce;   // assigned now; the debounced writer commits this exact value
  if (!hoverTimer) hoverTimer = setTimeout(() => {
    hoverTimer = undefined;
    try {
      const tmp = ROMP_TIMELINE_HOVER() + ".tmp";
      fs.writeFileSync(tmp, JSON.stringify({
        id: hoverPendingIds ? hoverPendingIds[0] : null,
        ids: hoverPendingIds, nonce: hoverPendingNonce,
      }));
      fs.renameSync(tmp, ROMP_TIMELINE_HOVER());
    } catch { /* ignore */ }
  }, 40);
  return hoverPendingNonce;
}

export function appendLocateDiag(m: any) {
  try {
    fs.appendFileSync(ROMP_LOCATE_DIAG(), JSON.stringify({
      t: Math.floor(Date.now() / 1000), sid: String(m.id || ""), ok: !!m.ok,
      trail: Array.isArray(m.trail) ? m.trail.map(String) : [],
      ...(m.anchor ? { anchor: String(m.anchor) } : {}),
      ...(typeof m.anchorT === "number" ? { anchorT: m.anchorT } : {}),
      ...(m.kind ? { kind: String(m.kind) } : {}),
    }) + "\n");
  } catch { /* ignore */ }
}

// ---- events-cache (romp-events' per-session snapshot) ----

export function turnEvent(sid: string, uuid: string | null, t: number): any | null {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(ROMP_STATE(), "events-cache", `${sid}.json`), "utf8"));
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
export function openTurnId(sid: string): string | null {
  const f = path.join(ROMP_STATE(), "events-cache", `${sid}.json`);
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

// The open turn's whole contiguous RUN, newest first (null when no open turn).
// romp-events slices one physical Claude Code turn at queue folds and mid-turn
// decisions: absorbed/decision/drain boundaries CONTINUE the same run, while
// typed/queued boundaries start a new one. Work for a queued prompt routinely
// ships under a LATER slice's id (three same-day incidents, 2026-06-12), so
// run-aware consumers (the liveness claim) must see every slice of the run,
// not just the newest one.
const _openRunCache = new Map<string, { m: number; ids: string[] | null }>();
export function openRunIds(sid: string): string[] | null {
  const f = path.join(ROMP_STATE(), "events-cache", `${sid}.json`);
  let st: fs.Stats;
  try { st = fs.statSync(f); } catch { return null; }
  const hit = _openRunCache.get(sid);
  if (hit && hit.m === st.mtimeMs) return hit.ids;
  let ids: string[] | null = null;
  try {
    const evs: any[] = JSON.parse(fs.readFileSync(f, "utf8"))?.data?.events || [];
    const last = evs[evs.length - 1];
    if (last && last.open) {
      ids = [];
      for (let i = evs.length - 1; i >= 0; i--) {
        ids.push(String(evs[i].id));
        const k = String(evs[i].kind || "");
        if (k !== "absorbed" && k !== "decision" && k !== "drain") break;  // run root
      }
    }
  } catch { /* unreadable cache → claim unknown */ }
  _openRunCache.set(sid, { m: st.mtimeMs, ids });
  return ids;
}

// ---- feed-detail cache ----

export function readFeedDetail(id: string): any | null {
  try {
    const raw = fs.readFileSync(path.join(ROMP_FEED_DETAIL(), `${id}.json`), "utf8").trim();
    if (!raw) return null;
    const d = JSON.parse(raw);
    return d && typeof d.paragraph === "string" && d.paragraph ? d : null;
  } catch { return null; }
}

// A real romp-events id is exactly `<fsid>:<ts>:<hash>`; synthesized fallback
// ids have 4 parts and never bind to a producer.
export function isEventId(id: string): boolean {
  const p = id.split(":");
  return p.length === 3 && /^[0-9a-f-]{16,}$/i.test(p[0]) && /^\d+$/.test(p[1]);
}

export function relTime(ms: number): string {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
