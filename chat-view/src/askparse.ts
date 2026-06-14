// Parse the Claude Code selection picker out of a captured tmux pane.
//
// A pending AskUserQuestion (and tool-permission) prompt lives ONLY in the TUI's
// on-screen state — Claude Code does not write it to the transcript JSONL until
// it's answered. So the chat view, which mirrors the transcript, is structurally
// blind to it; we capture the pane (`tmux capture-pane -p`) and parse the picker.
//
// The picker is a small state machine (verified empirically against the TUI):
//
//  • SINGLE-select — standard footer; rows `❯ N. label`; ↑/↓ move, Enter picks.
//        ☐ Header
//        Which option do you want to pick?
//        ❯ 1. Option A
//             desc…
//          2. Option B
//        Enter to select · ↑/↓ to navigate · Esc to cancel        ← footer
//
//  • MULTI-select selection screen ("Multi-pick" tab) — standard footer; a tab
//    bar `←  ☒ Header  ✔ Submit  →`; rows carry a checkbox `❯ N. [✔]/[ ] label`;
//    Space OR Enter TOGGLES the highlighted row; → crosses to the Submit tab.
//
//  • MULTI-select submit/review screen ("Submit" tab) — NO footer;
//        ←  ☒ Header  ✔ Submit  →
//        Review your answers
//         ● Which question?
//           → Pizza, Sushi          ← chosen
//        Ready to submit your answers?
//        ❯ 1. Submit answers        ← Enter on row 1 commits
//          2. Cancel
//
//  • MULTI-QUESTION wizard (AskUserQuestion with several questions) — one ☐/☒
//    tab per question plus ✔ Submit (`←  ☐ Color  ☐ Size  ✔ Submit  →`); each
//    question screen is a SINGLE-select (Enter picks and advances; typing on
//    the "Type something." row edits it inline, Enter commits it as that
//    question's answer), unless the question is multiSelect — then its rows
//    carry [✔]/[ ] checkboxes. So a Submit tab bar does NOT imply
//    multi-select; only checkbox rows do. Its review screen lists EVERY
//    `● question / → answer` pair. (Verified empirically, 2026-06-11.)
//
// Other awaiting screens (the free-text "type something" field, etc.) parse to
// null; the webview shows a plain text input for those.

export interface AskOption {
  n: number;            // 1-based ordinal AS THE TUI NUMBERS IT — equals its arrow-nav position
  label: string;
  desc?: string;
  selected: boolean;    // the ❯ cursor is currently on this row
  checked?: boolean;    // multi-select checkbox state ([✔]/[ ]); undefined for non-checkbox rows
}

export type AskKind = "single" | "multi" | "submit";

export interface ParsedAsk {
  kind: AskKind;
  header?: string;      // the ☐ chip / tab-bar name
  question?: string;
  options: AskOption[];
  cursor: number;       // n of the ❯ row (defaults to the first option)
  cursorFound: boolean; // false when no ❯ was detected — capture unreliable, don't send blind keys
  chosen?: string[];    // submit screen: the answers under review (all questions, flattened)
  pairs?: { q: string; a: string }[]; // submit screen: every ● question / → answer pair, in order
  multiSelect: boolean; // back-compat: kind === "multi"
  preview?: string;     // the side-by-side preview box (verbatim monospace text, with its border) the
                        // focused option draws to the RIGHT of the option list — undefined when none.
                        // It changes as the cursor moves (a re-capture re-posts it), so the card mirrors
                        // exactly what the TUI shows. (the user 2026-06-13)
  sig: string;          // change-signature, so the host only re-posts when it actually changed
}

const OPT_RE = /^\s*(❯)?\s*(\d+)\.\s+(.*\S)\s*$/;          // ❯? N. label  (checkbox, if any, lives inside the label)
const CHECK_RE = /^\[\s*([^\]]?)\s*\]\s*(.*)$/;             // [✔] label  /  [ ] label
const RULE_RE = /^\s*[─-]{3,}.*$/;
const HEADER_RE = /^\s*[☐☑▣▢]\s+(.+?)\s*$/;
const FOOTER_RE = /to navigate|Enter to select|Esc to (cancel|exit)/;
// The normal composer/status footer (mirrors extension.ts isComposerScreen) —
// its presence anywhere means the pane is at the message box, NOT a pending
// footer-less confirmation (PATH C below).
const COMPOSER_RE = /⏵⏵|shift\s*\+\s*tab to cycle|auto mode (on|off)|\bctx:\s*\d+%/;

