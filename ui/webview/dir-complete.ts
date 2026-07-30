// The new-session directory field's two decisions, kept out of the DOM so they can be tested:
// what the status line SAYS about a typed path, and where the keyboard lands when you walk the
// folder list. The kernel that will own the session supplies the status (kernel _dir_status) — for a
// remote host that is the remote machine's own disk, which is the whole reason this is a round trip
// rather than a guess in the browser (the user 2026-07-28).

export interface DirStatus {
  value: string; path: string; exists: boolean; isDir: boolean; isFile: boolean;
  canCreate: boolean; nearest: string; missing: number; isDefault: boolean;
}

/** One line saying what the typed path IS, and the tone to say it in. "" = say nothing (no answer yet). */
export function dirStatusLine(s: DirStatus | null): { text: string; cls: string } {
  if (!s) return { text: "", cls: "" };
  if (s.isDefault) return { text: s.path + "  (the default)", cls: "" };
  if (s.isDir) return { text: "✓ " + s.path, cls: "" };
  // a file where a folder was typed can never become one — no create offer follows, so say so plainly
  if (s.isFile) return { text: "not a folder: " + s.path, cls: "bad" };
  // Plain words for what is wrong (the user 2026-07-29: "still not there" read as waffle). A missing
  // folder is not INVALID, though, since starting here creates it, so it says which of the two it is
  // rather than collapsing both into one wrong label.
  if (s.canCreate) {
    // Name what will be MADE, and where (the user 2026-07-29). "will create it" left you to work out
    // which folder, at which path, on which machine, from a line that had just told you the path was
    // wrong. Say the path outright, and when the parent is missing too, say how much is being made.
    const above = s.missing > 1 ? ` and the ${s.missing - 1} folder${s.missing > 2 ? "s" : ""} above it` : "";
    return { text: `no such folder yet. Starting will create ${s.path}${above}`, cls: "warn" };
  }
  return { text: "invalid path: " + s.path, cls: "bad" };
}

/** Walk the completion list. -1 ("nothing chosen") is part of the cycle in BOTH directions, so walking
 *  off either end hands the field back to typing instead of trapping the cursor in the menu. */
export function nextDirActive(cur: number, delta: number, count: number): number {
  if (count <= 0) return -1;
  const next = cur + delta;
  if (next >= count) return -1;
  if (next < -1) return count - 1;
  return next;
}

/** The detail line of the "that folder isn't there" dialog: name the path, and how much would be made. */
export function createDirPrompt(name: string, s: DirStatus | null, fallback: string): string {
  const where = (s && s.path) || fallback;
  const under = s && s.missing > 1 ? ` (${s.missing} new folders under ${s.nearest})` : "";
  return `${where} doesn't exist${under}. Create it and start “${name}” there, or go back and edit the path?`;
}
