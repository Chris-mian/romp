// THE PANE LAYOUT TREE, the pure half of the pane docking kit (plans/pane-docking.md, phase one). A
// dashboard layout is one recursive tree: a SPLIT (a row or a column of children, with a ratio per child
// summing to 1) or a LEAF (one registered pane, optionally holding a chat tab group). The engine
// (panedock-main.ts, a later phase) reads a viewport and assigns every leaf a rectangle from this tree,
// so a pane is positioned by GEOMETRY and never re-parented in the DOM (an iframe re-parented reloads and
// drops its socket). This module is that geometry plus the tree edits (split, move, close/park, resize)
// and the versioned store round-trip; it is PURE, like chat-columns.ts: no DOM, no window, no pane ids of
// its own. The shell hands it the tree, the ids and the viewport. Nothing here shows anything; a
// half-built layout never reaches the screen because the shell applies a whole result, never a partial.

export type Dir = "row" | "col";
export type PaneId = string;

/** A leaf: one pane. `group`/`active` are an opaque chat tab group the shell fills in a later phase; this
 *  module never reads their contents, only whether `group` is non-empty (a chat leaf holding sessions is
 *  never closed, only emptied: closePane refuses it). */
export interface Leaf { pane: PaneId; group?: PaneId[]; active?: PaneId }
/** A split: `kids` laid out along `dir`, each taking `ratios[i]` of the space (ratios sum to 1, one per
 *  kid). A split always has at least two kids; a split reduced to one kid collapses into that kid.
 *  `fixed` (phase two, plans/pane-docking.md section 11): a kid may carry a FIXED px size instead of a ratio
 *  share (the timeline band, `#tl-pane{flex:0 0 var(--tl)}`): `fixed[i]` is that kid's px, null for a ratio
 *  kid. layout allots the fixed kids their px first and divides the remainder among the ratio kids, whose
 *  ratios sum to 1 (a fixed kid's ratio is 0). Absent when no kid is fixed, so a store without a band keeps
 *  its phase-one shape byte for byte. */
export interface Split { dir: Dir; kids: Node[]; ratios: number[]; fixed?: Array<number | null> }
export type Node = Leaf | Split;

/** The persisted store: the tree, plus the PARKED panes (closed from the rail but kept mounted and hidden,
 *  off the tree, so re-opening re-inserts with no reload; plans/pane-docking.md section 5), plus, while anything
 *  is parked, the REMEMBERED tree: the arrangement with the parked panes in their places, so a show puts each back
 *  where it was (plans/pane-buttons-with-many-chats.md section 6, the user 2026-09-21: a hide remembers and a show
 *  restores, for every rail button). Optional, appended after `parked`, so a store with nothing parked keeps the
 *  phase-one shape byte for byte and an older bundle ignores it. Versioned so an older reader that cannot parse it
 *  drops to the shipped stores rather than mis-rendering. */
export interface Layout { v: 1; tree: Node; parked: PaneId[]; remembered?: Node }

/** Where a dropped pane docks against a target leaf: an edge (dock/split) or the target's tab strip
 *  (join, handled by the shell, not this module). */
export type Edge = "left" | "right" | "top" | "bottom";

export interface Size { w: number; h: number }
export interface Rect { x: number; y: number; w: number; h: number }

export function isLeaf(n: Node): n is Leaf { return (n as Split).kids === undefined; }
export function isSplit(n: Node): n is Split { return (n as Split).kids !== undefined; }

const EPS = 1e-6;
function dirOf(e: Edge): Dir { return e === "left" || e === "right" ? "row" : "col"; }
function before(e: Edge): boolean { return e === "left" || e === "top"; }

/** Every pane id in the tree, left-to-right / top-to-bottom (depth first). */
export function leaves(n: Node): PaneId[] {
  return isLeaf(n) ? [n.pane] : n.kids.flatMap(leaves);
}

