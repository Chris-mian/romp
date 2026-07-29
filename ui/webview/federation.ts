// Federated dashboard — merge sessions from MANY kernels in the browser.
//
// Each attached kernel gets its own WebSocket. Messages from a remote kernel carry that kernel's own
// session ids (UUIDs); to keep them distinct in one merged dashboard we PREFIX every session id with the
// host on the way IN (`gpu1:‹uuid›`), and STRIP it + route to the owning connection on the way OUT. The
// panes (render.ts / feed.ts / fleet.ts) treat `host:‹uuid›` as an opaque id — they read it from a
// `data-id` and echo it back — so they need (almost) no changes; all the host-awareness lives here.
//
// This module is split into PURE functions (prefix / route / merge — fully unit-tested in
// multi-kernel-merge.test.ts) and a thin FederationManager that wires them to WebSockets + the DOM. The
// local kernel is just connection #0 with the empty-string host key, so its messages pass through
// unprefixed and the single-kernel path is byte-for-byte unchanged.

export const SEP = ":";
export const LOCAL = ""; // the local kernel's host key — no prefix, so the single-kernel path is untouched

/** `host:id` for a remote host; the bare id unchanged for the local host. */
export function prefixId(host: string, id: string): string {
  return host ? host + SEP + id : id;
}

/** The host a prefixed id belongs to, or "" (local) for a bare id. Session ids are UUIDs (no colon),
 *  so a colon unambiguously marks the host prefix. */
export function hostOf(id: string): string {
  if (typeof id !== "string") return "";
  const i = id.indexOf(SEP);
  return i > 0 ? id.slice(0, i) : "";
}

/** The bare session id with any `host:` prefix removed. */
export function bareId(id: string): string {
  if (typeof id !== "string") return id;
  const i = id.indexOf(SEP);
  return i > 0 ? id.slice(i + 1) : id;
}

// The shapes a kernel→browser message can carry a session id in. Kept generic (by field name, not by
// message type) so a new message type that reuses these field names is covered automatically:
const SCALAR_ID = ["id", "sid"]; //               a single session id
const ARRAY_ID = ["order", "names", "working", "awaiting"]; // an array of session ids
const OBJ_SID = ["asks", "items", "ledgers"]; //  an array of objects keyed by `.sid`
const OBJ_ID = ["tabs"]; //                       an array of objects keyed by `.id`

/** Return a COPY of an inbound message with every session-id field prefixed by `host`. The local host
 *  ("") is the identity transform, so local messages are untouched. Unknown fields pass through. */
export function prefixInbound(host: string, msg: any): any {
  if (!host || !msg || typeof msg !== "object" || Array.isArray(msg)) return msg;
  const out: any = { ...msg };
  for (const k of SCALAR_ID)
    if (typeof out[k] === "string") out[k] = prefixId(host, out[k]);
  for (const k of ARRAY_ID)
    if (Array.isArray(out[k])) out[k] = out[k].map((x: any) => (typeof x === "string" ? prefixId(host, x) : x));
  for (const k of OBJ_SID)
    if (Array.isArray(out[k]))
      out[k] = out[k].map((o: any) => _prefixIdBearing(host, o, "sid"));
  for (const k of OBJ_ID)
    if (Array.isArray(out[k]))
      out[k] = out[k].map((o: any) => _prefixIdBearing(host, o, "id"));
  // A `name` is DISPLAY text, not an address — prefix it too (on session-bearing messages) so a remote
  // session reads "host:name" everywhere it surfaces (chat tab + header), never colliding visually with a
  // local same-named one. Guarded by a co-present id/sid so we never touch an unrelated `name` field.
  if (typeof out.name === "string" && (typeof out.id === "string" || typeof out.sid === "string"))
    out.name = prefixId(host, out.name);
  // The + picker's session list (the user 2026-07-29: switching Host should list THAT machine's sessions,
  // so a remote one can be reopened or revived from here). Its rows are keyed `id`, not `sid`, so the
  // generic passes above leave them alone — and prefixing them is what makes a click route back: the row
  // posts openSession with the id, and routeOutbound sends it to the host in the prefix. Stamped with
  // the source host too, so the picker can drop a late reply for a host it is no longer showing.
  if (out.type === "sessionList" && Array.isArray(out.items)) {
    out.items = out.items.map((it: any) => (it && typeof it === "object" && typeof it.id === "string"
      ? { ...it, id: prefixId(host, it.id),
          name: typeof it.name === "string" ? prefixId(host, it.name) : it.name }
      : it));
    out.host = host;
  }
  // timeline payloads: the lanes skeleton nests everything under `data`; the bars detail is top-level.
  if (out.type === "data" && out.data && typeof out.data === "object") out.data = prefixTimelineData(host, out.data);
  else if (out.type === "bars") return { ...out, ..._prefixTimelineDetail(host, out) };
  if (out.activeChat && typeof out.activeChat === "object") out.activeChat = _prefixActiveChat(host, out.activeChat);
  return out;
}

