// T418 round two (the manager's read of PR 1663): the pure-layer cases, each red at c9b33002 (round one) on behaviour and green here.
// Imports only names round one exported, so the file compiles there and every case runs; the CONTROLS at the end pass at both.
import { test } from "node:test";
import assert from "node:assert/strict";
import { actionHead, toolRowLabel } from "./compact";

const T = (name: string, extra: Record<string, unknown> = {}) => ({ name, desc: "", input: "{}", ...extra });
const rows = (add: number, del: number) => [...Array(add).fill({ sign: "+" }), ...Array(del).fill({ sign: "-" })];

test("round two (a): the totals print ONCE at the end of the head, summed over every edit; a creation carries none", () => {
  assert.equal(actionHead([T("Edit", { file: "/a.ts", diffRows: rows(3, 1) }), T("NotebookEdit", { file: "/b.ipynb", diffRows: rows(2, 0) }), T("Write", { file: "/c.md" })]), "Edited 2 files, created a file +5 -1");
  assert.equal(actionHead([T("Write", { file: "/c.md" }), T("Write", { file: "/d.md" })]), "Created 2 files");
});
test("round two (d): a Bash whose command opens with a blank line labels its first non-blank line; a whitespace command reads Ran a command", () => {
  assert.deepEqual(toolRowLabel(T("Bash", { input: JSON.stringify({ command: "\n\n  make all\necho done" }) })), { text: "make all", code: true });
  assert.deepEqual(toolRowLabel(T("Bash", { input: JSON.stringify({ command: "   \n\t\n" }) })), { text: "Ran a command" });
});
test("round two (e): a fetched url with no host (file:, data:) falls to the url itself, clipped at 80 characters", () => {
  const data = "data:text/plain;base64," + "Q".repeat(200);
  const lbl = toolRowLabel(T("WebFetch", { input: JSON.stringify({ url: data }) })).text;
  assert.equal(lbl.length, "Fetched ".length + 80, lbl);
  assert.ok(lbl.endsWith("…"));
});
test("round two (f): reads and creations count DISTINCT files and the head orders by the printed number", () => {
  assert.equal(actionHead([...Array(4).fill(T("Read", { file: "/one" })), ...Array(3).fill(T("Bash"))]), "Ran 3 commands, read a file");
});
test("round two, medium 2 (pure part): a Grep with a path ends its label expecting the file link; the path is never printed as text", () => {
  const lbl = toolRowLabel(T("Grep", { input: JSON.stringify({ pattern: "foo", path: "/r/src/lib" }), file: "/r/src/lib" }));
  assert.equal(lbl.text, "Searched for foo in ");
  assert.ok(!lbl.text.includes("src/lib"));
});
// controls: unchanged behaviour, green at c9b33002 and here
test("control: a lone command and a description-bearing row read as in round one", () => {
  assert.equal(actionHead([T("Bash")]), "Ran a command");
  assert.deepEqual(toolRowLabel(T("Bash", { desc: "Verified the venv exists", input: JSON.stringify({ command: "ls" }) })), { text: "Verified the venv exists" });
  assert.equal(actionHead([T("Agent"), T("Task")]), "Ran 2 agents");
});
