// romp Postal Service — the message-format contract this extension consumes.
//
// Postal messages (peer-to-peer mail between romp sessions) land *inside* the
// transcript: a received message arrives as a user turn (Stop-hook drain or
// live push) or as a check_inbox tool result; a sent message is a send_message
// tool call. We turn those into clean, identity-coloured cards.
//
// We deliberately DO NOT parse the human-readable inbox/push prose
// ("📬 New message(s)…", "— from X (date):", the "####" banner, the reply
// hint). That text is presentation and is free to change. Instead we depend on
// two STABLE, machine-oriented parts of romp-postal's contract, plus the MCP
// tool schema:
//
//   1. The join marker `<!-- romp-msg-id: <id> -->`, emitted verbatim by both
//      format_inbox() and format_push() and described there as "exact id for
//      the timeline join". It is the ONLY piece of delivery prose we read.
//        → dotfiles/scripts/romp-postal   (format_inbox / format_push)
//
//   2. The timeline log at $XDG_STATE_HOME/romp/timeline/messages.jsonl, an
//      append-only JSONL written by deliver() via _tl_append(). Every "sent"
//      line is: {t, ev:"sent", id, from, from_id, to_id, body, park?}. We read
//      every displayed field from here, keyed by the id from (1).
//        → dotfiles/scripts/romp-postal   (deliver / _tl_append / TLDIR)
//
//   3. Outgoing sends are read from the structured MCP tool call `send_message`
//      ({to, body}); the tool name + input schema is the contract there.
//        → dotfiles/scripts/romp-postal   (MCP_TOOLS: send_message)
//
// Sender/recipient colour comes from the names registry the rest of the
// extension already reads ($XDG_STATE_HOME/romp/names/<id> = name\tdir\tbg\tfg),
// joined by from_id (incoming) or recipient name (outgoing).
//
// If romp-postal changes any of the three above, update THIS file — and the
// matching "consumer contract" note in romp-postal. Nothing else in the
// extension hard-codes the postal format.

import * as fs from "fs";
import * as path from "path";
import type { ChatEvent } from "./transcript";

// messages.jsonl lives under $XDG_STATE_HOME/romp/timeline/ (TLDIR in romp-postal).
export const TIMELINE_REL = ["timeline", "messages.jsonl"];

// (1) The join marker — the single bit of inbox/push prose we rely on.
const MSG_ID_RE = /<!--\s*romp-msg-id:\s*([^\s>]+)\s*-->/g;

// (3) The MCP send tool. May be namespaced, e.g. mcp__romp-postal__send_message.
const SEND_TOOL_RE = /(?:^|__)send_message$/;

export interface PeerColor { bg: string; fg: string; }

// One "sent" record from the timeline log (the fields we render).
export interface PostalRecord {
  id: string;
  from: string;
  fromId: string;
  toId: string;
  body: string;
  t: number;        // epoch seconds
  park: boolean;
}

// Resolve a romp identity colour from the names registry, by session id or name.
export interface ColorResolvers {
  byId: (id: string) => PeerColor | null;
  byName: (name: string) => PeerColor | null;
}

export function extractMsgIds(text: string): string[] {
  if (!text) return [];
  const ids: string[] = [];
  MSG_ID_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = MSG_ID_RE.exec(text))) ids.push(m[1]);
  return ids;
}

export function isSendTool(name: string): boolean {
  return SEND_TOOL_RE.test(name || "");
}

// (2) Read + index the timeline log, cached by mtime (it's append-only, so a
// new delivery always bumps mtime). Keyed by message id; last "sent" wins.
let cache: { mtimeMs: number; map: Map<string, PostalRecord> } | null = null;

export function loadPostalIndex(stateDir: string): Map<string, PostalRecord> {
  const file = path.join(stateDir, ...TIMELINE_REL);
  let st: fs.Stats;
  try { st = fs.statSync(file); } catch { return cache?.map ?? new Map(); }
  if (cache && cache.mtimeMs === st.mtimeMs) return cache.map;
  const map = new Map<string, PostalRecord>();
  let raw = "";
  try { raw = fs.readFileSync(file, "utf8"); } catch { return cache?.map ?? new Map(); }
  for (const line of raw.split("\n")) {
    const s = line.trim();
    if (!s) continue;
    let o: any;
    try { o = JSON.parse(s); } catch { continue; }
    if (o && o.ev === "sent" && o.id) {
      map.set(o.id, {
        id: o.id,
        from: o.from ?? "?",
        fromId: o.from_id ?? "",
        toId: o.to_id ?? "",
        body: o.body ?? "",
        t: typeof o.t === "number" ? o.t : 0,
        park: !!o.park,
      });
    }
  }
  cache = { mtimeMs: st.mtimeMs, map };
  return map;
}

function postalIn(rec: PostalRecord | undefined, colors: ColorResolvers, ts?: string, uuid?: string): ChatEvent | null {
  if (!rec) return null; // not in the timeline log -> leave the raw delivery as-is
  return {
    kind: "postal",
    direction: "in",
    peer: rec.from || "?",
    color: rec.fromId ? colors.byId(rec.fromId) : null,
    body: rec.body,
    t: rec.t || undefined,
    park: rec.park,
    ts,
    uuid,
  };
}

function postalOut(ev: Extract<ChatEvent, { kind: "tool" }>, colors: ColorResolvers): ChatEvent | null {
  // describeTool() stringifies unknown-tool input as pretty JSON, so the
  // structured {to, body} round-trips back via JSON.parse.
  let args: any;
  try { args = JSON.parse(ev.input); } catch { return null; }
  if (!args || typeof args.to !== "string" || typeof args.body !== "string") return null;
  const parked = /parked/i.test(ev.output || "");
  return {
    kind: "postal",
    direction: "out",
    peer: args.to,
    color: colors.byName(args.to),
    body: args.body,
    status: ev.isError ? undefined : parked ? "parked" : "delivered",
    ts: ev.ts,
    uuid: ev.uuid,
  };
}

// Replace postal traffic in an event list with structured postal cards. Any
// event we can't fully resolve is passed through unchanged (never dropped).
export function hydratePostal(events: ChatEvent[], stateDir: string, colors: ColorResolvers): ChatEvent[] {
  const index = loadPostalIndex(stateDir);
  const out: ChatEvent[] = [];
  for (const ev of events) {
    if (ev.kind === "tool" && isSendTool(ev.name)) {
      const card = postalOut(ev, colors);
      if (card) { out.push(card); continue; }
    }
    // Incoming: drain/push arrive as user text; check_inbox as tool output.
    const text = ev.kind === "user" ? ev.md : ev.kind === "tool" ? ev.output : "";
    const ids = extractMsgIds(text);
    if (ids.length) {
      const cards = ids
        .map((id) => postalIn(index.get(id), colors, ev.ts, ev.uuid))
        .filter((c): c is ChatEvent => c !== null);
      // All-or-nothing per event: only swap when every message resolved, so a
      // partial timeline never half-renders a delivery.
      if (cards.length === ids.length) { out.push(...cards); continue; }
    }
    out.push(ev);
  }
  return out;
}
