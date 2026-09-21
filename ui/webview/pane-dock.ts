// THE PANE DOCKING ENGINE's pure half (plans/pane-docking.md, phase two): everything the shell engine
// (panedock-main.ts) decides that needs no DOM. The drop ZONES (four half-zones per pane, chosen by the nearest
// edge, plus a chat pane's tab strip as the join zone for a tab payload), the LANDING rectangle the live accent
// outline shows for a zone, the grab-surface gate and the slop, the SEED of a layout from the three shipped
// stores (romp-panes for which leaves exist, romp-pane-grow for the row's ratios, the chat columns in row
// order, the timeline band as a fixed-px kid) and the RECONCILE of a layout with the panes the shell shows
// now (a pane turned off parks, a pane turned on opens at its default dock). Like pane-tree.ts: no window, no
// document; the engine hands it rects, ids and points. Node-tested in pane-dock.test.ts.
import {
  type Edge, type Layout, type Node, type PaneId, type Rect, type Split, closePane, dockRoot, has, leaves, openPane, resize, seedRowOverFixedBand, setFixed, edges, isLeaf, type EdgeRect,
  detach, splitAt, fixedOf, mkSplit,
} from "./pane-tree";

/** The gap between sibling panes, the shipped gutter's 7 px. */
export const GUTTER = 7;
/** The grab RING inside every pane's rectangle (px): the pane's own padding, the iframe inset by this much,
 *  so a press on the ring is a press on the pane element itself, a grab surface without chrome. Six px since
 *  2026-09-19: the user's first press on a 3 px ring showed the hand but landed nothing at a normal pointer speed;
 *  six is a target a pointer lands on without aiming, and still reads as the pane's margin, not as chrome. */
export const RING = 6;
/** A press becomes a drag after this much travel (px); under it a press is a click, a text selection, a scroll. */
export const SLOP = 4;
/** The band's height when nothing has set `--tl` yet (the stylesheet's `var(--tl,200px)`). */
export const DEFAULT_BAND_PX = 200;
/** The layout store's key (plans/pane-docking.md section 6): written only while the kit is on. */
export const LAYOUT_KEY = "romp-layout";

export const CHAT = "chat-pane", FLEET = "fleet-pane", FEED = "feed-pane", FILES = "files-pane", BAND = "tl-pane";
/** The shipped four the engine's title map falls back to. The ROW ORDER is no longer a list here: the shell's pane row
 *  is rendered from the pane registry in rail order (plans/panes-as-data.md, phase two), and the engine reads it off
 *  the DOM (`Shown.row`, in document order), so a data pane or a shipped pane this module never heard of takes its
 *  place from that order alone. */

export interface Pt { x: number; y: number }
export type Payload = "pane" | "tab";
export type Zone = { target: PaneId; edge: Edge; strip?: false } | { target: PaneId; strip: true; edge?: undefined };

export function isChatPane(id: PaneId): boolean { return id === CHAT || /^chat-pane-\d+$/.test(id); }
export function isBand(id: PaneId): boolean { return id === BAND; }

/** The romp-pane-grow key of a pane id, which is also its rail key and its `po-` class (`chat`, `fleet`, `feed`,
 *  `files`, `artifacts`, a data pane's own id; `chat<n>` for a column): the pane element's id without `-pane`, the
 *  shell's naming rule for every pane it renders from the registry (plans/panes-as-data.md). */
export function growKey(id: PaneId): string {
  const m = /^chat-pane-(\d+)$/.exec(id);
  if (m) return "chat" + m[1];
  return id.endsWith("-pane") ? id.slice(0, -5) : id;
}

function inside(r: Rect, p: Pt): boolean { return p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h; }

/** The HALF-ZONE of a point inside a rect: the edge the point is nearest to, distances measured as a fraction
 *  of the rect's own dimension so a wide, short pane still offers its top and bottom halves. null outside. */
export function edgeZone(rect: Rect, p: Pt): Edge | null {
  if (!inside(rect, p) || rect.w <= 0 || rect.h <= 0) return null;
  const dl = (p.x - rect.x) / rect.w, dr = (rect.x + rect.w - p.x) / rect.w;
  const dt = (p.y - rect.y) / rect.h, db = (rect.y + rect.h - p.y) / rect.h;
  const m = Math.min(dl, dr, dt, db);
  return m === dl ? "left" : m === dr ? "right" : m === dt ? "top" : "bottom";
}

