// Fleet — a by-SESSION view that mirrors the chat's LEDGER BOX (the user 2026-06-23): each live session, then
// its goal tree beneath it — collapsible checkmark nodes, recency-coloured "(Xm ago)" times, the same .ledger-*
// look. It rides the FEED payload (connects app=feed, reads its `ledgers` slice — one per-session build_session
// ledger, the SAME tree the ledger box draws) — the proven feed channel. Completed top goals hide behind a
// bottom "Show completed" checkbox (default off). The recency colour helpers are copied verbatim from render.ts
// so the colours are IDENTICAL to the ledger box.
import { delegate } from "./actions";
import { fleetVisibleRoots } from "./fleet-roots";

type Color = { bg: string; fg: string } | null;
interface LedgerNode {
  id: string; text: string; depth: number; done: boolean; blocked: boolean;
  t: number; mt?: number; current: boolean; derived?: boolean; recent?: boolean;
  cleared?: boolean; onpath?: boolean; children?: string[];
  summary?: string | null; blockSummary?: string | null; _rec?: number;
  // EXACT turn uuids the kernel already sends per node (build_session tree) — let the fleet deep-link a node to
  // the SAME place the feed modal does (the user 2026-06-27): promptAnchorUuid = the user's minting message,
  // anchorUuid = where the node resolved (an assistant turn).
  promptAnchorUuid?: string | null; anchorUuid?: string | null;
}
interface Ledger { summary?: string; tree: LedgerNode[]; current?: { t?: number } | null; archivedTops?: LedgerNode[]; }
interface FleetSession { sid: string; name: string; color: Color; status?: { state?: string } | null; ledger?: Ledger | null; }

const vscodeApi =
  typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let sessions: FleetSession[] = [];
// Whether the FIRST feed payload has arrived (the user 2026-06-29): before it has, the fleet must NOT claim
// "no work" — that's the loading gap, where the data simply hasn't landed yet. We leave #fleet-list empty so
// the page's romp loader (_pane_spin) stays up, exactly like the other panes, until real data arrives.
let loaded = false;
let emptyShown = false;   // the romp wordmark is currently showing → don't replay its fade-in every push
let searchQuery = "";     // #fleet-search filter (the user 2026-06-29): show only sessions whose NAME matches
// Provisional cards (the user 2026-06-29): a session working a brand-new prompt the planner hasn't classified
// into a goal yet has NO ledger node, so it's invisible in the fleet — exactly the "things about to appear" the
// user wants to track. They ride the SAME feed payload (feed.asks, provisional:true), so surface a dotted
// signature row per such session here. Stored from each push.
interface ProvCard { sid: string; name: string; color: { bg: string; fg: string } | null; text: string }
let provCards: ProvCard[] = [];
const DONE_KEY = "romp:fleetShowDone";
function showDone(): boolean { try { return localStorage.getItem(DONE_KEY) === "1"; } catch { return false; } }
function setShowDone(on: boolean) { try { localStorage.setItem(DONE_KEY, on ? "1" : "0"); } catch { /* ignore */ } }

// "Group by session" (the user 2026-06-29): ON by default = the original by-session sections. OFF = a FLAT
// chronological list of every session's goals merged together, newest first, each row tagged on the RIGHT
// with the session it belongs to (.fl-sesslabel). The fold state keys are session-scoped either way, so a
// node's collapse carries across both modes.
const GROUP_KEY = "romp:fleetGroupBySession";
function isGrouped(): boolean { try { return localStorage.getItem(GROUP_KEY) !== "0"; } catch { return true; } }
function setGrouped(on: boolean) { try { localStorage.setItem(GROUP_KEY, on ? "1" : "0"); } catch { /* ignore */ } }

// Recency cutoff (the user 2026-06-27): a LOGARITHMIC slider hides sessions whose freshest activity is older
// than the window. Stored as a 0..1000 slider position. The right end is ADAPTIVE (the user 2026-06-27): it
// tracks the OLDEST session currently in the fleet, so the slider's whole travel always spans the real fleet
// and every drag does something — a fixed 1-month max left the upper third a dead zone for a fleet that only
// spans hours. The 1-minute FLOOR is preserved and far-right still means "show everything". cutoffSecs() maps
// the position log-uniformly from 1 minute to that adaptive max (each pixel = a constant RATIO of time).
const CUTOFF_KEY = "romp:fleetCutoffPos";
const CUT_MIN = 60, CUT_MAX = 30 * 86400;            // 1 minute (floor) … 1 month (initial fallback before the first render)
let fleetMaxAge = CUT_MAX;                            // adaptive right end — the oldest in-fleet age, refreshed each render()
let refreshCutoffLabel: (() => void) | null = null;  // mountControls registers its label painter so render() can refresh it
function cutoffPos(): number {
  try { const v = parseInt(localStorage.getItem(CUTOFF_KEY) || "", 10); return Number.isFinite(v) ? Math.max(0, Math.min(1000, v)) : 1000; }
  catch { return 1000; }
}
function setCutoffPos(p: number) { try { localStorage.setItem(CUTOFF_KEY, String(p)); } catch { /* ignore */ } }
function cutoffSecs(): number { return CUT_MIN * Math.pow(Math.max(fleetMaxAge, CUT_MIN * 2) / CUT_MIN, cutoffPos() / 1000); }   // log-uniform 1m … oldest-in-fleet
function fmtAge(s: number): string {
  if (s < 3600) return Math.round(s / 60) + "m";
  if (s < 86400) return Math.round(s / 3600) + "h";
  return Math.round(s / 86400) + "d";
}
// The freshest activity time (unix secs) for a session, rolled up the visible tree (0 if nothing visible) —
// the SAME basis the cutoff filter uses, factored out so render() can both compute the adaptive max and filter.
function sessionFreshest(s: FleetSession): number {
  const tree = s.ledger?.tree || [];
  stampSubtreeRecency(tree, s.ledger?.current || null);
  const archivedTops = Array.isArray(s.ledger?.archivedTops) ? s.ledger!.archivedTops! : [];
  const roots = tree.filter((n) => n.depth === 0);
  const visibleRoots = fleetVisibleRoots(roots, archivedTops, showDone());
  if (!visibleRoots.length) return 0;
  return Math.max(s.ledger?.current?.t || 0, ...visibleRoots.map(nodeRecency));
}
const folded = new Set<string>(), expanded = new Set<string>();   // fold state, keyed "sid\0nodeId"
const fkey = (sid: string, id: string) => sid + "\0" + id;