/** Prefix an object's id field (`sid`/`id`) AND its display `name`, returning a copy (or the object
 *  unchanged if it isn't a prefixable object). */
function _prefixIdBearing(host: string, o: any, idKey: string): any {
  if (!o || typeof o !== "object" || typeof o[idKey] !== "string") return o;
  const out: any = { ...o, [idKey]: prefixId(host, o[idKey]) };
  if (typeof out.name === "string") out.name = prefixId(host, out.name);
  // A feed card's delegation origin (asks[].origin): peerHost empty means the SENDER is local to the
  // card's own kernel — attribute it to that host, and prefix peerSid so the click routes there. A
  // set peerHost means the sender lives on some OTHER host (that kernel recorded which); keep it,
  // and keep peerSid bare — the viewer may be that very host, where the bare uuid opens directly.
  if (out.origin && typeof out.origin === "object" && typeof out.origin.peerSid === "string" && !out.origin.peerHost)
    out.origin = { ...out.origin, peerHost: host, peerSid: prefixId(host, out.origin.peerSid) };
  return out;
}

// ── timeline payloads ────────────────────────────────────────────────────────────────────────────
// The timeline rides the same WS as everything else (app=timeline): a {type:"data", data:{…}} lanes
// skeleton and a heavy {type:"bars"} detail message. Both are per-sid keyed, so a remote host's copy
// needs the same prefixing as the flat messages above — but nested.

/** Prefix the per-sid DETAIL shared by {type:"data"}.data and {type:"bars"}: `turns` (an object keyed
 *  by sid whose bars carry `tid` = their sid), postal `messages` (fromId/toId), and the `judging` +
 *  Event uuids (bar id/promptId/workId, hover ids) are globally unique already
 *  and stay bare. */
function _prefixTimelineDetail(host: string, d: any): any {
  const out: any = { ...d };
  if (out.turns && typeof out.turns === "object" && !Array.isArray(out.turns)) {
    const turns: any = {};
    for (const [sid, bars] of Object.entries(out.turns))
      turns[prefixId(host, sid)] = Array.isArray(bars)
        ? bars.map((b: any) => (b && typeof b === "object" && typeof b.tid === "string" ? { ...b, tid: prefixId(host, b.tid) } : b))
        : bars;
    out.turns = turns;
  }
  if (Array.isArray(out.messages))
    out.messages = out.messages.map((m: any) => {
      if (!m || typeof m !== "object") return m;
      const c: any = { ...m };
      if (typeof c.fromId === "string") c.fromId = prefixId(host, c.fromId);
      if (typeof c.toId === "string") c.toId = prefixId(host, c.toId);
      return c;
    });
  for (const k of ["judging"])
    if (Array.isArray(out[k]))
      out[k] = out[k].map((e: any) => (e && typeof e === "object" && typeof e.sid === "string" ? { ...e, sid: prefixId(host, e.sid) } : e));
  return out;
}

/** The active-chat cue: `tid` is the chat's transcript sid (matched against bars' prefixed `tid`) and
 *  `name` its display name — prefix both so a remote kernel's cue lights its own (prefixed) lane. */
