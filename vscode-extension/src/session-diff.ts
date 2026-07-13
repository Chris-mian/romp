// Reviewing a session's uncommitted changes from the current window: parse
// `git status --porcelain` into pickable entries. Pure decision core —
// extension.ts runs git and opens the native diff editor.

export type ChangedFile = {
  path: string;          // repo-relative
  status: string;        // porcelain XY, trimmed (e.g. "M", "A", "??", "R")
  untracked: boolean;    // no HEAD side — diff against empty
  renamedFrom?: string;  // "R  old -> new" keeps the old path for the HEAD side
};

export function parsePorcelain(out: string): ChangedFile[] {
  const files: ChangedFile[] = [];
  for (const raw of String(out || "").split("\n")) {
    if (raw.length < 4) continue;
    const xy = raw.slice(0, 2);
    let rest = raw.slice(3);
    if (!rest) continue;
    let renamedFrom: string | undefined;
    if ((xy[0] === "R" || xy[0] === "C") && rest.includes(" -> ")) {
      const [from, to] = rest.split(" -> ");
      renamedFrom = unquote(from);
      rest = to;
    }
    files.push({
      path: unquote(rest),
      status: xy.trim(),
      untracked: xy === "??",
      renamedFrom,
    });
  }
  return files;
}

// git quotes paths with special characters ("a b.txt", with escapes); undo the
// plain-quote case (escape sequences are rare enough to pass through).
function unquote(p: string): string {
  const s = p.trim();
  return s.startsWith('"') && s.endsWith('"') ? s.slice(1, -1) : s;
}
