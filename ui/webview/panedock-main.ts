// THE PANE DOCKING ENGINE (plans/pane-docking.md, phase two), a dashboard-shell bundle loaded like
// palette-main.ts (a `<script src=/dist/panedock-main.js>` in the shell head, kernel.py). It runs ONLY
// when the per-browser gear switch `paneDocking` is on. DEFAULT OFF: with the switch off this bundle
// changes nothing, so the shipped pane layout (the _LANDING_* inline JS) is byte-for-byte what it is
// today and no engine code runs.
//
// This foundation slice reads the switch and toggles the `pane-docking` body class on the shell (the
// hook the positioning, the drop zones, the live accent outline and the dividers key on in the following
// commits). It changes NO layout yet: with the class present nothing is styled or repositioned until the
// positioning slice lands. Kept as a self-booting IIFE at the TOP document, like palette-main.
//
// The flag read is the shell's own raw-read idiom (JSON.parse of localStorage `romp:settings`, the
// literal `true` only), split into a PURE `isPaneDockingOn` so it is node-testable without a DOM.

export const PANE_DOCKING_CLASS = "pane-docking";
const SETTINGS_KEY = "romp:settings";

/** Whether the gear's per-browser `paneDocking` switch is on, from the raw `romp:settings` JSON. Only the
 *  literal `true` turns it on: a store from before the key, a missing value, or any other type reads OFF
 *  (the fail-safe default for an opt-in that gates a whole layout engine). Pure; never throws. */
export function isPaneDockingOn(rawSettings: string | null): boolean {
  try {
    const o = JSON.parse(rawSettings || "{}");
    return !!o && typeof o === "object" && (o as { paneDocking?: unknown }).paneDocking === true;
  } catch {
    return false;
  }
}

/** Reflect the switch onto the shell body's `pane-docking` class. Safe to call before the body exists. */
function apply(): void {
  if (typeof document === "undefined" || !document.body) return;
  let raw: string | null = null;
  try { raw = localStorage.getItem(SETTINGS_KEY); } catch { raw = null; }
  document.body.classList.toggle(PANE_DOCKING_CLASS, isPaneDockingOn(raw));
}

// boot only in a browser TOP document (guards keep an import in node inert, so the pure export is testable)
if (typeof window !== "undefined" && typeof document !== "undefined") {
  apply();
  // re-apply on a gear save in this document, and on a write from another tab (the shell's settings idiom)
  window.addEventListener("romp:settings", apply);
  window.addEventListener("storage", (e) => { if (!e || !e.key || e.key === SETTINGS_KEY) apply(); });
}
