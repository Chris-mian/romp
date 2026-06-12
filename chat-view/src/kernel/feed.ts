// The feed + ask fold: read-time projections of the romp record files into the
// three-column feed payload. Ported from chat-view/src/extension.ts — the fold
// semantics are spec'd in ~/.local/state/romp/REQUESTS.md and pinned by
// tests/test_romp_read_side.py (the Python twin used by romp -f).
import type { SessionState } from "./backend";
import {
  ChipColor, rompIds, rompMeta, readReqRows, readDecisionBrief, openTurnId,
  ROMP_SUMMARIES, ROMP_REQUESTS,
} from "./state";
import * as fs from "fs";
import * as path from "path";

// Recency colormap — a port of bin/romp_colormap.py (crameri "hawaii"):
// recent → bright, log scale. Re-sync stops + FADE_HI when the fleet swaps maps.
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
export function ageRgbTuple(ageSec: number): [number, number, number] {
  const a = Math.max(FEED_FADE_LO, Math.min(FEED_FADE_HI, ageSec));
  const f = (Math.log(a) - Math.log(FEED_FADE_LO)) / (Math.log(FEED_FADE_HI) - Math.log(FEED_FADE_LO));
  return feedRamp(1 - f);
}

function djb2(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export type Relevance = "DONE" | "DECISION" | "ACTION" | "IDEA" | "WAIT" | "DETAILS" | "UNTAGGED";
export interface FeedItem {
  itemId: string; sid: string; name: string; color: ChipColor | null;
  did: string; ask: string; t: number; live: boolean; relevance: Relevance;
  origin: "user" | "agent";
  inAsk?: boolean;
}

export function normRelevance(v: any): Relevance {
  const s = String(v || "").toUpperCase();
  return s === "DONE" || s === "DECISION" || s === "ACTION" || s === "IDEA" || s === "WAIT" || s === "DETAILS" ? s : "UNTAGGED";
}

// Rebuilt on every feed pass: the user's last typed-turn time per session, and
// turn_id → the typed turn's phrase (group-card titles).
export const lastReqBySid = new Map<string, number>();
export const reqPhraseById = new Map<string, string>();

export function computeFeedItems(states: Map<string, SessionState> | null): FeedItem[] {
  const liveNames = new Set<string>(states ? Array.from(states.keys()) : []);
  lastReqBySid.clear();
  reqPhraseById.clear();
  const out: FeedItem[] = [];
  for (const id of rompIds()) {
    const meta = rompMeta(id);
    const name = meta.name ?? id.slice(0, 8);
    if (!/[A-Za-z0-9]/.test(name)) continue;   // skip garbage names (stray "\")
    let raw: string;
    try { raw = fs.readFileSync(path.join(ROMP_SUMMARIES(), `${id}.jsonl`), "utf8"); }
    catch { continue; }
    const evs: any[] = [];
    for (const ln of raw.split("\n")) {
      const t = ln.trim();
      if (t) { try { evs.push(JSON.parse(t)); } catch { /* skip */ } }
    }
    evs.sort((a, b) => (a.t || 0) - (b.t || 0));
    // ORIGIN: a `request` line exists ONLY for turns the user typed; a reply with
    // a SAME-ID request line is user-prompted.
    const reqText = new Map<string, string>();
    for (const e of evs) {
      if (e.kind === "request" && typeof e.id === "string" && e.id) {
        reqText.set(e.id, String(e.text || ""));
        reqPhraseById.set(e.id, String(e.text || ""));
        const start = Number(e.id.split(":")[1]);
        const rt = Number.isFinite(start) && start > 0 ? start : (e.t || 0);
        lastReqBySid.set(id, Math.max(lastReqBySid.get(id) || 0, rt));
      }
    }
    // Dedupe replies by id, last line wins; display time = the turn's
    // PROCESS-START (the id's middle field), not the write-time.
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

// ---- the ask fold (column = DAG leaf-path accounting; see docs/design.md §3) ----

type RowStatus = "done" | "question" | "update";
export type AskColumn = "asks" | "needs_input" | "completed";
export interface AskLinked { did: string; relevance: Relevance; t: number; reply_id: string; status: RowStatus; sid: string; name: string; color: ChipColor | null; answer?: boolean }
export interface AskQuestion { reply_id: string; sid: string; name: string; t: number; brief: any | null; qtype: "decision" | "action" | "idea"; nodeId: string }
export interface AskPath { name: string; sid: string; color: ChipColor | null; since: number; lastPhrase: string }
export interface AskTreeNode {
  id: string; kind: "ask" | "handoff";
  text: string;
  who: string;
  whoSid: string;
  whoColor: ChipColor | null;
  whoWorking?: boolean;
  status: "done" | "question" | "open";
  t: number; last: number;
  children: string[];
  rows: AskLinked[];
}
export interface AskItem {
  itemId: string; sid: string; name: string; color: ChipColor | null;
  text: string; t: number; created: number; live: boolean;
  done: number; needsYou: number; linked: AskLinked[]; turnId: string;
  column: AskColumn; openQuestions: AskQuestion[]; openPaths: AskPath[];
  reopened: boolean;                   // resurrected: a question arrived AFTER the user's clear
  path: { events: string[]; msgs: string[] };
  tree: AskTreeNode[];
  // liveness reveal (2026-06-11): outline color in the feed — what an automated
  // "is this still being worked?" rule WOULD say. Colors only, decides nothing.
  liveness: AskLiveness; livenessWhy: string;
  // settled card moved out of WORKING by the read-time auto-filing rule — the
  // webview keeps its green ring in COMPLETED (verify before Clear)
  autoFiled?: boolean;
  // every path ends with an explicit DONE stamp (model or corrections) — the
  // OTHER door into COMPLETED; webview ring = blue
  explicitDone?: boolean;
  // newest link on some node is WAIT: paused on an EXTERNAL event — held in
  // WORKING, exempt from auto-filing and the green ring; ⏳ chip on the card
  waiting?: boolean;
  // every typed turn that touched this card (mint + amends) — joins a LIVE
  // blocked turn (permission/picker) to the card it's blocked on
  turnIds: string[];
  // set by refreshFeed when the owning session is blocked ON this card's work
  blocked?: { state: string; since: number; what: string };
  // missed-handoff suspects attached by refreshFeed (deterministic sweep)
  suspects?: Array<{ mid: string; to: string; t: number; snippet: string; why: string }>;
  groupTitle?: string; groupN?: number;
}
// The four liveness verdicts, session-level by construction:
//   active    — the owning session is mid-turn on THIS card
//   delegated — owner quiet, but a session holding an UNFINISHED handoff is mid-turn
//   stalled   — an unfinished handoff whose recipient is quiet or gone
//   settled   — no turn anywhere, no open handoff: nothing moves without the user
export type AskLiveness = "active" | "delegated" | "stalled" | "settled";

export function computeAskItems(states: Map<string, SessionState> | null, didById: Map<string, FeedItem>): AskItem[] {
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
  const clearedAt = new Map<string, number>();
  for (const c of readReqRows("cleared.jsonl")) {
    const cid = String(c.id);
    clearedAt.set(cid, Math.max(clearedAt.get(cid) || 0, c.t || 0));
  }
  const followupsById = new Map<string, any[]>();
  for (const f of readReqRows("followups.jsonl")) {
    const fid = String(f.id || "");
    if (!fid) continue;
    if (!followupsById.has(fid)) followupsById.set(fid, []);
    followupsById.get(fid)!.push(f);
  }
  const children = new Map<string, string[]>();
  for (const [cid, pids] of parents) {
    for (const p of pids) {
      const key = String(p);
      if (!children.has(key)) children.set(key, []);
      children.get(key)!.push(cid);
    }
  }
  const nodeLinks = new Map<string, any[]>();
  for (const l of readReqRows("links.jsonl")) {
    if (l.kind !== "link" || !Array.isArray(l.request_ids)) continue;
    const dbr = l.did_by_request && typeof l.did_by_request === "object" ? l.did_by_request : null;
    for (const rid of l.request_ids) {
      const key = String(rid);
      if (!asks.has(key) && !internals.has(key)) continue;
      if (!nodeLinks.has(key)) nodeLinks.set(key, []);
      const perReq = dbr && typeof dbr[key] === "string" && dbr[key].trim() ? dbr[key].trim()
        : typeof l.did === "string" && l.did.trim() ? l.did.trim() : null;
      nodeLinks.get(key)!.push(perReq ? { ...l, _didFor: perReq } : l);
    }
  }
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
        _corr: true,
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
  const answered = (l: any): boolean => (lastReqBySid.get(String(l.sid || "")) || 0) > (l.t || 0);
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
      // the session does NOT cross it off; only an explicit "did it" (a DONE
      // correction, newest-wins) closes it.
      else if (rel === "ACTION") st = { st: "question", qlink: newest };
      // DECISION is answered by the user's next typed turn OR by the session moving on
      else if (rel === "DECISION" && !answered(newest) && !movedOn(newest)) st = { st: "question", qlink: newest };
      // IDEA is dismissed by the user's next typed turn alone (it asks for a reaction)
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
    if ((parents.get(id) || []).length) continue;
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
    const rollCache = new Map<string, "done" | "question" | "open">();
    const rollup = (nid: string): "done" | "question" | "open" => {
      const hit = rollCache.get(nid);
      if (hit) return hit;
      rollCache.set(nid, "open");                      // cycle sentinel
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
          nodeId: nid,
        });
      } else if (st.st === "open" && !kidsOf(nid).length) {
        const node = asks.get(nid) ?? internals.get(nid);
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
    const fuOpen = (followupsById.get(id) || []).filter((f) => {
      const ft = f.t || 0;
      const minted = (children.get(id) || []).some((c) => seen.has(c) && ((asks.get(c) ?? internals.get(c))?.t || 0) >= ft);
      const refiled = (nodeLinks.get(id) || []).some((l) => (l.t || 0) > ft);
      return !minted && !refiled;
    });
    for (const f of fuOpen) openPaths.push({
      name: nameOf(String(a.sid || "")), sid: String(a.sid || ""), color: rompMeta(String(a.sid || "")).color,
      since: f.t || 0,
      lastPhrase: `Follow-up sent: ${String(f.text || "")}`,
    });
    const clearedT = clearedAt.get(id);
    const reopened = clearedT !== undefined &&
      (openQuestions.some((q) => q.t > clearedT) || fuOpen.some((f) => (f.t || 0) > clearedT));
    if (clearedT !== undefined && !reopened) continue;
    let column: AskColumn = openQuestions.length ? "needs_input" : allDone && !fuOpen.length ? "completed" : "asks";
    const rowRank = { question: 2, done: 1, update: 0 } as const;
    const rowFor = (l: any, open: { qlink?: any }): AskLinked => {
      const rel = normRelevance(l.relevance);
      const rid = String(l.reply_id || "");
      const fi = didById.get(rid);
      return {
        did: l._didFor ? String(l._didFor) : fi ? fi.did : (l._did ? String(l._did) : "(deliverable)"), relevance: rel, t: l.t || 0, reply_id: rid,
        status: rel === "DONE" ? "done" : (rel === "DECISION" || rel === "ACTION" || rel === "IDEA") && open.qlink === l ? "question" : "update",
        sid: String(l.sid || ""), name: nameOf(String(l.sid || "")),
        color: rompMeta(String(l.sid || "")).color,
        answer: l._answer ? true : undefined,    // the user's recorded answer → ↩ row
      };
    };
    const displayRows = (nid: string, open: NodeStatus): AskLinked[] => {
      const by = new Map<string, AskLinked>();
      for (const l of nodeLinks.get(nid) || []) {            // time-ascending
        const row = rowFor(l, open);
        const prev = by.get(row.reply_id);
        if (!prev) { by.set(row.reply_id, row); continue; }
        if (rowRank[row.status] > rowRank[prev.status]) prev.status = row.status;
        if (!l._corr) prev.t = Math.max(prev.t, row.t);
      }
      return Array.from(by.values()).sort((x, y) => x.t - y.t);
    };
    const rowByReply = new Map<string, AskLinked>();
    const nodeRows = new Map<string, AskLinked[]>();
    let last = a.t || 0;
    for (const nid of subgraph) {
      const node = asks.get(nid) ?? internals.get(nid);
      if (node?.t) last = Math.max(last, node.t);
      const rows = displayRows(nid, stOf.get(nid)!);
      nodeRows.set(nid, rows);
      for (const row of rows) {
        const prev = rowByReply.get(row.reply_id);
        if (!prev || rowRank[row.status] > rowRank[prev.status]) rowByReply.set(row.reply_id, row);
        last = Math.max(last, row.t);
      }
    }
    for (const f of fuOpen) last = Math.max(last, f.t || 0);
    const linked = Array.from(rowByReply.values()).sort((x, y) => y.t - x.t);
    const tree: AskTreeNode[] = subgraph.map((nid) => {
      const node = asks.get(nid) ?? internals.get(nid);
      const isAsk = asks.has(nid);
      const rows = nodeRows.get(nid) || [];
      const whoSid = String((isAsk ? node?.sid : (node?.to_sid || node?.sid)) || "");
      return {
        id: nid, kind: isAsk ? "ask" as const : "handoff" as const,
        text: String(node?.text || ""),
        who: nameOf(whoSid), whoSid, whoColor: rompMeta(whoSid).color,
        whoWorking: !!(states && states.get(nameOf(whoSid))?.state === "working"),
        status: rollup(nid),
        t: node?.t || 0,
        last: rows.length ? rows[rows.length - 1].t : (node?.t || 0),
        children: (children.get(nid) || []).filter((c) => seen.has(c))
          .sort((x, y) => ((asks.get(x) ?? internals.get(x))?.t || 0) - ((asks.get(y) ?? internals.get(y))?.t || 0)),
        rows,
      };
    });
    const meta = rompMeta(String(a.sid || ""));
    const name = meta.name ?? String(a.sid || "").slice(0, 8);
    // ---- liveness: deterministic from live state + the tree's open handoffs.
    // "Mid-turn" = working/compacting/permission — a permission prompt is a
    // paused turn, not a finished one.
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
    // on something else leaves the settled verdict standing.
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
    // WAIT exemption (the user 2026-06-11): a node whose newest link is WAIT ended
    // its turn on purpose pending an EXTERNAL event — settled but NOT done: stays
    // in WORKING, no green ring, no auto-filing. New work landing lifts it.
    const extWait = subgraph.some((nid) => {
      const ls = nodeLinks.get(nid) || [];
      const newest = ls.length ? ls[ls.length - 1] : null;
      return !!newest && normRelevance(newest.relevance) === "WAIT";
    });
    if (extWait && liveness === "settled") livenessWhy += " — but it is WAITING on an external event (exempt from auto-filing)";
    // AUTO-FILING (turned on 2026-06-11): a settled card never sits in WORKING —
    // nothing is moving it, so it rests in COMPLETED now and pulls itself back
    // the moment real work touches it. autoFiled keeps the green ring visible.
    // fuOpen guard: a just-sent follow-up holds the card until the bookkeeper
    // mints the delivered turn. states empty = probe unreachable: liveness is
    // unknowable, NOT "everyone quiet" — never mass-auto-file on a blind read.
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
  // CLAIM-LAG hold (the user 2026-06-11 evening): while a session is mid-turn and
  // its open turn is claimed by NO card yet (the ask capture for that prompt
  // hasn't landed), the turn's true card is unknown — one of this session's
  // "settled" cards is probably being worked right now. Hold the whole
  // session's auto-filing until capture lands; self-heals in seconds.
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
  const byTurn = new Map<string, number>();
  for (const a of out) byTurn.set(a.turnId, (byTurn.get(a.turnId) || 0) + 1);
  for (const a of out) {
    const n = byTurn.get(a.turnId) || 1;
    if (n > 1) { a.groupN = n; a.groupTitle = reqPhraseById.get(a.turnId) || ""; }
  }
  return out;
}

// ---- missed-handoff suspect sweep (deterministic, the user 2026-06-11) ----
// A message the classifier judged "not a delegation" (req-decision, req=false)
// is SUSPECT when the recipient then produced work linked to NOTHING within the
// window — orphan work right after a dismissed message is the classic missed
// handoff. Read from the decision log (mtime-cached); surfaced as a ⚠ badge on
// the sender's most plausible open card. Pure joins, no model.
const SUSPECT_WINDOW = 45 * 60;        // recipient orphan work this soon after the message
const SUSPECT_HORIZON = 48 * 3600;     // ignore older history
let _suspectCache: { key: string; rows: any[] } | null = null;
export function missedHandoffSuspects(now: number): Array<{ mid: string; fromSid: string; toSid: string; t: number; snippet: string; orphanT: number }> {
  const files = [path.join(ROMP_REQUESTS(), "decision-log.jsonl"), path.join(ROMP_REQUESTS(), "decision-log.jsonl.1")];
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
  // Only UNSURE audits reach the human (the user 2026-06-11): the daemon's
  // auditor repairs real handoffs automatically and suppresses coincidences;
  // unaudited suspects wait their turn in the queue rather than nagging.
  const rows = dismissed.flatMap((d) => {
    if (audits.get(String(d.msg_id)) !== "unsure") return [];
    const orphan = orphanLinks.find((l) => l.sid === String(d.to_sid) && l.t > (d.t || 0) && l.t <= (d.t || 0) + SUSPECT_WINDOW);
    return orphan ? [{ mid: String(d.msg_id), fromSid: String(d.from_sid || ""), toSid: String(d.to_sid || ""),
      t: d.t || 0, snippet: String(d.snippet || "").slice(0, 160), orphanT: orphan.t }] : [];
  });
  _suspectCache = { key, rows };
  return rows;
}

export function workingNames(states: Map<string, SessionState> | null): string[] {
  if (!states) return [];
  const out: string[] = [];
  for (const [name, info] of states) if (info.state === "working") out.push(name);
  return out;
}