/** Whether the tree holds a leaf for `pane`. */
export function has(n: Node, pane: PaneId): boolean {
  return isLeaf(n) ? n.pane === pane : n.kids.some((k) => has(k, pane));
}

/** The leaf for `pane`, or null. */
export function leafOf(n: Node, pane: PaneId): Leaf | null {
  if (isLeaf(n)) return n.pane === pane ? n : null;
  for (const k of n.kids) { const f = leafOf(k, pane); if (f) return f; }
  return null;
}

/** Normalise a split's ratios to sum 1 over the RATIO kids (clamped non-negative; a fixed kid's ratio is 0);
 *  a degenerate all-zero falls to equal shares among the ratio kids. Pure helper, so every edit re-normalises
 *  rather than trusting arithmetic to stay exact. */
function norm(ratios: number[], fixed?: Array<number | null>): number[] {
  const isFixed = (i: number) => !!fixed && typeof fixed[i] === "number";
  const clamped = ratios.map((r, i) => (isFixed(i) ? 0 : r > 0 ? r : 0));
  const free = clamped.filter((_, i) => !isFixed(i)).length;
  if (free === 0) return clamped;
  const sum = clamped.reduce((a, b) => a + b, 0);
  if (sum < EPS) return clamped.map((_, i) => (isFixed(i) ? 0 : 1 / free));
  return clamped.map((r) => r / sum);
}

/** A `fixed` array worth keeping: one with a px entry; an all-null array is dropped so the shape stays phase one's. */
function keepFixed(fixed?: Array<number | null>): Array<number | null> | undefined {
  return fixed && fixed.some((f) => typeof f === "number") ? fixed.map((f) => (typeof f === "number" && f > 0 ? f : null)) : undefined;
}

/** The module's one split constructor: ratios normalised, an all-null fixed array dropped (exported for the reconcile's
 *  remembered-place insertion in pane-dock.ts; every other edit goes through the functions below). */
export function mkSplit(dir: Dir, kids: Node[], ratios: number[], fixed?: Array<number | null>): Split {
  const fx = keepFixed(fixed);
  const out: Split = { dir, kids, ratios: norm(ratios, fx) };
  if (fx) out.fixed = fx;
  return out;
}

/** The fixed px of kid `i` of a split, or null for a ratio kid. */
export function fixedOf(n: Split, i: number): number | null {
  const f = n.fixed && n.fixed[i];
  return typeof f === "number" ? f : null;
}

/** GEOMETRY: every leaf's rectangle in px, from the tree, a viewport and the gutter thickness between
 *  siblings. A row divides width among kids by ratio (less the gutters between them); a column divides
 *  height. Fractional px are intended; the shell rounds at the edge. This is the whole render contract:
 *  the shell positions each pane iframe at its rect and never moves it in the DOM. */
export function layout(n: Node, box: Rect, gutter: number): Array<{ pane: PaneId; rect: Rect }> {
  if (isLeaf(n)) return [{ pane: n.pane, rect: box }];
  const horiz = n.dir === "row";
  const span = (horiz ? box.w : box.h) - gutter * (n.kids.length - 1);
  // the fixed kids take their px first (clamped to the span), the ratio kids divide what is left
  const fixedSum = n.kids.reduce((a, _, i) => a + (fixedOf(n, i) || 0), 0);
  const avail = span - fixedSum > 0 ? span - fixedSum : 0;
  const out: Array<{ pane: PaneId; rect: Rect }> = [];
  const far = horiz ? box.x + box.w : box.y + box.h;
  let off = horiz ? box.x : box.y;
  n.kids.forEach((kid, i) => {
    const fx = fixedOf(n, i);
    const size = fx !== null ? fx : avail * n.ratios[i];
    // clamp each kid's start and end to the box: a split narrower than its gutters would otherwise advance
    // the offset a full gutter per kid and land zero-width rects OUTSIDE the box
    const start = off < far ? off : far;
    const end = off + size < far ? off + size : far;
    const rect: Rect = horiz
      ? { x: start, y: box.y, w: end - start, h: box.h }
      : { x: box.x, y: start, w: box.w, h: end - start };
    out.push(...layout(kid, rect, gutter));
    off += size + gutter;
  });
  return out;
}

