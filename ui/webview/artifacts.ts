// "Artifacts": a session's files as its own column of the dashboard (plans/artifacts-pane.md, the user 2026-09-19).
// A selector at the top names the session; under it every file that was put into that session's thread, as a list and,
// for images, a grid of BIG thumbnails, so a run of plots can be opened and cycled through large. An on-top read of what
// already happened, by the kernel's deterministic rules (the edit tools' inputs, the paths the chat linked and rendered
// from the prose, a drop's saved path); nothing is injected into any session and nothing is written.
//
// The pane is NOT a feed consumer: like the Files pane it receives no pushed view. Its two kernel ops are request and
// response on this socket, routed to the kernel that owns the session by federation.js (loaded by the page, never
// imported): requestSessions for the selector (the picker's own payload) and listArtifacts for the listing, each answer
// carrying the reqId it was asked with, so a slow answer landing after a newer selection is dropped, never rendered.
// Thumbnails and the large view read the token-authed /file route with the session's sid (preview.ts fileUrl), never a
// new file server. The large view is the chat's lightbox (openLightbox) with its arrows stepping this pane's image
// sequence (setLightboxNav), plus one control that sends the picture to the Files pane through the shell's viewFile
// relay, the same message a chat file link posts; a row click on a file walks the chat's route ladder (file-route.ts:
// an open Files pane takes it, else the shared viewer opens here). The shell tells this pane which panes are on screen
// and whether the Files control exists ({romp:'panes', on, avail}), and nothing else passes between them.
import { fileUrl, openLightbox, setLightboxNav, previewKind, canPreview } from "./preview";
import { gridItems, cycleEntries, viaWord, rowRoute, ago, type ArtifactItem } from "./artifacts-model";
import { initFileView, openFileView } from "./file-view";
import { delegate } from "./actions";
import { applyTheme } from "./theme";
import { loadSettings, installSettingsSync, onExternalSettingsChange } from "./settings";

interface Listing { items: ArtifactItem[]; capped: boolean; max: number; error: string; sid: string }
interface SessionRow { id: string; name: string; color: { bg: string; fg: string } | null; running: boolean; time: string }

const SEL_KEY = "romp:artifacts:sid";
const vscodeApi = typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let sessions: SessionRow[] = [];
let selected: string | null = readSelected();
let listing: Listing | null = null;
let loading = false;
let reqSeq = 0;
let lastReq = 0;
let panesOn: Record<string, boolean> = {};
let panesAvail: Record<string, boolean> = {};

