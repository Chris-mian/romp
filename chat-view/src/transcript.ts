// Parse a Claude Code JSONL transcript into a flat list of chat events along
// the ACTIVE conversation path (leaf -> root), folding tool results into their
// calls. Runs in the extension host (Node). See README for the format notes.

// An image in a user turn: src is what the webview can display (a data: URL for
// an inline base64 paste, or "path:<p>" for an on-disk file the host hydrates);
// path is the image's on-disk location when known — shown as an open/copy link.
export interface UserImage { src: string; path?: string }

// Every event carries `uuid` = the source JSONL line it came from, so the
// webview can anchor each rendered turn with data-uuid (deep-link target).
export type ChatEvent =
  | { kind: "user"; md: string; ts?: string; uuid?: string; reminders?: string[]; human?: boolean; images?: UserImage[] }
  | { kind: "assistant"; md: string; ts?: string; uuid?: string }
  | { kind: "thinking"; text: string; encrypted: boolean; ts?: string; uuid?: string }
  | {
      kind: "tool";
      name: string;
      desc: string;
      input: string;
      output: string;
      isError: boolean;
      ts?: string;
      uuid?: string;
      resultUuid?: string;   // the tool_result line's uuid (e.g. an AskUserQuestion answer) — the deep-link anchor the timeline emits
      file?: string;   // path for Read/Edit/Write/NotebookEdit — enables open-in-editor
      diff?: string;   // trimmed red/green diff for Edit/MultiEdit
    }
  // A romp postal message (peer mail), folded out of the raw delivery prose /
  // send_message tool call by postal-spec.ts. direction: "in" = received,
  // "out" = sent. peer = the other session; color = its romp identity colour.
  | {
      kind: "postal";
      direction: "in" | "out";
      peer: string;
      color: { bg: string; fg: string } | null;
      body: string;
      mid?: string;      // postal message id (joins to the feed modal's handoff nodes)
      t?: number;        // epoch seconds (incoming, from the timeline log)
      park?: boolean;    // delivered while the recipient was offline
      status?: "delivered" | "parked"; // outgoing send result
      ts?: string;
      uuid?: string;
    }
  // The Claude Code Task to-do list — TaskCreate/TaskUpdate tool calls folded into
  // one live checklist (current status per task) instead of a card per call.
  | { kind: "todo"; tasks: TodoTask[]; ts?: string; uuid?: string }
  // Messages the user submitted while the session was still working — Claude Code
  // QUEUED them (transcript `queue-operation` enqueue records not yet resolved).
  // Mirrors the queue Claude Code shows below its input; cleared as each dequeues.
  | { kind: "queued"; texts: string[]; ts?: string; uuid?: string };

export interface TodoTask { id: string; subject: string; activeForm?: string; status: "pending" | "in_progress" | "completed" | string }

export interface SessionStatus {
  working: boolean;
  sinceEpoch: number | null; // start of the current turn (last human prompt)
}

export interface ParsedTranscript {
  sessionId: string;
  events: ChatEvent[];
  status: SessionStatus;
}

type Line = Record<string, any>;

const EMPTY = Buffer.alloc(0);

// Incremental parser state: the accumulated DAG (byUuid + ordered), the folded
// tool-result map, and the bytes of a not-yet-terminated final line. Feed
// appended chunks with feed(); read a snapshot with buildParsed(). This lets a
// live tailer avoid re-reading and re-JSON-parsing the whole (possibly multi-MB)
// transcript on every change — only the newly-appended bytes are parsed.
export interface IncParser {
  byUuid: Map<string, Line>;
  ordered: Line[];
  toolOut: Map<string, { text: string; isError: boolean; uuid?: string }>;
  // queue-operation records in arrival order (enqueue/dequeue/remove). They carry
  // NO uuid, so they never enter `ordered`/`byUuid` — kept here for foldQueue().
  queueOps: { op: string; content: string | null }[];
  lastLeaf?: string;
  sessionId: string;
  leftover: Buffer; // bytes after the last '\n' — an incomplete trailing line
}