/** Insert a new leaf at an edge of the target pane, subdividing. Flattens where it can: docking to an edge
 *  whose direction matches the target's parent split inserts a SIBLING in that split (the new pane takes
 *  half the target's share); otherwise the target leaf is replaced by a new two-kid split. Any depth. The
 *  root with no parent is wrapped. Returns a new tree (never mutates the input). Throws if `pane` is
 *  already in the tree or the target is absent. */
export function splitAt(tree: Node, target: PaneId, pane: PaneId, edge: Edge): Node {
  if (has(tree, pane)) throw new Error("splitAt: pane already in the tree: " + pane);
  if (!has(tree, target)) throw new Error("splitAt: target not in the tree: " + target);
  const dir = dirOf(edge);
  const leaf: Leaf = { pane };
  const rebuilt = (n: Node): Node => {
    if (isLeaf(n)) {
      if (n.pane !== target) return n;
      // the target with no parent match: replace it with a fresh two-kid split (a fixed target keeps its px:
      // the parent's fixed entry names the SLOT, which this split now fills, its two kids sharing the px)
      return mkSplit(dir, before(edge) ? [leaf, n] : [n, leaf], [0.5, 0.5]);
    }
    const idx = n.kids.findIndex((k) => isLeaf(k) && k.pane === target);
    if (idx >= 0 && n.dir === dir) {
      // flatten: the target is a direct child of a same-direction split, so the new pane is a sibling and
      // splits the target's own share in half; the other kids keep their ratios (norm re-scales). Beside a
      // FIXED target (the band) there is no share to halve: the new ratio kid takes an equal share among the
      // ratio kids (1/(free+1) of the total), and stays a ratio kid.
      const kids = n.kids.slice();
      const ratios = n.ratios.slice();
      const fixed = n.fixed ? n.fixed.slice() : n.kids.map(() => null as number | null);
      const at = before(edge) ? idx : idx + 1;
      const targetFixed = fixedOf(n, idx) !== null;
      const free = n.kids.filter((_, i) => fixedOf(n, i) === null).length;
      // the ratio kids sum to 1, so a share of 1/free gives the new kid 1/(free+1) of the total once re-normalised
      const share = targetFixed ? (free > 0 ? 1 / free : 1) : n.ratios[idx] / 2;
      kids.splice(at, 0, leaf);
      ratios.splice(at, 0, share);
      fixed.splice(at, 0, null);
      if (!targetFixed) ratios[before(edge) ? idx + 1 : idx] = share;
      return mkSplit(n.dir, kids, ratios, fixed);
    }
    return mkSplit(n.dir, n.kids.map(rebuilt), n.ratios, n.fixed);
  };
  return rebuilt(tree);
}

/** Remove `pane`'s leaf and collapse any split left with one kid (that kid takes the split's slot ratio).
 *  Returns the new tree (null if the pane was the whole tree) and the detached leaf (null if absent), never
 *  mutating the input. */
