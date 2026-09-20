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