// Top-level goals last seen as DONE (keyed "sid\0nodeId") — the basis for auto-collapsing a super-category the
// instant it FINISHES (the user 2026-06-29). See the transition pass in render().
const seenDone = new Set<string>();

const sessFolded = new Set<string>();   // sessions whose WHOLE task tree is collapsed, keyed by sid (the user 2026-06-24)

// Collapse / Expand are STICKY TOGGLE MODES (the user 2026-06-29), persisted across kernel restarts + reopens.
// "collapse" → render() folds EVERYTHING (every session + node) and KEEPS it folded as new work streams in;
// "expand" → render() force-expands everything; null → the manual per-node state (folded/expanded sets +
// the finished-top default). The active button "stays clicked". A manual fold/sessfold click LEAVES the mode
// (bakeFoldMode writes the mode's current look into the sets first, so only the node you touched changes).
type FoldMode = "collapse" | "expand" | null;
const FOLD_MODE_KEY = "romp:fleetFoldMode";
function foldMode(): FoldMode { try { const v = localStorage.getItem(FOLD_MODE_KEY); return v === "collapse" || v === "expand" ? v : null; } catch { return null; } }
function setFoldMode(m: FoldMode) { try { if (m) localStorage.setItem(FOLD_MODE_KEY, m); else localStorage.removeItem(FOLD_MODE_KEY); } catch { /* ignore */ } }
let curFoldMode: FoldMode = null;   // snapshot read once per render() so renderFleetNode doesn't re-hit localStorage per node

// A Collapse/Expand BUTTON click: toggle that mode on/off (mutually exclusive). Clear the manual sets so the
// mode is clean and toggling it back OFF returns to the default view.
function toggleFoldMode(m: "collapse" | "expand") {
  const on = foldMode() === m;
  folded.clear(); expanded.clear(); sessFolded.clear();
  setFoldMode(on ? null : m);
  render();
}
// Bake the ACTIVE mode's current look into the manual sets, then leave the mode — called when the user folds
// something by hand, so the auto mode releases but the view it produced is preserved (only the hand-toggled
// node then differs).
function bakeFoldMode() {
  const m = foldMode();
  if (!m) return;
  if (m === "collapse") {
    for (const s of sessions) {
      sessFolded.add(s.sid);
      for (const n of s.ledger?.tree || []) if (n.children && n.children.length) { folded.add(fkey(s.sid, n.id)); expanded.delete(fkey(s.sid, n.id)); }
    }
  } else {
    sessFolded.clear();
    for (const s of sessions) for (const n of s.ledger?.tree || []) if (n.children && n.children.length) { expanded.add(fkey(s.sid, n.id)); folded.delete(fkey(s.sid, n.id)); }
  }
  setFoldMode(null);
}
// Paint the two toggle buttons' "on" state from the persisted mode (called from render + at mount).
function paintFoldButtons() {
  const m = foldMode();
  const c = document.getElementById("fl-collapse"), e = document.getElementById("fl-expand");
  if (c) c.classList.toggle("on", m === "collapse");
  if (e) e.classList.toggle("on", m === "expand");
}