export function detach(tree: Node, pane: PaneId): { tree: Node | null; leaf: Leaf | null } {
  const found = leafOf(tree, pane);
  if (!found) return { tree, leaf: null };
  if (isLeaf(tree)) return { tree: tree.pane === pane ? null : tree, leaf: tree.pane === pane ? tree : null };
  // strip returns the rebuilt node and, when it COLLAPSED onto a kid that was fixed in it, that kid's px, so the
  // parent's slot for it becomes fixed (a band whose only sibling left would otherwise turn into a ratio kid)
  const strip = (n: Split): { node: Node | null; px: number | null } => {
    const keep: Node[] = [];
    const ratios: number[] = [];
    const fixed: Array<number | null> = [];
    n.kids.forEach((k, i) => {
      if (isLeaf(k) && k.pane === pane) return;   // drop the target leaf
      let kept: Node | null = k, px = fixedOf(n, i);
      if (isSplit(k)) { const r = strip(k); kept = r.node; if (r.px !== null && px === null) px = r.px; }
      if (kept === null) return;   // a nested split that emptied out drops with it
      keep.push(kept);
      ratios.push(n.ratios[i]);
      fixed.push(px);
    });
    if (keep.length === 0) return { node: null, px: null };   // every kid was the target (a duplicate-id tree): an EMPTY split, not a kid-less one, so closePane's only-pane guard catches it and never blanks the dashboard
    if (keep.length === 1) return { node: keep[0], px: fixed[0] };   // collapse: the lone kid takes this split's place (and its slot ratio, or carries its px up)
    return { node: mkSplit(n.dir, keep, ratios, fixed), px: null };
  };
  return { tree: strip(tree).node, leaf: found };
}

/** Move a pane to an edge of a target pane: detach it (collapsing its old parent), then dock it. The target
 *  must be a DIFFERENT pane still present after the detach. Returns a new tree. */
export function move(tree: Node, pane: PaneId, target: PaneId, edge: Edge): Node {
  if (pane === target) throw new Error("move: a pane cannot dock to itself: " + pane);
  const { tree: without, leaf } = detach(tree, pane);
  if (!leaf) throw new Error("move: pane not in the tree: " + pane);
  if (!without) throw new Error("move: cannot move the only pane");
  if (!has(without, target)) throw new Error("move: target not in the tree: " + target);
  const docked = splitAt(without, target, pane, edge);
  // carry the moved leaf's chat group across (splitAt mints a bare leaf): a group or an active ride the
  // move whenever either is present, an empty group included (a faithful carry, not a behavioural one)
  if (leaf.group !== undefined || leaf.active !== undefined) {
    const relabel = (n: Node): Node => isLeaf(n)
      ? (n.pane === pane ? { ...n, group: leaf.group, active: leaf.active } : n)
      : mkSplit(n.dir, n.kids.map(relabel), n.ratios, n.fixed);
    return relabel(docked);
  }
  return docked;
}

export interface CloseResult { ok: boolean; layout: Layout; reason?: string }

/** Close a pane from the rail: PARK it (remove the leaf from the tree, add the id to `parked`), keeping the
 *  shell's iframe mounted and hidden so a re-open has no reload. Refuses a chat leaf that still holds
 *  sessions (`group` non-empty): such a leaf is EMPTIED by moving its tabs, never rail-closed
 *  (plans/pane-docking.md section 5). Refuses closing the only pane. Never mutates the input. */
export function closePane(cur: Layout, pane: PaneId): CloseResult {
  const leaf = leafOf(cur.tree, pane);
  if (!leaf) return { ok: false, layout: cur, reason: "not in the tree" };
  if (leaf.group && leaf.group.length) return { ok: false, layout: cur, reason: "a chat pane holding sessions is emptied, not closed" };
  const { tree } = detach(cur.tree, pane);
  if (!tree) return { ok: false, layout: cur, reason: "cannot close the only pane" };
  const parked = cur.parked.includes(pane) ? cur.parked : cur.parked.concat(pane);
  return { ok: true, layout: { ...cur, v: 1, tree, parked } };   // the remembered tree rides along (section 6)
}

/** Open a pane at an edge of a target (the rail's "open at its default dock"): dock it and drop it from the
 *  parked set. Returns the CloseResult shape (never throws, like closePane): an absent target or opening a
 *  pane against itself is a refusal with a reason. A pane already in the tree is ok, and any STALE park of it
 *  is dropped (the parked set must never hold a docked pane), rather than returning the layout untouched. */
