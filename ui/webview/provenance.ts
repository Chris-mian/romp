// Card-age provenance (the user 2026-07-27): the card header's "Nm ago" stamps the card's NEWEST
// event — a completed card's age is when it was marked done — which hides where the thread CAME from.
// Hovering the stamp now tells the story: when the goal was started, each sub-item with the time it
// landed (or was asked), the root's own verdict events when shipped, and what the visible stamp itself
// marks. Rendered as a native `title` tooltip: zero extra DOM, click-safe across re-renders.
//
// Pure assembly, executed directly by provenance.test.ts. The wording/format helpers stay in feed.ts
// (relAge / clockHM / logPhrase are pinned there and used by a dozen other surfaces) and are injected,
// so this module owns only the story's structure: what appears, in what order, with which timestamp.

export interface LogRow { kind: string; src: string; why?: string | null; at?: number | null; evT?: number | null; }
export interface ProvNode {
  id: string; text: string; status: string; t: number; last: number; mt?: number;
  cleared?: boolean; log?: LogRow[] | null;
}
export interface ProvItem { itemId: string; t: number; column: string; tree: ProvNode[]; }
export interface ProvFmt {
  rel: (sec: number) => string;          // feed relAge
  clock: (t: number) => string;          // feed clockHM
  phrase: (r: LogRow) => string;         // feed logPhrase
}

const SUB_CAP = 8;                       // a huge tree stays a glanceable tooltip, not a scroll

function stamp(t: number, now: number, f: ProvFmt): string {
  return f.rel(now - t) + " · " + f.clock(t);
}

// the moment the card's thread began: its root node's mint time (earliest tree mint as a fallback for
// payloads without a root row; the card's own t as the last resort)
export function rootStart(it: ProvItem): number {
  const root = it.tree.find((n) => n.id === it.itemId);
  if (root?.t) return root.t;
  return it.tree.length ? Math.min(...it.tree.map((n) => n.t)) : it.t;
}

export function provenanceTitle(it: ProvItem, now: number, f: ProvFmt): string {
  const lines = ["started " + stamp(rootStart(it), now, f)];
  // the root's own verdict rows (asked you / you answered / …) — only shipped for non-done nodes
  const root = it.tree.find((n) => n.id === it.itemId);
  for (const r of root?.log ?? []) {
    const rt = r.at || r.evT || 0;
    if (rt) lines.push(f.phrase(r) + " " + stamp(rt, now, f));
  }
  // sub-items in mint order: a resolved sub is stamped when it RESOLVED (mt — where it landed), an
  // open one when it was minted (its resolution hasn't happened yet)
  const subs = it.tree.filter((n) => n.id !== it.itemId && !n.cleared);
  for (const n of subs.slice(0, SUB_CAP)) {
    const mark = n.status === "done" ? "✓" : n.status === "question" ? "⏸" : "·";
    const at = n.status === "open" ? n.t : (n.mt || n.last || n.t);
    const txt = n.text.length > 48 ? n.text.slice(0, 47) + "…" : n.text;
    lines.push(mark + " " + txt + " — " + stamp(at, now, f));
  }
  if (subs.length > SUB_CAP) lines.push("…and " + (subs.length - SUB_CAP) + " more");
  // what the visible "Nm ago" itself marks, so the stamp is self-explaining
  const what = it.column === "completed" ? "marked done"
    : it.column === "needs_input" ? "blocked" : "last update";
  lines.push(what + " " + stamp(it.t, now, f));
  return lines.join("\n");
}

// a GROUP card folds N sibling asks from one typed prompt — its stamp's story is the fold itself
export function provenanceGroupTitle(memberStarts: number[], t: number, now: number, f: ProvFmt): string {
  const lines: string[] = [];
  if (memberStarts.length) lines.push("started " + stamp(Math.min(...memberStarts), now, f));
  lines.push(memberStarts.length + " cards from one prompt");
  lines.push("last update " + stamp(t, now, f));
  return lines.join("\n");
}
