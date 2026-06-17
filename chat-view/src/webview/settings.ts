// Shared, persisted webview settings (the user 2026-06-14): one global settings store, surfaced via a
// gear → modal. localStorage-backed so same-origin views (the browser's /chat, /feed, /timeline tabs)
// share ONE setting, and a `storage` event live-syncs a change across the other open tabs. Keep this
// DOM-light: load/save are pure over localStorage (unit-tested); only the subscribe helper touches window.

export interface RompSettings {
  compact: boolean;   // chat transcript: collapse consecutive tool uses, hide thinking
  colormap: string;   // feed recency tint colormap (the user 2026-06-16): hawaii | viridis | magma | inferno | plasma | cividis
}
export const DEFAULT_SETTINGS: RompSettings = { compact: false, colormap: "hawaii" };
const KEY = "romp:settings";

export function loadSettings(): RompSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch { /* corrupt / unavailable → defaults */ }
  return { ...DEFAULT_SETTINGS };
}

export function saveSettings(patch: Partial<RompSettings>): RompSettings {
  const next = { ...loadSettings(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* ignore */ }
  return next;
}

// Fire `cb` when the settings change in ANOTHER same-origin tab (the browser views share localStorage;
// the `storage` event does NOT fire in the tab that made the change, so callers apply their own change
// directly). No-op where there's no window (tests, headless).
export function onExternalSettingsChange(cb: (s: RompSettings) => void): void {
  if (typeof window === "undefined") return;
  window.addEventListener("storage", (e: StorageEvent) => { if (e.key === KEY) cb(loadSettings()); });
}
