// "Artifacts": a session's files as its own column of the dashboard (plans/artifacts-pane.md, the user 2026-09-19; the second
// pass 2026-09-20, section 9). A picker at the top names the session; under it every file that was put into that session's
// thread, as a list and, for images, a grid of BIG thumbnails, so a run of plots can be opened and cycled through large. An
// on-top read of what already happened, by the kernel's deterministic rules (the edit tools' inputs, the paths the chat linked
// and rendered from the prose, a drop's saved path); nothing is injected into any session and nothing is written.
//
// The picker lists exactly the sessions OPEN in the chat panes of this dashboard: the shell's {romp:'chatTabs', tabs} broadcast,
// the union of every chat column's strip (a remote tab under its host id, which is what routes the listing to the kernel that
// owns it). Its button and its rows wear the strip's own label (host-prefix.ts sessionLabelNodes) in a ctx-menu card. Beside it
// the lock (the Sessions pane's padlock): unlocked, the pane shows whatever came last, a pick or the chat's most recently
// selected tab ({romp:'activeChat'} from the shell, {type:'activeChat'} from the kernel on ready); locked, it stays on the
// pick; only the lock button changes the lock (the pure machine: artifacts-model.ts nextSelection).
//
// The kernel traffic is request and response on this socket, routed to the kernel that owns the session by federation.js
// (loaded by the page, never imported): listArtifacts for the listing, each answer carrying the reqId it was asked with, so a
// slow answer landing after a newer selection is dropped, never rendered; and watchArtifacts, the one session this pane
// shows, which the owning kernel's pusher cycle answers with artifactsChanged {sid, version} when that session's transcript
// grew: the pane re-asks (on screen) or marks the listing stale (off screen) and re-asks when shown. No Refresh control, no
// polling. Thumbnails and the large view read the token-authed /file route with the session's sid (preview.ts fileUrl,
// host-routed for a remote session), never a new file server. The large view is the chat's lightbox (openLightbox) with its
// arrows stepping this pane's image sequence (setLightboxNav), plus one control that sends the picture to the Files pane
// through the shell's viewFile relay; a row click walks the chat's route ladder (file-route.ts). A page opened with no shell
// has no tabs to list and falls back to the picker's list (requestSessions), the first landing's behaviour.
import { fileUrl, openLightbox, setLightboxNav, canPreview } from "./preview";
import { gridItems, cycleEntries, viaWord, rowRoute, ago, nextSelection, normalizeTabs, shownRow, type ArtifactItem, type TabRow, type Selection, type SelectionEvent } from "./artifacts-model";
import { initFileView, openFileView } from "./file-view";
import { delegate } from "./actions";
import { applyTheme } from "./theme";
import { loadSettings, installSettingsSync, onExternalSettingsChange } from "./settings";
import { sessionLabelNodes } from "./host-prefix";
import { menuCard, showMenuCard, closeContextMenu } from "./ctx-menu";

interface Listing { items: ArtifactItem[]; capped: boolean; max: number; error: string; sid: string }

const SEL_KEY = "romp:artifacts:sid";
const LOCK_KEY = "romp:artifacts:lock";
const vscodeApi = typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;
const framed = window.parent && window.parent !== window;   // a pane of a dashboard (the shell tells it tabs and the active chat), or a page opened alone

let tabs: TabRow[] = [];                                    // the open tabs of the chat panes (the shell's union), the picker's rows
let sel: Selection = { sid: readSelected(), locked: readLock() };
let listing: Listing | null = null;
let loading = false;
let stale = false;                                          // a growth signal arrived while the pane was off screen: re-ask when shown
let reqSeq = 0;
let lastReq = 0;
let watched: string | null = null;                          // the session the kernel is told to watch (one per socket)
let panesOn: Record<string, boolean> = {};
let panesAvail: Record<string, boolean> = {};

