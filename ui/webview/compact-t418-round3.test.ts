// T418 round three (the manager's read of PR 1663 at 449906c9): pure-layer cases, each red at 449906c9 on behaviour and green here.
// Imports only names that exist there, so the file compiles and every case runs; the CONTROLS at the end pass at both.
import { test } from "node:test";
import assert from "node:assert/strict";
import { actionHead, toolRowLabel } from "./compact";

const T = (name: string, extra: Record<string, unknown> = {}) => ({ name, desc: "", input: "{}", ...extra });
const rows = (add: number, del: number) => [...Array(add).fill({ sign: "+" }), ...Array(del).fill({ sign: "-" })];

test("round three, medium: an edit's file count is the distinct files plus the uses that carried none, whoever the siblings are", () => {
  // one Edit with a path beside three NotebookEdits with none (the kernel does not turn notebook_path into file today): four edited files
  assert.equal(actionHead([T("Edit", { file: "/src/a.ts", diffRows: rows(2, 0) }), T("NotebookEdit"), T("NotebookEdit"), T("NotebookEdit")]), "Edited 4 files +2 -0");
  assert.equal(actionHead([T("NotebookEdit"), T("NotebookEdit"), T("NotebookEdit")]), "Edited 3 files");
  // two reads of one file beside a read that carried none: two files
  assert.equal(actionHead([T("Read", { file: "/x" }), T("Read", { file: "/x" }), T("Read")]), "Read 2 files");
  // the same file edited twice and nothing else: one file, as before
  assert.equal(actionHead([T("Edit", { file: "/a.ts", diffRows: rows(1, 0) }), T("Edit", { file: "/a.ts", diffRows: rows(1, 0) })]), "Edited a file +2 -0");
});
test("round three (c): a parsed hostname is clipped like every label part", () => {
  const host = "h" + "o".repeat(4000) + ".example";
  const lbl = toolRowLabel(T("WebFetch", { input: JSON.stringify({ url: "https://" + host + "/p" }) })).text;
  assert.equal(lbl.length, "Fetched ".length + 80, String(lbl.length));
  assert.ok(lbl.endsWith("…"));
});
// controls: unchanged behaviour, green at 449906c9 and here
test("control: the round-two head shape and a description-bearing row read as before", () => {
  assert.equal(actionHead([T("Edit", { file: "/a.ts", diffRows: rows(3, 1) }), T("NotebookEdit", { file: "/b.ipynb", diffRows: rows(2, 0) }), T("Write", { file: "/c.md" })]), "Edited 2 files, created a file +5 -1");
  assert.deepEqual(toolRowLabel(T("Bash", { desc: "Verified the venv exists", input: JSON.stringify({ command: "ls" }) })), { text: "Verified the venv exists" });
});
