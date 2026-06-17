import { marked } from "marked";
import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import python from "highlight.js/lib/languages/python";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import json from "highlight.js/lib/languages/json";
import xml from "highlight.js/lib/languages/xml";
import cssLang from "highlight.js/lib/languages/css";
import markdown from "highlight.js/lib/languages/markdown";
import diff from "highlight.js/lib/languages/diff";
import yaml from "highlight.js/lib/languages/yaml";
import type { ParsedAsk } from "../ask-types";
import { quoteReply } from "../quote";
import { markerLabel, chooseStamps } from "./time-marker";
import { compactDisplay, toolCounts } from "./compact";
import { loadSettings, onExternalSettingsChange, type RompSettings } from "./settings";

for (const [name, lang] of Object.entries({
  bash, sh: bash, shell: bash, python, py: python, javascript, js: javascript,
  typescript, ts: typescript, json, xml, html: xml, css: cssLang, markdown, md: markdown,
  diff, yaml, yml: yaml,
})) {
  try { hljs.registerLanguage(name, lang as any); } catch { /* dup alias */ }
}

marked.setOptions({ gfm: true, breaks: false });

// One answered (or pending) question on an AskUserQuestion turn: the prompt + its options, plus the
// user's answer TEXT per question (`chosen`). Answer text may name an option label OR be free-text
// ("Other"), and is empty while the question is still pending. multiSelect → chosen has >1 entry.
type AskAnswerBlock = { question: string; header?: string; options: { label: string; description?: string }[]; chosen: string[] };

type ChatEvent = (
  | { kind: "user"; md: string; uuid?: string; ts?: string; reminders?: string[]; human?: boolean; images?: { src: string; path?: string }[] }
  | { kind: "assistant"; md: string; uuid?: string; ts?: string }
  | { kind: "thinking"; text: string; encrypted: boolean; uuid?: string; ts?: string }
  | {
      kind: "tool";
      name: string;
      desc: string;
      input: string;
      output: string;
      isError: boolean;
      uuid?: string;
      resultUuid?: string;   // tool_result line uuid (AUQ answer) — the deep-link anchor the timeline emits
      ts?: string;
      file?: string;
      diff?: string;
      // AskUserQuestion only: the kernel joins the posed questions/options to the recorded answer and
      // attaches them here (the user 2026-06-16). Empty `chosen` while pending; filled once answered →
      // renderAsk flips the turn to the blue "you answered Claude's question" box.
      askAnswer?: AskAnswerBlock[];
    }
  | {
      kind: "postal";
      direction: "in" | "out";
      peer: string;
      color: { bg: string; fg: string } | null;
      body: string;
      summary?: string;  // incoming Haiku caption (≤9 words) — shown instead of the verbose body; body on hover
      mid?: string;      // postal message id (joins feed-modal handoff hovers to this card)
      t?: number;        // epoch seconds (incoming)
      park?: boolean;
      status?: "delivered" | "parked"; // outgoing
      ts?: string;
      uuid?: string;
    }
  // Claude Code's Task to-do list, folded into one live checklist.
  | { kind: "todo"; tasks: TodoTask[]; ts?: string; uuid?: string }
  | { kind: "queued"; texts: string[]; ts?: string; uuid?: string }
  // The session is delegating to a subagent (Task/Agent) — quiet but still working.
  | { kind: "subagent"; desc: string; ts?: string; uuid?: string }
  // The turn stopped on an API error (event-based: transcript isApiErrorMessage). The session is BLOCKED
  // until retried — a red-dot card at the bottom with a Retry button (the user 2026-06-16).
  | { kind: "apiError"; text: string; status?: number; category?: string; ts?: string; uuid?: string }
  | { kind: "compact"; ts?: string; uuid?: string }
) & { tlId?: string };   // tlId: the timeline atom this event's hover lights — a prompt → the DOT, work → the BAR

interface TodoTask { id: string; subject: string; activeForm?: string; status: string }

type ChipState = "working" | "subagent" | "ready" | "awaiting" | "idle" | "closed" | "compacting" | "blocked";
interface Status { state: ChipState; sinceEpoch: number | null; effort?: string; model?: string; ctx?: string; faded?: boolean;
  // ADDITIVE subagent signal: the desc of a subagent running in the background (or "" if undescribed), else
  // null. Shown as a separate orange chip/dot ONLY while the session is otherwise quiet (ready/idle) — a
  // working session hides it (the user 2026-06-16).
  subagent?: string | null; }
interface Color { bg: string; fg: string; }
interface Session { id: string; name: string; color: Color | null; events: ChatEvent[]; status: Status; firstSeen?: number; }

const vscodeApi =
  typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let settings: RompSettings = loadSettings();   // global webview settings (compact mode, …) — see settings.ts
const expandedGroups = new Set<string>();      // compact mode: tool-group keys the user clicked open

const sessions = new Map<string, Session>();
const order: string[] = [];           // positional tab order (for cycling)
const mru: string[] = [];             // recency stack, front = most-recently-active (close → return to previous)
let activeId: string | null = null;
// restore the last-active tab on refresh (persisted via setState); one-shot, applied when its session arrives
let wantActive: string | null = (() => { try { return ((vscodeApi?.getState?.() || {}) as any).activeId || null; } catch { return null; } })();
let pendingAnchor: string | null = null; // deep-link target waiting to be scrolled to
let pendingAnchorIntent: string | null = null; // kind the uuid anchor must honor — sticks with pendingAnchor across render-pass retries (pendingAnchorKind is cleared each pass, this isn't)
let pendingAnchorT: number | null = null; // time fallback (epoch s) when the uuid can't resolve
let pendingAnchorKind: string | null = null; // intent for the time fallback: "user" = land on the user's own turn
// Landing diagnostics (the user's ask, 2026-06-10): record HOW each deep-link
// landing resolved — exact pointer / refused wrong-kind pointer / time-nearby
// / gave up. The trail is posted to the host (→ ~/.local/state/romp/
// locate-diag.jsonl) on every attempt, and DEGRADED landings show a transient
// toast, so a bad jump is visibly flagged instead of looking like a confident
// (but wrong) link. "That click landed weird" + the log = a diagnosable bug.
let landTrail: string[] = [];

// Per-session rendered DOM, kept alive so switching tabs doesn't rebuild the
// whole transcript — only the active view is shown, others are display:none.
// Invariant: each ChatEvent renders to exactly one .turn child, so
// view.el.childNodes.length === view.rendered.
interface View { el: HTMLElement; rendered: number; scrollTop: number; stick: boolean; shown: boolean; stale: boolean; }
const views = new Map<string, View>();

// Pending pickers (AskUserQuestion / tool-permission) keyed by session id. These
// live ONLY in the session's tmux pane (Claude Code doesn't write a pending
// prompt to the transcript until it's answered), so the host captures+parses the
// pane and pushes them here. Kept OUT of the transcript `events` list so syncView
// never clobbers them; rendered into the dedicated #live-ask region instead.
// The pending prompt per session (its `kind` selects the widget). Kept OUT of the
// transcript events so syncView can't clobber it. A stored null = awaiting an
// unstructured screen (e.g. the free-text "type something" field) → a text input;
// no entry at all = not awaiting → hidden.
const liveAsks = new Map<string, ParsedAsk | null>();

// Per-session rolling digest (purpose + a few timestamped bullets), shown in the
// #ledger box just below the tabs. Swaps with the active tab; pushed by the host.
interface LedgerBullet { text: string; t?: number; id?: string; sid?: string; tlId?: string; }   // id/sid = locate anchor; tlId = the timeline atom (turn DOT) to light on hover
// A node of the goal-graph overview tree: open paths are expanded, done nodes are pruned to leaves.
// `current` = the focus node being worked on (gets a pointer + the live elapsed); a `done` node shows
// its completion time, recency-coloured, on the right (the user 2026-06-16).
// `derived` = this node is done only because all its children are (the kernel propagates completion up
// the tree), as opposed to an explicitly-asserted done. Rendered as the blue ✓ disc dimmed (the user
// 2026-06-16). Empty/false → explicit done (full disc).
interface LedgerTreeNode { id: string; text: string; depth: number; done: boolean; blocked: boolean; t?: number; mt?: number; current: boolean; derived?: boolean; recent?: boolean; cleared?: boolean; onpath?: boolean; children?: string[]; }
// tree = the goal overview (preferred view); bullets = captioned-turn fallback for goal-less sessions.
interface Ledger { summary: string; tree?: LedgerTreeNode[]; bullets: LedgerBullet[]; current?: LedgerBullet | null; }
const ledgers = new Map<string, Ledger | null>();

function el(tag: string, cls?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function md(src: string): string {
  // Transcript text (user prompts, assistant output, subagent reports, postal
  // bodies) is UNTRUSTED and `marked` emits raw HTML verbatim, so its output
  // must be sanitized before it ever reaches .innerHTML — otherwise a payload
  // like `<img src=x onerror=...>` or `[x](javascript:...)` runs in the webview
  // (which can postMessage the host to open files / drive sessions). DOMPurify
  // strips event-handler attributes and dangerous URL schemes. Keep data: URIs
  // on <img> (the CSP allows them and inline transcript images rely on them).
  try {
    const dirty = marked.parse(src) as string;
    return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true }, ADD_DATA_URI_TAGS: ["img"] });
  } catch { const d = document.createElement("div"); d.textContent = src; return d.innerHTML; }
}

function highlight(container: HTMLElement, lineNos = true) {
  container.querySelectorAll("pre code").forEach((node) => {
    const code = node as HTMLElement;
    const lang = (code.className.match(/language-([\w-]+)/) || [])[1];
    try {
      code.innerHTML = lang && hljs.getLanguage(lang)
        ? hljs.highlight(code.textContent || "", { language: lang }).value
        : hljs.highlightAuto(code.textContent || "").value;
      code.classList.add("hljs");
      if (lineNos) wrapCodeLines(code);   // per-line gutter so a soft-wrap reads distinctly from a real newline
    } catch { /* leave as-is */ }
  });
}

// Wrap each logical line of (hljs-highlighted) code in <span class=cl><span class=ct>…</span></span>,
// re-opening any hljs span that straddles a newline so the markup stays valid. A CSS counter on .cl
// draws the subtle line numbers; .ct holds the wrapping content (the user 2026-06-16).
function wrapCodeLines(code: HTMLElement) {
  const lines = code.innerHTML.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();   // a trailing newline isn't a blank line
  let open: string[] = [];
  code.innerHTML = lines.map((ln) => {
    const prefix = open.join("");
    const re = /<span[^>]*>|<\/span>/g; let m; const stack = open.slice();
    while ((m = re.exec(ln))) { if (m[0] === "</span>") stack.pop(); else stack.push(m[0]); }
    const suffix = "</span>".repeat(Math.max(0, stack.length));
    open = stack;
    return `<span class="cl"><span class="ct">${prefix}${ln}${suffix}</span></span>`;
  }).join("");
}

function dot(kind: "green" | "ring" | "user" | "red"): HTMLElement { return el("span", "dot " + kind); }

function ioRow(label: "IN" | "OUT", text: string, isError: boolean): HTMLElement {
  const row = el("div", "io-row" + (label === "OUT" ? " io-out" : "") + (isError ? " io-error" : ""));
  const lab = el("span", "io-label"); lab.textContent = label;
  const pre = el("pre", "io-pre"); pre.textContent = text;
  row.appendChild(lab); row.appendChild(pre);
  return row;
}

// Tools whose result is pure boilerplate ("…updated successfully", "Task #N
// created") — on success the OUT box is suppressed (the green ✓ rail dot is the
// success signal). On error the real message is always shown. (The Agent/Task
// subagent tool is NOT here — its output is the agent's report, which is signal.)
const ACK_TOOLS = new Set([
  "Edit", "Write", "MultiEdit", "NotebookEdit",
  "TodoWrite", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
]);

function shortPath(p: string): string {
  const parts = p.split("/").filter(Boolean);
  return parts.length <= 2 ? p : ".../" + parts.slice(-2).join("/");
}

function countLines(s: string): number {
  if (!s) return 0;
  const n = s.split("\n").length;
  return s.endsWith("\n") ? n - 1 : n;
}

function preEl(text: string): HTMLElement {
  const pre = el("pre", "io-pre fold-pre");
  pre.textContent = text;
  return pre;
}

// Markdown links: the webview sandbox only auto-opens http(s) — a vscode://
// link (e.g. a romp chat deep link pasted into a conversation) silently dies
// on click. Route every absolute-scheme anchor through the host instead: it
// openExternal()s normal URLs and feeds vscode://romp.romp-chat-view deep
// links straight into the extension's own URI handler.
document.addEventListener("click", (e) => {
  const a = (e.target as HTMLElement)?.closest?.("a[href]") as HTMLAnchorElement | null;
  if (!a) return;
  const href = a.getAttribute("href") || "";
  if (!/^[a-z][a-z0-9+.-]*:/i.test(href)) return; // fragment/relative — leave alone
  e.preventDefault();
  e.stopPropagation();
  if (vscodeApi) vscodeApi.postMessage({ type: "openLink", href });
}, true);

// A clickable file name that opens the real file in the editor (shared
// open/navigate surface — see extension.ts openFile handler).
function fileLink(path: string): HTMLElement {
  const a = el("span", "tool-file");
  a.textContent = shortPath(path);
  a.title = "Open " + path;
  a.addEventListener("click", (e) => {
    e.stopPropagation();
    if (vscodeApi) vscodeApi.postMessage({ type: "openFile", path });
  });
  return a;
}

// Visible-but-bounded IN/OUT block (clamped ~300px, click to expand fully).
function ioClamp(input: string, output: string, isError: boolean): HTMLElement {
  const clamp = el("div", "io-clamp");
  const io = el("div", "tool-io");
  if (input) io.appendChild(ioRow("IN", input, false));
  if (output) io.appendChild(ioRow("OUT", output, isError));
  clamp.appendChild(io);
  clamp.addEventListener("click", () => clamp.classList.toggle("expanded"));
  return clamp;
}

// Compact fold: the AFFORDANCE (caret + a summary like "12 lines" / "+5 −2") sits
// on the RIGHT of the tool's HEAD line; the expandable content hangs below the
// head, hidden until clicked — so each tool stays ONE row by default (the user:
// vertical-compact). `head` must already be appended to `turn`.
function inlineFold(head: HTMLElement, turn: HTMLElement, label: string, content: HTMLElement) {
  const toggle = el("span", "tool-fold-toggle");
  toggle.textContent = label;   // just the clickable summary ("+14 −0" / "12 lines") — no caret/bullet
  toggle.title = "click to expand";
  toggle.addEventListener("click", (e) => { e.stopPropagation(); turn.classList.toggle("fold-open"); });
  content.classList.add("tool-fold-body");
  head.appendChild(toggle);
  turn.appendChild(content);
}

// Hidden-until-clicked disclosure (caret + label) — for noise-by-default
// content like Read dumps and folded system reminders.
function foldable(label: string, content: HTMLElement): HTMLElement {
  const wrap = el("div", "fold");
  const head = el("div", "fold-head");
  const caret = el("span", "fold-caret"); caret.textContent = "▸";
  const lab = el("span", "fold-label"); lab.textContent = label;
  head.appendChild(caret); head.appendChild(lab);
  head.addEventListener("click", () => wrap.classList.toggle("open"));
  wrap.appendChild(head);
  wrap.appendChild(content);
  return wrap;
}

// ---- path-source pasted images ----
// A user turn may carry a "path:<abs path>" image (Claude Code's image-cache or a
// screenshot from disk). The webview can't read files, so we ask the host once per
// path; until/unless it returns a dataURL we show a "🖼 filename" chip, then swap in
// the real thumbnail when the host answers. Re-renders rebuild the element from these
// caches, so a thumbnail already fetched stays a thumbnail.
const imgUrlCache = new Map<string, string>();   // path → dataURL (loaded)
const imgFailed = new Set<string>();             // path → keep the chip, never retry
const imgRequested = new Set<string>();          // path → request in flight
function fillPathImg(wrap: HTMLElement, p: string): void {
  wrap.textContent = "";
  const url = imgUrlCache.get(p);
  if (url) {
    const img = document.createElement("img"); img.className = "user-img"; img.src = url; img.loading = "lazy"; img.title = p;
    wrap.appendChild(img);
  } else {
    const chip = el("div", "user-img-path"); chip.textContent = "🖼 " + (p.split("/").pop() || p); chip.title = p;
    wrap.appendChild(chip);
  }
}
function buildPathImg(p: string): HTMLElement {
  const wrap = el("span", "js-pathimg"); wrap.dataset.imgpath = p;
  fillPathImg(wrap, p);
  if (!imgUrlCache.has(p) && !imgFailed.has(p) && !imgRequested.has(p)) {
    imgRequested.add(p);
    if (vscodeApi) vscodeApi.postMessage({ type: "imgRequest", path: p });
  }
  return wrap;
}
function onImgData(p: string, url: string | null): void {
  imgRequested.delete(p);
  if (url) imgUrlCache.set(p, url); else imgFailed.add(p);
  document.querySelectorAll(".js-pathimg").forEach((n) => {
    const e = n as HTMLElement; if (e.dataset.imgpath === p) fillPathImg(e, p);
  });
}

// One image of a user turn: the picture (or its hydration chip) plus, when the
// on-disk path is known, a caption line — the full absolute path (click → open),
// ⧉ copies it. So both the rendered image AND its path stay accessible no matter
// how the image arrived (pasted inline, referenced by path, typed as text).
function userImage(im: { src: string; path?: string }): HTMLElement {
  const fig = el("span", "user-img-wrap");
  if (im.src.startsWith("path:")) {
    fig.appendChild(buildPathImg(im.src.slice(5)));   // host reads it → real thumbnail; chip until then / on failure
  } else {
    const img = document.createElement("img"); img.className = "user-img"; img.src = im.src; img.loading = "lazy";
    fig.appendChild(img);
  }
  if (im.path) fig.appendChild(imgCaption(im.path));
  return fig;
}
function imgCaption(path: string): HTMLElement {
  const cap = el("span", "img-caption");
  const icon = el("span", "img-icon");   // separate node, so selecting the path text doesn't grab the emoji
  icon.textContent = "🖼";
  cap.appendChild(icon);
  cap.appendChild(imgPathLink(path));
  const copy = el("span", "img-copy");
  copy.textContent = "⧉";
  copy.title = "Copy path: " + path;
  copy.addEventListener("click", (e) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(path).then(() => {
      copy.textContent = "✓";
      setTimeout(() => { copy.textContent = "⧉"; }, 900);
    });
  });
  cap.appendChild(copy);
  return cap;
}
// The full absolute path, clickable — opens the image file in the editor. Shown
// verbatim (never shortened to a basename) so it can also be read and selected/
// copied right where it stands.
function imgPathLink(path: string): HTMLElement {
  const a = el("span", "img-link");
  a.textContent = path;
  a.title = "Open " + path;
  a.addEventListener("click", (e) => {
    e.stopPropagation();
    if (vscodeApi) vscodeApi.postMessage({ type: "openFile", path });
  });
  return a;
}
// Make literal occurrences of the images' paths inside the rendered message text
// clickable with the same open-the-file link the captions use — the typed path
// stays visible verbatim, it just gains the link behavior.
function linkifyImgPaths(root: HTMLElement, paths: string[]): void {
  if (!paths.length) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let n: Node | null;
  while ((n = walker.nextNode())) nodes.push(n as Text);
  for (const tn of nodes) {
    for (const p of paths) {
      const i = tn.data.indexOf(p);
      if (i < 0) continue;
      tn.splitText(i + p.length);
      const mid = tn.splitText(i);
      mid.replaceWith(imgPathLink(p));
      break;   // the split invalidated this node's tail — one link per original node
    }
  }
}