function readSelected(): string | null { try { return localStorage.getItem(SEL_KEY); } catch { return null; } }
function writeSelected(sid: string | null): void { try { if (sid) localStorage.setItem(SEL_KEY, sid); else localStorage.removeItem(SEL_KEY); } catch { /* storage may be denied */ } }
function readLock(): boolean { try { return localStorage.getItem(LOCK_KEY) === "1"; } catch { return false; } }
function writeLock(on: boolean): void { try { localStorage.setItem(LOCK_KEY, on ? "1" : "0"); } catch { /* storage may be denied */ } }
function el(tag: string, cls?: string): HTMLElement { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
function onScreen(): boolean { return framed ? panesOn.artifacts === true : true; }

function ask(msg: Record<string, unknown>): void { vscodeApi?.postMessage(msg); }
function requestSessions(): void { ask({ type: "requestSessions" }); }
function requestListing(): void {
  stale = false;
  if (!sel.sid) { listing = null; paint(); return; }
  lastReq = ++reqSeq; loading = true; paint();
  ask({ type: "listArtifacts", sid: sel.sid, reqId: lastReq });
}
// the ONE watched session: the previous one unwatched on its own kernel (federation routes the frame by its sid), the new one watched
function watch(sid: string | null): void {
  if (sid === watched) return;
  if (watched) ask({ type: "watchArtifacts", sid: watched, unwatch: true });
  if (sid) ask({ type: "watchArtifacts", sid });
  watched = sid;
}
// every change of the selection goes through the machine; a changed session drops the listing, moves the watch and asks anew
function apply(ev: SelectionEvent): void {
  const next = nextSelection(sel, ev);
  const changed = next.sid !== sel.sid;
  sel = next; writeSelected(sel.sid); writeLock(sel.locked);
  if (changed) { listing = null; watch(sel.sid); requestListing(); return; }
  paint();
}

// ── the paint: the bar (the lock, the picker, the count), the grid, the list ─────────────────────────────────────────
function lockSvg(on: boolean): SVGElement {
  // the Sessions pane's padlock, byte for byte (romp-timeline-view.js _drawLockToggle): the body, then the seated (locked) or swung-out (unlocked) shackle
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "0 0 16 14"); svg.setAttribute("aria-hidden", "true");
  const body = document.createElementNS(NS, "rect"); body.setAttribute("x", "3"); body.setAttribute("y", "6.2"); body.setAttribute("width", "8"); body.setAttribute("height", "5.6"); body.setAttribute("rx", "1.2");
  const shackle = document.createElementNS(NS, "path"); shackle.setAttribute("d", on ? "M4.8 6.2 V4.4 a2.2 2.2 0 0 1 4.4 0 V6.2" : "M9.4 6.2 V5.3 A2.4 2.4 0 0 1 13.6 3.7");
  svg.append(body, shackle);
  return svg;
}
function paint(): void {
  const root = document.getElementById("artifacts-root");
  if (!root) return;
  root.replaceChildren();
  const bar = el("div", "art-bar");
  const lock = el("button", "art-lock" + (sel.locked ? " on" : "")) as HTMLButtonElement; lock.dataset.act = "art-lock"; lock.id = "art-lock";
  lock.setAttribute("aria-pressed", sel.locked ? "true" : "false");
  lock.title = sel.locked ? "Locked to this session. Click to follow the chat's active tab again." : "Following the chat's active tab. Click to lock the pane to this session.";
  lock.appendChild(lockSvg(sel.locked));
  const pick = el("button", "art-pick") as HTMLButtonElement; pick.dataset.act = "art-pick"; pick.id = "art-pick"; pick.title = "the session whose files are listed";
  pick.setAttribute("aria-haspopup", "menu");
  const shown = shownRow(tabs, sel.sid);
  if (shown.row) {
    pick.append(...sessionLabelNodes(shown.row.name, shown.row.id, shown.row.color));
    if (!shown.open) { const no = el("span", "art-not-open"); no.textContent = "not open"; pick.appendChild(no); }
  } else { const none = el("span", "art-none-label"); none.textContent = tabs.length ? "Choose a session…" : (framed ? "No chat tab is open" : "No sessions yet"); pick.appendChild(none); }
  const chev = el("span", "art-chev"); chev.textContent = "▾"; pick.appendChild(chev);
  const count = el("span", "art-count");
  if (listing && !listing.error) count.textContent = listing.capped ? "the newest " + listing.max + " files of more" : listing.items.length + (listing.items.length === 1 ? " file" : " files");
  const noteEl = el("span", "art-note"); noteEl.id = "art-note";   // what the last click could not do (a kind the viewer does not show); cleared by the next render
  bar.append(lock, pick, count, noteEl);
  const body = el("div", "art-body");
  if (!sel.sid) { const e = el("div", "art-empty"); e.textContent = framed ? "Select a chat tab, or pick a session, to see the files its thread wrote, showed and received." : "Pick a session to see the files its thread wrote, showed and received."; body.appendChild(e); }
  else if (loading && !listing) { const e = el("div", "art-empty"); e.textContent = "Reading the thread…"; body.appendChild(e); }
  else if (listing && listing.error) { const e = el("div", "art-err"); e.textContent = listing.error; body.appendChild(e); }
  else if (listing && !listing.items.length) { const e = el("div", "art-empty"); e.textContent = "This thread has put no file in yet."; body.appendChild(e); }
  else if (listing) {
    const imgs = gridItems(listing.items);
    if (imgs.length && canPreview()) {
      const grid = el("div", "art-grid");
      imgs.forEach((it, i) => {
        const cell = el("div", "art-thumb"); cell.dataset.act = "art-open"; cell.dataset.i = String(i); cell.title = it.path;
        const img = document.createElement("img"); img.loading = "lazy"; img.src = fileUrl(it.path, sel.sid); img.alt = it.name;
        const cap = el("div", "art-cap"); cap.textContent = it.name;
        cell.append(img, cap); grid.appendChild(cell);
      });
      body.appendChild(grid);
    }
    const list = el("div", "art-list");
    listing.items.forEach((it, i) => {
      const row = el("div", "art-row" + (it.exists ? "" : " missing") + (it.refused ? " refused" : "")); row.dataset.act = "art-row"; row.dataset.i = String(i);
      row.title = it.refused ? it.path + " (" + it.refused + ")" : it.path;
      const name = el("span", "art-name"); name.textContent = it.name;
      const dir = el("span", "art-dir"); dir.textContent = it.path.slice(0, it.path.length - it.name.length).replace(/\/$/, "");
      const via = el("span", "art-via"); via.textContent = viaWord(it.via);
      const age = el("span", "art-age"); age.textContent = it.t ? ago(Date.now() / 1000 - it.t) : "";
      row.append(name, dir, via, age); list.appendChild(row);
    });
    body.appendChild(list);
  }
  root.append(bar, body);
}

