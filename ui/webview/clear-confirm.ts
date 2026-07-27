// A typed /clear ends the conversation, and the kernel's episode boundary then settles the
// session's open cards with it (plans/clear-episodes.md). The chat composer is the one place romp
// sees the command BEFORE it runs, so it must never pass silently while open cards exist (the user
// 2026-07-27): sendComposer gates the send on an explicit confirm when clearConfirmDetail returns a
// detail. Pure helpers here so the gate's logic is node-testable without the DOM.

// mirrors the kernel's _is_clear_cmd (sdk_backend.py) — the same truth table, client-side
export function isClearCmd(text: string): boolean {
  const t = text.trim();
  return t === "/clear" || t.startsWith("/clear ");
}

export interface OpenCardNode { depth: number; done: boolean; cleared?: boolean; text: string; }

// The open TOP-level cards a /clear would drop — the same population the kernel's boundary settle
// takes (open tops only; completed stay, already-cleared are gone). Blocked tops count: they are
// open, and dropping an owed question is exactly the silent loss the gate exists to stop.
export function openTopTitles(tree: OpenCardNode[] | undefined | null): string[] {
  return (tree || []).filter((n) => n.depth === 0 && !n.done && !n.cleared).map((n) => n.text);
}

// The confirm modal's detail line, or null when no confirm is needed (nothing open to drop).
export function clearConfirmDetail(titles: string[]): string | null {
  if (!titles.length) return null;
  const list = titles.join(", ");
  const shown = list.length > 140 ? list.slice(0, 139) + "…" : list;
  const n = titles.length;
  return (n === 1 ? "Its 1 open card gets dropped with it: " : "Its " + n + " open cards get dropped with it: ")
    + shown
    + ". Undo clear on the feed restores the cards, but the agent will no longer remember the work behind them.";
}
