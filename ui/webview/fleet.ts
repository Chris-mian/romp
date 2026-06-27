// Fleet — a by-SESSION view that mirrors the chat's LEDGER BOX (the user 2026-06-23): each live session, then
// its goal tree beneath it — collapsible checkmark nodes, recency-coloured "(Xm ago)" times, the same .ledger-*
// look. It rides the FEED payload (connects app=feed, reads its `ledgers` slice — one per-session build_session
// ledger, the SAME tree the ledger box draws) — the proven feed channel. Completed top goals hide behind a
// bottom "Show completed" checkbox (default off). The recency colour helpers are copied verbatim from render.ts
// so the colours are IDENTICAL to the ledger box.
import { delegate } from "./actions";

type Color = { bg: string; fg: string } | null;
interface LedgerNode {
  id: string; text: string; depth: number; done: boolean; blocked: boolean;
  t: number; mt?: number; current: boolean; derived?: boolean; recent?: boolean;
  cleared?: boolean; onpath?: boolean; children?: string[];
  summary?: string | null; blockSummary?: string | null; _rec?: number;
}
interface Ledger { summary?: string; tree: LedgerNode[]; current?: { t?: number } | null; }
interface FleetSession { sid: string; name: string; color: Color; status?: { state?: string } | null; ledger?: Ledger | null; }

const vscodeApi =
  typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let sessions: FleetSession[] = [];
const DONE_KEY = "romp:fleetShowDone";
function showDone(): boolean { try { return localStorage.getItem(DONE_KEY) === "1"; } catch { return false; } }
function setShowDone(on: boolean) { try { localStorage.setItem(DONE_KEY, on ? "1" : "0"); } catch { /* ignore */ } }

// Recency cutoff (the user 2026-06-27): a LOGARITHMIC slider hides sessions whose freshest activity is older
// than the window. Stored as a 0..1000 slider position; cutoffSecs() maps it log-uniformly from 1 minute to
// 1 month, so each pixel covers a constant RATIO of time. Default = max (1 month, most inclusive).
const CUTOFF_KEY = "romp:fleetCutoffPos";
const CUT_MIN = 60, CUT_MAX = 30 * 86400;            // 1 minute … 1 month (seconds)
function cutoffPos(): number {
  try { const v = parseInt(localStorage.getItem(CUTOFF_KEY) || "", 10); return Number.isFinite(v) ? Math.max(0, Math.min(1000, v)) : 1000; }
  catch { return 1000; }
}
function setCutoffPos(p: number) { try { localStorage.setItem(CUTOFF_KEY, String(p)); } catch { /* ignore */ } }
function cutoffSecs(): number { return CUT_MIN * Math.pow(CUT_MAX / CUT_MIN, cutoffPos() / 1000); }   // log-uniform 1m…1mo
function fmtAge(s: number): string {
  if (s < 3600) return Math.round(s / 60) + "m";
  if (s < 86400) return Math.round(s / 3600) + "h";
  if (s < CUT_MAX - 1) return Math.round(s / 86400) + "d";
  return "1mo";
}
const folded = new Set<string>(), expanded = new Set<string>();   // fold state, keyed "sid\0nodeId"
const fkey = (sid: string, id: string) => sid + "\0" + id;

const sumOpen = new Set<string>();   // ⊕ distiller-summary panels currently expanded, keyed fkey(sid,nodeId)
const sessFolded = new Set<string>();   // sessions whose WHOLE task tree is collapsed, keyed by sid (the user 2026-06-24)

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