export interface ZoneOpts {
  /** the dragged pane (never a target of its own drop), or null for a tab payload */
  self: PaneId | null;
  /** the payload: a whole pane (edges only; a strip refuses it) or a single tab (a chat strip joins it) */
  payload: Payload;
  /** each chat pane's tab-strip height in px from its rect's top (the strip join zone), by pane id */
  strips?: Record<PaneId, number>;
}

/** The drop zone under a point, over the panes' current rectangles (viewport px, read right before the call).
 *  A point over the dragged pane itself is no zone (a drop there is a cancel); over a chat pane's strip band it
 *  is the STRIP join zone (a tab joins the group; a whole pane is refused there, which the engine shows as a
 *  refused outline); anywhere else in a pane it is that pane's nearest half. null over no pane. */
export function zoneAt(rects: ReadonlyArray<{ pane: PaneId; rect: Rect }>, p: Pt, opts: ZoneOpts): Zone | null {
  for (const { pane, rect } of rects) {
    if (!inside(rect, p)) continue;
    if (opts.self !== null && pane === opts.self) return null;
    const stripH = opts.strips && isChatPane(pane) ? opts.strips[pane] || 0 : 0;
    if (stripH > 0 && p.y < rect.y + stripH) return { target: pane, strip: true };
    const edge = edgeZone(rect, p);
    return edge ? { target: pane, edge } : null;
  }
  return null;
}

/** The rectangle the live outline shows for a zone: the target's half on that edge (what a dock there
 *  produces), or the strip band for a join. null when the target has no rect. */
export function landingRect(rects: ReadonlyArray<{ pane: PaneId; rect: Rect }>, zone: Zone, strips?: Record<PaneId, number>): Rect | null {
  const hit = rects.find((r) => r.pane === zone.target);
  if (!hit) return null;
  const r = hit.rect;
  if (zone.strip) return { x: r.x, y: r.y, w: r.w, h: Math.max(1, (strips && strips[zone.target]) || 0) };
  const hw = (r.w - GUTTER) / 2, hh = (r.h - GUTTER) / 2;
  switch (zone.edge) {
    case "left": return { x: r.x, y: r.y, w: Math.max(0, hw), h: r.h };
    case "right": return { x: r.x + r.w - Math.max(0, hw), y: r.y, w: Math.max(0, hw), h: r.h };
    case "top": return { x: r.x, y: r.y, w: r.w, h: Math.max(0, hh) };
    default: return { x: r.x, y: r.y + r.h - Math.max(0, hh), w: r.w, h: Math.max(0, hh) };
  }
}

/** A press, described for the grab gate: the primary button, the modifier, and what it landed on. */
export interface Press {
  button: number;
  alt: boolean;
  /** the pane element itself (its padding ring), not its iframe */
  onRing: boolean;
  /** the empty run of a pane's existing top row (the chat's tab strip between the + tab and its end; the Files bar) */
  onTopRun: boolean;
  /** a control, a link, a text field, or a text selection in progress: never a grab */
  onControl: boolean;
}

/** Whether a press may ARM a pane move: the primary button, not on a control, from a grab surface (the ring,
 *  a top-row empty run) or with Option/Alt held anywhere (plans/pane-docking.md section 3). The slop below
 *  still has to be crossed before anything lifts. */
export function grabbable(p: Press): boolean {
  return p.button === 0 && !p.onControl && (p.alt || p.onRing || p.onTopRun);
}

/** Whether a pointer has travelled past the slop from its press. */
export function crossedSlop(dx: number, dy: number, slop: number = SLOP): boolean {
  return Math.abs(dx) >= slop || Math.abs(dy) >= slop;
}

/** What the shell shows, read by the engine from the DOM: every row pane on screen in DOCUMENT order (the chat and its
 *  side columns, the outline, the feed, the files pane, the Artifacts pane and the data panes, as the shell renders and
 *  toggles them), whether the band is on, the band's px. */
