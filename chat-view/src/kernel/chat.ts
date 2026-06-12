// Per-session chat mirroring: incremental transcript parsing, status chips,
// ledgers, and live-picker mirroring/driving. Ported from
// chat-view/src/extension.ts, with all substrate access behind SessionBackend.
import * as fs from "fs";
import * as path from "path";
import { newIncParser, feed, buildParsed, type IncParser, type ParsedTranscript, type ChatEvent } from "../transcript";
import { hydratePostal } from "../postal-spec";
import { parseAskPane, type ParsedAsk } from "../askparse";
import type { SessionBackend, SessionState } from "./backend";
import { ChipColor, ROMP_STATE, rompMeta, colorForName } from "./state";

export type ChipState = "working" | "ready" | "awaiting" | "idle" | "closed" | "compacting";

export interface Session {
  id: string;
  file: string;
  name: string;
  color: ChipColor | null;
  lastSig: string;
  lastSince: number | null;
  lastState: ChipState | "";
  lastWorking: boolean;
  watcher?: fs.FSWatcher;
  debounce?: NodeJS.Timeout;
  closedTicks?: number;
  keepOpen?: boolean;
  addedAt?: number;
  workingSince?: number | null;
  parser?: IncParser;
  offset?: number;
  askSig?: string;
  ledgerSig?: string;
  firstSeen?: number;
  lastMetaSig?: string;         // model|effort|ctx|faded last pushed — a reopened/revived session's
                                // substrate vars land AFTER the tab opens, with no state change to ride on
  askComposerTicks?: number;    // consecutive composer-screen ticks while awaiting — heals a hookless
                                // picker's stranded "permission" state after it's answered
}

export function chipState(name: string, states: Map<string, SessionState> | null, working: boolean): ChipState {
  // Only trust the probe when it actually returned sessions — an empty map is
  // unreliable; don't mass-mark everything closed.
  if (states && states.size > 0) {
    const info = states.get(name);
    if (!info) return "closed";
    if (info.state === "working") return "working";
    if (info.state === "permission") return "awaiting";
    if (info.state === "compacting") return "compacting";
    return "ready";
  }
  return working ? "working" : "ready";
}

export function fadedFor(name: string, states: Map<string, SessionState> | null): boolean {
  if (!states || states.size === 0) return false;
  const info = states.get(name);
  if (!info) return true; // closed
  if (info.state === "working" || info.state === "permission" || info.state === "compacting") return false;
  const since = parseInt(info.since, 10);
  if (!since) return false;
  return Date.now() / 1000 - since > 3600; // idle > 1h
}

function sinceMsOf(name: string, states: Map<string, SessionState> | null, fallback: number | null): number | null {
  const raw = states ? states.get(name)?.since : undefined;
  const s = raw ? parseInt(raw, 10) : 0;
  return s ? s * 1000 : fallback;
}

// Frozen start of the current working burst (the spinner's clock survives tool
// boundaries); cleared when the turn finishes.
export function workingSinceMs(s: Session, state: ChipState, states: Map<string, SessionState> | null, fallback: number | null): number | null {
  if (state === "working") {
    if (s.workingSince == null) s.workingSince = sinceMsOf(s.name, states, fallback);
    return s.workingSince;
  }
  if (state !== "awaiting" && state !== "compacting") s.workingSince = null;
  return s.workingSince ?? null;
}

// The displayed-meta dedupe key (pairs with Session.lastMetaSig): every status
// post carries these four, so every post site should stamp it.
export function metaSigOf(name: string, states: Map<string, SessionState> | null): string {
  const i = states?.get(name);
  return [i?.model || "", i?.effort || "", i?.ctx || "", fadedFor(name, states)].join("|");
}

// An interrupt that lands BEFORE the first response token makes the TUI pop the
// prompt back into the composer and drop the turn from its conversation — but
// the user line already hit the transcript, and NOTHING marks the restore
// (verified 2026-06-11: the line just sits as the leaf until the next submit
// orphans it). Mirror the TUI: hide a trailing typed user turn once the session
// is back at rest. Not for working/compacting (a reply is coming), and not for
// closed (history should stand whole). The age guard rides out the
// submit→UserPromptSubmit-hook lag, so a just-sent prompt whose state still
// reads "waiting" is never hidden.
export const RESTED = new Set<ChipState>(["ready", "idle", "awaiting"]);
export function filterInterrupted(events: ChatEvent[], state: ChipState): ChatEvent[] {
  if (!RESTED.has(state)) return events;
  for (let i = events.length - 1; i >= 0; i--) {
    const e: any = events[i];
    if (e.kind === "queued" || e.kind === "todo") continue;   // trailing fixtures, not the turn itself
    if (e.kind === "user" && e.human && e.md && e.ts && Date.now() - Date.parse(e.ts) > 2500)
      return events.slice(0, i).concat(events.slice(i + 1));
    break;
  }
  return events;
}

