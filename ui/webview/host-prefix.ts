// A federated (remote) session surfaces everywhere as "host:name" — federation.js prefixes BOTH the
// display name and the sid with "host:" as messages arrive, and a LOCAL sid is a bare uuid that never
// contains a colon. So the sid is the designed marker: when it carries a host prefix and the name
// starts with the same prefix, the "host:" part is METADATA, not part of the name — and it renders as
// such (quiet gray, never bold, italic, a step smaller) instead of wearing the session's identity
// color at full weight (the user 2026-07-11). One helper + one .host-prefix class for every surface.
export function hostPrefix(name: string | null | undefined, sid: string | null | undefined): { host: string; rest: string } | null {
  if (!sid || !name) return null;
  const i = sid.indexOf(":");
  if (i <= 0) return null;
  const pre = sid.slice(0, i + 1);            // "host:" — exactly what federation prepended
  if (!name.startsWith(pre) || name.length <= pre.length) return null;
  return { host: pre, rest: name.slice(pre.length) };
}

/** Child nodes for a session-name element: [<span.host-prefix>host:</span>, "name"] for a remote
 *  session, or just the plain text for a local one. Use with `elm.replaceChildren(...)`. */
export function hostNameNodes(name: string, sid: string | null | undefined): Node[] {
  const p = hostPrefix(name, sid);
  if (!p) return [document.createTextNode(name)];
  const h = document.createElement("span");
  h.className = "host-prefix";
  h.textContent = p.host;
  return [h, document.createTextNode(p.rest)];
}

/** Same rendering when the host rides its OWN field instead of a sid prefix — the feed card's
 *  "↪ from" chip, whose peerSid stays a bare uuid (the sender may live on a third host neither
 *  the viewer nor the card's kernel can address). No host → plain text, identical to a local name. */
export function hostPartsNodes(host: string | null | undefined, name: string): Node[] {
  if (!host) return [document.createTextNode(name)];
  const h = document.createElement("span");
  h.className = "host-prefix";
  h.textContent = host + ":";
  return [h, document.createTextNode(name)];
}
