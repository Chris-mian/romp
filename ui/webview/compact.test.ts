import { test } from "node:test";
import * as assert from "node:assert/strict";
import { compactDisplay, itemAnchor, STANDALONE_TOOLS, actionHead, actionParts, actionPhrases, toolRowLabel, diffTotals, toolInputText, type DisplayItem } from "./compact";

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

test("compactDisplay: visible content between tools DOES split the run; each lone tool stays inline", () => {
  const d = compactDisplay(["tool", "assistant", "tool"]);
  assert.deepEqual(d, [
    { kind: "event", index: 0 },   // a lone tool renders inline, not a 1-element toolgroup (the user 2026-06-22)
    { kind: "event", index: 1 },
    { kind: "event", index: 2 },
  ]);
});

test("compactDisplay: a LONE tool renders inline; only a run of ≥2 collapses (the user 2026-06-22)", () => {
  assert.deepEqual(compactDisplay(["assistant", "tool", "assistant"]),
    [{ kind: "event", index: 0 }, { kind: "event", index: 1 }, { kind: "event", index: 2 }]);
  assert.deepEqual(compactDisplay(["tool", "tool"]), [{ kind: "toolgroup", indices: [0, 1] }]);
  assert.deepEqual(compactDisplay(["tool"]), [{ kind: "event", index: 0 }]);
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


test("every non-tool event owns exactly one display unit — the scroll-mark translation's ground truth", () => {
  // eventUnitIndex (render.ts) inverts this stream to map mark anchors (events) onto the frame's
  // unit space; that inversion is sound only if a user/assistant event is never folded into a
  // group and never dropped (the user 2026-08-18, whose reply notches vanished in compact mode)
  const kinds = ["user", "tool", "tool", "assistant", "user", "tool", "user"];
  const items = compactDisplay(kinds, kinds.map((k) => (k === "tool" ? "Bash" : undefined)));
  const seen = new Map<number, number>();
  items.forEach((it, u) => {
    if (it.kind === "toolgroup" || it.kind === "noticegroup") for (const i of it.indices) seen.set(i, u);   // noticegroup since 2026-09-08
    else if (it.kind === "event") seen.set(it.index, u);
  });
  for (let i = 0; i < kinds.length; i++) {
    assert.ok(seen.has(i), "event " + i + " (" + kinds[i] + ") maps to a unit");
    if (kinds[i] !== "tool") {
      const u = seen.get(i)!;
      const it = items[u];
      assert.equal(it.kind, "event", "a non-tool event is its OWN unit, never inside a fold");
    }
  }
});

test("consecutive retry-recovery notes fold like a tool run — a lone one stays first-class (T131)", () => {
  // the user 2026-08-27: seventeen consecutive 'Recovered after N retries' rows are a flood; the
  // collapsed-run idiom fits consecutive same-shape machine notices exactly. 2026-09-08: the fold is the
  // generic NOTICEGROUP (a bare "retried" run still folds when the caller passes no foldability array).
  const kinds = ["user", "retried", "retried", "retried", "assistant", "retried", "user"];
  const items = compactDisplay(kinds);
  assert.deepEqual(items, [
    { kind: "event", index: 0 },
    { kind: "noticegroup", indices: [1, 2, 3] },
    { kind: "event", index: 4 },
    { kind: "event", index: 5 },   // a lone recovery renders first-class, like a lone tool
    { kind: "event", index: 6 },
  ]);
});

test("the foldable set is the caller's (isFoldableNotice): effort/model-swap/reload/interrupt pairs fold; peers and boundaries never do (2026-09-08)", () => {
  const kinds = ["user", "effortApplied", "modelFallback", "user", "assistant", "postal-service", "compact", "retried", "retried"];
  const notices = [false, true, true, true /* an interrupt marker */, true /* its settle */, false, false, true, true];
  assert.deepEqual(compactDisplay(kinds, undefined, notices), [
    { kind: "event", index: 0 },
    { kind: "noticegroup", indices: [1, 2, 3, 4] },
    { kind: "event", index: 5 },   // a peer's mail stands alone — a reply may be owed
    { kind: "event", index: 6 },   // a compaction boundary is a boundary
    { kind: "noticegroup", indices: [7, 8] },
  ]);
  // with the array present, a "retried" NOT marked foldable is a plain event (the array is authoritative)
  assert.deepEqual(compactDisplay(["retried", "retried"], undefined, [false, false]),
    [{ kind: "event", index: 0 }, { kind: "event", index: 1 }]);
});

test("retry runs and tool runs break each other — two folds, never one mixed group", () => {
  const kinds = ["retried", "retried", "tool", "tool", "retried", "retried"];
  const items = compactDisplay(kinds, kinds.map((k) => (k === "tool" ? "Bash" : undefined)));
  assert.deepEqual(items, [
    { kind: "noticegroup", indices: [0, 1] },   // noticegroup since 2026-09-08
    { kind: "toolgroup", indices: [2, 3] },
    { kind: "noticegroup", indices: [4, 5] },
  ]);
});

test("thinking hides without breaking a retry run, same as a tool run", () => {
  const kinds = ["retried", "thinking", "retried"];
  assert.deepEqual(compactDisplay(kinds), [{ kind: "noticegroup", indices: [0, 2] }]);   // noticegroup since 2026-09-08
});

// T339 (the user 2026-09-11): a collapsed run is placed and timed by its LATEST member, never its first. The user's
// transcript held a notice run whose first member carried yesterday's clock among today's rows.
test("itemAnchor: a lone event is its own anchor; a run anchors on its latest member, ties on the later one", () => {
  const epochs = [1000, 2000, 500, 2000, null, 3000];
  const at = (i: number) => epochs[i] ?? null;
  assert.equal(itemAnchor({ kind: "event", index: 2 }, at), 2);
  assert.equal(itemAnchor({ kind: "noticegroup", indices: [2, 5] }, at), 5, "yesterday then today: today");
  assert.equal(itemAnchor({ kind: "noticegroup", indices: [5, 2] }, at), 5, "the latest, wherever it sits in the run");
  assert.equal(itemAnchor({ kind: "noticegroup", indices: [1, 3] }, at), 3, "a tie: the later member");
  assert.equal(itemAnchor({ kind: "noticegroup", indices: [0, 4, 1] }, at), 1, "a member with no epoch never anchors");
  assert.equal(itemAnchor({ kind: "toolgroup", indices: [2, 5] }, at), 2, "a tool run keeps its first member, as before");
  assert.equal(itemAnchor({ kind: "noticegroup", indices: [4, 4] } as DisplayItem, at), 4, "no timed member: the first");
});


// ── T418: the tool rows in the user's terms ──
const T = (name: string, extra: Record<string, unknown> = {}) => ({ name, desc: "", input: "{}", ...extra });
const rows = (add: number, del: number) => [...Array(add).fill({ sign: "+" }), ...Array(del).fill({ sign: "-" })];

test("T418 head: the screenshot's turn reads by action, ordered by the printed number, the edits' totals once at the end", () => {
  const tools = [
    ...Array(11).fill(T("Bash", { input: JSON.stringify({ command: "true" }) })),
    T("Write", { file: "/w/a.txt" }), T("Write", { file: "/w/b.txt" }),
    T("Edit", { file: "/w/f.ts", diffRows: rows(12, 0) }), T("Edit", { file: "/w/g.ts", diffRows: rows(20, 0) }), T("MultiEdit", { file: "/w/h.ts", diffRows: rows(5, 0) }),
    T("Read", { file: "/w/1" }), T("Read", { file: "/w/2" }), T("Read", { file: "/w/3" }), T("Read", { file: "/w/4" }),
  ];
  assert.equal(actionHead(tools), "Ran 11 commands, read 4 files, edited 3 files, created 2 files +37 -0");
  assert.deepEqual(actionParts(tools), { text: "Ran 11 commands, read 4 files, edited 3 files, created 2 files", add: 37, del: 0 });
});
test("T418 head: singulars, the sole search by its own words, tools with no action, the task list", () => {
  assert.equal(actionHead([T("Bash")]), "Ran a command");
  assert.equal(actionHead([T("Read", { file: "/a/b/c.py" })]), "Read a file");
  assert.equal(actionHead([T("Edit", { file: "/a.ts", diffRows: rows(12, 3) })]), "Edited a file +12 -3");
  assert.equal(actionHead([T("Grep", { input: JSON.stringify({ pattern: "foo", path: "/repo/src" }), file: "/repo/src" })]), "Searched for foo");
  assert.equal(actionHead([T("Grep", { input: JSON.stringify({ pattern: "foo" }) }), T("Glob", { input: JSON.stringify({ pattern: "*.ts" }) })]), "Searched 2 times");
  assert.equal(actionHead([T("WebFetch", { input: JSON.stringify({ url: "https://example.org/x" }) })]), "Fetched a page");
  assert.equal(actionHead([T("Agent"), T("Task")]), "Ran 2 agents");
  assert.equal(actionHead([T("TodoWrite"), T("TaskUpdate")]), "Updated the task list");
  assert.equal(actionHead([T("Skill"), T("Monitor")]), "Used 2 tools");
  assert.equal(actionHead([T("Skill")]), "Used a tool");
});
test("T418 head: distinct files for reads, edits and creations, uses for the rest; the order follows the printed number; the head never reads desc", () => {
  const tools = [T("Edit", { file: "/a.ts", diffRows: rows(3, 1), desc: "this is ignored" }), T("Edit", { file: "/a.ts", diffRows: rows(4, 0) })];
  assert.equal(actionHead(tools), "Edited a file +7 -1");
  assert.deepEqual(actionPhrases(tools).map((p) => [p.action, p.count, p.printed, p.add, p.del]), [["edit", 2, 1, 7, 1]]);
  assert.equal(actionHead([...Array(4).fill(T("Read", { file: "/one" })), ...Array(3).fill(T("Bash"))]), "Ran 3 commands, read a file");
  assert.deepEqual(diffTotals({ name: "Write", diff: "+ a\n+ b\n- c" }), { add: 2, del: 1 });
});
test("T418 head: the totals of every edit in a group sum into ONE printing; a creation carries none (the kernel emits no Write diff)", () => {
  const tools = [T("Edit", { file: "/a.ts", diffRows: rows(3, 1) }), T("NotebookEdit", { file: "/b.ipynb", diffRows: rows(2, 0) }), T("Write", { file: "/c.md" })];
  assert.deepEqual(actionParts(tools), { text: "Edited 2 files, created a file", add: 5, del: 1 });
  assert.equal(actionHead(tools), "Edited 2 files, created a file +5 -1");
  assert.equal(actionHead([T("Write", { file: "/c.md" })]), "Created a file");
});
test("T418 row: the model's description wins; else the derived phrase per tool, the file as the link after it; a bare Bash shows its command in the code face", () => {
  assert.deepEqual(toolRowLabel(T("Bash", { desc: "Verified the venv exists", input: JSON.stringify({ command: "ls" }) })), { text: "Verified the venv exists" });
  assert.deepEqual(toolRowLabel(T("Bash", { input: JSON.stringify({ command: "cd ~/x && make\necho done" }) })), { text: "cd ~/x && make", code: true });
  assert.deepEqual(toolRowLabel(T("Read", { file: "/home/u/repo/kernel/kernel.py" })), { text: "Read ", link: true });
  assert.deepEqual(toolRowLabel(T("Edit", { file: "/r/ui/feed.ts", diffRows: rows(12, 3) })), { text: "Edited ", link: true, totals: "+12 -3" });
  assert.deepEqual(toolRowLabel(T("Write", { file: "/r/new.md" })), { text: "Created ", link: true });
  assert.deepEqual(toolRowLabel(T("Grep", { input: JSON.stringify({ pattern: "foo", path: "/r/src/lib" }), file: "/r/src/lib" })), { text: "Searched for foo in ", link: true });
  assert.deepEqual(toolRowLabel(T("Grep", { input: JSON.stringify({ pattern: "foo" }) })), { text: "Searched for foo" });
  assert.deepEqual(toolRowLabel(T("Glob", { input: JSON.stringify({ pattern: "**/*.ts", path: "/r" }), file: "/r" })), { text: "Searched for **/*.ts in ", link: true });
  assert.deepEqual(toolRowLabel(T("WebFetch", { input: JSON.stringify({ url: "https://docs.example.org/a/b" }) })), { text: "Fetched docs.example.org" });
  assert.deepEqual(toolRowLabel(T("WebSearch", { input: JSON.stringify({ query: "romp kernel" }) })), { text: "Searched the web for romp kernel" });
  assert.deepEqual(toolRowLabel(T("Agent")), { text: "Ran an agent" });
  assert.deepEqual(toolRowLabel(T("TaskUpdate")), { text: "Updated the task list" });
  assert.deepEqual(toolRowLabel(T("Skill")), { text: "Used a tool", secondary: "Skill" });
  assert.deepEqual(toolRowLabel(T("LS", { file: "/r/dir" })), { text: "Used a tool", secondary: "LS" });
  const long = "x".repeat(100);
  assert.equal(toolRowLabel(T("Grep", { input: JSON.stringify({ pattern: long }) })).text.length, "Searched for ".length + 80);
});
test("T418 expanded row: a Bash shows its command as typed; other tools their input JSON", () => {
  assert.equal(toolInputText(T("Bash", { input: JSON.stringify({ command: "cd ~/x && make", description: "Built it" }) })), "cd ~/x && make");
  assert.equal(toolInputText(T("Read", { input: JSON.stringify({ file_path: "/a" }) })), JSON.stringify({ file_path: "/a" }));
  assert.equal(toolInputText(T("Bash", { input: "{not json" })), "{not json");
});