function renderEvent(ev: ChatEvent, prevEpoch?: number | null, worked?: number | null): HTMLElement {
  const turn = renderEventInner(ev);
  // Deep-link anchor. An AskUserQuestion widget carries the ANSWER-line (tool_result
  // user line) uuid — that's the uuid the timeline emits for the decision, and the
  // answer line produces no standalone event/DOM node of its own. Everything else
  // anchors on its own uuid.
  const anchorUuid = (ev.kind === "tool" && ev.name === "AskUserQuestion" && ev.resultUuid) ? ev.resultUuid : ev.uuid;
  if (anchorUuid) turn.dataset.uuid = anchorUuid; // deep-link anchor (shared with vs_chat)
  // epoch-seconds stamp → time-based anchor fallback (when a uuid anchor is
  // stale/orphaned, the deep link can still land on the nearest moment)
  const epoch = eventEpoch(ev);
  if (epoch != null) turn.dataset.t = String(epoch);
  // rail time-stamp: HH:MM just to the LEFT of every dot (the user 2026-06-10) — a left
  // timestamp column so each event on the rail shows when it happened. On every dotted turn,
  // postal cards included (the user 2026-06-13: a postal message rides the rail like every other
  // event instead of stamping the time inside its own card). Prompts ride this rail too instead
  // of an in-bubble stamp (the human via debugger, 2026-06-12). The date shows only on the first
  // turn of a new (non-today) day.
  if (epoch != null && turn.querySelector(".dot")) turn.insertBefore(timeMarker(epoch, prevEpoch ?? null), turn.firstChild);
  // rail-dot fleet links: hover anywhere on the turn → white-highlight this turn's
  // event on the timeline AND outline its feed card(s); click the DOT → open that
  // card's modal in the feed (the host resolves turn → event → cards). The whole
  // turn is the hover target (the user 2026-06-12) — hovering the MESSAGE bubble or
  // the WORK/reply body must light the timeline, not only the rail dot.
  const railDot = turn.querySelector(".dot") as HTMLElement | null;
  if (anchorUuid || epoch != null) wireTurnHover(turn, railDot, anchorUuid ?? null, epoch ?? 0, ev.tlId ?? null);
  // a finished prompt's last reply carries a small "worked 2m 14s" tick in the rail
  // gutter (left, by the time-markers) — how long the session ran on that prompt.
  if (worked != null) turn.appendChild(elapsedFooter(worked));
  return turn;
}

// Format a worked-duration (seconds) the same way the live work-timer formats its
// elapsed (elapsedMs): "45s" / "2m 14s" / "1h 03m". Units distinguish it from the
// HH:MM rail time-markers.
function durLabel(secs: number): string {
  secs = Math.max(0, Math.floor(secs));
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m ${secs % 60}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function elapsedFooter(secs: number): HTMLElement {
  const f = el("div", "turn-elapsed");
  f.textContent = durLabel(secs);
  f.title = `worked ${durLabel(secs)} on this prompt`;
  return f;
}

// Hover uses the same 120ms intent debounce as ledger bullets / feed rows so
// scrolling the transcript doesn't strobe the timeline; leave clears. The sid is
// read at event time (only the ACTIVE session's view is hoverable). The host
// decides which timeline ATOM to light (the prompt DOT vs the work BAR) from the
// hovered line's uuid: a user-prompt turn carries the event's boundary uuid →
// dot; an assistant/tool/thinking turn carries a work-line uuid (or resolves by
// time into the period) → bar. So hovering the message lights the dot and
// hovering the work body lights the bar — the chat just reports its own uuid.
// HOVER is on the RAIL DOT only (the user 2026-06-15: hovering the message TEXT must not light the
// timeline — only the rail/"timeline" gutter does); the dot also keeps the click (open the feed card).
function wireTurnHover(turn: HTMLElement, dot: HTMLElement | null, uuid: string | null, t: number, tlId?: string | null) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const hoverTarget = dot || turn;   // only the dot triggers the timeline highlight (turn fallback if no dot)
  hoverTarget.addEventListener("mouseenter", () => {
    timer = setTimeout(() => { timer = undefined; if (activeId) vscodeApi?.postMessage({ type: "dotHover", sid: activeId, uuid, t, tlId }); }, 120);
  });
  hoverTarget.addEventListener("mouseleave", () => {
    if (timer) { clearTimeout(timer); timer = undefined; return; } // never fired — nothing to clear
    vscodeApi?.postMessage({ type: "dotHover" });
  });
  if (dot) {
    dot.classList.add("dot-nav");
    dot.title = "click: open the feed card · hover: highlight on the timeline + feed";
    dot.addEventListener("click", (e) => {
      e.stopPropagation();
      if (activeId) vscodeApi?.postMessage({ type: "dotOpen", sid: activeId, uuid, t });
    });
  }
}

// Transient cross-highlight FROM the feed modal (host fans its row-hover here as
// glowTurns): white-ring the rail dot of every chat turn inside a hovered event's
// [start, end] span (per session), and any postal card carrying a hovered message
// id. Empty groups+mids = clear. Glow is hover-transient, so a re-render that
// drops it mid-hover self-heals on the next 40ms hover tick.
function applyGlow(groups: Array<{ sid: string; ranges: Array<[number, number]> }>, mids: string[]) {
  document.querySelectorAll(".ext-glow").forEach((n) => n.classList.remove("ext-glow"));
  const midSet = new Set(mids);
  if (midSet.size) {
    document.querySelectorAll<HTMLElement>(".turn[data-mid]").forEach((n) => {
      if (midSet.has(n.dataset.mid || "")) n.classList.add("ext-glow");
    });
  }
  for (const g of groups) {
    const v = views.get(g.sid);
    if (!v) continue;
    v.el.querySelectorAll<HTMLElement>(".turn[data-t]").forEach((n) => {
      const t = parseInt(n.dataset.t || "", 10);
      if (t && (g.ranges || []).some(([s, e]) => t >= s - 2 && t <= e + 2)) n.classList.add("ext-glow");
    });
  }
}

function eventEpoch(ev: ChatEvent): number | null {
  if (ev.ts) {
    const ms = Date.parse(ev.ts);
    if (!isNaN(ms)) return Math.floor(ms / 1000);
  }
  // postal "in" events carry their epoch in `t` (seconds) rather than an ISO `ts`,
  // so they still anchor a rail dot's hover wiring and deep-link fallback.
  if (ev.kind === "postal" && ev.t != null) return Math.floor(ev.t);
  return null;
}

// A rail time-stamp (HH:MM) for a turn. On the first turn of a new (non-today) day it
// also shows the date, with emphasis. A run of same-minute turns shows the stamp only
// on the first (the user 2026-06-12); see markerLabel() for the rules. A suppressed turn
// keeps an EMPTY marker (so the dot keeps its column alignment) but stashes its HH:MM in
// data-hm; restampMarkers() may later light it up if too much space has gone unstamped.
// data-hard marks the markerLabel-assigned stamps, which the spacing pass never touches.
function timeMarker(epoch: number, prevEpoch: number | null): HTMLElement {
  const { text, day, hm, date } = markerLabel(epoch, prevEpoch, Date.now());
  const m = el("div", "time-marker");
  if (day) m.classList.add("day");
  m.dataset.hm = hm;
  if (text) {
    m.dataset.hard = "1";
    if (day && date) {
      // Two lines: the date floats on its own row ABOVE, the time stays on the dot's row —
      // a combined "Yesterday · 21:24" overruns the 58px gutter and collides with the dot.
      const dd = el("span", "tm-date"); dd.textContent = date; m.appendChild(dd);
      const tt = el("span", "tm-time"); tt.textContent = hm; m.appendChild(tt);
    } else {
      m.textContent = text;
    }
  }
  return m;
}

// Post-layout spacing pass: minute-change stamps alone can leave a long unstamped scroll
// when many turns share a minute. After render we measure each timed turn's vertical
// position and reveal a suppressed stamp wherever >6 one-line rows have passed without one
// (the user 2026-06-12). Markers are absolutely-positioned in the gutter, so toggling their
// text never reflows the rail — the measurement is stable and the pass is idempotent
// (soft reveals are cleared and recomputed each run; data-hard stamps are left alone).
function restampMarkers(root: HTMLElement): void {
  const ms: HTMLElement[] = [];
  const ys: number[] = [];
  const hard: boolean[] = [];
  let prevY: number | null = null;
  let oneRow = Infinity;
  for (const t of Array.from(root.children) as HTMLElement[]) {
    const m = t.firstChild as HTMLElement | null;
    if (!m || m.nodeType !== 1 || !m.classList.contains("time-marker")) continue;
    const y = t.getBoundingClientRect().top;
    if (prevY != null) oneRow = Math.min(oneRow, y - prevY);
    prevY = y;
    if (m.dataset.hard !== "1") { m.textContent = ""; m.classList.remove("auto"); } // reset soft reveal
    ms.push(m); ys.push(y); hard.push(m.dataset.hard === "1");
  }
  if (!ms.length) return;
  if (!isFinite(oneRow) || oneRow <= 0) oneRow = 24;       // single row / degenerate → a sane default
  oneRow = Math.max(18, Math.min(oneRow, 80));             // clamp against noisy extremes
  const show = chooseStamps(ys, hard, oneRow, 6);
  for (let i = 0; i < ms.length; i++) {
    if (!hard[i] && show[i]) { ms[i].textContent = ms[i].dataset.hm || ""; ms[i].classList.add("auto"); }
  }
}

// Debounced rAF wrapper — coalesces the many syncView calls of a busy tail into one
// measure-and-restamp of the active view per frame.
let restampPending = false;
function scheduleRestamp(): void {
  if (restampPending) return;
  restampPending = true;
  requestAnimationFrame(() => {
    restampPending = false;
    const v = activeId ? views.get(activeId) : null;
    if (v) restampMarkers(v.el);
  });
}

function renderEventInner(ev: ChatEvent): HTMLElement {
  if (ev.kind === "user") {
    // Only GENUINE typed/queued prompts get the blue "your message" bubble. Harness-
    // injected user-role lines (compact summary, /command stdout, system reminders,
    // postal pushes — all promptSource≠typed/queued) fall back to a neutral note box.
    const injected = !ev.human;
    const turn = el("div", "turn turn-user" + (injected ? " injected" : ""));
    // Prompts ride the rail like every other turn: their own dot + a left-gutter HH:MM
    // marker (added in renderEvent), instead of a timestamp printed inside the bubble
    // (the human via debugger, 2026-06-12). Genuine prompts get a solid blue dot to match
    // the bubble; injected user-role notes get the hollow ring used by assistant turns.
    turn.appendChild(dot(injected ? "ring" : "user"));
    const hasImgs = !!(ev.images && ev.images.length);
    if (ev.md || hasImgs) {
      const bubble = el("div", (injected ? "user-note" : "user-bubble") + " md");
      if (ev.md) bubble.innerHTML = md(ev.md);
      // images, IN the bubble (part of his message): thumbnail + open/copy caption;
      // a literal path in the typed text becomes the same open-link inline.
      if (ev.images) {
        linkifyImgPaths(bubble, ev.images.map((im) => im.path).filter((p): p is string => !!p));
        for (const im of ev.images) bubble.appendChild(userImage(im));
      }
      turn.appendChild(bubble);
    }
    if (ev.reminders && ev.reminders.length) {
      const body = el("div", "reminder-body");
      for (const r of ev.reminders) body.appendChild(preEl(r));
      const n = ev.reminders.length;
      const f = foldable(`ⓘ ${n} system reminder${n > 1 ? "s" : ""}`, body);
      f.classList.add("reminder-fold");
      turn.appendChild(f);
    }
    return turn;
  }
  if (ev.kind === "assistant") {
    const turn = el("div", "turn turn-assistant");
    turn.appendChild(dot("ring"));
    const body = el("div", "assistant md");
    body.innerHTML = md(ev.md);
    highlight(body);
    turn.appendChild(body);
    return turn;
  }
  if (ev.kind === "thinking") {
    const turn = el("div", "turn turn-thinking");
    turn.appendChild(dot("ring"));
    const t = el("div", "thinking" + (ev.encrypted ? " encrypted" : ""));
    t.textContent = ev.encrypted ? "Thinking…" : ev.text;
    if (ev.encrypted) { turn.appendChild(t); return turn; }   // already a one-liner
    // condense: clamp to ~2 lines with a fade; click to expand (the user: don't let
    // the interspersed thinking blocks dominate vertically).
    const clamp = el("div", "think-clamp");
    clamp.appendChild(t);
    clamp.title = "click to expand";
    clamp.addEventListener("click", () => clamp.classList.toggle("expanded"));
    turn.appendChild(clamp);
    return turn;
  }
  if (ev.kind === "postal") return renderPostal(ev);
  if (ev.kind === "todo") return renderTodo(ev);
  if (ev.kind === "queued") return renderQueued(ev);
  if (ev.kind === "subagent") return renderSubagent(ev);
  if (ev.kind === "apiError") return renderApiError(ev);
  if (ev.kind === "compact") return renderCompact(ev);
  return renderTool(ev);
}

// AskUserQuestion — render the posed question(s) + options. While the question is still pending it's a
// neutral "Question" card; once it's been ANSWERED it becomes the blue, right-aligned "you answered
// Claude's question" box so the scrollback shows it was a reply to a popup, not a typed message (the
// user 2026-06-16). Prefers the kernel's structured askAnswer (question/options/chosen already joined);
// falls back to parsing the raw tool input/output when it isn't attached yet, so the turn renders the
// same either way.
function renderAsk(ev: Extract<ChatEvent, { kind: "tool" }>): HTMLElement | null {
  const blocks = (ev.askAnswer && ev.askAnswer.length) ? ev.askAnswer : parseAskRaw(ev);
  if (!blocks || !blocks.length) return null;
  // answered = at least one question has a recorded answer (chosen text). Empty chosen = still pending.
  const answered = blocks.some((b) => b.chosen && b.chosen.length > 0);

  const turn = el("div", "turn turn-ask" + (answered ? " answered" : ""));
  turn.appendChild(dot(answered ? "user" : "ring"));   // answered → the blue user dot, matching the box
  const card = el("div", "ask-card" + (answered ? " ask-answered" : ""));
  if (answered) {
    const tag = el("div", "ask-answered-tag");
    tag.textContent = "↳ You answered Claude’s question";
    card.appendChild(tag);
  } else {
    const head = el("div", "ask-head");
    head.textContent = blocks.length > 1 ? `${blocks.length} questions` : "Question";
    card.appendChild(head);
  }
  for (const b of blocks) {
    const qel = el("div", "ask-q");
    const qt = el("div", "ask-qtext"); qt.textContent = b.question || b.header || ""; qel.appendChild(qt);
    const opts = Array.isArray(b.options) ? b.options : [];
    const labels = opts.map((o) => String(o.label || "")).filter(Boolean);
    const chosen = (b.chosen || []).map((c) => String(c));
    const picked = new Set(chosen.filter((c) => labels.includes(c)));   // answers that name an option
    const others = chosen.filter((c) => !labels.includes(c));           // free-text "Other" answers
    for (const o of opts) {
      const isChosen = !!o.label && picked.has(String(o.label));
      const opt = el("div", "ask-opt" + (isChosen ? " chosen" : ""));
      const mark = el("span", "ask-mark"); mark.textContent = isChosen ? "●" : "○"; opt.appendChild(mark);
      const lab = el("span", "ask-optlabel"); lab.textContent = o.label || ""; opt.appendChild(lab);
      if (o.description) { const d = el("span", "ask-optdesc"); d.textContent = o.description; opt.appendChild(d); }
      qel.appendChild(opt);
    }
    // a free-text answer matching no option → a selected "Other" row + the verbatim words (quoted),
    // so a typed answer is never silently dropped to an empty-looking menu.
    for (const other of others) {
      const opt = el("div", "ask-opt chosen ask-other");
      const mark = el("span", "ask-mark"); mark.textContent = "●"; opt.appendChild(mark);
      const lab = el("span", "ask-optlabel"); lab.textContent = "Other"; opt.appendChild(lab);
      const d = el("span", "ask-answer-text"); d.textContent = "“" + other + "”"; opt.appendChild(d);
      qel.appendChild(opt);
    }
    card.appendChild(qel);
  }
  turn.appendChild(card);
  return turn;
}

// Fallback when the kernel hasn't attached askAnswer yet: parse the posed questions from the tool input
// (JSON) and the recorded answer from the tool output (`"<q>"="<a>"` pairs) into the same block shape
// renderAsk consumes. The answer text may name an option label OR be free-text ("Other"); multi-select
// joins labels as "A, B, C". Comma-split only when a label actually matches, so a free-text answer that
// happens to contain commas isn't shredded.
function parseAskRaw(ev: Extract<ChatEvent, { kind: "tool" }>): AskAnswerBlock[] | null {
  let data: any;
  try { data = JSON.parse(ev.input); } catch { return null; }
  const qs = data && Array.isArray(data.questions) ? data.questions : null;
  if (!qs || !qs.length) return null;
  const out = ev.output || "";
  const pairs = new Map<string, string>();
  for (const m of out.matchAll(/[“"]([^”"]*)[”"]\s*=\s*[“"]([^”"]*)[”"]/g)) pairs.set(m[1].trim(), m[2]);
  const pairVals = Array.from(pairs.values());
  const answerFor = (q: any): string =>
    qs.length === 1 && pairVals.length ? pairVals[0]
      : pairs.get(String(q.question || "").trim()) ?? pairs.get(String(q.header || "").trim()) ?? "";
  return qs.map((q: any): AskAnswerBlock => {
    const opts = Array.isArray(q.options) ? q.options : [];
    const labels = opts.map((o: any) => String(o.label || "")).filter(Boolean);
    const ans = answerFor(q);
    let chosen: string[] = [];
    if (ans) {
      if (labels.includes(ans)) chosen = [ans];
      else {
        const parts = ans.split(/,\s*/).map((s) => s.trim()).filter(Boolean);
        chosen = parts.some((p) => labels.includes(p)) ? parts : [ans];   // matched labels highlight; rest → "Other"
      }
    }
    return {
      question: String(q.question || ""),
      header: q.header ? String(q.header) : undefined,
      options: opts.map((o: any) => ({ label: String(o.label || ""), description: o.description ? String(o.description) : undefined })),
      chosen,
    };
  });
}

// Claude Code's Task to-do list — a compact live checklist mirroring the terminal:
// ○ pending / ◐ in_progress / ✓ completed (done is struck through).
function renderTodo(ev: Extract<ChatEvent, { kind: "todo" }>): HTMLElement {
  const turn = el("div", "turn turn-todo");
  turn.appendChild(dot("ring"));
  const card = el("div", "todo-card");
  const done = ev.tasks.filter((t) => t.status === "completed").length;
  const head = el("div", "todo-head"); head.textContent = `To-do · ${done}/${ev.tasks.length}`;
  card.appendChild(head);
  for (const t of ev.tasks) {
    const row = el("div", "todo-item todo-" + t.status);
    const mark = el("span", "todo-mark");
    mark.textContent = t.status === "completed" ? "✓" : t.status === "in_progress" ? "◐" : "○";
    row.appendChild(mark);
    const txt = el("span", "todo-text");
    txt.textContent = t.status === "in_progress" && t.activeForm ? t.activeForm : t.subject;
    row.appendChild(txt);
    card.appendChild(row);
  }
  turn.appendChild(card);
  return turn;
}

// A context compaction → one clean teal rail marker (the user 2026-06-14): replaces the raw /compact
// stdout (leaked ANSI dim codes + hook-completion noise). renderEvent adds the rail time-marker +
// hover wiring (this turn has a .dot); in compact mode it passes through unchanged → the same marker.
function renderCompact(_ev: Extract<ChatEvent, { kind: "compact" }>): HTMLElement {
  const turn = el("div", "turn turn-compact");
  turn.appendChild(dot("ring"));
  const line = el("div", "compact-line");
  line.textContent = "✦ Compacted";
  line.title = "the conversation was compacted here";
  turn.appendChild(line);
  return turn;
}

// Pending queued messages — the user's inputs submitted while the session was still
// working, not yet processed. Rendered at the bottom (closest to the composer),
// styled as faint right-aligned "you" bubbles so they read as his words, waiting.
function renderQueued(ev: Extract<ChatEvent, { kind: "queued" }>): HTMLElement {
  const turn = el("div", "turn turn-queued");
  const n = ev.texts.length;
  const head = el("div", "queued-head");
  head.textContent = `⌛ ${n} queued message${n === 1 ? "" : "s"}`;
  turn.appendChild(head);
  for (const t of ev.texts) {
    const bubble = el("div", "queued-bubble");
    bubble.textContent = t;
    turn.appendChild(bubble);
  }
  return turn;
}

