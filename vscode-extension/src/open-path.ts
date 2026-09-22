// Where a clicked path points, on the machine the extension host runs on — the kernel's rule
// (kernel.py _resolve_open_path), pure, so open-path.test.ts executes it. The webview posts a path AS
// WRITTEN in the transcript: `~/notes-api/x.md`, `design/foo.md`, `/abs/x.md`, or a file:// caption link. The
// kernel's own openFile handler expands `~` and resolves a relative path against the session's cwd
// before opening; the extension's opener handed the raw string to vscode.Uri.file, so a `~/` link
// (clickable since T351 stage 2, 2026-09-12) failed with the unexpanded path in the warning (the user
// 2026-09-21). Kept import-light (node's path only): the extension host is the remote machine under
// Remote-SSH, so `home` is os.homedir() THERE, and `cwd` is the session's dir from the kernel's
// /sessions list — never the extension host's own cwd, which says nothing about the session.
import * as path from "path";

/** The path to open. `~` and `~/…` expand against `home` (`~user/…` is left as written: the kernel's
 *  os.path.expanduser expands a known account's home, but node has no password-database lookup, so the
 *  extension does not); a file:// URI with an empty or localhost authority is its own decoded path;
 *  an absolute path is normalised; a relative path resolves against `cwd` when one is given, else is returned
 *  as written for the caller to look the session's dir up (needsSessionDir). */
export function resolveOpenPath(p: string, home: string, cwd?: string | null): string {
  let s = String(p || "").trim();
  if (s.startsWith("file://")) {
    try {
      const u = new URL(s);
      if (u.hostname === "" || u.hostname === "localhost") s = decodeURIComponent(u.pathname);
    } catch { /* not a URL after all: read as a path */ }
  }
  if (s === "~") s = home;
  else if (s.startsWith("~/")) s = path.join(home, s.slice(2));
  if (path.isAbsolute(s)) return path.resolve(s);
  if (cwd) return path.resolve(cwd, s);
  return s;
}

/** Whether the caller must look the session's dir up before this path can open: it is still relative. */
export function needsSessionDir(p: string): boolean {
  return !path.isAbsolute(p);
}