export function statusPayload(s: Session, state: ChipState, states: Map<string, SessionState> | null, sinceFallback: number | null) {
  return {
    state,
    sinceEpoch: workingSinceMs(s, state, states, sinceFallback),
    effort: states?.get(s.name)?.effort || undefined,
    model: states?.get(s.name)?.model || undefined,
    ctx: states?.get(s.name)?.ctx || undefined,
    faded: fadedFor(s.name, states),
  };
}

export function sig(file: string): string {
  try { const st = fs.statSync(file); return `${st.size}:${st.mtimeMs}`; }
  catch { return ""; }
}

export function firstSeenOf(s: Session): number {
  if (s.firstSeen != null) return s.firstSeen;
  let ms = 0;
  try {
    const fd = fs.openSync(s.file, "r");
    const buf = Buffer.alloc(65536);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    const firstLine = buf.toString("utf8", 0, n).split("\n").find((l) => l.trim());
    const ts = firstLine ? JSON.parse(firstLine)?.timestamp : null;
    const parsed = ts ? Date.parse(ts) : NaN;
    if (!isNaN(parsed)) ms = parsed;
  } catch { /* fall back to file time */ }
  if (!ms) { try { const st = fs.statSync(s.file); ms = st.birthtimeMs || st.mtimeMs || 0; } catch { /* 0 */ } }
  s.firstSeen = ms;
  return ms;
}

// /clear (and a resume) forks the conversation to a NEW transcript uuid in the
// same project dir, stamped with the SAME customTitle — the old file stops
// growing forever. These two helpers let a tab follow its session across forks,
// using the daemon's fork-grouping rule (romp-summarize-backfill
// custom_title()/sessions()): a transcript belongs to session <name> iff its
// head carries a {"type":"custom-title","customTitle":<name>} line.

const titleCache = new Map<string, { key: string; title: string | null }>();
export function customTitleOf(file: string): string | null {
  let st: fs.Stats;
  try { st = fs.statSync(file); } catch { return null; }
  const key = `${st.size}:${st.mtimeMs}`;
  const hit = titleCache.get(file);
  if (hit && hit.key === key) return hit.title;
  let title: string | null = null;
  try {
    const fd = fs.openSync(file, "r");
    const buf = Buffer.alloc(65536);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    for (const line of buf.toString("utf8", 0, n).split("\n")) {
      if (!line.includes("custom-title")) continue;
      try {
        const o = JSON.parse(line);
        if (o?.type === "custom-title" && o.customTitle) { title = String(o.customTitle); break; }
      } catch { /* keep scanning the head */ }
    }
  } catch { /* unreadable → no title */ }
  titleCache.set(file, { key, title });
  return title;
}

// The newest transcript in s's project dir carrying s's customTitle; s.file
// when no strictly-newer sibling matches (ties keep the current file — no
// churn). The name-fallback case (no romp identity, name = uuid prefix) never
// matches a real customTitle, so such tabs stay pinned.
export function liveTranscriptOf(s: Session): string {
  let bestM: number;
  try { bestM = fs.statSync(s.file).mtimeMs; } catch { bestM = -1; }
  const dir = path.dirname(s.file);
  let best = s.file;
  let names: string[];
  try { names = fs.readdirSync(dir); } catch { return s.file; }
  for (const n of names) {
    if (!n.endsWith(".jsonl") || n.startsWith("agent-")) continue;   // subagent transcripts: never a session fork
    const f = path.join(dir, n);
    if (f === s.file) continue;
    let m: number;
    try { m = fs.statSync(f).mtimeMs; } catch { continue; }
    if (m <= bestM) continue;
    if (customTitleOf(f) !== s.name) continue;
    best = f; bestM = m;
  }
  return best;
}