// Subagent in flight (Task/Agent) — the session is quiet but still working. A compact
// orange card at the bottom so it's clear WHY there's no streaming output.
function renderSubagent(ev: Extract<ChatEvent, { kind: "subagent" }>): HTMLElement {
  const turn = el("div", "turn turn-subagent");
  const head = el("div", "subagent-head");
  head.textContent = ev.desc ? `⚙ subagent · ${ev.desc}` : "⚙ subagent running…";
  turn.appendChild(head);
  return turn;
}

// The turn stopped on an API error — the session is BLOCKED until retried. A red-dot card at the bottom
// (so it stands out, the user 2026-06-16) carrying the error text + a red "API error" badge and a Retry
// button that pastes "retry" into the session to resume the stalled turn.
function renderApiError(ev: Extract<ChatEvent, { kind: "apiError" }>): HTMLElement {
  const turn = el("div", "turn turn-apierror");
  turn.appendChild(dot("red"));
  const card = el("div", "apierror-card");
  const head = el("div", "apierror-head");
  const badge = el("span", "apierror-badge");
  badge.textContent = ev.status ? `API error · ${ev.status}` : "API error";
  head.appendChild(badge);
  // Live countdown to the next AUTO-retry — apiRetryTick() (below) updates this text every second.
  const countdown = el("span", "apierror-countdown");
  countdown.textContent = "retrying soon…";
  head.appendChild(countdown);
  const retry = el("button", "apierror-retry") as HTMLButtonElement;
  retry.textContent = "Retry now";
  retry.title = "send “retry” into this session right now (also resets the auto-retry countdown)";
  retry.addEventListener("click", () => {
    if (vscodeApi) vscodeApi.postMessage({ type: "apiRetry", id: activeId });
    if (activeId) apiRetryNext.set(activeId, Date.now() + API_RETRY_MS);   // restart the countdown
  });
  head.appendChild(retry);
  card.appendChild(head);
  const body = el("div", "apierror-body");
  body.textContent = ev.text || "The session stopped on an API error.";
  card.appendChild(body);
  turn.appendChild(card);
  return turn;
}

// ── API-error auto-retry ──────────────────────────────────────────────────────────────────────────
// While a session sits BLOCKED on an API error (status.state === "blocked"), retry it every 10s until it
// recovers (the kernel stops marking it blocked → its timer is dropped). Client-side, self-cancelling, and
// covers EVERY blocked session (not just the visible tab); the active session's card shows a live
// countdown. The API may be down, so this deliberately doesn't depend on the summary/caption pipeline.
const API_RETRY_MS = 10_000;
const apiRetryNext = new Map<string, number>();   // sid -> epoch ms of its next auto-retry
function apiRetryTick(): void {
  const now = Date.now();
  const blocked = new Set<string>();
  sessions.forEach((s, id) => { if (s.status.state === "blocked") blocked.add(id); });
  apiRetryNext.forEach((_, id) => { if (!blocked.has(id)) apiRetryNext.delete(id); });   // recovered → stop
  blocked.forEach((id) => {
    if (!apiRetryNext.has(id)) apiRetryNext.set(id, now + API_RETRY_MS);
    if (now >= (apiRetryNext.get(id) as number)) {
      if (vscodeApi) vscodeApi.postMessage({ type: "apiRetry", id });
      apiRetryNext.set(id, now + API_RETRY_MS);                                          // reset the countdown
    }
  });
  // live "retrying in Ns" on the active session's card, if it's the blocked one being viewed
  const cd = document.querySelector(".apierror-countdown") as HTMLElement | null;
  if (cd) {
    const at = activeId ? apiRetryNext.get(activeId) : undefined;
    cd.textContent = at ? `retrying in ${Math.max(0, Math.ceil((at - now) / 1000))}s` : "retrying soon…";
  }
}
setInterval(apiRetryTick, 1000);

function renderTool(ev: Extract<ChatEvent, { kind: "tool" }>): HTMLElement {
  if (ev.name === "AskUserQuestion") { const a = renderAsk(ev); if (a) return a; }
  const turn = el("div", "turn turn-tool" + (ev.isError ? " tool-err" : ""));
  const d = dot(ev.isError ? "ring" : "green");
  if (ev.isError) d.classList.add("err");
  turn.appendChild(d);

  const head = el("div", "tool-head");
  const name = el("span", "tool-name"); name.textContent = ev.name;
  head.appendChild(name);
  if (ev.file) head.appendChild(fileLink(ev.file));
  else if (ev.desc) { const c = el("span", "tool-desc"); c.textContent = ev.desc; head.appendChild(c); }

  const ack = ACK_TOOLS.has(ev.name);
  turn.appendChild(head);

  if (ev.isError) {
    if (ev.input || ev.output) turn.appendChild(ioClamp(ev.input, ev.output, true)); // errors: always show
  } else if (ev.diff) {
    // Edit/MultiEdit: "+add −del" on the head line; the red/green diff hangs below, hidden.
    let add = 0, del = 0;
    for (const l of ev.diff.split("\n")) { if (l[0] === "+") add++; else if (l[0] === "-") del++; }
    const pre = el("pre", "io-pre fold-pre diff-fold");
    const code = el("code", "language-diff"); code.textContent = ev.diff; pre.appendChild(code);
    inlineFold(head, turn, `+${add} −${del}`, pre);
    highlight(pre, false);   // diffs carry +/− markers + already wrap (io-pre); no line-number gutter
  } else if (ev.name === "Read") {
    if (ev.output) inlineFold(head, turn, `${countLines(ev.output)} lines`, preEl(ev.output));
  } else if (!ack && (ev.input || ev.output)) {
    const signal = ev.name === "Task" || ev.name === "Agent";
    if (signal) {
      // Subagent (Task/Agent) = a delegated mini-conversation. Its PROMPT is context, not the signal,
      // so it folds onto the head line ("prompt"); the agent's REPORT renders as a faded, green-edged
      // sub-transcript block — clamped, click to expand. (the user 2026-06-14: not a big text box.)
      if (ev.input) inlineFold(head, turn, "prompt", preEl(ev.input));
      if (ev.output) {
        const clamp = el("div", "io-clamp agent-clamp");
        const report = el("div", "agent-report md"); report.innerHTML = md(ev.output); highlight(report);
        clamp.appendChild(report);
        clamp.addEventListener("click", () => clamp.classList.toggle("expanded"));
        turn.appendChild(clamp);
      }
    } else if (!ev.output) {
      const io = el("div", "tool-io"); if (ev.input) io.appendChild(ioRow("IN", ev.input, false)); turn.appendChild(io);
    } else {
      // Bash/Grep/Glob/…: output line-count on the head line (right of the command);
      // the command + full output hang below, hidden until clicked.
      const io = el("div", "tool-io tool-io-fold");
      if (ev.input) io.appendChild(ioRow("IN", ev.input, false));
      io.appendChild(ioRow("OUT", ev.output, false));
      const n = countLines(ev.output);
      inlineFold(head, turn, `${n} line${n === 1 ? "" : "s"}`, io);
    }
  }
  // No right-side status glyph: the LEFT rail dot already carries the outcome — a green ✓
  // disc on success, a red ✗ disc on error (the user 2026-06-13). The old in-head ✓/✗ sat
  // right beside an identical dot, so it was pure duplication.
  return turn;
}


// Navigate to a session by its romp NAME. If it's an open tab, just select it
// (no host round-trip); otherwise ask the host to resolve the name → transcript
// and open/revive it.
function navToSession(name: string) {
  const open = order.find((id) => sessions.get(id)?.name === name);
  if (open) { setActive(open); return; }
  if (vscodeApi) vscodeApi.postMessage({ type: "openByName", name });
}

// Turn an element into a clickable session-name chip (cursor + hover underline,
// click navigates). Used for the sender/recipient chip on a postal card.
function makeSessionChip(elm: HTMLElement, name: string) {
  elm.classList.add("chip-nav");
  elm.title = `Go to ${name}`;
  elm.addEventListener("click", (e) => { e.stopPropagation(); navToSession(name); });
}

// Names of sessions currently WORKING (broadcast by the host) → a working dot
// before that name wherever it renders (postal sender/recipient chips).
let workingSet = new Set<string>();
// Ensure a working dot (the same `.tab-dot` used on working tabs) sits before a
// postal peer name iff that session is working. Idempotent.
function setPeerDot(peerEl: HTMLElement, on: boolean) {
  const prev = peerEl.previousElementSibling;
  const has = !!prev && prev.classList.contains("peer-dot");
  if (on && !has) peerEl.parentElement?.insertBefore(el("span", "tab-dot peer-dot"), peerEl);
  else if (!on && has) prev!.remove();
}
function refreshPostalDots() {
  document.querySelectorAll(".postal-peer").forEach((p) => setPeerDot(p as HTMLElement, workingSet.has((p.textContent || "").trim())));
}

// A romp postal message, as a compact identity-coloured card.
// One-line summary for a postal card: the incoming Haiku caption, else the first non-empty line of the
// body (sent mail carries no caption), truncated. The full message lives behind a click-to-expand.
function postalSummary(ev: Extract<ChatEvent, { kind: "postal" }>): string {
  const cap = ev.summary && ev.summary.trim();
  if (cap) return cap;
  const first = (ev.body || "").split("\n").map((s) => s.trim()).find(Boolean) || "";
  return first.length > 100 ? first.slice(0, 99).trimEnd() + "…" : first;
}
const collapseWs = (s: string) => s.replace(/\s+/g, " ").trim();

function renderPostal(ev: Extract<ChatEvent, { kind: "postal" }>): HTMLElement {
  const turn = el("div", "turn turn-postal postal-" + ev.direction);
  if (ev.mid) turn.dataset.mid = ev.mid;   // joins feed-modal handoff hovers to this card
  const d = dot("ring");
  d.classList.add("mail");
  if (ev.color) d.style.background = ev.color.bg;
  turn.appendChild(d);

  const card = el("div", "postal-card");
  if (ev.color) {
    card.style.setProperty("--peer-bg", ev.color.bg);
    card.style.setProperty("--peer-fg", ev.color.fg);
  }

  const head = el("div", "postal-head");
  const arrow = el("span", "postal-arrow");
  arrow.textContent = ev.direction === "in" ? "↙" : "↗";
  const verb = el("span", "postal-dir");
  verb.textContent = ev.direction === "in" ? "from" : "to";
  const peer = el("span", "postal-peer");
  peer.textContent = ev.peer;
  makeSessionChip(peer, ev.peer); // click the sender/recipient name → go to that session's tab
  head.appendChild(arrow);
  head.appendChild(verb);
  head.appendChild(peer);
  setPeerDot(peer, workingSet.has(ev.peer));   // working dot before the peer name if that session is working

  if (ev.park || ev.status === "parked") {
    const b = el("span", "postal-badge parked");
    b.textContent = "⏸ parked";
    head.appendChild(b);
  } else if (ev.status === "delivered") {
    const b = el("span", "postal-badge delivered");
    b.textContent = "✓ delivered";
    head.appendChild(b);
  }

  // (no in-card time — the rail time-marker to the left of the dot carries it, like every
  // other event; see renderEvent's rail time-stamp.)
  card.appendChild(head);

  // Body: ALWAYS lead with a one-line summary — the incoming Haiku caption, or (sent mail / no caption)
  // the first line of the message — and let a click expand the box to the full message inline (the user
  // 2026-06-16). Both directions read the same now: a summary that opens on demand, instead of a hover
  // tooltip (incoming) vs. the whole body always (outgoing).
  const body = el("div", "postal-body md");
  const fullText = (ev.body || "").trim();
  const summaryText = postalSummary(ev);
  const expandable = !!summaryText && !!fullText && collapseWs(fullText) !== collapseWs(summaryText);
  if (expandable) {
    const sum = el("div", "postal-summary");
    const caret = el("span", "postal-expand-caret"); caret.textContent = "▸"; sum.appendChild(caret);
    const sumText = el("span", "postal-summary-text"); sumText.textContent = summaryText; sum.appendChild(sumText);
    const full = el("div", "postal-full md"); full.innerHTML = md(ev.body); highlight(full);
    sum.title = "click to expand the full message";
    sum.addEventListener("click", () => {
      const open = body.classList.toggle("expanded");
      caret.textContent = open ? "▾" : "▸";
    });
    body.classList.add("postal-expandable");
    body.appendChild(sum);
    body.appendChild(full);
  } else {
    body.innerHTML = md(ev.body);
    highlight(body);
  }
  card.appendChild(body);

  turn.appendChild(card);
  return turn;
}

// (statusline chips removed — working state shows the spinner, other states show
//  on the tab outline; CHIP_LABEL is no longer needed.)

function bgRgb(): [number, number, number] {
  try {
    const m = /(\d+)\D+(\d+)\D+(\d+)/.exec(getComputedStyle(document.body).backgroundColor || "");
    if (m) return [+m[1], +m[2], +m[3]];
  } catch { /* ignore */ }
  return [30, 30, 30];
}

// Perceptual fade for an idle session's color: blend toward the background until
// its luminance hits a uniform low target, so a bright hue (yellow) fades as much
// as a dim one (blue) — consistent "faded-ness" regardless of color. Never
// touches the bright color (only used for at-rest tabs).
function fadedColor(hex: string): string {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const [br, bgc, bb] = bgRgb();
  const lum = (x: number, y: number, z: number) => 0.2126 * x + 0.7152 * y + 0.0722 * z;
  const Lc = lum(r, g, b), Lb = lum(br, bgc, bb), Lt = Lb + 38;
  if (Lc <= Lt) return hex; // already dim — leave it
  const t = Math.min(0.85, (Lc - Lt) / (Lc - Lb));
  const hx = (a: number, c: number) => Math.round(a * (1 - t) + c * t).toString(16).padStart(2, "0");
  return `#${hx(r, br)}${hx(g, bgc)}${hx(b, bb)}`;
}

// Tab display order mirrors the romp timeline's lanes: three tiers, each by
// first-seen (launch) ascending. tier 0 = active live (within the last hour),
// tier 1 = ended/closed, tier 2 = idle live (>1h quiet).
// The shared, drag-set order (SID array) from the host — synced with the timeline.
// Sessions listed here come first in that explicit order; the rest fall back to the
// tier/first-seen default and append.
let sharedOrder: string[] = [];
// A session's LAST position in the shared order. A tab that drops out of the live order (its session
// died or /cleared → new id) keeps THIS slot instead of re-tiering to the end — so rows don't move on
// their own (the user 2026-06-16). Only sessions never seen in any order fall to the tier/first-seen default.
const lastIdx = new Map<string, number>();
function recordOrder(arr: string[]) { arr.forEach((id, i) => lastIdx.set(id, i)); }
function effIdx(id: string): number {
  const i = sharedOrder.indexOf(id);
  return i >= 0 ? i : (lastIdx.has(id) ? (lastIdx.get(id) as number) : Infinity);
}
function sortTabs() {
  order.sort((a, b) => {
    const ia = effIdx(a), ib = effIdx(b);
    if (ia !== ib) return ia - ib;                  // current OR last-known position — no jump when a tab dies
    const sa = sessions.get(a), sb = sessions.get(b);
    if (!sa || !sb) return 0;
    // Sessions not covered by the shared order tie here → order by LAUNCH TIME only, NEVER by state, so a
    // tab never moves on its own when its chip changes (working→ready→blocked/faded). The host now pushes
    // the saved order on connect, so covered tabs already resolve via effIdx above (the user 2026-06-16, #11).
    return (sa.firstSeen ?? 0) - (sb.firstSeen ?? 0);
  });
}
// Persist the current full tab order to the shared store (host writes the file →
// the timeline picks it up). Called after a drag.
function commitTabOrder() {
  sharedOrder = order.slice();
  recordOrder(sharedOrder);
  if (vscodeApi) vscodeApi.postMessage({ type: "reorderTabs", order: order.slice() });
}
// Apply a shared order pushed from the host (e.g. the timeline reordered it).
function applyTabOrder(o: any) {
  sharedOrder = Array.isArray(o) ? o.filter((x: any) => typeof x === "string") : [];
  recordOrder(sharedOrder);
  sortTabs();
  renderTabs();
}
let draggedId: string | null = null;
function reorderTo(dragId: string, targetId: string, after: boolean) {
  const di = order.indexOf(dragId);
  if (di < 0) return;
  order.splice(di, 1);
  const ti = order.indexOf(targetId);
  if (ti < 0) order.push(dragId);
  else order.splice(after ? ti + 1 : ti, 0, dragId);
  commitTabOrder();
  renderTabs();
}

// While a tab name is being edited in place, defer re-renders (a tick's status
// refresh would otherwise replace the tab bar and destroy the input mid-edit).
let renameActive = false;
let renderPendingAfterRename = false;
function renderTabs() {
  if (renameActive) { renderPendingAfterRename = true; return; }
  const bar = document.getElementById("tabs");
  if (!bar) return;
  bar.replaceChildren();
  for (const id of order) {
    const s = sessions.get(id);
    if (!s) continue;
    const tab = el("div", "tab" + (id === activeId ? " active" : ""));
    tab.tabIndex = 0;            // focusable for keyboard nav
    tab.dataset.id = id;
    tab.addEventListener("keydown", onTabKey);
    // drag-to-reorder (synced with the timeline via the shared session-order file)
    tab.draggable = true;
    tab.addEventListener("dragstart", (e) => { draggedId = id; if (e.dataTransfer) e.dataTransfer.effectAllowed = "move"; tab.classList.add("dragging"); });
    tab.addEventListener("dragend", () => { draggedId = null; document.querySelectorAll(".tab.dragging,.tab.drop-before,.tab.drop-after").forEach((t) => t.classList.remove("dragging", "drop-before", "drop-after")); });
    tab.addEventListener("dragover", (e) => {
      if (!draggedId || draggedId === id) return;
      e.preventDefault();
      const r = tab.getBoundingClientRect();
      const after = e.clientX > r.left + r.width / 2;
      tab.classList.toggle("drop-after", after);
      tab.classList.toggle("drop-before", !after);
    });
    tab.addEventListener("dragleave", () => tab.classList.remove("drop-before", "drop-after"));
    tab.addEventListener("drop", (e) => {
      tab.classList.remove("drop-before", "drop-after");
      if (!draggedId || draggedId === id) return;
      e.preventDefault();
      const r = tab.getBoundingClientRect();
      reorderTo(draggedId, id, e.clientX > r.left + r.width / 2);
    });
    if (s.color) {
      tab.style.setProperty("--chip-bg", s.color.bg);
      tab.style.setProperty("--chip-fg", s.color.fg);
      tab.classList.add("colored");
    }
    const st = s.status.state;
    // ADDITIVE: a background subagent shows ONLY while the session is otherwise quiet (ready/idle); a
    // working session hides it (the user 2026-06-16, re-spec from #9).
    const subActive = s.status.subagent != null && (st === "ready" || st === "idle");
    if (st === "working") tab.classList.add("tab-working");
    else if (st === "blocked") tab.classList.add("tab-blocked");     // red: stopped on an API error
    else if (st === "awaiting") tab.classList.add("tab-awaiting");
    else if (st === "compacting") tab.classList.add("tab-compacting");
    else if (st === "closed") tab.classList.add("tab-closed");       // dead session: read-only, struck-through label
    if (subActive) tab.classList.add("tab-subagent");                // orange accent ADDED to the quiet tab
    if (s.status.faded) tab.classList.add("at-rest");
    // WORKING shows a yellow dot; a quiet tab with a background subagent shows an ORANGE dot (additive).
    // BLOCKED (API error) gets NO dot — the dashed red tab highlight instead (the user 2026-06-16).
    if (st === "working") tab.appendChild(el("span", "tab-dot"));
    else if (subActive) tab.appendChild(el("span", "tab-dot tab-dot-subagent"));
    const label = el("span", "tab-label");
    label.textContent = s.name;
    if (s.status.faded && id !== activeId && s.color) {
      const full = s.color.bg;
      label.style.color = fadedColor(full);
      // hover un-fades the name to its full (readable) identity color, reverting on leave
      tab.addEventListener("mouseenter", () => { label.style.color = full; });
      tab.addEventListener("mouseleave", () => { label.style.color = fadedColor(full); });
    }
    tab.appendChild(label);
    const close = el("span", "tab-close");
    close.textContent = "×";
    // A dead (closed) session has nothing to end, so its ✕ just removes the read-only tab — no
    // "End session?" confirm (the user 2026-06-16). A live session still routes through the host's
    // Close-tab / End-session confirm (closeSession → confirmClose).
    const dead = st === "closed";
    close.title = dead ? "Close tab" : "Close tab (or end the session)";
    close.addEventListener("click", (e) => {
      e.stopPropagation();
      if (vscodeApi) vscodeApi.postMessage({ type: dead ? "closeTab" : "closeSession", id });
    });
    tab.appendChild(close);
    tab.addEventListener("click", () => setActive(id));
    // double-click a tab to show/hide the ledger overview — same as the strip's caret
    tab.addEventListener("dblclick", (e) => { e.preventDefault(); toggleLedgerCollapsed(); });
    // right-click → context menu; "Rename" edits the title in place
    tab.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); showTabMenu(e, tab, label, id); });
    bar.appendChild(tab);
  }
  const add = el("div", "tab tab-add");
  add.textContent = "+";
  add.title = "Open a session";
  add.addEventListener("click", () => openPicker());
  bar.appendChild(add);
  // (The collapse caret moved OFF the tab bar into the #ledger strip's title row — the strip now always
  // shows the session title + caret, expanding to goals / working-on / done. See renderLedger. 2026-06-16)
}

