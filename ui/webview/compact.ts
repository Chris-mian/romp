// Pure transcript-compaction logic (no DOM), so it can be unit-tested. Compact mode (the user
// 2026-06-14): hide "thinking" blocks entirely, and collapse each maximal run of TWO OR MORE consecutive
// tool uses into ONE summary line. A LONE tool stays inline — it renders first-class (its own tool line +
// expandable fold), since there's nothing to collapse and "Bash(…)" reads cleaner than "1 Bash" (the user
// 2026-06-22). Thinking is dropped FIRST, so tools separated only by thinking still count as consecutive;
// tools separated by visible content (an assistant reply, a prompt, …) do not. The rail timestamp logic
// runs over the RESULT of this, so the stamps reflect the compacted stream.
// The same shape folds LOW-STAKES NOTICES (2026-09-08, generalising the T131 retry-run fold): a run of ≥2
// consecutive foldable notices — a recovery, an effort change, a model swap, a reload, an interrupt + its
// settle, a background report, a system reminder, a romp notice — collapses into one `noticegroup` head.
// Which events are foldable is the caller's call (render.ts isFoldableNotice, passed per event): peers,
// API errors, compaction/clear boundaries, asks, to-dos, dividers and every bubble stay standalone.

/** The events compact mode may sweep into a noticegroup: the low-stakes, self-similar rows (a recovery, an effort
 *  change, a model swap, a reload, an interrupt marker and its settle, an injected notice: a system reminder or a
 *  romp notice on a user row). Peers, API errors, boundaries, asks, to-dos and every real bubble stay standalone.
 *  Pure over the event's shape so render.ts (the fold) and reveal-progress.ts (what counts as a message) share ONE
 *  reading (T336 review: the progress count took injected notices for messages). */
export function isFoldableNoticeShape(ev: { kind: string; interruptMarker?: unknown; interruptSettle?: unknown; rompSystem?: unknown; md?: unknown; source?: unknown; human?: unknown; undelivered?: unknown }): boolean {
  if (ev.kind === "retried" || ev.kind === "effortApplied" || ev.kind === "modelFallback" || ev.kind === "reconnecting") return true;
  if (ev.kind === "user") return !!(ev.interruptMarker || (ev.rompSystem && ev.md) || (ev.source && !ev.human && !ev.undelivered));
  if (ev.kind === "assistant") return !!ev.interruptSettle;
  return false;
}

export type DisplayItem =
  | { kind: "event"; index: number }            // a pass-through event, by its index in the source array
  | { kind: "toolgroup"; indices: number[] }    // a collapsed run of ≥2 consecutive tool uses (a lone tool is an "event")
  | { kind: "noticegroup"; indices: number[] }  // a collapsed run of ≥2 consecutive foldable notices (was the "retried"-only retrygroup)
  | { kind: "gap"; lo: number; hi: number; before: number };   // turns [lo, hi) the page does not hold (T386 stage 2): empty space before event `before`

// Tools that are an EXCEPTION to collapsing: they render FIRST-CLASS even in compact mode, never swept
// into a toolgroup (the user 2026-06-17). AskUserQuestion is the "↳ You answered Claude's question" box —
// a reply to a popup, not bookkeeping — so it must stay visible, not buried under a collapsed tool run.
export const STANDALONE_TOOLS = new Set<string>(["AskUserQuestion"]);

