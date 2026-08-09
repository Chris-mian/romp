// The command registry behind the palette (Cmd/Ctrl+P). Anything the dashboard can do gets
// registered here as a command; the palette is a fuzzy view over this list, so a new action
// becomes keyboard-reachable by registering it — never by minting another hotkey.

export type PaletteCommand = {
  id: string;       // stable, dot-namespaced ("session.open")
  title: string;    // what the palette shows and matches on — the user's words, verb first
  chord?: string;   // DEFAULT key binding, "Mod" form ("Mod+O" — Meta on a Mac, Ctrl elsewhere).
                    // The user's overrides live in the keybindings store (romp:keys); what a command
                    // actually answers to is effectiveChord(), and the palette's hotkey chip shows
                    // that, so a rebound command never advertises a stale default (the user 2026-08-09).
  hidden?: boolean; // bindable but not listed in the palette (palette.toggle: running "toggle the
                    // palette" FROM the palette would just blink it)
  run: () => void;
};

const commands = new Map<string, PaletteCommand>();

export function registerCommand(cmd: PaletteCommand): void {
  commands.set(cmd.id, cmd);   // re-registering an id replaces it, so a re-boot never duplicates
}

export function commandList(): PaletteCommand[] {
  return Array.from(commands.values());   // registration order — the palette's empty-query order
}

export function runCommand(id: string): boolean {
  const c = commands.get(id);
  if (!c) return false;
  c.run();
  return true;
}