function _prefixActiveChat(host: string, ac: any): any {
  if (!ac || typeof ac !== "object") return ac;
  const out: any = { ...ac };
  if (typeof out.tid === "string") out.tid = prefixId(host, out.tid);
  if (typeof out.name === "string") out.name = prefixId(host, out.name);
  return out;
}

/** Prefix a full timeline lanes payload ({type:"data"}.data): sessions (id + display name) plus the
 *  shared detail fields. */
export function prefixTimelineData(host: string, d: any): any {
  if (!host || !d || typeof d !== "object") return d;
  const out = _prefixTimelineDetail(host, d);
  if (Array.isArray(out.sessions)) out.sessions = out.sessions.map((s: any) => _prefixIdBearing(host, s, "id"));
  if (out.activeChat) out.activeChat = _prefixActiveChat(host, out.activeChat);
  return out;
}

export interface Route {
  host: string; // "" = the local kernel
  msg: any; // a copy with this host's ids stripped back to bare
}

/** Decide which kernel(s) an OUTBOUND (browser→kernel) message goes to, stripping the host prefix off the
 *  ids for that kernel. Most messages target one session → one route. A reorder (an `order[]` that can mix
 *  hosts after a cross-host drag) fans out to one route PER host, each carrying only its own sids in their
 *  relative order. A message with no session id (a global pref like setColormap, or `ready`) → local.
 *
 *  `knownHosts` (the manager passes its attached set) enables two extra routings that need to know which
 *  hosts exist: NAME-addressed messages (the timeline's compact/sendCommand target a session by display
 *  name, which inbound prefixing made `host:name`) route to a KNOWN host only — a local name that happens
 *  to contain ":" must never misroute — and a hover CLEAR (`timelineHover {off}` carries no sid) fans out
 *  to every kernel so a remote highlight can't stick. */
export function routeOutbound(msg: any, knownHosts?: ReadonlySet<string>): Route[] {
  if (!msg || typeof msg !== "object") return [{ host: LOCAL, msg }];

  // an explicit `host` field wins (the + modal's createSession picks the target kernel): route there with
  // the field stripped — the kernel's handlers are host-blind.
  if (typeof msg.host === "string") {
    const { host, ...rest } = msg;
    return [{ host: host || LOCAL, msg: rest }];
  }

  // order[] (reorderTabs / the timeline's writeOrder): split across the hosts it touches.
  if (Array.isArray(msg.order) && msg.order.some((x: any) => typeof x === "string")) {
    const byHost = new Map<string, string[]>();
    for (const x of msg.order) {
      if (typeof x !== "string") continue;
      const h = hostOf(x);
      if (!byHost.has(h)) byHost.set(h, []);
      byHost.get(h)!.push(bareId(x));
    }
    return [...byHost.entries()].map(([host, order]) => ({ host, msg: { ...msg, order } }));
  }

  // a hover CLEAR has no session id — broadcast so every kernel drops its highlight.
  if (msg.type === "timelineHover" && msg.off) return [LOCAL, ...(knownHosts || [])].map((h) => ({ host: h, msg }));

  // openFolder ALWAYS stays LOCAL, `id` UNSTRIPPED (the user 2026-07-03): unlike every other id-bearing
  // message, this one means "open a window on the machine the BROWSER is running on" — routing it to a
  // remote kernel would open a folder/terminal on that headless machine's own (unwatched) screen. The
  // local kernel needs the host prefix INTACT to know which remote machine to SSH into instead of treating
  // the path as local (see bin/romp-kernel's openFolder handler + _split_host_id).
  if (msg.type === "openFolder") return [{ host: LOCAL, msg }];

  // a scalar session id picks the owning host.
  let host = LOCAL;
  for (const k of SCALAR_ID) {
    if (typeof msg[k] === "string") {
      const h = hostOf(msg[k]);
      if (h) { host = h; break; }
    }
  }
  if (host !== LOCAL) {
    const out: any = { ...msg };
    for (const k of SCALAR_ID) if (typeof out[k] === "string") out[k] = bareId(out[k]);
    return [{ host, msg: out }];
  }

  // name-addressed (compact/sendCommand `name`, deepLink `session`): a remote lane's display name is
  // host-prefixed — route to that KNOWN host with the prefix stripped. Only the field that decided the
  // route is stripped (e.g. renameSession's `name` is the user's new title, untouched — it routed by id).
  if (knownHosts && knownHosts.size) {
    for (const k of ["name", "session"]) {
      if (typeof msg[k] === "string") {
        const h = hostOf(msg[k]);
        if (h && knownHosts.has(h)) return [{ host: h, msg: { ...msg, [k]: bareId(msg[k]) } }];
      }
    }
  }
  return [{ host: LOCAL, msg }];
}

