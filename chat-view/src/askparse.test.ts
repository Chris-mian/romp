// Unit tests for the TUI picker parser — pane-capture fixtures verified
// against the real Claude Code picker screens documented in askparse.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { parseAskPane } from "./askparse";

const FOOTER = "Enter to select · ↑/↓ to navigate · Esc to cancel";

test("single-select: header, question, options with descriptions, cursor", () => {
  const pane = [
    "",
    "☐ Auth method",
    "Which library should we use?",
    "❯ 1. passport",
    "     battle-tested, callback-style",
    "  2. lucia",
    "     newer, typescript-first",
    "",
    FOOTER,
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "single");
  assert.equal(ask.multiSelect, false);
  assert.equal(ask.header, "Auth method");
  assert.equal(ask.question, "Which library should we use?");
  assert.equal(ask.options.length, 2);
  assert.deepEqual(
    ask.options.map((o) => [o.n, o.label, o.desc, o.selected]),
    [[1, "passport", "battle-tested, callback-style", true],
     [2, "lucia", "newer, typescript-first", false]],
  );
  assert.equal(ask.cursor, 1);
  assert.equal(ask.cursorFound, true);
});

test("cursor on a later row; sig changes when the cursor moves", () => {
  const mk = (cur: number) => [
    "Pick one",
    (cur === 1 ? "❯ " : "  ") + "1. alpha",
    (cur === 2 ? "❯ " : "  ") + "2. beta",
    FOOTER,
  ].join("\n");
  const a = parseAskPane(mk(1))!;
  const b = parseAskPane(mk(2))!;
  assert.equal(b.cursor, 2);
  assert.notEqual(a.sig, b.sig);
});

test("no cursor captured: cursorFound false, cursor defaults to first option", () => {
  const ask = parseAskPane(["Pick one", "  1. alpha", "  2. beta", FOOTER].join("\n"))!;
  assert.equal(ask.cursorFound, false);
  assert.equal(ask.cursor, 1);
});

test("multi-select selection screen: tab bar + checkboxes", () => {
  const pane = [
    "←  ☒ Toppings  ✔ Submit  →",
    "Which toppings do you want?",
    "❯ 1. [✔] Pizza",
    "  2. [ ] Sushi",
    "  3. [✔] Salad",
    FOOTER,
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "multi");
  assert.equal(ask.multiSelect, true);
  assert.equal(ask.header, "Toppings");
  assert.deepEqual(ask.options.map((o) => [o.label, o.checked]),
    [["Pizza", true], ["Sushi", false], ["Salad", true]]);
});

test("multi-select submit screen: no footer, chosen answers, Submit row", () => {
  const pane = [
    "←  ☒ Toppings  ✔ Submit  →",
    "Review your answers",
    " ● Which toppings do you want?",
    "   → Pizza, Salad",
    "Ready to submit your answers?",
    "❯ 1. Submit answers",
    "  2. Cancel",
    "",
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "submit");
  assert.equal(ask.question, "Which toppings do you want?");
  assert.deepEqual(ask.chosen, ["Pizza", "Salad"]);
  assert.equal(ask.options[0].label, "Submit answers");
  assert.equal(ask.cursor, 1);
});

test("multi-question wizard tab: Submit tab bar + checkbox-less rows = SINGLE-select", () => {
  // verbatim shape of a captured AskUserQuestion pane (2026-06-11): two question
  // tabs + ✔ Submit; rows have NO checkboxes (Enter picks and advances). The tab
  // bar must NOT make this "multi" — that dropped every row from the webview card.
  const pane = [
    "────────────────────────────────────────",
    "←  ☐ Color  ☐ Size  ✔ Submit  →",
    "",
    "Favorite color?",
    "",
    "❯ 1. Red",
    "     The color red.",
    "  2. Green",
    "     The color green.",
    "  3. Blue",
    "     The color blue.",
    "  4. Type something.",
    "────────────────────────────────────────",
    "  5. Chat about this",
    "",
    "Enter to select · Tab/Arrow keys to navigate · Esc to cancel",
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "single");
  assert.equal(ask.multiSelect, false);
  assert.equal(ask.question, "Favorite color?");
  assert.equal(ask.header, "Color"); // first unanswered ☐ tab
  assert.equal(ask.options.length, 5);
  assert.equal(ask.options[0].label, "Red");
  assert.equal(ask.options[3].label, "Type something.");
  assert.equal(ask.options[4].label, "Chat about this");
  assert.equal(ask.cursor, 1);
  assert.equal(ask.cursorFound, true);
});