// Right-click context menu on a tab. Webviews can't use VS Code's native menus,
// so this is a small themed floating menu; one open at a time, dismissed by any
// outside click, Escape, scroll, or losing window focus.
let ctxMenuEl: HTMLElement | null = null;
function dismissTabMenu() {
  ctxMenuEl?.remove();
  ctxMenuEl = null;
}

// Right-clicking a SELECTION in the transcript pops a small menu with Reply (quote
// the selection into the composer as a "> …" blockquote) and Copy. With no selection
// inside the chat we leave the native/default menu alone. Reuses the tab menu's
// ctx-menu chrome + its global dismissal (outside-click / Esc / scroll / blur).
function showSelectionMenu(e: MouseEvent) {
  const content = document.getElementById("content");
  const sel = window.getSelection();
  const text = sel ? sel.toString() : "";
  if (!content || !sel || !sel.anchorNode || !content.contains(sel.anchorNode) || !text.trim()) return;
  e.preventDefault();
  dismissTabMenu();
  const menu = el("div", "ctx-menu");
  const mk = (labelText: string, fn: () => void) => {
    const item = el("div", "ctx-item");
    item.textContent = labelText;
    item.addEventListener("click", (ev) => { ev.stopPropagation(); dismissTabMenu(); fn(); });
    menu.appendChild(item);
  };
  mk("Reply", () => quoteSelectionIntoComposer(text));
  mk("Copy", () => copyToClipboard(text));
  document.body.appendChild(menu);
  ctxMenuEl = menu;
  const r = menu.getBoundingClientRect();
  menu.style.left = Math.max(0, Math.min(e.clientX, window.innerWidth - r.width - 4)) + "px";
  menu.style.top = Math.max(0, Math.min(e.clientY, window.innerHeight - r.height - 4)) + "px";
}

// Drop the selection into the composer as a markdown blockquote (quote.ts does the
// formatting), cursor on the blank line below it, and remember it as the draft.
function quoteSelectionIntoComposer(text: string) {
  const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null;
  if (!ta) return;
  const { value, caret } = quoteReply(text, ta.value);
  ta.value = value;
  ta.selectionStart = ta.selectionEnd = caret;
  growComposer(ta);
  ta.focus();
  if (activeId) drafts.set(activeId, ta.value);
}

function copyToClipboard(text: string) {
  navigator.clipboard?.writeText(text).catch(() => { try { document.execCommand("copy"); } catch { /* best effort */ } });
}
function showTabMenu(e: MouseEvent, tab: HTMLElement, label: HTMLElement, id: string) {
  dismissTabMenu();
  const menu = el("div", "ctx-menu");
  const rename = el("div", "ctx-item");
  rename.textContent = "Rename";
  rename.addEventListener("click", (ev) => { ev.stopPropagation(); dismissTabMenu(); startTabRename(tab, label, id); });
  menu.appendChild(rename);
  document.body.appendChild(menu);
  ctxMenuEl = menu;
  // at the cursor, clamped so it never overflows the pane
  const r = menu.getBoundingClientRect();
  menu.style.left = Math.max(0, Math.min(e.clientX, window.innerWidth - r.width - 4)) + "px";
  menu.style.top = Math.max(0, Math.min(e.clientY, window.innerHeight - r.height - 4)) + "px";
}
window.addEventListener("mousedown", (e) => { if (ctxMenuEl && !ctxMenuEl.contains(e.target as Node)) dismissTabMenu(); }, true);
window.addEventListener("keydown", (e) => { if (e.key === "Escape") dismissTabMenu(); }, true);
window.addEventListener("scroll", dismissTabMenu, true);
window.addEventListener("blur", () => dismissTabMenu());

// "Rename" (tab context menu): swap the tab's label for an inline input. Enter
// or clicking away commits (the host renames the tmux session and confirms with
// a "renamed" message — the label only changes once that lands), Esc cancels.
function startTabRename(tab: HTMLElement, label: HTMLElement, id: string) {
  const s = sessions.get(id);
  if (!s || tab.querySelector(".tab-rename")) return;
  const input = document.createElement("input") as HTMLInputElement;
  input.className = "tab-rename";
  input.value = s.name;
  input.spellcheck = false;
  input.size = Math.max(s.name.length, 4);
  renameActive = true;
  tab.draggable = false;            // dragging would eat the text selection
  label.style.display = "none";
  label.after(input);
  let finished = false;
  const done = (commit: boolean) => {
    if (finished) return;
    finished = true;
    const v = input.value.trim();
    input.remove();
    label.style.display = "";
    tab.draggable = true;
    renameActive = false;
    if (renderPendingAfterRename) { renderPendingAfterRename = false; renderTabs(); }
    if (commit && v && v !== s.name && vscodeApi) vscodeApi.postMessage({ type: "renameSession", id, name: v });
  };
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); done(true); }
    else if (e.key === "Escape") { e.preventDefault(); done(false); }
  });
  input.addEventListener("blur", () => done(true));
  // keep clicks inside the input from selecting/dragging the tab underneath
  for (const ev of ["click", "mousedown", "dblclick", "contextmenu"]) input.addEventListener(ev, (e) => e.stopPropagation());
  input.focus();
  input.select();
}

// Keyboard nav on a focused tab: ←/→ step prev/next; ↑/↓ jump to the nearest tab
// in the row above/below (tabs wrap via flex-wrap).
function onTabKey(e: KeyboardEvent) {
  if (!activeId || !order.length) return;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    const i = order.indexOf(activeId);
    if (i < 0) return;
    const dir = e.key === "ArrowRight" ? 1 : -1;
    setActive(order[(i + dir + order.length) % order.length]);
    focusActiveTab();
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    const t = tabInAdjacentRow(activeId, e.key === "ArrowDown" ? 1 : -1);
    if (t) { setActive(t); focusActiveTab(); }
  }
}
function focusActiveTab() {
  const bar = document.getElementById("tabs");
  (bar?.querySelector(`.tab[data-id="${activeId}"]`) as HTMLElement | null)?.focus();
}

// Window-level arrow nav for when the CHAT WINDOW (not the composer or a dialog)
// has focus: ←/→ step between tabs, ↑/↓ scroll the transcript. Deliberately
// yields to anything more specific —
//   • a typing target (textarea/input/contenteditable) keeps its native caret;
//   • an open picker/confirm overlay (.picker-overlay) owns its own keys;
//   • a handler that already acted (defaultPrevented) wins — a FOCUSED tab's
//     onTabKey (which also does ↑/↓ row-jumps) and the live-ask card both
//     preventDefault before this bubbles to window.
// On ←/→ we do NOT focus the tab, so focus stays in the window and ↑/↓ keep
// scrolling. Any modifier (so Cmd/Ctrl/Alt/Shift shortcuts and selection are
// untouched) bails out.
const NAV_SCROLL_STEP = 60;
function isTypingTarget(t: EventTarget | null): boolean {
  const elm = t as HTMLElement | null;
  if (!elm || typeof elm.tagName !== "string") return false;
  return elm.tagName === "TEXTAREA" || elm.tagName === "INPUT" || elm.isContentEditable === true;
}
window.addEventListener("keydown", (e) => {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  if (isTypingTarget(e.target)) return;
  if (document.querySelector(".picker-overlay")) return;   // #picker / #confirm open
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    if (!activeId || order.length < 2) return;
    const i = order.indexOf(activeId);
    if (i < 0) return;
    e.preventDefault();
    const dir = e.key === "ArrowRight" ? 1 : -1;
    setActive(order[(i + dir + order.length) % order.length]);
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    const content = document.getElementById("content");
    if (!content) return;
    e.preventDefault();
    content.scrollBy({ top: e.key === "ArrowDown" ? NAV_SCROLL_STEP : -NAV_SCROLL_STEP });
  }
});
// Nearest tab in the row above (dir<0) or below (dir>0) the given tab, by column.
function tabInAdjacentRow(id: string, dir: number): string | null {
  const bar = document.getElementById("tabs");
  const cur = bar?.querySelector(`.tab[data-id="${id}"]`) as HTMLElement | null;
  if (!bar || !cur) return null;
  const cr = cur.getBoundingClientRect();
  const cx = cr.left + cr.width / 2;
  let best: { id: string; score: number } | null = null;
  for (const t of Array.from(bar.querySelectorAll(".tab[data-id]")) as HTMLElement[]) {
    const r = t.getBoundingClientRect();
    const vGap = dir < 0 ? cr.top - r.bottom : r.top - cr.bottom; // >0 only if on a row in that direction
    if (vGap < -1) continue;
    if ((dir < 0 && r.bottom > cr.top + 1) || (dir > 0 && r.top < cr.bottom - 1)) continue;
    const score = Math.max(0, vGap) * 1000 + Math.abs(r.left + r.width / 2 - cx); // nearest row, then nearest column
    if (!best || score < best.score) best = { id: t.dataset.id!, score };
  }
  return best?.id ?? null;
}

// ---- session picker overlay (colored, Claude-Code-history style) ----

// When true, picking a row returns the selection to the extension (cross-ext
// pickSession) instead of opening a tab. pickAllowNew adds a "New session…" row.
let pickMode = false;
let pickAllowNew = false;

// "Opening session…" modal — shown the instant the user creates a session and
// dismissed when its tab actually arrives (the kernel spawn → tmux → first
// transcript poll has a visible delay; this is the "something is happening" cue).
let pendingNewSession: string | null = null;
let openingTimer: ReturnType<typeof setTimeout> | undefined;
function showOpeningModal(name: string) {
  hideOpeningModal();
  pendingNewSession = name;
  const overlay = el("div", "picker-overlay opening-overlay");
  overlay.id = "opening";
  overlay.style.display = "flex";
  const box = el("div", "picker-box opening-box");
  const title = el("div", "opening-title"); title.textContent = "Opening session";
  const nm = el("div", "opening-name"); nm.textContent = name;
  const dots = el("div", "opening-dots"); dots.append(el("span"), el("span"), el("span"));
  box.append(title, nm, dots);
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  // safety net: never strand the modal if the session never materializes (spawn failed)
  openingTimer = setTimeout(hideOpeningModal, 30000);
}
function hideOpeningModal() {
  pendingNewSession = null;
  if (openingTimer) { clearTimeout(openingTimer); openingTimer = undefined; }
  document.getElementById("opening")?.remove();
}

function openPicker(pick = false, prompt?: string, allowNew = false) {
  pickMode = pick;
  pickAllowNew = pick && allowNew;
  let overlay = document.getElementById("picker");
  if (!overlay) {
    overlay = el("div", "picker-overlay"); overlay.id = "picker";
    const box = el("div", "picker-box");
    const search = el("input", "picker-search") as HTMLInputElement;
    search.id = "picker-search";
    search.placeholder = "Search sessions…";
    search.spellcheck = false;
    search.addEventListener("input", () => { filterPicker(search.value); pickerError(null); });
    const errLine = el("div", "picker-error"); errLine.id = "picker-error";
    const list = el("div", "picker-list"); list.id = "picker-list";
    // hover and keyboard share one "active" row
    list.addEventListener("mouseover", (e) => {
      const row = (e.target as HTMLElement).closest(".picker-row");
      if (row) setActiveRow(row as HTMLElement);
    });
    const actions = el("div", "picker-actions");
    const newSess = el("button", "picker-action");
    newSess.id = "picker-new-btn";
    newSess.textContent = "✛ New session";
    newSess.title = "create a fresh romp session, named by the search box, and open it as a tab";
    newSess.addEventListener("click", () => {
      // The search box doubles as the name field — no native dialog.
      const name = search.value.trim();
      if (!name) { pickerError("Type the new session's name in the box above first."); search.focus(); return; }
      if (!/^[A-Za-z0-9._-]+$/.test(name)) { pickerError("Session names: letters, digits, . _ - only."); search.focus(); return; }
      if (vscodeApi) vscodeApi.postMessage({ type: "createSession", name });
      closePicker();
      showOpeningModal(name);   // "Opening…" cue until the new tab arrives (see upsert)
    });
    const openAll = el("button", "picker-action");
    openAll.textContent = "↗ Open all running sessions";
    openAll.addEventListener("click", () => {
      if (vscodeApi) vscodeApi.postMessage({ type: "openAll" });
      closePicker();
    });
    actions.appendChild(newSess);
    actions.appendChild(openAll);
    box.appendChild(search);
    box.appendChild(errLine);
    box.appendChild(list);
    box.appendChild(actions);
    overlay.appendChild(box);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closePicker(); });
    document.body.appendChild(overlay);
    document.addEventListener("keydown", pickerKey);
  }
  overlay.style.display = "flex";
  const actions = overlay.querySelector(".picker-actions") as HTMLElement | null;
  if (actions) actions.style.display = pick ? "none" : "";
  const s = document.getElementById("picker-search") as HTMLInputElement | null;
  if (s) { s.value = ""; s.placeholder = prompt || "Search sessions, or type a new session's name…"; s.focus(); }
  filterPicker(""); // reset row visibility and disarm the New-session button from a prior open
  pickerError(null);
  if (vscodeApi) vscodeApi.postMessage({ type: "requestSessions" });
}

// ---- in-webview confirm dialog (replaces the host's native modals) ----
// One overlay at a time; Esc / backdrop click cancels (cb(null)). Buttons carry
// a value handed to cb. Reuses the picker overlay's backdrop styling.
let confirmCb: ((v: string | null) => void) | null = null;
function showConfirm(title: string, detail: string, buttons: Array<{ label: string; value: string; danger?: boolean }>, cb: (v: string | null) => void) {
  closeConfirm(null);   // a newer dialog replaces (and cancels) an older one
  confirmCb = cb;
  const overlay = el("div", "picker-overlay confirm-overlay"); overlay.id = "confirm";
  const box = el("div", "picker-box confirm-box");
  const h = el("div", "confirm-title"); h.textContent = title;
  const d = el("div", "confirm-detail"); d.textContent = detail;
  const actions = el("div", "confirm-actions");
  for (const b of buttons) {
    const btn = el("button", "picker-action confirm-btn" + (b.danger ? " danger" : ""));
    btn.textContent = b.label;
    btn.addEventListener("click", () => closeConfirm(b.value));
    actions.appendChild(btn);
  }
  box.appendChild(h); box.appendChild(d); box.appendChild(actions);
  overlay.appendChild(box);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeConfirm(null); });
  document.body.appendChild(overlay);
  const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); closeConfirm(null); } };
  (overlay as any)._key = onKey;
  document.addEventListener("keydown", onKey, true);
  (actions.firstElementChild as HTMLElement | null)?.focus();
}
function closeConfirm(value: string | null) {
  const o = document.getElementById("confirm");
  if (o) {
    const k = (o as any)._key;
    if (k) document.removeEventListener("keydown", k, true);
    o.remove();
  }
  const cb = confirmCb;
  confirmCb = null;
  if (cb) cb(value);
}

// Inline validation message under the search box (null hides it).
function pickerError(msg: string | null) {
  const e = document.getElementById("picker-error");
  if (!e) return;
  e.textContent = msg || "";
  e.classList.toggle("show", !!msg);
}

function closePicker() {
  const o = document.getElementById("picker");
  if (o) o.style.display = "none";
  if (pickMode) {
    if (vscodeApi) vscodeApi.postMessage({ type: "pickResult", id: null });
    pickMode = false;
  }
}

function pickerRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll("#picker-list .picker-row:not(.hidden)")) as HTMLElement[];
}

function setActiveRow(row: HTMLElement | null) {
  document.querySelectorAll("#picker-list .picker-row.active").forEach((r) => r.classList.remove("active"));
  if (row) { row.classList.add("active"); row.scrollIntoView({ block: "nearest" }); }
}

function moveActive(delta: number) {
  const rows = pickerRows();
  if (!rows.length) return;
  const cur = rows.findIndex((r) => r.classList.contains("active"));
  const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1) : (cur + delta + rows.length) % rows.length;
  setActiveRow(rows[next]);
}

