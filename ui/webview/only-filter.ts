// Demo/recording VIEW filter (the user 2026-07-14): load the dashboard at `#only=<tag>` (or `?only=<tag>`)
// and every pane (chat tabs, feed, fleet, timeline) shows ONLY sessions whose name starts with <tag>,
// case-insensitive. The real sessions keep running and still show on the normal `:7433/` — they are just
// hidden from THIS view, so you get a clean frame for demo screencasts without standing up a separate
// instance. Empty / no tag → no filter (everything shows, unchanged).
//
// The panes are same-origin iframes of the shell, so each reads the SHELL's URL (window.top) — one
// `#only=demo` on the dashboard URL scopes all four panes at once. A cross-origin top (an embedded
// webview) falls back to the pane's own URL.

export function onlyTag(): string | null {
  const read = (loc: Location): string | null => {
    try {
      const hay = (loc.hash || "") + " " + (loc.search || "");
      const m = hay.match(/only=([^&\s]+)/i);
      return m ? (decodeURIComponent(m[1]).trim().toLowerCase() || null) : null;
    } catch { return null; }
  };
  if (typeof window === "undefined") return null;    // no DOM (a test/headless context) → no filter
  try { return read((window.top || window).location); } catch { /* cross-origin top */ }
  try { return read(window.location); } catch { return null; }   // fall back to this pane's own URL
}

export function matchesOnly(name: string | null | undefined, tag: string | null): boolean {
  if (!tag) return true;                             // no filter → everything passes
  return (name || "").toLowerCase().startsWith(tag);
}