// Side-by-side preview (an AskUserQuestion whose options carry a `preview`):
// Claude Code lays the option list on the LEFT and a bordered preview box on the
// RIGHT, on the SAME pane rows. Capturing that pane glues the box's text onto
// every option row, so OPT_RE (greedy to EOL) swallows the preview INTO the
// label and the box-only rows fall into the previous option's description — the
// card renders as garbled noise. We detect the box's left-border column and clip
// every row there before parsing, so only the left (option) column survives.
// Match VERTICAL and CORNER box glyphs ONLY — never horizontals (─━═) or the
// em/en dashes that legitimately appear inside a diagram.
const BOX_EDGE_RE = /[│┃┆┇┊┋╎╏║▏▕╭╮╯╰┌┐┘└┏┓┛┗╔╗╝╚├┤┣┫╠╣]/;

function isOpt(line: string): boolean { return OPT_RE.test(line); }
function isRule(line: string): boolean { return RULE_RE.test(line); }
function isBlank(line: string): boolean { return line.trim() === ""; }
function isIndented(line: string): boolean { return /^\s/.test(line) && line.trim() !== ""; }
// The `←  ☒ Header  ✔ Submit  →` tab bar (multi-select AND the multi-question wizard).
function isTabBar(line: string): boolean { return /[←→]/.test(line) && /Submit|☒|✔|☑/.test(line); }

// The column of a side-by-side preview box's LEFT border, or -1 when there is no
// such box. The left border is the leftmost glyph on its row, so we take the
// FIRST box edge per line; a genuine box spans ≥4 rows (≥2 corners + content) at
// one fixed column. Anything from that column rightward is preview, not options.
function previewBorderCol(lines: string[]): number {
  const hits = new Map<number, number>();
  for (const ln of lines) {
    for (let c = 0; c < ln.length; c++) {
      if (BOX_EDGE_RE.test(ln[c])) { hits.set(c, (hits.get(c) || 0) + 1); break; }
    }
  }
  let col = -1;
  for (const [c, n] of hits) if (c > 0 && n >= 4 && (col === -1 || c < col)) col = c;
  return col;
}

function gapIsSkippable(lines: string[], a: number, b: number): boolean {
  for (let i = a + 1; i < b; i++) {
    const t = lines[i];
    if (isBlank(t) || isRule(t) || (isIndented(t) && !isOpt(t))) continue;
    return false;
  }
  return true;
}

// The contiguous block of numbered option rows nearest `endIdx` (exclusive),
// excluding any earlier prose numbering (gaps must be blank/rule/description).
function optionBlock(lines: string[], endIdx: number): number[] {
  const candidates: number[] = [];
  for (let i = 0; i < endIdx; i++) if (isOpt(lines[i])) candidates.push(i);
  if (!candidates.length) return [];
  const block = [candidates[candidates.length - 1]];
  for (let k = candidates.length - 2; k >= 0; k--) {
    if (gapIsSkippable(lines, candidates[k], block[0])) block.unshift(candidates[k]);
    else break;
  }
  return block;
}

function parseOptions(lines: string[], block: number[], endIdx: number) {
  const options: AskOption[] = [];
  let cursor = 0, cursorFound = false, hasCheckbox = false;
  for (let bi = 0; bi < block.length; bi++) {
    const idx = block[bi];
    const m = lines[idx].match(OPT_RE);
    if (!m) continue;
    const selected = !!m[1];
    const n = parseInt(m[2], 10);
    let label = (m[3] || "").trim();
    let checked: boolean | undefined;
    const cm = label.match(CHECK_RE);
    if (cm) { checked = /[✔✓xX]/.test(cm[1]); label = cm[2].trim(); hasCheckbox = true; }
    const end = bi + 1 < block.length ? block[bi + 1] : endIdx;
    const desc: string[] = [];
    for (let j = idx + 1; j < end; j++) {
      const t = lines[j];
      if (isBlank(t) || isRule(t) || isOpt(t)) continue;
      if (isIndented(t)) desc.push(t.trim());
    }
    if (selected) { cursor = n; cursorFound = true; }
    options.push({ n, label, desc: desc.length ? desc.join(" ") : undefined, selected, checked });
  }
  if (!cursor && options.length) cursor = options[0].n;
  return { options, cursor, cursorFound, hasCheckbox };
}

