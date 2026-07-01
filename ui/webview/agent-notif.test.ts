import { test } from "node:test";
import assert from "node:assert";
import { parseAgentNotif } from "./agent-notif";
import * as fs from "node:fs";
import * as path from "node:path";

// A backgrounded agent's <task-notification>, as it arrives folded into a user turn's reminders (the OUTER
// wrapper already peeled by the kernel's _split_reminders). Synthetic — invented label + result, placeholder
// ids — never real recorded data.
const NOTIF = [
  "<task-id>11111111aaaa2222</task-id>",
  "<tool-use-id>toolu_0abcDEF123</tool-use-id>",
  "<output-file>/tmp/TESTHOST/tasks/11111111aaaa2222.output</output-file>",
  "<status>completed</status>",
  '<summary>Agent "widget audit" came to rest</summary>',
  "<note>A task-notification fires each time this agent comes to rest with no live background children.</note>",
  "<result>Found 3 widgets: **A**, B, C.\n\nA is stale; the rest are fine.</result>",
].join("\n");

test("pulls the agent name, status, and final result out of a task-notification", () => {
  const a = parseAgentNotif(NOTIF);
  assert.ok(a, "a task-notification parses");
  assert.equal(a!.label, "widget audit", "the agent name comes from the summary");
  assert.equal(a!.status, "completed");
  assert.match(a!.result, /Found 3 widgets/, "the result is the agent's final message");
  assert.doesNotMatch(a!.result, /task-id|tool-use-id|output-file|<note>/, "internal ids + boilerplate dropped");
});

test("a plain <system-reminder> (no task-id / Agent summary) is NOT an agent card", () => {
  assert.equal(parseAgentNotif("Your context is getting full. Consider /compact."), null);
  assert.equal(parseAgentNotif("<system-reminder>be concise</system-reminder>"), null);
});

test("falls back gracefully when the summary isn't the canonical Agent \"…\" shape", () => {
  // still a task-notification (has a <task-id>), but the summary lacks the Agent "…" quote
  const a = parseAgentNotif('<task-id>22223333</task-id><status>failed</status><summary>background sweep came to rest</summary>');
  assert.ok(a);
  assert.equal(a!.label, "background sweep", "strips the 'came to rest' tail for a label");
  assert.equal(a!.status, "failed");
  assert.equal(a!.result, "", "no <result> → empty");
});

// Source pin: the renderer routes a parsed notification to its own card and keeps the rest as a fold.
const RENDER = fs.readFileSync(path.join(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("render.ts splits agent notifications out of the reminders fold into agent cards", () => {
  assert.match(RENDER, /const a = parseAgentNotif\(r\);/);
  assert.match(RENDER, /turn\.appendChild\(renderAgentNotif\(a,/);
  assert.match(RENDER, /else plain\.push\(r\);/);
  assert.match(RENDER, /\$\{n\} system reminder/, "the leftover plain reminders still get the fold");
  assert.match(RENDER, /f\.classList\.add\("agent-notif-fold"\)/);
});

test("styles define the agent-notif card in the romp accent", () => {
  assert.match(CSS, /\.agent-notif-fold \.fold-head \{[^}]*var\(--accent\)/);
  assert.match(CSS, /\.agent-notif-body \{/);
});