function el(tag: string, cls?: string): HTMLElement { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

// Hover-highlight a GROUP of zones together (parity with the ledger box's linkHover, render.ts): the
// checkbox + time light as one unit when either is hovered, each keeping its own shape via .lz-hl, so a
// clickable row shows which parts go together (the user 2026-06-24).
function linkHover(group: HTMLElement[]): void {
  const on = () => group.forEach((g) => g.classList.add("lz-hl"));
  const off = () => group.forEach((g) => g.classList.remove("lz-hl"));
  group.forEach((g) => { g.addEventListener("mouseenter", on); g.addEventListener("mouseleave", off); });
}

// open a session's chat AND flip the pane back to the chat view (the user 2026-06-24): the Fleet toggle now
// lives in the chat tab bar, which is hidden while Fleet is shown — so picking a session must return there.
function backToChat() { try { if (window.parent !== window) window.parent.postMessage({ romp: "toggleFleet", to: "chat" }, "*"); } catch { /* not in the shell */ } }
function openSession(sid: string) { vscodeApi?.postMessage({ type: "openSession", id: sid }); backToChat(); }

// Deep-link a fleet node to the SAME place the feed modal's matching zone does (the user 2026-06-27): post the
// SAME `showOnTimeline` message (sid + anchorUuid + t), keyed off the node's kernel-supplied anchor uuids, then
// leave the full-screen Fleet view so the chat/timeline land is visible. kind="prompt" → the asking message
// (promptAnchorUuid); kind="work" → where it resolved (anchorUuid, using mt for a resolved node). A null anchor
// falls back to time-based nav kernel-side, exactly as the modal does.
function fleetNode(sid: string, nid: string): LedgerNode | null {
  const s = sessions.find((x) => x.sid === sid);
  return (s?.ledger?.tree || []).find((n) => n.id === nid) || null;
}
function fleetNavTo(el: HTMLElement, kind: "prompt" | "work") {
  const sid = el.dataset.sid, nid = el.dataset.nid;
  if (!sid) return;
  const n = nid ? fleetNode(sid, nid) : null;
  if (!n) { openSession(sid); return; }   // node gone from the payload → just open the session
  const resolved = !!(n.done || n.blocked);
  const t = kind === "work" ? ((resolved && n.mt) ? n.mt : n.t) : n.t;
  const anchorUuid = kind === "work" ? (n.anchorUuid ?? null) : (n.promptAnchorUuid ?? null);
  vscodeApi?.postMessage({ type: "showOnTimeline", itemId: nid, sid, t, anchor: kind, anchorUuid });
  backToChat();
}

// ── recency colour, copied verbatim from render.ts so Fleet's "(Xm ago)" colours match the ledger box ──
const COLORMAPS: Record<string, Array<[number, number, number]>> = {
  aurora: [[84, 178, 4], [0, 180, 115], [35, 175, 156], [66, 169, 176], [25, 168, 201], [14, 164, 227], [74, 155, 241], [113, 145, 244], [144, 136, 240]],   // romp green→teal→blue→purple at CONSTANT lightness — the default
  hawaii: [[140, 2, 115], [146, 46, 85], [151, 78, 62], [155, 111, 40], [156, 150, 28], [137, 189, 74], [107, 212, 142], [103, 233, 213], [179, 242, 253]],
  viridis: [[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137], [53, 183, 121], [110, 206, 88], [181, 222, 43], [253, 231, 37]],
  magma: [[0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129], [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135], [252, 253, 191]],
  inferno: [[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]],
  plasma: [[13, 8, 135], [75, 3, 161], [125, 3, 168], [168, 34, 150], [203, 70, 121], [229, 107, 93], [248, 148, 65], [253, 195, 40], [240, 249, 33]],
  cividis: [[0, 34, 78], [33, 59, 110], [76, 85, 108], [108, 110, 114], [142, 137, 120], [177, 165, 112], [217, 197, 92], [254, 232, 56]],
};
function selectedStops(): Array<[number, number, number]> {
  let name = "aurora";
  try { name = String(JSON.parse(localStorage.getItem("romp:settings") || "{}").colormap || "aurora"); } catch { /* default */ }
  return COLORMAPS[name.toLowerCase()] || COLORMAPS.aurora;
}
function ramp(v: number): [number, number, number] {
  const STOPS = selectedStops();
  v = Math.max(0, Math.min(1, v));
  const x = v * (STOPS.length - 1), i = Math.floor(x), fr = x - i;
  if (i >= STOPS.length - 1) return STOPS[STOPS.length - 1];
  const a = STOPS[i], b = STOPS[i + 1];
  return [Math.round(a[0] + (b[0] - a[0]) * fr), Math.round(a[1] + (b[1] - a[1]) * fr), Math.round(a[2] + (b[2] - a[2]) * fr)];
}
function recencyV(ageSecs: number): number {
  const LO = 120, HI = 345600;
  const a = Math.max(LO, Math.min(HI, ageSecs));
  return 1.0 - (Math.log(a) - Math.log(LO)) / (Math.log(HI) - Math.log(LO));
}
function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const l = (mx + mn) / 2;
  const s = d === 0 ? 0 : l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  if (d !== 0) {
    if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h, s, l];
}
function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) { const v = Math.round(l * 255); return [v, v, v]; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const hk = (t: number) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [Math.round(hk(h + 1 / 3) * 255), Math.round(hk(h) * 255), Math.round(hk(h - 1 / 3) * 255)];
}
function ageColorReadable(ageSecs: number): string {
  const v = recencyV(ageSecs);
  const c = ramp(v);
  const [h, s] = rgbToHsl(c[0], c[1], c[2]);
  const L = 0.50 + 0.22 * v;
  const S = Math.max(0.4, s) * (0.65 + 0.35 * v);
  const o = hslToRgb(h, Math.min(1, S), L);
  return `rgb(${o[0]}, ${o[1]}, ${o[2]})`;
}
function agehms(secs: number): string {
  secs = Math.max(0, Math.floor(secs));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

function nodeRecency(n: LedgerNode): number { return (n._rec ?? n.mt ?? n.t) || 0; }
// roll the freshest activity up to every node (mirrors render.ts stampSubtreeRecency)
function stampSubtreeRecency(tree: LedgerNode[], cur: { t?: number } | null): void {
  const byId = new Map(tree.map((n) => [n.id, n] as const));
  const eff = (n: LedgerNode) => (n.current && cur && cur.t) ? Math.max(cur.t, (n.mt ?? n.t) || 0) : ((n.mt ?? n.t) || 0);
  const inflight = new Set<string>();
  const calc = (n: LedgerNode): number => {
    if (n._rec != null) return n._rec;
    if (inflight.has(n.id)) return eff(n);
    inflight.add(n.id);
    let r = eff(n);
    for (const cid of n.children || []) { const c = byId.get(cid); if (c) r = Math.max(r, calc(c)); }
    n._rec = r;
    return r;
  };
  for (const n of tree) n._rec = undefined;
  for (const n of tree) calc(n);
}

// Per-session context a node needs to render (its node lookup + live-current time). One per session; in the
// FLAT view the same renderFleetNode is called with each root's own ctx so nodes from different sessions land
// in one shared container.
interface SessCtx { s: FleetSession; byId: Map<string, LedgerNode>; curT?: number;
  // SEARCH (the user 2026-06-29): subtreeHit(id) = this node OR any descendant matches the query → used to
  // FORCE-EXPAND collapsed branches that contain a match so the hit is revealed. null when not searching.
  subtreeHit?: (id: string) => boolean; }
let curSearch = "";   // the active query (lowercased), snapshot per render() for highlighting + fold override

// Paint `text` into `elm`, wrapping every case-insensitive occurrence of `q` in a .fl-hit highlight span (no
// match, or no query → plain text). Uses text nodes (no innerHTML) so goal text can never inject markup.
function highlightInto(elm: HTMLElement, text: string, q: string): void {
  elm.replaceChildren();
  if (!q) { elm.textContent = text; return; }
  const lc = text.toLowerCase();
  let i = 0, idx: number;
  while ((idx = lc.indexOf(q, i)) !== -1) {
    if (idx > i) elm.appendChild(document.createTextNode(text.slice(i, idx)));
    const m = el("span", "fl-hit"); m.textContent = text.slice(idx, idx + q.length);
    elm.appendChild(m);
    i = idx + q.length;
  }
  if (i < text.length) elm.appendChild(document.createTextNode(text.slice(i)));
}

// Render node `n` (and its open children) into `container`. Hoisted out of render() so the FLAT (ungrouped)
// view can merge nodes from many sessions into one list. `flat` adds the session-name tag on the RIGHT of a
// depth-0 row (the ungrouped view's "which session is this" marker).
function renderFleetNode(ctx: SessCtx, n: LedgerNode, depth: number, container: HTMLElement, now: number, flat: boolean) {
  const { s, byId, curT } = ctx;
  const expandable = !!(n.children && n.children.length);
  const defaultFold = !!n.done && (depth === 0 || !n.onpath);   // a finished top folds by default
  // SEARCH force-expand (the user 2026-06-29): if a collapsed branch CONTAINS a match, open it so the hit is
  // revealed — overriding the fold/mode state while a query is active.
  const hitChild = expandable && curSearch && !!ctx.subtreeHit
    && (n.children || []).some((cid) => ctx.subtreeHit!(cid));
  // a sticky Collapse/Expand mode overrides the per-node state (the user 2026-06-29); null → manual default
  const isFolded = expandable && !hitChild && (
    curFoldMode === "collapse" ? true
    : curFoldMode === "expand" ? false
    : (folded.has(fkey(s.sid, n.id)) || (defaultFold && !expanded.has(fkey(s.sid, n.id)))));
  const row = el("div", "ledger-tnode" + (depth === 0 ? " ledger-top" : "")
    + (n.current ? " current" : "") + (n.done ? " done" : "")
    + (n.blocked && !n.done ? " blocked" : "") + (n.derived ? " derived" : "")
    + (n.cleared ? " cleared" : "") + (n.cleared && n.summary && n.summary.trim() ? " cleared-done" : ""));
  row.style.paddingLeft = (4 + depth * 15) + "px";
  const tri = el("span", "ledger-tri" + (expandable ? " nav" : " empty"));
  tri.textContent = expandable ? (isFolded ? "▶" : "▼") : "";
  // click-safe: the fold toggle lives on the #fleet-list delegate; this caret just carries its state. The
  // caret is the innermost data-act, so a click on it folds without also firing the row's "open".
  if (expandable) { tri.dataset.act = "fold"; tri.dataset.sid = s.sid; tri.dataset.nid = n.id; tri.dataset.folded = isFolded ? "1" : "0"; }
  // .lz-nav → the pointer cursor (from styles.css), so the checkbox / text / time read as clickable. Each
  // zone DEEP-LINKS to the same place the feed modal's matching zone does (the user 2026-06-27): the TEXT
  // jumps to the message that asked for this (goprompt), and a resolved node's MARK + TIME jump to where it
  // resolved (gowork) — an open node's mark goes to the prompt, its time to the latest work. The zones carry
  // their own data-act (innermost wins), so a click lands the deep-link; the row's data-act="open" remains
  // the fallback for a click on the row's empty space. (Delegated via #fleet-list — see ./actions.)
  const resolved = !!(n.done || n.blocked);
  const mark = el("span", "ledger-tmark lz-nav");
  mark.dataset.sid = s.sid; mark.dataset.nid = n.id; mark.dataset.act = resolved ? "gowork" : "goprompt";
  mark.textContent = n.done ? "✓" : n.blocked ? "⏸" : "";   // open = a hollow CSS ring (no glyph)
  // restore the ledger box's mark TOOLTIP (the user 2026-06-24): the checkbox leads with WHY it reads the
  // way it does — explicit vs inferred (roll-up = every sub-step done, roll-down = a resolved parent) vs
  // dismissed vs blocked vs open — worked out from the children the render already has (no kernel round-trip).
  const markReason = (): string => {
    if (!n.done) return n.blocked ? "blocked — needs you" : "not yet done";
    if (n.cleared) {
      if (n.summary && n.summary.trim()) return "completed, then dismissed (cleared)";
      if (n.blockSummary && n.blockSummary.trim()) return "blocked, then dismissed (cleared)";
      return "dismissed — cleared, never judged done";
    }
    if (!n.derived) return "done — explicitly checked off";
    const kids = (n.children || []).map((id) => byId.get(id)).filter(Boolean) as LedgerNode[];
    return (kids.length > 0 && kids.every((k) => k.done))
      ? "done — inferred: every sub-step is complete"
      : "done — inferred: a parent goal was checked off";
  };
  mark.title = markReason();
  const txt = el("span", "ledger-ttext lz-nav");
  txt.dataset.sid = s.sid; txt.dataset.nid = n.id; txt.dataset.act = "goprompt";   // text → the asking message
  highlightInto(txt, n.text, curSearch);   // search: highlight the matched substring (plain text otherwise)
  txt.title = n.text;            // the full goal text on hover (it can wrap/clip in the narrow Fleet pane)
  // (The ⊕ distiller-summary expander was removed 2026-06-27 — the user: show just the goals, not the
  //  distiller takeaway / decision brief.)
  const time = el("span", "ledger-ttime");
  if (n.current && curT) {
    time.textContent = `(${agehms(now - curT)})`; time.style.color = ageColorReadable(now - curT);
  } else if (n.done && nodeRecency(n)) {
    const dt = now - nodeRecency(n);
    time.textContent = `(${agehms(dt)} ago)`; time.style.color = ageColorReadable(dt);
    txt.style.color = ageColorReadable(dt);                 // done text matches its rolled-up recency colour
  }
  if (time.textContent) { time.classList.add("lz-nav"); time.dataset.sid = s.sid; time.dataset.nid = n.id; time.dataset.act = "gowork"; }   // time → where the work happened/resolved
  // group the hover highlight like the ledger: a resolved node's checkbox + time light together, the text
  // on its own; an open node's checkbox + text are one block, the time on its own (the user 2026-06-24).
  if (n.done || n.blocked) { linkHover([txt]); linkHover(time.textContent ? [mark, time] : [mark]); }
  else { linkHover([mark, txt]); if (time.textContent) linkHover([time]); }
  row.appendChild(tri); row.appendChild(mark); row.appendChild(txt);
  row.appendChild(time);
  // FLAT view: tag each top-level goal with the session it belongs to, on the row's RIGHT (the user 2026-06-29).
  // It's a label, not its own action — a click bubbles to the row's data-act="open" and jumps into the session.
  if (flat && depth === 0) {
    const tag = el("span", "fl-sesslabel");
    if (s.status?.state === "working") tag.appendChild(el("span", "fl-workdot"));
    const tnm = el("span", "fl-sesslabel-name"); highlightInto(tnm, s.name, curSearch);
    if (s.color?.bg) tnm.style.color = s.color.bg;
    tag.appendChild(tnm);
    tag.title = "this goal belongs to “" + s.name + "” — click to open it";
    row.appendChild(tag);
  }
  row.dataset.act = "open"; row.dataset.sid = s.sid;   // click-safe: action lives on the #fleet-list delegate
  container.appendChild(row);
  if (expandable && !isFolded) for (const cid of n.children!) { const c = byId.get(cid); if (c) renderFleetNode(ctx, c, depth + 1, container, now, flat); }
}

function render() {
  const list = document.getElementById("fleet-list");
  if (!list) return;
  list.replaceChildren();
  // BEFORE the first payload: leave the list EMPTY so the page's romp loader (_pane_spin over #fleet-list)
  // stays up — no child means it never hides — instead of flashing a false "no work" message (the user
  // 2026-06-29). A WS drop / kernel restart re-shows that same loader (romp:wsdown), so a restart shows the
  // swirl, not "no tasks".
  if (!loaded) { emptyShown = false; return; }
  const sd = showDone();
  const grouped = isGrouped();
  curFoldMode = foldMode();   // snapshot the sticky Collapse/Expand mode once for this render
  paintFoldButtons();
  const now = Math.floor(Date.now() / 1000);
  let any = false;

  // Adaptive cutoff range: the slider's right end tracks the OLDEST in-fleet age, so its travel always spans
  // the real fleet (no dead zone). Compute it BEFORE filtering, then refresh the slider's "≤ <age>" label.
  let maxAge = CUT_MIN * 2;
  for (const s of sessions) { const f = sessionFreshest(s); if (f) maxAge = Math.max(maxAge, now - f); }
  fleetMaxAge = maxAge;
  refreshCutoffLabel?.();
  const cutoff = cutoffSecs();

  // Auto-collapse a super-category the instant it FINISHES (the user 2026-06-29): when a top-level goal flips
  // not-done → done (every sub-step checked off), drop any manual "expand" for it so it folds shut — even if
  // you'd expanded it while it was in progress. Event-based (keyed on the done TRANSITION, via seenDone), and
  // one-shot: you can re-expand it afterward and it stays open, since the transition won't fire again until it
  // reopens and re-completes. Runs over EVERY top goal (not just visible ones) so the collapse sticks even when
  // "Show completed" is off and the finished goal is momentarily filtered out. Once folded, defaultFold (a done
  // top with no manual expand) keeps it shut.
  for (const s of sessions) {
    for (const r of s.ledger?.tree || []) {
      if (r.depth !== 0) continue;
      const k = fkey(s.sid, r.id);
      if (r.done) { if (!seenDone.has(k)) { expanded.delete(k); seenDone.add(k); } }   // just finished → collapse
      else seenDone.delete(k);                                                          // (re)opened → re-arm
    }
  }

  // Provisional signature (the user 2026-06-29): a dotted "about to appear" row for a session working a
  // not-yet-classified prompt. Spinning swirl + the live gist; clicking opens the session. `flat` adds the
  // session-name tag on the right (matching renderFleetNode's flat tagging). Provisionals are always current,
  // so they ignore the recency cutoff.
  const provBySid = new Map<string, ProvCard>();
  for (const p of provCards) if (!provBySid.has(p.sid)) provBySid.set(p.sid, p);
  const makeProvRow = (p: ProvCard, flat: boolean) => {
    const row = el("div", "ledger-tnode ledger-top fl-prov");
    row.dataset.act = "open"; row.dataset.sid = p.sid;   // click-safe via the #fleet-list delegate
    row.title = "this session is working a brand-new prompt — the planner hasn't filed it as a task yet";
    row.appendChild(el("span", "fl-prov-swirl"));
    const txt = el("span", "ledger-ttext fl-prov-text"); txt.textContent = p.text;
    row.appendChild(txt);
    if (flat && p.name) {
      const tag = el("span", "fl-sesslabel");
      const tnm = el("span", "fl-sesslabel-name"); tnm.textContent = p.name;
      if (p.color?.bg) tnm.style.color = p.color.bg;
      tag.appendChild(tnm);
      row.appendChild(tag);
    }
    return row;
  };

  // First pass (shared by both views): keep the sessions whose freshest VISIBLE activity is inside the
  // slider window, each paired with its render context + visible roots.
  const survivors: { ctx: SessCtx; visibleRoots: LedgerNode[] }[] = [];
  const sq = searchQuery.trim().toLowerCase();           // search (the user 2026-06-29): session NAME or goal CONTENT
  curSearch = sq;                                        // snapshot for renderFleetNode (highlight + force-expand)
  for (const s of sessions) {
    const tree = s.ledger?.tree || [];
    // "Show completed" surfaces the FULLY-COMPLETED tops the compaction sweep archived out of the live tree
    // (the user 2026-06-27) — otherwise a finished+archived session has an empty live tree and vanishes, and
    // "Show completed" has nothing to reveal. The archive now carries each top's WHOLE SUBTREE (the user
    // 2026-06-29), so an archived completed goal EXPANDS to its hierarchy like a live one. ONLY shown when the
    // toggle is on (fleetVisibleRoots gates the depth-0 roots). The top-row selection is the pure ./fleet-roots.
    const archivedTops = Array.isArray(s.ledger?.archivedTops) ? s.ledger!.archivedTops! : [];
    stampSubtreeRecency(tree, s.ledger?.current || null);
    // byId spans the live tree AND the archived subtrees, so renderFleetNode can walk an archived top's
    // descendants. Only depth-0 archived nodes are ROOTS; the rest are reachable via their parents' children.
    const byId = new Map([...tree, ...archivedTops].map((n) => [n.id, n] as const));
    const roots = tree.filter((n) => n.depth === 0);
    const archRoots = archivedTops.filter((n) => n.depth === 0);
    // SEARCH (the user 2026-06-29): subtreeHit(id) = node OR any descendant text contains the query — memoized
    // over this session's nodes (live + archived). Drives the keep decision + the force-expand of collapsed
    // hits. Searching looks through DONE / ARCHIVED content too, even when "Show completed" is off (a match in
    // finished work should still be findable) — that's why it walks the whole tree, not just the open roots.
    const hitMemo = new Map<string, boolean>();
    const subtreeHit = (id: string): boolean => {
      const cached = hitMemo.get(id);
      if (cached !== undefined) return cached;
      hitMemo.set(id, false);                            // cycle guard (trees are acyclic, but be safe)
      const node = byId.get(id);
      let h = !!node && node.text.toLowerCase().includes(sq);
      if (!h && node) for (const cid of node.children || []) if (subtreeHit(cid)) { h = true; break; }
      hitMemo.set(id, h);
      return h;
    };
    let visibleRoots: LedgerNode[];
    if (sq) {
      // a match by session NAME shows the whole session (every top, done + archived); a CONTENT match shows
      // just the tops whose subtree hits — so completed/archived work IS revealed by search regardless of the
      // "Show completed" toggle (renderFleetNode then force-expands to the hit). The recency cutoff is bypassed:
      // an explicit search should find a goal no matter how old.
      const allRoots = roots.concat(archRoots);
      visibleRoots = s.name.toLowerCase().includes(sq) ? allRoots : allRoots.filter((r) => subtreeHit(r.id));
      if (!visibleRoots.length) continue;                // no name/content match → drop the session
    } else {
      visibleRoots = fleetVisibleRoots(roots, archRoots, sd);
      if (!visibleRoots.length) continue;                // nothing to show for this session → skip
      // recency cutoff (the user 2026-06-27): skip a session whose freshest VISIBLE activity is older than the window.
      const freshest = Math.max(s.ledger?.current?.t || 0, ...visibleRoots.map(nodeRecency));
      if (freshest && (now - freshest) > cutoff) continue;
    }
    survivors.push({ ctx: { s, byId, curT: s.ledger?.current?.t, subtreeHit: sq ? subtreeHit : undefined }, visibleRoots });
  }
  // SEARCH also filters the provisional ("about to appear") rows: keep one only if its session name or its
  // live gist matches the query (the user 2026-06-29).
  if (sq) for (const [sid, p] of Array.from(provBySid))
    if (!p.name.toLowerCase().includes(sq) && !(p.text || "").toLowerCase().includes(sq)) provBySid.delete(sid);

  if (grouped) {
    // BY-SESSION view: each session, then its goal tree beneath it (the original layout).
    for (const { ctx, visibleRoots } of survivors) {
      any = true;
      const s = ctx.s;
      const sec = el("div", "fl-session");
      const head = el("div", "fl-head");
      // session-level collapse caret (the user 2026-06-24): folds this session's WHOLE task tree. Its OWN
      // data-act="sessfold" (the innermost data-act in the head) so clicking it folds WITHOUT opening the
      // session — only a click on the name/rest of the head (data-act="open") jumps in.
      const sfolded = curFoldMode === "collapse" ? true : curFoldMode === "expand" ? false : sessFolded.has(s.sid);
      const caret = el("span", "fl-caret");
      caret.textContent = sfolded ? "▶" : "▼";
      caret.title = sfolded ? "expand this session's tasks" : "collapse this session's tasks";
      caret.dataset.act = "sessfold"; caret.dataset.sid = s.sid;
      caret.style.cssText = "flex:0 0 auto;cursor:pointer;color:var(--vscode-descriptionForeground,#9a9a9a);"
        + "font-size:9px;width:13px;text-align:center;user-select:none";
      head.appendChild(caret);
      if (s.status?.state === "working") head.appendChild(el("span", "fl-workdot"));
      const nm = el("span", "fl-name");
      highlightInto(nm, s.name, curSearch);   // highlight a name match
      if (s.color?.bg) nm.style.color = s.color.bg;
      head.appendChild(nm);
      head.title = "Open this session";
      head.dataset.act = "open"; head.dataset.sid = s.sid;   // click-safe: action lives on the #fleet-list delegate
      sec.appendChild(head);

      const treeBox = el("div", "ledger-tree");
      if (!sfolded) {
        for (const r of visibleRoots) renderFleetNode(ctx, r, 0, treeBox, now, false);
        const prov = provBySid.get(s.sid);               // a provisional row joins this session's tree
        if (prov) { treeBox.appendChild(makeProvRow(prov, false)); provBySid.delete(s.sid); }
        sec.appendChild(treeBox);
      }
      list.appendChild(sec);
    }
    // sessions that are ONLY provisional (no ledger tree → skipped above) still get a minimal section, so the
    // "about to appear" work is visible. Sorted by name for a stable order.
    for (const [, p] of Array.from(provBySid).sort((a, b) => (a[1].name || "").localeCompare(b[1].name || ""))) {
      any = true;
      const sec = el("div", "fl-session");
      const head = el("div", "fl-head");
      head.appendChild(el("span", "fl-workdot"));
      const nm = el("span", "fl-name"); nm.textContent = p.name; if (p.color?.bg) nm.style.color = p.color.bg;
      head.appendChild(nm);
      head.title = "Open this session"; head.dataset.act = "open"; head.dataset.sid = p.sid;
      sec.appendChild(head);
      const treeBox = el("div", "ledger-tree"); treeBox.appendChild(makeProvRow(p, false)); sec.appendChild(treeBox);
      list.appendChild(sec);
    }
  } else {
    // FLAT (ungrouped) view (the user 2026-06-29): every session's top goals merged into ONE chronological
    // list, newest first, each tagged on the right with its session. The whole subtree still expands inline,
    // and the per-node fold state (session-scoped keys) carries over from the grouped view.
    const flatRoots: { ctx: SessCtx; root: LedgerNode }[] = [];
    for (const { ctx, visibleRoots } of survivors) for (const r of visibleRoots) flatRoots.push({ ctx, root: r });
    flatRoots.sort((a, b) => nodeRecency(b.root) - nodeRecency(a.root));   // newest first
    if (flatRoots.length || provBySid.size) {
      any = true;
      const treeBox = el("div", "ledger-tree fl-flat");
      for (const { ctx, root } of flatRoots) renderFleetNode(ctx, root, 0, treeBox, now, true);
      for (const [, p] of Array.from(provBySid).sort((a, b) => (a[1].name || "").localeCompare(b[1].name || "")))
        treeBox.appendChild(makeProvRow(p, true));   // provisional rows ride the flat list too, tagged by session
      list.appendChild(treeBox);
    }
  }

  if (!any && sq) {
    // SEARCH with no match (the user 2026-06-29): say "No results" — NOT the romp wordmark, which reads as
    // "all clear" and hides that you're filtering.
    const nr = el("div", "fl-empty");
    nr.textContent = "No results for “" + searchQuery.trim() + "”";
    list.appendChild(nr);
    emptyShown = false;
  } else if (!any) {
    // GENUINELY empty (data loaded, no open work): the romp tri-color WORDMARK, centered + faded in — the
    // same calm inbox-zero treatment as the feed (the user 2026-06-29). The fade plays ONCE on the
    // not-empty→empty transition (emptyShown guard), not on every push, since render() rebuilds each time.
    const wm = el("div", "fl-wordmark" + (emptyShown ? " no-anim" : ""));
    wm.setAttribute("role", "img");
    wm.setAttribute("aria-label", sd ? "No work across the fleet yet" : "No open work — every session is clear");
    list.appendChild(wm);
    emptyShown = true;
  } else {
    emptyShown = false;
  }
}

// The Fleet controls live in a DOCKED bottom bar — its own dedicated rectangle in normal flow (#fleet-foot),
// NOT a floating overlay (the user 2026-06-29). Left side: the view controls — "Group by session" (off = the
// flat chronological list) + Collapse-all / Expand-all. Right side: the recency-cutoff slider ("≤ <age>",
// logarithmic 1 minute … 1 month) beside the "Show completed" checkbox. Mounted once into #fleet-foot.
function mountControls() {
  const foot = document.getElementById("fleet-foot");
  if (!foot || foot.dataset.mounted === "1") return;     // mount once into the docked footer
  foot.dataset.mounted = "1";
  foot.replaceChildren();

  // ── LEFT cluster: grouping + collapse/expand ──
  const left = el("div", "fl-foot-left");
  const grpLbl = el("label", "fl-foot-toggle") as HTMLLabelElement;
  const grp = document.createElement("input");
  grp.type = "checkbox"; grp.checked = isGrouped(); grp.style.cursor = "pointer";
  grp.title = "Group goals under their session. Off = one chronological list across every session, each tagged with its session.";
  grp.addEventListener("change", () => { setGrouped(grp.checked); render(); });
  grpLbl.appendChild(grp);
  grpLbl.appendChild(document.createTextNode("Group"));   // short label; the tooltip carries the full meaning
  // Collapse / Expand are STICKY toggle buttons: click to enter the mode (button "stays clicked"), click
  // again to leave, or fold something by hand to release it. id'd so paintFoldButtons can light the active one.
  const collapse = el("button", "fl-foot-btn"); collapse.id = "fl-collapse";
  collapse.textContent = "Collapse"; collapse.title = "Keep everything collapsed — folds every session + goal and stays that way as work streams in (click again, or fold something by hand, to release)";
  collapse.addEventListener("click", () => { collapse.classList.add("romp-acted"); setTimeout(() => collapse.classList.remove("romp-acted"), 280); toggleFoldMode("collapse"); });
  const expand = el("button", "fl-foot-btn"); expand.id = "fl-expand";
  expand.textContent = "Expand"; expand.title = "Keep everything expanded — opens every goal and stays that way as work streams in (click again, or fold something by hand, to release)";
  expand.addEventListener("click", () => { expand.classList.add("romp-acted"); setTimeout(() => expand.classList.remove("romp-acted"), 280); toggleFoldMode("expand"); });
  left.append(grpLbl, collapse, expand);

  // ── RIGHT cluster: recency cutoff slider + Show completed ──
  const right = el("div", "fl-foot-right");
  const lab = el("span");
  lab.style.cssText = "min-width:32px;text-align:right;font-variant-numeric:tabular-nums;flex:0 0 auto";
  const sl = document.createElement("input");
  // REVERSED direction + blue fill on the RIGHT (the user 2026-06-29): dragging RIGHT shows only MORE-RECENT
  // sessions (tighter window), LEFT shows everything. Done with a horizontal flip (scaleX(-1)) of the native
  // slider rather than mirroring the VALUE — so the accent (blue) fill, which a native range paints on the
  // LOW side, lands on the RIGHT. cutoffPos keeps its meaning (1000 = show all) and the value maps directly.
  sl.type = "range"; sl.min = "0"; sl.max = "1000"; sl.step = "1"; sl.value = String(cutoffPos());
  sl.style.cssText = "width:72px;min-width:48px;cursor:pointer;transform:scaleX(-1)";   // compact; shrinks on a narrow pane
  (sl.style as CSSStyleDeclaration & { accentColor: string }).accentColor = "var(--accent, #9cd2ff)";
  sl.title = "Drag RIGHT to show only more-recent sessions (down to the last minute); LEFT shows everything — logarithmic";
  const paint = () => { lab.textContent = "≤ " + fmtAge(cutoffSecs()); };
  refreshCutoffLabel = paint;   // render() refreshes the label when the adaptive max shifts with the fleet
  sl.addEventListener("input", () => { setCutoffPos(parseInt(sl.value, 10)); paint(); render(); });
  paint();
  right.appendChild(lab); right.appendChild(sl);
  // "Show completed" checkbox on the SAME row (no divider — the cluster gap separates them).
  const lbl = el("label", "fl-foot-toggle") as HTMLLabelElement;
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = showDone();
  cb.style.cursor = "pointer";
  cb.addEventListener("change", () => { setShowDone(cb.checked); render(); });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode("Show completed"));
  right.appendChild(lbl);

  foot.append(left, right);
}