function render() {
  const list = document.getElementById("fleet-list");
  if (!list) return;
  list.replaceChildren();
  const sd = showDone();
  const now = Math.floor(Date.now() / 1000);
  let any = false;

  const cutoff = cutoffSecs();
  for (const s of sessions) {
    const tree = s.ledger?.tree || [];
    if (!tree.length) continue;
    stampSubtreeRecency(tree, s.ledger?.current || null);
    // recency cutoff (the user 2026-06-27): skip a session whose freshest activity (rolled-up node recency
    // or its live current-node time) is older than the slider's window.
    const freshest = Math.max(s.ledger?.current?.t || 0, ...tree.map(nodeRecency));
    if (freshest && (now - freshest) > cutoff) continue;
    const byId = new Map(tree.map((n) => [n.id, n] as const));
    const roots = tree.filter((n) => n.depth === 0);
    // open = a top goal that's not done and not crossed off; "show completed" reveals the rest
    const visibleRoots = sd ? roots : roots.filter((n) => !n.done && !n.cleared);
    if (!visibleRoots.length) continue;
    any = true;

    const sec = el("div", "fl-session");
    const head = el("div", "fl-head");
    // session-level collapse caret (the user 2026-06-24): folds this session's WHOLE task tree. Its OWN
    // data-act="sessfold" (the innermost data-act in the head) so clicking it folds WITHOUT opening the
    // session — only a click on the name/rest of the head (data-act="open") jumps in.
    const sfolded = sessFolded.has(s.sid);
    const caret = el("span", "fl-caret");
    caret.textContent = sfolded ? "▶" : "▼";
    caret.title = sfolded ? "expand this session's tasks" : "collapse this session's tasks";
    caret.dataset.act = "sessfold"; caret.dataset.sid = s.sid;
    caret.style.cssText = "flex:0 0 auto;cursor:pointer;color:var(--vscode-descriptionForeground,#9a9a9a);"
      + "font-size:9px;width:13px;text-align:center;user-select:none";
    head.appendChild(caret);
    if (s.status?.state === "working") head.appendChild(el("span", "fl-workdot"));
    const nm = el("span", "fl-name");
    nm.textContent = s.name;
    if (s.color?.bg) nm.style.color = s.color.bg;
    head.appendChild(nm);
    head.title = "Open this session";
    head.dataset.act = "open"; head.dataset.sid = s.sid;   // click-safe: action lives on the #fleet-list delegate
    sec.appendChild(head);

    const treeBox = el("div", "ledger-tree");
    const curT = s.ledger?.current?.t;
    const renderNode = (n: LedgerNode, depth: number) => {
      const expandable = !!(n.children && n.children.length);
      const defaultFold = !!n.done && (depth === 0 || !n.onpath);   // a finished top folds by default
      const isFolded = expandable && (folded.has(fkey(s.sid, n.id)) || (defaultFold && !expanded.has(fkey(s.sid, n.id))));
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
      // .lz-nav → the pointer cursor (from styles.css), so the checkbox / text / time read as clickable — the
      // same per-zone affordance the ledger box has (the user 2026-06-24). The whole row still opens the
      // session (row data-act=open); these zones carry no data-act, so a click on them bubbles up to it.
      const mark = el("span", "ledger-tmark lz-nav");
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
      txt.textContent = n.text;
      txt.title = n.text;            // the full goal text on hover (it can wrap/clip in the narrow Fleet pane)
      // ⊕ distiller-summary expander (parity with the ledger box): the takeaway (done) / decision brief
      // (blocked) on its own line. data-act=sum so the #fleet-list delegate toggles it instead of opening the
      // session; state in sumOpen, keyed per session+node so each row remembers independently.
      const sumText = (n.summary || n.blockSummary || "").trim();
      const isSumOpen = sumOpen.has(fkey(s.sid, n.id));
      let sumToggle: HTMLElement | null = null;
      if (sumText) {
        sumToggle = el("span", "ledger-tsum-toggle nav");
        sumToggle.textContent = isSumOpen ? "⊖" : "⊕";
        sumToggle.title = isSumOpen ? "hide the distiller's summary" : "show the distiller's summary";
        sumToggle.dataset.act = "sum"; sumToggle.dataset.sid = s.sid; sumToggle.dataset.nid = n.id;
      }
      const time = el("span", "ledger-ttime");
      if (n.current && curT) {
        time.textContent = `(${agehms(now - curT)})`; time.style.color = ageColorReadable(now - curT);
      } else if (n.done && nodeRecency(n)) {
        const dt = now - nodeRecency(n);
        time.textContent = `(${agehms(dt)} ago)`; time.style.color = ageColorReadable(dt);
        txt.style.color = ageColorReadable(dt);                 // done text matches its rolled-up recency colour
      }
      if (time.textContent) time.classList.add("lz-nav");
      // group the hover highlight like the ledger: a resolved node's checkbox + time light together, the text
      // on its own; an open node's checkbox + text are one block, the time on its own (the user 2026-06-24).
      if (n.done || n.blocked) { linkHover([txt]); linkHover(time.textContent ? [mark, time] : [mark]); }
      else { linkHover([mark, txt]); if (time.textContent) linkHover([time]); }
      row.appendChild(tri); row.appendChild(mark); row.appendChild(txt);
      if (sumToggle) row.appendChild(sumToggle);
      row.appendChild(time);
      row.dataset.act = "open"; row.dataset.sid = s.sid;   // click-safe: action lives on the #fleet-list delegate
      treeBox.appendChild(row);
      if (sumText && isSumOpen) {                            // the ⊕'s expanded panel: the summary on its own line
        const det = el("div", "ledger-tsum");
        det.textContent = sumText;
        det.style.paddingLeft = (4 + depth * 15 + 22) + "px";   // align under the text, past the mark column
        treeBox.appendChild(det);
      }
      if (expandable && !isFolded) for (const cid of n.children!) { const c = byId.get(cid); if (c) renderNode(c, depth + 1); }
    };
    if (!sfolded) { for (const r of visibleRoots) renderNode(r, 0); sec.appendChild(treeBox); }   // folded → head only
    list.appendChild(sec);
  }

  if (!any) {
    const empty = el("div", "fl-empty");
    empty.textContent = sd ? "No work across the fleet yet." : "No open work — every session is clear.";
    list.appendChild(empty);
  }
}

