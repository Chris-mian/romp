// Unit tests for the transcript parser — the contract the kernel and the
// extension both consume. Run: npm test
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { parse, newIncParser, feed, buildParsed, ChatEvent } from "./transcript";

const NOW = () => new Date(Date.now() - 30_000).toISOString(); // recent: avoids the working-stale clamp

function uline(uuid: string, parent: string | null, text: string, opts: any = {}) {
  return JSON.stringify({
    type: "user", uuid, parentUuid: parent, timestamp: opts.ts ?? NOW(),
    promptSource: "promptSource" in opts ? opts.promptSource : "typed",
    sessionId: opts.sessionId,
    message: { role: "user", content: opts.blocks ?? text },
    ...(opts.extra || {}),
  });
}

function aline(uuid: string, parent: string | null, blocks: any[], opts: any = {}) {
  return JSON.stringify({
    type: "assistant", uuid, parentUuid: parent, timestamp: opts.ts ?? NOW(),
    message: { role: "assistant", content: blocks, stop_reason: "stop" in opts ? opts.stop : "end_turn" },
  });
}

function toolResultLine(uuid: string, parent: string | null, toolUseId: string, text: string, isError = false) {
  return JSON.stringify({
    type: "user", uuid, parentUuid: parent, timestamp: NOW(),
    message: { role: "user", content: [{ type: "tool_result", tool_use_id: toolUseId, content: text, is_error: isError }] },
  });
}

function qline(op: string, content: string | null = null) {
  return JSON.stringify({ type: "queue-operation", operation: op, content, timestamp: NOW() });
}

const join = (...lines: string[]) => lines.join("\n") + "\n";

test("basic turn: user, thinking, assistant text, tool with folded result", () => {
  const raw = join(
    uline("u1", null, "fix the bug", { sessionId: "sid-1" }),
    aline("a1", "u1", [
      { type: "thinking", thinking: "let me look" },
      { type: "tool_use", id: "t1", name: "Bash", input: { command: "ls", description: "List files" } },
    ], { stop: "tool_use" }),
    toolResultLine("u2", "a1", "t1", "file.txt"),
    aline("a2", "u2", [{ type: "text", text: "Done — found it." }]),
  );
  const out = parse(raw);
  assert.equal(out.sessionId, "sid-1");
  const kinds = out.events.map((e) => e.kind);
  assert.deepEqual(kinds, ["user", "thinking", "tool", "assistant"]);
  const user = out.events[0] as Extract<ChatEvent, { kind: "user" }>;
  assert.equal(user.human, true);
  const tool = out.events[2] as Extract<ChatEvent, { kind: "tool" }>;
  assert.equal(tool.name, "Bash");
  assert.equal(tool.desc, "List files");
  assert.equal(tool.input, "ls");
  assert.equal(tool.output, "file.txt");
  assert.equal(tool.resultUuid, "u2");
  assert.equal(out.status.working, false); // last assistant ended with end_turn
});

test("rewound branch is excluded from the active path", () => {
  const raw = join(
    uline("u1", null, "first"),
    aline("a1", "u1", [{ type: "text", text: "reply one" }]),
    uline("u2", "a1", "dead end"),
    aline("a2", "u2", [{ type: "text", text: "abandoned reply" }]),
    uline("u3", "a1", "second attempt"), // rewind: forks from a1
    aline("a3", "u3", [{ type: "text", text: "good reply" }]),
  );
  const texts = parse(raw).events.map((e: any) => e.md ?? "");
  assert.ok(texts.includes("second attempt"));
  assert.ok(!texts.includes("dead end"));
  assert.ok(!texts.includes("abandoned reply"));
});

test("compaction stitch: logicalParentUuid keeps pre-compaction history", () => {
  const raw = join(
    uline("u1", null, "early work"),
    aline("a1", "u1", [{ type: "text", text: "early reply" }]),
    JSON.stringify({
      type: "user", uuid: "c1", parentUuid: null, logicalParentUuid: "a1",
      timestamp: NOW(), isCompactSummary: true,
      message: { role: "user", content: "summary of earlier conversation" },
    }),
    aline("a2", "c1", [{ type: "text", text: "post-compaction reply" }]),
  );
  const texts = parse(raw).events.map((e: any) => e.md ?? "");
  assert.ok(texts.includes("early work"), "pre-compaction history must survive");
  assert.ok(texts.includes("post-compaction reply"));
});

