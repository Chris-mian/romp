// Where the settings gear (gear.js, the ⛭ modal) lives for THIS document (the user 2026-09-10, who
// wanted the gear out of the feed so the Feed pane can be turned off without losing settings).
//
// Two hosts, one rule:
// - The kernel's dashboard serves the gear on its OWN page, /settings (kernel _settings_page →
//   settings-page.ts), embedded by the shell as the hidden #f-settings iframe and lifted full-window
//   while the modal is open. The kernel's feed page sets window.__rompGearOnSettingsPage = true before
//   feed.js runs, so the feed mounts no gear there, and a control inside the feed that wants the modal
//   (the dead-credential card's login button) asks the SHELL, which forwards {romp:'openSettings'}
//   into the settings iframe (kernel _LANDING_SETTINGS_JS).
// - VS Code's feed panel sets nothing: it has no settings page, so the feed bundle hosts the gear itself
//   and an open request is a same-document message, as it always was.
// Pure over the window it is handed, so a node test drives both branches (gear-host.test.ts).

export type GearWindow = {
  __rompGearOnSettingsPage?: boolean;
  parent?: GearWindow | null;
  postMessage(m: unknown, origin: string): void;
};

/** True when this document mounts the gear (VS Code's feed panel, the /settings page); false in the
 *  kernel's feed page, where the shell's settings iframe has it. */
export function hostsGear(w: GearWindow): boolean {
  return !w.__rompGearOnSettingsPage;
}

export type GearOpenOpts = { tab?: string; section?: string };

/** Raise the gear: in the document that hosts it, or through the shell when this one does not. A
 *  hostless document with no parent (a standalone /feed tab on a kernel that serves the gear elsewhere)
 *  has nowhere to send the ask, and drops it rather than throw; the return says whether the ask was
 *  DELIVERED (here or to the shell), so a caller with a road of its own can take it (the off notice's
 *  button goes to the dashboard, T404 round two). `tab` and `section` ride the message in the shape the
 *  shell's __rompOpenSettings reads (T379's), naming the pane to open at. */
export function openGear(w: GearWindow, opts?: GearOpenOpts): boolean {
  const msg: Record<string, unknown> = { romp: "openSettings" };
  if (opts?.tab) msg.tab = opts.tab;
  if (opts?.section) msg.section = opts.section;
  if (hostsGear(w)) { w.postMessage(msg, "*"); return true; }
  const p = w.parent;
  if (p && p !== w) { try { p.postMessage(msg, "*"); return true; } catch { /* no shell to ask */ } }
  return false;
}