window.addEventListener("message", (e: MessageEvent) => {
  const m = e.data;
  if (!m || m.type !== "feed") return;               // Fleet rides the FEED payload (proven channel); reads its `ledgers`
  // "loaded" means the kernel actually BUILT the fleet's ledgers (the key is present, even if []) — NOT merely
  // that some feed message arrived. A feed push can reach us before the (cold) ledger build finishes; treating
  // that as loaded would drop the loader onto an empty pane (the user 2026-06-29). Until ledgers land, keep the
  // loader up (render() bails, leaving the list empty so _pane_spin holds).
  if (!Array.isArray(m.ledgers)) return;
  loaded = true;
  sessions = m.ledgers as FleetSession[];
  provCards = (Array.isArray(m.asks) ? m.asks : [])
    .filter((a: any) => a && a.provisional && a.sid)
    .map((a: any) => ({ sid: a.sid, name: a.name || "", color: a.color || null, text: a.text || "Working…" }));
  render();
});
window.addEventListener("storage", (e: StorageEvent) => { if (e.key === "romp:settings") render(); });   // colormap change → recolour

// Fleet-list clicks are DELEGATED to the stable #fleet-list (installed once). render() does
// `#fleet-list`.replaceChildren() on every feed push, so a handler hung on a rebuilt row/header/caret is
// destroyed mid-click and the click is dropped — delegation on the container that survives the rebuild fixes
// it. Each node declares its data-act + data-sid/data-nid (see render()). See ./actions and CLAUDE.md ## Design.
(() => {
  const list = document.getElementById("fleet-list");
  if (!list) return;
  delegate(list, {
    open: (el) => { const sid = el.dataset.sid; if (sid) openSession(sid); },
    goprompt: (el) => fleetNavTo(el, "prompt"),   // text/open-mark zone → the asking message (like the modal)
    gowork: (el) => fleetNavTo(el, "work"),        // resolved mark/time zone → where it resolved (like the modal)
    sessfold: (el) => {                                  // ▶/▼ on the session head → collapse/expand its whole tree
      const sid = el.dataset.sid;
      if (!sid) return;
      bakeFoldMode();   // a hand-fold leaves the sticky Collapse/Expand mode, preserving the current look
      if (sessFolded.has(sid)) sessFolded.delete(sid); else sessFolded.add(sid);
      render();
    },
    fold: (el) => {
      const sid = el.dataset.sid, nid = el.dataset.nid;
      if (!sid || !nid) return;
      bakeFoldMode();   // a hand-fold leaves the sticky Collapse/Expand mode, preserving the current look
      const k = fkey(sid, nid);
      if (el.dataset.folded === "1") { expanded.add(k); folded.delete(k); } else { folded.add(k); expanded.delete(k); }
      render();
    },
  });
})();