function pickerKey(e: KeyboardEvent) {
  const o = document.getElementById("picker");
  if (!o || o.style.display === "none") return;
  if (e.key === "Escape") closePicker();
  else if (e.key === "ArrowDown") { e.preventDefault(); moveActive(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moveActive(-1); }
  else if (e.key === "Enter") {
    e.preventDefault();
    const active = document.querySelector("#picker-list .picker-row.active:not(.hidden)") as HTMLElement | null;
    const target = active ?? pickerRows()[0];
    if (target) { target.click(); return; }
    // No matching session row — if the New-session button is armed (unique
    // name typed), Enter creates it.
    const btn = document.getElementById("picker-new-btn");
    if (btn?.classList.contains("active")) btn.click();
  }
}

function renderPicker(items: any[]) {
  const list = document.getElementById("picker-list");
  if (!list) return;
  list.replaceChildren();
  for (const it of items) {
    const row = el("div", "picker-row" + (it.running ? " running" : ""));
    row.dataset.search = (it.name + " " + (it.summary || "")).toLowerCase();
    const top = el("div", "picker-row-top");
    const name = el("span", "picker-name");
    name.textContent = it.name;
    if (it.color && it.color.bg) name.style.color = it.color.bg;
    const time = el("span", "picker-time");
    time.textContent = it.running ? "running" : it.time;
    top.appendChild(name);
    top.appendChild(time);
    row.appendChild(top);
    if (it.summary) {
      const sum = el("div", "picker-summary");
      sum.textContent = it.summary;
      row.appendChild(sum);
    }
    row.addEventListener("click", () => {
      if (pickMode) {
        if (vscodeApi) vscodeApi.postMessage({ type: "pickResult", id: it.id, name: it.name });
        pickMode = false; // so closePicker doesn't also post a cancel
      } else if (vscodeApi) {
        vscodeApi.postMessage({ type: "openSession", id: it.id });
      }
      closePicker();
    });
    list.appendChild(row);
  }
  if (pickAllowNew) {
    const row = el("div", "picker-row picker-new");
    row.dataset.search = "new session";
    const top = el("div", "picker-row-top");
    const label = el("span", "picker-name"); label.textContent = "+ New session…";
    top.appendChild(label);
    row.appendChild(top);
    row.addEventListener("click", () => {
      if (vscodeApi) vscodeApi.postMessage({ type: "pickResult", createNew: true });
      pickMode = false;
      closePicker();
    });
    list.appendChild(row);
  }
  // Re-apply the current filter (the list may refresh while the user is mid-
  // type) — it also sets the active row / arms the New-session button.
  const s = document.getElementById("picker-search") as HTMLInputElement | null;
  filterPicker(s?.value || "");
}

function filterPicker(q: string) {
  const query = q.toLowerCase();
  document.querySelectorAll("#picker-list .picker-row").forEach((r) => {
    const row = r as HTMLElement;
    const hit = !query || (row.dataset.search || "").includes(query);
    row.classList.toggle("hidden", !hit);
  });
  setActiveRow(pickerRows()[0] ?? null); // keep the highlight on the top of the filtered list
  // A name that matches NO session is a new one: move the highlight to the
  // "✛ New session" button so a bare Enter creates it (mirrors how the first
  // matching row is auto-selected when there ARE matches).
  const btn = document.getElementById("picker-new-btn");
  if (btn) {
    const actionsShown = (btn.closest(".picker-actions") as HTMLElement | null)?.style.display !== "none";
    btn.classList.toggle("active", actionsShown && !!q.trim() && pickerRows().length === 0);
  }
}

function nearBottom(c: HTMLElement): boolean {
  return c.scrollHeight - c.scrollTop - c.clientHeight < 80;
}

function cssEscape(s: string): string {
  return typeof (window as any).CSS?.escape === "function" ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&");
}

// Scroll the thread to the event carrying this source JSONL uuid (the deep-link
// anchor) and flash it. Multiple events can share one line's uuid (a multi-block
// assistant turn) — target the first. If it's not rendered yet, stash it as
// pendingAnchor for the next render pass to retry.
function scrollToAnchor(uuid: string): boolean {
  if (!uuid) return false;
  const v = activeId ? views.get(activeId) : null;
  const target = v?.el.querySelector(`.turn[data-uuid="${cssEscape(uuid)}"]`) as HTMLElement | null;
  if (!target) { pendingAnchor = uuid; landTrail.push("pointer-not-rendered"); return false; }
  // KIND GUARD — the robust half of "title clicks always land on the user's
  // instructions". Upstream producers substitute a reply uuid when the prompt
  // line is off the active path (compaction orphans it), so a prompt-intent
  // anchor can arrive pointing at an assistant turn. The uuid is checked
  // against the rendered DOM here, the one place that can't be fooled: if the
  // intent says "user" and the match isn't a user turn, refuse the uuid and
  // let the time fallback (which is kind-restricted) take over. A landing may
  // lose PRECISION, never KIND — regardless of which upstream hop lied.
  if (pendingAnchorIntent === "user" && !target.classList.contains("turn-user")) {
    pendingAnchor = null; pendingAnchorIntent = null; landTrail.push("pointer-wrong-kind"); return false;
  }
  pendingAnchor = null; pendingAnchorIntent = null;
  landTrail.push("pointer-exact");
  landOn(target);
  return true;
}

// Land on a turn at the TOP of the viewport and KEEP it landed while the chrome
// above the scroll container settles. Top-align (not center) so a jump lands on
// the START of the thing and you read DOWN into it — a long work period isn't
// half-scrolled-past on arrival (the user 2026-06-12). scrollIntoView is a
// one-shot: when a jump also switches tabs, the tab bar re-renders (possibly
// wrapping to a SECOND row) and the ledger box for the new session appears — both
// AFTER the scroll ran. #content shrinks by that growth and the landed turn drifts
// off its mark. So: re-align whenever the bar/ledger actually resizes, plus two
// timed retries for late layout (images, markdown), for ~1.2s — canceled the
// moment the user wheel-scrolls so we never fight a real gesture.
function landOn(target: HTMLElement) {
  const realign = () => target.scrollIntoView({ block: "start", behavior: "auto" });
  realign();
  target.classList.add("anchor-flash");
  setTimeout(() => target.classList.remove("anchor-flash"), 1700);
  const until = Date.now() + 1200;
  let ro: ResizeObserver | null = null;
  const stop = () => { ro?.disconnect(); ro = null; window.removeEventListener("wheel", stop); };
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => { if (Date.now() < until) realign(); else stop(); });
    for (const id of ["tabbar", "ledger"]) { const c = document.getElementById(id); if (c) ro.observe(c); }
  }
  window.addEventListener("wheel", stop, { passive: true });
  setTimeout(() => { if (ro && Date.now() < until + 100) realign(); }, 250);
  setTimeout(() => { if (ro) realign(); stop(); }, 1200);
}

// Time-based anchor FALLBACK: when the uuid anchor can't resolve (orphaned by a
// rewind, an id from another era, a bookkeeping line the chat doesn't render),
// land on the turn nearest the moment instead of silently dumping to the bottom.
// Skips thinking blocks, and PRESERVES INTENT: a prompt-intent click (kind
// "user") restricts to the user's own turns first — a fallback may degrade the
// PRECISION of a landing, never its KIND (the assistant-answer landing bug).
function scrollToNearestT(t: number, kind?: string): boolean {
  const v = activeId ? views.get(activeId) : null;
  if (!v) return false;
  const pick = (userOnly: boolean): { el: HTMLElement | null; d: number } => {
    let best: HTMLElement | null = null, bestd = Infinity;
    for (const elx of Array.from(v.el.querySelectorAll(".turn[data-t]")) as HTMLElement[]) {
      if (elx.classList.contains("turn-thinking")) continue;
      if (userOnly && !elx.classList.contains("turn-user")) continue;
      const d = Math.abs(Number(elx.dataset.t) - t);
      if (d < bestd) { bestd = d; best = elx; }
    }
    return { el: best, d: bestd };
  };
  const hit = pick(kind === "user");
  // Prompt intent NEVER degrades to a non-user turn: every card is minted from
  // a typed turn, so the nearest user turn IS the instruction (or a neighbor
  // of it) — whereas "the adjacent assistant turn" is exactly the wrong-kind
  // landing the guard upstream just refused. No user turn within the cap →
  // honest default scroll beats a confident wrong landing.
  if (!hit.el || hit.d > 6 * 3600) {               // nothing within 6h → not a real match
    landTrail.push(!hit.el ? (kind === "user" ? "no-user-turns" : "no-turns") : `nearest-too-far-${Math.round(hit.d)}s`);
    return false;
  }
  landTrail.push(`time-near-${Math.round(hit.d)}s`);
  landOn(hit.el);
  return true;
}

// Transient bottom-center notice for DEGRADED deep-link landings only (see
// the diagnostics block in showActive) — a bad jump announces itself instead
// of impersonating a successful one.
function landToast(msg: string) {
  const t = el("div", "locate-toast");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add("fade"), 5200);
  setTimeout(() => t.remove(), 6000);
}

// Trailing events to re-render on each sync, in case they mutated in place
// (e.g. a tool's output arriving after its tool_use was first shown). Earlier
// events are immutable in an append-only transcript, so they stay cached.
const TAIL_RECHECK = 25;

function ensureView(id: string): View {
  let v = views.get(id);
  if (!v) {
    const content = document.getElementById("content");
    const elv = el("div", "thread");
    elv.dataset.session = id;
    elv.style.display = "none";
    content?.appendChild(elv);
    v = { el: elv, rendered: 0, scrollTop: 0, stick: true, shown: false, stale: false };
    views.set(id, v);
  }
  return v;
}

// Bring this view's DOM up to date with its session's events: append new ones
// and re-render a bounded trailing window (cheap), or rebuild fully on a shrink
// (rewind). Does NOT touch scroll. No-op cost when nothing changed is ~O(TAIL).
function syncView(id: string): View {
  const v = ensureView(id);
  const s = sessions.get(id);
  if (!s) return v;
  const working = s.status.state === "working" || s.status.state === "compacting";
  // Compact mode: hide thinking, collapse consecutive tool runs, then run the SAME rail-timestamp
  // chain over the resulting display stream. It's a global transform (runs can span the trailing
  // window), so the compact path always does a full rebuild rather than the incremental append.
  if (settings.compact) { rebuildCompact(v, s, working); return v; }
  const len = s.events.length;
  let from: number;
  if (len < v.rendered) from = 0;                                   // shrink/rewind → full rebuild
  else if (v.stale) from = Math.min(v.rendered, lastTurnStart(s.events)); // updated while hidden → re-render the whole current turn
  else from = Math.min(v.rendered, Math.max(0, len - TAIL_RECHECK)); // append + re-check a trailing window
  v.stale = false;
  while (v.el.childNodes.length > from) v.el.removeChild(v.el.lastChild as ChildNode);
  for (let i = from; i < len; i++) {
    // the previous TIMED event's epoch → lets renderEvent decide if the minute/day
    // advanced (untimed events like todo/queued are skipped so the chain holds)
    let prevEpoch: number | null = null;
    for (let j = i - 1; j >= 0; j--) { const e = eventEpoch(s.events[j]); if (e != null) { prevEpoch = e; break; } }
    v.el.appendChild(renderEvent(s.events[i], prevEpoch, turnWorkedSecs(s.events, i, working)));
  }
  v.rendered = len;
  return v;
}

// Compact-mode full rebuild: drop thinking, fold consecutive tool runs to a summary line, then walk
// the resulting display stream computing prevEpoch over IT (same rail-timestamp rules, applied after
// compaction — the user's requirement). prevEpoch is the previous TIMED display item's epoch.
function rebuildCompact(v: View, s: Session, working: boolean): void {
  while (v.el.firstChild) v.el.removeChild(v.el.firstChild);
  const disp = compactDisplay(s.events.map((e) => e.kind));
  let prevEpoch: number | null = null;
  const advance = (i: number) => { const ep = eventEpoch(s.events[i]); if (ep != null) prevEpoch = ep; };
  for (const item of disp) {
    if (item.kind === "toolgroup") {
      const first = s.events[item.indices[0]];
      const key = toolGroupKey(first);
      const tools = item.indices.map((i) => s.events[i]) as Extract<ChatEvent, { kind: "tool" }>[];
      const open = expandedGroups.has(key);
      v.el.appendChild(renderToolGroup(tools, prevEpoch, key, open));   // summary line (caret = collapse toggle)
      advance(item.indices[0]);
      if (open) {
        // expand to the full non-compact portion: the original contiguous span (tools + any thinking
        // between them), each rendered as its normal turn, with timestamps continuing the chain.
        const start = item.indices[0], end = item.indices[item.indices.length - 1];
        for (let i = start; i <= end; i++) {
          const child = renderEvent(s.events[i], prevEpoch, turnWorkedSecs(s.events, i, working));
          child.classList.add("tg-child");   // indented under the open arrow → clearly part of the group
          v.el.appendChild(child);
          advance(i);
        }
      }
    } else {
      v.el.appendChild(renderEvent(s.events[item.index], prevEpoch, turnWorkedSecs(s.events, item.index, working)));
      advance(item.index);
    }
  }
  v.rendered = s.events.length;
}

// Stable identity for a collapsed tool run (survives rebuilds) = the first tool's uuid (else its epoch).
function toolGroupKey(first: ChatEvent): string { return "tg:" + (first.uuid || String(eventEpoch(first) ?? "")); }

// A collapsed run of consecutive tool uses → one rail line: a caret + "3 Edits, 2 Reads" with each
// tool word bold (matching the non-compact .tool-name, so it reads AS tools). Clicking the line toggles
// expand → the full non-compact cards (the user 2026-06-14). Carries the rail dot + time-marker + hover
// wiring like any event so it anchors on the timeline; the dot is a green ✓ disc, red ✗ if any errored.
function renderToolGroup(tools: Extract<ChatEvent, { kind: "tool" }>[], prevEpoch: number | null, key: string, open: boolean): HTMLElement {
  const turn = el("div", "turn turn-toolgroup" + (open ? " expanded" : ""));
  const anyErr = tools.some((t) => t.isError);
  const d = dot(anyErr ? "ring" : "green");
  if (anyErr) d.classList.add("err");
  turn.appendChild(d);
  const line = el("div", "toolgroup-line");
  line.title = open ? "click to collapse" : "click to expand";
  const caret = el("span", "toolgroup-caret"); caret.textContent = open ? "▾" : "▸"; line.appendChild(caret);
  if (!open) {   // collapsed → the "3 Edits, 2 Reads" summary; expanded → just the open arrow (the cards say it)
    toolCounts(tools.map((t) => t.name)).forEach((c, i) => {
      line.appendChild(document.createTextNode((i ? ", " : " ") + c.count + " "));
      const w = el("span", "toolgroup-tool"); w.textContent = c.label; line.appendChild(w);   // bold, like .tool-name
    });
  }
  line.addEventListener("click", (e) => { e.stopPropagation(); toggleToolGroup(key); });
  turn.appendChild(line);
  const epoch = eventEpoch(tools[0]);
  const anchorUuid = tools[0].uuid ?? null;
  if (anchorUuid) turn.dataset.uuid = anchorUuid;
  if (epoch != null) turn.dataset.t = String(epoch);
  if (epoch != null) turn.insertBefore(timeMarker(epoch, prevEpoch ?? null), turn.firstChild);
  const railDot = turn.querySelector(".dot") as HTMLElement | null;
  if (anchorUuid || epoch != null) wireTurnHover(turn, railDot, anchorUuid, epoch ?? 0, tools[0].tlId ?? null);
  return turn;
}

// Toggle a collapsed tool run open/closed and repaint the active view in place (scroll preserved).
function toggleToolGroup(key: string): void {
  if (expandedGroups.has(key)) expandedGroups.delete(key); else expandedGroups.add(key);
  const content = document.getElementById("content");
  const top = content ? content.scrollTop : 0;
  if (activeId) syncView(activeId);
  if (content) content.scrollTop = top;
  scheduleRestamp();
}

// Re-render every view from scratch (used when a setting like compact flips): reset each view so the
// next syncView rebuilds it via the right path, then repaint the active one.
function rerenderAll(): void {
  for (const v of views.values()) { while (v.el.firstChild) v.el.removeChild(v.el.firstChild); v.rendered = 0; v.stale = false; }
  showActive();
}

// Index of the last human-prompt event = start of the current turn, where any
// in-place mutations (a tool's output arriving, etc.) live. 0 if none.
function lastTurnStart(events: ChatEvent[]): number {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].kind === "user") return i;
  return 0;
}

// If event i is the LAST reply of a COMPLETED prompt-turn, return the seconds the
// session worked on it (the turn's genuine prompt timestamp → this reply); else
// null. A turn is "completed" when a new GENUINE prompt follows it (injected
// user-role lines — postal pushes, /command stdout — are skipped, NOT treated as the
// next prompt), or it's the final turn and the session is no longer working (the
// live spinner owns the in-progress turn). Drives the "worked …" rail footer.
function turnWorkedSecs(events: ChatEvent[], i: number, working: boolean): number | null {
  const ev = events[i];
  if (ev.kind === "user") return null;                 // a prompt, not a reply
  let completed = false;
  for (let j = i + 1; j < events.length; j++) {
    const e = events[j];
    if (e.kind !== "user") return null;                // another reply in this turn → i isn't its last
    if (e.human) { completed = true; break; }          // next genuine prompt → the turn ended at i
    // injected user line (postal push, /command stdout, …) → same turn, keep scanning
  }
  if (!completed && working) return null;              // final turn still in progress → spinner owns it
  const end = eventEpoch(ev);
  if (end == null) return null;
  let start: number | null = null;
  for (let j = i; j >= 0; j--) { const e = events[j]; if (e.kind === "user" && e.human) { start = eventEpoch(e); break; } }
  if (start == null) return null;
  const secs = end - start;
  return secs > 0 ? secs : null;
}

// Show only the active session's (lazily built) view and set its scroll: a
// deep-link anchor wins; else stick to bottom on first show / if it was left at
// the bottom; else restore the saved position. Switching tabs never rebuilds —
// the cached DOM is just revealed.
// Tell the extension which tab is active, so it can publish it to the romp
// timeline (which outlines the open lane). activeId may be null (no session).
function notifyActive() {
  if (vscodeApi) vscodeApi.postMessage({ type: "activeTab", id: activeId });
}

// Move id to the front of the recency stack (most-recently-active).
function touchMru(id: string) {
  const i = mru.indexOf(id);
  if (i >= 0) mru.splice(i, 1);
  mru.unshift(id);
}

function showActive() {
  const content = document.getElementById("content");
  if (!content) return;
  notifyActive();
  renderLedger();  // swap in the active session's digest box (or hide if none)
  renderLiveAsk(); // swap in the active session's pending picker (or hide if none)
  let empty = document.getElementById("empty-state");
  const s = activeId ? sessions.get(activeId) : null;
  if (!s) {
    for (const v of views.values()) v.el.style.display = "none";
    if (!empty) {
      empty = el("div", "empty-state"); empty.id = "empty-state";
      empty.textContent = "No session open — click + to add one.";
      content.appendChild(empty);
    } else { empty.style.display = ""; }
    document.body.style.removeProperty("--active-accent"); // no session → neutral window border
    updateStatusline();
    return;
  }
  if (empty) empty.style.display = "none";
  // A closed (dead) session is READ-ONLY: disable the composer so a message can't be black-holed into
  // a session that no longer exists (the user 2026-06-16). Re-runs each push, so a session that dies
  // while you're viewing it disables the box live; switching back to a live tab re-enables it.
  const composer = document.getElementById("composer-input") as HTMLTextAreaElement | null;
  if (composer) {
    const closed = s.status.state === "closed";
    composer.disabled = closed;
    composer.placeholder = closed ? "Session closed — read-only" : "Message this session…  (⏎ send · ⇧⏎ newline)";
  }
  // tint the whole-window border with the active session's identity color
  if (s.color && s.color.bg) document.body.style.setProperty("--active-accent", s.color.bg);
  else document.body.style.removeProperty("--active-accent");
  touchMru(activeId!); // record activation order so close returns to the previous tab
  const v = syncView(activeId!);
  for (const [vid, vv] of views) vv.el.style.display = vid === activeId ? "" : "none";
  updateStatusline();
  const att = { anchor: pendingAnchor, t: pendingAnchorT, kind: pendingAnchorKind };   // this pass's landing attempt, for diagnostics
  if (att.anchor || att.t != null) landTrail = [];
  let scrolled = pendingAnchor ? scrollToAnchor(pendingAnchor) : false;
  // uuid anchor failed (or none) → time fallback; only then default scroll
  if (!scrolled && pendingAnchorT != null) { scrolled = scrollToNearestT(pendingAnchorT, pendingAnchorKind ?? undefined); }
  if (!scrolled) { pendingAnchor = null; pendingAnchorIntent = null; pendingAnchorT = null; pendingAnchorKind = null; } // give up, use default scroll
  else { pendingAnchorT = null; pendingAnchorKind = null; }
  // Diagnostics: log every landing attempt; surface the degraded ones. Toasts
  // only fire when a time target existed (att.t) — a stale pointer-upgrade
  // retry on a later tab switch has no target and must not cry wolf.
  if (att.anchor || att.t != null) {
    vscodeApi?.postMessage({
      type: "locateDiag", id: activeId, ok: scrolled, trail: landTrail.slice(),
      anchor: att.anchor ?? undefined, anchorT: att.t ?? undefined, kind: att.kind ?? undefined,
    });
    const near = landTrail.find((s) => s.startsWith("time-near-"));
    const nearSec = near ? parseInt(near.slice(10), 10) : NaN;
    if (att.t != null && !scrolled)
      landToast("couldn't find that moment in this conversation — showing the latest instead (logged)");
    else if (att.t != null && !landTrail.includes("pointer-exact") && (!near || nearSec > 120))
      landToast("the exact line is gone from this conversation's active path (rewound or compacted) — landed nearby (logged)");
  }
  if (!scrolled) {
    if (!v.shown || v.stick) content.scrollTop = content.scrollHeight;
    else content.scrollTop = v.scrollTop;
  }
  v.shown = true;
  scheduleRestamp();
}

// Live tail-append to the ACTIVE view, preserving stick-to-bottom.
function appendActive() {
  const content = document.getElementById("content");
  if (!content || !activeId) { showActive(); return; }
  const stick = nearBottom(content);
  syncView(activeId);
  updateStatusline();
  if (stick) content.scrollTop = content.scrollHeight;
  scheduleRestamp();
}

// Row heights change when the pane is resized (text re-wraps), so the spacing-based
// stamps must be recomputed against the new layout.
window.addEventListener("resize", scheduleRestamp);

// ---- ledger box (rolling per-session digest, just below the tabs) ----

function setLedger(id: string, ledger: Ledger | null) {
  ledgers.set(id, ledger);
  if (id === activeId) renderLedger();
}

