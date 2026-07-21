// REGRESSION GUARD (the user 2026-06-29): the distiller's captions were silently removed once, and the
// source-regex pins didn't catch it — they were just rewritten to assert the removal. These tests EXECUTE the
// real rule (ui/webview/distiller-line.ts), so if the distiller line stops showing — or starts showing the
// planner's why, or sticks on a placeholder — they FAIL. feed.ts routes both the card and the modal node
// through these functions, so this is the single executable source of truth for "is the distiller shown?".
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { distillText, distillInputs, applyDistillLine, distillPending } from "./distiller-line";

// ── distillText: the rule, executed ───────────────────────────────────────────────────────────────────────
test("a COMPLETED item shows the distiller's takeaway (summary)", () => {
  assert.equal(distillText(true, false, "Shipped: see commit abc123", "ignored brief"), "Shipped: see commit abc123");
});

test("a BLOCKED item shows the distiller's decision brief (blockSummary)", () => {
  assert.equal(distillText(false, true, "ignored takeaway", "Decide: A vs B"), "Decide: A vs B");
});

test("the line stays EMPTY until the distiller produces — never a stuck placeholder", () => {
  assert.equal(distillText(true, false, null, null), "", "no summary yet → nothing (not '(generating…)')");
  assert.equal(distillText(true, false, "", null), "", "settled-empty → nothing");
  assert.equal(distillText(true, false, "   ", null), "", "whitespace-only → nothing (trimmed)");
});

test("a completed card never leaks the blockSummary, and a blocked card never leaks the summary", () => {
  assert.equal(distillText(true, false, null, "block brief"), "", "completed + only blockSummary → nothing");
  assert.equal(distillText(false, true, "done takeaway", null), "", "blocked + only summary → nothing");
});

test("neither completed nor blocked → nothing (an open/working card carries no distiller line)", () => {
  assert.equal(distillText(false, false, "x", "y"), "");
});

test("the takeaway is shown VERBATIM (trimmed) — a copy-pasteable artifact survives intact", () => {
  const artifact = "  romp --mail send ui3 \"hi\"\npath: ~/x/y.ts  ";
  assert.equal(distillText(true, false, artifact, null), artifact.trim());
});

// distillText structurally CANNOT show the why: its signature has no `why` parameter. This is the invariant
// that keeps the why-rationale lines (which the user dropped) from ever creeping back via this path.
test("distillText has no `why` input, so it can never display the planner's rationale", () => {
  assert.equal(distillText.length, 4, "(completed, blocked, summary, blockSummary) — exactly four params, no why");
});

// ── distillInputs: the brief keys on the GENUINE state, not the flickery column (the user 2026-07-21) ────────
test("distillInputs keys on distillState, so a still-blocked card KEEPS its brief while column reads working", () => {
  // the regression: recheck/rejudging drop a blocked card to the Working column each turn its session runs;
  // when the line keyed on column, the brief vanished every time (the docs thread "unblocked, no summary").
  assert.deepEqual(distillInputs("blocked", "working"), { completed: false, blocked: true },
    "genuinely blocked but momentarily in the Working column → STILL show the decision brief");
  assert.deepEqual(distillInputs("blocked", "needs_input"), { completed: false, blocked: true });
  assert.deepEqual(distillInputs("completed", "working"), { completed: true, blocked: false },
    "a completed card mid-rejudge keeps its takeaway too");
});

test("distillInputs shows nothing for a genuinely working card, and falls back to column when the field is absent", () => {
  assert.deepEqual(distillInputs(null, "working"), { completed: false, blocked: false },
    "a working card the kernel marked null → no line");
  // older / remote payloads omit the field: read the column's old meaning so federation frames still render
  assert.deepEqual(distillInputs(undefined, "needs_input"), { completed: false, blocked: true },
    "no distillState (old/remote) + needs_input column → blocked (legacy behavior preserved)");
  assert.deepEqual(distillInputs(undefined, "completed"), { completed: true, blocked: false });
  assert.deepEqual(distillInputs(undefined, "working"), { completed: false, blocked: false });
});

// The end-to-end guarantee, executed: a blocked card in the Working column (recheck/rejudge) still yields its
// brief text — distillInputs → distillText, the exact composition feed.ts runs.
test("blocked + working column composes to the decision brief text (the flicker fix, end to end)", () => {
  const { completed, blocked } = distillInputs("blocked", "working");
  assert.equal(distillText(completed, blocked, null, "Decide: consolidate the Internals pages or not"),
    "Decide: consolidate the Internals pages or not");
});

// ── applyDistillLine: the SHOW/HIDE behavior, executed against a fake element (no DOM needed) ───────────────
function fakeEl() { return { textContent: "x", style: { display: "x" } }; }

test("applyDistillLine SHOWS the line (display unset) and sets the text when the distiller has produced", () => {
  const el = fakeEl();
  const out = applyDistillLine(el, true, false, "Done: X", null);
  assert.equal(out, "Done: X");
  assert.equal(el.textContent, "Done: X");
  assert.equal(el.style.display, "", "a produced summary is shown (display cleared, not 'none')");
});

test("applyDistillLine HIDES the line when there's nothing to show — no empty box, no placeholder", () => {
  const el = fakeEl();
  applyDistillLine(el, true, false, "", null);
  assert.equal(el.textContent, "");
  assert.equal(el.style.display, "none");
});

test("applyDistillLine shows the blockSummary on a blocked card", () => {
  const el = fakeEl();
  applyDistillLine(el, false, true, null, "Decide A vs B");
  assert.equal(el.textContent, "Decide A vs B");
  assert.equal(el.style.display, "");
});

// ── distillPending: the "distiller is running → show the spinning swirl" rule, executed (the user 2026-06-29) ──
test("a COMPLETED card is distill-PENDING while its summary is null (distiller running → spinner)", () => {
  assert.equal(distillPending(true, false, null, null), true, "no summary yet → pending");
  assert.equal(distillPending(true, false, undefined, null), true, "undefined summary → pending");
});

test("a COMPLETED card is NOT pending once the distiller settled — produced OR gave up", () => {
  assert.equal(distillPending(true, false, "Shipped X", null), false, "produced takeaway → line shows, no spin");
  assert.equal(distillPending(true, false, "", null), false, "gave-up '' sentinel → no spin, no line");
});

test("a BLOCKED card is distill-PENDING while its blockSummary is null — but NOT when live-blocked (on you)", () => {
  assert.equal(distillPending(false, true, null, null), true, "awaiting decision brief → pending");
  assert.equal(distillPending(false, true, null, "Decide A vs B"), false, "brief produced → no spin");
  assert.equal(distillPending(false, true, null, null, true), false, "live permission/picker block is ON YOU → no distill spin");
});

test("an open/working card (neither completed nor blocked) is never distill-pending", () => {
  assert.equal(distillPending(false, false, null, null), false);
});
