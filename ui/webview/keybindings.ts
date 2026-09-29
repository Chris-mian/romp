// Keyboard bindings for the shell's commands (the user 2026-08-09, who wanted the shortcuts
// configurable "the way VS Code does it": record a chord, see conflicts, reset). This module is the
// PURE half — chord normalization, display, the localStorage store, conflict resolution, and the
// dispatch decision — so every rule here runs under real tests; the DOM (the dialog, the key wiring)
// lives in shortcuts-modal.ts / palette-main.ts. The VS Code surface does NOT use any of this: there
// the same actions are contributed commands, rebindable in VS Code's own Keyboard Shortcuts editor.
//
// A chord is a normalized string: modifiers in the fixed order Ctrl, Alt, Shift, Meta, then the key —
// "Meta+Shift+O", "Ctrl+P", "Alt+ArrowLeft". Single-character keys are uppercased; named keys keep
// their KeyboardEvent.key spelling. Defaults are declared with the "Mod" placeholder ("Mod+O"), which
// resolves to Meta on a Mac and Ctrl elsewhere — one declaration, both platforms.

import { DEFAULT_CHORDS } from "./commands";

export type Bindings = Record<string, string>;   // command id → chord ("" = deliberately unbound)

const KEY = "romp:keys";
export const KEYS_EVENT = "romp:keys";           // window event raised on every save (same-document)

// ── chord model ───────────────────────────────────────────────────────────────────────────────────

const MOD_ORDER = ["Ctrl", "Alt", "Shift", "Meta"];

// The chord a keydown spells, or null when it's a bare modifier (still being held, nothing to bind).
export function chordOf(e: { key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }): string | null {
  const k = e.key;
  if (!k || k === "Control" || k === "Alt" || k === "Shift" || k === "Meta") return null;
  const parts: string[] = [];
  if (e.ctrlKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey) parts.push("Shift");
  if (e.metaKey) parts.push("Meta");
  parts.push(k.length === 1 ? k.toUpperCase() : k);
  return parts.join("+");
}

// A default's "Mod" resolves per platform, and the result is NORMALIZED to the canonical modifier
// order — every comparison flows through here, so a default declared "Mod+Shift+O" (Meta+Shift) and
// the keydown's own spelling (Shift+Meta) land on the same string. The executed test caught the
// mismatch: without the re-sort, no Shift-carrying default ever matched a real keypress.
export function resolveChord(chord: string, mac: boolean): string {
  const parts = chord.replace(/(^|\+)Mod(\+)/, (m, a, b) => a + (mac ? "Meta" : "Ctrl") + b).split("+");
  const key = parts.pop() || "";
  const mods = MOD_ORDER.filter((m) => parts.includes(m));
  return [...mods, key].join("+");
}

// Chords a binding may NOT be: bare typing/navigation keys the panes own (Escape closes modals,
// Enter/Tab/Space/Backspace type). With modifiers they're fine (Ctrl+Enter is a real chord).
export function bindable(chord: string): boolean {
  if (chord.includes("+")) {
    const key = chord.split("+").pop() || "";
    return key !== "Escape";   // Escape stays the universal close, whatever the modifiers
  }
  if (/^(Escape|Enter|Tab| |Backspace|Delete)$/.test(chord)) return false;   // the panes own these bare
  return chord.length > 1;     // bare named keys (F1, Home) are fine; a bare letter would fire while typing
}

// The chat/pane keys that are BEHAVIOR, not bindable commands — listed so the one dialog answers "what can my
// keyboard do" completely, clearly marked built-in (Enter-to-send is deliberately not here: a typing key nobody
// looks up, the user 2026-08-09). Pure data, here rather than in the dialog, because the recorder REFUSES these
// too (2026-09-10): a hot key recorded as Alt+ArrowLeft would never fire — the shell's pane-focus script takes
// the key first — so the row says who owns it instead of binding a dead chord.
export const BUILT_IN: Array<[string, string]> = [
  ["Shift+Enter", "New line in the composer"],
  ["Escape", "Leave the composer / close a panel"],
  ["Ctrl+C", "Interrupt the session (composer)"],
  ["Alt+Arrows", "Move focus between panes"],
];