// Wire the top search bar (the user 2026-06-29): typing filters the fleet to sessions whose NAME matches.
// The input lives in the page body (kernel _fleet_page); installed once, re-renders on each keystroke.
// The trailing ✕ clears it (shown only while there's text), like any search bar — refocuses the input so you
// can keep typing.
(() => {
  const search = document.getElementById("fleet-search") as HTMLInputElement | null;
  const clear = document.getElementById("fleet-search-clear") as HTMLButtonElement | null;
  if (!search) return;
  const syncClear = () => { if (clear) clear.hidden = search.value === ""; };
  search.addEventListener("input", () => { searchQuery = search.value; syncClear(); render(); });
  clear?.addEventListener("click", () => { search.value = ""; searchQuery = ""; syncClear(); search.focus(); render(); });
  syncClear();
})();

mountControls();
render();
vscodeApi?.postMessage({ type: "ready" });   // ask the kernel to push the initial fleet state (like feed/timeline)

// Hold the romp loader up until the ledgers actually land (the user 2026-06-29: "show the loading thing until
// the tasks are ready to render"). The shared _pane_spin loader has an 8s backstop that would otherwise hide
// it over an EMPTY pane while a cold kernel is still building every session's ledger (which can take longer
// than 8s for a big fleet) — leaving a blank gap before the tasks paint. So while we're not loaded yet, keep
// re-asserting the loader, beating that backstop; stop the instant the data arrives (event-based via `loaded`).
const _keepLoader = setInterval(() => {
  if (loaded) { clearInterval(_keepLoader); return; }
  const spin = document.getElementById("pane-spin");
  if (spin) spin.classList.remove("gone");
}, 1000);

export {};   // module scope — keep its globals off feed.ts's (a global script)