// ── the picker's card: the open tabs, one row per session in the strip's label, the shown one marked ────────────────
function openPicker(anchor: HTMLElement): void {
  closeContextMenu();
  const card = menuCard({ className: "art-picker", id: "art-picker" });
  if (!tabs.length) {
    const none = el("div", "ctx-item art-none"); none.setAttribute("role", "menuitem"); none.tabIndex = -1;
    const b = el("span", "ctx-item-body"); b.textContent = framed ? "No chat tab is open" : "No sessions yet"; none.appendChild(b); card.appendChild(none);
  }
  for (const t of tabs) {
    const row = el("div", "ctx-item" + (t.id === sel.sid ? " current" : "")); row.setAttribute("role", "menuitem"); row.tabIndex = -1; row.dataset.sid = t.id; row.title = t.id;
    const b = el("span", "ctx-item-body"); b.append(...sessionLabelNodes(t.name, t.id, t.color)); row.appendChild(b);
    row.addEventListener("click", () => { const id = t.id; closeContextMenu(); apply({ type: "pick", id }); });   // a pick never changes the lock (9.5)
    card.appendChild(row);
  }
  const r = anchor.getBoundingClientRect();
  showMenuCard(card, r.left, r.bottom + 2, {});
}

// ── the clicks, delegated once on the root ───────────────────────────────────────────────────────────────────────────
function openLarge(i: number): void {
  if (!listing || !sel.sid) return;
  const imgs = gridItems(listing.items); const it = imgs[i]; if (!it) return;
  openLightbox(it.path, sel.sid);
  // the one extra control: send this picture to the Files pane's viewer (the shell's viewFile relay), hidden where no
  // Files control exists; the lightbox's bar is the file viewer's bar, so the button wears its dress
  if (framed && panesAvail.files !== false) {
    const bar = document.querySelector("#romp-lightbox .fileview-acts");
    if (bar && !bar.querySelector(".art-send")) {
      const b = el("button", "fileview-btn art-send") as HTMLButtonElement; b.textContent = "Files pane"; b.title = "open this picture in the Files pane";
      b.onclick = (ev) => { ev.stopPropagation(); const cur = document.querySelector<HTMLImageElement>("#romp-lightbox .romp-lightbox-img"); const p = cur && cur.alt ? cur.alt : it.path;
        window.parent.postMessage({ romp: "viewFile", path: p, sid: sel.sid, pane: "pane", frag: null }, "*"); };
      bar.insertBefore(b, bar.firstChild);
    }
  }
}
function note(text: string): void { const n = document.getElementById("art-note"); if (n) n.textContent = text; }
function openRow(i: number): void {
  if (!listing || !sel.sid) return;
  const it = listing.items[i]; if (!it || it.refused) return;
  if (it.kind === "other") { note("The viewer cannot show " + it.name + ": not a kind it renders."); return; }   // an ordinary kind of the listing, no viewer for it (the design's section 2)
  if (it.kind === "image" && it.exists && canPreview()) { openLarge(gridItems(listing.items).findIndex((g) => g.path === it.path)); return; }
  if (rowRoute(framed, panesOn, panesAvail) === "pane") window.parent.postMessage({ romp: "viewFile", path: it.path, sid: sel.sid, pane: "pane", frag: null }, "*");
  else openFileView(it.path, sel.sid, {});
}

