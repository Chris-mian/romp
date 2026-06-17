// Pure transcript-compaction logic (no DOM), so it can be unit-tested. Compact mode (the user
// 2026-06-14): hide "thinking" blocks entirely, and collapse each maximal run of CONSECUTIVE tool
// uses into ONE summary line. Thinking is dropped FIRST, so tools separated only by thinking still
// count as consecutive; tools separated by visible content (an assistant reply, a prompt, …) do not.
// The rail timestamp logic runs over the RESULT of this, so the stamps reflect the compacted stream.

export type DisplayItem =
  | { kind: "event"; index: number }            // a pass-through event, by its index in the source array
  | { kind: "toolgroup"; indices: number[] };   // a collapsed run of consecutive tool uses (≥1)

// Tools that are an EXCEPTION to collapsing: they render FIRST-CLASS even in compact mode, never swept
// into a toolgroup (the user 2026-06-17). AskUserQuestion is the "↳ You answered Claude's question" box —
// a reply to a popup, not bookkeeping — so it must stay visible, not buried under a collapsed tool run.
export const STANDALONE_TOOLS = new Set<string>(["AskUserQuestion"]);

// Given the per-event `kind` strings (and, for tool events, the tool `names` so the standalone-tool
// exception can be applied), produce the compacted display list. `names[i]` is the tool name for a
// "tool" event, undefined otherwise.
export function compactDisplay(kinds: readonly string[], names?: readonly (string | undefined)[]): DisplayItem[] {
  const out: DisplayItem[] = [];
  let run: number[] | null = null;
  const flush = () => { if (run) { out.push({ kind: "toolgroup", indices: run }); run = null; } };
  for (let i = 0; i < kinds.length; i++) {
    const k = kinds[i];
    if (k === "thinking") continue;                 // hidden — and does NOT break a tool run
    // A standalone tool (AskUserQuestion) is NOT collapsed: it breaks the run and passes through as its
    // own event, so renderTool → renderAsk draws the first-class box instead of "+1" inside a group.
    if (k === "tool" && !STANDALONE_TOOLS.has(names?.[i] ?? "")) { (run ||= []).push(i); continue; }
    flush();
    out.push({ kind: "event", index: i });
  }
  flush();
  return out;
}

// One pluralized count of a tool kind, e.g. { label: "Edits", count: 3 }. The label keeps the tool's
// own Capitalized name (so it reads AS a tool — the user 2026-06-14, matching the bold .tool-name in
// the non-compact view); only the Edit variants merge under "Edit".
export interface ToolCount { label: string; count: number; }

const LABEL: Record<string, string> = { Edit: "Edit", MultiEdit: "Edit", NotebookEdit: "Edit" };
function toolLabel(name: string): string { return LABEL[name] || name; }   // else the tool's own name
function plural(word: string, n: number): string {
  if (n === 1) return word;
  return word + (/(s|sh|ch|x|z)$/i.test(word) ? "es" : "s");
}

// Counts per tool kind from a run of tool NAMES: merge to a display label, order by count (desc; ties
// keep first-appearance via stable sort), pluralize by count.
export function toolCounts(names: readonly string[]): ToolCount[] {
  const counts = new Map<string, number>();
  for (const nm of names) { const w = toolLabel(nm); counts.set(w, (counts.get(w) || 0) + 1); }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([w, n]) => ({ label: plural(w, n), count: n }));
}

// "3 Edits, 2 Reads, 1 Bash" — the plain-text form (used for titles / tests). The rendered line styles
// each tool label in bold (see render.ts renderToolGroup), but the words are identical.
export function summarizeTools(names: readonly string[]): string {
  return toolCounts(names).map((c) => `${c.count} ${c.label}`).join(", ");
}