export interface Shown {
  row: PaneId[]; band: boolean; bandPx: number; grow: Record<string, number>;
  /** the pane ids whose ELEMENTS exist (shown or hidden); absent, every parked id is kept. A park keeps a MOUNTED
   *  iframe (section 5); a closed chat column has none, so its park is pruned rather than kept forever. */
  present?: PaneId[];
  /** where the NEXT new chat column docks (a tab dropped in a zone: the target's edge), instead of its default place
   *  right of the last chat. Set by the engine around the shipped split's column open; consumed by the first new
   *  chat column the reconcile meets. */
  newChatDock?: { target: PaneId; edge: Edge };
}

/** Seed a layout from the shipped stores, plans/pane-docking.md section 6: the row of shown panes weighted by
 *  their romp-pane-grow numbers over the band as a FIXED kid. This reproduces today's row when the kit turns on;
 *  the old keys are read, never written. */
export function seedLayout(sh: Shown): Layout {
  const row = sh.row.length ? sh.row : [CHAT];
  const grow: Record<PaneId, number> = {};
  // a pane the grow store never named (a data pane defined after the store was written, the Artifacts pane on an older
  // store) takes a FAIR weight, the mean of the named ones: the shipped OFF path gives a new pane 40 beside 34..60, and the
  // rail's re-show takes the average (__rompGrowFair); a weight of 1 beside those seeded an 8 px column (the phase-two read)
  const known = row.map((id) => sh.grow[growKey(id)]).filter((g): g is number => typeof g === "number" && g > 0);
  const fair = known.length ? known.reduce((a, b) => a + b, 0) / known.length : 1;
  for (const id of row) { const g = sh.grow[growKey(id)]; grow[id] = typeof g === "number" && g > 0 ? g : fair; }
  const tree = seedRowOverFixedBand(row, grow, sh.band ? BAND : null, sh.bandPx > 0 ? sh.bandPx : DEFAULT_BAND_PX);
  return { v: 1, tree, parked: [] };
}

/** A newly shown pane's DEFAULT DOCK: where the rail's "open" puts it (section 5). A chat column goes right of
 *  the last chat leaf; the outline right of the chat side; the feed right of the outline (else the chat side);
 *  the files right of the rightmost non-band leaf; the chat itself left of everything; the band at the bottom
 *  of the whole tree as a fixed kid. Returns the target leaf and edge, or null to dock against the root. */
export function defaultDock(tree: Node, pane: PaneId): { target: PaneId; edge: Edge } | null {
  const ls = leaves(tree).filter((p) => !isBand(p));
  if (!ls.length) return null;
  const chats = ls.filter(isChatPane);
  const lastChat = chats.length ? chats[chats.length - 1] : null;
  if (isBand(pane)) return null;
  if (pane === CHAT) return { target: ls[0], edge: "left" };
  if (isChatPane(pane)) return lastChat ? { target: lastChat, edge: "right" } : { target: ls[0], edge: "left" };
  if (pane === FLEET) return lastChat ? { target: lastChat, edge: "right" } : { target: ls[0], edge: "left" };
  if (pane === FEED) {
    if (ls.includes(FLEET)) return { target: FLEET, edge: "right" };
    if (lastChat) return { target: lastChat, edge: "right" };
    return { target: ls[0], edge: "left" };
  }
  return { target: ls[ls.length - 1], edge: "right" };   // files, the artifacts pane, a data pane: the right end (plans/panes-as-data.md section 4)
}

// ── THE REMEMBERED ARRANGEMENT (plans/pane-buttons-with-many-chats.md section 6; the user 2026-09-21: a hide remembers the
//    arrangement and a show restores it, as a rule for every rail button). The layout keeps, beside `parked`, the tree as it
//    was with the parked panes in their places; a show puts a returning pane back beside the neighbour it had, with the
//    share it had, and what the user did meanwhile (a move, a resize, a pane closed) stands. Pure helpers, node-tested
//    through reconcileShown. ──

/** The tree reduced to the panes in `keep`: every other leaf detached, splits collapsing as detach does; null when nothing
 *  of it is kept. */