/** Merge per-host tab orders into ONE list for the merged strip: each host's order VERBATIM (the kernel is
 *  authoritative within a host — never re-sort across hosts), concatenated in `hostSeq` order (local first,
 *  then attach order). Values are already prefixed by prefixInbound. Deduped; non-strings dropped. */
export function mergeHostOrder(perHost: Record<string, readonly string[]>, hostSeq: readonly string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const h of hostSeq) {
    for (const id of perHost[h] || []) {
      if (typeof id === "string" && !seen.has(id)) {
        seen.add(id);
        out.push(id);
      }
    }
  }
  return out;
}

/** Merge per-host feed snapshots into ONE payload. The `feed` message is a WHOLE-feed snapshot that the
 *  pane wholesale-replaces its state from — so without merging, the local kernel's snapshot and each
 *  remote's snapshot (both pushed ~every 2s) alternate and clobber each other, and the feed visibly flips
 *  back and forth ("repeatedly reloading"). Concatenate the arrays (items/asks/working) in hostSeq order
 *  (local first); keep the scalar chrome fields (now, dismissedCount, flags) from the LOCAL host, since the
 *  dashboard's own controls are local-authoritative. Ids are already prefixed by prefixInbound. */
export function mergeHostFeeds(perHost: Record<string, any>, hostSeq: readonly string[]): any {
  const local = perHost[LOCAL] || {};
  const merged: any = { ...local, type: "feed", items: [], asks: [], working: [], awaiting: [], order: [] };
  // `ledgers` drives the FLEET pane (it rides the same feed message). Only include it once at least one host
  // has actually BUILT its ledgers — else the fleet's loader-gate (needs an array) would drop onto an empty
  // pane. Kept undefined until then so the loader holds, exactly like the single-kernel path.
  let anyLedgers = false;
  const ledgers: any[] = [];
  // dismissed/undo chrome spans hosts: the count SUMS and undo is possible when ANY kernel can undo —
  // clearing a remote card must light the local Undo button (the clear routed to that kernel).
  let dismissed = 0, anyDismissed = false, canUndo = false;
  for (const h of hostSeq) {
    const f = perHost[h];
    if (!f) continue;
    if (Array.isArray(f.items)) merged.items.push(...f.items);
    if (Array.isArray(f.asks)) merged.asks.push(...f.asks);
    if (Array.isArray(f.working)) merged.working.push(...f.working);
    if (Array.isArray(f.awaiting)) merged.awaiting.push(...f.awaiting);   // straw awaiting dots ride like working
    if (Array.isArray(f.order)) merged.order.push(...f.order);   // grouped-mode session rank: local first, ids pre-prefixed
    if (Array.isArray(f.ledgers)) { anyLedgers = true; ledgers.push(...f.ledgers); }
    if (typeof f.dismissedCount === "number") { anyDismissed = true; dismissed += f.dismissedCount; }
    if (f.canUndoClear) canUndo = true;
  }
  if (anyLedgers) merged.ledgers = ledgers;
  else delete merged.ledgers;
  if (anyDismissed) merged.dismissedCount = dismissed;
  if ("canUndoClear" in merged || canUndo) merged.canUndoClear = canUndo;
  return merged;
}