export function openPane(cur: Layout, pane: PaneId, target: PaneId, edge: Edge): CloseResult {
  const unpark = (tree: Node): Layout => ({ ...cur, v: 1, tree, parked: cur.parked.filter((p) => p !== pane) });   // the remembered tree rides along
  if (has(cur.tree, pane)) return { ok: true, layout: unpark(cur.tree) };   // already docked: drop any stale park, no structural change
  if (pane === target) return { ok: false, layout: cur, reason: "a pane cannot open against itself" };
  if (!has(cur.tree, target)) return { ok: false, layout: cur, reason: "target not in the tree" };
  return { ok: true, layout: unpark(splitAt(cur.tree, target, pane, edge)) };
}

/** Re-weight the edge between kids `i` and `i+1` of the split at `path` (a list of kid indices from the
 *  root), moving `delta` (a fraction of the split, positive grows kid `i`). Each side is clamped to at
 *  least `minFrac` so neither collapses. Returns a new tree; a bad path or index is returned unchanged. */
export function resize(tree: Node, path: number[], i: number, delta: number, minFrac: number): Node {
  const at = (n: Node, p: number[]): Node => {
    if (p.length === 0) {
      if (isLeaf(n) || i < 0 || i + 1 >= n.kids.length) return n;
      if (!Number.isFinite(delta) || !Number.isFinite(minFrac)) return n;   // a NaN/Infinity delta or min passes both clamps below and zeroes two panes; leave the edge put
      if (fixedOf(n, i) !== null || fixedOf(n, i + 1) !== null) return n;   // a fixed kid's edge is sized in px (setFixed), never by ratio
      const ratios = n.ratios.slice();
      const pair = ratios[i] + ratios[i + 1];
      if (pair < 2 * minFrac) return n;   // neither side can meet the min: leave the edge where it is, never mint a negative ratio
      const lo = minFrac, hi = pair - minFrac;
      let a = ratios[i] + delta;
      a = a < lo ? lo : a > hi ? hi : a;
      ratios[i] = a; ratios[i + 1] = pair - a;
      return mkSplit(n.dir, n.kids.slice(), ratios, n.fixed);   // slice: the returned tree never aliases the input's kids array
    }
    if (isLeaf(n)) return n;
    const [head, ...rest] = p;
    if (head < 0 || head >= n.kids.length) return n;
    const kids = n.kids.slice();
    kids[head] = at(kids[head], rest);
    return mkSplit(n.dir, kids, n.ratios, n.fixed);
  };
  return at(tree, path);
}

/** Set (or clear, with null) the FIXED px of the slot holding `pane` (a direct kid of some split): the band's
 *  height following `--tl`. A pane that is the whole tree, or absent, leaves the tree unchanged. */
export function setFixed(tree: Node, pane: PaneId, px: number | null): Node {
  const at = (n: Node): Node => {
    if (isLeaf(n)) return n;
    const idx = n.kids.findIndex((k) => isLeaf(k) && k.pane === pane);
    if (idx >= 0) {
      const fixed = n.fixed ? n.fixed.slice() : n.kids.map(() => null as number | null);
      fixed[idx] = px !== null && Number.isFinite(px) && px > 0 ? px : null;
      return mkSplit(n.dir, n.kids.slice(), n.ratios, fixed);
    }
    return mkSplit(n.dir, n.kids.map(at), n.ratios, n.fixed);
  };
  return at(tree);
}

/** Every INTERNAL EDGE of the tree as a gutter rectangle: the gap between kids i and i+1 of the split at `path`,
 *  `gutter` thick, spanning the split's cross axis. `fixed` says a side is a fixed kid (the engine sizes that edge
 *  in px, never by ratio). The engine mounts one divider per edge from this. */
