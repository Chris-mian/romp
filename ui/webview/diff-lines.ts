// FALLBACK diff gutter (the user 2026-06-29). The preferred source is the kernel's diffRows — REAL file line
// numbers + context from Claude Code's structuredPatch (kernel _patch_rows). This function is the fallback for
// records that carry no structured patch: it turns the kernel's Edit/MultiEdit diff string (lines prefixed
// "- " removed / "+ " added) into rows with a RELATIVE gutter — removed lines count up the OLD column, added
// lines up the NEW column, both from 1 — so the diff still reads with a familiar two-column gutter.

export interface DiffRow {
  sign: "+" | "-" | " " | "@";   // "@" = a per-hunk header row (only from the kernel's real-line-number rows)
  text: string;            // the line content, WITHOUT the leading "+ " / "- " marker
  oldNo: number | null;    // old-side number (removed + context lines), else null
  newNo: number | null;    // new-side number (added + context lines), else null
}

// Parse the diff into numbered rows. A trailing empty line (from a trailing "\n") is dropped so it doesn't
// render as a blank numbered row. Anything not starting with "+ "/"- " is treated as context (rare; the
// kernel's _edit_diff emits only +/- lines, but be lenient).
export function numberDiff(diff: string): DiffRow[] {
  const lines = diff.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();   // drop a single trailing newline's empty
  const rows: DiffRow[] = [];
  let oldNo = 1, newNo = 1;
  for (const line of lines) {
    const marker = line.slice(0, 2);
    if (marker === "+ ") {
      rows.push({ sign: "+", text: line.slice(2), oldNo: null, newNo: newNo++ });
    } else if (marker === "- ") {
      rows.push({ sign: "-", text: line.slice(2), oldNo: oldNo++, newNo: null });
    } else {
      rows.push({ sign: " ", text: line.replace(/^ {2}/, ""), oldNo: oldNo++, newNo: newNo++ });
    }
  }
  return rows;
}