/** Stitch CROSS-HOST postal connectors onto merged lanes. Each kernel emits a connector when at least
 *  one end is its own lane; the FOREIGN end's sid is bare in its log (a kernel knows nothing of host
 *  prefixes) and inbound prefixing blindly prefixed it with the EMITTING host — so on the merged board
 *  it matches no lane. Re-point any endpoint that isn't a lane id at the lane whose BARE sid matches
 *  (uuids — no cross-host collisions), fill a missing display name from that lane, then dedupe the two
 *  kernels' copies of the same message (by id) — preferring the one that knows the real delivery time
 *  (hasExec: the recipient's kernel binds exec to its own transcript; the sender's can't). */
export function stitchMessages(messages: any[], sessions: readonly any[]): any[] {
  if (!messages.length) return messages;
  const laneIds = new Set(sessions.map((s: any) => s && s.id));
  const byBare = new Map(sessions.filter((s: any) => s && typeof s.id === "string").map((s: any) => [bareId(s.id), s]));
  const best = new Map<string, any>();
  const out: any[] = [];
  for (const m of messages) {
    if (!m || typeof m !== "object") { out.push(m); continue; }
    const c: any = { ...m };
    for (const [idKey, nameKey] of [["fromId", "from"], ["toId", "to"]] as const) {
      const v = c[idKey];
      if (typeof v !== "string" || laneIds.has(v)) continue;
      const lane = byBare.get(bareId(v));
      if (lane) {
        c[idKey] = lane.id;
        if (!c[nameKey]) c[nameKey] = lane.name; // the emitting kernel never knew the foreign name
      }
    }
    const key = typeof c.id === "string" ? c.id : null;
    if (!key) { out.push(c); continue; }
    const prev = best.get(key);
    if (!prev) { best.set(key, c); out.push(c); continue; }
    if (c.hasExec && !prev.hasExec) Object.assign(prev, c); // upgrade in place — keeps sent-order
  }
  return out;
}

/** Merge per-host timeline lanes payloads ({type:"data"}.data, already prefixed) into ONE. Sessions
 *  concatenate in hostSeq order (local lanes first, each remote host's group below — the view draws a
 *  half-row gap at each host boundary via the `host` field stamped here); `turns` (keyed by prefixed sid)
 *  union; the marks arrays concatenate, with cross-host connectors stitched onto the merged lanes.
 *  Scalar chrome (now/usage/focus/hover/cmapGrad…) stays LOCAL — the browser's own kernel is the
 *  clock + chrome authority, same as the feed merge. */
export function mergeHostTimelines(perHost: Record<string, any>, hostSeq: readonly string[]): any {
  const local = perHost[LOCAL] || {};
  const merged: any = { ...local, sessions: [], turns: {}, messages: [], judging: [] };
  for (const h of hostSeq) {
    const d = perHost[h];
    if (!d) continue;
    if (Array.isArray(d.sessions)) merged.sessions.push(...d.sessions.map((s: any) => ({ ...s, host: h })));
    if (d.turns && typeof d.turns === "object") Object.assign(merged.turns, d.turns);
    for (const k of ["messages", "judging"]) if (Array.isArray(d[k])) merged[k].push(...d[k]);
  }
  merged.messages = stitchMessages(merged.messages, merged.sessions);
  return merged;
}

/** Merge per-host {type:"bars"} detail messages (already prefixed) into ONE. The panel's applyBars
 *  wholesale-replaces its turns/marks, so per-host bars MUST be merged here or each host's push would
 *  clobber the others' bars (the same clobber the feed had). `now` stays LOCAL (clock authority).
 *  `sessions` (the merged lane list, from mergeHostTimelines) enables the cross-host connector stitch —
 *  the bars message itself carries no lanes. */
export function mergeHostBars(perHost: Record<string, any>, hostSeq: readonly string[],
                              sessions: readonly any[] = []): any {
  const local = perHost[LOCAL] || {};
  const merged: any = { ...local, type: "bars", turns: {}, messages: [], judging: [], warming: false };
  for (const h of hostSeq) {
    const b = perHost[h];
    if (!b) continue;
    if (b.turns && typeof b.turns === "object") Object.assign(merged.turns, b.turns);
    for (const k of ["messages", "judging", "nudges"]) if (Array.isArray(b[k])) merged[k].push(...b[k]);
    if (b.warming) merged.warming = true;   // still warming if ANY host's build is the cold partial (keep the loader)
  }
  merged.messages = stitchMessages(merged.messages, sessions);
  return merged;
}