// Given the per-event `kind` strings (and, for tool events, the tool `names` so the standalone-tool
// exception can be applied; and `notices[i]` = whether event i is a foldable notice), produce the
// compacted display list. `names[i]` is the tool name for a "tool" event, undefined otherwise. Without
// `notices`, only a bare "retried" run folds (the pre-2026-09-08 behaviour, kept for callers that pass none).
export function compactDisplay(kinds: readonly string[], names?: readonly (string | undefined)[], notices?: readonly boolean[]): DisplayItem[] {
  const out: DisplayItem[] = [];
  let run: number[] | null = null;
  let noticeRun: number[] | null = null;          // consecutive foldable notices
  // a LONE tool passes through as a normal event (its first-class inline tool line + fold); only a run of
  // TWO OR MORE collapses into a summary toolgroup (the user 2026-06-22)
  const flush = () => {
    if (!run) return;
    out.push(run.length === 1 ? { kind: "event", index: run[0] } : { kind: "toolgroup", indices: run });
    run = null;
  };
  // same shape for notice runs (the user 2026-08-27, seventeen consecutive recovery rows): a lone notice
  // stays a first-class row; a run of ≥2 collapses into one expandable head
  const flushNotices = () => {
    if (!noticeRun) return;
    out.push(noticeRun.length === 1 ? { kind: "event", index: noticeRun[0] } : { kind: "noticegroup", indices: noticeRun });
    noticeRun = null;
  };
  const foldable = (i: number) => notices ? !!notices[i] : kinds[i] === "retried";
  for (let i = 0; i < kinds.length; i++) {
    const k = kinds[i];
    if (k === "thinking") continue;                 // hidden — and does NOT break a tool run
    // A standalone tool (AskUserQuestion) is NOT collapsed: it breaks the run and passes through as its
    // own event, so renderTool → renderAsk draws the first-class box instead of "+1" inside a group.
    if (k === "tool" && !STANDALONE_TOOLS.has(names?.[i] ?? "")) { flushNotices(); (run ||= []).push(i); continue; }
    if (foldable(i)) { flush(); (noticeRun ||= []).push(i); continue; }
    flush();
    flushNotices();
    out.push({ kind: "event", index: i });
  }
  flush();
  flushNotices();
  return out;
}

/** The member a display unit is PLACED and TIMED by (T339, the user 2026-09-11). A collapsed NOTICE run anchors on the
 *  member with the LATEST epoch (ties: the later one), never the first: a run can hold a notice stamped earlier than the
 *  rows around it (one that kept the moment it was queued and landed in the transcript at delivery), so timed by its first
 *  member the run wore yesterday's clock among today's rows and the day walk read the step back as a day boundary. The
 *  latest member is the one in sequence with its neighbours; the head's rail time, the day walk and the walk's exit all
 *  read it (a run with no timed member falls to its first). Every other unit keeps its FIRST member, as before: a lone
 *  event is its own anchor, and a tool run's members are in transcript order with its head timed by its first.
 *  `epochAt(i)` is event i's epoch or null. */
export function itemAnchor(it: DisplayItem, epochAt: (i: number) => number | null): number {
  if (it.kind === "event") return it.index;
  if (it.kind === "gap") return it.before;   // a gap has no member: the event below it stands for its place
  if (it.kind === "toolgroup") return it.indices[0];
  let best = it.indices[0], bestEp: number | null = null;
  for (const i of it.indices) {
    const ep = epochAt(i);
    if (ep != null && (bestEp == null || ep >= bestEp)) { best = i; bestEp = ep; }
  }
  return best;
}

// One pluralized count of a tool kind, e.g. { label: "Edits", count: 3 }. The label keeps the tool's
// own Capitalized name (so it reads AS a tool — the user 2026-06-14, matching the bold .tool-name in
// the non-compact view); only the Edit variants merge under "Edit".
// ── The tool rows in the user's terms (T418, the user 2026-09-14: the chat's tool rows read the way the desktop app's do) ──
// The group head speaks by ACTION, not by tool name: "Ran 11 commands, read 4 files, edited 3 files, created 2 files +37 -0". A single
// tool use reads the same phrase in the singular. Inside a group each row's label is the model's own description when it wrote one,
// else a phrase derived from the tool's input in the same voice. Nothing here reads desc for the head's counts or totals: those come
// from the tool names and the edits' diff rows alone. Counts: commands, searches, fetches, agents and other tools count USES; reads,
// edits and creations count DISTINCT files; the head orders its phrases by the number it prints.

export interface ToolLike {
  name: string;
  desc?: string;
  input?: string;       // the tool_use input as JSON (clipped by the kernel)
  file?: string;        // file_path or path, when the input carried one
  diff?: string;        // the kernel's minimal diff for Edit / MultiEdit / Write ("- old" / "+ new" lines)
  diffRows?: readonly { sign: string }[];   // the real-line diff rows when the record carried a structuredPatch
}

export type ToolAction = "command" | "create" | "edit" | "read" | "search" | "fetch" | "agent" | "tasklist" | "tool";