test("multi-question wizard: second tab after answering — first ☐ tab is the header", () => {
  const pane = [
    "←  ☒ Color  ☐ Size  ✔ Submit  →",
    "",
    "Pick a size?",
    "",
    "❯ 1. Small",
    "  2. Large",
    "  3. Type something.",
    "",
    "Enter to select · Tab/Arrow keys to navigate · Esc to cancel",
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "single");
  assert.equal(ask.header, "Size");
  assert.equal(ask.question, "Pick a size?");
});

test("multiSelect question in the new tab-bar style still classifies as multi (checkbox rows)", () => {
  // verbatim shape (2026-06-11): single multiSelect question — ☐ tab, [ ] rows
  const pane = [
    "←  ☐ Toppings  ✔ Submit  →",
    "",
    "Pick toppings?",
    "",
    "❯ 1. [ ] Cheese",
    "  Add cheese.",
    "  2. [✔] Mushroom",
    "  Add mushrooms.",
    "  3. [ ] Type something",
    "",
    "Enter to select · ↑/↓ to navigate · Esc to cancel",
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "multi");
  assert.equal(ask.header, "Toppings");
  assert.deepEqual(ask.options.map((o) => [o.label, o.checked]),
    [["Cheese", false], ["Mushroom", true], ["Type something", false]]);
});

test("multi-question review screen: every ● question / → answer pair is collected", () => {
  // verbatim shape of the wizard's Submit tab (2026-06-11)
  const pane = [
    "←  ☒ Color  ☒ Size  ✔ Submit  →",
    "",
    "Review your answers",
    "",
    " ● Favorite color?",
    "   → Red",
    " ● Pick a size?",
    "   → Extra medium",
    "",
    "Ready to submit your answers?",
    "",
    "❯ 1. Submit answers",
    "  2. Cancel",
    "",
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.kind, "submit");
  assert.deepEqual(ask.pairs, [
    { q: "Favorite color?", a: "Red" },
    { q: "Pick a size?", a: "Extra medium" },
  ]);
  assert.deepEqual(ask.chosen, ["Red", "Extra medium"]);
  assert.equal(ask.question, undefined); // multi-question: no single question line
  assert.equal(ask.options[0].label, "Submit answers");
});