function mk(kind: AskKind, header: string | undefined, question: string | undefined, opts: ReturnType<typeof parseOptions>, preview?: string, chosen?: string[], pairs?: { q: string; a: string }[]): ParsedAsk {
  const sig = [
    kind, header || "", question || "",
    opts.options.map((o) => `${o.n}:${o.label}:${o.checked === undefined ? "" : o.checked ? "x" : "o"}`).join("|"),
    `cur${opts.cursor}`, (chosen || []).join(","), (pairs || []).map((p) => `${p.q}=${p.a}`).join(";"),
    preview ? `pv${preview.length}:${preview}` : "",   // re-post when the focused option's preview changes
  ].join("§");
  return { kind, header, question, options: opts.options, cursor: opts.cursor, cursorFound: opts.cursorFound, chosen, pairs, multiSelect: kind === "multi", preview, sig };
}

// Extract the side-by-side preview box: everything from the box's left border
// (bcol) rightward, with surrounding all-blank rows trimmed, kept VERBATIM (border
// glyphs and all) so the card reproduces the TUI's monospace layout exactly. The
// inverse of the clip at parseAskPane: the options keep the LEFT of bcol, the
// preview keeps the RIGHT.
function extractPreview(lines: string[], bcol: number): string | undefined {
  const col = lines.map((ln) => (ln.length > bcol ? ln.slice(bcol).replace(/\s+$/, "") : ""));
  let a = 0, b = col.length;
  while (a < b && col[a].trim() === "") a++;          // drop leading blank rows
  while (b > a && col[b - 1].trim() === "") b--;       // …and trailing
  return b > a ? col.slice(a, b).join("\n") : undefined;
}