const ACTION: Record<string, ToolAction> = {
  Bash: "command",
  Write: "create",
  Edit: "edit", MultiEdit: "edit", NotebookEdit: "edit",
  Read: "read",
  Grep: "search", Glob: "search",
  WebFetch: "fetch", WebSearch: "fetch",
  Agent: "agent", Task: "agent", Workflow: "agent",
  TodoWrite: "tasklist", TaskCreate: "tasklist", TaskUpdate: "tasklist", TaskGet: "tasklist", TaskList: "tasklist",
};
export function toolAction(name: string): ToolAction { return ACTION[name] || "tool"; }

/** +added −removed over a tool's diff: the real-line rows when present, else the minimal diff's signed lines. */
export function diffTotals(t: ToolLike): { add: number; del: number } {
  if (t.diffRows && t.diffRows.length) {
    let add = 0, del = 0;
    for (const r of t.diffRows) { if (r.sign === "+") add++; else if (r.sign === "-") del++; }
    return { add, del };
  }
  let add = 0, del = 0;
  for (const ln of (t.diff || "").split("\n")) { if (ln.startsWith("+")) add++; else if (ln.startsWith("-")) del++; }
  return { add, del };
}

function parseInput(t: ToolLike): Record<string, unknown> {
  try { const o = JSON.parse(t.input || ""); return o && typeof o === "object" ? o as Record<string, unknown> : {}; } catch { return {}; }
}
function clip(s: string, n = 80): string { s = s.replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
/** The host a fetched url names; a url with no host (file:, data:, about:) falls to the url itself, clipped like every other label part. */
function hostOf(url: string): string { try { const h = new URL(url).hostname; return h ? clip(h) : clip(url); } catch { return clip(url); } }   // the host clipped like every label part (round three, low c)
/** The one search's own words: "for <pattern>" (Grep, Glob); the path, when the input carries one, is the event's file, which the
 *  renderer prints as the link after "in ". */
function searchWords(t: ToolLike): string | null {
  const o = parseInput(t);
  if (t.name === "Grep" || t.name === "Glob") { const pat = typeof o.pattern === "string" ? o.pattern : ""; return pat ? "for " + clip(pat) : null; }
  return null;
}
const totalsText = (add: number, del: number): string => (add || del ? `+${add} -${del}` : "");

/** One head phrase per action over a group of tool uses. Commands, searches, fetches, agents and other tools count uses; reads,
 *  edits and creations count DISTINCT files (a file edited twice is one file, its rows summed). The phrases are ordered by the
 *  number they print (the largest first; ties keep first appearance). The edits' totals are returned apart, summed over every
 *  edit, for the caller to print ONCE: "ran 11 commands", "read 4 files", "edited 3 files", "created 2 files", "searched 3 times"
 *  (or "searched for <pattern>" for the group's sole search), "fetched 2 pages", "ran 2 agents", "updated the task list",
 *  "used 2 tools". A creation prints no totals: the kernel emits no diff for a Write. */
export interface ActionPhrase { action: ToolAction; count: number; printed: number; text: string; add: number; del: number }
export function actionPhrases(tools: readonly ToolLike[]): ActionPhrase[] {
  const order: ToolAction[] = [];
  const by = new Map<ToolAction, { count: number; files: Set<string>; nofile: number; add: number; del: number; first: ToolLike }>();
  for (const t of tools) {
    const a = toolAction(t.name);
    let e = by.get(a);
    if (!e) { e = { count: 0, files: new Set(), nofile: 0, add: 0, del: 0, first: t }; by.set(a, e); order.push(a); }
    e.count++;
    if (t.file) e.files.add(t.file); else e.nofile++;
    if (a === "edit") { const d = diffTotals(t); e.add += d.add; e.del += d.del; }
  }
  const out: ActionPhrase[] = [];
  for (const a of order) {
    const e = by.get(a)!; const n = e.count;
    const byFile = a === "read" || a === "edit" || a === "create";
    const files = e.files.size + e.nofile;   // the distinct files, plus one per use that carried no file (a NotebookEdit's notebook_path is not a file for the kernel today): round three's medium, where "size or uses" let a sibling's path decide the count
    const printed = byFile ? files : n;
    let text: string;
    switch (a) {
      case "command": text = n === 1 ? "ran a command" : `ran ${n} commands`; break;
      case "create": text = files === 1 ? "created a file" : `created ${files} files`; break;
      case "edit": text = files === 1 ? "edited a file" : `edited ${files} files`; break;
      case "read": text = files === 1 ? "read a file" : `read ${files} files`; break;
      case "search": { const w = n === 1 ? searchWords(e.first) : null; text = n === 1 ? (w ? "searched " + w : "searched once") : `searched ${n} times`; break; }
      case "fetch": text = n === 1 ? "fetched a page" : `fetched ${n} pages`; break;
      case "agent": text = n === 1 ? "ran an agent" : `ran ${n} agents`; break;
      case "tasklist": text = "updated the task list"; break;
      default: text = n === 1 ? "used a tool" : `used ${n} tools`;
    }
    out.push({ action: a, count: n, printed, text, add: e.add, del: e.del });
  }
  out.sort((x, y) => y.printed - x.printed);   // stable: ties keep first appearance
  return out;
}
/** The head's parts: the phrases joined by commas, the first letter capitalised, and the edits' totals summed for one printing. */
export function actionParts(tools: readonly ToolLike[]): { text: string; add: number; del: number } {
  const ph = actionPhrases(tools);
  const s = ph.map((p) => p.text).join(", ");
  return { text: s ? s[0].toUpperCase() + s.slice(1) : "", add: ph.reduce((a, p) => a + p.add, 0), del: ph.reduce((a, p) => a + p.del, 0) };
}
/** The whole head line as text: the phrases, then the totals once at the end when any edit carried rows. */
export function actionHead(tools: readonly ToolLike[]): string {
  const p = actionParts(tools); const tot = totalsText(p.add, p.del);
  return p.text + (tot ? " " + tot : "");
}

/** The raw text a tool row's expanded IN row shows (T418): a Bash command as the model typed it (the desktop app's "$ …" box);
 *  every other tool its input JSON as before. */
export function toolInputText(t: ToolLike): string {
  if (t.name === "Bash") { const o = parseInput(t); if (typeof o.command === "string" && o.command) return o.command; }
  return t.input || "";
}

/** A row's collapsed label: the model's description when it wrote one, else the derived phrase in the same voice. `code` marks a
 *  label that is the command itself (a Bash with no description), for the code face. `link` marks a label that ends expecting the
 *  event's file, which the renderer prints as the link right after it ("Read ", "Edited ", "Created ", "Searched for x in "); an
 *  event with a file the label does not name still gets its link after the label, so no file is lost and none is printed twice.
 *  An edit's totals are the diff fold's toggle, the renderer's; a failed edit changed nothing and prints none (round three). */
export interface RowLabel { text: string; link?: boolean; code?: boolean; secondary?: string }
export function toolRowLabel(t: ToolLike): RowLabel {
  const desc = (t.desc || "").trim();
  if (desc) return { text: clip(desc, 160) };
  const o = parseInput(t);
  if (t.name === "WebSearch") { const q = typeof o.query === "string" ? o.query : ""; return { text: q ? "Searched the web for " + clip(q) : "Searched the web" }; }   // its head counts as a fetch; its row says what it searched
  const a = toolAction(t.name);
  switch (a) {
    case "command": {
      const cmd = typeof o.command === "string" ? o.command : "";
      const first = cmd.split("\n").map((l) => l.trim()).find((l) => l.length > 0) || "";   // the first non-blank line: a command opening with a blank line is not an empty label
      return first ? { text: clip(first), code: true } : { text: "Ran a command" };
    }
    case "read": return t.file ? { text: "Read ", link: true } : { text: "Read a file" };
    case "edit": return t.file ? { text: "Edited ", link: true } : { text: "Edited a file" };
    case "create": return t.file ? { text: "Created ", link: true } : { text: "Created a file" };
    case "search": { const w = searchWords(t); const base = w ? "Searched " + w : "Searched"; return t.file ? { text: base + " in ", link: true } : { text: base }; }
    case "fetch": { const u = typeof o.url === "string" ? o.url : ""; return { text: u ? "Fetched " + hostOf(u) : "Fetched a page" }; }
    case "agent": return { text: "Ran an agent" };
    case "tasklist": return { text: "Updated the task list" };
    default: return { text: "Used a tool", secondary: t.name };
  }
}
