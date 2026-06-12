// The feed + ask fold: read-time projections of the romp record files into the
// three-column feed payload. Ported from chat-view/src/extension.ts — the fold
// semantics are spec'd in ~/.local/state/romp/REQUESTS.md and pinned by
// tests/test_romp_read_side.py (the Python twin used by romp -f).
import type { SessionState } from "./backend";
import {
  ChipColor, rompIds, rompMeta, readReqRows, readDecisionBrief, ROMP_SUMMARIES,
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

export type Relevance = "DONE" | "DECISION" | "ACTION" | "IDEA" | "DETAILS" | "UNTAGGED";
export interface FeedItem {
  itemId: string; sid: string; name: string; color: ChipColor | null;
  did: string; ask: string; t: number; live: boolean; relevance: Relevance;
  origin: "user" | "agent";
  inAsk?: boolean;
}

export function normRelevance(v: any): Relevance {
  const s = String(v || "").toUpperCase();
  return s === "DONE" || s === "DECISION" || s === "ACTION" || s === "IDEA" || s === "DETAILS" ? s : "UNTAGGED";
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
export interface AskLinked { did: string; relevance: Relevance; t: number; reply_id: string; status: RowStatus; sid: string; name: string; color: ChipColor | null }
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
  reopened: boolean;
  path: { events: string[]; msgs: string[] };
  tree: AskTreeNode[];
  groupTitle?: string; groupN?: number;
}

export function computeAskItems(states: Map<string, SessionState> | null, didById: Map<string, FeedItem>): AskItem[] {
  const liveNames = new Set<string>(states ? Array.from(states.keys()) : []);
  const asks = new Map<string, any>();
  const internals = new Map<string, any>();
  const parents = new Map<string, string[]>();
  for (const n of readReqRows("nodes.jsonl")) {
    if (n.kind === "ask" && typeof n.id === "string") { if (!asks.has(n.id)) asks.set(n.id, { ...n }); }
    else if (n.kind === "internal" && typeof n.id === "string") { if (!internals.has(n.id)) internals.set(n.id, { ...n }); }
    else if (n.kind === "parents" && typeof n.id === "string") parents.set(n.id, Array.isArray(n.parent_ids) ? n.parent_ids : []);
    else if (n.kind === "amend" && asks.has(n.id)) asks.get(n.id).text = String(n.text || asks.get(n.id).text || "");
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
    if (ls.length) {
      const newest = ls[ls.length - 1];
      const rel = normRelevance(newest.relevance);
      if (rel === "DONE") st = { st: "done" };
      else if (rel === "ACTION") st = { st: "question", qlink: newest };
      else if (rel === "DECISION" && !answered(newest) && !movedOn(newest)) st = { st: "question", qlink: newest };
      else if (rel === "IDEA" && !answered(newest)) st = { st: "question", qlink: newest };
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
    const column: AskColumn = openQuestions.length ? "needs_input" : allDone && !fuOpen.length ? "completed" : "asks";
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
    out.push({
      itemId: id, sid: String(a.sid || ""), name, color: meta.color,
      text: String(a.text || ""), t: last, created: a.t || 0,
      live: liveNames.has(name),
      done: linked.filter((r) => r.status === "done").length,
      needsYou: openQuestions.length,
      linked, turnId: String(a.turn_id || ""),
      column, openQuestions, openPaths, reopened,
      path: {
        events: [String(a.turn_id || ""), ...linked.map((r) => r.reply_id)].filter(Boolean),
        msgs: subgraph.filter((nid) => internals.has(nid)),
      },
      tree,
    });
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

export function workingNames(states: Map<string, SessionState> | null): string[] {
  if (!states) return [];
  const out: string[] = [];
  for (const [name, info] of states) if (info.state === "working") out.push(name);
  return out;
}