export function pruneTo(tree: Node, keep: ReadonlyArray<PaneId>): Node | null {
  const k = new Set(keep);
  let t: Node | null = tree;
  for (const p of leaves(tree)) { if (k.has(p) || !t) continue; t = detach(t, p).tree; }
  return t;
}

/** The same SHAPE: the same directions, the same leaves in the same order, the same fixed pattern. Ratios are not compared:
 *  a resize is not a rearrangement. */
export function sameShape(a: Node, b: Node): boolean {
  if (isLeaf(a) || isLeaf(b)) return isLeaf(a) && isLeaf(b) && a.pane === b.pane;
  if (a.dir !== b.dir || a.kids.length !== b.kids.length) return false;
  for (let i = 0; i < a.kids.length; i++) {
    if ((fixedOf(a, i) !== null) !== (fixedOf(b, i) !== null)) return false;
    if (!sameShape(a.kids[i], b.kids[i])) return false;
  }
  return true;
}

/** The memory after a park from `before` (the tree as shown right before it): the standing memory stays when it still
 *  describes `before` (reduced to before's panes it has before's shape: nothing was moved since it was taken, so it holds the
 *  pane about to park in its place and every earlier parked pane in theirs); else `before`, the freshest arrangement,
 *  replaces it (an earlier parked pane then returns at its default dock: its place was in a tree the user has since
 *  rearranged). */
export function remember(memory: Node | undefined, before: Node): Node {
  if (memory) { const r = pruneTo(memory, leaves(before)); if (r && sameShape(r, before)) return memory; }
  return before;
}

/** A node of `tree` holding exactly the leaves `set` (whatever its shape inside), or null. */
function nodeWithLeaves(tree: Node, set: ReadonlyArray<PaneId>): Node | null {
  const want = new Set(set), ls = leaves(tree);
  if (ls.length === want.size && ls.every((p) => want.has(p))) return tree;
  if (isLeaf(tree)) return null;
  for (const k of tree.kids) { const f = nodeWithLeaves(k, set); if (f) return f; }
  return null;
}

/** `pane` inserted beside the node `unit` of `tree` (found in it by identity): a sibling in the unit's parent split when that
 *  parent IS the remembered split reduced (the same direction and every leaf of it among `within`, the remembered split's
 *  leaves), its share `rel` times the unit's; else the unit wrapped in a new two-kid split of that direction (shares rel to
 *  1), so a group the memory kept apart (a chat over its feed inside a row) comes back as a group and the next returning
 *  pane finds it whole. */
function insertBeside(tree: Node, unit: Node, pane: PaneId, dir: "row" | "col", first: boolean, rel: number, within: ReadonlySet<PaneId>): Node {
  const leaf: Node = { pane };
  const wrap = (u: Node): Node => mkSplit(dir, first ? [leaf, u] : [u, leaf], first ? [rel, 1] : [1, rel]);
  if (unit === tree) return wrap(tree);
  const rebuilt = (n: Node): Node => {
    if (isLeaf(n)) return n;
    const idx = n.kids.indexOf(unit);
    if (idx >= 0) {
      if (n.dir === dir && fixedOf(n, idx) === null && leaves(n).every((q) => within.has(q))) {
        const kids = n.kids.slice(), ratios = n.ratios.slice(), fixed = n.fixed ? n.fixed.slice() : n.kids.map(() => null as number | null);
        const at = first ? idx : idx + 1;
        kids.splice(at, 0, leaf); ratios.splice(at, 0, n.ratios[idx] * rel); fixed.splice(at, 0, null);
        return mkSplit(n.dir, kids, ratios, fixed);
      }
      const kids = n.kids.slice(); kids[idx] = wrap(unit);
      return mkSplit(n.dir, kids, n.ratios, n.fixed);
    }
    return mkSplit(n.dir, n.kids.map(rebuilt), n.ratios, n.fixed);
  };
  return rebuilt(tree);
}