function agehms(secs: number): string {
  secs = Math.max(0, Math.floor(secs));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

// The "(age)" label is colored by recency on the SHARED romp colormap (crameri
// "hawaii": dark-magenta → orange → olive → green → teal → pale-cyan), log age
// scale — these STOPS + age_rgb are kept identical to scripts/romp_colormap.py so
// the ledger matches the terminal `romp -f` feed. The bullet TEXT stays at default
// brightness; only the age label is colored.
const STOPS: Array<[number, number, number]> = [
  [140, 2, 115], [146, 46, 85], [151, 78, 62], [155, 111, 40], [156, 150, 28],
  [137, 189, 74], [107, 212, 142], [103, 233, 213], [179, 242, 253],
];
function ramp(v: number): [number, number, number] {
  v = Math.max(0, Math.min(1, v));
  const x = v * (STOPS.length - 1), i = Math.floor(x), fr = x - i;
  if (i >= STOPS.length - 1) return STOPS[STOPS.length - 1];
  const a = STOPS[i], b = STOPS[i + 1];
  return [Math.round(a[0] + (b[0] - a[0]) * fr), Math.round(a[1] + (b[1] - a[1]) * fr), Math.round(a[2] + (b[2] - a[2]) * fr)];
}
// recency → ramp position [0..1] (recent → 1, old → 0), shared log age scale.
function recencyV(ageSecs: number): number {
  const LO = 120, HI = 345600; // 2 min (brightest) .. 96 h (darkest) — matches romp_colormap.py FADE_HI
  const a = Math.max(LO, Math.min(HI, ageSecs));
  return 1.0 - (Math.log(a) - Math.log(LO)) / (Math.log(HI) - Math.log(LO));
}
function ageColor(ageSecs: number): string {
  const c = ramp(recencyV(ageSecs));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}
function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const l = (mx + mn) / 2;
  const s = d === 0 ? 0 : l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  if (d !== 0) {
    if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h, s, l];
}
function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) { const v = Math.round(l * 255); return [v, v, v]; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const hk = (t: number) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [Math.round(hk(h + 1 / 3) * 255), Math.round(hk(h) * 255), Math.round(hk(h - 1 / 3) * 255)];
}
// Recency for the ledger: take the shared hawaii ramp color (same hue progression
// as the terminal `romp -f` feed) but remap its LIGHTNESS into a legible band so
// no bullet drops into the unreadable dark-magenta the raw ramp produces at the
// old end. Brightness still carries recency as a secondary cue — recent bullets
// are bright, oldest ones fade darker/muted — but the fade is floored (~L0.50) so
// even the oldest stays readable on the dark panel. Hue carries recency too
// (magenta = old → cyan = recent).
function ageColorReadable(ageSecs: number): string {
  const v = recencyV(ageSecs);             // 0 = oldest, 1 = most recent
  const c = ramp(v);
  const [h, s] = rgbToHsl(c[0], c[1], c[2]);
  const L = 0.50 + 0.22 * v;               // oldest → 0.50 (faded), recent → 0.72 (bright)
  const S = Math.max(0.4, s) * (0.65 + 0.35 * v); // mute the old end a touch; full vividness when recent
  const o = hslToRgb(h, Math.min(1, S), L);
  return `rgb(${o[0]}, ${o[1]}, ${o[2]})`;
}

// How many bullets the ledger box renders. The box is a scroll-pane (~6 rows tall,
// see .ledger-bullets in styles.css) so the rest scroll into view (the user 2026-06-12).
// Matches the host's recentReplyBullets cap in state.ts.
const LEDGER_BULLET_CAP = 30;

// Collapse state for the ledger summary box (toggled from the tab bar, persisted
// per-panel via the webview state so it survives reloads).
let ledgerCollapsed = false;
try { ledgerCollapsed = !!((vscodeApi && vscodeApi.getState && vscodeApi.getState()) || {}).ledgerCollapsed; } catch { /* ignore */ }
// Per-node fold state for the ledger tree (the user 2026-06-16): a node folds by DEFAULT once it's done
// (a "previous" task) unless it's on the recent path; the user can override either way. Keyed by node id
// (ids are session-scoped, so the sets are safe to keep global across session switches).
const ledgerFolded = new Set<string>();    // explicitly folded by the user (overrides a default-open)
const ledgerExpanded = new Set<string>();  // explicitly expanded by the user (overrides a default-fold)
function toggleLedgerCollapsed() {
  ledgerCollapsed = !ledgerCollapsed;
  try { if (vscodeApi && vscodeApi.setState) vscodeApi.setState({ ...(vscodeApi.getState() || {}), ledgerCollapsed }); } catch { /* ignore */ }
  renderLedger();
  renderTabs(); // refresh the ▾/▸ glyph
}

// (Relevance categorization — colored labels + filter checkboxes — was removed
// from the ledger per the user; that lives in the FEED panel now. The ledger keeps
// the plain newest-first bullets, no "·", live-refresh.)
// A small dim section header inside the overview (goals / working on / done).
function ledgerLabel(text: string): HTMLElement {
  const lab = el("div", "ledger-label");
  lab.textContent = text;
  return lab;
}

function renderLedger() {
  const host = document.getElementById("ledger");
  if (!host) return;
  const l = activeId ? ledgers.get(activeId) : null;
  const tree = (l && l.tree) || [];
  const cur = (l && l.current) || null;
  const bullets = (l && l.bullets) || [];
  // Title is the archiver headline; fall back to the session name so the strip always has a label.
  const titleText = l ? (l.summary || (activeId ? (sessions.get(activeId)?.name || "") : "")) : "";
  const hasBody = !!(tree.length || cur || bullets.length);
  // Show the strip only once there's something REAL to show — a digest headline (l.summary) or any
  // body (goals / working-on / done). A brand-new session with nothing yet renders NOTHING: the bare
  // session-name fallback used to surface the strip as just a name + caret before anything had
  // happened, which the user found confusing (2026-06-16). The name fallback still LABELS the strip
  // once a body exists (an active session whose archiver hasn't titled it yet).
  if (!l || (!l.summary && !hasBody)) { host.replaceChildren(); host.style.display = "none"; (host as any)._sig = ""; return; }
  host.style.display = "";
  const now = Date.now() / 1000;
  // SAME content as last render (an interim host push, e.g. the session just worked) → DON'T tear the
  // rows down: that would drop an in-progress hover (the fresh row gets no mouseenter under a stationary
  // pointer). Only tick ages/colors in place. Collapse state is in the sig so a toggle forces a rebuild.
  // (raw n.t/b.t in the sig, NOT the elapsed — wall-clock ticking is refreshLedgerAges's job.)
  const sig = (ledgerCollapsed ? "C" : "O") + "§" + (activeId || "") + "§" + titleText
    + "‖cur:" + (cur ? `${cur.id || ""}:${cur.t ?? ""}:${cur.text}` : "")
    + "‖tree:" + tree.map((n) => `${n.id}:${n.depth}:${n.done ? "d" : ""}${n.derived ? "v" : ""}${n.cleared ? "x" : ""}${n.current ? "c" : ""}${n.blocked ? "b" : ""}${n.recent ? "r" : ""}${n.onpath ? "p" : ""}:${n.t ?? ""}:${n.text}`).join("|")
    + "‖fold:" + [...ledgerFolded].sort().join(",") + "/" + [...ledgerExpanded].sort().join(",")
    + "‖b:" + (tree.length ? "" : bullets.slice(0, LEDGER_BULLET_CAP).map((b) => `${b.id || ""}:${b.t ?? ""}:${b.text}`).join("|"));
  if ((host as any)._sig === sig) { refreshLedgerAges(host, l, now); return; }
  (host as any)._sig = sig;
  host.replaceChildren();

  // --- always-visible title strip: caret + headline; a click anywhere on it toggles the overview ---
  const head = el("div", "ledger-head");
  const caret = el("span", "ledger-caret");
  caret.textContent = ledgerCollapsed ? "▸" : "▾";
  const sum = el("div", "ledger-summary");
  sum.textContent = titleText;
  // Title hue tracks the freshest activity across the whole overview.
  const newestT = Math.max(cur && cur.t ? cur.t : 0, ...tree.map((n) => n.t || 0), ...bullets.map((b) => b.t || 0));
  if (newestT) sum.style.color = ageColorReadable(now - newestT);
  head.append(caret, sum);
  head.title = ledgerCollapsed ? "Show session overview" : "Hide session overview";
  head.addEventListener("click", toggleLedgerCollapsed);
  host.appendChild(head);
  if (ledgerCollapsed) return;   // collapsed → just the title strip

  if (tree.length) {
    // --- the goal-graph overview tree: a COLLAPSIBLE checklist (the user 2026-06-16). Toggle arrows at
    //     EVERY level; completed / cleared ("previous") nodes fold by default so only their top line
    //     shows, the recent path + open work stay expanded, and the user can fold/expand any node. ✓ disc
    //     = done (DIMMED for derived / cleared); ○ = not done; ▸ = working; ⏸ = blocked; → = freshest change.
    // A FLAT ledger (no node anywhere has children) has no carets to align under, so drop the disclosure
    // column entirely — otherwise every leaf reserves an empty spacer and the whole list reads as dead-
    // indented (the user 2026-06-16). Keep the column when ANY node is expandable, for alignment.
    const anyExpandable = tree.some((n) => !!(n.children && n.children.length));
    const wrap = el("div", "ledger-tree" + (anyExpandable ? "" : " flat"));
    const byId = new Map(tree.map((n) => [n.id, n] as const));
    const roots = tree.filter((n) => n.depth === 0);
    // Unfinished goals on top, finished (done/cleared) at the bottom; WITHIN each group, most recent
    // first — sorted by the node's own timestamp (the same value the "(Xm ago)" the row shows), so the
    // displayed times read monotonically instead of in the kernel's subtree-max order (the user 2026-06-16).
    const byRecency = (a: LedgerTreeNode, b: LedgerTreeNode) => (b.t || 0) - (a.t || 0);
    const orderedRoots = [
      ...roots.filter((r) => !r.done).sort(byRecency),
      ...roots.filter((r) => r.done).sort(byRecency),
    ];
    const defaultFold = (n: LedgerTreeNode) => !!n.done && !n.onpath;   // a "previous" task folds unless it's the recent path
    const isFolded = (n: LedgerTreeNode) => !!(n.children && n.children.length) &&
      (ledgerFolded.has(n.id) || (defaultFold(n) && !ledgerExpanded.has(n.id)));
    const renderNode = (n: LedgerTreeNode, depth: number) => {
      const expandable = !!(n.children && n.children.length);
      const folded = isFolded(n);
      const row = el("div", "ledger-tnode" + (depth === 0 ? " ledger-top" : "")
        + (n.current ? " current" : "") + (n.done ? " done" : "")
        + (n.blocked && !n.current && !n.done ? " blocked" : "")
        + ((n.derived || n.cleared) ? " derived" : "") + (n.recent ? " recent" : ""));
      row.style.paddingLeft = (4 + depth * 15) + "px";          // indent by graph depth (a line of descent)
      // disclosure triangle at every level (▶ folded / ▼ open); a blank spacer keeps leaves aligned
      const tri = el("span", "ledger-tri" + (expandable ? " nav" : " empty"));
      tri.textContent = expandable ? (folded ? "▶" : "▼") : "";
      if (expandable) tri.onclick = (ev) => {
        ev.stopPropagation();
        if (isFolded(n)) { ledgerExpanded.add(n.id); ledgerFolded.delete(n.id); }
        else { ledgerFolded.add(n.id); ledgerExpanded.delete(n.id); }
        renderLedger();
      };
      const mark = el("span", "ledger-tmark");
      // ✓ done, ⏸ blocked; not-done (○) and current are CSS-drawn discs (no glyph) so every mark is the
      // SAME 13px size (the user 2026-06-16). Current is a filled dot, NOT a ▸ triangle — the triangle
      // read as a clickable disclosure caret that didn't expand (the user 2026-06-16).
      mark.textContent = n.done ? "✓" : (n.blocked && !n.current) ? "⏸" : "";
      const txt = el("span", "ledger-ttext");
      txt.textContent = n.text;
      const time = el("span", "ledger-ttime");
      setTnodeTime(time, n, cur, now);                          // "(Xm)" live for current, "(Xm ago)" for done
      if (n.done && n.t) txt.style.color = ageColorReadable(now - n.t);   // a done item's text matches its time colour
      // a → "most recent change" arrow to the LEFT of the freshest node; the kernel flags it + its path
      // (onpath) so it stays auto-expanded even inside an otherwise-folded done branch.
      const lead: HTMLElement[] = [];
      if (n.recent) { const arr = el("span", "ledger-recent"); arr.textContent = "→"; arr.title = "most recent change"; lead.push(arr); }
      if (anyExpandable) lead.push(tri);                         // no caret column in a flat ledger (see anyExpandable)
      // click a row to jump to its chat turn — done/blocked land on the assistant turn that resolved it
      // (its mt), open goals on where they began (t). The caret's own onclick stops propagation, so
      // clicking it only folds (the user 2026-06-16). scrollToNearestT lands on the nearest turn.
      const navT = (n.done || n.blocked) ? (n.mt ?? n.t) : n.t;
      if (navT) {
        row.classList.add("nav");
        row.title = "jump to this in the chat";
        row.addEventListener("click", () => { scrollToNearestT(navT, "assistant"); });
      }
      row.append(...lead, mark, txt, time);
      wrap.appendChild(row);
      if (expandable && !folded) for (const cid of n.children!) { const c = byId.get(cid); if (c) renderNode(c, depth + 1); }
    };
    for (const r of orderedRoots) renderNode(r, 0);
    host.appendChild(wrap);
  } else {
    // --- fallback for goal-less sessions: the live "working on" line + the captioned "done" bullets ---
    if (cur && cur.text) {
      host.appendChild(ledgerLabel("working on"));
      const row = el("div", "ledger-current" + (cur.id ? " nav" : ""));
      row.textContent = cur.text + (cur.t ? `  (${agehms(now - cur.t)})` : "");
      if (cur.id) wireBulletNav(row, cur);
      host.appendChild(row);
    }
    if (bullets.length) {
      host.appendChild(ledgerLabel("done"));
      const list = el("div", "ledger-bullets");
      for (const b of bullets.slice(0, LEDGER_BULLET_CAP)) {
        const col = b.t ? ageColorReadable(now - b.t) : "";
        const row = el("div", "ledger-bullet" + (b.id ? " nav" : ""));
        const age = el("span", "ledger-bullet-age");
        age.textContent = b.t ? `${agehms(now - b.t)} ago` : "";
        if (col) age.style.color = col;
        const txt = el("span", "ledger-bullet-text");
        txt.textContent = b.text;
        if (col) txt.style.color = col;
        row.append(age, txt);
        if (b.id) wireBulletNav(row, b);
        list.appendChild(row);
      }
      host.appendChild(list);
    }
  }
}

// A tree node's right-side time: the CURRENT node shows its live elapsed "(Xm)" (how long it's been
// worked on, from the in-progress turn's start); a DONE node shows when it finished "(Xm ago)". Both
// recency-tinted. Open non-current nodes show nothing. Factored out so refreshLedgerAges ticks it too.
function setTnodeTime(time: HTMLElement, n: LedgerTreeNode, cur: LedgerBullet | null, now: number) {
  if (n.current && cur && cur.t) {
    time.textContent = `(${agehms(now - cur.t)})`; time.style.color = ageColorReadable(now - cur.t);
  } else if (n.done && n.t) {
    time.textContent = `(${agehms(now - n.t)} ago)`; time.style.color = ageColorReadable(now - n.t);
  } else {
    time.textContent = "";
  }
}

// Same-content tick: refresh the existing bullets' "Xm ago" ages + recency colors
// in place (rows kept alive so a hover/click survives). Order matches bullets[0..8).
function refreshLedgerAges(host: HTMLElement, l: Ledger, now: number) {
  const tree = l.tree || [];
  const bullets = l.bullets || [];
  // title hue tracks the freshest activity across the whole overview
  const newestT = Math.max(l.current && l.current.t ? l.current.t : 0,
    ...tree.map((n) => n.t || 0), ...bullets.map((b) => b.t || 0));
  const sum = host.querySelector(".ledger-summary") as HTMLElement | null;
  if (sum && newestT) sum.style.color = ageColorReadable(now - newestT);
  // tree node times ("(Xm)" live current + "(Xm ago)" done) tick with the wall clock
  host.querySelectorAll(".ledger-tnode").forEach((row, i) => {
    const n = tree[i]; const time = row.querySelector(".ledger-ttime") as HTMLElement | null;
    if (n && time) setTnodeTime(time, n, l.current || null, now);
    // keep a done item's text colour in step with its (recency-tinted) time as the clock ticks
    const txt = row.querySelector(".ledger-ttext") as HTMLElement | null;
    if (n && txt && n.done && n.t) txt.style.color = ageColorReadable(now - n.t);
  });
  // fallback bullets (goal-less sessions)
  const bs = bullets.slice(0, LEDGER_BULLET_CAP);
  host.querySelectorAll(".ledger-bullet").forEach((row, i) => {
    const b = bs[i]; if (!b) return;
    const col = b.t ? ageColorReadable(now - b.t) : "";
    const age = row.querySelector(".ledger-bullet-age") as HTMLElement | null;
    const txt = row.querySelector(".ledger-bullet-text") as HTMLElement | null;
    if (age) { age.textContent = b.t ? `${agehms(now - b.t)} ago` : ""; if (col) age.style.color = col; }
    if (txt && col) txt.style.color = col;
  });
}

// Wire a ledger bullet exactly like a feed row: hover (120ms intent debounce) →
// transient timeline highlight of the bullet's event; leave → clear; click →
// locate (the host pans the timeline + opens the chat at that turn). The host
// resolves b.id (the reply's romp-events id) → turn.
function wireBulletNav(row: HTMLElement, b: LedgerBullet) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  row.title = "jump to this on the timeline";
  row.addEventListener("mouseenter", () => {
    timer = setTimeout(() => { timer = undefined; vscodeApi?.postMessage({ type: "ledgerHover", id: b.id, tlId: b.tlId }); }, 120);
  });
  row.addEventListener("mouseleave", () => {
    if (timer) { clearTimeout(timer); timer = undefined; }
    vscodeApi?.postMessage({ type: "ledgerHover", id: null });
  });
  row.addEventListener("click", () => {
    vscodeApi?.postMessage({ type: "ledgerLocate", id: b.id, sid: b.sid, t: b.t });
  });
}

// ---- live "awaiting your input" widgets (structured: radio / checkbox / submit / text) ----

function setLiveAsk(id: string, ask: ParsedAsk | null) {
  liveAsks.set(id, ask);
  if (id === activeId) renderLiveAsk();
}
function clearLiveAsk(id: string) {
  if (liveAsks.delete(id) && id === activeId) renderLiveAsk();
}

let sendingTimer: ReturnType<typeof setTimeout> | undefined;
// Local UI highlight for the single-select card (↑/↓); the actual selection is the
// delta send on confirm. Keyed so incidental re-posts of the same prompt keep it.
let liveAskFocus = 0;
let liveAskFocusKey = "";

// Render the widget matching the active session's pending prompt; it takes over
// the message box. single → radio rows, multi → checkboxes + Submit/Cancel,
// submit → review + action buttons, null → free-text input.
function renderLiveAsk() {
  const host = document.getElementById("live-ask");
  const footer = document.getElementById("footer");
  if (!host) return;
  host.replaceChildren();
  host.classList.remove("sending");
  if (sendingTimer) { clearTimeout(sendingTimer); sendingTimer = undefined; }
  sendingGuard = false; // a fresh render = the previous action resolved; re-enable
  const cur = activeId ? liveAsks.get(activeId) : undefined;
  if (cur) liveTextValue = ""; // leaving the free-text field (a structured screen is up)
  if (!activeId || !liveAsks.has(activeId)) {
    host.style.display = "none";
    liveTextValue = "";
    if (footer) footer.style.display = ""; // restore the message box
    return;
  }
  host.style.display = "";
  if (footer) footer.style.display = "none"; // the prompt takes over the message box
  const ask = liveAsks.get(activeId) ?? null;
  if (!ask) renderUnknownCard();
  else if (ask.kind === "multi") renderMultiCard(ask);
  else if (ask.kind === "submit") renderSubmitCard(ask);
  else renderSingleCard(ask);
  if (ask?.preview) appendPreview(host, ask.preview);
}