// "Show completed" sits as a small FLOATING chip at the BOTTOM-right of the Fleet view (the user 2026-06-24),
// matching the feed's own bottom-right controls so the two panes are consistent — not a footer bar. (The way
// BACK to chat is the rail's "Chat" toggle in the shell, so no footer "← Chat" is needed.)
function mountChip() {
  const foot = document.getElementById("fleet-foot");
  if (foot) foot.style.display = "none";                 // the old footer bar is gone
  if (document.getElementById("fl-showdone")) return;    // mount once
  const lbl = el("label", "fl-showdone") as HTMLLabelElement;
  lbl.id = "fl-showdone";
  lbl.style.cssText = "position:fixed;bottom:8px;right:10px;z-index:20;display:inline-flex;align-items:center;gap:6px;"
    + "cursor:pointer;user-select:none;font-size:11.5px;color:var(--vscode-descriptionForeground,#9a9a9a);"
    + "background:rgba(40,40,42,0.92);border:1px solid rgba(255,255,255,0.12);border-radius:6px;padding:3px 9px";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = showDone();
  cb.style.cursor = "pointer";
  cb.addEventListener("change", () => { setShowDone(cb.checked); render(); });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode("Show completed"));
  document.body.appendChild(lbl);
}

// Recency-cutoff slider (the user 2026-06-27): a floating chip just ABOVE "Show completed", with a label
// ("≤ 2d") + a logarithmic range slider (1 minute … 1 month). Dragging filters the fleet live and persists.
function mountCutoff() {
  if (document.getElementById("fl-cutoff")) return;      // mount once
  const box = el("div");
  box.id = "fl-cutoff";
  box.style.cssText = "position:fixed;bottom:38px;right:10px;z-index:20;display:inline-flex;align-items:center;gap:8px;"
    + "user-select:none;font-size:11.5px;color:var(--vscode-descriptionForeground,#9a9a9a);"
    + "background:rgba(40,40,42,0.92);border:1px solid rgba(255,255,255,0.12);border-radius:6px;padding:3px 9px";
  const lab = el("span");
  lab.style.cssText = "min-width:42px;text-align:right;font-variant-numeric:tabular-nums";
  const sl = document.createElement("input");
  sl.type = "range"; sl.min = "0"; sl.max = "1000"; sl.step = "1"; sl.value = String(cutoffPos());
  sl.style.cssText = "width:110px;cursor:pointer";
  (sl.style as CSSStyleDeclaration & { accentColor: string }).accentColor = "var(--accent, #9cd2ff)";
  sl.title = "Include sessions active within this window — logarithmic, 1 minute … 1 month";
  const paint = () => { lab.textContent = "≤ " + fmtAge(cutoffSecs()); };
  sl.addEventListener("input", () => { setCutoffPos(parseInt(sl.value, 10)); paint(); render(); });
  paint();
  box.appendChild(lab); box.appendChild(sl);
  document.body.appendChild(box);
}

window.addEventListener("message", (e: MessageEvent) => {
  const m = e.data;
  if (!m || m.type !== "feed") return;               // Fleet rides the FEED payload (proven channel); reads its `ledgers`
  sessions = Array.isArray(m.ledgers) ? (m.ledgers as FleetSession[]) : [];
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
    sessfold: (el) => {                                  // ▶/▼ on the session head → collapse/expand its whole tree
      const sid = el.dataset.sid;
      if (!sid) return;
      if (sessFolded.has(sid)) sessFolded.delete(sid); else sessFolded.add(sid);
      render();
    },
    sum: (el) => {                                       // ⊕/⊖ → toggle this node's distiller-summary panel
      const sid = el.dataset.sid, nid = el.dataset.nid;
      if (!sid || !nid) return;
      const k = fkey(sid, nid);
      if (sumOpen.has(k)) sumOpen.delete(k); else sumOpen.add(k);
      render();
    },
    fold: (el) => {
      const sid = el.dataset.sid, nid = el.dataset.nid;
      if (!sid || !nid) return;
      const k = fkey(sid, nid);
      if (el.dataset.folded === "1") { expanded.add(k); folded.delete(k); } else { folded.add(k); expanded.delete(k); }
      render();
    },
  });
})();

mountChip();
mountCutoff();
render();
vscodeApi?.postMessage({ type: "ready" });   // ask the kernel to push the initial fleet state (like feed/timeline)

export {};   // module scope — keep its globals off feed.ts's (a global script)
