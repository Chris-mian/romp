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
  chosen?: string[];    // submit screen: the answers under review
  multiSelect: boolean; // back-compat: kind === "multi"
  sig: string;          // change-signature, so the host only re-posts when it actually changed
}

const OPT_RE = /^\s*(❯)?\s*(\d+)\.\s+(.*\S)\s*$/;          // ❯? N. label  (checkbox, if any, lives inside the label)
const CHECK_RE = /^\[\s*([^\]]?)\s*\]\s*(.*)$/;             // [✔] label  /  [ ] label
const RULE_RE = /^\s*[─-]{3,}.*$/;
const HEADER_RE = /^\s*[☐☑▣▢]\s+(.+?)\s*$/;
const FOOTER_RE = /to navigate|Enter to select|Esc to (cancel|exit)/;

function isOpt(line: string): boolean { return OPT_RE.test(line); }
function isRule(line: string): boolean { return RULE_RE.test(line); }
function isBlank(line: string): boolean { return line.trim() === ""; }
function isIndented(line: string): boolean { return /^\s/.test(line) && line.trim() !== ""; }
// The `←  ☒ Header  ✔ Submit  →` wizard tab bar (multi-select only).
function isTabBar(line: string): boolean { return /[←→]/.test(line) && /Submit|☒|✔|☑/.test(line); }

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

function mk(kind: AskKind, header: string | undefined, question: string | undefined, opts: ReturnType<typeof parseOptions>, chosen?: string[]): ParsedAsk {
  const sig = [
    kind, header || "", question || "",
    opts.options.map((o) => `${o.n}:${o.label}:${o.checked === undefined ? "" : o.checked ? "x" : "o"}`).join("|"),
    `cur${opts.cursor}`, (chosen || []).join(","),
  ].join("§");
  return { kind, header, question, options: opts.options, cursor: opts.cursor, cursorFound: opts.cursorFound, chosen, multiSelect: kind === "multi", sig };
}

export function parseAskPane(text: string): ParsedAsk | null {
  if (!text) return null;
  const lines = text.replace(/\r/g, "").split("\n");

  // PATH A — footer-anchored: single-select or the multi-select SELECTION screen.
  let footIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) if (FOOTER_RE.test(lines[i])) { footIdx = i; break; }
  if (footIdx >= 0) {
    const block = optionBlock(lines, footIdx);
    if (block.length) {
      const firstOptIdx = block[0];
      let header: string | undefined, hasSubmitTab = false;
      const qLines: string[] = [];
      for (let k = firstOptIdx - 1; k >= 0 && qLines.length + (header ? 1 : 0) < 8; k--) {
        const t = lines[k];
        if (isRule(t)) break;
        if (isBlank(t)) continue;
        if (isTabBar(t)) { hasSubmitTab = true; const h = t.match(/☒\s*(.+?)\s+[✔✓]/); if (h && !header) header = h[1].trim(); continue; }
        const hm = t.match(HEADER_RE);
        if (hm && !header) { header = hm[1].trim(); continue; }
        qLines.push(t.trim());
      }
      const question = qLines.length ? qLines.reverse().join(" ") : undefined;
      const opts = parseOptions(lines, block, footIdx);
      if (opts.options.length) {
        const kind: AskKind = opts.hasCheckbox || hasSubmitTab ? "multi" : "single";
        return mk(kind, header, question, opts);
      }
    }
  }

  // PATH B — the multi-select SUBMIT/review screen (no footer; "Submit answers").
  let end = lines.length;
  while (end > 0 && !lines[end - 1].trim()) end--;
  if (end > 0) {
    const block = optionBlock(lines, end);
    if (block.length) {
      const opts = parseOptions(lines, block, end);
      if (opts.options.some((o) => /submit\b/i.test(o.label))) {
        const firstOptIdx = block[0];
        let question: string | undefined, chosen: string[] | undefined;
        for (let k = firstOptIdx - 1; k >= 0 && k > firstOptIdx - 14; k--) {
          const q = lines[k].match(/^\s*●\s*(.+\S)\s*$/); if (q && !question) question = q[1].trim();
          const c = lines[k].match(/^\s*→\s*(.+\S)\s*$/); if (c && !chosen) chosen = c[1].split(/,\s*/).map((s) => s.trim()).filter(Boolean);
        }
        return mk("submit", undefined, question, opts, chosen);
      }
    }
  }

  return null;
}
