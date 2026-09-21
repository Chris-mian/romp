// The Artifacts pane's pure parts (plans/artifacts-pane.md): the item record the kernel's listArtifacts answer carries, the
// grid's rule, the cycle's order, the rule words, a row click's route and the age words. No DOM at import, so the test
// runs them for real (ui/webview/artifacts.test.ts); artifacts.ts, the page, imports them.
import { fileLinkRoute } from "./file-route";

export interface ArtifactItem { path: string; name: string; t: number; via: string; exists: boolean; size: number | null; mtime: number | null; kind: string; refused: string }
/** The grid's rule: an existing, allowed image. Pure, so the test runs it. */
export function gridItems(items: ArtifactItem[]): ArtifactItem[] { return items.filter((it) => it.kind === "image" && it.exists && !it.refused); }
/** The cycle's order is the grid's (newest first); the lightbox steps by index and the ends end. */
export function cycleEntries(items: ArtifactItem[], sid: string): { path: string; sid: string }[] { return gridItems(items).map((it) => ({ path: it.path, sid })); }
/** The words of a rule, for the row's small tag. */
export function viaWord(via: string): string {
  return via === "write" ? "written" : via === "edit" ? "edited" : via === "multiedit" ? "edited" : via === "notebook" ? "notebook" : via === "rendered" ? "shown" : via === "drop" ? "dropped" : via;
}
/** Where a row click opens (the chat's ladder): the Files pane when it is on screen and its control exists, else here. */
export function rowRoute(framed: boolean, on: Record<string, boolean>, avail: Record<string, boolean>): "pane" | "here" {
  return fileLinkRoute(framed, on.files === true, avail.files !== false);
}

/** The chat's relative age words for a row (seconds ago): under a minute "just now", then minutes, hours, days. Pure. */
export function ago(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) { const h = Math.floor(s / 3600); return h + (h === 1 ? " hour ago" : " hours ago"); }
  const d = Math.floor(s / 86400); return d + (d === 1 ? " day ago" : " days ago");
}

// ── pass two (plans/artifacts-pane.md section 9): the open tabs, the selection machine ──────────────────────────────
/** One open chat tab as the shell's chatTabs broadcast carries it: the id (host-prefixed for a remote tab), the name as the
 *  strip shows it, the identity colour or null. */
export interface TabRow { id: string; name: string; color: { bg: string; fg: string } | null }
/** The shell's rows, taken verbatim and made safe: strings coerced, a row without an id dropped, one row per id (the first
 *  column's wins), the order kept. */
export function normalizeTabs(raw: unknown): TabRow[] {
  const out: TabRow[] = []; const seen = new Set<string>();
  for (const t of Array.isArray(raw) ? raw : []) {
    if (!t || typeof t !== "object") continue;
    const id = String((t as any).id || ""); if (!id || seen.has(id)) continue; seen.add(id);
    const c = (t as any).color;
    out.push({ id, name: String((t as any).name || id), color: c && typeof c === "object" && c.bg ? { bg: String(c.bg), fg: String(c.fg || "") } : null });
  }
  return out;
}
/** The pane's selection: the shown session and whether it is locked. */
export interface Selection { sid: string | null; locked: boolean }
export type SelectionEvent =
  | { type: "activeChat"; id: string | null }    // the chat's most recently selected tab (the shell's relay, the kernel's frame)
  | { type: "pick"; id: string }                  // a pick from the picker's list
  | { type: "toggleLock" }                        // the lock button
  | { type: "tabsChanged"; tabs: TabRow[] };      // the shell's union changed (a tab opened or closed)
/** The selection machine (section 9.5; the manager's paraphrase of the user, 2026-09-20): unlocked, the pane shows whatever came
 *  last, a pick or the chat's most recently selected tab; locked, it stays on the pick and ignores the chat; ONLY the lock
 *  button changes the lock, a pick never does (unlocked, a pick shows that session until the next tab switch replaces it;
 *  locked, a pick replaces the locked session and the lock stays on). A null active tab (no tab shown) selects nothing new.
 *  A closed tab keeps the selection: its listing stays readable, the button says "not open", the next switch replaces it. */
export function nextSelection(s: Selection, ev: SelectionEvent): Selection {
  switch (ev.type) {
    case "activeChat": return s.locked || !ev.id ? s : { sid: ev.id, locked: s.locked };
    case "pick": return { sid: ev.id, locked: s.locked };
    case "toggleLock": return { sid: s.sid, locked: !s.locked };
    case "tabsChanged": return s;
  }
}
/** The shown session's row: the union's row for it; else its last known row (the tab was open once this page's life), marked not
 *  open; else a stub (the id's first eight characters), marked not open. */
export function shownRow(tabs: TabRow[], sid: string | null, known?: Map<string, TabRow>): { row: TabRow | null; open: boolean } {
  if (!sid) return { row: null, open: false };
  const hit = tabs.find((t) => t.id === sid);
  if (hit) return { row: hit, open: true };
  const seen = known && known.get(sid);
  if (seen) return { row: seen, open: false };
  const i = sid.indexOf(":");
  return { row: { id: sid, name: (i > 0 ? sid.slice(0, i + 1) : "") + sid.slice(i + 1, i + 9), color: null }, open: false };
}

