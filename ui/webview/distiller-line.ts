// The distiller's display line, computed in ONE place so a test can EXECUTE the rule — not just regex the
// source, which is what let it get silently removed before (the user 2026-06-29: "make sure the distiller
// captions never turn off again"). The whole saga: the captions were dropped, and the source-pin tests were
// simply rewritten to assert the removal, so nothing caught it. distiller-line.test.ts runs THIS instead.
//
// THE CONTRACT (the test pins it behaviorally):
//   - a COMPLETED item shows the distiller's takeaway (summary)
//   - a BLOCKED item shows its decision brief (blockSummary)
//   - anything else shows nothing
//   - it is shown ONLY when the distiller has produced a non-empty value (trimmed) — never a "(generating…)"
//     placeholder (which used to stick)
//   - it NEVER takes — and therefore can NEVER show — the planner's why-created/why-blocked/why-done
//     rationale (the user dropped those, esp. under subgoals). The signature has no `why` by design.

/** The distiller line's text for an item/node, or "" when there's nothing to show. */
export function distillText(
  completed: boolean,
  blocked: boolean,
  summary?: string | null,
  blockSummary?: string | null,
): string {
  return (completed ? (summary || "") : blocked ? (blockSummary || "") : "").trim();
}

/** Populate a card's distiller line element: set its text and show it ONLY when non-empty. Returns the text.
 *  Takes a minimal element shape so it runs under `node --test` without a DOM (the real DOM node satisfies it). */
export function applyDistillLine(
  el: { textContent: string; style: { display: string } },
  completed: boolean,
  blocked: boolean,
  summary?: string | null,
  blockSummary?: string | null,
): string {
  const t = distillText(completed, blocked, summary, blockSummary);
  el.textContent = t;
  el.style.display = t ? "" : "none";   // hidden until the distiller produces — no stuck placeholder
  return t;
}
