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
  if (s.isFile) return { text: "that's a file, not a folder", cls: "bad" };
  if (s.canCreate) {
    return { text: "not there yet. Starting will offer to create it, under " + s.nearest, cls: "warn" };
  }
  return { text: "can't be reached: " + s.path, cls: "bad" };
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