// The focused option's side-by-side preview box, reproduced VERBATIM in a monospace
// block (the user 2026-06-13). The TUI draws it to the RIGHT of the options; the
// chat rail is narrow, so it sits BELOW the card and scrolls sideways if wider than
// the rail. Re-rendered on every re-post, so it tracks the cursor exactly — moving
// between options swaps the picture, mirroring the terminal. textContent, never
// innerHTML: the pane text is untrusted terminal output.
function appendPreview(host: HTMLElement, preview: string) {
  const card = (host.querySelector(".ask-card") as HTMLElement | null) ?? host;
  const pre = el("pre", "ask-preview");
  pre.textContent = preview;
  card.appendChild(pre);
}

function askCard(extraClass = ""): HTMLElement {
  const card = el("div", "ask-card ask-live" + (extraClass ? " " + extraClass : ""));
  document.getElementById("live-ask")!.appendChild(card);
  return card;
}
function qline(card: HTMLElement, text?: string) {
  if (text) { const qt = el("div", "ask-qtext"); qt.textContent = text; card.appendChild(qt); }
}

// The pickable rows of a single-select card — the TUI's "Type something." /
// "Chat about this" chrome rows are driven by dedicated UI instead (the inline
// custom field / nothing). Falls back to everything rather than render zero rows.
function singleOptions(ask: ParsedAsk) {
  const real = ask.options.filter((o) => !isMetaOption(o.label));
  return real.length ? real : ask.options;
}

// SINGLE-select: clickable radio rows; ↑/↓ highlight, Enter/number confirm.
// Also each question tab of the multi-QUESTION wizard (Enter picks + advances);
// its "Type something." slot is driven by the inline custom-answer field.
function renderSingleCard(ask: ParsedAsk) {
  const card = askCard();
  qline(card, ask.question || ask.header);
  const opts = singleOptions(ask);
  const key = (activeId || "") + "§" + opts.map((o) => `${o.n}:${o.label}`).join("|");
  if (key !== liveAskFocusKey) { liveAskFocusKey = key; const sel = opts.findIndex((o) => o.selected); liveAskFocus = sel >= 0 ? sel : 0; }
  liveAskFocus = Math.max(0, Math.min(liveAskFocus, opts.length - 1));
  opts.forEach((o, i) => {
    const row = el("div", "ask-live-opt" + (i === liveAskFocus ? " focus" : ""));
    const lab = el("span", "ask-optlabel"); lab.textContent = `${o.n}. ${o.label}`; row.appendChild(lab);
    if (o.desc) { const d = el("span", "ask-optdesc"); d.textContent = o.desc; row.appendChild(d); }
    row.addEventListener("click", () => answerLiveAsk(o.n));
    row.addEventListener("mousemove", () => { if (liveAskFocus !== i) { liveAskFocus = i; paintLiveAskFocus(); } });
    card.appendChild(row);
  });
  if (ask.options.some((o) => isTypeSomething(o.label))) {
    const row = el("div", "ask-custom");
    const plus = el("span", "ask-custom-plus"); plus.textContent = "+"; row.appendChild(plus);
    const inp = document.createElement("input");
    inp.type = "text"; inp.className = "ask-custom-input"; inp.placeholder = "add your own answer…";
    inp.value = liveTextValue;
    inp.addEventListener("input", () => { liveTextValue = inp.value; });
    // stop ALL keys from bubbling to onSingleKey (digits would jump-confirm rows)
    inp.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); const v = inp.value.trim(); if (v) addCustomLiveAsk(v); }
    });
    wirePasteFallback(inp);
    row.appendChild(inp);
    card.appendChild(row);
  }
  card.tabIndex = 0;
  card.addEventListener("keydown", onSingleKey);
  card.focus({ preventScroll: true });
}

// "Type something" is the inline free-text slot (handled by the +custom field);
// "Chat about this" / "Submit" are TUI chrome, not selectable answers.
function isTypeSomething(label: string): boolean { return /^\s*type something/i.test(label); }
function isMetaOption(label: string): boolean { return /^\s*(type something|chat about|submit$)/i.test(label.trim()); }

// MULTI-select: a real checkbox per real option, an inline "add your own" field
// (drives the TUI's Type-something slot), and Submit / Cancel buttons.
function renderMultiCard(ask: ParsedAsk) {
  const card = askCard("ask-live-multi");
  qline(card, ask.question || ask.header);
  // A custom answer that's already been typed shows up as a normal checked option
  // (its label is the text, no longer "Type something"), so it renders as a checkbox.
  for (const o of ask.options) {
    if (o.checked === undefined || isMetaOption(o.label)) continue;
    const row = el("label", "ask-check");
    const box = document.createElement("input"); box.type = "checkbox"; box.checked = !!o.checked;
    box.addEventListener("change", () => toggleLiveAsk(o.n));
    row.appendChild(box);
    const lab = el("span", "ask-optlabel"); lab.textContent = o.label; row.appendChild(lab);
    if (o.desc && o.desc.toLowerCase() !== "submit") { const d = el("span", "ask-optdesc"); d.textContent = o.desc; row.appendChild(d); }
    card.appendChild(row);
  }
  // Inline custom-answer field — only while the TUI still offers a Type-something slot.
  if (ask.options.some((o) => isTypeSomething(o.label))) {
    const row = el("div", "ask-custom");
    const plus = el("span", "ask-custom-plus"); plus.textContent = "+"; row.appendChild(plus);
    const inp = document.createElement("input");
    inp.type = "text"; inp.className = "ask-custom-input"; inp.placeholder = "add your own answer…";
    inp.value = liveTextValue;
    inp.addEventListener("input", () => { liveTextValue = inp.value; });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); const v = inp.value.trim(); if (v) addCustomLiveAsk(v); } });
    wirePasteFallback(inp);
    row.appendChild(inp);
    card.appendChild(row);
  }
  const actions = el("div", "ask-actions");
  const submit = el("button", "ask-btn ask-btn-primary"); submit.textContent = "Submit"; submit.addEventListener("click", () => submitLiveAsk()); actions.appendChild(submit);
  const cancel = el("button", "ask-btn"); cancel.textContent = "Cancel"; cancel.addEventListener("click", () => cancelLiveAsk()); actions.appendChild(cancel);
  card.appendChild(actions);
}

// Review screen: show chosen answers + the Submit answers / Cancel options as
// buttons (each is just an option pick, reusing answerLiveAsk). A multi-question
// wizard reviews every question→answer pair here; a single question keeps the
// flat "Selected: …" line.
function renderSubmitCard(ask: ParsedAsk) {
  const card = askCard("ask-live-submit");
  if (ask.pairs && ask.pairs.length > 1) {
    qline(card, "Review your answers");
    for (const p of ask.pairs) {
      const row = el("div", "ask-pair");
      if (p.q) { const q = el("div", "ask-pair-q"); q.textContent = p.q; row.appendChild(q); }
      const a = el("div", "ask-pair-a"); a.textContent = "→ " + (p.a || "(no answer)"); row.appendChild(a);
      card.appendChild(row);
    }
  } else {
    qline(card, ask.question);
    const chosen = el("div", "ask-chosen");
    chosen.textContent = ask.chosen && ask.chosen.length ? "Selected: " + ask.chosen.join(", ") : "(nothing selected)";
    card.appendChild(chosen);
  }
  const actions = el("div", "ask-actions");
  for (const o of ask.options) {
    const b = el("button", "ask-btn" + (/submit/i.test(o.label) ? " ask-btn-primary" : ""));
    b.textContent = o.label;
    b.addEventListener("click", () => answerLiveAsk(o.n));
    actions.appendChild(b);
  }
  card.appendChild(actions);
}

// Free-text (any unstructured awaiting screen): a text input. The value is held
// in liveTextValue so a re-render (re-mirror) doesn't wipe what's been typed.
let liveTextValue = "";

// Paste fallback. In the VS Code webview, native Cmd+V reliably reaches the
// composer textarea but NOT these dynamically-created fields — typing works,
// the paste event simply never fires (the user's report, 2026-06-11). On
// Cmd/Ctrl+V: give native paste ~150ms to land (a paste event disarms the
// fallback — e.g. in the browser, where it just works), then ask the HOST for
// vscode.env.clipboard text ("readClipboard" → "clipboardText") and insert it
// at the cursor ourselves.
let pasteTarget: HTMLInputElement | HTMLTextAreaElement | null = null;
let pasteArm = 0;
function wirePasteFallback(inp: HTMLInputElement | HTMLTextAreaElement) {
  inp.addEventListener("paste", () => { pasteArm++; }); // native worked — disarm any pending fallback
  inp.addEventListener("keydown", (ev) => {
    const e = ev as KeyboardEvent; // union element type degrades the overload to plain Event
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.key.toLowerCase() !== "v") return;
    const arm = ++pasteArm;
    setTimeout(() => {
      if (pasteArm !== arm) return; // a real paste event landed in the meantime
      pasteTarget = inp;
      vscodeApi?.postMessage({ type: "readClipboard" });
    }, 150);
  });
}
function insertClipboardText(text: string) {
  const inp = pasteTarget;
  pasteTarget = null;
  if (!inp || !text || !document.contains(inp)) return;
  const s = inp.selectionStart ?? inp.value.length;
  const t = inp.selectionEnd ?? s;
  inp.value = inp.value.slice(0, s) + text + inp.value.slice(t);
  const pos = s + text.length;
  try { inp.setSelectionRange(pos, pos); } catch { /* ignore */ }
  inp.dispatchEvent(new Event("input", { bubbles: true })); // keep liveTextValue/draft sync
  inp.focus();
}
// Safeguard: the session is awaiting input but the parser can't map the screen to
// a known widget (an unrecognized prompt, a free-text editor, etc.). Warn loudly
// so a prompt is never silently missed — and offer a best-effort text input in
// case it IS a plain text prompt.
function renderUnknownCard() {
  const card = askCard("ask-live-unknown");
  const warn = el("div", "ask-warn");
  warn.textContent = "⚠ Waiting on a prompt the panel can’t read — answer it in the terminal.";
  card.appendChild(warn);
  const input = document.createElement("input");
  input.type = "text"; input.className = "ask-text-input"; input.placeholder = "…or, if it’s a text prompt, type here + Enter";
  input.value = liveTextValue;
  input.addEventListener("input", () => { liveTextValue = input.value; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); const v = input.value.trim(); if (v) sendTextLiveAsk(v); }
  });
  wirePasteFallback(input);
  card.appendChild(input);
  const len = input.value.length; try { input.setSelectionRange(len, len); } catch { /* ignore */ }
}

function paintLiveAskFocus() {
  const rows = document.querySelectorAll("#live-ask .ask-live-opt");
  rows.forEach((r, i) => r.classList.toggle("focus", i === liveAskFocus));
}

// Single-select keyboard: ↑/↓ highlight, Enter confirms, number jumps to + confirms.
function onSingleKey(e: KeyboardEvent) {
  const ask = activeId ? liveAsks.get(activeId) : null;
  if (!ask || ask.kind !== "single") return;
  const opts = singleOptions(ask); // same rows the card renders
  const n = opts.length;
  if (e.key === "ArrowDown") { e.preventDefault(); liveAskFocus = (liveAskFocus + 1) % n; paintLiveAskFocus(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); liveAskFocus = (liveAskFocus - 1 + n) % n; paintLiveAskFocus(); }
  else if (e.key === "Enter") { e.preventDefault(); answerLiveAsk(opts[liveAskFocus].n); }
  else if (/^[1-9]$/.test(e.key)) {
    const idx = opts.findIndex((o) => o.n === parseInt(e.key, 10));
    if (idx >= 0) { liveAskFocus = idx; answerLiveAsk(opts[idx].n); }
  }
}

// One terminal-bound action in flight at a time (prevents double-submit); a short
// safety un-dim re-enables the card if a click aborted host-side (no-op) instead
// of hanging dimmed. Reset on every re-render (a new screen = the action resolved).
let sendingGuard = false;
function dimSending() {
  const host = document.getElementById("live-ask");
  if (!host) return;
  sendingGuard = true;
  host.classList.add("sending");
  if (sendingTimer) clearTimeout(sendingTimer);
  sendingTimer = setTimeout(() => { host.classList.remove("sending"); sendingTimer = undefined; sendingGuard = false; }, 700);
}
function answerLiveAsk(target: number) {
  if (!activeId || sendingGuard) return;
  if (vscodeApi) vscodeApi.postMessage({ type: "answerAsk", id: activeId, target });
  dimSending();
}
function toggleLiveAsk(target: number) { // optimistic; host toggles + re-mirrors. NOT guarded — rapid toggles allowed.
  if (activeId && vscodeApi) vscodeApi.postMessage({ type: "toggleAsk", id: activeId, target });
}
function addCustomLiveAsk(text: string) { // fills the TUI's Type-something slot inline; re-mirror shows it as a checked option
  if (activeId && vscodeApi) vscodeApi.postMessage({ type: "addCustomAsk", id: activeId, text });
  liveTextValue = "";
}
function submitLiveAsk() {
  if (!activeId || sendingGuard) return;
  if (vscodeApi) vscodeApi.postMessage({ type: "submitAsk", id: activeId });
  dimSending();
}
function cancelLiveAsk() {
  if (!activeId || sendingGuard) return;
  if (vscodeApi) vscodeApi.postMessage({ type: "cancelAsk", id: activeId });
  dimSending();
}
function sendTextLiveAsk(text: string) {
  if (!activeId || sendingGuard) return;
  if (vscodeApi) vscodeApi.postMessage({ type: "askText", id: activeId, text });
  liveTextValue = "";
  dimSending();
}

// Animated Claude-Code-style "working" line (sparkle + rotating gerund).
function elapsedMs(sinceMs: number | null): string {
  if (!sinceMs) return "";
  const s = Math.max(0, Math.floor((Date.now() - sinceMs) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Right side of the status line: "Opus 4.8 xhigh" (model + effort) — the context %
// is shown separately as a battery bar (ctxBar). Sourced from the @claude-model /
// @claude-effort / @claude-context tmux vars. Shown in EVERY state, not just working.
// Each value is a little dropdown: picking an entry has the host inject the matching
// /model or /effort slash command into the session's pane; the label then updates
// when the TUI's statusline republishes the tmux vars (meta-pending bridges the gap).
type MetaKind = "model" | "effort";
const MODEL_CHOICES: { label: string; value: string }[] = [
  { label: "Fable", value: "fable" },
  { label: "Opus", value: "opus" },
  { label: "Sonnet", value: "sonnet" },
  { label: "Haiku", value: "haiku" },
  { label: "Default", value: "default" },
];
const EFFORT_CHOICES: { label: string; value: string }[] =
  ["low", "medium", "high", "xhigh", "max"].map((v) => ({ label: v, value: v }));

// Is this menu entry the session's current value? Effort matches exactly; the
// model var holds a display name ("Opus 4.8"), so match on the leading word.
function isCurrentMeta(kind: MetaKind, st: Status, value: string): boolean {
  if (kind === "effort") return (st.effort || "").toLowerCase() === value;
  return (st.model || "").toLowerCase().startsWith(value);
}

// "<sessionId>:<kind>" → set when the user picks a value, cleared when the tmux
// var actually changes (or after 20s, if the TUI rejected/ignored the command).
const metaPending = new Map<string, { was: string; until: number }>();
function isMetaPending(kind: MetaKind, st: Status): boolean {
  if (!activeId) return false;
  const key = `${activeId}:${kind}`;
  const p = metaPending.get(key);
  if (!p) return false;
  const cur = (kind === "model" ? st.model : st.effort) || "";
  if (cur !== p.was || Date.now() > p.until) { metaPending.delete(key); return false; }
  return true;
}

function metaButton(kind: MetaKind, text: string): HTMLElement {
  const btn = el("span", "meta-btn");
  btn.dataset.kind = kind;
  const label = el("span", "meta-label");
  label.textContent = text;
  btn.appendChild(label);
  const caret = el("span", "meta-caret");
  caret.textContent = "▾";
  btn.appendChild(caret);
  btn.title = kind === "model" ? "change model (sends /model)" : "change thinking effort (sends /effort)";
  btn.addEventListener("click", (e) => { e.stopPropagation(); toggleMetaMenu(kind, btn); });
  return btn;
}

// Build or refresh the model/effort buttons inside #spinner-meta. Called from
// updateStatusline (fresh container) and the 1s ticker (label refresh in place).
function syncMetaControls(meta: HTMLElement, st: Status) {
  const want = [st.model ? "model" : "", st.effort ? "effort" : ""].filter(Boolean).join();
  const btns = Array.from(meta.querySelectorAll(".meta-btn")) as HTMLElement[];
  if (btns.map((b) => b.dataset.kind).join() !== want) {
    meta.replaceChildren();
    if (st.model) meta.appendChild(metaButton("model", st.model));
    if (st.effort) meta.appendChild(metaButton("effort", st.effort));
  }
  for (const b of Array.from(meta.querySelectorAll(".meta-btn")) as HTMLElement[]) {
    const kind = b.dataset.kind as MetaKind;
    const cur = (kind === "model" ? st.model : st.effort) || "";
    const label = b.querySelector(".meta-label") as HTMLElement | null;
    if (label && label.textContent !== cur) label.textContent = cur;
    b.classList.toggle("meta-pending", isMetaPending(kind, st));
  }
}

let metaMenuEl: HTMLElement | null = null;
function closeMetaMenu() {
  metaMenuEl?.remove();
  metaMenuEl = null;
}
function toggleMetaMenu(kind: MetaKind, btn: HTMLElement) {
  const wasOpen = metaMenuEl?.dataset.kind === kind;
  closeMetaMenu();
  if (wasOpen) return;
  const s = activeId ? sessions.get(activeId) : null;
  if (!s) return;
  // a pending permission/picker prompt owns the pane's keyboard — injecting a
  // slash command there would answer the prompt instead (host guards this too)
  if (s.status.state === "awaiting") return;
  const menu = el("div", "meta-menu");
  menu.dataset.kind = kind;
  for (const c of kind === "model" ? MODEL_CHOICES : EFFORT_CHOICES) {
    const item = el("div", "meta-item" + (isCurrentMeta(kind, s.status, c.value) ? " current" : ""));
    item.textContent = c.label;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      if (activeId && vscodeApi) {
        vscodeApi.postMessage({ type: kind === "model" ? "setModel" : "setEffort", id: activeId, value: c.value });
        const was = (kind === "model" ? s.status.model : s.status.effort) || "";
        metaPending.set(`${activeId}:${kind}`, { was, until: Date.now() + 20_000 });
        btn.classList.add("meta-pending");
      }
      closeMetaMenu();
    });
    menu.appendChild(item);
  }
  document.body.appendChild(menu);
  // anchored ABOVE the button (the statusline sits at the bottom of the panel)
  const r = btn.getBoundingClientRect();
  menu.style.right = Math.max(8, window.innerWidth - r.right) + "px";
  menu.style.bottom = (window.innerHeight - r.top + 6) + "px";
  metaMenuEl = menu;
}
document.addEventListener("click", () => closeMetaMenu());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMetaMenu(); });

// Context "battery": a small bar that FILLS with the context-used %, recolors as it
// fills (green → amber → red), with the % written inside. Replaces the plain "40%".
// CLICK → /compact the session, same as the timeline's battery click.
function ctxBar(): HTMLElement {
  const bar = el("span", "ctx-bar"); bar.id = "ctx-bar";
  bar.appendChild(el("span", "ctx-fill"));
  bar.appendChild(el("span", "ctx-text"));
  bar.appendChild(el("span", "ctx-scan"));   // compacting: teal rectangle whose right edge compresses leftward (as on the timeline)
  bar.addEventListener("click", () => {
    const s = activeId ? sessions.get(activeId) : null;
    if (!s || !vscodeApi) return;
    // awaiting: the pane's keyboard belongs to the prompt; compacting/closed: nothing to do
    if (s.status.state === "awaiting" || s.status.state === "compacting" || s.status.state === "closed") return;
    vscodeApi.postMessage({ type: "compactSession", id: activeId });
    bar.classList.add("ctx-clicked");   // immediate cue; the real compacting state takes over via the poll
  });
  return bar;
}
function setCtxBar(bar: HTMLElement, ctxStr: string | undefined, compacting = false) {
  // Compacting: hide the fill/% (the number is about to be wrong anyway) and run
  // the scanning bar instead, mirroring the timeline's battery. No ctx% needed.
  bar.classList.toggle("ctx-compacting", compacting);
  if (compacting) {
    bar.classList.remove("ctx-clicked");   // the click's pulse cue did its job
    bar.style.display = "";
    bar.title = "compacting context…";
    return;
  }
  if (!ctxStr) { bar.style.display = "none"; return; }
  bar.style.display = "";
  const pct = Math.max(0, Math.min(100, parseInt(ctxStr, 10) || 0));
  const fill = bar.querySelector(".ctx-fill") as HTMLElement | null;
  const txt = bar.querySelector(".ctx-text") as HTMLElement | null;
  if (fill) { fill.style.width = pct + "%"; fill.style.background = pct >= 85 ? "#c0392b" : pct >= 60 ? "#e0b020" : "#54B204"; }
  if (txt) txt.textContent = pct + "%";
  bar.title = `context ${pct}% used — click to /compact`;
}