// Incremental read: feed only the bytes appended since last time; full re-read
// on truncation/replacement or any parse error.
export function readParsedSession(s: Session): ParsedTranscript | null {
  let size: number;
  try { size = fs.statSync(s.file).size; } catch { return null; }
  if (size === 0) return null;
  try {
    if (!s.parser || (s.offset ?? 0) > size) {
      s.parser = newIncParser();
      s.offset = 0;
    }
    const from = s.offset ?? 0;
    if (size > from) {
      const fd = fs.openSync(s.file, "r");
      try {
        const len = size - from;
        const buf = Buffer.allocUnsafe(len);
        let got = 0;
        while (got < len) {
          const n = fs.readSync(fd, buf, got, len - got, from + got);
          if (n <= 0) break;
          got += n;
        }
        feed(s.parser, got === len ? buf : buf.subarray(0, got));
        s.offset = from + got;
      } finally { fs.closeSync(fd); }
    }
    const p = buildParsed(s.parser);
    p.events = hydratePostal(p.events, ROMP_STATE(), {
      byId: (id) => rompMeta(id).color,
      byName: colorForName,
    });
    return p;
  } catch (e) {
    console.error("romp-kernel: failed to parse transcript", s.file, e);
    s.parser = undefined;
    s.offset = 0;
    return null;
  }
}

// ---- live picker mirroring + driving (TUI backends only) ----

// The Claude Code composer (idle/working), NOT a pending prompt.
export function isComposerScreen(pane: string): boolean {
  return /⏵⏵|shift\s*\+\s*tab to cycle|auto mode (on|off)|\bctx:\s*\d+%/.test(pane);
}

type ParsedAskResult = ParsedAsk | null;

export class AskDriver {
  constructor(private backend: SessionBackend) {}

  private capture(name: string): string {
    return this.backend.tui ? this.backend.tui.capturePane(name) : "";
  }

  private keySeq(name: string, keys: string[]) {
    this.backend.tui?.sendKeys(name, keys);
  }

  parse(name: string): ParsedAskResult {
    try { return parseAskPane(this.capture(name)); } catch { return null; }
  }

  // The live-ask payload for an awaiting session: the parsed picker, "TEXT"
  // (free-text prompt), or null meaning "show the normal composer".
  liveAsk(name: string): { ask: ParsedAsk | null; sig: string } | null {
    if (!this.backend.tui) return null;
    const pane = this.capture(name);
    const parsed = parseAskPane(pane);
    if (!parsed && (!pane.trim() || isComposerScreen(pane))) return null;
    return { ask: parsed, sig: parsed ? parsed.sig : "TEXT" };
  }

  // Poll the pane until ready(parsed), then act — confirms a screen transition
  // landed before firing an action key.
  private whenReady(name: string, ready: (p: ParsedAskResult) => boolean, act: () => void, tries = 8, gap = 80) {
    const step = (left: number) => {
      const p = this.parse(name);
      if (ready(p)) { act(); return; }
      if (left > 0) setTimeout(() => step(left - 1), gap);
    };
    step(tries);
  }

  // Navigate ONE arrow key at a time, re-confirming the cursor after each press
  // (the TUI drops rapidly-batched arrows). Aborts if the screen changes kind.
  private stepNavTo(name: string, target: number, kindOk: (p: ParsedAskResult) => boolean, act: () => void, budget = 16) {
    const p = this.parse(name);
    if (!p || !kindOk(p)) return;
    if (budget <= 0) return;
    if (!p.cursorFound) { setTimeout(() => this.stepNavTo(name, target, kindOk, act, budget - 1), 110); return; }
    if (p.cursor === target) { act(); return; }
    this.keySeq(name, [p.cursor < target ? "Down" : "Up"]);
    setTimeout(() => this.stepNavTo(name, target, kindOk, act, budget - 1), 110);
  }

  // Single-select pick (and the submit-review screen's Submit/Cancel choice).
  answer(name: string, target: number) {
    const parsed = this.parse(name);
    if (!parsed || parsed.kind === "multi" || !parsed.cursorFound) return;
    this.stepNavTo(name, target, (p) => !!p && p.kind !== "multi", () => this.keySeq(name, ["Enter"]));
  }

  // Multi-select: toggle the target option.
  toggle(name: string, target: number) {
    const parsed = this.parse(name);
    if (!parsed || parsed.kind !== "multi" || !parsed.cursorFound) return;
    this.stepNavTo(name, target, (p) => !!p && p.kind === "multi", () => this.keySeq(name, ["Space"]));
  }

