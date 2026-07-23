// Bridging the feed's TWO key namespaces, in one place a test can execute.
//
// The feed's DOM cards are keyed with a render-local namespace so a single reconcile map can hold every
// card kind at once: "a:<goal itemId>" for an ask card, "g:<turnId>" for a turn group, "s:<col>:<sid>"
// for a grouped-mode session header (see reconcileCol).
//
// The HOST speaks the DOMAIN's identity instead. `_cards_for_segments` (kernel.py) answers "which cards
// cover these segments?" with bare goal node ids, because that is what the goal store holds.
//
// Cross-pane hover compares the two. It used to compare them RAW, so "a:<sid>:g227" was tested against
// "<sid>:g227" and never matched: hovering a timeline bar or a chat rail dot resolved the right cards
// server-side, shipped them to the feed, and lit nothing (the user 2026-07-23, who saw the highlight flow
// one way only). Both reverse directions were fully built and wired; this mismatch was the whole failure.
//
// The fix belongs on the CLIENT: the namespace prefixes are a rendering detail the kernel should not have
// to know, and the goal-node id is the real shared identity. Matching stays exact after the prefix — no
// substring or startsWith matching, which would let one goal's id light a different card.

const NS = /^(?:a:|g:|s:)/;

/** True when a card carrying `domKey` is one of the host-named `keys`. Accepts a host that already speaks
 *  DOM keys (so a future sender needs no change here) and one that speaks bare domain ids. */
export function extHoverMatches(domKey: string | null | undefined, keys: Set<string>): boolean {
  if (!domKey || !keys || !keys.size) return false;
  if (keys.has(domKey)) return true;
  const bare = domKey.replace(NS, "");
  return bare !== domKey && keys.has(bare);
}

/** The host-named keys a DOM key can satisfy — the same bridge, for callers that need to look up rather
 *  than test (e.g. finding the card to scroll to). Ordered most-specific first. */
export function cardKeyAliases(domKey: string): string[] {
  const bare = domKey.replace(NS, "");
  return bare !== domKey ? [domKey, bare] : [domKey];
}