/** Where a returning pane goes, from the memory: beside the nearest remembered neighbour the tree still shows, on the side it
 *  had, with its remembered share. From the pane's leaf upward, each remembered split's other kids are tried nearest first: a
 *  kid the tree shows whole (its shown leaves are one node of the tree, whatever happened inside) takes the pane as a sibling
 *  (or a wrap when the directions differ); failing that, the pane docks at the nearest shown leaf of the nearest kid. A fixed
 *  kid (the band) is no neighbour to dock beside. Null when the memory has nothing to say (the pane unknown to it, or none of
 *  its neighbours shown): the caller falls to the default dock. When nothing moved since the hide, the insertions rebuild
 *  the remembered tree exactly, shares included. */
export function placeFrom(memory: Node, tree: Node, pane: PaneId): Node | null {
  if (!has(memory, pane) || has(tree, pane)) return null;
  const chain: Array<{ split: Split; idx: number }> = [];
  const walk = (n: Node): boolean => {
    if (isLeaf(n)) return n.pane === pane;
    for (let i = 0; i < n.kids.length; i++) { if (walk(n.kids[i])) { chain.push({ split: n, idx: i }); return true; } }
    return false;
  };
  walk(memory);
  const shown = leaves(tree);
  for (const { split: a, idx: i } of chain) {
    let nearLeaf: { leaf: PaneId; first: boolean } | null = null;
    const order: number[] = [];
    for (let d = 1; d < a.kids.length; d++) { if (i - d >= 0) order.push(i - d); if (i + d < a.kids.length) order.push(i + d); }
    for (const j of order) {
      if (fixedOf(a, j) !== null) continue;
      const unit = pruneTo(a.kids[j], shown);
      if (!unit) continue;
      const first = i < j;
      const node = nodeWithLeaves(tree, leaves(unit));
      if (node) {
        const sp = fixedOf(a, i) !== null ? 0 : a.ratios[i], su = a.ratios[j];
        return insertBeside(tree, node, pane, a.dir, first, sp > 0 && su > 0 ? sp / su : 1, new Set(leaves(a)));
      }
      if (!nearLeaf) { const ls = leaves(unit); nearLeaf = { leaf: first ? ls[0] : ls[ls.length - 1], first }; }
    }
    if (nearLeaf) {
      const edge: Edge = a.dir === "row" ? (nearLeaf.first ? "left" : "right") : (nearLeaf.first ? "top" : "bottom");
      return splitAt(tree, nearLeaf.leaf, pane, edge);
    }
  }
  return null;
}

/** Reconcile a layout with what the shell SHOWS now: every leaf no longer shown is PARKED (its iframe stays
 *  mounted and hidden, today's togglePane feel) and the arrangement is REMEMBERED; every shown pane not in the
 *  tree comes back where the memory had it (else at its default dock), and the band's fixed px follows `bandPx`.
 *  The shown set is the rail's truth (body.po-* plus the columns present), so the tree can never allot a
 *  rectangle to a hidden pane or forget a visible one. Pure. */