  // Multi-select submit: cross to the Submit tab, wait for the review screen,
  // land on "Submit answers", Enter.
  submit(name: string) {
    const parsed = this.parse(name);
    if (!parsed) return;
    const commit = () => {
      const p = this.parse(name);
      if (!p || p.kind !== "submit") return;
      const sub = p.options.find((o) => /submit\b/i.test(o.label)) || p.options[0];
      this.stepNavTo(name, sub.n, (q) => !!q && q.kind === "submit", () => this.keySeq(name, ["Enter"]));
    };
    if (parsed.kind === "multi") {
      // Park the cursor on the FIRST option (a plain checkbox row) before
      // crossing tabs — on the "Type something" row, Right edits text instead.
      const first = parsed.options[0]?.n ?? 1;
      this.stepNavTo(name, first, (p) => !!p && p.kind === "multi", () => {
        this.keySeq(name, ["Right"]);
        this.whenReady(name, (p) => !!p && p.kind === "submit", commit);
      });
    } else if (parsed.kind === "submit") {
      commit();
    }
  }

  // Custom answer via the "Type something" slot: navigate to it, type. Multi:
  // Enter (commits, toggles OFF) + Space (re-checks it). Single (incl. each tab
  // of the multi-question wizard): Enter alone commits it as the answer.
  // Mirrors extension.ts addCustomAsk — keep the two in sync.
  addCustom(name: string, text: string) {
    if (!text.trim()) return;
    const parsed = this.parse(name);
    if (!parsed || parsed.kind === "submit") return;
    const slot = parsed.options.find((o) => /^\s*type something/i.test(o.label));
    if (!slot) return;
    const kind = parsed.kind;
    this.stepNavTo(name, slot.n, (p) => !!p && p.kind === kind, () => {
      this.backend.tui?.sendLiteral(name, text);
      setTimeout(() => this.keySeq(name, ["Enter"]), 170);
      if (kind === "multi") setTimeout(() => this.keySeq(name, ["Space"]), 350);
    });
  }

  cancel(name: string) {
    this.keySeq(name, ["Escape"]);
  }

  // Free-text answer ("Type something."): type the text, then Enter.
  sendText(name: string, text: string) {
    if (!text) return;
    this.backend.tui?.sendLiteral(name, text);
    setTimeout(() => this.keySeq(name, ["Enter"]), 120);
  }
}

// askLive pushes are change-gated on the kernel-side askSig, so a client that
// connects AFTER a prompt appeared never hears about it — the kernel believes
// "already sent" and the prompt stays invisible to that client until it changes
// (a reload made a blocked session's permission prompt vanish in both front
// ends, 2026-06-12). On client ready, compute the replay set: every session
// with a pending prompt — hook-confirmed awaiting, OR an already-signed
// hookless picker (askSig set while the chip reads ready/idle). Targeted at
// the connecting client only: a broadcast would re-render peers' live-ask
// widgets and wipe a half-typed free-text answer.
// The uuid anchor a kernel-side chat locate should carry for the events-cache
// event a click resolved to. The 60c811c rework made feed work-row locates
// TIME-ONLY — every click landed "near" (typically a tool block) instead of
// pointer-exact, and looked broken (the user's report, 2026-06-12). Prompt-intent
// clicks land on the turn's own (user) line; work-intent on the readable reply,
// falling back to the prompt line — an INTERRUPTED slice has no reply to land on.
export function chatAnchorFor(
  ev: { uuid?: string | null; replyUuid?: string | null } | null,
  kind?: "user",
): string | undefined {
  if (!ev) return undefined;
  const a = kind === "user" ? ev.uuid : (ev.replyUuid || ev.uuid);
  return a || undefined;
}

export function pendingAskReplays(
  sessions: Iterable<Session>,
  states: Map<string, SessionState> | null,
  asker: Pick<AskDriver, "liveAsk">,
): Array<{ id: string; ask: ParsedAsk | null }> {
  const out: Array<{ id: string; ask: ParsedAsk | null }> = [];
  for (const s of sessions) {
    if (!s.askSig && chipState(s.name, states, s.lastWorking) !== "awaiting") continue;
    const live = asker.liveAsk(s.name);   // re-parse the pane: the pane IS the truth
    if (live) out.push({ id: s.id, ask: live.ask });
  }
  return out;
}