// ── boot ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
applyTheme(document, loadSettings()); installSettingsSync(); onExternalSettingsChange((st) => applyTheme(document, st));
initFileView((m) => vscodeApi?.postMessage(m));   // the shared viewer's poster: its ops (fileGitLink, saveFile) ride this socket
setLightboxNav((sid) => { const cur = sel.sid; return listing && cur && sid === cur ? cycleEntries(listing.items, cur) : []; });
const root = document.getElementById("artifacts-root");
if (root) delegate(root, {
  "art-lock": () => apply({ type: "toggleLock" }),
  "art-pick": (e) => openPicker(e as HTMLElement),
  "art-open": (e) => openLarge(Number((e as HTMLElement).dataset.i)),
  "art-row": (e) => openRow(Number((e as HTMLElement).dataset.i)),
});
window.addEventListener("message", (ev) => {
  const m = ev.data;
  if (!m) return;
  if (m.romp === "panes") {
    panesOn = m.on || {}; panesAvail = m.avail || {};
    if (onScreen() && sel.sid && (stale || (!listing && !loading))) requestListing();   // shown again: a stale listing (a growth while off screen) is re-asked here
    return;
  }
  if (m.romp === "chatTabs") { tabs = normalizeTabs(m.tabs); apply({ type: "tabsChanged", tabs }); return; }   // the shell's union of the chat columns' open tabs (9.2)
  if (m.romp === "activeChat" || m.type === "activeChat") { apply({ type: "activeChat", id: typeof m.id === "string" && m.id ? m.id : null }); return; }   // the shell's relay, or the kernel's frame on ready (9.5)
  if (m.type === "artifactsChanged") {
    if (m.sid !== sel.sid) return;   // a signal for a session no longer shown (a stale watch on another kernel): nothing to do
    if (onScreen()) requestListing(); else stale = true;
    return;
  }
  if (m.type === "sessionList" && Array.isArray(m.items)) {
    if (framed) return;   // a dashboard pane lists the chat's open tabs, never the picker's thirty days
    tabs = normalizeTabs(m.items.map((s: any) => ({ id: s.id, name: s.name || s.id, color: s.color || null })));
    paint(); if (sel.sid && !listing && !loading) requestListing();
    return;
  }
  if (m.type === "artifactsListing") {
    if (m.reqId !== lastReq || m.sid !== sel.sid) return;   // a slow answer for an earlier selection: dropped, never rendered
    loading = false;
    listing = { items: Array.isArray(m.items) ? m.items : [], capped: !!m.capped, max: Number(m.max) || 500, error: String(m.error || ""), sid: String(m.sid || "") };
    paint();
  }
});
paint();
vscodeApi?.postMessage({ type: "ready" });   // the handshake every pane sends (files.ts): the kernel answers a pane of a dashboard window with the window's active chat (9.5), so a reloaded pane knows the focused session before any switch
if (!framed) requestSessions();
watch(sel.sid);
if (sel.sid) requestListing();
