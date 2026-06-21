import { test } from "node:test";
import * as assert from "node:assert/strict";
import { compactDisplay, summarizeTools, toolCounts, STANDALONE_TOOLS } from "./compact";

test("compactDisplay: thinking is dropped entirely", () => {
  const d = compactDisplay(["user", "thinking", "assistant"]);
  assert.deepEqual(d, [{ kind: "event", index: 0 }, { kind: "event", index: 2 }]);
});

test("compactDisplay: a run of consecutive tools collapses to one toolgroup", () => {
  const d = compactDisplay(["user", "tool", "tool", "tool", "assistant"]);
  assert.deepEqual(d, [
    { kind: "event", index: 0 },
    { kind: "toolgroup", indices: [1, 2, 3] },
    { kind: "event", index: 4 },
  ]);
});

test("compactDisplay: thinking between tools does NOT break the run (it's dropped first)", () => {
  const d = compactDisplay(["tool", "thinking", "tool"]);
  assert.deepEqual(d, [{ kind: "toolgroup", indices: [0, 2] }]);
});

test("compactDisplay: visible content between tools DOES split the run", () => {
  const d = compactDisplay(["tool", "assistant", "tool"]);
  assert.deepEqual(d, [
    { kind: "toolgroup", indices: [0] },
    { kind: "event", index: 1 },
    { kind: "toolgroup", indices: [2] },
  ]);
});

test("compactDisplay: a trailing tool run is flushed", () => {
  const d = compactDisplay(["assistant", "tool", "tool"]);
  assert.deepEqual(d, [{ kind: "event", index: 0 }, { kind: "toolgroup", indices: [1, 2] }]);
});

test("compactDisplay: AskUserQuestion is standalone — it breaks the run and passes through first-class", () => {
  // [Read, Edit, AskUserQuestion, Bash, Bash] → group(Read,Edit), the ask first-class, group(Bash,Bash).
  // The ask must NOT be swept into a toolgroup (the user 2026-06-17): it's the "you answered" box.
  const kinds = ["tool", "tool", "tool", "tool", "tool"];
  const names = ["Read", "Edit", "AskUserQuestion", "Bash", "Bash"];
  assert.deepEqual(compactDisplay(kinds, names), [
    { kind: "toolgroup", indices: [0, 1] },
    { kind: "event", index: 2 },
    { kind: "toolgroup", indices: [3, 4] },
  ]);
  assert.ok(STANDALONE_TOOLS.has("AskUserQuestion"));
});

test("compactDisplay: a lone AskUserQuestion run is a standalone event, never a 1-tool group", () => {
  assert.deepEqual(compactDisplay(["tool"], ["AskUserQuestion"]), [{ kind: "event", index: 0 }]);
});

test("compactDisplay: without names, every tool still collapses (back-compat)", () => {
  assert.deepEqual(compactDisplay(["tool", "tool", "tool"]), [{ kind: "toolgroup", indices: [0, 1, 2] }]);
});

test("summarizeTools: capitalized tool names, ordered by count desc, pluralized", () => {
  assert.equal(summarizeTools(["Edit", "Edit", "Edit", "Read", "Read", "Bash"]), "3 Edits, 2 Reads, 1 Bash");
});

test("summarizeTools: Edit variants merge as Edits; other tools keep their own name", () => {
  assert.equal(summarizeTools(["Edit", "MultiEdit", "Grep", "Glob"]), "2 Edits, 1 Grep, 1 Glob");
});

test("summarizeTools: a single tool is singular; Bash pluralizes correctly", () => {
  assert.equal(summarizeTools(["Read"]), "1 Read");
  assert.equal(summarizeTools(["Bash", "Bash"]), "2 Bashes");
});

test("toolCounts: returns ordered, pluralized {label,count} for styled rendering", () => {
  assert.deepEqual(toolCounts(["Edit", "Edit", "Read"]), [{ label: "Edits", count: 2 }, { label: "Read", count: 1 }]);
});
