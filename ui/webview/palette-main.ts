// Shell-page boot for the quick-pick hotkeys (browser dashboard only — the VS Code surface
// gets real contributed keybindings instead, rebindable in its own Keyboard Shortcuts
// editor). Obsidian's split, per the user (2026-08-08): Cmd/Ctrl+O is the SESSION JUMP
// switcher — sessions most-recently-used first, fuzzy by name, Enter switches; it never
// creates. Cmd/Ctrl+Shift+O opens the full new-session picker (create, directory, backend,
// host). Cmd/Ctrl+P toggles the command palette. All three combos are claimable by a page
// (Google Docs and Figma take Cmd+O/Cmd+P), the override lasts only while this tab has
// focus, and the window/tab-management set (Cmd+W/T/N/L/Q) stays untouched.
import { registerCommand } from "./commands";
import { initPalette, PickItem } from "./palette";

type SessionRow = { id: string; name: string; dir: string; bg: string };

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
  function chatPost(msg: object): void {
    // Reveal the chat pane if it's toggled off, focus it, and hand it the message. The
    // __romp* globals and the pane's message handlers are read lazily at RUN time, so boot
    // order across the shell's script tags doesn't matter.
    try { if (w.__rompPaneToggle) w.__rompPaneToggle("chat", true); } catch (e) { /* rail not booted yet */ }
    const f = pane("f-chat");
    try { f!.contentWindow!.focus(); f!.contentWindow!.postMessage(msg, "*"); }
    catch (e) { /* chat pane not loaded yet — nothing to talk to */ }
  }
  function openNewSessionPicker(): void {
    chatPost({ type: "openPicker", toggle: true });
  }

  // ── the session jump switcher (Cmd/Ctrl+O) ────────────────────────────────────────────────
  // Sessions come from the kernel's /sessions (the authoritative list, same-origin, kernel
  // order); recency comes from the chat pane's __rompMru (most-recently-ACTIVATED tab ids,
  // current session first). Obsidian's trick, kept: the current session is excluded and the
  // previous one sorts first, so Cmd+O Enter toggles between your two most recent sessions.
  function mruIds(): string[] {
    try { return (pane("f-chat")?.contentWindow as any)?.__rompMru?.slice() || []; }
    catch (e) { return []; }
  }
  function sessionItems(rows: SessionRow[]): PickItem[] {
    const mru = mruIds();
    const byId = new Map(rows.map((r) => [r.id, r]));
    const ordered: SessionRow[] = [];
    for (const id of mru.slice(1)) { const r = byId.get(id); if (r) { ordered.push(r); byId.delete(id); } }
    for (const r of rows) if (byId.has(r.id) && r.id !== mru[0]) ordered.push(r);
    const base = (d: string) => (d || "").replace(/\/+$/, "").split("/").pop() || "";
    return ordered.map((r) => ({
      title: r.name,
      dot: r.bg || "#8a8a8a",
      dim: base(r.dir),
      run: () => chatPost({ type: "jumpSession", id: r.id }),
    }));
  }
  function openSessionSwitcher(): void {
    fetch("/sessions").then((r) => r.json()).then((rows: SessionRow[]) => {
      palette.openPick({
        placeholder: "Jump to a session…",
        items: sessionItems(Array.isArray(rows) ? rows : []),
        altEnter: { label: "new session…", run: openNewSessionPicker },
      });
    }).catch(() => {
      // fail loudly, not with a silently empty list: the kernel not answering is the story
      palette.openPick({
        placeholder: "Jump to a session…",
        items: [{ title: "Couldn't load sessions — the kernel didn't answer", run: () => {} }],
        altEnter: { label: "new session…", run: openNewSessionPicker },
      });
    });
  }

  // ── the dashboard's actions, registered as commands ──────────────────────────────────────
  // Each calls the SAME code path its rail button uses; the palette adds reachability, not
  // behavior.
  registerCommand({ id: "session.jump", title: "Jump to a session", kbd: mod + "O", run: openSessionSwitcher });
  registerCommand({ id: "session.new", title: "New session", kbd: mod + (mac ? "⇧O" : "Shift+O"), run: openNewSessionPicker });
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

  // Esc (or running an item) hands focus back to the chat pane, so "palette, Esc, type"
  // never strands the keyboard on the shell document.
  const palette = initPalette({ onClose: () => { try { pane("f-chat")!.contentWindow!.focus(); } catch (e) { /* no chat pane */ } } });
  w.__rompPalette = palette;   // reachable by other shell scripts (e.g. a future mobile-bar button)

  function onKey(e: KeyboardEvent): void {
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.repeat) return;
    const k = (e.key || "").toLowerCase();
    if (k === "o") {
      e.preventDefault(); e.stopPropagation();
      palette.close();
      if (e.shiftKey) openNewSessionPicker(); else openSessionSwitcher();
    } else if (k === "p" && !e.shiftKey) {   // Cmd+Shift+P stays the browser's / VS Code's
      e.preventDefault(); e.stopPropagation();
      palette.toggle();
    }
  }
  // The same dual wiring as the Alt+Arrow pane nav (_LANDING_FOCUS_JS): capture on the shell
  // document AND on every same-origin pane document, re-attached on every iframe (re)load.
  // render.ts's own window-capture Cmd+O handler stands down inside the shell (inRompShell),
  // so a keystroke in the chat document lands here exactly once.
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
