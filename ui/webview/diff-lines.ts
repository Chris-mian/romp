// Turn the kernel's Edit/MultiEdit diff string (lines prefixed "- " for removed, "+ " for added) into rows
// carrying a relative line-number gutter (the user 2026-06-29). The Edit tool result in this environment is
// just "file updated" — it carries no absolute file line numbers — so the gutter numbers positions WITHIN the
// change: removed lines count up the OLD column, added lines count up the NEW column, both from 1. That gives
// the diff a familiar two-column gutter for reading/referencing a multi-line edit.

export interface DiffRow {
  sign: "+" | "-" | " ";
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