test("earlier prose numbering is not swallowed into the option block", () => {
  const pane = [
    "Here is my plan:",
    "1. refactor the parser",
    "2. add tests",
    "Some prose in between that is not part of a picker.",
    "Do you want to proceed?",
    "❯ 1. Yes, proceed",
    "  2. No, revise it",
    FOOTER,
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.equal(ask.options.length, 2, "plan numbering must not join the option block");
  assert.equal(ask.options[0].label, "Yes, proceed");
  // nearby prose (up to 8 lines) is folded into the question — pin that the
  // real ask is its tail, not that the prose is excluded
  assert.ok(ask.question!.endsWith("Do you want to proceed?"));
});

test("non-picker screens parse to null", () => {
  assert.equal(parseAskPane(""), null);
  assert.equal(parseAskPane("just some assistant prose\nand more prose"), null);
  // a footer with no numbered options above it
  assert.equal(parseAskPane(["type your answer below", FOOTER].join("\n")), null);
});

test("PATH C: footer-less confirmation (the /model switch prompt) parses; answered copy in scrollback does not", () => {
  // verbatim shape of a captured pane (2026-06-11): no key-hint footer, and the
  // picker replaces the composer + status line — options are the last content
  const picker = [
    "⏺ Some prior output from the conversation.",
    "",
    "❯ /model fable",
    "────────────────────────────────────────",
    "  Switch model?",
    "  Your next response will be slower and use more tokens",
    "",
    "  This conversation is cached for the current model. Switching to Fable 5",
    "  means the full history gets re-read on your next message.",
    "",
    "  ❯ 1. Yes, switch to Fable 5",
    "    2. No, go back",
    "",
  ].join("\n");
  const ask = parseAskPane(picker)!;
  assert.ok(ask, "footer-less confirmation must parse");
  assert.equal(ask.kind, "single");
  assert.equal(ask.options.length, 2);
  assert.equal(ask.options[0].label, "Yes, switch to Fable 5");
  assert.equal(ask.cursor, 1);
  assert.ok(ask.question!.includes("Switch model?"));
  // the same picker text ABOVE a restored composer (= it was answered) is scrollback, not a prompt
  const answered = picker + "\n────────────\n❯ \n────────────\n  ctx:2%   Fable 5 high   /tmp/x\n  ⏵⏵ accept edits on (shift+tab to cycle)";
  assert.equal(parseAskPane(answered), null);
  // a numbered list in plain output with a composer beneath stays null too
  const listOutput = ["⏺ Here are your choices:", "  ❯ 1. First thing", "    2. Second thing", "", "  ctx:5%   Fable 5 high   /tmp/x"].join("\n");
  assert.equal(parseAskPane(listOutput), null);
});

test("side-by-side preview box is captured into ask.preview, kept out of the option labels", () => {
  // An AskUserQuestion whose options carry a `preview` renders the option list
  // on the LEFT and a bordered diagram box on the RIGHT, on the SAME pane rows.
  // Capturing that pane would otherwise glue the box text onto each option (the
  // greedy OPT_RE swallowing it into the label, box-only rows landing in the
  // previous option's desc). Invented content — no real session data. The box's
  // left border aligns at a fixed column (padEnd) exactly as the TUI lays it out.
  const W = 30;
  const row = (left: string, box: string) => left.padEnd(W) + box;
  const pane = [
    "☐ Deploy strategy",
    "Which rollout should the canary use?",
    row("❯ 1. Blue-green",          "╭─ Topology ───────────────╮"),
    row("     instant cutover",      "│ inbound → LB → [a] (live) │"),
    row("  2. Rolling",              "│           ↘ [b] (staged)  │"),
    row("     gradual, N at a time", "╰───────────────────────────╯"),
    "",
    FOOTER,
  ].join("\n");
  const ask = parseAskPane(pane)!;
  assert.ok(ask, "preview-bearing picker must still parse");
  assert.equal(ask.kind, "single");
  assert.equal(ask.options.length, 2);
  assert.equal(ask.options[0].label, "Blue-green");
  assert.equal(ask.options[1].label, "Rolling");
  assert.equal(ask.options[0].desc, "instant cutover");
  assert.equal(ask.options[1].desc, "gradual, N at a time");
  assert.equal(ask.cursor, 1);
  assert.equal(ask.cursorFound, true);
  // The preview must stay OUT of the options/question/header (no garble)…
  const optText = JSON.stringify({ q: ask.question, h: ask.header, opts: ask.options });
  for (const leak of ["Topology", "LB", "staged", "↘", "│", "╭", "╰"]) {
    assert.ok(!optText.includes(leak), `preview text "${leak}" leaked into the options`);
  }
  // …and be captured VERBATIM in ask.preview, so the card can reproduce the box
  // exactly as the TUI drew it (the user 2026-06-13).
  assert.ok(ask.preview, "the preview box must be captured into ask.preview");
  assert.match(ask.preview!, /╭─ Topology ─+╮/);
  assert.match(ask.preview!, /│ inbound → LB → \[a\] \(live\) │/);
  assert.match(ask.preview!, /↘ \[b\] \(staged\)/);
  assert.match(ask.preview!, /╰─+╯/);
  // it carries the border verbatim and never bleeds into the option column
  assert.ok(!ask.preview!.includes("Blue-green") && !ask.preview!.includes("Rolling"));
});

test("the preview is captured per focused option and re-keys the sig when it changes", () => {
  // Moving the cursor swaps which option's box the TUI draws; a re-capture must
  // surface the new box AND change sig so the host re-posts it. Synthetic boxes.
  const W = 22;
  const row = (l: string, b: string) => l.padEnd(W) + b;
  const pane = (box: string[]) => [
    "Which layout?",
    row("❯ 1. Stacked", box[0]),
    row("  2. Columns", box[1]),
    row("", box[2]),
    row("", box[3]),
    "",
    FOOTER,
  ].join("\n");
  const a = parseAskPane(pane(["╭──────╮", "│ A    │", "│      │", "╰──────╯"]))!;
  const b = parseAskPane(pane(["╭──────╮", "│ B  B │", "│ B    │", "╰──────╯"]))!;
  assert.ok(a.preview && b.preview, "both captures carry a preview");
  assert.match(a.preview!, /│ A {4}│/);
  assert.match(b.preview!, /│ B {2}B │/);
  assert.notEqual(a.preview, b.preview);
  assert.notEqual(a.sig, b.sig);
  assert.deepEqual(a.options.map((o) => o.label), ["Stacked", "Columns"]); // options unaffected
});
