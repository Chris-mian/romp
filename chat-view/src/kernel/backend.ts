// SessionBackend — the semantic seam between romp's UI/host logic and whatever
// actually hosts Claude Code sessions.
//
// Everything above this interface (the kernel server, the chat/feed logic, the
// webview UI) speaks in SESSIONS and EVENTS; everything below it deals with the
// mechanics of one hosting substrate. The tmux backend synthesizes these
// semantics by scraping a TUI (capture-pane, send-keys); a headless backend
// gets most of them natively. The contract tests in src/kernel/*.test.ts run
// against every implementation.
//
// Required capabilities are what any backend must provide. TUI-only
// capabilities (live screen capture, raw key navigation) are optional — a
// backend without them simply has no live-picker mirroring, and callers must
// feature-check via `tui`.

export interface SessionState {
  state: string;    // "" | working | waiting | idle | permission | picker | compacting
  effort: string;
  model: string;
  ctx: string;      // context % string
  since: string;    // epoch seconds (string, as stored)
  summary: string;  // live one-phrase summary
}

// TUI-only operations (the tmux backend). `null` from SessionBackend.tui means
// the backend cannot mirror or drive live picker screens.
export interface TuiOps {
  // The session's visible screen as plain text ("" on failure).
  capturePane(name: string): string;
  // Send raw key names (tmux send-keys vocabulary: "Down", "Enter", "Space", …).
  sendKeys(name: string, keys: string[]): void;
  // Type a literal string (no key-name interpretation).
  sendLiteral(name: string, text: string): void;
}

export interface SessionBackend {
  // Live sessions, keyed by session NAME. Empty map = the probe is unreliable
  // (callers must not treat it as "everything closed"). Null only when the
  // backend is wholly unavailable.
  liveSessions(): Map<string, SessionState>;

  // Deliver `text` to the session as its next prompt (a typed turn).
  send(name: string, text: string): boolean;

  // Interrupt the session's current turn (Claude Code: Esc semantics).
  interrupt(name: string): boolean;

  // Launch a NEW detached session named `name` in `cwd`. Resolves once issued
  // (the session boots asynchronously — poll liveSessions for readiness).
  spawn(name: string, cwd: string): Promise<boolean>;

  // Resume a dead session by transcript id under `name` in `cwd`.
  resume(name: string, id: string, cwd?: string): boolean;

  // Rename a live session. Backends keep the romp names registry in sync.
  rename(oldName: string, newName: string): boolean;

  // End a session for good (transcript stays on disk).
  kill(name: string): boolean;

  // Force a session's published state to idle after an interrupt (Claude Code
  // fires no hook on Esc, so the substrate's state var would stay "working").
  // `notAfter`: do nothing if a newer state event already landed.
  markIdle(name: string, notAfter: number): void;

  // TUI capabilities, or null when this backend has none.
  readonly tui: TuiOps | null;
}