// ── the wiring: WebSockets per kernel + the attach UI ────────────────────────────────────────────
// Thin glue over the pure functions above. The LOCAL kernel stays the shim's existing single WS — this
// manager only ADDS connections to attached remote kernels, so with no remotes attached the dashboard is
// byte-for-byte the single-kernel path. The shim calls window.__rompFed.inbound("", msg) for local frames
// and window.__rompFed.outbound(m) for sends (both no-ops when this module isn't loaded, e.g. the timeline
// pane), and exposes window.__rompLocalSend + window.__rompApp.

interface Conn {
  host: string;
  ws: WebSocket | null;
  url: string;
  closed: boolean;
  live: boolean; // kernel reports this tunnel "up" — the only state in which its port is dialed
}

export class FederationManager {
  app = "chat";
  private conns = new Map<string, Conn>();
  private perHostOrder: Record<string, string[]> = {};
  private perHostTabs: Record<string, any[]> = {};
  private perHostSids: Record<string, Set<string>> = {};
  private perHostFeed: Record<string, any> = {}; // last feed snapshot per host — merged so they don't clobber
  private perHostTl: Record<string, any> = {}; //   last timeline lanes payload ({type:"data"}.data) per host
  private perHostTlBars: Record<string, any> = {}; // last timeline {type:"bars"} detail per host
  private hostSeq: string[] = [LOCAL]; // local first, then attach order — fixes the group order in the strip
  private downHosts = new Set<string>(); // attached, but its tunnel isn't up: what's on screen is a memory
  private lastSeen: Record<string, number> = {}; // host -> epoch secs of its last `up` poll

  start(): void {
    const w = window as any;
    this.app = w.__rompApp || "chat";
    w.__rompFed = {
      inbound: (h: string, m: any) => this.inbound(h, m),
      outbound: (m: any) => this.outbound(m),
      hosts: () => this.hostSeq.filter((h) => h !== LOCAL), // attached hosts (the + modal's host picker)
      // Hosts that are attached but NOT reachable right now. Their sessions stay on screen — dropping
      // them would lose the thread — but every surface that shows one has to say the link is down, or
      // you are reading a transcript that stopped updating with nothing telling you (the user
      // 2026-07-29). `lastSeen` dates what is on screen.
      down: () => [...this.downHosts],
      lastSeen: (h: string) => this.lastSeen[h] || 0,
    };
    this.poll();
    setInterval(() => this.poll(), 4000); // converge on attach/detach made from the shell's network panel
  }

  // kernel → browser: prefix this host's ids, merge tab orders, hand the rest to the panes.
  inbound(host: string, msg: any): void {
    const m = prefixInbound(host, msg);
    if (m && m.type === "session" && typeof m.id === "string") {
      (this.perHostSids[host] ||= new Set()).add(m.id);
    }
    if (m && m.type === "tabOrder") {
      this.perHostOrder[host] = Array.isArray(m.order) ? m.order.filter((x: any) => typeof x === "string") : [];
      this.perHostTabs[host] = Array.isArray(m.tabs) ? m.tabs : [];
      this.ensureHost(host);
      this.emitMergedOrder();
      return;
    }
    if (m && m.type === "feed") {
      this.perHostFeed[host] = m;
      this.ensureHost(host);
      this.emitMergedFeed();
      return;
    }
    // timeline snapshots replace the panel's state wholesale (update/applyBars) — merge per host like the feed.
    if (m && m.type === "data" && m.data && typeof m.data === "object") {
      this.perHostTl[host] = m.data;
      this.ensureHost(host);
      this.emitMergedTimeline(false);
      return;
    }
    if (m && m.type === "bars") {
      this.perHostTlBars[host] = m;
      this.ensureHost(host);
      this.emitMergedTimeline(true);
      return;
    }
    window.dispatchEvent(new MessageEvent("message", { data: m }));
  }