export interface EdgeRect { path: number[]; i: number; dir: Dir; rect: Rect; fixed: boolean; avail: number }
export function edges(n: Node, box: Rect, gutter: number, path: number[] = []): EdgeRect[] {
  if (isLeaf(n)) return [];
  const horiz = n.dir === "row";
  const span = (horiz ? box.w : box.h) - gutter * (n.kids.length - 1);
  const fixedSum = n.kids.reduce((a, _, i) => a + (fixedOf(n, i) || 0), 0);
  const avail = span - fixedSum > 0 ? span - fixedSum : 0;
  const far = horiz ? box.x + box.w : box.y + box.h;
  const out: EdgeRect[] = [];
  let off = horiz ? box.x : box.y;
  n.kids.forEach((kid, i) => {
    const fx = fixedOf(n, i);
    const size = fx !== null ? fx : avail * n.ratios[i];
    const start = off < far ? off : far;
    const end = off + size < far ? off + size : far;
    const rect: Rect = horiz ? { x: start, y: box.y, w: end - start, h: box.h } : { x: box.x, y: start, w: box.w, h: end - start };
    out.push(...edges(kid, rect, gutter, path.concat(i)));
    if (i + 1 < n.kids.length) {
      const g: Rect = horiz ? { x: end, y: box.y, w: gutter, h: box.h } : { x: box.x, y: end, w: box.w, h: gutter };
      out.push({ path, i, dir: n.dir, rect: g, fixed: fx !== null || fixedOf(n, i + 1) !== null, avail });   // avail: the ratio kids' px, so a px drag converts to a ratio delta
    }
    off += size + gutter;
  });
  return out;
}

/** Seed today's row as a tree: a COLUMN of [the row of `order` panes weighted by `grow`, the bottom band],
 *  the shipped `.col` shape (a horizontal `.row` over the timeline band). `bandFrac` is the band's share of
 *  the height. With no band, the tree is just the row. This is the "renders today's row unchanged" seed:
 *  layout() of it reproduces the shipped flex proportions. Pure; the shell passes the real pane ids and the
 *  grow weights read from romp-pane-grow. */
export function seedRowOverBand(order: PaneId[], grow: Record<PaneId, number>, band: PaneId | null, bandFrac: number): Node {
  if (order.length === 0) throw new Error("seedRowOverBand: no panes");
  const rowRatios = order.map((p) => (grow[p] > 0 ? grow[p] : 1));
  const row: Node = order.length === 1 ? { pane: order[0] } : mkSplit("row", order.map((p) => ({ pane: p })), rowRatios);
  if (!band) return row;
  return mkSplit("col", [row, { pane: band }], [1 - bandFrac, bandFrac]);
}

/** Dock a pane against the WHOLE tree (the band's "bottom of everything"; a pane opened when its default target is
 *  gone): the root is wrapped in a split along the edge's direction, the new leaf a ratio kid, or a FIXED kid when
 *  `fixedPx` is given. Throws if the pane is already in the tree. */
export function dockRoot(tree: Node, pane: PaneId, edge: Edge, fixedPx: number | null = null): Node {
  if (has(tree, pane)) throw new Error("dockRoot: pane already in the tree: " + pane);
  const leaf: Leaf = { pane };
  const kids = before(edge) ? [leaf, tree] : [tree, leaf];
  const at = before(edge) ? 0 : 1;
  if (fixedPx !== null && fixedPx > 0) {
    const fixed: Array<number | null> = [null, null]; fixed[at] = fixedPx;
    const ratios = [1, 1]; ratios[at] = 0;
    return mkSplit(dirOf(edge), kids, ratios, fixed);
  }
  return mkSplit(dirOf(edge), kids, [0.5, 0.5]);
}

/** Seed today's row over the timeline BAND at a FIXED height (phase two: `#tl-pane{flex:0 0 var(--tl)}`, the
 *  band's px read from `--tl`): a column of [the row, the band], the band a fixed kid. With no band, the row. */
export function seedRowOverFixedBand(order: PaneId[], grow: Record<PaneId, number>, band: PaneId | null, bandPx: number): Node {
  const row = seedRowOverBand(order, grow, null, 0);
  if (!band) return row;
  return mkSplit("col", [row, { pane: band }], [1, 0], [null, bandPx > 0 ? bandPx : 200]);
}

