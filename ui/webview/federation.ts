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
const ARRAY_ID = ["order", "names", "working"]; // an array of session ids
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
  return out;
}

/** Prefix an object's id field (`sid`/`id`) AND its display `name`, returning a copy (or the object
 *  unchanged if it isn't a prefixable object). */
function _prefixIdBearing(host: string, o: any, idKey: string): any {
  if (!o || typeof o !== "object" || typeof o[idKey] !== "string") return o;
  const out: any = { ...o, [idKey]: prefixId(host, o[idKey]) };
  if (typeof out.name === "string") out.name = prefixId(host, out.name);
  return out;
}

export interface Route {
  host: string; // "" = the local kernel
  msg: any; // a copy with this host's ids stripped back to bare
}

/** Decide which kernel(s) an OUTBOUND (browser→kernel) message goes to, stripping the host prefix off the
 *  ids for that kernel. Most messages target one session → one route. A reorder (an `order[]` that can mix
 *  hosts after a cross-host drag) fans out to one route PER host, each carrying only its own sids in their
 *  relative order. A message with no session id (a global pref like setColormap, or `ready`) → local. */
export function routeOutbound(msg: any): Route[] {
  if (!msg || typeof msg !== "object") return [{ host: LOCAL, msg }];

  // order[] (reorderTabs): split across the hosts it touches.
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

  // a scalar session id picks the owning host.
  let host = LOCAL;
  for (const k of SCALAR_ID) {
    if (typeof msg[k] === "string") {
      const h = hostOf(msg[k]);
      if (h) { host = h; break; }
    }
  }
  if (host === LOCAL) return [{ host: LOCAL, msg }];
  const out: any = { ...msg };
  for (const k of SCALAR_ID) if (typeof out[k] === "string") out[k] = bareId(out[k]);
  return [{ host, msg: out }];
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
  const merged: any = { ...local, type: "feed", items: [], asks: [], working: [] };
  // `ledgers` drives the FLEET pane (it rides the same feed message). Only include it once at least one host
  // has actually BUILT its ledgers — else the fleet's loader-gate (needs an array) would drop onto an empty
  // pane. Kept undefined until then so the loader holds, exactly like the single-kernel path.
  let anyLedgers = false;
  const ledgers: any[] = [];
  for (const h of hostSeq) {
    const f = perHost[h];
    if (!f) continue;
    if (Array.isArray(f.items)) merged.items.push(...f.items);
    if (Array.isArray(f.asks)) merged.asks.push(...f.asks);
    if (Array.isArray(f.working)) merged.working.push(...f.working);
    if (Array.isArray(f.ledgers)) { anyLedgers = true; ledgers.push(...f.ledgers); }
  }
  if (anyLedgers) merged.ledgers = ledgers;
  else delete merged.ledgers;
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
}

export class FederationManager {
  app = "chat";
  private conns = new Map<string, Conn>();
  private perHostOrder: Record<string, string[]> = {};
  private perHostTabs: Record<string, any[]> = {};
  private perHostSids: Record<string, Set<string>> = {};
  private perHostFeed: Record<string, any> = {}; // last feed snapshot per host — merged so they don't clobber
  private hostSeq: string[] = [LOCAL]; // local first, then attach order — fixes the group order in the strip

  start(): void {
    const w = window as any;
    this.app = w.__rompApp || "chat";
    w.__rompFed = { inbound: (h: string, m: any) => this.inbound(h, m), outbound: (m: any) => this.outbound(m) };
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
    window.dispatchEvent(new MessageEvent("message", { data: m }));
  }

  private emitMergedFeed(): void {
    window.dispatchEvent(new MessageEvent("message", { data: mergeHostFeeds(this.perHostFeed, this.hostSeq) }));
  }

  private emitMergedOrder(): void {
    const order = mergeHostOrder(this.perHostOrder, this.hostSeq);
    const tabs = this.hostSeq.flatMap((h) => this.perHostTabs[h] || []);
    window.dispatchEvent(new MessageEvent("message", { data: { type: "tabOrder", order, tabs } }));
  }

  // browser → kernel: route each message to the owning kernel, prefix stripped.
  outbound(m: any): void {
    for (const r of routeOutbound(m)) {
      if (r.host === LOCAL) {
        const s = (window as any).__rompLocalSend;
        if (typeof s === "function") s(r.msg);
      } else {
        const c = this.conns.get(r.host);
        if (c && c.ws && c.ws.readyState === 1) c.ws.send(JSON.stringify(r.msg));
      }
    }
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
    for (const [host, t] of want) if (!this.conns.has(host)) this.openRemote(host, t.localPort, t.token);
    for (const host of [...this.conns.keys()]) if (!want.has(host)) this.closeRemote(host);
  }

  private openRemote(host: string, port: number, token: string): void {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const url = `${proto}127.0.0.1:${port}/ws?app=${encodeURIComponent(this.app)}&token=${encodeURIComponent(token)}`;
    const conn: Conn = { host, ws: null, url, closed: false };
    this.conns.set(host, conn);
    this.ensureHost(host);
    this.connect(conn);
  }

  private connect(conn: Conn): void {
    if (conn.closed) return;
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
    this.emitMergedOrder();
    this.emitMergedFeed(); // drop the detached host's feed items so they don't linger
  }
}

// Bootstrap on the browser only (the node test imports the pure functions above; this never runs there).
if (typeof window !== "undefined" && typeof document !== "undefined") {
  new FederationManager().start();
}