export function newIncParser(): IncParser {
  return { byUuid: new Map(), ordered: [], toolOut: new Map(), queueOps: [], sessionId: "", leftover: EMPTY };
}

function ingestLine(p: IncParser, rawLine: string): void {
  const s = rawLine.trim();
  if (!s) return;
  let o: Line;
  try {
    o = JSON.parse(s);
  } catch {
    return;
  }
  if (o.type === "last-prompt" && o.leafUuid) p.lastLeaf = o.leafUuid;
  if (o.sessionId && !p.sessionId) p.sessionId = o.sessionId;
  // queued-message ops (no uuid → not part of the DAG): enqueue carries the text,
  // dequeue/remove resolve the oldest pending one (FIFO). Folded in buildParsed.
  if (o.type === "queue-operation" && typeof o.operation === "string") {
    p.queueOps.push({ op: o.operation, content: typeof o.content === "string" ? o.content : null });
  }
  if (o.uuid) {
    p.byUuid.set(o.uuid, o);
    p.ordered.push(o);
  }
  // Fold tool_results into a map keyed by tool_use_id as they stream in, so
  // buildParsed() never has to rescan every line for them on a snapshot.
  if (o.type === "user" && Array.isArray(o.message?.content)) {
    for (const b of o.message.content) {
      if (b && b.type === "tool_result" && b.tool_use_id) {
        p.toolOut.set(b.tool_use_id, {
          text: contentToText(b.content),
          isError: !!b.is_error,
          uuid: o.uuid,   // the tool_result (answer) USER line uuid → deep-link anchor for the tool widget
        });
      }
    }
  }
}

// Feed newly-appended bytes. Only complete (newline-terminated) lines are
// parsed; a partial trailing line is buffered until its '\n' arrives, so a
// half-written record is never parsed. Operates on bytes so a multibyte UTF-8
// char split across two reads is never mis-decoded.
export function feed(p: IncParser, chunk: Buffer): void {
  const buf = p.leftover.length ? Buffer.concat([p.leftover, chunk]) : chunk;
  let start = 0;
  let nl = buf.indexOf(0x0a, start);
  while (nl !== -1) {
    ingestLine(p, buf.toString("utf8", start, nl));
    start = nl + 1;
    nl = buf.indexOf(0x0a, start);
  }
  // Copy the remainder so we don't pin the whole chunk buffer in memory.
  p.leftover = start < buf.length ? Buffer.from(buf.subarray(start)) : EMPTY;
}

// Parse any buffered trailing bytes as a final line. For a one-shot parse of a
// complete file (whose last line may lack a newline); NOT for live tailing,
// where the trailing bytes may be a half-written record.
function flush(p: IncParser): void {
  if (p.leftover.length) {
    ingestLine(p, p.leftover.toString("utf8"));
    p.leftover = EMPTY;
  }
}