// A command's FIXED key: a built-in the pane owns that does what the command does, shown on the command's own
// row beside its rebindable chord rather than in the built-in section (the maintainer, 2026-09-23: the arrows
// are the natural keys and belong in the keymap). Command id → [chord spec, what the recorder says when it
// refuses the chord]. The bare arrows step sessions from the tab bar and anywhere in the chat outside a text
// field; they cannot be bound (they are the feed's card cursor, the file browser's back, the viewer's step in
// their own panes), so the recorder refuses them exactly as it refuses the rows above.
export const FIXED_KEYS: Record<string, [string, string]> = {
  "chat.nextTab": ["ArrowRight", "Go to the next session, from the tab bar"],
  "chat.prevTab": ["ArrowLeft", "Go to the previous session, from the tab bar"],
};

// The built-in behaviour a chord already belongs to (its description), or null when it is free to bind.
// "Alt+Arrows" stands for the four arrows; " / " separates alternatives; Ctrl here is the literal key.
// A command's fixed key (FIXED_KEYS) is a built-in too.
export function builtInOwner(chord: string, mac: boolean): string | null {
  const want = resolveChord(chord, mac);
  for (const [spec, what] of [...BUILT_IN, ...Object.values(FIXED_KEYS)]) {
    for (const alt of spec.split(" / ")) {
      const forms = alt.endsWith("+Arrows")
        ? ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].map((k) => alt.slice(0, -"Arrows".length) + k)
        : [alt];
      if (forms.some((f) => resolveChord(f, mac) === want)) return what;
    }
  }
  return null;
}