  private emitMergedFeed(): void {
    window.dispatchEvent(new MessageEvent("message", { data: mergeHostFeeds(this.perHostFeed, this.hostSeq) }));
  }

  private emitMergedTimeline(bars: boolean): void {
    // HOLD until the LOCAL lanes snapshot exists. The merges take `now` (the clock authority) from the
    // local payload, so a remote host winning the connect race would emit now:undefined — which the
    // panel's fitWindow turned into a permanently-NaN window (every bar/axis x = NaN; the "stub lane
    // lines, no bars" bug, 2026-07-15). The local kernel pushes on connect, so the hold is momentary,
    // and the local arrival itself emits (event-based, no timer).
    if (!(LOCAL in this.perHostTl)) return;
    const data = bars
      // the bars message carries no lanes — hand the merged lane list in for the connector stitch
      ? mergeHostBars(this.perHostTlBars, this.hostSeq, mergeHostTimelines(this.perHostTl, this.hostSeq).sessions)
      : { type: "data", data: mergeHostTimelines(this.perHostTl, this.hostSeq) };
    window.dispatchEvent(new MessageEvent("message", { data }));
  }

  private emitMergedOrder(): void {
    const order = mergeHostOrder(this.perHostOrder, this.hostSeq);
    const tabs = this.hostSeq.flatMap((h) => this.perHostTabs[h] || []);
    window.dispatchEvent(new MessageEvent("message", { data: { type: "tabOrder", order, tabs } }));
  }

  private lastClearHost = LOCAL; // where the most recent askClear routed — undoClear follows it

  // browser → kernel: route each message to the owning kernel, prefix stripped.
  outbound(m: any): void {
    // undoClear undoes the LAST clear, which may have gone to a remote kernel — follow it there.
    // (The kernel keeps its own cleared.jsonl; only the kernel that took the clear can undo it.)
    if (m && m.type === "undoClear" && this.lastClearHost !== LOCAL) {
      const c = this.conns.get(this.lastClearHost);
      if (c && c.ws && c.ws.readyState === 1) c.ws.send(JSON.stringify(m));
      else this.dropWarn(this.lastClearHost, m);
      this.lastClearHost = LOCAL;
      return;
    }
    const routes = routeOutbound(m, new Set(this.hostSeq.filter((h) => h !== LOCAL)));
    if (m && m.type === "askClear") this.lastClearHost = routes[0] ? routes[0].host : LOCAL;
    for (const r of routes) {
      if (r.host === LOCAL) {
        const s = (window as any).__rompLocalSend;
        if (typeof s === "function") s(r.msg);
      } else {
        const c = this.conns.get(r.host);
        if (c && c.ws && c.ws.readyState === 1) c.ws.send(JSON.stringify(r.msg));
        else this.dropWarn(r.host, r.msg);
      }
    }
  }

  // A route to a host whose socket isn't open would otherwise VANISH — creating a session on an
  // unreachable remote gave no feedback at all (the user 2026-07-10). Surface the drop as a local
  // `warn` (render.ts toasts it), naming the host and the action so the user knows what didn't land.
  private dropWarn(host: string, msg: any): void {
    window.dispatchEvent(new MessageEvent("message", { data: { type: "warn",
      text: `${host} is unreachable (its kernel isn't answering) — “${(msg && msg.type) || "action"}” was not delivered` } }));
  }

  private ensureHost(h: string): void {
    if (!this.hostSeq.includes(h)) this.hostSeq.push(h);
  }