test("incremental feed across split lines and split UTF-8 equals one-shot parse", () => {
  const raw = join(
    uline("u1", null, "emoji test \u{1F4EC} done"),
    aline("a1", "u1", [{ type: "text", text: "ok — fixed" }]),
  );
  const whole = parse(raw);
  const buf = Buffer.from(raw, "utf8");
  // feed in 3-byte chunks: guarantees lines AND multibyte chars split mid-read
  const p = newIncParser();
  for (let i = 0; i < buf.length; i += 3) feed(p, buf.subarray(i, Math.min(i + 3, buf.length)));
  const inc = buildParsed(p);
  assert.deepEqual(inc.events, whole.events);
});

test("queue folding: unresolved tail only, harness/banner enqueues filtered", () => {
  const raw = join(
    uline("u1", null, "main ask"),
    aline("a1", "u1", [{ type: "text", text: "working" }], { stop: "tool_use" }),
    qline("enqueue", "first queued"),
    qline("enqueue", "second queued"),
    qline("dequeue"),                                    // resolves "first queued"
    qline("enqueue", "<task-notification>bg done</task-notification>"),
    qline("enqueue", "#################### banner \u{1F4EC}"),
  );
  const out = parse(raw);
  const q = out.events.find((e) => e.kind === "queued") as Extract<ChatEvent, { kind: "queued" }>;
  assert.ok(q);
  assert.deepEqual(q.texts, ["second queued"]);
});

test("consumed queued messages (queued_command attachments) render as user turns", () => {
  const attLine = (uuid: string, parent: string, prompt: string) => JSON.stringify({
    type: "attachment", uuid, parentUuid: parent, timestamp: NOW(),
    attachment: { type: "queued_command", prompt, commandMode: "prompt" },
  });
  const raw = join(
    uline("u1", null, "main ask"),
    aline("a1", "u1", [{ type: "text", text: "working" }], { stop: "tool_use" }),
    qline("enqueue", "queued ONE"),
    qline("enqueue", "queued TWO"),
    qline("remove"), qline("remove"),                    // both consumed → pending block empty
    attLine("q1", "a1", "queued ONE"),
    attLine("q2", "q1", "queued TWO"),
    attLine("q3", "q2", "<task-notification>bg done</task-notification>"),  // harness plumbing: filtered
    aline("a2", "q3", [{ type: "text", text: "replying to both" }]),
  );
  const out = parse(raw);
  assert.equal(out.events.find((e) => e.kind === "queued"), undefined, "nothing still pending");
  const users = out.events.filter((e) => e.kind === "user") as Extract<ChatEvent, { kind: "user" }>[];
  assert.deepEqual(users.map((u) => u.md), ["main ask", "queued ONE", "queued TWO"]);
  assert.ok(users[1].human && users[2].human, "consumed queued messages are his (blue) bubbles");
});

test("a consumed POSTAL BANNER attachment stays visible, anchored at its own line", () => {
  // Queue-delivered mail used to be dropped here as "harness plumbing" — leaving
  // the message with NO chat line at all, so a timeline message-connector click
  // had nothing to land on (2026-06-12). It must flow through as a user event
  // (hydratePostal later swaps it into a postal-in card) carrying THIS line's
  // uuid — the same uuid romp-events now anchors the absorbed boundary on.
  const banner = "####################\n## \u{1F4EC} from peer_sess \u00b7 10:40\n####################\n"
    + "ASK: do the thing\n<!-- romp-msg-id: 1781000000.11111_22222.TESTHOST -->";
  const raw = join(
    uline("u1", null, "main ask"),
    aline("a1", "u1", [{ type: "text", text: "working" }], { stop: "tool_use" }),
    qline("enqueue", banner),
    qline("remove"),
    JSON.stringify({ type: "attachment", uuid: "qb1", parentUuid: "a1", timestamp: NOW(),
      attachment: { type: "queued_command", prompt: banner, commandMode: "prompt" } }),
    aline("a2", "qb1", [{ type: "text", text: "replied to the peer" }]),
  );
  const out = parse(raw);
  const banners = out.events.filter((e) => e.kind === "user" && e.md.includes("romp-msg-id"));
  assert.equal(banners.length, 1, "the banner attachment renders instead of vanishing");
  assert.equal((banners[0] as any).uuid, "qb1", "anchored at the attachment line");
});