// Derive the chat events + status from the current parser state. Pure read —
// safe to call after any feed().
// Fold the active path's TaskCreate/TaskUpdate calls into ONE checklist (current
// status per task). Task id comes from TaskCreate's RESULT ("Task #N created…");
// TaskUpdate carries {taskId, status}. Returns the tasks (creation order) + the uuid
// of the LAST task line, so the render places the checklist there (not one per call).
function foldTasks(path: Line[], toolOut: Map<string, { text: string; isError: boolean; uuid?: string }>): { tasks: TodoTask[]; lastUuid?: string } | null {
  const tasks = new Map<string, TodoTask & { order: number }>();
  let order = 0;
  let lastUuid: string | undefined;
  for (const o of path) {
    if (o.type !== "assistant" || !Array.isArray(o.message?.content)) continue;
    for (const b of o.message.content) {
      if (!b || b.type !== "tool_use") continue;
      if (b.name === "TaskCreate") {
        const m = String(toolOut.get(b.id)?.text || "").match(/Task #(\d+)/);
        const id = m ? m[1] : "c" + order;
        tasks.set(id, { id, subject: String(b.input?.subject || ""), activeForm: b.input?.activeForm ? String(b.input.activeForm) : undefined, status: "pending", order: order++ });
        lastUuid = o.uuid;
      } else if (b.name === "TaskUpdate") {
        const t = tasks.get(String(b.input?.taskId ?? ""));
        if (t) t.status = String(b.input?.status || t.status);
        lastUuid = o.uuid;
      }
    }
  }
  if (!tasks.size) return null;
  return { tasks: [...tasks.values()].sort((a, b) => a.order - b.order).map(({ order, ...t }) => t), lastUuid };
}

export function buildParsed(p: IncParser): ParsedTranscript {
  const { byUuid, ordered, toolOut } = p;

  // The active conversation tip is the LAST user/assistant line in file order:
  // Claude appends the live branch last, and the parentUuid walk below excludes
  // any abandoned/edited branch. We deliberately do NOT use last-prompt.leafUuid
  // as the leaf — it records the latest *prompt's* anchor, so walking up from it
  // drops that turn's reply (a descendant), and on a brand-new session it points
  // at a pre-prompt `system` node whose ancestors are only more system lines,
  // yielding an empty path (0 events — a freshly-opened session renders blank).
  // leafUuid survives only as a fallback for the degenerate no-conversation case.
  let leaf: string | undefined;
  for (let i = ordered.length - 1; i >= 0; i--) {
    const o = ordered[i];
    if ((o.type === "user" || o.type === "assistant") && !o.isSidechain) {
      leaf = o.uuid;
      break;
    }
  }
  if (!leaf && p.lastLeaf && byUuid.has(p.lastLeaf)) leaf = p.lastLeaf;

  const path: Line[] = [];
  const seen = new Set<string>();
  let cur: string | undefined = leaf;
  while (cur && byUuid.has(cur) && !seen.has(cur)) {
    seen.add(cur);
    path.push(byUuid.get(cur)!);
    // Stitch across context compactions: the compact-boundary record has
    // parentUuid null but logicalParentUuid = the pre-compaction leaf, and ALL
    // pre-compaction lines stay in the file. Following it renders the full
    // history (and keeps old deep-link anchor uuids resolvable) instead of
    // cutting the chat off at the newest compaction summary. Normal lines have
    // parentUuid set, so forks/rewinds still exclude abandoned branches.
    const ln = byUuid.get(cur)!;
    cur = ln.parentUuid ?? ln.logicalParentUuid ?? undefined;
  }
  path.reverse();

  const todoState = foldTasks(path, toolOut);   // one checklist for the whole Task list
  const events: ChatEvent[] = [];
  for (const o of path) {
    const ts: string | undefined = o.timestamp;
    const uuid: string | undefined = o.uuid;
    if (o.type === "user") {
      const c = o.message?.content;
      let raw = "";
      const images: UserImage[] = [];   // inline base64 → data URL; a path source → "path:<path>"
      if (typeof c === "string") raw = c;
      else if (Array.isArray(c)) {
        for (const b of c as any[]) {
          if (!b) continue;
          if (b.type === "text") raw += (raw ? "\n" : "") + (b.text || "");
          else if (b.type === "image") {
            const s = b.source || {};
            if (s.type === "base64" && s.data) images.push({ src: `data:${s.media_type || "image/png"};base64,${s.data}` });
            else if (s.path) images.push({ src: "path:" + s.path, path: s.path });
          }
        }
      }
      // the composer's "[Image #N]" placeholder chips arrive as literal text in the
      // same line as the attachment blocks; the image renders as a thumbnail below,
      // so the markers are noise (guarded by images.length: typed "[Image #1]" with
      // no attachment stays verbatim)
      if (images.length) raw = raw.replace(/\[Image #\d+\]\s?/g, "");
      // a standalone "[Image: source: <path>]" line (Claude Code emits one per pasted
      // file) → when the paste's real prompt — the line just emitted — already carries
      // the image inline as base64, this isMeta record names that image's on-disk
      // copy: attach the path to it (the open/copy link) instead of rendering a
      // second image-only bubble. With no preceding paste it's a path image itself.
      const ref = raw.match(/^\s*\[Image: source: (.+?)\]\s*$/);
      if (ref && !images.length) {
        const prev = events[events.length - 1];
        if (prev?.kind === "user" && prev.images?.length) {
          const orphan = prev.images.find((im) => !im.path);
          if (orphan) orphan.path = ref[1];
          continue;
        }
        images.push({ src: "path:" + ref[1], path: ref[1] });
        raw = "";
      }
      // an image-bearing user line is one of the user's PASTES → his (blue) styling
      const human = o.promptSource === "typed" || o.promptSource === "queued" || images.length > 0;
      // a bare image PATH typed (or file-dragged) into the composer arrives as plain
      // text — show the thumbnail too (the webview swaps the inline path for a link)
      if (human && !images.length) {
        for (const m of raw.matchAll(/(?:^|[\s'"`(])((?:~\/|\/)[^\s'"`()]+\.(?:png|jpe?g|gif|webp|bmp|svg))\b/gi)) {
          if (!images.some((im) => im.path === m[1])) images.push({ src: "path:" + m[1], path: m[1] });
          if (images.length >= 4) break;
        }
      }
      if (raw.trim() || images.length) {
        const { clean, reminders } = splitReminders(raw);
        if (clean || reminders.length || images.length)
          // GENUINE human prompt iff promptSource is typed/queued (or it's a paste);
          // other injected user-role lines (compact summary, /command stdout, reminders,
          // postal pushes) are not styled as "his message".
          events.push({ kind: "user", md: clean, ts, uuid, reminders: reminders.length ? reminders : undefined, human, images: images.length ? images : undefined });
      }
    } else if (o.type === "attachment") {
      // A CONSUMED queued message. While pending it lives as queue-operation
      // records (the "queued" block below); when the turn it waited on ends,
      // Claude Code resolves those ops (clearing that block) and re-writes the
      // message as a queued_command attachment chained into the conversation —
      // NOT as a user line. Without this branch every consumed queued message
      // vanished from the chat (the user's report, 2026-06-11). Task
      // notifications stay invisible (harness plumbing), but a POSTAL BANNER
      // attachment is real correspondence: pass it through so hydratePostal
      // swaps it into a postal-in card anchored at THIS line. Dropping banners
      // here left queue-delivered mail with no chat line at all, so a timeline
      // message-connector click had nothing to land on (the user's report,
      // 2026-06-12). An unresolved msg-id renders the raw banner — visible
      // beats vanished.
      const att = o.attachment;
      if (att?.type === "queued_command" && typeof att.prompt === "string") {
        const t = att.prompt.trim();
        if (t && !t.startsWith("<task-notification>"))
          events.push({ kind: "user", md: t, ts, uuid, human: true });
      }
    } else if (o.type === "assistant") {
      const blocks = o.message?.content;
      if (!Array.isArray(blocks)) continue;
      for (const b of blocks) {
        if (!b) continue;
        if (b.type === "text") {
          if (typeof b.text === "string" && b.text.trim())
            events.push({ kind: "assistant", md: b.text, ts, uuid });
        } else if (b.type === "thinking") {
          const text = (b.thinking ?? "").trim();
          events.push({ kind: "thinking", text, encrypted: text.length === 0, ts, uuid });
        } else if (b.type === "tool_use") {
          if (b.name === "TaskCreate" || b.name === "TaskUpdate") continue;   // folded into the one todo checklist
          const out = toolOut.get(b.id);
          const { desc, input, file, diff } = describeTool(b.name, b.input);
          events.push({
            kind: "tool",
            name: b.name || "tool",
            desc,
            input,
            output: out?.text ?? "",
            isError: out?.isError ?? false,
            ts,
            uuid,
            resultUuid: out?.uuid,   // the answer line's uuid → the AUQ widget's deep-link anchor
            file,
            diff,
          });
        }
      }
    }
  }
  // ONE folded to-do checklist, current-state, at the BOTTOM of the transcript —
  // mirrors the terminal's bottom-anchored to-do AND stays robust under the
  // incremental re-render (always the last event, so its trailing window re-renders
  // it on every status change instead of stranding a stale copy). Only render it
  // while there's OUTSTANDING work: once every task is completed/cancelled the list
  // isn't a live "to-do" anymore, so pinning it to the bottom falsely reads as recent
  // (the user 2026-06-10) — drop it when fully closed; it returns if new tasks appear.
  const todoLive = !!todoState && todoState.tasks.some((t) => t.status !== "completed" && t.status !== "cancelled");
  if (todoState && todoLive) events.push({ kind: "todo", tasks: todoState.tasks });

  // Still-pending queued messages (the user submitted them while the session was
  // working; Claude Code hasn't dequeued them yet) — at the VERY bottom, closest to
  // the composer, mirroring the queue Claude Code shows above its own input.
  const queued = foldQueue(p.queueOps);
  if (queued.length) events.push({ kind: "queued", texts: queued });

  return { sessionId: p.sessionId, events, status: computeStatus(ordered, path) };
}

// A queued enqueue is "genuine" (the user's typed message) only if it isn't harness
// plumbing — a background <task-notification> or a pushed romp-postal peer banner
// (those have their own rendering and aren't messages the user would edit/resend).
function isGenuineQueued(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  if (t.startsWith("<task-notification>")) return false;
  if (t.includes("romp-msg-id") || t.startsWith("####################") || t.includes("\u{1F4EC}")) return false;
  return true;
}

// FIFO-fold the queue-operation stream into the list of STILL-PENDING messages:
// each enqueue appends; each dequeue/remove resolves the oldest pending one. The
// unresolved tail is what's still queued (filtered to genuine the user messages).
function foldQueue(ops: { op: string; content: string | null }[]): string[] {
  const texts: string[] = [];
  let resolved = 0;   // count of enqueues already dequeued/removed (FIFO from the front)
  for (const o of ops) {
    if (o.op === "enqueue") texts.push(typeof o.content === "string" ? o.content : "");
    else if ((o.op === "dequeue" || o.op === "remove") && resolved < texts.length) resolved++;
  }
  return texts.slice(resolved).filter(isGenuineQueued).map((t) => t.trim());
}

// One-shot parse of an entire transcript string (tests, and the full re-read
// fallback). Equivalent to feeding the whole content and flushing the last line.
export function parse(raw: string): ParsedTranscript {
  const p = newIncParser();
  feed(p, Buffer.from(raw, "utf8"));
  flush(p);
  return buildParsed(p);
}

function computeStatus(ordered: Line[], path: Line[]): SessionStatus {
  // Last conversational line in file order.
  let last: Line | undefined;
  for (let i = ordered.length - 1; i >= 0; i--) {
    const t = ordered[i].type;
    if (t === "user" || t === "assistant") {
      last = ordered[i];
      break;
    }
  }
  // `working` is keyed PURELY on the transcript's own last-line stop_reason — an
  // event, never wall-clock age. An age threshold here can't tell "asleep / long
  // tool call" from "interrupted", and a laptop-sleep clock jump trips it (the
  // 2026-06-12 sleep/wake incident; see the Design rule in CLAUDE.md). The
  // pane/@claude-state layer (romp-idle-dots) is the authority that resolves a
  // genuinely interrupted turn — the transcript alone never should.
  let working = false;
  if (last) {
    if (last.type === "assistant") {
      const sr = last.message?.stop_reason;
      // end_turn / stop_sequence => the turn finished; anything else (tool_use,
      // null mid-stream) => still going.
      working = !(sr === "end_turn" || sr === "stop_sequence");
    } else {
      // a user / tool_result line is last => the model is about to respond.
      working = true;
    }
  }

  // Start of the current turn = timestamp of the most recent human prompt.
  let sinceEpoch: number | null = null;
  for (let i = path.length - 1; i >= 0; i--) {
    const o = path[i];
    if (o.type === "user" && typeof o.message?.content === "string" && o.timestamp) {
      sinceEpoch = Date.parse(o.timestamp);
      break;
    }
  }

  return { working, sinceEpoch };
}

function contentToText(c: any): string {
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((b) => {
        if (typeof b === "string") return b;
        if (b?.type === "text") return b.text ?? "";
        if (b?.type === "image") return "[image]";
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

interface ToolView { desc: string; input: string; file?: string; diff?: string; }

function describeTool(name: string, input: any): ToolView {
  if (input == null || typeof input !== "object") {
    return { desc: "", input: typeof input === "string" ? input : String(input) };
  }
  switch (name) {
    case "Bash":
      return { desc: input.description ?? "", input: input.command ?? "" };
    case "Read":
    case "NotebookEdit":
      return { desc: "", input: input.file_path ?? input.notebook_path ?? pretty(input), file: input.file_path ?? input.notebook_path };
    case "Write":
      return { desc: "", input: input.file_path ?? pretty(input), file: input.file_path };
    case "Edit":
      return { desc: "", input: input.file_path ?? pretty(input), file: input.file_path, diff: editDiff(input.old_string, input.new_string) };
    case "MultiEdit":
      return { desc: "", input: input.file_path ?? pretty(input), file: input.file_path, diff: multiEditDiff(input.edits) };
    case "Grep":
      return {
        desc: "",
        input: input.pattern
          ? input.pattern + (input.path ? `   ${input.path}` : "")
          : pretty(input),
      };
    case "Glob":
      return { desc: "", input: input.pattern ?? pretty(input) };
    case "WebFetch":
      return { desc: input.prompt ?? "", input: input.url ?? pretty(input) };
    case "Task":
    case "Agent":
      return { desc: input.description ?? "", input: input.prompt ?? pretty(input) };
    default:
      return { desc: input.description ?? "", input: pretty(input) };
  }
}

// A compact line-level diff: trim the shared head/tail (shown as context), and
// only the changed middle gets - / + markers. Output is hljs `diff`-friendly.
function editDiff(oldS?: unknown, newS?: unknown): string | undefined {
  if (typeof oldS !== "string" || typeof newS !== "string") return undefined;
  const a = oldS.split("\n");
  const b = newS.split("\n");
  let p = 0;
  while (p < a.length && p < b.length && a[p] === b[p]) p++;
  let s = 0;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
  const lines = [
    ...a.slice(0, p).map((l) => "  " + l),
    ...a.slice(p, a.length - s).map((l) => "-" + l),
    ...b.slice(p, b.length - s).map((l) => "+" + l),
    ...a.slice(a.length - s).map((l) => "  " + l),
  ];
  return lines.join("\n");
}

function multiEditDiff(edits: unknown): string | undefined {
  if (!Array.isArray(edits)) return undefined;
  const parts = edits
    .map((e: any, i: number) => {
      const d = editDiff(e?.old_string, e?.new_string);
      if (!d) return "";
      return edits.length > 1 ? `@@ edit ${i + 1} @@\n${d}` : d;
    })
    .filter(Boolean);
  return parts.length ? parts.join("\n") : undefined;
}

// Strip <system-reminder>…</system-reminder> blocks (framework injections —
// task nudges, file-modified notices, the session-start CLAUDE.md/env block)
// out of the conversational text; the renderer folds them away.
const REMINDER_RE = /<system-reminder>([\s\S]*?)<\/system-reminder>/g;
function splitReminders(text: string): { clean: string; reminders: string[] } {
  const reminders: string[] = [];
  const clean = text.replace(REMINDER_RE, (_m, body) => {
    const t = String(body).trim();
    if (t) reminders.push(t);
    return "";
  }).trim();
  return { clean, reminders };
}

function pretty(input: any): string {
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}
