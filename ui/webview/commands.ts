// The command registry behind the palette (Cmd/Ctrl+P). Anything the dashboard can do gets
// registered here as a command; the palette is a fuzzy view over this list, so a new action
// becomes keyboard-reachable by registering it — never by minting another hotkey.

export type PaletteCommand = {
  id: string;      // stable, dot-namespaced ("session.open")
  title: string;   // what the palette shows and matches on — the user's words, verb first
  kbd?: string;    // display-only hotkey chip ("⌘O"); the actual binding lives with the key wiring
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