test("todo fold: one checklist, dropped when everything is completed", () => {
  const mk = (status: string) => join(
    uline("u1", null, "do the tasks"),
    aline("a1", "u1", [{ type: "tool_use", id: "t1", name: "TaskCreate", input: { subject: "Build it" } }], { stop: "tool_use" }),
    toolResultLine("u2", "a1", "t1", "Task #1 created successfully"),
    aline("a2", "u2", [{ type: "tool_use", id: "t2", name: "TaskUpdate", input: { taskId: "1", status } }], { stop: "tool_use" }),
    toolResultLine("u3", "a2", "t2", "Updated"),
  );
  const live = parse(mk("in_progress"));
  const todo = live.events.find((e) => e.kind === "todo") as Extract<ChatEvent, { kind: "todo" }>;
  assert.ok(todo, "open task list renders");
  assert.deepEqual(todo.tasks, [{ id: "1", subject: "Build it", activeForm: undefined, status: "in_progress" }]);
  assert.ok(!live.events.some((e) => e.kind === "tool"), "Task tool calls fold away");
  const closed = parse(mk("completed"));
  assert.ok(!closed.events.some((e) => e.kind === "todo"), "fully-done list is dropped");
});

test("system reminders split out of user text", () => {
  const raw = join(
    uline("u1", null, "real question <system-reminder>injected nudge</system-reminder> tail"),
    aline("a1", "u1", [{ type: "text", text: "answer" }]),
  );
  const user = parse(raw).events[0] as Extract<ChatEvent, { kind: "user" }>;
  assert.equal(user.md, "real question  tail");
  assert.deepEqual(user.reminders, ["injected nudge"]);
});

test("Edit tool produces a trimmed line diff", () => {
  const raw = join(
    uline("u1", null, "edit it"),
    aline("a1", "u1", [{
      type: "tool_use", id: "t1", name: "Edit",
      input: { file_path: "/tmp/f.ts", old_string: "a\nb\nc", new_string: "a\nB\nc" },
    }], { stop: "tool_use" }),
    toolResultLine("u2", "a1", "t1", "ok"),
  );
  const tool = parse(raw).events.find((e) => e.kind === "tool") as Extract<ChatEvent, { kind: "tool" }>;
  assert.equal(tool.file, "/tmp/f.ts");
  assert.equal(tool.diff, "  a\n-b\n+B\n  c");
});

test("status: trailing user line means working; mid-stream assistant means working", () => {
  const t1 = parse(join(uline("u1", null, "go")));
  assert.equal(t1.status.working, true);
  const t2 = parse(join(
    uline("u1", null, "go"),
    aline("a1", "u1", [{ type: "text", text: "thinking about it" }], { stop: null }),
  ));
  assert.equal(t2.status.working, true);
});

test("typed image path becomes a thumbnail; [Image: source:] attaches to the paste", () => {
  const out = parse(join(
    uline("u1", null, "look at /tmp/shot.png please"),
    aline("a1", "u1", [{ type: "text", text: "looking" }]),
  ));
  const user = out.events[0] as Extract<ChatEvent, { kind: "user" }>;
  assert.deepEqual(user.images, [{ src: "path:/tmp/shot.png", path: "/tmp/shot.png" }]);

  const pasted = parse(join(
    uline("u1", null, "", {
      blocks: [
        { type: "text", text: "[Image #1] what is this" },
        { type: "image", source: { type: "base64", media_type: "image/png", data: "AAAA" } },
      ],
    }),
    uline("u2", "u1", "[Image: source: /tmp/paste.png]", { promptSource: undefined }),
    aline("a1", "u2", [{ type: "text", text: "a screenshot" }]),
  ));
  const ev = pasted.events[0] as Extract<ChatEvent, { kind: "user" }>;
  assert.equal(ev.md, "what is this");
  assert.equal(ev.images?.length, 1);
  assert.equal(ev.images![0].path, "/tmp/paste.png", "path record attaches to the inline paste");
  assert.equal(pasted.events.filter((e) => e.kind === "user").length, 1, "no second image-only bubble");
});