const CHIP_LABEL: Record<ChipState, string> = {
  working: "WORKING", subagent: "SUBAGENT", ready: "READY", awaiting: "BLOCKED",
  idle: "IDLE", closed: "CLOSED", compacting: "COMPACTING", blocked: "API ERROR",
};

function updateStatusline() {
  const sl = document.getElementById("statusline");
  const s = activeId ? sessions.get(activeId) : null;
  if (!sl || !s) return;
  sl.replaceChildren();
  // Left: the state chip — WORKING gets a sine color-pulse + elapsed timer; idle
  // states get the plain chip (no timer). Right: model + effort · ctx%, always.
  if (s.status.state === "working") {
    // pill bg stays on the chip; the gradient text-clip lives on an inner span
    // (background-clip:text on the chip itself would erase the pill background)
    const chip = el("span", "chip chip-working");
    const label = el("span", "chip-pulse");
    label.textContent = CHIP_LABEL.working;
    chip.appendChild(label);
    sl.appendChild(chip);
    const timer = el("span", "status-timer");
    timer.id = "work-timer";
    timer.textContent = elapsedMs(s.status.sinceEpoch);
    sl.appendChild(timer);
  } else if (s.status.state === "compacting") {
    const c = el("span", "compacting-line");
    c.textContent = "⟳ Compacting context…";
    sl.appendChild(c);
  } else {
    const chip = el("span", `chip chip-${s.status.state}`);
    chip.textContent = CHIP_LABEL[s.status.state] ?? s.status.state.toUpperCase();
    sl.appendChild(chip);
  }
  // ADDITIVE orange SUBAGENT chip: a quiet session (ready/idle) with a background subagent still running —
  // the signal explaining why a seemingly-idle session is doing work. A working session hides it (it's
  // already obviously busy). (the user 2026-06-16, re-spec from #9.)
  if (s.status.subagent != null && (s.status.state === "ready" || s.status.state === "idle")) {
    const sub = el("span", "chip chip-subagent");
    sub.textContent = "SUBAGENT";
    sub.title = s.status.subagent ? `a subagent is running in the background: ${s.status.subagent}` : "a subagent is running in the background";
    sl.appendChild(sub);
  }
  const meta = el("span", "spinner-meta");
  meta.id = "spinner-meta";
  syncMetaControls(meta, s.status);
  sl.appendChild(meta);
  const bar = ctxBar();
  setCtxBar(bar, s.status.ctx, s.status.state === "compacting");
  sl.appendChild(bar);
}

// Unsent composer text, per session — a draft belongs to the tab it was typed
// in: switching away stashes it (the box empties for the new tab's own draft),
// switching back restores it.
const drafts = new Map<string, string>();

function setActive(id: string, anchor?: string, anchorT?: number, anchorKind?: string) {
  if (activeId === id && anchor == null && anchorT == null) return; // already active, nothing to do
  closeMetaMenu(); // an open model/effort menu targets the tab we're leaving
  pendingAnchorT = anchorT ?? null;
  pendingAnchorKind = anchorKind ?? null;
  // Remember where we were in the tab we're leaving, so we can restore it.
  const content = document.getElementById("content");
  if (content && activeId && activeId !== id) {
    const cur = views.get(activeId);
    if (cur) { cur.scrollTop = content.scrollTop; cur.stick = nearBottom(content); }
  }
  // Stash the leaving tab's draft; show the entering tab's own (usually empty).
  const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null;
  if (ta && activeId !== id) {
    if (activeId) {
      if (ta.value) drafts.set(activeId, ta.value); else drafts.delete(activeId);
    }
    ta.value = drafts.get(id) ?? "";
    growComposer(ta);
  }
  pendingAnchor = anchor ?? null;
  pendingAnchorIntent = anchor ? (anchorKind ?? null) : null;
  activeId = id;
  try { vscodeApi?.setState?.({ ...(vscodeApi.getState?.() || {}), activeId: id }); } catch { /* ignore */ }
  sortTabs(); // re-sort on switch — applies any tier change deferred while a tab was active
  renderTabs();
  showActive();
}

function cycleTab(dir: number) {
  if (order.length < 2 || !activeId) return;
  const i = order.indexOf(activeId);
  if (i < 0) return;
  setActive(order[(i + dir + order.length) % order.length]);
}

// First event carrying a uuid — a stable identity for "which transcript is this".
// A fork (the tab re-pointed onto a new transcript) changes it; more turns on the
// same transcript keep it.
function firstUuid(events: ChatEvent[]): string | null {
  for (const e of events) if (e.uuid) return e.uuid;
  return null;
}

function upsert(msg: any) {
  const existed = sessions.has(msg.id);
  const prev = sessions.get(msg.id);
  const s: Session = {
    id: msg.id,
    name: msg.name,
    color: msg.color || null,
    events: msg.events || (prev ? prev.events : []),
    status: msg.status || (prev ? prev.status : { state: "idle", sinceEpoch: null }),
    firstSeen: msg.firstSeen ?? (prev ? prev.firstSeen : undefined),
  };
  sessions.set(msg.id, s);
  // The kernel re-sends the FULL "session" payload on every push. Distinguish an APPEND (more turns
  // on the SAME transcript — the common case) from a FORK (the tab re-pointed onto a NEW transcript,
  // events replaced wholesale, e.g. a /clear-style fork). Only a FORK drops the cached DOM and
  // rebuilds; an append lets syncView add just the new turns AND keeps the user's scroll position —
  // so new content no longer snaps the view to the bottom (the user 2026-06-15). Fork = the
  // transcript identity (first event's uuid) changed; an append keeps it.
  const forked = !!(existed && msg.events && prev && prev.events.length && msg.events.length
                    && firstUuid(msg.events) !== firstUuid(prev.events));
  if (forked) {
    const v = views.get(msg.id);
    if (v) { v.el.remove(); views.delete(msg.id); }
  }
  if ("ledger" in msg) ledgers.set(msg.id, msg.ledger ?? null);
  if (!existed) order.push(msg.id);
  if (!activeId) activeId = msg.id;
  if (wantActive && msg.id === wantActive) { wantActive = null; setActive(msg.id); }   // restore persisted tab on arrival
  sortTabs();
  renderTabs();
  // Active tab: a content refresh appends + preserves scroll (appendActive); a new tab or a fork
  // lands at the bottom/anchor (showActive). This is what keeps new pushes from snapping to bottom.
  if (msg.id === activeId) { if (existed && !forked) appendActive(); else showActive(); }
  // A non-active session's view is left to sync lazily when it's next shown.
  // The session the user just created has arrived → drop the "Opening…" cue and
  // focus its fresh tab (the whole point of opening it).
  if (!existed && pendingNewSession && msg.name === pendingNewSession) {
    hideOpeningModal();
    setActive(msg.id);
  }
}

function update(msg: any) {
  const s = sessions.get(msg.id);
  if (!s) return;
  s.events = msg.events || s.events;
  s.status = msg.status || s.status;
  if (msg.id !== activeId) sortTabs(); // re-sort on a non-active tier change; defer the active tab so it won't jump mid-read
  renderTabs();
  if (msg.id === activeId) {
    appendActive();
    renderLedger(); // refresh the summary box (ages + any new items) as the active session works
  } else {
    const v = views.get(msg.id);
    if (v) v.stale = true; // re-render its current turn when it's next shown
  }
}

function statusOnly(msg: any) {
  const s = sessions.get(msg.id);
  if (!s) return;
  s.status = msg.status || s.status;
  if (msg.id !== activeId) sortTabs(); // tier change on a non-active tab can re-order; active tab deferred
  renderTabs();
  if (msg.id === activeId) updateStatusline();
}

window.addEventListener("message", (e: MessageEvent) => {
  const m = e.data;
  if (!m) return;
  if (m.type === "session") upsert(m);
  else if (m.type === "update") update(m);
  else if (m.type === "status") statusOnly(m);
  else if (m.type === "focus") setActive(m.id, m.anchor, typeof m.anchorT === "number" ? m.anchorT : undefined, typeof m.anchorKind === "string" ? m.anchorKind : undefined);
  else if (m.type === "nextTab") cycleTab(1);
  else if (m.type === "prevTab") cycleTab(-1);
  else if (m.type === "sessionList") renderPicker(m.items || []);
  else if (m.type === "openPicker") openPicker(!!m.pick, m.prompt, !!m.allowNew);
  // The host asks US to confirm (in-page, no native dialogs): ending a live
  // session on tab-close, and reviving a dead one on open.
  else if (m.type === "confirmClose" && m.id) {
    const nm = String(m.name || "");
    showConfirm(`End “${nm}”?`,
      "“Close tab” just removes it from this panel and leaves the session running. “End session” shuts it down (the transcript stays on disk).",
      [{ label: "Close tab", value: "close" }, { label: "End session", value: "end", danger: true }, { label: "Cancel", value: "" }],
      (v) => {
        if (v === "close") vscodeApi?.postMessage({ type: "closeTab", id: m.id });
        // End session = shut it down AND remove the tab (the user 2026-06-16: an explicitly-ended session
        // shouldn't linger as a struck-through read-only tab — that's only for sessions that die on their
        // own). closeTab must durably dismiss it so the death event doesn't re-add the struck tab.
        else if (v === "end") { vscodeApi?.postMessage({ type: "endSession", id: m.id }); vscodeApi?.postMessage({ type: "closeTab", id: m.id }); }
      });
  }
  else if (m.type === "confirmRevive" && m.id) {
    const nm = String(m.name || "");
    showConfirm(`“${nm}” is closed — revive it?`,
      "Revive restarts the session and resumes its conversation. Read-only just shows the transcript.",
      [{ label: "Revive", value: "revive" }, { label: "View read-only", value: "ro" }, { label: "Cancel", value: "" }],
      (v) => {
        if (v === "revive") vscodeApi?.postMessage({ type: "reviveSession", id: m.id });
        else if (v === "ro") vscodeApi?.postMessage({ type: "viewReadOnly", id: m.id });
      });
  }
  else if (m.type === "focusComposer") { const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null; ta?.focus(); }
  else if (m.type === "glowTurns") applyGlow(Array.isArray(m.groups) ? m.groups : [], Array.isArray(m.mids) ? m.mids : []);
  else if (m.type === "askLive") setLiveAsk(m.id, m.ask ?? null);
  else if (m.type === "askLiveClear") clearLiveAsk(m.id);
  else if (m.type === "clipboardText") insertClipboardText(String(m.text ?? ""));
  else if (m.type === "ledger") setLedger(m.id, m.ledger ?? null);
  else if (m.type === "working") { workingSet = new Set(Array.isArray(m.names) ? m.names : []); refreshPostalDots(); }
  else if (m.type === "imgData" && typeof m.path === "string") onImgData(m.path, typeof m.url === "string" ? m.url : null);
  else if (m.type === "tabOrder") applyTabOrder(m.order);
  else if (m.type === "renamed" && m.id && typeof m.name === "string") {
    const s = sessions.get(m.id);
    if (s && s.name !== m.name) { s.name = m.name; renderTabs(); }
  }
  else if (m.type === "droppedPath" && typeof m.path === "string") insertComposerText(m.path);
  else if (m.type === "closed") {
    sessions.delete(m.id);
    liveAsks.delete(m.id);
    ledgers.delete(m.id);
    drafts.delete(m.id);
    const v = views.get(m.id);
    if (v) { v.el.remove(); views.delete(m.id); }
    const oi = order.indexOf(m.id); if (oi >= 0) order.splice(oi, 1);
    const mi = mru.indexOf(m.id); if (mi >= 0) mru.splice(mi, 1);
    sortTabs();
    renderTabs();
    if (activeId === m.id) {
      activeId = mru[0] || null; // MRU: return to the previously-active tab, not the positional neighbor
      const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null;
      if (ta) { ta.value = (activeId && drafts.get(activeId)) || ""; growComposer(ta); }
      showActive();
    }
  }
});

// Tick the working timer (the chip color-pulse is pure CSS) and keep the model/ctx
// meta fresh as status updates land.
setInterval(() => {
  const s = activeId ? sessions.get(activeId) : null;
  if (!s) return;
  if (s.status.state === "working") {
    const timer = document.getElementById("work-timer");
    if (timer) timer.textContent = elapsedMs(s.status.sinceEpoch);
    else updateStatusline();
  }
  const meta = document.getElementById("spinner-meta");
  if (meta) syncMetaControls(meta, s.status);
  const bar = document.getElementById("ctx-bar");
  if (bar) setCtxBar(bar, s.status.ctx, s.status.state === "compacting");
}, 1000);

// the last message we delivered per session — so a Ctrl+C interrupt can put it back
// in the box, mirroring Claude Code (which restores the in-flight prompt on Esc).
const lastSent = new Map<string, string>();
let interruptFlashT: number | undefined;
function flashInterrupted(ta: HTMLTextAreaElement) {
  ta.classList.add("interrupted-flash");
  if (interruptFlashT) window.clearTimeout(interruptFlashT);
  interruptFlashT = window.setTimeout(() => ta.classList.remove("interrupted-flash"), 650);
}
function growComposer(ta: HTMLTextAreaElement) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
}

// Composer: Enter sends the message to the active session as its next prompt,
// Shift+Enter inserts a newline; the box auto-grows a few lines.
function setupComposer() {
  const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null;
  if (!ta) return;
  ta.addEventListener("keydown", (e) => {
    // Ctrl+C = terminal-style interrupt of the active session (Control, not Cmd — on
    // macOS copy is Cmd+C, so this never collides with copy). The host sends Esc to
    // the pane; here we mirror Claude Code's UI: flash a cue, and drop the just-sent
    // prompt back into the (empty) box so you can edit and resend.
    if (e.ctrlKey && !e.metaKey && (e.key === "c" || e.key === "C")) {
      e.preventDefault();
      if (!activeId || !vscodeApi) return;
      vscodeApi.postMessage({ type: "interrupt", id: activeId });
      const restore = lastSent.get(activeId);
      if (restore && !ta.value.trim()) { ta.value = restore; growComposer(ta); }
      lastSent.delete(activeId);
      flashInterrupted(ta);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = ta.value.trim();
      if (!text || !activeId) return;
      lastSent.set(activeId, text);   // remembered for a possible Ctrl+C restore
      if (vscodeApi) vscodeApi.postMessage({ type: "sendMessage", id: activeId, text });
      drafts.delete(activeId);        // sent — no draft to restore on a later switch-back
      ta.value = "";
      ta.style.height = "";
    }
  });
  ta.addEventListener("input", () => growComposer(ta));

  // Drag a file onto the box → insert its PATH at the cursor. NOTE: VS Code's
  // workbench drop overlay captures plain external file drags over any editor
  // group ("drop to open", which is why a bare drop opened the PNG) before the
  // webview sees them — hold SHIFT while dropping to suppress the overlay and
  // hand the drop here. Pasting (below) is overlay-free and covers the same
  // need. Best path source first: File.path (Electron, when exposed), then
  // text/uri-list file:// entries (explorer drags), else the bytes go to the
  // host, which saves them and posts the saved path back ("droppedPath") —
  // sandboxed webviews expose NO filesystem path for OS drags, only content.
  ta.addEventListener("dragover", (e) => {
    e.preventDefault(); e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    ta.classList.add("drop-target");
  });
  ta.addEventListener("dragleave", () => ta.classList.remove("drop-target"));
  ta.addEventListener("drop", (e) => {
    e.preventDefault(); e.stopPropagation();
    ta.classList.remove("drop-target");
    const dt = e.dataTransfer;
    if (!dt) return;
    const uris = (dt.getData("text/uri-list") || "").split(/\r?\n/).filter((u) => u && !u.startsWith("#"));
    const fromUri = (u: string) => insertComposerText(decodeURIComponent(u.replace(/^file:\/\//, "")));
    const files = Array.from(dt.files || []);
    if (!files.length) { for (const u of uris) if (u.startsWith("file://")) fromUri(u); return; }
    files.forEach((f, i) => {
      const p = (f as any).path as string | undefined;
      if (p) { insertComposerText(p); return; }
      if (uris[i] && uris[i].startsWith("file://")) { fromUri(uris[i]); return; }
      shipFileToHost(f);
    });
  });

  // Cmd+V a copied file (Finder "Copy") or a clipboard screenshot → insert its
  // path, same pipeline as drops. Plain text pastes have no files on the
  // clipboard and keep the default behavior.
  ta.addEventListener("paste", (e) => {
    const files = Array.from(e.clipboardData?.files || []);
    if (!files.length) return;
    e.preventDefault();
    files.forEach((f) => {
      const p = (f as any).path as string | undefined;
      if (p) insertComposerText(p);
      else shipFileToHost(f);
    });
  });
  wirePasteFallback(ta); // belt-and-braces: native paste disarms it, so no double-insert

  // The bulletproof path: 📎 asks the host to run a native open dialog (no
  // workbench drop overlay to fight) and the picked path comes back as
  // droppedPath → insertComposerText. Mousedown (not click) so the textarea
  // keeps focus and the path lands at the existing cursor.
  const attach = document.getElementById("composer-attach") as HTMLButtonElement | null;
  attach?.addEventListener("mousedown", (e) => {
    e.preventDefault();
    vscodeApi?.postMessage({ type: "pickFile" });
  });
}

// No filesystem path available for a dropped/pasted file → ship the bytes to
// the host, which saves them under ~/.local/state/romp/drops/ and posts back
// {type:"droppedPath", path} for insertion.
function shipFileToHost(f: File) {
  if (f.size > 50 * 1024 * 1024) return;   // too big to ship over postMessage
  const reader = new FileReader();
  reader.onload = () => {
    const b64 = String(reader.result || "").split(",")[1] || "";
    if (b64 && vscodeApi) vscodeApi.postMessage({ type: "dropFile", name: f.name || "pasted.png", b64 });
  };
  reader.readAsDataURL(f);
}

// Insert text into the composer at the cursor, with whitespace separation on
// both sides so a dropped path never fuses with surrounding words.
function insertComposerText(text: string) {
  const ta = document.getElementById("composer-input") as HTMLTextAreaElement | null;
  if (!ta || !text) return;
  const s = ta.selectionStart ?? ta.value.length, epos = ta.selectionEnd ?? ta.value.length;
  const before = ta.value.slice(0, s), after = ta.value.slice(epos);
  const sep = before && !/\s$/.test(before) ? " " : "";
  ta.value = before + sep + text + (after && !/^\s/.test(after) ? " " : "") + after;
  const pos = (before + sep + text).length;
  ta.selectionStart = ta.selectionEnd = Math.min(pos, ta.value.length);
  growComposer(ta);
  ta.focus();
}

// ---- settings: the gear + modal live on the TIMELINE now (the user 2026-06-14). The chat just
// CONSUMES the shared 'romp:settings' (compact mode) — applying a change made there, in a same-origin
// tab, live via the storage event; and reading it at startup. ----
function setupSettings(): void {
  onExternalSettingsChange((s) => { settings = s; rerenderAll(); });
}

setupComposer();
setupSettings();
// right-click a selection in the transcript → Reply (quote it) / Copy
document.getElementById("content")?.addEventListener("contextmenu", showSelectionMenu);
if (vscodeApi) vscodeApi.postMessage({ type: "ready" });