/** Serialise the store: the remembered tree, when there is one, appended after `parked` (a store with nothing parked keeps
 *  the phase-one bytes). */
export function serialise(cur: Layout): string {
  const o: Record<string, unknown> = { v: 1, tree: cur.tree, parked: cur.parked };
  if (cur.remembered) o.remembered = cur.remembered;
  return JSON.stringify(o);
}

function validNode(n: unknown): n is Node {
  if (!n || typeof n !== "object") return false;
  const o = n as Record<string, unknown>;
  if (o.kids === undefined) {
    if (typeof o.pane !== "string") return false;
    if (o.group !== undefined && !(Array.isArray(o.group) && o.group.every((g) => typeof g === "string"))) return false;
    if (o.active !== undefined && typeof o.active !== "string") return false;
    return true;
  }
  if (!Array.isArray(o.kids) || o.kids.length < 2) return false;
  if (o.dir !== "row" && o.dir !== "col") return false;
  if (!Array.isArray(o.ratios) || o.ratios.length !== o.kids.length) return false;
  if (!(o.ratios as unknown[]).every((r) => typeof r === "number" && (r as number) >= 0)) return false;
  if (o.fixed !== undefined) {
    if (!Array.isArray(o.fixed) || o.fixed.length !== o.kids.length) return false;
    if (!(o.fixed as unknown[]).every((f) => f === null || (typeof f === "number" && Number.isFinite(f) && (f as number) > 0))) return false;
    if (!(o.fixed as unknown[]).some((f) => typeof f === "number")) return false;   // an all-null array is not a shape this module writes
  }
  const fx = (o.fixed as Array<number | null> | undefined) || null;
  const sum = (o.ratios as number[]).reduce((a, r, i) => a + (fx && typeof fx[i] === "number" ? 0 : r), 0);
  const free = (o.kids as unknown[]).filter((_, i) => !(fx && typeof fx[i] === "number")).length;
  if (free > 0 && Math.abs(sum - 1) > 1e-3) return false;   // the ratio kids sum to 1 (a fixed kid's ratio is ignored)
  return (o.kids as unknown[]).every(validNode);
}

/** Parse a serialised store, fail-closed: any shape violation returns null (the shell then falls to the
 *  shipped stores, never a mis-rendered tree), the read()/loadSettings idiom. */
export function parse(s: string): Layout | null {
  let raw: unknown;
  try { raw = JSON.parse(s); } catch { return null; }
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (o.v !== 1) return null;
  if (!validNode(o.tree)) return null;
  if (!Array.isArray(o.parked) || !o.parked.every((p) => typeof p === "string")) return null;
  const tree = o.tree as Node;
  const ls = leaves(tree);
  if (new Set(ls).size !== ls.length) return null;   // a duplicate pane id anywhere would strip to a kid-less split and blank the dashboard
  const parked = o.parked as PaneId[];
  if (parked.some((p) => has(tree, p))) return null;   // a pane cannot be both docked and parked
  // normalise every split's ratios once: validNode accepts a sum within 1e-3, but layout never re-normalises
  // (EPS 1e-6), so a stored [0.4995, 0.4996] would under-fill the box forever; mkSplit's norm() fixes it here
  const renorm = (n: Node): Node => isLeaf(n) ? n : mkSplit(n.dir, n.kids.map(renorm), n.ratios, n.fixed);
  const out: Layout = { v: 1, tree: renorm(tree), parked };
  // the remembered tree (section 6): a valid one rides along; a bad one is DROPPED and the layout stands, since it costs a
  // remembered place and never the dashboard (the tree above is what renders; fail-closed applies to that)
  if (o.remembered !== undefined && validNode(o.remembered)) {
    const m = o.remembered as Node, ml = leaves(m);
    if (new Set(ml).size === ml.length) out.remembered = renorm(m);
  }
  return out;
}