  private async poll(): Promise<void> {
    let tunnels: any[] = [];
    try {
      const r = await fetch("/tunnels", { cache: "no-store" });
      tunnels = (await r.json()).tunnels || [];
    } catch (e) {
      return;
    }
    const want = new Map<string, any>(tunnels.filter((t) => t.token && t.localPort).map((t) => [t.host, t]));
    for (const [host, t] of want) if (!this.conns.has(host)) this.openRemote(host, t.localPort, t.token, t.status === "up");
    for (const host of [...this.conns.keys()]) if (!want.has(host)) this.closeRemote(host);
    // The kernel's tunnel state gates dialing: it health-checks its own ssh tunnels, so "up" is
    // authoritative for whether anything listens on the local port at all. Blind 2s retries against
    // a dead tunnel port feed the browser's per-host WebSocket failure backoff (Firefox delays
    // re-admission after failures), which then holds the LOCAL panes' reconnects hostage after a
    // kernel restart — the stuck "Disconnected — reconnecting…" banner. A down tunnel is not
    // dialed at all; this poll re-dials within one cycle of the kernel reporting it up.
    for (const [host, t] of want) {
      const c = this.conns.get(host);
      if (!c) continue;
      c.live = t.status === "up";
      if (c.live && (!c.ws || c.ws.readyState === 3)) this.connect(c);
    }
    // Publish reachability for the panes. The kernel's own tunnel health is the authority (it dials and
    // health-checks the ssh), and it keeps retrying, so this flips back on its own when the host returns.
    const down = new Set([...want.keys()].filter((h) => want.get(h).status !== "up"));
    // lastOk comes from the KERNEL's row (when it last had that host answering end to end), so the
    // "last seen" a pane shows survives a page reload and doesn't restart with the browser.
    for (const [host, t] of want) if (typeof t.lastOk === "number" && t.lastOk) this.lastSeen[host] = t.lastOk;
    const changed = down.size !== this.downHosts.size || [...down].some((h) => !this.downHosts.has(h));
    this.downHosts = down;
    if (changed) window.dispatchEvent(new Event("romp-hosts"));   // panes repaint their disconnected marks
  }

  private openRemote(host: string, port: number, token: string, live: boolean): void {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const url = `${proto}127.0.0.1:${port}/ws?app=${encodeURIComponent(this.app)}&token=${encodeURIComponent(token)}`;
    const conn: Conn = { host, ws: null, url, closed: false, live };
    this.conns.set(host, conn);
    this.ensureHost(host);
    this.connect(conn);
  }

  private connect(conn: Conn): void {
    if (conn.closed || !conn.live) return;
    if (conn.ws && (conn.ws.readyState === 0 || conn.ws.readyState === 1)) return; // already connecting/open
    let ws: WebSocket;
    try {
      ws = new WebSocket(conn.url);
    } catch (e) {
      setTimeout(() => this.connect(conn), 2000);
      return;
    }
    conn.ws = ws;
    ws.onmessage = (ev: MessageEvent) => {
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (msg && msg.type === "ka") return;
      this.inbound(conn.host, msg);
    };
    ws.onclose = () => {
      if (!conn.closed) setTimeout(() => this.connect(conn), 2000); // reconnect a dropped remote
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch (e) {}
    };
  }

  private closeRemote(host: string): void {
    const c = this.conns.get(host);
    if (!c) return;
    c.closed = true;
    try {
      c.ws && c.ws.close();
    } catch (e) {}
    this.conns.delete(host);
    this.hostSeq = this.hostSeq.filter((h) => h !== host);
    // drop that host's tabs from the panes (else they linger stale), then re-emit the merged order.
    for (const sid of this.perHostSids[host] || []) {
      window.dispatchEvent(new MessageEvent("message", { data: { type: "closed", id: sid } }));
    }
    delete this.perHostOrder[host];
    delete this.perHostTabs[host];
    delete this.perHostSids[host];
    delete this.perHostFeed[host];
    const hadTl = host in this.perHostTl || host in this.perHostTlBars;
    delete this.perHostTl[host];
    delete this.perHostTlBars[host];
    this.emitMergedOrder();
    this.emitMergedFeed(); // drop the detached host's feed items so they don't linger
    if (hadTl) { this.emitMergedTimeline(false); this.emitMergedTimeline(true); } // …and its lanes/bars
  }
}

// Bootstrap on the browser only (the node test imports the pure functions above; this never runs there).
if (typeof window !== "undefined" && typeof document !== "undefined") {
  new FederationManager().start();
}
