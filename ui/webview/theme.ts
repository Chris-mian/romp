// The ONE theme applier (2026-08-28): every pane document funnels the theme setting through here
// so a surface can never half-apply it. Two body classes carry everything:
//   .chat-theme-yatharth — the contributed strip/identity aesthetic (theme "yatharth" AND
//                          "yatharth-light"; classic leaves the body bare, its pins byte-stable)
//   .theme-light         — the warm light theme's token blocks (styles.css/feed.css/THEME_CSS
//                          re-define the same custom-property names under it)
// Callers: render.ts (chat), feed.ts, fleet.ts, timeline-main.ts at boot + on settings changes;
// the browser shell applies the same classes with its own inline reader (kernel _landing — it
// loads no bundle). Components must never branch on these classes directly: theme differences
// live in the token blocks (CLAUDE.md-bound; the key-parity test enforces the light set).
import type { RompSettings } from "./settings";

export function applyTheme(doc: Document, s: RompSettings): void {
  doc.body.classList.toggle("chat-theme-yatharth", s.theme !== "classic");
  doc.body.classList.toggle("theme-light", s.theme === "yatharth-light");
}
