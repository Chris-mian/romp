// Build the composer text for a "quote-reply": selected transcript text becomes a
// markdown blockquote (every line prefixed "> "), followed by a blank line for the
// reply. Pure (no DOM) so it is unit-testable; render.ts wires it to the right-click
// "Reply" menu item and drops the result into the composer.

export interface QuoteResult {
  value: string;   // the composer's new full text
  caret: number;   // where to put the cursor (after the quote, on the blank reply line)
}

// `selected` = the user's highlighted text; `existing` = whatever is already in the
// composer (a draft). The quote is APPENDED so a reply never clobbers a draft; the
// caret lands at the end, on the blank line under the quote, ready to type.
export function quoteReply(selected: string, existing: string): QuoteResult {
  const quoted = selected
    .replace(/\r\n?/g, "\n")          // normalize CRLF / CR
    .trim()                            // drop selection's leading/trailing blank space
    .split("\n")
    .map((l) => ("> " + l).trimEnd())  // blockquote each line; a blank line becomes ">" (keeps one quote block)
    .join("\n");
  const block = quoted + "\n\n";
  if (!existing) return { value: block, caret: block.length };
  // separate from the existing draft with exactly one blank line
  const sep = existing.endsWith("\n\n") ? "" : existing.endsWith("\n") ? "\n" : "\n\n";
  const value = existing + sep + block;
  return { value, caret: value.length };
}