export function reconcileShown(cur: Layout, sh: Shown): Layout {
  const want = new Set<PaneId>(sh.row.concat(sh.band ? [BAND] : []));
  let lay: Layout = cur;
  // park what is gone (the only-pane refusal is fine: a tree of one hidden pane is replaced below), remembering the
  // arrangement as shown right before (section 6): the memory stands when it still describes this tree, else this tree is it
  const before = cur.tree;
  let parkedAny = false;
  for (const p of leaves(lay.tree)) {
    if (want.has(p)) continue;
    const r = closePane(lay, p);
    if (r.ok) { lay = r.layout; parkedAny = true; }
  }
  if (parkedAny) lay = { ...lay, remembered: remember(cur.remembered, before) };
  // open what is new, in the ROW's order, which is the rail's (so the outline lands right of the chat before the feed
  // asks for the outline, and a data pane after the shipped columns): the row is read off the DOM in document order
  const missing = sh.row.filter((p) => want.has(p) && !has(lay.tree, p));
  let hint = sh.newChatDock || null;
  for (const p of missing) {
    if (leaves(lay.tree).every((q) => !want.has(q))) {
      // the tree holds only panes that should be hidden (every shown pane was parked): start over from this pane,
      // and PARK the hidden ones the tree held (their iframes stay mounted and hidden, as a rail close leaves them)
      const dropped = leaves(lay.tree).filter((q) => !lay.parked.includes(q));
      lay = { ...lay, tree: { pane: p }, parked: lay.parked.concat(dropped).filter((q) => q !== p) };
      continue;
    }
    let d = defaultDock(lay.tree, p);
    if (hint && isChatPane(p) && p !== CHAT && has(lay.tree, hint.target) && hint.target !== p) { d = hint; hint = null; }   // the dropped tab's pane lands where the outline said
    else if (lay.remembered && p !== BAND) {
      // the remembered place (section 6): beside the neighbour it had, with the share it had; the band keeps its own road below
      const placed = placeFrom(lay.remembered, lay.tree, p);
      if (placed) { lay = { ...lay, tree: placed, parked: lay.parked.filter((q) => q !== p) }; continue; }
    }
    if (d && has(lay.tree, d.target)) {
      const r = openPane(lay, p, d.target, d.edge);
      if (r.ok) lay = r.layout;
    } else {
      lay = { ...lay, tree: dockRoot(lay.tree, p, "right"), parked: lay.parked.filter((q) => q !== p) };
    }
  }
  if (sh.band && !has(lay.tree, BAND)) {
    lay = { ...lay, tree: dockRoot(lay.tree, BAND, "bottom", sh.bandPx > 0 ? sh.bandPx : DEFAULT_BAND_PX), parked: lay.parked.filter((q) => q !== BAND) };
  }
  if (sh.band) lay = { ...lay, tree: setFixed(lay.tree, BAND, sh.bandPx > 0 ? sh.bandPx : DEFAULT_BAND_PX) };
  // a stale park of anything shown is dropped (the parked set never holds a docked pane), and so is the park of a
  // pane whose element is gone (a closed chat column: nothing is mounted to re-open)
  const parked = lay.parked.filter((q) => !has(lay.tree, q) && (!sh.present || sh.present.includes(q)));
  // the memory (section 6): reduced to the panes the layout still knows (the tree's and the parked), so a column closed while
  // hidden leaves no record; dropped when nothing is parked, or when it names no hidden pane (nothing left to say)
  let remembered = parked.length && lay.remembered ? pruneTo(lay.remembered, leaves(lay.tree).concat(parked)) : null;
  if (remembered && leaves(remembered).every((q) => has(lay.tree, q))) remembered = null;
  const out: Layout = { v: 1, tree: lay.tree, parked };
  if (remembered) out.remembered = remembered;
  return out;
}

/** The chat column number a pane id names: the first chat pane is column 1, `chat-pane-<n>` is column n, any other
 *  pane none. The shipped split script keys its membership store (romp-chat-cols) and __rompMoveTab by these. */
export function colNumberOf(pane: PaneId): number | null {
  if (pane === CHAT) return 1;
  const m = /^chat-pane-(\d+)$/.exec(pane);
  return m ? Number(m[1]) : null;
}

/** The column holding a session, from the shipped membership sets ({"2": [sids], ...}; the first column lists nothing
 *  and holds the rest): the entry's number, else 1. */
export function ownerColumn(sets: Record<string, string[]> | null | undefined, sid: string): number {
  for (const [k, ids] of Object.entries(sets || {})) if (Array.isArray(ids) && ids.includes(sid)) return Number(k) || 1;
  return 1;
}

/** What a TAB dropped in a zone does (plans/pane-docking.md section 4: a tab on a pane edge opens a new chat leaf there;
 *  a tab on another chat leaf's strip joins that group). Pure over the zone, the session and the membership sets:
 *  - `join`: the strip of a chat pane: the session moves into that column (the shipped mutation, __rompMoveTab(sid, col)).
 *  - `moveColumn`: the session is ALONE in a later column, so a new column would twin it and close it: the column's own
 *    pane moves to the target edge instead (a tab dropped in a zone is a pane there, with nothing minted).
 *  - `newColumn`: a new column opens with the session (__rompMoveTab(sid, "new")) and its leaf moves to the target edge.
 *  - `refuse`: the strip of a non-chat pane, or a lone column dropped on its own edge. */