function readSelected(): string | null { try { return localStorage.getItem(SEL_KEY); } catch { return null; } }
function writeSelected(sid: string | null): void { try { if (sid) localStorage.setItem(SEL_KEY, sid); else localStorage.removeItem(SEL_KEY); } catch { /* storage may be denied */ } }
function el(tag: string, cls?: string): HTMLElement { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

function ask(msg: Record<string, unknown>): void { vscodeApi?.postMessage(msg); }
function requestSessions(): void { ask({ type: "requestSessions" }); }
function requestListing(): void {
  if (!selected) { listing = null; paint(); return; }
  lastReq = ++reqSeq; loading = true; paint();
  ask({ type: "listArtifacts", sid: selected, reqId: lastReq });
}

function selectSession(sid: string | null): void {
  selected = sid; writeSelected(sid); listing = null; requestListing();
}

// ── the paint: the bar, the grid, the list ──────────────────────────────────────────────────────────────────────────
function paint(): void {
  const root = document.getElementById("artifacts-root");
  if (!root) return;
  root.replaceChildren();
  const bar = el("div", "art-bar");
  const dot = el("span", "art-dot");
  const sel = document.createElement("select"); sel.id = "art-session"; sel.title = "the session whose files are listed";
  const none = document.createElement("option"); none.value = ""; none.textContent = sessions.length ? "Choose a session…" : "No sessions yet"; sel.appendChild(none);
  for (const s of sessions) { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name + (s.running ? "" : "  (" + s.time + ")"); if (s.id === selected) o.selected = true; sel.appendChild(o); }
  const cur = sessions.find((s) => s.id === selected);
  dot.style.background = cur && cur.color ? cur.color.bg : "#666";
  sel.onchange = () => selectSession(sel.value || null);
  const refresh = el("button", "art-btn") as HTMLButtonElement; refresh.textContent = "Refresh"; refresh.dataset.act = "art-refresh"; refresh.title = "read the thread again";
  const count = el("span", "art-count");
  if (listing && !listing.error) count.textContent = listing.items.length + (listing.items.length === 1 ? " file" : " files") + (listing.capped ? " (the newest " + listing.max + ")" : "");
  bar.append(dot, sel, refresh, count);
  const body = el("div", "art-body");
  if (!selected) { const e = el("div", "art-empty"); e.textContent = "Pick a session to see the files its thread wrote, showed and received."; body.appendChild(e); }
  else if (loading && !listing) { const e = el("div", "art-empty"); e.textContent = "Reading the thread…"; body.appendChild(e); }
  else if (listing && listing.error) { const e = el("div", "art-err"); e.textContent = listing.error; body.appendChild(e); }
  else if (listing && !listing.items.length) { const e = el("div", "art-empty"); e.textContent = "This thread has put no file in yet."; body.appendChild(e); }
  else if (listing) {
    const imgs = gridItems(listing.items);
    if (imgs.length && canPreview()) {
      const grid = el("div", "art-grid");
      imgs.forEach((it, i) => {
        const cell = el("div", "art-thumb"); cell.dataset.act = "art-open"; cell.dataset.i = String(i); cell.title = it.path;
        const img = document.createElement("img"); img.loading = "lazy"; img.src = fileUrl(it.path, selected); img.alt = it.name;
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

// ── the clicks, delegated once on the root ───────────────────────────────────────────────────────────────────────────
function openLarge(i: number): void {
  if (!listing || !selected) return;
  const imgs = gridItems(listing.items); const it = imgs[i]; if (!it) return;
  openLightbox(it.path, selected);
  // the one extra control: send this picture to the Files pane's viewer (the shell's viewFile relay), hidden where no
  // Files control exists; the lightbox's bar is the file viewer's bar, so the button wears its dress
  if (window.parent !== window && panesAvail.files !== false) {
    const bar = document.querySelector("#romp-lightbox .fileview-acts");
    if (bar && !bar.querySelector(".art-send")) {
      const b = el("button", "fileview-btn art-send") as HTMLButtonElement; b.textContent = "Files pane"; b.title = "open this picture in the Files pane";
      b.onclick = (ev) => { ev.stopPropagation(); const cur = document.querySelector<HTMLImageElement>("#romp-lightbox .romp-lightbox-img"); const p = cur && cur.alt ? cur.alt : it.path;
        window.parent.postMessage({ romp: "viewFile", path: p, sid: selected, pane: "pane", frag: null }, "*"); };
      bar.insertBefore(b, bar.firstChild);
    }
  }
}
function openRow(i: number): void {
  if (!listing || !selected) return;
  const it = listing.items[i]; if (!it || it.refused) return;
  if (it.kind === "image" && it.exists && canPreview()) { openLarge(gridItems(listing.items).findIndex((g) => g.path === it.path)); return; }
  if (rowRoute(window.parent !== window, panesOn, panesAvail) === "pane") window.parent.postMessage({ romp: "viewFile", path: it.path, sid: selected, pane: "pane", frag: null }, "*");
  else openFileView(it.path, selected, {});
}

// ── boot ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
applyTheme(document, loadSettings()); installSettingsSync(); onExternalSettingsChange((st) => applyTheme(document, st));
initFileView((m) => vscodeApi?.postMessage(m));   // the shared viewer's poster: its ops (fileGitLink, saveFile) ride this socket
setLightboxNav((sid) => { const cur = selected; return listing && cur && sid === cur ? cycleEntries(listing.items, cur) : []; });
const root = document.getElementById("artifacts-root");
if (root) delegate(root, {
  "art-refresh": () => requestListing(),
  "art-open": (e) => openLarge(Number((e as HTMLElement).dataset.i)),
  "art-row": (e) => openRow(Number((e as HTMLElement).dataset.i)),
});
window.addEventListener("message", (ev) => {
  const m = ev.data;
  if (!m) return;
  if (m.romp === "panes") { panesOn = m.on || {}; panesAvail = m.avail || {}; if (panesOn.artifacts && selected && !listing && !loading) requestListing(); return; }
  if (m.type === "sessionList" && Array.isArray(m.items)) {
    sessions = m.items.map((s: any) => ({ id: String(s.id), name: String(s.name || s.id).slice(0, 80), color: s.color || null, running: !!s.running, time: String(s.time || "") }));
    if (selected && !sessions.some((s) => s.id === selected)) { const keep = selected; sessions.unshift({ id: keep, name: keep.slice(0, 8), color: null, running: false, time: "" }); }
    paint(); if (selected && !listing && !loading) requestListing();
    return;
  }
  if (m.type === "artifactsListing") {
    if (m.reqId !== lastReq || m.sid !== selected) return;   // a slow answer for an earlier selection: dropped, never rendered
    loading = false;
    listing = { items: Array.isArray(m.items) ? m.items : [], capped: !!m.capped, max: Number(m.max) || 500, error: String(m.error || ""), sid: String(m.sid || "") };
    paint();
  }
});
paint();
requestSessions();
if (selected) requestListing();
