// A plain-text paste that IS a local file's path (the user 2026-08-11: pasting a screenshot's
// path into a remote session's box rode the prompt as text to a machine where that path doesn't
// exist, while dragging the same file worked). The composer converts such a paste into a real
// attachment — but only when the WHOLE paste is one plausible path to a file kind the kernel's
// /file route can serve (previewKind: the same images+pdf allowlist previews wear), so prose that
// merely mentions a path, multi-line pastes, and non-media paths all stay ordinary text.
// Recognition here is deliberately SHAPE-only; existence is the kernel's call (/file 404s and the
// composer puts the exact text back), never a guess — the authoritative-source rule.
import { previewKind } from "./preview";

export function pastedFilePath(text: string): { path: string } | null {
  let s = (text || "").trim();
  if (!s || /[\r\n]/.test(s)) return null;                 // one paste = one line = one path
  const q = /^"(.*)"$|^'(.*)'$/.exec(s);                   // Finder/shell quote wrappers
  if (q) s = (q[1] ?? q[2] ?? "").trim();
  if (/^file:\/\//i.test(s)) {                             // browser / "Copy as URL" form
    try { s = decodeURIComponent(s.replace(/^file:\/\/[^/]*/i, "")); } catch { return null; }
  }
  s = s.replace(/\\([ ()'"&])/g, "$1");                    // terminal-escaped spaces & friends
  if (!/^[/~]/.test(s)) return null;                       // absolute or ~ only — a bare word is prose
  if (!previewKind(s)) return null;                        // only kinds /file serves (img + pdf)
  return { path: s };
}
