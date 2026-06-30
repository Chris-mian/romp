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
      out[k] = out[k].map((o: any) => (o && typeof o === "object" && typeof o.sid === "string" ? { ...o, sid: prefixId(host, o.sid) } : o));
  for (const k of OBJ_ID)
    if (Array.isArray(out[k]))
      out[k] = out[k].map((o: any) => (o && typeof o === "object" && typeof o.id === "string" ? { ...o, id: prefixId(host, o.id) } : o));
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
