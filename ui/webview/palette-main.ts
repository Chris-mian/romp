// Shell-page boot for the command palette and the global hotkeys (browser dashboard only —
// the VS Code surface gets real contributed keybindings instead, rebindable in its own
// Keyboard Shortcuts editor). Cmd/Ctrl+P toggles the palette; Cmd/Ctrl+O opens the session
// quick switcher — the existing new-session picker in the chat pane, one picker, one code
// path. Both combos are claimable by a page (Google Docs and Figma take exactly these), the
// override lasts only while this tab has focus, and the window/tab-management set
// (Cmd+W/T/N/L/Q) stays untouched.
import { registerCommand } from "./commands";
import { initPalette } from "./palette";

(function boot() {
  // The shell page only, never inside a pane: the pane documents get the KEY wiring below
  // (a keydown fires in whichever document holds focus and never crosses the iframe boundary),
  // but the palette itself must sit in the top document to composite over all the panes.
  if (window.parent && window.parent !== window) return;
  const w = window as any;
  const mac = /Mac|iP(hone|ad|od)/.test(navigator.platform || "");
  const mod = mac ? "⌘" : "Ctrl+";

  function pane(id: string): HTMLIFrameElement | null {
    return document.getElementById(id) as HTMLIFrameElement | null;
  }
  function openSwitcher(): void {
    // Reveal the chat pane if it's toggled off, focus it, and toggle the picker there. The
    // __romp* globals and the picker's message handler are read lazily at RUN time, so boot
    // order across the shell's script tags doesn't matter.
    try { if (w.__rompPaneToggle) w.__rompPaneToggle("chat", true); } catch (e) { /* rail not booted yet */ }
    const f = pane("f-chat");
    try {
      f!.contentWindow!.focus();
      f!.contentWindow!.postMessage({ type: "openPicker", toggle: true }, "*");
    } catch (e) { /* chat pane not loaded yet — nothing to open a picker in */ }
  }

  // The dashboard's actions, registered as commands. Each calls the SAME code path its rail
  // button uses; the palette adds reachability, not behavior.
  registerCommand({ id: "session.open", title: "Open or create a session", kbd: mod + "O", run: openSwitcher });
  registerCommand({
    id: "settings.open", title: "Open settings",
    run: () => { try { pane("f-feed")!.contentWindow!.postMessage({ romp: "openSettings" }, "*"); } catch (e) { /* feed not loaded */ } },
  });
  registerCommand({ id: "log.open", title: "Open the log", run: () => { if (w.__rompOpenErrs) w.__rompOpenErrs(); } });
  registerCommand({ id: "net.open", title: "Remote kernels", run: () => { if (w.__rompOpenNet) w.__rompOpenNet(); } });
  registerCommand({ id: "usage.open", title: "Token usage", run: () => { if (w.__rompUsagePanel) w.__rompUsagePanel(); } });
  registerCommand({ id: "kernel.restart", title: "Restart the romp kernel", run: () => { if (w.__rompRestart) w.__rompRestart(); } });
  // Pane toggles. The Outline pane's INTERNAL key stays 'fleet' (the pane controller's API);
  // the command speaks the user-facing name.
  const panes: Array<[string, string]> = [["chat", "chat"], ["timeline", "timeline"], ["fleet", "outline"], ["feed", "feed"]];
  for (const [key, label] of panes) {
    registerCommand({
      id: "pane." + label, title: "Show or hide the " + label + " pane",
      run: () => { if (w.__rompPaneToggle) w.__rompPaneToggle(key); },
    });
  }

  // Esc (or running a command) hands focus back to the chat pane, so "palette, Esc, type"
  // never strands the keyboard on the shell document.
  const palette = initPalette({ onClose: () => { try { pane("f-chat")!.contentWindow!.focus(); } catch (e) { /* no chat pane */ } } });
  w.__rompPalette = palette;   // reachable by other shell scripts (e.g. a future mobile-bar button)

  function onKey(e: KeyboardEvent): void {
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.repeat) return;
    const k = (e.key || "").toLowerCase();
    if (k === "o") { e.preventDefault(); e.stopPropagation(); palette.close(); openSwitcher(); }
    else if (k === "p") { e.preventDefault(); e.stopPropagation(); palette.toggle(); }
  }
  // The same dual wiring as the Alt+Arrow pane nav (_LANDING_FOCUS_JS): capture on the shell
  // document AND on every same-origin pane document, re-attached on every iframe (re)load.
  // When focus is already in the chat document, render.ts's own window-capture Cmd+O handler
  // runs first and stops propagation, so this one never double-fires.
  document.addEventListener("keydown", onKey, true);
  ["f-chat", "f-fleet", "f-feed", "f-timeline"].forEach((id) => {
    const f = pane(id);
    if (!f) return;
    const wire = () => {
      try { if (f.contentDocument) f.contentDocument.addEventListener("keydown", onKey, true); }
      catch (e) { /* cross-origin frame: not one of ours */ }
    };
    f.addEventListener("load", wire);
    wire();
  });
})();