export function parseAskPane(text: string): ParsedAsk | null {
  if (!text) return null;
  const raw = text.replace(/\r/g, "").split("\n");
  // Clip a side-by-side preview box so its text can't bleed into the options.
  // No box (the common case) → bcol < 0 → `raw` passes through untouched.
  const bcol = previewBorderCol(raw);
  const lines = bcol >= 0 ? raw.map((ln) => ln.slice(0, bcol)) : raw;
  const preview = bcol >= 0 ? extractPreview(raw, bcol) : undefined;   // the box we clipped off the right

  // PATH A — footer-anchored: single-select or the multi-select SELECTION screen.
  let footIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) if (FOOTER_RE.test(lines[i])) { footIdx = i; break; }
  if (footIdx >= 0) {
    const block = optionBlock(lines, footIdx);
    if (block.length) {
      const firstOptIdx = block[0];
      let header: string | undefined;
      const qLines: string[] = [];
      for (let k = firstOptIdx - 1; k >= 0 && qLines.length + (header ? 1 : 0) < 8; k--) {
        const t = lines[k];
        if (isRule(t)) break;
        if (isBlank(t)) continue;
        if (isTabBar(t)) {
          // Best-effort tab name: the first unanswered ☐ tab (the active one in
          // forward flow), else the first tab. Cosmetic — the question text wins.
          const h = t.match(/☐\s*([^☐☒✔✓→]+?)\s+[☐☒✔✓]/) || t.match(/[☐☒]\s*([^☐☒✔✓→]+?)\s+[☐☒✔✓]/);
          if (h && !header) header = h[1].trim();
          continue;
        }
        const hm = t.match(HEADER_RE);
        if (hm && !header) { header = hm[1].trim(); continue; }
        qLines.push(t.trim());
      }
      const question = qLines.length ? qLines.reverse().join(" ") : undefined;
      const opts = parseOptions(lines, block, footIdx);
      if (opts.options.length) {
        // ONLY checkbox rows mean multi-select — the ✔ Submit tab bar also tops
        // the multi-question wizard, whose per-question screens are single-select
        // (Enter picks). Classifying those as "multi" made the webview drop every
        // checkbox-less row and render an empty card (2026-06-11 bug).
        const kind: AskKind = opts.hasCheckbox ? "multi" : "single";
        return mk(kind, header, question, opts, preview);
      }
    }
  }

  // PATH B — the multi-select SUBMIT/review screen (no footer; "Submit answers").
  // HARDENED (2026-06-11 timeline_window incident): a label merely CONTAINING
  // "submit" matched ordinary numbered prose ("3. Enter after a 250ms gap so the
  // paste is fully received before submit.") and the probe then painted a phantom
  // permission state. The real screen's row is literally "Submit answers", and a
  // real review screen always carries the ● question (or → chosen) line above —
  // require both.
  let end = lines.length;
  while (end > 0 && !lines[end - 1].trim()) end--;
  if (end > 0) {
    const block = optionBlock(lines, end);
    if (block.length) {
      const opts = parseOptions(lines, block, end);
      if (opts.options.some((o) => /^submit answers\b/i.test(o.label.trim()))) {
        const firstOptIdx = block[0];
        // Collect EVERY "● question / → answer" pair above the options, in
        // document order — the multi-question wizard reviews all questions here.
        // Scan stops at the tab bar / rule that tops the review screen.
        let start = Math.max(0, firstOptIdx - 40);
        for (let k = firstOptIdx - 1; k >= start; k--) if (isTabBar(lines[k]) || isRule(lines[k])) { start = k + 1; break; }
        const pairs: { q: string; a: string }[] = [];
        for (let k = start; k < firstOptIdx; k++) {
          const q = lines[k].match(/^\s*●\s*(.+\S)\s*$/);
          if (q) { pairs.push({ q: q[1].trim(), a: "" }); continue; }
          const c = lines[k].match(/^\s*→\s*(.+\S)\s*$/);
          if (c) { const last = pairs[pairs.length - 1]; if (last && !last.a) last.a = c[1].trim(); else pairs.push({ q: "", a: c[1].trim() }); }
        }
        const chosen = pairs.flatMap((p) => p.a.split(/,\s*/)).map((s) => s.trim()).filter(Boolean);
        const question = pairs.length === 1 ? pairs[0].q || undefined : undefined;
        if (pairs.length) return mk("submit", undefined, question, opts, preview, chosen.length ? chosen : undefined, pairs);
      }
    }
  }

  // PATH C — a footer-LESS confirmation (e.g. /model's "Switch model?" prompt):
  // some TUI confirmations draw numbered options with NO key-hint footer at
  // all, and the picker REPLACES the composer + status line entirely (verified
  // against a captured pane, 2026-06-11 — the options are the pane's last
  // content). So: accept a ❯-cursor-bearing block of ≥2 plain options as the
  // LAST content of a pane showing no composer markers anywhere. An ANSWERED
  // picker lingering in scrollback always has the composer back beneath it,
  // which fails both tests.
  if (end > 0 && !COMPOSER_RE.test(text)) {
    const block = optionBlock(lines, end);
    if (block.length >= 2 && gapIsSkippable(lines, block[block.length - 1], end)) {
      const opts = parseOptions(lines, block, end);
      if (opts.options.length >= 2 && opts.cursorFound && !opts.hasCheckbox) {
        const firstOptIdx = block[0];
        let header: string | undefined;
        const qLines: string[] = [];
        for (let k = firstOptIdx - 1; k >= 0 && qLines.length < 8; k--) {
          const t = lines[k];
          if (isRule(t)) break;
          if (isBlank(t)) continue;
          const hm = t.match(HEADER_RE);
          if (hm && !header) { header = hm[1].trim(); continue; }
          qLines.push(t.trim());
        }
        return mk("single", header, qLines.length ? qLines.reverse().join(" ") : undefined, opts, preview);
      }
    }
  }

  return null;
}