// Display: ⌘⇧O on a Mac (symbols, no separators), Ctrl+Shift+O elsewhere.
export function displayChord(chord: string, mac: boolean): string {
  const c = resolveChord(chord, mac);
  const KEYCAP: Record<string, string> = { ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓" };
  const parts = c.split("+").map((p) => KEYCAP[p] || p);
  if (!mac) return parts.join("+");
  const SYM: Record<string, string> = { Ctrl: "⌃", Alt: "⌥", Shift: "⇧", Meta: "⌘" };
  return parts.map((p) => SYM[p] || p).join("");
}

// ── the store: user overrides over per-command defaults ──────────────────────────────────────────

export function loadOverrides(): Bindings {
  try {
    const d = JSON.parse(localStorage.getItem(KEY) || "{}");
    return d && typeof d === "object" ? (d as Bindings) : {};
  } catch (e) { return {}; }
}

// chord = the new binding; "" = unbind; null = forget the override (back to the default)
export function saveOverride(id: string, chord: string | null): void {
  const all = loadOverrides();
  if (chord === null) delete all[id]; else all[id] = chord;
  try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (e) { /* storage full/blocked */ }
  try { window.dispatchEvent(new Event(KEYS_EVENT)); } catch (e) { /* non-DOM (tests) */ }
}

// The chord a command answers to right now: the override when one exists, else its default, resolved.
export function effectiveChord(id: string, defaultChord: string | undefined, overrides: Bindings, mac: boolean): string {
  const o = overrides[id];
  if (o !== undefined) return o === "" ? "" : resolveChord(o, mac);
  return defaultChord ? resolveChord(defaultChord, mac) : "";
}

// chord → command id for the dispatcher, built from the full command list. A chord the reader SAVED for a
// command outranks any command's DEFAULT on the same chord (review, 2026-09-23): a default that lands on a chord
// someone had already bound — the session pair shipping on Ctrl+Alt+arrows, where a saved "Focus the next chat
// column" could sit — must not take the key from them; the dialog marks such a default as yielding (yieldsTo).
// Two SAVED bindings on one chord can only enter via a hand-edited store (the dialog refuses them) — the LAST
// registered command wins there, and the dialog shows both so the loser is visible, not silently dead.
export function chordMap(cmds: { id: string; chord?: string }[], overrides: Bindings, mac: boolean): Map<string, string> {
  const m = new Map<string, string>();
  const saved = new Set<string>();
  for (const c of cmds) {                                   // the reader's own bindings first…
    if (overrides[c.id] === undefined) continue;
    const ch = effectiveChord(c.id, c.chord, overrides, mac);
    if (ch) { m.set(ch, c.id); saved.add(ch); }
  }
  for (const c of cmds) {                                   // …then every default whose chord no saved binding holds
    if (overrides[c.id] !== undefined) continue;
    const ch = effectiveChord(c.id, c.chord, overrides, mac);
    if (ch && !saved.has(ch)) m.set(ch, c.id);
  }
  return m;
}

// The command whose SAVED binding holds `id`'s default chord — the one `id` yields to in chordMap — or null: `id`
// carries a saved binding of its own (or a deliberate unbind), has no default, or its default chord is free.
export function yieldsTo(id: string, cmds: { id: string; chord?: string }[], overrides: Bindings, mac: boolean): string | null {
  if (overrides[id] !== undefined) return null;
  const c = cmds.find((x) => x.id === id);
  const ch = c && c.chord ? resolveChord(c.chord, mac) : "";
  if (!ch) return null;
  for (const o of cmds) {
    if (o.id === id || !overrides[o.id]) continue;
    if (resolveChord(overrides[o.id], mac) === ch) return o.id;
  }
  return null;
}

// The command already holding a chord (the conflict the dialog names), or null.
export function conflictOf(chord: string, forId: string, cmds: { id: string; chord?: string }[], overrides: Bindings, mac: boolean): string | null {
  for (const c of cmds) {
    if (c.id === forId) continue;
    if (effectiveChord(c.id, c.chord, overrides, mac) === resolveChord(chord, mac)) return c.id;
  }
  return null;
}

// ── hover discoverability (the user 2026-08-10) ───────────────────────────────────────────────────

// The binding a command answers to RIGHT NOW, in display form ("⌘⇧O" on a Mac, "Ctrl+Shift+O"
// elsewhere); "" when unbound. Reads the live overrides store, so a rebind changes what the next
// hover says — a tooltip advertises the user's configuration, never a stale default.
export function keyHint(id: string): string {
  const mac = typeof navigator !== "undefined" && /Mac|iP(hone|ad|od)/.test(navigator.platform || "");
  const ch = effectiveChord(id, DEFAULT_CHORDS[id], loadOverrides(), mac);
  return ch ? displayChord(ch, mac) : "";
}

// A control's tooltip with its command's current binding appended — "Open a session (⌘⇧O)" — so every
// shortcut is discoverable by hovering the button that does the same thing (the user 2026-08-10).
// The bare title when the command is unbound.
export function titleWithKey(base: string, id: string): string {
  const k = keyHint(id);
  return k ? (base ? base + " (" + k + ")" : k) : base;
}

// ── the dispatch decision (pure: the wiring calls this per keydown) ───────────────────────────────

// Modifier-less (or Shift-only) chords must never fire while typing — same rule the chat's bare-arrow
// handlers follow. Chords with a real modifier fire regardless of focus. A keydown inside an input method's
// composition (isComposing, or the legacy keyCode 229) is the composition's, never a chord — the type-to-focus
// handler's rule, here too (review, 2026-09-23).
export function dispatchable(e: { ctrlKey: boolean; altKey: boolean; metaKey: boolean; repeat?: boolean; isComposing?: boolean; keyCode?: number }, typing: boolean): boolean {
  if (e.repeat) return false;
  if (e.isComposing || e.keyCode === 229) return false;
  if (typing && !e.ctrlKey && !e.altKey && !e.metaKey) return false;
  return true;
}