export type TabDrop = { kind: "join"; col: number } | { kind: "moveColumn"; pane: PaneId } | { kind: "newColumn" } | { kind: "refuse"; why: string };
export function planTabDrop(zone: Zone, sid: string, sets: Record<string, string[]> | null | undefined): TabDrop {
  if (zone.strip) {
    const col = colNumberOf(zone.target);
    return col === null ? { kind: "refuse", why: "a session joins a chat pane's strip, not this pane" } : { kind: "join", col };
  }
  const owner = ownerColumn(sets, sid);
  const alone = owner !== 1 && Array.isArray(sets && sets[String(owner)]) && sets![String(owner)].length === 1;
  if (alone) {
    const pane = "chat-pane-" + owner;
    if (pane === zone.target) return { kind: "refuse", why: "this session is already alone in this pane" };
    return { kind: "moveColumn", pane };
  }
  return { kind: "newColumn" };
}

/** A DIVIDER drag's clamp, against the pair's sizes AT THE PRESS (plans/pane-docking.md section 12, the 1927 read): the pointer's
 *  travel `px` along the axis is held so neither side of the edge drops under `minPx` (the engine's minimum for the edge, the
 *  same one `resize` holds as a fraction, so the two clamps agree and the edge sits at the pointer up to the minimum and no
 *  further). Clamping against the CURRENT tree, which the live drag rewrites every frame, shrank the window as the drag
 *  proceeded and the edge converged on half its range; the press geometry is the fixed frame of reference. A pair that cannot
 *  seat two minimums does not move. */
export function edgeClamp(a0: number, b0: number, px: number, minPx: number): number {
  const lo = minPx - a0, hi = b0 - minPx;
  if (lo > hi) return 0;
  return px < lo ? lo : px > hi ? hi : px;
}

/** The edge at `path`/`i` as the tree lays it out in `box` now (edges): the divider's rect and the ratio kids' px along its axis
 *  (`avail`). A drag re-reads its edge here when the press tree changes under it (the band re-sized by the shell's autosize:
 *  the 1927 read, round four: a divider between stacked panes under the band kept its press avail, origin and pair sizes, so
 *  the edge left the pointer and the pushed pane persisted under the minimum). Null when the path no longer names a split edge. */
export function edgeAt(tree: Node, box: Rect, gutter: number, path: number[], i: number): EdgeRect | null {
  return edges(tree, box, gutter).find((e) => e.i === i && e.path.length === path.length && e.path.every((p, k) => p === path[k])) || null;
}

/** The pair's sizes in px on either side of `edge` in `tree` (its split's ratios times the edge's avail): the drag's frame of
 *  reference at the press, and again after a rebase. Zero for a path that names no split. */
export function pressGeometry(tree: Node, edge: EdgeRect): { a0: number; b0: number } {
  let n: Node = tree;
  for (const k of edge.path) { if (isLeaf(n) || !n.kids[k]) return { a0: 0, b0: 0 }; n = n.kids[k]; }
  if (isLeaf(n) || edge.i + 1 >= n.ratios.length) return { a0: 0, b0: 0 };
  return { a0: edge.avail * n.ratios[edge.i], b0: edge.avail * n.ratios[edge.i + 1] };
}

/** The tree for a divider drag's frame: the edge moved by the pointer's ABSOLUTE travel from the press, applied to the tree
 *  as it was at the press (never incrementally to the frame before, which would compound the clamp's rounding). Pure. */
export function dragEdge(start: Node, path: number[], i: number, travelPx: number, avail: number, minFrac: number): Node {
  return resize(start, path, i, avail > 0 ? travelPx / avail : 0, minFrac);
}

/** The `--tl` band height in px from the shell's `.col` style value (`"312px"`), else the default. */
export function bandPxOf(tlValue: string | null | undefined): number {
  const n = parseFloat(String(tlValue || ""));
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_BAND_PX;
}

/** Round a rect to whole px for the DOM (the module's fractional rects are intended; the shell rounds at the
 *  edge), keeping the far edge exact so neighbours never overlap by a rounding step. */
export function roundRect(r: Rect): Rect {
  const x = Math.round(r.x), y = Math.round(r.y);
  return { x, y, w: Math.max(0, Math.round(r.x + r.w) - x), h: Math.max(0, Math.round(r.y + r.h) - y) };
}
