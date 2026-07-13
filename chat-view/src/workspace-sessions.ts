// Session ↔ workspace matching: which romp sessions live in (or above) the
// folders this VS Code window has open. Dirs come from the kernel's /sessions
// endpoint (the authoritative session list); folders from
// vscode.workspace.workspaceFolders. Pure decision core — extension.ts owns
// the fetch and the QuickPick.

export type SessionInfo = { id: string; name: string; dir: string };

export function normalizeDir(p: string): string {
  let s = String(p || "").replace(/\/+$/, "");
  return s || "/";
}

// A session belongs to this window when its dir and a workspace folder
// coincide or one contains the other (a worktree opened directly, a repo root
// containing the session's subdir, or a session running at the repo root
// while the window has a subfolder open).
export function sessionMatchesFolders(dir: string, folders: string[]): boolean {
  const d = normalizeDir(dir);
  if (d === "/") return false;
  return folders.some((f) => {
    const w = normalizeDir(f);
    if (w === "/") return false;
    return d === w || d.startsWith(w + "/") || w.startsWith(d + "/");
  });
}

export function sessionsForWorkspace(sessions: SessionInfo[], folders: string[]): SessionInfo[] {
  return (sessions || []).filter((s) => s && s.dir && sessionMatchesFolders(s.dir, folders));
}

// The citation text for the composer: absolute path (unambiguous for any
// session, whatever its cwd), with a line range only when the selection
// actually spans one — a bare cursor cites the file, not a line.
export function citeText(file: string, startLine?: number, endLine?: number, hasSelection = false): string {
  if (!hasSelection || !startLine) return file;
  if (!endLine || endLine === startLine) return `${file}:${startLine}`;
  return `${file}:${startLine}-${endLine}`;
}
